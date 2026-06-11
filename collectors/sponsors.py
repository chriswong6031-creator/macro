"""Sector SPDR daily shares outstanding -> ETF flows, computed not scraped.

One fetch of SSGA's fundfinder JSON covers all US SSGA ETFs. Shares
outstanding is exact from AUM/NAV (AUM = SO x NAV, same as-of date). The
engine/report computes flow(t) = delta(SO) x NAV(t), the same
creation/redemption signal paid vendors sell, at T+1.

Stored per fund (data/flows/<TICKER>.parquet): nav, aum_mn, so_mn.
History accumulates one row per trading day from first deployment — there is
no free historical SO source, so percentile work matures as data accrues.
"""
from __future__ import annotations

import logging

import pandas as pd

from collectors.base import Adapter
from lib import config

log = logging.getLogger(__name__)

FUNDFINDER = ("https://www.ssga.com/bin/v1/ssmp/fund/fundfinder"
              "?country=us&language=en&role=intermediary&product=etfs&ui=fund-finder")


class SectorFlowAdapter(Adapter):
    name = "sector_flows"
    group = "flows"

    def __init__(self) -> None:
        self.cfg = config.load()["sponsors"]

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        r = self.http_get(FUNDFINDER, retries=self.cfg["retries"], timeout=90,
                          headers={"User-Agent": "Mozilla/5.0 (research)"})
        funds = r.json()["data"]["funds"]["etfs"]["datas"]
        wanted = set(self.cfg["sector_funds"])
        frames: dict[str, pd.DataFrame] = {}
        for d in funds:
            tick = str(d.get("fundTicker", "")).strip()
            if tick not in wanted:
                continue
            try:
                nav = float(d["nav"][1])
                aum_mn = float(d["aum"][1])
                asof = pd.Timestamp(d["asOfDate"][1])
                if nav <= 0 or aum_mn <= 0:
                    raise ValueError(f"bad nav/aum {nav}/{aum_mn}")
                frames[tick] = pd.DataFrame(
                    {"nav": [nav], "aum_mn": [aum_mn], "so_mn": [aum_mn / nav]},
                    index=[asof])
            except Exception as e:  # noqa: BLE001
                log.warning("sector_flows: %s parse failed: %s", tick, e)
        missing = wanted - set(frames)
        if missing:
            log.warning("sector_flows: missing funds %s", sorted(missing))
        if len(frames) < len(wanted) * 0.7:
            raise RuntimeError(f"only {len(frames)}/{len(wanted)} sector funds parsed")
        return frames


def flows_table() -> pd.DataFrame | None:
    """Daily flow estimate per sector fund: delta(SO) x NAV ($mn)."""
    from lib import store
    cfg = config.load()["sponsors"]
    rows = []
    for t in cfg["sector_funds"]:
        df = store.read("flows", t)
        if df is None or len(df) < 2:
            continue
        d_so = df["so_mn"].diff()
        flow_mn = d_so * df["nav"]
        rows.append(pd.DataFrame({f"{t}_flow_mn": flow_mn}))
    if not rows:
        return None
    return pd.concat(rows, axis=1)
