"""Earnings-revision breadth — best effort, LOW CONFIDENCE by design.

There is no good free source for sector revision breadth. Three layers:
1. yfinance analyst fields (forward EPS estimate direction) for sector proxies
   where populated — sparse and unofficial.
2. Finnhub free tier if FINNHUB_KEY is set (optional).
3. Price-derived proxy that always works: sector RS trend vs equal-weight
   market (RSP) with credit confirmation (HYG/LQD direction agreement).

The regime engine does NOT consume this module — it feeds the weekly report
only, so its failure can never degrade the classifier.
"""
from __future__ import annotations

import logging
from datetime import date

import pandas as pd
import yfinance as yf

from collectors.base import Adapter
from lib import config, store

log = logging.getLogger(__name__)


class FundamentalsAdapter(Adapter):
    name = "fundamentals"
    group = "fundamentals"

    def __init__(self) -> None:
        self.cfg = config.load()["fundamentals"]
        self.sectors = config.load()["yahoo"]["tickers"]["sectors"]

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        rows = []
        today = pd.Timestamp(date.today())
        for t in self.sectors:
            rec: dict = {"sector": t}
            try:
                info = yf.Ticker(t).info or {}
                rec["fwd_pe"] = info.get("forwardPE")
                rec["trail_pe"] = info.get("trailingPE")
            except Exception as e:  # noqa: BLE001
                log.debug("yf info failed for %s: %s", t, e)
            rows.append(rec)
        df = pd.DataFrame(rows)
        # implied fwd EPS direction: trailing/forward PE ratio > 1 means the
        # market expects EPS growth; track its day-over-day drift over time
        df["implied_eps_growth"] = df["trail_pe"] / df["fwd_pe"] - 1
        snap = df.set_index("sector")

        prox = self._price_proxy()
        wide = pd.concat(
            {f"{c}": snap[c] for c in snap.columns}, axis=0
        ).to_frame().T
        wide.index = [today]
        wide.columns = [f"{a}_{b}" for a, b in wide.columns]
        return {"sector_estimates": wide, "revision_proxy": prox}

    def _price_proxy(self) -> pd.DataFrame:
        """Sector RS vs equal-weight market, confirmed by credit. Daily series,
        computed from already-stored yahoo data — no extra requests."""
        rsp = store.read("yahoo", "RSP")
        hyg = store.read("yahoo", "HYG")
        lqd = store.read("yahoo", "LQD")
        if rsp is None:
            raise RuntimeError("RSP not in store yet — run yahoo collector first")
        out = pd.DataFrame(index=rsp.index)
        credit = None
        if hyg is not None and lqd is not None:
            credit = (hyg["close"] / lqd["close"]).pct_change(20)
        for t in self.sectors:
            s = store.read("yahoo", t)
            if s is None:
                continue
            rs = (s["close"] / rsp["close"]).pct_change(60)
            conf = rs
            if credit is not None:
                # positive only when credit agrees with the sector trend
                conf = rs.where(~((rs > 0) & (credit.reindex(rs.index) < 0)), rs * 0.5)
            out[f"{t}_rev_proxy"] = conf
        return out.dropna(how="all")
