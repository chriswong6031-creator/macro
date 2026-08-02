"""Closed wire contracts for the Company Theme Exposure sidecar.

This is a membership projection, not a thematic score or a company-relationship
model.  The strict schema is intentional: consumers may pass it to an LLM, so
unknown producer fields are an input-boundary violation.
"""
from __future__ import annotations

from hashlib import sha256
import json
import math
import re
from typing import Any, Mapping

from engine.company_intelligence.contracts import ContractError, iso_timestamp, safe_ticker


EXPOSURE_SCHEMA = "company_theme_exposure.v1"
MANIFEST_SCHEMA = "company_theme_exposure_manifest.v1"
AUTHORITY = "context_only"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GENERATION_RE = re.compile(r"^[0-9a-f]{24,64}$")
_THEME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,95}$")
_BASKET_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,95}$")

_EXPOSURE_KEYS = frozenset({
    "schema", "authority", "generated_at", "generation_id", "status", "company",
    "company_intelligence", "exposures", "theme_state", "warnings",
})
_COMPANY_KEYS = frozenset({"ticker"})
_PIN_KEYS = frozenset({"generation_id", "context_sha256", "latest_event_id", "latest_event_call_date"})
_EXPOSURE_ITEM_KEYS = frozenset({"theme_id", "name_en", "name_zh", "basket_id"})
_THEME_STATE_KEYS = frozenset({"status", "as_of", "sha256"})
_MANIFEST_KEYS = frozenset({
    "schema", "generation_id", "generated_at", "company_count", "exposure_count",
    "source", "files", "status", "warnings",
})
_SOURCE_KEYS = frozenset({"company_intelligence", "membership", "crosswalk", "theme_state", "builder"})
_CI_SOURCE_KEYS = frozenset({"generation_id", "sha256"})
_STATIC_SOURCE_KEYS = frozenset({"sha256"})
_THEME_STATE_SOURCE_KEYS = frozenset({"status", "as_of", "sha256"})
_FILE_KEYS = frozenset({"sha256", "bytes"})
_WARNINGS = frozenset({"theme_state_missing", "theme_state_invalid", "theme_state_stale"})


def canonical_json_bytes(payload: object) -> bytes:
    """Canonical JSON used for every immutable identity and receipt."""
    try:
        return json.dumps(
            payload,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8") + b"\n"
    except (TypeError, ValueError) as exc:
        raise ContractError(f"payload is not canonical JSON: {exc}") from exc


def canonical_json_sha256(payload: object) -> str:
    return sha256(canonical_json_bytes(payload)).hexdigest()


def bytes_sha256(path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65_536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def company_filename(ticker: object) -> str:
    return f"companies/{safe_ticker(ticker)}.json"


def _mapping(value: object, *, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractError(f"{name} must be an object")
    return value


def _keys(value: Mapping[str, Any], expected: frozenset[str], *, name: str) -> None:
    if set(value) != expected:
        missing = sorted(expected - set(value))
        unknown = sorted(set(value) - expected)
        parts = []
        if missing:
            parts.append(f"missing={missing}")
        if unknown:
            parts.append(f"unsupported={unknown}")
        raise ContractError(f"{name} fields mismatch ({', '.join(parts)})")


def _sha(value: object, *, name: str) -> None:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ContractError(f"{name} must be sha256 hex")


def _generation(value: object, *, name: str) -> None:
    if not isinstance(value, str) or not _GENERATION_RE.fullmatch(value):
        raise ContractError(f"{name} invalid")


def _text(value: object, *, name: str, limit: int = 240, nullable: bool = False) -> None:
    if value is None and nullable:
        return
    if not isinstance(value, str) or not value or len(value) > limit or "\x00" in value:
        raise ContractError(f"{name} invalid")


def _theme_state(value: object, *, name: str) -> None:
    item = _mapping(value, name=name)
    _keys(item, _THEME_STATE_KEYS, name=name)
    status = item.get("status")
    if status not in {"fresh", "stale", "missing"}:
        raise ContractError(f"{name}.status invalid")
    as_of = item.get("as_of")
    source_hash = item.get("sha256")
    if status == "missing":
        if as_of is not None or source_hash is not None:
            raise ContractError(f"{name}.missing must not carry a receipt")
        return
    if not isinstance(as_of, str) or iso_timestamp(as_of) is None:
        raise ContractError(f"{name}.as_of invalid")
    _sha(source_hash, name=f"{name}.sha256")


def validate_exposure(payload: object) -> None:
    item = _mapping(payload, name="exposure")
    _keys(item, _EXPOSURE_KEYS, name="exposure")
    if item.get("schema") != EXPOSURE_SCHEMA:
        raise ContractError("exposure schema mismatch")
    if item.get("authority") != AUTHORITY:
        raise ContractError("company theme exposure must remain context_only")
    _generation(item.get("generation_id"), name="exposure.generation_id")
    if iso_timestamp(item.get("generated_at")) is None:
        raise ContractError("exposure.generated_at invalid")
    if item.get("status") not in {"ready", "partial"}:
        raise ContractError("exposure.status invalid")
    company = _mapping(item.get("company"), name="exposure.company")
    _keys(company, _COMPANY_KEYS, name="exposure.company")
    safe_ticker(company.get("ticker"))
    pin = _mapping(item.get("company_intelligence"), name="exposure.company_intelligence")
    _keys(pin, _PIN_KEYS, name="exposure.company_intelligence")
    _generation(pin.get("generation_id"), name="exposure.company_intelligence.generation_id")
    _sha(pin.get("context_sha256"), name="exposure.company_intelligence.context_sha256")
    event_id = pin.get("latest_event_id")
    event_date = pin.get("latest_event_call_date")
    if (event_id is None) != (event_date is None):
        raise ContractError("latest event identity must be jointly null or present")
    if event_id is not None:
        _text(event_id, name="exposure.company_intelligence.latest_event_id", limit=128)
        if not isinstance(event_date, str) or iso_timestamp(event_date) is None:
            raise ContractError("exposure.company_intelligence.latest_event_call_date invalid")
    exposures = item.get("exposures")
    if not isinstance(exposures, list) or len(exposures) > 64:
        raise ContractError("exposure.exposures invalid")
    identities: list[tuple[str, str]] = []
    for index, raw in enumerate(exposures):
        exposure = _mapping(raw, name=f"exposure.exposures[{index}]")
        _keys(exposure, _EXPOSURE_ITEM_KEYS, name=f"exposure.exposures[{index}]")
        theme_id = exposure.get("theme_id")
        basket_id = exposure.get("basket_id")
        if not isinstance(theme_id, str) or not _THEME_RE.fullmatch(theme_id):
            raise ContractError("exposure theme_id invalid")
        if not isinstance(basket_id, str) or not _BASKET_RE.fullmatch(basket_id):
            raise ContractError("exposure basket_id invalid")
        _text(exposure.get("name_en"), name="exposure.name_en")
        _text(exposure.get("name_zh"), name="exposure.name_zh")
        identities.append((theme_id, basket_id))
    if identities != sorted(set(identities)):
        raise ContractError("exposure.exposures must be sorted and unique")
    _theme_state(item.get("theme_state"), name="exposure.theme_state")
    warnings = item.get("warnings")
    if not isinstance(warnings, list) or warnings != sorted(set(warnings)) or any(value not in _WARNINGS for value in warnings):
        raise ContractError("exposure.warnings invalid")
    state = item["theme_state"]["status"]
    expected_sets = {
        "fresh": [[]],
        "stale": [["theme_state_stale"]],
        "missing": [["theme_state_missing"], ["theme_state_invalid"]],
    }
    if warnings not in expected_sets[state] or (item["status"] == "ready") != (not warnings):
        raise ContractError("exposure freshness status/warnings mismatch")


def validate_manifest(payload: object, *, allow_unmaterialized_files: bool = False) -> None:
    item = _mapping(payload, name="manifest")
    _keys(item, _MANIFEST_KEYS, name="manifest")
    if item.get("schema") != MANIFEST_SCHEMA:
        raise ContractError("manifest schema mismatch")
    _generation(item.get("generation_id"), name="manifest.generation_id")
    if iso_timestamp(item.get("generated_at")) is None:
        raise ContractError("manifest.generated_at invalid")
    for field in ("company_count", "exposure_count"):
        value = item.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ContractError(f"manifest.{field} invalid")
    if item.get("status") not in {"ready", "partial", "empty"}:
        raise ContractError("manifest.status invalid")
    if item["status"] == "empty" and (item["company_count"] or item["exposure_count"]):
        raise ContractError("empty manifest must have zero counts")
    if item["status"] != "empty" and item["company_count"] == 0:
        raise ContractError("nonempty manifest must have companies")
    warnings = item.get("warnings")
    if not isinstance(warnings, list) or warnings != sorted(set(warnings)) or any(value not in _WARNINGS for value in warnings):
        raise ContractError("manifest.warnings invalid")
    source = _mapping(item.get("source"), name="manifest.source")
    _keys(source, _SOURCE_KEYS, name="manifest.source")
    ci = _mapping(source.get("company_intelligence"), name="manifest.source.company_intelligence")
    _keys(ci, _CI_SOURCE_KEYS, name="manifest.source.company_intelligence")
    _generation(ci.get("generation_id"), name="manifest source company intelligence generation")
    _sha(ci.get("sha256"), name="manifest source company intelligence sha")
    for name in ("membership", "crosswalk"):
        block = _mapping(source.get(name), name=f"manifest.source.{name}")
        _keys(block, _STATIC_SOURCE_KEYS, name=f"manifest.source.{name}")
        _sha(block.get("sha256"), name=f"manifest source {name} sha")
    _theme_state(source.get("theme_state"), name="manifest.source.theme_state")
    if source.get("builder") != "company_theme_exposure.v1":
        raise ContractError("manifest source builder invalid")
    files = _mapping(item.get("files"), name="manifest.files")
    if len(files) != item["company_count"] and not (allow_unmaterialized_files and not files):
        raise ContractError("manifest company_count must match files")
    for name, raw in files.items():
        if not isinstance(name, str) or not name.startswith("companies/") or not name.endswith(".json"):
            raise ContractError("manifest file path invalid")
        company_filename(name[len("companies/"):-5])
        block = _mapping(raw, name=f"manifest file {name}")
        _keys(block, _FILE_KEYS, name=f"manifest file {name}")
        _sha(block.get("sha256"), name=f"manifest file {name} sha")
        if isinstance(block.get("bytes"), bool) or not isinstance(block.get("bytes"), int) or block["bytes"] <= 0:
            raise ContractError(f"manifest file {name} bytes invalid")
    if item["status"] == "ready" and warnings:
        raise ContractError("ready manifest cannot have warnings")
    if item["status"] == "partial" and not warnings:
        raise ContractError("partial manifest requires warnings")
