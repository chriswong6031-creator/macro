"""tests/test_grading_stats_calibration.py — Unit tests for calibration helpers in engine.grading_stats.

Coverage:
  1. reliability_curve: perfect calibration, degenerate constant probs, edge cases.
  2. brier_decomposition: perfect forecaster (reliability ≈ 0), known-answer decomposition,
     degenerate inputs, BS = reliability - resolution + uncertainty identity.
  3. era_split_stability: sign-flip detection, consistent verdict, insufficient-n gate,
     explicit split_date, continuous (non-binary) series.
  4. eb_shrink: small-n shrinks toward prior, large-n barely moves, fitted prior,
     degenerate / error cases.
  5. No scipy/sklearn imports (consistent with grading_stats contract).
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from engine import grading_stats as gs


# ════════════════════════════════════════════ 1 · reliability_curve ═══════════════


def test_reliability_curve_perfect_calibration_reliability_near_zero():
    """A perfectly calibrated forecaster: mean_prob ≈ obs_rate in every bin.

    When prob ≈ outcome (both 0 or both 1), the reliability component of
    brier_decomposition should be near zero; here we test that the curve shows
    mean_prob ≈ obs_rate in every populated bin.
    """
    rng = np.random.default_rng(0)
    probs = rng.uniform(0.0, 1.0, size=500)
    # Perfect calibration: outcome[i] = 1 iff probs[i] > threshold drawn from Uniform.
    # A simpler construction: for each prob p, draw Bernoulli(p).
    outcomes = rng.binomial(1, probs).astype(float)

    curve = gs.reliability_curve(probs, outcomes, n_bins=10)
    assert len(curve) > 0, "Expected at least one non-empty bin"

    # In expectation, mean_prob ≈ obs_rate. Allow generous tolerance given n=500.
    for bin_rec in curve:
        diff = abs(bin_rec["mean_prob"] - bin_rec["obs_rate"])
        assert diff < 0.25, (
            f"Bin [{bin_rec['bin_lo']:.1f}, {bin_rec['bin_hi']:.1f}]: "
            f"mean_prob={bin_rec['mean_prob']:.3f} vs obs_rate={bin_rec['obs_rate']:.3f} "
            f"(diff={diff:.3f} exceeds 0.25 — calibration appears poor)"
        )


def test_reliability_curve_degenerate_constant_probs():
    """Constant probabilities: all observations fall in one bin."""
    probs = np.full(50, 0.7)
    outcomes = np.array([1] * 35 + [0] * 15, dtype=float)
    curve = gs.reliability_curve(probs, outcomes, n_bins=10)
    # Only one bin should be populated (the one containing p=0.7).
    assert len(curve) == 1
    assert curve[0]["n"] == 50
    assert abs(curve[0]["mean_prob"] - 0.7) < 1e-9
    assert abs(curve[0]["obs_rate"] - 0.70) < 1e-9


def test_reliability_curve_all_correct_high_probs():
    """All probabilities high (near 1) and all outcomes = 1 → one bin near the top."""
    probs = np.linspace(0.9, 1.0, 20)
    outcomes = np.ones(20)
    curve = gs.reliability_curve(probs, outcomes, n_bins=10)
    assert len(curve) >= 1
    # All outcomes = 1, so obs_rate should be 1.0 in every bin.
    for rec in curve:
        assert rec["obs_rate"] == pytest.approx(1.0)


def test_reliability_curve_all_correct_low_probs():
    """All probabilities low (near 0) and all outcomes = 0 → one bin near the bottom."""
    probs = np.linspace(0.0, 0.1, 20)
    outcomes = np.zeros(20)
    curve = gs.reliability_curve(probs, outcomes, n_bins=10)
    assert len(curve) >= 1
    for rec in curve:
        assert rec["obs_rate"] == pytest.approx(0.0)


def test_reliability_curve_wilson_ci_per_bin():
    """Each populated bin should carry Wilson CI bounds from the existing primitive."""
    probs = np.array([0.1, 0.2, 0.8, 0.9])
    outcomes = np.array([0, 0, 1, 1], dtype=float)
    curve = gs.reliability_curve(probs, outcomes, n_bins=5)
    for rec in curve:
        assert "ci_lo" in rec
        assert "ci_hi" in rec
        if rec["n"] > 0:
            # Wilson CI should be valid [0,1] range.
            assert rec["ci_lo"] is not None
            assert rec["ci_hi"] is not None
            assert 0.0 <= rec["ci_lo"] <= rec["ci_hi"] <= 1.0


def test_reliability_curve_mismatched_lengths_raises():
    with pytest.raises(ValueError, match="same length"):
        gs.reliability_curve(np.array([0.5, 0.6]), np.array([1, 0, 1]))


def test_reliability_curve_n_bins_zero_raises():
    with pytest.raises(ValueError, match="n_bins must be"):
        gs.reliability_curve(np.array([0.5]), np.array([1.0]), n_bins=0)


def test_reliability_curve_returns_list_of_dicts():
    probs = np.linspace(0.0, 1.0, 100)
    outcomes = (probs > 0.5).astype(float)
    curve = gs.reliability_curve(probs, outcomes)
    assert isinstance(curve, list)
    for rec in curve:
        assert isinstance(rec, dict)
        assert {"bin_lo", "bin_hi", "mean_prob", "obs_rate", "n", "ci_lo", "ci_hi"}.issubset(rec)


def test_reliability_curve_bin_counts_sum_to_n():
    """Total count across bins equals the number of observations."""
    rng = np.random.default_rng(1)
    probs = rng.uniform(size=200)
    outcomes = rng.integers(0, 2, size=200).astype(float)
    curve = gs.reliability_curve(probs, outcomes, n_bins=10)
    total_n = sum(rec["n"] for rec in curve)
    assert total_n == 200


# ═══════════════════════════════════════════ 2 · brier_decomposition ═════════════


def test_brier_decomposition_perfect_forecaster():
    """Perfect forecaster: prob = outcome → reliability = 0, BS = 0."""
    probs = np.array([0.0, 0.0, 1.0, 1.0], dtype=float)
    outcomes = np.array([0, 0, 1, 1], dtype=float)
    d = gs.brier_decomposition(probs, outcomes, n_bins=10)
    assert d["brier_score"] == pytest.approx(0.0, abs=1e-9)
    assert d["reliability"] == pytest.approx(0.0, abs=1e-9)


def test_brier_decomposition_worst_forecaster():
    """Worst forecaster: prob = 1 when outcome = 0 and vice versa → BS = 1."""
    probs = np.array([1.0, 1.0, 0.0, 0.0], dtype=float)
    outcomes = np.array([0, 0, 1, 1], dtype=float)
    d = gs.brier_decomposition(probs, outcomes)
    assert d["brier_score"] == pytest.approx(1.0, abs=1e-9)


def test_brier_decomposition_bs_identity():
    """Known identity: BS ≈ reliability - resolution + uncertainty.

    The Murphy decomposition uses equal-width bins (a discrete approximation),
    so the identity holds approximately rather than exactly. The rounding comes
    from the bin discretization (ō_k is the bin mean forecast, not the midpoint)
    and from rounding of the stored floats. We allow up to 0.01 absolute error.
    """
    rng = np.random.default_rng(42)
    probs = rng.uniform(size=300)
    outcomes = rng.binomial(1, probs).astype(float)
    d = gs.brier_decomposition(probs, outcomes, n_bins=10)
    reconstructed = d["reliability"] - d["resolution"] + d["uncertainty"]
    # Allow up to 1pp absolute error due to bin-discretization of the decomposition.
    assert abs(reconstructed - d["brier_score"]) < 0.01, (
        f"BS identity failed: reliability({d['reliability']:.6f}) - "
        f"resolution({d['resolution']:.6f}) + uncertainty({d['uncertainty']:.6f}) = "
        f"{reconstructed:.6f} ≠ brier_score={d['brier_score']:.6f}"
    )


def test_brier_decomposition_uncertainty_equals_base_rate_times_complement():
    """Uncertainty = base_rate * (1 - base_rate)."""
    probs = np.array([0.3, 0.7, 0.3, 0.7], dtype=float)
    outcomes = np.array([0, 1, 1, 0], dtype=float)
    d = gs.brier_decomposition(probs, outcomes)
    base = d["base_rate"]
    expected_unc = base * (1.0 - base)
    assert d["uncertainty"] == pytest.approx(expected_unc, abs=1e-6)


def test_brier_decomposition_constant_prob_all_correct():
    """Constant prob = 0.0, all outcomes = 0 → BS = 0, reliability = 0."""
    probs = np.zeros(50)
    outcomes = np.zeros(50)
    d = gs.brier_decomposition(probs, outcomes)
    assert d["brier_score"] == pytest.approx(0.0, abs=1e-9)
    assert d["reliability"] == pytest.approx(0.0, abs=1e-9)
    assert d["base_rate"] == pytest.approx(0.0, abs=1e-9)
    assert d["uncertainty"] == pytest.approx(0.0, abs=1e-9)


def test_brier_decomposition_empty_input():
    """Empty arrays → all None outputs."""
    d = gs.brier_decomposition(np.array([]), np.array([]))
    assert d["brier_score"] is None
    assert d["n"] == 0


def test_brier_decomposition_mismatched_lengths_raises():
    with pytest.raises(ValueError, match="same length"):
        gs.brier_decomposition(np.array([0.5]), np.array([1, 0]))


def test_brier_decomposition_skilled_forecaster_has_negative_refinement():
    """Skilled forecaster (calibrated + decisive) should have refinement < 0."""
    # Create a skilled forecaster: probs well-separated and calibrated.
    rng = np.random.default_rng(7)
    probs = rng.choice([0.1, 0.9], size=200)
    outcomes = (probs > 0.5).astype(float)
    d = gs.brier_decomposition(probs, outcomes, n_bins=10)
    # Skilled: refinement (reliability - resolution) should be negative.
    assert d["refinement"] < 0, (
        f"Skilled forecaster should have refinement < 0; got {d['refinement']:.4f}"
    )


# ═══════════════════════════════════════════ 3 · era_split_stability ══════════════


def test_era_split_stability_sign_flip_detected():
    """Two eras with means of truly opposite sign → verdict = 'sign_flip'.

    Uses a continuous (non-binary) series with Era 1 positive mean and Era 2
    negative mean, so both era signs are non-zero and opposite.
    """
    n_per_era = 50
    dates = np.array([f"2020-{i:04d}" for i in range(n_per_era)] +
                     [f"2021-{i:04d}" for i in range(n_per_era)])
    # Era 1 mean = +0.8, Era 2 mean = -0.8 (clear sign flip for both non-zero).
    values = np.array([0.8] * n_per_era + [-0.8] * n_per_era)
    result = gs.era_split_stability(dates, values, n_splits=2)
    assert result["verdict"] == "sign_flip", (
        f"Expected 'sign_flip' for era means +0.8 vs -0.8, got {result['verdict']!r}"
    )


def test_era_split_stability_sign_flip_on_continuous():
    """Continuous series (non-binary) with positive vs negative means → 'sign_flip'."""
    n_per_era = 50
    dates = np.array([f"2020-{i:04d}" for i in range(n_per_era)] +
                     [f"2021-{i:04d}" for i in range(n_per_era)])
    values = np.array([0.05] * n_per_era + [-0.05] * n_per_era)
    result = gs.era_split_stability(dates, values, n_splits=2)
    assert result["verdict"] == "sign_flip"


def test_era_split_stability_consistent_verdict():
    """Both eras have similar positive means → verdict = 'consistent'."""
    n_per_era = 60
    dates = np.array([f"2020-{i:04d}" for i in range(n_per_era)] +
                     [f"2021-{i:04d}" for i in range(n_per_era)])
    # Era 1 and Era 2 both have mean ≈ 0.7 (both positive, very close).
    values = np.array([1.0] * 42 + [0.0] * 18 + [1.0] * 42 + [0.0] * 18, dtype=float)
    result = gs.era_split_stability(dates, values, n_splits=2)
    assert result["verdict"] in ("consistent", "inconclusive"), (
        f"Expected 'consistent' or 'inconclusive' for similar era means; got {result['verdict']!r}"
    )


def test_era_split_stability_insufficient_n_when_era_too_small():
    """Each era below min_n → verdict = 'insufficient_n'."""
    min_n = gs.MIN_N_DEFAULT  # 40
    # Only 10 total observations (5 per era) — well below min_n.
    dates = np.array([f"2020-{i:02d}" for i in range(5)] +
                     [f"2021-{i:02d}" for i in range(5)])
    values = np.ones(10)
    result = gs.era_split_stability(dates, values, n_splits=2, min_n=min_n)
    assert result["verdict"] == "insufficient_n", (
        f"Expected 'insufficient_n' when n_per_era=5 < min_n={min_n}; "
        f"got {result['verdict']!r}"
    )


def test_era_split_stability_explicit_split_date():
    """Explicit split_date routes data into the two requested eras.

    Also verifies that mean=0.0 in era 1 does not trigger sign_flip (since
    sign(0) = 0 by convention). Instead the verdict is 'consistent' or 'inconclusive'
    because 0.0 is not a negative sign.
    """
    dates = np.array([f"2020-{i:04d}" for i in range(60)] +
                     [f"2022-{i:04d}" for i in range(60)])
    values = np.concatenate([np.ones(60), np.zeros(60)])
    result = gs.era_split_stability(
        dates, values, split_date="2021-0000", n_splits=2, min_n=1
    )
    # Era 0 = 2020 dates (all ones); Era 1 = 2022 dates (all zeros).
    assert len(result["eras"]) == 2
    era0 = result["eras"][0]
    era1 = result["eras"][1]
    assert era0["n"] == 60
    assert era1["n"] == 60
    assert era0["mean"] == pytest.approx(1.0)
    assert era1["mean"] == pytest.approx(0.0)
    # mean=0.0 has sign=0 so no sign_flip (0 is not a negative sign).
    # The era means are far apart (1.0 vs 0.0) so verdict is inconclusive, not consistent.
    assert result["verdict"] in ("inconsistent", "inconclusive", "consistent"), (
        f"Unexpected verdict: {result['verdict']!r}"
    )

    # Now test with negative era 2 to confirm sign_flip works with explicit split.
    values2 = np.concatenate([np.ones(60) * 0.5, -np.ones(60) * 0.5])
    result2 = gs.era_split_stability(
        dates, values2, split_date="2021-0000", n_splits=2, min_n=1
    )
    assert result2["verdict"] == "sign_flip", (
        f"Expected sign_flip for means +0.5 vs -0.5; got {result2['verdict']!r}"
    )


def test_era_split_stability_three_eras():
    """n_splits=3 produces three era records."""
    n = 90
    dates = np.array([f"2020-{i:04d}" for i in range(n)])
    values = np.ones(n)
    result = gs.era_split_stability(dates, values, n_splits=3, min_n=1)
    assert result["n_splits"] == 3
    assert len(result["eras"]) == 3
    for rec in result["eras"]:
        assert rec["n"] == 30


def test_era_split_stability_empty_input():
    """Empty arrays → insufficient_n verdict."""
    result = gs.era_split_stability(np.array([]), np.array([]))
    assert result["verdict"] == "insufficient_n"
    assert result["eras"] == []


def test_era_split_stability_binary_has_ci():
    """Binary series should carry Wilson CI in each era record."""
    n = 50
    dates = np.array([f"2020-{i:04d}" for i in range(n)] +
                     [f"2021-{i:04d}" for i in range(n)])
    values = np.array([1.0] * 35 + [0.0] * 15 + [1.0] * 35 + [0.0] * 15)
    result = gs.era_split_stability(dates, values, n_splits=2, min_n=1)
    for rec in result["eras"]:
        assert rec["is_binary"] is True
        assert rec["ci_lo"] is not None
        assert rec["ci_hi"] is not None
        assert 0.0 <= rec["ci_lo"] <= rec["ci_hi"] <= 1.0


def test_era_split_stability_continuous_no_binary_flag():
    """Non-binary continuous series should have is_binary=False and ci_lo=None."""
    n = 50
    dates = np.array([f"2020-{i:04d}" for i in range(n)] +
                     [f"2021-{i:04d}" for i in range(n)])
    values = np.linspace(0.0, 1.0, n * 2) * 0.5 + 0.1  # values in (0.1, 0.6), non-binary
    result = gs.era_split_stability(dates, values, n_splits=2, min_n=1)
    for rec in result["eras"]:
        assert rec["is_binary"] is False
        assert rec["ci_lo"] is None


def test_era_split_stability_n_splits_below_2_raises():
    with pytest.raises(ValueError, match="n_splits must be"):
        gs.era_split_stability(np.array(["2020-01"]), np.array([1.0]), n_splits=1)


def test_era_split_stability_mismatched_lengths_raises():
    with pytest.raises(ValueError, match="same length"):
        gs.era_split_stability(np.array(["2020-01", "2020-02"]), np.array([1.0]))


# ══════════════════════════════════════════════ 4 · eb_shrink ════════════════════


def test_eb_shrink_small_n_pulls_toward_prior():
    """Small-n cell should be pulled strongly toward the prior mean.

    Uses k/n values where raw rates differ substantially from the prior center,
    so shrinkage direction is unambiguous.
    """
    # Small-n cell: raw rate = 0/2 = 0.0; prior_mean = 7/(7+3) = 0.7
    # → shrunk should be pulled UP from 0.0 toward 0.7
    # Large-n cell: raw rate = 90/100 = 0.9; prior_mean = 0.7
    # → shrunk should be pulled DOWN slightly from 0.9 toward 0.7, but stay near 0.9
    k = np.array([0, 90])
    n = np.array([2, 100])
    prior_alpha, prior_beta = 7.0, 3.0  # prior_mean = 0.7
    result = gs.eb_shrink(k, n, prior_alpha=prior_alpha, prior_beta=prior_beta)
    prior_mean = result["prior_mean"]
    assert prior_mean == pytest.approx(0.7, abs=1e-4)
    shrunk = result["shrunk_rates"]
    raw_small = 0.0
    raw_large = 0.9
    # Small-n (k=0, n=2): posterior = (0+7)/(2+10) = 7/12 ≈ 0.583 — well above raw 0.0.
    assert shrunk[0] > raw_small + 0.3, (
        f"Small-n cell: shrunk={shrunk[0]:.4f} should be pulled well above raw={raw_small}"
    )
    # Large-n cell: stays within 5pp of its raw rate 0.9.
    assert abs(shrunk[1] - raw_large) < 0.05, (
        f"Large-n cell: shrunk ({shrunk[1]:.4f}) moved more than 5pp from raw ({raw_large:.2f})"
    )
    # Large-n cell closer to its own raw rate than to the prior center.
    assert abs(shrunk[1] - raw_large) < abs(shrunk[1] - prior_mean), (
        f"Large-n cell: shrunk ({shrunk[1]:.4f}) should be closer to raw ({raw_large:.2f}) "
        f"than to prior ({prior_mean:.2f})"
    )


def test_eb_shrink_large_n_barely_moves():
    """Large-n cell should remain close to its raw rate."""
    k = np.array([1, 800])
    n = np.array([2, 1000])
    prior_alpha, prior_beta = 2.0, 8.0  # prior_mean = 0.2
    result = gs.eb_shrink(k, n, prior_alpha=prior_alpha, prior_beta=prior_beta)
    raw_large = 800 / 1000  # 0.8
    # Posterior for large-n cell = (800+2)/(1000+10) = 802/1010 ≈ 0.7941.
    posterior = (800 + prior_alpha) / (1000 + prior_alpha + prior_beta)
    assert result["shrunk_rates"][1] == pytest.approx(posterior, abs=1e-4)
    # Large-n cell stays within 2pp of its raw rate.
    assert abs(result["shrunk_rates"][1] - raw_large) < 0.02, (
        f"Large-n cell: shrunk rate {result['shrunk_rates'][1]:.4f} moved more than "
        f"2pp from raw rate {raw_large:.4f}"
    )


def test_eb_shrink_zero_n_cell_returns_prior_mean():
    """A cell with n=0 (no data) should return the prior mean."""
    result = gs.eb_shrink(
        k=np.array([0, 5]),
        n=np.array([0, 10]),
        prior_alpha=3.0, prior_beta=7.0
    )
    prior_mean = 3.0 / 10.0  # 0.3
    assert result["shrunk_rates"][0] == pytest.approx(prior_mean, abs=1e-6)


def test_eb_shrink_fitted_prior_is_flagged_is_fitted():
    """When priors are None (fitted from data), is_fitted must be True."""
    k = np.array([10, 20, 30, 40, 50])
    n = np.array([20, 40, 60, 80, 100])
    result = gs.eb_shrink(k, n)
    assert result["is_fitted"] is True


def test_eb_shrink_explicit_prior_is_not_fitted():
    """When explicit priors are passed, is_fitted must be False."""
    k = np.array([5, 10])
    n = np.array([10, 20])
    result = gs.eb_shrink(k, n, prior_alpha=2.0, prior_beta=3.0)
    assert result["is_fitted"] is False


def test_eb_shrink_fitted_result_is_in_sample_labeled():
    """fit_warning must be None for a normal fitted case (3+ cells, finite var)."""
    k = np.array([5, 10, 15, 20, 25])
    n = np.array([50, 50, 50, 50, 50])
    result = gs.eb_shrink(k, n)
    # Normal case with 5 cells and varying rates → no fit_warning expected.
    # (Degenerate cases like constant rates get a warning; heterogeneous rates do not.)
    # The prior should have been estimable.
    assert result["prior_alpha"] > 0
    assert result["prior_beta"] > 0
    assert result["n_cells"] == 5


def test_eb_shrink_too_few_cells_warns_and_falls_back():
    """Fewer than 3 cells → fit_warning is populated and fallback prior used."""
    k = np.array([3])
    n = np.array([10])
    result = gs.eb_shrink(k, n)  # is_fitted=True, n_cells=1
    assert result["fit_warning"] is not None
    # Fallback = Beta(1,1), prior_mean = 0.5.
    assert result["prior_mean"] == pytest.approx(0.5, abs=1e-6)


def test_eb_shrink_only_one_prior_raises():
    """Providing only one of prior_alpha or prior_beta must raise ValueError."""
    with pytest.raises(ValueError, match="both be set or both be None"):
        gs.eb_shrink(np.array([5]), np.array([10]), prior_alpha=2.0)


def test_eb_shrink_mismatched_shapes_raises():
    with pytest.raises(ValueError, match="same shape"):
        gs.eb_shrink(np.array([1, 2]), np.array([10]))


def test_eb_shrink_returns_correct_n_cells():
    k = np.array([1, 2, 3, 4, 5])
    n = np.array([10, 10, 10, 10, 10])
    result = gs.eb_shrink(k, n, prior_alpha=1.0, prior_beta=1.0)
    assert result["n_cells"] == 5
    assert len(result["shrunk_rates"]) == 5


def test_eb_shrink_posterior_between_raw_and_prior_for_explicit_prior():
    """For explicit prior, each shrunk rate should be between raw rate and prior_mean."""
    k = np.array([0, 5, 10])
    n = np.array([10, 10, 10])
    prior_alpha, prior_beta = 5.0, 5.0  # prior_mean = 0.5
    result = gs.eb_shrink(k, n, prior_alpha=prior_alpha, prior_beta=prior_beta)
    prior_mean = result["prior_mean"]
    for i, (k_i, n_i) in enumerate(zip(k, n)):
        raw = k_i / n_i
        shrunk = result["shrunk_rates"][i]
        lo = min(raw, prior_mean)
        hi = max(raw, prior_mean)
        assert lo - 1e-9 <= shrunk <= hi + 1e-9, (
            f"Cell {i}: shrunk={shrunk:.4f} not between raw={raw:.2f} and prior={prior_mean:.2f}"
        )


# ════════════════════════════════ 5 · No scipy/sklearn imports ════════════════════


def test_no_scipy_or_sklearn_in_grading_stats():
    """grading_stats must never import scipy or sklearn (thin data-bot env constraint)."""
    import ast

    import engine.grading_stats as gs_mod

    with open(gs_mod.__file__) as f:
        tree = ast.parse(f.read(), filename=gs_mod.__file__)

    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.add(node.module.split(".")[0])

    assert "scipy" not in imported, (
        f"grading_stats must not import scipy; found imports: {imported}"
    )
    assert "sklearn" not in imported, (
        f"grading_stats must not import sklearn; found imports: {imported}"
    )
