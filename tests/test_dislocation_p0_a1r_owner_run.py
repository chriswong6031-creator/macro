from __future__ import annotations

from dataclasses import replace
import gzip
from hashlib import sha256
import json
from pathlib import Path

import pytest

from collectors.edgar_forensics import persist_response
from collectors.sec_document_spine import persist_archive_document, persist_filing_manifest
from engine.fundamental_forensics.sec_document_spine import (
    build_filing_manifests,
    documents_from_archive_index,
    with_archive_documents,
    with_document_retrievals,
)
from scripts.research.dislocation_p0_a1r_owner_run import (
    OwnerRunBlocked,
    _fts_document_names,
    _packet_views_from_owner_packets,
    _replay_generic_source_receipt,
    execute_owner_replay,
)
from scripts.research.dislocation_p0_a1_lib import canonical_json, sha256_text
from scripts.research.dislocation_p0_source_adapter import (
    CanonicalSpineRef,
    read_exact_p0_source_packets,
)


def test_replays_persisted_generic_owner_sidecar_not_ephemeral_receipt(
    tmp_path: Path,
) -> None:
    content = json.dumps({"filings": {"recent": {}}}).encode()
    persisted = persist_response(
        tmp_path,
        cik="1",
        endpoint="submissions",
        url="https://data.sec.gov/submissions/CIK0000000001.json",
        content=content,
        retrieved_at="2026-08-22T10:00:00Z",
    )
    ephemeral = replace(persisted, retrieved_at="2026-08-22T11:00:00Z")
    raw, sidecar, storage_key, sidecar_sha = _replay_generic_source_receipt(
        tmp_path, ephemeral
    )
    sidecar_bytes = (tmp_path / storage_key).read_bytes()
    assert raw == content
    assert sidecar["retrieved_at"] == "2026-08-22T10:00:00Z"
    assert sidecar_sha == sha256(sidecar_bytes).hexdigest()


def test_replay_rejects_corrupt_generic_owner_object(tmp_path: Path) -> None:
    content = b'{"filings":{}}'
    receipt = persist_response(
        tmp_path,
        cik="1",
        endpoint="submissions",
        url="https://data.sec.gov/submissions/CIK0000000001.json",
        content=content,
        retrieved_at="2026-08-22T10:00:00Z",
    )
    with gzip.open(tmp_path / receipt.object_path, "wb") as handle:
        handle.write(content + b"corrupt")
    with pytest.raises(OwnerRunBlocked, match="receipt replay failed"):
        _replay_generic_source_receipt(tmp_path, receipt)


def test_fts_hit_id_must_bind_accession_and_exact_matched_document() -> None:
    candidate = {
        "accession": "0000000001-26-000001",
        "query_edges": [{
            "hit_id": "0000000001-26-000001:exhibit99.htm",
            "filename": "exhibit99.htm",
            "query_receipt_sha256": "a" * 64,
        }],
    }
    assert _fts_document_names(candidate) == ("exhibit99.htm",)
    crosswired = json.loads(json.dumps(candidate))
    crosswired["query_edges"][0]["hit_id"] = (
        "0000000001-26-999999:exhibit99.htm"
    )
    with pytest.raises(OwnerRunBlocked, match="crosswire"):
        _fts_document_names(crosswired)
    substituted = json.loads(json.dumps(candidate))
    substituted["query_edges"][0]["filename"] = "primary.htm"
    with pytest.raises(OwnerRunBlocked, match="crosswire"):
        _fts_document_names(substituted)


def _offline_replay_fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Build a small but complete owner archive without any network transport."""
    workspace = tmp_path / "workspace"
    owner_root = workspace / "canonical_owner_archive"
    generic_root = workspace / "generic_sec_source"
    rows: list[dict] = []
    refs: list[CanonicalSpineRef] = []
    receipt_rows: list[dict] = []
    recorded_at = "2026-08-22T12:00:00Z"
    for slot in range(1, 21):
        cik = f"{slot:010d}"
        accession = f"000000000{slot % 10}-26-{slot:06d}"
        submission = {
            "filings": {"recent": {
                "accessionNumber": [accession], "form": ["8-K"],
                "filingDate": ["2026-08-20"], "reportDate": ["2026-08-19"],
                "acceptanceDateTime": ["2026-08-20T15:30:00.000Z"],
                "primaryDocument": ["filing-cover.htm"], "isXBRL": [False],
                "isInlineXBRL": [False], "items": ["8.01"],
                "amendsAccessionNumber": [None],
            }}
        }
        manifest = build_filing_manifests(
            submission, cik=cik, ticker=None, recorded_at=recorded_at
        )[0]
        inventory = documents_from_archive_index(manifest, {
            "directory": {"item": [{"name": "filing-cover.htm"}, {"name": "fts-exhibit.htm"}]}
        })
        expanded = with_archive_documents(manifest, inventory)
        matched = next(document for document in expanded["documents"] if document["document_name"] == "fts-exhibit.htm")
        receipt = persist_archive_document(
            owner_root, matched, f"matched-{slot}".encode(), retrieved_at=recorded_at
        )
        retained = with_document_retrievals(
            expanded, {matched["document_id"]: receipt.to_dict()}
        )
        key = persist_filing_manifest(owner_root, retained)
        edge = {
            "family_candidate": "PHYSICAL_MECHANICAL_INTERRUPTION",
            "filename": "fts-exhibit.htm",
            "hit_id": f"{accession}:fts-exhibit.htm",
            "phrase": "equipment failure",
            "query_cell_id": f"cell-{slot}",
            "query_receipt_sha256": f"{slot:064x}",
        }
        rows.append({
            "slot": slot,
            "packet_id": f"packet-{slot}",
            "selection_key": f"selection-{slot:02d}",
            "retrieval_family": "PHYSICAL_MECHANICAL_INTERRUPTION",
            "query_edges": [edge],
            "manifest_storage_key": key,
            "manifest_id": retained["manifest_id"],
            "filing_id": retained["filing_id"],
            "issuer": retained["issuer"],
            "filing": retained["filing"],
            "clocks": retained["clocks"],
            "lineage": retained["lineage"],
            "matched_documents": [next(
                document for document in retained["documents"]
                if document["document_name"] == "fts-exhibit.htm"
            )],
        })
        refs.append(CanonicalSpineRef(
            slot, cik, accession, retained["filing"]["base_form"],
            retained["clocks"]["filed_on"], ("fts-exhibit.htm",), key,
        ))
        generic = persist_response(
            generic_root, cik=cik, endpoint="submissions",
            url=f"https://data.sec.gov/submissions/CIK{cik}.json",
            content=canonical_json(submission).encode(), retrieved_at=recorded_at,
        )
        receipt_path = generic_root / Path(generic.object_path).with_suffix(".receipt.json")
        receipt_rows.append({
            "owner": "collectors.edgar_forensics.SecForensicsCollector",
            "receipt_storage_key": Path(generic.object_path).with_suffix(".receipt.json").as_posix(),
            "receipt_file_sha256": sha256(receipt_path.read_bytes()).hexdigest(),
            "receipt": json.loads(receipt_path.read_text()),
        })
    packets = read_exact_p0_source_packets(archive_root=owner_root, refs=refs)
    assert packets.complete
    public, model, sources, _hosts = _packet_views_from_owner_packets(
        frozen_rows=rows, packets=packets.packets
    )
    assert public == rows
    packet_root = workspace / "source_packets"
    for relative, content in sources.items():
        target = packet_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    index = {"schema": "mastermind.dislocation_p0.a1r_model_packet_index.v2", "packets": model}
    index_path = packet_root / "packet_index.json"
    index_path.write_text(canonical_json(index) + "\n")
    manifest = {
        "schema": "mastermind.dislocation_p0.a1r_canonical_source_packets.v2",
        "status": "COMPLETE",
        "source_selection_manifest_sha256": "a" * 64,
        "source_selection_file_sha256": "b" * 64,
        "recorded_at": recorded_at,
        "submissions_transport_receipts": receipt_rows,
        "firewall": {"forbidden_dirs_present": [], "official_sec_hosts": ["data.sec.gov", "www.sec.gov"]},
        "authority": {"can_rank": False, "can_gate": False, "can_size": False, "can_originate_signal": False, "can_escalate": False},
        "n": 20,
        "packets": rows,
    }
    manifest["manifest_sha256"] = sha256_text(canonical_json(manifest))
    manifest_path = tmp_path / "frozen-manifest.json"
    manifest_path.write_text(canonical_json(manifest) + "\n")
    return manifest_path, workspace, index_path


def test_offline_owner_replay_rebuilds_bytes_and_rejects_packet_mutation(
    tmp_path: Path,
) -> None:
    manifest_path, workspace, index_path = _offline_replay_fixture(tmp_path)
    replay_out = tmp_path / "replay-out"
    proof = execute_owner_replay(
        frozen_manifest_path=manifest_path,
        workspace=workspace,
        replay_out=replay_out,
        packet_index_path=index_path,
    )
    assert proof["status"] == "COMPLETE_BYTE_IDENTICAL"
    assert proof["network_access"] == "NONE"
    assert proof["document_count"] == 20
    assert (replay_out / "source_packets" / "packet_index.json").read_bytes() == index_path.read_bytes()
    source_file = next((workspace / "source_packets" / "packets").glob("*.source"))
    source_file.write_bytes(b"tampered")
    with pytest.raises(OwnerRunBlocked, match="source packet bytes are not identical"):
        execute_owner_replay(
            frozen_manifest_path=manifest_path,
            workspace=workspace,
            replay_out=tmp_path / "tampered-replay",
            packet_index_path=index_path,
        )
