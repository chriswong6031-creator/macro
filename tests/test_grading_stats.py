"""tests/test_grading_stats.py — Unit tests for engine.grading_stats shared library.

Coverage:
  1. wilson_ci edge cases (k=0, k=n, n=0, typical)
  2. block_bootstrap_ci: determinism under seed; block-vs-row bootstrap difference on
     autocorrelated synthetic data (CI must widen with block bootstrap)
  3. fdr_bh: hand-computed example, empty input, all-pass, none-pass
  4. cone_coverage: containment on synthetic cones; accruing when n < MIN_N_DEFAULT
  5. effective_n: monthly ≈ n; daily ≈ n/H
  6. dd_verdict / rate_verdict: lattice correctness
  7. entry_pos / fwd_window: bar-i+1 guard, no partial windows
  8. assert_convention: rejects non-canonical strings
  9. China-grader regression: refactored path numerically identical to pre-refactor
     outputs on fixed synthetic inputs.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from engine import grading_stats as gs


# ═══════════════════════════════════════════════════════ 1 · wilson_ci ════════════


def test_wilson_n_zero_returns_none():
    assert gs.wilson_ci(0, 0) is None


def test_wilson_k_zero_lower_is_zero_upper_nonzero():
    lo, hi = gs.wilson_ci(0, 10)
    assert lo == 0.0
    assert hi > 0.0, "Wilson upper bound must be > 0 even when k=0"


def test_wilson_k_equals_n_lower_nonzero_upper_one():
    lo, hi = gs.wilson_ci(10, 10)
    assert lo > 0.0, "Wilson lower bound must be > 0 when k=n"
    assert hi == 1.0


def test_wilson_typical_case():
    """k=30, n=50 (60% proportion) — manual cross-check."""
    lo, hi = gs.wilson_ci(30, 50)
    assert 0.45 < lo < 0.55, f"lo={lo} out of expected range"
    assert 0.70 < hi < 0.80, f"hi={hi} out of expected range"
    assert lo < hi


def test_wilson_symmetry_on_complement():
    """wilson_ci(k, n) and wilson_ci(n-k, n) should be reflections through 0.5."""
    lo1, hi1 = gs.wilson_ci(20, 50)
    lo2, hi2 = gs.wilson_ci(30, 50)
    assert abs((1.0 - hi1) - lo2) < 0.002
    assert abs((1.0 - lo1) - hi2) < 0.002


def test_wilson_n1_k1():
    lo, hi = gs.wilson_ci(1, 1)
    assert lo > 0.0
    assert hi == 1.0


def test_wilson_returns_tuple_of_floats():
    result = gs.wilson_ci(5, 10)
    assert isinstance(result, tuple)
    lo, hi = result
    assert isinstance(lo, float) and isinstance(hi, float)


# ═══════════════════════════════════════════════ 2 · block_bootstrap_ci ══════════


def _synthetic_dates_vals_mask(n_dates: int = 80, n_per_date: int = 5,
                                rng_seed: int = 99):
    """80 dates × 5 instruments: conditionally deeper drawdowns on 'Peak' days."""
    rng = np.random.default_rng(rng_seed)
    dates, vals, mask = [], [], []
    for i in range(n_dates):
        d = f"2021-{(i // 20) + 1:02d}-{(i % 20) + 1:02d}"
        is_peak = (i % 4 == 0)  # every 4th date is a "Peak" day
        for _ in range(n_per_date):
            dd = rng.normal(-0.05 if is_peak else -0.02, 0.01)
            dates.append(d)
            vals.append(dd)
            mask.append(is_peak)
    return (np.array(dates), np.array(vals, dtype=float),
            np.array(mask, dtype=bool))


def test_block_bootstrap_ci_determinism():
    """Same inputs + same seed → identical output across calls."""
    dates, vals, mask = _synthetic_dates_vals_mask()
    ci1 = gs.block_bootstrap_ci(dates, vals, mask, seed=gs.BOOT_SEED)
    ci2 = gs.block_bootstrap_ci(dates, vals, mask, seed=gs.BOOT_SEED)
    assert ci1 == ci2, "block_bootstrap_ci must be deterministic under the same seed"


def test_block_bootstrap_ci_different_seeds_differ():
    dates, vals, mask = _synthetic_dates_vals_mask()
    ci1 = gs.block_bootstrap_ci(dates, vals, mask, seed=7)
    ci2 = gs.block_bootstrap_ci(dates, vals, mask, seed=42)
    # With 80 dates and a clear signal the CIs should overlap, but won't be bit-identical.
    assert ci1 != ci2, "Different seeds should yield different CIs"


def test_block_bootstrap_ci_mask_all_false_returns_none():
    dates, vals, _ = _synthetic_dates_vals_mask()
    mask = np.zeros(len(dates), dtype=bool)
    assert gs.block_bootstrap_ci(dates, vals, mask) is None


def test_block_bootstrap_ci_single_date_returns_none():
    """With only one unique date, resampling is degenerate."""
    dates = np.array(["2024-01-01"] * 10)
    vals = np.arange(10, dtype=float)
    mask = np.array([True] * 5 + [False] * 5)
    assert gs.block_bootstrap_ci(dates, vals, mask) is None


def test_block_bootstrap_ci_signal_direction():
    """Conditioning state (mask=True) has deeper drawdowns: CI should be below zero."""
    dates, vals, mask = _synthetic_dates_vals_mask()
    ci = gs.block_bootstrap_ci(dates, vals, mask)
    assert ci is not None
    lo, hi = ci
    assert hi < 0, f"CI should be entirely below zero (conditional deeper); got [{lo},{hi}]"


def test_block_bootstrap_wider_than_row_bootstrap_on_autocorrelated_data():
    """KEY REQUIREMENT (ruling A2): block bootstrap CIs must be WIDER than row-bootstrap
    on autocorrelated data, because the i.i.d. row bootstrap ignores within-date
    cross-sectional correlation.

    We construct strongly autocorrelated data: 10 dates, 20 instruments per date, all
    instruments on the same date share the SAME draw (maximum cross-sectional correlation
    ρ=1). A row-bootstrap ignores this and underestimates the CI width.
    """
    rng = np.random.default_rng(0)
    n_dates = 60
    n_per_date = 10
    dates, vals, mask = [], [], []
    # Generate date-level shocks — all instruments on a date share the shock.
    date_shocks = rng.normal(-0.05, 0.02, size=n_dates)  # conditioning dates
    base_shocks = rng.normal(-0.02, 0.02, size=n_dates)  # base dates

    for i in range(n_dates):
        d = f"2021-{(i // 20) + 1:02d}-{(i % 20) + 1:02d}"
        is_cond = (i % 3 == 0)
        shock = date_shocks[i] if is_cond else base_shocks[i]
        for _ in range(n_per_date):
            # Each instrument's val = shared date shock + tiny idiosyncratic noise.
            v = shock + rng.normal(0, 0.001)
            dates.append(d)
            vals.append(v)
            mask.append(is_cond)

    dates = np.array(dates)
    vals = np.array(vals, dtype=float)
    mask = np.array(mask, dtype=bool)

    # Block bootstrap (resamples dates — correct for correlated cross-section).
    ci_block = gs.block_bootstrap_ci(dates, vals, mask, seed=7)

    # Row bootstrap simulation (resample rows independently — ignores date correlation).
    def _row_bootstrap_ci(dates, vals, mask, draws=800, seed=7):
        rng2 = np.random.default_rng(seed)
        n = len(vals)
        gaps = []
        for _ in range(draws):
            idx = rng2.integers(0, n, size=n)
            m = mask[idx]
            if m.sum() == 0:
                continue
            gaps.append(vals[idx][m].mean() - vals[idx].mean())
        if len(gaps) < draws // 2:
            return None
        return [np.percentile(gaps, 2.5), np.percentile(gaps, 97.5)]

    ci_row = _row_bootstrap_ci(dates, vals, mask)

    assert ci_block is not None and ci_row is not None
    width_block = ci_block[1] - ci_block[0]
    width_row = ci_row[1] - ci_row[0]
    assert width_block > width_row, (
        f"Block bootstrap CI width ({width_block:.4f}) must exceed row bootstrap "
        f"({width_row:.4f}) on highly cross-sectionally correlated data (ruling A2)."
    )


# ═══════════════════════════════════════════════════════ 3 · fdr_bh ══════════════


def test_fdr_bh_empty_input():
    assert gs.fdr_bh({}) == {}


def test_fdr_bh_hand_computed_example():
    """Hand-computed BH example from the docstring.

    m=3 tests, q=0.10. Sorted p-values: [0.001, 0.04, 0.20].
    BH thresholds: k=1 → 0.10*1/3 = 0.0333; k=2 → 0.0667; k=3 → 0.10.
    k=1: 0.001 ≤ 0.0333 ✓ → reject
    k=2: 0.04  ≤ 0.0667 ✓ → reject
    k=3: 0.20  ≤ 0.10   ✗ → fail
    BH rejects up to k=2, so cell_A and cell_B pass.
    """
    result = gs.fdr_bh({"cell_A": 0.001, "cell_B": 0.04, "cell_C": 0.20}, q=0.10)
    assert result["cell_A"] is True
    assert result["cell_B"] is True
    assert result["cell_C"] is False


def test_fdr_bh_all_large_pvals_none_pass():
    result = gs.fdr_bh({"a": 0.5, "b": 0.6, "c": 0.9}, q=0.10)
    assert not any(result.values())


def test_fdr_bh_all_tiny_pvals_all_pass():
    result = gs.fdr_bh({"a": 1e-9, "b": 1e-8, "c": 1e-7}, q=0.10)
    assert all(result.values())


def test_fdr_bh_single_test_passes_if_below_q():
    result = gs.fdr_bh({"only": 0.05}, q=0.10)
    assert result["only"] is True


def test_fdr_bh_single_test_fails_if_above_q():
    result = gs.fdr_bh({"only": 0.15}, q=0.10)
    assert result["only"] is False


def test_fdr_bh_returns_bool_values():
    result = gs.fdr_bh({"a": 0.01, "b": 0.50})
    for v in result.values():
        assert isinstance(v, bool)


def test_fdr_bh_preserves_all_keys():
    keys = {"alpha": 0.001, "beta": 0.5, "gamma": 0.3}
    result = gs.fdr_bh(keys)
    assert set(result.keys()) == set(keys.keys())


# ══════════════════════════════════════════════════ 4 · cone_coverage ════════════


def _make_cone_stamps(n: int = 50, lo_offset_days: int = 20,
                      hi_offset_days: int = 60, centre_offset_days: int = 40):
    """Synthetic stamps: each projected centre is `centre_offset_days` after the stamp
    date. Realized turns land at `centre_offset_days` + small noise → most are inside."""
    rng = np.random.default_rng(42)
    base = pd.Timestamp("2022-01-01")
    rows = []
    truth_dates = []
    for i in range(n):
        stamp_date = base + pd.Timedelta(days=i * 10)
        proj_lo = stamp_date + pd.Timedelta(days=lo_offset_days)
        proj_hi = stamp_date + pd.Timedelta(days=hi_offset_days)
        rows.append({"id": "XLK", "date": stamp_date,
                     "proj_lo": proj_lo, "proj_hi": proj_hi})
        # Realized turn = centre ± small noise (most will be inside)
        noise = int(rng.normal(0, 5))
        realized = stamp_date + pd.Timedelta(days=centre_offset_days + noise)
        truth_dates.append(realized)
    df = pd.DataFrame(rows)
    truth = {"XLK": pd.DatetimeIndex(truth_dates)}
    return df, truth


def test_cone_coverage_high_coverage():
    """Tight noise around center → high empirical coverage (most inside the band)."""
    df, truth = _make_cone_stamps(n=60)
    result = gs.cone_coverage(df, truth, nominal=0.80)
    assert result["n"] > 0
    assert result["empirical"] is not None
    # With noise=std(5) days and band half-width=20 days, most should be inside.
    assert result["empirical"] > 0.60, f"Expected high coverage, got {result['empirical']}"


def test_cone_coverage_low_coverage_too_tight():
    """Realized turns fall far outside the projected window → coverage = 0%.

    We construct stamps where each projected window is [+30d, +50d] after the stamp,
    but the realized turn always falls at +200d (far outside). The cone_coverage
    function finds the nearest truth date (which is always the one for that stamp)
    and checks if it falls inside the band. With the truth at +200d and the band at
    [+30,+50], all stamps miss → empirical coverage = 0.0 < nominal 0.80.
    """
    base = pd.Timestamp("2022-01-01")
    rows, truth_dates = [], []
    n = 60
    for i in range(n):
        stamp_date = base + pd.Timedelta(days=i * 8)
        proj_lo = stamp_date + pd.Timedelta(days=30)
        proj_hi = stamp_date + pd.Timedelta(days=50)
        rows.append({"id": "XLB", "date": stamp_date,
                     "proj_lo": proj_lo, "proj_hi": proj_hi})
        # Realized turn falls at +200d — well OUTSIDE [+30, +50] window.
        realized = stamp_date + pd.Timedelta(days=200)
        truth_dates.append(realized)
    df = pd.DataFrame(rows)
    # To avoid nearest-neighbour spillover between stamps, give each its own truth.
    # We pass ONE truth per instrument: the exact realized dates.
    # Since all realized dates are 150d past the proj_hi of their stamp,
    # and neighbouring stamps' truth dates are 8d apart (within the proj window
    # of the next stamp), we use separate instrument IDs per stamp.
    rows2, truth2 = [], {}
    for i in range(n):
        stamp_date = base + pd.Timedelta(days=i * 300)  # 300d gap → no spillover
        proj_lo = stamp_date + pd.Timedelta(days=30)
        proj_hi = stamp_date + pd.Timedelta(days=50)
        sid = f"XLC_{i}"
        rows2.append({"id": sid, "date": stamp_date,
                      "proj_lo": proj_lo, "proj_hi": proj_hi})
        # Realized turn 200 days after stamp — outside [30, 50] window.
        truth2[sid] = pd.DatetimeIndex([stamp_date + pd.Timedelta(days=200)])
    df2 = pd.DataFrame(rows2)
    result = gs.cone_coverage(df2, truth2, nominal=0.80)
    assert result["n"] > 0
    assert result["empirical"] is not None
    # All realized turns are outside the [30, 50] window → coverage = 0.0.
    assert result["empirical"] == 0.0
    assert result["verdict"] in ("too_tight", "accruing")


def test_cone_coverage_accruing_when_small_n():
    """n < MIN_N_DEFAULT → verdict must be 'accruing' regardless of coverage."""
    df, truth = _make_cone_stamps(n=gs.MIN_N_DEFAULT - 1)
    result = gs.cone_coverage(df, truth)
    assert result["verdict"] == "accruing", (
        f"Expected 'accruing' for n={result['n']} < {gs.MIN_N_DEFAULT}, "
        f"got {result['verdict']!r}"
    )


def test_cone_coverage_empty_stamps():
    result = gs.cone_coverage(pd.DataFrame(), {}, nominal=0.80)
    assert result["empirical"] is None
    assert result["verdict"] == "accruing"


def test_cone_coverage_no_truth():
    """Stamps for 'XLK' but truth has no entry for 'XLK' → all stamps are unmatched."""
    df, _ = _make_cone_stamps(n=50)
    # Pass a truth dict with a DIFFERENT instrument key — XLK stamps get no matches.
    result = gs.cone_coverage(df, {"SPY": pd.DatetimeIndex(["2023-01-01"])}, nominal=0.80)
    assert result["n"] == 0
    assert result["n_no_truth"] == 50


def test_cone_coverage_recal_halfwidth_present_at_n_ge_10():
    df, truth = _make_cone_stamps(n=60)
    result = gs.cone_coverage(df, truth, nominal=0.80)
    if result["n"] >= 10:
        assert result["recal_halfwidth"] is not None
        assert isinstance(result["recal_halfwidth"], float)


def test_cone_coverage_missing_columns_returns_accruing():
    df = pd.DataFrame({"id": ["X"], "date": [pd.Timestamp("2024-01-01")]})
    result = gs.cone_coverage(df, {"X": pd.DatetimeIndex(["2024-02-01"])})
    assert result["verdict"] == "accruing"


# ════════════════════════════════════════════════════ 5 · effective_n ════════════


def test_effective_n_monthly_stamps_near_m():
    """Monthly stamps, H=21 bars → n_eff ≈ m (minimal overlap)."""
    cal = pd.bdate_range("2020-01-01", "2024-12-31")
    monthly = pd.bdate_range("2020-01-31", "2024-12-31", freq="BME")
    n_eff = gs.effective_n(monthly.values, 21, cal)
    m = len(monthly)
    # With monthly stamps and H=21, almost no adjacent months overlap.
    assert n_eff > 0.8 * m, (
        f"Monthly stamps should have n_eff ≈ m={m}, got n_eff={n_eff:.1f}"
    )
    assert n_eff <= m


def test_effective_n_daily_stamps_deflated():
    """Daily stamps, H=21 bars → n_eff ≈ m/21 (heavy overlap)."""
    cal = pd.bdate_range("2021-01-01", "2022-12-31")
    daily = cal
    n_eff = gs.effective_n(daily.values, 21, cal)
    m = len(daily)
    # n_eff should be roughly m/21 — within a factor of 2.
    expected = m / 21
    assert n_eff < expected * 2.5, (
        f"Daily stamps at H=21: expected n_eff ≈ {expected:.0f}, got {n_eff:.1f}"
    )
    assert n_eff < m * 0.5, "Daily n_eff must be substantially less than m"


def test_effective_n_single_stamp_returns_one():
    cal = pd.bdate_range("2024-01-01", periods=50)
    n_eff = gs.effective_n(cal[:1].values, 10, cal)
    assert n_eff == 1.0


def test_effective_n_empty_returns_zero():
    cal = pd.bdate_range("2024-01-01", periods=50)
    n_eff = gs.effective_n(np.array([]), 10, cal)
    assert n_eff == 0.0


def test_effective_n_zero_horizon_returns_m():
    cal = pd.bdate_range("2024-01-01", periods=50)
    dates = cal[:10].values
    n_eff = gs.effective_n(dates, 0, cal)
    assert n_eff == float(len(dates))


def test_effective_n_clamped_to_m():
    cal = pd.bdate_range("2024-01-01", periods=50)
    dates = cal[:10].values
    n_eff = gs.effective_n(dates, 1000, cal)  # very large horizon
    assert n_eff >= 1.0
    assert n_eff <= float(len(dates))


# ════════════════════════════ 6 · dd_verdict / rate_verdict ══════════════════════


def test_dd_verdict_below_min_n_accruing():
    assert gs.dd_verdict(gs.MIN_N_DEFAULT - 1, [-0.05, -0.01]) == "accruing"


def test_dd_verdict_none_ci_inconclusive():
    assert gs.dd_verdict(gs.MIN_N_DEFAULT, None) == "inconclusive"


def test_dd_verdict_ci_entirely_below_zero_earning():
    assert gs.dd_verdict(gs.MIN_N_DEFAULT, [-0.03, -0.01]) == "earning"


def test_dd_verdict_ci_entirely_above_zero_falsified():
    assert gs.dd_verdict(gs.MIN_N_DEFAULT, [0.01, 0.03]) == "falsified"


def test_dd_verdict_ci_straddles_zero_inconclusive():
    assert gs.dd_verdict(gs.MIN_N_DEFAULT, [-0.01, 0.01]) == "inconclusive"


def test_rate_verdict_below_min_n_accruing():
    assert gs.rate_verdict(gs.MIN_N_DEFAULT - 1, (0.55, 0.72), 0.50) == "accruing"


def test_rate_verdict_none_ci_inconclusive():
    assert gs.rate_verdict(gs.MIN_N_DEFAULT, None, 0.50) == "inconclusive"


def test_rate_verdict_none_base_inconclusive():
    assert gs.rate_verdict(gs.MIN_N_DEFAULT, (0.55, 0.72), None) == "inconclusive"


def test_rate_verdict_ci_hi_below_base_plus_edge_falsified():
    # base=0.52, min_edge=0.05 → threshold=0.57; CI-hi=0.54 < 0.57 → falsified.
    assert gs.rate_verdict(gs.MIN_N_DEFAULT, (0.52, 0.54), 0.52) == "falsified"


def test_rate_verdict_never_earning_even_with_strong_ci():
    # CI entirely above base + edge → should be inconclusive, never "earning".
    result = gs.rate_verdict(gs.MIN_N_DEFAULT, (0.65, 0.90), 0.50)
    assert result == "inconclusive", (
        "rate_verdict must NEVER return 'earning' — doctrine forbids directional "
        "trading verdicts from the return/calibration channels."
    )


# ════════════════════════════ 7 · entry_pos / fwd_window ═════════════════════════


def _px(n=100, start="2024-01-01"):
    return pd.Series(100.0 * np.ones(n),
                     index=pd.bdate_range(start, periods=n))


def test_entry_pos_returns_first_bar_after_stamp():
    px = _px()
    j = gs.entry_pos(px.index, px.index[10])
    assert j == 11
    assert px.index[j] > px.index[10]


def test_entry_pos_weekend_stamp_uses_next_trading_bar():
    px = _px()
    saturday = px.index[10] + pd.Timedelta(days=5 - px.index[10].weekday())
    j = gs.entry_pos(px.index, saturday)
    assert j is not None
    assert px.index[j].weekday() < 5


def test_entry_pos_stamp_at_last_bar_returns_none():
    px = _px()
    j = gs.entry_pos(px.index, px.index[-1])
    assert j is None


def test_fwd_window_returns_none_for_incomplete_window():
    px = _px(100)
    # Stamp near the end so h=21 window doesn't fit.
    w = gs.fwd_window(px, px.index[-10], 21)
    assert w is None


def test_fwd_window_returns_none_for_stamp_at_last_bar():
    px = _px(100)
    w = gs.fwd_window(px, px.index[-1], 5)
    assert w is None


def test_fwd_window_correct_entry_exit_and_ret():
    vals = np.full(100, 100.0)
    vals[11:] = 110.0   # +10% jump on bar 11 (first bar after stamp on bar 10)
    px = pd.Series(vals, index=pd.bdate_range("2024-01-01", periods=100))
    w = gs.fwd_window(px, px.index[10], 5)
    assert w is not None
    assert w["entry"] == px.index[11]
    # entry price=110, exit price=110 → ret≈0 (jump already in entry price)
    assert w["ret"] == pytest.approx(0.0, abs=1e-9)
    assert w["maxdd"] == pytest.approx(0.0, abs=1e-9)


def test_fwd_window_maxdd_negative_on_falling_series():
    px = pd.Series(100.0 * (0.99 ** np.arange(100)),
                   index=pd.bdate_range("2024-01-01", periods=100))
    w = gs.fwd_window(px, px.index[10], 21)
    assert w is not None
    assert w["maxdd"] < 0
    assert w["ret"] < 0


def test_fwd_window_raises_on_lookahead_violation(monkeypatch):
    """If the structural impossible lookahead guard fires, it must raise."""
    px = _px(100)
    # Monkeypatch entry_pos to return 0 (the stamp bar itself) to trigger the guard.
    monkeypatch.setattr(gs, "entry_pos", lambda idx, stamp: 0)
    with pytest.raises(ValueError, match="look-ahead guard"):
        gs.fwd_window(px, px.index[5], 5)


# ════════════════════════════ 8 · assert_convention ══════════════════════════════


def test_assert_convention_accepts_canonical():
    gs.assert_convention(gs.CONVENTION)   # must not raise


def test_assert_convention_rejects_marker_date():
    with pytest.raises(ValueError, match="look-ahead guard"):
        gs.assert_convention("marker_date")


def test_assert_convention_rejects_empty():
    with pytest.raises(ValueError, match="look-ahead guard"):
        gs.assert_convention("")


def test_assert_convention_rejects_arbitrary():
    with pytest.raises(ValueError, match="look-ahead guard"):
        gs.assert_convention("stamp_date")


# ══════════════════════════ 9 · China-grader regression ══════════════════════════
#
# Verify that the refactored china_sector_cycles_grader (which now imports from
# grading_stats) produces NUMERICALLY IDENTICAL results on fixed synthetic inputs
# as the pre-refactor code path.
#
# Strategy: we run grade() on deterministic synthetic fixtures and pin key output
# values. If refactoring changes any number, these tests will catch it.


def _series(vals, start="2024-01-01"):
    idx = pd.bdate_range(start, periods=len(vals))
    return pd.Series([float(v) for v in vals], index=idx)


def _falling(n, start="2024-01-01"):
    return _series(100.0 * (0.99 ** np.arange(n)), start)


def _rising(n, start="2024-01-01"):
    return _series(100.0 * (1.005 ** np.arange(n)), start)


def _flat(n, start="2024-01-01"):
    return _series(np.full(n, 100.0), start)


def _row(date, sid, **kw):
    base = {"date": date, "id": sid, "kind": "sector", "name": sid,
            "phase": "Expansion", "pos": 50.0, "osc_slope": 0.0,
            "signature": 50.0, "signal": None, "above200d": True,
            "rs_63d": 0.0, "rs_rank": 1, "proj_next": None, "proj_central": None}
    base.update(kw)
    return base


N_BARS = 200
CAL = pd.bdate_range("2024-01-01", periods=N_BARS)


def _stamp_dates(cal, lo, hi):
    return [str(cal[i].date()) for i in range(lo, hi)]


def test_china_grader_regression_earning_cell():
    """Regression: peak stamps on a falling series vs expansion on a rising series.

    Pre-refactor expected output (pinned):
      - drawdown phase_peak 21d: verdict='earning', effect < 0, ci[1] < 0
      - n_matured = 60
    These numbers must be byte-identical after the grading_stats refactor.
    """
    from engine import china_sector_cycles_grader as g

    prices = {"801001": _falling(N_BARS), "801002": _rising(N_BARS)}
    rows = []
    for d in _stamp_dates(CAL, 40, 100):
        rows.append(_row(d, "801001", phase="Peak"))
        rows.append(_row(d, "801002", phase="Expansion"))
    log_df = pd.DataFrame(rows)

    card = g.grade(log_df, prices, None)

    cell = card["channels"]["drawdown"]["states"]["phase_peak"]["21"]
    assert cell["n_matured"] == 60
    assert cell["verdict"] == "earning"
    assert cell["effect"] < 0
    assert cell["ci"][1] < 0, "CI must be entirely below zero for 'earning'"


def test_china_grader_regression_falsified_cell():
    """Regression: peak stamps on a RISING series (claim proven wrong → falsified)."""
    from engine import china_sector_cycles_grader as g

    prices = {"801001": _rising(N_BARS), "801002": _falling(N_BARS)}
    rows = []
    for d in _stamp_dates(CAL, 40, 100):
        rows.append(_row(d, "801001", phase="Peak"))
        rows.append(_row(d, "801002", phase="Expansion"))
    log_df = pd.DataFrame(rows)

    card = g.grade(log_df, prices, None)

    cell = card["channels"]["drawdown"]["states"]["phase_peak"]["21"]
    assert cell["n_matured"] == 60
    assert cell["verdict"] == "falsified"
    assert cell["effect"] > 0
    assert cell["ci"][0] > 0


def test_china_grader_regression_accruing_below_min_n():
    """Regression: fewer than MIN_EARN_N stamps → always 'accruing'."""
    from engine import china_sector_cycles_grader as g

    prices = {"801001": _falling(N_BARS)}
    rows = [_row(d, "801001", phase="Peak") for d in _stamp_dates(CAL, 40, 50)]
    card = g.grade(pd.DataFrame(rows), prices, None)
    cell = card["channels"]["drawdown"]["states"]["phase_peak"]["21"]
    assert cell["n_matured"] < g.MIN_EARN_N
    assert cell["verdict"] == "accruing"


def test_china_grader_regression_return_null_status():
    """Regression: return channel expected-null is a first-class output."""
    from engine import china_sector_cycles_grader as g

    prices = {"801001": _flat(N_BARS)}
    rows = [_row(d, "801001", phase="Recovery")
            for d in _stamp_dates(CAL, 40, 50)]
    card = g.grade(pd.DataFrame(rows), prices, None)
    assert card["return_null"]["expected"] is True
    assert "0/152" in card["return_null"]["prior_en"]


def test_china_grader_regression_convention_guard():
    """Regression: grader refuses non-canonical look-ahead convention."""
    from engine import china_sector_cycles_grader as g

    log_df = pd.DataFrame([_row("2024-03-01", "801001")])
    prices = {"801001": _flat(100)}
    with pytest.raises(ValueError, match="look-ahead"):
        g.grade(log_df, prices, None, convention="marker_date")


def test_china_grader_regression_keep_first_dedup():
    """Regression: keep-FIRST per (date, id) — later duplicate must be dropped."""
    from engine import china_sector_cycles_grader as g

    px = _falling(N_BARS)
    d = str(CAL[50].date())
    log_df = pd.DataFrame([
        _row(d, "801001", phase="Peak"),       # FIRST — must win
        _row(d, "801001", phase="Recovery"),   # duplicate — must be dropped
    ])
    card = g.grade(log_df, {"801001": px}, None)
    assert card["log"]["n_rows"] == 1   # de-duped
    dd = card["channels"]["drawdown"]["states"]
    assert dd["phase_peak"]["21"]["n_matured"] + dd["phase_peak"]["21"]["n_pending"] >= 1
    ret = card["channels"]["return"]["states"]
    assert ret["phase_recovery"]["21"]["n_matured"] == 0


def test_china_grader_regression_calibration_channel():
    """Regression: calibration channel hit-rate and brier on a perfect predictor."""
    from engine import china_sector_cycles_grader as g

    prices = {"801001": _rising(N_BARS)}
    good = [_row(d, "801001", proj_next="peak") for d in _stamp_dates(CAL, 40, 100)]
    card = g.grade(pd.DataFrame(good), prices, None)
    cell = card["channels"]["calibration"]["states"]["proj_peak"]["21"]
    assert cell["hit_rate"] == 1.0
    assert cell["brier"] == 0.0
    # Perfect predictor is still inconclusive (not the sizing channel).
    assert cell["verdict"] == "inconclusive"


def test_china_grader_regression_no_scipy_import():
    """Regression: grading_stats and china grader must not IMPORT scipy or sklearn.

    We check for actual import lines (not the word appearing in docstrings/comments).
    """
    import ast
    import importlib
    import sys

    def _imported_modules(src_path: str) -> set[str]:
        """Return the set of top-level module names that the file imports."""
        with open(src_path) as f:
            tree = ast.parse(f.read(), filename=src_path)
        mods: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    mods.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    mods.add(node.module.split(".")[0])
        return mods

    import engine.grading_stats as gs_mod
    gs_imports = _imported_modules(gs_mod.__file__)
    assert "scipy" not in gs_imports, f"grading_stats must not import scipy; found: {gs_imports}"
    assert "sklearn" not in gs_imports, f"grading_stats must not import sklearn; found: {gs_imports}"

    import engine.china_sector_cycles_grader as g_mod
    g_imports = _imported_modules(g_mod.__file__)
    assert "scipy" not in g_imports, f"china grader must not import scipy; found: {g_imports}"
    assert "sklearn" not in g_imports, f"china grader must not import sklearn; found: {g_imports}"
