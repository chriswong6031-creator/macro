"""engine.foresight_analyst — the LLM reasoning layer. The DETERMINISTIC parts (evidence
pack, the no-forecast guardrail, JSON parse/validate) are tested with an injected mock call;
the live LLM is not exercised (no credential -> graceful None, which is the house pattern).
"""
from __future__ import annotations

import json

from engine import foresight_analyst as fa


def _conv():
    return {"asof": "2026-06-28", "ranked": [
        {"theme": "memory_storage", "name": "Memory", "stage": "PRECIPICE", "heat": 0.72,
         "earliness": 0.9, "n_signals": 3, "signals": ["physical", "subsector_scarcity", "altdata"],
         "physical_confirmed": True},
        {"theme": "solar", "name": "Solar", "stage": "WATCH", "heat": 0.3, "earliness": 0.6,
         "n_signals": 1, "signals": ["demand"], "physical_confirmed": False},
    ]}


def _cascade():
    return {"themes": [{"theme": "memory_storage", "bottleneck_band": "TIGHT", "demand_band": None,
                        "guidance_band": None, "revision_breadth": 0.05, "altdata_summary": "1 insider cluster",
                        "rationale": "supply tight"}]}


def test_evidence_pack_from_convergence():
    pack = fa._evidence_pack(_conv(), _cascade())
    assert pack[0]["theme"] == "memory_storage" and pack[0]["heat"] == 0.72
    assert pack[0]["evidence"]["bottleneck_band"] == "TIGHT"      # joined from the cascade row


def test_no_forecast_guardrail():
    assert fa._has_forecast({"mechanism": "price target of $50"}) is True
    assert fa._has_forecast({"non_obvious": "30% upside"}) is True
    assert fa._has_forecast({"mechanism": "supply tightening while revisions are flat"}) is False


def test_parse_drops_forecast_and_invalid_theme():
    valid = {"memory_storage", "solar"}
    text = json.dumps({"regime_read": "early supply read", "theses": [
        {"theme": "memory_storage", "mechanism": "supply tight while estimates flat",
         "non_obvious": "insider cluster + subsector scarcity + flat revisions",
         "kill_criteria": ["bottleneck loosens to NEUTRAL"], "evidence": ["physical"],
         "dissent": "could be one-off", "confidence": "medium"},
        {"theme": "solar", "mechanism": "implies 40% upside to a $90 target",   # forecast -> dropped
         "kill_criteria": ["x"], "confidence": "low"},
        {"theme": "not_a_theme", "mechanism": "x", "kill_criteria": ["y"]},     # invalid -> dropped
    ]})
    out = fa._parse(text, valid)
    assert len(out["theses"]) == 1 and out["theses"][0]["theme"] == "memory_storage"


def test_compute_full_path_with_mock_call():
    def mock_call(system, user):
        return (json.dumps({"regime_read": "r", "regime_read_zh": "r", "confidence": "medium",
                            "theses": [{"theme": "memory_storage", "mechanism": "supply tight, estimates flat",
                                        "non_obvious": "three independent surfaces agree early",
                                        "kill_criteria": ["bottleneck loosens"], "evidence": ["physical"],
                                        "dissent": "small sample", "confidence": "medium"}]}), None)
    out = fa.compute_foresight_analyst(_conv(), _cascade(), call=mock_call, write_ledger=False)
    assert out is not None and out["n_theses"] == 1
    assert out["theses"][0]["theme"] == "memory_storage"


def test_compute_none_paths():
    # empty convergence -> None
    assert fa.compute_foresight_analyst(None, call=lambda s, u: ("{}", None)) is None
    assert fa.compute_foresight_analyst({"ranked": []}, call=lambda s, u: ("{}", None)) is None
    # call returns nothing -> None
    assert fa.compute_foresight_analyst(_conv(), call=lambda s, u: (None, "empty")) is None
