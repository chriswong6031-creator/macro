"""Tests for engine/local_projections.py.

A results table cannot show whether an estimator's guards actually bind - only a
test that perturbs the embargoed bars, forces a degenerate design, or measures
the naive/HAC gap on a known DGP can. Synthetic-only (no store, no data/ reads),
so this file runs in a sparse worktree with no `needs_full_checkout` marker,
mirroring tests/test_synthetic_control.py.
"""
import inspect
import math
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # noqa: E402

import engine.local_projections as lp  # noqa: E402
from engine.validation import newey_west_tstat  # noqa: E402


# --------------------------------------------------------------------------- #
# 1-2: recovery on a known-truth DGP
# --------------------------------------------------------------------------- #
def test_recovers_a_known_geometric_irf():
    y, shock, true_irf = lp.demo_series(true_beta=0.010, decay=0.75, seed=11)
    result = lp.impulse_response(y, shock)
    betas = np.array([row["beta"] for row in result["irf"]])
    assert np.all(np.abs(betas - true_irf) < 0.003)
    assert int(np.argmax(betas)) == 0


def test_recovers_a_hump_shaped_irf():
    rng = np.random.default_rng(23)
    n, horizons = 900, lp.HORIZONS
    shock = rng.standard_normal(n)
    # hump-shaped psi peaking at h=3, not a monotone decay
    j = np.arange(horizons + 1)
    psi = 0.012 * j * (0.7 ** j)
    y = np.convolve(shock, psi)[:n] + 0.008 * rng.standard_normal(n)
    result = lp.impulse_response(y, shock, horizons=horizons)
    betas = np.array([row["beta"] for row in result["irf"]])
    assert int(np.argmax(betas)) == 3


def test_no_shock_gives_a_null_at_every_horizon():
    rng = np.random.default_rng(0)
    n = 500
    shock = rng.standard_normal(n)
    y = rng.standard_normal(n) * 0.01  # independent of shock
    result = lp.impulse_response(y, shock)
    assert result["null"]["any_horizon_rejects"] is False
    words = result["null"]["plain_words"].lower()
    assert "effect" not in words or "no time-step" in words


# --------------------------------------------------------------------------- #
# 4-7: the HAC guard
# --------------------------------------------------------------------------- #
def test_hac_matches_validation_helper_on_an_intercept_only_regression():
    rng = np.random.default_rng(3)
    n = 300
    # build an MA(4)-overlapping series so the HAC correction actually engages
    eps = rng.standard_normal(n)
    y = eps.copy()
    for j in range(1, 5):
        y[j:] += 0.5 * eps[:-j]

    X = np.ones((n, 1))
    beta, resid, _ = lp._ols(X, y)
    V = lp._hac_sandwich(X, resid, lags=4)
    se_sandwich = float(np.sqrt(V[0, 0]))

    helper = newey_west_tstat(y, lags=4)
    assert helper["se"] is not None
    assert round(se_sandwich, 5) == round(helper["se"], 5)
    assert helper["lags"] == 4


def test_hac_lag_is_h_plus_one_and_reports_the_effective_clamp():
    rng = np.random.default_rng(5)
    n = 15
    y = rng.standard_normal(n) * 0.01
    shock = rng.standard_normal(n)
    h = 10
    row = lp.estimate_horizon(y, shock, h, lags=1, embargo=1, min_obs=2)
    assert not row.get("abstained")
    assert row["hac_lags_requested"] == h + 1
    assert row["hac_lags"] < row["hac_lags_requested"]
    assert row["hac_lags"] <= max(row["n"] - 1, 0)


def _ma_correlated_design(rng, n, lags_ma, ma_coef=0.6):
    """A hand-built (intercept, shock) design whose residual is MA(lags_ma) by
    construction - the exact structure an LP horizon target has (its residual
    at horizon h is MA(h) because adjacent targets share h-1 future periods).
    Used to test the HAC guard directly, decoupled from whether a particular
    fitted LP specification's own controls happen to absorb the persistence."""
    eps = rng.standard_normal(n)
    resid_true = eps.copy()
    for j in range(1, lags_ma + 1):
        resid_true[j:] += ma_coef * eps[:-j]
    shock = rng.standard_normal(n)
    X = np.column_stack([np.ones(n), shock])
    y = resid_true  # under the null, y is pure MA(lags_ma) noise, unrelated to shock
    return X, y


def test_overlapping_targets_inflate_the_naive_standard_error():
    # The intercept column is constant across t, so its coefficient's sandwich
    # variance isolates the effect of the MA(lags_ma) residual correlation
    # itself - exactly engine.validation.newey_west_tstat's own justification
    # ("overlapping windows serially-correlate a signal's per-date stats, so a
    # plain t-stat overstates significance"), which this module inherits
    # unmodified for the horizon-panel se.
    rng = np.random.default_rng(41)
    lags_ma = 6
    X, y = _ma_correlated_design(rng, n=300, lags_ma=lags_ma)
    beta, resid, xtx_pinv = lp._ols(X, y)
    sigma2 = float(np.dot(resid, resid) / (len(y) - 2))
    se_naive = math.sqrt(sigma2 * xtx_pinv[0, 0])
    V = lp._hac_sandwich(X, resid, lags_ma)
    se_hac = math.sqrt(V[0, 0])
    assert se_hac > se_naive
    assert se_hac / se_naive > 1.3


def test_naive_t_over_rejects_on_the_null_dgp():
    # Overlapping horizon targets make the LP residual MA(h) by construction
    # (target y[t+h] and y[t+h+1] share h-1 future periods) - a naive OLS se
    # assumes iid errors and understates the true variance under exactly that
    # structure, so it over-rejects a true null far more than the HAC se does.
    n_sims = 200
    lags_ma = 6
    naive_rejects = 0
    hac_rejects = 0
    for seed in range(n_sims):
        rng = np.random.default_rng(5000 + seed)
        X, y = _ma_correlated_design(rng, n=150, lags_ma=lags_ma)
        beta, resid, xtx_pinv = lp._ols(X, y)
        sigma2 = float(np.dot(resid, resid) / (len(y) - 2))
        se_naive = math.sqrt(sigma2 * xtx_pinv[0, 0])
        V = lp._hac_sandwich(X, resid, lags_ma)
        se_hac = math.sqrt(max(V[0, 0], 0.0))
        naive_t = beta[0] / se_naive if se_naive else 0.0
        hac_t = beta[0] / se_hac if se_hac else 0.0
        if abs(naive_t) > 1.96:
            naive_rejects += 1
        if abs(hac_t) > 1.96:
            hac_rejects += 1
    naive_rate = naive_rejects / n_sims
    hac_rate = hac_rejects / n_sims
    assert naive_rate > 0.15
    assert naive_rate > hac_rate


# --------------------------------------------------------------------------- #
# 8-9: lookahead guard
# --------------------------------------------------------------------------- #
def test_control_block_never_reads_the_embargoed_bars():
    rng = np.random.default_rng(9)
    n = 60
    y = rng.standard_normal(n)
    shock = rng.standard_normal(n)
    lags, embargo = 2, 3
    dm1 = lp.design_matrix(y, shock, lags=lags, embargo=embargo)

    t_ref = 40
    control_hi = t_ref - embargo
    gap = range(control_hi + 1, t_ref)  # bars strictly between control_hi and t_ref
    assert len(list(gap)) > 0

    y2 = y.copy()
    shock2 = shock.copy()
    for idx in gap:
        y2[idx] = 999.0
        shock2[idx] = -999.0

    dm2 = lp.design_matrix(y2, shock2, lags=lags, embargo=embargo)
    assert np.array_equal(dm1["X"][t_ref], dm2["X"][t_ref])


def test_targets_never_exceed_the_sample():
    rng = np.random.default_rng(15)
    n = 200
    y = rng.standard_normal(n) * 0.01
    shock = rng.standard_normal(n)
    result = lp.impulse_response(y, shock, horizons=10)
    ns = [result["diagnostics"]["n_by_horizon"][str(h)] for h in range(11)]
    assert all(ns[i] >= ns[i + 1] for i in range(len(ns) - 1))

    y_ext = np.concatenate([y, rng.standard_normal(20) * 0.01])
    shock_ext = np.concatenate([shock, rng.standard_normal(20)])
    result2 = lp.impulse_response(y_ext, shock_ext, horizons=10)
    for h in range(11):
        assert result2["diagnostics"]["n_by_horizon"][str(h)] >= result["diagnostics"]["n_by_horizon"][str(h)]


# --------------------------------------------------------------------------- #
# 10-12: typed refusals
# --------------------------------------------------------------------------- #
def test_abstains_below_min_obs():
    rng = np.random.default_rng(21)
    n = 30
    y = rng.standard_normal(n)
    shock = rng.standard_normal(n)
    row = lp.estimate_horizon(y, shock, 0, min_obs=1000)
    assert row["abstained"] is True
    assert row["schema"] == lp.ABSTENTION_SCHEMA
    assert row["reason"] == "insufficient_observations"
    assert not isinstance(row.get("beta"), float)


def test_degenerate_shock_abstains():
    rng = np.random.default_rng(22)
    n = 200
    y = rng.standard_normal(n)
    shock = np.ones(n) * 5.0  # constant
    row = lp.estimate_horizon(y, shock, 0, min_obs=10)
    assert row["abstained"] is True
    assert row["reason"] == "degenerate_shock"
    assert "t" not in row


def test_rank_deficient_design_abstains():
    rng = np.random.default_rng(24)
    n = 200
    y = rng.standard_normal(n)
    shock = rng.standard_normal(n)
    # controls=y duplicates the y_lag1 control column exactly -> rank deficient
    row = lp.estimate_horizon(y, shock, 0, controls=y, min_obs=10)
    assert row["abstained"] is True
    assert row["reason"] == "rank_deficient_design"


# --------------------------------------------------------------------------- #
# 13: BH correction
# --------------------------------------------------------------------------- #
def test_bh_correction_is_applied_and_reject_reads_q():
    y, shock, _ = lp.demo_series(seed=11)
    result = lp.impulse_response(y, shock)
    for h_str, row in result["fdr"].items():
        assert row["q"] >= row["p"] - 1e-9
        if row["p"] < 0.05 and row["q"] >= 0.05:
            assert row["reject"] is False
    ps = sorted(v["p"] for v in result["fdr"].values())
    qs = [result["fdr"][str(h)]["q"] for h in range(len(result["irf"]))
          if str(h) in result["fdr"]]
    # q must be monotone non-decreasing when sorted by ascending p (BH walk-up)
    sorted_by_p = sorted(result["fdr"].items(), key=lambda kv: kv[1]["p"])
    q_seq = [v["q"] for _, v in sorted_by_p]
    assert all(q_seq[i] <= q_seq[i + 1] + 1e-9 for i in range(len(q_seq) - 1))


# --------------------------------------------------------------------------- #
# 14-15: trial ledger integration
# --------------------------------------------------------------------------- #
def test_named_family_without_registration_raises():
    from engine.seasonality.event_study import UnregisteredSearchFamily

    y, shock, _ = lp.demo_series(seed=11, n=200)
    with pytest.raises(UnregisteredSearchFamily):
        lp.impulse_response(y, shock, family="lp.demo.unregistered", ledger=None)


def test_registered_family_reports_effective_n(tmp_path):
    from engine.trial_ledger import TrialLedger

    led = TrialLedger(path=tmp_path / "lp_ledger.jsonl", family="lp.test.registered")
    if hasattr(led, "log_declared_budget"):
        led.log_declared_budget(5, family="lp.test.registered")
    else:
        led.log_grid({"cfg": [1]}, info_cutoff="2026-09-05")

    y, shock, _ = lp.demo_series(seed=11, n=200)
    result = lp.impulse_response(y, shock, family="lp.test.registered", ledger=led)
    assert isinstance(result["multiple_testing"]["effective_n"], int)
    assert result["multiple_testing"]["effective_n"] >= 1


# --------------------------------------------------------------------------- #
# 16-19: frozen constants, plain words, CLI, purity
# --------------------------------------------------------------------------- #
def test_pre_registered_constants_are_frozen():
    assert lp.HORIZONS == 20
    assert lp.LAGS == 4
    assert lp.EMBARGO == 1
    assert lp.MIN_OBS_PER_H == 60
    assert lp.FDR_ALPHA == 0.10
    assert lp.CI_LEVEL == 0.95
    assert lp.SCHEMA == "engine.local_projections.irf.v1"
    assert lp.ABSTENTION_SCHEMA == "engine.local_projections.abstention.v1"
    assert lp.HAC_LAG_RULE == "h + 1"


def test_plain_words_has_no_jargon_and_fits_the_budget():
    banned = ["p-value", "p =", "beta", "hac", "newey", "horizon h", "schema", "engine.", "q ="]
    for rejecting in ([], [1, 4, 7]):
        fake = {"null": {"rejecting_horizons": rejecting}}
        words = lp.plain_words(fake)
        assert len(words.split()) <= 30
        low = words.lower()
        for b in banned:
            assert b not in low


def test_cli_demo_runs_in_process_and_reports_recovery(capsys):
    rc = lp.main(["--demo", "--json"])
    assert rc == 0
    captured = capsys.readouterr()
    import json
    payload = json.loads(captured.out.strip().splitlines()[-1])
    assert payload["schema"] == lp.SCHEMA
    betas = np.array([row["beta"] for row in payload["irf"]])
    _, _, true_irf = lp.demo_series()
    assert np.all(np.abs(betas - true_irf) < 0.003)


def test_module_does_no_io():
    src = inspect.getsource(lp)
    assert "open(" not in src
    assert "requests" not in src
    assert "pathlib.Path(" not in src
    assert "from engine.store" not in src
    assert "from data" not in src
    assert "import engine.store" not in src
