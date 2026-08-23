#!/usr/bin/env python3
"""Materialize or replay S1F's frozen exact-70 through canonical SEC owners.

This is a source-only facade.  Selection remains the frozen exact-70 manifest;
the generic SEC collector owns Submissions transport and the document spine owns
archive identities, receipts, and bytes.  The declared primary document is
optional *context* beside every mandatory exact FTS match, never a substitute.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from collectors.edgar_forensics import (  # noqa: E402
    RetrievalReceipt, SecForensicsCollector, endpoint_url, historical_submissions_url,
)
from scripts.research.dislocation_p0_a1_lib import (  # noqa: E402
    ALLOWED_HOSTS, assert_blind_workspace, canonical_json, forbidden_market_fields,
    sha256_text,
)
from scripts.research.dislocation_p0_a1r_owner_run import (  # noqa: E402
    CURRENT_SUBMISSIONS_MAX_BYTES, OwnerRunBlocked as A1ROwnerRunBlocked,
    _replay_generic_source_receipt,
)
from scripts.research.dislocation_p0_source_adapter import (  # noqa: E402
    CanonicalSpineRef, read_source_packets,
)
from scripts.research.dislocation_p0_source_materializer import (  # noqa: E402
    materialize_current_source_refs,
)
from scripts.research.dislocation_p0_s1f_runner import _selection_logical_hash  # noqa: E402
from scripts.research.dislocation_p0_s1f_selection import (  # noqa: E402
    AUTHORITY, STRATA, selection_margins_ok,
)


REQUIRED_PACKET_COUNT = 70
OWNER_MANIFEST_NAME = "S1F_CANONICAL_SOURCE_PACKET_MANIFEST.json"
OWNER_GAP_NAME = "S1F_CANONICAL_OWNER_GAP.json"
OWNER_REPLAY_NAME = "S1F_CANONICAL_OWNER_REPLAY_PROOF.json"
USER_AGENT = "MastermindX dislocation-p0-s1f research@mastermind-x.com"


class OwnerRunBlocked(RuntimeError):
    """The exact-70 selection cannot be fulfilled by canonical owners."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _digest(value: Any) -> str:
    return sha256_text(canonical_json(value))


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


def _read_object(path: Path, label: str) -> Mapping[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise OwnerRunBlocked(f"{label} is unreadable: {exc}") from exc
    if not isinstance(value, Mapping):
        raise OwnerRunBlocked(f"{label} must be an object")
    return value


def _hash_bound(value: Mapping[str, Any], field: str, label: str) -> None:
    body = dict(value)
    claimed = body.pop(field, None)
    if claimed != _digest(body):
        raise OwnerRunBlocked(f"{label} hash mismatch")


def _fts_document_names(candidate: Mapping[str, Any]) -> tuple[str, ...]:
    accession = str(candidate.get("accession") or "")
    edges = candidate.get("query_edges")
    if not accession or not isinstance(edges, list) or not edges:
        raise OwnerRunBlocked("S1F candidate has no complete FTS query edges")
    names: set[str] = set()
    for edge in edges:
        if not isinstance(edge, Mapping):
            raise OwnerRunBlocked("S1F candidate query edge is malformed")
        hit_id, filename, receipt = edge.get("hit_id"), edge.get("filename"), edge.get("query_receipt_sha256")
        if not all(isinstance(item, str) and item for item in (hit_id, filename, receipt)):
            raise OwnerRunBlocked("S1F candidate FTS edge identity is incomplete")
        hit_accession, separator, hit_filename = hit_id.partition(":")
        if separator != ":" or hit_accession != accession or hit_filename != filename:
            raise OwnerRunBlocked(f"S1F candidate FTS hit/document crosswire: {accession}:{filename}")
        names.add(filename)
    return tuple(sorted(names))


def _validate_inputs(
    *, selection_path: Path, receipt_path: Path, batch_plan_path: Path
) -> tuple[list[Mapping[str, Any]], Mapping[str, Any], Mapping[str, Any]]:
    selection = _read_object(selection_path, "S1F exact-70 selection")
    receipt = _read_object(receipt_path, "S1F selection receipt")
    batch = _read_object(batch_plan_path, "S1F batch plan")
    _hash_bound(selection, "manifest_sha256", "S1F exact-70 selection")
    _hash_bound(receipt, "receipt_sha256", "S1F selection receipt")
    _hash_bound(batch, "batch_plan_sha256", "S1F batch plan")
    candidates = selection.get("candidates")
    if (
        selection.get("schema") != "mastermind.dislocation_p0.s1f_exact70_source_manifest.v1"
        or selection.get("n") != REQUIRED_PACKET_COUNT
        or selection.get("selection_identity") != ["cik", "accession"]
        or selection.get("strata") != list(STRATA)
        or not isinstance(candidates, list)
        or len(candidates) != REQUIRED_PACKET_COUNT
        or selection.get("authority") != AUTHORITY
    ):
        raise OwnerRunBlocked("S1F exact-70 selection binding/cardinality mismatch")
    if not selection_margins_ok(candidates):
        raise OwnerRunBlocked("S1F exact-70 selection margin breach")
    identities = [(str(row.get("cik") or ""), str(row.get("accession") or "")) for row in candidates if isinstance(row, Mapping)]
    if len(identities) != REQUIRED_PACKET_COUNT or len(set(identities)) != REQUIRED_PACKET_COUNT or any(not all(item) for item in identities):
        raise OwnerRunBlocked("S1F exact-70 CIK/accession identity mismatch")
    excluded = selection.get("design_ciks_excluded")
    if (
        not isinstance(excluded, list)
        or len(excluded) != 20
        or len(set(excluded)) != 20
        or not all(isinstance(cik, str) and cik for cik in excluded)
        or {cik for cik, _accession in identities} & set(excluded)
    ):
        raise OwnerRunBlocked("S1F immutable design exclusion breach")
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            raise OwnerRunBlocked("S1F candidate is malformed")
        _fts_document_names(candidate)
    logical = _selection_logical_hash(candidates)
    if (
        receipt.get("status") != "COMPLETE"
        or receipt.get("selection_count") != REQUIRED_PACKET_COUNT
        or receipt.get("selection_identity_count") != REQUIRED_PACKET_COUNT
        or receipt.get("selection_manifest_sha256") != selection["manifest_sha256"]
        or receipt.get("selection_logical_sha256") != logical
        or receipt.get("design_ciks_excluded") != excluded
        or receipt.get("batch_plan_sha256") != batch.get("batch_plan_sha256")
        or receipt.get("selection_packet_manifest") != "S1F_EXACT70_SOURCE_MANIFEST.json"
        or receipt.get("batch_plan") != "S1F_EXACT70_AUDIT_BATCH_PLAN.json"
        or receipt.get("authority") != AUTHORITY
    ):
        raise OwnerRunBlocked("S1F selection receipt binding mismatch")
    batch_ids = [
        (str(packet.get("cik") or ""), str(packet.get("accession") or ""))
        for group in batch.get("batches", []) if isinstance(group, Mapping)
        for packet in group.get("packets", []) if isinstance(packet, Mapping)
    ]
    if (
        batch.get("schema") != "mastermind.dislocation_p0.s1f_exact70_audit_batch_plan.v1"
        or batch.get("selection_logical_sha256") != logical
        or batch.get("frozen_candidate_universe_sha256") != selection.get("frozen_candidate_universe_sha256")
        or batch.get("batch_order") != [group.get("batch_id") for group in batch.get("batches", []) if isinstance(group, Mapping)]
        or len(batch_ids) != REQUIRED_PACKET_COUNT
        or set(batch_ids) != set(identities)
        or batch.get("authority") != AUTHORITY
    ):
        raise OwnerRunBlocked("S1F audit batch identity binding mismatch")
    return list(candidates), receipt, batch


def _primary_view(document: Mapping[str, Any], *, source_path: str) -> dict[str, Any]:
    """Keep only owner-owned primary metadata; never invent type/description."""
    view = {
        "document_id": document["document_id"], "document_name": document["document_name"],
        "document_sha256": document["content_sha256"], "byte_length": document["byte_length"],
        "source_path": source_path, "document_type": document.get("document_type"),
        "document_type_status": "OWNER_AVAILABLE" if document.get("document_type") is not None else "OWNER_UNAVAILABLE",
    }
    return view


def _replay_transport_receipts(
    *, frozen: Mapping[str, Any], generic_root: Path, expected_ciks: set[str]
) -> tuple[list[dict[str, Any]], set[str]]:
    """Re-read every persisted generic-owner receipt/object without transport."""
    entries = frozen.get("submissions_transport_receipts")
    if not isinstance(entries, list) or not entries:
        raise OwnerRunBlocked("S1F frozen generic-SEC transport receipts are missing")
    rebuilt: list[dict[str, Any]] = []
    seen_current: set[str] = set(); seen_historical: set[tuple[str, str]] = set(); hosts: set[str] = set()
    for entry in entries:
        if not isinstance(entry, Mapping) or entry.get("owner") != "collectors.edgar_forensics.SecForensicsCollector" or not isinstance(entry.get("receipt"), Mapping):
            raise OwnerRunBlocked("S1F frozen generic-SEC transport receipt is malformed")
        try:
            receipt = RetrievalReceipt(**dict(entry["receipt"]))
        except TypeError as exc:
            raise OwnerRunBlocked(f"S1F frozen generic-SEC receipt is malformed: {exc}") from exc
        if receipt.endpoint != "submissions" or receipt.cik not in expected_ciks:
            raise OwnerRunBlocked("S1F frozen generic-SEC receipt coverage mismatch")
        source_kind, source_name = entry.get("source_kind"), entry.get("source_name")
        if source_kind == "current" and source_name is None:
            if receipt.cik in seen_current or receipt.url != endpoint_url(receipt.cik, "submissions"):
                raise OwnerRunBlocked("S1F current Submissions receipt coverage mismatch")
            seen_current.add(receipt.cik)
        elif source_kind == "historical" and isinstance(source_name, str):
            try:
                expected_url = historical_submissions_url(receipt.cik, source_name)
            except ValueError as exc:
                raise OwnerRunBlocked(f"S1F historical receipt source binding mismatch: {exc}") from exc
            key = (receipt.cik, source_name)
            if key in seen_historical or receipt.url != expected_url:
                raise OwnerRunBlocked("S1F historical Submissions receipt coverage mismatch")
            seen_historical.add(key)
        else:
            raise OwnerRunBlocked("S1F generic-SEC receipt source kind is invalid")
        try:
            _raw, stored, key, digest = _replay_generic_source_receipt(generic_root, receipt)
        except A1ROwnerRunBlocked as exc:
            raise OwnerRunBlocked(f"S1F generic-SEC owner replay failed: {exc}") from exc
        row = {"owner": "collectors.edgar_forensics.SecForensicsCollector", "source_kind": source_kind, "source_name": source_name, "receipt_storage_key": key, "receipt_file_sha256": digest, "receipt": stored}
        if canonical_json(row) != canonical_json(entry):
            raise OwnerRunBlocked(f"S1F frozen generic-SEC receipt projection drift: {receipt.cik}")
        rebuilt.append(row); hosts.add((urlparse(receipt.url).hostname or "").lower())
    if seen_current != expected_ciks:
        raise OwnerRunBlocked("S1F frozen generic-SEC receipt coverage is incomplete")
    return rebuilt, hosts


def _packet_artifacts(
    *, candidates: Sequence[Mapping[str, Any]], packets: Sequence[Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, bytes], set[str]]:
    public: list[dict[str, Any]] = []
    model: list[dict[str, Any]] = []
    files: dict[str, bytes] = {}
    hosts: set[str] = set()
    for slot, (candidate, packet) in enumerate(zip(candidates, packets, strict=True), start=1):
        if packet.slot != slot or (packet.issuer["cik"], packet.filing["accession"]) != (candidate["cik"], candidate["accession"]):
            raise OwnerRunBlocked("S1F canonical owner packet identity drift")
        if packet.primary_context is None or packet.primary_context_source is None:
            raise OwnerRunBlocked("S1F primary context is owner-unavailable")
        docs: list[dict[str, Any]] = []
        for document, source in zip(packet.matched_documents, packet.source_documents, strict=True):
            path = f"packets/{slot:02d}_{document['document_id']}.source"
            files[path] = source
            docs.append({"document_id": document["document_id"], "document_name": document["document_name"], "document_sha256": document["content_sha256"], "byte_length": document["byte_length"], "source_path": path})
            hosts.add((urlparse(document["archive_url"]).hostname or "").lower())
        primary_path = f"primary/{slot:02d}_{packet.primary_context['document_id']}.source"
        matched_path = next(
            (document["source_path"] for document in docs
             if document["document_id"] == packet.primary_context["document_id"]),
            None,
        )
        if matched_path is not None:
            primary_path = matched_path
        else:
            files[primary_path] = packet.primary_context_source
        hosts.add((urlparse(packet.primary_context["archive_url"]).hostname or "").lower())
        primary = _primary_view(packet.primary_context, source_path=primary_path)
        public.append({
            "slot": slot, "packet_id": f"s1f_packet_{candidate['selection_key']}",
            "selection_key": candidate["selection_key"], "retrieval_stratum": candidate["stratum"],
            "query_edges": candidate["query_edges"], "manifest_storage_key": packet.manifest_storage_key,
            "manifest_id": packet.manifest_id, "filing_id": packet.filing_id, "issuer": packet.issuer,
            "filing": packet.filing, "clocks": packet.clocks, "lineage": packet.lineage,
            "matched_documents": list(packet.matched_documents), "primary_context": primary,
            "primary_document_substitution": False,
        })
        model.append({"slot": slot, "packet_id": f"s1f_packet_{candidate['selection_key']}", "cik": packet.issuer["cik"], "accession": packet.filing["accession"], "accepted_at": packet.clocks["accepted_at"], "filed_on": packet.clocks["filed_on"], "documents": docs, "primary_context": primary, "primary_document_substitution": False})
    return public, model, files, hosts


def execute_owner_run(*, selection_path: Path, receipt_path: Path, batch_plan_path: Path, workspace: Path, public_out: Path) -> dict[str, Any]:
    """Perform the only permitted live path: the generic SEC/document owners."""
    candidates, receipt, batch = _validate_inputs(selection_path=selection_path, receipt_path=receipt_path, batch_plan_path=batch_plan_path)
    workspace, public_out = Path(workspace), Path(public_out)
    forbidden_dirs = assert_blind_workspace(workspace)
    refs = [CanonicalSpineRef(slot=index, cik=str(row["cik"]), accession=str(row["accession"]), expected_base_form=str(row["form"]), expected_filed_on=str(row["filed_on"]), expected_document_names=_fts_document_names(row), manifest_storage_key=None) for index, row in enumerate(candidates, start=1)]
    generic_root, owner_root = workspace / "generic_sec_source", workspace / "canonical_owner_archive"
    collector = SecForensicsCollector(generic_root, user_agent=USER_AGENT, max_response_bytes=CURRENT_SUBMISSIONS_MAX_BYTES)
    transport: list[dict[str, Any]] = []
    def fetch(cik: str) -> tuple[bytes, Mapping[str, str | None]]:
        owner_receipt = collector.fetch(cik, "submissions", max_response_bytes=CURRENT_SUBMISSIONS_MAX_BYTES)
        raw, persisted, storage_key, receipt_sha = _replay_generic_source_receipt(generic_root, owner_receipt)
        transport.append({"owner": "collectors.edgar_forensics.SecForensicsCollector", "source_kind": "current", "source_name": None, "receipt_storage_key": storage_key, "receipt_file_sha256": receipt_sha, "receipt": persisted})
        return raw, {"url": owner_receipt.url, "http_etag": owner_receipt.http_etag, "http_last_modified": owner_receipt.http_last_modified}
    def fetch_historical(cik: str, source_name: str) -> tuple[bytes, Mapping[str, str | None]]:
        owner_receipt = collector.fetch_historical_submissions_file(
            cik, source_name, max_response_bytes=CURRENT_SUBMISSIONS_MAX_BYTES,
        )
        raw, persisted, storage_key, receipt_sha = _replay_generic_source_receipt(generic_root, owner_receipt)
        transport.append({"owner": "collectors.edgar_forensics.SecForensicsCollector", "source_kind": "historical", "source_name": source_name, "receipt_storage_key": storage_key, "receipt_file_sha256": receipt_sha, "receipt": persisted})
        return raw, {"url": owner_receipt.url, "http_etag": owner_receipt.http_etag, "http_last_modified": owner_receipt.http_last_modified}
    recorded_at = _utc_now()
    result = materialize_current_source_refs(archive_root=owner_root, selections=refs, user_agent=USER_AGENT, fetch_submissions=fetch, fetch_historical_submissions=fetch_historical, recorded_at=recorded_at, required_packet_count=REQUIRED_PACKET_COUNT, include_primary_context=True, primary_context_required=True)
    hosts = {(urlparse(row["receipt"]["url"]).hostname or "").lower() for row in transport}
    if not hosts or not hosts.issubset(ALLOWED_HOSTS):
        raise OwnerRunBlocked(f"non-SEC generic owner host observed: {sorted(hosts)}")
    common = {"selection_manifest_sha256": _read_object(selection_path, "S1F exact-70 selection")["manifest_sha256"], "selection_receipt_sha256": receipt["receipt_sha256"], "batch_plan_sha256": batch["batch_plan_sha256"], "recorded_at": recorded_at, "submissions_transport_receipts": transport, "authority": dict(AUTHORITY), "firewall": {"forbidden_dirs_present": forbidden_dirs, "official_sec_hosts": sorted(hosts)}}
    if result.gaps:
        gap = {"schema": "mastermind.dislocation_p0.s1f_owner_gap.v1", "status": "BLOCKED_CANONICAL_OWNER_CAPABILITY", **common, "gaps": [item.__dict__ for item in result.gaps], "top_up_permitted": False, "p0_local_source_fallback_permitted": False}
        if forbidden_market_fields(gap): raise OwnerRunBlocked("S1F owner gap violates source-only firewall")
        _write_json(public_out / OWNER_GAP_NAME, gap)
        return {"status": "BLOCKED", "gap_path": str(public_out / OWNER_GAP_NAME), "gap_count": len(result.gaps)}
    packets = read_source_packets(archive_root=owner_root, refs=result.refs, required_packet_count=REQUIRED_PACKET_COUNT, include_primary_context=True, primary_context_required=True)
    if not packets.complete: raise OwnerRunBlocked(canonical_json({"code": "CANONICAL_OWNER_REPLAY_FAILED", "gaps": [item.__dict__ for item in packets.gaps]}))
    public, model, files, document_hosts = _packet_artifacts(candidates=candidates, packets=packets.packets)
    hosts |= document_hosts
    if not hosts or not hosts.issubset(ALLOWED_HOSTS): raise OwnerRunBlocked(f"non-SEC owner host observed: {sorted(hosts)}")
    for relative, content in files.items():
        path = workspace / "source_packets" / relative; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(content)
    _write_json(workspace / "source_packets" / "packet_index.json", {"schema": "mastermind.dislocation_p0.s1f_model_packet_index.v1", "packets": model})
    manifest = {"schema": "mastermind.dislocation_p0.s1f_canonical_source_packets.v1", "status": "COMPLETE", **common, "firewall": {"forbidden_dirs_present": forbidden_dirs, "official_sec_hosts": sorted(hosts)}, "n": REQUIRED_PACKET_COUNT, "packets": public}
    if forbidden_market_fields(manifest): raise OwnerRunBlocked("S1F owner manifest violates source-only firewall")
    manifest["manifest_sha256"] = _digest(manifest); _write_json(public_out / OWNER_MANIFEST_NAME, manifest)
    return {"status": "COMPLETE", "manifest_path": str(public_out / OWNER_MANIFEST_NAME), "manifest_sha256": manifest["manifest_sha256"], "packet_count": REQUIRED_PACKET_COUNT, "document_count": len(files), "official_sec_hosts": sorted(hosts)}


def execute_owner_replay(*, frozen_manifest_path: Path, workspace: Path, replay_out: Path, packet_index_path: Path | None = None) -> dict[str, Any]:
    """Offline byte-identical replay from persisted generic/document-owner state."""
    frozen, workspace, replay_out = _read_object(frozen_manifest_path, "S1F frozen owner manifest"), Path(workspace), Path(replay_out)
    _hash_bound(frozen, "manifest_sha256", "S1F frozen owner manifest")
    if frozen.get("schema") != "mastermind.dislocation_p0.s1f_canonical_source_packets.v1" or frozen.get("n") != REQUIRED_PACKET_COUNT or not isinstance(frozen.get("packets"), list) or len(frozen["packets"]) != REQUIRED_PACKET_COUNT: raise OwnerRunBlocked("S1F frozen owner manifest cardinality mismatch")
    if assert_blind_workspace(replay_out): raise OwnerRunBlocked("replay output violates source-only firewall")
    refs = []
    candidates = []
    for row in frozen["packets"]:
        if not isinstance(row, Mapping): raise OwnerRunBlocked("S1F frozen packet malformed")
        filing, issuer = row.get("filing"), row.get("issuer")
        if not isinstance(filing, Mapping) or not isinstance(issuer, Mapping): raise OwnerRunBlocked("S1F frozen packet identity malformed")
        edges = row.get("query_edges"); candidate = {"accession": filing.get("accession"), "query_edges": edges}
        names = _fts_document_names(candidate)
        refs.append(CanonicalSpineRef(slot=int(row.get("slot") or 0), cik=str(issuer.get("cik") or ""), accession=str(filing.get("accession") or ""), expected_base_form=str(filing.get("base_form") or ""), expected_filed_on=row.get("clocks", {}).get("filed_on") if isinstance(row.get("clocks"), Mapping) else None, expected_document_names=names, manifest_storage_key=str(row.get("manifest_storage_key") or "") or None))
        candidates.append({"cik": issuer.get("cik"), "accession": filing.get("accession"), "selection_key": row.get("selection_key"), "stratum": row.get("retrieval_stratum"), "query_edges": edges})
    packets = read_source_packets(archive_root=workspace / "canonical_owner_archive", refs=refs, required_packet_count=REQUIRED_PACKET_COUNT, include_primary_context=True, primary_context_required=True)
    if not packets.complete: raise OwnerRunBlocked(canonical_json({"code": "CANONICAL_OWNER_REPLAY_FAILED", "gaps": [item.__dict__ for item in packets.gaps]}))
    public, model, files, hosts = _packet_artifacts(candidates=candidates, packets=packets.packets)
    transport, transport_hosts = _replay_transport_receipts(
        frozen=frozen, generic_root=workspace / "generic_sec_source",
        expected_ciks={ref.cik for ref in refs},
    )
    hosts |= transport_hosts
    if not hosts or not hosts.issubset(ALLOWED_HOSTS):
        raise OwnerRunBlocked(f"S1F replay observed non-SEC host: {sorted(hosts)}")
    if frozen.get("firewall", {}).get("official_sec_hosts") != sorted(hosts):
        raise OwnerRunBlocked("S1F frozen firewall host projection drift")
    if canonical_json(public) != canonical_json(frozen["packets"]): raise OwnerRunBlocked("S1F canonical packet projection drift")
    source_root = Path(packet_index_path or workspace / "source_packets" / "packet_index.json").parent
    index = {"schema": "mastermind.dislocation_p0.s1f_model_packet_index.v1", "packets": model}; index_bytes = (canonical_json(index) + "\n").encode()
    if (source_root / "packet_index.json").read_bytes() != index_bytes: raise OwnerRunBlocked("S1F packet index is not byte-identical")
    for relative, content in files.items():
        if (source_root / relative).read_bytes() != content: raise OwnerRunBlocked(f"S1F source bytes are not byte-identical: {relative}")
        target = replay_out / "source_packets" / relative; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(content)
    _write_json(replay_out / "source_packets" / "packet_index.json", index)
    rebuilt = dict(frozen); rebuilt["packets"] = public; rebuilt["submissions_transport_receipts"] = transport
    rebuilt["firewall"] = {"forbidden_dirs_present": assert_blind_workspace(workspace), "official_sec_hosts": sorted(hosts)}
    rebuilt["manifest_sha256"] = _digest({key: value for key, value in rebuilt.items() if key != "manifest_sha256"})
    if Path(frozen_manifest_path).read_bytes() != (canonical_json(rebuilt) + "\n").encode(): raise OwnerRunBlocked("S1F canonical owner manifest is not byte-identical")
    _write_json(replay_out / OWNER_MANIFEST_NAME, rebuilt)
    proof = {"schema": "mastermind.dislocation_p0.s1f_canonical_owner_replay_proof.v1", "status": "COMPLETE_BYTE_IDENTICAL", "network_access": "NONE", "frozen_manifest_sha256": frozen["manifest_sha256"], "replayed_manifest_sha256": rebuilt["manifest_sha256"], "packet_count": REQUIRED_PACKET_COUNT, "document_count": len(files), "official_sec_hosts": sorted(hosts), "forbidden_dirs_present": assert_blind_workspace(workspace)}
    _write_json(replay_out / OWNER_REPLAY_NAME, proof); return proof


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(); mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--selection", type=Path); mode.add_argument("--replay-manifest", type=Path)
    parser.add_argument("--selection-receipt", type=Path); parser.add_argument("--batch-plan", type=Path)
    parser.add_argument("--workspace", type=Path, required=True); parser.add_argument("--public-out", type=Path); parser.add_argument("--replay-out", type=Path); parser.add_argument("--packet-index", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.selection:
            if not all((args.selection_receipt, args.batch_plan, args.public_out)): raise OwnerRunBlocked("owner run requires selection receipt, batch plan, and public output")
            result = execute_owner_run(selection_path=args.selection, receipt_path=args.selection_receipt, batch_plan_path=args.batch_plan, workspace=args.workspace, public_out=args.public_out)
        else:
            if args.replay_out is None: raise OwnerRunBlocked("owner replay requires replay output")
            result = execute_owner_replay(frozen_manifest_path=args.replay_manifest, workspace=args.workspace, replay_out=args.replay_out, packet_index_path=args.packet_index)
    except OwnerRunBlocked as exc:
        print(f"S1F_OWNER_RUN_BLOCKED:{exc}"); return 2
    print(canonical_json(result)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
