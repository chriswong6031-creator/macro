"""Transition detector — fires BEFORE the regime flips.

Six independent divergence flags; the state machine escalates
STABLE -> WEAKENING (>=2 flags) -> TRANSITIONING (>=3 flags or the quad
hysteresis countdown has started) and emits NEW_REGIME on the day the
confirmed quad actually changes.
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

    flags = pd.DataFrame({
        "flag_breadth_price": flag_breadth,
        "flag_credit_equity": flag_credit,
        "flag_ratio_inflection": flag_ratio,
        "flag_inflation_basket": flag_infl,
        "flag_confidence_decay": flag_decay,
        "flag_gex": flag_gex,
    })
    flags["n_flags"] = flags.sum(axis=1)
    return flags


def state_machine(flags: pd.DataFrame, regime: pd.DataFrame) -> pd.Series:
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
    return pd.Series(states, index=flags.index, name="transition_state")
