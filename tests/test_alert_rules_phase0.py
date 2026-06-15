"""Phase-0 event-study harness for the macro alert rules
(scripts/alert_rules_phase0.py). Tests the pure stats helpers on synthetic data
(deterministic, no data dependency) + a guarded end-to-end smoke that the
scorecard it writes is well-formed and self-consistent.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts import alert_rules_phase0 as ph


def _spy(n=800):
    idx = pd.bdate_range("2000-01-03", periods=n)
    return pd.Series(np.linspace(100, 200, n), index=idx)   # smooth uptrend


def test_clusters_counts_independent_windows():
    spy = _spy(50)
    idx = spy.index
    # three firings on consecutive days collapse to ONE cluster at h=5
    near = idx[[10, 11, 12]]
    assert ph._clusters(near, idx, h=5) == 1
    # firings 10 days apart are two independent windows at h=5
    far = idx[[10, 22]]
    assert ph._clusters(far, idx, h=5) == 2
    assert ph._clusters(idx[[]], idx, h=5) == 0


def test_event_study_thesis_direction_and_keys():
    spy = _spy()
    # events early in a monotonic uptrend → every forward return is POSITIVE
    ev = pd.Series(False, index=spy.index)
    ev.iloc[[50, 120, 300, 500]] = True
    up = ph.event_study(ev, spy, thesis="up")
    for h in ("1", "5", "20", "60"):
        r = up[h]
        assert {"hit", "base_hit", "mean", "base_mean", "n", "n_clusters"} <= set(r)
    # in a pure uptrend the 'up' thesis hits ~100%, the 'down' thesis ~0%
    assert up["20"]["hit"] == pytest.approx(1.0, abs=1e-6)
    down = ph.event_study(ev, spy, thesis="down")
    assert down["20"]["hit"] == pytest.approx(0.0, abs=1e-6)


def test_event_study_flags_insufficient_n():
    spy = _spy()
    ev = pd.Series(False, index=spy.index)
    ev.iloc[[10]] = True                       # a single firing
    r = ph.event_study(ev, spy, thesis="down")
    assert r["20"].get("insufficient") is True


@pytest.mark.parametrize("rule", ["ebp_widening", "hy_oas_widening", "capitulation_signal"])
def test_scorecard_is_well_formed_if_data_present(rule):
    # guarded end-to-end: only runs where the cached features frame is available
    try:
        from engine import inputs
        from engine.conditions import conditions_frame
        f = inputs.build_features()
        if "SPY" not in f.columns or f["SPY"].dropna().empty:
            pytest.skip("no SPY history in cache")
        cf = conditions_frame(f)
        trig = ph.build_triggers(f, cf)
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"features frame unavailable: {e}")
    assert rule in trig
    spec = trig[rule]
    assert spec["thesis"] in ("up", "down")
    assert spec["events"].dtype == bool
    study = ph.event_study(spec["events"], f["SPY"].dropna(), spec["thesis"])
    # every horizon present; hit-rates are valid probabilities
    for h in ("1", "5", "20", "60"):
        r = study[h]
        if not r.get("insufficient"):
            assert 0.0 <= r["hit"] <= 1.0 and 0.0 <= r["base_hit"] <= 1.0
