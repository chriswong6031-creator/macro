"""Promotion gate (engine/promotion_gate.py) — the PROPOSE-not-deploy capstone.

Composes honest-N DSR + PBO + CPCV-robustness + drift + beats-incumbent + the Holdout Vault.
A strong candidate clears every gate (ELIGIBLE, advisory); each weak input blocks with its
gate named. Deterministic.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.promotion_gate import cpcv_path_signs, promotion_gate  # noqa: E402
from engine.trial_ledger import TrialLedger  # noqa: E402
from engine.holdout_vault import HoldoutVault  # noqa: E402


def _strong_returns(seed=0, n=2000, edge=0.0012):
    return np.random.default_rng(seed).normal(edge, 0.01, n)


def test_strong_candidate_is_eligible():
    r = _strong_returns()
    led = TrialLedger(Path(tempfile.mkdtemp()) / "t.jsonl", family="cand")
    led.log_grid([{"i": i} for i in range(8)])
    out = promotion_gate(r, trial_ledger=led, family="cand",
                         ic_stream=np.random.default_rng(1).normal(0.05, 0.02, 200).tolist(),
                         incumbent_sharpe=0.5)
    assert out["eligible"] is True and out["verdict"] == "PROMOTE-ELIGIBLE"
    assert out["gates"]["deflated_sharpe"]["pass"] and out["blocking"] == []


def test_lowballed_n_does_not_save_a_weak_edge():
    # honest-N (a big ledger) sinks the DSR of a borderline edge → blocked
    r = _strong_returns(edge=0.0004)
    led = TrialLedger(Path(tempfile.mkdtemp()) / "t.jsonl", family="cand")
    led.log_grid([{"i": i} for i in range(400)])         # honestly counted: many trials
    out = promotion_gate(r, trial_ledger=led, family="cand")
    assert out["eligible"] is False and "deflated_sharpe" in out["blocking"]


def test_high_pbo_blocks():
    r = _strong_returns()
    rng = np.random.default_rng(2)
    M = rng.normal(0, 0.02, (600, 20)); M = M - M.mean(axis=0, keepdims=True)   # overfit matrix
    out = promotion_gate(r, n_trials=8, perf_matrix=M)
    assert "pbo" in out["blocking"] and out["eligible"] is False


def test_drift_blocks():
    r = _strong_returns()
    stream = (np.random.default_rng(3).normal(0.08, 0.02, 200).tolist()
              + np.random.default_rng(4).normal(-0.08, 0.02, 200).tolist())
    out = promotion_gate(r, n_trials=8, ic_stream=stream)
    assert "drift" in out["blocking"]


def test_must_beat_incumbent_by_margin():
    r = _strong_returns(edge=0.0012)            # ~ Sharpe ~1.9 annualized
    weak = promotion_gate(r, n_trials=8, incumbent_sharpe=5.0)   # incumbent far better
    assert "beats_incumbent" in weak["blocking"]


def test_cpcv_path_signs_robust_vs_fragile():
    robust = cpcv_path_signs(_strong_returns(edge=0.003), n_groups=6, k_test=2)
    assert promotion_gate(_strong_returns(edge=0.003), n_trials=8,
                          cpcv_path_signs=robust)["gates"]["cpcv_robust"]["pass"] is True
    fragile = [1, -1, 1, -1, 1, -1, 1, -1]      # sign flips every path → not robust
    assert promotion_gate(_strong_returns(), n_trials=8,
                          cpcv_path_signs=fragile)["gates"]["cpcv_robust"]["pass"] is False


def test_vault_peek_recorded_and_retired_refused():
    root = Path(tempfile.mkdtemp())
    v = HoldoutVault(root); v.seal("W", {"n": 100})
    r = _strong_returns()
    out = promotion_gate(r, n_trials=8, vault=v, hypothesis_id="hyp-1", window_id="W")
    assert out["gates"]["holdout_vault"]["pass"] and out["gates"]["holdout_vault"]["peek_n"] == 1
    v.retire("hyp-1", "tested")
    blocked = promotion_gate(r, n_trials=8, vault=v, hypothesis_id="hyp-1", window_id="W")
    assert "holdout_vault" in blocked["blocking"]    # no re-peeking a retired hypothesis


def test_no_inputs_is_not_eligible_and_never_raises():
    out = promotion_gate()
    assert out["eligible"] is False and out["gates"] == {}
