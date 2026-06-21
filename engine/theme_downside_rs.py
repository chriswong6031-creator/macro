"""Down-day-conditional Relative Strength per thematic basket.

DISPLAY-ONLY — directional:false.

This is the doctrine's earliest "holds up on down days" tell (scorecard
dimension 1b). The module is NEVER a scored forward-return predictor; it
surfaces a descriptive signal you can audit, consistent with the house rule
on the Theme Rotation Desk.

For each theme/basket: filter the lookback window to days where the
benchmark had a NEGATIVE return (down days), then compare the basket's
cross-sectional median-member return against the benchmark on those days.

Output per basket:
  down_day_alpha  — mean of (median_member_ret − bench_ret) on down days.
                    Positive = the basket consistently outperforms when the
                    market drops ("holds up").
  down_capture    — mean(median_member_ret) / mean(bench_ret) on down days.
                    Lower (more negative / closer to 0) is better.
                    NaN when n_down_days < 3 (not meaningful).
  holds_up        — bool convenience flag: down_day_alpha > 0 OR down_capture < 1.
  n_down_days     — how many down-benchmark sessions drove the calculation.
  lookback        — actual trading days used (min of requested lookback_d and
                    available history).

Public API: downside_rs(region='us', lookback_d=63) → dict[str, dict]
  Keys are basket ids.  Returns {} on any data shortfall (never raises).
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from engine import group_flow
from engine.baskets import _ew_level

log = logging.getLogger(__name__)

_MIN_DOWN_DAYS = 3     # guard: need at least this many down-bench sessions
_MIN_MEMBERS   = 3     # minimum live members to process a basket


def _r(x, n: int = 4):
    """Round to n decimals; return None for non-finite values."""
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return None
    return round(float(x), n)


# --------------------------------------------------------------------------- public API

def downside_rs(region: str = "us", lookback_d: int = 63) -> dict[str, dict]:
    """Compute down-day-conditional relative strength for every basket in *region*.

    Parameters
    ----------
    region:     'us' | 'cn' | 'hk' | 'ca'  (mirrors group_flow._setup convention)
    lookback_d: trailing calendar of trading days (default 63 ≈ 1 quarter)

    Returns
    -------
    dict mapping basket_id → {
        "down_day_alpha": float | None,
        "down_capture":   float | None,
        "holds_up":       bool,
        "n_down_days":    int,
        "lookback":       int,
    }
    Returns {} if the data store is unavailable or too short.
    """
    try:
        return _compute(region, lookback_d)
    except Exception:  # noqa: BLE001 — additive display-only leaf; never crash caller
        log.exception("theme_downside_rs: unexpected error for region=%s", region)
        return {}


# --------------------------------------------------------------------------- internals

def _compute(region: str, lookback_d: int) -> dict[str, dict]:
    if region == "us":
        s = group_flow._setup()
    else:
        from engine import narrative_rotation as _nr
        rcfg = _nr._region_cfg(region) or {}
        s = _nr._setup(rcfg) if rcfg else None

    if s is None:
        return {}

    closes: pd.DataFrame = s["closes"]
    rets:   pd.DataFrame = s["rets"]
    idx:    pd.Index     = s["idx"]
    bench:  pd.Series    = s["bench"]

    if len(idx) < max(lookback_d, 10):
        return {}

    # Benchmark *daily* returns over the lookback window (same recipe as group_flow._setup).
    bench_ret = bench.pct_change(fill_method=None)

    # Slice to the lookback window (last N rows).
    win_rets  = rets.iloc[-lookback_d:]
    win_bench = bench_ret.iloc[-lookback_d:]
    actual_lookback = len(win_rets)

    # Boolean mask for down-benchmark trading days in the window.
    down_mask = win_bench < 0.0

    results: dict[str, dict] = {}

    mem    = s["mem"]
    bdict  = mem["baskets"]
    items  = bdict.items() if isinstance(bdict, dict) else [(b["id"], b) for b in bdict]

    for bid, b in items:
        members = b.get("members", [])
        present = [m["ticker"] for m in members if m["ticker"] in rets.columns]
        if len(present) < _MIN_MEMBERS:
            results[bid] = _neutral(actual_lookback)
            continue

        # Build the same dated live-member mask used by theme_scoring.
        mask = pd.DataFrame(False, index=idx, columns=present)
        for m in members:
            t = m["ticker"]
            if t not in present:
                continue
            act = np.asarray(idx >= pd.Timestamp(m["added"]))
            if m.get("removed"):
                act = act & np.asarray(idx < pd.Timestamp(m["removed"]))
            mask[t] = act

        # Slice mask to the same window.
        mask_win = mask.iloc[-lookback_d:]

        # Per-day cross-sectional median member return (live members only).
        # Mask out non-live members with NaN then take row-wise median.
        member_rets_win = win_rets[present].where(mask_win)
        daily_median = member_rets_win.median(axis=1, skipna=True)

        # Filter to down-benchmark days only.
        down_days_bench  = win_bench[down_mask].dropna()
        down_days_basket = daily_median[down_mask].dropna()

        # Align on common index (both are already within the same window).
        shared = down_days_bench.index.intersection(down_days_basket.index)
        n_down = len(shared)

        if n_down < _MIN_DOWN_DAYS:
            results[bid] = _neutral(actual_lookback)
            continue

        b_bench  = down_days_bench.loc[shared]
        b_basket = down_days_basket.loc[shared]

        # down_day_alpha: mean excess return on down-benchmark days.
        alpha_series = b_basket - b_bench
        down_day_alpha = float(alpha_series.mean())

        # down_capture: mean basket return / mean bench return on those days.
        mean_bench  = float(b_bench.mean())
        mean_basket = float(b_basket.mean())
        # mean_bench is always < 0 on down days; NaN guard just in case.
        if abs(mean_bench) < 1e-9:
            down_capture = None
        else:
            down_capture = mean_basket / mean_bench

        # holds_up: outperforms OR captures less of the benchmark decline.
        holds_up = (down_day_alpha > 0) or (down_capture is not None and down_capture < 1.0)

        results[bid] = {
            "down_day_alpha": _r(down_day_alpha),
            "down_capture":   _r(down_capture),
            "holds_up":       bool(holds_up),
            "n_down_days":    n_down,
            "lookback":       actual_lookback,
        }

    return results


def _neutral(lookback: int) -> dict:
    """Return a typed-empty structure when a basket cannot be computed."""
    return {
        "down_day_alpha": None,
        "down_capture":   None,
        "holds_up":       False,
        "n_down_days":    0,
        "lookback":       lookback,
    }
