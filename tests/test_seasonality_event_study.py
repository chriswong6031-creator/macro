"""Tests for the biopharma event-study core and the RC/SPA primitives it leans on.

Everything here is synthetic and offline.  The suite is organised around the
failure modes the module exists to prevent rather than around its public surface:

* a test that a p-value is produced proves nothing — the CALIBRATION tests below
  (empirical size under a true null across hundreds of replications) are the ones
  that separate a real test statistic from a decorative one, and they are the
  reason this file is worth running;
* the leakage tests move the event and assert the estimate moves with it, because
  an estimation window that quietly includes post-event bars produces perfectly
  plausible output;
* the refusal tests assert the module RAISES or ABSTAINS by name — a forbidden
  estimator that merely logs a warning has already shipped the wrong number.
"""
from __future__ import annotations

import ast
import json
import math
import pathlib
import re

import numpy as np
import pandas as pd
import pytest

from engine.seasonality import contracts as C
from engine.seasonality import event_study as es
from engine.trial_ledger import TrialLedger
from engine.validation import reality_check, spa_test

MODULE_SOURCE_PATH = (
    pathlib.Path(__file__).resolve().parents[1] / "engine" / "seasonality" / "event_study.py"
)


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def calendar() -> pd.DatetimeIndex:
    """~16 years of business days, so an era split has both sides."""
    return pd.bdate_range("2005-01-03", periods=4000, tz="UTC")


@pytest.fixture(scope="module")
def tape(calendar):
    """(prices_by_issuer, benchmark) — pure noise, no planted effect."""
    rng = np.random.default_rng(11)
    issuers = [f"BIO{i:02d}" for i in range(25)]
    prices = {
        t: pd.Series(40.0 * np.cumprod(1.0 + rng.normal(0, 0.025, len(calendar))),
                     index=calendar)
        for t in issuers
    }
    bench = pd.Series(100.0 * np.cumprod(1.0 + rng.normal(0, 0.009, len(calendar))),
                      index=calendar, name="SPY")
    return prices, bench


@pytest.fixture(scope="module")
def cohort(calendar, tape):
    """60 events across 25 issuers, spread over 60 distinct months."""
    prices, _ = tape
    issuers = sorted(prices)
    return [
        {"event_id": f"E{k:03d}", "issuer_id": issuers[k % len(issuers)],
         "event_date": calendar[600 + k * 40].date().isoformat()}
        for k in range(60)
    ]


# --------------------------------------------------------------------------- #
# Part 1 — White's Reality Check / Hansen's SPA
# --------------------------------------------------------------------------- #
def _rc_panel(seed: int, T: int = 120, K: int = 5, edge: float = 0.0):
    """Benchmark losses and K model losses.  ``edge`` shifts model 0's loss DOWN,
    i.e. makes it genuinely better than the benchmark."""
    rng = np.random.default_rng(seed)
    bench = rng.normal(size=T)
    models = rng.normal(size=(T, K))
    models[:, 0] -= edge
    return bench, models


def test_rc_and_spa_return_the_documented_shape():
    bench, models = _rc_panel(1)
    for fn in (reality_check, spa_test):
        out = fn(bench, models, B=300, seed=3)
        assert set(out) >= {"statistic", "p_value", "n_models", "n_obs", "block",
                            "B", "best_model", "recentred_models"}
        assert out["n_models"] == 5 and out["n_obs"] == 120
        assert 0.0 <= out["p_value"] <= 1.0
        assert out["abstained"] is False


def test_rc_auto_block_is_the_documented_cube_root():
    bench, models = _rc_panel(2, T=125)
    out = reality_check(bench, models, B=200, seed=3)
    assert out["block"] == max(1, round(125 ** (1 / 3)))
    assert reality_check(bench, models, block=9, B=200, seed=3)["block"] == 9


def test_rc_and_spa_find_a_genuinely_superior_model():
    """A model with a real edge must be detected — a test that never rejects has
    perfect size and zero value."""
    bench, models = _rc_panel(4, T=250, edge=0.5)
    rc = reality_check(bench, models, B=1000, seed=5)
    spa = spa_test(bench, models, B=1000, seed=5)
    assert rc["p_value"] < 0.01, rc
    assert spa["p_value"] < 0.01, spa
    assert rc["best_model"] == "model_0" and spa["best_model"] == "model_0"


def test_spa_recentring_drops_hopeless_models_from_the_null():
    """Hansen's consistent recentring: a catastrophically bad model must not
    contribute to the bootstrap null (that is the power RC gives away)."""
    rng = np.random.default_rng(6)
    T = 200
    bench = rng.normal(size=T)
    models = rng.normal(size=(T, 3))
    models[:, 2] += 6.0                       # model 2 is hopeless
    out = spa_test(bench, models, B=800, seed=7)
    assert out["recentred_models"] < out["n_models"]
    assert out["recentred_models"] >= 1


@pytest.mark.parametrize("kwargs,reason", [
    (dict(T=10), "insufficient_obs_lt_20"),
])
def test_rc_abstains_on_short_samples(kwargs, reason):
    bench, models = _rc_panel(8, T=kwargs["T"])
    for fn in (reality_check, spa_test):
        out = fn(bench, models, B=100, seed=1)
        assert out["abstained"] is True and out["reason"] == reason
        assert out["p_value"] is None and out["statistic"] is None


def test_rc_abstains_on_all_nan_and_zero_variance_columns():
    bench, models = _rc_panel(9, T=80, K=3)
    nan_models = models.copy()
    nan_models[:, 1] = np.nan
    out = reality_check(bench, nan_models, B=100, seed=1)
    assert out["abstained"] and out["reason"].startswith("all_nan_model_columns")

    flat = models.copy()
    flat[:, 1] = bench                        # d_1 is identically zero
    out = spa_test(bench, flat, B=100, seed=1)
    assert out["abstained"] and out["reason"].startswith("zero_variance_loss_differential")


def test_rc_abstains_when_there_are_no_models():
    bench, _ = _rc_panel(10, T=80)
    out = reality_check(bench, pd.DataFrame(index=range(80)), B=100, seed=1)
    assert out["abstained"] and out["reason"] == "no_models"


def test_spa_recentring_actually_moves_the_reported_p_value():
    """The BEHAVIOUR, not the bookkeeping.  ``recentred_models < n_models`` is
    satisfied by an implementation that counts the drops and then reports SPA_u
    anyway; the recentring only earns its docstring if dropping the hopeless model
    from the null makes SPA_c STRICTLY more powerful than the variant that keeps it.
    A stealth mutant that reports ``_p(dbar)`` (= SPA_u) survives the bookkeeping
    assertion and dies here."""
    rng = np.random.default_rng(6)
    T = 200
    bench = rng.normal(size=T)
    models = rng.normal(size=(T, 3))
    models[:, 0] -= 0.12                      # model 0 has a marginal real edge
    models[:, 2] += 6.0                       # model 2 is hopeless
    out = spa_test(bench, models, B=2000, seed=7)
    assert out["recentred_models"] < out["n_models"]
    assert out["p_value"] < out["p_value_upper"], out
    assert out["p_value_lower"] <= out["p_value"]


def test_rc_and_spa_are_deterministic_given_a_seed():
    bench, models = _rc_panel(12, T=140)
    for fn in (reality_check, spa_test):
        assert fn(bench, models, B=400, seed=99) == fn(bench, models, B=400, seed=99)
        assert fn(bench, models, B=400, seed=99) != fn(bench, models, B=400, seed=100)


@pytest.mark.parametrize("kwargs,reason", [
    (dict(B=0), "insufficient_bootstrap_draws_lt_2:0"),
    (dict(B=1), "insufficient_bootstrap_draws_lt_2:1"),
    (dict(block=0), "non_positive_block:0"),
    (dict(block=-5), "non_positive_block:-5"),
])
def test_a_degenerate_bootstrap_argument_abstains_instead_of_being_coerced(kwargs, reason):
    """``B=0`` returned ``p_value=1.0`` computed as ``(1+0)/(0+1)`` from an empty
    null, and ``block=0`` was silently rounded up to an iid bootstrap of a
    serially-correlated differential.  Both are caller errors and both now have a
    name."""
    bench, models = _rc_panel(60, T=80, K=3)
    for fn in (reality_check, spa_test):
        out = fn(bench, models, **{"B": 300, "seed": 1, **kwargs})
        assert out["abstained"] is True and out["reason"] == reason, out
        assert out["p_value"] is None and out["statistic"] is None


def test_an_all_nan_benchmark_is_named_rather_than_reported_as_too_few_rows():
    """A named refusal that names something other than the actual defect is worse
    than an unnamed one — it sends the reader to look at the row count."""
    _bench, models = _rc_panel(61, T=80, K=3)
    out = reality_check(np.full(80, np.nan), models, B=200, seed=1)
    assert out["abstained"] is True and out["reason"] == "all_nan_benchmark"


def test_an_abstention_reports_the_block_it_would_have_used():
    bench, models = _rc_panel(62, T=10, K=3)
    out = reality_check(bench, models, B=200, seed=1)
    assert out["reason"] == "insufficient_obs_lt_20"
    assert out["block"] == max(1, round(10 ** (1 / 3))), out       # never None


def test_two_meaningful_indices_are_joined_by_LABEL_not_by_position():
    """Equal length is not alignment.  Two date-indexed series offset by one row used
    to be zipped positionally and answer a question about rows that never met."""
    rng = np.random.default_rng(63)
    idx = pd.date_range("2020-01-01", periods=60, freq="D")
    bench = pd.Series(rng.normal(size=60), index=idx)
    frame = pd.DataFrame({"m": rng.normal(size=60)}, index=idx + pd.Timedelta(days=1))
    out = reality_check(bench, frame, B=200, seed=1)
    # 59 overlapping labels; a positional join would have found 60 and a differential
    # of exactly zero (which would have abstained as zero-variance instead).
    assert out["abstained"] is False
    assert out["n_obs"] == 59, out
    assert out["statistic"] != 0.0


def test_rc_accepts_a_dataframe_and_reports_the_column_key():
    bench, models = _rc_panel(13, T=100, K=3, edge=0.6)
    frame = pd.DataFrame(models, columns=["slow", "medium", "fast"])
    out = reality_check(bench, frame, B=500, seed=2)
    assert out["best_model"] == "slow"


# --------------------------------------------------------------------------- #
# CALIBRATION — empirical size under a true null.  These are the load-bearing tests.
# --------------------------------------------------------------------------- #
def _rc_size(block, reps: int = 600, B: int = 400, T: int = 120, K: int = 5):
    """Empirical rejection rate of RC and SPA_c under the LEAST-FAVOURABLE null —
    every model's expected loss exactly equal to the benchmark's, which is where
    both tests are most distorted."""
    rc = spa = 0
    for r in range(reps):
        bench, models = _rc_panel(20000 + r, T=T, K=K)
        if reality_check(bench, models, block=block, B=B, seed=r)["p_value"] < 0.05:
            rc += 1
        if spa_test(bench, models, block=block, B=B, seed=r)["p_value"] < 0.05:
            spa += 1
    return rc / reps, spa / reps


def test_rc_and_spa_are_exact_when_the_block_matches_the_dependence():
    """The core machinery, with the bootstrap correctly specified: iid losses
    resampled one observation at a time.  Both tests must sit on 5%.  This is the
    test that separates a real statistic from a decorative one — a broken family
    test shows up here as a size of 0.3 or 0.001, not as a rounding error."""
    size_rc, size_spa = _rc_size(block=1)
    assert 0.03 <= size_rc <= 0.08, f"Reality Check empirical size {size_rc}"
    assert 0.03 <= size_spa <= 0.08, f"SPA empirical size {size_spa}"


def test_the_auto_block_costs_size_and_the_cost_is_bounded():
    """With the documented ``T ** (1/3)`` block on iid data the bootstrap has ~24
    effective blocks and both tests drift ABOVE nominal — RC mildly, SPA_c more.
    That drift is disclosed in ``engine.validation``'s measured-size grid; this test
    pins it so it cannot silently grow into the 20% range that would make either
    test useless."""
    size_rc, size_spa = _rc_size(block=None)
    assert 0.03 <= size_rc <= 0.095, f"Reality Check empirical size {size_rc}"
    assert 0.04 <= size_spa <= 0.115, f"SPA empirical size {size_spa}"
    assert size_spa >= size_rc - 0.02, "SPA_c is the more liberal of the two"


def test_spa_reports_hansens_bracketing_variants():
    """SPA_l <= SPA_c <= SPA_u, always.  The brackets exist so the finite-sample
    slack is auditable; a caller who reads whichever is smallest is p-hacking, which
    is why only ``p_value`` is the reported number."""
    bench, models = _rc_panel(44, T=200, K=6, edge=0.25)
    out = spa_test(bench, models, B=800, seed=9)
    assert out["p_value_lower"] <= out["p_value"] <= out["p_value_upper"]


def test_a_bootstrap_p_value_is_never_exactly_zero():
    """``(1 + count) / (B + 1)``: the floor is what a bootstrap of that size can
    actually resolve.  Reporting 0.0 claims a precision B draws cannot deliver."""
    bench, models = _rc_panel(45, T=250, edge=3.0)
    for fn in (reality_check, spa_test):
        out = fn(bench, models, B=200, seed=1)
        assert out["p_value"] == pytest.approx(1.0 / 201.0, abs=1e-6)


def test_spa_does_not_reject_when_no_model_beats_the_benchmark():
    """The atom at zero.  When every candidate loses in sample, SPA's statistic and
    every bootstrap draw collapse to 0; the honest reading is 'no evidence at all',
    and a strict `>` comparison would report the strongest possible rejection."""
    rng = np.random.default_rng(46)
    T = 150
    bench = rng.normal(size=T)
    models = rng.normal(size=(T, 3)) + 5.0        # every model far worse
    out = spa_test(bench, models, B=400, seed=2)
    assert out["statistic"] == 0.0
    assert out["p_value"] > 0.9


def test_bmp_and_corrado_have_approximately_nominal_size():
    """The same discipline for the cross-sectional tests, and BMP is run against
    EVENT-INDUCED VARIANCE (a random per-event variance burst inside the window)
    because that is the condition it exists to survive."""
    reps, n_events, win, days = 400, 60, 5, 120
    hits_bmp = hits_corrado = 0
    cols = list(range(-(days // 2), days - days // 2))
    for r in range(reps):
        rng = np.random.default_rng(70000 + r)
        sigma = rng.uniform(0.01, 0.05, size=n_events)
        burst = rng.uniform(1.0, 3.0, size=n_events)     # event-induced variance
        ar = rng.normal(size=(n_events, win)) * (sigma * burst)[:, None]
        if (bmp := es.bmp_test(ar, sigma))["p_value"] < 0.05:
            hits_bmp += 1
        assert bmp["abstained"] is False
        full = pd.DataFrame(rng.normal(size=(n_events, days)) * sigma[:, None],
                            columns=cols)
        if es.corrado_rank_test(full)["p_value"] < 0.05:
            hits_corrado += 1
    size_bmp, size_corrado = hits_bmp / reps, hits_corrado / reps
    assert 0.02 <= size_bmp <= 0.09, f"BMP empirical size {size_bmp}"
    assert 0.02 <= size_corrado <= 0.09, f"Corrado empirical size {size_corrado}"


def test_bmp_standardization_beats_a_raw_car_t_on_heterogeneous_sigma():
    """The separating DGP for BMP's FIRST step, and the one the suite was missing.

    ``scar = car`` (i.e. no standardization at all — a plain cross-sectional t on raw
    CARs) passes every other test in this file: it has the same size under the null,
    and the planted-effect test uses a CONSTANT sigma, where standardizing is a scalar
    rescale and both statistics are numerically identical.  What separates them is
    heterogeneous per-event sigma with a constant additive effect: unstandardized, the
    loud events dominate both the mean and the SD it is divided by.  MEASURED at
    1.0e-2 window sigma spread and a +2% event-day effect, N=60: BMP ~83%, raw-CAR t
    ~46%.  Fewer reps here, so the gap is asserted with room."""
    reps, n, L, effect = 300, 60, 5, 0.020
    hits_bmp = hits_raw = 0
    for r in range(reps):
        rng = np.random.default_rng(91000 + r)
        sigma = rng.uniform(0.005, 0.06, size=n)
        ar = rng.normal(size=(n, L)) * sigma[:, None]
        ar[:, L // 2] += effect
        if es.bmp_test(ar, sigma)["p_value"] < 0.05:
            hits_bmp += 1
        car = ar.sum(axis=1)
        t = car.mean() * math.sqrt(n) / car.std(ddof=1)
        if es._student_t_two_sided_p(t, n - 1) < 0.05:
            hits_raw += 1
    power_bmp, power_raw = hits_bmp / reps, hits_raw / reps
    assert power_bmp > 0.70, f"BMP power {power_bmp}"
    assert power_bmp - power_raw > 0.20, (power_bmp, power_raw)


def test_bmp_survives_an_event_induced_variance_burst_that_breaks_patell():
    """The SECOND step — the cross-sectional denominator.  The test that a variance
    burst destroys is PATELL's (estimation-period sd used as if it were the truth),
    not the raw-CAR t the docstring used to name.  Both claims are measured here so
    the docstring cannot drift back."""
    reps, n, L = 400, 60, 5
    hits_bmp = hits_patell = hits_raw = 0
    for r in range(reps):
        rng = np.random.default_rng(80000 + r)
        sigma = rng.uniform(0.01, 0.05, size=n)
        burst = rng.uniform(1.0, 9.0, size=n)
        ar = rng.normal(size=(n, L)) * (sigma * burst)[:, None]
        if es.bmp_test(ar, sigma)["p_value"] < 0.05:
            hits_bmp += 1
        car = ar.sum(axis=1)
        scar = car / (sigma * math.sqrt(L))
        z = scar.mean() * math.sqrt(n)
        if 2.0 * (1.0 - es._norm_cdf(abs(z))) < 0.05:
            hits_patell += 1
        t = car.mean() * math.sqrt(n) / car.std(ddof=1)
        if es._student_t_two_sided_p(t, n - 1) < 0.05:
            hits_raw += 1
    size_bmp, size_patell, size_raw = (h / reps for h in
                                       (hits_bmp, hits_patell, hits_raw))
    assert 0.02 <= size_bmp <= 0.09, f"BMP size under a burst {size_bmp}"
    assert 0.02 <= size_raw <= 0.09, f"raw-CAR t size under a burst {size_raw}"
    assert size_patell > 0.30, f"Patell is supposed to break here, got {size_patell}"


def test_corrado_size_on_the_residual_shaped_panel_the_pipeline_actually_feeds_it():
    """The published Corrado grid is measured on an iid Gaussian matrix, where every
    column is exchangeable.  ``estimate_reaction`` feeds it IN-SAMPLE OLS residuals
    concatenated with OUT-OF-SAMPLE event ARs — two blocks that are not exchangeable.
    The docstring now claims that costs little and errs conservative; this measures
    it rather than asserting it."""
    reps, n, n_est, win = 120, 60, 220, 21
    cols = list(range(-250, -250 + n_est)) + list(range(-10, 11))
    hits = 0
    for r in range(reps):
        rng = np.random.default_rng(61000 + r)
        rows = []
        for _ in range(n):
            s = rng.uniform(0.01, 0.05)
            x = rng.normal(0, 0.01, n_est + win)
            y = 1.0 * x + rng.normal(0, s, n_est + win)
            A = np.column_stack([np.ones(n_est), x[:n_est]])
            coef, *_ = np.linalg.lstsq(A, y[:n_est], rcond=None)
            rows.append(np.concatenate([y[:n_est] - A @ coef,
                                        y[n_est:] - (coef[0] + coef[1] * x[n_est:])]))
        out = es.corrado_rank_test(pd.DataFrame(np.array(rows), columns=cols),
                                   event_cols=list(range(-10, 11)))
        assert out["abstained"] is False
        if out["p_value"] < 0.05:
            hits += 1
    size = hits / reps
    assert 0.0 <= size <= 0.10, f"Corrado size on the pipeline's own panel {size}"


def test_bmp_and_corrado_detect_a_planted_effect():
    rng = np.random.default_rng(31)
    sigma = np.full(80, 0.02)
    ar = rng.normal(size=(80, 5)) * sigma[:, None] + 0.012
    assert es.bmp_test(ar, sigma)["p_value"] < 0.01

    days = 120
    cols = list(range(-(days // 2), days - days // 2))
    mat = rng.normal(size=(80, days)) * 0.02
    mat[:, cols.index(0)] += 0.05
    assert es.corrado_rank_test(pd.DataFrame(mat, columns=cols))["p_value"] < 0.01


# --------------------------------------------------------------------------- #
# earliest_executable_bar — the maximum, computed explicitly
# --------------------------------------------------------------------------- #
def test_execution_bar_is_the_next_bar_after_the_cutoff_when_all_facts_are_early(calendar):
    receipt = es.earliest_executable_bar(
        "2016-06-01T12:00:00Z",
        [{"id": "adv", "known_at": "2016-05-30T00:00:00Z"}],
        trading_bars=calendar)
    assert receipt["binding_source"]["kind"] == "decision_cutoff"
    assert receipt["execution_bar"] == "2016-06-02T00:00:00Z"


def test_a_fact_known_after_the_cutoff_moves_the_execution_bar(calendar):
    """The whole point of the function: a fact that becomes available AFTER the
    decision cutoff pushes execution later.  Anchoring on the cutoff would buy at a
    price nobody could have paid."""
    early = es.earliest_executable_bar(
        "2016-06-01T12:00:00Z",
        [{"id": "float", "known_at": "2016-05-20T00:00:00Z"}],
        trading_bars=calendar)
    late = es.earliest_executable_bar(
        "2016-06-01T12:00:00Z",
        [{"id": "float", "known_at": "2016-05-20T00:00:00Z",
          "available_at": "2016-06-06T09:00:00Z"}],
        trading_bars=calendar)
    assert late["execution_bar"] > early["execution_bar"]
    assert late["execution_bar"] == "2016-06-07T00:00:00Z"
    assert late["binding_source"] == {"kind": "fact", "fact_index": 0,
                                      "key": "available_at", "fact_id": "float"}
    assert late["binding_timestamp"] == "2016-06-06T09:00:00Z"


def test_execution_bar_abstains_when_the_calendar_runs_out(calendar):
    receipt = es.earliest_executable_bar(
        "2099-01-01T00:00:00Z", [], trading_bars=calendar)
    assert receipt["abstained"] is True
    assert receipt["reason"] == "no_tradable_bar_after_availability"
    assert receipt["execution_bar"] is None


def test_a_fact_with_no_availability_timestamp_is_refused(calendar):
    with pytest.raises(es.EventStudyError, match="no availability timestamp"):
        es.earliest_executable_bar("2016-06-01T00:00:00Z", [{"id": "x", "value": 1}],
                                   trading_bars=calendar)


# --------------------------------------------------------------------------- #
# abnormal returns — the estimation window ends BEFORE the event window
# --------------------------------------------------------------------------- #
def test_overlapping_estimation_and_event_windows_are_refused(calendar, tape):
    prices, bench = tape
    px = prices["BIO00"]
    with pytest.raises(es.EventStudyError, match="STRICTLY before"):
        es.abnormal_returns(px, 900, benchmark=bench,
                            estimation=(-250, -5), window=(-10, 10))
    with pytest.raises(es.EventStudyError, match="STRICTLY before"):
        es.abnormal_returns(px, 900, benchmark=bench,
                            estimation=(-250, -10), window=(-10, 10))


def test_an_estimation_window_reaching_the_event_day_is_refused(calendar, tape):
    """``estimation[1] < window[0]`` is NOT the law — ``estimation[1] < min(window[0],
    0)`` is.  A post-drift study (``window=(1, 10)``) satisfies the first while
    letting the event day itself, and every bar up to the window's open, into the OLS
    fit.  Measured on a planted event day, that moved beta by +0.16 and doubled
    sigma."""
    prices, bench = tape
    px = prices["BIO00"]
    for estimation, window in [((-250, 0), (1, 10)),      # event day in the fit
                               ((-250, 5), (6, 10)),      # bars +1..+5 in the fit
                               ((-250, 2), (3, 10))]:     # bars +1, +2 in the fit
        with pytest.raises(es.EventStudyError, match="STRICTLY before"):
            es.abnormal_returns(px, 900, benchmark=bench,
                                estimation=estimation, window=window)
    # A post-drift window with a properly separated estimation sample still works.
    ok = es.abnormal_returns(px, 900, benchmark=bench,
                             estimation=(-250, -31), window=(1, 10))
    assert ok["abstained"] is False and ok["n_estimation_obs"] == 220


def test_no_post_event_bar_enters_the_estimation_sample(calendar, tape):
    prices, bench = tape
    out = es.abnormal_returns(prices["BIO00"], calendar[900], benchmark=bench)
    assert out["abstained"] is False
    assert out["estimation_end_bar"] < out["event_bar"]
    assert out["gap_days"] == 20                    # (-10) - (-31) - 1
    est_end_pos = out["event_position"] - 31
    assert est_end_pos < out["event_position"] + out["window"][0]
    # The reported metadata is not the sample.  Pin the sample SIZE too: a slice that
    # reaches past the declared end is the realistic failure, and it changes only this.
    assert out["n_estimation_obs"] == (-31) - (-250) + 1


def test_the_fitted_sample_is_blind_to_every_bar_from_the_window_onward(calendar, tape):
    """The behavioural version of the module's headline PIT claim.

    Replace every bar from the event window's open onward with garbage.  Alpha, beta,
    r2 and sigma_estimation must be BIT-IDENTICAL, because none of those bars may
    touch the normal-return model.  A widened estimation slice — the realistic bug,
    since it changes no argument and trips no guard on the declared window — moves
    sigma by ~2x here and halves every downstream SCAR and BMP t-stat."""
    prices, bench = tape
    px = prices["BIO00"].copy()
    pos = 900
    clean = es.abnormal_returns(px, pos, benchmark=bench)
    assert clean["abstained"] is False

    poisoned = px.copy()
    poisoned.iloc[pos + clean["window"][0]:] *= np.linspace(
        1.0, 6.0, len(poisoned) - (pos + clean["window"][0]))
    out = es.abnormal_returns(poisoned, pos, benchmark=bench)
    for key in ("alpha", "beta", "r2", "sigma_estimation", "n_estimation_obs"):
        assert out[key] == clean[key], (key, out[key], clean[key])
    assert out["car"] != clean["car"]           # the EVENT window did move


def test_an_event_off_the_trading_calendar_anchors_on_the_preceding_bar(calendar, tape):
    """A Saturday readout is studied against Friday's close, never Monday's — the
    latter is the first look-ahead, and it is one ``side=`` keyword away."""
    prices, bench = tape
    saturday = pd.Timestamp("2016-06-11T12:00:00Z")      # 2016-06-11 is a Saturday
    out = es.abnormal_returns(prices["BIO00"], saturday, benchmark=bench)
    assert out["abstained"] is False
    assert out["event_bar"].startswith("2016-06-10")     # Friday, not Monday the 13th
    friday = es.abnormal_returns(prices["BIO00"],
                                 pd.Timestamp("2016-06-10T00:00:00Z"), benchmark=bench)
    assert out["event_position"] == friday["event_position"]


def test_moving_the_event_later_changes_the_estimate(calendar, tape):
    prices, bench = tape
    a = es.abnormal_returns(prices["BIO00"], calendar[900], benchmark=bench)
    b = es.abnormal_returns(prices["BIO00"], calendar[1200], benchmark=bench)
    assert a["beta"] != b["beta"]
    assert a["sigma_estimation"] != b["sigma_estimation"]
    assert a["car"] != b["car"]


def test_market_adjusted_fixes_beta_at_one_and_raw_needs_no_benchmark(calendar, tape):
    prices, bench = tape
    adj = es.abnormal_returns(prices["BIO00"], calendar[900], benchmark=bench,
                              model="market_adjusted")
    assert adj["beta"] == 1.0 and adj["alpha"] == 0.0 and adj["abstained"] is False
    raw = es.abnormal_returns(prices["BIO00"], calendar[900], model="raw")
    assert raw["abstained"] is False and raw["beta"] == 0.0
    missing = es.abnormal_returns(prices["BIO00"], calendar[900], model="market")
    assert missing["abstained"] and missing["reason"] == "benchmark_required_for_model"


def test_abnormal_returns_abstain_at_the_series_edges(calendar, tape):
    prices, bench = tape
    early = es.abnormal_returns(prices["BIO00"], 100, benchmark=bench)
    assert early["abstained"]
    assert early["reason"] == "estimation_window_truncated_at_series_start"
    late = es.abnormal_returns(prices["BIO00"], len(calendar) - 2, benchmark=bench)
    assert late["abstained"]
    assert late["reason"] == "event_window_truncated_at_series_edge"


def test_ar_window_covers_every_relative_day_and_car_is_their_sum(calendar, tape):
    prices, bench = tape
    out = es.abnormal_returns(prices["BIO00"], calendar[900], benchmark=bench,
                              window=(-3, 4))
    assert sorted(out["ar"]) == list(range(-3, 5))
    assert out["car"] == pytest.approx(sum(out["ar"].values()))


def test_every_declared_benchmark_leg_is_returned(calendar, tape):
    """SPY / XBI / IBB are sensitivity legs.  ALL of them come back."""
    prices, bench = tape
    rng = np.random.default_rng(2)
    legs = {
        "SPY": bench,
        "XBI": pd.Series(80.0 * np.cumprod(1 + rng.normal(0, 0.014, len(calendar))),
                         index=calendar),
        "IBB": pd.Series(90.0 * np.cumprod(1 + rng.normal(0, 0.012, len(calendar))),
                         index=calendar),
    }
    out = es.abnormal_returns_all_benchmarks(prices["BIO00"], calendar[900], legs)
    assert sorted(out["legs"]) == sorted(es.SENSITIVITY_BENCHMARKS)
    assert out["selection_policy"] == "all_legs_reported"
    cars = {k: v["car"] for k, v in out["legs"].items()}
    assert len({round(c, 10) for c in cars.values()}) == 3   # genuinely different legs


def test_there_is_no_benchmark_chooser_anywhere_in_the_module():
    """Benchmark shopping with a helper's name on it.  The omission is the control,
    so it is pinned rather than trusted."""
    chooser = re.compile(
        r"(best|choose|choos|select|pick|optimal|winning).*bench|bench.*"
        r"(best|choose|choos|select|pick|optimal|winning)", re.IGNORECASE)
    offenders = [n for n in dir(es) if chooser.search(n)]
    assert offenders == [], offenders
    tree = ast.parse(MODULE_SOURCE_PATH.read_text(encoding="utf-8"))
    defs = [n.name for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    assert [n for n in defs if chooser.search(n)] == []


# --------------------------------------------------------------------------- #
# cross-sectional tests — shape, abstention, and the BMP contract
# --------------------------------------------------------------------------- #
def test_bmp_abstains_rather_than_dividing_by_a_dead_sigma():
    rng = np.random.default_rng(21)
    ar = rng.normal(size=(30, 5)) * 0.02
    sigma = np.full(30, 0.02)
    sigma[0] = 0.0
    out = es.bmp_test(ar, sigma)
    assert out["abstained"] is False and out["n_dropped"] == 1 and out["n_events"] == 29

    out = es.bmp_test(ar[:1], sigma[:1])
    assert out["abstained"] and out["reason"] == "insufficient_events_lt_2"

    with pytest.raises(es.EventStudyError, match="entries for"):
        es.bmp_test(ar, sigma[:5])


def test_bmp_uses_a_student_t_not_a_normal():
    """N is small by construction here (the FLOOR is 50 events); the normal
    approximation over-rejects and the exact t is what keeps the size honest."""
    rng = np.random.default_rng(22)
    sigma = np.full(12, 0.02)
    ar = rng.normal(size=(12, 3)) * sigma[:, None] + 0.011
    out = es.bmp_test(ar, sigma)
    assert out["df"] == 11
    normal_p = 2.0 * (1.0 - es._norm_cdf(abs(out["t_stat"])))
    assert out["p_value"] > normal_p


def test_corrado_refuses_a_ranking_period_no_wider_than_the_window():
    rng = np.random.default_rng(23)
    mat = pd.DataFrame(rng.normal(size=(20, 12)), columns=list(range(-6, 6)))
    out = es.corrado_rank_test(mat, event_cols=list(range(-6, 6)))
    assert out["abstained"]
    assert out["reason"] == "ranking_period_not_wider_than_event_window"


def test_corrado_abstains_when_the_event_columns_cannot_be_identified():
    rng = np.random.default_rng(24)
    mat = pd.DataFrame(rng.normal(size=(20, 30)),
                       columns=[f"d{i}" for i in range(30)])
    out = es.corrado_rank_test(mat)
    assert out["abstained"] and out["reason"] == "event_columns_unidentified"


def test_corrado_defaults_to_the_event_day_when_columns_are_relative_days():
    rng = np.random.default_rng(25)
    cols = list(range(-40, 41))
    mat = pd.DataFrame(rng.normal(size=(30, len(cols))), columns=cols)
    out = es.corrado_rank_test(mat)
    assert out["abstained"] is False and out["event_cols"] == [0]


# --------------------------------------------------------------------------- #
# DNR:LAW-TIME-CLUSTERED-CI
# --------------------------------------------------------------------------- #
def test_issuer_only_clusters_are_refused_by_name():
    with pytest.raises(es.EventStudyError) as exc:
        es.clustered_bootstrap_ci([0.01] * 12,
                                  {"issuer_id": [f"T{i}" for i in range(12)]})
    assert "DNR:LAW-TIME-CLUSTERED-CI" in str(exc.value)
    assert "months, not tickers" in str(exc.value)


def test_a_bare_label_array_cannot_pass_as_a_cluster_key():
    with pytest.raises(es.EventStudyError, match="time or issuer identity"):
        es.clustered_bootstrap_ci([0.01] * 6, ["a", "a", "b", "b", "c", "c"])


def test_clustered_bootstrap_resamples_whole_clusters():
    """Within-cluster correlation must survive: a panel whose every cluster is
    internally identical cannot have a tighter interval than the cluster count
    supports.  Duplicating each event inside its cluster must NOT shrink the CI the
    way an event-level bootstrap would."""
    rng = np.random.default_rng(26)
    cluster_effect = rng.normal(0, 0.05, size=12)
    cars, dates, issuers = [], [], []
    for c in range(12):
        for k in range(5):
            cars.append(cluster_effect[c])          # perfectly correlated inside
            dates.append(f"2018-{c + 1:02d}")
            issuers.append(f"T{c * 5 + k}")
    wide = es.clustered_bootstrap_ci(cars, {"date_cluster": dates, "issuer_id": issuers},
                                     B=2000, seed=3)
    assert wide["n_time_clusters"] == 12
    assert wide["n_issuer_clusters"] == 60
    assert wide["effective_n"] == 12                # months, not tickers
    span = wide["ci"][2] - wide["ci"][0]
    per_event = es.clustered_bootstrap_ci(
        cars, {"date_cluster": [f"2018-{i:02d}" for i in range(1, 61)]},
        B=2000, seed=3)
    assert span > (per_event["ci"][2] - per_event["ci"][0])


def test_clustered_bootstrap_is_deterministic():
    rng = np.random.default_rng(27)
    cars = rng.normal(0, 0.03, 40)
    clusters = {"date_cluster": [f"2018-{1 + i % 10:02d}" for i in range(40)]}
    a = es.clustered_bootstrap_ci(cars, clusters, B=500, seed=5)
    b = es.clustered_bootstrap_ci(cars, clusters, B=500, seed=5)
    c = es.clustered_bootstrap_ci(cars, clusters, B=500, seed=6)
    assert a == b
    # ``a != c`` alone is satisfied by the echoed ``seed`` field, so an implementation
    # that ignores the seed entirely passes it.  Assert on the NUMBER.
    assert a["ci"] != c["ci"], (a["ci"], c["ci"])
    assert a["ci"] == b["ci"]


def test_the_clustered_interval_holds_its_nominal_size_at_the_build_floor():
    """The load-bearing calibration test for the one field a reader keys on.

    ``excludes_zero`` on a true mean of zero must fire ~5% of the time, and it must do
    so at the cluster counts this module's OWN build floor admits (20 date clusters) —
    a plain percentile interval on the resampled means rejects 7-9% there, which is
    not a rounding error, it is a headline that is wrong one time in twelve instead of
    one in twenty.  Fewer reps here than the shipped measurement, so the band is
    [0.5%, 9%]: wide enough for Monte-Carlo noise, narrow enough that the percentile
    interval this replaced (measured 6.9% / 8.3% at these two panels) would sit at its
    edge and a genuinely broken interval would blow straight through it."""
    for label, sizes in (("equal", [5] * 20),
                         ("ragged", [1, 2, 3, 4, 6, 8, 11, 12] * 2 + [5] * 4)):
        rng = np.random.default_rng(4242)
        hits = 0
        reps = 300
        for r in range(reps):
            cars, dates = [], []
            for g, s in enumerate(sizes):
                effect = rng.normal(0, 0.02)          # a whole-cluster common draw
                for value in effect + rng.normal(0, 0.02, int(s)):
                    cars.append(value)
                    dates.append(f"c{g:03d}")
            out = es.clustered_bootstrap_ci(cars, {"date_cluster": dates},
                                            B=400, seed=r)
            hits += int(out["excludes_zero"])
        size = hits / reps
        assert 0.005 <= size <= 0.09, f"{label} panel empirical size {size}"

    # POSITIVE CONTROL.  A size band with a low floor is also satisfied by an interval
    # that is simply always too wide to exclude anything, so a real effect must be
    # detected on the same machinery.
    rng = np.random.default_rng(909)
    hits = 0
    reps = 120
    for r in range(reps):
        cars, dates = [], []
        for g in range(20):
            effect = 0.030 + rng.normal(0, 0.02)
            for value in effect + rng.normal(0, 0.02, 5):
                cars.append(value)
                dates.append(f"c{g:03d}")
        hits += int(es.clustered_bootstrap_ci(cars, {"date_cluster": dates},
                                              B=400, seed=r)["excludes_zero"])
    assert hits / reps > 0.50, f"power at a true mean of +3% is only {hits / reps}"


def test_the_interval_is_studentized_and_says_which_critical_value_set_its_width():
    """Both critical values ride along, so a published width is auditable.  The
    effective-cluster floor is not decorative: a panel where one month carries most of
    the events must get a WIDER interval than the same events spread evenly, even
    though both have the same cluster count."""
    rng = np.random.default_rng(77)
    even_cars, even_dates = [], []
    for g in range(20):
        for value in rng.normal(0, 0.02) + rng.normal(0, 0.02, 5):
            even_cars.append(value)
            even_dates.append(f"c{g:03d}")
    even = es.clustered_bootstrap_ci(even_cars, {"date_cluster": even_dates},
                                     B=800, seed=3)
    lumpy_cars, lumpy_dates = [], []
    for g in range(20):
        size = 81 if g == 0 else 1
        for value in rng.normal(0, 0.02) + rng.normal(0, 0.02, size):
            lumpy_cars.append(value)
            lumpy_dates.append(f"c{g:03d}")
    lumpy = es.clustered_bootstrap_ci(lumpy_cars, {"date_cluster": lumpy_dates},
                                      B=800, seed=3)
    assert even["n_time_clusters"] == lumpy["n_time_clusters"] == 20
    assert even["effective_clusters_kish"] == pytest.approx(20.0, abs=0.01)
    assert lumpy["effective_clusters_kish"] < 3.0
    assert lumpy["q_used"] > even["q_used"] * 2
    assert lumpy["critical_source"] == "effective_cluster_t"
    assert set(even) >= {"q_bootstrap", "q_floor", "q_used", "cluster_robust_se"}
    assert even["q_used"] == max(even["q_bootstrap"], even["q_floor"])
    assert even["ci"][1] == even["mean_car"]


# --------------------------------------------------------------------------- #
# interval precision — never a midpoint
# --------------------------------------------------------------------------- #
def test_a_day_precision_event_is_a_point_study():
    policy = es.event_interval_policy(C.source_temporal_day("2018-03-05"))
    assert policy["mode"] == "point" and policy["abstained"] is False


def test_a_month_precision_event_abstains_without_interval_sensitivity():
    month = C.source_temporal_month(2018, 3)
    policy = es.event_interval_policy(month)
    assert policy["mode"] == "abstain"
    assert policy["reason"] == "interval_span_exceeds_threshold_without_sensitivity"
    assert policy["span_seconds"] > es.MAX_EVENT_SPAN_SECONDS


def test_a_month_precision_event_runs_across_the_whole_interval(calendar):
    month = C.source_temporal_month(2018, 3)
    policy = es.event_interval_policy(month, run_interval_sensitivity=True)
    assert policy["mode"] == "interval_sensitivity"
    anchors = es.interval_sensitivity_anchors(month, calendar)
    assert len(anchors) > 1
    # The WHOLE interval, first session to last — not a centre, not an endpoint.
    assert anchors[0].date().isoformat() == "2018-03-01"
    assert anchors[-1].date().isoformat() == "2018-03-30"
    mid = anchors[len(anchors) // 2]
    assert len([a for a in anchors if a != mid]) == len(anchors) - 1


def test_an_unbounded_temporal_is_not_study_eligible():
    unavailable = C.source_temporal_unavailable("issuer never stated a date")
    policy = es.event_interval_policy(unavailable)
    assert policy["mode"] == "abstain"
    assert policy["reason"] == "source_temporal_not_study_eligible"
    assert es.interval_sensitivity_anchors(unavailable, [pd.Timestamp("2018-01-02", tz="UTC")]) == []


def test_no_midpoint_imputation_exists_in_the_module():
    """Structural: nothing in the module is NAMED for, or COMPUTES, a span centre.

    The name scan alone is vacuous against the form the law actually forbids — a
    caller writes ``anchor = lower + (upper - lower) / 2`` and no identifier says
    "midpoint" anywhere.  So the arithmetic is scanned too: any division by 2 whose
    operand mentions a bound, or any ``(a + b) / 2``, has to justify itself.  The two
    legitimate halvings in the module (a binary-search pivot over ``bars`` and quarter
    arithmetic on a month number) are allow-listed BY OPERAND, not by line."""
    source = MODULE_SOURCE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    named = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            named.append(node.name)
        elif isinstance(node, ast.Name):
            named.append(node.id)
    assert [n for n in named if "midpoint" in n.lower() or "midpt" in n.lower()] == []

    bound_words = ("lower", "upper", "bound", "span", "start", "end", "cutoff",
                   "date", "moment", "temporal", "anchor", "event")
    offenders = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.BinOp)
                and isinstance(node.op, (ast.Div, ast.FloorDiv))):
            continue
        if not (isinstance(node.right, ast.Constant) and node.right.value == 2):
            continue
        operand = ast.unparse(node.left).lower()
        if any(word in operand for word in bound_words):
            offenders.append(ast.unparse(node))
    assert offenders == [], offenders


def test_event_bounds_preserve_the_source_span_exactly():
    month = C.source_temporal_month(2018, 3)
    lower, upper = es.event_bounds({"actual": month})
    assert lower.isoformat().startswith("2018-03-01")
    assert upper.isoformat().startswith("2018-03-31")


def test_a_plain_event_date_is_lifted_to_a_whole_day_span():
    lower, upper = es.event_bounds({"event_date": "2018-03-05"})
    assert lower.date().isoformat() == "2018-03-05"
    assert upper.date().isoformat() == "2018-03-05"
    assert upper > lower                       # a span, never a midnight instant


def test_an_event_with_no_temporal_field_is_refused():
    with pytest.raises(es.EventStudyError, match="no temporal span"):
        es.event_temporal({"event_id": "E1", "issuer_id": "BIO00"})


# --------------------------------------------------------------------------- #
# contamination / placebo / perturbation / matched controls
# --------------------------------------------------------------------------- #
def test_overlapping_events_on_the_same_issuer_are_flagged():
    events = [
        {"event_id": "A", "issuer_id": "BIO00", "event_date": "2018-03-05"},
        {"event_id": "B", "issuer_id": "BIO00", "event_date": "2018-03-09"},
        {"event_id": "C", "issuer_id": "BIO01", "event_date": "2018-03-07"},
        {"event_id": "D", "issuer_id": "BIO00", "event_date": "2019-01-04"},
    ]
    flags = es.flag_contamination(events, window=(-10, 10))
    flagged = {f["event_id"] for f in flags}
    assert flagged == {"A", "B"}
    assert flags[0]["contaminating_event_ids"] == ["B"]
    assert all(f["contaminated"] for f in flags)


def test_placebo_offsets_land_on_trading_days_and_zero_is_refused(calendar):
    events = [{"event_id": "A", "issuer_id": "BIO00", "event_date": "2010-06-15"}]
    rows = es.placebo_dates(events, offsets=(-40, 40), calendar=calendar)
    assert len(rows) == 2
    assert all(not r["abstained"] for r in rows)
    stamps = {pd.Timestamp(r["placebo_date"]) for r in rows}
    assert stamps <= set(calendar)
    with pytest.raises(es.EventStudyError, match="not a placebo"):
        es.placebo_dates(events, offsets=(0, 5), calendar=calendar)


def test_placebo_off_calendar_abstains_by_name(calendar):
    events = [{"event_id": "A", "issuer_id": "BIO00",
               "event_date": calendar[2].date().isoformat()}]
    rows = es.placebo_dates(events, offsets=(-50,), calendar=calendar)
    assert rows[0]["abstained"] and rows[0]["reason"] == "placebo_offset_off_calendar"


def test_perturbation_slides_the_whole_span_and_refuses_zero():
    events = [{"event_id": "A", "issuer_id": "BIO00", "actual": C.source_temporal_month(2018, 3)}]
    rows = es.perturb_event_dates(events, deltas=(-5, 5))
    assert len(rows) == 2
    for row in rows:
        lower = pd.Timestamp(row["perturbed_lower"])
        upper = pd.Timestamp(row["perturbed_upper"])
        src_lo = pd.Timestamp(row["source_event_lower"])
        src_hi = pd.Timestamp(row["source_event_upper"])
        assert (lower - src_lo) == (upper - src_hi)      # the span moves as a unit
        assert (upper - lower) == (src_hi - src_lo)      # and keeps its width
    with pytest.raises(es.EventStudyError, match="not a perturbation"):
        es.perturb_event_dates(events, deltas=(0,))


def test_matched_controls_respect_the_caliper_and_are_deterministic():
    candidates = [{"candidate_id": f"C{i}", "mcap": 100 + i, "adv": 5.0}
                  for i in range(10)]
    events = [{"event_id": "E1", "mcap": 103, "adv": 5.0},
              {"event_id": "E2", "mcap": 103, "adv": 5.0},
              {"event_id": "E3", "mcap": 9000, "adv": 5.0},
              {"event_id": "E4", "adv": 5.0}]
    rows = es.matched_controls(events, candidates, on=["mcap", "adv"],
                               tolerance={"mcap": 2.0, "adv": 0.5})
    by_id = {r["event_id"]: r for r in rows}
    assert by_id["E1"]["matched"] and by_id["E2"]["matched"]
    assert by_id["E1"]["control_id"] != by_id["E2"]["control_id"]   # no replacement
    assert by_id["E3"]["reason"] == "no_candidate_inside_caliper"
    assert by_id["E4"]["reason"] == "event_missing_covariate"
    assert rows == es.matched_controls(events, candidates, on=["mcap", "adv"],
                                       tolerance={"mcap": 2.0, "adv": 0.5})
    with pytest.raises(es.EventStudyError, match="caliper"):
        es.matched_controls(events, candidates, on=["mcap"], tolerance=0.0)


# --------------------------------------------------------------------------- #
# build floors, cohort accounting, era split
# --------------------------------------------------------------------------- #
def test_build_floors_name_the_failing_floor_and_the_observed_count(cohort):
    report = es.check_build_floors(cohort[:10])
    assert report["floors_passed"] is False
    failed = {f["floor"]: f for f in report["failed_floors"]}
    assert set(failed) == {"min_events", "min_issuers", "min_date_clusters"}
    assert failed["min_events"] == {"floor": "min_events", "required": 50, "observed": 10}
    assert report["floors_are"] == "descriptive_build_floors_not_promotion_gates"
    assert es.check_build_floors(cohort)["floors_passed"] is True


def test_a_caller_supplied_floor_overlays_the_defaults_and_says_it_relaxed_them(cohort):
    """``floors={}`` used to switch every floor OFF and still report
    ``floors_passed: True`` — the one field a downstream reader is told to key on.
    Three events, one issuer, one month were then indistinguishable from a fifty-event
    cohort."""
    thin = [{"event_id": f"E{i}", "issuer_id": "ACME", "event_date": "2024-01-05"}
            for i in range(3)]
    empty = es.check_build_floors(thin, floors={})
    assert empty["floors"] == es.BUILD_FLOORS          # {} overlays nothing
    assert empty["floors_passed"] is False

    partial = es.check_build_floors(cohort, floors={"min_events": 55})
    assert partial["floors"]["min_issuers"] == es.BUILD_FLOORS["min_issuers"]
    assert partial["floors_relaxed"] == []
    assert partial["floors_are_default"] is False      # raised, but not default

    relaxed = es.check_build_floors(
        thin, floors={"min_events": 3, "min_issuers": 1, "min_date_clusters": 1})
    assert relaxed["floors_passed"] is True
    assert relaxed["floors_passed_at_default"] is False
    assert {f["floor"] for f in relaxed["floors_relaxed"]} == set(es.BUILD_FLOORS)
    assert {"floor": "min_events", "default": 50, "used": 3} in relaxed["floors_relaxed"]
    assert sorted(relaxed["failed_floors_at_default"]) == sorted(es.BUILD_FLOORS)


def test_an_undateable_event_does_not_clear_a_floor_it_cannot_be_studied_under():
    """An unbounded span counts toward ``min_events`` but contributes no date cluster,
    and the estimator drops it anyway — so the floors read the STUDYABLE rows."""
    dated = [{"event_id": f"D{i}", "issuer_id": f"BIO{i:02d}",
              "actual": C.source_temporal_day(f"2018-0{1 + i % 9}-05")} for i in range(5)]
    ghosts = [{"event_id": f"G{i}", "issuer_id": f"GHO{i:02d}",
               "actual": C.source_temporal_unavailable("issuer never stated a date")}
              for i in range(60)]
    counts = es.cohort_counts(dated + ghosts)
    assert counts["n_events"] == 65
    assert counts["n_events_bounded"] == 5
    assert counts["n_issuers"] == 65 and counts["n_issuers_bounded"] == 5
    report = es.check_build_floors(dated + ghosts)
    failed = {f["floor"]: f["observed"] for f in report["failed_floors"]}
    assert failed["min_events"] == 5          # not 65
    assert failed["min_issuers"] == 5         # not 65


def test_events_in_one_cluster_are_never_counted_as_independent():
    """Forty readouts from one issuer in one month are not forty draws."""
    events = [{"event_id": f"E{i}", "issuer_id": "BIO00", "event_date": "2018-03-05"}
              for i in range(40)]
    counts = es.cohort_counts(events)
    assert counts["n_events"] == 40
    assert counts["n_issuers"] == 1
    assert counts["n_date_clusters"] == 1
    assert counts["effective_n"] == 1


def test_effective_n_is_the_scarcer_of_issuers_and_date_clusters(cohort):
    counts = es.cohort_counts(cohort)
    assert counts["effective_n"] == min(counts["n_issuers"], counts["n_date_clusters"])
    assert counts["effective_n"] < counts["n_events"]


def test_era_split_returns_both_eras_when_the_panel_spans_the_break(cohort):
    split = es.era_split(cohort)
    assert split["law"] == "DNR:LAW-ERA-SPLIT"
    assert split["n_pre_2010"] > 0 and split["n_post_2010"] > 0
    assert split["era_split_available"] is True
    assert "Era split applied" in split["disclosure"]


def test_a_post_2010_only_panel_discloses_the_missing_regime():
    events = [{"event_id": f"E{i}", "issuer_id": f"BIO{i:02d}",
               "event_date": f"201{5 + i % 4}-06-0{1 + i % 8}"} for i in range(20)]
    split = es.era_split(events)
    assert split["pre_2010"] == []              # not a fabricated second era
    assert split["n_post_2010"] == 20
    assert split["era_split_available"] is False
    assert "UNMEASURED" in split["disclosure"]
    assert f"No pre-{es.ERA_BREAK_YEAR} evidence" in split["disclosure"]


def test_an_event_straddling_the_break_is_assignable_to_neither_era():
    events = [{"event_id": "S", "issuer_id": "BIO00",
               "actual": C.source_temporal_year(2010 - 1 + 1)},
              {"event_id": "R", "issuer_id": "BIO01",
               "actual": C.source_temporal_range("2009-12-20T00:00:00Z",
                                                 "2010-01-20T00:00:00Z",
                                                 original_value="late 2009 / early 2010")}]
    split = es.era_split(events)
    assert "R" in split["unassignable"]
    assert split["n_unassignable"] >= 1


# --------------------------------------------------------------------------- #
# family registration — no winner out of an unregistered search
# --------------------------------------------------------------------------- #
@pytest.fixture()
def ledger(tmp_path) -> TrialLedger:
    return TrialLedger(path=tmp_path / "trial_ledger.jsonl")


def test_inspecting_a_winner_without_registration_raises(ledger):
    with pytest.raises(es.UnregisteredSearchFamily, match="never registered"):
        es.inspect_winner({"cfg_a": 1.0, "cfg_b": 2.0}, ledger=ledger,
                          family="biopharma_event_window")


def test_registering_the_family_first_unlocks_the_winner(ledger):
    configs = [{"window": w} for w in (5, 10, 20, 30)]
    reg = es.register_search_family(ledger, "biopharma_event_window", configs)
    assert reg["registered"] and reg["n_configs"] == 4 and reg["effective_n"] == 4
    out = es.inspect_winner({"cfg_a": 1.0, "cfg_b": 2.0}, ledger=ledger,
                            family="biopharma_event_window")
    assert out["winner"] == "cfg_b"
    assert out["effective_n"] == 4               # the budget travels with the number


def test_registration_is_idempotent_and_needs_a_family(ledger):
    configs = [{"window": w} for w in (5, 10)]
    es.register_search_family(ledger, "fam", configs)
    again = es.register_search_family(ledger, "fam", configs)
    assert again["n_newly_distinct"] == 0 and again["effective_n"] == 2
    with pytest.raises(es.EventStudyError, match="non-empty family"):
        es.register_search_family(ledger, "", configs)
    with pytest.raises(es.EventStudyError, match="at least one config"):
        es.register_search_family(ledger, "fam", [])


def test_registration_writes_the_leakage_audit_stamp(ledger, tmp_path):
    """``info_cutoff`` is what lets a later leakage audit check the config could not
    have peeked ahead.  The wrapper dropped it, so every row this module wrote carried
    ``info_cutoff: null`` and the audit was permanently unavailable."""
    reg = es.register_search_family(ledger, "fam", [{"w": 5}, {"w": 10}],
                                    info_cutoff="2018-12-31T00:00:00Z",
                                    note="pre-registered at generation")
    assert reg["info_cutoff"] == "2018-12-31T00:00:00Z"
    rows = [json.loads(line) for line in
            ledger.path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert rows and all(r["info_cutoff"] == "2018-12-31T00:00:00Z" for r in rows)
    assert all(r["note"] == "pre-registered at generation" for r in rows)


def test_the_winner_reader_refuses_to_rank_the_sensitivity_benchmarks(ledger):
    """``inspect_winner`` is a generic argmax, and a generic argmax fed SPY/XBI/IBB is
    the benchmark chooser the module says it does not contain — a registered family
    would otherwise buy benchmark shopping with a receipt attached."""
    es.register_search_family(ledger, "bench_family",
                              [{"benchmark": b} for b in es.SENSITIVITY_BENCHMARKS])
    with pytest.raises(es.EventStudyError, match="sensitivity benchmarks"):
        es.inspect_winner({"SPY": 0.01, "XBI": 0.04, "IBB": 0.02},
                          ledger=ledger, family="bench_family")
    with pytest.raises(es.EventStudyError, match="sensitivity benchmarks"):
        es.inspect_winner({"cfg_a": 1.0, "xbi": 2.0},
                          ledger=ledger, family="bench_family")
    # A genuine config family is untouched.
    assert es.inspect_winner({"cfg_a": 1.0, "cfg_b": 2.0}, ledger=ledger,
                             family="bench_family")["winner"] == "cfg_b"


def test_a_missing_ledger_is_an_unregistered_family():
    assert es.family_is_registered(None, "fam") is False
    with pytest.raises(es.UnregisteredSearchFamily):
        es.inspect_winner({"a": 1.0}, ledger=None, family="fam")


# --------------------------------------------------------------------------- #
# estimate_reaction — ESTIMAND 1
# --------------------------------------------------------------------------- #
def test_estimate_reaction_reports_every_leg_and_every_count(tape, cohort):
    prices, bench = tape
    rng = np.random.default_rng(41)
    idx = bench.index
    xbi = pd.Series(80.0 * np.cumprod(1 + rng.normal(0, 0.014, len(idx))), index=idx)
    out = es.estimate_reaction(prices, cohort, benchmarks={"SPY": bench, "XBI": xbi},
                               B=400, seed=7)
    assert out["estimand"] == "ex_post_reaction" and out["is_tradable"] is False
    assert out["abstained"] is False
    assert sorted(out["legs"]) == ["SPY", "XBI"]
    assert out["selection_policy"] == "all_legs_reported"
    for name in ("n_events", "n_issuers", "n_date_clusters", "effective_n"):
        assert name in out
    for leg in out["legs"].values():
        assert leg["bmp"]["abstained"] is False
        assert leg["corrado_rank"]["abstained"] is False
        assert leg["clustered_ci"]["abstained"] is False
        assert leg["clustered_ci"]["law"] == "DNR:LAW-TIME-CLUSTERED-CI"
    assert out["era"]["law"] == "DNR:LAW-ERA-SPLIT"
    assert out["legs"]["SPY"]["mean_car"] != out["legs"]["XBI"]["mean_car"]


def test_bmp_is_given_the_event_window_and_nothing_else(tape, cohort):
    """The law is enforced on ``bmp_test``'s SIGNATURE (it tests whatever matrix it is
    handed); this is the call site's half.  Handing it the ranking period as well is
    invisible under ``model="market"`` — OLS residuals sum to zero, so the CAR is
    unchanged and the t is scale-invariant — and FLIPS the answer under
    ``market_adjusted``, which is why this runs on the non-market model."""
    prices, bench = tape
    window = (-4, 4)
    out = es.estimate_reaction(prices, cohort, benchmarks={"SPY": bench},
                               model="market_adjusted", window=window,
                               B=200, seed=7)
    leg = out["legs"]["SPY"]
    assert leg["bmp"]["window_len"] == window[1] - window[0] + 1
    # And the number itself: rebuild the event-window matrix by hand and re-run.
    rows, sigmas = [], []
    for res in leg["per_event"]:
        if res.get("abstained"):
            continue
        rows.append([res["ar"][d] for d in range(window[0], window[1] + 1)])
        sigmas.append(res["sigma_estimation"])
    assert len(rows) == leg["n_estimated"] >= 2
    assert es.bmp_test(np.array(rows), sigmas) == leg["bmp"]


def test_the_clustered_ci_is_given_the_calendar_clusters_not_the_issuers(tape, cohort):
    """``DNR:LAW-TIME-CLUSTERED-CI`` is enforced on the API, which a call site can
    evade by passing issuer labels under the ``date_cluster`` key.  On this cohort the
    two counts diverge (60 months, 25 issuers), so the interval's own cluster count is
    the check."""
    prices, bench = tape
    out = es.estimate_reaction(prices, cohort, benchmarks={"SPY": bench},
                               B=200, seed=7)
    assert out["n_date_clusters"] != out["n_issuers"]
    ci = out["legs"]["SPY"]["clustered_ci"]
    assert ci["n_time_clusters"] == out["n_date_clusters"]
    assert ci["n_time_clusters"] != out["n_issuers"]
    assert ci["n_issuer_clusters"] == out["n_issuers"]
    # One definition of effective_n across the payload: the scarcer of the two.
    assert ci["effective_n"] == min(ci["n_time_clusters"], ci["n_issuer_clusters"])
    assert ci["effective_n"] == out["effective_n"]


def test_contaminated_events_are_dropped_rather_than_flagged_and_pooled(tape, calendar):
    """A flag computed into the payload and then ignored is decoration.  An event
    whose window overlaps another event on the same issuer is not a reaction to this
    catalyst, and pooling it into the cohort mean is how a strong-looking result turns
    out to be one issuer announcing twice in a fortnight."""
    prices, bench = tape
    issuers = sorted(prices)
    events = [{"event_id": f"E{k:03d}", "issuer_id": issuers[k % len(issuers)],
               "event_date": calendar[600 + k * 40].date().isoformat()}
              for k in range(60)]
    twin = dict(events[0])
    twin["event_id"] = "E000_TWIN"
    twin["event_date"] = calendar[603].date().isoformat()   # 3 bars from E000
    out = es.estimate_reaction(prices, events + [twin], benchmarks={"SPY": bench},
                               B=200, seed=7)
    flagged = {row["event_id"] for row in out["contamination"]}
    assert flagged == {"E000", "E000_TWIN"}
    assert out["n_contaminated"] == 2
    assert out["contamination_policy"] == "excluded_from_pooled_statistics"
    dropped = {d["event_id"]: d["reason"] for d in out["dropped_events"]}
    assert dropped["E000"] == "contaminated_by_overlapping_event"
    assert dropped["E000_TWIN"] == "contaminated_by_overlapping_event"
    estimated = {r["event_id"] for r in out["legs"]["SPY"]["per_event"]}
    assert flagged & estimated == set()
    assert out["n_events"] == 59

    pooled = es.estimate_reaction(prices, events + [twin], benchmarks={"SPY": bench},
                                  B=200, seed=7, exclude_contaminated=False)
    assert pooled["contamination_policy"] == "pooled_in_deliberately_by_caller"
    assert pooled["n_events"] == 61
    assert pooled["legs"]["SPY"]["mean_car"] != out["legs"]["SPY"]["mean_car"]


def test_n_events_supplied_is_right_for_a_one_shot_iterable(tape, cohort):
    """``len(list(events))`` on an already-consumed iterable reported 0 supplied
    events beside a 60-event result — a disclosure field that fails open."""
    prices, bench = tape
    out = es.estimate_reaction(prices, (e for e in cohort), benchmarks={"SPY": bench},
                               B=100, seed=7)
    assert out["n_events_supplied"] == 60
    assert out["n_events"] == 60


def test_select_winner_stamps_the_multiple_testing_budget_on_the_result(tape, cohort, ledger):
    prices, bench = tape
    es.register_search_family(ledger, "fam", [{"w": w} for w in (5, 10, 20)])
    out = es.estimate_reaction(prices, cohort, benchmarks={"SPY": bench}, B=100,
                               select_winner=True, ledger=ledger, family="fam")
    assert out["search_family"]["family"] == "fam"
    assert out["search_family"]["effective_n"] == 3
    plain = es.estimate_reaction(prices, cohort, benchmarks={"SPY": bench}, B=100)
    assert plain["search_family"] is None


def test_estimate_reaction_abstains_below_a_build_floor(tape, cohort):
    prices, bench = tape
    out = es.estimate_reaction(prices, cohort[:12], benchmarks={"SPY": bench},
                               B=100, seed=7)
    assert out["abstained"] is True
    assert out["reason"].startswith("build_floor_not_met:")
    assert "min_events(12<50)" in out["reason"]
    assert out["legs"] == {}
    assert out["build_floors"]["failed_floors"]


def test_estimate_reaction_drops_interval_precision_events_by_name(tape, cohort):
    prices, bench = tape
    wide = dict(cohort[0])
    wide.pop("event_date")
    wide["actual"] = C.source_temporal_month(2010, 6)
    out = es.estimate_reaction(prices, [wide] + cohort[1:], benchmarks={"SPY": bench},
                               B=100, seed=7)
    dropped = {d["event_id"]: d for d in out["dropped_events"]}
    assert cohort[0]["event_id"] in dropped
    assert dropped[cohort[0]["event_id"]]["reason"] == (
        "interval_span_exceeds_threshold_without_sensitivity")
    assert out["n_events"] == 59


def test_estimate_reaction_is_deterministic(tape, cohort):
    prices, bench = tape
    a = es.estimate_reaction(prices, cohort, benchmarks={"SPY": bench}, B=300, seed=4)
    b = es.estimate_reaction(prices, cohort, benchmarks={"SPY": bench}, B=300, seed=4)
    assert a == b


def test_estimate_reaction_refuses_a_winner_from_an_unregistered_family(tape, cohort, ledger):
    prices, bench = tape
    with pytest.raises(es.UnregisteredSearchFamily):
        es.estimate_reaction(prices, cohort, benchmarks={"SPY": bench}, B=100,
                             select_winner=True, ledger=ledger, family="unregistered")
    es.register_search_family(ledger, "registered", [{"w": 10}])
    out = es.estimate_reaction(prices, cohort, benchmarks={"SPY": bench}, B=100,
                               select_winner=True, ledger=ledger, family="registered")
    assert out["abstained"] is False


def test_a_missing_price_series_abstains_per_event_rather_than_crashing(tape, cohort):
    prices, bench = tape
    partial = {k: v for k, v in prices.items() if k != "BIO00"}
    out = es.estimate_reaction(partial, cohort, benchmarks={"SPY": bench}, B=100, seed=7)
    reasons = {r.get("reason") for r in out["legs"]["SPY"]["per_event"]}
    assert "no_price_series_for_issuer" in reasons
    assert out["abstained"] is False


# --------------------------------------------------------------------------- #
# forecast_ex_ante — ESTIMAND 2, and the wall between the two
# --------------------------------------------------------------------------- #
def _ex_ante(calendar, **overrides):
    kwargs = dict(
        event={"event_id": "E001", "issuer_id": "BIO00", "event_date": "2016-06-10"},
        features={"adv": {"value": 1e6, "known_at": "2016-05-30T00:00:00Z"},
                  "float": {"value": 2e7, "known_at": "2016-05-31T00:00:00Z"}},
        decision_cutoff="2016-06-01T12:00:00Z",
        trading_bars=calendar,
        risk_set=["BIO00", "BIO01"],
        event_policy={"kind": "pdufa", "status": "scheduled"},
        outcome_policy={"grade": "fwd_20d_car", "benchmark": "XBI"},
    )
    kwargs.update(overrides)
    return es.forecast_ex_ante(**kwargs)


def test_ex_ante_row_freezes_everything_it_promises(calendar):
    row = _ex_ante(calendar)
    assert row["estimand"] == "ex_ante_tradable" and row["is_tradable"] is True
    assert row["abstained"] is False
    assert row["prediction_issued_at"] == "2016-06-01T12:00:00Z"   # no wall clock
    assert row["feature_snapshot"] == {"adv": 1e6, "float": 2e7}
    assert len(row["feature_snapshot_hash"]) == 64
    assert row["risk_set"] == ["BIO00", "BIO01"]
    assert row["event_policy"]["kind"] == "pdufa"
    assert row["outcome_policy"]["grade"] == "fwd_20d_car"
    assert row["availability_receipt"]["schema"] == es.AVAILABILITY_RECEIPT_SCHEMA
    assert row["execution_bar"] == "2016-06-02T00:00:00Z"


def test_ex_ante_rows_are_identical_across_calls(calendar):
    assert _ex_ante(calendar) == _ex_ante(calendar)


def test_a_changed_feature_value_changes_the_snapshot_hash(calendar):
    base = _ex_ante(calendar)
    moved = _ex_ante(calendar, features={
        "adv": {"value": 1.5e6, "known_at": "2016-05-30T00:00:00Z"},
        "float": {"value": 2e7, "known_at": "2016-05-31T00:00:00Z"}})
    assert base["feature_snapshot_hash"] != moved["feature_snapshot_hash"]


def test_a_feature_known_after_the_cutoff_is_a_leak(calendar):
    row = _ex_ante(calendar, features={
        "adv": {"value": 1e6, "known_at": "2016-05-30T00:00:00Z"},
        "peek": {"value": 3.0, "known_at": "2016-06-09T00:00:00Z"}})
    assert row["abstained"] is True
    assert row["reason"] == "feature_known_after_decision_cutoff:['peek']"
    assert row["leaking_features"] == ["peek"]
    assert "peek" not in row["feature_snapshot"]


def test_a_realized_outcome_feature_is_refused_whatever_its_timestamp(calendar):
    row = _ex_ante(calendar, features={
        "realized_return": {"value": 0.4, "known_at": "1999-01-01T00:00:00Z"}})
    assert row["abstained"] is True
    assert row["reason"].startswith("realized_outcome_in_feature_cut")
    assert row["realized_outcome_features_refused"] == ["realized_return"]


def test_a_feature_with_no_known_at_is_refused(calendar):
    with pytest.raises(es.EventStudyError, match="no known_at"):
        _ex_ante(calendar, features={"adv": {"value": 1e6}})


def test_a_late_available_fact_pushes_the_ex_ante_execution_bar(calendar):
    """Published before the cutoff, AVAILABLE after it: the feature is legal, and
    execution still has to wait."""
    early = _ex_ante(calendar)
    late = _ex_ante(calendar, features={
        "adv": {"value": 1e6, "known_at": "2016-05-30T00:00:00Z"},
        "float": {"value": 2e7, "known_at": "2016-05-31T00:00:00Z",
                  "published": "2016-05-31T00:00:00Z",
                  "available_at": "2016-06-08T21:00:00Z"}})
    assert late["abstained"] is False
    assert late["execution_bar"] > early["execution_bar"]
    assert late["availability_receipt"]["binding_source"]["fact_id"] == "float"
    assert late["availability_receipt"]["binding_source"]["key"] == "available_at"


def test_a_decision_cutoff_after_the_event_is_refused(calendar):
    """THE front-door leak.  ``known_at <= cutoff`` is vacuous if the caller picks the
    cutoff: a cutoff three weeks after the readout makes the realized post-event move
    a legal feature, and the row comes back clean, non-abstaining and
    ``is_tradable: True``.  Nothing about the feature is suspicious — the relation
    between the cutoff and the event is what has to be checked."""
    row = es.forecast_ex_ante(
        event={"event_id": "E1", "issuer_id": "ACME", "event_date": "2016-06-10"},
        features={"price_move_since_readout":
                  {"value": 0.42, "known_at": "2016-06-20T00:00:00Z"}},
        decision_cutoff="2016-06-24T00:00:00Z", trading_bars=calendar,
        risk_set=["ACME"], event_policy={}, outcome_policy={})
    assert row["abstained"] is True
    assert row["reason"].startswith("decision_cutoff_not_before_event:")
    assert row["is_tradable"] is True          # the estimand's claim, now unusable
    assert row["execution_bar"] is None


def test_the_cutoff_must_precede_the_event_by_a_strictly_positive_margin(calendar):
    """The boundary, in both directions: an event-day cutoff is refused (the event's
    span opens at midnight and a decision taken during it is not ex-ante), and one
    second earlier is accepted."""
    common = dict(
        event={"event_id": "E1", "issuer_id": "ACME", "event_date": "2016-06-10"},
        features={"adv": {"value": 1e6, "known_at": "2016-06-01T00:00:00Z"}},
        trading_bars=calendar, risk_set=["ACME"], event_policy={}, outcome_policy={})
    at_open = es.forecast_ex_ante(decision_cutoff="2016-06-10T00:00:00Z", **common)
    assert at_open["abstained"] is True
    assert at_open["reason"].startswith("decision_cutoff_not_before_event:")
    just_before = es.forecast_ex_ante(
        decision_cutoff="2016-06-09T23:59:59Z", **common)
    assert just_before["abstained"] is False


def test_the_feature_leak_boundary_is_the_cutoff_itself(calendar):
    """One second, not one week.  The original leak test used an 8-day margin, so any
    tolerance under 8 days — or an off-by-one that rejects a feature known exactly at
    the cutoff — was invisible."""
    one_second_late = _ex_ante(calendar, features={
        "adv": {"value": 1e6, "known_at": "2016-05-30T00:00:00Z"},
        "peek": {"value": 3.0, "known_at": "2016-06-01T12:00:01Z"}})
    assert one_second_late["abstained"] is True
    assert one_second_late["leaking_features"] == ["peek"]

    exactly_at = _ex_ante(calendar, features={
        "adv": {"value": 1e6, "known_at": "2016-05-30T00:00:00Z"},
        "edge": {"value": 3.0, "known_at": "2016-06-01T12:00:00Z"}})
    assert exactly_at["abstained"] is False, exactly_at["reason"]
    assert exactly_at["feature_snapshot"]["edge"] == 3.0


@pytest.mark.parametrize("name", [
    "outcome", "actual_outcome_pdufa", "realized_car_5d", "trial_result",
    "post_event_car", "car_20d", "pdufa_resolution_flag", "restated_cash",
])
def test_a_realized_outcome_is_refused_however_it_is_spelled(calendar, name):
    """Exact-name equality refused ``outcome`` and waved through every spelling a real
    feature table would actually use."""
    row = _ex_ante(calendar, features={
        name: {"value": 1.0, "known_at": "2016-05-30T00:00:00Z"}})
    assert row["abstained"] is True, name
    assert row["reason"].startswith("realized_outcome_in_feature_cut")
    assert row["realized_outcome_features_refused"] == [name]
    assert row["realized_outcome_matches"][0]["matched"] in es.REALIZED_OUTCOME_KEYS


@pytest.mark.parametrize("name", ["cash_runway", "adv_20d", "carve_out_value",
                                  "float_shares", "days_to_pdufa"])
def test_an_innocent_feature_name_is_not_swept_up(calendar, name):
    row = _ex_ante(calendar, features={
        name: {"value": 1.0, "known_at": "2016-05-30T00:00:00Z"}})
    assert row["abstained"] is False, (name, row["reason"])


def test_the_realized_outcome_guard_cannot_be_switched_off_by_the_caller(calendar):
    """``forbidden_keys`` ADDS to the module's set; it does not replace it.  As a
    replacement, ``forbidden_keys=()`` accepted a feature literally named
    ``outcome``."""
    row = _ex_ante(calendar, forbidden_keys=(), features={
        "outcome": {"value": 1.0, "known_at": "2016-05-30T00:00:00Z"}})
    assert row["abstained"] is True
    assert row["realized_outcome_features_refused"] == ["outcome"]
    extra = _ex_ante(calendar, forbidden_keys=("insider_tip",), features={
        "insider_tip": {"value": 1.0, "known_at": "2016-05-30T00:00:00Z"}})
    assert extra["abstained"] is True
    assert extra["realized_outcome_features_refused"] == ["insider_tip"]


def test_a_value_restated_after_the_cutoff_is_refused_not_absorbed(calendar):
    """The canonical point-in-time failure: a revision keeps the ORIGINAL
    ``known_at``, so every timestamp check passes and the feature cut silently carries
    a number nobody had.  The snapshot hash makes it detectable only to a caller who
    stored the earlier hash, and nothing in the module stores one."""
    original = _ex_ante(calendar, features={
        "cash_runway": {"value": 18.0, "known_at": "2016-05-20T00:00:00Z"}})
    assert original["abstained"] is False

    restated = _ex_ante(calendar, features={
        "cash_runway": {"value": 4.0, "known_at": "2016-05-20T00:00:00Z",
                        "revised_at": "2016-06-30T00:00:00Z"}})
    assert restated["abstained"] is True
    assert restated["reason"] == "revision_after_decision_cutoff:['cash_runway']"
    assert restated["revised_features_refused"][0]["key"] == "revised_at"

    # A revision that landed BEFORE the cutoff is legitimate point-in-time data.
    in_time = _ex_ante(calendar, features={
        "cash_runway": {"value": 4.0, "known_at": "2016-05-20T00:00:00Z",
                        "vintage": "2016-05-25T00:00:00Z"}})
    assert in_time["abstained"] is False
    assert in_time["feature_snapshot"]["cash_runway"] == 4.0


def test_a_feature_whose_availability_is_a_span_still_moves_the_execution_bar(calendar):
    """``earliest_executable_bar`` reads ``source_temporal.upper_bound`` as an
    availability stamp.  ``forecast_ex_ante`` rebuilt each fact from four flat keys and
    dropped the span, so a feature that was only available days later executed at the
    cutoff bar — the exact 'price nobody could have paid' the receipt exists to
    prevent."""
    early = _ex_ante(calendar)
    spanned = _ex_ante(calendar, features={
        "adv": {"value": 1e6, "known_at": "2016-05-30T00:00:00Z"},
        "float": {"value": 2e7, "known_at": "2016-05-31T00:00:00Z",
                  "source_temporal": C.source_temporal_day("2016-06-08")}})
    assert spanned["abstained"] is False
    assert spanned["execution_bar"] > early["execution_bar"]
    binding = spanned["availability_receipt"]["binding_source"]
    assert binding == {"kind": "fact", "fact_index": 1,
                       "key": "source_temporal.upper_bound", "fact_id": "float"}


def test_the_two_estimands_do_not_share_a_code_path():
    """Structural, not aspirational.  ``forecast_ex_ante`` must not reach the ex-post
    machinery — the realistic failure is a shared helper that grows one convenient
    argument, and a comment does not stop that."""
    tree = ast.parse(MODULE_SOURCE_PATH.read_text(encoding="utf-8"))
    bodies = {n.name: n for n in ast.walk(tree)
              if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    assert "forecast_ex_ante" in bodies and "estimate_reaction" in bodies

    def called(fn: ast.AST) -> set[str]:
        names: set[str] = set()
        for node in ast.walk(fn):
            if isinstance(node, ast.Call):
                target = node.func
                if isinstance(target, ast.Name):
                    names.add(target.id)
                elif isinstance(target, ast.Attribute):
                    names.add(target.attr)
        return names

    ex_post_only = {"estimate_reaction", "abnormal_returns",
                    "abnormal_returns_all_benchmarks", "bmp_test", "corrado_rank_test",
                    "clustered_bootstrap_ci", "_ar_slice", "_as_matrix"}
    assert called(bodies["forecast_ex_ante"]) & ex_post_only == set()
    assert "forecast_ex_ante" not in called(bodies["estimate_reaction"])


def test_the_ex_post_estimator_never_claims_to_be_tradable(tape, cohort):
    prices, bench = tape
    out = es.estimate_reaction(prices, cohort[:5], benchmarks={"SPY": bench}, B=50)
    assert out["is_tradable"] is False
    assert out["estimand"] == "ex_post_reaction"


# --------------------------------------------------------------------------- #
# package wiring
# --------------------------------------------------------------------------- #
def test_the_package_exposes_event_study_lazily_without_widening_star_imports():
    import engine.seasonality as pkg

    assert pkg.event_study is es
    assert "event_study" not in pkg.__all__
    with pytest.raises(AttributeError):
        pkg.definitely_not_a_module


def test_every_public_symbol_is_exported():
    missing = [n for n in es.__all__ if not hasattr(es, n)]
    assert missing == []
    assert "SENSITIVITY_BENCHMARKS" in es.__all__
    assert es.SENSITIVITY_BENCHMARKS == ("SPY", "XBI", "IBB")
    assert es.BUILD_FLOORS == {"min_events": 50, "min_issuers": 20,
                               "min_date_clusters": 20}
    assert es.ERA_BREAK_YEAR == 2010
