"""Closed-world candidate-term projection for the issuer-state build.

This module is intentionally pre-instrument.  A validated document-term row is
projected one-for-one into an immutable *candidate term* so later resolver work
has a clean, point-in-time input.  It performs no fuzzy joining, never creates
an ``instrument_id``, and cannot calculate capacity, dilution, risk, or a
trading/Prophet decision.

The important distinction is temporal: a document-term may have been available
in the source ledger before this compiler ran, but the candidate-term becomes
available only when this deterministic projection is actually compiled.  This
prevents a later W3A deployment from silently backdating its own knowledge.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from engine.capital_structure.document_terms import (
    DOCUMENT_TERM_SCHEMA,
    current_document_terms_as_of,
    validate_document_term_history,
    validate_observation_source_binding,
)
from engine.capital_structure.source_identity import (
    validate_manifest_content_binding,
    validate_manifest_ledger,
)


INSTRUMENT_CANDIDATE_TERM_SCHEMA = "capital_structure.instrument_candidate_term.v1"
MAPPING_VERSION = "capital-structure-instrument-candidate-terms/1.0.0"
_DIRECT_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "contracts" / "capital_structure_document_term_observation.schema.json"
_CANDIDATE_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "contracts" / "capital_structure_instrument_candidate_term.schema.json"

_FAMILY_BY_DIRECT_CLASSIFICATION = {
    "common_stock": "common_stock",
    "preferred_stock": "preferred_stock",
    "debt": "debt",
    "units": "units",
    "warrants": "warrant",
    "other": "other",
}
_SUPPORTED_TERM_TYPES = {
    "amount_to_be_registered": {"share_count", "principal_amount", "quantity"},
    "proposed_maximum_offering_price_per_unit": {"price"},
    "proposed_maximum_aggregate_offering_price": {"amount"},
    "registration_fee": {"amount"},
    "filing_fee_rate": {"rate"},
}


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _digest_id(prefix: str, body: Mapping[str, Any]) -> str:
    return prefix + _sha256(body)[:24]


def _parse_time(value: Any, field: str) -> datetime:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError(f"{field} is required")
    try:
        parsed = datetime.fromisoformat(raw[:-1] + "+00:00" if raw.endswith("Z") else raw)
    except ValueError as exc:
        raise ValueError(f"{field} must be ISO-8601: {raw!r}") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _iso(value: Any, field: str) -> str:
    return _parse_time(value, field).isoformat().replace("+00:00", "Z")


def _load_schema(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_schema(record: Mapping[str, Any], schema: Mapping[str, Any], label: str) -> None:
    from jsonschema import Draft202012Validator, FormatChecker

    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(record))
    if errors:
        joined = "; ".join(
            f"{'.'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
            for error in errors[:5]
        )
        raise ValueError(f"{label} contract violation: {joined}")


def direct_observation_sha256(record: Mapping[str, Any]) -> str:
    """Return the exact canonical digest of a validated direct observation."""
    return _sha256(record)


def logical_candidate_term_id_for(source: Mapping[str, Any]) -> str:
    """Stable one-to-one slot identity; it intentionally contains no instrument key."""
    return _digest_id(
        "instrument-candidate-term-slot:cs:",
        {
            "source_logical_observation_id": source.get("logical_observation_id"),
            "mapping_version": MAPPING_VERSION,
        },
    )


def candidate_term_id_for(record: Mapping[str, Any]) -> str:
    body = deepcopy(dict(record))
    body.pop("candidate_term_id", None)
    return _digest_id("instrument-candidate-term:cs:", body)


def _source_receipt(source: Mapping[str, Any], source_digest: str) -> dict[str, Any]:
    point_in_time = source.get("point_in_time") or {}
    body = {
        "direct_observation_id": source.get("observation_id"),
        "direct_observation_sha256": source_digest,
        "direct_available_at": point_in_time.get("available_at"),
    }
    return {
        "schema": "capital_structure.instrument_candidate_term_input_receipt.v1",
        "receipt_id": _digest_id("receipt:instrument-candidate-term-input:cs:", body),
        "verification_state": "validated_document_term_observation",
        **body,
    }


def candidate_mapping_for_document_term(source: Mapping[str, Any]) -> dict[str, Any]:
    """Classify only what the source row directly closes.

    ``registration_security_candidate`` is deliberately weaker than primary,
    resale, active, executable, or available capacity.  Only the direct amount
    field can receive it; fee, rate, and price rows are linked evidence but do
    not establish a supply role.
    """
    upstream_state = source.get("state") or {}
    disposition = str(upstream_state.get("disposition") or "")
    if disposition == "ambiguous":
        return {
            "mapping_version": MAPPING_VERSION,
            "family": "unknown",
            "supply_role": "unknown",
            "state": {"disposition": "ambiguous", "reason": "upstream_document_term_ambiguous"},
        }
    if disposition != "observed":
        return {
            "mapping_version": MAPPING_VERSION,
            "family": "unknown",
            "supply_role": "unknown",
            "state": {"disposition": "deferred", "reason": "upstream_document_term_unavailable"},
        }

    term = source.get("term") or {}
    name = str(term.get("name") or "")
    term_type = str(term.get("term_type") or "")
    if term_type not in _SUPPORTED_TERM_TYPES.get(name, set()):
        return {
            "mapping_version": MAPPING_VERSION,
            "family": "unknown",
            "supply_role": "unknown",
            "state": {"disposition": "deferred", "reason": "unsupported_source_term_type"},
        }

    security = source.get("security") or {}
    row_id = security.get("row_id")
    classification = str(security.get("classification") or "unknown")
    if row_id is None:
        return {
            "mapping_version": MAPPING_VERSION,
            "family": "unknown",
            "supply_role": "unknown",
            "state": {"disposition": "deferred", "reason": "missing_security_row"},
        }
    family = _FAMILY_BY_DIRECT_CLASSIFICATION.get(classification)
    if family is None:
        return {
            "mapping_version": MAPPING_VERSION,
            "family": "unknown",
            "supply_role": "unknown",
            "state": {"disposition": "deferred", "reason": "security_classification_unknown"},
        }
    if name == "amount_to_be_registered":
        return {
            "mapping_version": MAPPING_VERSION,
            "family": family,
            "supply_role": "registration_security_candidate",
            "state": {"disposition": "observed", "reason": "direct_security_class_mapping"},
        }
    return {
        "mapping_version": MAPPING_VERSION,
        "family": family,
        "supply_role": "not_applicable",
        "state": {
            "disposition": "observed",
            "reason": "direct_security_class_mapping_supply_not_applicable",
        },
    }


def _candidate_semantic_key(record: Mapping[str, Any]) -> tuple[str, str, str]:
    source = record.get("source_term") or {}
    candidate = record.get("candidate") or {}
    return (
        str(source.get("observation_id") or ""),
        str(source.get("observation_sha256") or ""),
        str(candidate.get("mapping_version") or ""),
    )


def _embedded_mapping_source(record: Mapping[str, Any]) -> dict[str, Any]:
    """Return the closed mapping inputs carried inside a candidate record.

    This intentionally needs no external ledger so standalone validation catches
    a family/supply-role mutation even if an attacker recomputes the immutable
    candidate ID.  The compiler performs the stronger whole-source binding
    separately when the direct ledger is available.
    """
    return {
        "state": deepcopy(record.get("source_term_state") or {}),
        "security": deepcopy(record.get("security") or {}),
        "term": deepcopy(record.get("term") or {}),
    }


def validate_candidate_source_binding(record: Mapping[str, Any], source: Mapping[str, Any]) -> None:
    """Prove a candidate remains an exact projection of one direct source row.

    The candidate ledger keeps copied evidence for queryability, but that copy is
    not trusted merely because its candidate ID was recomputed.  This binding is
    checked whenever the offline compiler sees the append-only direct ledger.
    """
    source_digest = direct_observation_sha256(source)
    source_term = record.get("source_term") or {}
    source_point = source.get("point_in_time") or {}
    if (
        source_term.get("schema") != DOCUMENT_TERM_SCHEMA
        or source_term.get("observation_id") != source.get("observation_id")
        or source_term.get("logical_observation_id") != source.get("logical_observation_id")
        or int(source_term.get("correction_version") or 0)
        != int((source.get("version") or {}).get("correction_version") or 0)
        or source_term.get("observation_sha256") != source_digest
        or source_term.get("source_available_at") != source_point.get("source_available_at")
        or source_term.get("available_at") != source_point.get("available_at")
        or source_term.get("receipt") != _source_receipt(source, source_digest)
    ):
        raise ValueError("instrument candidate-term source receipt does not bind its direct observation")
    copied_fields = (
        "issuer_id", "filing", "document", "security", "term", "reported",
        "normalized", "evidence", "extraction",
    )
    for field in copied_fields:
        if record.get(field) != source.get(field):
            raise ValueError(f"instrument candidate-term {field} is detached from its direct observation")
    if record.get("source_term_state") != source.get("state"):
        raise ValueError("instrument candidate-term source_term_state is detached from its direct observation")
    point = record.get("point_in_time") or {}
    if (
        point.get("source_available_at") != source_point.get("source_available_at")
        or point.get("source_term_available_at") != source_point.get("available_at")
    ):
        raise ValueError("instrument candidate-term point-in-time source lineage is detached")
    relationships = record.get("relationships") or {}
    if list(relationships.get("source_observation_supersedes") or []) != list(
        (source.get("relationships") or {}).get("supersedes") or []
    ):
        raise ValueError("instrument candidate-term source supersedes lineage is detached")
    if record.get("logical_candidate_term_id") != logical_candidate_term_id_for(source):
        raise ValueError("instrument candidate-term logical identity is detached from its direct observation")
    if record.get("candidate") != candidate_mapping_for_document_term(source):
        raise ValueError("instrument candidate-term mapping is detached from its direct observation")


def _validate_candidate_term_structure(records: Sequence[Mapping[str, Any]]) -> None:
    """Validate candidate-local shape, IDs, and correction chains only.

    This is intentionally private: a candidate record duplicates direct-term
    fields, and a recomputed candidate ID can make an altered duplicate look
    structurally self-consistent.  It is therefore not proof of issuer,
    evidence, direct-value, or source-receipt authority.  Public validation and
    all PIT reads bind these rows to verified direct observations below.
    """
    schema = _load_schema(_CANDIDATE_SCHEMA_PATH)
    by_id: set[str] = set()
    by_logical: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for index, raw in enumerate(records):
        record = dict(raw)
        _validate_schema(record, schema, f"instrument candidate-term row {index}")
        candidate_id = str(record.get("candidate_term_id") or "")
        if candidate_id != candidate_term_id_for(record):
            raise ValueError(f"instrument candidate-term row {index} candidate_term_id digest mismatch")
        if candidate_id in by_id:
            raise ValueError(f"duplicate instrument candidate-term candidate_term_id {candidate_id}")
        by_id.add(candidate_id)
        source = record.get("source_term") or {}
        receipt = source.get("receipt") or {}
        if (
            source.get("observation_id") != receipt.get("direct_observation_id")
            or source.get("observation_sha256") != receipt.get("direct_observation_sha256")
            or source.get("available_at") != receipt.get("direct_available_at")
        ):
            raise ValueError(f"instrument candidate-term row {index} source receipt is detached")
        expected_receipt = _source_receipt(
            {
                "observation_id": source.get("observation_id"),
                "point_in_time": {"available_at": source.get("available_at")},
            },
            str(source.get("observation_sha256") or ""),
        )
        if receipt != expected_receipt:
            raise ValueError(f"instrument candidate-term row {index} source receipt digest mismatch")
        point = record.get("point_in_time") or {}
        source_available = _parse_time(point.get("source_available_at"), "source_available_at")
        direct_available = _parse_time(point.get("source_term_available_at"), "source_term_available_at")
        available = _parse_time(point.get("available_at"), "available_at")
        if direct_available < source_available or available < direct_available:
            raise ValueError(f"instrument candidate-term row {index} point-in-time lineage is retroactive")
        if record.get("candidate") != candidate_mapping_for_document_term(_embedded_mapping_source(record)):
            raise ValueError(f"instrument candidate-term row {index} candidate mapping is detached from embedded source fields")
        logical = str(record.get("logical_candidate_term_id") or "")
        if not logical:
            raise ValueError(f"instrument candidate-term row {index} lacks logical_candidate_term_id")
        by_logical[logical].append(record)

    for logical, versions in by_logical.items():
        ordered = sorted(versions, key=lambda row: int((row.get("version") or {}).get("correction_version") or 0))
        actual = [int((row.get("version") or {}).get("correction_version") or 0) for row in ordered]
        if actual != list(range(1, len(ordered) + 1)):
            raise ValueError(f"instrument candidate-term {logical} has non-contiguous correction versions")
        for number, record in enumerate(ordered, start=1):
            version = record.get("version") or {}
            relationships = record.get("relationships") or {}
            prior = ordered[number - 2] if number > 1 else None
            if prior is None:
                if version.get("correction_of") is not None or list(relationships.get("supersedes") or []):
                    raise ValueError(f"instrument candidate-term {logical} v1 cannot be a correction")
                continue
            if version.get("correction_of") != prior.get("candidate_term_id"):
                raise ValueError(f"instrument candidate-term {logical} correction does not point to prior version")
            if list(relationships.get("supersedes") or []) != [prior.get("candidate_term_id")]:
                raise ValueError(f"instrument candidate-term {logical} supersedes does not point to prior version")
            prior_time = _parse_time((prior.get("point_in_time") or {}).get("available_at"), "prior.available_at")
            current_time = _parse_time((record.get("point_in_time") or {}).get("available_at"), "available_at")
            if current_time <= prior_time:
                raise ValueError(f"instrument candidate-term {logical} correction is retroactive")


def validate_candidate_term_structure(records: Sequence[Mapping[str, Any]]) -> None:
    """Run untrusted candidate-local integrity checks without source authority.

    This helper is suitable only for safely decoding a ledger before the caller
    supplies the direct-term authority needed for trusted validation.  It must
    never be used to authorize semantic or PIT reads.
    """
    _validate_candidate_term_structure(records)


def _validate_candidate_term_history_against_sources(
    records: Sequence[Mapping[str, Any]], direct_sources: Sequence[Mapping[str, Any]],
) -> None:
    _validate_candidate_term_structure(records)
    sources_by_id = {str(row["observation_id"]): row for row in direct_sources}
    for index, record in enumerate(records):
        source_id = str((record.get("source_term") or {}).get("observation_id") or "")
        source = sources_by_id.get(source_id)
        if source is None:
            raise ValueError(
                f"instrument candidate-term row {index} source observation is absent from verified direct ledger"
            )
        validate_candidate_source_binding(record, source)


def validate_candidate_term_history(
    records: Sequence[Mapping[str, Any]],
    *,
    document_term_observations: Sequence[Mapping[str, Any]],
    source_manifests: Sequence[Mapping[str, Any]],
    source_reader: Callable[[Mapping[str, Any]], bytes | None],
) -> None:
    """Validate candidates against the verified direct-term source authority.

    Candidate-local IDs detect accidental corruption but are not an authority
    boundary.  A trusted read must prove each copied issuer, evidence span, and
    direct fact against the validated direct ledger and its retained source
    bytes.
    """
    direct_sources = validate_document_term_authority(
        document_term_observations,
        source_manifests=source_manifests,
        source_reader=source_reader,
    )
    _validate_candidate_term_history_against_sources(records, direct_sources)


def current_candidate_terms_as_of(
    records: Sequence[Mapping[str, Any]],
    as_of: str,
    *,
    document_term_observations: Sequence[Mapping[str, Any]],
    source_manifests: Sequence[Mapping[str, Any]],
    source_reader: Callable[[Mapping[str, Any]], bytes | None],
) -> list[dict[str, Any]]:
    """Return verified candidate versions visible strictly at system time."""
    validate_candidate_term_history(
        records,
        document_term_observations=document_term_observations,
        source_manifests=source_manifests,
        source_reader=source_reader,
    )
    cutoff = _parse_time(as_of, "as_of")
    visible: dict[str, Mapping[str, Any]] = {}
    for raw in records:
        record = dict(raw)
        available = _parse_time((record.get("point_in_time") or {}).get("available_at"), "available_at")
        if available > cutoff:
            continue
        logical = str(record["logical_candidate_term_id"])
        prior = visible.get(logical)
        if prior is None or int((record.get("version") or {}).get("correction_version") or 0) > int((prior.get("version") or {}).get("correction_version") or 0):
            visible[logical] = record
    return [dict(visible[key]) for key in sorted(visible)]


def validate_document_term_authority(
    records: Sequence[Mapping[str, Any]],
    *,
    source_manifests: Sequence[Mapping[str, Any]],
    source_reader: Callable[[Mapping[str, Any]], bytes | None],
) -> list[dict[str, Any]]:
    """Verify direct-term rows against immutable manifests and retained bytes.

    Candidate receipts name a direct observation, but no digest alone can prove
    that the candidate's copied issuer/evidence/value came from that observation.
    Reuse the direct-term source validator before a candidate ledger is compiled
    or read, so a self-consistent edit to either Parquet file fails closed.
    """
    schema = _load_schema(_DIRECT_SCHEMA_PATH)
    sources = [deepcopy(dict(raw)) for raw in records]
    manifests = [deepcopy(dict(raw)) for raw in source_manifests]
    validate_manifest_ledger(manifests)
    for index, manifest in enumerate(manifests):
        validate_manifest_content_binding(manifest)
    for index, source in enumerate(sources):
        _validate_schema(source, schema, f"document-term input row {index}")
    validate_document_term_history(sources)

    manifests_by_id = {str(manifest["manifest_id"]): manifest for manifest in manifests}
    source_cache: dict[str, bytes] = {}
    for index, source in enumerate(sources):
        manifest_id = str((source.get("document") or {}).get("source_manifest_id") or "")
        manifest = manifests_by_id.get(manifest_id)
        if manifest is None:
            raise ValueError(f"document-term input row {index} source manifest is absent")
        raw = source_cache.get(manifest_id)
        if raw is None:
            loaded = source_reader(manifest)
            if not isinstance(loaded, bytes):
                raise ValueError(f"document-term input row {index} retained source bytes are unavailable")
            source_cache[manifest_id] = loaded
            raw = loaded
        validate_observation_source_binding(source, manifest, raw)
    return sources


def _project_record(
    source: Mapping[str, Any], *, generated_at: str, correction_version: int, correction_of: str | None,
) -> dict[str, Any]:
    source_digest = direct_observation_sha256(source)
    source_point = source.get("point_in_time") or {}
    source_relationships = source.get("relationships") or {}
    record: dict[str, Any] = {
        "schema": INSTRUMENT_CANDIDATE_TERM_SCHEMA,
        "logical_candidate_term_id": logical_candidate_term_id_for(source),
        "issuer_id": source["issuer_id"],
        "source_term": {
            "schema": DOCUMENT_TERM_SCHEMA,
            "observation_id": source["observation_id"],
            "logical_observation_id": source["logical_observation_id"],
            "correction_version": int((source.get("version") or {}).get("correction_version") or 0),
            "observation_sha256": source_digest,
            "source_available_at": source_point["source_available_at"],
            "available_at": source_point["available_at"],
            "receipt": _source_receipt(source, source_digest),
        },
        "candidate": candidate_mapping_for_document_term(source),
        "filing": deepcopy(source["filing"]),
        "document": deepcopy(source["document"]),
        "security": deepcopy(source["security"]),
        "term": deepcopy(source["term"]),
        "source_term_state": deepcopy(source["state"]),
        "reported": deepcopy(source["reported"]),
        "normalized": deepcopy(source["normalized"]),
        "evidence": deepcopy(source["evidence"]),
        "extraction": deepcopy(source["extraction"]),
        "relationships": {
            "supersedes": [correction_of] if correction_of else [],
            "source_observation_supersedes": list(source_relationships.get("supersedes") or []),
            "contradiction_ids": [],
        },
        "version": {
            "immutable_record": True,
            "correction_version": correction_version,
            "correction_of": correction_of,
        },
        "point_in_time": {
            "source_available_at": source_point["source_available_at"],
            "source_term_available_at": source_point["available_at"],
            "available_at": generated_at,
        },
        "authority": {
            "is_context_only": True,
            "instrument_authority": False,
            "capacity_authority": False,
            "risk_authority": False,
            "probability_authority": False,
            "rank_authority": False,
            "sizing_authority": False,
            "entry_authority": False,
            "trade_authority": False,
            "prophet_authority": False,
        },
    }
    record["candidate_term_id"] = candidate_term_id_for(record)
    return record


def compile_candidate_term_records(
    document_term_observations: Sequence[Mapping[str, Any]],
    *,
    source_manifests: Sequence[Mapping[str, Any]],
    source_reader: Callable[[Mapping[str, Any]], bytes | None],
    existing_candidate_terms: Sequence[Mapping[str, Any]] = (),
    generated_at: str,
    source_as_of: str | None = None,
) -> dict[str, Any]:
    """Project current direct terms into an append-only candidate-term ledger.

    A first run intentionally establishes a fresh candidate baseline from the
    latest direct row visible in the input ledger.  It does **not** replay old
    upstream corrections with fabricated historical candidate availability.
    Subsequent source corrections create an ordinary candidate correction when
    this compiler observes them.
    """
    generated = _iso(generated_at, "generated_at")
    direct_sources = validate_document_term_authority(
        document_term_observations,
        source_manifests=source_manifests,
        source_reader=source_reader,
    )
    existing = [deepcopy(dict(raw)) for raw in existing_candidate_terms]
    _validate_candidate_term_history_against_sources(existing, direct_sources)

    if source_as_of is None:
        source_cutoff = max(
            (_parse_time((row.get("point_in_time") or {}).get("available_at"), "source.available_at") for row in direct_sources),
            default=_parse_time(generated, "generated_at"),
        ).isoformat().replace("+00:00", "Z")
    else:
        source_cutoff = _iso(source_as_of, "source_as_of")
        latest_direct = max(
            (_parse_time((row.get("point_in_time") or {}).get("available_at"), "source.available_at") for row in direct_sources),
            default=_parse_time(generated, "generated_at"),
        )
        if _parse_time(source_cutoff, "source_as_of") < latest_direct:
            raise ValueError(
                "historical source_as_of cannot write the canonical candidate ledger; "
                "use a read-only isolated replay instead"
            )
    selected = current_document_terms_as_of(direct_sources, source_cutoff) if direct_sources else []
    for source in selected:
        direct_available = _parse_time((source.get("point_in_time") or {}).get("available_at"), "source.available_at")
        if _parse_time(generated, "generated_at") < direct_available:
            raise ValueError("generated_at cannot precede a selected document-term availability")

    current_by_logical: dict[str, Mapping[str, Any]] = {}
    for record in existing:
        logical = str(record["logical_candidate_term_id"])
        prior = current_by_logical.get(logical)
        if prior is None or int((record.get("version") or {}).get("correction_version") or 0) > int((prior.get("version") or {}).get("correction_version") or 0):
            current_by_logical[logical] = record

    additions: list[dict[str, Any]] = []
    unchanged = 0
    for source in sorted(selected, key=lambda row: str(row["logical_observation_id"])):
        logical = logical_candidate_term_id_for(source)
        prior = current_by_logical.get(logical)
        source_digest = direct_observation_sha256(source)
        next_key = (str(source["observation_id"]), source_digest, MAPPING_VERSION)
        if prior is not None and _candidate_semantic_key(prior) == next_key:
            unchanged += 1
            continue
        correction_version = 1 if prior is None else int((prior.get("version") or {}).get("correction_version") or 0) + 1
        correction_of = None if prior is None else str(prior["candidate_term_id"])
        if prior is not None:
            prior_available = _parse_time((prior.get("point_in_time") or {}).get("available_at"), "prior.available_at")
            if _parse_time(generated, "generated_at") <= prior_available:
                raise ValueError("generated_at must be later than the prior candidate-term correction")
        additions.append(_project_record(
            source,
            generated_at=generated,
            correction_version=correction_version,
            correction_of=correction_of,
        ))

    observations = existing + additions
    _validate_candidate_term_history_against_sources(observations, direct_sources)
    return {
        "observations": sorted(
            observations,
            key=lambda row: (str(row["logical_candidate_term_id"]), int((row.get("version") or {}).get("correction_version") or 0)),
        ),
        "counts": {
            "input_document_terms": len(direct_sources),
            "input_current_document_terms": len(selected),
            "created": len(additions),
            "unchanged": unchanged,
            "total": len(observations),
        },
        "source_as_of": source_cutoff,
    }
