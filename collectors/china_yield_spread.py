"""China–US sovereign yield curve & spread — the carry/RMB-pressure leg.

KEYLESS · DISPLAY/CONTEXT-ONLY. Wraps ak.bond_zh_us_rate (东方财富网-中美国债收益率),
the keyless Eastmoney datacenter series of CN + US Treasury yields at 2/5/10/30y.

Stored under group `china_yield`, one parquet `rates`, datetime-indexed (from 日期):

  cn_2y · cn_5y · cn_10y · cn_30y · cn_slope_10_2(=cn_10y−cn_2y)
  us_2y · us_10y · cn_us_10y_spread(=cn_10y−us_10y)

A negative + widening cn_us_10y_spread = carry/RMB-outflow pressure; the CN slope is
the domestic growth/easing read. Both are consumed downstream by china_policy_watch
(new leg in the PBoC stance + EASING_REFLATION chain) — this collector only stores the
raw curve, never scores.

akshare column names DRIFT across versions, so Chinese source columns are matched by
SUBSTRING (e.g. '中国国债收益率2年' contained in a column), not exact equality.
akshare is imported LAZILY inside fetch() so a missing dep surfaces as a tracked adapter
failure rather than silently removing the adapter; RuntimeError raised only if NOTHING
is fetched (the runner's circuit breaker then notices).
"""
from __future__ import annotations

import logging

import pandas as pd

from collectors.base import Adapter

log = logging.getLogger(__name__)

# full-history start (matches spec) vs recent window for incremental refreshes.
_FULL_START = "20180101"
_RECENT_START = "20230101"

# stored_column -> ordered substring needles into the akshare frame (drift-tolerant).
# More specific needles first so '中国国债收益率10年-2年' never matches the plain 10y leg.
_CN = {
    "cn_2y":  ("中国国债收益率2年",),
    "cn_5y":  ("中国国债收益率5年",),
    "cn_10y": ("中国国债收益率10年",),
    "cn_30y": ("中国国债收益率30年",),
}
_US = {
    "us_2y":  ("美国国债收益率2年",),
    "us_10y": ("美国国债收益率10年",),
}


def _col(df: pd.DataFrame, *needles: str):
    """First column whose name CONTAINS a needle (akshare Chinese column drift).

    Guards against the '10年-2年' slope columns shadowing the plain '10年' legs by
    rejecting any candidate carrying the '-' / '－' slope marker unless asked for it.
    """
    for n in needles:
        for c in df.columns:
            cs = str(c)
            if n in cs and ("-" not in cs and "－" not in cs):
                return c
    return None


class ChinaYieldSpreadAdapter(Adapter):
    name = "china_yield_spread"
    group = "china_yield"
    stale_after_days = 6   # daily series but tolerates weekend/holiday gaps + 502s
    # the Eastmoney bond datacenter occasionally 502s from a non-CN IP; tag it so a
    # blocked fetch is reported as 'blocked' (regime context) rather than circuit-broken.
    expected_failure = "bond_zh_us_rate may 502 from a non-CN IP — yield-curve context only"

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        try:
            import akshare as ak
        except Exception as e:  # noqa: BLE001 — tracked adapter failure
            raise RuntimeError(f"china_yield_spread: akshare unavailable ({e})") from e

        start = _FULL_START if full_history else _RECENT_START
        try:
            raw = ak.bond_zh_us_rate(start_date=start)
        except Exception as e:  # noqa: BLE001 — surfaced to the runner / breaker
            raise RuntimeError(f"china_yield_spread: bond_zh_us_rate failed ({e})") from e

        if raw is None or raw.empty:
            raise RuntimeError("china_yield_spread: bond_zh_us_rate returned no rows")

        dcol = _col(raw, "日期", "date") or raw.columns[0]
        idx = pd.to_datetime(raw[dcol], errors="coerce")

        out = pd.DataFrame(index=idx)
        for stored, needles in {**_CN, **_US}.items():
            src = _col(raw, *needles)
            if src is not None:
                # value-assign — raw[src] carries a RangeIndex that would otherwise
                # align to NaN against the DatetimeIndex.
                out[stored] = pd.to_numeric(raw[src], errors="coerce").to_numpy()

        out = out[~out.index.isna()].sort_index()
        out = out[~out.index.duplicated(keep="last")]

        # derived legs — only where both inputs are present.
        if "cn_10y" in out.columns and "cn_2y" in out.columns:
            out["cn_slope_10_2"] = out["cn_10y"] - out["cn_2y"]
        if "cn_10y" in out.columns and "us_10y" in out.columns:
            out["cn_us_10y_spread"] = out["cn_10y"] - out["us_10y"]

        out = out.dropna(how="all")
        if out.empty:
            raise RuntimeError(
                f"china_yield_spread: no usable yield columns in {list(raw.columns)}")

        log.info("china_yield_spread: %d rows, cols=%s", len(out), list(out.columns))
        return {"rates": out}
