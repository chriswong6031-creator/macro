"""Bottom-formation radar (engine v2, anticipation tier) — a single point-in-time
0-100 raw score that a name's forward outcome is a DURABLE bottom (not a dead-cat
bounce), built to be FORWARDED to the top of the watchlist BEFORE price confirms.

HONESTY CONTRACT (research/ANTICIPATION_ENGINE_DESIGN.md): our own measurements show
entry timing has NEGATIVE forward-return correlation — anticipation is a DRAWDOWN /
capital-efficiency lever, NOT a return-alpha lever. So this score is a pure ENTRY /
watchlist-ORDERING overlay; it MUST NOT touch the cross-sectional selection rank. The
raw score here is mapped to a probability ONLY by a fitted calibration curve
(scripts/calibrate_bottom_radar.py) — raw weights are NOT probabilities — and the
PRIMED tier earns a starter SIZE only if calibration proves positive expectancy net of
the stop; otherwise it is watchlist-ordering display-only.

Reuses the existing leading machinery (engine.cycles early_signals / rsi_divergence /
bottom_confidence / washout, engine.velocity deterioration) and adds the legs that were
missing: graded divergence, volatility contraction, relative-strength holding, and (for
the volume-bearing deep names) a capitulation->dry-up signature. Every input is causal
(<= as_of); truncate-and-recompute == full at a past date.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine import velocity
from engine.cycles import rsi_divergence, rsi as _rsi

# leg weights (research §anticipation_engine; sum to 1.0). These weight the RAW score;
# they are NOT probabilities — the calibration curve maps raw -> P(durable bottom).
_W = {
    "timing_band": 0.18,   # cycle low is due (the ~70% timing prior)
    "divergence": 0.20,    # graded bullish RSI divergence (strongest close-only; only ARMS)
    "mtf_turn": 0.18,      # multi-timeframe turning confluence (weekly heaviest)
    "vol_contract": 0.12,  # volatility contraction (coiled spring)
    "rs_hold": 0.12,       # relative strength holding / not making a lower low
    "deter_easing": 0.08,  # deterioration / rising-variance easing (critical-slowing-down)
    "capitulation": 0.12,  # washout resolving + (volume) climax->dry-up
}

# weekly-dominant multi-timeframe confluence weights (mirror bottom_confidence)
_TF_W = {"D": 0.20, "3D": 0.20, "W": 0.45, "M": 0.15}


def _tf_up(s: dict) -> bool:
    return bool(s and (s.get("macd_cross_up") or s.get("macd_curl_up")
                       or s.get("macd_approaching_up") or s.get("stoch_cross_up")))


def _divergence_grade(close: pd.Series, mtf: dict) -> float:
    """A/B/C graded bullish divergence -> [0,1]. A (1.0): a confirmed bullish RSI
    divergence with both pivots oversold; B (0.6): divergence present but shallower;
    C/none (0): no clean divergence. Hidden/continuation divergence is rejected by
    rsi_divergence's pivot logic already (it requires a price lower-low)."""
    div = rsi_divergence(close)
    if not div.get("bull"):
        # a bare daily oscillator pop out of deep oversold is a weak C-tier arm
        d = mtf.get("D", {})
        return 0.25 if (d.get("stoch_cross_up") and (d.get("rsi14") or 50) < 45) else 0.0
    r = _rsi(close.dropna(), 14)
    try:
        last_rsi = float(r.iloc[-1])
    except Exception:
        last_rsi = 50.0
    # A-tier when the divergence is fresh and momentum is still building from oversold
    fresh = (div.get("bull_bars_ago") or 99) <= 6
    return 1.0 if (fresh and last_rsi < 55) else 0.6


def _vol_contraction(close: pd.Series, n: int = 20, lookback: int = 120) -> float:
    """Volatility CONTRACTION as a coiled-spring precursor: the percentile of the
    current n-day realized vol within its own `lookback` history, INVERTED (low vol =
    high score). Close-only; range-based squeeze would be better but needs high/low."""
    c = close.dropna()
    if len(c) < lookback + n:
        return 0.0
    rv = c.pct_change().rolling(n).std()
    cur = rv.iloc[-1]
    hist = rv.iloc[-lookback:]
    if not np.isfinite(cur) or hist.notna().sum() < 30:
        return 0.0
    pct = float((hist <= cur).mean())     # 0 = calmest in the window
    return float(np.clip(1.0 - pct, 0.0, 1.0))


def _rs_hold(close: pd.Series, bench: pd.Series | None) -> float:
    """Relative strength HOLDING: the stock's RS line vs the benchmark is NOT making a
    lower low while price does (positive RS divergence), or RS deterioration is easing.
    Higher = institutions defending the name. Needs a benchmark; 0.5 (neutral) without."""
    if bench is None or not len(bench):
        return 0.5
    c = close.dropna()
    b = bench.reindex(c.index).ffill()
    rs = (c / b).dropna()
    if len(rs) < 40:
        return 0.5
    win = rs.iloc[-20:]
    prior = rs.iloc[-40:-20]
    # RS made a higher low over the recent window than the prior one = holding/improving
    holding = float(win.min() >= prior.min() * 0.998)
    # and RS not currently at its 60d low
    not_new_low = float(rs.iloc[-1] > rs.iloc[-60:].min() * 1.005) if len(rs) >= 60 else 0.5
    return float(np.clip(0.6 * holding + 0.4 * not_new_low, 0.0, 1.0))


def _deter_easing(close: pd.Series, bench: pd.Series | None) -> float:
    """Critical-slowing-down EASING: the deterioration composite (trend/accel/rvar) is
    rolling OFF its recent peak — the decline is losing downside energy."""
    c = close.dropna()
    if len(c) < 120:
        return 0.0
    try:
        feats = velocity.velocity_features(c, bench=bench)
        dz = velocity.deterioration_z(feats).dropna()
    except Exception:
        return 0.0
    if len(dz) < 15:
        return 0.0
    cur = float(dz.iloc[-1])
    peak = float(dz.iloc[-15:].max())
    # eased = pulled back from a recent stress peak toward calm (lower = better)
    if peak <= 0:
        return 0.4
    return float(np.clip((peak - cur) / (abs(peak) + 1e-6), 0.0, 1.0))


def _capitulation(close: pd.Series, volume: pd.Series | None, cyc: dict, wo: dict) -> float:
    """Washout RESOLVING + (volume tier) a capitulation->dry-up signature: a volume
    climax at/near the candidate low followed by declining volume on the retest =
    sellers exhausted. Close-only names get the washout-reclaim half only."""
    # washout reclaim half (close-only): price was washed out and is reclaiming the 10d
    reclaim = 0.0
    knife = (wo or {}).get("knife")
    lvl = (wo or {}).get("level", "none")
    if lvl in ("watch", "elevated", "high") and cyc.get("above_ma10"):
        reclaim = 0.5            # washed out AND reclaiming = constructive resolution
    elif lvl in ("watch", "elevated"):
        reclaim = 0.2
    if volume is None or not len(volume):
        return reclaim
    v = volume.reindex(close.dropna().index).ffill().dropna()
    if len(v) < 60:
        return reclaim
    avg = v.iloc[-60:].mean()
    if avg <= 0:
        return reclaim
    # climax: a >1.8x-average volume spike in the last ~15 bars (capitulation)
    recent = v.iloc[-15:]
    climax = float((recent / avg).max() >= 1.8)
    # dry-up: the most recent 3 bars' volume is below the 15-bar average (selling done)
    dryup = float(v.iloc[-3:].mean() < recent.mean() * 0.9)
    vol_sig = 0.5 * climax + 0.5 * (climax * dryup)     # dry-up only counts after a climax
    return float(np.clip(reclaim + 0.5 * vol_sig, 0.0, 1.0))


def _timing_band(cyc: dict) -> float:
    ph = cyc.get("dc_phase")
    if ph in ("approaching_band", "in_band"):
        return 1.0
    if ph == "mid":
        return 0.4
    if ph == "stretched":
        return 0.5          # overdue — a low could form, but the count is unreliable
    return 0.0              # 'new' — a low just formed (handled by the confirmed stage)


def assess(close: pd.Series, high: pd.Series | None, volume: pd.Series | None, *,
           cyc: dict, mtf: dict, early: dict, wo: dict, bench: pd.Series | None = None,
           regime: dict | None = None) -> dict | None:
    """Point-in-time bottom-formation radar. Returns the raw score + per-leg breakdown +
    veto flags + the proposed stage, or None when the cycle isn't computable. The raw
    score becomes a probability only via the fitted calibration curve."""
    if not cyc or not mtf.get("D"):
        return None
    c = close.dropna()
    if len(c) < 120:
        return None

    legs = {
        "timing_band": _timing_band(cyc),
        "divergence": _divergence_grade(c, mtf),
        "mtf_turn": float(np.clip(sum(w * _tf_up(mtf.get(tf, {})) for tf, w in _TF_W.items()), 0, 1)),
        "vol_contract": _vol_contraction(c),
        "rs_hold": _rs_hold(c, bench),
        "deter_easing": _deter_easing(c, bench),
        "capitulation": _capitulation(c, volume, cyc, wo),
    }
    raw = 100.0 * sum(_W[k] * legs[k] for k in _W)

    # ── hard vetos (the dead-cat discriminators) ────────────────────────────────
    vetos = []
    if cyc.get("failed_cycle"):
        vetos.append("failed_cycle")
    reg = (regime or {}).get("regime")
    if reg == "bear":
        vetos.append("htf_downtrend")
    if (wo or {}).get("level") == "high" and (regime or {}).get("put_absent"):
        vetos.append("knife_put_absent")     # deep washout + no Fed put = falling knife
    # nothing actually LEADING (no divergence arm AND no MTF turn) — not a setup yet
    if legs["divergence"] <= 0.0 and legs["mtf_turn"] < 0.2:
        vetos.append("no_lead")
    blocked = bool(vetos)

    # ── proposed stage (maps onto the existing ladder; price confirmation gates up) ──
    above10 = cyc.get("above_ma10")
    swing = cyc.get("swing_low") or cyc.get("cand_swing")
    d = mtf.get("D", {})
    confirmed = bool(swing and above10 and (d.get("macd_cross_up") or d.get("macd_pos")))
    near_low = cyc.get("dc_phase") in ("approaching_band", "in_band")
    if blocked:
        stage = "blocked"
    elif confirmed:
        stage = "confirmed"
    elif swing and above10:
        stage = "turning"
    elif near_low and raw >= 45 and (legs["divergence"] > 0 or legs["mtf_turn"] >= 0.2):
        stage = "primed"               # the anticipatory, pre-confirmation call
    else:
        stage = "watch"

    return {"raw": round(raw, 1), "legs": {k: round(v, 2) for k, v in legs.items()},
            "vetos": vetos, "blocked": blocked, "stage": stage,
            "has_volume": volume is not None and len(volume) > 0}
