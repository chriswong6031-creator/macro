"""Finite-difference-verified greeks + GEX engine sanity.

The greeks (gamma/vanna/charm) are checked against numerical derivatives of delta —
the only honest way to pin the sign+scaling conventions the whole magnets layer
rests on. Engine tests assert the economic behaviour (call-heavy -> +GEX, magnets
at the max dollar-gamma strikes, fragility tiering).
"""
import math

import numpy as np
import pandas as pd
import pytest

from engine.greeks import bs_greeks
from engine.gex_engine import compute_gex

R, Q = 0.03, 0.01


def _delta(S, K, T, sig, call):
    return bs_greeks(S, K, T, sig, call, R, Q)[0]


@pytest.mark.parametrize("call", [True, False])
def test_gamma_is_dDelta_dS(call):
    S, K, T, sig = 100.0, 105.0, 0.5, 0.2
    _, gamma, _, _ = bs_greeks(S, K, T, sig, call, R, Q)
    h = 1e-3 * S
    fd = (_delta(S + h, K, T, sig, call) - _delta(S - h, K, T, sig, call)) / (2 * h)
    assert abs(gamma - fd) < 1e-4, (gamma, fd)


@pytest.mark.parametrize("call", [True, False])
def test_vanna_is_dDelta_dSigma(call):
    S, K, T, sig = 100.0, 105.0, 0.5, 0.2
    _, _, vanna, _ = bs_greeks(S, K, T, sig, call, R, Q)
    h = 1e-4
    fd = (_delta(S, K, T, sig + h, call) - _delta(S, K, T, sig - h, call)) / (2 * h)
    assert abs(vanna - fd) < 5e-4, (vanna, fd)


@pytest.mark.parametrize("call", [True, False])
def test_charm_is_dDelta_dt(call):
    S, K, T, sig = 100.0, 105.0, 0.5, 0.2
    _, _, _, charm = bs_greeks(S, K, T, sig, call, R, Q)
    h = 1e-4
    # charm = d delta / d calendar-time = - d delta / dT
    fd = -(_delta(S, K, T + h, sig, call) - _delta(S, K, T - h, sig, call)) / (2 * h)
    assert abs(charm - fd) < 5e-4, (charm, fd)


def test_degenerate_nan():
    assert all(math.isnan(x) for x in bs_greeks(100, 100, 0.0, 0.2, True))
    assert all(math.isnan(x) for x in bs_greeks(100, 100, 0.5, 0.0, False))


def _chain(call_oi, put_oi, S=100.0, iv=0.25, T=0.08):
    rows = []
    for k in range(80, 121, 2):
        rows.append(dict(K=float(k), T=T, iv=iv, oi=call_oi, is_call=True))
        rows.append(dict(K=float(k), T=T, iv=iv, oi=put_oi, is_call=False))
    return pd.DataFrame(rows)


def test_call_heavy_pos_gex_put_heavy_neg():
    S = 100.0
    assert compute_gex(_chain(1000, 10, S), S)["net_gex_bn"] > 0
    assert compute_gex(_chain(10, 1000, S), S)["net_gex_bn"] < 0


def test_magnets_at_max_dollar_gamma_strike():
    S, rows = 100.0, []
    for k in range(80, 121, 2):
        oi = 8000 if k in (94, 110) else 100
        rows.append(dict(K=float(k), T=0.08, iv=0.25, oi=oi, is_call=True))
        rows.append(dict(K=float(k), T=0.08, iv=0.25, oi=oi, is_call=False))
    g = compute_gex(pd.DataFrame(rows), S)
    assert g["magnet_down"] == 94.0
    assert g["magnet_up"] == 110.0


def test_summary_keys_and_tiers():
    S = 100.0
    g = compute_gex(_chain(1000, 1000, S), S)
    for k in ("net_gex_bn", "net_vex", "net_cex", "gamma_regime", "magnet_up",
              "magnet_down", "charm_anchor", "iv30", "put_call_oi_ratio", "max_pain", "tier"):
        assert k in g
    assert g["tier"] in ("full", "thin_chain")
    assert compute_gex(pd.DataFrame([]), S)["tier"] == "no_options"
    few = [dict(K=100.0, T=0.08, iv=0.25, oi=100, is_call=True),
           dict(K=105.0, T=0.08, iv=0.25, oi=100, is_call=False)]
    assert compute_gex(pd.DataFrame(few), S)["tier"] == "no_options"   # <6 strikes


def test_gamma_regime_passport_single_name_vs_index():
    """Audit #29: every gamma_regime carries an assumption-basis passport. Single names are
    flagged structurally-constant (product attribute, not a time-varying signal); indices are
    not, but are still assumption-signed."""
    S = 100.0
    single = compute_gex(_chain(1000, 1000, S), S, symbol="AAPL")["regime_passport"]
    assert single["basis"] == "assumption"
    assert single["structurally_constant"] is True
    assert single["is_index_product"] is False
    assert single["verdict"] == "display-only"

    index = compute_gex(_chain(1000, 1000, S), S, symbol="SPX")["regime_passport"]
    assert index["basis"] == "assumption"
    assert index["structurally_constant"] is False   # market-wide read, not a name attribute
    assert index["is_index_product"] is True

    # no symbol -> still assumption-basis, but constancy is unknown (None)
    anon = compute_gex(_chain(1000, 1000, S), S)["regime_passport"]
    assert anon["basis"] == "assumption" and anon["structurally_constant"] is None


# ── gamma_profile — the ±25% spot-grid exposure curve (masterplan §4.2) ──────────────
# One definition: _gamma_flip is a thin wrapper over gamma_profile, so the published
# curve and the published crossing can never disagree.

def test_gamma_profile_shape_and_center():
    from engine.gex_engine import DEFAULTS, _window, gamma_profile
    S = 100.0
    cfg = dict(DEFAULTS)
    c = _window(_chain(1000, 10, S), S, cfg)
    grid, net, flips = gamma_profile(c, S, cfg)
    assert grid is not None and len(grid) == 101 and len(net) == 101
    # centre grid point IS the current spot (linspace 0.75..1.25 × S, index 50)
    assert grid[50] == pytest.approx(S)
    # grid strictly increasing
    assert all(grid[i] < grid[i + 1] for i in range(100))


def test_gamma_profile_sign_at_spot_matches_book():
    from engine.gex_engine import DEFAULTS, _window, gamma_profile
    S = 100.0
    cfg = dict(DEFAULTS)
    call_heavy = gamma_profile(_window(_chain(1000, 10, S), S, cfg), S, cfg)
    put_heavy = gamma_profile(_window(_chain(10, 1000, S), S, cfg), S, cfg)
    assert call_heavy[1][50] > 0   # dealers long-call heavy → positive gamma at spot
    assert put_heavy[1][50] < 0    # dealers short-put heavy → negative gamma at spot


def test_gamma_flip_is_nearest_profile_crossing():
    from engine.gex_engine import DEFAULTS, _gamma_flip, _window, gamma_profile
    S = 100.0
    cfg = dict(DEFAULTS)
    # A mixed book whose sign changes across the grid: heavy puts below spot,
    # heavy calls above — the classic index shape with a flip near spot.
    rows = []
    for k in range(80, 121, 2):
        rows.append(dict(K=float(k), T=0.08, iv=0.25, oi=3000 if k >= 100 else 50, is_call=True))
        rows.append(dict(K=float(k), T=0.08, iv=0.25, oi=3000 if k < 100 else 50, is_call=False))
    c = _window(pd.DataFrame(rows), S, cfg)
    grid, net, flips = gamma_profile(c, S, cfg)
    flip, dist, regime = _gamma_flip(c, S, cfg)
    if flip is None:
        assert not flips
    else:
        assert flips, "wrapper found a flip the profile did not"
        assert flip == pytest.approx(min(flips, key=lambda f: abs(f - S)))
        # the crossing really is a sign change of the published curve
        i = int(np.searchsorted(grid, flip))
        assert 0 < i < 101
        assert (net[i - 1] < 0) != (net[i] < 0) or net[i - 1] == 0.0


def test_gamma_profile_thin_chain_declines():
    from engine.gex_engine import DEFAULTS, gamma_profile
    S = 100.0
    few = pd.DataFrame([
        dict(K=100.0, T=0.08, iv=0.25, oi=100, is_call=True),
        dict(K=105.0, T=0.08, iv=0.25, oi=100, is_call=False),
    ])
    grid, net, flips = gamma_profile(few, S, dict(DEFAULTS))
    assert grid is None and net is None and flips == []
