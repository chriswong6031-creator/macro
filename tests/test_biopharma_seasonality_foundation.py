"""Contract and multiplicity tests for the clean-room seasonality foundation."""
from __future__ import annotations

import json
from datetime import date

import pytest

from engine.seasonality.contracts import (
    BIOTEMPORAL_EVENT_SCHEMA,
    ContractError,
    build_neuralweb_state,
    build_prophet_overlay,
    validate_bitemporal_event,
)
from engine.seasonality.foundation import build_methodology_manifest
from engine.seasonality.multiplicity import benjamini_yekutieli, max_t_adjusted_p_values
from scripts.build_biopharma_seasonality import build

_HASH_A = "sha256:" + "a" * 64
_HASH_B = "sha256:" + "b" * 64


def _event() -> dict:
    return {
        "schema": BIOTEMPORAL_EVENT_SCHEMA,
        "event_id": "evt:issuer-1:pdufa-2027-01",
        "issuer_id": "issuer:1",
        "event_type": "fda_pdufa",
        "status": "scheduled",
        "date_precision": "exact_date",
        "scheduled_start": "2027-01-15T00:00:00Z",
        "scheduled_end": "2027-01-15T23:59:59Z",
        "actual_at": None,
        "certainty": 0.9,
        "published_at": "2026-07-30T20:00:00Z",
        "ingested_at": "2026-07-30T20:05:00Z",
        "known_at": "2026-07-30T20:05:00Z",
        "effective_at": "2027-01-15T00:00:00Z",
        "source_class": "issuer_filing",
        "source_url": "https://example.test/filing",
        "source_hash": _HASH_A,
    }


def _state() -> dict:
    return build_neuralweb_state(
        artifact_id="biopharma-seasonality-state",
        entity={"type": "issuer", "id": "issuer:1", "ticker": "BIO"},
        asof="2026-08-01",
        available_at="2026-08-01T21:30:00Z",
        expires_at="2026-08-02T21:30:00Z",
        clock={"type": "event", "phase": "pre_event_20d", "event_id": "evt:1"},
        forecast={
            "target": "excess_return_gt_0",
            "horizon_td": 20,
            "p": 0.58,
            "p_baseline": 0.51,
            "edge": 0.07,
            "ci90": [0.48, 0.65],
        },
        evidence={
            "n_independent": 74,
            "n_issuers": 31,
            "n_date_clusters": 48,
            "live_n": 18,
            "q_by": 0.07,
            "p_max_t": None,
            "spa_p": 0.03,
        },
        uncertainty={"abstain": False, "flags": ["forward_sample_thin"]},
        provenance={
            "model_version": "seasonality-2026q3",
            "pattern_spec_hash": _HASH_A,
            "data_snapshot": _HASH_B,
        },
    )


def test_bitemporal_event_accepts_future_effective_date():
    validated = validate_bitemporal_event(_event())
    assert validated["effective_at"].startswith("2027-")


def test_bitemporal_event_rejects_knowledge_before_ingestion():
    event = _event()
    event["known_at"] = "2026-07-30T20:01:00Z"
    with pytest.raises(ContractError, match="known_at cannot precede ingested_at"):
        validate_bitemporal_event(event)


def test_neuralweb_state_is_context_only_and_cannot_rank():
    state = _state()
    assert state["is_context_only"] is True
    assert state["authority"]["may_rank"] is False
    assert state["authority"]["may_originate"] is False
    assert state["authority"]["may_boost_confidence"] is False


def test_neuralweb_state_rejects_probability_edge_mismatch():
    with pytest.raises(ContractError, match="forecast.edge must equal"):
        build_neuralweb_state(
            artifact_id="biopharma-seasonality-state",
            entity={"type": "issuer", "id": "issuer:1"},
            asof="2026-08-01",
            available_at="2026-08-01T00:00:00Z",
            expires_at="2026-08-02T00:00:00Z",
            clock={"type": "calendar", "phase": "august"},
            forecast={
                "target": "excess_return_gt_0",
                "horizon_td": 20,
                "p": 0.6,
                "p_baseline": 0.5,
                "edge": 0.2,
                "ci90": [0.4, 0.7],
            },
            evidence={"n_independent": 12, "n_issuers": 1, "n_date_clusters": 12, "live_n": 0},
            uncertainty={"abstain": True, "flags": ["not_forward_validated"]},
            provenance={"model_version": "test", "pattern_spec_hash": _HASH_A, "data_snapshot": _HASH_B},
        )


def test_prophet_overlay_cannot_cap_on_positive_context():
    with pytest.raises(ContractError, match="requires adverse_event=true"):
        build_prophet_overlay(
            plan_id="BIO-BULL-2026-08-01",
            seasonality_state_ref="sha256:state",
            horizon_match=True,
            event_inside_plan_horizon=True,
            overlap_with_existing_features=False,
            action="CAP_CONFIDENCE",
            reason_codes=["calendar_tailwind"],
            expires_at="2026-08-02T00:00:00Z",
            adverse_event=False,
            deescalation_gate_passed=True,
            confidence_cap=0.6,
        )


def test_prophet_adverse_cap_requires_separate_gate():
    with pytest.raises(ContractError, match="separately passed"):
        build_prophet_overlay(
            plan_id="BIO-BULL-2026-08-01",
            seasonality_state_ref="sha256:state",
            horizon_match=True,
            event_inside_plan_horizon=True,
            overlap_with_existing_features=False,
            action="CAP_CONFIDENCE",
            reason_codes=["binary_event_hazard"],
            expires_at="2026-08-02T00:00:00Z",
            adverse_event=True,
            deescalation_gate_passed=False,
            confidence_cap=0.6,
        )


def test_prophet_adverse_cap_stays_shrink_only_after_gate():
    overlay = build_prophet_overlay(
        plan_id="BIO-BULL-2026-08-01",
        seasonality_state_ref="sha256:state",
        horizon_match=True,
        event_inside_plan_horizon=True,
        overlap_with_existing_features=False,
        action="CAP_CONFIDENCE",
        reason_codes=["binary_event_hazard"],
        expires_at="2026-08-02T00:00:00Z",
        adverse_event=True,
        deescalation_gate_passed=True,
        confidence_cap=0.6,
    )
    assert overlay["confidence_cap"] == 0.6
    assert not any(overlay["authority"].values())


def test_benjamini_yekutieli_known_panel_and_order():
    adjusted = benjamini_yekutieli([0.20, 0.01, 0.02])
    assert adjusted == pytest.approx([0.3666666667, 0.055, 0.055])


def test_max_t_uses_family_maximum_and_finite_sample_correction():
    adjusted = max_t_adjusted_p_values(
        [2.0, 0.5],
        [[1.0, 1.5], [2.1, 0.1], [0.3, 0.4]],
    )
    assert adjusted == pytest.approx([0.5, 0.75])


def test_methodology_manifest_admits_no_live_forecasts():
    manifest = build_methodology_manifest(date(2026, 8, 1))
    assert manifest["status"] == "foundation_contracts_live"
    assert manifest["availability"]["live_forecasts"] is False
    assert manifest["authority"]["may_rank"] is False


def test_build_writes_public_methodology_manifest(tmp_path):
    output = build(root=tmp_path, as_of=date(2026, 8, 1))
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert output == tmp_path / "site" / "seasonalitydata" / "methodology.json"
    assert payload["schema"] == "biopharma_seasonality.methodology.v1"
    assert payload["as_of"] == "2026-08-01"
