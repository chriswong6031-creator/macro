"""SEC EDGAR → Remaining Performance Obligation (RPO) per stock — the demand-side
forward-bookings signal for the Demand Desk (memory demand-desk-divergence, L2).

WHY RPO. For subscription / long-contract businesses (enterprise SaaS especially),
Remaining Performance Obligation = signed, contracted revenue NOT yet recognized.
It is the company's own number, but it is CONTRACTUALLY LOCKED and leads recognized
revenue by several quarters — far more forward-looking than the trailing income
statement, and much harder to manage than guidance language. RPO growth running
ahead of (or behind) the priced consensus is exactly the L2 "independent
observable" the Demand Context panel exists to surface, for the software complex
that the customer-capex chains don't reach.

This reuses the proven edgar_facts fetch plumbing (companyfacts API + fair-access
pacing + ticker→CIK map). Bounded to the software/agents baskets where RPO is a
standard disclosure; names without the tag simply yield no rows. Extended (W5a
follow-up) to union in all config.themes member tickers so the Foresight Desk
leg8_member_backlog can compute per-theme medians. Writes data/edgar/rpo.parquet
(ticker, fy, rpo, revenue, as_of). Drip + cache + resilient.

NEGATIVE CACHE (rpo_no_data.json): tickers that return no RPO rows from EDGAR are
recorded with a timestamp so the drip budget is not wasted re-probing them on every
run. TTL = NO_DATA_TTL_DAYS (default 90 days — RPO is an annual disclosure, so a
ticker that doesn't tag it today almost certainly won't for months).
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta, timezone

import pandas as pd

from collectors.edgar_facts import FACTS_URL, _annual, _cik_map, _get_json
from lib import config

log = logging.getLogger("edgar_rpo")

# RPO is an INSTANT balance (remaining obligation at period end). Fallback chain
# across the tags filers have used.
RPO_TAGS = ["RevenueRemainingPerformanceObligation"]
# Recognized revenue, for the RPO/revenue coverage ratio (a FLOW concept).
REV_TAGS = ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues",
            "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet"]
# Baskets where RPO/contracted-bookings is a meaningful, standard disclosure.
RPO_BASKETS = ("ai_software", "non_ai_software", "ai_agents")
KEEP_YEARS = 6

# TTL for the negative cache (known-empty tickers). 90 days: RPO is annual and
# a non-filer today is very unlikely to start filing within one quarter.
NO_DATA_TTL_DAYS = 90


def _cache_path():
    p = config.data_dir() / "edgar" / "rpo.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _no_data_cache_path():
    p = config.data_dir() / "edgar" / "rpo_no_data.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _load_no_data_cache() -> dict[str, str]:
    """Load the negative cache. Returns {ticker: iso_timestamp_str}."""
    p = _no_data_cache_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return {}


def _save_no_data_cache(cache: dict[str, str]) -> None:
    """Persist the negative cache atomically."""
    _no_data_cache_path().write_text(json.dumps(cache, indent=2, sort_keys=True))


def _is_no_data_fresh(ts_str: str) -> bool:
    """Return True if the negative-cache entry is within TTL (suppress re-probe)."""
    try:
        recorded = datetime.fromisoformat(ts_str).replace(tzinfo=timezone.utc)
        return datetime.now(tz=timezone.utc) - recorded < timedelta(days=NO_DATA_TTL_DAYS)
    except Exception:  # noqa: BLE001
        return False


def _concept(usgaap: dict, names: list[str], instant: bool) -> dict[int, float]:
    combined: dict[int, float] = {}
    for nm in names:
        node = usgaap.get(nm)
        if not node:
            continue
        entries = node.get("units", {}).get("USD")
        if not entries:
            continue
        for fy, val in _annual(entries, instant=instant).items():
            combined.setdefault(fy, val)
    return combined


def _rpo_for(cik: int) -> list[dict]:
    data = _get_json(FACTS_URL.format(cik))
    time.sleep(0.12)                       # SEC fair-access pacing (<10 req/s)
    if not data:
        return []
    usgaap = (data.get("facts") or {}).get("us-gaap") or {}
    if not usgaap:
        return []
    rpo = _concept(usgaap, RPO_TAGS, instant=True)
    if not rpo:
        return []                          # no RPO disclosure → nothing to record
    rev = _concept(usgaap, REV_TAGS, instant=False)
    years = sorted(rpo)[-KEEP_YEARS:]
    return [{"fy": int(fy), "rpo": float(rpo[fy]),
             "revenue": float(rev[fy]) if fy in rev else None} for fy in years]


def _rpo_universe() -> list[str]:
    """Tickers in the RPO-relevant baskets (software / agents) UNION all config.themes members.

    Self-maintaining: theme-member changes in config.yml flow automatically on the
    next collect run (mirrors the pattern in collectors/yahoo.py). Many industrials
    don't tag RevenueRemainingPerformanceObligation — the per-ticker failure handling
    in _rpo_for covers that gracefully (returns []). The negative cache
    (rpo_no_data.json) prevents the drip budget being wasted re-probing known-empty
    tickers on every run.

    Never removes existing names — only additive.
    """
    out: set[str] = set()

    # --- leg A: software/agents baskets (original universe) ---
    p = config.data_dir() / "baskets" / "membership.json"
    if p.exists():
        try:
            baskets = (json.loads(p.read_text()).get("baskets") or {})
        except Exception:  # noqa: BLE001
            baskets = {}
        for slug in RPO_BASKETS:
            for m in (baskets.get(slug, {}).get("members") or []):
                if not m.get("removed") and m.get("ticker"):
                    out.add(m["ticker"])

    # --- leg B: all config.themes members (W5a Foresight Desk leg8 unlock) ---
    # (theme or {}): a bare `some_theme:` YAML key yields None — never crash collect
    for theme in (config.load().get("themes") or {}).values():
        for t in ((theme or {}).get("tickers") or []):
            if t:
                out.add(t)

    return sorted(out)


def fetch_rpo(max_new: int = 80, tickers: list[str] | None = None) -> pd.DataFrame:
    """Drip RPO for the extended universe into data/edgar/rpo.parquet. Best-effort:
    re-fetches names absent or older than ~25 days; skips known-empty tickers within
    the NO_DATA_TTL_DAYS window; never raises."""
    cache = _cache_path()
    existing = pd.read_parquet(cache) if cache.exists() else pd.DataFrame()
    cik = _cik_map()
    universe = tickers or _rpo_universe()
    now = pd.Timestamp.utcnow().tz_localize(None)
    now_iso = datetime.now(tz=timezone.utc).isoformat()

    # Negative cache: tickers confirmed to have no RPO tag in EDGAR
    no_data = _load_no_data_cache()

    def stale(t: str) -> bool:
        if existing.empty or t not in set(existing.get("ticker", [])):
            return True
        rows = existing[existing["ticker"] == t]
        try:
            return (now - pd.to_datetime(rows["as_of"]).max()).days >= 25
        except Exception:  # noqa: BLE001
            return True

    def skip_no_data(t: str) -> bool:
        """True if ticker is in the negative cache and within TTL."""
        ts = no_data.get(t)
        return ts is not None and _is_no_data_fresh(ts)

    todo = [t for t in universe if t in cik and stale(t) and not skip_no_data(t)][:max_new]
    log.info(
        "edgar_rpo: %d in universe, %d with CIK, %d neg-cached, fetching %d",
        len(universe), len(cik), sum(1 for t in universe if skip_no_data(t)), len(todo),
    )
    fresh = []
    no_data_updated = False
    for t in todo:
        try:
            rows = _rpo_for(cik[t])
            if rows:
                for rec in rows:
                    fresh.append({"ticker": t, **rec, "as_of": now.isoformat()})
                # Clear from negative cache if it was there (ticker started filing)
                if t in no_data:
                    del no_data[t]
                    no_data_updated = True
            else:
                # No RPO tag — record in negative cache to avoid re-probing
                no_data[t] = now_iso
                no_data_updated = True
                log.debug("edgar_rpo: %s has no RPO tag — added to negative cache", t)
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.debug("rpo %s failed: %s", t, e)
    if no_data_updated:
        _save_no_data_cache(no_data)
    if fresh:
        fdf = pd.DataFrame(fresh)
        keep = existing[~existing["ticker"].isin(fdf["ticker"])] if not existing.empty else existing
        out = pd.concat([keep, fdf], ignore_index=True)
        out.to_parquet(cache, index=False)
    else:
        out = existing
    n_t = out["ticker"].nunique() if not out.empty else 0
    log.info("edgar_rpo: cache now %d tickers, %d ticker-years", n_t, len(out))
    return out


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    fetch_rpo()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
