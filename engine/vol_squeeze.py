"""engine/vol_squeeze.py — the single-stock **Volatility Black Hole** (price-based).

The dealer-gamma ``vol_hole`` (engine/gex_model.volatility_hole) only exists for the ~20
optionable names. This is the PRICE analog that works on any name with enough history: a
volatility compression → expansion state machine read straight off daily OHLCV.

Mechanism (the honest version of the "black hole" framing): realized volatility mean-reverts
(GARCH persistence ~0.97, ~23-day half-life), so a deep, *durable* compression is a coiled
spring — a larger directional move tends to follow. The catch the literature is unanimous on:
**the squeeze is directionally agnostic.** It tells you a move is loading, not which way. So:

* we detect compression with a DUAL gate — Bollinger-bandwidth percentile AND realized-vol
  percentile both in their low quantile (one alone is a parameter artifact), optionally
  AND-ed with the TTM squeeze (Bollinger inside Keltner) when high/low are present;
* we require the squeeze to PERSIST (default ≥ 5 bars) before trusting it;
* we only call a DIRECTION once price closes beyond the squeeze box — and, when volume is
  available, only on a > 1.3× volume confirmation. Otherwise the read stays "coiled, direction
  unconfirmed".

States: ``COILED`` (compressed, armed) · ``COMPRESSED`` (compressing but < min duration) ·
``FIRED_UP`` / ``FIRED_DOWN`` (just broke the box) · ``EXPANSION`` (vol already elevated, the
move is underway / late) · ``NONE``.

Honest framing: a **timing confirmer**, moderate edge, never a standalone alpha. It belongs
*after* a directional thesis (the selection edge) — it sharpens the entry, it does not pick
the name. Pure function of one stock's price (+ optional high/low/volume).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine.stock_technicals import bb_bandwidth, realized_vol, ttm_squeeze
from engine.indicators import pct_rank_window

DEFAULTS = {
    "pctile_thresh": 25.0,   # BBWP & HVP both below this (of the trailing 252d) = compressed
    "min_duration": 5,       # bars a squeeze must persist before it is "armed" (COILED)
    "rank_window": 252,      # lookback for the percentile ranks
    "release_window": 3,     # a break within this many bars of the last compressed bar = a fire
    "vol_confirm": 1.3,      # breakout-day volume vs 20d average for a CONFIRMED fire
    "min_bars": 160,         # need this much history for a trustworthy percentile
}


def _series(x, index=None):
    s = pd.to_numeric(x, errors="coerce").astype(float)
    return s.reindex(index) if index is not None else s


def assess(close: pd.Series, high: pd.Series | None = None,
           low: pd.Series | None = None, volume: pd.Series | None = None,
           cfg: dict | None = None) -> dict | None:
    """Return the vol-squeeze block, or None when history is too short.

    Output keys: state, bias (up/down/neutral), coiled (bool), days_compressed,
    bbwp, hv_pctile, box_hi, box_lo, pos (0..1 in the box), to_upper_pct, to_lower_pct,
    fired_dir (up/down/None), volume_confirmed (bool/None), coverage, caveat.
    """
    c = _series(close).dropna()
    cf = {**DEFAULTS, **(cfg or {})}
    if len(c) < cf["min_bars"]:
        return None

    has_hl = high is not None and low is not None
    if has_hl:
        hi = _series(high, c.index)
        lo = _series(low, c.index)
        has_hl = bool(hi.notna().sum() > 40 and lo.notna().sum() > 40)
    has_vol = volume is not None
    if has_vol:
        vol = _series(volume, c.index).fillna(0.0)
        has_vol = bool((vol > 0).sum() > 40)

    thr = cf["pctile_thresh"]
    rw = cf["rank_window"]
    bbwp = pct_rank_window(bb_bandwidth(c, 20, 2.0), rw) * 100.0
    hvp = pct_rank_window(realized_vol(c, 20), rw) * 100.0
    compressed = (bbwp < thr) & (hvp < thr)
    if has_hl:                       # tighten with the TTM squeeze where we have the range
        compressed = compressed & ttm_squeeze(hi, lo, c)
    compressed = compressed.fillna(False)

    # consecutive compressed bars ending today (or at the most recent compressed bar)
    arr = compressed.to_numpy()
    # days since the last compressed bar
    last_true_idx = np.where(arr)[0]
    if len(last_true_idx) == 0:
        bbwp_l, hvp_l = _f(bbwp.iloc[-1]), _f(hvp.iloc[-1])
        state = "EXPANSION" if (hvp_l is not None and hvp_l >= 80) else "NONE"
        return _out(state, "neutral", 0, bbwp_l, hvp_l, None, None, None, None, None,
                    None, _coverage(has_hl, has_vol))

    days_since_compressed = len(arr) - 1 - last_true_idx[-1]

    # the current run length: count back from the most recent compressed bar
    run = 0
    for v in arr[: last_true_idx[-1] + 1][::-1]:
        if v:
            run += 1
        else:
            break

    # the sticky squeeze box = high/low (or close) range over that compression run
    run_start = last_true_idx[-1] + 1 - run
    box_slice = slice(run_start, last_true_idx[-1] + 1)
    if has_hl:
        box_hi = _f(hi.iloc[box_slice].max())
        box_lo = _f(lo.iloc[box_slice].min())
    else:
        box_hi = _f(c.iloc[box_slice].max())
        box_lo = _f(c.iloc[box_slice].min())

    px = _f(c.iloc[-1])
    bbwp_l, hvp_l = _f(bbwp.iloc[-1]), _f(hvp.iloc[-1])
    pos = (round((px - box_lo) / (box_hi - box_lo), 3)
           if (box_hi is not None and box_lo is not None and box_hi > box_lo and px is not None)
           else None)
    to_upper = (round((box_hi - px) / px * 100.0, 2)
                if (box_hi is not None and px) else None)
    to_lower = (round((px - box_lo) / px * 100.0, 2)
                if (box_lo is not None and px) else None)

    # a light directional LEAN (trend), used only to colour COILED — never a confirmed call
    sma20 = c.rolling(20, min_periods=20).mean()
    lean = "neutral"
    s20 = _f(sma20.iloc[-1])
    if s20 and px:
        lean = "up" if px >= s20 else "down"

    armed = run >= cf["min_duration"]

    # ---- still compressed today -------------------------------------------
    if days_since_compressed == 0:
        state = "COILED" if armed else "COMPRESSED"
        return _out(state, lean, run, bbwp_l, hvp_l, box_hi, box_lo, pos,
                    to_upper, to_lower, None, _coverage(has_hl, has_vol))

    # ---- a recent release: did it break the box? --------------------------
    if days_since_compressed <= cf["release_window"] and armed:
        vol_ok = None
        if has_vol:
            vsma = vol.rolling(20, min_periods=10).mean()
            rv = (_f(vol.iloc[-1]) / _f(vsma.iloc[-1])) if _f(vsma.iloc[-1]) else None
            vol_ok = bool(rv is not None and rv >= cf["vol_confirm"])
        fired = None
        if box_hi is not None and px is not None and px > box_hi:
            fired = "up"
        elif box_lo is not None and px is not None and px < box_lo:
            fired = "down"
        if fired == "up":
            return _out("FIRED_UP", "up", run, bbwp_l, hvp_l, box_hi, box_lo, pos,
                        to_upper, to_lower, "up",
                        _coverage(has_hl, has_vol), volume_confirmed=vol_ok)
        if fired == "down":
            return _out("FIRED_DOWN", "down", run, bbwp_l, hvp_l, box_hi, box_lo, pos,
                        to_upper, to_lower, "down",
                        _coverage(has_hl, has_vol), volume_confirmed=vol_ok)
        # released but still inside the box — treat as a relaxing coil
        return _out("COILED", lean, run, bbwp_l, hvp_l, box_hi, box_lo, pos,
                    to_upper, to_lower, None, _coverage(has_hl, has_vol))

    # ---- compression is stale -> normal / expansion -----------------------
    state = "EXPANSION" if (hvp_l is not None and hvp_l >= 80) else "NONE"
    return _out(state, "neutral", 0, bbwp_l, hvp_l, None, None, None, None, None,
                None, _coverage(has_hl, has_vol))


# ---------------------------------------------------------------------------
def _f(x) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if (np.isnan(v) or np.isinf(v)) else v


def _coverage(has_hl: bool, has_vol: bool) -> str:
    return "ohlcv" if (has_hl and has_vol) else "ohlc" if has_hl else "close"


_CAVEAT = ("Volatility compression read — a TIMING context, not a direction call. A durable "
           "squeeze means a larger move is loading; which way is unconfirmed until price breaks "
           "the box (on volume). Moderate edge, never a standalone signal.")
_CAVEAT_ZH = ("波动压缩读数 — 属择时背景，并非方向判断。持续的压缩意味着更大的波动正在蓄势；"
              "方向要等价格放量突破压缩箱后才确认。中等效力，绝非独立信号。")


def _out(state, bias, days, bbwp, hvp, box_hi, box_lo, pos, to_upper, to_lower,
         fired_dir, coverage, *, volume_confirmed=None) -> dict:
    return {
        "state": state, "bias": bias, "coiled": state in ("COILED", "FIRED_UP", "FIRED_DOWN"),
        "days_compressed": int(days),
        "bbwp": None if bbwp is None else round(bbwp, 0),
        "hv_pctile": None if hvp is None else round(hvp, 0),
        "box_hi": box_hi, "box_lo": box_lo, "pos": pos,
        "to_upper_pct": to_upper, "to_lower_pct": to_lower,
        "fired_dir": fired_dir, "volume_confirmed": volume_confirmed,
        "coverage": coverage, "caveat": _CAVEAT, "caveat_zh": _CAVEAT_ZH,
    }
