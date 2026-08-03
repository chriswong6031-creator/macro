"""Pure authenticated SEC Company Facts -> share-count v2 materializer.

This module is deliberately a closed *model* boundary.  It receives the full
already-selected ordered Company Facts manifest prefix, only the next bounded
raw-byte batch, and the selected signed coverage receipt plus an injected pure
verifier.  It does not read storage, choose a current count, calculate
dilution, or emit a decision/risk/Prophet claim.

The materializer's canonical availability clock is ``materialized_at``.  SEC
Company Facts has no fact-level public availability timestamp, so
``public_available_at`` is explicitly null rather than guessed from the filing
date or the source retrieval clock.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Protocol

from .share_count_truth import (
    SUPPORTED_FACTS,
    _Definition,
    _accession_or_none,
    _candidate_source_issue,
    _decimal_text,
    _fact_filing,
    _fact_period,
    _source_entry,
    _string_or_none,
    _validate_canonical_fact_evidence,
    _valid_date,
)


BRIDGE_RECEIPT_SCHEMA = "capital_structure.companyfacts_bridge_receipt.v2"
OBSERVATION_SCHEMA = "capital_structure.share_count_observation.v2"
SOURCE_SNAPSHOT_SCHEMA = "capital_structure.companyfacts_source_snapshot.v2"
SNAPSHOT_FACT_SCHEMA = "capital_structure.share_count_snapshot_fact_observation.v2"
LEDGER_RECEIPT_SCHEMA = "capital_structure.share_count_ledger_receipt.v2"
LEDGER_SCHEMA = "capital_structure.share_count_ledger.v2"
COMPILER_VERSION = "capital-structure-share-count-materializer/2.1.0"

MAX_SOURCE_PREFIX = 16_384
MAX_SOURCE_BATCH = 24
MAX_SOURCE_BYTES = 64 * 1024 * 1024
MAX_TOTAL_SOURCE_BYTES = 256 * 1024 * 1024
MAX_COVERAGE_RECEIPT_BYTES = 4 * 1024 * 1024
MAX_MANIFEST_METADATA_BYTES = 512 * 1024
MAX_PREFIX_METADATA_BYTES = 32 * 1024 * 1024
MAX_SUPPORTED_FACT_ENTRIES_PER_SOURCE = 250_000
MAX_LEDGER_OBSERVATIONS = 1_000_000
MAX_SNAPSHOT_FACT_VIEWS = 1_000_000
MAX_LEDGER_RECEIPTS = 4_096
MAX_LEDGER_BYTES = 128 * 1024 * 1024

_PREFIX_DOMAIN = "capital-structure-share-count-ledger-prefix/v1"
_PREFIX_FIELDS = {
    "observations": "observation_ids",
    "source_snapshots": "source_snapshot_ids",
    "bridges": "bridge_receipt_ids",
    "source_manifests": "source_manifest_ids",
}

_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
_MANIFEST_ID_RE = re.compile(r"^manifest:cs-companyfacts:[a-f0-9]{64}$")
_ISSUER_RE = re.compile(r"^issuer:([0-9]{10})$")


class ShareCountMaterializerError(ValueError):
    """An authenticated Company Facts prefix cannot safely materialize."""


class CoverageReceiptVerifier(Protocol):
    """Pure signature verifier for the selected Company Facts receipt."""

    def verify(self, payload: bytes, signature: str, *, key_id: str) -> bool: ...


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ShareCountMaterializerError("materializer input is not canonical JSON data") from exc


def _digest_id(prefix: str, value: Any) -> str:
    return prefix + hashlib.sha256(_canonical_json(value)).hexdigest()[:24]


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _parse_timestamp(value: Any, field: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        raise ShareCountMaterializerError(f"{field} is required")
    try:
        parsed = datetime.fromisoformat(raw[:-1] + "+00:00" if raw.endswith("Z") else raw)
    except ValueError as exc:
        raise ShareCountMaterializerError(f"{field} must be ISO-8601 with timezone") from exc
    if parsed.tzinfo is None:
        raise ShareCountMaterializerError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _authority() -> dict[str, bool]:
    return {
        "is_context_only": True,
        "share_count_ledger_authority": False,
        "instrument_authority": False,
        "capacity_authority": False,
        "runway_authority": False,
        "risk_authority": False,
        "rank_authority": False,
        "sizing_authority": False,
        "entry_authority": False,
        "trade_authority": False,
        "prophet_authority": False,
    }


def bridge_receipt_id_for(record: Mapping[str, Any]) -> str:
    material = deepcopy(dict(record))
    material.pop("bridge_receipt_id", None)
    return _digest_id("companyfacts-bridge:cs:", material)


def logical_observation_id_for(record: Mapping[str, Any]) -> str:
    metric, fact, period, filing = (
        record.get("metric") or {}, record.get("fact") or {}, record.get("period") or {}, record.get("filing") or {},
    )
    return _digest_id("share-count-slot-v2:cs:", {
        "issuer_id": record.get("issuer_id"), "metric_kind": metric.get("kind"),
        "namespace": fact.get("namespace"), "name": fact.get("name"), "unit": fact.get("unit"),
        "period_end": period.get("period_end"), "accession": filing.get("accession"),
        "form": filing.get("form"), "filed": filing.get("filed"),
    })


def fact_revision_id_for(record: Mapping[str, Any]) -> str:
    evidence = record.get("evidence") or {}
    entry_hashes = sorted(
        str(item.get("entry_sha256") or "")
        for item in evidence.get("fact_entries") or [] if isinstance(item, Mapping)
    )
    return _digest_id("share-count-revision-v2:cs:", {
        "logical_observation_id": record.get("logical_observation_id"),
        "metric": record.get("metric"), "fact": record.get("fact"),
        "security_class": record.get("security_class"), "period": record.get("period"),
        "filing": record.get("filing"), "entry_sha256s": entry_hashes,
    })


def observation_id_for(record: Mapping[str, Any]) -> str:
    material = deepcopy(dict(record))
    material.pop("observation_id", None)
    return _digest_id("share-count-v2:cs:", material)


def snapshot_fact_observation_id_for(record: Mapping[str, Any]) -> str:
    material = deepcopy(dict(record))
    material.pop("snapshot_fact_observation_id", None)
    return _digest_id("share-count-snapshot-fact-v2:cs:", material)


def source_snapshot_id_for(record: Mapping[str, Any]) -> str:
    material = deepcopy(dict(record))
    material.pop("source_snapshot_id", None)
    return _digest_id("companyfacts-snapshot-v2:cs:", material)


def ledger_receipt_id_for(record: Mapping[str, Any]) -> str:
    material = deepcopy(dict(record))
    material.pop("ledger_receipt_id", None)
    return _digest_id("share-count-ledger-receipt-v2:cs:", material)


def _empty_prefix(label: str) -> dict[str, Any]:
    if label not in _PREFIX_FIELDS:
        raise ShareCountMaterializerError("unknown share-count ledger prefix domain")
    return {
        "count": 0,
        "rolling_sha256": _sha256(_canonical_json({
            "domain": _PREFIX_DOMAIN,
            "label": label,
            "genesis": True,
        })),
    }


def _advance_prefix(
    previous: Mapping[str, Any], *, label: str, appended_ids: Sequence[str],
) -> dict[str, Any]:
    expected_keys = {"count", "rolling_sha256"}
    if (
        label not in _PREFIX_FIELDS
        or not isinstance(previous, Mapping)
        or set(previous) != expected_keys
        or isinstance(previous.get("count"), bool)
        or not isinstance(previous.get("count"), int)
        or previous["count"] < 0
        or not isinstance(previous.get("rolling_sha256"), str)
        or _SHA256_RE.fullmatch(previous["rolling_sha256"]) is None
    ):
        raise ShareCountMaterializerError("share-count rolling prefix is invalid")
    ordered = list(appended_ids)
    if any(not isinstance(value, str) or not value for value in ordered):
        raise ShareCountMaterializerError("share-count rolling prefix append is invalid")
    if not ordered:
        return dict(previous)
    return {
        "count": int(previous["count"]) + len(ordered),
        "rolling_sha256": _sha256(_canonical_json({
            "domain": _PREFIX_DOMAIN,
            "label": label,
            "previous": dict(previous),
            "appended_ids": ordered,
        })),
    }


def _empty_prefixes() -> dict[str, dict[str, Any]]:
    return {label: _empty_prefix(label) for label in _PREFIX_FIELDS}


def _schema(name: str) -> dict[str, Any]:
    path = Path(__file__).resolve().parents[2] / "contracts" / name
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_schema(record: Mapping[str, Any], filename: str, label: str) -> None:
    from jsonschema import Draft202012Validator, FormatChecker

    errors = list(Draft202012Validator(_schema(filename), format_checker=FormatChecker()).iter_errors(dict(record)))
    if errors:
        detail = "; ".join(
            f"{'.'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
            for error in errors[:5]
        )
        raise ShareCountMaterializerError(f"{label} contract violation: {detail}")


def _coverage_receipt_identity(record: Mapping[str, Any]) -> str:
    material = deepcopy(dict(record))
    material.pop("receipt_id", None)
    auth = material.get("auth")
    if isinstance(auth, Mapping):
        auth = dict(auth)
        auth.pop("signature", None)
        material["auth"] = auth
    return "receipt:cs-companyfacts:" + hashlib.sha256(_canonical_json(material)).hexdigest()


def _coverage_auth_payload(record: Mapping[str, Any]) -> bytes:
    material = deepcopy(dict(record))
    auth = material.get("auth")
    if not isinstance(auth, Mapping):
        raise ShareCountMaterializerError("coverage receipt has no authentication envelope")
    auth = dict(auth)
    auth.pop("signature", None)
    material["auth"] = auth
    return _canonical_json({"domain": "capital_structure.companyfacts_receipt/v1", "receipt": material})


def _coverage_generation_id(record: Mapping[str, Any]) -> str:
    generation = record.get("generation") or {}
    source = generation.get("source_manifest") or {}
    coverage = generation.get("coverage") or {}
    material = {
        "schema": "capital_structure.companyfacts_generation/v1",
        "source_manifest_file": {"sha256": source.get("sha256"), "byte_length": source.get("byte_length")},
        "coverage_file": {"sha256": coverage.get("sha256"), "byte_length": coverage.get("byte_length")},
        "source_manifest_ledger": dict(record.get("companyfacts_manifest_ledger") or {}),
        "coverage_ledger": dict(record.get("coverage_ledger") or {}),
    }
    return "generation:cs-companyfacts:" + hashlib.sha256(_canonical_json(material)).hexdigest()


def _ordered_prefix_receipt(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    hasher = hashlib.sha256()
    total = 0
    for index, item in enumerate(records):
        encoded = _canonical_json(dict(item))
        if len(encoded) > MAX_MANIFEST_METADATA_BYTES:
            raise ShareCountMaterializerError(f"ordered prefix manifest {index} exceeds metadata bound")
        total += len(encoded) + 1
        if total > MAX_PREFIX_METADATA_BYTES:
            raise ShareCountMaterializerError("ordered prefix exceeds metadata aggregate bound")
        hasher.update(encoded)
        hasher.update(b"\n")
    digest = hasher.hexdigest()
    return {"record_count": len(records), "prefix_sha256": digest, "immutable_prefix": True}


def _canonical_cik(value: Any, *, field: str) -> str:
    raw = str(value or "").strip()
    if not raw.isdigit() or len(raw) > 10 or int(raw) == 0:
        raise ShareCountMaterializerError(f"{field} must be a positive SEC CIK")
    return raw.zfill(10)


def _validate_store_binding(*, backend: Any, store_id: Any, label: str) -> None:
    expected = {
        "capital_structure_local": "local", "r2_capital_structure": "r2",
        "r2_research": "r2", "r2_shared": "r2",
    }.get(str(store_id or ""))
    if expected is None or backend != expected:
        raise ShareCountMaterializerError(f"{label} backend/store_id binding is invalid")


def _validate_source_manifest(record: Mapping[str, Any]) -> dict[str, Any]:
    """Validate every material identity axis before raw bytes are parsed."""
    native = deepcopy(dict(record))
    _validate_schema(native, "capital_structure_companyfacts_source_manifest.schema.json", "Company Facts source manifest")
    manifest_id = str(native.get("manifest_id") or "")
    material = dict(native)
    material.pop("manifest_id", None)
    expected_id = "manifest:cs-companyfacts:" + hashlib.sha256(_canonical_json(material)).hexdigest()
    if manifest_id != expected_id:
        raise ShareCountMaterializerError("Company Facts source manifest identity digest mismatch")
    issuer, source, request = native["issuer"], native["content"], native["request"]
    storage, anchor, retrieval = native["storage"], native["anchor"], native["retrieval"]
    cik = _canonical_cik(issuer["cik"], field="source manifest issuer.cik")
    digest, byte_length = str(source["content_sha256"]), int(source["byte_length"])
    if (
        issuer["issuer_id"] != f"sec:cik:{cik}"
        or native["source_id"] != f"sec-companyfacts:{cik}:{digest}"
        or request["canonical_url"] != f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
        or source["root_locator"] != f"sha256:{digest}"
        or storage["object_key"] != f"capital_structure/sec/sha256/{digest[:2]}/{digest}"
        or native["spans"] != [{"span_id": f"root:{digest}", "locator_type": "document", "locator": f"bytes:0-{byte_length}", "text_sha256": digest}]
    ):
        raise ShareCountMaterializerError("Company Facts source manifest content identity is detached")
    _validate_store_binding(backend=storage["backend"], store_id=storage["store_id"], label="Company Facts source storage")
    _validate_store_binding(backend=anchor["complete_submission_backend"], store_id=anchor["complete_submission_store_id"], label="Company Facts anchor storage")
    anchor_digest = str(anchor["complete_submission_sha256"])
    if anchor["complete_submission_object_key"] != f"capital_structure/sec/sha256/{anchor_digest[:2]}/{anchor_digest}":
        raise ShareCountMaterializerError("Company Facts anchor object key is detached from its digest")
    retrieved = _parse_timestamp(retrieval["retrieved_at"], "source manifest retrieval.retrieved_at")
    first_seen = _parse_timestamp(retrieval["first_seen_at"], "source manifest retrieval.first_seen_at")
    if retrieved != first_seen:
        raise ShareCountMaterializerError("Company Facts source manifest retrieval clocks are not exact")
    if native["source_system"] != "sec_edgar_companyfacts" or native["parser"] != {
        "eligibility": "eligible", "corruption_state": "clean", "parser_version": "companyfacts-json-cik-validator/1.0.0",
    }:
        raise ShareCountMaterializerError("Company Facts source manifest is not an eligible clean SEC capture")
    if native.get("authority") != {
        "is_context_only": True, "share_count_ledger_authority": False, "instrument_authority": False,
        "capacity_authority": False, "runway_authority": False, "risk_authority": False,
        "rank_authority": False, "sizing_authority": False, "entry_authority": False, "prophet_authority": False,
    }:
        raise ShareCountMaterializerError("Company Facts source manifest authority is not all-false")
    return native


def _validate_authenticated_selection(
    authenticated_manifests: Sequence[Mapping[str, Any]], source_inputs: Sequence[bytes], coverage_receipt: Mapping[str, Any],
    coverage_receipt_bytes: bytes, verifier: CoverageReceiptVerifier,
) -> tuple[list[dict[str, Any]], list[bytes], dict[str, Any]]:
    if isinstance(authenticated_manifests, (str, bytes)) or not isinstance(authenticated_manifests, Sequence):
        raise ShareCountMaterializerError("authenticated_manifests must be an ordered sequence")
    if not authenticated_manifests or len(authenticated_manifests) > MAX_SOURCE_PREFIX:
        raise ShareCountMaterializerError("authenticated_manifests must be a nonempty bounded prefix")
    if isinstance(source_inputs, (str, bytes)) or not isinstance(source_inputs, Sequence) or len(source_inputs) > MAX_SOURCE_BATCH:
        raise ShareCountMaterializerError("source_inputs must be a bounded ordered raw-byte batch")
    if not isinstance(coverage_receipt_bytes, bytes):
        raise ShareCountMaterializerError("coverage_receipt_bytes must be exact receipt bytes")
    if len(coverage_receipt_bytes) > MAX_COVERAGE_RECEIPT_BYTES:
        raise ShareCountMaterializerError("coverage receipt exceeds materializer byte bound")
    receipt = deepcopy(dict(coverage_receipt))
    _validate_schema(receipt, "capital_structure_companyfacts_coverage_receipt.schema.json", "coverage receipt")
    expected_bytes = _canonical_json(receipt) + b"\n"
    if coverage_receipt_bytes != expected_bytes:
        raise ShareCountMaterializerError("coverage receipt bytes are not the exact canonical selected receipt")
    if receipt.get("receipt_id") != _coverage_receipt_identity(receipt):
        raise ShareCountMaterializerError("coverage receipt identity digest mismatch")
    auth = receipt.get("auth") or {}
    signature, key_id = auth.get("signature"), auth.get("key_id")
    if not isinstance(signature, str) or not isinstance(key_id, str) or not verifier.verify(
        _coverage_auth_payload(receipt), signature, key_id=key_id,
    ):
        raise ShareCountMaterializerError("coverage receipt authentication mismatch")
    if receipt.get("generation", {}).get("generation_id") != _coverage_generation_id(receipt):
        raise ShareCountMaterializerError("coverage receipt generation identity mismatch")

    manifests: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, source_manifest in enumerate(authenticated_manifests):
        manifest = _validate_source_manifest(source_manifest)
        manifest_id = str(manifest["manifest_id"])
        if manifest_id in seen:
            raise ShareCountMaterializerError(f"authenticated manifest prefix repeats a Company Facts manifest at {index}")
        seen.add(manifest_id)
        manifests.append(manifest)
    raw_batch: list[bytes] = []
    total_bytes = 0
    for index, raw in enumerate(source_inputs):
        if not isinstance(raw, bytes):
            raise ShareCountMaterializerError(f"source input {index} must be raw bytes")
        if len(raw) > MAX_SOURCE_BYTES:
            raise ShareCountMaterializerError("source input exceeds materializer byte bound")
        total_bytes += len(raw)
        if total_bytes > MAX_TOTAL_SOURCE_BYTES:
            raise ShareCountMaterializerError("source input batch exceeds aggregate materializer byte bound")
        raw_batch.append(raw)
    prefix = _ordered_prefix_receipt(manifests)
    if prefix != receipt.get("companyfacts_manifest_ledger"):
        raise ShareCountMaterializerError("coverage receipt does not bind the exact ordered Company Facts manifest prefix")
    return manifests, raw_batch, receipt


def _bridge_receipt(manifest: Mapping[str, Any], receipt: Mapping[str, Any], *, materialized_at: str, receipt_bytes: bytes) -> dict[str, Any]:
    issuer, content, storage = manifest["issuer"], manifest["content"], manifest["storage"]
    record: dict[str, Any] = {
        "schema": BRIDGE_RECEIPT_SCHEMA, "bridge_receipt_id": "", "source_manifest_id": manifest["manifest_id"],
        "issuer": {"issuer_id": f"issuer:{issuer['cik']}", "cik": issuer["cik"]},
        "source": {
            "source_id": manifest["source_id"], "source_url": manifest["request"]["canonical_url"],
            "content_sha256": content["content_sha256"], "byte_length": content["byte_length"],
            "backend": storage["backend"], "store_id": storage["store_id"], "object_key": storage["object_key"],
        },
        "anchor": deepcopy(dict(manifest["anchor"])),
        "selection": {
            "coverage_receipt_id": receipt["receipt_id"],
            "coverage_receipt": {"sha256": _sha256(receipt_bytes), "byte_length": len(receipt_bytes)},
            "coverage_sequence": receipt["sequence"], "generation": deepcopy(dict(receipt["generation"])),
            "companyfacts_manifest_prefix": deepcopy(dict(receipt["companyfacts_manifest_ledger"])),
            "coverage_prefix": deepcopy(dict(receipt["coverage_ledger"])),
        },
        "point_in_time": {
            "source_retrieved_at": _parse_timestamp(manifest["retrieval"]["retrieved_at"], "source manifest retrieval"),
            "materialized_at": materialized_at, "available_at": materialized_at, "public_available_at": None,
        },
        "authority": _authority(),
    }
    record["bridge_receipt_id"] = bridge_receipt_id_for(record)
    validate_bridge_receipt(record)
    return record


def _fact_candidates(payload: Mapping[str, Any], *, issuer_id: str, materialized_at: str) -> list[dict[str, Any]]:
    facts = payload.get("facts")
    if not isinstance(facts, Mapping):
        raise ShareCountMaterializerError("Company Facts payload must contain facts object")
    candidates: list[dict[str, Any]] = []
    for (namespace, name), definition in SUPPORTED_FACTS.items():
        taxonomy = facts.get(namespace)
        concept = taxonomy.get(name) if isinstance(taxonomy, Mapping) else None
        units = concept.get("units") if isinstance(concept, Mapping) else None
        if not isinstance(units, Mapping):
            continue
        for raw_unit, raw_entries in sorted(units.items(), key=lambda item: str(item[0])):
            unit = str(raw_unit)
            entries = raw_entries if isinstance(raw_entries, list) else [raw_entries]
            for index, entry in enumerate(entries):
                if len(candidates) >= MAX_SUPPORTED_FACT_ENTRIES_PER_SOURCE:
                    raise ShareCountMaterializerError("supported Company Facts entries exceed materializer bound")
                source_issue = _candidate_source_issue(entry, unit, definition)
                mapping = entry if isinstance(entry, Mapping) else {}
                filed = _valid_date(mapping.get("filed"))
                issue = source_issue
                if issue is None and filed is not None and _timestamp(materialized_at).date() < date.fromisoformat(filed):
                    issue = "materialization_precedes_filed_date"
                entry_evidence = _source_entry(
                    pointer=f"/facts/{namespace}/{name}/units/{unit}/{index}",
                    entry=entry, unit=unit, source_issue=source_issue,
                )
                # Retain the exact decoded JSON value committed by the entry
                # hash. Opaque hashes alone cannot re-derive a downstream value.
                entry_evidence["raw_entry"] = deepcopy(
                    dict(entry) if isinstance(entry, Mapping) else entry,
                )
                candidates.append({
                    "definition": definition, "namespace": namespace, "name": name, "unit": unit, "entry": entry,
                    "entry_evidence": entry_evidence,
                    "issue": issue,
                    "slot_key": (
                        issuer_id, definition.metric_kind, namespace, name, unit, _valid_date(mapping.get("end")),
                        _accession_or_none(mapping.get("accn")), _string_or_none(mapping.get("form"), max_length=32), filed,
                    ),
                })
    return candidates


def _state_for_group(group: Sequence[Mapping[str, Any]]) -> tuple[str, str]:
    values = {str(item["entry_evidence"]["value"]) for item in group if item["entry_evidence"]["value"] is not None}
    if len(values) > 1:
        return "ambiguous", "multiple_distinct_values_for_fact_slot"
    contexts = {(item["entry_evidence"]["fiscal_year"], item["entry_evidence"]["fiscal_period"], item["entry_evidence"]["frame"]) for item in group}
    if len(contexts) > 1:
        return "ambiguous", "multiple_distinct_contexts_for_fact_slot"
    issues = sorted(str(item["issue"]) for item in group if item.get("issue"))
    return ("deferred", issues[0]) if issues else ("observed", "direct_sec_companyfacts_fact")


def _record_from_group(group: Sequence[Mapping[str, Any]], *, bridge: Mapping[str, Any]) -> dict[str, Any]:
    ordered = sorted(group, key=lambda item: item["entry_evidence"]["json_pointer"])
    first, definition = ordered[0], ordered[0]["definition"]
    disposition, reason = _state_for_group(ordered)
    raw_value, unit = first["entry_evidence"]["value"], str(first["unit"])
    if disposition == "observed":
        reported = {"value": raw_value, "unit": unit, "scale": "1"}
        normalized = {"value": raw_value, "unit": definition.expected_unit, "scale": "1", "state": "observed"}
    elif disposition == "ambiguous":
        reported = {"value": None, "unit": unit, "scale": "1"}
        normalized = {"value": None, "unit": None, "scale": None, "state": "ambiguous"}
    else:
        reported = {"value": raw_value, "unit": unit, "scale": "1"}
        normalized = {"value": None, "unit": None, "scale": None, "state": "deferred"}
    record: dict[str, Any] = {
        "schema": OBSERVATION_SCHEMA, "observation_id": "", "logical_observation_id": "", "fact_revision_id": "",
        "issuer_id": bridge["issuer"]["issuer_id"], "metric": {"kind": definition.metric_kind, "scope": "direct_sec_companyfacts_fact"},
        "fact": {"namespace": first["namespace"], "name": first["name"], "unit": unit, "scale": "1", "source_value_encoding": "companyfacts_actual_units"},
        "security_class": {"state": definition.security_state, "classification": definition.security_classification, "raw_label": None, "basis": definition.security_basis},
        "period": _fact_period(first["entry"]), "filing": _fact_filing(first["entry"]),
        "state": {"disposition": disposition, "reason": reason}, "reported": reported, "normalized": normalized,
        "evidence": {"bridge_receipt_id": bridge["bridge_receipt_id"], "source_manifest_id": bridge["source_manifest_id"], "fact_entries": [deepcopy(item["entry_evidence"]) for item in ordered]},
        "point_in_time": deepcopy(dict(bridge["point_in_time"])), "relationships": {"supersedes": [], "contradiction_ids": []},
        "version": {"immutable_record": True, "correction_version": 1, "correction_of": None}, "authority": _authority(),
    }
    record["logical_observation_id"] = logical_observation_id_for(record)
    record["fact_revision_id"] = fact_revision_id_for(record)
    record["observation_id"] = observation_id_for(record)
    validate_share_count_observation(record)
    return record


def _apply_correction(
    candidate: Mapping[str, Any], *, current: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], bool]:
    if current is None:
        return dict(candidate), True
    if current.get("fact_revision_id") == candidate.get("fact_revision_id"):
        return dict(current), False
    corrected = deepcopy(dict(candidate))
    corrected["version"] = {"immutable_record": True, "correction_version": int(current["version"]["correction_version"]) + 1, "correction_of": current["observation_id"]}
    corrected["relationships"] = {"supersedes": [current["observation_id"]], "contradiction_ids": []}
    corrected["observation_id"] = observation_id_for(corrected)
    validate_share_count_observation(corrected)
    return corrected, True


def _entry_hashes(record: Mapping[str, Any]) -> list[str]:
    hashes = sorted({str(item.get("entry_sha256") or "") for item in (record.get("evidence") or {}).get("fact_entries") or [] if isinstance(item, Mapping)})
    if not hashes or any(_SHA256_RE.fullmatch(value) is None for value in hashes):
        raise ShareCountMaterializerError("fact evidence has no valid entry hashes")
    return hashes


def _semantics_from_evidence(record: Mapping[str, Any], *, materialized_at: str) -> dict[str, Any]:
    """Re-derive direct-fact state without trusting a stored disposition."""
    fact = record.get("fact") or {}
    definition = SUPPORTED_FACTS.get((str(fact.get("namespace") or ""), str(fact.get("name") or "")))
    if definition is None:
        raise ShareCountMaterializerError("observation names unsupported Company Facts fact semantics")
    if record.get("metric") != {
        "kind": definition.metric_kind,
        "scope": "direct_sec_companyfacts_fact",
    }:
        raise ShareCountMaterializerError(
            "observation metric is detached from Company Facts concept semantics",
        )
    if record.get("security_class") != {
        "state": definition.security_state,
        "classification": definition.security_classification,
        "raw_label": None,
        "basis": definition.security_basis,
    }:
        raise ShareCountMaterializerError(
            "observation security class is detached from Company Facts concept semantics",
        )
    entries = [dict(entry) for entry in (record.get("evidence") or {}).get("fact_entries") or [] if isinstance(entry, Mapping)]
    if not entries:
        raise ShareCountMaterializerError("observation lacks direct fact entries")
    pointers = [str(entry.get("json_pointer") or "") for entry in entries]
    if pointers != sorted(pointers) or len(set(pointers)) != len(pointers):
        raise ShareCountMaterializerError("observation fact-entry pointers must be sorted and unique")
    unit = str(fact.get("unit") or "")
    for entry in entries:
        if "raw_entry" not in entry:
            raise ShareCountMaterializerError("observation fact entry lacks exact raw JSON evidence")
        raw_entry = entry["raw_entry"]
        expected_entry = _source_entry(
            pointer=str(entry.get("json_pointer") or ""), entry=raw_entry,
            unit=unit,
            source_issue=_candidate_source_issue(raw_entry, unit, definition),
        )
        expected_entry["raw_entry"] = deepcopy(raw_entry)
        if entry != expected_entry:
            raise ShareCountMaterializerError(
                "observation fact entry does not re-derive from exact raw JSON evidence",
            )
    _validate_canonical_fact_evidence(record, entries, definition)
    first_raw = entries[0]["raw_entry"]
    if record.get("period") != _fact_period(first_raw):
        raise ShareCountMaterializerError(
            "observation period is detached from exact raw JSON evidence",
        )
    if record.get("filing") != _fact_filing(first_raw):
        raise ShareCountMaterializerError(
            "observation filing is detached from exact raw JSON evidence",
        )
    values = {str(entry["value"]) for entry in entries if entry.get("value") is not None}
    contexts = {(entry.get("fiscal_year"), entry.get("fiscal_period"), entry.get("frame")) for entry in entries}
    if len(values) > 1:
        disposition, reason = "ambiguous", "multiple_distinct_values_for_fact_slot"
    elif len(contexts) > 1:
        disposition, reason = "ambiguous", "multiple_distinct_contexts_for_fact_slot"
    else:
        issues: set[str] = set()
        for entry in entries:
            source_issue = entry.get("source_issue")
            if source_issue is not None:
                issues.add(str(source_issue))
                continue
            filed = _valid_date(entry.get("filed"))
            if filed is None:
                issues.add("missing_filing_provenance")
            elif _timestamp(materialized_at).date() < date.fromisoformat(filed):
                issues.add("materialization_precedes_filed_date")
        disposition, reason = ("deferred", sorted(issues)[0]) if issues else ("observed", "direct_sec_companyfacts_fact")
    value = entries[0].get("value")
    if disposition == "observed":
        reported = {"value": value, "unit": unit, "scale": "1"}
        normalized = {"value": value, "unit": definition.expected_unit, "scale": "1", "state": "observed"}
    elif disposition == "ambiguous":
        reported = {"value": None, "unit": unit, "scale": "1"}
        normalized = {"value": None, "unit": None, "scale": None, "state": "ambiguous"}
    else:
        reported = {"value": value, "unit": unit, "scale": "1"}
        normalized = {"value": None, "unit": None, "scale": None, "state": "deferred"}
    return {"state": {"disposition": disposition, "reason": reason}, "reported": reported, "normalized": normalized}


def _snapshot_fact(candidate: Mapping[str, Any], applied: Mapping[str, Any], bridge: Mapping[str, Any]) -> dict[str, Any]:
    record: dict[str, Any] = {
        "schema": SNAPSHOT_FACT_SCHEMA, "snapshot_fact_observation_id": "", "bridge_receipt_id": bridge["bridge_receipt_id"], "source_manifest_id": bridge["source_manifest_id"],
        "logical_observation_id": candidate["logical_observation_id"], "fact_revision_id": candidate["fact_revision_id"], "observation_id": applied["observation_id"],
        "state": deepcopy(candidate["state"]), "reported": deepcopy(candidate["reported"]), "normalized": deepcopy(candidate["normalized"]),
        "point_in_time": deepcopy(bridge["point_in_time"]), "fact_entry_sha256s": _entry_hashes(candidate), "authority": _authority(),
    }
    record["snapshot_fact_observation_id"] = snapshot_fact_observation_id_for(record)
    validate_snapshot_fact_observation(record)
    return record


def _source_snapshot(
    bridge: Mapping[str, Any], facts: Sequence[Mapping[str, Any]],
    observations: Sequence[Mapping[str, Any]], *,
    canonical_by_id: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    ordered = sorted((deepcopy(dict(fact)) for fact in facts), key=lambda fact: str(fact["logical_observation_id"]))
    record: dict[str, Any] = {
        "schema": SOURCE_SNAPSHOT_SCHEMA, "source_snapshot_id": "", "bridge_receipt_id": bridge["bridge_receipt_id"], "source_manifest_id": bridge["source_manifest_id"],
        "bridge_receipt": deepcopy(dict(bridge)), "snapshot_fact_observations": ordered,
        "fact_links": [{"logical_observation_id": fact["logical_observation_id"], "snapshot_fact_observation_id": fact["snapshot_fact_observation_id"]} for fact in ordered], "authority": _authority(),
    }
    record["source_snapshot_id"] = source_snapshot_id_for(record)
    validate_source_snapshot(
        record, observations, canonical_by_id=canonical_by_id,
    )
    return record


def _append_ledger_receipt(
    receipts: Sequence[Mapping[str, Any]], observations: Sequence[Mapping[str, Any]],
    snapshots: Sequence[Mapping[str, Any]], *, materialized_at: str,
) -> list[dict[str, Any]]:
    """Append one constant-size transition for one bounded materializer batch."""
    existing = [deepcopy(dict(item)) for item in receipts]
    previous_prefixes = (
        deepcopy(dict(existing[-1]["prefixes"])) if existing else _empty_prefixes()
    )
    previous_snapshot_count = int(previous_prefixes["source_snapshots"]["count"])
    previous_observation_count = int(previous_prefixes["observations"]["count"])
    if previous_snapshot_count > len(snapshots) or previous_observation_count > len(observations):
        raise ShareCountMaterializerError("ledger receipt prefix exceeds canonical history")
    appended_snapshots = list(snapshots[previous_snapshot_count:])
    appended_observations = list(observations[previous_observation_count:])
    if not appended_snapshots:
        return existing
    if len(appended_snapshots) > MAX_SOURCE_BATCH:
        raise ShareCountMaterializerError("ledger receipt append exceeds source batch bound")
    if existing and _timestamp(materialized_at) < _timestamp(str(existing[-1]["materialized_at"])):
        raise ShareCountMaterializerError("materializer clock cannot move backward in the ledger chain")
    appended = {
        "observation_ids": [str(item["observation_id"]) for item in appended_observations],
        "source_snapshot_ids": [str(item["source_snapshot_id"]) for item in appended_snapshots],
        "bridge_receipt_ids": [str(item["bridge_receipt_id"]) for item in appended_snapshots],
        "source_manifest_ids": [str(item["source_manifest_id"]) for item in appended_snapshots],
    }
    prefixes = {
        label: _advance_prefix(
            previous_prefixes[label], label=label,
            appended_ids=appended[field],
        )
        for label, field in _PREFIX_FIELDS.items()
    }
    record: dict[str, Any] = {
        "schema": LEDGER_RECEIPT_SCHEMA, "ledger_receipt_id": "", "sequence": len(existing) + 1,
        "predecessor_ledger_receipt_id": None if not existing else existing[-1]["ledger_receipt_id"], "materialized_at": materialized_at,
        "appended": appended, "prefixes": prefixes,
    }
    record["ledger_receipt_id"] = ledger_receipt_id_for(record)
    validate_ledger_receipt(record)
    return [*existing, record]


def validate_bridge_receipt(record: Mapping[str, Any]) -> None:
    _validate_schema(record, "capital_structure_companyfacts_bridge_receipt.schema.json", "bridge receipt")
    if record.get("bridge_receipt_id") != bridge_receipt_id_for(record):
        raise ShareCountMaterializerError("bridge receipt identity digest mismatch")
    issuer, source, anchor, selection, point = record["issuer"], record["source"], record["anchor"], record["selection"], record["point_in_time"]
    cik = _canonical_cik(issuer["cik"], field="bridge issuer.cik")
    if issuer["issuer_id"] != f"issuer:{cik}" or source["source_id"] != f"sec-companyfacts:{cik}:{source['content_sha256']}" or source["source_url"] != f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json":
        raise ShareCountMaterializerError("bridge receipt issuer/source identity is detached")
    if source["object_key"] != f"capital_structure/sec/sha256/{source['content_sha256'][:2]}/{source['content_sha256']}":
        raise ShareCountMaterializerError("bridge receipt source object key is detached")
    _validate_store_binding(backend=source["backend"], store_id=source["store_id"], label="bridge source storage")
    _validate_store_binding(backend=anchor["complete_submission_backend"], store_id=anchor["complete_submission_store_id"], label="bridge anchor storage")
    if anchor["complete_submission_object_key"] != f"capital_structure/sec/sha256/{anchor['complete_submission_sha256'][:2]}/{anchor['complete_submission_sha256']}":
        raise ShareCountMaterializerError("bridge anchor object key is detached")
    if selection["generation"]["generation_id"].split(":")[-1] not in selection["generation"]["source_manifest"]["path"] or selection["generation"]["generation_id"].split(":")[-1] not in selection["generation"]["coverage"]["path"]:
        raise ShareCountMaterializerError("bridge generation paths are detached from generation identity")
    source_retrieved = _parse_timestamp(point["source_retrieved_at"], "bridge source_retrieved_at")
    materialized = _parse_timestamp(point["materialized_at"], "bridge materialized_at")
    if point["available_at"] != materialized or point["public_available_at"] is not None or _timestamp(materialized) < _timestamp(source_retrieved):
        raise ShareCountMaterializerError("bridge point-in-time clocks are invalid")
    if record["authority"] != _authority():
        raise ShareCountMaterializerError("bridge authority is not all-false")


def validate_share_count_observation(record: Mapping[str, Any]) -> None:
    _validate_schema(record, "capital_structure_share_count_observation_v2.schema.json", "share-count v2 observation")
    if record.get("logical_observation_id") != logical_observation_id_for(record) or record.get("fact_revision_id") != fact_revision_id_for(record) or record.get("observation_id") != observation_id_for(record):
        raise ShareCountMaterializerError("share-count v2 observation identity digest mismatch")
    point = record["point_in_time"]
    source_retrieved = _parse_timestamp(point["source_retrieved_at"], "observation source_retrieved_at")
    materialized = _parse_timestamp(point["materialized_at"], "observation materialized_at")
    if point["available_at"] != materialized or point["public_available_at"] is not None or _timestamp(materialized) < _timestamp(source_retrieved):
        raise ShareCountMaterializerError("observation point-in-time clocks are invalid")
    if record["authority"] != _authority():
        raise ShareCountMaterializerError("observation authority is not all-false")
    if not _MANIFEST_ID_RE.fullmatch(str((record.get("evidence") or {}).get("source_manifest_id") or "")):
        raise ShareCountMaterializerError("observation evidence source manifest is invalid")
    _entry_hashes(record)
    expected = _semantics_from_evidence(record, materialized_at=materialized)
    if any(record[field] != expected[field] for field in ("state", "reported", "normalized")):
        raise ShareCountMaterializerError("observation state does not re-derive from direct evidence")


def validate_snapshot_fact_observation(record: Mapping[str, Any]) -> None:
    _validate_schema(record, "capital_structure_share_count_snapshot_fact_observation_v2.schema.json", "snapshot-fact v2 observation")
    if record.get("snapshot_fact_observation_id") != snapshot_fact_observation_id_for(record):
        raise ShareCountMaterializerError("snapshot-fact v2 observation identity digest mismatch")
    hashes = list(record["fact_entry_sha256s"])
    if hashes != sorted(hashes) or len(hashes) != len(set(hashes)):
        raise ShareCountMaterializerError("snapshot-fact entry hashes must be sorted and unique")
    point = record["point_in_time"]
    if point["available_at"] != point["materialized_at"] or point["public_available_at"] is not None:
        raise ShareCountMaterializerError("snapshot-fact availability must be materialization availability")
    if _timestamp(_parse_timestamp(point["materialized_at"], "snapshot-fact materialized_at")) < _timestamp(_parse_timestamp(point["source_retrieved_at"], "snapshot-fact source_retrieved_at")):
        raise ShareCountMaterializerError("snapshot-fact materialization precedes source retrieval")
    if record["authority"] != _authority():
        raise ShareCountMaterializerError("snapshot-fact authority is not all-false")


def validate_source_snapshot(
    snapshot: Mapping[str, Any], observations: Sequence[Mapping[str, Any]], *,
    canonical_by_id: Mapping[str, Mapping[str, Any]] | None = None,
) -> None:
    _validate_schema(snapshot, "capital_structure_companyfacts_source_snapshot_v2.schema.json", "source snapshot v2")
    if snapshot.get("source_snapshot_id") != source_snapshot_id_for(snapshot):
        raise ShareCountMaterializerError("source snapshot identity digest mismatch")
    bridge = snapshot.get("bridge_receipt")
    if not isinstance(bridge, Mapping):
        raise ShareCountMaterializerError("source snapshot bridge receipt is absent")
    validate_bridge_receipt(bridge)
    if snapshot["bridge_receipt_id"] != bridge["bridge_receipt_id"] or snapshot["source_manifest_id"] != bridge["source_manifest_id"]:
        raise ShareCountMaterializerError("source snapshot bridge links are detached")
    canonical = (
        dict(canonical_by_id)
        if canonical_by_id is not None
        else {str(row.get("observation_id")): row for row in observations}
    )
    seen_ids, seen_logical = set(), set()
    for fact in snapshot["snapshot_fact_observations"]:
        validate_snapshot_fact_observation(fact)
        fact_id, logical_id = fact["snapshot_fact_observation_id"], fact["logical_observation_id"]
        if fact_id in seen_ids or logical_id in seen_logical:
            raise ShareCountMaterializerError("source snapshot repeats a snapshot fact slot")
        seen_ids.add(fact_id); seen_logical.add(logical_id)
        row = canonical.get(str(fact["observation_id"]))
        if row is None or row["logical_observation_id"] != logical_id or row["fact_revision_id"] != fact["fact_revision_id"]:
            raise ShareCountMaterializerError("snapshot fact does not resolve canonical observation lineage")
        if row.get("issuer_id") != bridge["issuer"]["issuer_id"]:
            raise ShareCountMaterializerError(
                "canonical observation is detached from its authenticated source bridge",
            )
        if fact["bridge_receipt_id"] != bridge["bridge_receipt_id"] or fact["source_manifest_id"] != bridge["source_manifest_id"] or fact["point_in_time"] != bridge["point_in_time"]:
            raise ShareCountMaterializerError("snapshot fact is detached from source bridge clocks")
        if fact["fact_entry_sha256s"] != _entry_hashes(row):
            raise ShareCountMaterializerError("snapshot fact hashes do not match canonical fact revision")
        expected = _semantics_from_evidence(row, materialized_at=bridge["point_in_time"]["materialized_at"])
        if any(fact[field] != expected[field] for field in ("state", "reported", "normalized")):
            raise ShareCountMaterializerError("snapshot fact state does not re-derive from direct evidence")
    links = snapshot["fact_links"]
    if len(links) != len(seen_ids) or {link["snapshot_fact_observation_id"] for link in links} != seen_ids or {link["logical_observation_id"] for link in links} != seen_logical:
        raise ShareCountMaterializerError("source snapshot fact links are not exact")
    if snapshot["authority"] != _authority():
        raise ShareCountMaterializerError("source snapshot authority is not all-false")


def validate_ledger_receipt(record: Mapping[str, Any]) -> None:
    _validate_schema(record, "capital_structure_share_count_ledger_receipt_v2.schema.json", "ledger receipt v2")
    if record.get("ledger_receipt_id") != ledger_receipt_id_for(record):
        raise ShareCountMaterializerError("ledger receipt identity digest mismatch")
    appended = record.get("appended") or {}
    source_lengths = {
        len(appended.get(field) or [])
        for field in ("source_snapshot_ids", "bridge_receipt_ids", "source_manifest_ids")
    }
    if len(source_lengths) != 1 or not 1 <= next(iter(source_lengths), 0) <= MAX_SOURCE_BATCH:
        raise ShareCountMaterializerError("ledger receipt source append axes are not one-to-one")
    if len(appended.get("observation_ids") or []) > MAX_LEDGER_OBSERVATIONS:
        raise ShareCountMaterializerError("ledger receipt observation append exceeds model bound")


def validate_share_count_history(observations: Sequence[Mapping[str, Any]]) -> None:
    by_slot: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    ids: set[str] = set()
    for index, row in enumerate(observations):
        observation_id = str(row.get("observation_id") or "")
        if observation_id in ids:
            raise ShareCountMaterializerError(f"duplicate observation ID at history row {index}")
        ids.add(observation_id)
        validate_share_count_observation(row)
        by_slot[str(row["logical_observation_id"])].append(row)
    for logical_id, versions in by_slot.items():
        versions.sort(key=lambda row: int(row["version"]["correction_version"]))
        for expected, row in enumerate(versions, start=1):
            version, relationships = row["version"], row["relationships"]
            if version["correction_version"] != expected:
                raise ShareCountMaterializerError(f"{logical_id} correction versions must be contiguous")
            if expected == 1:
                if version["correction_of"] is not None or relationships["supersedes"]:
                    raise ShareCountMaterializerError("first correction version cannot name a predecessor")
                continue
            previous = versions[expected - 2]
            if version["correction_of"] != previous["observation_id"] or relationships["supersedes"] != [previous["observation_id"]]:
                raise ShareCountMaterializerError("correction chain is not single-predecessor append-only")
            if row["fact_revision_id"] == previous["fact_revision_id"]:
                raise ShareCountMaterializerError("unchanged fact revision cannot create a correction")
            if _timestamp(row["point_in_time"]["materialized_at"]) < _timestamp(previous["point_in_time"]["materialized_at"]):
                raise ShareCountMaterializerError("correction materialization clock cannot move backward")


def validate_share_count_ledger(ledger: Mapping[str, Any], *, expected_ledger_head_receipt_id: str | None = None) -> None:
    if len(_canonical_json(dict(ledger))) + 1 > MAX_LEDGER_BYTES:
        raise ShareCountMaterializerError("share-count v2 ledger exceeds canonical byte bound")
    _validate_schema(ledger, "capital_structure_share_count_ledger_v2.schema.json", "share-count v2 ledger")
    if ledger.get("schema") != LEDGER_SCHEMA or ledger.get("status") != "ok" or ledger.get("authority") != _authority():
        raise ShareCountMaterializerError("share-count v2 ledger top-level state is invalid")
    observations, snapshots, receipts = ledger["observations"], ledger["source_snapshots"], ledger["ledger_receipts"]
    snapshot_fact_views = sum(
        len(snapshot.get("snapshot_fact_observations") or []) for snapshot in snapshots
    )
    if (
        len(observations) > MAX_LEDGER_OBSERVATIONS
        or snapshot_fact_views > MAX_SNAPSHOT_FACT_VIEWS
        or len(snapshots) > MAX_SOURCE_PREFIX
        or len(receipts) > MAX_LEDGER_RECEIPTS
    ):
        raise ShareCountMaterializerError("share-count v2 ledger exceeds model bounds")
    validate_share_count_history(observations)
    canonical_by_id = {str(row.get("observation_id") or ""): row for row in observations}
    manifest_ids: list[str] = []
    bridge_ids: list[str] = []
    snapshot_ids: list[str] = []
    for snapshot in snapshots:
        validate_source_snapshot(snapshot, observations, canonical_by_id=canonical_by_id)
        manifest_ids.append(snapshot["source_manifest_id"]); bridge_ids.append(snapshot["bridge_receipt_id"]); snapshot_ids.append(snapshot["source_snapshot_id"])
    if len(set(manifest_ids)) != len(manifest_ids) or len(set(bridge_ids)) != len(bridge_ids) or len(set(snapshot_ids)) != len(snapshot_ids):
        raise ShareCountMaterializerError("share-count v2 ledger source history has duplicate identities")
    bridge_truth = {
        snapshot["bridge_receipt_id"]: {
            "source_manifest_id": snapshot["source_manifest_id"],
            "issuer_id": snapshot["bridge_receipt"]["issuer"]["issuer_id"],
            "point_in_time": snapshot["bridge_receipt"]["point_in_time"],
        }
        for snapshot in snapshots
    }
    for observation in observations:
        evidence = observation.get("evidence") or {}
        origin = bridge_truth.get(evidence.get("bridge_receipt_id"))
        if (
            origin is None
            or evidence.get("source_manifest_id") != origin["source_manifest_id"]
            or observation.get("issuer_id") != origin["issuer_id"]
            or observation.get("point_in_time") != origin["point_in_time"]
        ):
            raise ShareCountMaterializerError(
                "canonical observation is detached from its originating authenticated bridge",
            )
    originations = {
        (fact["observation_id"], snapshot["bridge_receipt_id"])
        for snapshot in snapshots for fact in snapshot["snapshot_fact_observations"]
    }
    for observation in observations:
        if (observation["observation_id"], observation["evidence"]["bridge_receipt_id"]) not in originations:
            raise ShareCountMaterializerError("canonical observation is detached from its originating source snapshot")
    predecessor: str | None = None
    expected_prefixes = _empty_prefixes()
    consumed_observations = 0
    consumed_snapshots = 0
    for index, receipt in enumerate(receipts, start=1):
        validate_ledger_receipt(receipt)
        if receipt["sequence"] != index or receipt["predecessor_ledger_receipt_id"] != predecessor:
            raise ShareCountMaterializerError("share-count v2 ledger receipt chain is broken")
        appended = receipt["appended"]
        source_count = len(appended["source_snapshot_ids"])
        observation_count = len(appended["observation_ids"])
        if (
            appended["source_snapshot_ids"]
            != snapshot_ids[consumed_snapshots:consumed_snapshots + source_count]
            or appended["bridge_receipt_ids"]
            != bridge_ids[consumed_snapshots:consumed_snapshots + source_count]
            or appended["source_manifest_ids"]
            != manifest_ids[consumed_snapshots:consumed_snapshots + source_count]
            or appended["observation_ids"]
            != [
                row["observation_id"]
                for row in observations[
                    consumed_observations:consumed_observations + observation_count
                ]
            ]
        ):
            raise ShareCountMaterializerError("ledger receipt append is not the next exact history suffix")
        expected_prefixes = {
            label: _advance_prefix(
                expected_prefixes[label], label=label,
                appended_ids=appended[field],
            )
            for label, field in _PREFIX_FIELDS.items()
        }
        if receipt["prefixes"] != expected_prefixes:
            raise ShareCountMaterializerError("ledger receipt rolling prefix commitment is invalid")
        consumed_snapshots += source_count
        consumed_observations += observation_count
        if index > 1 and _timestamp(receipt["materialized_at"]) < _timestamp(receipts[index - 2]["materialized_at"]):
            raise ShareCountMaterializerError("ledger receipt materialization clock cannot move backward")
        predecessor = receipt["ledger_receipt_id"]
    if consumed_snapshots != len(snapshots) or consumed_observations != len(observations):
        raise ShareCountMaterializerError("ledger receipt chain does not consume exact canonical history")
    if ledger["ledger_head_receipt_id"] != predecessor:
        raise ShareCountMaterializerError("ledger head receipt is detached")
    if ledger["materialized_at"] != receipts[-1]["materialized_at"]:
        raise ShareCountMaterializerError("ledger materialized_at is detached from head receipt")
    if receipts[-1]["prefixes"] != expected_prefixes:
        raise ShareCountMaterializerError("ledger head does not bind exact rolling prefixes")
    counts = ledger["counts"]
    tail_facts = snapshots[-1]["snapshot_fact_observations"]
    expected_counts = {"observations_total": len(observations), "source_snapshots_total": len(snapshots), "current_snapshot": {"snapshot_fact_observations": len(tail_facts), **{state: sum(fact["state"]["disposition"] == state for fact in tail_facts) for state in ("observed", "deferred", "ambiguous")}}}
    if counts != expected_counts:
        raise ShareCountMaterializerError("ledger counts are detached")
    if expected_ledger_head_receipt_id is not None and expected_ledger_head_receipt_id != predecessor:
        raise ShareCountMaterializerError("ledger head does not match caller-held witness")


def compile_authenticated_companyfacts_share_count_prefix(
    authenticated_manifests: Sequence[Mapping[str, Any]], source_inputs: Sequence[bytes], coverage_receipt: Mapping[str, Any], *,
    coverage_receipt_bytes: bytes, coverage_receipt_verifier: CoverageReceiptVerifier,
    materialized_at: str, existing_ledger: Mapping[str, Any] | None = None,
    expected_existing_ledger_head_receipt_id: str | None = None,
) -> dict[str, Any]:
    """Compile one authenticated ordered Company Facts prefix into a v2 ledger.

    ``authenticated_manifests`` is the whole selected receipt prefix, while
    ``source_inputs`` holds raw bytes only for the next contiguous unconsumed
    metadata slice (at most ``MAX_SOURCE_BATCH``). This prevents historical
    object reparsing as the prefix grows. The caller supplies exact
    selected-receipt bytes and a pure verifier; storage opening, pointer
    resolution, and key management remain outside this model. An existing
    ledger must be externally head-pinned before extension.
    """
    materialized = _parse_timestamp(materialized_at, "materialized_at")
    manifests, raw_batch, selected_receipt = _validate_authenticated_selection(
        authenticated_manifests, source_inputs, coverage_receipt, coverage_receipt_bytes, coverage_receipt_verifier,
    )
    input_manifest_ids = [item["manifest_id"] for item in manifests]
    if existing_ledger is None:
        if expected_existing_ledger_head_receipt_id is not None:
            raise ShareCountMaterializerError("expected existing ledger head requires existing_ledger")
        observations: list[dict[str, Any]] = []
        snapshots: list[dict[str, Any]] = []
        receipts: list[dict[str, Any]] = []
        existing_prefix = 0
    else:
        if expected_existing_ledger_head_receipt_id is None:
            raise ShareCountMaterializerError("existing ledger extension requires a caller-held head receipt")
        validate_share_count_ledger(existing_ledger, expected_ledger_head_receipt_id=expected_existing_ledger_head_receipt_id)
        observations = [deepcopy(dict(row)) for row in existing_ledger["observations"]]
        snapshots = [deepcopy(dict(row)) for row in existing_ledger["source_snapshots"]]
        receipts = [deepcopy(dict(row)) for row in existing_ledger["ledger_receipts"]]
        existing_manifest_ids = [snapshot["source_manifest_id"] for snapshot in snapshots]
        if input_manifest_ids[:len(existing_manifest_ids)] != existing_manifest_ids:
            raise ShareCountMaterializerError("authenticated source prefix does not extend existing ledger prefix")
        existing_prefix = len(existing_manifest_ids)
        if existing_prefix == len(input_manifest_ids) and not raw_batch:
            return deepcopy(dict(existing_ledger))
    if existing_prefix > len(input_manifest_ids):
        raise ShareCountMaterializerError("existing ledger is longer than supplied authenticated source prefix")
    remaining = len(input_manifest_ids) - existing_prefix
    if not raw_batch and remaining:
        raise ShareCountMaterializerError("unconsumed authenticated source prefix requires a raw-byte batch")
    if len(raw_batch) > remaining:
        raise ShareCountMaterializerError("raw-byte batch exceeds unconsumed authenticated source prefix")
    if len(snapshots) + len(raw_batch) > MAX_SOURCE_PREFIX:
        raise ShareCountMaterializerError("share-count source history exceeds model bound")
    if raw_batch and len(receipts) >= MAX_LEDGER_RECEIPTS:
        raise ShareCountMaterializerError("share-count receipt history requires a checkpoint")

    canonical_by_id = {
        str(row["observation_id"]): row for row in observations
    }
    latest_by_logical: dict[str, Mapping[str, Any]] = {}
    for row in observations:
        latest_by_logical[str(row["logical_observation_id"])] = row
    snapshot_fact_views = sum(
        len(snapshot["snapshot_fact_observations"]) for snapshot in snapshots
    )

    for manifest, raw in zip(manifests[existing_prefix:existing_prefix + len(raw_batch)], raw_batch):
        content = manifest["content"]
        if len(raw) != int(content["byte_length"]) or _sha256(raw) != content["content_sha256"]:
            raise ShareCountMaterializerError("source input raw bytes do not bind next authenticated manifest content")
        retrieved = _parse_timestamp(manifest["retrieval"]["retrieved_at"], "source manifest retrieval")
        if _timestamp(materialized) < _timestamp(retrieved):
            raise ShareCountMaterializerError("materialization cannot precede retained source retrieval")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ShareCountMaterializerError("retained Company Facts bytes must be UTF-8 JSON") from exc
        if not isinstance(payload, Mapping):
            raise ShareCountMaterializerError("retained Company Facts root must be an object")
        if _canonical_cik(payload.get("cik"), field="Company Facts payload cik") != manifest["issuer"]["cik"]:
            raise ShareCountMaterializerError("Company Facts payload CIK does not match authenticated manifest")
        bridge = _bridge_receipt(manifest, selected_receipt, materialized_at=materialized, receipt_bytes=coverage_receipt_bytes)
        groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
        for candidate in _fact_candidates(payload, issuer_id=bridge["issuer"]["issuer_id"], materialized_at=materialized):
            groups[candidate["slot_key"]].append(candidate)
        snapshot_facts: list[dict[str, Any]] = []
        additions: list[dict[str, Any]] = []
        for _slot, group in sorted(groups.items(), key=lambda item: repr(item[0])):
            candidate = _record_from_group(group, bridge=bridge)
            logical_id = str(candidate["logical_observation_id"])
            applied, is_new = _apply_correction(
                candidate, current=latest_by_logical.get(logical_id),
            )
            if is_new:
                additions.append(applied)
                latest_by_logical[logical_id] = applied
            snapshot_facts.append(_snapshot_fact(candidate, applied, bridge))
        if len(observations) + len(additions) > MAX_LEDGER_OBSERVATIONS:
            raise ShareCountMaterializerError(
                "share-count observation history exceeds model bound",
            )
        if snapshot_fact_views + len(snapshot_facts) > MAX_SNAPSHOT_FACT_VIEWS:
            raise ShareCountMaterializerError(
                "share-count snapshot fact history exceeds model bound",
            )
        observations.extend(additions)
        canonical_by_id.update({str(row["observation_id"]): row for row in additions})
        snapshots.append(_source_snapshot(
            bridge, snapshot_facts, observations,
            canonical_by_id=canonical_by_id,
        ))
        snapshot_fact_views += len(snapshot_facts)

    receipts = _append_ledger_receipt(
        receipts, observations, snapshots, materialized_at=materialized,
    )

    result = {
        "schema": LEDGER_SCHEMA, "status": "ok", "compiler_version": COMPILER_VERSION, "materialized_at": receipts[-1]["materialized_at"],
        "observations": observations, "source_snapshots": snapshots, "ledger_receipts": receipts,
        "ledger_head_receipt_id": receipts[-1]["ledger_receipt_id"],
        "counts": {"observations_total": len(observations), "source_snapshots_total": len(snapshots), "current_snapshot": {"snapshot_fact_observations": len(snapshots[-1]["snapshot_fact_observations"]), **{state: sum(fact["state"]["disposition"] == state for fact in snapshots[-1]["snapshot_fact_observations"]) for state in ("observed", "deferred", "ambiguous")}}},
        "authority": _authority(),
    }
    validate_share_count_ledger(result)
    return result


__all__ = [
    "BRIDGE_RECEIPT_SCHEMA", "COMPILER_VERSION", "CoverageReceiptVerifier", "LEDGER_SCHEMA", "LEDGER_RECEIPT_SCHEMA", "MAX_SOURCE_BATCH",
    "OBSERVATION_SCHEMA", "SNAPSHOT_FACT_SCHEMA", "SOURCE_SNAPSHOT_SCHEMA", "ShareCountMaterializerError",
    "bridge_receipt_id_for", "compile_authenticated_companyfacts_share_count_prefix", "fact_revision_id_for",
    "ledger_receipt_id_for", "logical_observation_id_for", "observation_id_for", "snapshot_fact_observation_id_for",
    "source_snapshot_id_for", "validate_bridge_receipt", "validate_ledger_receipt", "validate_share_count_history",
    "validate_share_count_ledger", "validate_share_count_observation", "validate_snapshot_fact_observation", "validate_source_snapshot",
]
