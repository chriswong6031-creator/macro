"""Regime-snap / narrative-relief detector (DISPLAY-ONLY).

The VELOCITY complement to the Fear<->Euphoria panel (the site-builder's
regime-LEVEL synthesis over the same RORO legs). This reads the
TRANSITION: a fast risk-ON snap — the cross-asset RORO complex
flipping risk-on HARD and BROADLY over 1-3 sessions, coming OUT of recent
elevated fear. That is the 'relief rally' fingerprint: a geopolitical
de-escalation, a post-CPI relief day, a growth-scare reversal — the moves where
VIX collapses, yields fall, oil gives back a fear premium and high-beta snaps
back faster than the slow technicals (RSI, breadth, moving averages) can
recover.

Discipline (identical to the Fear<->Euphoria panel — see
research/FEAR_EUPHORIA_PANEL_SPEC.md and the RORO note in engine.conditions):
  * ZERO new data — reads only the signed roro_<key> legs and a few risk gauges
    already on the conditions frame.
  * NEVER scored — nothing in axes / regime / macro_risk imports this. It is a
    render kwarg / context lens, exactly like RORO itself (which gates nothing).
  * The relief-magnitude scales with the fear premium being unwound (bigger
    prior fear -> bigger mean-reversion available). It is a CONTEXT gauge, not a
    position size, until scripts/regime_snap_history.py is promoted to a full
    Phase-0 (PIT, FDR, Deflated-Sharpe) harness and PASSES. Until then it is a
    faster READ on a turn that is happening, not a forecast that one will.

Why velocity, not level: the slow technicals lag a violent re-rate by
construction (they need days to recover), but the cross-asset PRICE legs are
coincident-to-leading. Counting how many legs flip risk-on together, and how
fast the composite is moving, confirms the snap on day 1 instead of day 5 —
which is the whole point (the first leg of a relief rally is the largest).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine.indicators import pct_rank_window
from lib import config

# The 7 signed RORO legs (engine.conditions stores them as roro_<key>, each
# oriented risk-on-positive). Same set/order as the Fear<->Euphoria decomposition.
_LEG_KEYS = ["vix", "hy_oas", "skew", "vix_term", "nfci", "copper_gold", "dxy"]

_DEFAULTS = {
    "window_d": 2,                 # 1-3 session change (2 captures a 2-day re-rate)
    "leg_sigma_mult": 1.0,         # leg 'flips' when its window-change > 1σ of its own history
    "leg_std_lookback_d": 252,
    "min_legs": 4,                 # >=4 of ~7 cross-asset legs flip risk-on together
    "vel_pctile_lookback_d": 504,  # ~2y window for the RORO-velocity percentile
    "vel_min_pctile": 0.90,        # RORO velocity in its top decile = a genuine thrust
    "fear_lookback_d": 21,         # 'recent' fear = trailing ~month
    "fear_min": 0.40,              # the thrust must come OUT of a fear context (modest bar)
    "require_capitulation": True,  # AND a washout must have printed recently (the decisive gate)
    "cap_lookback_d": 21,          # window for 'a capitulation signal printed recently'
}


def _cfg(cfg: dict | None = None) -> dict:
    if cfg is not None:
        return {**_DEFAULTS, **cfg}
    try:
        c = dict(config.load()["engine"]["conditions"].get("regime_snap") or {})
    except Exception:  # noqa: BLE001 — config-less callers (tests) fall back to defaults
        c = {}
    return {**_DEFAULTS, **c}


def _fear_index(cf: pd.DataFrame) -> pd.Series:
    """Daily 0..1 fear gauge from gauges already on the conditions frame. Mean of
    whatever is available, so it degrades gracefully: VRP percentile, SKEW
    percentile, VIX percentile, VIX-term backwardation, the capitulation count and
    the RORO level."""
    gauges = []
    for col in ("vrp_pctile", "skew_pctile", "vix_pctile"):
        if col in cf.columns:
            gauges.append(cf[col].clip(0, 1))
    if "vix_term" in cf.columns:
        # vix/vix3m > 1 = front-month backwardation = acute fear; 1.0 -> 0, 1.10 -> 1
        gauges.append(((cf["vix_term"] - 1.0) / 0.10).clip(0, 1))
    if "capitulation_score" in cf.columns:
        gauges.append((cf["capitulation_score"] / 3.0).clip(0, 1))
    if "roro" in cf.columns:
        gauges.append((-cf["roro"] / 1.5).clip(0, 1))      # deeply negative RORO = fear
    if not gauges:
        return pd.Series(np.nan, index=cf.index)
    return pd.concat(gauges, axis=1).mean(axis=1)


def snap_frame(cf: pd.DataFrame, cfg: dict | None = None) -> pd.DataFrame:
    """Daily regime-snap time series from a conditions frame. Display-only; a pure
    function of cf (no new data, no look-ahead — every window is trailing).

    Columns: roro, roro_velocity, vel_pctile, legs_up, legs_total, fear_index,
    fear_built, snap (0/1), relief_magnitude (0..100), and per-leg <key>_flip
    booleans for the evidence line."""
    c = _cfg(cfg)
    w = int(c["window_d"])
    out = pd.DataFrame(index=cf.index)

    roro = cf["roro"] if "roro" in cf.columns else pd.Series(np.nan, index=cf.index)
    out["roro"] = roro
    out["roro_velocity"] = roro.diff(w)
    out["vel_pctile"] = pct_rank_window(out["roro_velocity"], int(c["vel_pctile_lookback_d"]))

    # Per-leg flip: the leg moved risk-on by more than `leg_sigma_mult` of its own
    # window-change volatility. Counting agreeing legs is the dispersion the
    # headline RORO mean hides — a single-leg lurch and a broad thrust can move the
    # mean by the same amount; only the broad thrust is a regime snap.
    legs_present = [k for k in _LEG_KEYS if f"roro_{k}" in cf.columns]
    flip_cols = []
    for k in legs_present:
        d = cf[f"roro_{k}"].diff(w)
        std = d.rolling(int(c["leg_std_lookback_d"]), min_periods=60).std()
        flip = (d > float(c["leg_sigma_mult"]) * std) & d.notna() & std.notna()
        out[f"{k}_flip"] = flip
        flip_cols.append(flip.astype(float))
    out["legs_total"] = float(len(legs_present))
    out["legs_up"] = (pd.concat(flip_cols, axis=1).sum(axis=1)
                      if flip_cols else pd.Series(0.0, index=cf.index))

    fear = _fear_index(cf)
    out["fear_index"] = fear
    # Peak fear over the trailing window, EXCLUDING today (shift 1): the premium
    # that built up and is now being unwound by the snap.
    out["fear_built"] = fear.rolling(int(c["fear_lookback_d"]), min_periods=3).max().shift(1)

    # Capitulation washout gate — the DECISIVE quality filter. Historical
    # verification (scripts/regime_snap_history.py) showed that the velocity+breadth
    # thrust ALONE fires on mid-crash dead-cat rallies (negative forward returns —
    # it fired ~3wk before the COVID bottom). Requiring that a capitulation signal
    # (engine.conditions capitulation_score: VRP-spike / VIX>30 / COT-washout)
    # printed in the trailing window separates a relief OUT OF a washout from a
    # falling knife, flips forward returns from negative to ~base-rate, and catches
    # the slow-grind reliefs (2022 CPI, SVB, the 2026-06 geopolitical relief) the
    # acute-fear gate missed. Absent the column it degrades to all-True (no gate).
    cap_ok = pd.Series(True, index=cf.index)
    if c.get("require_capitulation") and "capitulation_score" in cf.columns:
        cap_ok = (cf["capitulation_score"].rolling(
            int(c["cap_lookback_d"]), min_periods=1).max() >= 1)
    out["cap_recent"] = cap_ok.fillna(False).astype(int)

    snap = (
        (out["vel_pctile"] >= float(c["vel_min_pctile"]))
        & (out["legs_up"] >= float(c["min_legs"]))
        & (out["roro_velocity"] > 0)
        & (out["fear_built"] >= float(c["fear_min"]))
        & cap_ok
    )
    out["snap"] = snap.fillna(False).astype(int)

    # Relief magnitude (0..100): the fear premium being unwound, broadened by how
    # many legs confirm. Dominated by fear_built (the mean-reversion fuel); the
    # leg-breadth term modulates it +/-25%. Only meaningful on snap days.
    breadth = (out["legs_up"] / out["legs_total"].replace(0, np.nan)).clip(0, 1)
    mag = 100.0 * out["fear_built"].clip(0, 1) * (0.5 + 0.5 * breadth)
    out["relief_magnitude"] = (mag * out["snap"]).clip(0, 100).fillna(0.0)
    return out


def snap_snapshot(cf: pd.DataFrame, cfg: dict | None = None) -> dict | None:
    """Latest-day display payload for the relief-radar card. None on shortfall
    (e.g. a too-shallow frame), never raises — additive panel."""
    try:
        c = _cfg(cfg)
        sf = snap_frame(cf, c)
        if sf["roro"].dropna().empty:
            return None
        last = sf.iloc[-1]

        # days since the most recent snap strictly before today
        prior = sf["snap"].iloc[:-1]
        fired = prior[prior == 1]
        days_since = (None if fired.empty
                      else int((len(sf) - 1) - sf.index.get_loc(fired.index[-1])))

        legs_present = [k for k in _LEG_KEYS if f"roro_{k}" in cf.columns]
        flipped = [k for k in legs_present if bool(last.get(f"{k}_flip", False))]

        # playbook invalidation inputs: is fear re-building (relief stalling) and
        # where is the front-end VIX term (backwardation returning = re-stress)
        fear_rebuilding = False
        if "fear_index" in sf.columns and len(sf) >= 4:
            a, b = sf["fear_index"].iloc[-1], sf["fear_index"].iloc[-4]
            fear_rebuilding = bool(np.isfinite(a) and np.isfinite(b) and a > b)

        def _f(x: float | None) -> float | None:
            return None if x is None or not np.isfinite(x) else round(float(x), 3)

        return {
            "snap": bool(last["snap"]),
            "relief_magnitude": (None if not last["snap"]
                                 else int(round(float(last["relief_magnitude"])))),
            "roro": _f(last.get("roro")),
            "cap_recent": bool(last.get("cap_recent", 0)),
            "fear_built": _f(last.get("fear_built")),
            "roro_velocity": _f(last.get("roro_velocity")),
            "vel_pctile": _f(last.get("vel_pctile")),
            "legs_up": int(last["legs_up"]) if np.isfinite(last["legs_up"]) else 0,
            "legs_total": int(last["legs_total"]) if np.isfinite(last["legs_total"]) else 0,
            "flipped_legs": flipped,
            "days_since_last_snap": days_since,
            "fear_rebuilding": fear_rebuilding,
            "vix_term": _f(cf["vix_term"].iloc[-1]) if "vix_term" in cf.columns else None,
        }
    except Exception:  # noqa: BLE001 — additive panel, never fatal
        return None
