"""Durable-bottom / Euphoric-top Confluence Organ — display-tier, deterministic.

Scores two mirrored 0-100 sides (washout bottom / euphoric top) per complex
commodity member AND at the sector-index level.  Deterministic: every condition
is a boolean derived from existing engine outputs; no scoring, no backtested
weights beyond the config-declared constants.

Each side is split into two sub-groups:
  Bottom: capitulation group (washing out / knife) + turn group (bottom confirming)
  Top:    euphoria group (blowing off) + rollover group (top confirming)
Sub-scores are availability-normalised exactly like the combined score_side.
The state machine uses sub-scores for anticipatory vs confirmatory labelling.

Promotion gauntlet pre-registered separately in
research/COMMODITY_BOTTOM_TOP_PREREG.md.

House law:
  - LLMs do not originate, escalate, or score these signals.
  - "validated" is CI-guarded and must NOT appear in this file.
  - Null state is printed honestly; no scored authority here.
  - Returns {} on outer failure (never raises from build_confluence).
"""
from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# bilingual condition labels (EN / ZH) — shown in the receipt of fired conditions
# --------------------------------------------------------------------------- #
_LABELS: dict[str, tuple[str, str]] = {
    # BOTTOM capitulation group
    "shock_bottom":      ("Exogenous washout", "外生冲击洗盘"),
    "oversold_ltf":      ("Oversold short-term", "短周期超卖"),
    "oversold_htf":      ("Oversold longer-term", "中周期超卖"),
    "cot_short":         ("COT crowded short", "COT大幅偏空"),
    "stretch_below":     ("Deeply below its 200-day trend", "深跌破200日均线"),
    # BOTTOM turn group
    "curl":              ("Momentum curl up", "动量上钩"),
    "armed":             ("Technical arm triggered", "技术触发"),
    "bc_conf":           ("Bottom-confidence high", "底部信心高"),
    "cycle_bottom":      ("Cycle in trough/recovery", "周期处于低谷/复苏"),
    # INDEX-only bottom
    "breadth_bottom":    ("Sector breadth washout", "板块广度超卖"),
    # TOP euphoria group
    "shock_top":         ("Exogenous blow-off bid", "外生吹顶买盘"),
    "overbought_ltf":    ("Overbought short-term", "短周期超买"),
    "overbought_htf":    ("Overbought longer-term", "中周期超买"),
    "cot_long":          ("COT crowded long", "COT大幅偏多"),
    "stretch":           ("Price stretched above 200-day", "价格大幅偏离200日均线"),
    # TOP rollover group
    "curl_dn":           ("Momentum rolling over", "动量下钩"),
    "divergence":        ("Momentum diverging from trend", "动量与趋势背离"),
    "cycle_top":         ("Cycle at peak/downturn", "周期处于顶峰/下行"),
    # INDEX-only top
    "breadth_top":       ("Sector breadth euphoric", "板块广度亢奋"),
}


def _lbl(code: str) -> dict[str, str]:
    """Return a label dict for the receipt."""
    en, zh = _LABELS.get(code, (code, code))
    return {"code": code, "label_en": en, "label_zh": zh}


# --------------------------------------------------------------------------- #
# core scoring
# --------------------------------------------------------------------------- #
def score_side(
    conditions: list[tuple[str, bool, bool, float]],
) -> tuple[float | None, list[dict], int]:
    """Compute a 0-100 availability-normalised confluence score.

    Parameters
    ----------
    conditions : list of (code, fired, applicable, weight)
        code       : str identifier for the condition.
        fired      : bool — did the condition trigger?
        applicable : bool — does this condition apply given available data?
        weight     : float — relative importance (from cfg.weights).

    Returns
    -------
    score        : 0-100 float or None (if applicable weight sum == 0 or
                   n_applicable < min_applicable, caller checks min_applicable).
    fired_codes  : list of label dicts for conditions that fired.
    n_applicable : int count of applicable conditions.
    """
    w_fired = 0.0
    w_total = 0.0
    fired_codes: list[dict] = []
    n_applicable = 0

    for code, fired, applicable, weight in conditions:
        if not applicable:
            continue
        n_applicable += 1
        w_total += weight
        if fired:
            w_fired += weight
            fired_codes.append(_lbl(code))

    if w_total == 0.0:
        return None, fired_codes, n_applicable

    # fix #7: wrap in float() to prevent numpy scalar leaking out
    return float(round(100.0 * w_fired / w_total, 1)), fired_codes, n_applicable


def _safe_float(v: Any) -> float | None:
    """JSON-safe float: None for NaN/inf/non-numeric."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if not math.isfinite(f) else f


def _score_group(
    conditions: list[tuple[str, bool, bool, float]],
    group_min_applicable: int = 2,
) -> float | None:
    """Availability-normalised sub-score for a group of conditions (0-100 or None).

    Returns None if fewer than group_min_applicable conditions are applicable,
    or if applicable weight sum is zero.  group_min_applicable=0 means: return
    None only when there are literally zero applicable conditions.
    """
    w_fired = 0.0
    w_total = 0.0
    n_app = 0
    for _code, fired, applicable, weight in conditions:
        if not applicable:
            continue
        n_app += 1
        w_total += weight
        if fired:
            w_fired += weight

    if n_app < group_min_applicable or w_total == 0.0:
        return None

    return float(round(100.0 * w_fired / w_total, 1))


def _state_from_scores_cfg(
    bottom_score: float | None,
    top_score: float | None,
    n_bottom: int,
    n_top: int,
    cfg: dict,
    *,
    capitulation_score: float | None = None,
    turn_score: float | None = None,
    euphoria_score: float | None = None,
    rollover_score: float | None = None,
) -> tuple[str | None, str | None]:
    """Two-phase config-driven state machine.

    Sub-scores (capitulation/turn for bottom; euphoria/rollover for top) drive
    the anticipatory vs confirmatory state labels.  The combined bottom_score /
    top_score are used as fallback when sub-scores are None (i.e. insufficient
    applicable conditions per group).  Treats a None sub-score as -1 for
    threshold comparisons.
    """
    min_app = int(cfg.get("min_applicable", 3))
    strong = float(cfg.get("strong_threshold", 60))
    early = float(cfg.get("early_threshold", 40))

    # treat None as -1 for threshold checks
    cap  = capitulation_score if capitulation_score is not None else -1.0
    turn = turn_score         if turn_score         is not None else -1.0
    euph = euphoria_score     if euphoria_score      is not None else -1.0
    roll = rollover_score     if rollover_score      is not None else -1.0
    bot  = bottom_score       if bottom_score        is not None else -1.0
    top  = top_score          if top_score           is not None else -1.0

    # guard: if no side has enough applicable conditions, return null
    if max(n_bottom, n_top) < min_app:
        return None, "insufficient signal"

    # ------ BOTTOM states (two-phase) ------
    # "Washout bottom forming": turn confirming + capitulation context
    bottom_forming = (turn >= strong and cap >= early)
    # "Washing out — high risk": deep capitulation but no turn yet (anticipatory knife)
    washing_out    = (cap >= strong and turn < early)
    # "Basing — early bottom signs": both groups partially active OR combined score early
    basing = (
        (turn >= early and cap >= early)
        or (bottom_score is not None and bottom_score >= early)
    )

    # ------ TOP states (two-phase) ------
    # "Euphoric top — rolling over": rollover confirming + euphoria context
    top_rolling = (roll >= strong and euph >= early)
    # "Blowing off — extended": deep euphoria but no rollover yet
    blowing_off  = (euph >= strong and roll < early)
    # "Extended — late cycle": both groups partially active OR combined top score early
    extended = (
        (roll >= early and euph >= early)
        or (top_score is not None and top_score >= early)
    )

    # determine which side to award when both qualify — pick side with higher max sub-score
    # (bottom wins ties)
    bot_max = max(cap, turn, bot)
    top_max = max(euph, roll, top)

    # resolve in priority order: strongest state first, tie-break by side max
    if bottom_forming and top_rolling:
        if top_max > bot_max:
            return "Euphoric top — rolling over", None
        return "Washout bottom forming", None
    if bottom_forming:
        return "Washout bottom forming", None
    if top_rolling:
        return "Euphoric top — rolling over", None

    if washing_out and blowing_off:
        if top_max > bot_max:
            return "Blowing off — extended", None
        return "Washing out — high risk", None
    if washing_out:
        return "Washing out — high risk", None
    if blowing_off:
        return "Blowing off — extended", None

    if basing and extended:
        if top_max > bot_max:
            return "Extended — late cycle", None
        return "Basing — early bottom signs", None
    if basing:
        return "Basing — early bottom signs", None
    if extended:
        return "Extended — late cycle", None

    return "Neutral", None


# --------------------------------------------------------------------------- #
# per-member assessment
# --------------------------------------------------------------------------- #
def assess_member(
    name: str,
    klass: str,
    df: pd.DataFrame,
    cfg: dict,
    cycle_phase: str | None = None,
) -> dict:
    """Compute bottom + top confluence for one commodity member frame.

    Parameters
    ----------
    name        : member name (e.g. "gold", "wheat").
    klass       : display class string (e.g. "precious", "grain").
    df          : compute_asset output DataFrame (columns: close, ts_trend,
                  momentum_state, shock_z [opt], pos_pctile [opt], …).
    cfg         : full commodities config section.
    cycle_phase : optional phase string from cycle_positions.json for this member.

    Returns
    -------
    JSON-safe dict with state, scores, and fired-condition receipts.  Never raises —
    returns a null-state dict on any failure.
    """
    _null = {
        "name": name,
        "label": name.replace("_", " ").title(),
        "class": klass,
        "state": None,
        "null_reason": "compute error",
        "bottom_score": None,
        "top_score": None,
        "capitulation_score": None,
        "turn_score": None,
        "euphoria_score": None,
        "rollover_score": None,
        "bottom_fired": [],
        "top_fired": [],
        "n_bottom_applicable": 0,
        "n_top_applicable": 0,
    }
    try:
        return _assess_member_inner(name, klass, df, cfg, cycle_phase)
    except Exception:  # noqa: BLE001 — display organ must never break the build
        log.warning("commodity_confluence.assess_member failed for %s", name, exc_info=True)
        return _null


def _assess_member_inner(
    name: str,
    klass: str,
    df: pd.DataFrame,
    cfg: dict,
    cycle_phase: str | None,
) -> dict:
    from engine.commodity_mtf import mtf_ladder
    from engine.commodity_signals import technical_arming
    from engine.commodity_index import price_shock

    ccfg = cfg.get("confluence", {})
    wt = ccfg.get("weights", {})

    # thresholds
    stoch_os      = float(ccfg.get("stoch_oversold", 20))
    stoch_ob      = float(ccfg.get("stoch_overbought", 80))
    stoch_os_3d   = float(ccfg.get("stoch_oversold_3d", 25))
    stoch_ob_3d   = float(ccfg.get("stoch_overbought_3d", 75))
    rsi_os        = float(ccfg.get("rsi_oversold", 35))
    rsi_ob        = float(ccfg.get("rsi_overbought", 65))
    w_stoch_os    = float(ccfg.get("w_stoch_oversold", 25))
    w_stoch_ob    = float(ccfg.get("w_stoch_overbought", 75))
    w_rsi_os      = float(ccfg.get("w_rsi_oversold", 40))
    w_rsi_ob      = float(ccfg.get("w_rsi_overbought", 60))
    shock_z_macro = float(ccfg.get("shock_z_macro", 1.5))
    shock_z_price = float(ccfg.get("shock_z_price", 1.75))
    bc_score_min  = float(ccfg.get("bc_score_min", 40))
    bc_score_min_app = float(ccfg.get("bc_score_min_applicable", 10))
    cot_cs_pct    = float(ccfg.get("cot_crowded_short_pctile", 15))
    cot_cl_pct    = float(ccfg.get("cot_crowded_long_pctile", 85))
    stretch_thr   = float(ccfg.get("stretch_above_200d", 0.25))

    # weights
    w_shock        = float(wt.get("shock", 2.0))
    w_os_ltf       = float(wt.get("oversold_ltf", 1.0))
    w_os_htf       = float(wt.get("oversold_htf", 1.0))
    w_curl         = float(wt.get("curl", 1.5))
    w_armed        = float(wt.get("armed", 1.5))
    w_bc           = float(wt.get("bc_conf", 2.0))
    w_cot          = float(wt.get("cot", 1.0))
    w_cycle        = float(wt.get("cycle", 1.0))
    w_stretch      = float(wt.get("stretch", 1.5))
    w_stretch_below = float(wt.get("stretch_below", wt.get("stretch", 1.5)))
    w_div          = float(wt.get("divergence", 2.0))

    close = df["close"].dropna() if "close" in df.columns else pd.Series(dtype=float)

    # --- MTF ladder (runs on close) -----------------------------------------
    a = mtf_ladder(close) if len(close) >= 60 else {}
    mtf = a.get("mtf", {}) or {}
    ladder = a.get("ladder", {}) or {}

    d_tf  = mtf.get("D") or {}
    td_tf = mtf.get("3D") or {}
    w_tf  = mtf.get("W") or {}

    d_present = bool(d_tf)
    w_present = bool(w_tf)

    # --- technical arming ---------------------------------------------------
    arm_result = {}
    arm_applicable = False
    try:
        if len(close) >= 60:
            arm_result = technical_arming(df, cfg)
            # applicable when stoch_k is present (non-null = arming ran successfully)
            arm_applicable = arm_result.get("stoch_k") is not None
    except Exception:  # noqa: BLE001
        pass

    # shock freshness: max bars since last non-null observation
    _SHOCK_FRESHNESS_BARS = 10

    # --- shock (macro if available, else price-based) -----------------------
    has_macro_shock = (
        "shock_z" in df.columns and df["shock_z"].notna().any()
    )
    has_price_shock = False
    shock_z_val: float | None = None
    shock_applicable = False

    if has_macro_shock:
        sv = df["shock_z"].dropna()
        if len(sv) > 0:
            # fix #5: freshness gate — only applicable if last non-null is recent
            last_idx = df.index.get_loc(sv.index[-1]) if len(sv) > 0 else -1
            frame_last_idx = len(df) - 1
            if (frame_last_idx - last_idx) <= _SHOCK_FRESHNESS_BARS:
                shock_z_val = _safe_float(sv.iloc[-1])
                shock_applicable = shock_z_val is not None
    elif len(close) >= 25:
        ps_cfg = cfg.get("index", {}).get("price_shock", {
            "return_window_d": 21, "z_lookback_d": 252, "shock_z": 1.75
        })
        try:
            ps_out = price_shock(close, ps_cfg)
            szp = ps_out["shock_z_price"].dropna()
            if len(szp) > 0:
                last_idx = df.index.get_loc(szp.index[-1]) if len(szp) > 0 else -1
                frame_last_idx = len(df) - 1
                if (frame_last_idx - last_idx) <= _SHOCK_FRESHNESS_BARS:
                    shock_z_val = _safe_float(szp.iloc[-1])
                    has_price_shock = True
                    shock_applicable = shock_z_val is not None
        except Exception:  # noqa: BLE001
            pass

    # select correct threshold depending on source
    eff_shock_thr_neg = -shock_z_macro if has_macro_shock else -shock_z_price
    eff_shock_thr_pos =  shock_z_macro if has_macro_shock else  shock_z_price

    # --- COT positioning (fix #5: freshness gate) ---------------------------
    has_pos = "pos_pctile" in df.columns and df["pos_pctile"].notna().any()
    pos_pctile_val: float | None = None
    if has_pos:
        pp = df["pos_pctile"].dropna()
        if len(pp) > 0:
            last_idx = df.index.get_loc(pp.index[-1])
            frame_last_idx = len(df) - 1
            if (frame_last_idx - last_idx) <= _SHOCK_FRESHNESS_BARS:
                pos_pctile_val = _safe_float(pp.iloc[-1])

    # --- bc_score (bottom-confidence from ladder) ---------------------------
    bc_val = _safe_float(ladder.get("bc_score"))
    # applicable only when bc_score is not None AND above the min-applicable floor
    # (bc_score < bc_score_min_applicable = noise-level DECLINE output; don't inflate denominator)
    bc_applicable = (bc_val is not None) and (bc_val >= bc_score_min_app)

    # --- member trend/momentum (last row) -----------------------------------
    last_ts_trend: str | None = None
    last_mom_state: str | None = None
    if "ts_trend" in df.columns:
        s = df["ts_trend"].dropna()
        last_ts_trend = str(s.iloc[-1]) if len(s) > 0 else None
    if "momentum_state" in df.columns:
        s = df["momentum_state"].dropna()
        last_mom_state = str(s.iloc[-1]) if len(s) > 0 else None

    both_trend_present = (last_ts_trend is not None) and (last_mom_state is not None)

    # --- 200-day SMA stretch (both sides) ----------------------------------
    has_200d = len(close) >= 200
    stretch_val: float | None = None
    sma200_val: float | None = None
    if has_200d:
        sma200_val = float(close.rolling(200).mean().dropna().iloc[-1])
        if sma200_val > 0:
            stretch_val = float(close.iloc[-1]) / sma200_val - 1.0

    # stretch_below: close/SMA200 - 1 <= -stretch_above_200d (deeply below 200d)
    # applicable when >= 200 bars present
    stretch_below_fired = (stretch_val is not None) and (stretch_val <= -stretch_thr)

    # --- cycle phase -------------------------------------------------------
    _BOTTOM_PHASES = {"trough", "recovery", "accumulation"}
    _TOP_PHASES    = {"peak", "downturn", "distribution"}
    cycle_applicable = cycle_phase is not None
    cycle_bottom_fired = cycle_applicable and (
        (cycle_phase or "").lower() in _BOTTOM_PHASES
    )
    cycle_top_fired = cycle_applicable and (
        (cycle_phase or "").lower() in _TOP_PHASES
    )

    # ======================================================================= #
    # BOTTOM side conditions — split into capitulation + turn groups
    # ======================================================================= #
    d_stoch = _safe_float(d_tf.get("stoch"))
    d_rsi14 = _safe_float(d_tf.get("rsi14"))
    td_stoch = _safe_float(td_tf.get("stoch"))
    w_stoch = _safe_float(w_tf.get("stoch"))
    w_rsi14 = _safe_float(w_tf.get("rsi14"))

    # shock (bottom)
    shock_bot_fired = (shock_z_val is not None) and (shock_z_val <= eff_shock_thr_neg)

    # oversold_ltf: D stoch <= stoch_oversold AND (3D stoch <= stoch_oversold_3d OR D rsi14 <= rsi_oversold)
    os_ltf_fired = False
    if d_present and d_stoch is not None:
        cond_3d = (td_stoch is not None and td_stoch <= stoch_os_3d)
        cond_rsi = (d_rsi14 is not None and d_rsi14 <= rsi_os)
        os_ltf_fired = (d_stoch <= stoch_os) and (cond_3d or cond_rsi)

    # oversold_htf: W stoch <= w_stoch_oversold OR W rsi14 <= w_rsi_oversold
    os_htf_fired = False
    if w_present:
        os_htf_fired = (
            (w_stoch is not None and w_stoch <= w_stoch_os)
            or (w_rsi14 is not None and w_rsi14 <= w_rsi_os)
        )

    # cot (bottom): pos_pctile <= cot_crowded_short_pctile
    cot_applicable = pos_pctile_val is not None if has_pos else False
    cot_bot_fired = (pos_pctile_val is not None) and (pos_pctile_val <= cot_cs_pct)

    # capitulation group: shock, oversold_ltf, oversold_htf, cot_short, stretch_below
    capitulation_conditions: list[tuple[str, bool, bool, float]] = [
        ("shock_bottom",  shock_bot_fired,     shock_applicable, w_shock),
        ("oversold_ltf",  os_ltf_fired,        d_present,        w_os_ltf),
        ("oversold_htf",  os_htf_fired,        w_present,        w_os_htf),
        ("cot_short",     cot_bot_fired,       cot_applicable,   w_cot),
        ("stretch_below", stretch_below_fired, has_200d,         w_stretch_below),
    ]

    # curl (bottom): D or 3D macd_curl_up OR D stoch_cross_up
    curl_bot_fired = False
    if d_present:
        curl_bot_fired = (
            bool(d_tf.get("macd_curl_up"))
            or bool(td_tf.get("macd_curl_up"))
            or bool(d_tf.get("stoch_cross_up"))
        )

    # armed
    armed_fired = bool(arm_result.get("armed", False))

    # bc_conf
    bc_conf_fired = (bc_val is not None) and (bc_val >= bc_score_min)

    # turn group: curl, armed, bc_conf, cycle_bottom
    turn_conditions: list[tuple[str, bool, bool, float]] = [
        ("curl",         curl_bot_fired,      d_present,        w_curl),
        ("armed",        armed_fired,         arm_applicable,   w_armed),
        ("bc_conf",      bc_conf_fired,       bc_applicable,    w_bc),
        ("cycle_bottom", cycle_bottom_fired,  cycle_applicable, w_cycle),
    ]

    # combined bottom (all conditions, for magnitude readout)
    bottom_conditions: list[tuple[str, bool, bool, float]] = (
        capitulation_conditions + turn_conditions
    )

    # ======================================================================= #
    # TOP side conditions — split into euphoria + rollover groups
    # ======================================================================= #
    # shock (top)
    shock_top_fired = (shock_z_val is not None) and (shock_z_val >= eff_shock_thr_pos)

    # overbought_ltf: D stoch >= stoch_overbought AND (3D stoch >= stoch_overbought_3d OR D rsi14 >= rsi_overbought)
    ob_ltf_fired = False
    if d_present and d_stoch is not None:
        cond_3d = (td_stoch is not None and td_stoch >= stoch_ob_3d)
        cond_rsi = (d_rsi14 is not None and d_rsi14 >= rsi_ob)
        ob_ltf_fired = (d_stoch >= stoch_ob) and (cond_3d or cond_rsi)

    # overbought_htf: W stoch >= w_stoch_overbought OR W rsi14 >= w_rsi_overbought
    ob_htf_fired = False
    if w_present:
        ob_htf_fired = (
            (w_stoch is not None and w_stoch >= w_stoch_ob)
            or (w_rsi14 is not None and w_rsi14 >= w_rsi_ob)
        )

    # cot (top): pos_pctile >= cot_crowded_long_pctile
    cot_top_fired = (pos_pctile_val is not None) and (pos_pctile_val >= cot_cl_pct)

    # stretch (top): close/SMA200 - 1 >= stretch_above_200d
    stretch_fired = (stretch_val is not None) and (stretch_val >= stretch_thr)

    # euphoria group: shock_top, overbought_ltf, overbought_htf, cot_long, stretch
    euphoria_conditions: list[tuple[str, bool, bool, float]] = [
        ("shock_top",      shock_top_fired, shock_applicable, w_shock),
        ("overbought_ltf", ob_ltf_fired,    d_present,        w_os_ltf),
        ("overbought_htf", ob_htf_fired,    w_present,        w_os_htf),
        ("cot_long",       cot_top_fired,   cot_applicable,   w_cot),
        ("stretch",        stretch_fired,   has_200d,         w_stretch),
    ]

    # curl_dn (top): D or 3D macd_curl_dn OR D stoch_cross_dn
    curl_top_fired = False
    if d_present:
        curl_top_fired = (
            bool(d_tf.get("macd_curl_dn"))
            or bool(td_tf.get("macd_curl_dn"))
            or bool(d_tf.get("stoch_cross_dn"))
        )

    # divergence (top, fix #4): ts_trend up + momentum_state bear + price still elevated
    # (D stoch >= 50 OR close >= SMA200) to avoid firing on a dip that's already below trend
    # Applicable when ts_trend + momentum_state + (stoch or SMA200) present
    has_stoch_for_div = d_stoch is not None
    has_sma200_for_div = sma200_val is not None
    div_applicable = both_trend_present and (has_stoch_for_div or has_sma200_for_div)
    div_elevated = (
        (d_stoch is not None and d_stoch >= 50)
        or (sma200_val is not None and stretch_val is not None and stretch_val >= 0.0)
    )
    divergence_fired = (
        div_applicable
        and last_ts_trend == "up"
        and last_mom_state == "bear"
        and div_elevated
    )

    # rollover group: curl_dn, divergence, cycle_top
    rollover_conditions: list[tuple[str, bool, bool, float]] = [
        ("curl_dn",    curl_top_fired,    d_present,       w_curl),
        ("divergence", divergence_fired,  div_applicable,  w_div),
        ("cycle_top",  cycle_top_fired,   cycle_applicable, w_cycle),
    ]

    # combined top (all conditions, for magnitude readout)
    top_conditions: list[tuple[str, bool, bool, float]] = (
        euphoria_conditions + rollover_conditions
    )

    # --- score --------------------------------------------------------------
    min_app = int(ccfg.get("min_applicable", 3))
    _group_min = int(ccfg.get("group_min_applicable", 2))

    bottom_score, bottom_fired, n_bot_app = score_side(bottom_conditions)
    top_score,    top_fired,    n_top_app = score_side(top_conditions)

    if n_bot_app < min_app:
        bottom_score = None
    if n_top_app < min_app:
        top_score = None

    # sub-scores (None if < group_min_applicable applicable within the group)
    capitulation_score = _score_group(capitulation_conditions, _group_min)
    turn_score         = _score_group(turn_conditions,         _group_min)
    euphoria_score     = _score_group(euphoria_conditions,     _group_min)
    rollover_score     = _score_group(rollover_conditions,     _group_min)

    state, null_reason = _state_from_scores_cfg(
        bottom_score, top_score, n_bot_app, n_top_app, ccfg,
        capitulation_score=capitulation_score,
        turn_score=turn_score,
        euphoria_score=euphoria_score,
        rollover_score=rollover_score,
    )

    return {
        "name": name,
        "label": name.replace("_", " ").title(),
        "class": klass,
        "state": state,
        "null_reason": null_reason,
        "bottom_score": bottom_score,
        "top_score": top_score,
        "capitulation_score": capitulation_score,
        "turn_score": turn_score,
        "euphoria_score": euphoria_score,
        "rollover_score": rollover_score,
        "bottom_fired": bottom_fired,
        "top_fired": top_fired,
        "n_bottom_applicable": n_bot_app,
        "n_top_applicable": n_top_app,
    }


# --------------------------------------------------------------------------- #
# index-level assessment
# --------------------------------------------------------------------------- #
def assess_index(
    index_close: pd.Series,
    breadth: dict,
    cfg: dict,
) -> dict:
    """Compute bottom + top confluence for the commodity sector composite.

    Parameters
    ----------
    index_close : equal-weight composite close series.
    breadth     : breadth snapshot dict from build_index (may be empty).
    cfg         : full commodities config section.

    Returns
    -------
    Same shape as assess_member result.  Never raises.
    """
    try:
        return _assess_index_inner(index_close, breadth, cfg)
    except Exception:  # noqa: BLE001
        log.warning("commodity_confluence.assess_index failed", exc_info=True)
        return {"name": "index", "label": "Commodity Index", "class": "index",
                "state": None, "null_reason": "compute error",
                "bottom_score": None, "top_score": None,
                "capitulation_score": None, "turn_score": None,
                "euphoria_score": None, "rollover_score": None,
                "bottom_fired": [], "top_fired": [],
                "n_bottom_applicable": 0, "n_top_applicable": 0}


def _assess_index_inner(
    index_close: pd.Series,
    breadth: dict,
    cfg: dict,
) -> dict:
    from engine.commodity_mtf import mtf_ladder
    from engine.commodity_index import price_shock

    ccfg = cfg.get("confluence", {})
    wt = ccfg.get("weights", {})

    stoch_os    = float(ccfg.get("stoch_oversold", 20))
    stoch_ob    = float(ccfg.get("stoch_overbought", 80))
    stoch_os_3d = float(ccfg.get("stoch_oversold_3d", 25))
    stoch_ob_3d = float(ccfg.get("stoch_overbought_3d", 75))
    rsi_os      = float(ccfg.get("rsi_oversold", 35))
    rsi_ob      = float(ccfg.get("rsi_overbought", 65))
    w_stoch_os  = float(ccfg.get("w_stoch_oversold", 25))
    w_stoch_ob  = float(ccfg.get("w_stoch_overbought", 75))
    w_rsi_os    = float(ccfg.get("w_rsi_oversold", 40))
    w_rsi_ob    = float(ccfg.get("w_rsi_overbought", 60))
    shock_z_pr  = float(ccfg.get("shock_z_price", 1.75))
    stretch_thr = float(ccfg.get("stretch_above_200d", 0.25))
    br_wash     = float(ccfg.get("breadth_washout_pctile", 0.10))
    br_euph     = float(ccfg.get("breadth_euphoria_pctile", 0.90))

    w_shock   = float(wt.get("shock", 2.0))
    w_os_ltf  = float(wt.get("oversold_ltf", 1.0))
    w_os_htf  = float(wt.get("oversold_htf", 1.0))
    w_curl    = float(wt.get("curl", 1.5))
    w_stretch = float(wt.get("stretch", 1.5))
    w_div     = float(wt.get("divergence", 2.0))
    w_breadth = float(wt.get("breadth", 1.5))

    close = index_close.dropna() if hasattr(index_close, "dropna") else pd.Series(dtype=float)
    min_app = int(ccfg.get("min_applicable", 3))

    # MTF
    a = mtf_ladder(close) if len(close) >= 60 else {}
    mtf = a.get("mtf", {}) or {}
    d_tf  = mtf.get("D") or {}
    td_tf = mtf.get("3D") or {}
    w_tf  = mtf.get("W") or {}

    d_present = bool(d_tf)
    w_present = bool(w_tf)

    # price shock (index uses price-based only)
    ps_cfg = cfg.get("index", {}).get("price_shock", {
        "return_window_d": 21, "z_lookback_d": 252, "shock_z": 1.75
    })
    shock_z_val: float | None = None
    shock_applicable = False
    if len(close) >= 25:
        try:
            ps_out = price_shock(close, ps_cfg)
            szp = ps_out["shock_z_price"].dropna()
            if len(szp) > 0:
                shock_z_val = _safe_float(szp.iloc[-1])
                shock_applicable = shock_z_val is not None
        except Exception:  # noqa: BLE001
            pass

    # breadth
    bp_val: float | None = None
    breadth_applicable = isinstance(breadth, dict) and "breadth_pctile" in breadth
    if breadth_applicable:
        bp_val = _safe_float(breadth.get("breadth_pctile"))
        breadth_applicable = bp_val is not None

    # 200-day stretch
    has_200d = len(close) >= 200
    stretch_val: float | None = None
    if has_200d:
        sma200 = float(close.rolling(200).mean().dropna().iloc[-1])
        if sma200 > 0:
            stretch_val = float(close.iloc[-1]) / sma200 - 1.0

    d_stoch  = _safe_float(d_tf.get("stoch"))
    d_rsi14  = _safe_float(d_tf.get("rsi14"))
    td_stoch = _safe_float(td_tf.get("stoch"))
    w_stoch  = _safe_float(w_tf.get("stoch"))
    w_rsi14  = _safe_float(w_tf.get("rsi14"))

    _group_min = int(ccfg.get("group_min_applicable", 2))

    # --- BOTTOM capitulation group (index: shock, oversold_ltf, oversold_htf, stretch_below, breadth_bottom) ---
    shock_bot = (shock_z_val is not None) and (shock_z_val <= -shock_z_pr)

    os_ltf = False
    if d_present and d_stoch is not None:
        os_ltf = (d_stoch <= stoch_os) and (
            (td_stoch is not None and td_stoch <= stoch_os_3d)
            or (d_rsi14 is not None and d_rsi14 <= rsi_os)
        )

    os_htf = False
    if w_present:
        os_htf = (
            (w_stoch is not None and w_stoch <= w_stoch_os)
            or (w_rsi14 is not None and w_rsi14 <= w_rsi_os)
        )

    stretch_bot_fired = (stretch_val is not None) and (stretch_val <= -stretch_thr)
    breadth_bot = breadth_applicable and (bp_val is not None) and (bp_val <= br_wash)

    cap_idx_conditions: list[tuple[str, bool, bool, float]] = [
        ("shock_bottom",   shock_bot,        shock_applicable,   w_shock),
        ("oversold_ltf",   os_ltf,           d_present,          w_os_ltf),
        ("oversold_htf",   os_htf,           w_present,          w_os_htf),
        ("stretch_below",  stretch_bot_fired, has_200d,           w_stretch),
        ("breadth_bottom", breadth_bot,      breadth_applicable, w_breadth),
    ]

    # --- BOTTOM turn group (index: curl only — no COT, arming, bc_score) ---
    curl_bot = False
    if d_present:
        curl_bot = (
            bool(d_tf.get("macd_curl_up"))
            or bool(td_tf.get("macd_curl_up"))
            or bool(d_tf.get("stoch_cross_up"))
        )

    turn_idx_conditions: list[tuple[str, bool, bool, float]] = [
        ("curl", curl_bot, d_present, w_curl),
    ]

    bottom_conditions: list[tuple[str, bool, bool, float]] = (
        cap_idx_conditions + turn_idx_conditions
    )

    # --- TOP euphoria group (index: shock_top, overbought_ltf, overbought_htf, stretch, breadth_top) ---
    shock_top = (shock_z_val is not None) and (shock_z_val >= shock_z_pr)

    ob_ltf = False
    if d_present and d_stoch is not None:
        ob_ltf = (d_stoch >= stoch_ob) and (
            (td_stoch is not None and td_stoch >= stoch_ob_3d)
            or (d_rsi14 is not None and d_rsi14 >= rsi_ob)
        )

    ob_htf = False
    if w_present:
        ob_htf = (
            (w_stoch is not None and w_stoch >= w_stoch_ob)
            or (w_rsi14 is not None and w_rsi14 >= w_rsi_ob)
        )

    stretch_top_fired = (stretch_val is not None) and (stretch_val >= stretch_thr)
    breadth_top = breadth_applicable and (bp_val is not None) and (bp_val >= br_euph)

    euph_idx_conditions: list[tuple[str, bool, bool, float]] = [
        ("shock_top",      shock_top,         shock_applicable,   w_shock),
        ("overbought_ltf", ob_ltf,            d_present,          w_os_ltf),
        ("overbought_htf", ob_htf,            w_present,          w_os_htf),
        ("stretch",        stretch_top_fired,  has_200d,           w_stretch),
        ("breadth_top",    breadth_top,       breadth_applicable, w_breadth),
    ]

    # --- TOP rollover group (index: curl_dn only — divergence not available at index level) ---
    curl_top = False
    if d_present:
        curl_top = (
            bool(d_tf.get("macd_curl_dn"))
            or bool(td_tf.get("macd_curl_dn"))
            or bool(d_tf.get("stoch_cross_dn"))
        )

    roll_idx_conditions: list[tuple[str, bool, bool, float]] = [
        ("curl_dn", curl_top, d_present, w_curl),
    ]

    # divergence: for the index, ts_trend vs momentum_state is not directly
    # available — skip (not applicable), keeping this slot as non-penalising.
    top_conditions: list[tuple[str, bool, bool, float]] = (
        euph_idx_conditions + roll_idx_conditions
    )

    bottom_score, bottom_fired, n_bot = score_side(bottom_conditions)
    top_score,    top_fired,    n_top = score_side(top_conditions)

    if n_bot < min_app:
        bottom_score = None
    if n_top < min_app:
        top_score = None

    capitulation_score = _score_group(cap_idx_conditions,  _group_min)
    turn_score         = _score_group(turn_idx_conditions,  _group_min)
    euphoria_score     = _score_group(euph_idx_conditions,  _group_min)
    rollover_score     = _score_group(roll_idx_conditions,  _group_min)

    state, null_reason = _state_from_scores_cfg(
        bottom_score, top_score, n_bot, n_top, ccfg,
        capitulation_score=capitulation_score,
        turn_score=turn_score,
        euphoria_score=euphoria_score,
        rollover_score=rollover_score,
    )

    return {
        "name": "index",
        "label": "Commodity Index",
        "class": "index",
        "state": state,
        "null_reason": null_reason,
        "bottom_score": bottom_score,
        "top_score": top_score,
        "capitulation_score": capitulation_score,
        "turn_score": turn_score,
        "euphoria_score": euphoria_score,
        "rollover_score": rollover_score,
        "bottom_fired": bottom_fired,
        "top_fired": top_fired,
        "n_bottom_applicable": n_bot,
        "n_top_applicable": n_top,
    }


# --------------------------------------------------------------------------- #
# top-level build
# --------------------------------------------------------------------------- #
def build_confluence(
    member_results: dict[str, pd.DataFrame],
    cfg: dict,
    index_close: pd.Series | None = None,
    breadth: dict | None = None,
) -> dict:
    """Build the full confluence snapshot for all members + the sector index.

    Parameters
    ----------
    member_results : {name: compute_asset_frame} — keyed by member name.
    cfg            : full commodities config section.
    index_close    : optional composite close (idx_ew from composite_series).
    breadth        : optional breadth snapshot dict from build_index.

    Returns
    -------
    JSON-safe dict:
        {"asof": str, "members": [...assess_member dicts...], "index": {...}}
    Returns {} on failure (never raises).
    """
    try:
        return _build_confluence_inner(member_results, cfg, index_close, breadth)
    except Exception:  # noqa: BLE001 — must never break the build
        log.warning("commodity_confluence.build_confluence failed", exc_info=True)
        return {}


def _build_confluence_inner(
    member_results: dict[str, pd.DataFrame],
    cfg: dict,
    index_close: pd.Series | None,
    breadth: dict | None,
) -> dict:
    if not member_results:
        return {}

    # read cycle_positions.json once if present
    cycle_pos: dict[str, dict] = {}
    try:
        from lib import config as _cfg_mod
        cp_path = _cfg_mod.data_dir() / "commodity" / "cycle_positions.json"
        if cp_path.exists():
            cycle_pos = json.loads(cp_path.read_text())
    except Exception:  # noqa: BLE001 — optional P3 bridge
        pass

    # member class lookup
    try:
        from lib import config as _cfg_mod
        _member_classes = {
            n: spec[2]
            for n, spec in _cfg_mod.load()["commodities"].get("complex_members", {}).items()
        }
    except Exception:  # noqa: BLE001
        _member_classes = {}

    # asof: last date across all members
    asof_ts = max(
        (df.index.max() for df in member_results.values()
         if isinstance(df, pd.DataFrame) and len(df) > 0),
        default=pd.Timestamp.now(),
    )
    asof = str(asof_ts.date()) if hasattr(asof_ts, "date") else str(asof_ts)

    members_out: list[dict] = []
    import time as _time
    for name, df in member_results.items():
        if not isinstance(df, pd.DataFrame):
            continue
        klass = _member_classes.get(name, "")
        cp_entry = cycle_pos.get(name, {})
        phase = cp_entry.get("phase") if isinstance(cp_entry, dict) else None
        _t0 = _time.time()
        result = assess_member(name, klass, df, cfg, cycle_phase=phase)
        _elapsed = _time.time() - _t0
        if _elapsed > 1.0:
            log.info("[timing] confluence.assess_member %s in %.2fs", name, _elapsed)
        members_out.append(result)

    # index
    index_result: dict = {}
    if index_close is not None and len(index_close.dropna()) >= 30:
        index_result = assess_index(index_close, breadth or {}, cfg)

    return {
        "asof": asof,
        "members": members_out,
        "index": index_result,
    }
