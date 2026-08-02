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
    queued_forms = {row["form"] for row in result["review_queue"]}
    assert "S-3/A" not in queued_forms
    assert queued_forms == {"424B5"}
    assert result["telemetry"]["authority"]["prophet_authority"] is False


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
    pd.DataFrame(records).to_parquet(tmp_path / "source_manifest.parquet", index=False)

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
    pd.DataFrame(records).to_parquet(tmp_path / "source_manifest.parquet", index=False)
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
    pd.DataFrame(records).to_parquet(tmp_path / "source_manifest.parquet", index=False)
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
    pd.DataFrame(records).to_parquet(tmp_path / "source_manifest.parquet", index=False)
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
    source_path = tmp_path / "source_manifest.parquet"
    pd.DataFrame(good).to_parquet(source_path, index=False)
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
    pd.DataFrame([*good, *bad]).to_parquet(source_path, index=False)

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
    source_path = tmp_path / "source_manifest.parquet"
    source_frame = pd.DataFrame(records)
    source_frame.to_parquet(source_path, index=False)
    compile_from_disk(root=tmp_path, generated_at="2026-08-01T12:00:00Z")
    artifact_names = (
        "event_versions.parquet", "event_edges.parquet", "review_queue.parquet", "telemetry.json",
    )
    before = {name: (tmp_path / name).read_bytes() for name in artifact_names}

    source_frame.iloc[0:0].to_parquet(source_path, index=False)
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
    source_path = tmp_path / "source_manifest.parquet"
    pd.DataFrame(records).to_parquet(source_path, index=False)
    compile_from_disk(root=tmp_path, generated_at="2026-08-01T12:00:00Z")

    changed = deepcopy(records)
    if mutation == "body":
        changed[0]["issuer"]["ticker"] = "MUT"
        _resign_bundle(changed)
    else:
        changed.reverse()
    pd.DataFrame(changed).to_parquet(source_path, index=False)

    with pytest.raises(ValueError, match="mutated or reordered inside committed prefix"):
        compile_from_disk(root=tmp_path, generated_at="2026-08-02T12:00:00Z")


def test_prior_policy_receipt_can_migrate_via_valid_append_and_new_generation(tmp_path):
    first = _bundle(
        "0000000001-26-000001", "S-3",
        accepted_at="2026-08-01T10:00:00Z", first_seen_at="2026-08-01T10:00:03Z",
    )
    source_path = tmp_path / "source_manifest.parquet"
    pd.DataFrame(first).to_parquet(source_path, index=False)
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
    pd.DataFrame([*first, *appended]).to_parquet(source_path, index=False)
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
    source_path = tmp_path / "source_manifest.parquet"
    pd.DataFrame(records).to_parquet(source_path, index=False)
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
    template = pd.DataFrame(_bundle(
        "0000000001-26-000001", "S-3",
        accepted_at="2026-08-01T10:00:00Z", first_seen_at="2026-08-01T10:00:03Z",
    ))
    template.iloc[0:0].to_parquet(tmp_path / "source_manifest.parquet", index=False)

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
    source_path = tmp_path / "source_manifest.parquet"
    pd.DataFrame(records).to_parquet(source_path, index=False)
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
    pd.DataFrame([*records, *changed]).to_parquet(source_path, index=False)
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
    """A capital-structure integrity failure must BLOCK the nightly checkpoint.

    The step is located STRUCTURALLY — its own parsed step dict — never by
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
    compile_call = "python -m scripts.compile_capital_structure_events"
    steps = [
        step
        for job in yaml.safe_load(daily)["jobs"].values()
        for step in (job.get("steps") or [])
    ]
    runs = [str(step.get("run") or "") for step in steps]
    collect_at = next(
        i for i, run in enumerate(runs) if "python -m scripts.collect " in run
    )
    compile_at = next(i for i, run in enumerate(runs) if compile_call in run)
    commit_at = next(
        i for i, step in enumerate(steps)
        if str(step.get("name") or "").startswith("commit data")
    )
    assert collect_at < compile_at
    assert compile_at < commit_at
    assert "continue-on-error" not in steps[compile_at]
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
