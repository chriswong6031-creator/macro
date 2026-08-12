"""Regression tests for the 2026-08-12 Market-State / Risk-Radar authority audit."""
from __future__ import annotations

import json

import pandas as pd

from engine import market_state as ms
from engine import market_state_audit as msa
from engine import risk_radar as rr
from engine import risk_radar_audit as rra
from scripts import build_site


_RISK_ON_GATE = {"met": False, "spy_below_200dma": False, "breadth_weak": False}


def _two_rows(**cols) -> pd.DataFrame:
    idx = pd.to_datetime(["2026-08-10", "2026-08-11"])
    return pd.DataFrame({key: [value, value] for key, value in cols.items()}, index=idx)


def test_midterm_calendar_cannot_promote_a_66_point_read_to_caution():
    out = rr.compute(
        sigs=_two_rows(credit_oas_roc=0.665, credit_hyg_tlt=0.665),
        asof="2026-08-11",
        gate=_RISK_ON_GATE,
    )
    assert out["top_score"] == 66.5
    assert out["state"] == "watch"
    assert out["cycle_context"]["modulation"]["band_delta"] == 0.0
    assert out["can_force"] is False
    assert out["authority"]["tier"] == "advisory"


def test_unconfirmed_bubble_read_is_labeled_as_extension_not_blowoff():
    out = rr.compute(
        sigs=_two_rows(bubble_ext=0.744, bubble_leadership=0.214),
        asof="2026-08-11", gate=_RISK_ON_GATE,
    )
    assert out["top_score"] == 66.5
    assert out["dominant_scare"] == "bubble"
    assert out["dominant_label_en"] == "Trend extension watch"
    assert out["scares"][0]["firing_legs"][0]["confirmed"] is False


def test_below_base_caution_publishes_candidate_but_cannot_cap_market_state():
    latest = {
        "risk_radar": {
            "state": "caution",
            "alert": False,
            "can_force": False,
            "top_score": 71,
            "state_ungated": "caution",
            "drawdown_prob": {"h21": 0.16, "base_h21": 0.178},
            "scares": [],
        },
        "conditions": {"complacency": {"state": "watch", "breadth_div": False}},
        "turning_point": {"present": False},
    }
    overrides = []
    mapped = ms._radar_override(latest, overrides)
    assert mapped["candidate_ceiling"] is not None
    assert mapped["ceiling"] is None
    assert mapped["binding"] is False
    assert mapped["amp_keys"] == []
    assert overrides == []


def test_advisory_radar_does_not_manufacture_a_binding_flip_claim():
    components = [
        {"key": "trend", "label_en": "Trend", "label_zh": "趋势", "score": 90,
         "weight": 0.5},
        {"key": "breadth", "label_en": "Breadth", "label_zh": "广度", "score": 90,
         "weight": 0.5},
    ]
    radar = {"state": "caution", "can_force": False, "ceiling": None,
             "candidate_ceiling": 56, "authority": {"tier": "advisory"}}
    assert ms._radar_escalation_claim(radar, 59) is None
    en, _zh = ms._flip_text(
        components, "RISK_ON", raw_score=90, radar=radar, overrides=[]
    )
    assert "Risk Radar escalates" not in en


def test_confirmed_above_base_loud_state_can_still_bind(monkeypatch):
    monkeypatch.setattr(
        ms, "_rr_scorecard_track",
        lambda _market: {"monitoring": {"log_fresh": True}},
    )
    latest = {
        "risk_radar": {
            "state": "elevated",
            "alert": True,
            "can_force": True,
            "top_score": 82,
            "state_ungated": "elevated",
            "drawdown_prob": {"h21": 0.25, "base_h21": 0.178},
            "authority": {"tier": "binding", "can_force": True,
                          "note_en": "Binding guard", "note_zh": "约束性护栏"},
            "scares": [],
        },
        "conditions": {"complacency": {"breadth_div": False}},
        "turning_point": {"present": False},
    }
    overrides = []
    mapped = ms._radar_override(latest, overrides)
    assert mapped["ceiling"] == mapped["candidate_ceiling"]
    assert mapped["binding"] is True
    assert overrides and overrides[0]["kind"] == "radar"


def test_stale_display_monitor_does_not_rewrite_producer_authority(monkeypatch):
    monkeypatch.setattr(
        ms, "_rr_scorecard_track",
        lambda _market: {"monitoring": {"log_fresh": False}},
    )
    latest = {
        "risk_radar": {
            "market": "us", "state": "elevated", "alert": True, "can_force": True,
            "top_score": 82, "state_ungated": "elevated",
            "authority": {"tier": "binding", "can_force": True,
                          "reason": "confirmed_validated_loud_edge"},
            "drawdown_prob": {"h21": 0.25, "base_h21": 0.178}, "scares": [],
        },
        "conditions": {"complacency": {"breadth_div": False}},
        "turning_point": {"present": False},
    }
    mapped = ms._radar_override(latest, [])
    assert mapped["can_force"] is True
    assert mapped["binding"] is True
    assert mapped["ceiling"] is not None
    assert mapped["track"]["monitoring"]["log_fresh"] is False


def test_display_only_complacency_does_not_change_volatility_component():
    base = {"risk_appetite": {"vix_term": 0.88},
            "complacency": {"vix_pctile": 0.18, "state": "calm"}}
    caution = {"risk_appetite": {"vix_term": 0.88},
               "complacency": {"vix_pctile": 0.18, "state": "watch"}}
    assert ms._comp_vol({"conditions": base})["score"] == ms._comp_vol({"conditions": caution})["score"]


def test_radar_authority_requires_loud_above_base_confirmed_evidence():
    scare = {"tier": "A", "band": "caution",
             "firing_legs": [{"leg": "credit_oas_roc", "confirmed": True}]}
    strong = rr._market_state_authority(
        "elevated", True, [scare], {"state_above_base": True}, rr._calib()
    )
    assert strong["can_force"] is True
    assert rr._market_state_authority(
        "caution", False, [scare], {"state_above_base": True}, rr._calib()
    )["can_force"] is False
    assert rr._market_state_authority(
        "elevated", True, [scare], {"state_above_base": False}, rr._calib()
    )["can_force"] is False
    unconfirmed = {"tier": "A", "band": "elevated",
                   "firing_legs": [{"leg": "credit_oas_roc", "confirmed": False}]}
    assert rr._market_state_authority(
        "elevated", True, [unconfirmed], {"state_above_base": True}, rr._calib()
    )["can_force"] is False


def test_calm_confirmed_scare_cannot_authorize_an_unconfirmed_loud_scare():
    calm_confirmed = {
        "tier": "A", "band": "watch",
        "firing_legs": [{"leg": "credit_oas_roc", "confirmed": True}],
    }
    loud_unconfirmed = {
        "tier": "A", "band": "elevated",
        "firing_legs": [{"leg": "rates_move", "confirmed": False}],
    }
    out = rr._market_state_authority(
        "elevated", True, [loud_unconfirmed, calm_confirmed],
        {"state_above_base": True}, rr._calib(),
    )
    assert out["can_force"] is False
    assert out["confirmed_validated_legs"] == []


def test_history_chart_prefers_measured_raw_score(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    path = data_dir / "market_state" / "forward_log.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"asof": "2026-08-07", "score": 50, "raw_score": 78}) + "\n")
    monkeypatch.setattr(build_site.config, "data_dir", lambda: data_dir)
    assert build_site._ms_history_view()[0]["score"] == 78


def test_rotation_view_separates_current_pulse_from_legacy_damage_cohort(monkeypatch):
    from engine import sector_pulse

    pulse = {
        "as_of": "2026-08-10",
        "themes": [
            {"id": "ai_software", "name": "AI Software", "name_zh": "AI 软件",
             "heat": "heating", "rank": 1, "rank_delta_5d": 10, "score": 73,
             "label": "dominant", "reco": "accumulate"},
            {"id": "memory_storage", "name": "Memory", "name_zh": "内存",
             "heat": "broken", "rank": 42, "rank_delta_5d": -8, "score": 40,
             "label": "deteriorating", "reco": "avoid"},
        ],
    }
    monkeypatch.setattr(sector_pulse, "build_pulse", lambda _region: pulse)
    view = build_site._sector_heat_view()
    assert [row["id"] for row in view["rotation"]] == ["ai_software", "memory_storage"]
    assert view["rotation"][0]["rank"] == 1
    assert view["rotation"][1]["heat"] == "broken"


def test_risk_copy_uses_actual_odds_not_a_fixed_lift_claim():
    dominant = {"label_en": "Bubble / blow-off unwind", "label_zh": "泡沫/见顶回吐",
                "score": 66.5, "firing_legs": [{"leg": "bubble_ext", "pctile": 0.744}]}
    en, _zh = rr._headline(
        "caution", dominant, [dominant],
        {"h21": 0.16, "base_h21": 0.178, "lift_h21": 0.9, "state_above_base": False},
    )
    assert "16% vs 18% normal" in en
    assert "1.5-2x" not in en
    assert "not a measured edge" in en


def test_risk_forward_ledger_preserves_authority_and_confirmation_provenance():
    snap = {
        "asof": "2026-08-11", "state": "elevated", "alert": True,
        "state_ungated": "elevated", "can_force": True,
        "authority": {"tier": "binding", "reason": "confirmed_validated_loud_edge",
                      "confirmed_validated_legs": ["credit_oas_roc"]},
        "scares": [{"scare": "credit", "score": 82, "band": "elevated",
                    "firing_legs": [{"leg": "credit_oas_roc", "pctile": 0.94,
                                     "confirmed": True, "era_robust": True,
                                     "lift_2020": 1.4}]}],
    }
    entry = rra._entry_from_snapshot(snap)
    assert entry["can_force"] is True
    assert entry["authority_reason"] == "confirmed_validated_loud_edge"
    assert entry["confirmed_validated_legs"] == ["credit_oas_roc"]
    assert entry["scares"]["credit"]["firing_legs"][0]["confirmed"] is True


def test_market_state_ledger_preserves_measured_vs_policy_score_provenance():
    snap = {
        "asof": "2026-08-11", "verdict": "RISK_ON", "score": 78, "raw_score": 78,
        "score_source": "blend", "score_ceiling": None, "score_caps": [],
        "radar": {"state": "watch", "top_score": 67, "can_force": False,
                  "binding": False,
                  "track": {"monitoring": {"log_fresh": True}},
                  "authority": {"reason": "early_tier_advisory"}},
    }
    entry = msa._entry_from_snapshot(snap)
    assert entry["score_source"] == "blend"
    assert entry["radar_can_force"] is False
    assert entry["radar_binding"] is False
    assert entry["radar_monitor_fresh"] is True
    assert entry["radar_authority_reason"] == "early_tier_advisory"
