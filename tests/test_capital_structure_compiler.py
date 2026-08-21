from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

import pandas as pd
import pytest
import requests

from collectors.sec_capital_structure import FORM_POLICY
from engine.capital_structure.source_identity import manifest_id_for
from scripts.compile_capital_structure_events import (
    CapitalStructureCompileDegraded,
    EVENT_COLUMNS,
    _generation_id,
    _load_existing_events,
    compile_from_disk,
    compile_manifest_records,
)
from engine.capital_structure.source_ledger_io import (
    encode_source_ledger,
    read_source_ledger,
    source_ledger_path,
)


def _write_ledger(path, records):
    """Write a source-manifest ledger fixture, bypassing the validating writer.

    Fixtures deliberately include ledgers the identity law rejects.
    """
    path.write_bytes(encode_source_ledger(list(records)))


ROOT = Path(__file__).resolve().parents[1]


def _manifest(
    accession: str,
    form: str,
    *,
    accepted_at: str,
    first_seen_at: str,
    filing_date: str = "2026-08-01",
    file_number: str | None = "333-123",
    document_role: str = "complete_submission",
    parent_manifest_id: str | None = None,
    parser_eligibility: str = "eligible",
    corruption_state: str = "clean",
    content_marker: str = "v1",
    include_file_number_provenance: bool = True,
) -> dict:
    raw = f"{accession}|{form}|{document_role}|{content_marker}".encode()
    digest = sha256(raw).hexdigest()
    sequence = "0" if document_role == "complete_submission" else "1"
    document_name = (
        "complete-submission.txt" if document_role == "complete_submission" else "primary.htm"
    )
    record = {
        "schema": "capital_structure.source_manifest/v1",
        "manifest_id": "",
        "source_system": "sec_edgar",
        "source_id": f"{accession}:{sequence}:{document_name}",
        "issuer": {
            "issuer_id": "sec:cik:0000000001", "cik": "1", "ticker": "ABC",
            "aliases": ["ABC Corp"],
        },
        "filing": {
            "accession": accession, "form": form, "filing_date": filing_date,
            "accepted_at": accepted_at, "file_number": file_number,
        },
        "document": {
            "canonical_url": f"https://www.sec.gov/Archives/{accession}.txt#document={sequence}",
            "document_name": document_name, "document_type": form,
            "document_role": document_role, "sequence": sequence, "media_type": "text/plain",
            "byte_length": len(raw), "document_version": 1,
            "content_sha256": digest, "parent_manifest_id": parent_manifest_id,
            "root_locator": f"sha256:{digest}",
        },
        "retrieval": {
            "retrieved_at": first_seen_at, "first_seen_at": first_seen_at,
            "transport_status": "retrieved",
        },
        "storage": {
            "backend": "r2",
            "store_id": "r2_shared",
            "object_key": f"capital_structure/sec/sha256/{digest[:2]}/{digest}",
            "content_addressed": True, "retention_state": "retained",
        },
        "rights": {
            "redistribution_class": "public_source_link",
            "attribution_required": True, "license_note": "SEC filing",
        },
        "privacy": {"classification": "public", "contains_personal_data": False},
        "parser": {
            "eligibility": parser_eligibility, "corruption_state": corruption_state,
            "parser_version": "sec-submission-sgml/1.0.0",
        },
        "spans": [{
            "span_id": f"root:{digest}", "locator_type": "document",
            "locator": f"bytes:0-{len(raw)}", "text_sha256": digest,
        }],
    }
    if include_file_number_provenance:
        record["filing"]["file_number_provenance"] = (
            {
                "state": "observed", "value": file_number,
                "candidate_values": [file_number],
                "sources": ["legacy_sgml_file_number"],
            }
            if file_number
            else {
                "state": "unavailable", "value": None,
                "candidate_values": [], "sources": [],
            }
        )
    record["manifest_id"] = manifest_id_for(record)
    return record


def _bundle(accession: str, form: str, **kwargs) -> list[dict]:
    complete = _manifest(accession, form, document_role="complete_submission", **kwargs)
    primary = _manifest(
        accession,
        form,
        document_role="primary",
        parent_manifest_id=complete["manifest_id"],
        **kwargs,
    )
    return [complete, primary]


def _resign_manifest(record: dict) -> dict:
    record["manifest_id"] = manifest_id_for(record)
    return record


def _resign_bundle(records: list[dict]) -> list[dict]:
    complete = next(
        (row for row in records if row["document"]["document_role"] == "complete_submission"),
        None,
    )
    if complete is not None:
        _resign_manifest(complete)
        for row in records:
            if row is complete:
                continue
            row["document"]["parent_manifest_id"] = complete["manifest_id"]
            _resign_manifest(row)
    else:
        for row in records:
            _resign_manifest(row)
    return records


def _set_bundle_version(records: list[dict], version: int) -> list[dict]:
    for row in records:
        row["document"]["document_version"] = version
    return _resign_bundle(records)


def _schema() -> dict:
    return json.loads((
        ROOT / "contracts/capital_structure_source_manifest.schema.json"
    ).read_text())


def test_compiler_skips_intervening_prospectus_when_linking_registration_amendment():
    records = [
        *_bundle(
            "0000000001-26-000001", "S-3",
            accepted_at="2026-08-01T10:00:00Z", first_seen_at="2026-08-01T10:00:03Z",
        ),
        *_bundle(
            "0000000001-26-000002", "424B5",
            accepted_at="2026-08-02T10:00:00Z", first_seen_at="2026-08-02T10:00:03Z",
        ),
        *_bundle(
            "0000000001-26-000003", "S-3/A",
            accepted_at="2026-08-03T10:00:00Z", first_seen_at="2026-08-03T10:00:03Z",
        ),
    ]
    result = compile_manifest_records(
        records, manifest_schema=_schema(), generated_at="2026-08-03T12:00:00Z"
    )

    assert len(result["events"]) == 3
    assert len(result["edges"]) == 1
    edge = result["edges"][0]
    assert edge["relationship"] == "amendment_of"
    by_form = {event["filing"]["form"]: event for event in result["events"]}
    assert edge["from_event_id"] == by_form["S-3/A"]["event_id"]
    assert edge["to_event_id"] == by_form["S-3"]["event_id"]
    assert edge["to_event_id"] != by_form["424B5"]["event_id"]
    assert by_form["S-3/A"]["classification"] == {
        "state": "classified", "defer_reason": None,
    }
    assert by_form["S-3/A"]["filing"]["file_number_provenance"] == {
        "state": "observed", "value": "333-123",
        "candidate_values": ["333-123"],
        "sources": ["legacy_sgml_file_number"],
    }
    queued_forms = {row["form"] for row in result["review_queue"]}
    assert "S-3/A" not in queued_forms
    assert queued_forms == {"424B5"}
    assert result["telemetry"]["authority"]["prophet_authority"] is False


def test_legacy_file_number_without_provenance_cannot_create_exact_linkage():
    records = [
        *_bundle(
            "0000000001-26-000001", "S-3",
            accepted_at="2026-08-01T10:00:00Z",
            first_seen_at="2026-08-01T10:00:03Z",
            include_file_number_provenance=False,
        ),
        *_bundle(
            "0000000001-26-000002", "S-3/A",
            accepted_at="2026-08-02T10:00:00Z",
            first_seen_at="2026-08-02T10:00:03Z",
            include_file_number_provenance=False,
        ),
    ]

    result = compile_manifest_records(records, manifest_schema=_schema())

    assert result["telemetry"]["counts"]["compile_failures"] == 0
    assert all(event["filing"]["file_number"] is None for event in result["events"])
    assert all(
        "file_number_provenance" not in event["filing"]
        for event in result["events"]
    )
    assert not [
        edge for edge in result["edges"] if edge["relationship"] == "amendment_of"
    ]
    assert any(
        item["accession"] == "0000000001-26-000002"
        and item["classification_state"] == "deferred_linkage"
        and item["defer_reason"] == "missing_exact_linkage_keys"
        for item in result["review_queue"]
    )


def test_provenance_backfill_emits_a_new_hardened_event_version():
    accession = "0000000001-26-000001"
    legacy_bundle = _bundle(
        accession, "S-3",
        accepted_at="2026-08-01T10:00:00Z",
        first_seen_at="2026-08-01T10:00:03Z",
        include_file_number_provenance=False,
    )
    first = compile_manifest_records(
        legacy_bundle,
        manifest_schema=_schema(),
        generated_at="2026-08-01T12:00:00Z",
    )
    hardened_bundle = _bundle(
        accession, "S-3",
        accepted_at="2026-08-01T10:00:00Z",
        first_seen_at="2026-08-02T10:00:03Z",
        content_marker="provenance-backfill",
    )
    _set_bundle_version(hardened_bundle, 2)

    corrected = compile_manifest_records(
        [*legacy_bundle, *hardened_bundle],
        existing_events=first["events"],
        manifest_schema=_schema(),
        generated_at="2026-08-02T12:00:00Z",
    )

    assert len(corrected["events"]) == 2
    legacy_event, hardened_event = corrected["events"]
    assert "file_number_provenance" not in legacy_event["filing"]
    assert legacy_event["filing"]["file_number"] is None
    assert hardened_event["filing"]["file_number"] == "333-123"
    assert hardened_event["filing"]["file_number_provenance"] == {
        "state": "observed", "value": "333-123",
        "candidate_values": ["333-123"],
        "sources": ["legacy_sgml_file_number"],
    }
    assert hardened_event["version"]["correction_of"] == legacy_event["event_id"]
    assert any(
        edge["relationship"] == "supersedes"
        and edge["from_event_id"] == hardened_event["event_id"]
        and edge["to_event_id"] == legacy_event["event_id"]
        for edge in corrected["edges"]
    )


def test_compiler_uses_system_first_seen_clock_for_backfilled_filing():
    records = _bundle(
        "0000000001-20-000001", "S-3", filing_date="2020-01-02",
        accepted_at="2020-01-02T15:30:00Z", first_seen_at="2026-08-01T10:00:00Z",
    )
    event = compile_manifest_records(records, manifest_schema=_schema())["events"][0]
    assert event["point_in_time"]["public_available_at"] == "2020-01-02T15:30:00Z"
    assert event["point_in_time"]["available_at"] == "2026-08-01T10:00:00Z"


def test_event_clock_waits_for_latest_evidence_dependency():
    records = _bundle(
        "0000000001-26-000001", "S-3",
        accepted_at="2026-01-01T10:00:00Z", first_seen_at="2026-01-01T10:00:03Z",
    )
    records[1]["retrieval"] = {
        **records[1]["retrieval"],
        "retrieved_at": "2026-02-01T12:00:00Z",
        "first_seen_at": "2026-02-01T12:00:00Z",
    }
    _resign_manifest(records[1])

    event = compile_manifest_records(records, manifest_schema=_schema())["events"][0]

    assert event["point_in_time"]["available_at"] == "2026-02-01T12:00:00Z"


def test_invalid_manifest_is_deferred_not_promoted_to_event():
    bundle = _bundle(
        "0000000001-26-000001", "S-3",
        accepted_at="2026-08-01T10:00:00Z", first_seen_at="2026-08-01T10:00:03Z",
    )
    bad = bundle[1]
    bad["storage"]["content_addressed"] = "yes"
    _resign_manifest(bad)
    result = compile_manifest_records(bundle, manifest_schema=_schema())
    assert result["events"] == []
    assert result["telemetry"]["status"] == "degraded"
    assert result["telemetry"]["generation_id"] is None
    assert result["telemetry"]["artifact_hashes"] == {
        "event_versions": None, "event_edges": None, "review_queue": None,
    }
    assert result["telemetry"]["counts"]["compile_failures"] == 1
    assert result["telemetry"]["compile_failures"][0]["state"] == "invalid_source_manifest_bundle"


def test_disk_compiler_is_network_free_and_idempotent(tmp_path, monkeypatch):
    records = _bundle(
        "0000000001-26-000001", "S-3",
        accepted_at="2026-08-01T10:00:00Z", first_seen_at="2026-08-01T10:00:03Z",
    )
    _write_ledger(source_ledger_path(tmp_path), records)

    def explode(*args, **kwargs):
        raise AssertionError("offline compiler attempted network access")

    monkeypatch.setattr(requests, "get", explode)
    first = compile_from_disk(root=tmp_path, generated_at="2026-08-01T12:00:00Z")
    first_events = pd.read_parquet(tmp_path / "event_versions.parquet")
    second = compile_from_disk(root=tmp_path, generated_at="2026-08-01T12:00:00Z")
    second_events = pd.read_parquet(tmp_path / "event_versions.parquet")

    assert first == second == {
        "status": "ok", "events": 1, "edges": 0, "review_queue": 0, "failures": 0,
    }
    assert first_events["event_id"].tolist() == second_events["event_id"].tolist()


def test_bad_manifest_quarantines_entire_accession_and_digest_links_are_semantic():
    bundle = _bundle(
        "0000000001-26-000001", "S-3",
        accepted_at="2026-08-01T10:00:00Z", first_seen_at="2026-08-01T10:00:03Z",
    )
    bundle[1]["document"]["root_locator"] = "sha256:" + ("f" * 64)
    _resign_manifest(bundle[1])
    result = compile_manifest_records(bundle, manifest_schema=_schema())
    assert result["events"] == []
    assert result["telemetry"]["counts"]["compile_failures"] == 1
    assert "root_locator digest" in " ".join(
        result["telemetry"]["compile_failures"][0]["errors"]
    )


def test_manifest_full_body_identity_and_global_duplicate_ids_fail_before_grouping():
    first = _bundle(
        "0000000001-26-000001", "S-3",
        accepted_at="2026-08-01T10:00:00Z", first_seen_at="2026-08-01T10:00:03Z",
    )
    body_mutation = deepcopy(first[0])
    body_mutation["issuer"]["ticker"] = "MUTATED"
    with pytest.raises(ValueError, match="source manifest identity mismatch"):
        compile_manifest_records([body_mutation], manifest_schema=_schema())

    with pytest.raises(ValueError, match="duplicate global manifest_id"):
        compile_manifest_records([first[0], deepcopy(first[0])], manifest_schema=_schema())

    second = _bundle(
        "0000000002-26-000001", "S-3",
        accepted_at="2026-08-01T11:00:00Z", first_seen_at="2026-08-01T11:00:03Z",
    )
    second[0]["manifest_id"] = first[0]["manifest_id"]
    with pytest.raises(ValueError, match="source manifest identity mismatch"):
        compile_manifest_records(
            [first[0], second[0]], manifest_schema=_schema()
        )


def test_latest_closed_bundle_ignores_old_only_child_documents():
    accession = "0000000001-26-000001"
    first = _bundle(
        accession, "S-3", accepted_at="2026-08-01T10:00:00Z",
        first_seen_at="2026-08-01T10:00:03Z", content_marker="v1",
    )
    stale_exhibit = _manifest(
        accession, "S-3", accepted_at="2026-08-01T10:00:00Z",
        first_seen_at="2026-08-01T10:00:03Z", document_role="exhibit",
        parent_manifest_id=first[0]["manifest_id"], content_marker="stale-exhibit",
    )
    stale_exhibit["source_id"] = f"{accession}:9:removed-exhibit.htm"
    stale_exhibit["document"] = {
        **stale_exhibit["document"],
        "document_name": "removed-exhibit.htm",
        "document_role": "exhibit",
        "sequence": "9",
    }
    _resign_manifest(stale_exhibit)
    second = _bundle(
        accession, "S-3", accepted_at="2026-08-01T10:00:00Z",
        first_seen_at="2026-08-02T10:00:03Z", content_marker="v2",
    )
    _set_bundle_version(second, 2)

    result = compile_manifest_records(
        [*first, stale_exhibit, *second], manifest_schema=_schema()
    )

    assert result["telemetry"]["counts"]["compile_failures"] == 0
    assert set(result["events"][0]["source"]["manifest_ids"]) == {
        row["manifest_id"] for row in second
    }


@pytest.mark.parametrize(("bundle_mutator", "expected_state"), [
    (lambda rows: rows[:1], "deferred_missing_document"),
    (
        lambda rows: [rows[0], {**rows[1], "parser": {**rows[1]["parser"], "eligibility": "deferred"}}],
        "deferred_unsupported_media",
    ),
    (
        lambda rows: [rows[0], {**rows[1], "parser": {**rows[1]["parser"], "corruption_state": "suspect"}}],
        "deferred_conflict",
    ),
    (
        lambda rows: [
            {**rows[0], "parser": {**rows[0]["parser"], "corruption_state": "suspect"}},
            rows[1],
        ],
        "deferred_conflict",
    ),
])
def test_missing_or_unreadable_primary_is_explicitly_deferred(bundle_mutator, expected_state):
    bundle = _bundle(
        "0000000001-26-000001", "S-3",
        accepted_at="2026-08-01T10:00:00Z", first_seen_at="2026-08-01T10:00:03Z",
    )
    result = compile_manifest_records(
        _resign_bundle(bundle_mutator(bundle)), manifest_schema=_schema()
    )
    assert result["events"][0]["classification"]["state"] == expected_state
    assert result["review_queue"][0]["classification_state"] == expected_state


def test_changed_evidence_emits_correction_at_produced_time_then_reruns_idempotently():
    first_bundle = _bundle(
        "0000000001-26-000001", "S-3",
        accepted_at="2026-08-01T10:00:00Z", first_seen_at="2026-08-01T10:00:03Z",
        content_marker="v1",
    )
    first = compile_manifest_records(
        first_bundle, manifest_schema=_schema(), generated_at="2026-08-01T12:00:00Z"
    )
    changed_bundle = _bundle(
        "0000000001-26-000001", "S-3",
        accepted_at="2026-08-01T10:00:00Z", first_seen_at="2026-08-01T10:00:03Z",
        content_marker="v2",
    )
    _set_bundle_version(changed_bundle, 2)
    manifest_ledger = [*first_bundle, *changed_bundle]
    corrected = compile_manifest_records(
        manifest_ledger,
        existing_events=first["events"],
        manifest_schema=_schema(),
        generated_at="2026-08-03T12:00:00Z",
    )
    assert len(corrected["events"]) == 2
    original, correction = corrected["events"]
    assert correction["version"] == {
        "immutable_record": True,
        "correction_version": 2,
        "correction_of": original["event_id"],
        "identity_format": 2,
    }
    assert correction["point_in_time"]["available_at"] == "2026-08-03T12:00:00Z"
    assert any(edge["relationship"] == "supersedes" for edge in corrected["edges"])

    replay = compile_manifest_records(
        manifest_ledger,
        existing_events=corrected["events"],
        existing_edges=corrected["edges"],
        manifest_schema=_schema(),
        generated_at="2026-08-04T12:00:00Z",
    )
    assert [event["event_id"] for event in replay["events"]] == [
        event["event_id"] for event in corrected["events"]
    ]
    assert replay["telemetry"]["counts"]["new_event_versions"] == 0


def test_existing_event_ledger_rejects_null_json_instead_of_overwriting_history(tmp_path):
    records = _bundle(
        "0000000001-26-000001", "S-3",
        accepted_at="2026-08-01T10:00:00Z", first_seen_at="2026-08-01T10:00:03Z",
    )
    _write_ledger(source_ledger_path(tmp_path), records)
    compile_from_disk(root=tmp_path, generated_at="2026-08-01T12:00:00Z")
    frame = pd.read_parquet(tmp_path / "event_versions.parquet")
    assert frame.columns.tolist() == EVENT_COLUMNS
    frame.loc[0, "event_json"] = None
    with pytest.raises(ValueError, match="null/non-string event_json"):
        _load_existing_events(frame)


def test_generation_receipt_rejects_tampered_or_partial_prior_artifacts(tmp_path):
    records = _bundle(
        "0000000001-26-000001", "S-3",
        accepted_at="2026-08-01T10:00:00Z", first_seen_at="2026-08-01T10:00:03Z",
    )
    _write_ledger(source_ledger_path(tmp_path), records)
    compile_from_disk(root=tmp_path, generated_at="2026-08-01T12:00:00Z")
    event_path = tmp_path / "event_versions.parquet"
    event_path.write_bytes(event_path.read_bytes() + b"tamper")

    with pytest.raises(ValueError, match="generation receipt hash mismatch"):
        compile_from_disk(root=tmp_path, generated_at="2026-08-02T12:00:00Z")

    event_path.unlink()
    with pytest.raises(ValueError, match="committed generation is incomplete"):
        compile_from_disk(root=tmp_path, generated_at="2026-08-02T12:00:00Z")


def test_ok_marker_with_all_artifacts_deleted_is_not_treated_as_virgin(tmp_path):
    records = _bundle(
        "0000000001-26-000001", "S-3",
        accepted_at="2026-08-01T10:00:00Z", first_seen_at="2026-08-01T10:00:03Z",
    )
    _write_ledger(source_ledger_path(tmp_path), records)
    compile_from_disk(root=tmp_path, generated_at="2026-08-01T12:00:00Z")
    for name in ("event_versions.parquet", "event_edges.parquet", "review_queue.parquet"):
        (tmp_path / name).unlink()

    with pytest.raises(ValueError, match="claims a generation but all artifacts are missing"):
        compile_from_disk(root=tmp_path, generated_at="2026-08-02T12:00:00Z")


def test_accession_failure_blocks_partial_publish_and_preserves_prior_generation(tmp_path):
    good = _bundle(
        "0000000001-26-000001", "S-3",
        accepted_at="2026-08-01T10:00:00Z", first_seen_at="2026-08-01T10:00:03Z",
    )
    source_path = source_ledger_path(tmp_path)
    _write_ledger(source_path, good)
    compile_from_disk(root=tmp_path, generated_at="2026-08-01T12:00:00Z")
    artifact_names = (
        "event_versions.parquet", "event_edges.parquet", "review_queue.parquet", "telemetry.json",
    )
    before = {name: (tmp_path / name).read_bytes() for name in artifact_names}

    bad = _bundle(
        "0000000001-26-000002", "S-3",
        accepted_at="2026-08-02T10:00:00Z", first_seen_at="2026-08-02T10:00:03Z",
    )
    bad[1]["parser"]["eligibility"] = "not-a-valid-state"
    _resign_bundle(bad)
    _write_ledger(source_path, [*good, *bad])

    with pytest.raises(CapitalStructureCompileDegraded) as exc_info:
        compile_from_disk(root=tmp_path, generated_at="2026-08-02T12:00:00Z")
    assert exc_info.value.telemetry["status"] == "degraded"
    assert exc_info.value.telemetry["counts"]["compile_failures"] == 1
    assert {name: (tmp_path / name).read_bytes() for name in artifact_names} == before


def test_empty_source_manifest_cannot_orphan_persisted_event_lineage(tmp_path):
    records = _bundle(
        "0000000001-26-000001", "S-3",
        accepted_at="2026-08-01T10:00:00Z", first_seen_at="2026-08-01T10:00:03Z",
    )
    source_path = source_ledger_path(tmp_path)
    _write_ledger(source_path, records)
    compile_from_disk(root=tmp_path, generated_at="2026-08-01T12:00:00Z")
    artifact_names = (
        "event_versions.parquet", "event_edges.parquet", "review_queue.parquet", "telemetry.json",
    )
    before = {name: (tmp_path / name).read_bytes() for name in artifact_names}

    _write_ledger(source_path, [])
    with pytest.raises(ValueError, match="source ledger truncated below committed prefix"):
        compile_from_disk(root=tmp_path, generated_at="2026-08-02T12:00:00Z")

    assert {name: (tmp_path / name).read_bytes() for name in artifact_names} == before


@pytest.mark.parametrize("mutation", ["body", "reorder"])
def test_source_receipt_rejects_mutation_or_reorder_inside_committed_prefix(
    tmp_path, mutation,
):
    records = _bundle(
        "0000000001-26-000001", "S-3",
        accepted_at="2026-08-01T10:00:00Z", first_seen_at="2026-08-01T10:00:03Z",
    )
    source_path = source_ledger_path(tmp_path)
    _write_ledger(source_path, records)
    compile_from_disk(root=tmp_path, generated_at="2026-08-01T12:00:00Z")

    changed = deepcopy(records)
    if mutation == "body":
        changed[0]["issuer"]["ticker"] = "MUT"
        _resign_bundle(changed)
    else:
        changed.reverse()
    _write_ledger(source_path, changed)

    with pytest.raises(ValueError, match="mutated or reordered inside committed prefix"):
        compile_from_disk(root=tmp_path, generated_at="2026-08-02T12:00:00Z")


def test_new_bundle_schema_growth_cannot_invalidate_retained_manifests(tmp_path):
    """Reproduces the nightly failure first seen 2026-08-05, end to end.

    The retained rows predate ``filing.file_number_provenance``; the appended
    bundle carries it.  Under the old parquet ledger, pyarrow back-filled that
    nested key as null into every retained row, so their stored manifest IDs no
    longer matched their bodies and this compile raised ManifestIdentityError --
    discarding the whole night's collection.
    """
    retained = _bundle(
        "0000000001-26-000001", "S-3",
        accepted_at="2026-08-01T10:00:00Z", first_seen_at="2026-08-01T10:00:03Z",
        include_file_number_provenance=False,
    )
    source_path = source_ledger_path(tmp_path)
    _write_ledger(source_path, retained)
    first = compile_from_disk(root=tmp_path, generated_at="2026-08-01T12:00:00Z")
    assert first["status"] == "ok"

    grown = _bundle(
        "0000000002-26-000001", "S-3",
        accepted_at="2026-08-02T10:00:00Z", first_seen_at="2026-08-02T10:00:03Z",
        include_file_number_provenance=True,
    )
    assert "file_number_provenance" not in retained[0]["filing"]
    assert "file_number_provenance" in grown[0]["filing"]
    _write_ledger(source_path, [*retained, *grown])

    second = compile_from_disk(root=tmp_path, generated_at="2026-08-02T12:00:00Z")
    assert second["status"] == "ok"
    assert second["events"] == 2
    # The retained prefix is still readable as the IDs it was written with.
    assert read_source_ledger(source_path)[0] == retained[0]


def test_prior_policy_receipt_can_migrate_via_valid_append_and_new_generation(tmp_path):
    first = _bundle(
        "0000000001-26-000001", "S-3",
        accepted_at="2026-08-01T10:00:00Z", first_seen_at="2026-08-01T10:00:03Z",
    )
    source_path = source_ledger_path(tmp_path)
    _write_ledger(source_path, first)
    compile_from_disk(root=tmp_path, generated_at="2026-08-01T12:00:00Z")

    telemetry_path = tmp_path / "telemetry.json"
    prior = json.loads(telemetry_path.read_text())
    prior["source_ledger_receipt"]["form_policy_version"] = "retired-policy/0.9"
    prior["form_policy"]["policy_version"] = "retired-policy/0.9"
    prior["generation_id"] = _generation_id(
        as_of=prior["as_of"],
        artifact_hashes=prior["artifact_hashes"],
        source_ledger_receipt=prior["source_ledger_receipt"],
    )
    telemetry_path.write_text(json.dumps(prior, indent=2, sort_keys=True) + "\n")

    appended = _bundle(
        "0000000002-26-000001", "S-3",
        accepted_at="2026-08-02T10:00:00Z", first_seen_at="2026-08-02T10:00:03Z",
    )
    _write_ledger(source_path, [*first, *appended])
    summary = compile_from_disk(root=tmp_path, generated_at="2026-08-02T12:00:00Z")
    current = json.loads(telemetry_path.read_text())

    assert summary["status"] == "ok"
    assert summary["events"] == 2
    assert current["source_ledger_receipt"]["form_policy_version"] == FORM_POLICY[
        "policy_version"
    ]


def test_missing_source_manifest_cannot_replace_verified_prior_generation(tmp_path):
    records = _bundle(
        "0000000001-26-000001", "S-3",
        accepted_at="2026-08-01T10:00:00Z", first_seen_at="2026-08-01T10:00:03Z",
    )
    source_path = source_ledger_path(tmp_path)
    _write_ledger(source_path, records)
    compile_from_disk(root=tmp_path, generated_at="2026-08-01T12:00:00Z")
    before = (tmp_path / "telemetry.json").read_bytes()
    source_path.unlink()

    with pytest.raises(ValueError, match="source ledger truncated below committed prefix"):
        compile_from_disk(root=tmp_path, generated_at="2026-08-02T12:00:00Z")
    assert (tmp_path / "telemetry.json").read_bytes() == before


def test_no_source_run_emits_strict_zero_telemetry(tmp_path):
    summary = compile_from_disk(root=tmp_path, generated_at="2026-08-01T12:00:00Z")
    telemetry = json.loads((tmp_path / "telemetry.json").read_text())
    assert summary["status"] == "no_source_manifest"
    assert telemetry["status"] == "no_source_manifest"
    assert telemetry["generation_id"] is None
    assert telemetry["counts"] == {
        "source_manifests": 0,
        "accessions_grouped": 0,
        "event_versions": 0,
        "new_event_versions": 0,
        "event_edges": 0,
        "review_queue": 0,
        "compile_failures": 0,
    }
    assert telemetry["migration_receipt"]["immutable_record"] is True
    assert telemetry["source_ledger_receipt"]["record_count"] == 0


def test_existing_valid_empty_source_manifest_is_no_source_not_green_generation(tmp_path):
    _write_ledger(source_ledger_path(tmp_path), [])

    summary = compile_from_disk(root=tmp_path, generated_at="2026-08-01T12:00:00Z")
    telemetry = json.loads((tmp_path / "telemetry.json").read_text())

    assert summary["status"] == "no_source_manifest"
    assert telemetry["status"] == "no_source_manifest"
    assert telemetry["source_ledger_receipt"]["record_count"] == 0
    assert not (tmp_path / "event_versions.parquet").exists()


def test_generation_receipt_hashes_artifacts_and_failed_promotion_rolls_back(tmp_path, monkeypatch):
    records = _bundle(
        "0000000001-26-000001", "S-3",
        accepted_at="2026-08-01T10:00:00Z", first_seen_at="2026-08-01T10:00:03Z",
        content_marker="v1",
    )
    source_path = source_ledger_path(tmp_path)
    _write_ledger(source_path, records)
    compile_from_disk(root=tmp_path, generated_at="2026-08-01T12:00:00Z")
    artifact_names = [
        "event_versions.parquet", "event_edges.parquet", "review_queue.parquet", "telemetry.json",
    ]
    before = {name: (tmp_path / name).read_bytes() for name in artifact_names}
    receipt = json.loads(before["telemetry.json"])
    for key, filename in {
        "event_versions": "event_versions.parquet",
        "event_edges": "event_edges.parquet",
        "review_queue": "review_queue.parquet",
    }.items():
        assert receipt["artifact_hashes"][key] == sha256(before[filename]).hexdigest()

    changed = _bundle(
        "0000000001-26-000001", "S-3",
        accepted_at="2026-08-01T10:00:00Z", first_seen_at="2026-08-01T10:00:03Z",
        content_marker="v2",
    )
    _set_bundle_version(changed, 2)
    _write_ledger(source_path, [*records, *changed])
    from scripts import compile_capital_structure_events as compiler

    real_replace = compiler.os.replace
    failed = False

    def fail_commit_marker(source, target):
        nonlocal failed
        if Path(target) == tmp_path / "telemetry.json" and not failed:
            failed = True
            raise OSError("injected telemetry promotion failure")
        return real_replace(source, target)

    monkeypatch.setattr(compiler.os, "replace", fail_commit_marker)
    with pytest.raises(OSError, match="injected telemetry"):
        compile_from_disk(root=tmp_path, generated_at="2026-08-02T12:00:00Z")
    assert {name: (tmp_path / name).read_bytes() for name in artifact_names} == before
    assert not list(tmp_path.glob("*.tmp*"))


def test_nightly_order_and_render_network_firewall_are_pinned():
    """A capital-structure integrity failure blocks ITS OWN checkpoint — and no other.

    RESTATED 2026-08-06 TWICE, first for the checkpoint split and then for the
    JOB split.  This pin originally read `collect < compile < commit` with
    `commit` found by `name.startswith("commit data")`.  That was one checkpoint,
    and this compiler sat upstream of it, which is exactly what let a
    capital-structure defect hold the night's market collection on the runner:
    six consecutive nights from 2026-08-01 through four unrelated causes (#4534
    duck-typing, runner ENOSPC, #4600 ledger identity, #4640 SEC grammar),
    `data/stocks` frozen at 2026-07-31.

    The invariant now has two halves and BOTH must hold:

      1. `run collectors` -> "commit market data" -> "push market data" all
         happen in the `collect` job, and this compiler runs in a DIFFERENT job
         that `needs:` it.  The market plane is committed and published before
         this lane can start at all; nothing it does — failing, hanging, or
         spending its job's whole budget — can reach it.
      2. this compiler -> "commit capital-structure data", inside that job.  The
         compiler is still upstream of its OWN checkpoint and still carries no
         `continue-on-error`, so an integrity failure still blocks publication of
         a partial event generation.  (#4578 added continue-on-error here;
         correctly reverted.)

    Half 1 is asserted through `needs:`, NOT through a position in a flattened
    list of every job's steps.  That distinction is the whole point after the job
    split: a flattened index across jobs is just YAML declaration order, which
    guarantees nothing about execution and would keep this test green if the
    compiler were moved into a job that runs CONCURRENTLY with `collect`.  Only
    the dependency edge orders two jobs.

    Half 2 alone is the old assertion and is NOT sufficient: naming the second
    checkpoint "commit data ..." would satisfy it verbatim while restoring the
    very coupling the split removed.  So the market checkpoint is asserted by its
    own name, in its own job, and no step anywhere may be named "commit data" any
    more.  Both sides are guarded from the other direction by
    tests/test_daily_collect_commit_path.py and
    tests/test_daily_capital_structure_job.py.

    The steps are located STRUCTURALLY — their own parsed step dicts — never by
    slicing the file text between two step names. The old slice ran from
    "- name: compile capital-structure" to "- name: refresh Finviz themes", so
    it only held while those two steps stayed adjacent: on 2026-08-01 #4013
    inserted an audit step (legitimately `continue-on-error: true`) between
    them, the slice swallowed it, and this test failed while its own subject
    was untouched and still correct. A sibling's continue-on-error can neither
    break nor satisfy the pin below.
    """
    import yaml

    daily = (ROOT / ".github/workflows/daily.yml").read_text()
    jobs = yaml.safe_load(daily)["jobs"]
    compile_call = "python -m scripts.compile_capital_structure_events"

    def _locate(predicate, label):
        """Return (job_name, step_index) for the single step matching predicate."""
        hits = [
            (job_name, i)
            for job_name, job in jobs.items()
            for i, step in enumerate(job.get("steps") or [])
            if predicate(step)
        ]
        assert len(hits) == 1, f"expected exactly one {label} step, got {hits}"
        return hits[0]

    def _named(prefix):
        return _locate(
            lambda s: str(s.get("name") or "").startswith(prefix), repr(prefix)
        )

    collect_job, collect_at = _locate(
        lambda s: "python -m scripts.collect " in str(s.get("run") or ""), "collectors"
    )
    market_commit_job, market_commit_at = _named("commit market data")
    market_push_job, market_push_at = _named("push market data")
    compile_job, compile_at = _locate(
        lambda s: compile_call in str(s.get("run") or ""), "event-spine compile"
    )
    cs_commit_job, cs_commit_at = _named("commit capital-structure data")

    # Half 1a — the market checkpoint is complete inside the collectors' own job.
    assert collect_job == market_commit_job == market_push_job, (
        "the collectors and the market checkpoint must stay in one job "
        f"(collectors in {collect_job!r}, commit in {market_commit_job!r}, push in "
        f"{market_push_job!r}); otherwise the collected bytes cross a job boundary "
        "before anything has committed them"
    )
    assert collect_at < market_commit_at < market_push_at, (
        f"in {collect_job!r} the order must be collectors -> commit -> push "
        f"(got {collect_at}, {market_commit_at}, {market_push_at})"
    )

    # Half 1b — the compiler runs in a LATER job, ordered by `needs:`, not by
    # where its YAML happens to sit.
    assert compile_job != collect_job, (
        f"the capital-structure compiler is back inside {collect_job!r}. It is "
        "fatal by design, so it would again red the one job the whole nightly "
        "hangs off — three consecutive lost nights (#4600, #4640, #4740)."
    )
    compile_needs = jobs[compile_job].get("needs") or []
    if isinstance(compile_needs, str):
        compile_needs = [compile_needs]
    assert collect_job in compile_needs, (
        f"job {compile_job!r} runs the capital-structure compiler but does not "
        f"`needs: {collect_job}` (needs={compile_needs!r}). Without that edge the "
        "two jobs may run CONCURRENTLY and the compiler is no longer downstream "
        "of the market checkpoint at all — it would merely be declared later in "
        "the file, which orders nothing."
    )

    # Half 2 — the compiler still gates its own generation, fatally, in its job.
    assert compile_job == cs_commit_job, (
        f"the compiler runs in {compile_job!r} but its checkpoint is in "
        f"{cs_commit_job!r}; a step outcome cannot gate a commit in another job"
    )
    assert compile_at < cs_commit_at, (
        "the capital-structure compiler must still run BEFORE the checkpoint that "
        "publishes its generation, or a rejected ledger could be committed"
    )
    compile_step = jobs[compile_job]["steps"][compile_at]
    assert "continue-on-error" not in compile_step, (
        "the compile step must stay fatal for its own checkpoint (#4578)"
    )
    # The second checkpoint must not impersonate the first.
    all_names = [
        str(step.get("name") or "")
        for job in jobs.values()
        for step in (job.get("steps") or [])
    ]
    assert not [n for n in all_names if n.startswith("commit data")], (
        "a step is named 'commit data ...' again. The two checkpoints are 'commit "
        "market data' and 'commit capital-structure data'; a step reusing the old "
        "name would satisfy this pin's previous form while re-coupling the market "
        "plane to the capital-structure lane."
    )

    assert "R2_BUCKET: ${{ secrets.R2_BUCKET }}" in daily
    assert (
        "R2_CAPITAL_STRUCTURE_BUCKET: ${{ secrets.R2_CAPITAL_STRUCTURE_BUCKET }}"
        in daily
    )
    assert compile_call not in (ROOT / ".github/workflows/render.yml").read_text()
    assert compile_call not in (ROOT / ".github/workflows/engine-render.yml").read_text()


def test_collector_is_registered_in_serial_sec_host_group():
    from scripts.collect import _CONCURRENT_HOSTS, _SLOW, all_adapters

    assert _CONCURRENT_HOSTS["sec_capital_structure"] == "sec"
    assert "sec_capital_structure" in _SLOW
    assert "sec_capital_structure" in all_adapters()
