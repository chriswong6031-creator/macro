"""Unit tests for scripts/slf056_funding_tail_phase0.py.

Pure-function tests only — no network, no file I/O (except trial_ledger which
writes to a tempfile). All fixtures are tiny synthetic series.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.slf056_funding_tail_phase0 import (
    auc_roc,
    bootstrap_auc_ci,
    eval_g1,
    eval_g2,
    eval_g3,
    leave_one_out_auc,
    spy_drawdown_entry,
    tlt_fwd_return_sign,
    vix_signal,
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _make_series(vals, start="2020-01-01", freq="B"):
    idx = pd.bdate_range(start, periods=len(vals))
    return pd.Series(vals, index=idx)


# --------------------------------------------------------------------------- #
# auc_roc
# --------------------------------------------------------------------------- #
class TestAucRoc:
    def test_perfect_positive_predictor(self):
        """Signal perfectly separates: high signal -> positive outcome."""
        signal = _make_series([1, 2, 3, 4, 5, 6, 7, 8, 9, 10,
                                11, 12, 13, 14, 15, 16, 17, 18, 19, 20])
        outcome = _make_series([0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                                 1, 1, 1, 1, 1, 1, 1, 1, 1, 1])
        auc = auc_roc(signal, outcome)
        assert auc == pytest.approx(1.0, abs=1e-6)

    def test_perfect_negative_predictor(self):
        """High signal -> negative outcome = AUC of 0.
        AUC = P(signal[positive] > signal[negative]).
        For AUC=0: positives always have LOWER signal than negatives."""
        # Positives (outcome=1) have signal in {1..10}, negatives have {11..20}
        # P(signal[pos] > signal[neg]) = 0.0 -> AUC = 0.0
        signal = _make_series([1, 2, 3, 4, 5, 6, 7, 8, 9, 10,
                                11, 12, 13, 14, 15, 16, 17, 18, 19, 20])
        outcome = _make_series([1, 1, 1, 1, 1, 1, 1, 1, 1, 1,
                                 0, 0, 0, 0, 0, 0, 0, 0, 0, 0])
        auc = auc_roc(signal, outcome)
        assert auc == pytest.approx(0.0, abs=1e-6)

    def test_random_is_near_half(self):
        """Uncorrelated random signal -> AUC near 0.5."""
        rng = np.random.default_rng(99)
        n = 200
        signal = _make_series(rng.standard_normal(n))
        outcome = _make_series(rng.integers(0, 2, n).astype(float))
        auc = auc_roc(signal, outcome)
        assert 0.3 < auc < 0.7   # relaxed — random can vary

    def test_returns_nan_on_insufficient_positives(self):
        """Only 3 positives -> AUC = NaN (below min_pos threshold)."""
        signal = _make_series(list(range(20)))
        outcome = _make_series([0] * 17 + [1] * 3)
        auc = auc_roc(signal, outcome)
        assert np.isnan(auc)

    def test_returns_nan_when_too_few_obs(self):
        signal = _make_series([1.0, 2.0])
        outcome = _make_series([0.0, 1.0])
        auc = auc_roc(signal, outcome)
        assert np.isnan(auc)


# --------------------------------------------------------------------------- #
# bootstrap_auc_ci
# --------------------------------------------------------------------------- #
class TestBootstrapAucCi:
    def test_ci_structure(self):
        """CI dict has expected keys and ci_lo <= auc <= ci_hi (roughly)."""
        rng = np.random.default_rng(7)
        n = 100
        sig = _make_series(rng.standard_normal(n))
        # Build a positively predictive outcome
        out = _make_series((sig.values > 0).astype(float))
        res = bootstrap_auc_ci(sig, out, block=5, B=200, seed=0)
        assert "auc" in res
        assert "ci_lo" in res
        assert "ci_hi" in res
        assert res["ci_lo"] <= res["auc"] <= res["ci_hi"] + 0.01  # tiny tolerance

    def test_empty_on_short_series(self):
        """Too short to bootstrap -> returns empty dict."""
        sig = _make_series([1.0, 2.0, 3.0])
        out = _make_series([0.0, 1.0, 0.0])
        res = bootstrap_auc_ci(sig, out, block=5, B=100)
        assert res == {}

    def test_ci_level_stored(self):
        rng = np.random.default_rng(0)
        n = 80
        sig = _make_series(rng.standard_normal(n))
        out = _make_series((rng.standard_normal(n) > 0).astype(float))
        res = bootstrap_auc_ci(sig, out, block=5, B=100, ci=0.90)
        assert res.get("ci_level") == pytest.approx(0.90)


# --------------------------------------------------------------------------- #
# Outcome constructors
# --------------------------------------------------------------------------- #
class TestSpyDrawdownEntry:
    def test_declining_prices_trigger_drawdown(self):
        """A price series that drops 10% within 21d should have outcome=1."""
        prices = _make_series([100.0] * 5 + [90.0] * 20 + [100.0] * 10)
        out = spy_drawdown_entry(prices, horizon_d=21, thresh=-0.05)
        # After the first bar, the next 21 days include the drop
        assert int(out.iloc[2]) == 1  # at bar 2, a >5% drop within 21d is imminent

    def test_stable_prices_no_drawdown(self):
        """A flat price series -> no drawdown events."""
        prices = _make_series([100.0] * 50)
        out = spy_drawdown_entry(prices, horizon_d=21, thresh=-0.05)
        # No drawdown — all outcomes should be 0 or NaN
        valid = out.dropna()
        assert (valid == 0).all()


class TestTltFwdReturnSign:
    def test_rising_prices_return_1(self):
        """Consistently rising prices -> outcomes in non-tail rows are 1.
        The tail rows have no future price (shift(-horizon) = NaN), so the comparison
        NaN > 0 = False = 0; we test only the rows that do have a future price.
        """
        horizon = 21
        n = 50
        prices = _make_series([100.0 + i * 0.5 for i in range(n)])
        out = tlt_fwd_return_sign(prices, horizon_d=horizon)
        # First n-horizon rows have valid forward returns and should be 1
        valid_rows = out.iloc[:n - horizon]
        assert (valid_rows == 1).all()

    def test_falling_prices_return_0(self):
        """Consistently falling prices -> outcomes 0."""
        prices = _make_series([100.0 - i * 0.5 for i in range(50)])
        out = tlt_fwd_return_sign(prices, horizon_d=21)
        valid = out.dropna()
        assert (valid == 0).all()


class TestVixSignal:
    def test_above_threshold_returns_1(self):
        """VIX > 25 -> signal = 1 (after shift)."""
        vix = _make_series([30.0] * 10)
        out = vix_signal(vix, thresh=25.0)
        # shift(1) makes first bar NaN
        assert out.iloc[1] == pytest.approx(1.0)

    def test_below_threshold_returns_0(self):
        """VIX < 25 -> signal = 0."""
        vix = _make_series([15.0] * 10)
        out = vix_signal(vix, thresh=25.0)
        assert out.iloc[1] == pytest.approx(0.0)


# --------------------------------------------------------------------------- #
# Leave-one-out
# --------------------------------------------------------------------------- #
class TestLeaveOneOut:
    def _make_synthetic(self):
        rng = np.random.default_rng(42)
        n = 300
        idx = pd.bdate_range("2018-01-01", periods=n)
        sig = pd.Series(rng.standard_normal(n), index=idx)
        out = pd.Series(rng.integers(0, 2, n).astype(float), index=idx)
        return sig, out

    def test_returns_full_and_all_episodes(self):
        sig, out = self._make_synthetic()
        episodes = {
            "ep1": ("2018-03-01", "2018-04-30"),
            "ep2": ("2018-07-01", "2018-08-31"),
        }
        res = leave_one_out_auc(sig, out, episodes)
        assert "full" in res
        assert "ep1" in res
        assert "ep2" in res
        assert "auc" in res["full"]

    def test_removal_reduces_n(self):
        """After removing an episode, fewer rows are used."""
        n = 300
        idx = pd.bdate_range("2018-01-01", periods=n)
        rng = np.random.default_rng(7)
        sig = pd.Series(rng.standard_normal(n), index=idx)
        out = pd.Series(rng.integers(0, 2, n).astype(float), index=idx)
        episodes = {"big_ep": ("2018-01-01", "2018-06-30")}
        res = leave_one_out_auc(sig, out, episodes)
        # Removed ~125 days
        assert res["big_ep"]["n_removed"] > 80


# --------------------------------------------------------------------------- #
# Gate evaluators
# --------------------------------------------------------------------------- #
class TestGateEvaluators:
    def test_g1_passes_when_auc_and_ci_satisfy_condition(self):
        """G1 passes when any result has AUC >= 0.60 and ci_lo > 0.50."""
        auc_results = {
            "sig_h21": {"auc": 0.65, "ci_lo": 0.55, "ci_hi": 0.75},
            "sig_h63": {"auc": 0.55, "ci_lo": 0.40, "ci_hi": 0.60},
        }
        passed, detail = eval_g1(auc_results)
        assert passed

    def test_g1_fails_when_auc_below_threshold(self):
        auc_results = {
            "sig_h21": {"auc": 0.50, "ci_lo": 0.40, "ci_hi": 0.60},
        }
        passed, detail = eval_g1(auc_results)
        assert not passed

    def test_g1_fails_when_ci_lo_not_above_0_50(self):
        """AUC >= 0.60 but CI lo does not exclude 0.50 -> fail."""
        auc_results = {
            "sig_h21": {"auc": 0.62, "ci_lo": 0.45, "ci_hi": 0.80},
        }
        passed, detail = eval_g1(auc_results)
        assert not passed

    def test_g2_passes_when_all_directions_stable(self):
        loo = {
            "full": {"auc": 0.65},
            "ep1": {"auc": 0.63, "n_removed": 30},
            "ep2": {"auc": 0.62, "n_removed": 25},
        }
        passed, detail = eval_g2(loo)
        assert passed

    def test_g2_fails_when_sign_flips(self):
        loo = {
            "full": {"auc": 0.65},
            "ep1": {"auc": 0.63, "n_removed": 30},
            "ep2": {"auc": 0.42, "n_removed": 25},   # flips below 0.5
        }
        passed, detail = eval_g2(loo)
        assert not passed

    def test_g3_passes_when_composite_beats_vix(self):
        passed, detail = eval_g3(0.65, 0.60)
        assert passed
        assert "0.65" in detail or "0.6500" in detail

    def test_g3_fails_when_vix_wins(self):
        passed, detail = eval_g3(0.55, 0.65)
        assert not passed

    def test_g3_fails_on_nan_input(self):
        passed, detail = eval_g3(np.nan, 0.60)
        assert not passed
