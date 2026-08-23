"""Immutable, schema-validated loader for the exact W1-A datapoint catalog."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from jsonschema import Draft202012Validator, FormatChecker
from lib.dataos.registry import load_registry as load_dataos_registry

from .contracts import (
    CONSUMER_USES,
    REGISTRY_SCHEMA,
    REGISTRY_VERSION,
    DatapointContractError,
    canonical_json_sha256,
    deep_freeze,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY_PATH = REPO_ROOT / "config/intelligence_workspace/datapoints.v1.json"
REGISTRY_SCHEMA_PATH = REPO_ROOT / "contracts/intelligence_workspace/datapoint_registry.schema.json"

ADAPTER_OWNER_FIELDS: Mapping[str, frozenset[str]] = MappingProxyType(
    {
        "quote": frozenset({"last"}),
        "technicals": frozenset({"ret_1m", "ret_3m", "ret_12m"}),
        "stage": frozenset({"stage", "weeks_in_stage"}),
        "industry": frozenset({"industry_rank_percentile", "member_rs_percentile"}),
        "earnings_calendar": frozenset({"next_date"}),
        "company_intelligence": frozenset({"eps_growth_pct", "revenue_growth_pct"}),
        "theme": frozenset({"local_memberships"}),
    }
)

TYPE_OPERATORS: Mapping[str, frozenset[str]] = MappingProxyType(
    {
        "number": frozenset({"eq", "ne", "gt", "gte", "lt", "lte", "between"}),
        "integer": frozenset({"eq", "ne", "gt", "gte", "lt", "lte", "between"}),
        "date": frozenset({"eq", "before", "on_or_before", "after", "on_or_after", "between"}),
        "enum": frozenset({"eq", "ne", "in", "not_in"}),
        "entity_ref_set": frozenset({"contains", "not_contains", "is_empty", "is_not_empty"}),
    }
)

FROZEN_FIELD_METADATA: Mapping[str, Mapping[str, Any]] = MappingProxyType(
    {
        "market.price.last": {"value_type": "number", "unit": "currency", "unit_policy": "owner_currency_code", "basis_policy": "owner_native", "entity_types": ("security",), "adapter_id": "quote", "owner_field_key": "last", "point_in_time_policy": "current_only", "rights_policy": "subscriber_allowed"},
        "market.return.1m": {"value_type": "number", "unit": "percent", "unit_policy": "fixed", "basis_policy": "owner_native_price_history", "entity_types": ("security",), "adapter_id": "technicals", "owner_field_key": "ret_1m", "point_in_time_policy": "current_only", "rights_policy": "subscriber_allowed"},
        "market.return.3m": {"value_type": "number", "unit": "percent", "unit_policy": "fixed", "basis_policy": "owner_native_price_history", "entity_types": ("security",), "adapter_id": "technicals", "owner_field_key": "ret_3m", "point_in_time_policy": "current_only", "rights_policy": "subscriber_allowed"},
        "market.return.12m": {"value_type": "number", "unit": "percent", "unit_policy": "fixed", "basis_policy": "owner_native_price_history", "entity_types": ("security",), "adapter_id": "technicals", "owner_field_key": "ret_12m", "point_in_time_policy": "current_only", "rights_policy": "subscriber_allowed"},
        "stage.current": {"value_type": "integer", "unit": "stage_code", "unit_policy": "fixed", "basis_policy": "owner_classification", "entity_types": ("security",), "adapter_id": "stage", "owner_field_key": "stage", "point_in_time_policy": "current_only", "rights_policy": "subscriber_allowed"},
        "stage.weeks_in_stage": {"value_type": "integer", "unit": "weeks", "unit_policy": "fixed", "basis_policy": "owner_classification", "entity_types": ("security",), "adapter_id": "stage", "owner_field_key": "weeks_in_stage", "point_in_time_policy": "current_only", "rights_policy": "subscriber_allowed"},
        "industry.rank.percentile": {"value_type": "number", "unit": "percentile", "unit_policy": "fixed", "basis_policy": "owner_comparison_set", "entity_types": ("industry",), "adapter_id": "industry", "owner_field_key": "industry_rank_percentile", "point_in_time_policy": "current_only", "rights_policy": "subscriber_allowed"},
        "security.industry_member.rs_percentile": {"value_type": "number", "unit": "percentile", "unit_policy": "fixed", "basis_policy": "owner_comparison_set", "entity_types": ("security",), "adapter_id": "industry", "owner_field_key": "member_rs_percentile", "point_in_time_policy": "current_only", "rights_policy": "subscriber_allowed"},
        "earnings.next_date": {"value_type": "date", "unit": "iso_date", "unit_policy": "fixed", "basis_policy": "owner_native", "entity_types": ("security",), "adapter_id": "earnings_calendar", "owner_field_key": "next_date", "point_in_time_policy": "current_only", "rights_policy": "subscriber_allowed"},
        "earnings.latest.eps_growth_pct": {"value_type": "number", "unit": "percent", "unit_policy": "fixed", "basis_policy": "owner_event_metric", "entity_types": ("security",), "adapter_id": "company_intelligence", "owner_field_key": "eps_growth_pct", "point_in_time_policy": "current_only", "rights_policy": "subscriber_allowed"},
        "earnings.latest.revenue_growth_pct": {"value_type": "number", "unit": "percent", "unit_policy": "fixed", "basis_policy": "owner_event_metric", "entity_types": ("security",), "adapter_id": "company_intelligence", "owner_field_key": "revenue_growth_pct", "point_in_time_policy": "current_only", "rights_policy": "subscriber_allowed"},
        "theme.local.memberships": {"value_type": "entity_ref_set", "unit": "entity_refs", "unit_policy": "fixed", "basis_policy": "direct_source_relation", "entity_types": ("security",), "adapter_id": "theme", "owner_field_key": "local_memberships", "point_in_time_policy": "current_only", "rights_policy": "owner_dynamic"},
    }
)
FROZEN_FIELD_IDS = tuple(FROZEN_FIELD_METADATA)
FROZEN_SEMANTIC_DIGESTS: Mapping[str, str] = MappingProxyType(
    {
        "market.price.last": "d6394a2e0e472c742d23d0b7e1f4251dacd923bbb531422697ce61e38492b026",
        "market.return.1m": "e01483a2618bcff3a7bdc346c0f5aec6bf7364fd19015c4ebc0d32beb8a2cb90",
        "market.return.3m": "32ed4dc4142a729d5ed0e15810967ffe3f546cfd733c6c5b45c4866ab773409d",
        "market.return.12m": "1cd28f05822f8fd6ab91535179841428ac72a90c60767c175ced4e7611b2b954",
        "stage.current": "e56bc26346151c42b13a98cace8d41c98de973474ea102e1264baf6c1788dbc3",
        "stage.weeks_in_stage": "6f43be7771a790c54d2d51876d0e432980237c00fc5e301d0eabab9f64b35ea5",
        "industry.rank.percentile": "a8049b2993623ca7a1f66cbc3078918aa6583f9bdfa103002d1958c822a93d8c",
        "security.industry_member.rs_percentile": "e43c33eaa0c57ce4fc25d0a520057ff4597c3303dc5c88c0fc4f1c2b92f111c3",
        "earnings.next_date": "410a222d3a3ca01c6b9d2cd380392f0c8f1e1bd7aef12c73048f4b90e96386d0",
        "earnings.latest.eps_growth_pct": "581bcec8b51e2995b2be7f55c4fe74fc044fb2e7b2225adf78096f2c04288b84",
        "earnings.latest.revenue_growth_pct": "404f66d8842cb8bf8b76a65264b3769921097696bf0db80fcfc92d9de89c456f",
        "theme.local.memberships": "ae7e3da8c3ea83d4acef26930a13fdfdd99b077c0c5b901f6fdffcf081f9a78b",
    }
)


@dataclass(frozen=True, slots=True)
class FieldSpec:
    field_id: str
    label: str
    value_type: str
    unit: str
    unit_policy: str
    basis_policy: str
    entity_types: tuple[str, ...]
    universes: tuple[str, ...]
    owner_ref: Mapping[str, Any]
    adapter_id: str
    owner_field_key: str
    timestamp_policy: str
    freshness_policy: str
    point_in_time_policy: str
    status_policy: str
    operators: tuple[str, ...]
    renderer: str
    rights_policy: str
    consumer_uses: tuple[str, ...]
    constraints: Mapping[str, Any]
    cost_weight: int

    @classmethod
    def from_mapping(cls, row: Mapping[str, Any]) -> "FieldSpec":
        return cls(
            **{
                **dict(row),
                "entity_types": tuple(row["entity_types"]),
                "universes": tuple(row["universes"]),
                "owner_ref": deep_freeze(row["owner_ref"]),
                "operators": tuple(row["operators"]),
                "consumer_uses": tuple(row["consumer_uses"]),
                "constraints": deep_freeze(row["constraints"]),
            }
        )


@dataclass(frozen=True, slots=True)
class DatapointRegistry:
    schema: str
    registry_version: str
    digest: str
    limits: Mapping[str, int]
    fields: tuple[FieldSpec, ...]
    fields_by_id: Mapping[str, FieldSpec]
    raw: Mapping[str, Any]

    def field(self, field_id: str) -> FieldSpec:
        try:
            return self.fields_by_id[field_id]
        except KeyError as exc:
            raise DatapointContractError(f"unknown datapoint field: {field_id!r}") from exc


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise DatapointContractError(f"duplicate JSON key: {key!r}")
        out[key] = value
    return out


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except (OSError, json.JSONDecodeError) as exc:
        raise DatapointContractError(f"cannot load JSON contract {path}: {exc}") from exc


def _schema_validate(document: Mapping[str, Any]) -> None:
    schema = _read_json(REGISTRY_SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(document),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if errors:
        error = errors[0]
        location = ".".join(str(part) for part in error.absolute_path) or "<root>"
        raise DatapointContractError(f"registry schema violation at {location}: {error.message}")


def _validate_field(field: Mapping[str, Any]) -> None:
    adapter_id = str(field["adapter_id"])
    owner_key = str(field["owner_field_key"])
    if adapter_id not in ADAPTER_OWNER_FIELDS:
        raise DatapointContractError(f"unknown adapter: {adapter_id!r}")
    if owner_key not in ADAPTER_OWNER_FIELDS[adapter_id]:
        raise DatapointContractError(f"unknown owner field {owner_key!r} for adapter {adapter_id!r}")
    allowed_operators = TYPE_OPERATORS[field["value_type"]]
    invalid_operators = set(field["operators"]) - allowed_operators
    if invalid_operators:
        raise DatapointContractError(
            f"operators {sorted(invalid_operators)} incompatible with {field['value_type']}"
        )
    if set(field["consumer_uses"]) - CONSUMER_USES:
        raise DatapointContractError("field contains unsupported consumer use")
    dataset_id = field["owner_ref"]["dataset_id"]
    if dataset_id is not None and load_dataos_registry().get(dataset_id) is None:
        raise DatapointContractError(
            f"owner_ref.dataset_id is not registered in Data OS: {dataset_id!r}"
        )

    constraints = field["constraints"]
    allowed_constraint_keys = {
        "number": {"minimum", "maximum"},
        "integer": {"minimum", "maximum"},
        "date": set(),
        "enum": {"enum_values"},
        "entity_ref_set": {"min_items", "max_items", "item_pattern"},
    }[field["value_type"]]
    if set(constraints) - allowed_constraint_keys:
        raise DatapointContractError(f"invalid constraints for {field['value_type']}")
    if "minimum" in constraints and "maximum" in constraints and constraints["minimum"] > constraints["maximum"]:
        raise DatapointContractError("constraint minimum exceeds maximum")
    if "min_items" in constraints and "max_items" in constraints and constraints["min_items"] > constraints["max_items"]:
        raise DatapointContractError("constraint min_items exceeds max_items")


def _validate_frozen_manifest(document: Mapping[str, Any]) -> None:
    fields = document["fields"]
    actual_ids = tuple(field["field_id"] for field in fields)
    if actual_ids != FROZEN_FIELD_IDS:
        raise DatapointContractError(
            f"W1-A manifest must be exact and ordered: expected={FROZEN_FIELD_IDS!r} actual={actual_ids!r}"
        )
    semantic_bindings: set[tuple[Any, ...]] = set()
    for field in fields:
        _validate_field(field)
        semantic_row = {key: value for key, value in field.items() if key != "label"}
        if canonical_json_sha256(semantic_row) != FROZEN_SEMANTIC_DIGESTS[field["field_id"]]:
            raise DatapointContractError(
                f"frozen semantic drift for {field['field_id']}: only label copy is mutable"
            )
        frozen = FROZEN_FIELD_METADATA[field["field_id"]]
        for key, expected in frozen.items():
            actual = tuple(field[key]) if key == "entity_types" else field[key]
            if actual != expected:
                raise DatapointContractError(
                    f"frozen semantic drift for {field['field_id']}.{key}: {actual!r} != {expected!r}"
                )
        binding = (field["adapter_id"], field["owner_field_key"], tuple(field["entity_types"]))
        if binding in semantic_bindings:
            raise DatapointContractError(f"duplicate semantic binding/alias is forbidden: {binding!r}")
        semantic_bindings.add(binding)


@lru_cache(maxsize=8)
def _load_registry_cached(path_text: str) -> DatapointRegistry:
    path = Path(path_text)
    document = _read_json(path)
    if not isinstance(document, Mapping):
        raise DatapointContractError("registry root must be an object")
    _schema_validate(document)
    if document["schema"] != REGISTRY_SCHEMA or document["registry_version"] != REGISTRY_VERSION:
        raise DatapointContractError("unsupported registry schema/version")
    _validate_frozen_manifest(document)
    digest = canonical_json_sha256(document)
    fields = tuple(FieldSpec.from_mapping(row) for row in document["fields"])
    by_id = MappingProxyType({field.field_id: field for field in fields})
    return DatapointRegistry(
        schema=document["schema"],
        registry_version=document["registry_version"],
        digest=digest,
        limits=deep_freeze(document["limits"]),
        fields=fields,
        fields_by_id=by_id,
        raw=deep_freeze(document),
    )


def load_registry(path: str | Path | None = None) -> DatapointRegistry:
    resolved = (Path(path) if path is not None else DEFAULT_REGISTRY_PATH).resolve()
    return _load_registry_cached(str(resolved))


def clear_registry_cache() -> None:
    _load_registry_cached.cache_clear()
