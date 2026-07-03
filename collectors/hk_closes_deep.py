"""HK closes-deep nightly refresh — incremental append to data/hk_search/closes_deep.parquet.

The deep wide matrix (Date x ticker, close-only, ~40y back to 1986 for the blue chips) was
originally built by a one-off research script (scripts/hk_residual_alpha_phase0.py --fetch)
and was NEVER wired into the nightly collect lane.  As a result the file drifted stale
(last observed gap: closes_deep 2026-06-18 vs hk_stocks 2026-07-03, HKCA-3 in the audit).

This adapter closes that gap:
  - On a normal run it downloads the trailing ~2 months for all constituents and
    merge-upserts (combine_first) onto the existing parquet, keeping the full deep history.
  - On --full-history it refetches from the beginning (same as the one-off --fetch flag).
  - It writes to data/hk_search/ (group="hk_search", series_name="closes_deep") so the
    path is identical to what all consumers already read.
  - Stale-after-days = 5 (same cadence as hk_breadth).
  - Named tripwire: stale detection fires if max date falls behind hk_stocks.

Universe: data/hk_breadth/constituents.parquet (written by HkBreadthAdapter; must exist).
Fail-closed: if the constituents file is missing, raises immediately (do not silently produce
an empty or truncated parquet).  If yfinance returns fewer names than expected, coverage is
logged and the run proceeds (consistent with hk_breadth min_coverage behavior).
"""
from __future__ import annotations

import logging

import pandas as pd
import yfinance as yf

from collectors.base import Adapter
from lib import config

log = logging.getLogger(__name__)

_CONSTITUENTS_PATH = "hk_breadth/constituents.parquet"
_MIN_COVERAGE = 0.50          # fail if yfinance returns < 50% of expected tickers
_INCREMENTAL_PERIOD = "2mo"   # enough to cover any short outage (>= stale_after_days x margin)


class HkClosesDeepAdapter(Adapter):
    """Nightly incremental refresh of data/hk_search/closes_deep.parquet."""

    name = "hk_closes_deep"
    group = "hk_search"        # -> store writes data/hk_search/closes_deep.parquet
    stale_after_days = 5

    def _tickers(self) -> list[str]:
        p = config.data_dir() / _CONSTITUENTS_PATH
        if not p.exists():
            raise RuntimeError(
                "hk_closes_deep: constituents file missing "
                f"({p}) -- run hk_breadth first"
            )
        return list(pd.read_parquet(p).index)

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        tickers = self._tickers()

        if full_history:
            period = "max"
            log.info("hk_closes_deep: full-history fetch for %d tickers", len(tickers))
        else:
            period = _INCREMENTAL_PERIOD
            log.info(
                "hk_closes_deep: incremental fetch for %d tickers (%s)",
                len(tickers), period,
            )

        raw = yf.download(
            tickers,
            period=period,
            auto_adjust=True,
            progress=False,
            threads=True,
        )

        # yfinance returns a multi-level frame for multiple tickers.
        if hasattr(raw.columns, "levels"):
            level0 = raw.columns.get_level_values(0)
            if "Close" in level0:
                closes = raw["Close"]
            else:
                closes = raw.xs("Close", axis=1, level=0)
        else:
            # Single ticker fallback (shouldn't happen for 150+ tickers, but be safe)
            closes = raw[["Close"]] if "Close" in raw.columns else raw

        # Keep only the requested tickers (yfinance may silently drop delisted names)
        valid = [t for t in tickers if t in closes.columns]
        closes = closes[valid].dropna(how="all")

        coverage = len(valid) / len(tickers) if tickers else 0.0
        log.info(
            "hk_closes_deep: %d/%d tickers resolved (%.0f%%), date range %s->%s",
            len(valid), len(tickers), 100 * coverage,
            closes.index.min().date() if not closes.empty else "N/A",
            closes.index.max().date() if not closes.empty else "N/A",
        )
        if coverage < _MIN_COVERAGE:
            raise RuntimeError(
                f"hk_closes_deep: coverage {coverage:.0%} < {_MIN_COVERAGE:.0%} "
                f"({len(valid)}/{len(tickers)} tickers)"
            )
        if closes.empty:
            raise RuntimeError("hk_closes_deep: yfinance returned no rows")

        # The validate() + store.upsert() path in run_adapter handles the merge with
        # the existing parquet (combine_first keeps old deep-history rows).
        return {"closes_deep": closes}
