"""W1B: accession-wide closed-manifest-bundle persistence.

Hostile end-to-end coverage, not classifier-only:
- complete unchanged + primary changes → whole N+1 bundle
- complete changes + children unchanged → whole N+1 bundle
- new child selected → whole N+1 bundle
- previously current exhibit deselected → whole candidate N+1, no exhibit N+1
- one exhibit changes → whole N+1 bundle
- all unchanged → zero manifests + one verified re-observation
- N+1 children reference the N+1 complete manifest
- unchanged members keep the same evidence_id
- reminted unchanged members do not mint duplicate economic events
- historical v1 legacy:{source_id} → later coordinate identity is not a
  false capital-change event; the historical row is not rewritten
"""
from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

import collectors.sec_capital_structure as sec
from collectors.sec_capital_structure import (
    SecCapitalStructureAdapter,
)
from engine.capital_structure.source_identity import (
    child_occurrence,
    classify_bundle_against_published,
    current_manifest_bundle,
    evidence_id_for,
    evidence_id_from_manifest,
    evidence_occurrence_from_manifest,
    manifest_id_for,
    refine_evidence_ids_for_semantic_compare,
)
from engine.capital_structure.source_ledger_io import (
    read_source_ledger,
    source_ledger_path,
)
from engine.capital_structure.source_store import (
    ContentAddressedSourceStore,
    LocalStore,
)
from scripts.compile_capital_structure_events import compile_manifest_records


ROOT = Path(__file__).resolve().parents[1]
ACCESSION = "0001234567-26-000001"

SINGLE_INDEX = """\
Form Type                            Company Name                              CIK         Date Filed  Filename
-------------------------------------------------------------------------------------------------------------------------------------------
S-3                                  ACME CORP                                 1234567     20260731    edgar/data/1234567/0001234567-26-000001.txt
"""

SUBMISSION = b"""\
<SEC-DOCUMENT>0001234567-26-000001.txt
<ACCEPTANCE-DATETIME>20260801123456
<FILE-NUMBER>333-123456
<DOCUMENT>
<TYPE>S-3
<SEQUENCE>1
<FILENAME>forms3.htm
<DESCRIPTION>REGISTRATION STATEMENT
<TEXT><html><body>Registration statement.</body></html></TEXT>
</DOCUMENT>
<DOCUMENT>
<TYPE>EX-10.1
<SEQUENCE>2
<FILENAME>purchase.htm
<DESCRIPTION>PURCHASE AGREEMENT
<TEXT><html><body>Purchase agreement.</body></html></TEXT>
</DOCUMENT>
<DOCUMENT>
<TYPE>GRAPHIC
<SEQUENCE>3
<FILENAME>logo.jpg
<TEXT>binary-placeholder</TEXT>
</DOCUMENT>
"""


class OneFilingAdapter(SecCapitalStructureAdapter):
    def _fetch_index(self, value, ua):
        return SINGLE_INDEX

    def _fetch_submission(self, url, ua):
        return SUBMISSION


def _clock(at: datetime):
    return {"now": at}


def _now_fn(clock: dict):
    def _now():
        return clock["now"]
    return _now


def _wire_collector(tmp_path, monkeypatch, clock: dict):
    monkeypatch.setattr(sec, "_data_dir", lambda: tmp_path / "capital_structure")
    monkeypatch.setattr(sec, "_cik_map", lambda: {1234567: "ACME"})
    monkeypatch.setattr(sec, "_ua", lambda: "test@example.com")
    monkeypatch.setattr(sec, "PACE_SECONDS", 0)
    monkeypatch.setattr(
        sec, "due_index_dates", lambda *args, **kwargs: [date(2026, 7, 31)]
    )
    store = ContentAddressedSourceStore(
        LocalStore(tmp_path / "objects"), backend="local"
    )
    adapter = OneFilingAdapter(
        source_store=store,
        now_fn=_now_fn(clock),
        max_filings_per_run=1,
    )
    adapter.latest_filings_enabled = False
    return adapter, tmp_path / "capital_structure"


def _force_requeue(monkeypatch) -> None:
    monkeypatch.setattr(sec, "_eligible_complete_accessions", lambda manifests: set())


def _bump_parser_version(monkeypatch, role: str) -> None:
    real = sec.inspect_source_document

    def _inspect(raw, filename="", document_role=""):
        result = real(raw, filename=filename, document_role=document_role)
        if document_role == role:
            return replace(result, parser_version="sec-source-inspector/1.1.0")
        return result

    monkeypatch.setattr(sec, "inspect_source_document", _inspect)


def _select_extra_child(monkeypatch) -> None:
    real = sec.select_relevant_documents

    def _select(form, documents):
        selected = list(real(form, documents))
        taken = {id(doc) for _, doc in selected}
        for doc in documents:
            if id(doc) not in taken:
                selected.append(("exhibit", doc))
                break
        return selected

    monkeypatch.setattr(sec, "select_relevant_documents", _select)


def _deselect_exhibits(monkeypatch) -> None:
    real = sec.select_relevant_documents

    def _select(form, documents):
        return [
            (role, doc)
            for role, doc in real(form, documents)
            if role != "exhibit"
        ]

    monkeypatch.setattr(sec, "select_relevant_documents", _select)


def _spy_bundle_decisions(monkeypatch) -> list[dict[str, Any]]:
    seen: list[dict[str, Any]] = []
    real = sec.classify_bundle_against_published

    def _classify(candidates, published):
        decision = real(candidates, published)
        seen.append(decision)
        return decision

    monkeypatch.setattr(sec, "classify_bundle_against_published", _classify)
    return seen


def _ledger(root: Path) -> list[dict]:
    return list(read_source_ledger(source_ledger_path(root)))


def _by_version(records: list[dict], version: int) -> list[dict]:
    return [
        row for row in records
        if int((row.get("document") or {}).get("document_version") or 0) == version
    ]


def _assert_closed_bundle(records: list[dict], version: int) -> tuple[dict, list[dict]]:
    bundle = _by_version(records, version)
    complete = [
        row for row in bundle
        if (row.get("document") or {}).get("document_role") == "complete_submission"
    ]
    children = [
        row for row in bundle
        if (row.get("document") or {}).get("document_role") != "complete_submission"
    ]
    assert len(complete) == 1, f"version {version} must have exactly one complete"
    assert children, f"version {version} must retain children"
    parent = complete[0]["manifest_id"]
    assert {row["document"]["parent_manifest_id"] for row in children} == {parent}
    roles = sorted(
        str((row.get("document") or {}).get("document_role")) for row in bundle
    )
    assert "complete_submission" in roles
    return complete[0], children


def _compile(records: list[dict], *, existing=(), generated_at: str):
    result = compile_manifest_records(
        records,
        existing_events=existing,
        existing_edges=[],
        generated_at=generated_at,
    )
    assert result["telemetry"]["counts"]["compile_failures"] == 0, result["telemetry"]
    return result


def _first_fetch(tmp_path, monkeypatch):
    clock = _clock(datetime(2026, 8, 1, 13, 0, tzinfo=timezone.utc))
    adapter, root = _wire_collector(tmp_path, monkeypatch, clock)
    adapter.fetch()
    records = _ledger(root)
    v1 = _by_version(records, 1)
    assert v1
    _assert_closed_bundle(records, 1)
    return adapter, root, clock, records


def _second_fetch(adapter, clock: dict, monkeypatch) -> None:
    clock["now"] = datetime(2026, 8, 2, 15, 30, tzinfo=timezone.utc)
    _force_requeue(monkeypatch)
    adapter.fetch()


def _assert_unchanged_evidence_ids(v1: list[dict], v2: list[dict]) -> None:
    v1_ids = {row["evidence_id"]: row for row in v1}
    for row in v2:
        eid = row["evidence_id"]
        if eid in v1_ids:
            assert eid == v1_ids[eid]["evidence_id"]


def _assert_no_duplicate_event(prior_events: list[dict], merged_result: dict) -> None:
    prior_ids = [event["event_id"] for event in prior_events]
    merged_ids = [event["event_id"] for event in merged_result["events"]]
    assert prior_ids, "prior compile must have produced an event"
    assert merged_ids[: len(prior_ids)] == prior_ids
    extra = merged_ids[len(prior_ids):]
    assert extra == [], f"unchanged economics minted extra events: {extra}"


# ─────────────────────────────────────────────────────────────────────────────
# Collector E2E
# ─────────────────────────────────────────────────────────────────────────────


def test_complete_unchanged_primary_change_persists_whole_n1_bundle(
    tmp_path, monkeypatch,
):
    adapter, root, clock, first_records = _first_fetch(tmp_path, monkeypatch)
    prior = _compile(first_records, generated_at="2026-08-01T16:00:00Z")
    _bump_parser_version(monkeypatch, "primary")
    _second_fetch(adapter, clock, monkeypatch)

    records = _ledger(root)
    v1, v2 = _by_version(records, 1), _by_version(records, 2)
    complete, children = _assert_closed_bundle(records, 2)
    assert len(v2) == len(v1)
    assert {row["document"]["document_role"] for row in v2} == {
        row["document"]["document_role"] for row in v1
    }
    _assert_unchanged_evidence_ids(v1, v2)
    primary = next(
        row for row in children if row["document"]["document_role"] == "primary"
    )
    assert primary["parser"]["parser_version"] == "sec-source-inspector/1.1.0"
    unchanged_complete = next(
        row for row in v2 if row["document"]["document_role"] == "complete_submission"
    )
    assert unchanged_complete["parser"]["parser_version"] != primary["parser"]["parser_version"]
    assert complete["manifest_id"] == unchanged_complete["manifest_id"]

    merged = _compile(
        records, existing=prior["events"], generated_at="2026-08-02T16:00:00Z",
    )
    _assert_no_duplicate_event(prior["events"], merged)


def test_complete_changes_children_unchanged_persists_whole_n1_bundle(
    tmp_path, monkeypatch,
):
    adapter, root, clock, first_records = _first_fetch(tmp_path, monkeypatch)
    prior = _compile(first_records, generated_at="2026-08-01T16:00:00Z")
    _bump_parser_version(monkeypatch, "complete_submission")
    _second_fetch(adapter, clock, monkeypatch)

    records = _ledger(root)
    v1, v2 = _by_version(records, 1), _by_version(records, 2)
    complete, children = _assert_closed_bundle(records, 2)
    assert len(v2) == len(v1)
    assert complete["parser"]["parser_version"] == "sec-source-inspector/1.1.0"
    assert all(
        row["parser"]["parser_version"] != "sec-source-inspector/1.1.0"
        for row in children
    )
    _assert_unchanged_evidence_ids(v1, v2)
    merged = _compile(
        records, existing=prior["events"], generated_at="2026-08-02T16:00:00Z",
    )
    _assert_no_duplicate_event(prior["events"], merged)


def test_new_child_selected_persists_whole_n1_bundle(tmp_path, monkeypatch):
    adapter, root, clock, first_records = _first_fetch(tmp_path, monkeypatch)
    prior = _compile(first_records, generated_at="2026-08-01T16:00:00Z")
    _select_extra_child(monkeypatch)
    _second_fetch(adapter, clock, monkeypatch)

    records = _ledger(root)
    v1, v2 = _by_version(records, 1), _by_version(records, 2)
    _assert_closed_bundle(records, 2)
    assert len(v2) == len(v1) + 1
    _assert_unchanged_evidence_ids(v1, v2)
    merged = _compile(
        records, existing=prior["events"], generated_at="2026-08-02T16:00:00Z",
    )
    assert merged["telemetry"]["counts"]["compile_failures"] == 0
    assert merged["events"][0]["event_id"] == prior["events"][0]["event_id"]
    if len(merged["events"]) > 1:
        assert merged["events"][1]["version"]["correction_of"] == merged["events"][0]["event_id"]


def test_deselected_exhibit_persists_candidate_n1_without_removed_member(
    tmp_path, monkeypatch,
):
    adapter, root, clock, first_records = _first_fetch(tmp_path, monkeypatch)
    v1 = _by_version(first_records, 1)
    v1_roles = {
        str((row.get("document") or {}).get("document_role")) for row in v1
    }
    assert v1_roles == {"complete_submission", "primary", "exhibit"}
    v1_exhibit = next(
        row for row in v1 if row["document"]["document_role"] == "exhibit"
    )
    prior = _compile(first_records, generated_at="2026-08-01T16:00:00Z")
    decisions = _spy_bundle_decisions(monkeypatch)
    _deselect_exhibits(monkeypatch)
    _second_fetch(adapter, clock, monkeypatch)

    assert decisions, "collector must classify the deselection refetch"
    decision = decisions[-1]
    assert decision["status"] == "revision"
    persist_roles = [
        str((row.get("document") or {}).get("document_role"))
        for row in decision["persist"]
    ]
    assert persist_roles == ["complete_submission", "primary"]
    assert not any(
        str((row.get("document") or {}).get("document_role")) == "exhibit"
        for row in decision["persist"]
    )
    removed_roles = {
        str((row.get("document") or {}).get("document_role"))
        for row in decision["removed"]
    }
    assert "exhibit" in removed_roles

    records = _ledger(root)
    v1_after, v2 = _by_version(records, 1), _by_version(records, 2)
    assert v1_after == v1
    complete, children = _assert_closed_bundle(records, 2)
    assert len(v2) == 2
    v2_roles = {
        str((row.get("document") or {}).get("document_role")) for row in v2
    }
    assert v2_roles == {"complete_submission", "primary"}
    assert all(row["document"]["parent_manifest_id"] == complete["manifest_id"] for row in children)
    _assert_unchanged_evidence_ids(v1, v2)
    surviving = {row["evidence_id"] for row in v2}
    assert v1_exhibit["evidence_id"] not in surviving
    assert all(
        int((row.get("document") or {}).get("document_version") or 0) == 2
        for row in v2
    )

    current = current_manifest_bundle(records, accession=ACCESSION)
    assert {
        str((row.get("document") or {}).get("document_role")) for row in current
    } == {"complete_submission", "primary"}
    assert v1_exhibit["manifest_id"] not in {row["manifest_id"] for row in current}

    merged = _compile(
        records, existing=prior["events"], generated_at="2026-08-02T16:00:00Z",
    )
    assert merged["telemetry"]["counts"]["compile_failures"] == 0
    assert merged["events"][0]["event_id"] == prior["events"][0]["event_id"]
    extra = merged["events"][len(prior["events"]):]
    if extra:
        assert extra[0]["version"]["correction_of"] == merged["events"][0]["event_id"]
        assert extra[0]["event_id"] != merged["events"][0]["event_id"]

    third_at = datetime(2026, 8, 3, 16, 0, tzinfo=timezone.utc)
    clock["now"] = third_at
    _force_requeue(monkeypatch)
    adapter.fetch()
    after_third = _ledger(root)
    assert after_third == records
    assert decisions[-1]["status"] == "re_observed"
    assert decisions[-1]["persist"] == []
    payload = json.loads((root / "ingestion_run.json").read_text())
    assert int(payload["counters"]["re_observed"]) >= 1
    third_compile = _compile(
        after_third, existing=merged["events"], generated_at="2026-08-03T16:00:00Z",
    )
    _assert_no_duplicate_event(merged["events"], third_compile)


def test_one_exhibit_change_persists_whole_n1_bundle(tmp_path, monkeypatch):
    adapter, root, clock, first_records = _first_fetch(tmp_path, monkeypatch)
    prior = _compile(first_records, generated_at="2026-08-01T16:00:00Z")
    _bump_parser_version(monkeypatch, "exhibit")
    _second_fetch(adapter, clock, monkeypatch)

    records = _ledger(root)
    v1, v2 = _by_version(records, 1), _by_version(records, 2)
    _complete, children = _assert_closed_bundle(records, 2)
    assert len(v2) == len(v1)
    exhibit = next(
        row for row in children if row["document"]["document_role"] == "exhibit"
    )
    assert exhibit["parser"]["parser_version"] == "sec-source-inspector/1.1.0"
    _assert_unchanged_evidence_ids(v1, v2)
    merged = _compile(
        records, existing=prior["events"], generated_at="2026-08-02T16:00:00Z",
    )
    _assert_no_duplicate_event(prior["events"], merged)


def test_all_unchanged_is_reobservation_with_zero_manifests(
    tmp_path, monkeypatch,
):
    adapter, root, clock, first_records = _first_fetch(tmp_path, monkeypatch)
    prior = _compile(first_records, generated_at="2026-08-01T16:00:00Z")
    _second_fetch(adapter, clock, monkeypatch)

    records = _ledger(root)
    assert _by_version(records, 2) == []
    assert len(records) == len(first_records)
    payload = json.loads((root / "ingestion_run.json").read_text())
    assert int(payload["counters"]["re_observed"]) >= 1
    merged = _compile(
        records, existing=prior["events"], generated_at="2026-08-02T16:00:00Z",
    )
    _assert_no_duplicate_event(prior["events"], merged)


def test_classifier_persist_is_whole_bundle_on_revision():
    acc = "0001234567-26-000091"
    complete = {
        "schema": "capital_structure.source_manifest/v1",
        "source_system": "sec_edgar",
        "source_id": f"{acc}:0:complete-submission.txt",
        "issuer": {"issuer_id": "sec:cik:0001234567", "cik": "1234567"},
        "filing": {
            "accession": acc, "form": "S-3", "filing_date": "2026-08-01",
            "accepted_at": "2026-08-01T10:00:00Z", "file_number": "333-1",
        },
        "document": {
            "canonical_url": "https://www.sec.gov/Archives/a.txt",
            "document_name": "complete-submission.txt", "document_type": "S-3",
            "document_role": "complete_submission", "sequence": "0",
            "media_type": "text/plain", "byte_length": 4, "document_version": 1,
            "content_sha256": "a" * 64, "parent_manifest_id": None,
            "root_locator": "sha256:" + "a" * 64,
        },
        "retrieval": {
            "retrieved_at": "2026-08-01T10:00:00Z",
            "first_seen_at": "2026-08-01T10:00:00Z",
            "transport_status": "retrieved",
        },
        "storage": {
            "backend": "r2", "store_id": "r2_shared",
            "object_key": "k", "content_addressed": True, "retention_state": "retained",
        },
        "rights": {
            "redistribution_class": "public_source_link",
            "attribution_required": True, "license_note": "SEC",
        },
        "privacy": {"classification": "public", "contains_personal_data": False},
        "parser": {
            "eligibility": "eligible", "corruption_state": "clean",
            "parser_version": "sec-source-inspector/1.0.0",
        },
        "spans": [{
            "span_id": "root:" + "a" * 64, "locator_type": "document",
            "locator": "bytes:0-4", "text_sha256": "a" * 64,
        }],
        "evidence_occurrence": "submission",
        "evidence_key_format": 1,
        "first_known_at": "2026-08-01T10:00:00Z",
    }
    complete["evidence_id"] = evidence_id_for(
        source_system="sec_edgar", submission_accession=acc,
        occurrence="submission", content_sha256="a" * 64,
    )
    complete["manifest_id"] = manifest_id_for(complete)
    child = dict(complete)
    child["source_id"] = f"{acc}:1:forms3.htm"
    child["document"] = dict(complete["document"])
    child["document"]["document_role"] = "primary"
    child["document"]["document_name"] = "forms3.htm"
    child["document"]["sequence"] = "1"
    child["document"]["parent_manifest_id"] = complete["manifest_id"]
    child["document"]["content_sha256"] = "b" * 64
    child["document"]["root_locator"] = "sha256:" + "b" * 64
    child["evidence_occurrence"] = child_occurrence(
        parent_content_sha256="a" * 64, byte_start=10, byte_end=20,
    )
    child["evidence_id"] = evidence_id_for(
        source_system="sec_edgar", submission_accession=acc,
        occurrence=child["evidence_occurrence"], content_sha256="b" * 64,
    )
    child["parser"] = dict(complete["parser"])
    child["manifest_id"] = manifest_id_for(child)

    later_complete = dict(complete)
    later_complete["retrieval"] = dict(complete["retrieval"])
    later_complete["retrieval"]["retrieved_at"] = "2026-08-02T10:00:00Z"
    later_complete["document"] = dict(complete["document"])
    later_complete["document"]["document_version"] = 2
    later_complete["manifest_id"] = manifest_id_for(later_complete)

    later_child = dict(child)
    later_child["retrieval"] = dict(child["retrieval"])
    later_child["retrieval"]["retrieved_at"] = "2026-08-02T10:00:00Z"
    later_child["document"] = dict(child["document"])
    later_child["document"]["document_version"] = 2
    later_child["document"]["parent_manifest_id"] = later_complete["manifest_id"]
    later_child["parser"] = {**child["parser"], "parser_version": "sec-source-inspector/1.1.0"}
    later_child["manifest_id"] = manifest_id_for(later_child)

    decision = classify_bundle_against_published(
        [later_complete, later_child], [complete, child],
    )
    assert decision["status"] == "revision"
    assert [row["evidence_id"] for row in decision["changed"]] == [later_child["evidence_id"]]
    assert decision["persist"] == [later_complete, later_child]
    assert decision["append"] is decision["persist"] or decision["append"] == decision["persist"]
    assert decision["removed"] == []


def test_classifier_deselected_member_is_revision_not_reobservation():
    acc = "0001234567-26-000092"
    complete = _compiler_manifest(
        acc, document_role="complete_submission", document_version=1,
        parent_manifest_id=None, content_marker="complete",
        first_seen_at="2026-08-01T10:00:00Z", stamp_child_coords=True,
    )
    primary = _compiler_manifest(
        acc, document_role="primary", document_version=1,
        parent_manifest_id=complete["manifest_id"], content_marker="primary",
        first_seen_at="2026-08-01T10:00:00Z", stamp_child_coords=True,
    )
    exhibit = _compiler_manifest(
        acc, document_role="exhibit", document_version=1,
        parent_manifest_id=complete["manifest_id"], content_marker="exhibit",
        first_seen_at="2026-08-01T10:00:00Z", stamp_child_coords=True,
        sequence="2", document_name="purchase.htm",
    )
    later_complete = _compiler_manifest(
        acc, document_role="complete_submission", document_version=2,
        parent_manifest_id=None, content_marker="complete",
        first_seen_at="2026-08-02T10:00:00Z", stamp_child_coords=True,
    )
    later_primary = _compiler_manifest(
        acc, document_role="primary", document_version=2,
        parent_manifest_id=later_complete["manifest_id"], content_marker="primary",
        first_seen_at="2026-08-02T10:00:00Z", stamp_child_coords=True,
    )
    decision = classify_bundle_against_published(
        [later_complete, later_primary],
        [complete, primary, exhibit],
    )
    assert decision["status"] == "revision"
    assert decision["changed"] == []
    assert [row["evidence_id"] for row in decision["removed"]] == [exhibit["evidence_id"]]
    assert decision["persist"] == [later_complete, later_primary]
    assert exhibit["evidence_id"] not in {
        row["evidence_id"] for row in decision["persist"]
    }

    same_again = classify_bundle_against_published(
        [later_complete, later_primary],
        [complete, primary, exhibit, later_complete, later_primary],
    )
    assert same_again["status"] == "re_observed"
    assert same_again["persist"] == []
    assert same_again["removed"] == []


# ─────────────────────────────────────────────────────────────────────────────
# Historical identity refinement
# ─────────────────────────────────────────────────────────────────────────────


def _compiler_manifest(
    accession: str,
    *,
    document_role: str,
    document_version: int,
    parent_manifest_id: str | None,
    content_marker: str,
    first_seen_at: str,
    stamp_child_coords: bool,
    sequence: str | None = None,
    document_name: str | None = None,
) -> dict[str, Any]:
    raw = f"{accession}|S-3|{document_role}|{content_marker}".encode()
    digest = sha256(raw).hexdigest()
    if sequence is None:
        sequence = "0" if document_role == "complete_submission" else "1"
    if document_name is None:
        document_name = (
            "complete-submission.txt" if document_role == "complete_submission" else "primary.htm"
        )
    parent_digest = sha256(
        f"{accession}|S-3|complete_submission|{content_marker}".encode()
    ).hexdigest()
    record: dict[str, Any] = {
        "schema": "capital_structure.source_manifest/v1",
        "manifest_id": "",
        "source_system": "sec_edgar",
        "source_id": f"{accession}:{sequence}:{document_name}",
        "issuer": {
            "issuer_id": "sec:cik:0000000001", "cik": "1", "ticker": "ABC",
            "aliases": ["ABC Corp"],
        },
        "filing": {
            "accession": accession, "form": "S-3", "filing_date": "2026-08-01",
            "accepted_at": "2026-08-01T10:00:00Z", "file_number": "333-123",
            "file_number_provenance": {
                "state": "observed", "value": "333-123",
                "candidate_values": ["333-123"],
                "sources": ["legacy_sgml_file_number"],
            },
        },
        "document": {
            "canonical_url": f"https://www.sec.gov/Archives/{accession}.txt#document={sequence}",
            "document_name": document_name, "document_type": "S-3",
            "document_role": document_role, "sequence": sequence,
            "media_type": "text/plain", "byte_length": len(raw),
            "document_version": document_version, "content_sha256": digest,
            "parent_manifest_id": parent_manifest_id,
            "root_locator": f"sha256:{digest}",
        },
        "retrieval": {
            "retrieved_at": first_seen_at, "first_seen_at": first_seen_at,
            "transport_status": "retrieved",
        },
        "storage": {
            "backend": "r2", "store_id": "r2_shared",
            "object_key": f"capital_structure/sec/sha256/{digest[:2]}/{digest}",
            "content_addressed": True, "retention_state": "retained",
        },
        "rights": {
            "redistribution_class": "public_source_link",
            "attribution_required": True, "license_note": "SEC filing",
        },
        "privacy": {"classification": "public", "contains_personal_data": False},
        "parser": {
            "eligibility": "eligible", "corruption_state": "clean",
            "parser_version": "sec-submission-sgml/1.0.0",
        },
        "spans": [{
            "span_id": f"root:{digest}", "locator_type": "document",
            "locator": f"bytes:0-{len(raw)}", "text_sha256": digest,
        }],
    }
    if stamp_child_coords and document_role != "complete_submission":
        occ = child_occurrence(
            parent_content_sha256=parent_digest, byte_start=0, byte_end=len(raw),
        )
        record["evidence_occurrence"] = occ
        record["evidence_key_format"] = 1
        record["evidence_id"] = evidence_id_for(
            source_system="sec_edgar",
            submission_accession=accession,
            occurrence=occ,
            content_sha256=digest,
        )
        record["first_known_at"] = "2026-08-01T10:00:03Z"
    elif document_role == "complete_submission" and stamp_child_coords:
        record["evidence_occurrence"] = "submission"
        record["evidence_key_format"] = 1
        record["evidence_id"] = evidence_id_for(
            source_system="sec_edgar",
            submission_accession=accession,
            occurrence="submission",
            content_sha256=digest,
        )
        record["first_known_at"] = "2026-08-01T10:00:03Z"
    record["manifest_id"] = manifest_id_for(record)
    return record


def test_legacy_child_identity_refinement_is_not_a_capital_change_event():
    acc = "0000000001-26-000077"
    v1_complete = _compiler_manifest(
        acc, document_role="complete_submission", document_version=1,
        parent_manifest_id=None, content_marker="same-bytes",
        first_seen_at="2026-08-01T10:00:03Z", stamp_child_coords=False,
    )
    v1_child = _compiler_manifest(
        acc, document_role="primary", document_version=1,
        parent_manifest_id=v1_complete["manifest_id"], content_marker="same-bytes",
        first_seen_at="2026-08-01T10:00:03Z", stamp_child_coords=False,
    )
    v1 = [v1_complete, v1_child]
    occ = evidence_occurrence_from_manifest(v1_child)
    assert isinstance(occ, str) and occ.startswith("legacy:")
    legacy_eid = evidence_id_from_manifest(v1_child)
    assert "evidence_id" not in v1_child

    first = _compile(v1, generated_at="2026-08-01T12:00:00Z")
    assert len(first["events"]) == 1
    v1_snapshot = dict(v1_child)

    w1_complete = _compiler_manifest(
        acc, document_role="complete_submission", document_version=2,
        parent_manifest_id=None, content_marker="same-bytes",
        first_seen_at="2026-08-19T18:00:03Z", stamp_child_coords=True,
    )
    w1_child = _compiler_manifest(
        acc, document_role="primary", document_version=2,
        parent_manifest_id=w1_complete["manifest_id"], content_marker="same-bytes",
        first_seen_at="2026-08-19T18:00:03Z", stamp_child_coords=True,
    )
    coord_eid = w1_child["evidence_id"]
    assert not str(evidence_occurrence_from_manifest(w1_child)).startswith("legacy:")
    assert coord_eid != legacy_eid
    refined = refine_evidence_ids_for_semantic_compare(
        [legacy_eid], accession=acc, records=[*v1, w1_complete, w1_child],
    )
    assert refined == [coord_eid]

    merged_ledger = [*v1, w1_complete, w1_child]
    second = _compile(
        merged_ledger, existing=first["events"], generated_at="2026-08-19T20:00:00Z",
    )
    _assert_no_duplicate_event(first["events"], second)
    historical = next(
        row for row in merged_ledger if row["manifest_id"] == v1_snapshot["manifest_id"]
    )
    assert historical == v1_snapshot
    assert "evidence_id" not in historical
    assert evidence_id_from_manifest(historical) == legacy_eid
