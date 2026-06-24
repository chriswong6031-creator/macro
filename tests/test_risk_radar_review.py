"""Tests for engine/risk_radar_review.py — the Opus self-correction loop.

Hermetic: the LLM `call` and the do-no-harm `compare` are injected. Focus on the CODE clamp
(proposals stay on the rails), and that a proposal is APPLIED only when the backtest says it
improves — otherwise rejected and logged.
"""
from __future__ import annotations

import json

from engine import risk_radar_review as rev
from engine.risk_radar import _calib


def _proposal(**deltas):
    return json.dumps({"analysis": "too many FPs from vol", "deltas": deltas,
                       "rationale": "nudge bands up"})


def test_clamp_keeps_bands_on_rails_and_ordered():
    base = _calib()
    # absurd proposal: elevated band to 999, watch above caution -> must clamp + reorder
    p = rev._clamp({"bands": {"elevated": 999.0, "watch": 95.0}}, base, rev._DEFAULTS)
    b = p["bands"]
    assert b["watch"] < b["caution"] < b["elevated"] < b["risk_off"]
    # within +/- band_max_delta of the baked default
    from engine.risk_radar import _DEFAULT_BANDS
    assert abs(b["elevated"] - _DEFAULT_BANDS["elevated"]) <= rev._DEFAULTS["band_max_delta"] + 1e-9


def test_clamp_thr_pct_and_alert_from_rails():
    base = _calib()
    p = rev._clamp({"legs": {"credit_oas_roc": {"thr_pct": 0.40}},   # below floor
                    "alert_from": "calm"}, base, rev._DEFAULTS)        # not allowed
    assert p["legs"]["credit_oas_roc"]["thr_pct"] >= rev._THR_LO
    assert p["alert_from"] in rev._ALERT_ALLOWED                       # 'calm' rejected -> keeps base


def test_clamp_prob_cal_monotonic():
    base = _calib()
    p = rev._clamp({"prob_cal": {"h21": {"calm": 0.5, "risk-off": 0.1}}}, base, rev._DEFAULTS)
    h = p["prob_cal"]["h21"]
    assert h["calm"] <= h["watch"] <= h["caution"] <= h["elevated"] <= h["risk-off"]


def test_applies_only_when_backtest_improves(tmp_path):
    sc = {"n_graded": 100, "alert_precision": 0.3, "recall_dd5_h21": 0.4, "recent_mistakes": []}
    out = rev.run(force=True, root=tmp_path, scorecard=sc,
                  call=lambda s, u: _proposal(bands={"elevated": 74.0}),
                  compare=lambda p: {"improves": True, "legs_ok": True,
                                     "base": {}, "proposed": {}})
    assert out["applied"] is True
    assert (tmp_path / "data" / "risk_radar" / "calibration.json").exists()


def test_rejects_when_backtest_does_not_improve(tmp_path):
    sc = {"n_graded": 100, "alert_precision": 0.3, "recall_dd5_h21": 0.4, "recent_mistakes": []}
    out = rev.run(force=True, root=tmp_path, scorecard=sc,
                  call=lambda s, u: _proposal(bands={"elevated": 60.0}),
                  compare=lambda p: {"improves": False, "legs_ok": True, "base": {}, "proposed": {}})
    assert out["applied"] is False
    assert out["degraded_reason"] == "rejected_by_do_no_harm"
    assert not (tmp_path / "data" / "risk_radar" / "calibration.json").exists()
    # but the rejected proposal IS logged (full audit trail)
    assert (tmp_path / "data" / "risk_radar" / "review_log.jsonl").exists()


def test_insufficient_graded_degrades(tmp_path):
    out = rev.run(force=True, root=tmp_path, scorecard={"n_graded": 5},
                  call=lambda s, u: _proposal(bands={}), compare=lambda p: {"improves": True})
    assert out["applied"] is False
    assert out["degraded_reason"] == "insufficient_graded"


def test_explicit_disable(monkeypatch):
    monkeypatch.setattr(rev, "_cfg", lambda: {**rev._DEFAULTS, "enabled": False})
    out = rev.run(force=False, scorecard={"n_graded": 100})
    assert out["applied"] is False and out["degraded_reason"] == "disabled"


def test_no_token_is_noop(tmp_path):
    # enabled (config) but no token + no injected call -> safe no-op, never applies
    out = rev.run(force=True, root=tmp_path, scorecard={"n_graded": 100, "recent_mistakes": []})
    assert out["applied"] is False
    assert out["degraded_reason"] in ("no_client_or_key", "no_usable_proposal")


def test_no_proposal_degrades(tmp_path):
    out = rev.run(force=True, root=tmp_path, scorecard={"n_graded": 100, "recent_mistakes": []},
                  call=lambda s, u: "not json", compare=lambda p: {"improves": True})
    assert out["applied"] is False
    assert out["degraded_reason"] == "no_usable_proposal"
