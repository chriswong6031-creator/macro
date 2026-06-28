"""Whole-A valuation anchor — the market-wide PE/PB level + history percentile.

KEYLESS · DISPLAY/CONTEXT-ONLY. The anti-chase macro frame for the China hub:
how richly the WHOLE A-share market is priced right now versus its own 10-year
and full history. Two keyless akshare/legulegu calls, both returning one row per
trading day with the percentiles ALREADY baked in by the source:

  stock_a_ttm_lyr()  -> whole-market median / equal-weight PE (TTM + LYR) + close
                        + quantileInRecent10Years* / quantileInAllHistory*
  stock_a_all_pb()   -> whole-market median / equal-weight PB + close + the same
                        history-quantile columns

Stored as a time-series under group `china_a_val` (one parquet per series, the
runner upsert-archives forever). Source quantiles arrive as 0..1 fractions; we
keep them as fractions (the engine multiplies by 100 where it wants pct points).

CONTEXT, NOT A SIGNAL. Surfaced as the hub's "is the whole market cheap or
expensive" frame and a small ±0.05 edge nudge downstream — never a scored axis
into an allocation. Whole-market valuation has no validated cross-sectional edge;
it is the regime backdrop you read the per-name reads against.

akshare column names DRIFT across versions, so every field is matched by
SUBSTRING (e.g. 'Recent10Years' + 'MiddlePeTtm' in the column name), not exact
equality. Lazy akshare import inside fetch(); per-call try/except; raises only
when NOTHING was fetched (the runner then degrades the family, never the build).
"""
from __future__ import annotations

import logging

import pandas as pd

from collectors.base import Adapter

log = logging.getLogger(__name__)


def _col(df: pd.DataFrame, *needles: str):
    """First column whose name contains ALL of *needles* (case-insensitive).

    akshare/legulegu column names wobble across versions; substring-AND matching
    survives that (e.g. ('Recent10Years', 'MiddlePeTtm') still finds
    'quantileInRecent10YearsMiddlePeTtm' even if a prefix changes).
    """
    low = [(c, str(c).lower()) for c in df.columns]
    wants = [n.lower() for n in needles]
    for c, lc in low:
        if all(w in lc for w in wants):
            return c
    return None


def _series(df: pd.DataFrame, col) -> pd.Series | None:
    if col is None or col not in df.columns:
        return None
    return pd.to_numeric(df[col], errors="coerce")


class ChinaAValuationAdapter(Adapter):
    """Whole-A median PE/PB + 10y/all-history percentiles (keyless, daily)."""

    name = "china_a_valuation"
    group = "china_a_val"
    stale_after_days = 4   # daily trading-day series; tolerate weekends/holidays

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        try:
            import akshare as ak
        except Exception as e:  # noqa: BLE001 — tracked adapter failure
            raise RuntimeError(f"china_a_valuation: akshare unavailable ({e})") from e

        out: dict[str, pd.DataFrame] = {}
        errors: list[str] = []

        # --- whole-market PE (TTM/LYR) + history percentiles ---------------- #
        pe_close: pd.Series | None = None
        try:
            df = ak.stock_a_ttm_lyr()
            if df is None or df.empty:
                raise ValueError("empty PE table")
            idx = pd.to_datetime(df[_col(df, "date") or "date"], errors="coerce")
            base = pd.DataFrame(index=idx)
            cols = {
                "median_pe_ttm": _series(df, _col(df, "middlePETTM")),
                "avg_pe_ttm":    _series(df, _col(df, "averagePETTM")),
                "close":         _series(df, _col(df, "close")),
                # quantiles baked in by the source (0..1 fractions)
                "pe_pctile_10y": _series(df, _col(df, "Recent10Years", "MiddlePeTtm")),
                "pe_pctile_all": _series(df, _col(df, "AllHistory", "MiddlePeTtm")),
            }
            for k, s in cols.items():
                if s is not None:
                    base[k] = s.to_numpy()
            base = base[~base.index.isna()].dropna(how="all").sort_index()
            if base.empty:
                raise ValueError("no usable PE columns")
            out["pe"] = base
            if "close" in base.columns:
                pe_close = base["close"]
        except Exception as e:  # noqa: BLE001 — per-call isolation
            errors.append(f"pe({e})")
            log.warning("china_a_valuation PE failed: %s", e)

        # --- whole-market PB + history percentiles -------------------------- #
        try:
            df = ak.stock_a_all_pb()
            if df is None or df.empty:
                raise ValueError("empty PB table")
            idx = pd.to_datetime(df[_col(df, "date") or "date"], errors="coerce")
            base = pd.DataFrame(index=idx)
            cols = {
                "median_pb":     _series(df, _col(df, "middlePB")),
                "pb_pctile_10y": _series(df, _col(df, "Recent10Years", "MiddlePB")),
                "pb_pctile_all": _series(df, _col(df, "AllHistory", "MiddlePB")),
            }
            for k, s in cols.items():
                if s is not None:
                    base[k] = s.to_numpy()
            # carry a close for this series too — prefer the PE-table close
            # (CSI-proxy index level) when available, else the PB-table close.
            pb_close = _series(df, _col(df, "close"))
            if pb_close is not None:
                base["close"] = pb_close.to_numpy()
            base = base[~base.index.isna()].dropna(how="all").sort_index()
            if base.empty:
                raise ValueError("no usable PB columns")
            if pe_close is not None:
                # align the canonical close from the PE table onto PB dates
                # (drop dup dates first — reindex rejects a duplicated axis)
                pe_c = pe_close[~pe_close.index.duplicated(keep="last")]
                base["close"] = pe_c.reindex(base.index).combine_first(
                    base.get("close"))
            out["pb"] = base
        except Exception as e:  # noqa: BLE001 — per-call isolation
            errors.append(f"pb({e})")
            log.warning("china_a_valuation PB failed: %s", e)

        if not out:
            raise RuntimeError(
                f"china_a_valuation: no series fetched ({'; '.join(errors)})")
        if errors:
            log.warning("china_a_valuation partial: %s", "; ".join(errors))
        log.info("china_a_valuation: fetched %s", list(out))
        return out
