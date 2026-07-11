"""W1-A: W-tier setup layer — weekly/bi-weekly setup state + stage assignment.

Computes a multi-timeframe setup snapshot per the China Alpha Masterplan (F2/W1):
  - 2W-FRI resample via cycles._tf_state (stoch, stoch_cross_up, macd_pos,
    macd_approaching_up, macd_bars_to_cross, macd_cross_up, rsi14)
  - 1W-FRI StochRSI k/d cross: last bullish k-over-d cross, bars-since, d-value-at-cross
    (washout zone = d_at_cross < 25)
  - 2y (504-bar) range width + spot position; base_age heuristic
  - setup_live bool + reasons list

Stage assignment rules (ENTRY / RIPENING / RAN_LATE) mirror the masterplan spec exactly.

W8-R1: assign_ripening_zone() — three-zone lifecycle classifier (FALLING / READY / BASING).
  Hard precedence cascade: FALLING veto first (no cross can override), then READY evidence,
  then BASING. Zone thresholds v1 frozen descriptively — amendment-logged, recalibrated at
  china_alpha W6 (F3 discipline). Display-tier only; may_rank=false.

Nearest sibling: engine/hold.py (same _tf_bars / _stoch_rsi_kd / _rsi_macd imports;
same dict | None returns; same MIN_HISTORY guard).

Public API:
  w_setup(close)           -> dict | None   (W-tier state per name)
  assign_stage(...)        -> dict           (stage + sublabel + detail)
  assign_ripening_zone(...) -> dict          (zone + evidence: W8-R1)
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from engine.cycles import _tf_state  # noqa: E402 (already tested primitive)
from engine.confluence_tiers import (  # noqa: E402
    _stoch_rsi_kd,
    _rsi_macd,
    _tf_bars,
    _xup,
)

log = logging.getLogger(__name__)

# ── constants ─────────────────────────────────────────────────────────────────
MIN_HISTORY = 120          # skip series shorter than this daily bars
RANGE_BARS = 504           # 2-year (~504 trading days) range width for base calc
W1_FRESH_BARS = 3          # 1W cross is "fresh" within this many weekly bars
W1_WASHOUT_D = 25.0        # d < this at cross = deep washout zone
W2_STOCH_WASHOUT = 35.0    # 2W stoch <= this = washout state
W2_MACD_IMMINENCE = 10.0   # bars_to_cross <= this (in 2W bars) = imminent
FRESH_CROSS_SESSIONS = 5   # gate cross within this many sessions = the entry window is OPEN

# Stage labels
STAGE_ENTRY = "ENTRY"
STAGE_RIPENING = "RIPENING"
STAGE_RAN_LATE = "RAN_LATE"
STAGE_NONE = None


# ── helpers ───────────────────────────────────────────────────────────────────

def _w1_cross_info(daily: pd.Series) -> dict:
    """Last bullish 1W StochRSI k-over-d cross: bars_since, d_at_cross, date.

    Returns dict with keys:
      cross_date, bars_since, d_at_cross, from_washout
    All None when no 1W cross found.  Never raises.
    """
    try:
        wk = daily.resample("W-FRI").last().dropna()
        if len(wk) < 40:
            return {"cross_date": None, "bars_since": None,
                    "d_at_cross": None, "from_washout": False}
        k, d = _stoch_rsi_kd(wk)
        xup = _xup(k, d).fillna(False)
        cross_dates = wk.index[xup.values.astype(bool)]
        if len(cross_dates) == 0:
            return {"cross_date": None, "bars_since": None,
                    "d_at_cross": None, "from_washout": False}
        cd = cross_dates[-1]
        d_at = float(d.reindex([cd]).iloc[0]) if cd in d.index else None
        bars_since = int((wk.index > cd).sum())
        return {
            "cross_date": str(cd.date()),
            "bars_since": bars_since,
            "d_at_cross": round(d_at, 1) if d_at is not None else None,
            "from_washout": bool(d_at is not None and d_at < W1_WASHOUT_D),
        }
    except Exception:
        return {"cross_date": None, "bars_since": None,
                "d_at_cross": None, "from_washout": False}


def _base_range(daily: pd.Series) -> dict:
    """2-year range width and spot position inside the range.

    Returns dict with keys:
      range_lo, range_hi, range_width_pct, spot_pct_in_range, bars_used
    """
    try:
        s = daily.dropna()
        if len(s) < 60:
            return {"range_lo": None, "range_hi": None,
                    "range_width_pct": None, "spot_pct_in_range": None, "bars_used": 0}
        window = s.iloc[-RANGE_BARS:] if len(s) >= RANGE_BARS else s
        lo = float(window.min())
        hi = float(window.max())
        spot = float(s.iloc[-1])
        rng_pct = round((hi - lo) / lo * 100, 1) if lo > 0 else None
        pct_in = round((spot - lo) / (hi - lo) * 100, 1) if (hi - lo) > 0 else None
        return {
            "range_lo": round(lo, 2), "range_hi": round(hi, 2),
            "range_width_pct": rng_pct,
            "spot_pct_in_range": pct_in,
            "bars_used": len(window),
        }
    except Exception:
        return {"range_lo": None, "range_hi": None,
                "range_width_pct": None, "spot_pct_in_range": None, "bars_used": 0}


# ── public API ─────────────────────────────────────────────────────────────────

def w_setup(close: pd.Series) -> dict | None:
    """Compute W-tier setup state for a single name.

    Parameters
    ----------
    close : pd.Series
        Daily close prices with DatetimeIndex.

    Returns
    -------
    dict | None
        None when series is too short (<MIN_HISTORY bars) or unusable.
        Otherwise a dict with:
          w2      : _tf_state on 2W-FRI resample (stoch, stoch_cross_up, macd_pos,
                    macd_approaching_up, macd_bars_to_cross, macd_cross_up, rsi14, ...)
          w1_cross: last bullish 1W StochRSI k/d cross info (cross_date, bars_since,
                    d_at_cross, from_washout)
          base    : 2y range width + spot position
          setup_live   : bool — any W-tier setup condition is active
          setup_reasons: list of strings describing active conditions
    """
    try:
        c = close.dropna()
        if not isinstance(c.index, pd.DatetimeIndex):
            c = c.copy()
            c.index = pd.to_datetime(c.index)
        if len(c) < MIN_HISTORY:
            return None

        # ── 2W-FRI state ─────────────────────────────────────────────────────
        w2_series = c.resample("2W-FRI").last().dropna()
        if len(w2_series) < 40:
            return None
        w2 = _tf_state(w2_series)
        if not w2:
            return None

        # ── 1W StochRSI k/d cross ─────────────────────────────────────────────
        w1_cross = _w1_cross_info(c)

        # ── 2y base range ─────────────────────────────────────────────────────
        base = _base_range(c)

        # ── setup_live evaluation ─────────────────────────────────────────────
        # Condition A: 2W stoch washout or stoch_cross_up
        cond_a = bool(
            (w2.get("stoch") is not None and w2["stoch"] <= W2_STOCH_WASHOUT)
            or w2.get("stoch_cross_up")
        )

        # Condition B: 1W fresh bull cross from deep washout zone
        cond_b = bool(
            w1_cross["cross_date"] is not None
            and w1_cross.get("bars_since") is not None
            and w1_cross["bars_since"] <= W1_FRESH_BARS
            and w1_cross.get("from_washout")
        )

        # Condition C: 2W MACD approaching cross within threshold or already crossed
        btc = w2.get("macd_bars_to_cross")
        cond_c = bool(
            (w2.get("macd_approaching_up") and btc is not None and btc <= W2_MACD_IMMINENCE)
            or w2.get("macd_cross_up")
        )

        setup_live = cond_a or cond_b or cond_c

        reasons: list[str] = []
        if cond_a:
            if w2.get("stoch_cross_up"):
                reasons.append("2W stoch cross-up (washout exit)")
            else:
                reasons.append(f"2W stoch washout (stoch={w2.get('stoch')})")
        if cond_b:
            d_at = w1_cross.get("d_at_cross")
            bars = w1_cross.get("bars_since")
            reasons.append(
                f"1W cross from washout (d={d_at}, {bars} bar{'s' if bars != 1 else ''} ago)"
            )
        if cond_c:
            if w2.get("macd_cross_up"):
                reasons.append("2W MACD crossed up")
            else:
                reasons.append(
                    f"2W MACD cross ~{round(btc, 1)} 2W-bars out"
                    if btc is not None else "2W MACD approaching cross"
                )

        return {
            "w2": w2,
            "w1_cross": w1_cross,
            "base": base,
            "setup_live": setup_live,
            "setup_reasons": reasons,
        }
    except Exception as exc:
        log.debug("w_setup failed: %s", exc)
        return None


def assign_stage(
    *,
    gate_eligible: bool,
    entry_status: str | None,
    overextended: bool,
    last_cross_info: dict | None,
    hold_state: dict | None,
    wsetup: dict | None,
) -> dict:
    """Assign the lifecycle stage for one name from existing gate / entry / W-setup signals.

    Gate-eligible rows (rules 1-2). The T1-T4 confluence cross IS this board's entry
    definition, so a FRESH cross (<= FRESH_CROSS_SESSIONS) means the window is OPEN —
    the daily-cycle gauge may not overrule it. The daily ladder flips any fresh-buy
    reading to TOP WATCH / "extended" on daily RSI>70, and the first breakout thrust
    off a base (an A-share limit-up especially) trivially trips that — which had the
    board demoting exactly the freshest base breakouts to RAN_LATE while stale,
    already-run names sat on ENTRY. Precedence, adjudicated:

    Rule 2a — overextended (the A-share price-extension read, extension_read) -> RAN_LATE.
              F6 ruling preserved: TRUE extension beats everything, incl. a fresh cross.
              muted_entry=True when the entry gauge was nominally open (buy_now/partial).
    Rule 2b — entry_status in {exit, avoid, blocked} (cycle failed / rolling over)
              -> RAN_LATE with a stand-aside sublabel, never "entry passed".
    Rule 1a — fresh gate cross (last_cross_info.sessions_since <= FRESH_CROSS_SESSIONS)
              -> ENTRY. detail carries cross age so the card can show freshness.
    Rule 1  — entry_status in {buy_now, partial} -> ENTRY (pullback/re-entry window
              inside a live signal).
    Rule 2c — remaining wait states (hold / extended / topping / watch / buy_soon /
              await_confluence / wait_pullback) -> RAN_LATE
              sublabel: "signal live — entry passed; wait for pullback" (or the cross
              age when known). entry_status None with no fresh cross stays shelf-less.

    Non-eligible rows (rules 3-5), unchanged:

    Rule 3 — NOT gate-eligible, last 2D/3D cross within 15 ticks -> RAN_LATE
              sublabel: "signal fired <date> (N sessions ago), +X% since"
              if hold_state says basing-intact, append re-entry chip
    Rule 4 — NOT gate-eligible, no recent cross, but setup_live -> RIPENING
              sublabel: the specific w_setup reason chips
    Rule 5 — else -> no shelf (stage=None)

    Parameters
    ----------
    gate_eligible : bool
        From signal_gate.gate()["eligible"].
    entry_status : str | None
        From entry_signal.assess()["status"] — e.g. "buy_now", "partial", "hold", etc.
    overextended : bool
        True when the name has ALREADY RUN in price terms (china_signals.extension_read
        .extended — the validated A-share anti-chase read). NOT the daily-RSI gauge.
    last_cross_info : dict | None
        Keys: cross_date (str), sessions_since (int), pct_since (float).
        Rule 1a fires when sessions_since <= FRESH_CROSS_SESSIONS (eligible rows);
        rule 3 fires when sessions_since <= 15 (non-eligible rows).
    hold_state : dict | None
        From engine.hold.hold_state(). Keys: state, anchor.
        Rule 3 may append a basing-intact chip.
    wsetup : dict | None
        From w_setup().  setup_live + setup_reasons drive rule 4.

    Returns
    -------
    dict with keys: stage, sublabel, sublabel_zh, detail
    """
    if gate_eligible:
        _ci = last_cross_info or {}
        _sess = _ci.get("sessions_since")
        _cross_fresh = _sess is not None and _sess <= FRESH_CROSS_SESSIONS

        # ── Rule 2a: TRUE price extension beats everything (F6) ─────────────
        if overextended:
            _muted = entry_status in ("buy_now", "partial")
            return {
                "stage": STAGE_RAN_LATE,
                "sublabel": ("entry gauge open — but extended; wait for pullback"
                             if _muted
                             else "extended — has already run; wait for pullback"),
                "sublabel_zh": ("入场量表打开 — 但已过度延伸；等待回调"
                                if _muted else "已大幅上涨 — 等待回调"),
                "detail": {
                    "entry_status": entry_status,
                    "overextended": True,
                    "muted_entry": _muted,
                },
            }

        # ── Rule 2b: failed / rolling-over cycle — stand aside, not "entry passed"
        if entry_status in ("exit", "avoid", "blocked"):
            return {
                "stage": STAGE_RAN_LATE,
                "sublabel": "cycle failed / rolling over — stand aside",
                "sublabel_zh": "周期失败/掉头向下 — 观望",
                "detail": {
                    "entry_status": entry_status,
                    "overextended": False,
                    "muted_entry": False,
                },
            }

        # ── Rule 1a: fresh gate cross = the entry window is OPEN ────────────
        # The cross is the board's own entry definition; a not-price-extended name
        # whose cross fired within FRESH_CROSS_SESSIONS is ENTRY regardless of the
        # daily-cycle gauge (whose RSI>70 gate mislabels the first base-breakout
        # thrust as "extended").
        if _cross_fresh:
            return {
                "stage": STAGE_ENTRY,
                "sublabel": None,
                "detail": {
                    "entry_status": entry_status,
                    "cross_date": _ci.get("cross_date"),
                    "cross_sessions_since": _sess,
                    "pct_since": _ci.get("pct_since"),
                    "fresh_cross": True,
                },
            }

        # ── Rule 1: entry gauge open (pullback / re-entry inside a live signal)
        if entry_status in ("buy_now", "partial"):
            return {
                "stage": STAGE_ENTRY,
                "sublabel": None,
                "detail": {"entry_status": entry_status},
            }

        # ── Rule 2c: remaining wait states — entry window not open ──────────
        if entry_status is not None:
            if _sess is not None:
                _pct = _ci.get("pct_since")
                _pct_str = f", +{round(_pct, 1)}%" if _pct is not None else ""
                _sublabel = (f"signal fired {_ci.get('cross_date', 'unknown')} "
                             f"({_sess} sessions ago{_pct_str}) — entry passed; wait for pullback")
                _sublabel_zh = (f"信号于{_ci.get('cross_date', '')}触发（{_sess}个交易日前）；"
                                "入场时机已过，等待回调")
            else:
                _sublabel = "signal live — entry passed; wait for pullback"
                _sublabel_zh = "信号有效但入场时机已过；等待回调"
            return {
                "stage": STAGE_RAN_LATE,
                "sublabel": _sublabel,
                "sublabel_zh": _sublabel_zh,
                "detail": {
                    "entry_status": entry_status,
                    "overextended": False,
                    "muted_entry": False,
                    "cross_sessions_since": _sess,
                },
            }
        # entry_status None + no fresh cross: shelf-less (pre-existing behavior)
        return {"stage": STAGE_NONE, "sublabel": None, "detail": {}}

    # ── Rule 3: NOT gate-eligible, recent cross (within 15 sessions) ─────────
    if not gate_eligible and last_cross_info:
        sess = last_cross_info.get("sessions_since")
        if sess is not None and sess <= 15:
            cd = last_cross_info.get("cross_date", "unknown")
            pct = last_cross_info.get("pct_since")
            pct_str = f", +{round(pct, 1)}%" if pct is not None else ""
            sublabel = f"signal fired {cd} ({sess} sessions ago){pct_str}"
            basing_chip = None
            launched_chip = None
            if hold_state:
                _hs_state = hold_state.get("state")
                _anchor = hold_state.get("anchor", "")
                _inv = hold_state.get("invalidation")
                _maxup = hold_state.get("maxup_pct")
                if _hs_state == "intact":
                    _inv_str = (f", invalidation {_inv:.2f}" if _inv is not None else "")
                    basing_chip = f"basing since {_anchor}{_inv_str}"
                elif _hs_state == "launched":
                    _pct_str = (f", +{_maxup:.1f}%" if _maxup is not None else "")
                    launched_chip = f"launched from {_anchor}{_pct_str}"
            return {
                "stage": STAGE_RAN_LATE,
                "sublabel": sublabel,
                "detail": {
                    "cross_date": cd, "sessions_since": sess,
                    "pct_since": pct,
                    "basing_chip": basing_chip,
                    "launched_chip": launched_chip,
                },
            }

    # ── Rule 4: NOT gate-eligible, no recent cross, but setup_live ───────────
    if not gate_eligible and wsetup and wsetup.get("setup_live"):
        reasons = wsetup.get("setup_reasons") or []
        btc = wsetup.get("w2", {}).get("macd_bars_to_cross")
        sublabel = "; ".join(reasons) if reasons else "W-tier setup forming"
        return {
            "stage": STAGE_RIPENING,
            "sublabel": sublabel,
            "detail": {
                "reasons": reasons,
                "macd_bars_to_cross": btc,
                "w2_stoch": wsetup.get("w2", {}).get("stoch"),
            },
        }

    # ── Rule 5: no shelf ─────────────────────────────────────────────────────
    return {"stage": STAGE_NONE, "sublabel": None, "detail": {}}


# ── W8-R1: Ripening three-zone lifecycle classifier ───────────────────────────
#
# Zone thresholds (v1 frozen descriptively — amendment-logged, recalibrated at
# china_alpha W6). These are display-tier grouping constants only; they do not
# affect board_ordering, alert_triage, or any authority surface (may_rank=false).
#
# Precedence cascade (HARD — no override):
#   1. FALLING  — directional veto; no fresh-cross evidence overrides this
#   2. READY    — directional evidence live AND tape not collapsing
#   3. BASING   — everything else with setup_live (washout present, drifting)
#
# Operator fixture tests (R7 census data, pinned here for regression):
#   000792: ret_5d=-13.6%, hist=-0.253 (falling) → FALLING
#   002709: ret_5d=-24.4%, hist=-1.061 (falling), w1_cross_bars_since=2 → FALLING
#           (precedence: FALLING veto beats fresh cross evidence)
#   601360: ret_5d=+1.6%,  hist=+0.041 (rising),  w1_cross_bars_since=3, d=3.6 → READY
#   601933: ret_5d=-2.9%,  hist=+0.022 (positive), w1_cross_bars_since=1 → READY

# FALLING zone thresholds
_FALLING_RET5D_THRESH = -0.08          # 5d return <= -8% → FALLING (absolute)
# READY zone: fresh 1W cross window
_READY_W1_CROSS_MAX_BARS = 3           # 1W cross within this many weekly bars = fresh
# READY zone: 2W MACD imminence window (bars to cross)
_READY_MACD_BARS_MAX = 10              # 2W MACD bars_to_cross <= this = READY (when hist >= 0)

ZONE_FALLING = "FALLING"
ZONE_READY   = "READY"
ZONE_BASING  = "BASING"


def assign_ripening_zone(
    *,
    ret_5d: float | None,
    macd_hist_d: float | None,
    macd_hist_prev_d: float | None,
    w1_cross_bars_since: int | None,
    w1_from_washout: bool,
    macd_bars_to_cross_2w: float | None,
    stoch_2w: float | None,
    stoch_2w_prev: float | None = None,
) -> dict:
    """Assign a FALLING / READY / BASING zone for a ripening candidate.

    PURE function — no I/O, no side-effects, deterministic given inputs.
    Display-tier only (W8-R1). Zone thresholds v1 frozen descriptively;
    recalibrated at china_alpha W6.

    Parameters
    ----------
    ret_5d : float | None
        5-session price return as a decimal (e.g. -0.136 for -13.6%).
    macd_hist_d : float | None
        Daily MACD histogram last bar value.
    macd_hist_prev_d : float | None
        Daily MACD histogram one bar prior (for slope direction).
    w1_cross_bars_since : int | None
        Bars since the last 1W StochRSI k/d bullish cross (from w_setup).
        None means no cross was found.
    w1_from_washout : bool
        True when the 1W cross originated from the deep washout zone (d < 25).
    macd_bars_to_cross_2w : float | None
        2W MACD estimated bars to cross (None = no approach detected / already crossed).
    stoch_2w : float | None
        2W StochRSI last value (0-100 scale).
    stoch_2w_prev : float | None
        2W StochRSI previous value (for reclaim arrow; optional, not used in zone logic).

    Returns
    -------
    dict with keys:
        zone     : str — FALLING | READY | BASING
        evidence : list[str] — machine evidence receipts (EN quant shorthand;
                   ledger/hover tier — never rendered at rest, doctrine Law 2)
        evidence_display : list[dict] — plain-word bilingual twins for the glance
                   tier, parallel to `evidence`; each entry is
                   {"en": str, "zh": str, "receipt": str} with receipt == the
                   matching `evidence` string.
    """
    evidence: list[str] = []
    display: list[dict] = []

    def _emit(receipt: str, en: str, zh: str) -> None:
        evidence.append(receipt)
        display.append({"en": en, "zh": zh, "receipt": receipt})

    # ── Step 1: FALLING veto (evaluated FIRST — no cross evidence can override) ──────
    # Condition F1: catastrophic 5d drawdown
    _ret_falling = ret_5d is not None and ret_5d <= _FALLING_RET5D_THRESH
    # Condition F2: daily MACD histogram negative AND declining (knife shape)
    _macd_neg_falling = (
        macd_hist_d is not None
        and macd_hist_d < 0
        and macd_hist_prev_d is not None
        and macd_hist_d < macd_hist_prev_d
    )
    if _ret_falling or _macd_neg_falling:
        if _ret_falling:
            _emit(
                f"5d return {ret_5d*100:.1f}% (below -8% veto)",
                f"down {abs(ret_5d)*100:.1f}% in 5 days — falling too fast",
                f"5日下跌{abs(ret_5d)*100:.1f}% — 跌势过急",
            )
        if _macd_neg_falling:
            _emit(
                f"D-MACD hist {macd_hist_d:+.3f} (negative & falling from "
                f"{macd_hist_prev_d:+.3f})",
                "daily momentum negative and worsening",
                "日线动能为负且继续走弱",
            )
        return {"zone": ZONE_FALLING, "evidence": evidence, "evidence_display": display}

    # ── Step 2: READY — directional evidence live, tape not collapsing ────────────────
    # Condition R1: fresh 1W washout cross AND daily MACD hist >= 0
    _fresh_1w_cross = (
        w1_cross_bars_since is not None
        and w1_cross_bars_since <= _READY_W1_CROSS_MAX_BARS
        and w1_from_washout
        and macd_hist_d is not None
        and macd_hist_d >= 0
    )
    # Condition R2: daily MACD histogram turned positive (hist > 0 AND rising)
    _macd_turned_pos = (
        macd_hist_d is not None
        and macd_hist_d > 0
        and macd_hist_prev_d is not None
        and macd_hist_d > macd_hist_prev_d
    )
    # Condition R3: 2W MACD imminent (bars_to_cross <= threshold) AND daily hist >= 0
    _macd_imminent = (
        macd_bars_to_cross_2w is not None
        and macd_bars_to_cross_2w <= _READY_MACD_BARS_MAX
        and macd_hist_d is not None
        and macd_hist_d >= 0
    )

    if _fresh_1w_cross or _macd_turned_pos or _macd_imminent:
        if _fresh_1w_cross:
            if w1_cross_bars_since == 0:
                _when_en, _when_zh = "this week", "本周"
            elif w1_cross_bars_since == 1:
                _when_en, _when_zh = "1 wk ago", "1周前"
            else:
                _when_en, _when_zh = f"{w1_cross_bars_since} wks ago", f"{w1_cross_bars_since}周前"
            _emit(
                f"1W cross {w1_cross_bars_since} bar{'s' if w1_cross_bars_since != 1 else ''} ago"
                f" (d-washout), D-MACD {'+' if macd_hist_d and macd_hist_d >= 0 else ''}"
                f"{macd_hist_d:.3f}",
                f"weekly gauge turned up from washout {_when_en}",
                f"周线{_when_zh}自超卖区转强",
            )
        if _macd_turned_pos and not _fresh_1w_cross:
            _emit(
                f"D-MACD hist turned positive: {macd_hist_d:+.3f}"
                + (f" (from {macd_hist_prev_d:+.3f})" if macd_hist_prev_d is not None else ""),
                "daily momentum just turned positive",
                "日线动能刚刚转正",
            )
        if _macd_imminent:
            _emit(
                f"2W MACD ~{macd_bars_to_cross_2w:.1f} bars to cross",
                f"time to turn: ~{macd_bars_to_cross_2w:.1f} wk at this pace",
                f"距转向约{macd_bars_to_cross_2w:.1f}周（按当前速度）",
            )
        return {"zone": ZONE_READY, "evidence": evidence, "evidence_display": display}

    # ── Step 3: BASING — washout present but no directional trigger yet ───────────────
    if stoch_2w is not None:
        if stoch_2w <= 20:
            _st_en, _st_zh = "deeply oversold", "深度超卖"
        elif stoch_2w <= 35:
            _st_en, _st_zh = "in the washout zone", "仍处超卖区"
        else:
            _st_en, _st_zh = "oversold gauge off the lows", "超卖量表已脱离低位"
        _emit(f"2W stoch {stoch_2w:.1f} (washout)", _st_en, _st_zh)
    if macd_hist_d is not None:
        _rising = macd_hist_prev_d is not None and macd_hist_d > macd_hist_prev_d
        _slope_tag = "rising" if _rising else "flat/falling"
        _emit(
            f"D-MACD {macd_hist_d:+.3f} ({_slope_tag})",
            "daily momentum improving" if _rising else "daily momentum flat or fading",
            "日线动能改善" if _rising else "日线动能持平或走弱",
        )
    if w1_cross_bars_since is not None:
        if w1_cross_bars_since <= _READY_W1_CROSS_MAX_BARS:
            _sc_en, _sc_zh = "weekly gauge turned up — not confirmed yet", "周线已转向 — 尚未确认"
        else:
            _sc_en = f"weekly turn {w1_cross_bars_since} wks ago — gone stale"
            _sc_zh = f"周线转向已{w1_cross_bars_since}周 — 已失效"
        _emit(f"1W cross {w1_cross_bars_since} bars ago (stale)", _sc_en, _sc_zh)
    return {"zone": ZONE_BASING, "evidence": evidence, "evidence_display": display}
