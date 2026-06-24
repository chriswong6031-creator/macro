"""Tests for engine/risk_brain.py — the Opus daily risk-officer overlay.

Hermetic: the LLM `call` is injected, evidence is written to a tmp root. Focus on the
CODE clamp (the directive can only be more cautious than the engine; gross_tilt is
subtract-only + bounded), graceful degradation, the no-data gate, and the ledger.
"""
from __future__ import annotations

import json

from engine import risk_brain as rb


def _ok_reply(posture="risk-on", tilt=0.0, brain_state="neutral"):
    return (json.dumps({
        "risk_read": "Breadth is thinning under firm indexes [E1][E3].",
        "risk_read_zh": "宽度走弱。",
        "engine_agreement": "agree", "brain_state": brain_state,
        "themes_to_retire": ["semis-momentum"], "narratives_to_turn": [],
        "contagion_chain": [{"from": "memory", "to": "semis", "mechanism": "pricing"}],
        "wobbling_leaders": ["NVDA"],
        "directive": {"posture": posture, "gross_tilt": tilt, "favor": "entries",
                      "avoid": ["semis"], "rationale": "thinning tape"},
        "evidence_ids": ["E1", "E3"], "dissent": "could just be rotation",
        "falsifiable_check": {"confirm": "SPY -5% in 21d", "disconfirm": "SPY makes new high"},
        "confidence": "MED"}), None)


def _evidence(engine_state="neutral", score=30.0):
    return {"as_of": "2026-06-23", "engine_state": engine_state, "engine_score": score,
            "evidence": [{"id": "E1", "text": "risk_state neutral"},
                         {"id": "E3", "text": "3 breakdowns"}]}


# --- directive clamp (the hard boundary) -------------------------------------
def test_directive_gross_tilt_is_subtract_only():
    brief = rb._reconcile_directive({"directive": {"posture": "neutral", "gross_tilt": 0.4}},
                                    "neutral", rb._cfg())
    assert brief["directive"]["gross_tilt"] == 0.0  # positive clamped away


def test_directive_gross_tilt_bounded():
    brief = rb._reconcile_directive({"directive": {"posture": "defensive", "gross_tilt": -0.9}},
                                    "risk-off", rb._cfg())
    assert brief["directive"]["gross_tilt"] == -0.5  # cap


def test_directive_cannot_be_less_cautious_than_engine():
    # engine elevated but model said risk-on -> clamped up to de-gross, override recorded
    brief = rb._reconcile_directive({"directive": {"posture": "risk-on", "gross_tilt": 0.0}},
                                    "elevated", rb._cfg())
    assert brief["directive"]["posture"] == "de-gross"
    assert brief["directive"]["gross_tilt"] < 0      # elevated forces a real cut
    assert "override_reason" in brief["directive"]


def test_directive_passthrough_when_consistent():
    brief = rb._reconcile_directive({"directive": {"posture": "de-gross", "gross_tilt": -0.2}},
                                    "caution", rb._cfg())
    assert brief["directive"]["posture"] == "de-gross"
    assert brief["directive"]["gross_tilt"] == -0.2
    assert "override_reason" not in brief["directive"]


# --- synthesize --------------------------------------------------------------
def test_synthesize_happy_path_clamps():
    out = rb.synthesize(_evidence("elevated", 70.0),
                        call=lambda m, s, u: _ok_reply(posture="risk-on", tilt=0.3))
    assert out["schema"] == "risk_brain.v1"
    assert out["risk_read"]
    # model said risk-on + positive tilt; clamp forces caution + subtract-only
    assert out["directive"]["posture"] == "de-gross"
    assert out["directive"]["gross_tilt"] <= 0.0


def test_synthesize_no_call_degrades():
    out = rb.synthesize(_evidence(), call=None)
    assert out.get("degraded_reason") == "no_client_or_key"


def test_synthesize_unparseable_degrades():
    out = rb.synthesize(_evidence(), call=lambda m, s, u: ("not json at all", None))
    assert out.get("degraded_reason") == "unparseable_reply"


def test_synthesize_no_evidence_degrades():
    out = rb.synthesize({"evidence": []}, call=lambda m, s, u: _ok_reply())
    assert out.get("degraded_reason") == "no_evidence"


# --- gather_evidence + no-data gate ------------------------------------------
def test_gather_evidence_none_without_risk_state(tmp_path):
    (tmp_path / "data" / "regime").mkdir(parents=True)
    (tmp_path / "data" / "regime" / "latest.json").write_text(json.dumps({"date": "2026-06-23"}))
    assert rb.gather_evidence(root=tmp_path) is None


def test_gather_evidence_builds_pack(tmp_path):
    (tmp_path / "data" / "regime").mkdir(parents=True)
    latest = {"date": "2026-06-23",
              "risk_state": {"state": "caution", "score": 40, "alert": False,
                             "drivers": [{"key": "breadth_div", "intensity": 1.0}]},
              "conditions": {"complacency": {"state": "watch", "breadth_div": True}}}
    (tmp_path / "data" / "regime" / "latest.json").write_text(json.dumps(latest))
    ev = rb.gather_evidence(root=tmp_path)
    assert ev is not None
    assert ev["engine_state"] == "caution"
    assert any(e["id"] == "E1" for e in ev["evidence"])


# --- run + ledger ------------------------------------------------------------
def test_run_force_persists_and_no_ledger_when_calm(tmp_path):
    (tmp_path / "data" / "regime").mkdir(parents=True)
    (tmp_path / "data" / "regime" / "latest.json").write_text(json.dumps(
        {"date": "2026-06-23", "risk_state": {"state": "neutral", "score": 30}}))
    out = rb.run(force=True, root=tmp_path, call=lambda m, s, u: _ok_reply(brain_state="neutral"))
    assert (tmp_path / "site" / "riskdata" / "risk_brain.json").exists()
    # neutral brain_state -> no graded thesis logged
    assert not (tmp_path / "data" / "risk_brain" / "theses.jsonl").exists()


def test_run_logs_thesis_when_elevated(tmp_path):
    (tmp_path / "data" / "regime").mkdir(parents=True)
    (tmp_path / "data" / "regime" / "latest.json").write_text(json.dumps(
        {"date": "2026-06-23", "risk_state": {"state": "elevated", "score": 70}}))
    out = rb.run(force=True, root=tmp_path,
                 call=lambda m, s, u: _ok_reply(posture="defensive", tilt=-0.3, brain_state="elevated"))
    led = tmp_path / "data" / "risk_brain" / "theses.jsonl"
    assert led.exists()
    rows = [json.loads(x) for x in led.read_text().splitlines()]
    assert rows[0]["brain_state"] == "elevated"
    assert rows[0]["falsifier"]["check"]["kind"] == "max_drawdown"


def test_run_disabled_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(rb, "_cfg", lambda: {**rb._DEFAULTS, "enabled": False})
    assert rb.run(force=False, root=tmp_path) is None
