"""SEC EDGAR full-text search → bottleneck-language hits (leg 6 of engine/bottleneck.py;
research/THEMATIC_FORESIGHT_DESK.md T1).

WHY. The highest-signal, lowest-cost leg of the 13D HBM pattern is the firm itself saying
the words — "sold out," "capacity constrained," "on allocation," "longer lead times." SEC
EDGAR full-text search is keyless (UA header, <10 req/s, 2001→present) and surfaces the
exact sentence at the filer level. We sweep a phrase dictionary across 10-K/10-Q/8-K,
keep only hits whose ticker is in our curated theme universe (config `themes:`), and store
them so the engine can read mention FREQUENCY + ACCELERATION per theme.

Bounded + drip + cached (mirrors collectors/edgar_rpo): refreshes only when the cache is
stale, caps pages per phrase, reuses collectors.edgar_facts._get_json for the fair-access
UA/pacing. Writes data/edgar/bottleneck_hits.parquet (phrase, form, file_date, cik,
ticker, display_name), deduped by document id. Network failure is non-fatal — the engine's
language leg simply stays None.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import date, timedelta

import pandas as pd

from collectors.edgar_facts import _get_json
from lib import config

log = logging.getLogger("edgar_fts")

FTS_URL = "https://efts.sec.gov/LATEST/search-index"
FORMS = "10-K,10-Q,8-K"
PHRASES = [
    "sold out", "capacity constrained", "supply constrained", "on allocation",
    "longer lead times", "extended lead times", "record backlog",
    "unable to meet demand", "demand exceeds supply", "tight supply",
]
MAX_PAGES = 5              # 10 hits/page -> up to 50 most-recent hits per phrase
LOOKBACK_DAYS = 400        # window swept (covers the engine's 240d accel window + margin)
STALE_DAYS = 7             # skip refresh if the cache's newest fetch is younger than this
# EDGAR display_names come in two shapes, both handled below:
#   legacy   "COMPANY  (TICK, CIK 0001234567)"          — ticker + CIK in ONE paren
#   current  "COMPANY  (TICK)  (CIK 0001234567)"        — ticker and CIK in SEPARATE parens
#            "COMPANY  (TICK, TICK-WT)  (CIK ...)"       — multiple share classes / warrants
#            "Boeing Co (The)  (BA)  (CIK 0000012927)"  — a name-paren BEFORE the ticker paren
# The old regex only matched the legacy single-paren form, so every current-format hit
# parsed to None (silently dropping the entire EDGAR-language leg). The ticker paren is the
# LAST ticker-shaped paren immediately preceding the CIK paren — so an issuer-name paren like
# "(The)" (Boeing/Coca-Cola/Disney/Carlyle) is overwritten by the real "(BA)" paren rather
# than mistaken for the ticker.
_PAREN_RE = re.compile(r"\(([^)]*)\)")
_TICKER_TOK = re.compile(r"^[A-Z][A-Z.\-]{0,6}$")
# common issuer-name-paren tokens that are ticker-SHAPED but are not tickers
_NOT_TICKER = {"THE", "INC", "CO", "CORP", "LP", "LLP", "LLC", "LTD", "PLC", "SA", "AG",
               "NV", "SE", "AB", "NEW", "OLD", "CLASS", "OF", "GROUP", "HLDG", "HLDGS"}


def _tickers_from_display(name: str) -> list[str]:
    """Tickers from the paren immediately preceding the CIK paren (the ticker paren).

    Returns [] when no ticker-shaped token precedes the CIK. Handles the legacy single-paren
    '(TICK, CIK ..)', the current two-paren '(TICK) (CIK ..)', multi-class '(TICK, TICK-WT)',
    and a leading issuer-name paren like '(The)' (which gets overwritten by the real paren)."""
    last: list[str] = []
    for grp in _PAREN_RE.findall(name or ""):
        g = grp.strip()
        if g.upper().startswith("CIK"):
            return last                         # the ticker paren is the one just before CIK
        toks = []
        for tok in g.split(","):
            tok = tok.strip().upper()
            if tok and tok not in _NOT_TICKER and tok != "CIK" and _TICKER_TOK.match(tok):
                toks.append(tok)
        if toks:
            last = toks                         # overwrite earlier name-parens like (The)
    return last                                 # legacy form (CIK lives inside the ticker paren)


def _cache_path():
    p = config.data_dir() / "edgar" / "bottleneck_hits.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _theme_universe() -> set[str]:
    themes = (config.load() or {}).get("themes") or {}
    out: set[str] = set()
    for spec in themes.values():
        out.update(spec.get("tickers") or [])
    return out


def _parse_hit(h: dict) -> dict | None:
    src = h.get("_source") or {}
    names = src.get("display_names") or []
    if not names:
        return None
    cand = _tickers_from_display(names[0])
    if not cand:
        return None
    ticker = cand[0]
    ciks = src.get("ciks") or []
    return {
        "id": h.get("_id"),
        "ticker": ticker,
        "cik": str(ciks[0]) if ciks else None,
        "form": (src.get("root_forms") or [src.get("file_type")] or [None])[0],
        "file_date": src.get("file_date"),
        "display_name": names[0],
    }


def _is_stale(p) -> bool:
    if not p.exists():
        return True
    try:
        df = pd.read_parquet(p)
        if df.empty or "fetched" not in df.columns:
            return True
        newest = pd.to_datetime(df["fetched"]).max().date()
        return (date.today() - newest).days >= STALE_DAYS
    except Exception:  # noqa: BLE001
        return True


def fetch_bottleneck_hits(force: bool = False, phrases: list[str] | None = None) -> pd.DataFrame | None:
    """Sweep the phrase dictionary, filter to the theme universe, upsert the cache.
    Returns the (filtered) frame, or the existing cache when fresh / on total failure."""
    p = _cache_path()
    if not force and not _is_stale(p):
        log.info("edgar_fts cache fresh; skipping refresh")
        return pd.read_parquet(p) if p.exists() else None

    universe = _theme_universe()
    if not universe:
        return None
    enddt = date.today()
    startdt = enddt - timedelta(days=LOOKBACK_DAYS)
    rows: list[dict] = []
    first_request = True
    for phrase in (phrases or PHRASES):
        for page in range(MAX_PAGES):
            url = (f'{FTS_URL}?q="{phrase.replace(" ", "+")}"&forms={FORMS}'
                   f"&startdt={startdt}&enddt={enddt}&from={page * 10}")
            data = _get_json(url, retries=1 if first_request else 3)
            # network down / endpoint unreachable on the very first call -> abort the whole
            # sweep (don't grind through dozens of 40s timeouts) and keep any existing cache.
            if data is None and first_request:
                log.warning("edgar_fts: EDGAR unreachable; keeping existing cache")
                return pd.read_parquet(p) if p.exists() else None
            first_request = False
            hits = ((data or {}).get("hits") or {}).get("hits") or []
            if not hits:
                break
            for h in hits:
                rec = _parse_hit(h)
                if rec and rec["ticker"] in universe:
                    rec["phrase"] = phrase
                    rows.append(rec)
            time.sleep(0.15)               # fair-access pacing (<10 req/s)
            if len(hits) < 10:
                break

    today = date.today().isoformat()
    if not rows:
        log.info("edgar_fts: no in-universe hits this sweep")
        # still stamp a fetch so we don't re-sweep every build on an empty window
        if p.exists():
            return pd.read_parquet(p)
        return None
    new = pd.DataFrame(rows)
    new["fetched"] = today
    if p.exists():
        try:
            old = pd.read_parquet(p)
            new = pd.concat([old, new], ignore_index=True)
        except Exception:  # noqa: BLE001
            pass
    new = new.drop_duplicates(subset=["id", "phrase"]).reset_index(drop=True)
    new.to_parquet(p, index=False)
    log.info("edgar_fts: %d bottleneck-language hits cached -> %s", len(new), p)
    return new


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    df = fetch_bottleneck_hits(force=True)
    print(f"rows: {0 if df is None else len(df)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
