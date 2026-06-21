"""Combinatorial Purged CV + Probability of Backtest Overfitting (engine.validation).

The P3/P4 anti-overfit core: CPCV yields many backtest paths with a symmetric purge; PBO
measures how likely picking the in-sample-best config is selection over noise. Pure-numpy,
deterministic (fixed seeds).
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.validation import cpcv_paths, prob_backtest_overfitting  # noqa: E402


# --- CPCV ----------------------------------------------------------------- #
def test_cpcv_path_count_is_n_choose_k():
    paths = cpcv_paths(120, n_groups=6, k_test=2, embargo=0)
    assert len(paths) == math.comb(6, 2) == 15


def test_cpcv_train_test_disjoint_and_cover_all_groups():
    paths = cpcv_paths(120, n_groups=6, k_test=2, embargo=0)
    seen_test = set()
    for train, test in paths:
        assert set(train.tolist()).isdisjoint(set(test.tolist()))   # never train on test
        seen_test.update(test.tolist())
    assert seen_test == set(range(120))                             # every obs is tested somewhere


def test_cpcv_symmetric_purge_drops_both_sides():
    # one test group in the MIDDLE → embargo rows on BOTH sides must be absent from train
    paths = cpcv_paths(100, n_groups=5, k_test=1, embargo=3)
    # group 2 spans rows [40,60); test=group2 path is the 3rd combo (single-group combos in order)
    train, test = next((tr, te) for tr, te in paths if te[0] == 40)
    trains = set(train.tolist())
    assert all(r not in trains for r in range(37, 40))             # 3 rows BEFORE the block purged
    assert all(r not in trains for r in range(60, 63))             # 3 rows AFTER the block purged
    assert 36 in trains and 63 in trains                            # just outside the purge → kept


def test_cpcv_degenerate_returns_empty():
    assert cpcv_paths(10, n_groups=1, k_test=1) == []
    assert cpcv_paths(10, n_groups=4, k_test=4) == []              # k_test must be < n_groups


# --- PBO ------------------------------------------------------------------ #
def test_pbo_low_for_a_genuinely_good_config():
    # one config has a real, persistent edge → the IS-best is it, and it generalizes OOS.
    rng = np.random.default_rng(0)
    M = rng.normal(0.0, 0.02, (600, 12))
    M[:, 0] += 0.006                        # clear persistent edge (IR ≈ 0.3/period)
    out = prob_backtest_overfitting(M, n_splits=10)
    assert out["pbo"] < 0.10               # selecting the IS-best is NOT overfitting here
    assert out["median_logit"] > 0
    assert out["n_combos"] == math.comb(10, 5)


def test_pbo_high_when_no_config_has_a_real_edge():
    # demean each column → NO config has a real edge, so the IS-best is pure IS-luck and
    # mean-reverts OOS: the textbook overfit signature → PBO → 1.
    rng = np.random.default_rng(1)
    M = rng.normal(0.0, 0.02, (600, 20))
    M = M - M.mean(axis=0, keepdims=True)
    out = prob_backtest_overfitting(M, n_splits=10)
    assert out["pbo"] > 0.70               # picking the in-sample winner is selection over noise
    assert out["median_logit"] < 0


def test_pbo_degrades_on_bad_input():
    assert prob_backtest_overfitting(np.zeros((10, 1))) is None    # need ≥2 configs
    assert prob_backtest_overfitting(np.zeros(10)) is None         # need 2-D
    assert prob_backtest_overfitting(np.zeros((4, 5)), n_splits=10) is None  # T < n_splits
