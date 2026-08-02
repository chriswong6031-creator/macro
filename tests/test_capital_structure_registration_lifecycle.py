"""Adversarial tests for the registration lifecycle truth-plane compiler."""
from __future__ import annotations

import copy
from hashlib import sha256
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from engine.capital_structure.event_spine import build_event_version, make_stable_span
from engine.capital_structure.registration_lifecycle import (
    AUTHORITY,
    SCOPE,
    UNAVAILABLE,
    compile_registration_lifecycles,
    validate_registration_lifecycle_bundle,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = (
    ROOT
    / "tests"
    / "fixtures"
    / "capital_structure"
    / "registration_lifecycle"
    / "adversarial_cases.json"
)
GENERATED_AT = "2026-08-10T12:00:00Z"
HASH = "f" * 64


def _rehash_event(event: dict) -> dict:
    identity = copy.deepcopy(event)
    identity.pop("event_id")
    event["event_id"] = "event:cs:" + sha256(
        json.dumps(
            identity,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()[:24]
    return event


def _rehash_stable_id(value: dict, field: str, prefix: str) -> dict:
    identity = copy.deepcopy(value)
    identity.pop(field)
    value[field] = prefix + sha256(
        json.dumps(
            identity,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()[:24]
    return value


def _rehash_bundle(bundle: dict) -> dict:
    return _rehash_stable_id(
        bundle, "generation_id", "registration-lifecycle:cs:"
    )


def _event(
    suffix: int,
    form: str,
    *,
    accepted_at: str | None,
    seen_at: str | None = None,
    file_number: str | None = "333-123",
    issuer_id: str = "sec:cik:0000000001",
    cik: str = "1",
    ticker: str = "ABC",
    correction_version: int = 1,
    correction_of: str | None = None,
    source_suffix: str = "base",
    classification_state: str | None = None,
    defer_reason: str | None = None,
    trusted_file_number: bool = True,
) -> dict:
    accession = f"0000000001-26-{suffix:06d}"
    observed_at = seen_at or accepted_at or "2026-08-01T12:00:00Z"
    manifest_id = (
        f"manifest:{accession}:{correction_version}:{source_suffix}"
    )
    observation = {
        "source_system": "sec_edgar",
        "source_id": accession,
        "manifest_id": manifest_id,
        "accession": accession,
        "issuer_id": issuer_id,
        "cik": cik,
        "ticker": ticker,
        "aliases": [f"{ticker} Corp"],
        "form": form,
        "file_number": file_number,
        "filing_date": "2026-08-01",
        "accepted_at": accepted_at,
        "first_seen_at": observed_at,
        "primary_document_url": (
            f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession}.htm"
        ),
        "exhibit_urls": [],
        "content_hashes": [HASH],
    }
    if classification_state is not None:
        observation["classification_state"] = classification_state
        observation["defer_reason"] = defer_reason
    span = make_stable_span(
        manifest_id,
        f"{form}:{source_suffix}:{file_number}",
        locator="document",
    )
    event = build_event_version(
        observation,
        [span],
        correction_version=correction_version,
        correction_of=correction_of,
    )
    if trusted_file_number:
        event["filing"]["file_number_provenance"] = (
            {
                "state": "observed",
                "value": file_number,
                "candidate_values": [file_number],
                "sources": ["sec_header_file_number"],
            }
            if file_number is not None
            else {
                "state": "unavailable",
                "value": None,
                "candidate_values": [],
                "sources": [],
            }
        )
        _rehash_event(event)
    return event


def _edge(
    child: dict,
    parent: dict,
    relationship: str,
    *,
    observed_at: str | None = None,
) -> dict:
    child_at = str((child.get("point_in_time") or {}).get("available_at"))
    parent_at = str((parent.get("point_in_time") or {}).get("available_at"))
    body = {
        "schema": "capital_structure.event_edge.v1",
        "from_event_id": child["event_id"],
        "to_event_id": parent["event_id"],
        "relationship": relationship,
        "link_method": "explicit_event_id",
        "observed_at": observed_at or max(child_at, parent_at),
        "immutable_record": True,
    }
    body["edge_id"] = "edge:cs:" + sha256(
        json.dumps(
            body, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()[:24]
    return body


def _scenario(name: str) -> tuple[list[dict], list[dict]]:
    cases = json.loads(FIXTURES.read_text(encoding="utf-8"))
    rows = cases[name]
    events = [
        _event(
            int(row["accession_suffix"]),
            str(row["form"]),
            accepted_at=str(row["accepted_at"]),
        )
        for row in rows
    ]
    edges = [
        _edge(
            events[index],
            events[int(row["target_index"])],
            str(row["relationship"]),
        )
        for index, row in enumerate(rows)
        if row["relationship"] is not None
    ]
    return events, edges


def _compile(
    events: list[dict],
    edges: list[dict],
    *,
    as_of: str = "2026-08-09T12:00:00Z",
    generated_at: str = GENERATED_AT,
) -> dict:
    return compile_registration_lifecycles(
        events, edges, as_of, generated_at
    )


def _schema_errors(bundle: dict) -> list:
    schema = json.loads(
        (
            ROOT
            / "contracts"
            / "capital_structure_registration_lifecycle.schema.json"
        ).read_text(encoding="utf-8")
    )
    return list(
        Draft202012Validator(
            schema, format_checker=FormatChecker()
        ).iter_errors(bundle)
    )


def _all_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        keys = set(value)
        for child in value.values():
            keys.update(_all_keys(child))
        return keys
    if isinstance(value, list):
        keys: set[str] = set()
        for child in value:
            keys.update(_all_keys(child))
        return keys
    return set()


def test_full_lifecycle_is_schema_valid_pit_and_post_effective_amendment_stays_effective():
    events, edges = _scenario("full_lifecycle")

    amended = _compile(events, edges, as_of="2026-08-02T23:59:59Z")
    effective = _compile(events, edges, as_of="2026-08-04T23:59:59Z")
    withdrawn = _compile(events, edges, as_of="2026-08-05T10:00:00Z")

    validate_registration_lifecycle_bundle(withdrawn)
    assert not _schema_errors(withdrawn)
    assert amended["records"][0]["observed_registration_state"] == "amended"
    assert effective["records"][0]["observed_registration_state"] == "effective"
    assert [
        row["state_after_event"] for row in effective["records"][0]["timeline"]
    ] == ["filed", "amended", "effective", "effective"]
    record = withdrawn["records"][0]
    assert record["observed_registration_state"] == "withdrawn"
    assert [row["transition"] for row in record["timeline"]] == [
        "filed",
        "amended",
        "effective",
        "amended",
        "withdrawn",
    ]
    assert record["registration"] == {
        "file_number": "333-123",
        "file_number_provenance": {
            "state": "observed",
            "value": "333-123",
            "candidate_values": ["333-123"],
            "sources": ["sec_header_file_number"],
        },
        "registration_family": "registration_s3",
    }
    assert record["authority"] == withdrawn["authority"] == AUTHORITY
    assert record["scope"] == withdrawn["scope"] == SCOPE
    assert record["unavailable"] == withdrawn["unavailable"] == UNAVAILABLE
    assert withdrawn["coverage"] == {
        "state": "observed",
        "reason": "linked_observed_registration_lifecycles_only",
        "candidate_event_count": 5,
        "lifecycle_count": 1,
        "timeline_event_count": 5,
        "deferred_count": 0,
    }
    assert not (
        _all_keys(withdrawn)
        & {
            "active_capacity",
            "executable_capacity",
            "primary_resale",
            "pricing",
            "remaining_dollars",
            "instrument",
            "instruments",
            "risk",
            "probability",
            "prophet_signal",
        }
    )


def test_missing_exact_group_or_linkage_keys_defer_without_guessing():
    missing_file = _event(31, "S-3", accepted_at="2026-08-01T10:00:00Z", file_number=None)
    root = _event(32, "S-3", accepted_at="2026-08-01T11:00:00Z")
    effect = _event(33, "EFFECT", accepted_at="2026-08-02T11:00:00Z")
    legacy = _event(
        37,
        "S-1",
        accepted_at="2026-08-01T12:00:00Z",
        trusted_file_number=False,
    )

    bundle = _compile([missing_file, root, effect, legacy], [])

    assert bundle["records"][0]["observed_registration_state"] == "filed"
    assert bundle["coverage"]["state"] == "partial"
    reasons = {item["reason"] for item in bundle["deferred"]}
    assert reasons == {
        "missing_file_number",
        "missing_lifecycle_edge",
        "untrusted_file_number_provenance",
    }
    assert all(
        item["candidate_event_ids"] == [] for item in bundle["deferred"]
    )


@pytest.mark.parametrize("mutation", ["value", "candidate", "filing"])
def test_file_number_provenance_requires_exact_typed_canonical_equality(
    mutation: str,
):
    event = _event(38, "S-3", accepted_at="2026-08-01T10:00:00Z")
    provenance = event["filing"]["file_number_provenance"]
    if mutation == "value":
        provenance["value"] = " 333-123 "
        provenance["candidate_values"] = [" 333-123 "]
    elif mutation == "candidate":
        provenance["candidate_values"] = [" 333-123 "]
    else:
        event["filing"]["file_number"] = " 333-123 "
    _rehash_event(event)

    bundle = _compile([event], [])

    assert bundle["records"] == []
    assert {item["reason"] for item in bundle["deferred"]} == {
        "untrusted_file_number_provenance"
    }


def test_missing_acceptance_clock_and_unclassified_observation_defer():
    missing_clock = _event(34, "S-3", accepted_at=None)
    deferred = _event(
        35,
        "S-1",
        accepted_at="2026-08-01T10:00:00Z",
        classification_state="deferred_linkage",
        defer_reason="fixture_requires_review",
    )

    bundle = _compile([missing_clock, deferred], [])

    assert bundle["records"] == []
    assert {item["reason"] for item in bundle["deferred"]} == {
        "missing_sec_accepted_at",
        "registration_observation_not_classified",
    }


def test_future_sec_acceptance_clock_cannot_leak_through_earlier_system_availability():
    malformed = _event(
        36,
        "S-3",
        accepted_at="2026-08-05T10:00:00Z",
        seen_at="2026-08-01T10:00:00Z",
    )

    bundle = _compile(
        [malformed], [], as_of="2026-08-02T10:00:00Z"
    )

    assert bundle["records"] == []
    assert {item["reason"] for item in bundle["deferred"]} == {
        "noncausal_event_clock"
    }
    assert "2026-08-05T10:00:00Z" not in json.dumps(bundle)


def test_multiple_edges_and_cross_group_edges_defer_instead_of_selecting_a_target():
    root = _event(41, "S-3", accepted_at="2026-08-01T10:00:00Z")
    amendment = _event(42, "S-3/A", accepted_at="2026-08-02T10:00:00Z")
    effect = _event(43, "EFFECT", accepted_at="2026-08-03T10:00:00Z")
    edges = [
        _edge(amendment, root, "amendment_of"),
        _edge(effect, root, "effectuates"),
        _edge(effect, amendment, "effectuates"),
    ]
    ambiguous = _compile([root, amendment, effect], edges)

    assert ambiguous["records"][0]["observed_registration_state"] == "amended"
    issue = next(
        item
        for item in ambiguous["deferred"]
        if item["reason"] == "ambiguous_lifecycle_edge"
    )
    assert set(issue["candidate_event_ids"]) == {
        root["event_id"],
        amendment["event_id"],
    }

    other_root = _event(
        44,
        "S-3",
        accepted_at="2026-08-01T09:00:00Z",
        issuer_id="sec:cik:0000000002",
        cik="2",
        ticker="DEF",
    )
    cross_effect = _event(
        45,
        "EFFECT",
        accepted_at="2026-08-02T09:00:00Z",
    )
    cross = _compile(
        [other_root, cross_effect],
        [_edge(cross_effect, other_root, "effectuates")],
    )
    assert "cross_issuer_link" in {
        item["reason"] for item in cross["deferred"]
    }


@pytest.mark.parametrize(
    ("child_form", "child_file_number", "reason"),
    [
        ("S-3/A", "333-999", "file_number_mismatch"),
        ("S-1/A", "333-123", "registration_family_mismatch"),
    ],
)
def test_file_number_and_registration_family_mismatches_defer(
    child_form: str, child_file_number: str, reason: str
):
    root = _event(51, "S-3", accepted_at="2026-08-01T10:00:00Z")
    child = _event(
        52,
        child_form,
        accepted_at="2026-08-02T10:00:00Z",
        file_number=child_file_number,
    )

    bundle = _compile(
        [root, child], [_edge(child, root, "amendment_of")]
    )

    assert reason in {item["reason"] for item in bundle["deferred"]}
    assert bundle["records"][0]["observed_registration_state"] == "filed"


def test_equal_sec_acceptance_clocks_defer_the_group_and_never_use_event_id_order():
    events, edges = _scenario("equal_clock_ambiguity")

    bundle = _compile(events, edges)

    assert bundle["records"] == []
    issue = next(
        item
        for item in bundle["deferred"]
        if item["reason"] == "ambiguous_sec_chronology"
    )
    assert set(issue["event_ids"]) == {
        events[1]["event_id"],
        events[2]["event_id"],
    }


def test_multiple_original_roots_for_one_strict_key_defer_the_entire_group():
    first = _event(24, "S-3", accepted_at="2026-08-01T10:00:00Z")
    second = _event(25, "S-3ASR", accepted_at="2026-08-02T10:00:00Z")

    bundle = _compile([first, second], [])

    assert bundle["records"] == []
    issue = next(
        item
        for item in bundle["deferred"]
        if item["reason"] == "multiple_registration_roots"
    )
    assert set(issue["candidate_event_ids"]) == {
        first["event_id"],
        second["event_id"],
    }


def test_future_events_and_edges_cannot_change_prior_snapshot_or_source_receipt():
    root = _event(61, "S-3", accepted_at="2026-08-01T10:00:00Z")
    future = _event(62, "EFFECT", accepted_at="2026-08-05T10:00:00Z")
    future_edge = _edge(future, root, "effectuates")

    base = _compile([root], [], as_of="2026-08-03T00:00:00Z")
    appended = _compile(
        [future, root], [future_edge], as_of="2026-08-03T00:00:00Z"
    )

    assert appended == base
    assert appended["source_receipt"]["visible_event_ids"] == [root["event_id"]]
    assert appended["source_receipt"]["visible_edge_ids"] == []

    verified_base = compile_registration_lifecycles(
        [root],
        [],
        "2026-08-03T00:00:00Z",
        GENERATED_AT,
        source_generation={
            "generation_id": "generation:cs:" + "a" * 24,
            "as_of": "2026-08-06T00:00:00Z",
            "status": "ok",
            "artifact_hashes": {
                "event_versions": "a" * 64,
                "event_edges": "b" * 64,
            },
        },
    )
    verified_appended = compile_registration_lifecycles(
        [root, future],
        [future_edge],
        "2026-08-03T00:00:00Z",
        GENERATED_AT,
        source_generation={
            "generation_id": "generation:cs:" + "c" * 24,
            "as_of": "2026-08-07T00:00:00Z",
            "status": "ok",
            "artifact_hashes": {
                "event_versions": "c" * 64,
                "event_edges": "d" * 64,
            },
        },
    )
    assert verified_appended == verified_base
    assert (
        verified_base["source_receipt"]["verification_state"]
        == "verified_telemetry_last_generation"
    )


def test_visible_same_group_correction_resolves_locked_old_edge_with_full_receipt():
    original = _event(71, "S-3", accepted_at="2026-08-01T10:00:00Z")
    effect = _event(72, "EFFECT", accepted_at="2026-08-02T10:00:00Z")
    correction = _event(
        71,
        "S-3",
        accepted_at="2026-08-01T10:00:00Z",
        seen_at="2026-08-04T10:00:00Z",
        correction_version=2,
        correction_of=original["event_id"],
        source_suffix="corrected",
    )
    lifecycle_edge = _edge(effect, original, "effectuates")
    correction_edge = _edge(
        correction,
        original,
        "supersedes",
        observed_at="2026-08-04T10:00:00Z",
    )

    before = _compile(
        [original, effect, correction],
        [lifecycle_edge, correction_edge],
        as_of="2026-08-03T00:00:00Z",
    )
    after = _compile(
        [correction, effect, original],
        [correction_edge, lifecycle_edge],
        as_of="2026-08-05T00:00:00Z",
    )

    assert before["records"][0]["timeline"][0]["event_id"] == original["event_id"]
    record = after["records"][0]
    assert record["timeline"][0]["event_id"] == correction["event_id"]
    assert record["timeline"][1]["relationship"] == {
        "edge_id": lifecycle_edge["edge_id"],
        "relationship": "effectuates",
        "to_event_id": original["event_id"],
        "resolved_to_event_id": correction["event_id"],
        "observed_at": lifecycle_edge["observed_at"],
    }
    receipt = record["derivation_receipt"]
    assert set(receipt["event_ids"]) == {
        original["event_id"],
        correction["event_id"],
        effect["event_id"],
    }
    assert set(receipt["edge_ids"]) == {
        lifecycle_edge["edge_id"],
        correction_edge["edge_id"],
    }


def test_standalone_corrected_root_receipts_its_own_full_supersession_chain():
    original = _event(74, "S-3", accepted_at="2026-08-01T10:00:00Z")
    correction = _event(
        74,
        "S-3ASR",
        accepted_at="2026-08-01T10:00:00Z",
        seen_at="2026-08-04T10:00:00Z",
        correction_version=2,
        correction_of=original["event_id"],
        source_suffix="corrected-root",
    )
    correction_edge = _edge(
        correction,
        original,
        "supersedes",
        observed_at="2026-08-04T10:00:00Z",
    )

    bundle = _compile(
        [original, correction],
        [correction_edge],
        as_of="2026-08-05T00:00:00Z",
    )

    receipt = bundle["records"][0]["derivation_receipt"]
    assert set(receipt["event_ids"]) == {
        original["event_id"],
        correction["event_id"],
    }
    assert receipt["edge_ids"] == [correction_edge["edge_id"]]


def test_correction_version_without_exact_supersedes_edge_is_deferred():
    original = _event(73, "S-3", accepted_at="2026-08-01T10:00:00Z")
    correction = _event(
        73,
        "S-3",
        accepted_at="2026-08-01T10:00:00Z",
        seen_at="2026-08-04T10:00:00Z",
        correction_version=2,
        correction_of=original["event_id"],
        source_suffix="missing-supersedes",
    )

    bundle = _compile(
        [original, correction], [], as_of="2026-08-05T00:00:00Z"
    )

    assert bundle["records"] == []
    assert {item["reason"] for item in bundle["deferred"]} == {
        "correction_link_missing"
    }


@pytest.mark.parametrize(
    "foreign_logical_key, correction_version", [(True, 2), (False, 3)]
)
def test_correction_must_target_direct_prior_version_of_same_logical_sec_observation(
    foreign_logical_key: bool,
    correction_version: int,
):
    original = _event(76, "S-3", accepted_at="2026-08-01T10:00:00Z")
    correction = _event(
        77 if foreign_logical_key else 76,
        "S-3",
        accepted_at="2026-08-01T10:00:00Z",
        seen_at="2026-08-04T10:00:00Z",
        correction_version=correction_version,
        correction_of=original["event_id"],
        source_suffix="foreign-logical" if foreign_logical_key else "skipped-version",
    )
    correction_edge = _edge(
        correction,
        original,
        "supersedes",
        observed_at="2026-08-04T10:00:00Z",
    )

    bundle = _compile(
        [original, correction],
        [correction_edge],
        as_of="2026-08-05T00:00:00Z",
    )

    assert bundle["records"] == []
    assert {item["reason"] for item in bundle["deferred"]} == {
        "correction_history_mismatch"
    }


def test_group_changing_correction_does_not_retarget_an_old_lifecycle_edge():
    original = _event(81, "S-3", accepted_at="2026-08-01T10:00:00Z")
    effect = _event(82, "EFFECT", accepted_at="2026-08-02T10:00:00Z")
    correction = _event(
        81,
        "S-3",
        accepted_at="2026-08-01T10:00:00Z",
        seen_at="2026-08-04T10:00:00Z",
        file_number="333-999",
        correction_version=2,
        correction_of=original["event_id"],
        source_suffix="wrong-group",
    )
    edges = [
        _edge(effect, original, "effectuates"),
        _edge(
            correction,
            original,
            "supersedes",
            observed_at="2026-08-04T10:00:00Z",
        ),
    ]

    bundle = _compile(
        [original, effect, correction], edges, as_of="2026-08-05T00:00:00Z"
    )

    assert bundle["records"] == []
    assert "correction_group_changed" in {
        item["reason"] for item in bundle["deferred"]
    }


def test_correction_cannot_change_root_to_amendment_role_inside_same_family():
    prior_root = _event(83, "S-3ASR", accepted_at="2026-08-01T09:00:00Z")
    original = _event(84, "S-3", accepted_at="2026-08-01T10:00:00Z")
    correction = _event(
        84,
        "S-3/A",
        accepted_at="2026-08-02T10:00:00Z",
        seen_at="2026-08-04T10:00:00Z",
        correction_version=2,
        correction_of=original["event_id"],
        source_suffix="role-change",
    )
    edges = [
        _edge(
            correction,
            original,
            "supersedes",
            observed_at="2026-08-04T10:00:00Z",
        ),
        _edge(
            correction,
            prior_root,
            "amendment_of",
            observed_at="2026-08-04T10:00:00Z",
        ),
    ]

    bundle = _compile(
        [prior_root, original, correction],
        edges,
        as_of="2026-08-05T00:00:00Z",
    )

    assert bundle["records"][0]["observed_registration_state"] == "filed"
    assert "correction_group_changed" in {
        item["reason"] for item in bundle["deferred"]
    }
    assert all(
        row["event_id"] != correction["event_id"]
        for row in bundle["records"][0]["timeline"]
    )


def test_post_withdrawal_effect_is_deferred_and_cannot_reopen_observed_state():
    events, edges = _scenario("post_withdrawal_effect")

    bundle = _compile(events, edges)

    record = bundle["records"][0]
    assert record["observed_registration_state"] == "withdrawn"
    assert [row["transition"] for row in record["timeline"]] == [
        "filed",
        "withdrawn",
    ]
    issue = next(
        item
        for item in bundle["deferred"]
        if item["reason"] == "post_withdrawal_transition"
    )
    assert issue["event_ids"] == [events[2]["event_id"]]
    assert record["coverage"]["state"] == "partial"
    assert issue["defer_id"] in record["coverage"]["deferred_ids"]


def test_immutable_id_collisions_and_orphan_edges_are_hard_integrity_failures():
    root = _event(91, "S-3", accepted_at="2026-08-01T10:00:00Z")
    mutation = copy.deepcopy(root)
    mutation["issuer"]["ticker"] = "MUT"
    with pytest.raises(ValueError, match="immutable event collision"):
        _compile([root, mutation], [])

    with pytest.raises(ValueError, match="identity digest mismatch"):
        _compile([mutation], [])

    effect = _event(92, "EFFECT", accepted_at="2026-08-02T10:00:00Z")
    edge = _edge(effect, root, "effectuates")
    edge_mutation = copy.deepcopy(edge)
    edge_mutation["to_event_id"] = effect["event_id"]
    with pytest.raises(ValueError, match="immutable edge collision"):
        _compile([root, effect], [edge, edge_mutation])

    with pytest.raises(ValueError, match="orphan edge"):
        _compile([effect], [edge])


def test_non_registration_inputs_are_explicitly_unavailable_not_an_empty_green_state():
    event = _event(101, "10-Q", accepted_at="2026-08-01T10:00:00Z")

    bundle = _compile([event], [])

    validate_registration_lifecycle_bundle(bundle)
    assert bundle["coverage"] == {
        "state": "unavailable",
        "reason": "no_visible_registration_lifecycle_observations",
        "candidate_event_count": 0,
        "lifecycle_count": 0,
        "timeline_event_count": 0,
        "deferred_count": 0,
    }
    assert bundle["records"] == []
    assert bundle["deferred"] == []


def test_unavailable_upstream_generation_emits_no_false_zero_lifecycle_claim():
    bundle = compile_registration_lifecycles(
        [],
        [],
        "2026-08-01T10:00:00Z",
        "2026-08-01T11:00:00Z",
        source_generation={
            "generation_id": None,
            "as_of": None,
            "status": "missing",
            "artifact_hashes": {},
        },
    )

    validate_registration_lifecycle_bundle(bundle)
    assert bundle["coverage"]["state"] == "unavailable"
    assert bundle["coverage"]["reason"] == "upstream_generation_unavailable"
    assert bundle["records"] == []


def test_schema_pins_the_complete_scope_and_unavailable_firewall():
    events, edges = _scenario("full_lifecycle")
    bundle = _compile(events, edges)

    weakened = copy.deepcopy(bundle)
    weakened["unavailable"] = ["risk_assessment"]
    with pytest.raises(ValueError, match="violates contract"):
        validate_registration_lifecycle_bundle(weakened)

    weakened = copy.deepcopy(bundle)
    weakened["scope"]["does_not_establish"] = ["trade_decision"]
    with pytest.raises(ValueError, match="violates contract"):
        validate_registration_lifecycle_bundle(weakened)


def test_semantic_validator_rejects_empty_observed_or_unbound_lifecycle_artifacts():
    events, edges = _scenario("full_lifecycle")
    bundle = _compile(events, edges)

    empty_observed = copy.deepcopy(bundle)
    empty_observed["records"] = []
    empty_observed["coverage"].update(
        {
            "state": "observed",
            "reason": "linked_observed_registration_lifecycles_only",
            "lifecycle_count": 0,
            "timeline_event_count": 0,
        }
    )
    _rehash_bundle(empty_observed)
    with pytest.raises(ValueError, match="semantic invariant failed: observed coverage"):
        validate_registration_lifecycle_bundle(empty_observed)

    contradictory_latest = copy.deepcopy(bundle)
    record = contradictory_latest["records"][0]
    record["latest_observed_event_id"] = record["timeline"][0]["event_id"]
    record["observed_registration_state"] = "filed"
    _rehash_bundle(contradictory_latest)
    with pytest.raises(
        ValueError, match="semantic invariant failed: lifecycle .* latest event"
    ):
        validate_registration_lifecycle_bundle(contradictory_latest)

    absent_derivation_membership = copy.deepcopy(bundle)
    derivation = absent_derivation_membership["records"][0]["derivation_receipt"]
    derivation["event_ids"] = []
    _rehash_stable_id(derivation, "receipt_id", "receipt:lifecycle:cs:")
    _rehash_bundle(absent_derivation_membership)
    with pytest.raises(
        ValueError,
        match="semantic invariant failed: lifecycle .* timeline is not covered",
    ):
        validate_registration_lifecycle_bundle(absent_derivation_membership)

    forged_source_receipt = copy.deepcopy(bundle)
    forged_source_receipt["source_receipt"]["receipt_id"] = (
        "receipt:registration-lifecycle:cs:" + "0" * 24
    )
    _rehash_bundle(forged_source_receipt)
    with pytest.raises(
        ValueError, match="semantic invariant failed: source_receipt.receipt_id"
    ):
        validate_registration_lifecycle_bundle(forged_source_receipt)

    partial_events, partial_edges = _scenario("post_withdrawal_effect")
    partial = _compile(partial_events, partial_edges)
    partial_record = partial["records"][0]
    partial_record["coverage"] = {
        "state": "observed",
        "reason": "linked_observed_registration_events_only",
        "deferred_ids": [],
    }
    _rehash_bundle(partial)
    with pytest.raises(
        ValueError,
        match="semantic invariant failed: lifecycle .* coverage does not bind",
    ):
        validate_registration_lifecycle_bundle(partial)
