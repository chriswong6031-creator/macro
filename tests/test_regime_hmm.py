"""Unit guards for engine.regime_hmm — the informed 4-state Gaussian HMM over the quads.

Pure-math checks on a synthetic 4-quad series (no data cache): the model must recover a state
per quad with means in the correct (growth, inflation) quadrant, emit a proper probability
simplex, produce row-stochastic transitions, and put high mass on the true quad in a
quad-dominated window.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from engine import regime_hmm as H

_CENTROID = {"Q1": (0.5, -0.5), "Q2": (0.5, 0.5), "Q3": (-0.5, 0.5), "Q4": (-0.5, -0.5)}


def _synthetic(block=200, cycles=2, seed=1):
    rng = np.random.default_rng(seed)
    order = ["Q1", "Q2", "Q3", "Q4"] * cycles
    rows, quads = [], []
    for q in order:
        gc, ic = _CENTROID[q]
        rows.append(rng.normal([gc, ic], 0.15, (block, 2)))
        quads += [q] * block
    X = np.vstack(rows)
    idx = pd.bdate_range("2005-01-03", periods=len(X))
    return pd.DataFrame({"growth_score": X[:, 0], "inflation_score": X[:, 1], "quad": quads}, index=idx)


def test_recovers_a_state_per_quad_with_correct_signs():
    out = H.fit_regime_hmm(_synthetic())
    assert out is not None
    assert set(out["quads_present"]) == {"Q1", "Q2", "Q3", "Q4"}
    for s in out["state_means"]:
        gc, ic = _CENTROID[s["quad"]]
        assert np.sign(s["growth"]) == np.sign(gc), s
        assert np.sign(s["inflation"]) == np.sign(ic), s


def test_regime_probs_form_a_simplex():
    out = H.fit_regime_hmm(_synthetic())
    p = out["regime_probs"]
    assert abs(sum(p.values()) - 1.0) < 1e-6
    assert all(0.0 <= v <= 1.0 for v in p.values())


def test_transition_matrix_rows_are_stochastic():
    out = H.fit_regime_hmm(_synthetic())
    for q, row in out["transition_matrix"].items():
        s = sum(row.values())
        assert abs(s - 1.0) < 1e-6 or s == 0.0   # present quads sum to 1; absent -> 0


def test_dominant_quad_gets_high_posterior():
    # last block of the synthetic cycle is Q4 -> today's soft read should be Q4-dominant
    out = H.fit_regime_hmm(_synthetic())
    assert out["modal_quad"] == "Q4"
    assert out["regime_probs"]["Q4"] > 0.5


def test_too_short_returns_none():
    idx = pd.bdate_range("2024-01-01", periods=100)
    df = pd.DataFrame({"growth_score": np.zeros(100), "inflation_score": np.zeros(100)}, index=idx)
    assert H.fit_regime_hmm(df) is None


def test_hazard_and_dwell_are_consistent():
    out = H.fit_regime_hmm(_synthetic())
    stay = out["transition_matrix"][out["modal_quad"]][out["modal_quad"]]
    if out["expected_dwell_months"] is not None:
        assert out["expected_dwell_months"] == pytest.approx(1.0 / (1.0 - stay), rel=0.05)
        assert 0.0 <= out["hazard"] <= 1.0
