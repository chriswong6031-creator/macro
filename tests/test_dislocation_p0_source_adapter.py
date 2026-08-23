"""P0 consumes, but never mints, canonical SEC document-spine packets."""
from __future__ import annotations

from pathlib import Path

from collectors.sec_document_spine import persist_archive_document, persist_filing_manifest
from engine.fundamental_forensics.sec_document_spine import (
    build_filing_manifests,
    documents_from_archive_index,
    with_archive_documents,
    with_document_retrievals,
)
from scripts.research.dislocation_p0_source_adapter import CanonicalSpineRef, read_exact_p0_source_packets


RECORDED = "2026-08-22T12:00:00Z"
ACCEPTED = "2026-08-20T15:30:00Z"


def _submission(accession: str, *, form: str = "8-K", accepted: str | None = ACCEPTED) -> dict:
    return {
        "filings": {"recent": {
            "accessionNumber": [accession], "form": [form], "filingDate": ["2026-08-20"],
            "reportDate": ["2026-08-19"], "acceptanceDateTime": [accepted],
            "primaryDocument": ["primary.htm"], "isXBRL": [False], "isInlineXBRL": [False],
            "items": ["2.05"], "amendsAccessionNumber": [None],
        }}
    }


def _stored_manifest(root: Path, slot: int, *, form: str = "8-K", accepted: str | None = ACCEPTED) -> tuple[dict, str]:
    cik = f"{slot:010d}"
    accession = f"000000000{slot % 10}-26-{slot:06d}"
    manifest = build_filing_manifests(_submission(accession, form=form, accepted=accepted), cik=cik, ticker=f"T{slot}", recorded_at=RECORDED)[0]
    inventory = documents_from_archive_index(
        manifest,
        {"directory": {"item": [
            {"name": "primary.htm"}, {"name": "matched.htm"},
        ]}},
    )
    expanded = with_archive_documents(manifest, inventory)
    matched = next(
        document for document in expanded["documents"]
        if document["document_name"] == "matched.htm"
    )
    receipt = persist_archive_document(
        root, matched, f"matched-source-{slot}".encode(), retrieved_at=RECORDED
    )
    stored = with_document_retrievals(
        expanded, {matched["document_id"]: receipt.to_dict()}
    )
    return stored, persist_filing_manifest(root, stored)


def _panel(root: Path) -> tuple[list[CanonicalSpineRef], list[dict]]:
    refs, manifests = [], []
    for slot in range(1, 21):
        manifest, key = _stored_manifest(root, slot)
        refs.append(CanonicalSpineRef(
            slot, manifest["issuer"]["cik"], manifest["filing"]["accession"],
            manifest["filing"]["base_form"], manifest["clocks"]["filed_on"],
            ("matched.htm",), key,
        ))
        manifests.append(manifest)
    return refs, manifests


def test_returns_twenty_verbatim_owner_packets_and_never_writes(tmp_path: Path) -> None:
    refs, manifests = _panel(tmp_path)
    before = {path.relative_to(tmp_path): path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    result = read_exact_p0_source_packets(archive_root=tmp_path, refs=refs)
    after = {path.relative_to(tmp_path): path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    assert result.complete and not result.gaps and len(result.packets) == 20
    assert before == after
    first, owner = result.packets[0], manifests[0]
    assert first.manifest_id == owner["manifest_id"]
    assert first.clocks == owner["clocks"]
    assert first.clocks["accepted_at"] == "2026-08-20T15:30:00.000000Z"
    matched = next(
        document for document in owner["documents"]
        if document["document_name"] == "matched.htm"
    )
    assert first.matched_documents == (matched,)
    assert first.source_documents == (b"matched-source-1",)


def test_atomically_refuses_absent_historical_owner_reference(tmp_path: Path) -> None:
    refs, _ = _panel(tmp_path)
    refs[7] = CanonicalSpineRef(
        8, refs[7].cik, refs[7].accession, refs[7].expected_base_form,
        refs[7].expected_filed_on, refs[7].expected_document_names, None,
    )
    result = read_exact_p0_source_packets(archive_root=tmp_path, refs=refs)
    assert result.packets == ()
    assert [(gap.slot, gap.code) for gap in result.gaps] == [(8, "OWNER_CAPABILITY_GAP")]


def test_crosswire_tamper_and_amendment_are_typed_gaps(tmp_path: Path) -> None:
    refs, _ = _panel(tmp_path)
    refs[0] = CanonicalSpineRef(
        1, "9999999999", refs[0].accession, refs[0].expected_base_form,
        refs[0].expected_filed_on, refs[0].expected_document_names,
        refs[0].manifest_storage_key,
    )
    result = read_exact_p0_source_packets(archive_root=tmp_path, refs=refs)
    assert result.packets == () and result.gaps[0].code == "OWNER_IDENTITY_MISMATCH"

    refs, _ = _panel(tmp_path / "tamper")
    path = tmp_path / "tamper" / refs[0].manifest_storage_key
    path.write_bytes(b"{}")
    result = read_exact_p0_source_packets(archive_root=tmp_path / "tamper", refs=refs)
    assert result.packets == () and result.gaps[0].code == "OWNER_MANIFEST_INVALID"

    refs, manifests = _panel(tmp_path / "amend")
    amended, key = _stored_manifest(tmp_path / "amend", 21, form="8-K/A")
    refs[0] = CanonicalSpineRef(
        1, amended["issuer"]["cik"], amended["filing"]["accession"],
        amended["filing"]["base_form"], amended["clocks"]["filed_on"],
        ("matched.htm",), key,
    )
    result = read_exact_p0_source_packets(archive_root=tmp_path / "amend", refs=refs)
    assert result.packets == () and result.gaps[0].code == "OWNER_AMENDMENT_ORIGIN_REFUSED"


def test_cardinality_and_exact_acceptance_fail_closed(tmp_path: Path) -> None:
    refs, _ = _panel(tmp_path)
    result = read_exact_p0_source_packets(archive_root=tmp_path, refs=refs[:19])
    assert result.packets == () and result.gaps[0].code == "EXACT_CARDINALITY_UNSATISFIED"

    refs, _ = _panel(tmp_path / "clock")
    missing_clock, key = _stored_manifest(tmp_path / "clock", 21, accepted=None)
    refs[0] = CanonicalSpineRef(
        1, missing_clock["issuer"]["cik"], missing_clock["filing"]["accession"],
        missing_clock["filing"]["base_form"], missing_clock["clocks"]["filed_on"],
        ("matched.htm",), key,
    )
    result = read_exact_p0_source_packets(archive_root=tmp_path / "clock", refs=refs)
    assert result.packets == () and result.gaps[0].code == "OWNER_EXACT_ACCEPTANCE_ABSENT"


def test_frozen_base_form_and_filed_on_must_match_owner(tmp_path: Path) -> None:
    refs, _ = _panel(tmp_path)
    refs[0] = CanonicalSpineRef(
        1, refs[0].cik, refs[0].accession, "6-K",
        refs[0].expected_filed_on, refs[0].expected_document_names,
        refs[0].manifest_storage_key,
    )
    result = read_exact_p0_source_packets(archive_root=tmp_path, refs=refs)
    assert result.packets == () and result.gaps[0].code == "OWNER_IDENTITY_MISMATCH"

    refs, _ = _panel(tmp_path / "filed")
    refs[0] = CanonicalSpineRef(
        1, refs[0].cik, refs[0].accession, refs[0].expected_base_form,
        "2026-08-19", refs[0].expected_document_names,
        refs[0].manifest_storage_key,
    )
    result = read_exact_p0_source_packets(archive_root=tmp_path / "filed", refs=refs)
    assert result.packets == () and result.gaps[0].code == "OWNER_IDENTITY_MISMATCH"


def test_filing_cover_cannot_replace_missing_fts_exhibit(tmp_path: Path) -> None:
    refs, _ = _panel(tmp_path)
    refs[0] = CanonicalSpineRef(
        1, refs[0].cik, refs[0].accession, refs[0].expected_base_form,
        refs[0].expected_filed_on, ("absent-exhibit.htm",),
        refs[0].manifest_storage_key,
    )
    result = read_exact_p0_source_packets(archive_root=tmp_path, refs=refs)
    assert result.packets == ()
    assert result.gaps[0].code == "OWNER_FTS_DOCUMENT_NOT_IN_INDEX"
