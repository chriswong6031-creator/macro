"""Private BC-C2 point-in-time read adapter owned by Capital Structure.

The caller supplies a canonical SEC issuer id and a timezone-aware system
clock.  This module reuses the owner's telemetry-bound immutable generation and
projection kernel, returns at most one issuer record, and preserves the owner's
explicit unavailable capabilities.  It does not resolve tickers, infer a
BioCatalyst sponsor/asset/trial relationship, calculate cash or dilution, add a
route, persist a read, or write a second filing state.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from engine.capital_structure.projection import (
    AUTHORITY,
    UNAVAILABLE_CAPABILITIES,
    build_projection_bundle,
    validate_projection_bundle,
)
from engine.capital_structure.verified_projection_generation import (
    read_verified_projection_generation,
)
from engine.sector_intelligence.contracts import (
    ContractRegistry,
    canonical_json_sha256,
)

ADAPTER_ID = "biocatalyst_capital_structure_pit_adapter.v1"
READ_CONTRACT_ID = "biocatalyst_capital_structure_pit_read.v1"
SELECTION_SCOPE = "verified_owner_generation_system_time_one_issuer"
HASH_SCOPE = "canonical_payload_excluding_read_id_and_read_payload_sha256"

_ISSUER_ID = re.compile(r"^sec:cik:[0-9]{10}$")
_LIMITATIONS = [
    "caller_supplied_sec_issuer_id_only",
    "event_state_only",
    "explicit_owner_generation_coverage_only",
    "no_cash_burn_runway_or_dilution_calculation",
    "no_identity_resolution",
    "no_model_or_signal_authority",
    "no_negative_issuer_coverage_conclusion",
    "private_in_process_only",
]
_INTEGRITY_SCOPE = {
    "validation": "verified_owner_generation_and_projection_contract",
    "authorized_transport": "private_in_process_only",
    "persistence_authorized": False,
    "owner_truth_plane": "capital_structure",
}


class BioCatalystCapitalStructureAdapterError(ValueError):
    """The owner generation cannot be safely projected."""


def _data_root() -> Path:
    from lib import config

    return config.data_dir() / "capital_structure"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_time(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    try:
        parsed = datetime.fromisoformat(
            raw[:-1] + "+00:00" if raw.endswith("Z") else raw
        )
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _canonical_time(value: object) -> str | None:
    parsed = _parse_time(value)
    if parsed is None:
        return None
    return parsed.isoformat().replace("+00:00", "Z")


def _read_identity(payload: Mapping[str, Any]) -> dict[str, Any]:
    receipt = payload.get("owner_receipt")
    projection = payload.get("owner_projection")
    return {
        "query": payload.get("query"),
        "generated_at": payload.get("generated_at"),
        "available": payload.get("available"),
        "unavailable_reason": payload.get("unavailable_reason"),
        "source_generation_id": (
            (receipt.get("source_receipt") or {}).get("generation_id")
            if isinstance(receipt, Mapping)
            else None
        ),
        "projection_generation_id": (
            receipt.get("projection_generation_id")
            if isinstance(receipt, Mapping)
            else None
        ),
        "event_ids": (
            [item.get("event_id") for item in projection.get("timeline") or []]
            if isinstance(projection, Mapping)
            else []
        ),
    }


def _finish(payload: dict[str, Any]) -> dict[str, Any]:
    payload["read_id"] = (
        "biocatalyst_capital_structure_pit_read_"
        + canonical_json_sha256(_read_identity(payload))[:24]
    )
    payload["read_payload_sha256"] = canonical_json_sha256(
        {
            key: value
            for key, value in payload.items()
            if key not in {"read_id", "read_payload_sha256"}
        }
    )
    validate_capital_structure_pit_read(payload)
    return payload


def _base_payload(
    *, issuer_id: str | None, as_of: str | None, generated_at: str
) -> dict[str, Any]:
    return {
        "contract_id": READ_CONTRACT_ID,
        "schema_version": "1.0.0",
        "adapter_id": ADAPTER_ID,
        "generated_at": generated_at,
        "query": {
            "issuer_id": issuer_id,
            "as_of": as_of,
            "selection_scope": SELECTION_SCOPE,
        },
        "available": False,
        "unavailable_reason": "owner_generation_unavailable",
        "coverage": {
            "state": "unavailable",
            "owner_state": "unavailable",
            "owner_reason": "query_not_evaluated",
            "absence_conclusion": False,
        },
        "owner_receipt": None,
        "owner_projection": None,
        "unavailable_capabilities": list(UNAVAILABLE_CAPABILITIES),
        "limitations": list(_LIMITATIONS),
        "integrity_scope": dict(_INTEGRITY_SCOPE),
        "authority": dict(AUTHORITY),
        "hash_scope": HASH_SCOPE,
    }


def _owner_receipt(bundle: Mapping[str, Any]) -> dict[str, Any]:
    source = bundle.get("source_receipt") or {}
    return {
        "source_receipt": dict(source),
        "projection_generation_id": bundle.get("generation_id"),
        "projection_version": bundle.get("projection_version"),
        "projection_as_of": bundle.get("as_of"),
    }


def read_biocatalyst_capital_structure_pit(
    params: Mapping[str, Any],
    *,
    root: Path | str | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Read one issuer from the owner's verified ledgers at ``params.as_of``.

    Invalid identity/time inputs return a strict unavailable document without
    reading owner storage.  A tampered owner generation raises instead of being
    misreported as an uncovered issuer.
    """

    produced = _canonical_time(generated_at or _now_iso())
    if produced is None:
        raise BioCatalystCapitalStructureAdapterError("invalid_generated_at")
    raw_issuer = params.get("issuer_id")
    issuer_id = (
        raw_issuer.strip()
        if isinstance(raw_issuer, str) and _ISSUER_ID.fullmatch(raw_issuer.strip())
        else None
    )
    as_of = _canonical_time(params.get("as_of"))
    payload = _base_payload(
        issuer_id=issuer_id, as_of=as_of, generated_at=produced
    )
    if issuer_id is None:
        payload["unavailable_reason"] = "invalid_issuer_id"
        payload["coverage"]["owner_reason"] = "invalid_issuer_id"
        return _finish(payload)
    if as_of is None:
        payload["unavailable_reason"] = "invalid_as_of"
        payload["coverage"]["owner_reason"] = "invalid_as_of"
        return _finish(payload)

    try:
        generation = read_verified_projection_generation(root or _data_root())
    except ValueError as exc:
        raise BioCatalystCapitalStructureAdapterError(
            "owner_generation_integrity_failure"
        ) from exc
    source_clock = _parse_time(generation.telemetry.get("as_of"))
    requested_clock = _parse_time(as_of)
    if source_clock is not None and requested_clock > source_clock:
        payload["unavailable_reason"] = "as_of_after_verified_generation"
        payload["coverage"]["owner_reason"] = "as_of_after_verified_generation"
        return _finish(payload)
    try:
        bundle = build_projection_bundle(
            generation.events,
            generation.edges,
            generation.reviews,
            generation.telemetry,
            as_of=as_of,
            generated_at=produced,
        )
        validate_projection_bundle(bundle)
    except ValueError as exc:
        raise BioCatalystCapitalStructureAdapterError(
            "owner_generation_integrity_failure"
        ) from exc

    payload["owner_receipt"] = _owner_receipt(bundle)
    payload["coverage"] = {
        "state": "unavailable",
        "owner_state": bundle["coverage"]["state"],
        "owner_reason": bundle["coverage"]["reason"],
        "absence_conclusion": False,
    }
    if bundle["coverage"]["state"] == "unavailable":
        payload["unavailable_reason"] = "owner_generation_unavailable"
        return _finish(payload)

    record = next(
        (
            item
            for item in bundle["records"]
            if item.get("issuer_id") == issuer_id
        ),
        None,
    )
    if record is None:
        payload["unavailable_reason"] = "issuer_not_covered"
        payload["coverage"]["owner_reason"] = "issuer_not_covered_no_absence_conclusion"
        return _finish(payload)

    payload["available"] = True
    payload["unavailable_reason"] = None
    payload["coverage"]["state"] = "available"
    payload["owner_projection"] = record
    return _finish(payload)


def validate_capital_structure_pit_read(document: Mapping[str, Any]) -> None:
    """Validate the registered contract plus its deterministic receipt hashes."""

    ContractRegistry().validate(READ_CONTRACT_ID, document)
    expected_read_id = (
        "biocatalyst_capital_structure_pit_read_"
        + canonical_json_sha256(_read_identity(document))[:24]
    )
    if document.get("read_id") != expected_read_id:
        raise BioCatalystCapitalStructureAdapterError("read_id_mismatch")
    expected_payload_sha256 = canonical_json_sha256(
        {
            key: value
            for key, value in document.items()
            if key not in {"read_id", "read_payload_sha256"}
        }
    )
    if document.get("read_payload_sha256") != expected_payload_sha256:
        raise BioCatalystCapitalStructureAdapterError(
            "read_payload_sha256_mismatch"
        )


__all__ = [
    "ADAPTER_ID",
    "HASH_SCOPE",
    "READ_CONTRACT_ID",
    "SELECTION_SCOPE",
    "BioCatalystCapitalStructureAdapterError",
    "read_biocatalyst_capital_structure_pit",
    "validate_capital_structure_pit_read",
]
