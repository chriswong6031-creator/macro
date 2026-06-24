"""Tests for engine/risk_radar_audit.py — forward-outcome log + deterministic grading.

Uses a synthetic SPY path so true-positive / false-positive grading is deterministic.
"""
from __future__ import annotations

import pandas as pd

from engine import risk_radar_audit as rra


def _synthetic_spy():
    """Flat at 100, then a -8% air-pocket starting ~index 30. So an as-of a few days before the
    drop -> drawdown within 21bd (true positive); an as-of in the flat zone -> no drawdown (FP)."""
    idx = pd.bdate_range("2026-01-01", periods=70)
    px = [100.0] * len(idx)
    for i in range(30, 36):
        px[i] = 100.0 - (i - 29) * 1.4          # slide down to ~92 (-8%)
    for i in range(36, len(idx)):
        px[i] = 95.0                             # partial recover, stays down
    return pd.Series(px, index=idx)


def _snap(asof, state, alert):
    return {"asof": str(asof.date()), "state": state, "alert": alert,
            "dominant_scare": "growth", "top_score": 72.0,
            "scares": [{"scare": "growth", "score": 72.0, "band": state}],
            "drawdown_prob": {"h5": 0.04, "h10": 0.10, "h21": 0.20, "conjunction_n": 1}}


def test_log_is_idempotent(tmp_path):
    spy = _synthetic_spy()
    snap = _snap(spy.index[25], "elevated", True)
    assert rra.log_snapshot(snap, root=tmp_path) is True
    assert rra.log_snapshot(snap, root=tmp_path) is False     # same asof -> no dup
    rows = rra._read(rra._path(tmp_path))
    assert len(rows) == 1


def test_grade_true_and_false_positive(tmp_path, monkeypatch):
    spy = _synthetic_spy()
    monkeypatch.setattr(rra, "_spy", lambda: spy)
    rra.log_snapshot(_snap(spy.index[25], "elevated", True), root=tmp_path)   # ~5bd before the drop -> TP
    rra.log_snapshot(_snap(spy.index[5], "elevated", True), root=tmp_path)    # flat zone -> FP
    n = rra.grade_log(root=tmp_path)
    assert n == 2
    rows = {r["asof"]: r for r in rra._read(rra._path(tmp_path))}
    tp = rows[str(spy.index[25].date())]
    fp = rows[str(spy.index[5].date())]
    assert tp["graded"]["outcome"] == "true_positive"
    assert tp["graded"]["any_dd5_within_h21"] is True
    assert fp["graded"]["outcome"] == "false_positive"
    assert fp["graded"]["any_dd5_within_h21"] is False


def test_immature_entry_not_graded(tmp_path, monkeypatch):
    spy = _synthetic_spy()
    monkeypatch.setattr(rra, "_spy", lambda: spy)
    rra.log_snapshot(_snap(spy.index[-2], "elevated", True), root=tmp_path)   # no 21bd ahead -> immature
    assert rra.grade_log(root=tmp_path) == 0
    assert rra._read(rra._path(tmp_path))[0]["graded"] is None


def test_scorecard_precision_and_recall(tmp_path, monkeypatch):
    spy = _synthetic_spy()
    monkeypatch.setattr(rra, "_spy", lambda: spy)
    rra.log_snapshot(_snap(spy.index[25], "elevated", True), root=tmp_path)   # TP
    rra.log_snapshot(_snap(spy.index[5], "elevated", True), root=tmp_path)    # FP
    rra.log_snapshot(_snap(spy.index[10], "calm", False), root=tmp_path)      # calm, no dd
    rra.grade_log(root=tmp_path)
    sc = rra.scorecard(root=tmp_path)
    assert sc["n_graded"] == 3
    assert sc["n_alerts"] == 2 and sc["n_true_pos"] == 1 and sc["n_false_pos"] == 1
    assert sc["alert_precision"] == 0.5
    # the one FP must appear in recent_mistakes
    assert any(m["kind"] == "false_positive" for m in sc["recent_mistakes"])


def test_snapshot_and_grade_returns_scorecard(tmp_path, monkeypatch):
    spy = _synthetic_spy()
    monkeypatch.setattr(rra, "_spy", lambda: spy)
    sc = rra.snapshot_and_grade(_snap(spy.index[25], "elevated", True), root=tmp_path)
    assert isinstance(sc, dict) and "n_graded" in sc


def test_scorecard_empty_is_safe(tmp_path):
    assert rra.scorecard(root=tmp_path)["n_graded"] == 0
