"""Per-stock Southbound Stock-Connect holdings — HK's marginal-buyer smart-money feed.

Mainland money buying HK-listed shares via Southbound Connect (港股通) is HK's dominant
marginal buyer; per research/CHINA_HK_STOCK_SIGNALS.md (Phase 4, never built) the
per-NAME holding is "a China-specific smart-money signal with no US analog, free from
Eastmoney". This collector snapshots it daily from the Eastmoney datacenter — the same
``datacenter-web.eastmoney.com`` host the China leaderboard in build_china already uses.

The heavy lifting + the per-stock panel persistence live in engine/hk_southbound_stocks
(``fetch_snapshot`` writes the long-form cross-section to data/hk_southbound/holdings.parquet,
keyed by (date, ticker) so a per-name flow history accrues for future deep-history
validation). This adapter just drives that fetch in the COLLECT step (so the snapshot is
committed by the daily 'commit data' step) and returns a one-row daily SUMMARY for the
standard store + staleness tracking. The conviction engine reads holdings.parquet.
"""
from __future__ import annotations

import logging

import pandas as pd

from collectors.base import Adapter

log = logging.getLogger(__name__)


class HkSouthboundHoldingsAdapter(Adapter):
    name = "hk_southbound_holdings"
    group = "hk_southbound"
    stale_after_days = 5            # Connect-holdings disclosure is daily on HK trading days

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        from engine import hk_southbound_stocks as sb
        snap = sb.fetch_snapshot()          # persists the per-stock panel (holdings.parquet)
        if snap is None or snap.empty:
            raise RuntimeError("hk_southbound: Eastmoney datacenter returned no rows")
        # one-row daily SUMMARY for the standard date-indexed store (the per-stock panel is
        # persisted separately by fetch_snapshot). Gives last_good_date + a coverage trace.
        chg5 = pd.to_numeric(snap.get("chg5_v"), errors="coerce")
        hold = pd.to_numeric(snap.get("hold_mktcap"), errors="coerce")
        day = pd.Timestamp(snap["date"].iloc[0]).normalize()
        row = {
            "n_names": int(len(snap)),
            "total_hold_b": round(float(hold.sum()) / 1e9, 1) if hold.notna().any() else None,
            "net_chg5_b": round(float(chg5.sum()) / 1e9, 1) if chg5.notna().any() else None,
            "n_adding": int((chg5 > 0).sum()),
        }
        return {"summary": pd.DataFrame([row], index=[day])}
