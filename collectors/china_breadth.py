"""China A-share breadth — computed from the curated large-cap constituent
universe (config["china"]["constituents"]), reusing BreadthAdapter.compute().

There is no free Chinese-ETF holdings feed comparable to the US Wikipedia S&P 500
list, so the universe is hand-curated by sector in config.yml. That makes this a
LARGE-CAP (CSI300-style) breadth gauge, not full-market breadth — labeled honestly
on the dashboard. yfinance handles .SS/.SZ closes (verified); coverage is logged
and the run fails if too many curated names fail to resolve.

Outputs mirror the US breadth series (data/china_breadth/breadth.parquet):
pct_above_50/200, nh/nl, adv/dec/ad_line, n_members. Also writes a constituents
table (symbol/name/sector) used by the per-sector drill-down + stock search, and
caches the close matrix for the search library.
"""
from __future__ import annotations

import logging

import pandas as pd

from collectors.breadth import BreadthAdapter
from lib import config

log = logging.getLogger(__name__)


class ChinaBreadthAdapter(BreadthAdapter):
    name = "china_breadth"
    group = "china_breadth"

    def __init__(self) -> None:
        self.cfg = config.load()["china"]["breadth"]
        self.ycfg = config.load()["china"]["yahoo"]
        self.const_cfg = config.load()["china"]["constituents"]
        self.cache_path = config.data_dir() / "china_breadth" / "_closes_cache.parquet"

    def constituents(self) -> pd.DataFrame:
        rows = []
        for sector, tickers in self.const_cfg.items():
            for t in tickers:
                rows.append({"symbol": t, "name": t, "sector": sector})
        return pd.DataFrame(rows).drop_duplicates(subset="symbol")

    def constituents_checked(self, members: pd.DataFrame) -> pd.DataFrame:
        if members.empty or len(members) < 30:
            raise ValueError(f"china constituents list suspicious: {len(members)} rows")
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
        log.info("china_breadth coverage: %d/%d curated names resolved (%.0f%%)",
                 live_cols, len(tickers), 100 * coverage)
        if coverage < self.cfg["min_coverage"]:
            raise RuntimeError(f"china_breadth closes too sparse: {live_cols}/{len(tickers)} "
                               f"(< {self.cfg['min_coverage']:.0%})")

        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        if not full_history:
            closes.to_parquet(self.cache_path)
        members.set_index("symbol").to_parquet(self.cache_path.parent / "constituents.parquet")

        return {"breadth": self.compute(closes)}
