"""Narrative Brain tests (hermetic — LLM call injected, no token/network)."""
from __future__ import annotations

import json

from engine import narrative_brain as nb


def _durability_json(verdict="ENTER"):
    return json.dumps({
        "strength": 80, "durability": 75, "continuity": 70, "composite": 75,
        "verdict": verdict, "confidence": "MED",
        "rationale": "Federal activity leads price [P2][P3].", "rationale_zh": "联邦活动领先价格 [P2]。",
        "evidence_ids": ["P2", "P3"], "dissent": "Could be a one-off award.",
        "falsifiable_check": {"confirm": "proxy beats SPY", "disconfirm": "proxy lags SPY by 5% over 21d"}})


def _rotation_json():
    return json.dumps({"summary": "defense leads on activity", "summary_zh": "国防靠活动领先",
                       "accumulate": ["defense"], "reduce": [], "watch": ["watch contracts"], "confidence": "MED"})


def _stub_call(verdict="ENTER"):
    def call(model, system, user):
        if "durability" in system.lower():
            return _durability_json(verdict), None
        return _rotation_json(), None
    return call


def _theme(basket, name, state="POSITIVE_DIVERGENCE", lifecycle="emerging"):
    return {"basket": basket, "name": name, "name_zh": name, "category": "x",
            "state": state, "lifecycle": lifecycle,
            "evidence": [{"id": "P2", "text": "divergence z = 1.8 (activity ahead of price)."},
                         {"id": "P3", "text": "sources: Federal contracts z=1.9, Congress z=0.6."}]}


def _evidence(themes):
    return {"as_of": "2026-06-19", "region": "us", "themes": themes}


def test_synthesize_assessments_and_rotation():
    ev = _evidence([_theme("defense", "Defense"), _theme("space_economy", "Space")])
    out = nb.synthesize(ev, call=_stub_call())
    assert out["schema"] == "narrative_brain.v1"
    assert {a["basket"] for a in out["assessments"]} == {"defense", "space_economy"}
    d = out["assessments"][0]
    assert d["verdict"] in nb._VERDICTS and d["evidence_ids"] and d["rationale_zh"]
    assert d["falsifiable_check"]["disconfirm"]
    assert out["rotation"]["accumulate"] == ["defense"]


def test_reconcile_clamps_enter_on_fading_theme():
    # model says ENTER, but radar flags the theme fading -> clamp to MONITOR
    ev = _evidence([_theme("critical_minerals", "Critical Minerals",
                           state="NEGATIVE_DIVERGENCE", lifecycle="fading")])
    out = nb.synthesize(ev, call=_stub_call("ENTER"))
    a = out["assessments"][0]
    assert a["verdict"] == "MONITOR" and a.get("override_reason")


def test_reconcile_allows_enter_on_healthy_theme():
    ev = _evidence([_theme("defense", "Defense", state="POSITIVE_DIVERGENCE", lifecycle="emerging")])
    out = nb.synthesize(ev, call=_stub_call("ENTER"))
    assert out["assessments"][0]["verdict"] == "ENTER"


def test_is_risk_blocked():
    assert nb._is_risk_blocked({"state": "NEGATIVE_DIVERGENCE", "lifecycle": "emerging"})
    assert nb._is_risk_blocked({"state": "CONFIRMED_UP", "lifecycle": "fading"})
    assert not nb._is_risk_blocked({"state": "POSITIVE_DIVERGENCE", "lifecycle": "emerging"})


def test_max_themes_cap(monkeypatch):
    monkeypatch.setattr(nb, "_cfg", lambda: {**nb._DEFAULTS, "max_themes": 1})
    ev = _evidence([_theme("a", "A"), _theme("b", "B"), _theme("c", "C")])
    out = nb.synthesize(ev, call=_stub_call())
    assert len(out["assessments"]) == 1


def test_degraded_when_no_call_or_evidence():
    assert nb.synthesize(_evidence([_theme("a", "A")]), call=None).get("degraded_reason") in (
        "no_client_or_key", "no_usable_reply", None)   # env-dependent; just must not raise
    assert nb.synthesize(None, call=_stub_call())["degraded_reason"] == "no_evidence"
    bad = nb.synthesize(_evidence([_theme("a", "A")]), call=lambda *a: (None, "x"))
    assert bad["degraded_reason"] == "no_usable_reply"


def test_gather_evidence_reads_radar(tmp_path):
    fdir = tmp_path / "site" / "basketdata"
    fdir.mkdir(parents=True)
    radar = {"as_of": "2026-06-19", "flags": [
        {"basket": "defense", "name": "Defense", "name_zh": "国防", "category": "Industrials",
         "state": "POSITIVE_DIVERGENCE", "lifecycle": "emerging", "divergence": 1.8,
         "observable": {"accel": 1.6, "n_sources": 2, "covered": ["LMT", "NOC"],
                        "sources": [{"name": "usaspending", "label_en": "Federal contracts", "z": 1.9}]},
         "consensus": {"rel_60d": -0.08, "z": -0.9, "dir": -1},
         "news": {"velocity": 12.4, "acceleration": 2.1, "unscheduled_share": 0.4}}]}
    (fdir / "radar.json").write_text(json.dumps(radar))
    ev = nb.gather_evidence(root=tmp_path)
    assert ev and len(ev["themes"]) == 1
    t = ev["themes"][0]
    assert t["basket"] == "defense" and t["state"] == "POSITIVE_DIVERGENCE"
    assert {e["id"] for e in t["evidence"]} >= {"P1", "P2", "P3", "P4"}
    assert nb.gather_evidence(root=tmp_path / "missing") is None      # no radar -> None


def test_ledger_idempotent_and_shape(tmp_path):
    (tmp_path / "data" / "baskets").mkdir(parents=True)
    (tmp_path / "data" / "baskets" / "membership.json").write_text(json.dumps(
        {"baskets": {"defense": {"etf_proxy": "ITA"}}}))
    brief = {"as_of": "2026-06-19", "assessments": [
        {"basket": "defense", "verdict": "ENTER", "confidence": "MED", "composite": 75,
         "rationale": "x", "falsifiable_check": {"disconfirm": "proxy lags SPY"}},
        {"basket": "space_economy", "verdict": "MONITOR"}]}   # MONITOR -> soft, not logged
    n1 = nb._append_ledger(brief, root=tmp_path)
    n2 = nb._append_ledger(brief, root=tmp_path)
    assert n1 == 1 and n2 == 0                                 # only ENTER logged; idempotent
    rec = json.loads((tmp_path / "data" / "narrative_brain" / "theses.jsonl").read_text().splitlines()[0])
    assert rec["lean"] == "constructive" and rec["subject_ticker"] == "ITA"
    assert rec["falsifier"]["check"]["kind"] == "rel_return" and rec["falsifier"]["check"]["op"] == "<"


def test_run_disabled_returns_none(monkeypatch):
    monkeypatch.setattr(nb, "_cfg", lambda: {**nb._DEFAULTS, "enabled": False})
    assert nb.run(persist=False) is None
