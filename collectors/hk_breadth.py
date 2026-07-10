"""Hong Kong breadth — computed from the curated constituent universe
(config["hk"]["sectors"] members), reusing BreadthAdapter.compute().

There is no free HK-ETF holdings feed, and HK sector-ETF coverage is thin, so the
universe is hand-curated by Hang-Seng-industry sector in config.yml. Those same
names also form the DEEP synthetic sector baskets (15-25y history, far richer than
the ~5y HK sector ETFs) the engine RS-ranks. That makes this a large-cap
(HSI/HSCEI-style) breadth gauge, not full-market breadth — labeled honestly on the
dashboard. yfinance handles .HK closes (verified); coverage is logged and the run
fails if too many curated names fail to resolve.

Outputs mirror the US/China breadth series (data/hk_breadth/breadth.parquet):
pct_above_50/200, nh/nl, adv/dec/ad_line, n_members. Also writes a constituents
table (symbol/name/sector) used by the per-sector drill-down + stock search, and
caches the close matrix for the search library + the synthetic baskets.
"""
from __future__ import annotations

import logging

import pandas as pd

from collectors.breadth import BreadthAdapter
from lib import config

log = logging.getLogger(__name__)


class HkBreadthAdapter(BreadthAdapter):
    name = "hk_breadth"
    group = "hk_breadth"

    def __init__(self) -> None:
        self.cfg = config.load()["hk"]["breadth"]
        hk = config.load()["hk"]
        self.ycfg = hk["yahoo"]          # batch_size/retries/backoff for base _download_closes
        self.sectors = hk["sectors"]
        self.names = hk.get("names", {})
        self.cache_path = config.data_dir() / "hk_breadth" / "_closes_cache.parquet"

    def constituents(self) -> pd.DataFrame:
        rows = []
        for sector, meta in self.sectors.items():
            for t in meta["members"]:
                rows.append({"symbol": t, "name": self.names.get(t, t), "sector": sector})
        return pd.DataFrame(rows).drop_duplicates(subset="symbol")

    def constituents_checked(self, members: pd.DataFrame) -> pd.DataFrame:
        if members.empty or len(members) < 30:
            raise ValueError(f"hk constituents list suspicious: {len(members)} rows")
        return members

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        members = self.constituents_checked(self.constituents())
        tickers = members["symbol"].tolist()

        if full_history:
            closes = self._download_closes(tickers, "max")
        else:
            closes = None
            if self.cache_path.exists():
                cached = pd.read_parquet(self.cache_path)
                age = (pd.Timestamp.utcnow().tz_localize(None) - cached.index.max()).days
                if age <= 14:
                    fresh = self._download_closes(tickers, "1mo")
                    closes = self._merge_refreshed(fresh, cached)  # split-seam repair
            if closes is None:
                days = self.cfg["lookback_days_live"]
                closes = self._download_closes(tickers, f"{max(1, days // 365 + 1)}y")
            cutoff = closes.index.max() - pd.Timedelta(days=self.cfg["lookback_days_live"] + 30)
            closes = closes[closes.index >= cutoff]

        live_cols = closes.dropna(axis=1, how="all").shape[1]
        coverage = live_cols / len(tickers)
        log.info("hk_breadth coverage: %d/%d curated names resolved (%.0f%%)",
                 live_cols, len(tickers), 100 * coverage)
        if coverage < self.cfg["min_coverage"]:
            raise RuntimeError(f"hk_breadth closes too sparse: {live_cols}/{len(tickers)} "
                               f"(< {self.cfg['min_coverage']:.0%})")

        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        if not full_history:
            closes.to_parquet(self.cache_path)
        members.set_index("symbol").to_parquet(self.cache_path.parent / "constituents.parquet")

        return {"breadth": self.compute(closes)}
