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
    return candidates


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
        source_name = f"{packet.slot:02d}_{packet.primary_document['document_id']}.source"
        source_path = packet_dir / source_name
        source_path.write_bytes(packet.source_bytes)
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
            "primary_document": packet.primary_document,
        })
        model_packets.append({
            "slot": packet.slot,
            "packet_id": packet_id,
            "cik": packet.issuer["cik"],
            "accession": packet.filing["accession"],
            "accepted_at": packet.clocks["accepted_at"],
            "filed_on": packet.clocks["filed_on"],
            "document_id": packet.primary_document["document_id"],
            "document_sha256": packet.primary_document["content_sha256"],
            "byte_length": packet.primary_document["byte_length"],
            "source_path": f"packets/{source_name}",
        })
        source_hosts.add(
            (urlparse(packet.primary_document["archive_url"]).hostname or "").lower()
        )
    if not source_hosts.issubset(ALLOWED_HOSTS):
        raise OwnerRunBlocked(f"non-SEC owner host observed: {sorted(source_hosts)}")
    _write_json(workspace / "source_packets" / "packet_index.json", {
        "schema": "mastermind.dislocation_p0.a1r_model_packet_index.v1",
        "packets": model_packets,
    })

    owner_manifest = {
        "schema": "mastermind.dislocation_p0.a1r_canonical_source_packets.v1",
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
            row["primary_document"]["content_sha256"] for row in public_packets
        ],
        "official_sec_hosts": sorted(source_hosts),
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--public-out", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = execute_owner_run(
            selection_path=args.selection,
            workspace=args.workspace,
            public_out=args.public_out,
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
