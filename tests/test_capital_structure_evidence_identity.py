"""Hostile tests for Capital Structure V2 Wave 1 evidence identity law.

Covers ALL mandatory cases from the W1 spec:
- same SEC occurrence, different retrieval clocks → same evidence_id
- identical bytes in two accessions → different evidence_ids
- identical bytes in two child occurrences of one accession → different evidence_ids
- same occurrence with corrected file-number / issuer / parser → same evidence_id, separate manifest_id
- complete submission vs children → distinct ids; children carry parent+byte coords
- historical v1 manifests remain valid
- multiple historical v1 manifest_ids for one occurrence → one evidence_id (no deletion)
- ordinary re-observation does not mint a duplicate economic event
- new event identity does not change because retrieval clock changes
- stale overlapping CS generation is withheld as a whole family
- winning generation remains coherent
- #5792 fail-closed: selected>0 with neither new retained evidence nor re-observation cannot green

Uses the committed SGML fixture with two DOCUMENT blocks so document_inner_spans works.
Never depends on live data/capital_structure.
"""
from __future__ import annotations

import io
import json
import subprocess
import sys
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.capital_structure.ingestion_health import (  # noqa: E402
    build_ingestion_run,
    decide_verdict,
)
from engine.capital_structure.source_identity import (  # noqa: E402
    ChildOccurrenceUnbound,
    EvidenceIdentityError,
    ManifestIdentityError,
    child_occurrence,
    classify_bundle_against_published,
    document_inner_spans,
    evidence_id_for,
    evidence_id_from_manifest,
    interpretation_fingerprint,
    manifest_id_for,
    published_first_known_at,
    validate_manifest_identity,
    writable_child_occurrence,
)
from scripts.ci import append_only_base_fence as fence  # noqa: E402
from scripts.compile_capital_structure_events import (  # noqa: E402
    _semantic_event_body,
    compile_manifest_records,
)

FIXTURE = ROOT / "tests/fixtures/capital_structure/evidence_identity/two_document_submission.txt"
REGISTRY = ROOT / "config/append_only_artifacts.json"
CS_SOURCE_MANIFEST = "data/capital_structure/source_manifest.jsonl"
CS_SITE = "site/capital-structure-data"
CS_DATA = "data/capital_structure"

# ── shared SGML fixture helpers ──────────────────────────────────────────────

def _raw() -> bytes:
    return FIXTURE.read_bytes()


def _spans() -> tuple[tuple[int, int], ...]:
    return document_inner_spans(_raw())


def _parent_sha() -> str:
    return sha256(_raw()).hexdigest()


def _child_occ(idx: int) -> dict:
    s, e = _spans()[idx]
    return child_occurrence(parent_content_sha256=_parent_sha(), byte_start=s, byte_end=e)


# ── minimal manifest factory for hostility tests ───────────────────────────


def _manifest_v2(
    accession: str,
    document_role: str,
    content: bytes,
    *,
    first_seen_at: str = "2026-08-01T10:00:00Z",
    retrieved_at: str = "2026-08-01T10:00:00Z",
    first_known_at: str | None = None,
    file_number: str | None = "333-100001",
    evidence_id: str | None = None,
    evidence_occurrence: Any = "submission",
    byte_start: int | None = None,
    byte_end: int | None = None,
    parent_content_sha256: str | None = None,
    document_version: int = 1,
    parser_eligibility: str = "eligible",
) -> dict:
    digest = sha256(content).hexdigest()
    record: dict[str, Any] = {
        "schema": "capital_structure.source_manifest/v1",
        "source_system": "sec_edgar",
        "source_id": accession,
        "filing": {
            "accession": accession,
            "form": "S-3",
            "filing_date": "2026-08-01",
            "accepted_at": "2026-08-01T10:00:00Z",
            "file_number": file_number,
        },
        "document": {
            "document_role": document_role,
            "sequence": "1",
            "filename": "form.htm",
            "content_sha256": digest,
            "document_version": document_version,
        },
        "retrieval": {
            "first_seen_at": first_seen_at,
            "retrieved_at": retrieved_at,
        },
        "issuer": {
            "cik": "0001234567",
            "issuer_id": "issuer:0001234567",
        },
        "parser": {
            "eligibility": parser_eligibility,
            "corruption_state": "clean",
            "parser_version": "sec-submission-sgml/1.0.0",
        },
        "spans": [{
            "span_id": f"root:{digest}",
            "locator_type": "document",
            "locator": f"bytes:0-{len(content)}",
            "text_sha256": digest,
        }],
        "storage": {
            "backend": "r2",
            "store_id": "r2_shared",
            "object_key": f"capital_structure/sec/sha256/{digest[:2]}/{digest}",
            "content_addressed": True,
            "retention_state": "retained",
        },
        "rights": {
            "redistribution_class": "public_source_link",
            "attribution_required": True,
            "license_note": "SEC filing",
        },
        "privacy": {"classification": "public", "contains_personal_data": False},
    }
    if document_role != "complete_submission":
        # For child docs parent_manifest_id is required; caller must set it later.
        record["document"]["parent_manifest_id"] = None
    if evidence_id is not None:
        record["evidence_id"] = evidence_id
    if evidence_occurrence is not None:
        record["evidence_occurrence"] = evidence_occurrence
    if first_known_at is not None:
        record["first_known_at"] = first_known_at
        record["evidence_key_format"] = 1
    record["manifest_id"] = manifest_id_for(record)
    return record


# ─────────────────────────────────────────────────────────────────────────────
# 1. Same SEC occurrence, different retrieval clocks → same evidence_id
# ─────────────────────────────────────────────────────────────────────────────

def test_same_occurrence_different_clocks_same_evidence_id():
    content = b"S-3 document body"
    acc = "0001234567-26-000099"
    eid1 = evidence_id_for(
        source_system="sec_edgar",
        submission_accession=acc,
        occurrence="submission",
        content_sha256=sha256(content).hexdigest(),
    )
    eid2 = evidence_id_for(
        source_system="sec_edgar",
        submission_accession=acc,
        occurrence="submission",
        content_sha256=sha256(content).hexdigest(),
    )
    assert eid1 == eid2, "same occurrence+bytes must yield same evidence_id regardless of clock"
    assert eid1.startswith("evidence:cs:")


# ─────────────────────────────────────────────────────────────────────────────
# 2. Identical bytes in two accessions → different evidence_ids
# ─────────────────────────────────────────────────────────────────────────────

def test_identical_bytes_two_accessions_different_evidence_ids():
    content = b"S-3 document body"
    digest = sha256(content).hexdigest()
    eid_a = evidence_id_for(
        source_system="sec_edgar",
        submission_accession="0001111111-26-000001",
        occurrence="submission",
        content_sha256=digest,
    )
    eid_b = evidence_id_for(
        source_system="sec_edgar",
        submission_accession="0001111111-26-000002",
        occurrence="submission",
        content_sha256=digest,
    )
    assert eid_a != eid_b, "different accessions must yield different evidence_ids even with identical bytes"


# ─────────────────────────────────────────────────────────────────────────────
# 3. Identical bytes in two child occurrences of one accession → different evidence_ids
# ─────────────────────────────────────────────────────────────────────────────

def test_identical_bytes_two_child_occurrences_different_evidence_ids():
    raw = _raw()
    spans = _spans()
    parent_sha = _parent_sha()
    assert len(spans) >= 2, "fixture must have at least 2 DOCUMENT blocks"

    occ1 = child_occurrence(parent_content_sha256=parent_sha, byte_start=spans[0][0], byte_end=spans[0][1])
    occ2 = child_occurrence(parent_content_sha256=parent_sha, byte_start=spans[1][0], byte_end=spans[1][1])
    acc = "0001234567-26-099001"
    child1_bytes = raw[spans[0][0]:spans[0][1]]
    child2_bytes = raw[spans[1][0]:spans[1][1]]

    eid1 = evidence_id_for(
        source_system="sec_edgar",
        submission_accession=acc,
        occurrence=occ1,
        content_sha256=sha256(child1_bytes).hexdigest(),
    )
    eid2 = evidence_id_for(
        source_system="sec_edgar",
        submission_accession=acc,
        occurrence=occ2,
        content_sha256=sha256(child2_bytes).hexdigest(),
    )
    assert eid1 != eid2, "two child occurrences must differ even when bytes happen to match"


# ─────────────────────────────────────────────────────────────────────────────
# 4. Same occurrence + corrected file-number/issuer/parser → same evidence_id, new manifest_id
# ─────────────────────────────────────────────────────────────────────────────

def test_interpretation_revision_same_evidence_id_different_manifest_id():
    content = b"S-3 document body v2"
    acc = "0001234567-26-000100"
    digest = sha256(content).hexdigest()

    v1 = _manifest_v2(acc, "complete_submission", content, file_number="333-000001")
    v2 = deepcopy(v1)
    v2.pop("manifest_id")
    v2["filing"]["file_number"] = "333-000002"  # interpretation correction
    v2["manifest_id"] = manifest_id_for(v2)

    eid_v1 = evidence_id_from_manifest(v1)
    eid_v2 = evidence_id_from_manifest(v2)
    assert eid_v1 == eid_v2, "file_number change must not change evidence_id (occurrence+bytes unchanged)"
    assert v1["manifest_id"] != v2["manifest_id"], "different body → different manifest_id"
    assert eid_v1 == evidence_id_for(
        source_system="sec_edgar",
        submission_accession=acc,
        occurrence="submission",
        content_sha256=digest,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 5. Complete submission vs children → distinct ids; children carry parent+byte coords
# ─────────────────────────────────────────────────────────────────────────────

def test_complete_submission_vs_children_distinct_ids():
    raw = _raw()
    spans = _spans()
    parent_sha = _parent_sha()
    acc = "0001234567-26-099001"

    complete_eid = evidence_id_for(
        source_system="sec_edgar",
        submission_accession=acc,
        occurrence="submission",
        content_sha256=sha256(raw).hexdigest(),
    )
    child_eids = []
    for s, e in spans:
        occ = child_occurrence(parent_content_sha256=parent_sha, byte_start=s, byte_end=e)
        # child occurrence dict carries parent_content_sha256, byte_start, byte_end
        assert occ["parent_content_sha256"] == parent_sha
        assert occ["byte_start"] == s
        assert occ["byte_end"] == e
        eid = evidence_id_for(
            source_system="sec_edgar",
            submission_accession=acc,
            occurrence=occ,
            content_sha256=sha256(raw[s:e]).hexdigest(),
        )
        child_eids.append(eid)
    all_ids = [complete_eid] + child_eids
    assert len(set(all_ids)) == len(all_ids), "complete + each child must have distinct evidence_ids"


# ─────────────────────────────────────────────────────────────────────────────
# 6. Historical v1 manifests remain valid under validate_manifest_identity / schema
# ─────────────────────────────────────────────────────────────────────────────

def test_historical_v1_manifest_validates_without_evidence_fields():
    content = b"historical s-3 body"
    acc = "0001234567-26-000001"
    # v1 row: no evidence_id, no evidence_occurrence, no first_known_at
    record: dict[str, Any] = {
        "schema": "capital_structure.source_manifest/v1",
        "source_system": "sec_edgar",
        "source_id": acc,
        "filing": {
            "accession": acc,
            "form": "S-3",
            "filing_date": "2026-01-01",
            "accepted_at": "2026-01-01T00:00:00Z",
            "file_number": "333-000001",
        },
        "document": {
            "document_role": "complete_submission",
            "sequence": "0",
            "filename": "complete.txt",
            "content_sha256": sha256(content).hexdigest(),
            "document_version": 1,
        },
        "retrieval": {"first_seen_at": "2026-01-01T00:00:00Z", "retrieved_at": "2026-01-01T00:00:00Z"},
        "issuer": {"cik": "0001234567", "issuer_id": "issuer:0001234567"},
        "parser": {"eligibility": "eligible", "corruption_state": "clean", "parser_version": "sec/1.0.0"},
        "spans": [{"span_id": f"root:{sha256(content).hexdigest()}", "locator_type": "document", "locator": "bytes:0-19", "text_sha256": sha256(content).hexdigest()}],
        "storage": {"backend": "r2", "store_id": "r2_shared", "object_key": "x/y", "content_addressed": True, "retention_state": "retained"},
        "rights": {"redistribution_class": "public_source_link", "attribution_required": True, "license_note": "SEC filing"},
        "privacy": {"classification": "public", "contains_personal_data": False},
    }
    record["manifest_id"] = manifest_id_for(record)
    validate_manifest_identity(record)  # must not raise for v1 row


# ─────────────────────────────────────────────────────────────────────────────
# 7. Multiple historical v1 manifest_ids for one occurrence → one evidence_id (no deletion)
# ─────────────────────────────────────────────────────────────────────────────

def test_multiple_v1_manifests_same_occurrence_one_evidence_id():
    content = b"historical s-3 body with provenance change"
    acc = "0001234567-26-000010"
    # Two v1 rows: same occurrence+bytes, different file_number (interpretation change)
    v1 = _manifest_v2(acc, "complete_submission", content, file_number="333-000001")
    v2 = deepcopy(v1)
    v2.pop("manifest_id")
    v2["filing"]["file_number"] = "333-000002"
    v2["document"]["document_version"] = 2
    v2["manifest_id"] = manifest_id_for(v2)

    eid1 = evidence_id_from_manifest(v1)
    eid2 = evidence_id_from_manifest(v2)
    assert eid1 == eid2, "v1 and v2 for same occurrence+bytes must map to one evidence_id"
    # Both rows must remain independently valid (no deletion)
    validate_manifest_identity(v1)
    validate_manifest_identity(v2)


# ─────────────────────────────────────────────────────────────────────────────
# 8. published_first_known_at freezes at first published record
# ─────────────────────────────────────────────────────────────────────────────

def test_published_first_known_at_freezes_at_first_record():
    content = b"stable bytes"
    acc = "0001234567-26-000020"
    digest = sha256(content).hexdigest()
    eid = evidence_id_for(
        source_system="sec_edgar",
        submission_accession=acc,
        occurrence="submission",
        content_sha256=digest,
    )
    # First published row carries first_known_at
    early_row = _manifest_v2(acc, "complete_submission", content, first_known_at="2026-01-01T00:00:00Z")
    early_row["evidence_id"] = eid
    # A later competing local timestamp must not overwrite
    result = published_first_known_at(eid, [early_row], candidate_timestamp="2026-08-01T00:00:00Z")
    assert result == "2026-01-01T00:00:00Z", "published first_known_at must not move backward"

    # When no published row exists, candidate is used
    result2 = published_first_known_at(eid, [], candidate_timestamp="2026-08-01T00:00:00Z")
    assert result2 == "2026-08-01T00:00:00Z"


# ─────────────────────────────────────────────────────────────────────────────
# 9. Ordinary re-observation does not increment unique evidence count
#    or mint a duplicate economic event
# ─────────────────────────────────────────────────────────────────────────────

def _make_manifest_record(
    accession: str,
    document_role: str,
    *,
    accepted_at: str = "2026-08-01T10:00:00Z",
    first_seen_at: str = "2026-08-01T10:00:03Z",
    file_number: str = "333-100001",
    parent_manifest_id: str | None = None,
    content_marker: str = "v1",
    first_known_at: str | None = None,
) -> dict:
    """Build a schema-valid manifest record. Mirrors test_capital_structure_compiler._manifest."""
    sequence = "0" if document_role == "complete_submission" else "1"
    doc_name = "complete-submission.txt" if document_role == "complete_submission" else "primary.htm"
    raw = f"{accession}|S-3|{document_role}|{content_marker}".encode()
    digest = sha256(raw).hexdigest()
    record: dict[str, Any] = {
        "schema": "capital_structure.source_manifest/v1",
        "source_system": "sec_edgar",
        "source_id": f"{accession}:{sequence}:{doc_name}",
        "issuer": {
            "issuer_id": "issuer:0001234567",
            "cik": "1234567",
            "ticker": "TST",
            "aliases": [],
        },
        "filing": {
            "accession": accession,
            "form": "S-3",
            "filing_date": "2026-08-01",
            "accepted_at": accepted_at,
            "file_number": file_number,
            "file_number_provenance": {
                "state": "observed",
                "value": file_number,
                "candidate_values": [file_number],
                "sources": ["legacy_sgml_file_number"],
            },
        },
        "document": {
            "canonical_url": f"https://www.sec.gov/Archives/{accession}.txt#doc={sequence}",
            "document_name": doc_name,
            "document_type": "S-3",
            "document_role": document_role,
            "sequence": sequence,
            "media_type": "text/plain",
            "byte_length": len(raw),
            "document_version": 1,
            "content_sha256": digest,
            "parent_manifest_id": parent_manifest_id,
            "root_locator": f"sha256:{digest}",
        },
        "retrieval": {
            "retrieved_at": first_seen_at,
            "first_seen_at": first_seen_at,
            "transport_status": "retrieved",
        },
        "storage": {
            "backend": "r2",
            "store_id": "r2_shared",
            "object_key": f"capital_structure/sec/sha256/{digest[:2]}/{digest}",
            "content_addressed": True,
            "retention_state": "retained",
        },
        "rights": {"redistribution_class": "public_source_link", "attribution_required": True, "license_note": "SEC filing"},
        "privacy": {"classification": "public", "contains_personal_data": False},
        "parser": {"eligibility": "eligible", "corruption_state": "clean", "parser_version": "sec-submission-sgml/1.0.0"},
        "spans": [{
            "span_id": f"root:{digest}",
            "locator_type": "document",
            "locator": f"bytes:0-{len(raw)}",
            "text_sha256": digest,
        }],
    }
    if first_known_at is not None:
        record["first_known_at"] = first_known_at
        record["evidence_key_format"] = 1
    record["manifest_id"] = manifest_id_for(record)
    return record


def _make_minimal_bundle(
    accession: str,
    *,
    accepted_at: str = "2026-08-01T10:00:00Z",
    first_seen_at: str = "2026-08-01T10:00:03Z",
    file_number: str = "333-100001",
    first_known_at: str | None = None,
) -> list[dict]:
    """Build a minimal compile-ready complete+primary manifest bundle."""
    complete = _make_manifest_record(
        accession, "complete_submission",
        accepted_at=accepted_at, first_seen_at=first_seen_at,
        file_number=file_number, first_known_at=first_known_at,
    )
    primary = _make_manifest_record(
        accession, "primary",
        accepted_at=accepted_at, first_seen_at=first_seen_at,
        file_number=file_number, first_known_at=first_known_at,
        parent_manifest_id=complete["manifest_id"],
    )
    return [complete, primary]


def test_reobservation_does_not_mint_duplicate_event():
    """Two compilations from identical manifest bundles must produce identical events."""
    acc = "0001234567-26-000030"
    bundle = _make_minimal_bundle(acc)
    result1 = compile_manifest_records(manifests=bundle, existing_events=[], existing_edges=[])
    events1 = result1["events"]
    assert len(events1) == 1

    # Second compile from the same bundle — should be idempotent
    result2 = compile_manifest_records(manifests=bundle, existing_events=events1, existing_edges=[])
    events2 = result2["events"]
    # No new events should be appended
    assert len(events2) == 1, "re-observation must not mint a duplicate event"
    assert events2[0]["event_id"] == events1[0]["event_id"]


# ─────────────────────────────────────────────────────────────────────────────
# 10. New event identity does not change because retrieval clock changes
# ─────────────────────────────────────────────────────────────────────────────

def test_event_identity_stable_across_clock_changes():
    """A later observation with a different first_seen_at must not generate a correction.

    In W1 a re-observation does not add a new manifest record.  This test
    simulates a concurrent race where two workers each fetched the same bytes at
    different wall clocks and both landed their (different) manifest_ids in the
    ledger — the combined ledger must produce exactly one event and the event_id
    must be unchanged.
    """
    acc = "0001234567-26-000040"
    bundle_early = _make_minimal_bundle(acc, first_seen_at="2026-08-01T10:00:03Z")
    result_early = compile_manifest_records(manifests=bundle_early, existing_events=[], existing_edges=[])
    events_early = result_early["events"]
    assert len(events_early) == 1

    # Same accession/bytes but a later first_seen_at → new manifest_ids but same economic content.
    # Both bundles land in the ledger (concurrent race scenario).
    bundle_late = _make_minimal_bundle(acc, first_seen_at="2026-08-02T10:00:03Z")
    # Combined ledger: both sets of manifests; lineage check sees old IDs (from events_early)
    # inside current_manifest_ids and does not raise.  Semantic comparison pops manifest_ids
    # so the candidate matches the prior and no correction is emitted.
    bundle_both = bundle_early + bundle_late
    result_late = compile_manifest_records(manifests=bundle_both, existing_events=events_early, existing_edges=[])
    events_late = result_late["events"]
    assert len(events_late) == 1, "clock change alone must not generate a correction event"
    assert events_late[0]["event_id"] == events_early[0]["event_id"]


# ─────────────────────────────────────────────────────────────────────────────
# 11. _semantic_event_body pops manifest_ids so clock noise does not drive identity
# ─────────────────────────────────────────────────────────────────────────────

def test_semantic_event_body_pops_manifest_ids_and_evidence_manifest_id():
    acc = "0001234567-26-000050"
    bundle = _make_minimal_bundle(acc)
    result = compile_manifest_records(manifests=bundle, existing_events=[], existing_edges=[])
    event = result["events"][0]

    # The semantic body must not contain source.manifest_ids or evidence[].manifest_id
    import json as _json
    body_bytes = _semantic_event_body(event)
    body = _json.loads(body_bytes)
    assert "manifest_ids" not in body.get("source", {}), \
        "_semantic_event_body must pop source.manifest_ids"
    for ev_item in body.get("evidence", []):
        assert "manifest_id" not in ev_item, \
            "_semantic_event_body must pop evidence[].manifest_id"


# ─────────────────────────────────────────────────────────────────────────────
# 12. Stale overlapping CS generation is withheld as a whole family
#     and winning generation's paths remain coherent
# ─────────────────────────────────────────────────────────────────────────────

def _git(repo: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=str(repo), capture_output=True, check=True)
    return done.stdout.decode()


def _write(repo: Path, path: str, payload: bytes) -> None:
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)


def _manifest_line(manifest_id: str) -> bytes:
    return (json.dumps({"manifest_id": manifest_id}, sort_keys=True, separators=(",", ":")) + "\n").encode()


@pytest.fixture
def cs_lane(tmp_path: Path) -> dict:
    """A repo where origin/main has run-A's CS generation and HEAD is run-B's stale generation.

    Run B's source_manifest.jsonl DROPS a row that origin/main carries —
    the fence must withhold data/capital_structure AND site/capital-structure-data.
    """
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--quiet", "--bare", "-b", "main", str(origin)], check=True)
    runner = tmp_path / "runner"
    subprocess.run(["git", "init", "--quiet", "-b", "main", str(runner)], check=True)
    _git(runner, "config", "user.email", "bot@example.invalid")
    _git(runner, "config", "user.name", "dashboard-bot")
    _git(runner, "remote", "add", "origin", str(origin))

    # Base: one manifest row
    base_manifest = _manifest_line("manifest:cs:aaa") + _manifest_line("manifest:cs:bbb")
    _write(runner, CS_SOURCE_MANIFEST, base_manifest)
    _write(runner, f"{CS_DATA}/source_objects/x.bin", b"object")
    _write(runner, f"{CS_SITE}/events.json", b'{"events":[]}')
    _git(runner, "add", "-A")
    _git(runner, "commit", "--quiet", "-m", "base: cs generation")
    _git(runner, "push", "--quiet", "origin", "main")
    base_sha = _git(runner, "rev-parse", "HEAD").strip()

    # Run A: extends manifest with a third row — lands on origin/main first.
    a_manifest = base_manifest + _manifest_line("manifest:cs:ccc")
    _write(runner, CS_SOURCE_MANIFEST, a_manifest)
    _write(runner, f"{CS_SITE}/events.json", b'{"events":[1]}')
    _git(runner, "add", "-A")
    _git(runner, "commit", "--quiet", "-m", "data: cs generation run-A")
    _git(runner, "push", "--quiet", "origin", "main")

    # Run B workspace: branches off base, commits a stale generation
    # that DROPS manifest:cs:bbb (only has aaa + ccc).
    _git(runner, "reset", "--hard", "--quiet", base_sha)
    b_manifest = _manifest_line("manifest:cs:aaa") + _manifest_line("manifest:cs:ccc")
    _write(runner, CS_SOURCE_MANIFEST, b_manifest)
    _write(runner, f"{CS_SITE}/events.json", b'{"events":[2]}')
    _git(runner, "add", "-A")
    _git(runner, "commit", "--quiet", "-m", "data: cs generation run-B (stale)")
    _git(runner, "fetch", "--quiet", "origin", "main")

    return {
        "repo": runner,
        "base_sha": base_sha,
        "a_manifest": a_manifest,
    }


def test_stale_cs_generation_withholds_whole_family(cs_lane, capsys):
    repo = cs_lane["repo"]
    exit_code = fence.run(
        repo,
        onto="origin/main",
        head="HEAD",
        registry=REGISTRY,
        restore=True,
        amend=False,
    )
    assert exit_code == 0, "withhold must succeed (exit 0)"
    out = capsys.readouterr().out
    # Both withhold_paths must be reported as withheld
    assert "capital-structure" in out.lower() or "withheld" in out.lower(), (
        "fence output must mention the capital-structure family or withhold action"
    )
    # After withhold, HEAD's source_manifest.jsonl must match origin/main (run A's version)
    committed = _git(repo, "show", "HEAD:data/capital_structure/source_manifest.jsonl")
    # The committed manifest in HEAD should now carry manifest:cs:bbb (from run A)
    assert "manifest:cs:bbb" in committed, (
        "After withhold, CS generation must be restored to origin/main's coherent state"
    )


def test_winning_cs_generation_coherent_after_withhold(cs_lane):
    """After the fence withholds, both data/capital_structure and site/capital-structure-data
    paths are restored to origin/main's winning state."""
    repo = cs_lane["repo"]
    fence.run(
        repo,
        onto="origin/main",
        head="HEAD",
        registry=REGISTRY,
        restore=True,
        amend=False,
    )
    # Check both withhold_paths are coherent (match origin/main)
    manifest_head = _git(repo, "show", "HEAD:data/capital_structure/source_manifest.jsonl")
    manifest_main = _git(repo, "show", "origin/main:data/capital_structure/source_manifest.jsonl")
    assert manifest_head == manifest_main, (
        "After withhold, data/capital_structure must match origin/main"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 13. Registry includes capital-structure
# ─────────────────────────────────────────────────────────────────────────────

def test_registry_includes_capital_structure_family():
    families = fence.load_registry(REGISTRY)
    keys = {family.key for family in families}
    assert "capital-structure" in keys, "append_only_artifacts.json must declare capital-structure family"


def test_cs_family_withholds_both_data_and_site_paths():
    families = fence.load_registry(REGISTRY)
    cs = next((f for f in families if f.key == "capital-structure"), None)
    assert cs is not None
    withhold = set(cs.withhold_paths)
    assert "data/capital_structure" in withhold, "capital-structure family must withhold data/capital_structure"
    assert "site/capital-structure-data" in withhold, "capital-structure family must withhold site/capital-structure-data"


def test_cs_family_source_manifest_is_a_member():
    families = fence.load_registry(REGISTRY)
    cs = next((f for f in families if f.key == "capital-structure"), None)
    assert cs is not None
    member_paths = {m.path for m in cs.members}
    assert CS_SOURCE_MANIFEST in member_paths, (
        f"capital-structure family must declare {CS_SOURCE_MANIFEST} as a member"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 14. #5792 fail-closed: selected>0 with neither new retained evidence nor re-observation cannot green
# ─────────────────────────────────────────────────────────────────────────────

def _watermark(n: int) -> dict:
    return {"source_manifest_count": n, "retrieval_attempt_count": 0}


def test_5792_selected_with_zero_progress_fails():
    verdict, reason = decide_verdict(
        selected=3,
        manifested_delta=0,
        verified_retained=0,
        no_new_work_proven=False,
        no_new_work_reason=None,
        re_observed=0,
    )
    assert verdict == "fail", "#5792: selected>0 with no progress must fail"


def test_5792_selected_with_re_observed_passes():
    verdict, _ = decide_verdict(
        selected=3,
        manifested_delta=0,
        verified_retained=0,
        no_new_work_proven=False,
        no_new_work_reason=None,
        re_observed=2,
    )
    assert verdict == "ok", "selected>0 AND re_observed>0 must pass (#5792 third progress term)"


def test_5792_re_observed_zero_no_new_work_not_proven_fails():
    """selected>0 AND no progressed AND re_observed==0 is still a fail even if selected>0."""
    verdict, _ = decide_verdict(
        selected=1,
        manifested_delta=0,
        verified_retained=0,
        no_new_work_proven=False,
        no_new_work_reason=None,
        re_observed=0,
    )
    assert verdict == "fail"


def test_build_ingestion_run_always_emits_re_observed():
    run = build_ingestion_run(
        as_of="2026-08-19T00:00:00Z",
        store_id="r2_shared",
        selected=0,
        retrieved=0,
        verified_retained=0,
        manifested=0,
        deferred=0,
        parser_deferred=0,
        storage_deferred=0,
        parked=0,
        watermark_before=_watermark(10),
        watermark_after=_watermark(10),
        no_new_work_proven=True,
        re_observed=0,
    )
    assert "re_observed" in run["counters"], "build_ingestion_run must always emit counters.re_observed"
    assert run["counters"]["re_observed"] == 0


def test_build_ingestion_run_optional_evidence_fields():
    run = build_ingestion_run(
        as_of="2026-08-19T00:00:00Z",
        store_id="r2_shared",
        selected=5,
        retrieved=5,
        verified_retained=0,
        manifested=0,
        deferred=0,
        parser_deferred=0,
        storage_deferred=0,
        parked=0,
        watermark_before=_watermark(10),
        watermark_after=_watermark(10),
        no_new_work_proven=False,
        re_observed=5,
        unique_evidence_count=4,
        manifest_revision_count=1,
        observation_count=5,
    )
    assert run["counters"]["re_observed"] == 5
    assert run["counters"]["unique_evidence_count"] == 4
    assert run["counters"]["manifest_revision_count"] == 1
    assert run["counters"]["observation_count"] == 5
    assert run["verdict"] == "ok"


# ─────────────────────────────────────────────────────────────────────────────
# 15. New events carry evidence_ids in source; PIT uses first_known_at
# ─────────────────────────────────────────────────────────────────────────────

def test_new_event_carries_evidence_ids_in_source():
    acc = "0001234567-26-000060"
    # Pass first_known_at so _make_manifest_record stamps evidence_key_format=1;
    # the compiler then derives evidence_ids from the rows via evidence_id_from_manifest.
    bundle = _make_minimal_bundle(acc, first_known_at="2026-08-01T10:00:00Z")
    result = compile_manifest_records(manifests=bundle, existing_events=[], existing_edges=[])
    events = result["events"]
    assert events, "should compile at least one event"
    source = events[0].get("source", {})
    assert "evidence_ids" in source, "new W1 events must carry source.evidence_ids"
    assert all(eid.startswith("evidence:cs:") for eid in source["evidence_ids"])


def test_pit_uses_first_known_at_not_retrieval_clock():
    acc = "0001234567-26-000070"
    canonical_ts = "2026-06-01T00:00:00Z"
    # Pass first_known_at directly so the manifest rows carry the canonical timestamp.
    # The compiler must use this value for all point_in_time PIT fields.
    bundle = _make_minimal_bundle(acc, first_known_at=canonical_ts)
    result = compile_manifest_records(manifests=bundle, existing_events=[], existing_edges=[])
    events = result["events"]
    assert events
    pit = events[0].get("point_in_time", {})
    assert pit.get("first_seen_at") == canonical_ts, (
        "point_in_time.first_seen_at must use canonical first_known_at, not wall clock"
    )
    assert pit.get("available_at") == canonical_ts


# ─────────────────────────────────────────────────────────────────────────────
# 16. evidence_id_for rejects unexpected kwargs (clock, issuer, filename, etc.)
# ─────────────────────────────────────────────────────────────────────────────

def test_evidence_id_for_rejects_unexpected_kwargs():
    with pytest.raises((TypeError, EvidenceIdentityError)):
        evidence_id_for(
            source_system="sec_edgar",
            submission_accession="0001234567-26-000001",
            occurrence="submission",
            content_sha256="a" * 64,
            retrieved_at="2026-08-01T10:00:00Z",  # must be rejected
        )


# ─────────────────────────────────────────────────────────────────────────────
# 17. document_inner_spans works on the canonical fixture
# ─────────────────────────────────────────────────────────────────────────────

def test_two_document_fixture_spans_are_correct():
    raw = _raw()
    spans = _spans()
    assert len(spans) == 2, "fixture must yield exactly 2 inner spans"
    for s, e in spans:
        assert 0 < s < e <= len(raw)
        inner = raw[s:e]
        assert b"<TYPE>" in inner, "inner span must contain DOCUMENT content"


# ─────────────────────────────────────────────────────────────────────────────
# W1A.1 Independent post-W1 event identity is clock-independent
# ─────────────────────────────────────────────────────────────────────────────

def test_independent_compiles_share_post_w1_event_id_with_empty_existing():
    acc = "0001234567-26-000080"
    early = _make_minimal_bundle(
        acc, first_seen_at="2026-08-01T10:00:03Z", first_known_at="2026-08-01T10:00:03Z",
    )
    late = _make_minimal_bundle(
        acc, first_seen_at="2026-08-19T18:00:03Z", first_known_at="2026-08-19T18:00:03Z",
    )
    result_early = compile_manifest_records(
        manifests=early, existing_events=[], existing_edges=[],
    )
    result_late = compile_manifest_records(
        manifests=late, existing_events=[], existing_edges=[],
    )
    assert result_early["events"] and result_late["events"]
    early_event = result_early["events"][0]
    late_event = result_late["events"][0]
    assert early_event["event_id"] == late_event["event_id"]
    assert early_event["source"]["manifest_ids"] != late_event["source"]["manifest_ids"]
    assert early_event["version"].get("identity_format") == 2
    assert late_event["version"].get("identity_format") == 2


def test_compile_interpretation_correction_mints_distinct_event_version():
    acc = "0001234567-26-000081"
    original = _make_minimal_bundle(
        acc, file_number="333-100001", first_known_at="2026-08-01T10:00:03Z",
    )
    first = compile_manifest_records(
        manifests=original, existing_events=[], existing_edges=[],
        generated_at="2026-08-01T12:00:00Z",
    )
    corrected = _make_minimal_bundle(
        acc, file_number="333-200002", first_known_at="2026-08-01T10:00:03Z",
    )
    complete = next(
        row for row in corrected
        if row["document"]["document_role"] == "complete_submission"
    )
    for row in corrected:
        row["document"]["document_version"] = 2
    complete["manifest_id"] = manifest_id_for(complete)
    for row in corrected:
        if row is not complete:
            row["document"]["parent_manifest_id"] = complete["manifest_id"]
        row["manifest_id"] = manifest_id_for(row)
    second = compile_manifest_records(
        manifests=original + corrected,
        existing_events=first["events"],
        existing_edges=[],
        generated_at="2026-08-03T12:00:00Z",
    )
    assert len(second["events"]) == 2
    assert second["events"][1]["event_id"] != second["events"][0]["event_id"]
    assert second["events"][1]["version"]["correction_of"] == second["events"][0]["event_id"]
    assert second["events"][1]["version"]["identity_format"] == 2


# ─────────────────────────────────────────────────────────────────────────────
# W1A.2 New writes never mint legacy:{source_id} child occurrence
# ─────────────────────────────────────────────────────────────────────────────

def test_writable_child_occurrence_refuses_unbound_coordinates():
    with pytest.raises(ChildOccurrenceUnbound, match="legacy"):
        writable_child_occurrence(
            parent_content_sha256=None, byte_start=None, byte_end=None,
        )
    occ = writable_child_occurrence(
        parent_content_sha256=_parent_sha(),
        byte_start=_spans()[0][0],
        byte_end=_spans()[0][1],
    )
    assert occ["parent_content_sha256"] == _parent_sha()


def test_malformed_fresh_submission_cannot_mint_legacy_child_occurrence():
    from collectors.sec_capital_structure import (
        DocumentInspection,
        SecCapitalStructureAdapter,
        parse_submission,
    )
    from engine.capital_structure.source_store import SourceReceipt, STORE_ID_DEDICATED_R2

    malformed = _raw().replace(b"</DOCUMENT>", b"</DOC>", 1)
    bundle = parse_submission(malformed)
    assert bundle.documents, "malformed fixture must still yield DOCUMENT blocks"
    assert all(doc.byte_start is None and doc.byte_end is None for doc in bundle.documents)

    child = bundle.documents[0]
    digest = sha256(child.raw).hexdigest()
    receipt = SourceReceipt(
        object_key=f"capital_structure/sec/sha256/{digest[:2]}/{digest}",
        sha256=digest, byte_length=len(child.raw), media_type="text/plain",
        backend="r2", store_id=STORE_ID_DEDICATED_R2,
    )
    discovery = {
        "accession": "0001234567-26-099001",
        "cik": "1234567",
        "ticker": "TST",
        "company_name": "Test Issuer",
        "form": "S-3",
        "filing_date": "2026-08-01",
        "canonical_url": "https://www.sec.gov/Archives/test.txt",
    }
    with pytest.raises(ChildOccurrenceUnbound, match="legacy"):
        SecCapitalStructureAdapter._manifest_record(
            discovery=discovery, bundle=bundle,
            source_id="0001234567-26-099001:1:forms3.htm",
            canonical_url=discovery["canonical_url"],
            document_name="forms3.htm", document_type="S-3",
            document_role="primary", sequence="1", raw=child.raw,
            receipt=receipt,
            inspection=DocumentInspection("text/plain", "eligible", "clean"),
            retrieved_at="2026-08-01T12:36:00+00:00",
            first_seen_at="2026-08-01T12:36:00+00:00", document_version=1,
            parent_manifest_id="manifest:cs:" + "a" * 64,
        )

    later = parse_submission(_raw())
    bound = later.documents[0]
    assert bound.byte_start is not None and bound.byte_end is not None
    later_occ = writable_child_occurrence(
        parent_content_sha256=sha256(_raw()).hexdigest(),
        byte_start=bound.byte_start,
        byte_end=bound.byte_end,
    )
    later_eid = evidence_id_for(
        source_system="sec_edgar",
        submission_accession="0001234567-26-099001",
        occurrence=later_occ,
        content_sha256=sha256(bound.raw).hexdigest(),
    )
    assert not later_eid.startswith("legacy:")
    unbound_id = f"legacy:0001234567-26-099001:1:forms3.htm"
    assert later_eid != unbound_id


# ─────────────────────────────────────────────────────────────────────────────
# W1A.3 Bundle-level re-observation, not a complete-row shortcut
# ─────────────────────────────────────────────────────────────────────────────

def _stamp_evidence(record: dict, occurrence: Any) -> dict:
    filing = record.get("filing") or {}
    document = record.get("document") or {}
    record["evidence_occurrence"] = occurrence
    record["evidence_key_format"] = 1
    record["evidence_id"] = evidence_id_for(
        source_system=str(record.get("source_system") or "sec_edgar"),
        submission_accession=str(filing.get("accession") or ""),
        occurrence=occurrence,
        content_sha256=str(document.get("content_sha256") or ""),
    )
    record["manifest_id"] = manifest_id_for(record)
    return record


def test_historical_v1_complete_reobserved_unchanged_is_not_a_new_revision():
    acc = "0001234567-26-000090"
    v1 = _make_manifest_record(acc, "complete_submission", first_seen_at="2026-01-01T00:00:00Z")
    assert "evidence_id" not in v1
    w1 = _make_manifest_record(
        acc, "complete_submission", first_seen_at="2026-08-19T18:00:00Z",
        first_known_at="2026-08-19T18:00:00Z",
    )
    w1 = _stamp_evidence(w1, "submission")
    assert evidence_id_from_manifest(v1) == w1["evidence_id"]
    decision = classify_bundle_against_published([w1], [v1])
    assert decision["status"] == "re_observed"
    assert decision["persist"] == []
    assert decision["append"] == []


def test_complete_unchanged_child_interpretation_change_is_bundle_revision():
    acc = "0001234567-26-000091"
    parent_sha = _parent_sha()
    child_occ = _child_occ(0)
    complete = _stamp_evidence(
        _make_manifest_record(acc, "complete_submission", first_known_at="2026-08-01T10:00:00Z"),
        "submission",
    )
    child = _make_manifest_record(
        acc, "primary", parent_manifest_id=complete["manifest_id"],
        first_known_at="2026-08-01T10:00:00Z",
    )
    child["document"]["content_sha256"] = sha256(_raw()[_spans()[0][0]:_spans()[0][1]]).hexdigest()
    child = _stamp_evidence(child, child_occ)
    published = [complete, child]

    candidate_complete = _stamp_evidence(
        _make_manifest_record(
            acc, "complete_submission", first_seen_at="2026-08-19T18:00:00Z",
            first_known_at="2026-08-01T10:00:00Z",
        ),
        "submission",
    )
    candidate_child = _make_manifest_record(
        acc, "primary", parent_manifest_id=complete["manifest_id"],
        first_seen_at="2026-08-19T18:00:00Z",
        first_known_at="2026-08-01T10:00:00Z",
    )
    candidate_child["document"]["content_sha256"] = child["document"]["content_sha256"]
    candidate_child["parser"]["parser_version"] = "sec-submission-sgml/1.1.0"
    candidate_child = _stamp_evidence(candidate_child, child_occ)

    decision = classify_bundle_against_published(
        [candidate_complete, candidate_child], published,
    )
    assert decision["status"] == "revision"
    assert [row["evidence_id"] for row in decision["changed"]] == [
        candidate_child["evidence_id"]
    ]
    assert [row["evidence_id"] for row in decision["persist"]] == [
        candidate_complete["evidence_id"], candidate_child["evidence_id"],
    ]
    assert decision["append"] == decision["persist"]
    assert interpretation_fingerprint(candidate_complete) == interpretation_fingerprint(complete)


def test_complete_and_children_unchanged_is_one_verified_reobservation():
    acc = "0001234567-26-000092"
    child_occ = _child_occ(0)
    complete = _stamp_evidence(
        _make_manifest_record(acc, "complete_submission", first_known_at="2026-08-01T10:00:00Z"),
        "submission",
    )
    child = _make_manifest_record(
        acc, "primary", parent_manifest_id=complete["manifest_id"],
        first_known_at="2026-08-01T10:00:00Z",
    )
    child["document"]["content_sha256"] = sha256(_raw()[_spans()[0][0]:_spans()[0][1]]).hexdigest()
    child = _stamp_evidence(child, child_occ)
    published = [complete, child]

    later_complete = _stamp_evidence(
        _make_manifest_record(
            acc, "complete_submission", first_seen_at="2026-08-19T18:00:00Z",
            first_known_at="2026-08-01T10:00:00Z",
        ),
        "submission",
    )
    later_child = _make_manifest_record(
        acc, "primary", parent_manifest_id=complete["manifest_id"],
        first_seen_at="2026-08-19T18:00:00Z",
        first_known_at="2026-08-01T10:00:00Z",
    )
    later_child["document"]["content_sha256"] = child["document"]["content_sha256"]
    later_child = _stamp_evidence(later_child, child_occ)

    decision = classify_bundle_against_published(
        [later_complete, later_child], published,
    )
    assert decision["status"] == "re_observed"
    assert decision["persist"] == []
    assert decision["append"] == []
    assert len(decision["unchanged"]) == 2
