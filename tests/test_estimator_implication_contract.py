"""Contract + behavior tests for engine/estimator_implication.py (packet B-A-F10-4)."""
from __future__ import annotations

import copy
import re
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from engine.estimator_implication import (
    AUTHORITY_KEYS,
    FORBIDDEN_KEYS,
    REPO_ROOT,
    SC_MODULE_PATH,
    ImplicationContractError,
    build_estimator_implications,
    compose_event_study_implication,
    compose_synthetic_control_implication,
    compute_payload_id,
    load_contract,
    sha256_file,
    validate_payload,
)
from engine.seasonality.event_study import UnregisteredSearchFamily


class _StubLedger:
    """A duck-typed ledger with no registered families, for the refusal test."""

    def families(self):
        return []

    def effective_n(self, family):
        return 0


def test_contract_file_is_a_valid_draft_2020_12_schema():
    Draft202012Validator.check_schema(load_contract())


def test_synthetic_control_payload_validates_against_the_contract():
    payload = compose_synthetic_control_implication()
    validate_payload(payload)


def test_provenance_names_the_producing_module_and_its_live_digest():
    payload = compose_synthetic_control_implication()
    assert payload["provenance"]["producing_module"] == "engine/synthetic_control.py"
    live_digest = sha256_file(REPO_ROOT / SC_MODULE_PATH)
    assert payload["provenance"]["producing_module_sha256"] == live_digest


@pytest.mark.parametrize("forbidden_key", sorted(FORBIDDEN_KEYS))
def test_contract_rejects_promotion_fields(forbidden_key):
    payload = compose_synthetic_control_implication()
    payload = copy.deepcopy(payload)
    payload[forbidden_key] = 1
    with pytest.raises((ImplicationContractError, ValidationError)):
        validate_payload(payload)


def test_contract_rejects_nested_promotion_field():
    payload = copy.deepcopy(compose_synthetic_control_implication())
    payload["point_estimate"]["rank"] = 1
    with pytest.raises(ValidationError):
        validate_payload(payload)


def test_unregistered_event_study_family_is_refused():
    with pytest.raises(UnregisteredSearchFamily):
        compose_event_study_implication(ledger=_StubLedger())


def test_registered_family_block_is_required_and_cannot_be_null():
    base = compose_synthetic_control_implication()

    missing = copy.deepcopy(base)
    del missing["registered_family"]
    with pytest.raises(ValidationError):
        validate_payload(missing)

    unregistered = copy.deepcopy(base)
    unregistered["registered_family"]["registered"] = False
    with pytest.raises(ValidationError):
        validate_payload(unregistered)


def test_null_values_carry_a_plain_word_null_reason_in_both_languages():
    payload = compose_synthetic_control_implication()
    assert payload["honest_n"]["episode_n"] is None
    assert payload["null_reasons"], "expected at least one null_reasons entry"
    for nr in payload["null_reasons"]:
        assert nr["reason"]["en"].strip()
        assert nr["reason"]["zh"].strip()
        assert nr["detail"]["en"].strip()
        assert nr["detail"]["zh"].strip()


def test_payload_id_is_deterministic_and_content_bound():
    payload = compose_synthetic_control_implication()
    recomputed = compute_payload_id(
        composer_version=payload["composer_version"],
        estimator_id=payload["estimator_id"],
        result_artifact_path=payload["provenance"]["result_artifact_path"],
        result_artifact_sha256=payload["provenance"]["result_artifact_sha256"],
        selection_id=payload["selection"]["selection_id"],
        family_id=payload["registered_family"]["family_id"],
    )
    assert recomputed == payload["payload_id"]

    mutated = compute_payload_id(
        composer_version=payload["composer_version"],
        estimator_id=payload["estimator_id"],
        result_artifact_path=payload["provenance"]["result_artifact_path"],
        result_artifact_sha256=payload["provenance"]["result_artifact_sha256"],
        selection_id="a-different-selection",
        family_id=payload["registered_family"]["family_id"],
    )
    assert mutated != payload["payload_id"]


def test_authority_block_is_exactly_five_literal_false_keys():
    payload = copy.deepcopy(compose_synthetic_control_implication())
    validate_payload(payload)  # sanity: base payload passes

    extra = copy.deepcopy(payload)
    extra["authority"]["extra_authority"] = False
    with pytest.raises(ValidationError):
        validate_payload(extra)

    flipped = copy.deepcopy(payload)
    flipped["authority"]["trading_authority"] = True
    with pytest.raises(ValidationError):
        validate_payload(flipped)

    assert set(AUTHORITY_KEYS) == {
        "forecast_authority", "ranking_authority", "gating_authority",
        "sizing_authority", "trading_authority",
    }


def test_composer_performs_no_writes_and_no_network():
    source = (REPO_ROOT / "engine" / "estimator_implication.py").read_text(encoding="utf-8")
    assert not re.search(r'open\([^)]*["\']w', source)
    assert not re.search(r'open\([^)]*["\']a', source)
    assert ".write_text(" not in source
    for banned_import in ("import requests", "import urllib", "import httpx"):
        assert banned_import not in source


def test_build_returns_a_typed_refusal_not_a_fabricated_payload():
    envelope = build_estimator_implications()
    assert envelope["schema"] == "mastermind.estimator_implications/v1"
    assert len(envelope["refusals"]) == 1
    refusal = envelope["refusals"][0]
    assert refusal["estimator_id"] == "engine.seasonality.event_study"
    assert refusal["refusal_code"] == "unregistered_search_family"
    assert refusal["detail"]["en"].strip()
    assert refusal["detail"]["zh"].strip()
    event_study_payloads = [p for p in envelope["payloads"]
                             if p["estimator_id"] == "engine.seasonality.event_study"]
    assert event_study_payloads == []
    sc_payloads = [p for p in envelope["payloads"] if p["estimator_id"] == "engine.synthetic_control"]
    assert len(sc_payloads) == 1


# The literal key set of #6830's mastermind.research_implication_card/v1
# (engine/research_implication_card.py, PR #6830) — the drift alarm for the
# two-payload risk named in the frozen spec. Update this set only alongside a
# verified re-read of #6830's diff; do not "fix" a failure by relaxing it.
_CARD_V1_KEYS = frozenset({
    "schema", "card_id", "adapter_version", "quality", "null_reasons",
    "limitations", "diagnostics", "uncertainty", "point_estimate",
    "selected_result_id", "provenance",
    "forecast_authority", "ranking_authority", "gating_authority",
    "sizing_authority", "trading_authority",
})

_SHARED_SPELLING_KEYS = frozenset({
    "quality", "null_reasons", "limitations", "diagnostics", "uncertainty",
    "forecast_authority", "ranking_authority", "gating_authority",
    "sizing_authority", "trading_authority",
})


def test_payload_keys_are_a_profile_of_research_implication_card_v1():
    payload = compose_synthetic_control_implication()
    b_top_keys = set(payload.keys()) | set(payload["authority"].keys())

    # B never uses a top-level/authority key name that A's card would recognize
    # under a *different* meaning: every shared-spelling key must actually be
    # shared, never silently renamed underneath the same word.
    for key in _SHARED_SPELLING_KEYS:
        assert key in _CARD_V1_KEYS, f"{key!r} drifted out of A's card vocabulary"
        assert key in b_top_keys, f"{key!r} missing from B's payload"

    # B's own id/version keys are deliberately renamed (see module docstring);
    # assert the rename, not an accidental collision with A's spelling.
    assert "payload_id" in b_top_keys and "card_id" not in b_top_keys
    assert "composer_version" in b_top_keys and "adapter_version" not in b_top_keys
    assert payload["schema"] != "mastermind.research_implication_card/v1"
