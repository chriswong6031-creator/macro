#!/usr/bin/env python3
"""Materialize the frozen A1R twenty through canonical SEC owner primitives."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from collectors.edgar_forensics import RetrievalReceipt, SecForensicsCollector  # noqa: E402
from scripts.research.dislocation_p0_a1_lib import (  # noqa: E402
    ALLOWED_HOSTS,
    assert_blind_workspace,
    canonical_json,
    forbidden_market_fields,
    sha256_text,
)
from scripts.research.dislocation_p0_source_adapter import (  # noqa: E402
    CanonicalSpineRef,
    read_exact_p0_source_packets,
)
from scripts.research.dislocation_p0_source_materializer import (  # noqa: E402
    materialize_current_p0_source_refs,
)


OWNER_MANIFEST_NAME = "A1R_CANONICAL_SOURCE_PACKET_MANIFEST.json"
OWNER_GAP_NAME = "A1R_CANONICAL_OWNER_GAP.json"
USER_AGENT = "MastermindX dislocation-p0-a1r research@mastermind-x.com"
CURRENT_SUBMISSIONS_MAX_BYTES = 8 * 1024 * 1024


class OwnerRunBlocked(RuntimeError):
    """The frozen selection cannot be replayed through canonical owners."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with Path(path).open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(canonical_json(value) + "\n", encoding="utf-8")
    temporary.replace(path)


def _replay_generic_source_receipt(
    root: Path,
    receipt: RetrievalReceipt,
) -> tuple[bytes, Mapping[str, Any], str, str]:
    """Replay the exact persisted generic-owner sidecar and bounded object."""
    receipt_storage_key = Path(receipt.object_path).with_suffix(
        ".receipt.json"
    ).as_posix()
    receipt_path = Path(root) / receipt_storage_key
    receipt_bytes = receipt_path.read_bytes()
    stored_receipt = json.loads(receipt_bytes.decode("utf-8"))
    if not isinstance(stored_receipt, Mapping) or any(
        stored_receipt.get(field) != getattr(receipt, field)
        for field in (
            "schema",
            "cik",
            "endpoint",
            "url",
            "sha256",
            "bytes",
            "object_path",
        )
    ):
        raise OwnerRunBlocked(
            f"canonical generic-SEC receipt mismatch: {receipt.cik}"
        )
    expected_bytes = stored_receipt.get("bytes")
    if (
        isinstance(expected_bytes, bool)
        or not isinstance(expected_bytes, int)
        or expected_bytes < 1
        or expected_bytes > CURRENT_SUBMISSIONS_MAX_BYTES
    ):
        raise OwnerRunBlocked(
            f"canonical generic-SEC receipt length invalid: {receipt.cik}"
        )
    object_path = Path(root) / str(stored_receipt["object_path"])
    with gzip.open(object_path, "rb") as handle:
        raw = handle.read(expected_bytes + 1)
    if (
        len(raw) != expected_bytes
        or sha256(raw).hexdigest() != stored_receipt["sha256"]
    ):
        raise OwnerRunBlocked(
            f"canonical generic-SEC receipt replay failed: {receipt.cik}"
        )
    return (
        raw,
        stored_receipt,
        receipt_storage_key,
        sha256(receipt_bytes).hexdigest(),
    )


def _validate_selection(value: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    body = dict(value)
    claimed = body.pop("manifest_sha256", None)
    if claimed != sha256_text(canonical_json(body)):
        raise OwnerRunBlocked("exact-twenty selection manifest hash mismatch")
    candidates = value.get("candidates")
    if (
        value.get("n") != 20
        or not isinstance(candidates, list)
        or len(candidates) != 20
    ):
        raise OwnerRunBlocked("exact-twenty selection cardinality mismatch")
    keys = [str(row.get("selection_key") or "") for row in candidates]
    if keys != sorted(keys) or len(set(keys)) != 20:
        raise OwnerRunBlocked("exact-twenty selection order/identity mismatch")
    identities = [
        (str(row.get("cik") or ""), str(row.get("accession") or ""))
        for row in candidates
    ]
    if len(set(identities)) != 20 or any(not all(identity) for identity in identities):
        raise OwnerRunBlocked("exact-twenty CIK/accession identity mismatch")
    for row in candidates:
        _fts_document_names(row)
    return candidates


def _fts_document_names(candidate: Mapping[str, Any]) -> tuple[str, ...]:
    """Validate and return every exact SEC FTS-matched archive member."""
    accession = str(candidate.get("accession") or "")
    edges = candidate.get("query_edges")
    if not isinstance(edges, list) or not edges:
        raise OwnerRunBlocked(f"candidate has no FTS query edges: {accession}")
    names: set[str] = set()
    for edge in edges:
        if not isinstance(edge, Mapping):
            raise OwnerRunBlocked(f"candidate has malformed FTS query edge: {accession}")
        hit_id = edge.get("hit_id")
        filename = edge.get("filename")
        query_receipt = edge.get("query_receipt_sha256")
        if not all(isinstance(value, str) and value for value in (hit_id, filename, query_receipt)):
            raise OwnerRunBlocked(f"candidate FTS edge identity is incomplete: {accession}")
        hit_accession, separator, hit_filename = hit_id.partition(":")
        if separator != ":" or hit_accession != accession or hit_filename != filename:
            raise OwnerRunBlocked(
                f"candidate FTS hit/document crosswire: {accession}:{filename}"
            )
        names.add(filename)
    if not names:
        raise OwnerRunBlocked(f"candidate has no exact FTS document: {accession}")
    return tuple(sorted(names))


def _validated_frozen_owner_manifest(path: Path) -> Mapping[str, Any]:
    """Load a v2 owner manifest without treating it as an owner of bytes.

    The frozen manifest is allowed to supply only the immutable *run receipt*
    fields (notably ``recorded_at`` and the generic-SEC transport sidecars).
    Filing/document identities and every source byte are rebuilt below from the
    SEC document-spine archive.
    """
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise OwnerRunBlocked(f"frozen owner manifest is unreadable: {exc}") from exc
    if not isinstance(value, Mapping):
        raise OwnerRunBlocked("frozen owner manifest must be an object")
    body = dict(value)
    claimed = body.pop("manifest_sha256", None)
    if claimed != sha256_text(canonical_json(body)):
        raise OwnerRunBlocked("frozen owner manifest logical SHA mismatch")
    if (
        value.get("schema") != "mastermind.dislocation_p0.a1r_canonical_source_packets.v2"
        or value.get("status") != "COMPLETE"
        or value.get("n") != 20
        or not isinstance(value.get("packets"), list)
        or len(value["packets"]) != 20
    ):
        raise OwnerRunBlocked("frozen owner manifest state/cardinality mismatch")
    if forbidden_market_fields(value):
        raise OwnerRunBlocked("frozen owner manifest contains forbidden fields")
    return value


def _refs_from_frozen_owner_manifest(
    frozen: Mapping[str, Any],
) -> tuple[list[CanonicalSpineRef], list[Mapping[str, Any]]]:
    """Reconstruct references from the frozen FTS packet projection.

    This intentionally takes the document names from the FTS query edges and
    requires the frozen projection to agree; it has no primary-document branch.
    """
    rows = frozen["packets"]
    if not all(isinstance(row, Mapping) for row in rows):
        raise OwnerRunBlocked("frozen owner manifest packet is malformed")
    ordered = sorted(rows, key=lambda row: int(row.get("slot") or 0))
    refs: list[CanonicalSpineRef] = []
    slots: set[int] = set()
    pairs: set[tuple[str, str]] = set()
    for row in ordered:
        slot = row.get("slot")
        filing = row.get("filing")
        issuer = row.get("issuer")
        if (
            isinstance(slot, bool)
            or not isinstance(slot, int)
            or not isinstance(filing, Mapping)
            or not isinstance(issuer, Mapping)
        ):
            raise OwnerRunBlocked("frozen owner manifest packet identity is malformed")
        cik = str(issuer.get("cik") or "")
        accession = str(filing.get("accession") or "")
        base_form = str(filing.get("base_form") or "")
        filed_on = row.get("clocks", {}).get("filed_on") if isinstance(row.get("clocks"), Mapping) else None
        names = _fts_document_names({
            "accession": accession,
            "query_edges": row.get("query_edges"),
        })
        frozen_documents = row.get("matched_documents")
        if not isinstance(frozen_documents, list):
            raise OwnerRunBlocked(f"frozen matched-documents projection missing: slot {slot}")
        frozen_names = tuple(sorted(
            str(document.get("document_name") or "")
            for document in frozen_documents
            if isinstance(document, Mapping)
        ))
        if len(frozen_names) != len(frozen_documents) or frozen_names != names:
            raise OwnerRunBlocked(
                f"frozen FTS matched-document projection drift: slot {slot}"
            )
        if slot in slots or (cik, accession) in pairs:
            raise OwnerRunBlocked("frozen owner manifest contains duplicate packet identity")
        slots.add(slot)
        pairs.add((cik, accession))
        storage_key = row.get("manifest_storage_key")
        if not all(isinstance(value, str) and value for value in (cik, accession, base_form, storage_key)):
            raise OwnerRunBlocked(f"frozen owner manifest packet reference missing: slot {slot}")
        refs.append(CanonicalSpineRef(
            slot=slot,
            cik=cik,
            accession=accession,
            expected_base_form=base_form,
            expected_filed_on=filed_on if isinstance(filed_on, str) else None,
            expected_document_names=names,
            manifest_storage_key=storage_key,
        ))
    if slots != set(range(1, 21)):
        raise OwnerRunBlocked("frozen owner manifest slots are not exactly 1..20")
    return refs, ordered


def _packet_views_from_owner_packets(
    *,
    frozen_rows: Sequence[Mapping[str, Any]],
    packets: Sequence[Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, bytes], set[str]]:
    """Build fresh public/model packet views and source bytes from owner packets."""
    public_packets: list[dict[str, Any]] = []
    model_packets: list[dict[str, Any]] = []
    source_files: dict[str, bytes] = {}
    source_hosts: set[str] = set()
    for frozen_row, packet in zip(frozen_rows, packets):
        if packet.slot != frozen_row.get("slot"):
            raise OwnerRunBlocked("canonical owner packet slot ordering drift")
        packet_id = frozen_row.get("packet_id")
        selection_key = frozen_row.get("selection_key")
        family = frozen_row.get("retrieval_family")
        query_edges = frozen_row.get("query_edges")
        if not all(isinstance(value, str) and value for value in (packet_id, selection_key, family)) or not isinstance(query_edges, list):
            raise OwnerRunBlocked(f"frozen packet provenance missing: slot {packet.slot}")
        model_documents: list[dict[str, Any]] = []
        for document, source_bytes in zip(packet.matched_documents, packet.source_documents):
            document_id = str(document.get("document_id") or "")
            if not document_id:
                raise OwnerRunBlocked(f"canonical owner document id missing: slot {packet.slot}")
            source_name = f"{packet.slot:02d}_{document_id}.source"
            source_path = f"packets/{source_name}"
            if source_path in source_files:
                raise OwnerRunBlocked(f"canonical owner source path collision: {source_path}")
            source_files[source_path] = source_bytes
            model_documents.append({
                "document_id": document_id,
                "document_name": document["document_name"],
                "document_sha256": document["content_sha256"],
                "byte_length": document["byte_length"],
                "source_path": source_path,
            })
            source_hosts.add((urlparse(document["archive_url"]).hostname or "").lower())
        public_packets.append({
            "slot": packet.slot,
            "packet_id": packet_id,
            "selection_key": selection_key,
            "retrieval_family": family,
            "query_edges": query_edges,
            "manifest_storage_key": packet.manifest_storage_key,
            "manifest_id": packet.manifest_id,
            "filing_id": packet.filing_id,
            "issuer": packet.issuer,
            "filing": packet.filing,
            "clocks": packet.clocks,
            "lineage": packet.lineage,
            "matched_documents": list(packet.matched_documents),
        })
        model_packets.append({
            "slot": packet.slot,
            "packet_id": packet_id,
            "cik": packet.issuer["cik"],
            "accession": packet.filing["accession"],
            "accepted_at": packet.clocks["accepted_at"],
            "filed_on": packet.clocks["filed_on"],
            "documents": model_documents,
        })
    return public_packets, model_packets, source_files, source_hosts


def _replay_submission_transport_receipts(
    *, frozen: Mapping[str, Any], generic_sec_root: Path, expected_ciks: set[str]
) -> tuple[list[dict[str, Any]], set[str]]:
    """Verify persisted broad-SEC receipts without calling the SEC network."""
    entries = frozen.get("submissions_transport_receipts")
    if not isinstance(entries, list) or not entries:
        raise OwnerRunBlocked("frozen generic-SEC transport receipts are missing")
    replayed: list[dict[str, Any]] = []
    seen: set[str] = set()
    hosts: set[str] = set()
    for entry in entries:
        if not isinstance(entry, Mapping) or entry.get("owner") != "collectors.edgar_forensics.SecForensicsCollector":
            raise OwnerRunBlocked("frozen generic-SEC transport receipt owner mismatch")
        receipt_value = entry.get("receipt")
        if not isinstance(receipt_value, Mapping):
            raise OwnerRunBlocked("frozen generic-SEC transport receipt missing")
        try:
            receipt = RetrievalReceipt(**dict(receipt_value))
        except TypeError as exc:
            raise OwnerRunBlocked(f"frozen generic-SEC transport receipt malformed: {exc}") from exc
        if receipt.endpoint != "submissions" or receipt.cik not in expected_ciks or receipt.cik in seen:
            raise OwnerRunBlocked("frozen generic-SEC transport receipt CIK coverage mismatch")
        _raw, stored, storage_key, receipt_sha = _replay_generic_source_receipt(
            generic_sec_root, receipt
        )
        rebuilt = {
            "owner": "collectors.edgar_forensics.SecForensicsCollector",
            "receipt_storage_key": storage_key,
            "receipt_file_sha256": receipt_sha,
            "receipt": stored,
        }
        if canonical_json(rebuilt) != canonical_json(entry):
            raise OwnerRunBlocked(
                f"frozen generic-SEC transport receipt projection drift: {receipt.cik}"
            )
        seen.add(receipt.cik)
        hosts.add((urlparse(receipt.url).hostname or "").lower())
        replayed.append(rebuilt)
    if seen != expected_ciks:
        raise OwnerRunBlocked("frozen generic-SEC transport receipt coverage is incomplete")
    return replayed, hosts


def execute_owner_replay(
    *,
    frozen_manifest_path: Path,
    workspace: Path,
    replay_out: Path,
    packet_index_path: Path | None = None,
) -> dict[str, Any]:
    """Prove a frozen v2 packet set is reproducible offline from owner records.

    The function does not construct a collector and performs no network I/O.
    It reads retained document-spine manifests/receipts and persisted broad-SEC
    sidecars, reserializes the public/model packet artifacts, and compares every
    regenerated byte with the frozen result before writing a separately-named
    replay proof tree.
    """
    workspace = Path(workspace)
    replay_out = Path(replay_out)
    frozen_manifest_path = Path(frozen_manifest_path)
    forbidden_dirs = assert_blind_workspace(workspace)
    if assert_blind_workspace(replay_out):
        raise OwnerRunBlocked("replay output workspace violates source-only firewall")
    frozen = _validated_frozen_owner_manifest(frozen_manifest_path)
    refs, frozen_rows = _refs_from_frozen_owner_manifest(frozen)
    packets = read_exact_p0_source_packets(
        archive_root=workspace / "canonical_owner_archive", refs=refs
    )
    if not packets.complete:
        raise OwnerRunBlocked(canonical_json({
            "code": "CANONICAL_OWNER_REPLAY_FAILED",
            "gaps": [item.__dict__ for item in packets.gaps],
        }))
    public_packets, model_packets, source_files, document_hosts = _packet_views_from_owner_packets(
        frozen_rows=frozen_rows, packets=packets.packets
    )
    if canonical_json(public_packets) != canonical_json(frozen_rows):
        raise OwnerRunBlocked("canonical owner manifest packet projection drift")
    receipt_rows, receipt_hosts = _replay_submission_transport_receipts(
        frozen=frozen,
        generic_sec_root=workspace / "generic_sec_source",
        expected_ciks={ref.cik for ref in refs},
    )
    source_hosts = document_hosts | receipt_hosts
    if not source_hosts or not source_hosts.issubset(ALLOWED_HOSTS):
        raise OwnerRunBlocked(f"non-SEC replay source host observed: {sorted(source_hosts)}")
    if frozen.get("firewall", {}).get("official_sec_hosts") != sorted(source_hosts):
        raise OwnerRunBlocked("frozen owner firewall host projection drift")

    regenerated_index = {
        "schema": "mastermind.dislocation_p0.a1r_model_packet_index.v2",
        "packets": model_packets,
    }
    index_bytes = (canonical_json(regenerated_index) + "\n").encode("utf-8")
    expected_index = Path(packet_index_path or workspace / "source_packets" / "packet_index.json")
    if expected_index.read_bytes() != index_bytes:
        raise OwnerRunBlocked("model packet index is not byte-identical on offline replay")
    expected_source_root = expected_index.parent
    expected_paths = set(source_files)
    actual_paths = {
        path.relative_to(expected_source_root).as_posix()
        for path in (expected_source_root / "packets").glob("*.source")
    }
    if actual_paths != expected_paths:
        raise OwnerRunBlocked("source packet file inventory drift on offline replay")
    for relative, source_bytes in source_files.items():
        if (expected_source_root / relative).read_bytes() != source_bytes:
            raise OwnerRunBlocked(f"source packet bytes are not identical on offline replay: {relative}")

    rebuilt = {
        "schema": frozen["schema"],
        "status": frozen["status"],
        "source_selection_manifest_sha256": frozen["source_selection_manifest_sha256"],
        "source_selection_file_sha256": frozen["source_selection_file_sha256"],
        # Keep the original run's clock and transport receipts: a replay must
        # not mint a new collection time merely to make a hash look fresh.
        "recorded_at": frozen["recorded_at"],
        "submissions_transport_receipts": receipt_rows,
        "firewall": {
            "forbidden_dirs_present": forbidden_dirs,
            "official_sec_hosts": sorted(source_hosts),
        },
        "authority": frozen["authority"],
        "n": 20,
        "packets": public_packets,
    }
    rebuilt["manifest_sha256"] = sha256_text(canonical_json(rebuilt))
    rebuilt_bytes = (canonical_json(rebuilt) + "\n").encode("utf-8")
    if frozen_manifest_path.read_bytes() != rebuilt_bytes:
        raise OwnerRunBlocked("canonical source manifest is not byte-identical on offline replay")

    for relative, source_bytes in source_files.items():
        output = replay_out / "source_packets" / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(source_bytes)
    _write_json(replay_out / "source_packets" / "packet_index.json", regenerated_index)
    _write_json(replay_out / OWNER_MANIFEST_NAME, rebuilt)
    proof = {
        "schema": "mastermind.dislocation_p0.a1r_canonical_owner_replay_proof.v1",
        "status": "COMPLETE_BYTE_IDENTICAL",
        "network_access": "NONE",
        "frozen_manifest_path": str(frozen_manifest_path),
        "frozen_manifest_sha256": frozen["manifest_sha256"],
        "replayed_manifest_sha256": rebuilt["manifest_sha256"],
        "model_packet_index_sha256": sha256(index_bytes).hexdigest(),
        "packet_count": len(model_packets),
        "document_count": len(source_files),
        "source_file_sha256": {
            relative: sha256(source_bytes).hexdigest()
            for relative, source_bytes in sorted(source_files.items())
        },
        "official_sec_hosts": sorted(source_hosts),
        "forbidden_dirs_present": forbidden_dirs,
    }
    _write_json(replay_out / "A1R_CANONICAL_OWNER_REPLAY_PROOF.json", proof)
    return proof


def execute_owner_run(
    *,
    selection_path: Path,
    workspace: Path,
    public_out: Path,
) -> dict[str, Any]:
    workspace = Path(workspace)
    public_out = Path(public_out)
    selection_path = Path(selection_path)
    forbidden_dirs = assert_blind_workspace(workspace)
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    if not isinstance(selection, Mapping):
        raise OwnerRunBlocked("exact-twenty selection must be an object")
    candidates = _validate_selection(selection)
    refs = [
        CanonicalSpineRef(
            slot=slot,
            cik=str(row["cik"]),
            accession=str(row["accession"]),
            expected_base_form=str(row["base_form"]),
            expected_filed_on=str(row["filed_on"]),
            expected_document_names=_fts_document_names(row),
            manifest_storage_key=None,
        )
        for slot, row in enumerate(candidates, start=1)
    ]

    owner_root = workspace / "canonical_owner_archive"
    broad_source_root = workspace / "generic_sec_source"
    source_collector = SecForensicsCollector(
        broad_source_root,
        user_agent=USER_AGENT,
        max_response_bytes=CURRENT_SUBMISSIONS_MAX_BYTES,
    )
    submission_receipts: list[dict[str, Any]] = []

    def fetch_with_receipt(cik: str) -> tuple[bytes, Mapping[str, str | None]]:
        receipt = source_collector.fetch(
            cik,
            "submissions",
            max_response_bytes=CURRENT_SUBMISSIONS_MAX_BYTES,
        )
        raw, stored_receipt, receipt_storage_key, receipt_file_sha256 = (
            _replay_generic_source_receipt(broad_source_root, receipt)
        )
        submission_receipts.append({
            "owner": "collectors.edgar_forensics.SecForensicsCollector",
            "receipt_storage_key": receipt_storage_key,
            "receipt_file_sha256": receipt_file_sha256,
            "receipt": stored_receipt,
        })
        return raw, {
            "url": receipt.url,
            "http_etag": receipt.http_etag,
            "http_last_modified": receipt.http_last_modified,
        }

    recorded_at = _utc_now()
    result = materialize_current_p0_source_refs(
        archive_root=owner_root,
        selections=refs,
        user_agent=USER_AGENT,
        fetch_submissions=fetch_with_receipt,
        recorded_at=recorded_at,
    )
    source_hosts = {
        (urlparse(row["receipt"]["url"]).hostname or "").lower()
        for row in submission_receipts
    }
    if not source_hosts.issubset(ALLOWED_HOSTS):
        raise OwnerRunBlocked(f"non-SEC source host observed: {sorted(source_hosts)}")

    common = {
        "source_selection_manifest_sha256": selection["manifest_sha256"],
        "source_selection_file_sha256": _file_sha256(selection_path),
        "recorded_at": recorded_at,
        "submissions_transport_receipts": submission_receipts,
        "firewall": {
            "forbidden_dirs_present": forbidden_dirs,
            "official_sec_hosts": sorted(source_hosts),
        },
        "authority": {
            "can_rank": False,
            "can_gate": False,
            "can_size": False,
            "can_originate_signal": False,
            "can_escalate": False,
        },
    }
    if result.gaps:
        gap = {
            "schema": "mastermind.dislocation_p0.a1r_owner_gap.v1",
            "status": "BLOCKED_CANONICAL_OWNER_CAPABILITY",
            **common,
            "gaps": [
                {
                    "slot": item.slot,
                    "cik": item.cik,
                    "accession": item.accession,
                    "code": item.code,
                    "detail": item.detail,
                }
                for item in result.gaps
            ],
            "top_up_permitted": False,
            "p0_local_source_fallback_permitted": False,
        }
        if forbidden_market_fields(gap):
            raise OwnerRunBlocked("owner gap artifact contains forbidden fields")
        gap_path = public_out / OWNER_GAP_NAME
        _write_json(gap_path, gap)
        return {
            "status": "BLOCKED",
            "gap_path": str(gap_path),
            "gap_count": len(result.gaps),
            "gap_codes": sorted({item.code for item in result.gaps}),
        }

    packets = read_exact_p0_source_packets(
        archive_root=owner_root, refs=result.refs
    )
    if not packets.complete:
        raise OwnerRunBlocked(canonical_json({
            "code": "CANONICAL_OWNER_REPLAY_FAILED",
            "gaps": [item.__dict__ for item in packets.gaps],
        }))
    packet_dir = workspace / "source_packets" / "packets"
    packet_dir.mkdir(parents=True, exist_ok=True)
    public_packets: list[dict[str, Any]] = []
    model_packets: list[dict[str, Any]] = []
    for candidate, packet in zip(candidates, packets.packets):
        packet_id = str(candidate["candidate_id"])
        model_documents: list[dict[str, Any]] = []
        for document, source_bytes in zip(
            packet.matched_documents, packet.source_documents
        ):
            source_name = f"{packet.slot:02d}_{document['document_id']}.source"
            source_path = packet_dir / source_name
            source_path.write_bytes(source_bytes)
            model_documents.append({
                "document_id": document["document_id"],
                "document_name": document["document_name"],
                "document_sha256": document["content_sha256"],
                "byte_length": document["byte_length"],
                "source_path": f"packets/{source_name}",
            })
        public_packets.append({
            "slot": packet.slot,
            "packet_id": packet_id,
            "selection_key": candidate["selection_key"],
            "retrieval_family": candidate["family"],
            "query_edges": candidate["query_edges"],
            "manifest_storage_key": packet.manifest_storage_key,
            "manifest_id": packet.manifest_id,
            "filing_id": packet.filing_id,
            "issuer": packet.issuer,
            "filing": packet.filing,
            "clocks": packet.clocks,
            "lineage": packet.lineage,
            "matched_documents": list(packet.matched_documents),
        })
        model_packets.append({
            "slot": packet.slot,
            "packet_id": packet_id,
            "cik": packet.issuer["cik"],
            "accession": packet.filing["accession"],
            "accepted_at": packet.clocks["accepted_at"],
            "filed_on": packet.clocks["filed_on"],
            "documents": model_documents,
        })
        source_hosts.update(
            (urlparse(document["archive_url"]).hostname or "").lower()
            for document in packet.matched_documents
        )
    if not source_hosts.issubset(ALLOWED_HOSTS):
        raise OwnerRunBlocked(f"non-SEC owner host observed: {sorted(source_hosts)}")
    _write_json(workspace / "source_packets" / "packet_index.json", {
        "schema": "mastermind.dislocation_p0.a1r_model_packet_index.v2",
        "packets": model_packets,
    })

    owner_manifest = {
        "schema": "mastermind.dislocation_p0.a1r_canonical_source_packets.v2",
        "status": "COMPLETE",
        **common,
        "firewall": {
            "forbidden_dirs_present": forbidden_dirs,
            "official_sec_hosts": sorted(source_hosts),
        },
        "n": 20,
        "packets": public_packets,
    }
    if forbidden_market_fields(owner_manifest):
        raise OwnerRunBlocked("owner packet manifest contains forbidden fields")
    owner_manifest["manifest_sha256"] = sha256_text(canonical_json(owner_manifest))
    manifest_path = public_out / OWNER_MANIFEST_NAME
    _write_json(manifest_path, owner_manifest)
    return {
        "status": "COMPLETE",
        "manifest_path": str(manifest_path),
        "manifest_sha256": owner_manifest["manifest_sha256"],
        "packet_count": 20,
        "document_sha256": [
            document["content_sha256"]
            for row in public_packets
            for document in row["matched_documents"]
        ],
        "official_sec_hosts": sorted(source_hosts),
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--selection", type=Path)
    mode.add_argument("--replay-manifest", type=Path)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--public-out", type=Path)
    parser.add_argument("--replay-out", type=Path)
    parser.add_argument("--packet-index", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.selection:
            if args.public_out is None:
                raise OwnerRunBlocked("--public-out is required with --selection")
            result = execute_owner_run(
                selection_path=args.selection,
                workspace=args.workspace,
                public_out=args.public_out,
            )
        else:
            if args.replay_out is None:
                raise OwnerRunBlocked("--replay-out is required with --replay-manifest")
            result = execute_owner_replay(
                frozen_manifest_path=args.replay_manifest,
                workspace=args.workspace,
                replay_out=args.replay_out,
                packet_index_path=args.packet_index,
            )
    except Exception as exc:  # noqa: BLE001 - one typed CLI blocker.
        print(canonical_json({
            "status": "BLOCKED",
            "blocker": type(exc).__name__,
            "detail": str(exc),
        }))
        return 1
    print(canonical_json(result))
    return 0 if result["status"] == "COMPLETE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
