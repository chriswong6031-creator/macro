"""THE cycle ontology — single source of truth for position/phase/turn/stance
semantics across cycle.html, markets.html, country_cycles, sector_cycles(_china),
sector_central(_china).

site/cycle_ontology.js is GENERATED from this module (scripts/gen_ontology_js.py)
— never hand-edit the JS.

W1.2 (Cycle Intelligence Masterplan Phase 1, D1-W1).
Implements:
  - canonical_position(): 100·Φ(z), causal, per-frequency params (D/W/M)
  - classify_phase(): 5-phase wheel with hysteresis (confirm_persist hook)
  - detect_turns(): ZigZag v2 with confirmed_at + NP-6 fix
  - resolve_state(): full 5×8 crosswalk → 9 stances
  - transition_signal(): phase-transition badge
  - match_turns(): re-keying primitive for narrative migrator
  - project_next(): §4.5 overdue semantics (anchors at last confirmed turn)
  - export_payload(): everything JS needs, JSON-serializable

Pure pandas/numpy/stdlib; no new dependencies.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

# ─────────────────────────────────────────────────────────────────────────────
# Version — bumped on any algo or param change
# ─────────────────────────────────────────────────────────────────────────────
ONTOLOGY_VERSION = "1.0.0"
DETECTOR_VERSION = 2          # ZigZag detector version (v2 adds confirmed_at + NP-6 fix)

# ─────────────────────────────────────────────────────────────────────────────
# §1.1 Position parameter sets — declared, versioned, bindable
# ─────────────────────────────────────────────────────────────────────────────
POSITION_PARAMS: dict[str, dict] = {
    "D": {"trend_span": 252, "smooth_span": 10, "min_bars": 200,
          "vol_floor_frac": 0.25, "note": "ETFs, sectors, baskets, daily FRED tapes"},
    "W": {"trend_span": 52,  "smooth_span": 2,  "min_bars": 40,
          "vol_floor_frac": 0.25, "note": "weekly resamples"},
    "M": {"trend_span": 36,  "smooth_span": 2,  "min_bars": 24,
          "vol_floor_frac": 0.25, "note": "monthly macro tapes: Case-Shiller, DRAM ASP, ISM"},
}

# Calibration constants — may be refit by the calibration pillar; any refit bumps
# ONTOLOGY_VERSION.  68/32 match the existing _classify_phase cuts for v1 continuity.
Z_SCALE = 1.0          # σ units for the 68/32 phase-position boundaries
ZONE_HI  = 84.0        # Φ(+1σ) ≈ 84 — "Stretched"
ZONE_EHI = 68.0        # Φ(+0.47σ) ≈ 68 — "Elevated"
ZONE_ELO = 32.0        # Φ(−0.47σ) ≈ 32 — "Depressed"
ZONE_LO  = 16.0        # Φ(−1σ) ≈ 16 — "Washed out"

# §1.3 Zone bands — declared once, consumed by JS
ZONES: list[dict] = [
    {"lo": ZONE_HI,  "hi": 100.0, "word": "Stretched",  "word_zh": "超涨"},
    {"lo": ZONE_EHI, "hi": ZONE_HI,  "word": "Elevated",   "word_zh": "偏高"},
    {"lo": ZONE_ELO, "hi": ZONE_EHI, "word": "Mid-range",  "word_zh": "中位"},
    {"lo": ZONE_LO,  "hi": ZONE_ELO, "word": "Depressed",  "word_zh": "偏低"},
    {"lo": 0.0,      "hi": ZONE_LO,  "word": "Washed out", "word_zh": "超跌"},
]

# ─────────────────────────────────────────────────────────────────────────────
# §2.1 Master 5-phase wheel — SOLE owner of phase labels, shorts, hues, zh
# ─────────────────────────────────────────────────────────────────────────────
PHASES: dict[str, dict] = {
    "Trough":    {"label": "Trough",    "short": "Bottoming",    "hue": "#5b9bf0",
                  "label_zh": "底部",   "short_zh": "筑底"},
    "Recovery":  {"label": "Recovery",  "short": "Prime entry",  "hue": "#2dd4bf",
                  "label_zh": "复苏",   "short_zh": "入场"},
    "Expansion": {"label": "Expansion", "short": "Trending",     "hue": "#45b873",
                  "label_zh": "扩张",   "short_zh": "扩张"},
    "Peak":      {"label": "Peak",      "short": "Topping",      "hue": "#e0a030",
                  "label_zh": "顶部",   "short_zh": "做顶"},
    "Downturn":  {"label": "Downturn",  "short": "Rolling over", "hue": "#e0556b",
                  "label_zh": "下行",   "short_zh": "下行"},
}

# ─────────────────────────────────────────────────────────────────────────────
# §2.2 Ladder re-export + direction map (keys frozen for calibration continuity)
# ─────────────────────────────────────────────────────────────────────────────
# Import cycles only for the LADDER constant re-export; cycle_ontology itself
# never calls cycles.analyze() — that lives in sector_cycles (_record_core).
try:
    from engine.cycles import LADDER as _CYCLES_LADDER, STATE_DISPLAY as _STATE_DISPLAY
    LADDER: list[str] = list(_CYCLES_LADDER)
    LADDER_DIR: dict[str, int] = {
        k: (1 if v.get("dir") == "up" else -1 if v.get("dir") == "down" else 0)
        for k, v in _STATE_DISPLAY.items()
    }
except ImportError:
    # Fallback for standalone testing / import isolation
    LADDER = ["DECLINE", "BOTTOM WATCH", "TURN SIGNALED", "FRESH BUY",
              "RALLY ON", "TOP WATCH", "ROLLING OVER", "COUNTERTREND BOUNCE",
              "CONFIRMING TURN"]
    LADDER_DIR = {
        "DECLINE": -1, "BOTTOM WATCH": -1, "TURN SIGNALED": 1, "FRESH BUY": 1,
        "RALLY ON": 1, "TOP WATCH": 0, "ROLLING OVER": -1, "COUNTERTREND BOUNCE": 0,
        "CONFIRMING TURN": 0,
    }

# ─────────────────────────────────────────────────────────────────────────────
# §2.3 Stance vocabulary — 9 stances with en/zh/tone
# tone: bullish | bearish | neutral | caution | anticipatory
# tone drives zh up/down color-flip via existing root tokens (A17/A18):
#   bullish → green, bearish → red, neutral → no flip, caution/anticipatory → amber
# ─────────────────────────────────────────────────────────────────────────────
STANCES: dict[str, dict] = {
    "AVOID":              {"en": "Avoid",              "zh": "回避",      "tone": "bearish"},
    "WAIT":               {"en": "Wait",               "zh": "观望",      "tone": "neutral"},
    "GET READY":          {"en": "Get Ready",          "zh": "准备",      "tone": "anticipatory"},
    "BUY":                {"en": "Buy",                "zh": "买入",      "tone": "bullish"},
    "HOLD":               {"en": "Hold",               "zh": "持有",      "tone": "bullish"},
    "TRIM":               {"en": "Trim",               "zh": "减仓",      "tone": "caution"},
    "SELL":               {"en": "Sell",               "zh": "卖出",      "tone": "bearish"},
    "COUNTERTREND ONLY":  {"en": "Countertrend Only",  "zh": "仅限逆势短线", "tone": "caution"},
    "HIGH-RISK BOUNCE":   {"en": "High-Risk Bounce",   "zh": "高风险反弹", "tone": "caution"},
}

# ─────────────────────────────────────────────────────────────────────────────
# §2.3 The full 5×8 crosswalk matrix
# Keys: (phase, ladder_state) → {stance, divergence, note_key}
# note_key indexes DIVERGENCE_NOTES below.
# pos_gate: optional {"field": "pos", "op": ">="|"<", "val": float}
#   — when present, the cell has TWO sub-cells based on position.
# ─────────────────────────────────────────────────────────────────────────────
#
# Full matrix (per D1 §2.3):
#
# ladder \ phase      | Trough       | Recovery         | Expansion        | Peak                    | Downturn
# --------------------|--------------|------------------|------------------|-------------------------|------------------------
# DECLINE             | AVOID        | AVOID D          | WAIT D           | TRIM                    | AVOID
# BOTTOM WATCH        | GET READY    | GET READY        | WAIT             | COUNTERTREND ONLY D     | WAIT
# TURN SIGNALED       | BUY          | BUY              | BUY              | COUNTERTREND ONLY D     | pos≥55: CT ONLY D; <55: GET READY
# FRESH BUY           | BUY          | BUY              | BUY              | COUNTERTREND ONLY D     | pos≥55: CT ONLY D; <55: BUY
# RALLY ON            | HOLD D       | HOLD             | HOLD             | HOLD                    | HOLD D
# TOP WATCH           | WAIT D       | HOLD             | TRIM             | TRIM                    | TRIM
# ROLLING OVER        | WAIT D       | WAIT D           | TRIM             | SELL                    | SELL
# COUNTERTREND BOUNCE | HIGH-RISK    | HIGH-RISK        | HIGH-RISK        | HIGH-RISK               | HIGH-RISK

_CT = "COUNTERTREND ONLY"
_HR = "HIGH-RISK BOUNCE"

# Simple crosswalk entries without pos-gating
_SIMPLE_CROSSWALK: dict[tuple[str, str], dict] = {
    # DECLINE
    ("Trough",    "DECLINE"):            {"stance": "AVOID",      "divergence": False},
    ("Recovery",  "DECLINE"):            {"stance": "AVOID",      "divergence": True,  "note_key": "decline_recovery"},
    ("Expansion", "DECLINE"):            {"stance": "WAIT",       "divergence": True,  "note_key": "decline_expansion"},
    ("Peak",      "DECLINE"):            {"stance": "TRIM",       "divergence": False},  # clocks agree on caution
    ("Downturn",  "DECLINE"):            {"stance": "AVOID",      "divergence": False},

    # BOTTOM WATCH
    ("Trough",    "BOTTOM WATCH"):       {"stance": "GET READY",  "divergence": False},
    ("Recovery",  "BOTTOM WATCH"):       {"stance": "GET READY",  "divergence": False},
    ("Expansion", "BOTTOM WATCH"):       {"stance": "WAIT",       "divergence": False},
    ("Peak",      "BOTTOM WATCH"):       {"stance": _CT,          "divergence": True,  "note_key": "peak_buy_signal"},
    ("Downturn",  "BOTTOM WATCH"):       {"stance": "WAIT",       "divergence": False},

    # TURN SIGNALED
    ("Trough",    "TURN SIGNALED"):      {"stance": "BUY",        "divergence": False},
    ("Recovery",  "TURN SIGNALED"):      {"stance": "BUY",        "divergence": False},
    ("Expansion", "TURN SIGNALED"):      {"stance": "BUY",        "divergence": False},
    ("Peak",      "TURN SIGNALED"):      {"stance": _CT,          "divergence": True,  "note_key": "peak_buy_signal"},
    # Downturn/TURN SIGNALED: pos-gated (handled specially in resolve_state)

    # FRESH BUY
    ("Trough",    "FRESH BUY"):          {"stance": "BUY",        "divergence": False},
    ("Recovery",  "FRESH BUY"):          {"stance": "BUY",        "divergence": False},
    ("Expansion", "FRESH BUY"):          {"stance": "BUY",        "divergence": False},
    ("Peak",      "FRESH BUY"):          {"stance": _CT,          "divergence": True,  "note_key": "peak_buy_signal"},
    # Downturn/FRESH BUY: pos-gated (handled specially in resolve_state)

    # RALLY ON
    ("Trough",    "RALLY ON"):           {"stance": "HOLD",       "divergence": True,  "note_key": "sell_in_trough"},
    ("Recovery",  "RALLY ON"):           {"stance": "HOLD",       "divergence": False},
    ("Expansion", "RALLY ON"):           {"stance": "HOLD",       "divergence": False},
    ("Peak",      "RALLY ON"):           {"stance": "HOLD",       "divergence": False},
    ("Downturn",  "RALLY ON"):           {"stance": "HOLD",       "divergence": True,  "note_key": "sell_in_downturn"},

    # TOP WATCH
    ("Trough",    "TOP WATCH"):          {"stance": "WAIT",       "divergence": True,  "note_key": "sell_in_trough"},
    ("Recovery",  "TOP WATCH"):          {"stance": "HOLD",       "divergence": False},  # don't-chase
    ("Expansion", "TOP WATCH"):          {"stance": "TRIM",       "divergence": False},
    ("Peak",      "TOP WATCH"):          {"stance": "TRIM",       "divergence": False},
    ("Downturn",  "TOP WATCH"):          {"stance": "TRIM",       "divergence": False},

    # ROLLING OVER
    ("Trough",    "ROLLING OVER"):       {"stance": "WAIT",       "divergence": True,  "note_key": "sell_in_trough"},
    ("Recovery",  "ROLLING OVER"):       {"stance": "WAIT",       "divergence": True,  "note_key": "decline_recovery"},
    ("Expansion", "ROLLING OVER"):       {"stance": "TRIM",       "divergence": False},
    ("Peak",      "ROLLING OVER"):       {"stance": "SELL",       "divergence": False},
    ("Downturn",  "ROLLING OVER"):       {"stance": "SELL",       "divergence": False},

    # COUNTERTREND BOUNCE
    ("Trough",    "COUNTERTREND BOUNCE"): {"stance": _HR,         "divergence": False},
    ("Recovery",  "COUNTERTREND BOUNCE"): {"stance": _HR,         "divergence": False},
    ("Expansion", "COUNTERTREND BOUNCE"): {"stance": _HR,         "divergence": False},
    ("Peak",      "COUNTERTREND BOUNCE"): {"stance": _HR,         "divergence": False},
    ("Downturn",  "COUNTERTREND BOUNCE"): {"stance": _HR,         "divergence": False},

    # CONFIRMING TURN — HK-specific: evidence witnesses present but weekly unconfirmed.
    # Softer than COUNTERTREND BOUNCE (watch/context); caution stance across all phases.
    ("Trough",    "CONFIRMING TURN"):     {"stance": _HR,         "divergence": False},
    ("Recovery",  "CONFIRMING TURN"):     {"stance": _HR,         "divergence": False},
    ("Expansion", "CONFIRMING TURN"):     {"stance": _HR,         "divergence": False},
    ("Peak",      "CONFIRMING TURN"):     {"stance": _HR,         "divergence": False},
    ("Downturn",  "CONFIRMING TURN"):     {"stance": _HR,         "divergence": False},
}

# Divergence notes in EN/ZH (keyed by note_key above)
DIVERGENCE_NOTES: dict[str, dict[str, str]] = {
    "peak_buy_signal": {
        "en": ("Cycle read is Topping; the daily timing ladder is hunting a short-term low. "
               "Any buy here is countertrend only."),
        "zh": ("周期读数为做顶中；日线时点阶梯正在寻找短线低点。此处任何买入仅属逆势短线。"),
    },
    "extended_uptrend": {
        "en": ("Position is stretched above trend, but the 200-day trend and momentum are still "
               "up — a late-stage continuation, not a fresh entry. Don't chase; this is NOT a "
               "topping or countertrend signal."),
        "zh": ("位置已高于趋势并偏拉伸，但200日趋势与动量仍向上——属晚段延续，而非新入场点。"
               "不宜追高；这并非见顶或逆势信号。"),
    },
    "decline_recovery": {
        "en": ("The broader phase suggests recovery, but the daily cycle has failed. "
               "Phase confidence is low; treat as bottoming rather than confirmed entry."),
        "zh": ("更大级别阶段显示复苏，但日线周期已失败。阶段置信度低；视为筑底而非确认入场。"),
    },
    "decline_expansion": {
        "en": ("The trend phase is Expansion but the daily cycle is in Decline. "
               "Tactical caution warranted; wait for daily recovery confirmation."),
        "zh": ("趋势阶段为扩张，但日线周期处于下行。需战术谨慎；等待日线周期恢复确认。"),
    },
    "sell_in_trough": {
        "en": ("Cycle read is washed out / bottoming; daily sell signals are late-downleg noise. "
               "Stance is Wait — the sell opportunity has passed."),
        "zh": ("周期读数为超跌/筑底阶段；日线卖出信号属下行尾段噪音。立场观望——卖出时机已过。"),
    },
    "sell_in_downturn": {
        "en": ("The cycle is in Downturn but the daily ladder shows a rallying structure. "
               "Hold, but trim into strength — the larger trend is down."),
        "zh": ("周期处于下行阶段，但日线阶梯显示反弹结构。持有，但逢强减仓——更大趋势向下。"),
    },
    "countertrend_downturn_high": {
        "en": ("Position is elevated in a Downturn phase. Daily buy signal is countertrend — "
               "the larger cycle suggests the rebound will fail."),
        "zh": ("下行阶段中位置偏高。日线买入信号属逆势——更大级别周期暗示反弹将失败。"),
    },
    "none": {"en": "", "zh": ""},
}

# Signal TTL: transition badge stays visible this many bars after the phase change
SIGNAL_TTL_BARS = 10

# ─────────────────────────────────────────────────────────────────────────────
# §3 ZigZag turn primitive
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class TurnParams:
    pct: float                 # ZigZag reversal threshold (%)
    basis: str = "close_tr"   # "close_price" | "close_tr"
    freq: str  = "D"          # "D" | "W" | "M"
    version: int = DETECTOR_VERSION

    def params_hash(self) -> str:
        s = f"{self.pct}:{self.basis}:{self.freq}:{self.version}"
        return hashlib.sha1(s.encode()).hexdigest()[:8]


# ─────────────────────────────────────────────────────────────────────────────
# §3.3 / ruling A5 — turn_epoch: the ONE identity for a (basis, zz_params, detector)
# tuple.  An epoch bump atomically re-keys narratives (scripts/rekey_narratives.py),
# re-runs backfill, re-fits hazard, re-stamps the experiments registry (W4.8).
#   file scheme: narratives.<epoch>.json
#   collapse of the three former version keys (basis_version / detector_version /
#   params_hash) into ONE stamp per D1-§3.3 + ruling A5.
# ─────────────────────────────────────────────────────────────────────────────

# The legacy, un-suffixed narratives.json (data/*/narratives.json) is the CURRENT
# total-return epoch by definition — it was researched against the close_tr, 14%-frozen
# turn set that ships today.  Loaders that fall back to the un-suffixed file tag it with
# this constant so provenance is never ambiguous.  (Matches the keystone gate's
# EPOCH="tr_v0" stamp in scripts/keystone_position_gate_phase0.py.)
LEGACY_TR_EPOCH = "tr_v0"

# Human-readable prefix on every computed epoch tag so a filename reveals its basis at a
# glance:  price_a1b2c3d4  /  tr_9f8e7d6c .
_EPOCH_BASIS_PREFIX: dict[str, str] = {
    "close_price": "price",
    "close_tr":    "tr",
}


def turn_epoch(
    basis: str,
    zz_params: dict | float,
    *,
    detector_version: int = DETECTOR_VERSION,
) -> str:
    """The turn_epoch tag = short hash of (basis, zz_params, detector_version).

    Ruling A5: ONE re-key scheme, D1-owned.  Any change to the price basis, the
    ZigZag reversal threshold(s)/rule, or the detector algorithm produces a NEW epoch,
    which the migrator re-keys narratives into (`narratives.<epoch>.json`).

    Parameters
    ----------
    basis : str
        "close_price" | "close_tr" (the price basis the turns were detected on).
    zz_params : dict | float
        The ZigZag parametrisation.  A bare float is treated as {"pct": <float>}.
        Serialised canonically (sorted keys) so ordering never perturbs the hash.
    detector_version : int
        The ZigZag detector algorithm version (DETECTOR_VERSION by default).

    Returns
    -------
    str
        "<basis_prefix>_<8-hex>", e.g. "tr_1a2b3c4d" / "price_9f8e7d6c".

    Notes
    -----
    This is a PURE function of its declared inputs — the same tuple always yields the
    same tag, on any machine, forever.  That determinism is what lets a builder compute
    "which narratives file is mine" without reading any state.
    """
    if isinstance(zz_params, (int, float)) and not isinstance(zz_params, bool):
        zz_params = {"pct": float(zz_params)}
    if not isinstance(zz_params, dict):
        raise TypeError(f"turn_epoch: zz_params must be dict or float, got {type(zz_params).__name__}")

    canon = json.dumps(
        {"basis": basis, "zz": zz_params, "detector_version": int(detector_version)},
        sort_keys=True, separators=(",", ":"),
    )
    h = hashlib.sha1(canon.encode()).hexdigest()[:8]
    prefix = _EPOCH_BASIS_PREFIX.get(basis, basis.replace("close_", "") or "x")
    return f"{prefix}_{h}"


# Default turn detection thresholds per family
TURN_DETECTOR_DEFAULTS: dict = {
    "pct_sector": 14.0,
    "pct_country": 14.0,
    "pct_cn": 18.0,
    "pct_basket_vol_scaled": True,  # vol-scaled for thematic baskets
    "version": DETECTOR_VERSION,
}

# Declared sub-detector roles (find_troughs, _pivots stay in cycles.py)
SUB_DETECTORS: dict[str, str] = {
    "find_troughs": "timing-ladder daily/investor cycle lows — NOT cycle turns",
    "_pivots":      "RSI-divergence internal pivot utility — NOT cycle turns",
}

# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _normal_cdf(z: float) -> float:
    """Standard normal CDF via math.erf — pure stdlib, no scipy."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _vec_normal_cdf(z_arr: np.ndarray) -> np.ndarray:
    """Vectorised normal CDF, element-wise via math.erf."""
    _cdf = np.frompyfunc(lambda z: 0.5 * (1.0 + math.erf(z / math.sqrt(2.0))), 1, 1)
    return _cdf(z_arr).astype(float)


def _yf(ts: "pd.Timestamp") -> float:
    """Decimal year (day-precision) — shared x-axis convention."""
    return ts.year + (ts.dayofyear - 1) / 365.25


def _x_to_ym(x: float) -> str:
    """Decimal year → 'YYYY-MM' string."""
    yr = int(x)
    mo = min(12, max(1, int(round((x - yr) * 12)) + 1))
    if mo == 13:
        yr, mo = yr + 1, 1
    return f"{yr}-{mo:02d}"


# ─────────────────────────────────────────────────────────────────────────────
# §1.1 canonical_position()
# 100·Φ(z) where z = EMA-detrended log residual / EWMA vol (causal vol floor)
# ─────────────────────────────────────────────────────────────────────────────

def canonical_position(
    close: "pd.Series",
    *,
    freq: str = "D",
    trend_span: int | None = None,
    smooth_span: int | None = None,
) -> "pd.Series":
    """Canonical cycle position: 100·Φ(z), causal.

    z_t = EMA(log-detrend residual, smooth_span) / max(EWMSTD, 0.25·expanding_median(EWMSTD))

    Parameters
    ----------
    close : pd.Series  Price series (any basis — basis declared by caller).
    freq  : str        "D", "W", or "M" — selects the declared POSITION_PARAMS set.
    trend_span, smooth_span : override the param-set values (proxy-registry use only).

    Returns
    -------
    pd.Series  0–100, same index as `close`.  NaN where insufficient history.
    """
    params = POSITION_PARAMS.get(freq, POSITION_PARAMS["D"])
    ts = int(trend_span or params["trend_span"])
    ss = int(smooth_span or params["smooth_span"])
    vol_floor_frac = float(params["vol_floor_frac"])
    min_bars = int(params["min_bars"])

    c = close.dropna()
    if len(c) < min_bars:
        return pd.Series(np.nan, index=close.index, dtype=float)

    # Step 1: log-detrend (EMA trend removal, causal)
    log_c = np.log(c.clip(lower=1e-12))
    ema_trend = log_c.ewm(span=ts, min_periods=ts // 2).mean()
    d = log_c - ema_trend                     # residual (log-detrended)

    # Step 2: smooth the residual
    d_smooth = d.ewm(span=ss, min_periods=1).mean()

    # Step 3: EWMA vol of the raw residual (NOT the smoothed one)
    sigma = d.ewm(span=ts, min_periods=ts // 3).std()

    # Step 4: causal vol floor — expanding median of sigma
    sigma_np = sigma.to_numpy().copy()
    exp_med = np.full_like(sigma_np, np.nan)
    running: list[float] = []
    for i, v in enumerate(sigma_np):
        if not np.isnan(v):
            running.append(v)
        if running:
            exp_med[i] = float(np.median(running))
    exp_med_series = pd.Series(exp_med, index=sigma.index)
    sigma_star = sigma.combine(exp_med_series * vol_floor_frac, max).fillna(sigma)

    # Step 5: z-score + CDF
    z = d_smooth / sigma_star.replace(0, np.nan)
    pos = (100.0 * _vec_normal_cdf(z.to_numpy())).round(2)
    result = pd.Series(pos, index=d_smooth.index)
    # Reindex back to original close index (NaN for leading NaN values)
    return result.reindex(close.index)


# ─────────────────────────────────────────────────────────────────────────────
# §2.1 classify_phase() with hysteresis
# ─────────────────────────────────────────────────────────────────────────────

def classify_phase(
    pos_now: float,
    osc_slope: float,
    w: dict,
    t3: dict,
    *,
    prev_phase: str | None = None,
    confirm_persist: int = 0,
    pending: dict | None = None,
) -> dict:
    """Classify the 5-phase wheel from position + multi-timeframe MACD votes.

    Hysteresis (NP-4 fix): when confirm_persist > 0, a phase change is only
    committed after `confirm_persist` consecutive stamps agree (causal).
    Ships OFF (confirm_persist=0) in v1 for behavioral continuity per D1 §2.1.

    Parameters
    ----------
    pos_now       : float   Current canonical position (0–100).
    osc_slope     : float   Oscillator slope (pos[now] - pos[22-bars-ago]).
    w             : dict    Weekly MTF state from cycles.mtf_snapshot.
    t3            : dict    3-day MTF state from cycles.mtf_snapshot.
    prev_phase    : str     Previous confirmed phase (for hysteresis).
    confirm_persist : int   Number of consecutive bars required to confirm a new phase.
    pending       : dict    Mutable hysteresis state: {"phase": str, "count": int}.
                            Caller must persist this between calls for hysteresis to work.

    Returns
    -------
    dict  PhaseRead:
        phase, phase_label, phase_label_zh, phase_dir,
        phase_short, phase_short_zh, phase_hue,
        votes, pending (updated hysteresis state)
    """
    # Replicate the exact logic from sector_cycles._classify_phase (sans above200 dead param)
    votes = (2 if w.get("macd_pos") else -2) + (1 if t3.get("macd_pos") else -1)
    if osc_slope > 3:
        votes += 1
    elif osc_slope < -3:
        votes -= 1
    if w.get("macd_cross_dn") or w.get("macd_curl_dn"):
        votes -= 1
    if w.get("macd_cross_up") or w.get("macd_curl_up"):
        votes += 1
    rising = votes > 0 or (votes == 0 and bool(w.get("macd_pos")))

    if pos_now >= ZONE_EHI:
        candidate = "Peak" if rising else "Downturn"
    elif pos_now <= ZONE_ELO:
        candidate = "Recovery" if rising else "Trough"
    elif rising:
        candidate = "Expansion"
    else:
        candidate = "Downturn"

    # ── Hysteresis ─────────────────────────────────────────────────────────
    if confirm_persist > 0 and prev_phase is not None:
        if pending is None:
            pending = {}
        if candidate != prev_phase:
            # Accumulate consecutive stamps agreeing on the candidate
            if pending.get("phase") == candidate:
                pending["count"] = pending.get("count", 0) + 1
            else:
                pending["phase"] = candidate
                pending["count"] = 1
            if pending["count"] >= confirm_persist:
                # Threshold crossed — commit the transition
                committed = candidate
                pending = {}
            else:
                # Hold the previous phase
                committed = prev_phase
        else:
            committed = candidate
            pending = {}
    else:
        committed = candidate
        if pending is None:
            pending = {}

    phase_meta = PHASES.get(committed, PHASES["Expansion"])
    phase_dir = "rising" if rising else "falling"
    return {
        "phase":         committed,
        "phase_label":   phase_meta["label"],
        "phase_label_zh": phase_meta["label_zh"],
        "phase_short":   phase_meta["short"],
        "phase_short_zh": phase_meta["short_zh"],
        "phase_hue":     phase_meta["hue"],
        "phase_dir":     phase_dir,
        "votes":         votes,
        "pending":       pending,
    }


# ─────────────────────────────────────────────────────────────────────────────
# §3.1 detect_turns() — ZigZag v2 with confirmed_at + NP-6 fix
# ─────────────────────────────────────────────────────────────────────────────

def detect_turns(
    close: "pd.Series",
    *,
    series_id: str,
    params: TurnParams,
    major_pct: float = 20.0,
) -> list[dict]:
    """ZigZag v2: detect alternating peaks/troughs with confirmed_at (NP-2 fix).

    Key additions over _detect_swings (v1):
    - confirmed_at: the bar index/date at which the reversal threshold was first
      crossed (when the turn became KNOWABLE). Required for PIT-honest grading.
    - confirm_lag_bars: bars between the pivot and its confirmation.
    - NP-6 fix: upward-seed fix — pre-first-pivot reference tracks BOTH directions
      (max and min), so a series opening on a rally correctly seeds its first peak.
    - turn_id: 'series_id:kind:YYYY-MM' (month-quantized; absorbs typical re-datings).
    - Provisional flag: the last entry is always provisional (open running extreme).

    Parameters
    ----------
    close      : pd.Series   Close price series.
    series_id  : str         Identifier for turn_id generation (e.g. "xlk", "XLK").
    params     : TurnParams  Detection parameters (pct, basis, freq, version).
    major_pct  : float       Magnitude threshold for the "major" flag.

    Returns
    -------
    list[dict]  Turn records in wire format (see D1 §3.2).
    """
    c = close.dropna()
    arr = c.to_numpy()
    n = len(arr)
    if n < 30:
        return []
    th = params.pct / 100.0
    phash = params.params_hash()

    # piv: (pivot_idx, kind, confirmed_at_idx)
    piv: list[tuple[int, str, int]] = []
    trend = 0             # 0 = unknown direction, +1 = up-leg, -1 = down-leg
    ext_i, ext_px = 0, arr[0]

    # NP-6 fix: track BOTH a running min AND max for the unknown-leg seed,
    # so a series that opens on a rally correctly identifies its first peak.
    ref_min_px = arr[0]
    ref_min_i  = 0
    ref_max_px = arr[0]
    ref_max_i  = 0

    for i in range(1, n):
        p = arr[i]
        if trend == 0:
            # Update both running min and max during unknown leg
            if p < ref_min_px:
                ref_min_px = p
                ref_min_i  = i
            if p > ref_max_px:
                ref_max_px = p
                ref_max_i  = i

            if p >= ref_min_px * (1 + th):
                # Price rose ≥ pct from running min → the running min was a trough
                piv.append((ref_min_i, "trough", i))
                trend, ext_i, ext_px = 1, i, p
            elif p <= ref_max_px * (1 - th):
                # Price fell ≥ pct from running max → the running max was a peak
                piv.append((ref_max_i, "peak", i))
                trend, ext_i, ext_px = -1, i, p

        elif trend == 1:
            if p > ext_px:
                ext_i, ext_px = i, p
            elif p <= ext_px * (1 - th):
                piv.append((ext_i, "peak", i))
                trend, ext_i, ext_px = -1, i, p
        else:  # trend == -1
            if p < ext_px:
                ext_i, ext_px = i, p
            elif p >= ext_px * (1 + th):
                piv.append((ext_i, "trough", i))
                trend, ext_i, ext_px = 1, i, p

    # Provisional final entry (open running extreme)
    prov_kind = "peak" if trend == 1 else "trough" if trend == -1 else "peak"
    piv.append((ext_i, prov_kind, n - 1))  # confirmed_at = last bar (still open)

    out: list[dict] = []
    for n_, (piv_i, kind, conf_i) in enumerate(piv):
        ts = c.index[piv_i]
        conf_ts = c.index[min(conf_i, n - 1)]
        prev_px = arr[piv[n_ - 1][0]] if n_ else None
        mag = round(abs(arr[piv_i] - prev_px) / prev_px * 100.0, 1) if prev_px else None
        t_ym = ts.strftime("%Y-%m")
        is_prov = (n_ == len(piv) - 1)

        # turn_id: month-quantized; add -b suffix on collision (ZigZag alternates,
        # so same-month same-kind collisions are very rare — no need to pre-scan)
        turn_id = f"{series_id}:{kind}:{t_ym}"

        out.append({
            "turn_id":         turn_id,
            "k":               kind,
            "date":            str(ts.date()),
            "t":               t_ym,
            "x":               round(_yf(ts), 3),
            "px":              round(float(arr[piv_i]), 4),
            "basis":           params.basis,
            "mag_pct":         mag,
            "major":           bool(mag is not None and mag >= major_pct),
            "provisional":     is_prov,
            "confirmed_at":    str(conf_ts.date()),
            "confirm_lag_bars": int(conf_i - piv_i),
            "detector": {
                "name":        "zigzag",
                "pct":         params.pct,
                "version":     params.version,
                "params_hash": phash,
            },
        })
    return out


# ─────────────────────────────────────────────────────────────────────────────
# §3.1b realized_extrema_turns() — INDEPENDENT ground-truth turns (ruling A6/C2)
#
# The audit's ruling A6 (masterplan §1) flags that grading the ZigZag detector's
# projected turns against the SAME ZigZag detector's confirmed turns is circular —
# "the detector grades itself".  W2.4's turn precision/recall therefore needs a
# ground-truth turn set defined WITHOUT the ZigZag / detect_turns machinery.
#
# realized_extrema_turns() is that independent oracle.  It never calls
# detect_turns / _detect_swings / find_troughs; it is a self-contained
# forward-realized-move segmentation:
#
#   1. Walk the (optionally month-resampled) close series left→right holding a
#      running extreme.  A candidate PEAK is the running MAX; a candidate TROUGH
#      the running MIN.
#   2. A candidate is PROMOTED to a confirmed turn the first time price REVERSES
#      by >= min_move_pct FROM that extreme, in the OPPOSITE direction.  The turn
#      DATE is the bar of the extreme (argmax/argmin); the CONFIRM date is the bar
#      where the reversal threshold was first crossed.
#   3. Turns strictly alternate peak/trough (a peak can only be followed by a
#      trough and vice-versa), enforced by flipping the tracked direction on each
#      promotion.
#
# This IS a threshold-reversal rule, like ZigZag — there is no threshold-free way
# to define "a turn" on a noisy price series, and pretending otherwise would just
# hide a threshold.  Independence is achieved along THREE axes the audit cares about:
#
#   (a) IMPLEMENTATION independence — a separate code path with no shared state,
#       constants, or helpers with detect_turns.  A bug (or a deliberate tweak) in
#       detect_turns cannot move a realized_extrema_turns output.
#   (b) PARAMETER independence — its min_move_pct is a DISTINCT knob from the
#       stamp-time ZigZag pct (14/18%).  The default (min_move_pct=20 for the
#       "major move" bar) is deliberately DIFFERENT from the 14/18% stamp threshold,
#       so ground truth is the set of *material* reversals, not the same swing set
#       the detector already emitted.  test_promise_graders proves that perturbing
#       the ZigZag pct changes detect_turns turns but NOT realized_extrema_turns.
#   (c) BASIS/CADENCE independence — it grades against realized forward moves on the
#       actual price path; it does not consume any stamped field (proj/phase/pos).
#
# The remaining shared axis — both read the same close series — is unavoidable and
# CORRECT: ground truth for "did a turn happen in the price" must be a function of
# the price.  The point of A6 is that truth must not be a function of the DETECTOR;
# that is what this guarantees.
# ─────────────────────────────────────────────────────────────────────────────

def realized_extrema_turns(
    close: "pd.Series",
    *,
    series_id: str = "",
    min_move_pct: float = 20.0,
    freq: str = "M",
) -> list[dict]:
    """Independent ground-truth turns from forward-realized extrema (ruling A6/C2).

    Ground truth for turn precision/recall (D2 §3.1) — defined WITHOUT the ZigZag
    detector so the detector is never graded against itself.  A confirmed turn is
    the argmax/argmin of a price leg that was subsequently reversed by at least
    ``min_move_pct``, in the opposite direction.

    Parameters
    ----------
    close        : pd.Series   Close price series (DatetimeIndex).  Graded on the
                               SAME price basis the stamps were computed on
                               (close_price for ETFs; Shenwan index close for CN).
    series_id    : str         Identifier used to build turn_id strings.
    min_move_pct : float       Minimum reversal (in %) FROM the extreme required to
                               CONFIRM that the extreme was a turn.  This is the
                               ONLY threshold; it is deliberately DISTINCT from the
                               stamp-time ZigZag pct so truth is not the detector's
                               own swing set (ruling A6).  Default 20% ("major move").
    freq         : str         "M" resamples to month-end closes first (matches the
                               monthly stamp cadence — a turn is dated to a month,
                               which is the granularity projections carry).  "D"
                               grades on the daily path.  Default "M".

    Returns
    -------
    list[dict]   Confirmed turns (NEVER the provisional open leg), each::

        {"turn_id": "<series_id>:<kind>:<YYYY-MM>",
         "k": "peak"|"trough",
         "date": "YYYY-MM-DD",       # bar of the extreme (the turn itself)
         "t":    "YYYY-MM",          # month-quantized
         "px":   <float>,            # price at the extreme
         "confirmed_at": "YYYY-MM-DD",  # bar the reversal threshold was crossed
         "confirm_lag_bars": <int>,
         "min_move_pct": <float>,    # the threshold that confirmed it
         "source": "realized_extrema"}   # provenance tag — NOT a detect_turns turn

    Notes
    -----
    - Only CONFIRMED turns are returned; the final open leg (whose reversal has not
      yet happened) is excluded — grading against an unconfirmed extreme would be a
      look-ahead into the future the stamp could not have seen matter yet.
    - Determinism: pure function of (close, min_move_pct, freq).  No RNG, no I/O.
    """
    if close is None:
        return []
    c = close.dropna()
    if freq and freq.upper().startswith("M"):
        # Month-end close: the projection cadence is monthly, so ground-truth turns
        # are dated to a month.  Resampling FIRST (a) matches that granularity and
        # (b) removes intramonth noise that would otherwise fragment a leg.
        c = c.resample("ME").last().dropna()
    arr = c.to_numpy(dtype=float)
    idx = c.index
    n = len(arr)
    if n < 4:
        return []

    th = float(min_move_pct) / 100.0
    turns: list[tuple[int, str, int]] = []   # (extreme_i, kind, confirm_i)

    # Seed: track BOTH a running max and running min until the first material move
    # decides the opening direction (mirrors the NP-6 dual-seed logic conceptually,
    # but is a wholly separate code path — no shared state with detect_turns).
    trend = 0                       # 0 unknown, +1 up-leg (seeking a peak), -1 down-leg
    ext_i, ext_px = 0, arr[0]
    ref_max_px, ref_max_i = arr[0], 0
    ref_min_px, ref_min_i = arr[0], 0

    for i in range(1, n):
        p = arr[i]
        if trend == 0:
            if p > ref_max_px:
                ref_max_px, ref_max_i = p, i
            if p < ref_min_px:
                ref_min_px, ref_min_i = p, i
            # First material move decides direction AND retro-confirms the seed extreme.
            if p >= ref_min_px * (1 + th):
                turns.append((ref_min_i, "trough", i))
                trend, ext_i, ext_px = 1, i, p
            elif p <= ref_max_px * (1 - th):
                turns.append((ref_max_i, "peak", i))
                trend, ext_i, ext_px = -1, i, p
        elif trend == 1:            # seeking a peak: track the running max
            if p > ext_px:
                ext_i, ext_px = i, p
            elif p <= ext_px * (1 - th):   # reversed down >= th FROM the max → peak confirmed
                turns.append((ext_i, "peak", i))
                trend, ext_i, ext_px = -1, i, p
        else:                       # trend == -1, seeking a trough: track running min
            if p < ext_px:
                ext_i, ext_px = i, p
            elif p >= ext_px * (1 + th):   # reversed up >= th FROM the min → trough confirmed
                turns.append((ext_i, "trough", i))
                trend, ext_i, ext_px = 1, i, p

    out: list[dict] = []
    for ext_i, kind, conf_i in turns:
        ts = idx[ext_i]
        conf_ts = idx[min(conf_i, n - 1)]
        out.append({
            "turn_id":          f"{series_id}:{kind}:{ts.strftime('%Y-%m')}",
            "k":                kind,
            "date":             str(ts.date()),
            "t":                ts.strftime("%Y-%m"),
            "px":               round(float(arr[ext_i]), 4),
            "confirmed_at":     str(conf_ts.date()),
            "confirm_lag_bars": int(conf_i - ext_i),
            "min_move_pct":     float(min_move_pct),
            "source":           "realized_extrema",
        })
    return out


# ─────────────────────────────────────────────────────────────────────────────
# §4.2 resolve_state() — crosswalk + overrides → stance, divergence, tone
# ─────────────────────────────────────────────────────────────────────────────

def resolve_state(
    *,
    pos: float,
    phase: str,
    phase_dir: str,
    ladder_state: str,
    dc_phase: str | None = None,
    ic_phase: str | None = None,
    failed_cycle: bool = False,
    trend_up: bool = False,
) -> dict:
    """Resolve the full state for a single instrument bar.

    Rules (ordered):
    1. failed_cycle override: DECLINE + failed_cycle in Trough/Recovery → sets
       phase_conf=low; stance never softer than AVOID in those phases.
    2. Position-gated cells (Downturn × TURN SIGNALED/FRESH BUY).
    3. Matrix lookup from _SIMPLE_CROSSWALK.
    3b. trend_up softening of the Peak buy-signal cells (see below).
    4. Raises ValueError on unknown phase/ladder_state.

    trend_up: the name is in a CONFIRMED uptrend (above its long-term trend AND
    momentum still rising). A "Peak" phase is high-position AND rising by
    construction (classify_phase routes high+falling to Downturn), so the
    ("Peak", buy-ladder) cells otherwise fire "Countertrend Only / Topping" on
    every stretched-but-still-rising name — a read that contradicts the trend it
    is riding. When trend_up, those cells soften to a "don't-chase / extended"
    HOLD instead. A stretched bounce in a DOWNtrend (trend_up False) keeps the
    countertrend read; a genuinely rolling-over name classifies as Downturn and
    is unaffected.

    Returns
    -------
    dict:
        stance, stance_zh, tone,
        divergence, divergence_note, divergence_note_zh,
        clocks (phase, ladder, agree),
        phase_conf ("normal" | "low"),
        failed_cycle_override (bool)
    """
    if phase not in PHASES:
        raise ValueError(f"resolve_state: unknown phase {phase!r}; expected one of {list(PHASES)}")
    if ladder_state not in LADDER:
        raise ValueError(f"resolve_state: unknown ladder_state {ladder_state!r}; expected one of {LADDER}")

    phase_conf = "normal"
    failed_override = False

    # ── 1. failed_cycle override ────────────────────────────────────────────
    if failed_cycle and ladder_state == "DECLINE":
        if phase in ("Trough", "Recovery"):
            phase_conf = "low"
            failed_override = True
        # failed_cycle + DECLINE: stance comes from the matrix but is never
        # softened below AVOID; enforced by the matrix cell (Trough→AVOID,
        # Recovery→AVOID+D) — no additional override needed.

    # ── 2. Position-gated cells for Downturn + buy signals ─────────────────
    note_key = "none"
    if phase == "Downturn" and ladder_state in ("TURN SIGNALED", "FRESH BUY"):
        if pos >= 55.0:
            stance = "COUNTERTREND ONLY"
            divergence = True
            note_key = "countertrend_downturn_high"
        else:
            stance = "GET READY" if ladder_state == "TURN SIGNALED" else "BUY"
            # BUY (partial) per D1 — we emit BUY; the "partial" qualifier is in
            # the divergence note.  No divergence flag when pos < 55.
            divergence = False
        cell = None  # skip matrix lookup
    else:
        # ── 3. Matrix lookup ────────────────────────────────────────────────
        cell = _SIMPLE_CROSSWALK.get((phase, ladder_state))
        if cell is None:
            raise ValueError(
                f"resolve_state: no crosswalk entry for ({phase!r}, {ladder_state!r})"
            )
        stance = cell["stance"]
        divergence = cell.get("divergence", False)
        note_key = cell.get("note_key", "none")

    # ── 3b. trend_up softening of the Peak buy-signal cells ────────────────
    # ("Peak", BOTTOM WATCH / TURN SIGNALED / FRESH BUY) => COUNTERTREND ONLY + "topping" note.
    # But a "Peak" is high-position AND still rising (high+falling => Downturn), so a fresh daily
    # buy signal on a name that is ALSO above its long-term trend is trend-CONTINUATION, not
    # countertrend — the hard "topping / countertrend only" read overclaims a reversal. Soften to
    # a "don't-chase / extended" HOLD (no divergence, no topping note). Downtrend bounces
    # (trend_up False) and rolling-over names (phase == Downturn) are untouched.
    if (trend_up and phase == "Peak"
            and ladder_state in ("BOTTOM WATCH", "TURN SIGNALED", "FRESH BUY")):
        stance = "HOLD"
        divergence = False
        note_key = "extended_uptrend"

    stance_meta = STANCES[stance]
    note = DIVERGENCE_NOTES.get(note_key, DIVERGENCE_NOTES["none"])

    return {
        "stance":              stance,
        "stance_zh":           stance_meta["zh"],
        "tone":                stance_meta["tone"],
        "divergence":          divergence,
        "divergence_note":     note["en"],
        "divergence_note_zh":  note["zh"],
        "clocks": {
            "phase":   phase,
            "ladder":  ladder_state,
            "agree":   not divergence,
        },
        "phase_conf":            phase_conf,
        "failed_cycle_override": failed_override,
    }


# ─────────────────────────────────────────────────────────────────────────────
# §2.4 transition_signal()
# ─────────────────────────────────────────────────────────────────────────────

def transition_signal(
    prev_phase: str | None,
    phase: str,
    ladder_state: str,
    phase_age_bars: int = 0,
) -> str | None:
    """Phase-transition badge: BUY on Trough→Recovery, SELL on Peak→Downturn.

    The badge only fires when:
    - The phase changed in the last SIGNAL_TTL_BARS bars (phase_age_bars < TTL)
    - The ladder confirms (TURN SIGNALED or FRESH BUY for BUY; TOP WATCH or
      ROLLING OVER or DECLINE for SELL)

    By construction the badge cannot contradict either clock.
    """
    if phase_age_bars >= SIGNAL_TTL_BARS:
        return None

    buy_ladders  = {"TURN SIGNALED", "FRESH BUY"}
    sell_ladders = {"TOP WATCH", "ROLLING OVER", "DECLINE"}

    if phase == "Recovery" and prev_phase == "Trough" and ladder_state in buy_ladders:
        return "BUY"
    if phase == "Downturn" and prev_phase == "Peak" and ladder_state in sell_ladders:
        return "SELL"
    return None


# ─────────────────────────────────────────────────────────────────────────────
# §3.3 match_turns() — narrative re-keying primitive
# ─────────────────────────────────────────────────────────────────────────────

def match_turns(
    old_bindings: dict[str, Any],
    new_turns: list[dict],
    tol_days: int = 60,
) -> dict[str, Any]:
    """Match old turn-keyed bindings to new turn IDs (re-keying primitive).

    For each old binding (key may be a raw date string or a turn_id), find the
    nearest new turn of the same kind within ±tol_days.  Returns a mapping:

        {old_key: {"status": "exact"|"shifted"|"orphaned"|"new",
                   "new_turn_id": str | None,
                   "delta_days": int | None}}

    The full migrator script (scripts/migrate_narrative_keys.py) uses this
    primitive; the actual file rewrite lives there.

    Statuses
    --------
    exact   : new turn_id == old_key (no change needed; same month)
    shifted : unique match within tolerance but turn_id changed
    orphaned: no match within tolerance (or two candidates tie)
    new     : turn in new_turns with no corresponding old binding
    """
    import datetime as dt

    def _parse_date(s: str) -> dt.date | None:
        """Parse 'YYYY-MM-DD', 'YYYY-MM', or '{series}:{kind}:{YYYY-MM}' → date."""
        try:
            if len(s) == 10 and s[4] == "-" and s[7] == "-":
                return dt.date.fromisoformat(s)
            if len(s) == 7 and s[4] == "-":
                yr, mo = int(s[:4]), int(s[5:])
                return dt.date(yr, mo, 15)
            # turn_id format: series:kind:YYYY-MM
            parts = s.rsplit(":", 2)
            if len(parts) == 3:
                yr, mo = int(parts[-1][:4]), int(parts[-1][5:])
                return dt.date(yr, mo, 15)
        except (ValueError, IndexError):
            pass
        return None

    def _kind_from_key(s: str) -> str | None:
        """Extract 'trough' or 'peak' from a turn_id or infer from binding."""
        for kw in ("trough", "peak"):
            if kw in s.lower():
                return kw
        return None

    result: dict[str, Any] = {}
    matched_new_ids: set[str] = set()

    for old_key, _binding in old_bindings.items():
        old_date = _parse_date(old_key)
        old_kind = _kind_from_key(old_key)
        if old_date is None:
            result[old_key] = {"status": "orphaned", "new_turn_id": None, "delta_days": None,
                                "reason": "could not parse date from key"}
            continue

        candidates = []
        for t in new_turns:
            if t.get("provisional"):
                continue
            if old_kind and t.get("k") != old_kind:
                continue
            try:
                t_date = dt.date.fromisoformat(t["date"])
            except (KeyError, ValueError):
                continue
            delta = abs((t_date - old_date).days)
            if delta <= tol_days:
                candidates.append((delta, t))

        if len(candidates) == 0:
            result[old_key] = {"status": "orphaned", "new_turn_id": None, "delta_days": None,
                                "reason": "no turn within tolerance"}
        elif len(candidates) == 1:
            delta, t = candidates[0]
            new_id = t["turn_id"]
            matched_new_ids.add(new_id)
            if new_id == old_key:
                status = "exact"
            else:
                # Check for tie-breaking: same delta → multiple candidates with same distance
                status = "shifted"
            result[old_key] = {"status": status, "new_turn_id": new_id, "delta_days": delta}
        else:
            # Multiple candidates: sort by delta; if two share the minimum, it's a tie → orphan
            candidates.sort(key=lambda x: x[0])
            if candidates[0][0] == candidates[1][0]:
                result[old_key] = {"status": "orphaned", "new_turn_id": None, "delta_days": None,
                                    "reason": "two candidates tie within tolerance"}
            else:
                delta, t = candidates[0]
                new_id = t["turn_id"]
                matched_new_ids.add(new_id)
                result[old_key] = {"status": "shifted", "new_turn_id": new_id, "delta_days": delta}

    # Mark new turns that had no old binding
    for t in new_turns:
        if not t.get("provisional") and t["turn_id"] not in matched_new_ids:
            result[t["turn_id"]] = {"status": "new", "new_turn_id": t["turn_id"], "delta_days": 0}

    return result


# ─────────────────────────────────────────────────────────────────────────────
# §4.5 project_next() — overdue semantics (anchors at last CONFIRMED turn)
# ─────────────────────────────────────────────────────────────────────────────

def project_next(
    turns: list[dict],
    today_x: float,
) -> dict | None:
    """Next-turn projection anchored at the last CONFIRMED turn (not TODAY).

    Fixes NP-1: the incumbent _project_next re-anchors at TODAY once overdue,
    making the projected date float perpetually ~18 days ahead.  This version
    anchors at last_confirmed.x + median_half_cycle; if today > central_x the
    record emits overdue=True instead of pushing the date.

    Parameters
    ----------
    turns    : list[dict]  Turn records from detect_turns() (includes provisional).
    today_x  : float       Decimal year for today.

    Returns
    -------
    dict or None if insufficient turns.
    """
    confirmed = [t for t in turns if not t.get("provisional")]
    if len(confirmed) < 3:
        return None

    xs = [t["x"] for t in confirmed]
    halves = [xs[i] - xs[i - 1] for i in range(1, len(xs))]
    if not halves:
        return None

    med   = float(np.median(halves))
    lo_h  = float(np.percentile(halves, 25))
    hi_h  = float(np.percentile(halves, 75))
    last  = confirmed[-1]
    next_kind = "peak" if last["k"] == "trough" else "trough"

    central_x = last["x"] + med
    lo_x      = last["x"] + lo_h
    hi_x      = last["x"] + hi_h

    overdue      = today_x > central_x
    overdue_frac = round((today_x - last["x"]) / med, 3) if med > 0 else None

    return {
        "nextTurn":    next_kind,
        "central":     _x_to_ym(central_x),
        "low":         _x_to_ym(lo_x),
        "high":        _x_to_ym(hi_x),
        "central_x":   round(central_x, 3),
        "overdue":     overdue,
        "overdue_frac": overdue_frac,
        "last_confirmed_x": round(last["x"], 3),
        "last_confirmed_t": last["t"],
        "period_yrs": {
            "median": round(med * 2, 2),
            "lo":     round(lo_h * 2, 2),
            "hi":     round(hi_h * 2, 2),
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# §5.2 export_payload() — everything JS needs, JSON-serializable
# ─────────────────────────────────────────────────────────────────────────────

def export_payload() -> dict:
    """Return a JSON-serializable dict of all vocabulary data the JS layer needs.

    This is the ONLY way data flows to site/cycle_ontology.js — no logic, no
    classification functions are exposed to JS.  JS renders stamped outputs.
    """
    # Build the flat crosswalk lookup (all 40 cells, including pos-gated Downturn ones)
    crosswalk_flat: dict[str, dict] = {}
    for (phase, ladder), cell in _SIMPLE_CROSSWALK.items():
        key = f"{phase}|{ladder}"
        crosswalk_flat[key] = {
            "stance":     cell["stance"],
            "divergence": cell.get("divergence", False),
            "tone":       STANCES[cell["stance"]]["tone"],
            "en":         STANCES[cell["stance"]]["en"],
            "zh":         STANCES[cell["stance"]]["zh"],
            "note_en":    DIVERGENCE_NOTES.get(cell.get("note_key", "none"), {"en": ""})["en"],
            "note_zh":    DIVERGENCE_NOTES.get(cell.get("note_key", "none"), {"zh": ""})["zh"],
        }
    # Add pos-gated Downturn cells for JS (JS can use these for display guidance)
    for ladder_s in ("TURN SIGNALED", "FRESH BUY"):
        for pos_gate, pos_label in [(">=55", True), ("<55", False)]:
            stance = "COUNTERTREND ONLY" if pos_gate == ">=55" else (
                "GET READY" if ladder_s == "TURN SIGNALED" else "BUY"
            )
            key = f"Downturn|{ladder_s}|pos{pos_gate}"
            crosswalk_flat[key] = {
                "stance":     stance,
                "divergence": pos_gate == ">=55",
                "tone":       STANCES[stance]["tone"],
                "en":         STANCES[stance]["en"],
                "zh":         STANCES[stance]["zh"],
                "note_en":    DIVERGENCE_NOTES["countertrend_downturn_high"]["en"] if pos_gate == ">=55" else "",
                "note_zh":    DIVERGENCE_NOTES["countertrend_downturn_high"]["zh"] if pos_gate == ">=55" else "",
                "pos_gate":   pos_gate,
            }

    return {
        "version":          ONTOLOGY_VERSION,
        "detector_version": DETECTOR_VERSION,
        "phases":           PHASES,
        "zones":            ZONES,
        "stances":          STANCES,
        "ladder":           LADDER,
        "ladder_dir":       LADDER_DIR,
        "crosswalk":        crosswalk_flat,
        "divergence_notes": DIVERGENCE_NOTES,
        "position_params":  POSITION_PARAMS,
        "turn_detector_defaults": TURN_DETECTOR_DEFAULTS,
        "signal_ttl_bars":  SIGNAL_TTL_BARS,
        "zone_hi":          ZONE_HI,
        "zone_ehi":         ZONE_EHI,
        "zone_elo":         ZONE_ELO,
        "zone_lo":          ZONE_LO,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Stance matrix registration as a versioned bindable artifact (A17)
# Written to data/cycle_ontology/stance_matrix.json
# ─────────────────────────────────────────────────────────────────────────────

def _load_stance_evidence(repo_root: str) -> dict:
    """Load the per (phase|ladder) evidence table from the W4.6 risk-calibration artifact.
    Returns {} on any error (fallback: stance matrix ships with no evidence, unchanged)."""
    try:
        p = os.path.join(repo_root, "data", "regime", "ladder_risk_calibration.json")
        if not os.path.exists(p):
            return {}
        with open(p, encoding="utf-8") as fh:
            d = json.load(fh)
        return (d.get("stance_evidence") or {}).get("cells") or {}
    except Exception:  # noqa: BLE001
        return {}


def write_stance_matrix(path: str | None = None) -> str:
    """Write the stance matrix JSON artifact (versioned, provenance fields).

    Returns the path written.
    """
    if path is None:
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(repo_root, "data", "cycle_ontology", "stance_matrix.json")

    os.makedirs(os.path.dirname(path), exist_ok=True)

    # W4.6 (R3): per (phase x ladder) backfilled vol-residualized DD / forward stats — the
    # EVIDENCE per stance cell. Read from the committed risk-calibration artifact when
    # present (fallback: no evidence). Display/bindable METADATA only — attaching it changes
    # no stance, tone, or resolve_state behavior this wave.
    # repo root = parent of data/ (path is <root>/data/cycle_ontology/stance_matrix.json)
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(path))))
    evidence = _load_stance_evidence(repo_root)

    def _ev(phase: str, ladder: str) -> dict | None:
        return evidence.get(f"{phase}|{ladder}")

    # Build human-readable matrix
    matrix: list[dict] = []
    for (phase, ladder), cell in _SIMPLE_CROSSWALK.items():
        row = {
            "phase":     phase,
            "ladder":    ladder,
            "stance":    cell["stance"],
            "divergence": cell.get("divergence", False),
            "tone":      STANCES[cell["stance"]]["tone"],
            "note_key":  cell.get("note_key", "none"),
        }
        ev = _ev(phase, ladder)
        if ev is not None:
            row["evidence"] = ev
        matrix.append(row)
    # Downturn pos-gated cells
    for ladder_s in ("TURN SIGNALED", "FRESH BUY"):
        for pos_gate in (">=55", "<55"):
            stance = "COUNTERTREND ONLY" if pos_gate == ">=55" else (
                "GET READY" if ladder_s == "TURN SIGNALED" else "BUY"
            )
            row = {
                "phase":     "Downturn",
                "ladder":    ladder_s,
                "stance":    stance,
                "divergence": pos_gate == ">=55",
                "tone":      STANCES[stance]["tone"],
                "pos_gate":  pos_gate,
            }
            ev = _ev("Downturn", ladder_s)
            if ev is not None:
                row["evidence"] = ev
            matrix.append(row)

    artifact = {
        "version":           ONTOLOGY_VERSION,
        "detector_version":  DETECTOR_VERSION,
        "provenance":        "engine/cycle_ontology.py:write_stance_matrix()",
        "generated_from":    "CROSSWALK + STANCES constants in cycle_ontology.py",
        "n_cells":           len(matrix),
        "n_phases":          len(PHASES),
        "n_ladder_states":   len(LADDER),
        "matrix":            matrix,
        "stances":           STANCES,
    }

    with open(path, "w", encoding="utf-8") as fh:
        json.dump(artifact, fh, indent=2, ensure_ascii=False)
    return path
