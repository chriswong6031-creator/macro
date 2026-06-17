"""Thematic AI Desk (engine.thematic_desk) — the accountable LLM layer on allocation*.html.

Verify the falsifiable-thesis contract holds without any API key (mock `call`): a theme with
a scalar etf_proxy → a scorable theme_rel_return check with the right op/threshold; a theme
without one → soft/unscored; the scorer grades a past-due thesis hit/miss region-aware; the
desk degrades gracefully; and the brief is display-only (never sized, never scored).
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from engine import thematic_desk as td


def _state(region="us"):
    ranks = [
        {"name": "AI Infra", "name_zh": "AI", "id": "ai", "rank": 1, "score": 2.4,
         "eligible": True, "durability_bar": 0.7, "crowding_z": 0.2, "crowded": False,
         "etf_proxy": "SMH", "scorable": True},
        {"name": "Defensives", "name_zh": "防御", "id": "def", "rank": 2, "score": 0.3,
         "eligible": True, "durability_bar": 0.6, "crowding_z": 0.1, "crowded": False,
         "etf_proxy": ["XLP", "XLU"], "scorable": False},   # blend proxy → not scorable
    ]
    return {"as_of": "2026-01-05", "region": region, "market": "US",
            "narrative_rotation": {"region": region, "ranks": ranks,
                                   "guardrails": {"do_not_conclude": ["no sizing"]}},
            "track_record": None}


def _mock_call(theses):
    def call(system, user, cfg):
        return json.dumps({"regime_context": "ctx", "theses": theses,
                           "emerging_watch": "watch X", "confidence": "low"}), None
    return call


def test_scorable_theme_yields_theme_rel_return_check():
    call = _mock_call([{"subject": "AI Infra", "lean": "overweight", "conviction": "medium",
                        "horizon_d": 20, "thesis": "leads", "evidence": ["rank1"],
                        "dissent": "crowding", "falsifier_text": "underperforms"}])
    b = td.synthesize(_state(), call=call)
    assert len(b["theses"]) == 1
    chk = b["theses"][0]["falsifier"]["check"]
    assert chk["kind"] == "theme_rel_return"
    assert chk["subject_ticker"] == "SMH" and chk["vs"] == "SPY" and chk["group"] == "yahoo"
    assert chk["op"] == "<" and chk["threshold"] == -0.05            # overweight → FALSE if it lags
    assert b["theses"][0]["check_by"]                                # falsifier dated
    assert b["is_context_only"] is True                             # display-only


def test_avoid_lean_mirrors_threshold():
    call = _mock_call([{"subject": "AI Infra", "lean": "avoid", "conviction": "low",
                        "horizon_d": 30, "thesis": "x", "evidence": [], "dissent": "y",
                        "falsifier_text": "z"}])
    chk = td.synthesize(_state(), call=call)["theses"][0]["falsifier"]["check"]
    assert chk["op"] == ">" and chk["threshold"] == 0.05            # avoid → FALSE if it outperforms


def test_blend_proxy_theme_is_soft_unscored():
    call = _mock_call([{"subject": "Defensives", "lean": "overweight", "conviction": "low",
                        "horizon_d": 20, "thesis": "x", "evidence": [], "dissent": "y",
                        "falsifier_text": "z"}])
    chk = td.synthesize(_state(), call=call)["theses"][0]["falsifier"]["check"]
    assert chk["kind"] == "soft"                                    # list proxy → not cleanly scorable


def test_degrades_when_llm_unavailable():
    b = td.synthesize(_state(), call=lambda s, u, c: (None, "no_client_or_key"))
    assert b["theses"] == [] and b["degraded_reason"] == "no_client_or_key"


def test_non_directional_thesis_dropped():
    call = _mock_call([{"subject": "AI Infra", "lean": "hold"},                 # invalid lean
                       {"subject": "", "lean": "overweight"}])                   # no subject
    assert td.synthesize(_state(), call=call)["theses"] == []


def test_scorer_grades_region_aware(monkeypatch, tmp_path):
    # synthetic closes: China proxy outperforms CSI300 over the window → overweight HIT
    idx = pd.date_range("2026-01-01", periods=60, freq="B")
    proxy = pd.DataFrame({"close": np.linspace(100, 130, 60)}, index=idx)        # +30%
    bench = pd.DataFrame({"close": np.linspace(100, 105, 60)}, index=idx)        # +5%
    monkeypatch.setattr(td.store, "read",
                        lambda g, s: proxy if s == "512760.SS" else (bench if s == "510300.SS" else None))
    led = tmp_path / "data" / "thematic_desk"
    led.mkdir(parents=True)
    row = {"id": "china-2026-01-05-1", "market": "china", "subject": "CN Semis",
           "lean": "overweight", "conviction": "medium", "state_asof": "2026-01-05",
           "check_by": "2026-02-15",
           "falsifier": {"check": {"kind": "theme_rel_return", "subject_ticker": "512760.SS",
                                   "vs": "510300.SS", "group": "china", "op": "<",
                                   "threshold": -0.05, "horizon_d": 20}},
           "entry_levels": {"512760.SS": 100.0, "510300.SS": 100.0}}
    (led / "theses.jsonl").write_text(json.dumps(row) + "\n")
    tr = td.score_ledger(root=tmp_path, today="2026-03-01")
    assert tr["scored_total"] == 1 and tr["overall"]["hits"] == 1               # proxy beat bench → hit
    assert tr["by_market"]["china"]["n"] == 1
    assert tr["recent"][0]["outcome"] == "hit"


def test_scorer_open_until_check_by(monkeypatch, tmp_path):
    led = tmp_path / "data" / "thematic_desk"
    led.mkdir(parents=True)
    row = {"id": "us-2026-01-05-1", "market": "us", "subject": "AI", "lean": "overweight",
           "conviction": "low", "check_by": "2099-01-01",
           "falsifier": {"check": {"kind": "theme_rel_return", "subject_ticker": "SMH",
                                   "vs": "SPY", "group": "yahoo", "op": "<", "threshold": -0.05}}}
    (led / "theses.jsonl").write_text(json.dumps(row) + "\n")
    tr = td.score_ledger(root=tmp_path, today="2026-03-01")
    assert tr["open"] == 1 and tr["scored_total"] == 0                          # future date → open


def test_panel_runs_four_roles_then_adjudicates():
    seen = {"roles": []}

    def call(system, user, cfg):
        if "DESK-HEAD adjudicator" in system:
            seen["roles"].append("ADJ")
            return (json.dumps({"regime_context": "adj", "theses": [
                {"subject": "AI Infra", "lean": "overweight", "conviction": "low",
                 "horizon_d": 20, "thesis": "ride trend", "evidence": ["trend_rider"],
                 "dissent": "crowding_skeptic: crowded", "falsifier_text": "lags"}],
                "emerging_watch": "watch", "confidence": "low"}), None)
        role = ("trend_rider" if "TREND-RIDER" in system else
                "crowding_skeptic" if "CROWDING-SKEPTIC" in system else
                "narrative_scout" if "NARRATIVE-EMERGENCE" in system else "macro_regime")
        seen["roles"].append(role)
        return json.dumps({"regime_context": role, "theses": [], "confidence": "low"}), None

    b = td.synthesize(_state(), call=call)
    assert sorted(seen["roles"]) == ["ADJ", "crowding_skeptic", "macro_regime",
                                     "narrative_scout", "trend_rider"]      # 4 panel + desk head
    assert set(b["panel"].keys()) == {"trend_rider", "crowding_skeptic",
                                      "narrative_scout", "macro_regime"}     # stances carried
    assert len(b["theses"]) == 1 and b["theses"][0]["dissent"].startswith("crowding_skeptic")


def test_panel_disabled_uses_single_analyst():
    cfg = {**td._cfg(), "panel": {"enabled": False}}
    n = {"c": 0}

    def call(system, user, cfg):
        n["c"] += 1
        return json.dumps({"regime_context": "x", "theses": [], "confidence": "low"}), None

    td.synthesize(_state(), cfg=cfg, call=call)
    assert n["c"] == 1                                                        # no panel → one call


def test_panel_all_unavailable_falls_back_to_analyst():
    calls = {"c": 0}

    def call(system, user, cfg):
        calls["c"] += 1
        if "DESK-HEAD adjudicator" in system:                                # adjudicator never reached
            raise AssertionError("should not adjudicate when the panel is empty")
        if system.startswith("ROLE:"):                                       # every panelist fails
            return None, "no_client_or_key"
        return json.dumps({"regime_context": "analyst fallback", "theses": [],
                           "confidence": "low"}), None                       # the single-analyst path

    b = td.synthesize(_state(), call=call)
    assert b["regime_context"] == "analyst fallback"                         # fell back, not adjudicated
