"""Concept-drift detectors (engine/drift.py) — Page-Hinkley + ADWIN.

A stationary stream must NOT alarm; a stream whose mean shifts (a degrading signal IC) MUST,
and ADWIN must shrink its window to track the new regime. Deterministic (fixed seeds).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.drift import ADWIN, PageHinkley, rolling_ic_drift  # noqa: E402


def test_page_hinkley_no_alarm_on_stationary():
    rng = np.random.default_rng(0)
    ph = PageHinkley(delta=0.005, threshold=0.5, direction="down")
    alarms = sum(ph.update(x) for x in rng.normal(0.05, 0.02, 500))
    assert alarms == 0


def test_page_hinkley_catches_a_downshift():
    rng = np.random.default_rng(1)
    ph = PageHinkley(delta=0.005, threshold=0.25, direction="down")
    stream = np.concatenate([rng.normal(0.06, 0.02, 250),     # healthy IC
                             rng.normal(-0.02, 0.02, 250)])    # IC decays below zero
    first = next((i for i, x in enumerate(stream) if ph.update(x)), None)
    assert first is not None and first >= 250                 # alarm only after the shift


def test_adwin_no_drift_and_full_window_on_stationary():
    rng = np.random.default_rng(2)
    ad = ADWIN(delta=0.002)
    drifts = sum(ad.update(x) for x in rng.normal(0.05, 0.02, 400))
    assert drifts == 0 and ad.width == 400


def test_adwin_shrinks_window_after_shift():
    rng = np.random.default_rng(3)
    ad = ADWIN(delta=0.002)
    for x in rng.normal(0.10, 0.02, 300):
        ad.update(x)
    drifted = False
    for x in rng.normal(-0.10, 0.02, 300):
        drifted = ad.update(x) or drifted
    assert drifted is True
    assert ad.width < 600                       # dropped the stale pre-shift part
    assert ad.mean < 0                          # tracks the NEW (negative) regime


def test_rolling_ic_drift_flags_a_decay():
    rng = np.random.default_rng(4)
    healthy = rng.normal(0.08, 0.02, 200).tolist()
    decayed = rng.normal(-0.08, 0.02, 200).tolist()    # IC clearly inverts
    out = rolling_ic_drift(healthy + decayed, threshold=0.25)
    assert out["drift"] is True
    assert out["ph_drift_index"] is not None and out["ph_drift_index"] >= 200
    assert out["current_mean"] < 0             # ADWIN tracks the NEW (negative) regime
    assert out["current_width"] < 400          # and dropped the stale healthy part


def test_rolling_ic_drift_quiet_on_healthy_and_degrades_on_short():
    rng = np.random.default_rng(5)
    out = rolling_ic_drift(rng.normal(0.05, 0.02, 300).tolist(), threshold=0.5)
    assert out["drift"] is False
    assert rolling_ic_drift([0.1, 0.1])["drift"] is False      # too short → no-drift, no crash
    assert rolling_ic_drift([])["n"] == 0
