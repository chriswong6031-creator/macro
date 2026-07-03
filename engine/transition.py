"""Transition detector — fires BEFORE the regime flips.

Seven independent divergence flags; the state machine escalates
STABLE -> WEAKENING (>=2 flags) -> TRANSITIONING (>=3 flags or the quad
hysteresis countdown has started) and emits NEW_REGIME on the day the
confirmed quad actually changes.

De-escalation is RATCHETED (2026-07-02 semis-breakdown incident): the raw
counter is memoryless, so WEAKENING regressed to STABLE on 2026-07-01 — the
eve of the breakdown — purely because two momentary flag windows rolled off
while the cyclical/defensive rotation was still live (the history oscillated
TRANSITIONING<->STABLE<->WEAKENING 5x over 06-15..07-01). The ratchet makes
"all clear" something the tape must EARN: escalation stays instant, but
stepping DOWN one level requires clear_dwell_days consecutive clean sessions
(n_flags below the weakening bar, rotation-persistence off, contradiction
floor off); any dirty session resets the countdown (the re-arm hard clamp);
and a max_dwell_days auto-release guarantees a stuck state self-heals —
degrade-safe, never a hard lock. The whole series is reconstructed from flag
history each build (like regime.apply_hysteresis), so no state file exists to
corrupt: a short history simply degrades to the raw read.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine.indicators import rolling_slope
from lib import config

RISK_ON_QUADS = {"Q1", "Q2"}
INFLATION_UP_QUADS = {"Q2", "Q3"}


def compute_flags(f: pd.DataFrame, regime: pd.DataFrame) -> pd.DataFrame:
    cfg = config.load()["engine"]["transition"]

    # 1. breadth/price divergence
    bp = cfg["breadth_price"]
    near_high = f["SPY"] >= f["SPY"].rolling(bp["high_window_d"], min_periods=30).max() \
        * (1 - bp["index_near_high_pct"] / 100)
    breadth_drop = f["pct_above_50"].diff(bp["breadth_drop_window_d"]) < -bp["breadth_drop_pts"]
    flag_breadth = (near_high & breadth_drop).fillna(False)

    # 2. credit/equity divergence
    ce = cfg["credit_equity"]
    spy_ret = f["SPY"].pct_change(ce["ret_window_d"], fill_method=None)
    oas_chg = f["hy_oas"].diff(ce["ret_window_d"])
    oas_z = (oas_chg - oas_chg.rolling(252, min_periods=126).mean()) \
        / oas_chg.rolling(252, min_periods=126).std()
    flag_credit = ((spy_ret > 0) & (oas_z > ce["oas_z_threshold"])).fillna(False)

    # 3. cyclical/defensive ratio slope sign flip against the quad's stance
    win = cfg["ratio_inflection"]["slope_window_d"]
    risk_on = regime["quad"].isin(RISK_ON_QUADS)
    flag_ratio = pd.Series(False, index=f.index)
    for col in ["xly_xlp", "sphb_splv"]:
        if col not in f or f[col].isna().all():
            continue
        sl = rolling_slope(np.log(f[col].where(f[col] > 0)), win)
        flipped_dn = (sl < 0) & (sl.shift(5) > 0)
        flipped_up = (sl > 0) & (sl.shift(5) < 0)
        flag_ratio |= (risk_on & flipped_dn).fillna(False) | (~risk_on & flipped_up).fillna(False)

    # 4. inflation basket inflecting against the quad's inflation assumption
    infl_up = regime["quad"].isin(INFLATION_UP_QUADS)
    if "infl_basket" in f and not f["infl_basket"].isna().all():
        isl = rolling_slope(np.log(f["infl_basket"].where(f["infl_basket"] > 0)), win)
        i_dn = (isl < 0) & (isl.shift(5) > 0)
        i_up = (isl > 0) & (isl.shift(5) < 0)
        flag_infl = (infl_up & i_dn).fillna(False) | (~infl_up & i_up).fillna(False)
    else:
        flag_infl = pd.Series(False, index=f.index)

    # 5. dominant-axis agreement decay over 10d
    dom_is_growth = regime["growth_score"].abs() >= regime["inflation_score"].abs()
    dom_agree = regime["growth_agreement"].where(dom_is_growth, regime["inflation_agreement"])
    decay_w = cfg["confidence_decay_window_d"]
    flag_decay = (dom_agree.diff(decay_w) < -0.1).fillna(False)

    # 6. GEX fragility: net GEX negative or spot within proximity of the flip
    if "net_gex_bn" in f and not f["net_gex_bn"].isna().all():
        near_flip = f["spot_vs_flip_pct"].abs() <= cfg["gex_flip_proximity_pct"]
        flag_gex = ((f["net_gex_bn"] < 0) | near_flip).fillna(False)
    else:
        flag_gex = pd.Series(False, index=f.index)

    # 7. SLOW rotation persistence (incident root-cause #2): the cyclical/defensive
    # ratio slope has sat on the wrong side of the quad's risk stance for
    # rotation_persist_days STRAIGHT — a LEVEL condition, unlike flag 3's 5-day
    # inflection window which rolls off while the rotation is still live. This is
    # the flag whose absence let the memoryless counter forget the June rotation.
    # Counts toward n_flags AND gates the ratchet's de-escalation.
    persist_n = int(cfg.get("rotation_persist_days", 10))
    contra = pd.Series(False, index=f.index)
    for col in ["xly_xlp", "sphb_splv"]:
        if col not in f or f[col].isna().all():
            continue
        sl = rolling_slope(np.log(f[col].where(f[col] > 0)), win)
        contra |= ((risk_on & (sl < 0)).fillna(False)
                   | (~risk_on & (sl > 0)).fillna(False))
    flag_rotation = (contra.rolling(persist_n, min_periods=persist_n).sum()
                     >= persist_n).fillna(False)

    flags = pd.DataFrame({
        "flag_breadth_price": flag_breadth,
        "flag_credit_equity": flag_credit,
        "flag_ratio_inflection": flag_ratio,
        "flag_inflation_basket": flag_infl,
        "flag_confidence_decay": flag_decay,
        "flag_gex": flag_gex,
        "flag_rotation_persistence": flag_rotation,
    })
    flags["n_flags"] = flags.sum(axis=1)
    return flags


def contradiction_floor(regime: pd.DataFrame) -> pd.Series:
    """{cyclical_defensive, wei_trend} BOTH contradicting the growth axis's own
    sign forces at least WEAKENING regardless of the flag windows (incident
    signals.md §4 item 3: the label's contradiction list knew, but the momentary
    flags had rolled off). Reads the per-component c_ scores classify() already
    writes; degrades to all-False when the columns are absent."""
    cols = ["c_growth_cyclical_defensive", "c_growth_wei_trend"]
    if any(c not in regime.columns for c in cols):
        return pd.Series(False, index=regime.index)
    sign = np.sign(regime["growth_score"])
    both = pd.Series(True, index=regime.index)
    for c in cols:
        both &= (regime[c] * sign) < 0
    return both.fillna(False)


_LEVELS = ["STABLE", "WEAKENING", "TRANSITIONING"]


def _raw_states(flags: pd.DataFrame, regime: pd.DataFrame) -> pd.Series:
    """The memoryless flag-counter read (the pre-ratchet legacy behavior)."""
    cfg = config.load()["engine"]["transition"]
    weak_n, trans_n = cfg["weakening_flags"], cfg["transitioning_flags"]

    quad = regime["quad"]
    quad_changed = quad.ne(quad.shift()) & quad.notna() & quad.shift().notna()
    pending = regime["pending_days"] > 0

    states: list[str] = []
    prev_quad_change_recent = 0
    for dt in flags.index:
        n = int(flags.loc[dt, "n_flags"])
        if bool(quad_changed.loc[dt]):
            states.append("NEW_REGIME")
            prev_quad_change_recent = 5  # show NEW_REGIME stickiness for a week
            continue
        if prev_quad_change_recent > 0 and n < weak_n:
            states.append("NEW_REGIME")
            prev_quad_change_recent -= 1
            continue
        prev_quad_change_recent = 0
        if n >= trans_n or (n >= weak_n and bool(pending.loc[dt])):
            states.append("TRANSITIONING")
        elif n >= weak_n:
            states.append("WEAKENING")
        else:
            states.append("STABLE")
    return pd.Series(states, index=flags.index, name="transition_state_raw")


def state_machine_detail(flags: pd.DataFrame, regime: pd.DataFrame) -> pd.DataFrame:
    """Raw + ratcheted transition state, walked deterministically from flag history.

    Escalation is instant (any session may go hotter the moment flags/pending
    justify it). De-escalation steps down ONE level only after clear_dwell_days
    consecutive CLEAN sessions — n_flags < weakening_flags AND the slow
    rotation-persistence flag off AND the contradiction floor off. A dirty
    session resets the countdown to 0 (re-arm hard clamp). max_dwell_days of
    being held above the raw read force-releases one step, so a permanently
    dirty tape degrades gracefully instead of locking WEAKENING forever.
    NEW_REGIME passes through verbatim and resets the ladder: a confirmed flip
    is a new baseline, not something to de-escalate FROM.

    Returns columns: transition_state (ratcheted, the headline),
    transition_state_raw, transition_ratcheted (bool: held hotter than raw),
    transition_dwell_remaining (clean sessions still required to step down).
    """
    cfg = config.load()["engine"]["transition"]
    raw = _raw_states(flags, regime)
    ratchet_on = bool(cfg.get("ratchet_enabled", True))
    clear_dwell = int(cfg.get("clear_dwell_days", 5))
    max_dwell = int(cfg.get("max_dwell_days", 15))
    weak_n = int(cfg["weakening_flags"])
    if bool(cfg.get("contradiction_floor", True)):
        floor = contradiction_floor(regime).reindex(flags.index).fillna(False)
    else:
        floor = pd.Series(False, index=flags.index)
    rot = flags.get("flag_rotation_persistence",
                    pd.Series(False, index=flags.index))

    out_state: list[str] = []
    out_ratcheted: list[bool] = []
    out_dwell: list[int] = []
    cur = 0          # confirmed ladder level (index into _LEVELS)
    dwell_clean = 0  # consecutive clean sessions toward the next step-down
    held = 0         # consecutive sessions held above the raw read (max-dwell guard)
    for dt in flags.index:
        raw_s = str(raw.loc[dt])
        if raw_s == "NEW_REGIME":
            out_state.append("NEW_REGIME")
            out_ratcheted.append(False)
            out_dwell.append(0)
            cur, dwell_clean, held = 0, 0, 0
            continue
        raw_lvl = _LEVELS.index(raw_s)
        if not ratchet_on:
            out_state.append(raw_s)
            out_ratcheted.append(False)
            out_dwell.append(0)
            cur, dwell_clean, held = raw_lvl, 0, 0
            continue
        n = int(flags.loc[dt, "n_flags"])
        forced = bool(floor.loc[dt])
        target = max(raw_lvl, 1 if forced else 0)  # contradiction pair floors at WEAKENING
        if target >= cur:
            cur = target
            dwell_clean, held = 0, 0
        else:
            held += 1
            clean = (n < weak_n) and not bool(rot.loc[dt]) and not forced
            dwell_clean = dwell_clean + 1 if clean else 0  # re-arm hard clamp
            if dwell_clean >= clear_dwell or held >= max_dwell:
                cur -= 1  # one level per completed dwell, never straight to STABLE
                dwell_clean, held = 0, 0
        out_state.append(_LEVELS[cur])
        out_ratcheted.append(cur > raw_lvl)
        out_dwell.append(clear_dwell - dwell_clean if cur > raw_lvl else 0)
    return pd.DataFrame({
        "transition_state": out_state,
        "transition_state_raw": raw.tolist(),
        "transition_ratcheted": out_ratcheted,
        "transition_dwell_remaining": out_dwell,
    }, index=flags.index)


def state_machine(flags: pd.DataFrame, regime: pd.DataFrame) -> pd.Series:
    """Back-compat wrapper: the ratcheted headline state as a Series."""
    return state_machine_detail(flags, regime)["transition_state"].rename("transition_state")
