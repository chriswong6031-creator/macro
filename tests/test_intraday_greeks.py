"""Tests for engine/intraday_greeks — the intraday Black-Scholes greek engine.

The engine solves implied vol from option mids (Newton + bisection), computes greeks
(vectorized twins of engine/greeks.bs_greeks), and aggregates per-strike dealer exposure
(GEX/DEX/VEX/CEX) + gamma flip / call-wall / put-wall using the SAME conventions as the
EOD engine (engine/gex_engine.compute_gex + engine/gex_model). These tests pin:

  (1) IV solve round-trip: price a BS option at a known vol → solve back within 1e-4.
  (2) greek parity: bs_greeks_vec == scalar engine/greeks.bs_greeks (delta,gamma,vanna,charm).
  (3) put-call parity delta identity: call_delta − put_delta == e^{−qT}.
  (4) gamma symmetry: call gamma == put gamma.
  (5) DEALER-SIGN + exposure parity vs engine/gex_engine.compute_gex on a synthetic chain
      (net GEX/VEX/CEX agree — the intraday map can never drift from the EOD map).
  (6) put-call-parity spot recovery from the tape.
  (7) coverage honesty: strikes without a quoted+OI'd contract contribute 0, coverage < 1.
  (8) degenerate-input guards: sub-penny mids, at/below-intrinsic mids, bad S/K/T → NaN/skip.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from engine.greeks import bs_greeks as scalar_bs
from engine.gex_engine import DEFAULTS as GEX_DEFAULTS, compute_gex
from engine.intraday_greeks import (
    CONTRACT_MULTIPLIER,
    DEFAULT_Q,
    DEFAULT_R,
    PCT_MOVE,
    bs_greeks_vec,
    bs_price,
    compute_greek_grids,
    implied_vol_vec,
    parity_spot,
)

S0 = 600.0
R = DEFAULT_R
Q = DEFAULT_Q


# ── (1) IV solve round-trip ──────────────────────────────────────────────────────────

def test_iv_roundtrip_recovers_known_vol():
    # Strikes/tenors chosen so every contract carries real extrinsic value at these vols
    # (a deep-OTM short-tenor option can be worth < 1¢ — correctly guarded, see the
    # guard test below; here we assert the SOLVABLE ones round-trip tightly).
    K = np.array([580.0, 590.0, 600.0, 610.0, 620.0])
    T = np.array([0.05, 0.08, 0.10, 0.25, 0.5])
    sig = np.array([0.18, 0.20, 0.22, 0.28, 0.35])
    for is_call in (True, False):
        isc = np.full(K.shape, is_call)
        px = bs_price(S0, K, T, sig, isc, R, Q)
        iv = implied_vol_vec(px, S0, K, T, isc, R, Q)
        assert np.all(np.isfinite(iv)), f"unsolved IVs for is_call={is_call}: {iv}"
        assert np.max(np.abs(iv - sig)) < 1e-4, f"IV round-trip error too large: {iv - sig}"


def test_iv_roundtrip_deep_itm_otm_and_short_tenor():
    # Deep ITM / OTM and near-0DTE — the numerically nasty corners.
    K = np.array([500.0, 700.0, 599.0, 601.0])
    T = np.array([1.0 / 365.0, 1.0 / 365.0, 4.0 / 24.0 / 365.0, 4.0 / 24.0 / 365.0])
    sig = np.array([0.30, 0.30, 0.25, 0.25])
    isc = np.array([True, True, True, False])
    px = bs_price(S0, K, T, sig, isc, R, Q)
    iv = implied_vol_vec(px, S0, K, T, isc, R, Q)
    # Every one that priced above intrinsic + guard should solve back accurately.
    solved = np.isfinite(iv)
    assert solved.any()
    assert np.max(np.abs(iv[solved] - sig[solved])) < 1e-3


# ── (2) greek parity vs the scalar FD-verified engine/greeks.bs_greeks ────────────────

def test_greek_parity_vs_scalar_engine():
    K = np.array([580.0, 600.0, 620.0])
    T = np.array([0.02, 0.10, 0.30])
    sig = np.array([0.18, 0.22, 0.30])
    for is_call in (True, False):
        isc = np.full(K.shape, is_call)
        dv, gv, vv, cv = bs_greeks_vec(S0, K, T, sig, isc, R, Q)
        for i in range(len(K)):
            sd, sg, sv, sc = scalar_bs(S0, float(K[i]), float(T[i]), float(sig[i]),
                                       is_call, R, Q)
            assert abs(dv[i] - sd) < 1e-12, f"delta mismatch @ {K[i]}"
            assert abs(gv[i] - sg) < 1e-12, f"gamma mismatch @ {K[i]}"
            assert abs(vv[i] - sv) < 1e-12, f"vanna mismatch @ {K[i]}"
            assert abs(cv[i] - sc) < 1e-12, f"charm mismatch @ {K[i]}"


def test_greeks_nan_on_degenerate_inputs():
    K = np.array([600.0, 0.0, 600.0, 600.0])
    T = np.array([0.1, 0.1, -0.1, 0.1])
    sig = np.array([0.2, 0.2, 0.2, 0.0])
    isc = np.array([True, True, True, True])
    dv, gv, vv, cv = bs_greeks_vec(S0, K, T, sig, isc, R, Q)
    # index 0 is valid; 1 (K=0), 2 (T<0), 3 (sigma=0) are degenerate → NaN.
    assert np.isfinite(dv[0]) and np.isfinite(gv[0])
    assert np.isnan(gv[1]) and np.isnan(gv[2]) and np.isnan(gv[3])


# ── (3) put-call parity delta identity ───────────────────────────────────────────────

def test_put_call_parity_delta_identity():
    K = np.array([580.0, 600.0, 620.0])
    T = np.array([0.05, 0.05, 0.05])
    sig = np.array([0.2, 0.2, 0.2])
    dc, *_ = bs_greeks_vec(S0, K, T, sig, np.full(3, True), R, Q)
    dp, *_ = bs_greeks_vec(S0, K, T, sig, np.full(3, False), R, Q)
    # call_delta - put_delta == e^{-qT} exactly (dividend-adjusted parity).
    expected = np.exp(-Q * T)
    assert np.max(np.abs((dc - dp) - expected)) < 1e-12


# ── (4) gamma symmetry ───────────────────────────────────────────────────────────────

def test_gamma_symmetry_call_equals_put():
    K = np.array([585.0, 600.0, 615.0])
    T = np.array([0.02, 0.10, 0.30])
    sig = np.array([0.18, 0.22, 0.28])
    _, gc, vc, _ = bs_greeks_vec(S0, K, T, sig, np.full(3, True), R, Q)
    _, gp, vp, _ = bs_greeks_vec(S0, K, T, sig, np.full(3, False), R, Q)
    assert np.max(np.abs(gc - gp)) < 1e-15   # gamma call==put
    assert np.max(np.abs(vc - vp)) < 1e-15   # vanna call==put too


# ── (5) DEALER-SIGN + exposure parity vs engine/gex_engine.compute_gex ────────────────

def _synthetic_chain_and_contracts(iv=0.22, T=14 / 365.0):
    """One expiry, 8 strikes, call+put, KNOWN iv, CLEANLY separated OI (calls dominant
    above spot, puts dominant below — so the dealer sign is unambiguous per strike).
    Returns (eod_chain_df, intraday_contracts) priced consistently at the same iv."""
    strikes = [585.0, 590.0, 595.0, 600.0, 605.0, 610.0, 615.0, 620.0]
    rows, contracts = [], []
    for K in strikes:
        for right, isc in (("C", True), ("P", False)):
            if isc:
                oi = 500.0 + max(0.0, K - S0) * 80.0   # calls: light below spot, heavy above
            else:
                oi = 500.0 + max(0.0, S0 - K) * 80.0   # puts: light above spot, heavy below
            rows.append({"K": K, "T": T, "iv": iv, "oi": oi, "is_call": isc,
                         "expiry": pd.Timestamp("2026-07-20")})
            mid = float(bs_price(S0, np.array([K]), np.array([T]), np.array([iv]),
                                 np.array([isc]), R, Q)[0])
            contracts.append({"exp_years": T, "strike": K, "right": right,
                              "mid": mid, "oi": oi})
    return pd.DataFrame(rows), contracts


def _eod_signed_gex_by_strike(chain, spot, r=R, q=Q):
    """Per-strike signed dollar-gamma computed the EOD way (sign·gamma·oi·mult·S²·pm,
    summed over call+put at each strike) — the ground truth the intraday `gex` must match.
    Uses engine/greeks.bs_greeks directly (the same call compute_gex makes)."""
    out: dict[float, float] = {}
    for row in chain.itertuples(index=False):
        _, gamma, _, _ = scalar_bs(spot, float(row.K), float(row.T), float(row.iv),
                                   bool(row.is_call), r, q)
        sign = 1.0 if row.is_call else -1.0
        out[float(row.K)] = out.get(float(row.K), 0.0) + \
            sign * gamma * float(row.oi) * CONTRACT_MULTIPLIER * spot * spot * PCT_MOVE
    return out


def test_exposure_parity_with_eod_compute_gex():
    chain, contracts = _synthetic_chain_and_contracts()
    cfg = dict(GEX_DEFAULTS)
    cfg.update(r=R, q=Q, contract_multiplier=CONTRACT_MULTIPLIER, pct_move=PCT_MOVE,
               strike_window_pct=0.25, min_strikes=6)
    eod = compute_gex(chain, S0, cfg, symbol="SPY")

    gg = compute_greek_grids(contracts, spot=S0, r=R, q=Q)
    intraday_gex_bn = sum(gg.gex) / 1e9
    intraday_vex = sum(gg.vex)
    intraday_cex = sum(gg.cex)

    # Net GEX (bn) agrees to ~1e-8 — both engines use bs_greeks conventions + the SAME
    # sign·gamma·oi·mult·S²·pm formula. This is the anti-drift guarantee.
    assert abs(eod["net_gex_bn"] - intraday_gex_bn) < 1e-6
    # VEX / CEX agree to a small relative tolerance (the gap is only the IV-solve residual).
    assert abs(eod["net_vex"] - intraday_vex) < max(1.0, abs(eod["net_vex"]) * 1e-6)
    assert abs(eod["net_cex"] - intraday_cex) < max(1.0, abs(eod["net_cex"]) * 1e-6)


def test_dealer_sign_matches_eod_per_strike():
    """The intraday per-strike signed dollar-gamma must equal the EOD convention EXACTLY
    (sign·gamma·oi·mult·S²·pm summed per strike) — the anti-drift guarantee, per strike."""
    chain, contracts = _synthetic_chain_and_contracts()
    gg = compute_greek_grids(contracts, spot=S0, r=R, q=Q)
    eod = _eod_signed_gex_by_strike(chain, S0)
    intraday = dict(zip(gg.strikes, gg.gex))
    for k in eod:
        assert abs(eod[k] - intraday.get(k, 0.0)) < max(1.0, abs(eod[k]) * 1e-6), \
            f"per-strike gex drift at {k}: eod={eod[k]} intraday={intraday.get(k)}"
    # With cleanly call-dominant OI above spot and put-dominant below, the signed net
    # gamma is +above / −below (the convention compute_gex uses to place the walls).
    for k, g in intraday.items():
        if k > S0 + 2:
            assert g >= 0, f"expected +net gamma above spot at {k}, got {g}"
        if k < S0 - 2:
            assert g <= 0, f"expected -net gamma below spot at {k}, got {g}"
    # Walls land on the convention-correct sides.
    assert gg.call_wall is not None and gg.call_wall > S0
    assert gg.put_wall is not None and gg.put_wall < S0


def test_walls_and_flip_definitions():
    chain, contracts = _synthetic_chain_and_contracts()
    gg = compute_greek_grids(contracts, spot=S0, r=R, q=Q)
    # call_wall = strike with the largest POSITIVE net gamma above spot.
    above = [(k, g) for k, g in zip(gg.strikes, gg.gex) if k > S0 and g > 0]
    assert gg.call_wall == max(above, key=lambda kg: kg[1])[0]
    # put_wall = strike with the largest |NEGATIVE| net gamma below spot.
    below = [(k, g) for k, g in zip(gg.strikes, gg.gex) if k < S0 and g < 0]
    assert gg.put_wall == min(below, key=lambda kg: kg[1])[0]
    # flip lies between the innermost sign change (or is None if no crossing).
    if gg.flip is not None:
        assert min(gg.strikes) <= gg.flip <= max(gg.strikes)


# ── (6) put-call-parity spot recovery ────────────────────────────────────────────────

def test_parity_spot_recovers_true_spot():
    contracts = []
    T = 0.02
    for K in [590.0, 595.0, 600.0, 605.0, 610.0]:
        for right, isc in (("C", True), ("P", False)):
            mid = float(bs_price(S0, np.array([K]), np.array([T]), np.array([0.2]),
                                 np.array([isc]), R, Q)[0])
            contracts.append({"exp_years": T, "strike": K, "right": right, "mid": mid})
    ps = parity_spot(contracts, R, Q)
    assert ps is not None
    assert abs(ps - S0) < 0.5


def test_parity_spot_none_when_no_paired_strike():
    # Only calls, no puts → parity cannot resolve.
    contracts = [{"exp_years": 0.02, "strike": 600.0, "right": "C", "mid": 5.0}]
    assert parity_spot(contracts, R, Q) is None


def test_grid_uses_parity_spot_then_prev_close_fallback():
    # No explicit spot, paired mids present → parity spot, source='parity'.
    contracts = []
    T = 0.02
    for K in [595.0, 600.0, 605.0]:
        for right, isc in (("C", True), ("P", False)):
            mid = float(bs_price(S0, np.array([K]), np.array([T]), np.array([0.2]),
                                 np.array([isc]), R, Q)[0])
            contracts.append({"exp_years": T, "strike": K, "right": right,
                              "mid": mid, "oi": 1000.0})
    gg = compute_greek_grids(contracts, spot=None)
    assert gg.spot_source == "parity"
    assert abs(gg.spot - S0) < 0.5

    # Only calls (no parity) but a prev_close fallback → source='prev_close'.
    calls_only = [c for c in contracts if c["right"] == "C"]
    gg2 = compute_greek_grids(calls_only, spot=None, spot_fallback=601.0)
    assert gg2.spot_source == "prev_close"
    assert gg2.spot == 601.0

    # No spot at all → empty grids, source='none' (no fabrication).
    gg3 = compute_greek_grids(calls_only, spot=None, spot_fallback=None)
    assert gg3.spot_source == "none"
    assert gg3.strikes == []


# ── (7) coverage honesty ─────────────────────────────────────────────────────────────

def test_coverage_honest_when_some_strikes_lack_oi():
    T = 0.02
    contracts = []
    strikes = [595.0, 600.0, 605.0, 610.0]
    for K in strikes:
        for right, isc in (("C", True), ("P", False)):
            mid = float(bs_price(S0, np.array([K]), np.array([T]), np.array([0.2]),
                                 np.array([isc]), R, Q)[0])
            # Only strikes 595/600 get OI; 605/610 have oi=0 → contribute nothing.
            oi = 1000.0 if K in (595.0, 600.0) else 0.0
            contracts.append({"exp_years": T, "strike": K, "right": right,
                              "mid": mid, "oi": oi})
    gg = compute_greek_grids(contracts, spot=S0, union_strikes=strikes)
    # Grid spans all 4 strikes (the union), but only 2 received real contributions.
    assert set(gg.strikes) == set(strikes)
    assert 0.0 < gg.coverage < 1.0
    # The zero-OI strikes read exactly 0 in every greek (honest, not fabricated).
    for k, g in zip(gg.strikes, gg.gex):
        if k in (605.0, 610.0):
            assert g == 0.0


def test_full_coverage_when_all_have_oi():
    T = 0.02
    contracts = []
    strikes = [595.0, 600.0, 605.0]
    for K in strikes:
        for right, isc in (("C", True), ("P", False)):
            mid = float(bs_price(S0, np.array([K]), np.array([T]), np.array([0.2]),
                                 np.array([isc]), R, Q)[0])
            contracts.append({"exp_years": T, "strike": K, "right": right,
                              "mid": mid, "oi": 1500.0})
    gg = compute_greek_grids(contracts, spot=S0, union_strikes=strikes)
    assert gg.coverage == 1.0
    assert gg.n_contracts == 6


# ── (8) degenerate-input guards ──────────────────────────────────────────────────────

def test_iv_guards_subpenny_and_intrinsic_mids():
    # A sub-penny mid, and a mid AT intrinsic value (no time value) → NaN (unsolvable).
    K = np.array([600.0, 500.0])
    T = np.array([0.02, 0.02])
    isc = np.array([True, True])
    intrinsic_only = float(max(S0 - 500.0, 0.0))   # = 100.0, pure intrinsic for the 500 call
    mids = np.array([0.005, intrinsic_only])       # sub-penny; at-intrinsic
    iv = implied_vol_vec(mids, S0, K, T, isc, R, Q)
    assert np.isnan(iv[0])   # sub-penny guarded
    assert np.isnan(iv[1])   # at-intrinsic → no extrinsic value → IV undefined


def test_compute_grids_empty_on_no_usable_contracts():
    # All contracts have oi=0 → nothing contributes → empty grids, coverage 0.
    contracts = [{"exp_years": 0.02, "strike": 600.0, "right": "C", "mid": 5.0, "oi": 0.0}]
    gg = compute_greek_grids(contracts, spot=S0)
    assert gg.strikes == []
    assert gg.coverage == 0.0
    assert gg.n_contracts == 0


# ── (9) the Newton step never divides by a zero vega (live M1 RuntimeWarning, 2026-07-29) ──
# `engine/intraday_greeks.py` raised `RuntimeWarning: divide by zero encountered in divide`
# on the M1 poller during RTH. Cause: the Newton step is written
# `np.where(step_ok, sigma - diff / vega, sigma)`, and np.where evaluates BOTH branches — so
# `diff / vega` runs even for elements the step_ok mask discards. vega is EXACTLY 0.0
# whenever _pdf(d1) underflows (|d1| > ~38.6 → exp(-d1²/2) == 0.0 in float64), which a
# late-day 0DTE wing reaches easily: T floored at MIN_T (1 minute) gives σ·√T ≈ 4e-4, so a
# strike ~2% OTM already has |d1| ≈ 49. The fix masks the DENOMINATOR; it must not change
# any solved value.

def _late_day_0dte_wing():
    """A 2¢ SPY-like wing, ~2% OTM, one minute from expiry — the live warning's input."""
    from engine.intraday_greeks import MIN_T

    S = 640.0
    K = np.array([653.0])
    T = np.array([MIN_T])
    mid = np.array([0.02])
    isc = np.array([True])
    return mid, S, K, T, isc


def test_zero_vega_underflow_is_the_documented_case():
    """Pin the mechanism, so a future refactor can't silently break the reasoning."""
    from engine.intraday_greeks import IV_SEED, _d1_d2, _pdf, bs_vega

    _, S, K, T, _ = _late_day_0dte_wing()
    sig = np.array([IV_SEED])
    d1, _, _ = _d1_d2(S, K, T, sig)
    assert abs(float(d1[0])) > 38.6           # past the float64 underflow threshold
    assert float(_pdf(d1)[0]) == 0.0          # exactly zero, not merely small
    assert float(bs_vega(S, K, T, sig)[0]) == 0.0


def test_newton_step_emits_no_divide_warning_on_zero_vega():
    import warnings

    mid, S, K, T, isc = _late_day_0dte_wing()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        iv = implied_vol_vec(mid, S, K, T, isc, R, Q)
    divides = [w for w in caught
               if issubclass(w.category, RuntimeWarning) and "divide" in str(w.message)]
    assert not divides, f"zero-vega Newton step still warns: {[str(w.message) for w in divides]}"
    # Unchanged semantics: this quote is genuinely unpriceable → honest NaN, never a fake IV.
    assert np.isnan(iv[0])


def test_zero_vega_element_does_not_poison_its_neighbours():
    """A mixed batch: the pathological wing must not disturb the solvable contracts."""
    import warnings

    from engine.intraday_greeks import MIN_T

    S = 640.0
    K = np.array([653.0, 640.0, 630.0, 650.0])
    T = np.array([MIN_T, 30 / 365.0, 30 / 365.0, 7 / 365.0])
    sig = np.array([0.0, 0.18, 0.24, 0.31])           # element 0 is the unpriceable wing
    isc = np.array([True, True, False, True])
    mid = bs_price(S, K, T, np.where(sig > 0, sig, 0.2), isc, R, Q).copy()
    mid[0] = 0.02
    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)  # any RuntimeWarning fails the test
        iv = implied_vol_vec(mid, S, K, T, isc, R, Q)
    assert np.isnan(iv[0])
    assert np.max(np.abs(iv[1:] - sig[1:])) < 1e-4, f"neighbour IVs drifted: {iv}"


def test_iv_solve_is_unchanged_by_the_guard():
    """Guard parity: masking the denominator changes no solved value anywhere on the grid."""
    K = np.array([560.0, 580.0, 600.0, 620.0, 640.0])
    T = np.array([0.01, 0.05, 0.10, 0.30, 0.75])
    sig = np.array([0.35, 0.24, 0.20, 0.26, 0.33])
    for isc_v in (True, False):
        isc = np.full(K.shape, isc_v)
        px = bs_price(S0, K, T, sig, isc, R, Q)
        iv = implied_vol_vec(px, S0, K, T, isc, R, Q)
        assert np.all(np.isfinite(iv))
        assert np.max(np.abs(iv - sig)) < 1e-4


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
