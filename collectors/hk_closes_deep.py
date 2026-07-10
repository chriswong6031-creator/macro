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
from collectors.breadth import repair_seams
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

    def _download(self, tickers: list[str], period: str) -> pd.DataFrame:
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
                return raw["Close"]
            return raw.xs("Close", axis=1, level=0)
        # Single ticker fallback (shouldn't happen for 150+ tickers, but be safe)
        return raw[["Close"]] if "Close" in raw.columns else raw

    def _heal_store_seams(self, fresh: pd.DataFrame) -> None:
        """In-place split-seam repair of the stored deep matrix (#2120 KLAC class).

        The runner merges fetch()'s fresh window into closes_deep.parquet with
        plain combine_first (store.upsert, overwrite_overlap=False), so after a
        split the stored PRE-window history stays on the old price basis — a
        permanent fake ±N00% day at the refresh boundary. Detection therefore
        runs here against the stored file, and the heal rewrites the flagged
        columns WHOLESALE in the store BEFORE the runner's merge: returning the
        healed history through fetch() would let stale cached cells resurrect
        via combine_first wherever the re-pull lacks a row. Never fatal."""
        try:
            path = config.data_dir() / self.group / "closes_deep.parquet"
            if not path.exists():
                return
            cached = pd.read_parquet(path)
            # merged target IS the cached matrix: detector (a) sees a boundary
            # re-basing via fresh-vs-cached overlap, detector (b) sees residual
            # seams from past refreshes inside cached itself.
            cached, healed = repair_seams(cached, fresh, cached, self._download,
                                          "max", name=self.name)
            if healed:
                cached.to_parquet(path)
                log.info("hk_closes_deep: healed %d split-seamed column(s) in %s: %s",
                         len(healed), path.name, healed[:12])
        except Exception as e:  # noqa: BLE001 — repair must never kill the run
            log.warning("hk_closes_deep: seam heal failed (%s) — store kept as-is; "
                        "the scan retries next run", e)

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

        closes = self._download(tickers, period)

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

        # Split-seam repair must run BEFORE the runner's combine_first merge —
        # the stored pre-window history is the vulnerable part (#2120 class).
        if not full_history:
            self._heal_store_seams(closes)

        # The validate() + store.upsert() path in run_adapter handles the merge with
        # the existing parquet (combine_first keeps old deep-history rows).
        return {"closes_deep": closes}
