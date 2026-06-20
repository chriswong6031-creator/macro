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
standard disclosure; names without the tag simply yield no rows. Writes
data/edgar/rpo.parquet (ticker, fy, rpo, revenue, as_of). Drip + cache + resilient.
"""
from __future__ import annotations

import json
import logging
import time

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


def _cache_path():
    p = config.data_dir() / "edgar" / "rpo.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


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
    """Tickers in the RPO-relevant baskets (software / agents)."""
    p = config.data_dir() / "baskets" / "membership.json"
    if not p.exists():
        return []
    baskets = (json.loads(p.read_text()).get("baskets") or {})
    out: set[str] = set()
    for slug in RPO_BASKETS:
        for m in (baskets.get(slug, {}).get("members") or []):
            if not m.get("removed") and m.get("ticker"):
                out.add(m["ticker"])
    return sorted(out)


def fetch_rpo(max_new: int = 80, tickers: list[str] | None = None) -> pd.DataFrame:
    """Drip RPO for the software universe into data/edgar/rpo.parquet. Best-effort:
    re-fetches names absent or older than ~25 days; never raises."""
    cache = _cache_path()
    existing = pd.read_parquet(cache) if cache.exists() else pd.DataFrame()
    cik = _cik_map()
    universe = tickers or _rpo_universe()
    now = pd.Timestamp.utcnow().tz_localize(None)

    def stale(t: str) -> bool:
        if existing.empty or t not in set(existing.get("ticker", [])):
            return True
        rows = existing[existing["ticker"] == t]
        try:
            return (now - pd.to_datetime(rows["as_of"]).max()).days >= 25
        except Exception:  # noqa: BLE001
            return True

    todo = [t for t in universe if t in cik and stale(t)][:max_new]
    log.info("edgar_rpo: %d in universe, %d with CIK, fetching %d", len(universe), len(cik), len(todo))
    fresh = []
    for t in todo:
        try:
            for rec in _rpo_for(cik[t]):
                fresh.append({"ticker": t, **rec, "as_of": now.isoformat()})
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.debug("rpo %s failed: %s", t, e)
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
