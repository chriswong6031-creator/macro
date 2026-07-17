"""Refresh the `now` stanzas in site/markets_data.js from on-disk parquets.

INTL-47 — markets_data.js is a hand-curated static file; its `now` blocks
(live level / % off ATH / returns) decay silently.  This script re-reads the
parquets we already collect and patches only the `level`, `asOf`, `ath`,
`athDate`, and `pctFromATH` fields for markets where we have a matching
on-disk series.  The archival cycle-turn data and all hand-written prose
fields are left completely untouched.

Ticker map (conservative — only well-tracked local-currency or ETF proxies):
  us      yahoo/_GSPC      S&P 500 (USD points)
  uk      intl/_FTSE       FTSE 100 (GBP points)
  europe  intl/_STOXX      STOXX 600 (EUR points)
  japan   intl/_N225       Nikkei 225 (JPY points)
  taiwan  intl/_TWII       TAIEX (TWD points)
  india   intl/_NSEI       Nifty 50 (INR points)
  hk      yahoo/EWH        iShares MSCI Hong Kong ETF (USD proxy)
  canada  yahoo/EWC        iShares MSCI Canada ETF (USD proxy)
  korea   intl/_KS11       KOSPI (KRW points)
  australia intl/_AXJO     S&P/ASX 200 (AUD points)

China (CSI 300 / 000300.SS) is not available as a clean local series in the
current on-disk store; it is intentionally skipped so the curated hand-value
stays rather than being overwritten with a bad proxy.

Fail-soft: any series that is missing, too short (<30 rows), or has a stale
last print (>14 days) is silently skipped — the hand-written value is preserved.
"""
from __future__ import annotations

import json
import logging
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Ticker map: market-id -> (data folder relative to data/, parquet basename)
# ---------------------------------------------------------------------------
_TICKER_MAP: dict[str, tuple[str, str]] = {
    "us":     ("yahoo", "_GSPC"),
    "uk":     ("intl",  "_FTSE"),
    "europe": ("intl",  "_STOXX"),
    "japan":  ("intl",  "_N225"),
    "taiwan": ("intl",  "_TWII"),
    "india":  ("intl",  "_NSEI"),
    "hk":     ("yahoo", "EWH"),     # USD ETF proxy — level in USD, not HSI points
    "canada": ("yahoo", "EWC"),     # USD ETF proxy — level in USD, not TSX points
    "korea":  ("intl",  "_KS11"),   # KOSPI local-currency points
    "australia": ("intl", "_AXJO"), # S&P/ASX 200 local-currency points
}

_STALE_THRESHOLD_DAYS = 14   # skip a series whose last print is older than this


def _load_series(data_root: Path, folder: str, ticker: str) -> pd.Series | None:
    """Load the `close` column from a parquet; return None on any error."""
    p = data_root / folder / f"{ticker}.parquet"
    if not p.exists():
        log.debug("skip %s/%s — file missing", folder, ticker)
        return None
    try:
        df = pd.read_parquet(p)
        if "close" not in df.columns:
            log.debug("skip %s/%s — no `close` column", folder, ticker)
            return None
        s = df["close"].dropna().astype(float)
        if len(s) < 30:
            log.debug("skip %s/%s — too short (%d rows)", folder, ticker, len(s))
            return None
        last_date = s.index[-1]
        if hasattr(last_date, "date"):
            last_date = last_date.date()
        age_days = (date.today() - last_date).days
        if age_days > _STALE_THRESHOLD_DAYS:
            log.warning("skip %s/%s — last print %s is %dd old (threshold %d)",
                        folder, ticker, last_date, age_days, _STALE_THRESHOLD_DAYS)
            return None
        return s
    except Exception as exc:  # noqa: BLE001
        log.warning("skip %s/%s — read error: %s", folder, ticker, exc)
        return None


def _compute_now_patch(s: pd.Series) -> dict:
    """Return {level, asOf, ath, athDate, pctFromATH} from a price series."""
    cur  = float(s.iloc[-1])
    ath  = float(s.max())
    # find the date of the ATH
    ath_idx = s.idxmax()
    if hasattr(ath_idx, "date"):
        ath_date_str = ath_idx.strftime("%Y-%m")
    else:
        ath_date_str = str(ath_idx)[:7]
    last_idx = s.index[-1]
    if hasattr(last_idx, "date"):
        as_of_str = last_idx.strftime("%Y-%m-%d")
    else:
        as_of_str = str(last_idx)[:10]
    pct_from_ath = round((cur / ath - 1.0) * 100.0, 1)
    return {
        "level":      round(cur, 2),
        "asOf":       as_of_str,
        "ath":        round(ath, 2),
        "athDate":    ath_date_str,
        "pctFromATH": pct_from_ath,
    }


def _patch_js(js_text: str, market_id: str, patch: dict) -> str:
    """Patch `now` block fields for the given market_id inside the JS string.

    Targets the first `"now": {...}` that follows the market's `"id": "X"` line.
    Only the fields listed in `patch` are updated; all other fields are kept as-is.
    """
    # Locate the market block (the '"id": "X"' occurrence)
    id_pat = re.compile(r'"id"\s*:\s*"' + re.escape(market_id) + r'"')
    m = id_pat.search(js_text)
    if not m:
        log.warning("market id %r not found in JS — skipping patch", market_id)
        return js_text

    # Find the next '"now": {' after that position
    now_start = js_text.find('"now"', m.end())
    if now_start == -1:
        log.warning("no 'now' block found for market %r — skipping", market_id)
        return js_text

    # Find the opening brace
    brace_open = js_text.find('{', now_start)
    if brace_open == -1:
        return js_text

    # Find matching closing brace (handles nested braces, though now blocks are flat)
    depth = 0
    brace_close = brace_open
    for i in range(brace_open, len(js_text)):
        if js_text[i] == '{':
            depth += 1
        elif js_text[i] == '}':
            depth -= 1
            if depth == 0:
                brace_close = i
                break

    now_body = js_text[brace_open + 1:brace_close]

    # Patch each field: replace its value while keeping structure intact
    for field, new_val in patch.items():
        # Match: "field": <old-value> (string, number, or null)
        field_pat = re.compile(
            r'("' + re.escape(field) + r'"\s*:\s*)(["\d\-\.null][^,\n}]*)'
        )
        if isinstance(new_val, str):
            replacement = r'\g<1>"' + new_val.replace('"', r'\"') + '"'
        elif new_val is None:
            replacement = r'\g<1>null'
        else:
            replacement = r'\g<1>' + str(new_val)
        patched, n_subs = field_pat.subn(replacement, now_body)
        if n_subs:
            now_body = patched
        else:
            log.debug("field %r not found in now block for %r", field, market_id)

    return js_text[:brace_open + 1] + now_body + js_text[brace_close:]


def refresh(data_root: Path, markets_data_js: Path, *, dry_run: bool = False) -> int:
    """Load parquets, patch now blocks, write updated markets_data.js.

    Returns the number of markets successfully updated.
    """
    if not markets_data_js.exists():
        log.error("markets_data.js not found at %s", markets_data_js)
        return 0

    js_text = markets_data_js.read_text(encoding="utf-8")
    updated = 0

    for market_id, (folder, ticker) in _TICKER_MAP.items():
        s = _load_series(data_root, folder, ticker)
        if s is None:
            continue
        patch = _compute_now_patch(s)
        js_text = _patch_js(js_text, market_id, patch)
        log.info("patched now block for %s (%s/%s): level=%.2f asOf=%s pctFromATH=%.1f%%",
                 market_id, folder, ticker,
                 patch["level"], patch["asOf"], patch["pctFromATH"])
        updated += 1

    # Update the top-level MARKET_META.asOf to today
    today_str = date.today().isoformat()
    js_text = re.sub(
        r'("asOf"\s*:\s*)"[^"]*"',
        r'\g<1>"' + today_str + '"',
        js_text,
        count=1,   # only the first one (in MARKET_META)
    )

    if not dry_run:
        markets_data_js.write_text(js_text, encoding="utf-8")
        log.info("wrote updated markets_data.js (asOf=%s, %d markets patched)", today_str, updated)

    return updated


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    try:
        from lib import config
        root = config.ROOT
        data_root = config.data_dir()
    except Exception:  # running outside the normal project path
        root = Path(__file__).parent.parent
        data_root = root / "data"

    site_dir = root / "site"
    markets_data_js = site_dir / "markets_data.js"

    updated = refresh(data_root, markets_data_js)
    if updated == 0:
        log.warning("no markets updated — all series missing or stale")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
