"""Deterministic W1-A request planner, owner dispatcher, and rights projection."""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
import json
from pathlib import Path
import re
from typing import Any, Protocol

from jsonschema import Draft202012Validator, FormatChecker

from .contracts import (
    AUDIENCES,
    CONSUMER_USES,
    AdapterResult,
    CanonicalEntity,
    DatapointContractError,
    EntityRequest,
    OwnerResolutionRequest,
    ResolutionRequest,
    RightsDecision,
    VALUE_SCHEMA,
    canonical_json_bytes,
    canonical_json_sha256,
    concrete_unit,
    iso_utc,
    parse_rfc3339,
    semantic_fingerprint,
    thaw,
    validate_adapter_result,
    validate_clock,
)
from .registry import ADAPTER_OWNER_FIELDS, DatapointRegistry, FieldSpec, load_registry


VALUE_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "contracts/intelligence_workspace/datapoint_value.schema.json"


@lru_cache(maxsize=1)
def _value_validator() -> Draft202012Validator:
    """Cache immutable contract metadata, never resolved datapoint values."""
    schema = json.loads(VALUE_SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


class RequestValidationError(ValueError):
    """The full request is invalid; adapters have not been called."""


class AdapterContractError(RuntimeError):
    """An adapter violated its programmer contract; resolution fails closed."""


class IdentityNormalizer(Protocol):
    def normalize_many(self, entities: Sequence[EntityRequest]) -> Sequence[CanonicalEntity]: ...


class DatapointAdapter(Protocol):
    def resolve_many(
        self,
        canonical_entities: Sequence[CanonicalEntity],
        field_specs: Sequence[FieldSpec],
        request: OwnerResolutionRequest,
        context: "RequestContext",
    ) -> Mapping[Any, AdapterResult | Mapping[str, Any]]: ...


RightsProjector = Callable[
    [FieldSpec, AdapterResult, CanonicalEntity, "RequestContext"],
    RightsDecision | bool,
]


@dataclass(slots=True)
class RequestContext:
    generated_at: datetime
    requested_as_of: datetime | None
    memo: dict[str, Any] = field(default_factory=dict)
    source_loads: dict[str, int] = field(default_factory=dict)

    def memoize(self, key: str, loader: Callable[[], Any]) -> Any:
        """One request only; nothing here survives a resolver call."""
        if key not in self.memo:
            self.memo[key] = loader()
            self.source_loads[key] = self.source_loads.get(key, 0) + 1
        return self.memo[key]


def _coerce_entity(payload: EntityRequest | Mapping[str, Any]) -> EntityRequest:
    if isinstance(payload, EntityRequest):
        return payload
    if not isinstance(payload, Mapping):
        raise RequestValidationError("each entity must be an EntityRequest or object")
    allowed = {"type", "id", "symbol", "universe"}
    unknown = set(payload) - allowed
    if unknown:
        raise RequestValidationError(f"unknown entity request keys: {sorted(unknown)}")
    return EntityRequest(
        type=str(payload.get("type") or "").strip(),
        id=str(payload["id"]).strip() if payload.get("id") is not None else None,
        symbol=str(payload["symbol"]).strip().upper() if payload.get("symbol") is not None else None,
        universe=str(payload["universe"]).strip() if payload.get("universe") is not None else None,
    )


def _coerce_request(payload: ResolutionRequest | Mapping[str, Any]) -> ResolutionRequest:
    if isinstance(payload, ResolutionRequest):
        return payload
    if not isinstance(payload, Mapping):
        raise RequestValidationError("request must be a ResolutionRequest or object")
    allowed = {"entities", "field_ids", "audience", "consumer_use", "requested_as_of"}
    unknown = set(payload) - allowed
    missing = {"entities", "field_ids", "audience", "consumer_use"} - set(payload)
    if unknown or missing:
        raise RequestValidationError(
            f"request keys invalid; missing={sorted(missing)} unknown={sorted(unknown)}"
        )
    if not isinstance(payload["entities"], Sequence) or isinstance(payload["entities"], (str, bytes)):
        raise RequestValidationError("entities must be a sequence")
    if not isinstance(payload["field_ids"], Sequence) or isinstance(payload["field_ids"], (str, bytes)):
        raise RequestValidationError("field_ids must be a sequence")
    return ResolutionRequest(
        entities=tuple(_coerce_entity(entity) for entity in payload["entities"]),
        field_ids=tuple(str(field_id).strip() for field_id in payload["field_ids"]),
        audience=str(payload["audience"]).strip(),
        consumer_use=str(payload["consumer_use"]).strip(),
        requested_as_of=(
            str(payload["requested_as_of"]).strip()
            if payload.get("requested_as_of") is not None
            else None
        ),
    )


def _structural_validate(
    request: ResolutionRequest,
    registry: DatapointRegistry,
    now: datetime,
) -> tuple[tuple[FieldSpec, ...], datetime | None]:
    limits = registry.limits
    if not request.entities:
        raise RequestValidationError("at least one entity is required")
    if not request.field_ids:
        raise RequestValidationError("at least one field is required")
    if len(request.entities) > limits["max_entities"]:
        raise RequestValidationError("max_entities exceeded")
    if len(request.field_ids) > limits["max_fields"]:
        raise RequestValidationError("max_fields exceeded")
    if len(set(request.field_ids)) != len(request.field_ids):
        raise RequestValidationError("duplicate requested field")
    if request.audience not in AUDIENCES:
        raise RequestValidationError(f"unsupported audience: {request.audience!r}")
    if request.consumer_use not in CONSUMER_USES:
        raise RequestValidationError(f"unsupported consumer use: {request.consumer_use!r}")

    edge_keys: list[tuple[str, str, str | None]] = []
    for entity in request.entities:
        identity = entity.id if entity.id is not None else f"symbol:{entity.symbol}"
        edge_keys.append((entity.type, identity, entity.universe))
    if len(set(edge_keys)) != len(edge_keys):
        raise RequestValidationError("duplicate requested entity")

    try:
        fields = tuple(registry.field(field_id) for field_id in request.field_ids)
    except DatapointContractError as exc:
        raise RequestValidationError(str(exc)) from exc
    for entity in request.entities:
        if entity.type not in {"security", "industry"}:
            raise RequestValidationError(f"unsupported entity type: {entity.type!r}")
        if entity.type == "security":
            if bool(entity.id) == bool(entity.symbol):
                raise RequestValidationError("security entity requires exactly one of id or symbol")
        elif not entity.id or entity.symbol:
            raise RequestValidationError("industry entity requires id and does not accept symbol")
        for spec in fields:
            if entity.type not in spec.entity_types:
                raise RequestValidationError(
                    f"field {spec.field_id!r} is incompatible with entity type {entity.type!r}"
                )
            if entity.universe is not None and entity.universe not in spec.universes:
                raise RequestValidationError(
                    f"field {spec.field_id!r} is incompatible with universe {entity.universe!r}"
                )
            if request.consumer_use not in spec.consumer_uses:
                raise RequestValidationError(
                    f"field {spec.field_id!r} does not allow consumer use {request.consumer_use!r}"
                )

    cells = len(request.entities) * len(fields)
    if cells > limits["max_cells"]:
        raise RequestValidationError("max_cells exceeded")
    request_cost = len(request.entities) * sum(spec.cost_weight for spec in fields)
    if request_cost > limits["max_request_cost"]:
        raise RequestValidationError("max_request_cost exceeded")

    requested_as_of = None
    if request.requested_as_of is not None:
        try:
            requested_as_of = parse_rfc3339(request.requested_as_of, field_name="requested_as_of")
        except DatapointContractError as exc:
            raise RequestValidationError(str(exc)) from exc
        if requested_as_of > now:
            raise RequestValidationError("requested_as_of may not be in the future")
    return fields, requested_as_of


def _validate_canonical_entities(
    edge_entities: Sequence[EntityRequest],
    canonical_entities: Sequence[CanonicalEntity],
    fields: Sequence[FieldSpec],
) -> tuple[CanonicalEntity, ...]:
    if len(canonical_entities) != len(edge_entities):
        raise RequestValidationError("identity normalizer changed entity cardinality")
    seen: set[tuple[str, str]] = set()
    normalized: list[CanonicalEntity] = []
    for edge, canonical in zip(edge_entities, canonical_entities, strict=True):
        if not isinstance(canonical, CanonicalEntity):
            raise RequestValidationError("identity normalizer returned a non-canonical entity")
        if canonical.type != edge.type:
            raise RequestValidationError("identity normalizer changed entity type")
        if edge.id and canonical.id != edge.id:
            raise RequestValidationError("explicit canonical entity may not be silently redirected")
        if edge.symbol and canonical.alias_interpretation != "current_alias_only":
            raise RequestValidationError(
                "symbol normalization must mark current_alias_only and cannot claim historical naming"
            )
        key = (canonical.type, canonical.id)
        if key in seen:
            raise RequestValidationError("duplicate canonical entity request")
        seen.add(key)
        for spec in fields:
            if canonical.type not in spec.entity_types or canonical.universe not in spec.universes:
                raise RequestValidationError(
                    f"canonical entity {canonical.id!r} is incompatible with {spec.field_id!r}"
                )
        normalized.append(canonical)
    return tuple(normalized)


def _coerce_adapter_result(value: AdapterResult | Mapping[str, Any]) -> AdapterResult:
    if isinstance(value, AdapterResult):
        return value
    if isinstance(value, Mapping):
        try:
            return AdapterResult.from_mapping(value)
        except DatapointContractError as exc:
            raise AdapterContractError(str(exc)) from exc
    raise AdapterContractError("adapter result must be AdapterResult or mapping")


def _lookup_adapter_result(
    returned: Mapping[Any, AdapterResult | Mapping[str, Any]],
    entity: CanonicalEntity,
    field_id: str,
) -> AdapterResult | None:
    candidates = (
        (entity.type, entity.id, field_id),
        (entity.id, field_id),
        entity.id,
    )
    present = [key for key in candidates if key in returned]
    if len(present) > 1:
        raise AdapterContractError(f"adapter returned ambiguous keys for {entity.id}/{field_id}")
    return _coerce_adapter_result(returned[present[0]]) if present else None


def _disposition(spec: FieldSpec, reason: str) -> AdapterResult:
    status = "not_applicable" if reason == "not_applicable" else "unavailable"
    return AdapterResult(
        value=None,
        status=status,
        reason_code=reason,
        unit=None,
        observed_at=None,
        effective_at=None,
        as_of=None,
        freshness={"state": "not_applicable", "policy": "owner_native"},
        quality={"state": "unknown", "issues": []},
        source={
            "source_id": "intelligence_workspace.resolver",
            "owner": "intelligence_workspace",
            "license_class": "internal_derived",
            "dataset_id": None,
        },
        provenance={
            "kind": "resolver_disposition",
            "owner_field_key": spec.owner_field_key,
            "basis": spec.basis_policy,
        },
    )


def _source_payload(source: Mapping[str, Any], *, subscriber: bool) -> dict[str, Any]:
    allowed = {"source_id", "owner", "license_class", "dataset_id", "source_family", "delay"}
    if not subscriber:
        allowed.add("artifact_id")
    return {key: thaw(value) for key, value in source.items() if key in allowed}


def _provenance_payload(provenance: Mapping[str, Any], *, subscriber: bool) -> dict[str, Any]:
    allowed = {
        "kind", "owner_field_key", "formula_version", "field_lineage", "basis",
        "relationship", "alias_interpretation",
    }
    if not subscriber:
        allowed.add("owner_artifact")
    return {key: thaw(value) for key, value in provenance.items() if key in allowed}


_PRIVATE_SUBSCRIBER_TEXT = re.compile(
    r"(?:^/|file://|(?:^|[\\/])(?:Users|agentos|code|collectors|config|contracts|data|docs|engine|lib|research|scripts|site|templates|tests|tools|\.github|\.claude|\.codex)[\\/]"
    r"|\b(?:credentials?|api[_-]?key|access[_-]?token|provider[_-]?metadata)\b)",
    re.IGNORECASE,
)


def _validate_subscriber_metadata(value: Any, *, location: str) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            _validate_subscriber_metadata(item, location=f"{location}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _validate_subscriber_metadata(item, location=f"{location}[{index}]")
    elif isinstance(value, str) and _PRIVATE_SUBSCRIBER_TEXT.search(value):
        raise AdapterContractError(
            f"subscriber metadata contains private/path-like text at {location}"
        )


@dataclass(slots=True)
class DatapointResolver:
    registry: DatapointRegistry
    identity_normalizer: IdentityNormalizer
    adapters: Mapping[str, DatapointAdapter]
    rights_projector: RightsProjector | None = None
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)

    def __init__(
        self,
        *,
        identity_normalizer: IdentityNormalizer,
        adapters: Mapping[str, DatapointAdapter],
        registry: DatapointRegistry | None = None,
        rights_projector: RightsProjector | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.registry = registry or load_registry()
        self.identity_normalizer = identity_normalizer
        unknown_adapters = set(adapters) - set(ADAPTER_OWNER_FIELDS)
        if unknown_adapters:
            raise DatapointContractError(
                f"runtime adapters are outside the static allowlist: {sorted(unknown_adapters)}"
            )
        self.adapters = dict(adapters)
        self.rights_projector = rights_projector
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def resolve_current_industry_relationship(
        self,
        entity: CanonicalEntity,
    ) -> dict[str, Any]:
        """Project the one bounded related-entity edge needed by W1-B.

        This does not add a datapoint, formula, registry entry, identity system,
        or general relationship query language. The existing Stage owner resolves
        its current security->industry edge; this resolver applies the same
        subscriber metadata projection used by registered datapoint envelopes.
        """
        if (
            not isinstance(entity, CanonicalEntity)
            or entity.type != "security"
            or entity.universe != "us_equity"
            or entity.state != "active"
        ):
            raise RequestValidationError(
                "current-industry relationship requires one active canonical US security"
            )
        adapter = self.adapters.get("stage")
        owner_resolver = getattr(adapter, "resolve_current_industry_relationship", None)
        if not callable(owner_resolver):
            raise RequestValidationError("runtime Stage owner lacks current-industry relationship")
        now = self.clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise DatapointContractError("resolver clock must be timezone-aware")
        now = now.astimezone(timezone.utc)
        context = RequestContext(generated_at=now, requested_as_of=None)
        try:
            result = owner_resolver(entity, context)
        except Exception as exc:
            raise AdapterContractError("Stage current-industry relationship failed") from exc
        if not isinstance(result, AdapterResult):
            raise AdapterContractError("Stage current-industry relationship returned invalid result")
        if result.status not in {"available", "unknown", "unavailable", "stale", "not_applicable"}:
            raise AdapterContractError("Stage current-industry relationship returned invalid status")
        if result.unit != "industry_id":
            raise AdapterContractError("Stage current-industry relationship returned invalid unit")
        if result.status == "available":
            industry_id = str(result.value or "").strip()
            if not industry_id or result.reason_code is not None:
                raise AdapterContractError("available current-industry relationship lacks target")
        else:
            if result.value is not None or not result.reason_code:
                raise AdapterContractError("non-available current-industry relationship carries target")
            industry_id = ""
        observed_at = validate_clock(result.observed_at, field_name="observed_at")
        effective_at = validate_clock(result.effective_at, field_name="effective_at")
        as_of = validate_clock(result.as_of, field_name="as_of")
        source = _source_payload(result.source, subscriber=True)
        provenance = _provenance_payload(result.provenance, subscriber=True)
        if (
            source.get("source_id") != "stage_analysis.screener"
            or provenance.get("kind") != "owner_relationship"
            or provenance.get("relationship") != "security.current_industry"
        ):
            raise AdapterContractError("Stage current-industry relationship authority drift")
        _validate_subscriber_metadata(source, location="source")
        _validate_subscriber_metadata(provenance, location="provenance")
        payload: dict[str, Any] = {
            "schema": "intelligence_workspace.current_industry_relationship.v1",
            "registry_digest": self.registry.digest,
            "relationship": "security.current_industry",
            "from": {"type": "security", "id": entity.id},
            "to": (
                {"type": "industry", "id": industry_id, "universe": "us_industry"}
                if industry_id else None
            ),
            "status": result.status,
            "reason_code": result.reason_code,
            "observed_at": observed_at,
            "effective_at": effective_at,
            "as_of": as_of,
            "generated_at": iso_utc(now),
            "freshness": thaw(result.freshness),
            "quality": thaw(result.quality),
            "source": source,
            "provenance": provenance,
            "audience": "subscriber",
            "consumer_use": "ai_fact",
            "relationship_fingerprint": "",
        }
        fingerprint_basis = {
            key: value for key, value in payload.items()
            if key not in {"generated_at", "relationship_fingerprint"}
        }
        payload["relationship_fingerprint"] = canonical_json_sha256(fingerprint_basis)
        canonical_json_bytes(payload)
        return payload

    def resolve(self, payload: ResolutionRequest | Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
        request = _coerce_request(payload)
        now = self.clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise DatapointContractError("resolver clock must be timezone-aware")
        now = now.astimezone(timezone.utc)
        fields, requested_as_of = _structural_validate(request, self.registry, now)

        # Identity is normalized only after the complete structural/cost check,
        # and before any owner adapter I/O.  Current aliases are an edge
        # convenience, never historical naming evidence.
        try:
            normalized = self.identity_normalizer.normalize_many(request.entities)
        except Exception as exc:
            raise RequestValidationError(f"identity normalization failed closed: {exc}") from exc
        entities = _validate_canonical_entities(request.entities, normalized, fields)

        historical_current_only = requested_as_of is not None and requested_as_of < now
        planned_fields = tuple(
            spec
            for spec in fields
            if not (historical_current_only and spec.point_in_time_policy == "current_only")
        )
        required_adapters = {spec.adapter_id for spec in planned_fields}
        missing_adapters = required_adapters - set(self.adapters)
        if missing_adapters:
            raise RequestValidationError(f"runtime adapter allowlist is incomplete: {sorted(missing_adapters)}")

        context = RequestContext(
            generated_at=now,
            requested_as_of=requested_as_of,
        )
        owner_request = OwnerResolutionRequest(requested_as_of=request.requested_as_of)
        owner_results: dict[tuple[str, str], AdapterResult] = {}
        grouped_specs: dict[str, list[FieldSpec]] = {}
        for spec in planned_fields:
            grouped_specs.setdefault(spec.adapter_id, []).append(spec)
        for adapter_id, adapter_fields in grouped_specs.items():
            eligible = [entity for entity in entities if entity.state == "active"]
            if not eligible:
                continue
            try:
                returned = self.adapters[adapter_id].resolve_many(
                    tuple(eligible), tuple(adapter_fields), owner_request, context
                )
            except Exception as exc:
                raise AdapterContractError(
                    f"adapter {adapter_id!r} failed for "
                    f"{[spec.field_id for spec in adapter_fields]!r}: {exc}"
                ) from exc
            if not isinstance(returned, Mapping):
                raise AdapterContractError(f"adapter {adapter_id!r} did not return a mapping")
            expected_ids = {entity.id for entity in eligible}
            expected_types = {entity.id: entity.type for entity in eligible}
            expected_fields = {spec.field_id for spec in adapter_fields}
            for key in returned:
                if isinstance(key, tuple):
                    if len(key) == 3:
                        key_type, key_id, key_field = key
                        if key_id not in expected_types or key_type != expected_types[key_id]:
                            raise AdapterContractError(
                                "adapter returned a mismatched entity type component"
                            )
                    elif len(key) == 2:
                        key_id, key_field = key
                    else:
                        raise AdapterContractError("adapter returned malformed composite key")
                    if key_id not in expected_ids or key_field not in expected_fields:
                        raise AdapterContractError("adapter returned an unrequested cell")
                else:
                    if len(adapter_fields) != 1:
                        raise AdapterContractError(
                            "entity-only adapter keys are ambiguous for a multi-field batch"
                        )
                    if key not in expected_ids:
                        raise AdapterContractError("adapter returned an unrequested entity")
            for spec in adapter_fields:
                for entity in eligible:
                    result = _lookup_adapter_result(returned, entity, spec.field_id)
                    if (
                        result is not None
                        and result.provenance.get("kind") == "resolver_disposition"
                    ):
                        raise AdapterContractError(
                            "adapter may not forge a resolver_disposition provenance kind"
                        )
                    owner_results[(entity.id, spec.field_id)] = result or _disposition(
                        spec, "owner_missing"
                    )

        envelopes: list[dict[str, Any]] = []
        for entity in entities:  # first-seen entity order
            for spec in fields:  # then first-seen field order
                if entity.state != "active":
                    result = _disposition(
                        spec,
                        "superseded_entity" if entity.state == "superseded" else "retired_entity",
                    )
                elif (
                    requested_as_of is not None
                    and requested_as_of < now
                    and spec.point_in_time_policy == "current_only"
                ):
                    result = _disposition(spec, "history_not_supported")
                else:
                    result = owner_results[(entity.id, spec.field_id)]
                envelopes.append(self._envelope(spec, entity, result, request, context))
        return tuple(envelopes)

    def _envelope(
        self,
        spec: FieldSpec,
        entity: CanonicalEntity,
        result: AdapterResult,
        request: ResolutionRequest,
        context: RequestContext,
    ) -> dict[str, Any]:
        try:
            value = validate_adapter_result(spec, result)
            unit = concrete_unit(spec, result)
            observed_at = validate_clock(result.observed_at, field_name="observed_at")
            effective_at = validate_clock(result.effective_at, field_name="effective_at")
            as_of = validate_clock(result.as_of, field_name="as_of")
        except DatapointContractError as exc:
            raise AdapterContractError(f"invalid {spec.field_id}/{entity.id} owner result: {exc}") from exc

        subscriber = request.audience == "subscriber"
        blocked = False
        allowed_uses = list(spec.consumer_uses)
        if subscriber:
            if spec.rights_policy == "internal_only":
                blocked = True
            elif spec.rights_policy == "owner_dynamic":
                if self.rights_projector is None:
                    blocked = True
                else:
                    decision = self.rights_projector(spec, result, entity, context)
                    if isinstance(decision, bool):
                        decision = RightsDecision(decision)
                    if not isinstance(decision, RightsDecision):
                        raise AdapterContractError("rights projector returned invalid decision")
                    blocked = not decision.allowed
                    if decision.consumer_uses is not None:
                        invalid = set(decision.consumer_uses) - set(spec.consumer_uses)
                        if invalid:
                            raise AdapterContractError("rights projector widened consumer uses")
                        allowed_uses = [use for use in spec.consumer_uses if use in decision.consumer_uses]
                        if request.consumer_use not in allowed_uses:
                            blocked = True

        status = "rights_blocked" if blocked else result.status
        reason_code = "rights_blocked" if blocked else result.reason_code
        envelope: dict[str, Any] = {
            "schema": VALUE_SCHEMA,
            "registry_version": self.registry.registry_version,
            "registry_digest": self.registry.digest,
            "field_id": spec.field_id,
            "entity": {"type": entity.type, "id": entity.id},
            "value": None if blocked else value,
            "status": status,
            "reason_code": reason_code,
            "unit": unit,
            "observed_at": observed_at,
            "effective_at": effective_at,
            "as_of": as_of,
            "generated_at": iso_utc(context.generated_at),
            "freshness": thaw(result.freshness),
            "quality": thaw(result.quality),
            "source": _source_payload(result.source, subscriber=subscriber),
            "provenance": _provenance_payload(result.provenance, subscriber=subscriber),
            "consumer_uses": allowed_uses,
            "audience": request.audience,
            "fact_fingerprint": "",
        }
        if subscriber:
            _validate_subscriber_metadata(envelope["source"], location="source")
            _validate_subscriber_metadata(envelope["provenance"], location="provenance")
        envelope["fact_fingerprint"] = semantic_fingerprint(envelope)
        self._validate_envelope(envelope)
        return envelope

    @staticmethod
    def _validate_envelope(envelope: Mapping[str, Any]) -> None:
        canonical_json_bytes(envelope)
        errors = list(_value_validator().iter_errors(envelope))
        if errors:
            error = sorted(errors, key=lambda item: tuple(str(p) for p in item.absolute_path))[0]
            location = ".".join(str(part) for part in error.absolute_path) or "<root>"
            raise AdapterContractError(f"datapoint_value schema violation at {location}: {error.message}")
