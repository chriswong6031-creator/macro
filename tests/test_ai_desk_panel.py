"""AI Desk Phase B — the adversarial analyst PANEL + desk-head adjudicator.

Verifies the four independent analysts run over the same bundle, the adjudicator
collapses them into the SAME falsifiable thesis schema (so the engine falsifier /
ledger / scorer downstream are untouched), the adjudicator's dissent is preserved,
the panel is surfaced for the page, and the whole thing degrades to the single
analyst when the panel is off or unavailable. Keyless — the fake model is routed by
the ROLE marker in each system prompt."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import ai_desk as d  # noqa: E402

CFG = d._cfg()

_FLOW = {
    "as_of": "2026-03-02", "verdict": "display_only",
    "regime": {"vix": 17.0, "elevated": False},
    "cluster": {"absorption": 0.55, "regime": "mixed", "dominant_cluster": ["Energy"]},
    "sectors": [{"name": "Energy", "type": "sector", "read_quality": 0.7, "stage": "emerging"}],
    "baskets": [], "emerging": {"sectors": ["Energy"], "baskets": []},
    "ai_handoff": {"overall_verdict": "display_only",
                   "do_not_conclude": ["no forward returns from flow_score"]},
}

_FINAL = {
    "regime_context": "Cyclical cluster concentrating; the panel is split.",
    "theses": [{"subject": "Energy", "lean": "overweight", "conviction": "low",
                "horizon_d": 20, "thesis": "Energy leads the cluster.",
                "evidence": ["opportunity: cluster leader", "structural: co-moving"],
                "dissent": "Skeptic: narrow and mean-reverting — likely a coincident trap.",
                "falsifier_text": "Energy lags SPY by >5% over 20 trading days."}],
    "confidence": "low",
}


def _state():
    return {"as_of": "2026-03-02", "flow": d._flow_view(_FLOW), "regime_snap": None,
            "track_record": None, "sources_present": {"flow": True, "regime_snap": False}}


def _role(system: str) -> str:
    """Mirror how a real routed responder must disambiguate — adjudicator FIRST,
    because its prompt legitimately names the analysts (incl. 'SKEPTIC')."""
    if "DESK HEAD" in system:
        return "adjudicator"
    for tag in ("OPPORTUNITY", "SKEPTIC", "BASE-RATE", "STRUCTURAL"):
        if f"ROLE: {tag}" in system:
            return tag.lower()
    return "single"


def _make_call(record=None, fail_roles=()):
    def call(system, user, cfg):
        role = _role(system)
        if record is not None:
            record.append(role)
        if role in fail_roles:
            return None, "llm_error"
        if role in ("adjudicator", "single"):
            return json.dumps(_FINAL), None
        return json.dumps({"stance": f"{role} read", "key_risk": "x",
                           "candidates": [{"subject": "Energy", "lean": "overweight",
                                           "rationale": "r", "strength": "moderate"}]}), None
    return call


# --- the panel runs, the adjudicator synthesizes ------------------------- #
def test_panel_runs_all_four_analysts_then_adjudicates():
    seen = []
    brief = d.synthesize(_state(), CFG, call=_make_call(record=seen))
    assert {"opportunity", "skeptic", "base-rate", "structural"} <= set(seen)
    assert "adjudicator" in seen and "single" not in seen      # adjudicated, not single-shot
    assert set(brief["panel"]) == {"opportunity", "skeptic", "base_rate", "structural"}


def test_adjudicated_thesis_keeps_schema_and_engine_falsifier():
    brief = d.synthesize(_state(), CFG, call=_make_call())
    assert brief["schema"] == "ai_desk.v1" and brief["is_context_only"] is True
    assert len(brief["theses"]) == 1
    t = brief["theses"][0]
    assert t["subject"] == "Energy" and t["lean"] == "overweight"
    chk = t["falsifier"]["check"]                              # engine-derived, unchanged by Phase B
    assert chk["kind"] == "rel_return" and chk["subject_ticker"] == "XLE" and t["check_by"]


def test_adjudicator_dissent_is_preserved():
    t = d.synthesize(_state(), CFG, call=_make_call())["theses"][0]
    assert "skeptic" in (t["dissent"] or "").lower()           # the bear case survives onto the card


# --- graceful degradation ------------------------------------------------ #
def test_panel_disabled_falls_back_to_single_analyst():
    seen = []
    cfg = {**CFG, "panel": {"enabled": False}}
    brief = d.synthesize(_state(), cfg, call=_make_call(record=seen))
    assert seen == ["single"]                                  # exactly one call, no panel
    assert not brief.get("panel") and len(brief["theses"]) == 1


def test_whole_panel_unavailable_falls_back_to_single():
    seen = []
    call = _make_call(record=seen,
                      fail_roles=("opportunity", "skeptic", "base-rate", "structural"))
    brief = d.synthesize(_state(), CFG, call=call)
    assert "single" in seen and "adjudicator" not in seen      # no panel survivors -> single analyst
    assert brief["panel"] == {} and len(brief["theses"]) == 1


def test_partial_panel_still_adjudicates():
    seen = []
    call = _make_call(record=seen, fail_roles=("opportunity", "base-rate"))  # 2 of 4 fail
    brief = d.synthesize(_state(), CFG, call=call)
    assert "adjudicator" in seen and "single" not in seen      # survivors are enough to adjudicate
    assert set(brief["panel"]) == {"skeptic", "structural"}
    assert len(brief["theses"]) == 1
