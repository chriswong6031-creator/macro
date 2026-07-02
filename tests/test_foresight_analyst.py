"""engine.foresight_analyst — the LLM reasoning layer. The DETERMINISTIC parts (evidence
pack, the no-forecast guardrail, JSON parse/validate) are tested with an injected mock call;
the live LLM is not exercised (no credential -> graceful None, which is the house pattern).

W4b additions:
  (d) forecast clamp strips a price from kill_criteria and keeps the thesis
  (e) ungrounded evidence excluded from display (evidence_display), kept in ledger (evidence)
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


# ── existing tests (unchanged) ────────────────────────────────────────────────

def test_evidence_pack_from_convergence():
    pack = fa._evidence_pack(_conv(), _cascade())
    assert pack[0]["theme"] == "memory_storage" and pack[0]["heat"] == 0.72
    assert pack[0]["evidence"]["bottleneck_band"] == "TIGHT"      # joined from the cascade row


def test_no_forecast_guardrail():
    """_has_forecast only checks the mechanism field now (the hard drop gate)."""
    assert fa._has_forecast({"mechanism": "price target of $50"}) is True
    assert fa._has_forecast({"mechanism": "30% upside expected"}) is True
    assert fa._has_forecast({"mechanism": "supply tightening while revisions are flat"}) is False


def test_parse_drops_when_mechanism_is_forecast():
    """Mechanism with forecast language -> whole thesis dropped (unchanged hard gate)."""
    valid = {"memory_storage", "solar"}
    text = json.dumps({"regime_read": "early supply read", "theses": [
        {"theme": "solar", "mechanism": "implies 40% upside to a $90 target",   # forecast -> dropped
         "kill_criteria": ["x"], "confidence": "low"},
        {"theme": "not_a_theme", "mechanism": "x", "kill_criteria": ["y"]},     # invalid -> dropped
    ]})
    out = fa._parse(text, valid)
    assert len(out["theses"]) == 0


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


# ── W4b: forecast clamp (d) ──────────────────────────────────────────────────

def test_clamp_strips_price_from_kill_criteria_keeps_thesis():
    """(d) Forecast fragment in kill_criteria is clamped, thesis is kept (not dropped)."""
    valid = {"memory_storage"}
    # kill_criteria contains a price — should be clamped, not dropped
    text = json.dumps({"regime_read": "early supply read", "theses": [
        {"theme": "memory_storage",
         "mechanism": "supply tight while estimates are flat",           # no forecast here
         "non_obvious": "insider cluster + flat revisions",
         "kill_criteria": ["bottleneck loosens to NEUTRAL",
                           "expect a 20% return if band loosens"],    # <- forecast in kill_criteria
         "evidence": ["physical", "altdata"],
         "dissent": "could be one-off", "confidence": "medium"},
    ]})
    out = fa._parse(text, valid)
    assert out is not None
    # Thesis is KEPT despite the forecast fragment in kill_criteria
    assert len(out["theses"]) == 1
    th = out["theses"][0]
    # The clamped kill_criteria should have "[forecast removed]" in place of the offending fragment
    kc_combined = " ".join(str(k) for k in (th["kill_criteria"] or []))
    assert "[forecast removed]" in kc_combined
    assert "20% return" not in kc_combined
    # The first criterion (no forecast) should be intact
    assert "bottleneck loosens to NEUTRAL" in kc_combined
    # _forecast_clamped audit field should list what was removed
    assert th.get("_forecast_clamped") is not None
    assert len(th["_forecast_clamped"]) > 0


def test_clamp_mechanism_forecast_still_drops():
    """Forecast in MECHANISM still drops the whole thesis (unchanged hard gate)."""
    valid = {"memory_storage"}
    text = json.dumps({"regime_read": "r", "theses": [
        {"theme": "memory_storage",
         "mechanism": "expects 30% upside on supply tightening",    # <- forecast in mechanism
         "kill_criteria": ["band loosens"],
         "evidence": ["physical"], "confidence": "low"},
    ]})
    out = fa._parse(text, valid)
    assert out is not None
    assert len(out["theses"]) == 0   # dropped, not clamped


def test_clamp_forecast_in_dissent_keeps_thesis():
    """Forecast fragment in dissent is clamped; thesis is kept."""
    valid = {"memory_storage"}
    text = json.dumps({"regime_read": "r", "theses": [
        {"theme": "memory_storage",
         "mechanism": "supply tight while revisions flat",
         "kill_criteria": ["band loosens"],
         "evidence": ["physical"],
         "dissent": "price target of $200 by Q4",          # <- forecast in dissent
         "confidence": "low"},
    ]})
    out = fa._parse(text, valid)
    assert out is not None
    assert len(out["theses"]) == 1
    th = out["theses"][0]
    assert "[forecast removed]" in (th.get("dissent") or "")
    assert "$200" not in (th.get("dissent") or "")


# ── W4b: ungrounded evidence (e) ────────────────────────────────────────────

def test_ungrounded_evidence_excluded_from_display_kept_in_ledger():
    """(e) Evidence items not found in the pack text are tagged ungrounded=True and
    excluded from evidence_display but kept in the evidence list for audit."""
    pack = fa._evidence_pack(_conv(), _cascade())
    valid = {"memory_storage"}
    # "bottleneck is TIGHT" → grounded (TIGHT is in the cascade/pack)
    # "mystery surface from nowhere" → NOT in the pack → ungrounded
    text = json.dumps({"regime_read": "r", "theses": [
        {"theme": "memory_storage",
         "mechanism": "supply tight while revisions flat",
         "kill_criteria": ["band loosens"],
         "evidence": ["bottleneck is TIGHT",           # grounded (TIGHT in pack)
                      "mystery surface from nowhere"],  # NOT in pack -> ungrounded
         "dissent": "small sample", "confidence": "low"},
    ]})
    out = fa._parse(text, valid, pack=pack)
    assert out is not None
    assert len(out["theses"]) == 1
    th = out["theses"][0]

    # evidence list (ledger) contains all items (possibly tagged with ungrounded:True)
    assert len(th["evidence"]) == 2

    # evidence_display excludes ungrounded items (only string items remain)
    disp = th.get("evidence_display") or []
    assert all(isinstance(e, str) for e in disp)
    # "mystery surface from nowhere" is not a substring of the pack text, so not displayed
    assert not any("mystery" in str(e) for e in disp)

    # n_grounded should be less than n_total_evidence
    assert th["n_total_evidence"] == 2
    assert th["n_grounded"] < 2   # "mystery surface from nowhere" was not grounded


def test_all_evidence_grounded_when_in_pack():
    """All evidence grounded when items are substrings of the pack."""
    pack = fa._evidence_pack(_conv(), _cascade())
    valid = {"memory_storage"}
    text = json.dumps({"regime_read": "r", "theses": [
        {"theme": "memory_storage",
         "mechanism": "supply tight while revisions flat",
         "kill_criteria": ["band loosens"],
         "evidence": ["supply tight",   # from rationale in cascade
                      "insider cluster"],    # from altdata_summary
         "confidence": "low"},
    ]})
    out = fa._parse(text, valid, pack=pack)
    assert out is not None
    th = out["theses"][0]
    # Both items should be grounded (they appear in the pack text)
    assert th["n_grounded"] == th["n_total_evidence"]
    assert len(th.get("evidence_display") or []) == th["n_total_evidence"]


def test_short_evidence_items_accepted_as_trivially_grounded():
    """Very short evidence items (< 4 chars) are treated as trivially grounded."""
    pack = fa._evidence_pack(_conv(), _cascade())
    valid = {"memory_storage"}
    text = json.dumps({"regime_read": "r", "theses": [
        {"theme": "memory_storage",
         "mechanism": "supply tight",
         "kill_criteria": ["x"],
         "evidence": ["ok", "T1"],   # short items
         "confidence": "low"},
    ]})
    out = fa._parse(text, valid, pack=pack)
    assert out is not None
    th = out["theses"][0]
    assert th["n_grounded"] == th["n_total_evidence"]


# ── _clamp_string utility tests ───────────────────────────────────────────────

def test_clamp_string_removes_forecast_fragment():
    s = "the band will loosen; price target $180"
    clamped, removed = fa._clamp_string(s)
    assert "$180" not in clamped
    assert "[forecast removed]" in clamped
    assert len(removed) > 0


def test_clamp_string_no_forecast_unchanged():
    s = "supply tight while revisions are flat"
    clamped, removed = fa._clamp_string(s)
    assert clamped == s
    assert removed == []


# ── _check_evidence_grounding utility tests ───────────────────────────────────

def test_grounding_check_case_insensitive():
    items = ["TIGHT band confirmed", "fabricated claim about 50% upside"]
    pack_text = "tight band confirmed present in tight data"
    annotated, n_grounded, n_total = fa._check_evidence_grounding(items, pack_text)
    assert n_total == 2
    # "tight band confirmed" is in pack_text (case-insensitive)
    assert n_grounded >= 1
    # "fabricated claim about 50% upside" is not in pack_text
    ungrounded = [e for e in annotated if isinstance(e, dict) and e.get("ungrounded")]
    assert len(ungrounded) >= 1
