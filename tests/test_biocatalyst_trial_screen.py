"""Hostile contract tests for the pure BioCatalyst Trial Screen v1 transform."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

import engine.biocatalyst.trial_screen as trial_screen
from engine.biocatalyst.trial_screen import (
    MAX_FACET_BUCKETS,
    MAX_FACETS_RESPONSE_BYTES,
    MAX_INPUT_SNAPSHOTS,
    TrialScreenError,
    build_trial_screen_facets_read_model,
    build_trial_screen_read_model,
    canonicalize_trial_screen_filters,
    validate_trial_screen_facets_read_model,
    validate_trial_screen_read_model,
)
from engine.sector_intelligence import canonical_json_sha256, validate_contract
from engine.sector_intelligence.contracts import ContractValidationError


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_FIXTURE = (
    ROOT / "data" / "biocatalyst" / "fixtures" / "clinicaltrials" / "trial_snapshot.v1.valid.json"
)


def _observed(value: object, path: str) -> dict[str, object]:
    return {"state": "observed", "value": value, "source_json_path": path}


def _rehash_snapshot(snapshot: dict) -> None:
    snapshot["projection_sha256"] = canonical_json_sha256(
        {key: value for key, value in snapshot.items() if key != "projection_sha256"}
    )


def _snapshot(
    nct_id: str,
    *,
    sponsor: str = "Northstar Biopharma",
    condition: str = "Glioma",
    intervention_name: str = "NX-101",
    intervention_aliases: list[str] | None = None,
    intervention_type: str = "DRUG",
    intervention_description: str = "non-searchable description",
    phase: str = "PHASE2",
    status: str = "RECRUITING",
    study_type: str = "INTERVENTIONAL",
    primary_completion: str | None = "2026-02",
) -> dict:
    snapshot = json.loads(SNAPSHOT_FIXTURE.read_text(encoding="utf-8"))
    suffix = nct_id.removeprefix("NCT")
    content_sha = ("a" * 56) + suffix
    snapshot.update(
        {
            "snapshot_id": f"trial_snapshot_{nct_id}_screen",
            "nct_id": nct_id,
            "source_snapshot_ref": f"ctgov_snapshot_{nct_id}_screen",
            "source_record_ref": f"src:ctgov:{nct_id}:sha256:{content_sha}",
            "canonical_content_sha256": content_sha,
        }
    )
    snapshot["source_attribution"]["source_uri"] = f"https://clinicaltrials.gov/study/{nct_id}"
    facts = snapshot["facts"]
    facts["brief_title"] = _observed(
        f"{sponsor} {nct_id} study", "/protocolSection/identificationModule/briefTitle"
    )
    facts["official_title"] = _observed(
        f"Official {nct_id} Study", "/protocolSection/identificationModule/officialTitle"
    )
    facts["overall_status"] = _observed(
        status, "/protocolSection/statusModule/overallStatus"
    )
    facts["study_type"] = _observed(study_type, "/protocolSection/designModule/studyType")
    facts["phases"] = _observed([phase], "/protocolSection/designModule/phases")
    facts["sponsor"] = _observed(
        {"name": sponsor, "class": "INDUSTRY"},
        "/protocolSection/sponsorCollaboratorsModule/leadSponsor",
    )
    facts["conditions"] = _observed(
        [condition], "/protocolSection/conditionsModule/conditions"
    )
    facts["interventions"] = _observed(
        [
            {
                "type": intervention_type,
                "name": intervention_name,
                "otherNames": intervention_aliases or ["Northstar-101"],
                "description": intervention_description,
            }
        ],
        "/protocolSection/armsInterventionsModule/interventions",
    )
    if primary_completion is None:
        facts["primary_completion_date"] = {
            "state": "source_missing",
            "value": None,
            "source_json_path": "/protocolSection/statusModule/primaryCompletionDateStruct",
        }
    else:
        facts["primary_completion_date"] = _observed(
            {"date": primary_completion, "type": "ESTIMATED"},
            "/protocolSection/statusModule/primaryCompletionDateStruct",
        )
    _rehash_snapshot(snapshot)
    validate_contract(snapshot, repo_root=ROOT)
    return snapshot


def _context(count: int) -> dict[str, object]:
    return {
        "as_of": "2026-08-03T12:00:00Z",
        "last_success_at": "2026-08-03T12:00:00Z",
        "source_dataset_timestamp_raw": "2026-08-01T09:00:00",
        "configured_nct_count": count,
        "observed_nct_count": count,
    }


def _cursor(offset: int) -> str:
    return f"opaque-screen-cursor-{offset}"


def _build(
    snapshots: list[dict],
    *,
    filters: dict | None = None,
    offset: int = 0,
    limit: int = 50,
) -> dict:
    return build_trial_screen_read_model(
        trial_snapshots=snapshots,
        publication_context=_context(len(snapshots)),
        filters=filters,
        offset=offset,
        limit=limit,
        next_cursor_factory=_cursor,
    )


def _build_facets(
    snapshots: list[dict], *, filters: dict | None = None, context: dict | None = None
) -> dict:
    return build_trial_screen_facets_read_model(
        trial_snapshots=snapshots,
        publication_context=context or _context(len(snapshots)),
        filters=filters,
    )


def test_literal_and_filters_normalize_text_and_match_only_name_or_ctgov_alias() -> None:
    matching = _snapshot(
        "NCT00000001",
        sponsor="North  Star Biopharma",
        condition="Neuro  Oncology",
        intervention_name="NX 101",
        intervention_aliases=["Northstar-101"],
        primary_completion="2026-02",
    )
    result = _build(
        [matching],
        filters={
            "sponsor": "  NORTH star  ",
            "condition": "neuro oncology",
            "intervention": "northstar",
            "phase": "phase2",
            "status": " recruiting ",
            "study_type": "interventional",
            "primary_completion_from": "2026-02-01",
            "primary_completion_to": "2026-02-28",
        },
    )

    assert result["coverage"]["matched"] == 1
    assert result["query"] == {
        "sponsor": "north star",
        "condition": "neuro oncology",
        "intervention": "northstar",
        "phase": "phase2",
        "status": "recruiting",
        "study_type": "interventional",
        "primary_completion_from": "2026-02-01",
        "primary_completion_to": "2026-02-28",
        "filter_composition": "literal_and",
        "lexical_matching": "sponsor_condition_intervention_name_or_other_names_normalized_substring",
        "exact_matching": "phase_status_study_type_normalized_exact",
        "primary_completion_matching": "full_interval_containment",
    }
    row = result["rows"][0]
    assert row["interventions"]["values"] == [
        {"name": "NX 101", "aliases": ["Northstar-101"], "type": "DRUG"}
    ]
    assert row["enrollment"] == {
        "state": "observed", "value": {"count": 160, "type": "ESTIMATED"}
    }
    assert row["primary_completion"] == {
        "state": "observed",
        "literal": "2026-02",
        "precision": "month",
        "interval": {"start": "2026-02-01", "end": "2026-02-28"},
        "type": "ESTIMATED",
    }
    validate_contract(result, repo_root=ROOT)
    assert validate_trial_screen_read_model(
        result,
        trial_snapshots=[matching],
        publication_context=_context(1),
        filters={
            "sponsor": "  NORTH star  ",
            "condition": "neuro oncology",
            "intervention": "northstar",
            "phase": "phase2",
            "status": " recruiting ",
            "study_type": "interventional",
            "primary_completion_from": "2026-02-01",
            "primary_completion_to": "2026-02-28",
        },
        next_cursor_factory=_cursor,
    ) == result


@pytest.mark.parametrize(
    ("field", "candidate", "query"),
    [
        ("sponsor", {"sponsor": "Southstar Biopharma"}, {"sponsor": "northstar"}),
        ("condition", {"condition": "Lung cancer"}, {"condition": "glioma"}),
        (
            "intervention_description",
            {"intervention_name": "Drug A", "intervention_aliases": ["Drug-A"], "intervention_description": "Northstar only in description"},
            {"intervention": "northstar"},
        ),
        ("phase", {"phase": "PHASE2A"}, {"phase": "phase2"}),
        ("status", {"status": "RECRUITING SOON"}, {"status": "recruiting"}),
        ("study_type", {"study_type": "OBSERVATIONAL"}, {"study_type": "interventional"}),
    ],
)
def test_filter_near_misses_do_not_receive_alias_or_substring_inference(
    field: str, candidate: dict[str, object], query: dict[str, str]
) -> None:
    snapshot = _snapshot("NCT00000002", **candidate)
    result = _build([snapshot], filters=query)
    assert result["coverage"]["matched"] == 0, field
    assert result["rows"] == []


def test_partial_source_dates_use_closed_intervals_and_filters_require_day_precision() -> None:
    snapshots = [
        _snapshot("NCT00000010", primary_completion="2028"),
        _snapshot("NCT00000011", primary_completion="2028-02"),
        _snapshot("NCT00000012", primary_completion="2028-02-29"),
        _snapshot("NCT00000013", primary_completion=None),
    ]
    february = _build(
        snapshots,
        filters={"primary_completion_from": "2028-02-01", "primary_completion_to": "2028-02-29"},
    )
    # The year interval is not fully contained in February; no made-up day is
    # allowed.  Month and leap-day literals are both honestly contained.
    assert [row["nct_id"] for row in february["rows"]] == ["NCT00000011", "NCT00000012"]

    tight = _build(
        snapshots,
        filters={"primary_completion_from": "2028-02-15", "primary_completion_to": "2028-02-29"},
    )
    assert [row["nct_id"] for row in tight["rows"]] == ["NCT00000012"]

    for filters in (
        {"primary_completion_from": "2028-02"},
        {"primary_completion_to": "2028"},
        {"primary_completion_from": "2027-02-29"},
        {"primary_completion_from": "2028-03-01", "primary_completion_to": "2028-02-29"},
    ):
        with pytest.raises(TrialScreenError):
            _build(snapshots, filters=filters)

    malformed = _snapshot("NCT00000014", primary_completion="2028-02")
    malformed["facts"]["primary_completion_date"]["value"]["date"] = "2028-02-30"
    _rehash_snapshot(malformed)
    # The input contract permits the date string grammar, but Trial Screen
    # independently rejects an impossible calendar literal rather than placing
    # it at an invented date.
    validate_contract(malformed, repo_root=ROOT)
    with pytest.raises(TrialScreenError, match="primary_completion_date"):
        _build([malformed])


def test_chronological_interval_order_pagination_and_opaque_cursor_are_consistent() -> None:
    snapshots = [
        _snapshot("NCT00000022", primary_completion="2026"),
        _snapshot("NCT00000021", primary_completion="2026-01-01"),
        _snapshot("NCT00000023", primary_completion="2026-02"),
        _snapshot("NCT00000024", primary_completion=None),
    ]
    first = _build(snapshots, limit=2)
    assert [row["nct_id"] for row in first["rows"]] == ["NCT00000021", "NCT00000022"]
    assert first["pagination"] == {
        "limit": 2,
        "offset": 0,
        "total": 4,
        "returned": 2,
        "next_cursor": "opaque-screen-cursor-2",
    }
    second = _build(snapshots, offset=2, limit=2)
    assert [row["nct_id"] for row in second["rows"]] == ["NCT00000023", "NCT00000024"]
    assert second["pagination"]["next_cursor"] is None

    forged = deepcopy(first)
    forged["pagination"]["next_cursor"] = None
    with pytest.raises(ContractValidationError):
        validate_contract(forged, repo_root=ROOT)
    forged = deepcopy(first)
    forged["pagination"]["total"] = 3
    with pytest.raises(ContractValidationError):
        validate_contract(forged, repo_root=ROOT)
    with pytest.raises(TrialScreenError, match="next_cursor_factory_required"):
        build_trial_screen_read_model(
            trial_snapshots=snapshots,
            publication_context=_context(4),
            limit=2,
        )


def test_public_context_is_pointer_bound_and_the_screen_never_leaks_private_snapshot_fields() -> None:
    snapshot = _snapshot("NCT00000031")
    result = _build([snapshot])
    serialized = json.dumps(result, sort_keys=True)
    for forbidden in (
        "generation_id",
        "source_snapshot_ref",
        "source_record_ref",
        "canonical_content_sha256",
        "projection_sha256",
        "transaction_from",
        "evidence_claim_refs",
        "source_json_path",
        "raw_object_key",
        "description",
        "otherNames",
    ):
        assert forbidden not in serialized
    assert "screen_id" not in result
    assert "model_payload_sha256" not in result
    assert result["as_of"] == "2026-08-03T12:00:00Z"
    assert result["source"] == {
        "name": "ClinicalTrials.gov",
        "dataset_timestamp_raw": "2026-08-01T09:00:00",
    }
    assert result["coverage"] == {
        "class": "current_only", "configured": 1, "observed": 1, "matched": 1
    }
    assert result["capacity"] == {
        "max_input_snapshots": 10_000,
        "max_page_limit": 250,
        "max_sanitized_row_bytes": 131_072,
        "max_sanitized_scan_bytes": 33_554_432,
        "max_response_bytes": 1_048_576,
        "overflow_behavior": "reject_no_partial_screen",
    }

    contexts = [
        {},
        {**_context(1), "generation_id": "must-not-enter"},
        {**_context(1), "last_success_at": "2026-08-03T12:00:01Z"},
        {
            **_context(1),
            "source_dataset_timestamp_raw": "2026-08-01T09:00:01",
        },
        {
            **_context(1),
            "as_of": "2026-08-01T15:00:03Z",
            "last_success_at": "2026-08-01T15:00:03Z",
        },
        {**_context(1), "observed_nct_count": 0},
        {**_context(1), "configured_nct_count": 0},
    ]
    for context in contexts:
        with pytest.raises(TrialScreenError):
            build_trial_screen_read_model(
                trial_snapshots=[snapshot], publication_context=context, next_cursor_factory=_cursor
            )


def test_bounds_missing_malformed_and_contract_authority_fail_closed() -> None:
    snapshot = _snapshot("NCT00000041")
    for filters in (
        {"unknown": "x"},
        {"status": 1},
        {"phase": " "},
        {"primary_completion_from": "2026-02-30"},
    ):
        if filters == {"phase": " "}:
            assert canonicalize_trial_screen_filters(filters)["phase"] is None
        else:
            with pytest.raises(TrialScreenError):
                _build([snapshot], filters=filters)
    for offset, limit in ((-1, 1), (0, 0), (0, 251), (10_001, 1)):
        with pytest.raises(TrialScreenError):
            _build([snapshot], offset=offset, limit=limit)
    with pytest.raises(TrialScreenError, match="input_snapshot_limit"):
        build_trial_screen_read_model(
            trial_snapshots=[snapshot] * (MAX_INPUT_SNAPSHOTS + 1),
            publication_context=_context(MAX_INPUT_SNAPSHOTS + 1),
            next_cursor_factory=_cursor,
        )

    result = _build([snapshot])
    forged = deepcopy(result)
    forged["authority"]["decision_authority"] = True
    with pytest.raises(ContractValidationError):
        validate_contract(forged, repo_root=ROOT)
    forged = deepcopy(result)
    for field in ("sponsor", "condition", "intervention", "phase", "status", "study_type"):
        candidate = deepcopy(forged)
        candidate["query"][field] = " UNNORMALIZED "
        with pytest.raises(ContractValidationError):
            validate_contract(candidate, repo_root=ROOT)
    for field in ("primary_completion_from", "primary_completion_to"):
        candidate = deepcopy(forged)
        candidate["query"][field] = "2026-02"
        with pytest.raises(ContractValidationError):
            validate_contract(candidate, repo_root=ROOT)
    forged = deepcopy(result)
    forged["rows"][0]["primary_completion"]["interval"]["start"] = "2026-02-02"
    # Contract semantics require the interval to be the deterministic expansion
    # of the preserved literal, not merely two valid calendar dates.
    with pytest.raises(ContractValidationError):
        validate_contract(forged, repo_root=ROOT)
    forged = deepcopy(result)
    forged["coverage"]["observed"] = 0
    with pytest.raises(ContractValidationError):
        validate_contract(forged, repo_root=ROOT)
    filtered = _build([snapshot], filters={"sponsor": "northstar"})
    forged = deepcopy(filtered)
    forged["rows"][0]["sponsor"]["value"]["name"] = "Southstar Biopharma"
    with pytest.raises(ContractValidationError):
        validate_contract(forged, repo_root=ROOT)
    forged = deepcopy(result)
    forged["rows"][0]["source"]["retrieved_at"] = "2026-08-04T00:00:00Z"
    with pytest.raises(ContractValidationError):
        validate_contract(forged, repo_root=ROOT)
    with pytest.raises(TrialScreenError, match="next_cursor_invalid"):
        build_trial_screen_read_model(
            trial_snapshots=[snapshot, _snapshot("NCT00000042")],
            publication_context=_context(2),
            limit=1,
            next_cursor_factory=lambda _offset: "x" * 385,
        )


def test_sanitized_row_scan_and_response_byte_ceilings_fail_atomically(
    monkeypatch,
) -> None:
    explosive_aliases = [f"{index:02d}" + "x" * 1_998 for index in range(64)]
    explosive = _snapshot(
        "NCT00000051",
        intervention_aliases=explosive_aliases,
    )
    explosive["facts"]["interventions"]["value"].append(
        {
            "type": "DRUG",
            "name": "NX-102",
            "otherNames": [alias.replace("x", "y") for alias in explosive_aliases],
        }
    )
    _rehash_snapshot(explosive)
    validate_contract(explosive, repo_root=ROOT)
    with pytest.raises(TrialScreenError, match="row_too_large"):
        _build([explosive])

    ordinary = _snapshot("NCT00000052")
    ordinary_model = _build([ordinary])
    monkeypatch.setattr(trial_screen, "MAX_SANITIZED_SCAN_BYTES", 1)
    with pytest.raises(TrialScreenError, match="sanitized_scan_too_large"):
        _build([ordinary])

    monkeypatch.setattr(
        trial_screen,
        "MAX_SANITIZED_SCAN_BYTES",
        32 * 1024 * 1024,
    )
    monkeypatch.setattr(trial_screen, "MAX_RESPONSE_BYTES", 1)
    with pytest.raises(TrialScreenError, match="response_too_large"):
        _build([ordinary])
    with pytest.raises(TrialScreenError, match="response_too_large"):
        validate_trial_screen_read_model(
            ordinary_model,
            trial_snapshots=[ordinary],
            publication_context=_context(1),
            next_cursor_factory=_cursor,
        )


def test_facets_are_atomic_self_excluding_and_compose_all_other_filters() -> None:
    phase_two = _snapshot(
        "NCT00000101", sponsor="Northstar", condition="Glioma", phase="PHASE2"
    )
    phase_three = _snapshot(
        "NCT00000102", sponsor="Northstar", condition="Glioma", phase="PHASE3"
    )
    wrong_condition = _snapshot(
        "NCT00000103", sponsor="Northstar", condition="Lung cancer", phase="PHASE4"
    )
    wrong_sponsor = _snapshot(
        "NCT00000104", sponsor="Southstar", condition="Glioma", phase="PHASE1"
    )
    result = _build_facets(
        [phase_two, phase_three, wrong_condition, wrong_sponsor],
        filters={"sponsor": " NORTHSTAR ", "condition": " glioma ", "phase": "phase2"},
    )

    assert result["scope"] == "current_configured_snapshot_generation"
    assert result["coverage"] == {
        "class": "current_only", "configured": 4, "observed": 4, "matched": 1
    }
    assert result["facet_semantics"] == {
        "filter_composition": "literal_and_self_excluding_dimension",
        "counting_unit": "unique_trial",
        "selector_normalization": "whitespace_collapse_then_casefold",
        "bucket_order": "normalized_token_ascending",
        "partial_results": False,
    }
    phase, status, study_type = result["facets"]
    # Phase removes only the phase selector: sponsor and condition still
    # compose literally, so neither wrong-condition nor wrong-sponsor leaks in.
    assert phase["base_matched"] == 2
    assert phase["additivity"] == "non_additive"
    assert phase["buckets"] == [
        {"token": "phase2", "count": 1},
        {"token": "phase3", "count": 1},
    ]
    # The other facets retain the requested phase filter and therefore see only
    # the final one-trial AND intersection.
    assert status["base_matched"] == study_type["base_matched"] == 1
    assert status["buckets"] == [{"token": "recruiting", "count": 1}]
    assert study_type["buckets"] == [{"token": "interventional", "count": 1}]
    assert "pagination" not in result and "cursor" not in json.dumps(result)
    validate_contract(result, repo_root=ROOT)
    assert validate_trial_screen_facets_read_model(
        result,
        trial_snapshots=[phase_two, phase_three, wrong_condition, wrong_sponsor],
        publication_context=_context(4),
        filters={"sponsor": " NORTHSTAR ", "condition": " glioma ", "phase": "phase2"},
    ) == result


def test_facets_dedupe_multiphase_ncts_and_preserve_missingness_unselectable() -> None:
    multi_phase = _snapshot("NCT00000111", phase="PHASE2")
    multi_phase["facts"]["phases"]["value"] = [
        "Phase  2",
        " phase 2 ",
        "PHASE3",
    ]
    _rehash_snapshot(multi_phase)
    validate_contract(multi_phase, repo_root=ROOT)
    unselectable_phase = _snapshot("NCT00000112", phase=" ")
    missing_phase = _snapshot("NCT00000113", phase="PHASE1")
    missing_phase["facts"]["phases"] = {
        "state": "source_missing",
        "value": None,
        "source_json_path": "/protocolSection/designModule/phases",
    }
    _rehash_snapshot(missing_phase)
    validate_contract(missing_phase, repo_root=ROOT)

    result = _build_facets([multi_phase, unselectable_phase, missing_phase])
    phase = result["facets"][0]
    assert phase["base_matched"] == 3
    assert phase["buckets"] == [
        {"token": "phase 2", "count": 1},
        {"token": "phase3", "count": 1},
    ]
    # One NCT has two different selectable phase tokens, so phase is explicitly
    # non-additive; repeated normalized values cannot increment its NCT count.
    assert sum(bucket["count"] for bucket in phase["buckets"]) == 2
    assert phase["missingness"] == {
        "observed": 2,
        "observed_selectable": 1,
        "observed_unselectable": 1,
        "source_null": 0,
        "source_missing": 1,
        "not_applicable": 0,
        "parser_degraded": 0,
        "license_restricted": 0,
    }
    assert sum(phase["missingness"][state] for state in (
        "observed", "source_null", "source_missing", "not_applicable",
        "parser_degraded", "license_restricted",
    )) == phase["base_matched"]

    long_status = _snapshot("NCT00000114", status="X" * 81)
    status = _build_facets([long_status])["facets"][1]
    assert status["buckets"] == []
    assert status["missingness"]["observed_unselectable"] == 1
    assert status["missingness"]["observed_selectable"] == 0


def test_facets_binding_and_contract_semantics_reject_forged_aggregate() -> None:
    first = _snapshot("NCT00000121", phase="PHASE2", status="Recruiting")
    second = _snapshot("NCT00000122", phase="PHASE3", status="Active, not recruiting")
    result = _build_facets([first, second])
    assert result["as_of"] == "2026-08-03T12:00:00Z"
    assert result["source"] == {
        "name": "ClinicalTrials.gov", "dataset_timestamp_raw": "2026-08-01T09:00:00"
    }

    forged = deepcopy(result)
    forged["facets"][0]["buckets"] = list(reversed(forged["facets"][0]["buckets"]))
    with pytest.raises(ContractValidationError, match="bucket_order"):
        validate_contract(forged, repo_root=ROOT)
    forged = deepcopy(result)
    forged["facets"][1]["buckets"][0]["count"] = 2
    with pytest.raises(ContractValidationError, match="additivity"):
        validate_contract(forged, repo_root=ROOT)
    forged = deepcopy(result)
    forged["facets"][2]["missingness"]["source_missing"] = 1
    with pytest.raises(ContractValidationError, match="missingness"):
        validate_contract(forged, repo_root=ROOT)
    forged = deepcopy(result)
    forged["coverage"]["matched"] = 3
    with pytest.raises(ContractValidationError, match="coverage"):
        validate_contract(forged, repo_root=ROOT)
    forged = deepcopy(result)
    forged["capacity"]["max_buckets_per_dimension"] = 65
    with pytest.raises(ContractValidationError, match="capacity"):
        validate_contract(forged, repo_root=ROOT)
    forged = deepcopy(result)
    forged["facet_semantics"]["counting_unit"] = "source_value"
    with pytest.raises(ContractValidationError, match="semantics"):
        validate_contract(forged, repo_root=ROOT)
    forged = deepcopy(result)
    forged["facets"][0]["base_matched"] = 1
    forged["facets"][0]["missingness"]["observed"] = 1
    forged["facets"][0]["missingness"]["observed_selectable"] = 1
    forged["facets"][0]["buckets"] = [{"token": "phase2", "count": 1}]
    with pytest.raises(ContractValidationError, match="coverage"):
        validate_contract(forged, repo_root=ROOT)
    forged = deepcopy(result)
    forged["facets"][0]["buckets"][0]["count"] = (
        forged["facets"][0]["base_matched"] + 1
    )
    with pytest.raises(ContractValidationError, match="bucket_count"):
        validate_contract(forged, repo_root=ROOT)
    forged = deepcopy(result)
    forged["facets"][0]["missingness"]["observed_selectable"] = 0
    forged["facets"][0]["missingness"]["observed_unselectable"] = 2
    with pytest.raises(ContractValidationError, match="bucket_count"):
        validate_contract(forged, repo_root=ROOT)
    forged = deepcopy(result)
    forged["facets"][0]["missingness"]["observed_selectable"] = 1
    forged["facets"][0]["missingness"]["observed_unselectable"] = 1
    forged["facets"][0]["buckets"] = [{"token": "phase2", "count": 2}]
    with pytest.raises(ContractValidationError, match="bucket_count"):
        validate_contract(forged, repo_root=ROOT)
    selected = _build_facets(
        [first, _snapshot("NCT00000123", sponsor="Other Sponsor")],
        filters={"sponsor": "northstar"},
    )
    forged = deepcopy(selected)
    forged["facets"][1]["base_matched"] = 2
    forged["facets"][1]["missingness"]["observed"] = 2
    forged["facets"][1]["missingness"]["observed_selectable"] = 2
    forged["facets"][1]["buckets"][0]["count"] = 2
    with pytest.raises(ContractValidationError, match="self_exclusion"):
        validate_contract(forged, repo_root=ROOT)
    forged = deepcopy(result)
    forged["facets"][0]["buckets"][0]["count"] = 2
    with pytest.raises(TrialScreenError, match="input_binding_mismatch"):
        validate_trial_screen_facets_read_model(
            forged,
            trial_snapshots=[first, second],
            publication_context=_context(2),
        )

    for context in (
        {**_context(2), "last_success_at": "2026-08-03T12:00:01Z"},
        {**_context(2), "source_dataset_timestamp_raw": "2026-08-01T09:00:01"},
        {**_context(2), "observed_nct_count": 1},
    ):
        with pytest.raises(TrialScreenError):
            _build_facets([first, second], context=context)


def test_facets_caps_fail_whole_response_and_expose_no_forbidden_enumerations(
    monkeypatch,
) -> None:
    snapshots = [
        _snapshot(f"NCT{index:08d}", status=f"STATUS {index:02d}")
        for index in range(1, MAX_FACET_BUCKETS + 2)
    ]
    with pytest.raises(TrialScreenError, match="bucket_limit_exceeded"):
        _build_facets(snapshots)

    ordinary = _snapshot("NCT00000191")
    result = _build_facets([ordinary])
    serialized = json.dumps(result, sort_keys=True)
    for forbidden in (
        "nct_id",
        "brief_title",
        "official_title",
        "country",
        "enrollment",
        "primary_completion_date",
        "top_",
        "rows",
    ):
        assert forbidden not in serialized

    with pytest.raises(TrialScreenError, match="input_snapshot_limit"):
        build_trial_screen_facets_read_model(
            trial_snapshots=[ordinary] * (MAX_INPUT_SNAPSHOTS + 1),
            publication_context=_context(MAX_INPUT_SNAPSHOTS + 1),
        )
    monkeypatch.setattr(trial_screen, "MAX_SANITIZED_SCAN_BYTES", 1)
    with pytest.raises(TrialScreenError, match="sanitized_scan_too_large"):
        _build_facets([ordinary])
    monkeypatch.setattr(trial_screen, "MAX_SANITIZED_SCAN_BYTES", 32 * 1024 * 1024)
    monkeypatch.setattr(trial_screen, "MAX_FACETS_RESPONSE_BYTES", 1)
    with pytest.raises(TrialScreenError, match="facets_response_too_large"):
        _build_facets([ordinary])
    assert MAX_FACETS_RESPONSE_BYTES == 256 * 1024
