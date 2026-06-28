"""Probability calibration (engine.validation) — Expected Calibration Error + isotonic PAV.

A well-calibrated forecaster has low ECE; a miscalibrated one is corrected by isotonic
recalibration (monotone, non-parametric) so ece_after < ece_before. Deterministic.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.validation import (apply_calibration, expected_calibration_error,  # noqa: E402
                               isotonic_calibration)


def test_ece_low_for_a_well_calibrated_forecaster():
    rng = np.random.default_rng(0)
    p = rng.uniform(0, 1, 4000)
    y = (rng.uniform(0, 1, 4000) < p).astype(float)    # outcomes truly occur with prob p
    out = expected_calibration_error(p, y)
    assert out["ece"] < 0.03                            # stated odds match reality


def test_ece_high_for_an_overconfident_forecaster():
    rng = np.random.default_rng(1)
    true_p = rng.uniform(0, 1, 4000)
    y = (rng.uniform(0, 1, 4000) < true_p).astype(float)
    p = np.clip((true_p - 0.5) * 2.2 + 0.5, 0, 1)       # pushed toward 0/1 → overconfident
    out = expected_calibration_error(p, y)
    assert out["ece"] > 0.08 and out["mce"] >= out["ece"]


def test_ece_thin_sample_returns_empty():
    assert expected_calibration_error([0.5] * 10, [1] * 10) == {}


def test_isotonic_fixes_a_miscalibrated_score():
    rng = np.random.default_rng(2)
    true_p = rng.uniform(0, 1, 4000)
    y = (rng.uniform(0, 1, 4000) < true_p).astype(float)
    p = true_p ** 2                                     # squashed scores: monotone but miscalibrated
    model = isotonic_calibration(p, y)
    assert model["ece_after"] <= model["ece_before"]   # recalibration never hurts in-sample
    assert model["ece_after"] < 0.04                    # and lands well-calibrated
    yc = np.asarray(model["y_cal"])
    assert np.all(np.diff(yc) >= -1e-9)                 # the map is non-decreasing (monotone)


def test_apply_calibration_maps_new_scores_monotonically():
    rng = np.random.default_rng(3)
    true_p = rng.uniform(0, 1, 3000)
    y = (rng.uniform(0, 1, 3000) < true_p).astype(float)
    model = isotonic_calibration(true_p ** 2, y)
    lo = float(apply_calibration(model, 0.05))
    hi = float(apply_calibration(model, 0.95))
    assert hi >= lo                                     # higher raw score → higher calibrated prob
    assert apply_calibration({}, 0.7) == 0.7           # empty model → identity, no crash


def test_isotonic_thin_sample_returns_empty():
    assert isotonic_calibration([0.5] * 10, [1] * 10) == {}
