"""W1-A: W-tier setup layer — weekly/bi-weekly setup state + stage assignment.

Computes a multi-timeframe setup snapshot per the China Alpha Masterplan (F2/W1):
  - 2W-FRI resample via cycles._tf_state (stoch, stoch_cross_up, macd_pos,
    macd_approaching_up, macd_bars_to_cross, macd_cross_up, rsi14)
  - 1W-FRI StochRSI k/d cross: last bullish k-over-d cross, bars-since, d-value-at-cross
    (washout zone = d_at_cross < 25)
  - 2y (504-bar) range width + spot position; base_age heuristic
  - setup_live bool + reasons list

Stage assignment rules (ENTRY / RIPENING / RAN_LATE) mirror the masterplan spec exactly.

Nearest sibling: engine/hold.py (same _tf_bars / _stoch_rsi_kd / _rsi_macd imports;
same dict | None returns; same MIN_HISTORY guard).

Public API:
  w_setup(close)           -> dict | None   (W-tier state per name)
  assign_stage(...)        -> dict           (stage + sublabel + detail)
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

    Implements EXACTLY the masterplan F1/W1 stage rules 1-5:

    Rule 1 — gate-eligible AND entry_status in {buy_now, partial} -> ENTRY
    Rule 2 — gate-eligible BUT entry_status == hold OR overextended -> RAN_LATE
              sublabel: "signal live - entry passed; wait for pullback"
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
        True when the name is in an extended/overbought state (alignment.overextended
        or entry_status in {"extended", "topping"}).
    last_cross_info : dict | None
        Keys: cross_date (str), sessions_since (int), pct_since (float).
        Rule 3 fires when sessions_since <= 15.
    hold_state : dict | None
        From engine.hold.hold_state(). Keys: state, anchor.
        Rule 3 may append a basing-intact chip.
    wsetup : dict | None
        From w_setup().  setup_live + setup_reasons drive rule 4.

    Returns
    -------
    dict with keys: stage, sublabel, detail
    """
    # ── Rule 1: gate-eligible + actionable entry (ONLY when NOT overextended) ───
    if gate_eligible and entry_status in ("buy_now", "partial") and not overextended:
        return {
            "stage": STAGE_ENTRY,
            "sublabel": None,
            "detail": {"entry_status": entry_status},
        }

    # ── Rule 2: gate-eligible but extended / hold / overextended ─────────────
    # Fires when gate is live but the entry is NOT immediately actionable:
    #   - overextended flag (alignment.overextended in the spec) — F6 ruling: extension
    #     beats the timing gauge, even when entry_status is buy_now or partial
    #   - entry_status == "hold" (the explicit spec case)
    #   - entry_status not in {buy_now, partial} (extended, topping, etc.)
    #
    # Adjudicated design (F6): a buy_now/partial + overextended row is a LEGITIMATE
    # input that routes here.  We emit muted_entry=True in the detail dict so the
    # template can suppress green banding without rewriting the entry_signal block.
    # Sublabel varies by whether the entry gauge was nominally open:
    if gate_eligible and (
        overextended
        or entry_status == "hold"
        or entry_status not in ("buy_now", "partial", None)
    ):
        _muted = overextended and entry_status in ("buy_now", "partial")
        _sublabel = (
            "entry gauge open — but extended; wait for pullback"
            if _muted
            else "signal live — entry passed; wait for pullback"
        )
        return {
            "stage": STAGE_RAN_LATE,
            "sublabel": _sublabel,
            "detail": {
                "entry_status": entry_status,
                "overextended": overextended,
                "muted_entry": _muted,
            },
        }

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
