"""Dead-name DELISTING-REASON detection + bankruptcy imputation — the bankruptcy
tail of the survivorship de-bias (Phase 1A+ of research/INSTITUTIONAL_ROADMAP.md).

THE RESIDUAL BIAS this closes. collectors/edgar_deadname_prices recovers delisted
daily closes, but the names free sources DO serve skew to ACQUISITIONS (the price
ran up to a deal and stopped — a realized winner); the BANKRUPTCY tail (price→0) is
under-served, so the recovered panel keeps a mild UP bias. `price_coverage()` stamps
that caveat and notes "a −100% bankruptcy imputation needs a delisting-reason feed
(Ch.11 8-Ks) not yet wired." This module wires it.

HOW (detect). For each resolved dead CIK we read the structured SEC submissions feed
(https://data.sec.gov/submissions/CIK##########.json — keyless, reachable
everywhere, the `items` field is machine-readable, not text-parsed) and look for an
8-K carrying **Item 1.03 (Bankruptcy or Receivership)**. That positively flags a
bankruptcy delisting AND carries the SEC `filed` date — the moment the wipeout
became PUBLIC, the only date at which a −100% is leak-free knowable. Each dead name
is classified:
  * bankruptcy  ← an 8-K with Item 1.03 (EARLIEST such filing = first knowable)
  * acquisition ← the curated M&A/rename CIK seed, or an 8-K Item 5.01 (Change in
                  Control of Registrant — the target reporting it was acquired out)
  * unknown     ← neither positive signal present
Bankruptcy wins a tie (a name acquired out of Chapter 11 still wiped its old equity,
which is what the imputation must capture). A long-dead filer's "recent" filings ARE
its final filings (it stopped filing at delisting), so the death 8-K lives there — no
overflow-file crawl needed for dead names.

HOW (impute). For a flagged bankruptcy that HAS a recovered price anchor, append a
terminal close of ~0 (a penny) into dead_name_prices.parquet, source=
"imputed_bankruptcy", so the leak-free backtest realizes the −100% wipe instead of a
survivorship gap. Two disciplines:
  * LEAK-FREE — the −100% is knowable only at the 8-K `filed` date, so the terminal
    is stamped at max(filed, last_close) and placed STRICTLY AFTER the last real bar
    (never overwriting realized market data, never before the bankruptcy is public).
  * MIS-RESOLUTION GUARD — a true bankruptcy 8-K lands AROUND the index-removal
    date; we only impute when `filed` is near the membership end_date, so a
    ticker-reuse / renamed-survivor CIK that files an unrelated later 1.03 can't
    inject a phantom −100% onto the old ticker's prices.

KEYLESS · resumable · drip-capped · RESILIENT — no-op when data.sec.gov is blocked
(a name we can't fetch is simply left uncached and retried next run), exactly like
the companyfacts drip in collectors/edgar_deadnames. NOTHING in the live stack
depends on it; it only de-biases the dead-name price panel.
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timezone

import pandas as pd

from collectors.edgar_deadname_prices import _prices_path
from collectors.edgar_deadnames import _load_cik_cache, dead_universe
from lib import config

log = logging.getLogger(__name__)

SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{:010d}.json"
REFRESH_DAYS = 30                         # delisting reason is static; refresh rarely

ITEM_BANKRUPTCY = "1.03"                  # 8-K Item 1.03 — Bankruptcy or Receivership
ITEM_CHANGE_CONTROL = "5.01"              # 8-K Item 5.01 — Changes in Control of Registrant
_ITEM_RE = re.compile(r"\d\.\d{2}")
_FORMS_8K = {"8-K", "8-K/A"}

# ~0 terminal close. A penny is the canonical near-total-loss floor (bankrupt equity
# recovers pennies on the dollar at best); a −100% wipe from any realistic last close.
_TERMINAL_CLOSE = 0.01

# A real Chapter-11 8-K lands around the index-removal date. Only impute the terminal
# when `filed` is within this window of the membership end_date — rejects a renamed
# survivor / reused-ticker CIK whose unrelated later 1.03 would otherwise inject a
# phantom −100% onto the dead ticker's old prices.
_BK_NEAR_END_BEFORE = 540                 # days before end_date filing may precede removal
_BK_NEAR_END_AFTER = 180                  # days after end_date (S&P removal can lag the filing)


# --------------------------------------------------------------------------- #
# resilient submissions fetch (mirrors collectors/edgar_deadnames._get_json)
# --------------------------------------------------------------------------- #
def _headers() -> dict:
    return {"User-Agent": config.load()["edgar"]["user_agent"],
            "Accept-Encoding": "gzip, deflate"}


def _get_submissions(cik: int, retries: int = 3) -> dict | None:
    """data.sec.gov submissions JSON for one CIK. Returns None on 404 or after
    exhausted retries — the caller leaves an unfetched name uncached so it retries
    next run (true no-op when blocked)."""
    import requests
    url = SUBMISSIONS_URL.format(int(cik))
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=_headers(), timeout=40)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()
        except Exception as e:  # noqa: BLE001 — tolerate per-filer failure
            if attempt == retries - 1:
                log.debug("submissions GET failed CIK%s: %s", cik, e)
                return None
            time.sleep(1.5 * (attempt + 1))
    return None


# --------------------------------------------------------------------------- #
# classification
# --------------------------------------------------------------------------- #
def _classify_filings(recent: dict, cik_method: str) -> dict:
    """Classify one filer's delisting reason from its `recent` submissions block.

    `recent` carries parallel arrays (form / items / filingDate / accessionNumber).
    Returns {reason, method, bankruptcy_date, bankruptcy_accession, items_seen,
    n_8k}. bankruptcy_date is the EARLIEST 8-K Item-1.03 filing (first the wipeout
    is knowable → leak-free anchor)."""
    forms = recent.get("form") or []
    items = recent.get("items") or []
    dates = recent.get("filingDate") or []
    accns = recent.get("accessionNumber") or []

    def _at(arr, i):
        return arr[i] if i < len(arr) else None

    bk_date = bk_accn = None
    change_control = False
    items_seen: set[str] = set()
    n_8k = 0
    for i in range(len(forms)):
        if _at(forms, i) not in _FORMS_8K:
            continue
        n_8k += 1
        codes = set(_ITEM_RE.findall(_at(items, i) or ""))
        items_seen |= codes
        if ITEM_BANKRUPTCY in codes:
            d = _at(dates, i)
            if d and (bk_date is None or d < bk_date):   # ISO dates sort lexically
                bk_date, bk_accn = d, _at(accns, i)
        if ITEM_CHANGE_CONTROL in codes:
            change_control = True

    if bk_date:
        reason, method = "bankruptcy", "8k_item_1.03"
    elif cik_method == "seed":
        reason, method = "acquisition", "seed"
    elif change_control:
        reason, method = "acquisition", "8k_item_5.01"
    else:
        reason, method = "unknown", "none"
    return {"reason": reason, "method": method,
            "bankruptcy_date": bk_date, "bankruptcy_accession": bk_accn,
            "items_seen": sorted(items_seen), "n_8k": int(n_8k)}


# --------------------------------------------------------------------------- #
# detection drip (resumable, cached, drip-capped, resilient)
# --------------------------------------------------------------------------- #
def _delisting_path():
    p = config.data_dir() / "edgar" / "dead_name_delisting.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _load_delisting_cache() -> dict:
    p = _delisting_path()
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:  # noqa: BLE001
            return {}
    return {}


def detect_delisting_reasons(force: bool = False, max_new: int = 200,
                             tickers: list[str] | None = None) -> dict:
    """Classify each resolved dead CIK acquisition / bankruptcy / unknown from its
    8-K item codes, resumably, caching to data/edgar/dead_name_delisting.json. Drip-
    capped (`max_new`); skips names scanned within REFRESH_DAYS. RESILIENT — a name
    data.sec.gov declines is left uncached (retried next run), never raises."""
    cache = _load_cik_cache()
    resolved = {t: v for t, v in cache.items() if v.get("cik")}
    if tickers is not None:
        resolved = {t: v for t, v in resolved.items() if t in tickers}
    if not resolved:
        log.warning("detect_delisting_reasons: no resolved CIKs — run resolve_dead_ciks first")
        return {}

    out = _load_delisting_cache()

    def stale(t: str) -> bool:
        if force:
            return True
        rec = out.get(t)
        if not rec or not rec.get("at"):
            return True
        try:
            return (datetime.now(timezone.utc) - pd.to_datetime(rec["at"])).days > REFRESH_DAYS
        except Exception:  # noqa: BLE001
            return True

    todo = [t for t in resolved if stale(t)][:max_new]
    log.info("delisting reasons: %d resolved, scanning %d (cap %d)", len(resolved), len(todo), max_new)

    now = datetime.now(timezone.utc).isoformat()
    scanned = 0
    for t in todo:
        data = _get_submissions(int(resolved[t]["cik"]))
        time.sleep(0.12)                  # SEC fair-access pacing (<10 req/s)
        if data is None:
            continue                      # blocked / transient — leave uncached, retry next run
        recent = (data.get("filings") or {}).get("recent") or {}
        info = _classify_filings(recent, resolved[t].get("method", ""))
        info["at"] = now
        out[t] = info
        scanned += 1

    if scanned:
        _delisting_path().write_text(json.dumps(out, indent=0, sort_keys=True))
    n_bk = sum(1 for v in out.values() if v.get("reason") == "bankruptcy")
    log.info("delisting reasons: +%d scanned, %d bankruptcies / %d classified",
             scanned, n_bk, len(out))
    return out


def delisting_breakdown(universe: list[str] | None = None) -> dict:
    """{bankruptcy, acquisition, unknown, n_classified} over the dead universe, from
    the cached 8-K reason feed. The honest delisting-reason split every consumer
    should display alongside dead-name price coverage."""
    uni = set(dead_universe()) if universe is None else set(universe)
    cache = _load_delisting_cache()
    counts = {"bankruptcy": 0, "acquisition": 0, "unknown": 0}
    for t, info in cache.items():
        if t not in uni:
            continue
        r = info.get("reason")
        if r in counts:
            counts[r] += 1
    counts["n_classified"] = sum(counts[k] for k in ("bankruptcy", "acquisition", "unknown"))
    return counts


# --------------------------------------------------------------------------- #
# imputation — append the realized −100% terminal for flagged bankruptcies
# --------------------------------------------------------------------------- #
def _end_dates() -> dict:
    """ticker -> latest membership end_date (Timestamp), for the mis-resolution guard."""
    try:
        m = pd.read_parquet(config.data_dir() / "breadth" / "sp1500_pit_membership.parquet",
                            columns=["ticker", "end_date"])
    except Exception:  # noqa: BLE001
        return {}
    m = m.dropna(subset=["end_date"])
    if m.empty:
        return {}
    return pd.to_datetime(m.groupby("ticker")["end_date"].max()).to_dict()


def impute_bankruptcies() -> pd.DataFrame:
    """Append an imputed ~0 terminal close for every flagged bankruptcy that has a
    recovered price anchor, so the leak-free backtest sees the realized −100% instead
    of a survivorship gap. Leak-free + idempotent (re-imputation drops prior imputed
    rows first). Returns the rewritten dead_name_prices table (unchanged if there is
    nothing to anchor)."""
    cache = _load_delisting_cache()
    bankrupt = {t: v for t, v in cache.items()
                if v.get("reason") == "bankruptcy" and v.get("bankruptcy_date")}
    p = _prices_path()
    if not p.exists():
        log.info("impute_bankruptcies: no dead_name_prices.parquet yet — nothing to anchor")
        return pd.DataFrame()
    prices = pd.read_parquet(p)
    if prices.empty:
        return prices
    prices["date"] = pd.to_datetime(prices["date"])
    # idempotent: rebuild imputations from scratch each run
    real = prices[prices["source"] != "imputed_bankruptcy"].copy()
    end_dates = _end_dates()

    rows, imputed, skipped_far = [], [], 0
    for t, info in bankrupt.items():
        sub = real[real["ticker"] == t]
        if sub.empty:
            continue                      # no price anchor → can't realize a −100% (no from-price)
        filed = pd.to_datetime(info["bankruptcy_date"], errors="coerce")
        if pd.isna(filed):
            continue
        # mis-resolution guard: the death 8-K must land near the index-removal date
        end = end_dates.get(t)
        if end is not None and not (
                end - pd.Timedelta(days=_BK_NEAR_END_BEFORE) <= filed
                <= end + pd.Timedelta(days=_BK_NEAR_END_AFTER)):
            skipped_far += 1
            continue
        last_date = sub["date"].max()
        # leak-free: terminal knowable at `filed`; place strictly AFTER the last real
        # bar so the −100% is a NEW subsequent point (never overwrites realized data,
        # never before the bankruptcy is public).
        terminal = max(filed, last_date)
        if terminal <= last_date:
            terminal = last_date + pd.Timedelta(days=1)
        rows.append({"ticker": t, "date": terminal, "close": _TERMINAL_CLOSE,
                     "source": "imputed_bankruptcy"})
        imputed.append(t)

    out = pd.concat([real, pd.DataFrame(rows)], ignore_index=True) if rows else real
    out = out.sort_values(["ticker", "date"]).reset_index(drop=True)
    out.to_parquet(p)
    log.info("impute_bankruptcies: %d bankruptcy names, %d imputed, %d skipped (8-K far from end_date)",
             len(bankrupt), len(imputed), skipped_far)
    return out
