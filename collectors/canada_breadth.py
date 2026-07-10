"""Canada / TSX breadth — computed from the curated large-cap constituent universe
(config["canada"]["constituents"]), reusing BreadthAdapter.compute().

The universe is hand-curated by sector in config.yml from the verified S&P/TSX 60 +
large-cap complement, so this is a LARGE-CAP breadth gauge (not full-Composite),
labeled honestly on the dashboard. yfinance handles .TO closes (verified); coverage
is logged and the run fails if too many curated names fail to resolve.

Outputs mirror the US/China breadth series (data/canada_breadth/breadth.parquet):
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


class CanadaBreadthAdapter(BreadthAdapter):
    name = "canada_breadth"
    group = "canada_breadth"

    def __init__(self) -> None:
        self.cfg = config.load()["canada"]["breadth"]
        self.ycfg = config.load()["canada"]["yahoo"]
        self.const_cfg = config.load()["canada"]["constituents"]
        self.cache_path = config.data_dir() / "canada_breadth" / "_closes_cache.parquet"

    def constituents(self) -> pd.DataFrame:
        rows = []
        for sector, tickers in self.const_cfg.items():
            for t in tickers:
                rows.append({"symbol": t, "name": t, "sector": sector})
        return pd.DataFrame(rows).drop_duplicates(subset="symbol")

    def constituents_checked(self, members: pd.DataFrame) -> pd.DataFrame:
        if members.empty or len(members) < 30:
            raise ValueError(f"canada constituents list suspicious: {len(members)} rows")
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
        log.info("canada_breadth coverage: %d/%d curated names resolved (%.0f%%)",
                 live_cols, len(tickers), 100 * coverage)
        if coverage < self.cfg["min_coverage"]:
            raise RuntimeError(f"canada_breadth closes too sparse: {live_cols}/{len(tickers)} "
                               f"(< {self.cfg['min_coverage']:.0%})")

        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        if not full_history:
            closes.to_parquet(self.cache_path)
        members.set_index("symbol").to_parquet(self.cache_path.parent / "constituents.parquet")

        return {"breadth": self.compute(closes)}
