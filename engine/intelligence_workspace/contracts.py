"""Dependency-light Python contracts for the W1-A datapoint read layer."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from hashlib import sha256
import json
import math
import re
from types import MappingProxyType
from typing import Any, Mapping

from lib.dataos.registry import load_registry as load_dataos_registry


REGISTRY_SCHEMA = "datapoint_registry.v1"
REGISTRY_VERSION = "1.0.0"
VALUE_SCHEMA = "datapoint_value.v1"

AUDIENCES = frozenset({"internal", "subscriber"})
CONSUMER_USES = frozenset({"display", "query", "ai_fact", "alert_input", "context"})
STATUSES = frozenset(
    {"available", "unknown", "unavailable", "stale", "not_applicable", "rights_blocked"}
)
REASON_CODES = frozenset(
    {
        "owner_missing",
        "owner_unavailable",
        "owner_degraded",
        "owner_stale",
        "value_missing",
        "history_not_supported",
        "not_applicable",
        "rights_blocked",
        "retired_entity",
        "superseded_entity",
    }
)
ENTITY_TYPES = frozenset({"security", "industry"})
_SECURITY_ID_RE = re.compile(r"^SEC:[A-Z0-9][A-Z0-9:._-]{2,157}$")
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")


class DatapointContractError(ValueError):
    """Raised when catalog, adapter, or envelope bytes violate W1-A law."""


def canonical_json_bytes(payload: object) -> bytes:
    """Canonical UTF-8 JSON, with non-finite floats refused."""
    try:
        return json.dumps(
            payload,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise DatapointContractError(f"payload is not canonical JSON: {exc}") from exc


def canonical_json_sha256(payload: object) -> str:
    return sha256(canonical_json_bytes(payload)).hexdigest()


def iso_utc(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise DatapointContractError("datetime must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def parse_rfc3339(value: object, *, field_name: str) -> datetime:
    """Parse a precise, timezone-bearing RFC3339 knowledge cutoff."""
    text = str(value or "").strip()
    if "T" not in text or not (text.endswith("Z") or re.search(r"[+-]\d\d:\d\d$", text)):
        raise DatapointContractError(f"{field_name} must be a timezone-bearing RFC3339 timestamp")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DatapointContractError(f"{field_name} must be RFC3339: {value!r}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise DatapointContractError(f"{field_name} must include a timezone")
    return parsed.astimezone(timezone.utc)


def validate_clock(value: object, *, field_name: str) -> str | None:
    """Accept exact ISO date or timezone-bearing timestamp without widening precision."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return iso_utc(value)
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    if not text:
        raise DatapointContractError(f"{field_name} may not be blank")
    if "T" not in text:
        try:
            return date.fromisoformat(text).isoformat()
        except ValueError as exc:
            raise DatapointContractError(f"{field_name} must be ISO date or RFC3339") from exc
    parse_rfc3339(text, field_name=field_name)
    return text


def deep_freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): deep_freeze(item) for key, item in value.items()})
    if isinstance(value, list | tuple):
        return tuple(deep_freeze(item) for item in value)
    return value


def thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [thaw(item) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class EntityRequest:
    type: str
    id: str | None = None
    symbol: str | None = None
    universe: str | None = None


@dataclass(frozen=True, slots=True)
class CanonicalEntity:
    type: str
    id: str
    universe: str
    state: str = "active"
    alias_interpretation: str | None = None

    def __post_init__(self) -> None:
        if self.type not in ENTITY_TYPES:
            raise DatapointContractError(f"unsupported canonical entity type: {self.type!r}")
        if not self.id:
            raise DatapointContractError("canonical entity id is required")
        if self.type == "security" and not _SECURITY_ID_RE.fullmatch(self.id):
            raise DatapointContractError(f"security identity is not canonical SEC:*: {self.id!r}")
        if not self.universe:
            raise DatapointContractError("canonical entity universe is required")
        if self.state not in {"active", "retired", "superseded"}:
            raise DatapointContractError(f"unsupported canonical entity state: {self.state!r}")


@dataclass(frozen=True, slots=True)
class ResolutionRequest:
    entities: tuple[EntityRequest, ...]
    field_ids: tuple[str, ...]
    audience: str
    consumer_use: str
    requested_as_of: str | None = None


@dataclass(frozen=True, slots=True)
class OwnerResolutionRequest:
    """Audience-blind owner request passed across the adapter boundary."""

    requested_as_of: str | None = None


@dataclass(frozen=True, slots=True)
class AdapterResult:
    """Owner-returned fact.  The central resolver alone creates final envelopes."""

    value: Any
    status: str
    reason_code: str | None
    unit: str | None
    observed_at: str | date | datetime | None
    effective_at: str | date | datetime | None
    as_of: str | date | datetime | None
    freshness: Mapping[str, Any]
    quality: Mapping[str, Any]
    source: Mapping[str, Any]
    provenance: Mapping[str, Any]
    rights_context: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("freshness", "quality", "source", "provenance", "rights_context"):
            value = getattr(self, name)
            if not isinstance(value, Mapping):
                raise DatapointContractError(f"AdapterResult.{name} must be a mapping")
            object.__setattr__(self, name, deep_freeze(value))

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "AdapterResult":
        allowed = {
            "value", "status", "reason_code", "unit", "observed_at", "effective_at",
            "as_of", "freshness", "quality", "source", "provenance", "rights_context",
        }
        unknown = set(payload) - allowed
        missing = allowed - {"rights_context"} - set(payload)
        if unknown or missing:
            raise DatapointContractError(
                f"AdapterResult keys invalid; missing={sorted(missing)} unknown={sorted(unknown)}"
            )
        return cls(**{key: payload[key] for key in allowed if key in payload})


@dataclass(frozen=True, slots=True)
class RightsDecision:
    allowed: bool
    consumer_uses: tuple[str, ...] | None = None


def semantic_fingerprint(envelope: Mapping[str, Any]) -> str:
    """Bind the fact, not transport time or private/hidden provenance."""
    payload = {
        "registry_digest": envelope["registry_digest"],
        "field_id": envelope["field_id"],
        "entity": envelope["entity"],
        "value": envelope["value"],
        "status": envelope["status"],
        "reason_code": envelope["reason_code"],
        "unit": envelope["unit"],
        "observed_at": envelope["observed_at"],
        "effective_at": envelope["effective_at"],
        "as_of": envelope["as_of"],
        "source_id": envelope["source"]["source_id"],
        "quality_state": envelope["quality"]["state"],
    }
    return canonical_json_sha256(payload)


def finite_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def concrete_unit(field_spec: Any, result: AdapterResult) -> str:
    if field_spec.unit_policy == "owner_currency_code":
        if result.status == "available":
            unit = str(result.unit or "")
            if not _CURRENCY_RE.fullmatch(unit):
                raise DatapointContractError(
                    f"{field_spec.field_id} available value requires owner ISO currency unit"
                )
            return unit
        return str(result.unit or field_spec.unit)
    if result.unit is not None and result.unit != field_spec.unit:
        raise DatapointContractError(
            f"{field_spec.field_id} owner unit {result.unit!r} != frozen {field_spec.unit!r}"
        )
    return field_spec.unit


def normalize_available_value(field_spec: Any, value: Any) -> Any:
    value_type = field_spec.value_type
    if value_type == "number":
        if not finite_number(value):
            raise DatapointContractError(f"{field_spec.field_id} requires a finite number")
        normalized: Any = float(value)
    elif value_type == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            raise DatapointContractError(f"{field_spec.field_id} requires an integer")
        normalized = value
    elif value_type == "date":
        if isinstance(value, datetime):
            raise DatapointContractError(f"{field_spec.field_id} requires a date, not a timestamp")
        try:
            normalized = value.isoformat() if isinstance(value, date) else date.fromisoformat(str(value)).isoformat()
        except ValueError as exc:
            raise DatapointContractError(f"{field_spec.field_id} requires an ISO date") from exc
    elif value_type == "entity_ref_set":
        if not isinstance(value, (list, tuple)) or isinstance(value, (str, bytes)):
            raise DatapointContractError(f"{field_spec.field_id} requires an entity-ref list")
        if any(not isinstance(item, str) for item in value):
            raise DatapointContractError(f"{field_spec.field_id} entity refs must be strings")
        if len(set(value)) != len(value):
            raise DatapointContractError(f"{field_spec.field_id} entity refs must be unique")
        normalized = sorted(value)
    elif value_type == "enum":
        normalized = value
    else:  # registry validation should make this unreachable
        raise DatapointContractError(f"unsupported value type: {value_type!r}")

    constraints = field_spec.constraints
    if value_type in {"number", "integer"}:
        if "minimum" in constraints and normalized < constraints["minimum"]:
            raise DatapointContractError(f"{field_spec.field_id} value is below minimum")
        if "maximum" in constraints and normalized > constraints["maximum"]:
            raise DatapointContractError(f"{field_spec.field_id} value is above maximum")
    if value_type == "entity_ref_set":
        if len(normalized) < int(constraints.get("min_items", 0)):
            raise DatapointContractError(f"{field_spec.field_id} relation set is too small")
        if len(normalized) > int(constraints.get("max_items", len(normalized))):
            raise DatapointContractError(f"{field_spec.field_id} relation set is too large")
        pattern = constraints.get("item_pattern")
        if pattern and any(re.fullmatch(pattern, item) is None for item in normalized):
            raise DatapointContractError(f"{field_spec.field_id} contains non-local-theme ref")
    if value_type == "enum" and normalized not in constraints.get("enum_values", ()):
        raise DatapointContractError(f"{field_spec.field_id} value is outside its enum")
    canonical_json_bytes(normalized)
    return normalized


def validate_adapter_result(field_spec: Any, result: AdapterResult) -> Any:
    if result.status not in STATUSES:
        raise DatapointContractError(f"unknown adapter status: {result.status!r}")
    if result.status == "rights_blocked":
        raise DatapointContractError("rights_blocked is created by projection, not an owner adapter")
    if result.status == "available":
        if result.reason_code is not None:
            raise DatapointContractError("available adapter result may not carry reason_code")
        normalized = normalize_available_value(field_spec, result.value)
    else:
        if result.value is not None:
            raise DatapointContractError("non-available adapter result must carry value=null")
        if result.reason_code not in REASON_CODES:
            raise DatapointContractError("non-available adapter result requires closed reason_code")
        if result.status == "not_applicable" and result.reason_code != "not_applicable":
            raise DatapointContractError("not_applicable status requires not_applicable reason")
        if result.status == "stale" and result.reason_code != "owner_stale":
            raise DatapointContractError("stale status requires owner_stale reason")
        if result.reason_code == "rights_blocked":
            raise DatapointContractError("rights_blocked reason is reserved for projection")
        normalized = None

    freshness = thaw(result.freshness)
    quality = thaw(result.quality)
    if set(freshness) != {"state", "policy"}:
        raise DatapointContractError("freshness must contain exactly state and policy")
    if freshness["state"] not in {"fresh", "stale", "unknown", "not_applicable"}:
        raise DatapointContractError("freshness state is outside closed vocabulary")
    if freshness["policy"] != "owner_native":
        raise DatapointContractError("freshness must remain owner_native")
    if result.status == "stale" and freshness["state"] != "stale":
        raise DatapointContractError("stale status must preserve stale owner freshness")
    if set(quality) != {"state", "issues"}:
        raise DatapointContractError("quality must contain exactly state and issues")
    if quality["state"] not in {"ok", "degraded", "unknown"}:
        raise DatapointContractError("quality state is outside closed vocabulary")
    if not isinstance(quality["issues"], list) or len(set(quality["issues"])) != len(quality["issues"]):
        raise DatapointContractError("quality issues must be a unique list")
    if not result.source.get("source_id") or not result.source.get("owner") or not result.source.get("license_class"):
        raise DatapointContractError("adapter source requires source_id, owner, and license_class")
    source_owner = str(result.source["owner"])
    provenance_kind = result.provenance.get("kind")
    if provenance_kind == "resolver_disposition":
        if source_owner != "intelligence_workspace":
            raise DatapointContractError(
                "resolver disposition must retain the intelligence_workspace owner"
            )
    elif source_owner != field_spec.owner_ref["owner"]:
        raise DatapointContractError(
            "adapter source owner is incompatible with the frozen owner lineage"
        )
    source_dataset_id = result.source.get("dataset_id")
    if source_dataset_id is not None and load_dataos_registry().get(source_dataset_id) is None:
        raise DatapointContractError(
            f"adapter source dataset_id is not registered in Data OS: {source_dataset_id!r}"
        )
    if source_dataset_id != field_spec.owner_ref["dataset_id"]:
        raise DatapointContractError(
            "adapter source dataset_id is incompatible with the frozen owner lineage"
        )
    if not result.provenance.get("kind") or not result.provenance.get("owner_field_key"):
        raise DatapointContractError("adapter provenance requires kind and owner_field_key")
    if result.provenance.get("owner_field_key") != field_spec.owner_field_key:
        raise DatapointContractError("adapter provenance owner_field_key violates registry binding")
    return normalized
