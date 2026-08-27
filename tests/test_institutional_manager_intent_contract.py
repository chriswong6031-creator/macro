from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import inspect
import json
from pathlib import Path

import pytest

import lib.institutional_intelligence as manager_intent
from lib.evidence_foundation import (
    CORRECTION_KINDS,
    COVERAGE_CLASSES,
    REPLAY_MODES,
    SCHEMA_PATH as K1_REFERENCE_SCHEMA_PATH,
    VINTAGE_STATES,
    compute_reference_id,
    load_vocabulary,
    validate_reference,
)
from lib.institutional_intelligence import (
    InstitutionalIntelligenceError,
    compile_recipe,
    compute_recipe_id,
    validate,
    violations,
)


FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "institutional_intelligence"
    / "source_backed_manager_intent_recipe.json"
)
RAW_REF_ID = "efr_9b1450aec5bd550aff068fbd28246c44505702d75577cef76e2349d0706a8915"
THEME_REF_ID = "efr_c5a0444802fa2ed354a7324be6dc5bb17b81cd205d44ee49465be43db5e36011"
AS_OF = "2026-08-08T01:00:00Z"
CUSIP = "037833100"
_CURRENT_RAW_NATIVE_IDENTITY = {
    "accession": "0001398344-26-013841",
    "filer_cik": "0001792167",
    "receipt_id": "i13fraw_c16997a2b2d352a4b7ada643273e00ca482505cf84b1e33e3688d3b0dc6fa8d2",
}
_K1_REPLAY_CUTOFFS = {
    axis: {"state": "unknown", "value": None, "grain": "date"}
    for axis in (
        "belief_or_build", "knowable", "observed", "review_due",
        "source_published", "system_recorded", "world_valid",
    )
}
_K1_ALL_FALSE_AUTHORITY = {
    "can_rank": False, "can_gate": False, "can_size": False,
    "can_originate": False, "can_open_entry": False,
}


def recipe() -> dict:
    value = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert value["recipe_id"] == compute_recipe_id(value)
    return value


def stamp(value: dict) -> dict:
    value["recipe_id"] = compute_recipe_id(value)
    return value


def rejected(value: dict, expected: str) -> None:
    stamp(value)
    with pytest.raises(InstitutionalIntelligenceError, match=expected):
        validate(value)


def event(value: dict, observation_id: str) -> dict:
    return next(row for row in value["observations"] if row["observation_id"] == observation_id)


def replace_reference(value: dict, old_id: str, mutate) -> str:
    reference = next(row for row in value["evidence_refs"] if row["reference_id"] == old_id)
    mutate(reference)
    reference["reference_id"] = compute_reference_id(reference)
    new_id = reference["reference_id"]
    validate_reference(reference)
    for row in value["observations"]:
        if row["evidence_reference_id"] == old_id:
            row["evidence_reference_id"] = new_id
            row["reference_binding"]["reference_id"] = new_id
    for row in value["theme_comparisons"]:
        if row["membership_reference_id"] == old_id:
            row["membership_reference_id"] = new_id
    return new_id


def append_theme_correction(
    value: dict,
    *,
    belief_date: str,
    rights_blocked: bool = False,
) -> str:
    reference = deepcopy(
        next(row for row in value["evidence_refs"] if row["reference_id"] == THEME_REF_ID)
    )
    computed_at = f"{belief_date}T00:15:00Z"
    reference["native_identity"]["belief_time"] = belief_date
    reference["provenance"]["pointer"] = reference["provenance"]["pointer"].replace(
        "belief_time=2026-07-31",
        f"belief_time={belief_date}",
    )
    for clock in reference["clocks"]:
        if clock["field"] == "belief_time":
            clock["value"] = belief_date
        elif clock["field"] == "computed_at":
            clock["value"] = computed_at
    reference["correction"] = {
        "kind": "source_correction",
        "predecessor_reference_ids": [RAW_REF_ID],
        "clock_field": "computed_at",
        "chronology_state": "owner_clock_order_verified",
        "append_only": True,
        "mutates_predecessor": False,
    }
    reference["relations"] = [{
        "type": "corrects",
        "target_reference_id": RAW_REF_ID,
        "deterministic_key": None,
        "automatic_effect": False,
        "independence": {
            axis: {
                "state": "shared",
                "assessment": "declarative_unverified",
                "basis": "synthetic correction lineage shares predecessor source",
            }
            for axis in (
                "source_independence",
                "information_novelty",
                "mechanism_independence",
            )
        },
    }]
    if rights_blocked:
        reference["rights"] = {"state": "rights_blocked", "policy_id": "hostile"}
        reference["missingness"] = {
            "state": "absent",
            "reason": "rights_blocked",
            "zero_substituted": False,
        }
    reference["reference_id"] = compute_reference_id(reference)
    validate_reference(reference)
    value["evidence_refs"].append(reference)

    successor = deepcopy(event(value, "obs_theme_peer"))
    successor["observation_id"] = f"obs_theme_peer_corrected_{belief_date.replace('-', '_')}"
    successor["evidence_reference_id"] = reference["reference_id"]
    successor["reference_binding"] = {
        "reference_id": reference["reference_id"],
        "owner_store": reference["owner_store"],
        "native_identity": deepcopy(reference["native_identity"]),
        "valid_clock": {"field": "valid_from", "value": "2026-07-30"},
        "available_clock": {"field": "computed_at", "value": computed_at},
    }
    successor["correction"] = {
        "kind": "source_correction",
        "predecessor_observation_id": "obs_theme_peer",
        "reason": "synthetic PIT correction",
        "append_only": True,
    }
    value["observations"].append(successor)
    return successor["observation_id"]


def _transition(
    transition_id: str,
    *,
    sequence: int,
    previous: str | None,
    from_state: str,
    to_state: str,
    at: str,
    campaign_id: str = "cmp_meeder_alpha_1",
) -> dict:
    return {
        "transition_id": transition_id,
        "campaign_id": campaign_id,
        "sequence": sequence,
        "previous_transition_id": previous,
        "subject_id": "SEC:US-XNAS-ALPH",
        "manager_complex_id": "mcx_meeder_adviser",
        "complex_epoch_id": "mce_meeder_2026q2",
        "from": from_state,
        "to": to_state,
        "transitioned_at": at,
        "observation_ids": ["obs_manager_positive"],
        "correction": {
            "kind": "none",
            "supersedes_transition_id": None,
            "reason": None,
            "append_only": True,
        },
    }


def _hash_hex(label: str) -> str:
    return sha256(label.encode("utf-8")).hexdigest()


def _owner_row_raw_ref(
    *,
    accession: str,
    report_period: str,
    accepted_at: str,
    retained_at: str,
    label: str,
    filer_cik: str = "0001792167",
) -> dict:
    """Build a fresh, real-shaped K1 ``institutional_13f.raw_receipt`` ref."""
    receipt_id = f"i13fraw_{_hash_hex(label)}"
    reference = {
        "schema": "evidence_foundation.reference.v1",
        "version": "1.0.0",
        "object_class": "world_observation",
        "owner_store": "institutional_13f.raw_receipt",
        "native_identity": {
            "filer_cik": filer_cik,
            "accession": accession,
            "receipt_id": receipt_id,
        },
        "native_schema": "institutional_13f.raw_evidence_receipt/v1",
        "native_digest": {"state": "known", "sha256": _hash_hex(f"{label}:digest")},
        "coverage_class": "source_release_snapshot_only",
        "freshness": {"state": "native_clock_bound", "clock_field": "clocks.retained_at", "policy_id": None},
        "rights": {"state": "permitted", "policy_id": None},
        "authority_class": "fact",
        "subject": {"key_type": "institutional_manager_cik", "key": filer_cik},
        "secondary_subjects": [{"key_type": "accession", "key": accession}],
        "clocks": [
            {"class": "world_valid", "field": "clocks.report_period", "grain": "date", "value": report_period, "value_state": "known"},
            {"class": "source_published", "field": "clocks.accepted_at", "grain": "datetime", "value": accepted_at, "value_state": "known"},
            {"class": "system_recorded", "field": "clocks.retained_at", "grain": "datetime", "value": retained_at, "value_state": "known"},
        ],
        "provenance": {
            "pointer_only": True,
            "body_embedded": False,
            "owner_reader": "engine.institutional_census.models.RawEvidenceReceipt.from_json_bytes",
            "owner_reader_kind": "parser",
            "pointer": f"institutional-13f/raw/{filer_cik}/{accession}/{receipt_id}.json",
        },
        "relations": [],
        "missingness": {"state": "present", "reason": None, "zero_substituted": False},
        "correction": {
            "kind": "none", "predecessor_reference_ids": [], "clock_field": None,
            "chronology_state": "not_applicable", "append_only": True, "mutates_predecessor": False,
        },
        "replay": {
            "mode": "live", "cutoffs": deepcopy(_K1_REPLAY_CUTOFFS),
            "code_revision": None, "input_digest": None, "vintage_state": "owner_native",
        },
        "authority": deepcopy(_K1_ALL_FALSE_AUTHORITY),
    }
    reference["reference_id"] = compute_reference_id(reference)
    validate_reference(reference)
    return reference


def _owner_row_catalog_ref(
    *,
    report_period: str,
    source_cutoff_at: str,
    published_at: str,
    label: str,
) -> dict:
    """Build a fresh, real-shaped K1 ``institutional_13f.catalog_generation`` ref."""
    generation_id = f"i13fgen_{_hash_hex(label)}"
    reference = {
        "schema": "evidence_foundation.reference.v1",
        "version": "1.0.0",
        "object_class": "derived_view",
        "owner_store": "institutional_13f.catalog_generation",
        "native_identity": {"generation_id": generation_id, "report_period": report_period},
        "native_schema": "institutional_13f.catalog_generation_manifest/v1",
        "native_digest": {"state": "known", "sha256": _hash_hex(f"{label}:digest")},
        "coverage_class": "immutable_generation",
        "freshness": {"state": "native_clock_bound", "clock_field": "clocks.published_at", "policy_id": None},
        "rights": {"state": "permitted", "policy_id": None},
        "authority_class": "deterministic",
        "subject": {"key_type": "institutional_catalog_generation_id", "key": generation_id},
        "secondary_subjects": [],
        "clocks": [
            {"class": "world_valid", "field": "clocks.report_period", "grain": "date", "value": report_period, "value_state": "known"},
            {"class": "knowable", "field": "clocks.source_cutoff_at", "grain": "datetime", "value": source_cutoff_at, "value_state": "known"},
            {"class": "belief_or_build", "field": "clocks.published_at", "grain": "datetime", "value": published_at, "value_state": "known"},
        ],
        "provenance": {
            "pointer_only": True,
            "body_embedded": False,
            "owner_reader": "engine.institutional_census.catalog.load_catalog_generation",
            "owner_reader_kind": "direct",
            "pointer": f"institutional-13f/catalog/{report_period}/generations/{generation_id}/manifest.json",
        },
        "relations": [],
        "missingness": {"state": "present", "reason": None, "zero_substituted": False},
        "correction": {
            "kind": "none", "predecessor_reference_ids": [], "clock_field": None,
            "chronology_state": "not_applicable", "append_only": True, "mutates_predecessor": False,
        },
        "replay": {
            "mode": "live", "cutoffs": deepcopy(_K1_REPLAY_CUTOFFS),
            "code_revision": None, "input_digest": None, "vintage_state": "owner_native",
        },
        "authority": deepcopy(_K1_ALL_FALSE_AUTHORITY),
    }
    reference["reference_id"] = compute_reference_id(reference)
    validate_reference(reference)
    return reference


def _reference_binding_from(
    reference: dict, *, valid_field: str, valid_value: str, available_field: str, available_value: str,
) -> dict:
    return {
        "reference_id": reference["reference_id"],
        "owner_store": reference["owner_store"],
        "native_identity": deepcopy(reference["native_identity"]),
        "valid_clock": {"field": valid_field, "value": valid_value},
        "available_clock": {"field": available_field, "value": available_value},
    }


def _current_raw_ref_view() -> dict:
    """The existing fixture raw ref, described only as needed to build bindings."""
    return {"reference_id": RAW_REF_ID, "owner_store": "institutional_13f.raw_receipt", "native_identity": deepcopy(_CURRENT_RAW_NATIVE_IDENTITY)}


def owner_row_case(
    *,
    cusip: str = CUSIP,
    security_cusip: str | None = None,
    previous_report_period: str = "2025-12-31",
    previous_accession: str = "0001398344-25-098765",
    previous_accepted_at: str = "2025-12-15T20:00:00Z",
    previous_retained_at: str = "2025-12-15T20:01:00Z",
    previous_source_cutoff_at: str = "2025-12-15T20:00:00Z",
    previous_published_at: str = "2025-12-15T20:05:00Z",
    current_report_period: str = "2026-03-31",
    current_catalog_report_period: str | None = None,
    previous_row_cusip: str | None = None,
    current_row_cusip: str | None = None,
    current_row_accession: str | None = None,
    subject_id: str | None = None,
    measure: dict | None = None,
    swap_previous_catalog_for_raw: bool = False,
    unlisted_previous_raw_reference: bool = False,
    primary_reference_is_previous: bool = False,
    observation_id: str = "obs_owner_row_positive",
) -> tuple[dict, str]:
    """A deep-copied fixture recipe extended with one ``source_backed_owner_row``
    observation.  Defaults produce a fully lawful two-period owner-read; keyword
    overrides isolate exactly one K2-C falsifier axis at a time."""
    value = recipe()

    prev_raw = _owner_row_raw_ref(
        accession=previous_accession,
        report_period=previous_report_period,
        accepted_at=previous_accepted_at,
        retained_at=previous_retained_at,
        label=f"owner-row-prev-raw:{observation_id}:{previous_report_period}:{previous_retained_at}",
    )
    resolved_current_catalog_period = current_catalog_report_period or current_report_period
    prev_catalog = _owner_row_catalog_ref(
        report_period=previous_report_period,
        source_cutoff_at=previous_source_cutoff_at,
        published_at=previous_published_at,
        label=f"owner-row-prev-catalog:{observation_id}:{previous_report_period}",
    )
    current_catalog = _owner_row_catalog_ref(
        report_period=resolved_current_catalog_period,
        source_cutoff_at="2026-05-15T20:00:00Z",
        published_at="2026-05-15T20:05:00Z",
        label=f"owner-row-current-catalog:{observation_id}:{resolved_current_catalog_period}",
    )
    value["evidence_refs"].extend([prev_raw, prev_catalog, current_catalog])

    previous_binding = {
        "catalog_binding": _reference_binding_from(
            prev_catalog, valid_field="clocks.report_period", valid_value=previous_report_period,
            available_field="clocks.published_at", available_value=previous_published_at,
        ),
        "raw_receipt_binding": _reference_binding_from(
            prev_raw, valid_field="clocks.report_period", valid_value=previous_report_period,
            available_field="clocks.retained_at", available_value=previous_retained_at,
        ),
        "row": {
            "accession": previous_accession,
            "infotable_sk": 7,
            "row_hash": _hash_hex(f"owner-row-prev-row:{observation_id}"),
            "cusip": previous_row_cusip if previous_row_cusip is not None else cusip,
        },
    }
    if swap_previous_catalog_for_raw:
        previous_binding["catalog_binding"] = deepcopy(previous_binding["raw_receipt_binding"])
    if unlisted_previous_raw_reference:
        previous_binding["raw_receipt_binding"]["reference_id"] = "efr_" + "0" * 64

    current_binding = {
        "catalog_binding": _reference_binding_from(
            current_catalog, valid_field="clocks.report_period", valid_value=resolved_current_catalog_period,
            available_field="clocks.published_at", available_value="2026-05-15T20:05:00Z",
        ),
        "raw_receipt_binding": _reference_binding_from(
            _current_raw_ref_view(), valid_field="clocks.report_period", valid_value="2026-03-31",
            available_field="clocks.retained_at", available_value="2026-05-15T20:01:00Z",
        ),
        "row": {
            "accession": current_row_accession if current_row_accession is not None else _CURRENT_RAW_NATIVE_IDENTITY["accession"],
            "infotable_sk": 12,
            "row_hash": _hash_hex(f"owner-row-current-row:{observation_id}"),
            "cusip": current_row_cusip if current_row_cusip is not None else cusip,
        },
    }

    primary_binding = deepcopy(
        previous_binding["raw_receipt_binding"] if primary_reference_is_previous else current_binding["raw_receipt_binding"]
    )

    observation = {
        "observation_id": observation_id,
        "evidence_basis": "source_backed_owner_row",
        "evidence_reference_id": primary_binding["reference_id"],
        "reference_binding": primary_binding,
        "vehicle_epoch_id": "vie_meeder_2026q2",
        "subject_id": subject_id if subject_id is not None else f"cusip:{cusip}",
        "theme_id": "theme_ai_infrastructure",
        "theme_epoch_id": "theme_epoch_2026q2",
        "plane": "manager_research_intent",
        "measure": measure if measure is not None else {"kind": "reported_share_change", "q_prev": 100, "q_now": 140},
        "denominator": {
            "kind": "public_reported_sleeve", "state": "partial",
            "total_positions": 2, "included_positions": 2, "excluded_positions": 0, "missing_positions": 0,
        },
        "correction": {"kind": "none", "predecessor_observation_id": None, "reason": None, "append_only": True},
        "owner_row_binding": {
            "security": {
                "key_type": "cusip",
                "cusip": security_cusip if security_cusip is not None else cusip,
                "dataos_security_id": None,
                "dataos_resolution": "unresolved_no_authoritative_cusip_plane",
            },
            "previous": previous_binding,
            "current": current_binding,
        },
    }
    value["observations"].append(observation)
    stamp(value)
    return value, observation_id


def test_full_k1_refs_are_valid_and_actual_raw_receipt_contract_is_exact() -> None:
    value = recipe()
    refs = {row["reference_id"]: validate_reference(row) for row in value["evidence_refs"]}
    assert set(refs) == {
        RAW_REF_ID,
        "efr_d9ddc49e1b0d02bc6980fbdc61df12a242f69f3a9b098fb34229f7dd64e58f34",
        THEME_REF_ID,
    }
    raw = refs[RAW_REF_ID]
    assert raw["owner_store"] == "institutional_13f.raw_receipt"
    assert raw["native_schema"] == "institutional_13f.raw_evidence_receipt/v1"
    assert raw["native_identity"] == {
        "accession": "0001398344-26-013841",
        "filer_cik": "0001792167",
        "receipt_id": "i13fraw_c16997a2b2d352a4b7ada643273e00ca482505cf84b1e33e3688d3b0dc6fa8d2",
    }
    assert raw["native_digest"] == {
        "state": "known",
        "sha256": "cc09d4f341c5d2fbb03ec994178f9ed38dddd4e4ee8e1bc333be9fb605917311",
    }
    assert raw["provenance"] == {
        "pointer_only": True,
        "body_embedded": False,
        "owner_reader": "engine.institutional_census.models.RawEvidenceReceipt.from_json_bytes",
        "owner_reader_kind": "parser",
        "pointer": "institutional-13f/raw/0001792167/0001398344-26-013841/i13fraw_c16997a2b2d352a4b7ada643273e00ca482505cf84b1e33e3688d3b0dc6fa8d2.json",
    }
    assert raw["rights"]["state"] == "permitted"
    assert raw["coverage_class"] == "source_release_snapshot_only"
    assert [row["field"] for row in raw["clocks"]] == [
        "clocks.report_period", "clocks.accepted_at", "clocks.retained_at"
    ]


def test_fixture_is_closed_deterministic_pointer_only_and_all_authority_false() -> None:
    value = recipe()
    assert validate(value) == value
    first = compile_recipe(value, as_of=AS_OF)
    second = compile_recipe(deepcopy(value), as_of=AS_OF)
    assert first == second
    assert first["owner_payloads_copied"] is False
    assert first["persistence"] == "none"
    assert first["master_score"] is None
    assert first["authority"] == {
        "can_rank": False,
        "can_gate": False,
        "can_size": False,
        "can_originate": False,
        "can_open_entry": False,
    }


def test_four_planes_have_closed_positive_and_adverse_receipts() -> None:
    receipt = compile_recipe(recipe(), as_of=AS_OF)
    by_id = {row["observation_id"]: row for row in receipt["events"]}
    assert {row["plane"] for row in receipt["events"]} == {
        "manager_research_intent",
        "fund_flow_pressure",
        "theme_capital_rotation",
        "institutionalization_saturation",
    }
    assert by_id["obs_manager_positive"]["state"] == "MANAGER_RESEARCH_INTENT_ELIGIBLE_CONTEXT"
    assert by_id["obs_source_pointer_only"]["state"] == "SOURCE_POINTER_ONLY_NO_SECURITY_BINDING"
    assert by_id["obs_flow_true_s"]["state"] == "MECHANICAL_FLOW_RESIDUAL"
    assert by_id["obs_flow_proxy"]["state"] == "MECHANICAL_FLOW_PROXY"
    assert by_id["obs_saturation_positive"]["state"] == "SATURATION_OBSERVED"
    assert by_id["obs_saturation_adverse"]["state"] == "SATURATION_UNAVAILABLE"
    assert by_id["obs_saturation_positive"]["measure"] == {
        "kind": "complex_presence",
        "state": "observed",
        "present_complex_epoch_ids": ["mce_meeder_2026q2"],
        "present_complex_count": 1,
    }
    saturation = receipt["institutionalization_saturation"]
    assert saturation["present_complex_epoch_ids"] == ["mce_meeder_2026q2"]
    assert saturation["present_complex_count"] == 1
    assert saturation["eligible_complex_count"] == 2
    assert saturation["saturation_ratio"] == 0.5
    assert saturation["denominator"] == {
        "kind": "eligible_research_complexes",
        "eligible_complex_epoch_ids": ["mce_meeder_2026q2", "mce_peer_2026q2"],
        "excluded_complex_epochs": [
            {"complex_epoch_id": "mce_passive_2026q2", "reason": "passive"},
            {"complex_epoch_id": "mce_unresolved_2026q2", "reason": "unresolved"},
        ],
    }


def test_saturation_has_no_detached_count_or_caller_denominator_override() -> None:
    value = recipe()
    event(value, "obs_saturation_positive")["measure"]["position_count"] = 999
    rejected(value, "json_schema:observations")

    value = recipe()
    event(value, "obs_saturation_positive")["denominator"][
        "eligible_complex_epoch_ids"
    ] = ["mce_does_not_exist"]
    rejected(value, "saturation_denominator_not_derived")

    value = recipe()
    event(value, "obs_saturation_positive")["measure"][
        "present_complex_epoch_ids"
    ].append("mce_peer_2026q2")
    rejected(value, "saturation_present_complex_unbacked")


@pytest.mark.parametrize(
    "interval_update",
    [
        {
            "effective_from": "2030-01-01T00:00:00Z",
            "valid_from": "2030-01-01T00:00:00Z",
            "knowable_from": "2030-01-02T00:00:00Z",
        },
        {
            "effective_to": "2026-05-01T00:00:00Z",
            "valid_to": "2026-05-01T00:00:00Z",
            "knowable_to": "2026-05-01T00:00:00Z",
        },
    ],
)
def test_saturation_denominator_cannot_keep_future_or_expired_epoch_eligible(
    interval_update: dict,
) -> None:
    value = recipe()
    value["manager_complex_epochs"][1]["interval"].update(interval_update)
    value["theme_comparisons"] = []
    value["campaign_transitions"] = []
    value["observations"] = [
        row for row in value["observations"]
        if row["plane"] == "institutionalization_saturation"
    ]
    rejected(value, "saturation_denominator_not_derived")


def test_superseded_saturation_observation_cannot_contribute_present_count() -> None:
    value = recipe()
    successor_id = append_theme_correction(value, belief_date="2026-09-01")
    successor = event(value, successor_id)
    predecessor = event(value, "obs_saturation_positive")
    successor.update({
        "vehicle_epoch_id": predecessor["vehicle_epoch_id"],
        "subject_id": predecessor["subject_id"],
        "theme_id": predecessor["theme_id"],
        "theme_epoch_id": predecessor["theme_epoch_id"],
        "plane": predecessor["plane"],
        "measure": {"kind": "unavailable", "reason": "source_missing"},
        "denominator": deepcopy(predecessor["denominator"]),
    })
    successor["correction"]["predecessor_observation_id"] = predecessor["observation_id"]
    stamp(value)

    earlier = compile_recipe(value, as_of=AS_OF)
    assert earlier["institutionalization_saturation"]["present_complex_count"] == 1

    later = compile_recipe(value, as_of="2026-09-02T00:30:00Z")
    later_events = {row["observation_id"]: row for row in later["events"]}
    assert later_events[predecessor["observation_id"]]["state"] == "SUPERSEDED"
    assert later_events[successor_id]["state"] == "SATURATION_UNAVAILABLE"
    assert later["institutionalization_saturation"]["present_complex_epoch_ids"] == []
    assert later["institutionalization_saturation"]["present_complex_count"] == 0
    assert later["institutionalization_saturation"]["saturation_ratio"] == 0.0


def test_event_pointer_tamper_and_full_ref_tamper_fail_closed() -> None:
    value = recipe()
    event(value, "obs_manager_positive")["evidence_reference_id"] = "efr_" + "0" * 64
    rejected(value, "event_reference_id_conflict|event_reference_unresolved")

    value = recipe()
    raw = next(row for row in value["evidence_refs"] if row["reference_id"] == RAW_REF_ID)
    raw["native_identity"]["filer_cik"] = "0000000001"
    rejected(value, "k1_evidence_ref_invalid")

    value = recipe()
    event(value, "obs_manager_positive")["reference_binding"]["native_identity"]["filer_cik"] = "0000000001"
    rejected(value, "event_native_identity_binding_conflict")


def test_source_pointer_cannot_claim_security_binding_without_owner_selection() -> None:
    value = recipe()
    event(value, "obs_source_pointer_only")["subject_id"] = "SEC:US-XNAS-FAKE"
    rejected(value, "source_pointer_cannot_bind_security_subject")


def test_true_s_residual_is_compiler_derived_and_caller_result_is_forbidden() -> None:
    value = recipe()
    row = event(value, "obs_flow_true_s")
    row["measure"]["residual_shares"] = 999
    rejected(value, "json_schema:observations")
    receipt = compile_recipe(recipe(), as_of=AS_OF)
    compiled = next(row for row in receipt["events"] if row["observation_id"] == "obs_flow_true_s")
    assert compiled["measure"] == {
        "kind": "etf_true_share_residual",
        "state": "computed_true_shares_outstanding",
        "formula": "Q_now - Q_prev * (S_now / S_prev)",
        "residual_shares": 30.0,
    }


def test_13f_never_borrows_etf_s_and_proxy_never_becomes_intent() -> None:
    value = recipe()
    event(value, "obs_manager_positive")["measure"] = {
        "kind": "etf_true_share_residual",
        "q_prev": 100,
        "q_now": 150,
        "s_prev": 1000,
        "s_now": 1200,
    }
    rejected(value, "plane_measure_denominator_shape_conflict")
    receipt = compile_recipe(recipe(), as_of=AS_OF)
    proxy = next(row for row in receipt["events"] if row["observation_id"] == "obs_flow_proxy")
    assert proxy["measure"]["residual_shares"] is None
    assert proxy["state"] == "MECHANICAL_FLOW_PROXY"


def test_within_theme_preference_is_derived_from_distinct_pit_members() -> None:
    receipt = compile_recipe(recipe(), as_of=AS_OF)
    positive, adverse = receipt["theme_comparisons"]
    assert positive["state"] == "WITHIN_THEME_PREFERENCE_COMPUTED"
    assert positive["target_reported_share_delta"] == 40.0
    assert positive["eligible_peer_mean_reported_share_delta"] == 10.0
    assert positive["preference_spread"] == 30.0
    assert adverse["state"] == "INSUFFICIENT_ELIGIBLE_PEERS"
    assert adverse["preference_spread"] is None


def test_future_theme_comparison_never_compiles_or_copies_future_eligibility() -> None:
    receipt = compile_recipe(recipe(), as_of="2026-08-02T00:00:00Z")
    positive = next(
        row for row in receipt["theme_comparisons"]
        if row["comparison_id"] == "thc_positive"
    )
    assert positive["state"] == "NOT_YET_KNOWABLE"
    assert positive["compiled_as_of"] == "2026-08-02T00:00:00Z"
    assert positive["as_of"] == "2026-08-08T00:00:00Z"
    assert positive["target_reported_share_delta"] is None
    assert positive["eligible_peer_mean_reported_share_delta"] is None
    assert positive["preference_spread"] is None
    assert positive["eligible_peer_observation_ids"] == []
    assert positive["denominator_receipt"]["eligible_observation_ids"] == []
    assert {
        row["reason"] for row in positive["denominator_receipt"]["excluded_members"]
    } == {"comparison_not_yet_knowable"}


def test_same_target_peer_or_one_name_denominator_is_rejected() -> None:
    value = recipe()
    comparison = value["theme_comparisons"][0]
    comparison["peer_observation_ids"] = [comparison["target_observation_id"]]
    comparison["denominator_receipt"]["member_observation_ids"] = [comparison["target_observation_id"]]
    comparison["denominator_receipt"]["eligible_observation_ids"] = [comparison["target_observation_id"]]
    rejected(value, "theme_target_peer_overlap|theme_denominator_membership_invalid")


def test_late_peer_and_passive_peer_as_eligible_are_rejected() -> None:
    value = recipe()
    peer = event(value, "obs_theme_peer")
    peer["reference_binding"]["available_clock"]["value"] = "2026-09-01T00:00:00Z"
    rejected(value, "event_available_clock_binding_conflict|theme_peer_not_knowable_at_cutoff")

    value = recipe()
    comparison = value["theme_comparisons"][1]
    comparison["denominator_receipt"]["eligible_observation_ids"].append("obs_theme_peer_mechanical")
    comparison["denominator_receipt"]["excluded_members"] = []
    rejected(value, "theme_ineligible_member_marked_eligible")


def test_membership_pointer_clock_tamper_is_rejected() -> None:
    value = recipe()
    value["theme_comparisons"][0]["membership_clock_binding"]["value"] = "2026-08-09T00:00:00Z"
    rejected(value, "theme_membership_clock_unbound|theme_membership_lookahead")


def test_date_grain_membership_clock_uses_conservative_following_midnight() -> None:
    value = recipe()
    for comparison in value["theme_comparisons"]:
        comparison["membership_clock_binding"] = {
            "field": "belief_time",
            "value": "2026-07-31",
        }
    stamp(value)
    receipt = compile_recipe(value, as_of=AS_OF)
    assert receipt["theme_comparisons"][0]["state"] == "WITHIN_THEME_PREFERENCE_COMPUTED"


def test_campaign_refuses_rights_blocked_and_preknowledge_observations() -> None:
    value = recipe()

    def block(reference: dict) -> None:
        reference["rights"] = {"state": "rights_blocked", "policy_id": "test_block"}
        reference["missingness"] = {
            "state": "absent",
            "reason": "rights_blocked",
            "zero_substituted": False,
        }

    replace_reference(value, RAW_REF_ID, block)
    rejected(value, "campaign_observation_ineligible")

    value = recipe()
    value["campaign_transitions"][0]["transitioned_at"] = "2026-05-15T20:00:30Z"
    rejected(value, "campaign_observation_ineligible|campaign_observation_not_yet_knowable")


def test_campaign_history_is_emitted_and_requires_append_only_linear_chain() -> None:
    value = recipe()
    value["campaign_transitions"].extend([
        _transition("ctr_campaign_2", sequence=2, previous="ctr_campaign_1", from_state="INITIATED", to_state="ACCUMULATING", at="2026-05-17T20:01:00Z"),
        _transition("ctr_campaign_3", sequence=3, previous="ctr_campaign_2", from_state="ACCUMULATING", to_state="PAUSED", at="2026-05-18T20:01:00Z"),
        _transition("ctr_campaign_4", sequence=4, previous="ctr_campaign_3", from_state="PAUSED", to_state="CLOSED", at="2026-05-19T20:01:00Z"),
        _transition("ctr_campaign_5", sequence=1, previous=None, from_state="IDLE", to_state="INITIATED", at="2026-05-20T20:01:00Z", campaign_id="cmp_meeder_alpha_2"),
    ])
    stamp(value)
    receipt = compile_recipe(value, as_of=AS_OF)
    assert [row["transition_id"] for row in receipt["campaign_history"]] == [
        "ctr_campaign_1", "ctr_campaign_2", "ctr_campaign_3", "ctr_campaign_4", "ctr_campaign_5"
    ]
    assert receipt["current_campaign_states"] == {
        "cmp_meeder_alpha_1": "CLOSED",
        "cmp_meeder_alpha_2": "INITIATED",
    }

    value = recipe()
    value["campaign_transitions"].append(
        _transition("ctr_overlap", sequence=1, previous=None, from_state="IDLE", to_state="INITIATED", at="2026-05-17T20:01:00Z", campaign_id="cmp_overlap")
    )
    rejected(value, "new_campaign_before_prior_close")


def test_campaign_skips_reversals_unresolved_and_duplicate_edges_fail() -> None:
    value = recipe()
    value["campaign_transitions"].append(
        _transition("ctr_skip", sequence=2, previous="ctr_campaign_1", from_state="INITIATED", to_state="PAUSED", at="2026-05-17T20:01:00Z")
    )
    rejected(value, "invalid_campaign_history")

    value = recipe()
    value["campaign_transitions"][0]["observation_ids"] = ["obs_flow_true_s"]
    rejected(value, "campaign_observation_ineligible")


def test_event_missingness_rights_coverage_and_caller_output_cannot_be_invented() -> None:
    for field, value_to_add in (
        ("missingness", {"state": "present", "reason": None, "zero_substituted": False}),
        ("rights", {"state": "permitted", "policy_id": None}),
        ("coverage_class", "record_history_complete"),
        ("compiled_result", 999),
    ):
        value = recipe()
        event(value, "obs_manager_positive")[field] = value_to_add
        rejected(value, "json_schema:observations")


@pytest.mark.parametrize(
    ("mutation", "expected_state"),
    [
        (
            lambda reference: reference.update(
                freshness={"state": "unknown", "clock_field": None, "policy_id": None}
            ),
            "FRESHNESS_UNKNOWN",
        ),
        (
            lambda reference: reference.update(
                missingness={
                    "state": "absent",
                    "reason": "stale",
                    "zero_substituted": False,
                }
            ),
            "STALE",
        ),
    ],
)
def test_k1_freshness_and_missingness_fail_closed_without_positive_outputs(
    mutation,
    expected_state: str,
) -> None:
    value = recipe()
    replace_reference(value, RAW_REF_ID, mutation)
    value["campaign_transitions"] = []
    value["theme_comparisons"] = []
    value["observations"] = [
        row for row in value["observations"]
        if row["plane"] not in {
            "institutionalization_saturation",
            "theme_capital_rotation",
        }
    ]
    stamp(value)
    receipt = compile_recipe(value, as_of="2026-08-10T00:00:00Z")
    raw_events = [
        row for row in receipt["events"]
        if row["evidence_reference_id"] != THEME_REF_ID
    ]
    assert raw_events
    assert {row["reference_state"] for row in raw_events} == {expected_state}
    assert all(row["measure"]["state"] == "not_compiled" for row in raw_events)
    assert receipt["complex_count_receipt"]["distinct_eligible_research_complex_count"] == 0
    assert receipt["complex_count_receipt"]["mechanical_vehicle_epoch_count"] == 0


def test_k1_owner_incoherent_coverage_is_rejected_before_compilation() -> None:
    value = recipe()
    raw = next(row for row in value["evidence_refs"] if row["reference_id"] == RAW_REF_ID)
    raw["coverage_class"] = "current_only"
    raw["reference_id"] = compute_reference_id(raw)
    for row in value["observations"]:
        if row["evidence_reference_id"] == RAW_REF_ID:
            row["evidence_reference_id"] = raw["reference_id"]
            row["reference_binding"]["reference_id"] = raw["reference_id"]
    rejected(value, "k1_evidence_ref_invalid")


def test_epoch_intervals_lineage_decision_modes_and_raw_actor_history_are_closed() -> None:
    value = recipe()
    value["manager_complex_epochs"][0]["interval"]["valid_to"] = "2026-03-01T00:00:00Z"
    rejected(value, "epoch_interval_reversed")

    value = recipe()
    value["manager_complex_epochs"][0]["lineage"].update(
        predecessor_epoch_id="mce_old", reason="silent rename"
    )
    rejected(value, "epoch_original_has_predecessor")

    value = recipe()
    value["vehicle_epochs"][2]["decision_mode"] = "discretionary"
    rejected(value, "vehicle_class_decision_mode_conflict")

    assert value["manager_complex_epochs"][0]["actor_identity"]["raw_actor_string"]
    assert value["manager_complex_epochs"][0]["actor_identity"]["original_ontology_version"]

    value = recipe()
    interval = value["manager_complex_epochs"][0]["interval"]
    interval["effective_to"] = interval["effective_from"]
    rejected(value, "epoch_interval_reversed")


def test_epoch_and_actor_lineage_bind_to_the_correct_registry_and_entity() -> None:
    value = recipe()
    actor = value["manager_complex_epochs"][0]["actor_identity"]
    actor["remap_lineage"] = {
        "state": "remapped",
        "predecessor_epoch_id": "mce_does_not_exist",
        "reason": "hostile dangling remap",
        "append_only": True,
    }
    rejected(value, "actor_remap_predecessor_invalid|actor_remap_epoch_lineage_conflict")

    value = recipe()
    value["filer_epochs"][0]["lineage"] = {
        "state": "corrected",
        "predecessor_epoch_id": "fie_does_not_exist",
        "reason": "hostile dangling filer correction",
        "append_only": True,
    }
    rejected(value, "filer_lineage_predecessor_invalid")

    value = recipe()
    value["vehicle_epochs"][0]["lineage"] = {
        "state": "corrected",
        "predecessor_epoch_id": "vie_does_not_exist",
        "reason": "hostile dangling vehicle correction",
        "append_only": True,
    }
    rejected(value, "vehicle_lineage_predecessor_invalid")

    value = recipe()
    current = value["manager_complex_epochs"][0]
    current["lineage"] = {
        "state": "corrected",
        "predecessor_epoch_id": current["complex_epoch_id"],
        "reason": "hostile self correction",
        "append_only": True,
    }
    current["actor_identity"]["remap_lineage"] = deepcopy(current["lineage"])
    rejected(value, "manager_complex_lineage_predecessor_invalid|actor_remap_predecessor_invalid")

    value = recipe()
    first, second = value["manager_complex_epochs"][:2]
    for row, predecessor in ((first, second), (second, first)):
        row["lineage"] = {
            "state": "corrected",
            "predecessor_epoch_id": predecessor["complex_epoch_id"],
            "reason": "hostile cycle",
            "append_only": True,
        }
        row["actor_identity"]["remap_lineage"] = deepcopy(row["lineage"])
    rejected(value, "manager_complex_lineage_cycle|actor_remap_cycle")


def test_valid_manager_and_actor_remap_is_linear_append_only_and_nonoverlapping() -> None:
    value = recipe()
    current = value["manager_complex_epochs"][0]
    predecessor = deepcopy(current)
    predecessor["complex_epoch_id"] = "mce_meeder_2026q1"
    predecessor["interval"] = {
        "effective_from": "2025-01-01T00:00:00Z",
        "effective_to": current["interval"]["effective_from"],
        "valid_from": "2025-01-01T00:00:00Z",
        "valid_to": current["interval"]["valid_from"],
        "knowable_from": "2025-01-01T00:00:00Z",
        "knowable_to": current["interval"]["knowable_from"],
    }
    predecessor["status"] = "inactive"
    predecessor["actor_identity"]["remap_lineage"] = {
        "state": "original",
        "predecessor_epoch_id": None,
        "reason": None,
        "append_only": True,
    }
    predecessor["lineage"] = deepcopy(predecessor["actor_identity"]["remap_lineage"])
    current["actor_identity"]["remap_lineage"] = {
        "state": "remapped",
        "predecessor_epoch_id": predecessor["complex_epoch_id"],
        "reason": "canonical entity remapped without mutating history",
        "append_only": True,
    }
    current["lineage"] = deepcopy(current["actor_identity"]["remap_lineage"])
    value["manager_complex_epochs"].append(predecessor)
    for saturation in [
        row for row in value["observations"]
        if row["plane"] == "institutionalization_saturation"
    ]:
        saturation["denominator"]["excluded_complex_epochs"].insert(0, {
            "complex_epoch_id": predecessor["complex_epoch_id"],
            "reason": "inactive",
        })
    stamp(value)
    assert validate(value)


def test_future_epochs_refuse_events_counts_campaigns_and_reliability() -> None:
    value = recipe()
    for row in (
        value["manager_complex_epochs"][0],
        value["filer_epochs"][0],
        value["vehicle_epochs"][0],
    ):
        row["interval"].update(
            effective_from="2030-01-01T00:00:00Z",
            valid_from="2030-01-01T00:00:00Z",
            knowable_from="2030-01-02T00:00:00Z",
        )
    stamp(value)
    errors = violations(value)
    assert "event_epoch_not_applicable" in errors
    assert "campaign_observation_ineligible" in errors
    assert "reliability_epoch_not_applicable" in errors
    with pytest.raises(InstitutionalIntelligenceError):
        compile_recipe(value, as_of="2026-08-10T00:00:00Z")


def test_expiry_after_event_preserves_historical_campaign_and_reliability() -> None:
    value = recipe()
    for row in (
        value["manager_complex_epochs"][0],
        value["filer_epochs"][0],
        value["vehicle_epochs"][0],
    ):
        row["interval"].update(
            effective_to="2026-08-05T00:00:00Z",
            valid_to="2026-08-05T00:00:00Z",
            knowable_to="2026-08-05T00:00:00Z",
        )
    value["theme_comparisons"] = []
    value["observations"] = [
        row for row in value["observations"]
        if row["plane"] != "theme_capital_rotation"
    ]
    stamp(value)
    receipt = compile_recipe(value, as_of=AS_OF)
    events = {row["observation_id"]: row for row in receipt["events"]}
    assert events["obs_manager_positive"]["state"] == "VEHICLE_EPOCH_EFFECTIVE_EXPIRED"
    assert events["obs_manager_positive"]["measure"]["state"] == "not_compiled"
    assert receipt["complex_count_receipt"]["distinct_eligible_research_complex_count"] == 0
    assert receipt["campaign_history"][0]["record_state"] == "CURRENT_APPEND_ONLY_RECORD"
    assert receipt["campaign_history"][0]["transition_epoch_state"] == "APPLICABLE"
    assert receipt["current_campaign_states"] == {"cmp_meeder_alpha_1": "INITIATED"}
    assert receipt["reliability"][0]["epoch_state"] == "APPLICABLE"
    assert receipt["reliability"][0]["posterior"] == 0.5


def test_campaign_and_reliability_cutoffs_must_be_inside_epoch_intervals() -> None:
    value = recipe()
    for row in (value["manager_complex_epochs"][0], value["vehicle_epochs"][0]):
        row["interval"]["valid_to"] = "2026-05-16T00:00:00Z"
    stamp(value)
    assert "campaign_observation_ineligible" in violations(value)

    value = recipe()
    value["manager_complex_epochs"][0]["interval"]["knowable_from"] = "2026-07-15T00:00:00Z"
    stamp(value)
    assert "reliability_epoch_not_applicable" in violations(value)


@pytest.mark.parametrize(
    "role",
    [
        "institution_or_manager_complex",
        "fund_company",
        "fund_vehicle",
        "manager_or_person",
        "broker_or_research_house",
        "analyst",
        "named_market_actor_or_broker_seat",
        "holder_controller_or_executive",
    ],
)
def test_canonical_eight_china_actor_roles_are_additive_extensions(role: str) -> None:
    value = recipe()
    actor = value["manager_complex_epochs"][0]["actor_identity"]
    actor["role"] = role
    actor["ontology_source"] = "CHINA_ALPHA_INTELLIGENCE_MASTERPLAN"
    stamp(value)
    assert validate(value)


def test_unresolved_complex_never_inflates_independent_research_count() -> None:
    receipt = compile_recipe(recipe(), as_of=AS_OF)
    assert receipt["complex_count_receipt"]["unresolved_complex_epoch_count"] == 1
    assert receipt["complex_count_receipt"]["distinct_eligible_research_complex_count"] == 1

    value = recipe()
    value["observations"] = [event(value, "obs_source_pointer_only")]
    value["theme_comparisons"] = []
    value["campaign_transitions"] = []
    value["reliability"] = [value["reliability"][1]]
    meeder = value["manager_complex_epochs"][0]
    meeder.update(status="unresolved", resolution_state="unresolved", decision_mode="unknown")
    meeder["actor_identity"]["resolution_state"] = "unresolved"
    meeder["actor_identity"]["remap_lineage"] = {
        "state": "unresolved", "predecessor_epoch_id": None,
        "reason": "hostile unresolved", "append_only": True,
    }
    vehicle_row = value["vehicle_epochs"][0]
    vehicle_row.update(status="unresolved", resolution_state="unresolved", decision_mode="unknown", vehicle_class="synthetic_fund_of_funds")
    vehicle_row["lineage"] = {
        "state": "unresolved", "predecessor_epoch_id": None,
        "reason": "hostile unresolved", "append_only": True,
    }
    stamp(value)
    compiled = compile_recipe(value, as_of=AS_OF)
    assert compiled["complex_count_receipt"]["distinct_eligible_research_complex_count"] == 0


def test_same_complex_deductions_cannot_be_negative_when_complexes_exceed_vehicles() -> None:
    value = recipe()
    value["observations"] = [
        row for row in value["observations"]
        if row["plane"] != "institutionalization_saturation"
    ]
    for ordinal in range(5):
        row = deepcopy(value["manager_complex_epochs"][1])
        row["manager_complex_id"] = f"mcx_extra_{ordinal}"
        row["complex_epoch_id"] = f"mce_extra_{ordinal}"
        row["actor_identity"]["raw_actor_string"] = f"Synthetic extra {ordinal}"
        value["manager_complex_epochs"].append(row)
    stamp(value)
    count = compile_recipe(value, as_of=AS_OF)["complex_count_receipt"]
    assert count["same_complex_multivehicle_deductions"] == 0
    assert count["same_complex_multivehicle_deductions"] >= 0


def test_independence_axes_remain_separate_and_declarative_unverified() -> None:
    independence = compile_recipe(recipe(), as_of=AS_OF)["complex_count_receipt"]["independence"]
    assert set(independence) == {
        "source_independence", "information_novelty", "mechanism_independence"
    }
    assert {
        (row["state"], row["assessment"])
        for row in independence.values()
    } == {("not_assessed", "declarative_unverified")}
    assert all("not independence proof" in row["basis"] for row in independence.values())


def test_reliability_counts_states_cutoffs_and_uncertainty_are_fail_closed() -> None:
    value = recipe()
    value["reliability"][1]["eligibility_state"] = "eligible"
    rejected(value, "reliability_state_coherence_invalid")

    value = recipe()
    value["reliability"][0]["matured_trials"] = 3
    rejected(value, "reliability_count_coherence_invalid")

    value = recipe()
    value["reliability"][0]["uncertainty_method"].update(lower=0.9, upper=0.1)
    rejected(value, "json_schema:reliability")

    receipt = compile_recipe(recipe(), as_of=AS_OF)
    eligible, insufficient = receipt["reliability"]
    assert 0 <= eligible["uncertainty_bounds"]["lower"] <= eligible["posterior"] <= eligible["uncertainty_bounds"]["upper"] <= 1
    assert insufficient["posterior"] is None
    assert insufficient["uncertainty_bounds"] == {"lower": None, "upper": None}

    with pytest.raises(InstitutionalIntelligenceError, match="reliability_cutoff_after_compile_as_of"):
        compile_recipe(recipe(), as_of="2026-07-15T00:00:00Z")


def test_reliability_is_closed_complex_epoch_domain_horizon_action_and_eval_os_only() -> None:
    value = recipe()
    value["reliability"][0]["domain"] = "caller_story"
    rejected(value, "json_schema:reliability")
    value = recipe()
    value["reliability"][0]["manager_complex_id"] = "mcx_wrong"
    rejected(value, "reliability_complex_epoch_unresolved")
    value = recipe()
    value["reliability"][0]["legacy_grade_imported"] = True
    rejected(value, "json_schema:reliability")
    source = inspect.getsource(manager_intent)
    assert all(
        name not in source
        for name in (
            "engine.manager_quality",
            "engine.manager_trades",
            "engine.fund_followability",
        )
    )


def test_k1_closed_vocabularies_are_reused_not_locally_weakened() -> None:
    k1_schema = json.loads(K1_REFERENCE_SCHEMA_PATH.read_text(encoding="utf-8"))
    k1_defs = k1_schema["$defs"]
    k1_vocabulary = load_vocabulary()
    k2_schema = json.loads(manager_intent.SCHEMA_PATH.read_text(encoding="utf-8"))
    reused = compile_recipe(recipe(), as_of=AS_OF)["k1_contract_reuse"]
    assert reused["coverage_classes"] == sorted(COVERAGE_CLASSES)
    assert reused["correction_kinds"] == sorted({"none", *CORRECTION_KINDS})
    assert reused["replay_modes"] == sorted(REPLAY_MODES)
    assert reused["vintage_states"] == sorted(VINTAGE_STATES)
    assert reused["rights_states"] == sorted(k1_defs["rights"]["properties"]["state"]["enum"])
    assert reused["missingness_states"] == sorted(k1_defs["missingness"]["properties"]["state"]["enum"])
    assert reused["missingness_reasons"] == sorted(
        value for value in k1_defs["missingness"]["properties"]["reason"]["enum"]
        if value is not None
    )
    assert reused["correction_chronology_states"] == sorted(
        k1_defs["correction"]["properties"]["chronology_state"]["enum"]
    )
    assert reused["independence_axes"] == k1_defs["independence"]["required"]
    assert reused["independence_states"] == sorted(k1_defs["axis"]["properties"]["state"]["enum"])
    assert reused["independence_assessment"] == k1_defs["axis"]["properties"]["assessment"]["const"]
    assert reused["clock_classes"] == sorted(k1_vocabulary["clock_classes"])
    assert reused["clock_grains"] == sorted(k1_defs["nativeClock"]["properties"]["grain"]["enum"])
    assert reused["clock_value_states"] == sorted(k1_defs["nativeClock"]["properties"]["value_state"]["enum"])
    assert reused["object_classes"] == sorted(k1_vocabulary["object_classes"])
    assert reused["authority_classes"] == sorted(k1_schema["properties"]["authority_class"]["enum"])
    assert reused["authority_fields"] == sorted(k1_defs["authority"]["required"])
    assert set(k2_schema["$defs"]["missingReason"]["enum"]) == set(reused["missingness_reasons"])
    assert set(k2_schema["$defs"]["observationCorrection"]["properties"]["kind"]["enum"]) == set(reused["correction_kinds"])
    assert set(k2_schema["$defs"]["campaignCorrection"]["properties"]["kind"]["enum"]) == set(reused["correction_kinds"])


def test_correction_requires_real_k1_append_supersession_lineage() -> None:
    value = recipe()
    successor = deepcopy(event(value, "obs_manager_positive"))
    successor["observation_id"] = "obs_manager_corrected"
    successor["correction"] = {
        "kind": "source_correction",
        "predecessor_observation_id": "obs_manager_positive",
        "reason": "synthetic correction attack",
        "append_only": True,
    }
    value["observations"].append(successor)
    rejected(value, "observation_correction_clock_not_later|observation_correction_k1_lineage_unbound")


def test_future_observation_correction_is_not_premature_supersession() -> None:
    value = recipe()
    successor_id = append_theme_correction(value, belief_date="2026-09-01")
    stamp(value)

    earlier = compile_recipe(value, as_of=AS_OF)
    earlier_events = {row["observation_id"]: row for row in earlier["events"]}
    assert earlier_events["obs_theme_peer"]["state"] == "THEME_MEMBER_CHANGE"
    assert earlier_events[successor_id]["state"] == "NOT_KNOWABLE"
    assert earlier["theme_comparisons"][0]["state"] == "WITHIN_THEME_PREFERENCE_COMPUTED"

    later = compile_recipe(value, as_of="2026-09-02T00:30:00Z")
    later_events = {row["observation_id"]: row for row in later["events"]}
    assert later_events["obs_theme_peer"]["state"] == "SUPERSEDED"
    assert later_events[successor_id]["state"] == "THEME_MEMBER_CHANGE"
    # The comparison is a PIT receipt at 2026-08-08, so the later correction
    # never rewrites its historical denominator or result.
    assert later["theme_comparisons"][0]["state"] == "WITHIN_THEME_PREFERENCE_COMPUTED"


def test_rights_blocked_correction_never_erases_usable_predecessor() -> None:
    value = recipe()
    successor_id = append_theme_correction(
        value,
        belief_date="2026-08-01",
        rights_blocked=True,
    )
    stamp(value)
    receipt = compile_recipe(value, as_of=AS_OF)
    events = {row["observation_id"]: row for row in receipt["events"]}
    assert events["obs_theme_peer"]["state"] == "THEME_MEMBER_CHANGE"
    assert events[successor_id]["state"] == "RIGHTS_BLOCKED"
    assert receipt["theme_comparisons"][0]["state"] == "WITHIN_THEME_PREFERENCE_COMPUTED"


def test_future_campaign_correction_preserves_current_predecessor_until_known() -> None:
    value = recipe()
    correction = deepcopy(value["campaign_transitions"][0])
    correction["transition_id"] = "ctr_campaign_1_corrected"
    correction["transitioned_at"] = "2026-09-01T00:00:00Z"
    correction["correction"] = {
        "kind": "source_correction",
        "supersedes_transition_id": "ctr_campaign_1",
        "reason": "future synthetic campaign correction",
        "append_only": True,
    }
    value["campaign_transitions"].append(correction)
    stamp(value)

    earlier = compile_recipe(value, as_of=AS_OF)
    earlier_history = {row["transition_id"]: row for row in earlier["campaign_history"]}
    assert earlier_history["ctr_campaign_1"]["record_state"] == "CURRENT_APPEND_ONLY_RECORD"
    assert earlier_history["ctr_campaign_1_corrected"]["record_state"] == "NOT_YET_KNOWABLE"
    assert earlier["current_campaign_states"] == {"cmp_meeder_alpha_1": "INITIATED"}

    later = compile_recipe(value, as_of="2026-09-02T00:00:00Z")
    later_history = {row["transition_id"]: row for row in later["campaign_history"]}
    assert later_history["ctr_campaign_1"]["record_state"] == "SUPERSEDED"
    assert later_history["ctr_campaign_1_corrected"]["record_state"] == "CURRENT_APPEND_ONLY_RECORD"
    assert later["current_campaign_states"] == {"cmp_meeder_alpha_1": "INITIATED"}


def test_no_authority_alias_payload_copy_or_freeform_plane_shape_can_enter() -> None:
    value = recipe()
    value["authority"]["can_rank"] = True
    rejected(value, "json_schema:authority|authority_must_be_all_false")
    value = recipe()
    event(value, "obs_manager_positive")["owner_payload"] = {"shares": 10}
    rejected(value, "json_schema:observations")
    value = recipe()
    event(value, "obs_saturation_positive")["denominator"] = {
        "kind": "public_reported_sleeve",
        "state": "complete",
        "total_positions": 1,
        "included_positions": 1,
        "excluded_positions": 0,
        "missing_positions": 0,
    }
    rejected(value, "plane_measure_denominator_shape_conflict")


def test_recipe_id_and_schema_reject_noncanonical_mutation() -> None:
    value = recipe()
    value["manager_complex_epochs"][0]["status"] = "inactive"
    assert "recipe_id_mismatch" in violations(value)


# --- K2-C wave: source_backed_owner_row contract extension (K2-B v1.1.0) -----


def test_owner_row_binding_forbidden_on_every_other_basis() -> None:
    value, _ = owner_row_case()
    donor = event(value, "obs_owner_row_positive")["owner_row_binding"]
    value["observations"] = [row for row in value["observations"] if row["observation_id"] != "obs_owner_row_positive"]
    event(value, "obs_manager_positive")["owner_row_binding"] = donor
    rejected(value, "json_schema:observations")


def test_source_backed_owner_row_without_binding_is_rejected() -> None:
    value = recipe()
    stub = deepcopy(event(value, "obs_manager_positive"))
    stub["observation_id"] = "obs_owner_row_no_binding"
    stub["evidence_basis"] = "source_backed_owner_row"
    value["observations"].append(stub)
    rejected(value, "json_schema:observations")


def test_owner_row_binding_reference_must_be_listed() -> None:
    value, _ = owner_row_case(unlisted_previous_raw_reference=True)
    rejected(value, "owner_row_binding_reference_unresolved")


def test_owner_row_catalog_and_raw_owner_store_cannot_be_swapped() -> None:
    value, _ = owner_row_case(swap_previous_catalog_for_raw=True)
    rejected(value, "owner_row_binding_owner_store_mismatch")


def test_owner_row_row_accession_must_match_raw_receipt_accession() -> None:
    value, _ = owner_row_case(current_row_accession="0001398344-26-000001")
    rejected(value, "owner_row_accession_conflict")


def test_owner_row_catalog_and_raw_report_period_must_agree() -> None:
    value, _ = owner_row_case(current_catalog_report_period="2026-04-30")
    rejected(value, "owner_row_report_period_conflict")


def test_owner_row_previous_period_must_be_strictly_earlier() -> None:
    value, _ = owner_row_case(
        previous_report_period="2026-06-30",
        previous_accepted_at="2026-06-15T20:00:00Z",
        previous_retained_at="2026-06-15T20:01:00Z",
        previous_source_cutoff_at="2026-06-15T20:00:00Z",
        previous_published_at="2026-06-15T20:05:00Z",
    )
    rejected(value, "owner_row_report_period_not_increasing")


def test_owner_row_subject_and_row_cusip_must_match_security_cusip() -> None:
    value, _ = owner_row_case(subject_id="cusip:999999999")
    rejected(value, "owner_row_subject_id_conflict")

    value, _ = owner_row_case(current_row_cusip="999999999")
    rejected(value, "owner_row_security_cusip_conflict")


def test_owner_row_primary_reference_must_be_current_raw_receipt() -> None:
    value, _ = owner_row_case(primary_reference_is_previous=True)
    rejected(value, "owner_row_primary_reference_not_current_raw_receipt")


def test_owner_row_previous_period_not_yet_available_is_non_positive() -> None:
    value, observation_id = owner_row_case(
        previous_retained_at="2026-09-01T00:00:00Z",
        previous_published_at="2026-09-01T00:05:00Z",
    )
    assert validate(value)
    receipt = compile_recipe(value, as_of=AS_OF)
    compiled = next(row for row in receipt["events"] if row["observation_id"] == observation_id)
    assert compiled["state"] != "MANAGER_RESEARCH_INTENT_ELIGIBLE_CONTEXT"
    assert compiled["state"] == "MANAGER_INTENT_INELIGIBLE_OR_INSUFFICIENT"


def test_owner_row_cusip_grammar_violation_is_rejected() -> None:
    value, _ = owner_row_case(security_cusip="abcdefghi")
    rejected(value, "json_schema:observations")


def test_owner_row_forbids_null_quantity_under_owner_row_basis() -> None:
    value, _ = owner_row_case(measure={"kind": "reported_share_change", "q_prev": None, "q_now": 140})
    rejected(value, "owner_row_measure_null_quantity_forbidden")

    value, _ = owner_row_case(measure={"kind": "reported_share_change", "q_prev": 100, "q_now": None})
    rejected(value, "owner_row_measure_null_quantity_forbidden")


def test_owner_row_valid_observation_is_security_bound_and_eligible() -> None:
    value, observation_id = owner_row_case()
    assert validate(value)
    receipt = compile_recipe(value, as_of=AS_OF)
    compiled = next(row for row in receipt["events"] if row["observation_id"] == observation_id)
    assert compiled["state"] == "MANAGER_RESEARCH_INTENT_ELIGIBLE_CONTEXT"
    assert compiled["state"] != "SOURCE_POINTER_ONLY_NO_SECURITY_BINDING"
    assert compiled["measure"]["kind"] == "reported_share_change"
    assert compiled["measure"]["state"] == "computed"
    assert compiled["measure"]["reported_share_delta"] == 40.0


def test_owner_row_compilation_is_deterministic() -> None:
    value, _ = owner_row_case()
    first = compile_recipe(value, as_of=AS_OF)
    second = compile_recipe(deepcopy(value), as_of=AS_OF)
    assert first == second


def test_owner_row_basis_does_not_perturb_existing_bases() -> None:
    receipt = compile_recipe(recipe(), as_of=AS_OF)
    by_id = {row["observation_id"]: row for row in receipt["events"]}
    assert by_id["obs_manager_positive"]["state"] == "MANAGER_RESEARCH_INTENT_ELIGIBLE_CONTEXT"
    assert by_id["obs_source_pointer_only"]["state"] == "SOURCE_POINTER_ONLY_NO_SECURITY_BINDING"
    assert manager_intent.VERSION == "1.1.0"
    assert receipt["version"] == "1.1.0"
