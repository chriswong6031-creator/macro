"""Compile retained SEC evidence into the immutable capital-structure event spine.

The compiler is offline by construction: it reads committed source manifests,
never calls SEC, and emits context-only immutable event versions, graph edges,
and a deterministic review queue.  Semantic term extraction and issuer-state
calculation are later waves and cannot be smuggled into this layer.

Usage:
    python -m scripts.compile_capital_structure_events
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from collections.abc import Mapping, Sequence
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any

import pandas as pd

from collectors.sec_capital_structure import FORM_POLICY, file_number_provenance_errors
from engine.capital_structure import (
    append_event_versions_strict,
    build_event_version,
    build_review_queue,
    link_registration_graph,
    route_form,
)
from engine.capital_structure.source_identity import (
    source_ledger_prefix_hash,
    validate_manifest_ledger,
)

EVENT_COLUMNS = [
    "event_id", "logical_event_id", "accession", "cik", "ticker", "form",
    "filing_date", "accepted_at", "available_at", "classification_state",
    "correction_version", "event_json",
]
EDGE_COLUMNS = [
    "edge_id", "schema", "from_event_id", "to_event_id", "relationship",
    "link_method", "observed_at", "immutable_record",
]
REVIEW_COLUMNS = [
    "queue_id", "schema", "event_id", "accession", "issuer_id", "form",
    "classification_state", "defer_reason", "candidate_event_ids",
    "source_manifest_ids", "first_queued_at", "review_state", "immutable_source",
]

CONTRACT_FILES = {
    "manifest": "capital_structure_source_manifest.schema.json",
    "event": "capital_structure_event.schema.json",
    "edge": "capital_structure_event_edge.schema.json",
    "review": "capital_structure_review_item.schema.json",
    "telemetry": "capital_structure_telemetry.schema.json",
}


class CapitalStructureCompileDegraded(RuntimeError):
    """A source accession failed, so no partial generation may be published."""

    def __init__(self, telemetry: Mapping[str, Any]):
        self.telemetry = dict(telemetry)
        failures = self.telemetry.get("compile_failures") or []
        super().__init__(
            f"capital-structure compile degraded with {len(failures)} accession failure(s)"
        )


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _data_root() -> Path:
    from lib import config
    return config.data_dir() / "capital_structure"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _native(value: Any) -> Any:
    """Convert pandas/Arrow nested values to stable Python containers."""
    if isinstance(value, Mapping):
        return {str(key): _native(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_native(item) for item in value]
    if hasattr(value, "tolist") and not isinstance(value, (str, bytes, bytearray)):
        try:
            return _native(value.tolist())
        except Exception:  # noqa: BLE001
            pass
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item") and not isinstance(value, (str, bytes, bytearray)):
        try:
            return value.item()
        except Exception:  # noqa: BLE001
            pass
    return value


def dataframe_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return [_native(row) for row in frame.to_dict(orient="records")]


def _load_contract(kind: str) -> dict[str, Any]:
    filename = CONTRACT_FILES[kind]
    return json.loads((_repo_root() / "contracts" / filename).read_text(encoding="utf-8"))


def _contract_errors(record: Mapping[str, Any], schema: Mapping[str, Any]) -> list[str]:
    from jsonschema import Draft202012Validator, FormatChecker

    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return [
        f"{'.'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
        for error in validator.iter_errors(record)
    ]


def _validate_contract(
    record: Mapping[str, Any], schema: Mapping[str, Any], *, label: str
) -> None:
    errors = _contract_errors(record, schema)
    if errors:
        raise ValueError(f"{label} contract violation: {'; '.join(errors[:5])}")


def _semantic_manifest_errors(record: Mapping[str, Any]) -> list[str]:
    """Enforce content-address and span invariants JSON Schema cannot express."""
    errors: list[str] = []
    document = record.get("document") or {}
    storage = record.get("storage") or {}
    digest = str(document.get("content_sha256") or "").lower()
    root_locator = str(document.get("root_locator") or "")
    locator_digest = root_locator.partition(":")[2].lower()
    object_key = str(storage.get("object_key") or "")
    object_digest = object_key.rsplit("/", 1)[-1].lower()
    shard = object_key.rsplit("/", 2)[-2].lower() if object_key.count("/") >= 2 else ""
    if digest and locator_digest != digest:
        errors.append("document.root_locator digest must equal document.content_sha256")
    if digest and object_digest != digest:
        errors.append("storage.object_key digest must equal document.content_sha256")
    if digest and shard != digest[:2]:
        errors.append("storage.object_key shard must equal the first two digest characters")
    spans = record.get("spans") or []
    byte_length = int(document.get("byte_length") or 0)
    expected_locator = f"bytes:0-{byte_length}"
    if digest and not any(
        str((span or {}).get("text_sha256") or "").lower() == digest
        and (span or {}).get("locator_type") == "document"
        and (span or {}).get("locator") == expected_locator
        for span in spans if isinstance(span, Mapping)
    ):
        errors.append(
            "spans must retain an exact document root span matching content hash and byte length"
        )
    return errors


def _validate_manifest(record: Mapping[str, Any], schema: Mapping[str, Any]) -> list[str]:
    errors = _contract_errors(record, schema)
    if not errors:
        errors.extend(_semantic_manifest_errors(record))
        errors.extend(file_number_provenance_errors(record.get("filing")))
    return errors


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_dependency_max(values: Sequence[Any]) -> str:
    """Return when every selected evidence dependency was available."""
    stamps = [pd.Timestamp(value) for value in values if value]
    if not stamps:
        raise ValueError("source group has no first_seen_at")
    normalized = [
        stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")
        for stamp in stamps
    ]
    return max(normalized).isoformat().replace("+00:00", "Z")


def _single(values: Sequence[Any], field: str, *, nullable: bool = False) -> Any:
    unique = {str(value) for value in values if value is not None and str(value) != ""}
    if not unique:
        if nullable:
            return None
        raise ValueError(f"source group has no {field}")
    if len(unique) != 1:
        raise ValueError(f"source group conflicts on {field}: {sorted(unique)}")
    return next(iter(unique))


def _span_evidence(record: Mapping[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for raw_span in record.get("spans") or []:
        span = dict(_native(raw_span))
        span["manifest_id"] = str(record["manifest_id"])
        out.append(span)
    return out


def _current_manifest_bundle(
    records: Sequence[Mapping[str, Any]], *, accession: str
) -> list[dict[str, Any]]:
    """Select current document versions and enforce closed accession lineage."""
    by_manifest: dict[str, dict[str, Any]] = {}
    manifest_bytes: dict[str, bytes] = {}
    for raw in records:
        row = dict(_native(raw))
        manifest_id = str(row.get("manifest_id") or "")
        encoded = _canonical_json(row)
        if manifest_id in manifest_bytes and manifest_bytes[manifest_id] != encoded:
            raise ValueError(f"immutable manifest collision for {manifest_id}")
        manifest_bytes[manifest_id] = encoded
        by_manifest.setdefault(manifest_id, row)

    for row in by_manifest.values():
        row_accession = str((row.get("filing") or {}).get("accession") or "")
        if row_accession != accession:
            raise ValueError(
                f"manifest {row.get('manifest_id')} belongs to accession {row_accession!r}"
            )

    all_rows = list(by_manifest.values())
    complete_versions = [
        int((row.get("document") or {}).get("document_version") or 0)
        for row in all_rows
        if (row.get("document") or {}).get("document_role") == "complete_submission"
    ]
    if not complete_versions:
        raise ValueError(f"{accession}: bundle has no complete_submission version")
    bundle_version = max(complete_versions)
    if any(
        int((row.get("document") or {}).get("document_version") or 0) > bundle_version
        for row in all_rows
    ):
        raise ValueError(
            f"{accession}: child document version exceeds latest complete bundle version"
        )
    bundle_rows = [
        row for row in all_rows
        if int((row.get("document") or {}).get("document_version") or 0) == bundle_version
    ]

    by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in bundle_rows:
        by_source[str(row.get("source_id") or "")].append(row)

    current: list[dict[str, Any]] = []
    for source_id, versions in by_source.items():
        hashes = {
            str((row.get("document") or {}).get("content_sha256") or "").lower()
            for row in versions
        }
        if len(hashes) != 1:
            raise ValueError(
                f"source_id {source_id!r} has competing document version {bundle_version}"
            )
        versions.sort(
            key=lambda row: (
                str((row.get("retrieval") or {}).get("retrieved_at") or ""),
                str(row.get("manifest_id") or ""),
            )
        )
        current.append(versions[-1])

    complete = [
        row for row in current
        if (row.get("document") or {}).get("document_role") == "complete_submission"
    ]
    if len(complete) != 1:
        raise ValueError(
            f"{accession}: bundle requires exactly one current complete_submission; found {len(complete)}"
        )
    complete_id = str(complete[0]["manifest_id"])
    if (complete[0].get("document") or {}).get("parent_manifest_id") is not None:
        raise ValueError(f"{accession}: complete_submission cannot have a parent_manifest_id")
    primaries = [
        row for row in current
        if (row.get("document") or {}).get("document_role") == "primary"
    ]
    if len(primaries) > 1:
        raise ValueError(f"{accession}: bundle has multiple current primary documents")
    for row in current:
        role = (row.get("document") or {}).get("document_role")
        if role == "complete_submission":
            continue
        parent_id = str((row.get("document") or {}).get("parent_manifest_id") or "")
        if parent_id != complete_id:
            raise ValueError(
                f"{accession}: {row.get('manifest_id')} parent must reference {complete_id}"
            )
    return sorted(current, key=lambda row: str(row.get("manifest_id") or ""))


def event_from_manifest_group(
    records: Sequence[Mapping[str, Any]],
    *,
    correction_version: int = 1,
    correction_of: str | None = None,
    produced_at: str | None = None,
) -> dict[str, Any]:
    """Compile one accession's strict manifests into one immutable event version."""
    if not records:
        raise ValueError("manifest group is empty")
    rows = [dict(_native(record)) for record in records]
    accession = _single([row.get("filing", {}).get("accession") for row in rows], "accession")
    rows = _current_manifest_bundle(rows, accession=str(accession))
    form = _single([row.get("filing", {}).get("form") for row in rows], "form")
    filing_date = _single(
        [row.get("filing", {}).get("filing_date") for row in rows], "filing_date"
    )
    accepted_at = _single(
        [row.get("filing", {}).get("accepted_at") for row in rows],
        "accepted_at", nullable=True,
    )
    observed_file_number = _single(
        [row.get("filing", {}).get("file_number") for row in rows],
        "file_number", nullable=True,
    )
    # Legacy manifests remain schema-valid and immutable, but their first-match
    # SGML value predates conflict-aware provenance. Keep compiling the bundle
    # while withholding that untrusted value from exact lifecycle linkage. The
    # bounded collector queue will create a new provenance-bearing bundle version.
    provenance_rows = [
        dict((row.get("filing") or {}).get("file_number_provenance"))
        for row in rows
        if isinstance(
            (row.get("filing") or {}).get("file_number_provenance"), Mapping
        )
    ]
    has_hardened_file_number_provenance = len(provenance_rows) == len(rows)
    if has_hardened_file_number_provenance and len({
        _canonical_json(value) for value in provenance_rows
    }) != 1:
        raise ValueError("source group conflicts on file_number_provenance")
    file_number_provenance = (
        provenance_rows[0] if has_hardened_file_number_provenance else None
    )
    file_number = (
        observed_file_number if has_hardened_file_number_provenance else None
    )
    cik = _single([row.get("issuer", {}).get("cik") for row in rows], "cik")

    primaries = [
        row for row in rows if row.get("document", {}).get("document_role") == "primary"
    ]
    complete = [
        row for row in rows
        if row.get("document", {}).get("document_role") == "complete_submission"
    ]
    evidence_record = (primaries or complete)[0]
    spans = _span_evidence(evidence_record)
    if not spans:
        raise ValueError(f"{accession}: evidence document has no stable spans")

    issuer = evidence_record.get("issuer") or {}
    source_first_seen = _utc_dependency_max([
        row.get("retrieval", {}).get("first_seen_at") for row in rows
    ])
    first_seen = produced_at or source_first_seen
    exhibits = [
        row.get("document", {}).get("canonical_url")
        for row in rows
        if row.get("document", {}).get("document_role") in {
            "exhibit", "underwriting_exhibit", "filing_fee_exhibit",
        }
    ]
    observation = {
        "source_system": "sec_edgar",
        "source_id": str(accession),
        "manifest_ids": sorted(str(row["manifest_id"]) for row in rows),
        "accession": str(accession),
        "issuer_id": issuer.get("issuer_id"),
        "cik": cik,
        "ticker": issuer.get("ticker"),
        "aliases": issuer.get("aliases") or [],
        "form": form,
        "file_number": file_number,
        "file_number_provenance": file_number_provenance,
        "filing_date": filing_date,
        "accepted_at": accepted_at,
        "first_seen_at": first_seen,
        "primary_document_url": (
            evidence_record.get("document", {}).get("canonical_url") if primaries else None
        ),
        "exhibit_urls": sorted({str(url) for url in exhibits if url}),
        "content_hashes": sorted({
            str(row.get("document", {}).get("content_sha256"))
            for row in rows if row.get("document", {}).get("content_sha256")
        }),
    }
    parser = evidence_record.get("parser") or {}
    root_parser = complete[0].get("parser") or {}
    if str(root_parser.get("corruption_state") or "unknown") != "clean":
        observation["classification_state"] = "deferred_conflict"
        observation["defer_reason"] = (
            "complete_submission_corruption_state_"
            + str(root_parser.get("corruption_state") or "unknown")
        )
    elif str(root_parser.get("eligibility") or "unknown") != "eligible":
        observation["classification_state"] = "deferred_unsupported_media"
        observation["defer_reason"] = (
            "complete_submission_parser_eligibility_"
            + str(root_parser.get("eligibility") or "unknown")
        )
    elif not primaries:
        observation["classification_state"] = "deferred_missing_document"
        observation["defer_reason"] = "primary_document_not_retained"
    elif str(parser.get("corruption_state") or "unknown") != "clean":
        observation["classification_state"] = "deferred_conflict"
        observation["defer_reason"] = (
            "primary_document_corruption_state_"
            + str(parser.get("corruption_state") or "unknown")
        )
    elif str(parser.get("eligibility") or "unknown") != "eligible":
        observation["classification_state"] = "deferred_unsupported_media"
        observation["defer_reason"] = (
            "primary_document_parser_eligibility_"
            + str(parser.get("eligibility") or "unknown")
        )
    return build_event_version(
        observation,
        spans,
        correction_version=correction_version,
        correction_of=correction_of,
    )


def _normalize_cell(value: Any) -> Any:
    native = _native(value)
    return None if native is None else native


def _validate_event_history(events: Sequence[Mapping[str, Any]]) -> None:
    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for event in events:
        source = event.get("source") or {}
        filing = event.get("filing") or {}
        grouped[(
            str(source.get("source_system") or ""),
            str(filing.get("accession") or source.get("source_id") or ""),
        )].append(event)
    for logical_key, versions in grouped.items():
        by_version: dict[int, Mapping[str, Any]] = {}
        for event in versions:
            number = int((event.get("version") or {}).get("correction_version") or 0)
            if number in by_version:
                raise ValueError(
                    f"logical event {logical_key} has duplicate correction_version {number}"
                )
            by_version[number] = event
        expected = list(range(1, len(by_version) + 1))
        if sorted(by_version) != expected:
            raise ValueError(
                f"logical event {logical_key} has non-contiguous correction history"
            )
        for number in expected:
            event = by_version[number]
            correction_of = (event.get("version") or {}).get("correction_of")
            if number == 1 and correction_of is not None:
                raise ValueError(f"logical event {logical_key} v1 cannot be a correction")
            if number > 1:
                prior_id = str(by_version[number - 1].get("event_id") or "")
                if str(correction_of or "") != prior_id:
                    raise ValueError(
                        f"logical event {logical_key} v{number} must correct {prior_id}"
                    )
                prior_time = pd.Timestamp(
                    (by_version[number - 1].get("point_in_time") or {}).get("available_at")
                )
                current_time = pd.Timestamp(
                    (event.get("point_in_time") or {}).get("available_at")
                )
                if current_time <= prior_time:
                    raise ValueError(
                        f"logical event {logical_key} v{number} must be produced after v{number - 1}"
                    )


def _validate_event_source_lineage(
    events: Sequence[Mapping[str, Any]], manifest_ids: set[str]
) -> None:
    """Require every immutable event reference to resolve in the current source ledger."""
    for event in events:
        event_id = str(event.get("event_id") or "<missing-event-id>")
        source_ids = {
            str(value)
            for value in (event.get("source") or {}).get("manifest_ids") or []
            if value is not None and str(value)
        }
        evidence_ids = {
            str((evidence or {}).get("manifest_id") or "")
            for evidence in event.get("evidence") or []
            if isinstance(evidence, Mapping)
        }
        evidence_ids.discard("")
        detached_evidence = sorted(evidence_ids - source_ids)
        missing = sorted((source_ids | evidence_ids) - manifest_ids)
        if detached_evidence:
            raise ValueError(
                f"event {event_id} evidence manifest_ids are absent from its source lineage: "
                + ", ".join(detached_evidence)
            )
        if missing:
            raise ValueError(
                f"event {event_id} source lineage is absent from current "
                "source_manifest.parquet: " + ", ".join(missing)
            )


def _validate_event_identity(event: Mapping[str, Any], *, label: str) -> None:
    body = copy.deepcopy(dict(event))
    event_id = str(body.pop("event_id", ""))
    expected = "event:cs:" + hashlib.sha256(_canonical_json(body)).hexdigest()[:24]
    if event_id != expected:
        raise ValueError(f"{label} event_id digest mismatch: {event_id!r} != {expected!r}")


def _validate_edge_identity(edge: Mapping[str, Any], *, label: str) -> None:
    body = copy.deepcopy(dict(edge))
    edge_id = str(body.pop("edge_id", ""))
    expected = "edge:cs:" + hashlib.sha256(_canonical_json(body)).hexdigest()[:24]
    if edge_id != expected:
        raise ValueError(f"{label} edge_id digest mismatch: {edge_id!r} != {expected!r}")


def _load_existing_events(
    frame: pd.DataFrame | None,
    event_schema: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if frame is None:
        return []
    if frame.columns.tolist() != EVENT_COLUMNS:
        raise ValueError(
            "event ledger columns must exactly equal "
            f"{EVENT_COLUMNS}; got {frame.columns.tolist()}"
        )
    if frame.empty:
        return []
    schema = event_schema or _load_contract("event")
    events: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, row in frame.iterrows():
        value = row["event_json"]
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"event ledger row {index} has null/non-string event_json")
        try:
            event = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError(f"event ledger row {index} has malformed event_json") from exc
        if not isinstance(event, Mapping):
            raise ValueError(f"event ledger row {index} event_json must be an object")
        _validate_contract(event, schema, label=f"event ledger row {index}")
        _validate_event_identity(event, label=f"event ledger row {index}")
        event_id = str(event.get("event_id") or "")
        if event_id in seen:
            raise ValueError(f"event ledger contains duplicate event_id {event_id}")
        seen.add(event_id)
        filing = event.get("filing") or {}
        issuer = event.get("issuer") or {}
        point_in_time = event.get("point_in_time") or {}
        version = event.get("version") or {}
        classification = event.get("classification") or {}
        expected = {
            "event_id": event_id,
            "logical_event_id": f"sec:{filing.get('accession')}",
            "accession": filing.get("accession"),
            "cik": issuer.get("cik"),
            "ticker": issuer.get("ticker"),
            "form": filing.get("form"),
            "filing_date": filing.get("filing_date"),
            "accepted_at": filing.get("accepted_at"),
            "available_at": point_in_time.get("available_at"),
            "classification_state": classification.get("state"),
            "correction_version": int(version.get("correction_version")),
        }
        for column, expected_value in expected.items():
            actual = _normalize_cell(row[column])
            if column == "correction_version" and actual is not None:
                actual = int(actual)
            if actual != expected_value:
                raise ValueError(
                    f"event ledger row {index} denormalized {column} mismatch: "
                    f"{actual!r} != {expected_value!r}"
                )
        canonical = json.dumps(event, sort_keys=True, separators=(",", ":"))
        if value != canonical:
            raise ValueError(f"event ledger row {index} event_json is not canonical")
        events.append(dict(event))
    _validate_event_history(events)
    return events


def _load_existing_edges(
    frame: pd.DataFrame | None,
    edge_schema: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if frame is None:
        return []
    if frame.columns.tolist() != EDGE_COLUMNS:
        raise ValueError(
            "edge ledger columns must exactly equal "
            f"{EDGE_COLUMNS}; got {frame.columns.tolist()}"
        )
    if frame.empty:
        return []
    schema = edge_schema or _load_contract("edge")
    edges: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(dataframe_records(frame)):
        row = dict(raw)
        _validate_contract(row, schema, label=f"edge ledger row {index}")
        _validate_edge_identity(row, label=f"edge ledger row {index}")
        edge_id = str(row.get("edge_id") or "")
        if edge_id in seen:
            raise ValueError(f"edge ledger contains duplicate edge_id {edge_id}")
        seen.add(edge_id)
        edges.append(row)
    return edges


def _append_edges_strict(
    existing: Sequence[Mapping[str, Any]], incoming: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    by_id: dict[str, bytes] = {}
    for raw in [*existing, *incoming]:
        edge = copy.deepcopy(dict(raw))
        edge_id = str(edge.get("edge_id") or "")
        if not edge_id:
            raise ValueError("every event edge requires edge_id")
        encoded = _canonical_json(edge)
        prior = by_id.get(edge_id)
        if prior is not None:
            if prior != encoded:
                raise ValueError(f"immutable edge collision for {edge_id}")
            continue
        by_id[edge_id] = encoded
        out.append(edge)
    return out


def _trusted_event_file_number(event: Mapping[str, Any]) -> str | None:
    """Admit only a provenance-bound event file number to exact graph keys."""
    filing = event.get("filing") or {}
    file_number = filing.get("file_number")
    provenance = filing.get("file_number_provenance")
    if not isinstance(file_number, str) or not isinstance(provenance, Mapping):
        return None
    value = provenance.get("value")
    candidates = provenance.get("candidate_values")
    sources = provenance.get("sources")
    if (
        provenance.get("state") != "observed"
        or value != file_number
        or candidates != [file_number]
        or not isinstance(sources, list)
        or not sources
    ):
        return None
    return file_number


def _linkage_metadata(events: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    metadata: dict[str, dict[str, Any]] = {}
    families_by_key: dict[tuple[str, str], set[str]] = defaultdict(set)
    for event in events:
        filing = event.get("filing") or {}
        issuer = event.get("issuer") or {}
        route = route_form(filing.get("form"))
        file_number = _trusted_event_file_number(event) or ""
        cik = str(issuer.get("cik") or "")
        if route.registration_family and cik and file_number:
            families_by_key[(cik, file_number)].add(route.registration_family)
    for event in events:
        filing = event.get("filing") or {}
        issuer = event.get("issuer") or {}
        route = route_form(filing.get("form"))
        file_number = _trusted_event_file_number(event) or ""
        cik = str(issuer.get("cik") or "")
        family = route.registration_family
        if not family and cik and file_number:
            candidates = families_by_key.get((cik, file_number), set())
            if len(candidates) == 1:
                family = next(iter(candidates))
        metadata[str(event["event_id"])] = {
            "file_number": file_number or None,
            "registration_family": family,
        }
    return metadata


def _semantic_event_body(event: Mapping[str, Any]) -> bytes:
    """Canonical event meaning, excluding immutable-version bookkeeping clocks."""
    body = copy.deepcopy(dict(event))
    body.pop("event_id", None)
    body.pop("version", None)
    body.pop("point_in_time", None)
    relationships = body.get("relationships") or {}
    relationships["supersedes"] = []
    return _canonical_json(body)


def _latest_events_by_logical_key(
    events: Sequence[Mapping[str, Any]],
) -> dict[tuple[str, str], Mapping[str, Any]]:
    latest: dict[tuple[str, str], Mapping[str, Any]] = {}
    for event in events:
        source = event.get("source") or {}
        filing = event.get("filing") or {}
        key = (
            str(source.get("source_system") or ""),
            str(filing.get("accession") or source.get("source_id") or ""),
        )
        prior = latest.get(key)
        if prior is None or int((event.get("version") or {}).get("correction_version") or 0) > int(
            (prior.get("version") or {}).get("correction_version") or 0
        ):
            latest[key] = event
    return latest


def _migration_receipt() -> dict[str, Any]:
    body: dict[str, Any] = {
        "schema": "capital_structure.migration_receipt.v1",
        "source_contract": "capital_structure.event.v1",
        "target_contract": "company_event.v1",
        "state": "temporary_adapter_active_pending_target",
        "owner": "capital-structure-intelligence",
        "review_by": "2026-10-01",
        "adjudicator": "neural-web-architecture-owner",
        "acceptance_evidence": [
            "docs/CAPITAL_STRUCTURE_INTELLIGENCE_CONTRACT.md",
            "tests/test_capital_structure_pit.py",
        ],
        "pit_preservation_state": "not_yet_tested",
        "legacy_writer": "collectors/edgar_dilution.py",
        "legacy_projection_state": "shadow_only_no_cutover",
        "immutable_record": True,
    }
    body["receipt_id"] = "migration:cs:" + hashlib.sha256(_canonical_json(body)).hexdigest()[:24]
    return body


def _source_ledger_receipt(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "schema": "capital_structure.source_ledger_receipt.v1",
        "record_count": len(records),
        "prefix_sha256": source_ledger_prefix_hash(records),
        "form_policy_version": str(FORM_POLICY["policy_version"]),
        "immutable_prefix": True,
    }


def _generation_id(
    *,
    as_of: str,
    artifact_hashes: Mapping[str, str | None],
    source_ledger_receipt: Mapping[str, Any],
) -> str:
    return "generation:cs:" + hashlib.sha256(
        _canonical_json({
            "as_of": as_of,
            "artifact_hashes": artifact_hashes,
            "source_ledger_receipt": source_ledger_receipt,
        })
    ).hexdigest()[:24]


def _build_telemetry(
    *,
    status: str,
    as_of: str,
    counts: Mapping[str, int],
    failures: Sequence[Mapping[str, Any]],
    artifact_hashes: Mapping[str, str | None],
    source_ledger_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    source_receipt = dict(source_ledger_receipt)
    if int(source_receipt.get("record_count") or 0) != int(
        counts.get("source_manifests") or 0
    ):
        raise ValueError("source ledger receipt count must match telemetry source count")
    if source_receipt.get("form_policy_version") != FORM_POLICY["policy_version"]:
        raise ValueError("new telemetry must stamp the current source form policy")
    hashes = {
        "event_versions": artifact_hashes.get("event_versions"),
        "event_edges": artifact_hashes.get("event_edges"),
        "review_queue": artifact_hashes.get("review_queue"),
    }
    generation_id = None
    if status == "ok":
        generation_id = _generation_id(
            as_of=as_of,
            artifact_hashes=hashes,
            source_ledger_receipt=source_receipt,
        )
    return {
        "schema": "capital_structure.telemetry.v1",
        "status": status,
        "as_of": as_of,
        "generation_id": generation_id,
        "authority": {
            "is_context_only": True,
            "rank_authority": False,
            "sizing_authority": False,
            "entry_authority": False,
            "prophet_authority": False,
        },
        "form_policy": FORM_POLICY,
        "coverage_claim": "registration_allowlist_plus_issuer_scoped_reconciliation",
        # Reconciliation is scoped, not blanket market coverage.  It is therefore
        # disclosed in ``form_policy`` but not mislabeled as an uncollected form.
        "known_exclusions": sorted({
            *FORM_POLICY["capital_relevant_declared_not_collected"],
        }),
        "counts": {key: int(value) for key, value in counts.items()},
        "compile_failures": [dict(failure) for failure in failures],
        "migration_receipt": _migration_receipt(),
        "source_ledger_receipt": source_receipt,
        "artifact_hashes": hashes,
    }


def compile_manifest_records(
    manifests: Sequence[Mapping[str, Any]],
    *,
    existing_events: Sequence[Mapping[str, Any]] = (),
    existing_edges: Sequence[Mapping[str, Any]] = (),
    manifest_schema: Mapping[str, Any] | None = None,
    event_schema: Mapping[str, Any] | None = None,
    edge_schema: Mapping[str, Any] | None = None,
    review_schema: Mapping[str, Any] | None = None,
    telemetry_schema: Mapping[str, Any] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Pure compile surface used by nightly and fixture tests."""
    now = generated_at or _now_iso()
    source_contract = manifest_schema or _load_contract("manifest")
    event_contract = event_schema or _load_contract("event")
    edge_contract = edge_schema or _load_contract("edge")
    review_contract = review_schema or _load_contract("review")
    telemetry_contract = telemetry_schema or _load_contract("telemetry")
    manifest_records = [dict(_native(record)) for record in manifests]
    # Identity/collision law is global, not accession-local quarantine. A
    # divergent ID in another accession can poison the ledger prefix and must
    # fail before any grouping or partial compilation occurs.
    validate_manifest_ledger(manifest_records)
    source_receipt = _source_ledger_receipt(manifest_records)
    groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    invalid_by_accession: dict[str, list[str]] = defaultdict(list)
    current_manifest_ids: set[str] = set()
    failures: list[dict[str, Any]] = []
    for native in manifest_records:
        manifest_id = str(native.get("manifest_id") or "")
        if manifest_id:
            current_manifest_ids.add(manifest_id)
        accession = str((native.get("filing") or {}).get("accession") or "")
        if not accession:
            failures.append({
                "accession": None, "state": "missing_accession",
                "errors": ["filing.accession is required"],
            })
            continue
        groups[accession].append(native)
        errors = _validate_manifest(native, source_contract)
        if errors:
            invalid_by_accession[accession].extend(errors)

    incoming: list[dict[str, Any]] = []
    existing = [copy.deepcopy(dict(event)) for event in existing_events]
    for index, event in enumerate(existing):
        _validate_contract(event, event_contract, label=f"existing event {index}")
        _validate_event_identity(event, label=f"existing event {index}")
    _validate_event_history(existing)
    existing_edge_rows = [copy.deepcopy(dict(edge)) for edge in existing_edges]
    for index, edge in enumerate(existing_edge_rows):
        _validate_contract(edge, edge_contract, label=f"existing edge {index}")
        _validate_edge_identity(edge, label=f"existing edge {index}")
    existing_event_ids = {str(event["event_id"]) for event in existing}
    for edge in existing_edge_rows:
        if (
            str(edge.get("from_event_id") or "") not in existing_event_ids
            or str(edge.get("to_event_id") or "") not in existing_event_ids
        ):
            raise ValueError(f"existing edge {edge.get('edge_id')} has an orphan endpoint")
    latest = _latest_events_by_logical_key(existing)
    for accession in sorted(groups):
        if invalid_by_accession.get(accession):
            failures.append({
                "accession": accession,
                "state": "invalid_source_manifest_bundle",
                "errors": invalid_by_accession[accession][:5],
            })
            continue
        try:
            candidate = event_from_manifest_group(groups[accession])
            logical_key = ("sec_edgar", accession)
            prior = latest.get(logical_key)
            if prior is not None and _semantic_event_body(candidate) == _semantic_event_body(prior):
                continue
            if prior is not None:
                produced = pd.Timestamp(now)
                prior_available = pd.Timestamp(
                    (prior.get("point_in_time") or {}).get("available_at")
                )
                if produced <= prior_available:
                    raise ValueError(
                        "correction generated_at must be later than the prior system availability"
                    )
                candidate = event_from_manifest_group(
                    groups[accession],
                    correction_version=int(
                        (prior.get("version") or {}).get("correction_version") or 1
                    ) + 1,
                    correction_of=str(prior["event_id"]),
                    produced_at=now,
                )
            _validate_contract(candidate, event_contract, label=f"compiled event {accession}")
            _validate_event_identity(candidate, label=f"compiled event {accession}")
            incoming.append(candidate)
            latest[logical_key] = candidate
        except Exception as exc:  # noqa: BLE001
            failures.append({
                "accession": accession, "state": "compile_deferred",
                "errors": [f"{type(exc).__name__}: {exc}"],
            })

    events = append_event_versions_strict(existing, incoming)
    _validate_event_history(events)
    if any(
        _canonical_json(event) != _canonical_json(events[index])
        for index, event in enumerate(existing)
    ):
        raise ValueError("existing immutable event prefix was not preserved")
    _validate_event_source_lineage(events, current_manifest_ids)
    graph = link_registration_graph(
        events, _linkage_metadata(events), existing_edges=existing_edge_rows
    )
    edges = _append_edges_strict(existing_edge_rows, graph["edges"])
    if any(
        _canonical_json(edge) != _canonical_json(edges[index])
        for index, edge in enumerate(existing_edge_rows)
    ):
        raise ValueError("existing immutable edge prefix was not preserved")
    review_queue = build_review_queue(events, graph, resolved_edges=edges)
    event_ids = {str(event["event_id"]) for event in events}
    for index, event in enumerate(events):
        _validate_contract(event, event_contract, label=f"output event {index}")
        _validate_event_identity(event, label=f"output event {index}")
    for index, edge in enumerate(edges):
        _validate_contract(edge, edge_contract, label=f"output edge {index}")
        _validate_edge_identity(edge, label=f"output edge {index}")
        if (
            str(edge.get("from_event_id") or "") not in event_ids
            or str(edge.get("to_event_id") or "") not in event_ids
        ):
            raise ValueError(f"output edge {edge.get('edge_id')} has an orphan endpoint")
    for index, item in enumerate(review_queue):
        _validate_contract(item, review_contract, label=f"review item {index}")
    payload_hashes = {
        "event_versions": hashlib.sha256(_canonical_json(events)).hexdigest(),
        "event_edges": hashlib.sha256(_canonical_json(edges)).hexdigest(),
        "review_queue": hashlib.sha256(_canonical_json(review_queue)).hexdigest(),
    }
    telemetry_status = (
        "degraded" if failures
        else "no_source_manifest" if not manifest_records
        else "ok"
    )
    telemetry = _build_telemetry(
        status=telemetry_status,
        as_of=now,
        counts={
            "source_manifests": len(manifest_records),
            "accessions_grouped": len(groups),
            "event_versions": len(events),
            "new_event_versions": len(incoming),
            "event_edges": len(edges),
            "review_queue": len(review_queue),
            "compile_failures": len(failures),
        },
        failures=failures,
        artifact_hashes=(
            payload_hashes
            if telemetry_status == "ok"
            else {
                "event_versions": None,
                "event_edges": None,
                "review_queue": None,
            }
        ),
        source_ledger_receipt=source_receipt,
    )
    _validate_contract(telemetry, telemetry_contract, label="compiler telemetry")
    return {
        "events": events,
        "edges": edges,
        "review_queue": review_queue,
        "telemetry": telemetry,
    }


def _event_frame(events: Sequence[Mapping[str, Any]]) -> pd.DataFrame:
    rows = []
    for event in events:
        filing = event.get("filing") or {}
        issuer = event.get("issuer") or {}
        point_in_time = event.get("point_in_time") or {}
        rows.append({
            "event_id": event["event_id"],
            "logical_event_id": f"sec:{filing.get('accession')}",
            "accession": filing.get("accession"),
            "cik": issuer.get("cik"),
            "ticker": issuer.get("ticker"),
            "form": filing.get("form"),
            "filing_date": filing.get("filing_date"),
            "accepted_at": filing.get("accepted_at"),
            "available_at": point_in_time.get("available_at"),
            "classification_state": (event.get("classification") or {}).get("state"),
            "correction_version": (event.get("version") or {}).get("correction_version"),
            "event_json": json.dumps(event, sort_keys=True, separators=(",", ":")),
        })
    return pd.DataFrame(rows, columns=EVENT_COLUMNS)


def _write_json(payload: Mapping[str, Any], path: Path) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _promote_generation(staged: Sequence[tuple[Path, Path]], backup_root: Path) -> None:
    """Promote staged files with rollback; callers place telemetry last.

    A hard kill cannot make four files atomically change together on a normal
    filesystem.  The last-promoted telemetry receipt is therefore the commit
    marker: its hashes either match the three artifacts or consumers must fail
    closed.  Ordinary exceptions roll every promoted target back immediately.
    """
    promoted: list[tuple[Path, Path | None]] = []
    try:
        for index, (source, target) in enumerate(staged):
            target.parent.mkdir(parents=True, exist_ok=True)
            backup: Path | None = None
            if target.exists():
                backup = backup_root / f"{index}-{target.name}.backup"
                shutil.copy2(target, backup)
            os.replace(source, target)
            promoted.append((target, backup))
    except Exception:
        for target, backup in reversed(promoted):
            if backup is None:
                target.unlink(missing_ok=True)
            else:
                shutil.copy2(backup, target)
        raise


def _empty_counts() -> dict[str, int]:
    return {
        "source_manifests": 0,
        "accessions_grouped": 0,
        "event_versions": 0,
        "new_event_versions": 0,
        "event_edges": 0,
        "review_queue": 0,
        "compile_failures": 0,
    }


def _staging_parent(root: Path) -> Path:
    """Choose a same-filesystem directory outside the governed artifact root."""
    parent = root.parent
    if root.name == "capital_structure" and parent.name == "data":
        parent = parent.parent
    parent.mkdir(parents=True, exist_ok=True)
    return parent


def _validate_committed_generation(
    root: Path,
    telemetry_schema: Mapping[str, Any],
    current_source_records: Sequence[Mapping[str, Any]],
) -> bool:
    """Verify output hashes and exact append-only source prefix before reuse."""
    artifact_paths = {
        "event_versions": root / "event_versions.parquet",
        "event_edges": root / "event_edges.parquet",
        "review_queue": root / "review_queue.parquet",
    }
    present = {key: path.exists() for key, path in artifact_paths.items()}
    telemetry_path = root / "telemetry.json"
    if not any(present.values()) and not telemetry_path.exists():
        return False
    if any(present.values()) and not all(present.values()):
        missing = sorted(key for key, exists in present.items() if not exists)
        raise ValueError(
            "capital-structure committed generation is incomplete; missing "
            + ", ".join(missing)
        )
    if not telemetry_path.exists():
        raise ValueError("capital-structure generation has no telemetry commit marker")
    try:
        telemetry = json.loads(telemetry_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("capital-structure telemetry commit marker is unreadable") from exc
    if not isinstance(telemetry, Mapping):
        raise ValueError("capital-structure telemetry commit marker must be an object")
    _validate_contract(telemetry, telemetry_schema, label="committed generation telemetry")
    source_receipt = telemetry.get("source_ledger_receipt") or {}
    prior_count = int(source_receipt.get("record_count") or 0)
    if prior_count != int((telemetry.get("counts") or {}).get("source_manifests") or 0):
        raise ValueError(
            "capital-structure source receipt count does not match telemetry counts"
        )
    if source_receipt.get("form_policy_version") != (
        telemetry.get("form_policy") or {}
    ).get("policy_version"):
        raise ValueError(
            "capital-structure source receipt policy does not match telemetry policy"
        )
    if len(current_source_records) < prior_count:
        raise ValueError(
            "capital-structure source ledger truncated below committed prefix length"
        )
    current_prefix = source_ledger_prefix_hash(current_source_records, count=prior_count)
    if current_prefix != str(source_receipt.get("prefix_sha256") or ""):
        raise ValueError(
            "capital-structure source ledger mutated or reordered inside committed prefix"
        )
    if not any(present.values()):
        if telemetry.get("status") in {"no_source_manifest", "degraded"}:
            return False
        raise ValueError(
            "capital-structure telemetry claims a generation but all artifacts are missing"
        )
    if telemetry.get("status") != "ok":
        raise ValueError("capital-structure data artifacts require status=ok telemetry")
    expected_hashes = telemetry.get("artifact_hashes") or {}
    expected_generation_id = _generation_id(
        as_of=str(telemetry.get("as_of") or ""),
        artifact_hashes=expected_hashes,
        source_ledger_receipt=source_receipt,
    )
    if telemetry.get("generation_id") != expected_generation_id:
        raise ValueError("capital-structure generation_id does not bind its artifact hashes")
    for key, path in artifact_paths.items():
        if _sha256_file(path) != str(expected_hashes.get(key) or ""):
            raise ValueError(
                f"capital-structure generation receipt hash mismatch for {key}"
            )
    return True


def compile_from_disk(*, root: Path | None = None, generated_at: str | None = None) -> dict[str, Any]:
    root = root or _data_root()
    now = generated_at or _now_iso()
    contracts = {kind: _load_contract(kind) for kind in CONTRACT_FILES}
    manifest_path = root / "source_manifest.parquet"
    manifests = (
        dataframe_records(pd.read_parquet(manifest_path))
        if manifest_path.exists()
        else []
    )
    has_prior_generation = _validate_committed_generation(
        root, contracts["telemetry"], manifests
    )
    if not manifests:
        if has_prior_generation:  # defensive; a committed ok receipt requires >= 1 row
            raise ValueError("verified generation cannot have an empty source ledger")
        empty_source_receipt = _source_ledger_receipt([])
        telemetry = _build_telemetry(
            status="no_source_manifest",
            as_of=now,
            counts=_empty_counts(),
            failures=[],
            artifact_hashes={
                "event_versions": None,
                "event_edges": None,
                "review_queue": None,
            },
            source_ledger_receipt=empty_source_receipt,
        )
        _validate_contract(telemetry, contracts["telemetry"], label="no-source telemetry")
        root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix=".capital-structure-compile-", dir=_staging_parent(root)
        ) as tmp_dir:
            stage_root = Path(tmp_dir)
            telemetry_stage = stage_root / "telemetry.json"
            _write_json(telemetry, telemetry_stage)
            _promote_generation(
                [(telemetry_stage, root / "telemetry.json")], stage_root
            )
        return {
            "status": "no_source_manifest",
            "events": 0, "edges": 0, "review_queue": 0, "failures": 0,
        }
    event_path = root / "event_versions.parquet"
    edge_path = root / "event_edges.parquet"
    existing = _load_existing_events(
        pd.read_parquet(event_path) if event_path.exists() else None,
        contracts["event"],
    )
    existing_edges = _load_existing_edges(
        pd.read_parquet(edge_path) if edge_path.exists() else None,
        contracts["edge"],
    )
    result = compile_manifest_records(
        manifests,
        existing_events=existing,
        existing_edges=existing_edges,
        manifest_schema=contracts["manifest"],
        event_schema=contracts["event"],
        edge_schema=contracts["edge"],
        review_schema=contracts["review"],
        telemetry_schema=contracts["telemetry"],
        generated_at=now,
    )
    if result["telemetry"]["status"] != "ok":
        # Per-accession failures are not a partially successful generation.
        # Preserve the prior telemetry-last marker and every prior ledger byte.
        raise CapitalStructureCompileDegraded(result["telemetry"])
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".capital-structure-compile-", dir=_staging_parent(root)
    ) as tmp_dir:
        stage_root = Path(tmp_dir)
        event_stage = stage_root / "event_versions.parquet"
        edge_stage = stage_root / "event_edges.parquet"
        review_stage = stage_root / "review_queue.parquet"
        telemetry_stage = stage_root / "telemetry.json"
        _event_frame(result["events"]).to_parquet(event_stage, index=False)
        pd.DataFrame(result["edges"], columns=EDGE_COLUMNS).to_parquet(edge_stage, index=False)
        pd.DataFrame(result["review_queue"], columns=REVIEW_COLUMNS).to_parquet(
            review_stage, index=False
        )
        # Validate the serialized representation, not only the in-memory records.
        roundtrip_events = _load_existing_events(
            pd.read_parquet(event_stage), contracts["event"]
        )
        roundtrip_edges = _load_existing_edges(
            pd.read_parquet(edge_stage), contracts["edge"]
        )
        roundtrip_review_frame = pd.read_parquet(review_stage)
        if roundtrip_review_frame.columns.tolist() != REVIEW_COLUMNS:
            raise ValueError("staged review queue columns changed during serialization")
        roundtrip_review = dataframe_records(roundtrip_review_frame)
        for index, item in enumerate(roundtrip_review):
            _validate_contract(item, contracts["review"], label=f"staged review item {index}")
        if [item["event_id"] for item in roundtrip_events] != [
            item["event_id"] for item in result["events"]
        ]:
            raise ValueError("staged event ledger changed during serialization")
        if [item["edge_id"] for item in roundtrip_edges] != [
            item["edge_id"] for item in result["edges"]
        ]:
            raise ValueError("staged edge ledger changed during serialization")
        if [item["queue_id"] for item in roundtrip_review] != [
            item["queue_id"] for item in result["review_queue"]
        ]:
            raise ValueError("staged review queue changed during serialization")
        artifact_hashes = {
            "event_versions": _sha256_file(event_stage),
            "event_edges": _sha256_file(edge_stage),
            "review_queue": _sha256_file(review_stage),
        }
        result["telemetry"] = _build_telemetry(
            status="ok",
            as_of=now,
            counts=result["telemetry"]["counts"],
            failures=result["telemetry"]["compile_failures"],
            artifact_hashes=artifact_hashes,
            source_ledger_receipt=result["telemetry"]["source_ledger_receipt"],
        )
        _validate_contract(
            result["telemetry"], contracts["telemetry"], label="generation telemetry"
        )
        _write_json(result["telemetry"], telemetry_stage)
        # Telemetry is the generation commit marker and must be promoted last.
        _promote_generation(
            [
                (event_stage, event_path),
                (edge_stage, edge_path),
                (review_stage, root / "review_queue.parquet"),
                (telemetry_stage, root / "telemetry.json"),
            ],
            stage_root,
        )
    return {
        "status": "ok",
        "events": len(result["events"]),
        "edges": len(result["edges"]),
        "review_queue": len(result["review_queue"]),
        "failures": result["telemetry"]["counts"]["compile_failures"],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=None, help="capital-structure data dir")
    args = parser.parse_args(argv)
    summary = compile_from_disk(root=args.root)
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
