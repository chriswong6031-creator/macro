"""Regression tests for two adversarially-confirmed signal-surface bugs.

1. engine/gex_model.py — a strike whose feed gamma AND iv are both blank used to be
   filled with a 0.0001 sentinel IV, and the BS gamma 1/sigma factor then produced a
   ~2500x near-money spike that became the heatmap max and corrupted the color scale.
2. engine/hk_stock_signals.py — a NEUTRAL regime-fit tilt returned 0.0, which stayed
   in the edge-z denominator and haircut any name with a beta role; it must return
   None so the leg drops out of the renormalization.
"""
from datetime import date, timedelta

import numpy as np
import pandas as pd

from engine.gex_model import bs_greeks, build_model
from engine.hk_stock_signals import _regime_fit_z

SPOT = 100.0


def _mini_chain(blank_atm=False):
    today = pd.Timestamp(date.today())
    exp = today + timedelta(days=30)
    T = 30 / 365.0
    rows = []
    for k in range(80, 121, 2):
        iv = 0.25 + 0.004 * (SPOT - k)
        for is_call in (True, False):
            row = dict(K=float(k), T=T, iv=iv, oi=500.0, is_call=is_call, expiry=exp,
                       volume=150.0, gamma=bs_greeks(SPOT, k, T, iv, is_call)[1])
            intrinsic = max(0.0, (SPOT - k) if is_call else (k - SPOT))
            row["bid"], row["ask"] = intrinsic + 1.0, intrinsic + 1.4
            rows.append(row)
    df = pd.DataFrame(rows)
    if blank_atm:                       # a realistic co-missing illiquid contract
        m = (df["K"] == 100.0) & df["is_call"]
        df.loc[m, ["iv", "gamma"]] = np.nan
    return df


def test_gex_blank_iv_and_gamma_not_spiked():
    base = build_model(_mini_chain(), SPOT, {"q": 0.0})["surface"]
    blanked = build_model(_mini_chain(blank_atm=True), SPOT, {"q": 0.0})["surface"]
    # the blank ATM cell must contribute ~zero gamma, NOT a ~2500x spike that
    # becomes gex_max and washes out the whole heatmap.
    assert blanked["gex_max"] <= base["gex_max"] * 1.5 + 1, \
        f"blank-iv cell spiked gex_max: {blanked['gex_max']} vs base {base['gex_max']}"


def test_calibrate_vector_expret_cross_fit_is_oos():
    from scripts.calibrate_vector import _expret_signal
    idx = pd.date_range("2015-01-01", periods=400, freq="D")
    sig = pd.Series(np.linspace(-2.5, 2.5, 400), index=idx)
    fwd = pd.DataFrame({90: np.cos(np.linspace(0, 8, 400))}, index=idx)
    pre, post = idx[:200], idx[200:]
    halves = {"pre": pre, "post": post, "full": idx}
    bands, labels = [-3.0, -1.0, 1.0, 3.0], ["lo", "mid", "hi"]
    base = _expret_signal(sig, fwd, bands, labels, 90, halves=halves)
    fwd2 = fwd.copy()
    fwd2.loc[post, 90] = fwd2.loc[post, 90] + 100.0          # perturb POST's own outcomes
    pert = _expret_signal(sig, fwd2, bands, labels, 90, halves=halves)
    # the post half is oriented by the PRE half, so perturbing post outcomes must NOT
    # change the post-half orientation — proves the pre/post comparison is out-of-sample
    a, b = base.loc[post].dropna(), pert.loc[post].dropna()
    common = a.index.intersection(b.index)
    assert len(common) > 50
    assert np.allclose(a.loc[common], b.loc[common]), "post orientation leaked its own outcomes"


def test_hk_neutral_regime_fit_drops_out():
    # informative tilts keep their signal...
    assert _regime_fit_z("amplifier", "favored") == 0.8
    assert _regime_fit_z("amplifier", "exposed") == -0.8
    assert _regime_fit_z("cushion", "lag") == -0.3
    # ...but a NEUTRAL tilt returns None (absent leg), even WITH a beta role,
    # so it cannot haircut the name via the denominator.
    assert _regime_fit_z("amplifier", "neutral") is None
    assert _regime_fit_z("cushion", None) is None
    assert _regime_fit_z(None, None) is None
