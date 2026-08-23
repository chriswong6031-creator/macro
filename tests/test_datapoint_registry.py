from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
from types import MappingProxyType

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from engine.intelligence_workspace.contracts import (
    AdapterResult,
    CanonicalEntity,
    DatapointContractError,
    RightsDecision,
)
from engine.intelligence_workspace.registry import (
    FROZEN_FIELD_IDS,
    clear_registry_cache,
    load_registry,
)
from engine.intelligence_workspace.resolver import (
    AdapterContractError,
    DatapointResolver,
    RequestValidationError,
    VALUE_SCHEMA_PATH,
)


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "config/intelligence_workspace/datapoints.v1.json"
NOW = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)


def _catalog() -> dict:
    return json.loads(CATALOG.read_text(encoding="utf-8"))


def _load_mutant(tmp_path: Path, mutate) -> None:
    payload = _catalog()
    mutate(payload)
    path = tmp_path / "mutant.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    clear_registry_cache()
    load_registry(path)


class Identity:
    calls = 0

    def normalize_many(self, entities):
        self.calls += 1
        out = []
        for entity in entities:
            entity_id = entity.id or "SEC:US-XNAS-AAPL"
            out.append(
                CanonicalEntity(
                    entity.type,
                    entity_id,
                    entity.universe or "us_equity",
                    alias_interpretation="current_alias_only" if entity.symbol else None,
                )
            )
        return out


class Adapter:
    def __init__(self, values=None):
        self.values = {} if values is None else values
        self.calls = 0

    def resolve_many(self, entities, specs, request, context):
        self.calls += 1
        context.memoize(f"load:{specs[0].adapter_id}", lambda: object())
        returned = {}
        for spec in specs:
            default = 2 if spec.value_type == "integer" else 15.0
            value = self.values[spec.field_id] if spec.field_id in self.values else default
            unit = "USD" if spec.unit_policy == "owner_currency_code" else spec.unit
            if spec.value_type == "date":
                value = "2026-10-29"
            elif spec.value_type == "entity_ref_set" and spec.field_id not in self.values:
                value = ["ltheme:finviz:ai", "ltheme:finviz:cloud"]
            returned.update({
                (entity.id, spec.field_id): AdapterResult(
                value=value,
                status="available",
                reason_code=None,
                unit=unit,
                observed_at="2026-08-22",
                effective_at="2026-08-22",
                as_of="2026-08-22",
                freshness={"state": "fresh", "policy": "owner_native"},
                quality={"state": "ok", "issues": []},
                source={
                    "source_id": f"owner.{spec.owner_field_key}",
                    "owner": spec.owner_ref["owner"],
                    "license_class": "internal_derived",
                    "dataset_id": spec.owner_ref["dataset_id"],
                    "artifact_id": "/Users/private/owner.json",
                },
                provenance={
                    "kind": "owner_derived",
                    "owner_field_key": spec.owner_field_key,
                    "basis": spec.basis_policy,
                    "owner_artifact": "/Users/private/owner.json",
                },
            )
                for entity in entities
            })
        return returned


def _resolver(field_ids, *, adapter=None, audience="internal", requested_as_of=None, rights=None):
    registry = load_registry()
    adapters = {registry.field(field_id).adapter_id: adapter or Adapter() for field_id in field_ids}
    resolver = DatapointResolver(
        registry=registry,
        identity_normalizer=Identity(),
        adapters=adapters,
        rights_projector=rights,
        clock=lambda: NOW,
    )
    request = {
        "entities": [{"type": "security", "id": "SEC:US-XNAS-AAPL", "universe": "us_equity"}],
        "field_ids": list(field_ids),
        "audience": audience,
        "consumer_use": "query",
        "requested_as_of": requested_as_of,
    }
    return resolver, request


def test_registry_exact_manifest_digest_and_immutable_cache():
    clear_registry_cache()
    first = load_registry()
    second = load_registry()
    assert first is second
    assert tuple(field.field_id for field in first.fields) == FROZEN_FIELD_IDS
    assert len(first.digest) == 64
    assert first.limits == {"max_fields": 12, "max_entities": 250, "max_cells": 2000, "max_request_cost": 8000}
    with pytest.raises(TypeError):
        first.limits["max_fields"] = 13


def test_registry_root_cost_ceiling_is_frozen(tmp_path):
    with pytest.raises(DatapointContractError, match="schema violation.*8000"):
        _load_mutant(
            tmp_path,
            lambda document: document["limits"].update(max_request_cost=99999),
        )


@pytest.mark.parametrize(
    "mutate,match",
    [
        (lambda doc: doc.update(schema="wrong"), "schema violation"),
        (lambda doc: doc.update(registry_version="2.0.0"), "schema violation"),
        (lambda doc: doc["fields"].__setitem__(1, deepcopy(doc["fields"][0])), "manifest must be exact"),
        (lambda doc: doc["fields"][2].update(unit="ratio"), "frozen semantic drift"),
        (lambda doc: doc["fields"][4].update(value_type="number"), "frozen semantic drift"),
        (lambda doc: doc["fields"][6].update(entity_types=["security"]), "frozen semantic drift"),
        (lambda doc: doc["fields"][0].update(adapter_id="unknown"), "schema violation"),
        (lambda doc: doc["fields"][0].update(owner_field_key="bogus"), "unknown owner field"),
        (lambda doc: doc["fields"][8].update(operators=["contains"]), "incompatible"),
        (lambda doc: doc["fields"][8].update(constraints={"minimum": 0}), "invalid constraints"),
        (lambda doc: doc["fields"][0].update(rights_policy="public"), "schema violation"),
        (lambda doc: doc["fields"][0].update(consumer_uses=["rank"]), "schema violation"),
        (lambda doc: doc["fields"][0].update(point_in_time_policy="retro_stamp"), "schema violation"),
        (lambda doc: doc["fields"][0].update(cost_weight=0), "schema violation"),
        (lambda doc: doc["fields"][0]["owner_ref"].update(owner="unrelated_owner"), "frozen semantic drift"),
        (lambda doc: doc["fields"][4].update(constraints={"minimum": 0, "maximum": 4}), "frozen semantic drift"),
        (lambda doc: doc["fields"][0].update(universes=["us_industry"]), "frozen semantic drift"),
        (lambda doc: doc["fields"][0].update(timestamp_policy="owner_build_clock"), "frozen semantic drift"),
        (lambda doc: doc["fields"][0]["owner_ref"].update(dataset_id="equity.bars.daily.stocks"), "frozen semantic drift"),
    ],
)
def test_registry_mutants_fail_closed(tmp_path, mutate, match):
    with pytest.raises(DatapointContractError, match=match):
        _load_mutant(tmp_path, mutate)


def test_catalog_does_not_mint_dataset_ids():
    assert all(field["owner_ref"]["dataset_id"] is None for field in _catalog()["fields"])


def test_unregistered_dataset_id_fails_closed(tmp_path):
    with pytest.raises(DatapointContractError, match="not registered in Data OS"):
        _load_mutant(
            tmp_path,
            lambda doc: doc["fields"][0]["owner_ref"].update(dataset_id="fake.owner.output"),
        )


def test_stage_integer_envelope_validates_against_json_schema():
    resolver, request = _resolver(["stage.current"])
    envelope = resolver.resolve(request)[0]
    assert envelope["value"] == 2
    schema = json.loads(VALUE_SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(envelope)


@pytest.mark.parametrize("value", [0.0, -0.0])
def test_zero_is_available(value):
    adapter = Adapter({"market.return.3m": value})
    resolver, request = _resolver(["market.return.3m"], adapter=adapter)
    envelope = resolver.resolve(request)[0]
    assert envelope["status"] == "available"
    assert envelope["value"] == value


@pytest.mark.parametrize("value", [float("nan"), float("inf"), None])
def test_non_finite_or_null_available_scalar_refused(value):
    adapter = Adapter({"market.return.3m": value})
    resolver, request = _resolver(["market.return.3m"], adapter=adapter)
    with pytest.raises(AdapterContractError):
        resolver.resolve(request)


def test_theme_set_sorted_and_empty_available():
    for source, expected in [([], []), (["ltheme:finviz:z", "ltheme:finviz:a"], ["ltheme:finviz:a", "ltheme:finviz:z"])]:
        adapter = Adapter({"theme.local.memberships": source})
        resolver, request = _resolver(
            ["theme.local.memberships"], adapter=adapter, rights=lambda *_: RightsDecision(True)
        )
        assert resolver.resolve(request)[0]["value"] == expected


def test_request_validation_happens_before_identity_or_adapter_io():
    identity = Identity()
    adapter = Adapter()
    resolver = DatapointResolver(
        identity_normalizer=identity,
        adapters={"technicals": adapter},
        clock=lambda: NOW,
    )
    with pytest.raises(RequestValidationError, match="duplicate requested field"):
        resolver.resolve(
            {
                "entities": [{"type": "security", "id": "SEC:US-XNAS-AAPL"}],
                "field_ids": ["market.return.3m", "market.return.3m"],
                "audience": "internal",
                "consumer_use": "query",
            }
        )
    assert identity.calls == 0
    assert adapter.calls == 0


def test_future_cutoff_rejected_before_io_and_current_only_history_has_no_owner_call():
    resolver, request = _resolver(["market.return.3m"], requested_as_of="2026-08-24T00:00:00Z")
    adapter = resolver.adapters["technicals"]
    with pytest.raises(RequestValidationError, match="future"):
        resolver.resolve(request)
    assert adapter.calls == 0

    resolver, request = _resolver(["market.return.3m"], requested_as_of="2026-08-01T00:00:00Z")
    adapter = resolver.adapters["technicals"]
    result = resolver.resolve(request)[0]
    assert result["status"] == "unavailable"
    assert result["reason_code"] == "history_not_supported"
    assert result["value"] is None
    assert result["observed_at"] is None
    assert adapter.calls == 0

    # A historical current-only request is a resolver disposition and does not
    # require the runtime owner adapter to be installed.
    no_adapter = DatapointResolver(
        identity_normalizer=Identity(),
        adapters={},
        clock=lambda: NOW,
    )
    result = no_adapter.resolve(request)[0]
    assert result["reason_code"] == "history_not_supported"


def test_symbol_alias_normalizes_then_historical_current_only_disposes_without_adapter_io():
    resolver, request = _resolver(["market.return.3m"], requested_as_of="2026-08-01T00:00:00Z")
    request["entities"] = [{"type": "security", "symbol": "AAPL"}]
    adapter = resolver.adapters["technicals"]
    envelope = resolver.resolve(request)[0]
    assert envelope["entity"]["id"] == "SEC:US-XNAS-AAPL"
    assert envelope["reason_code"] == "history_not_supported"
    assert adapter.calls == 0


def test_owner_adapter_boundary_is_audience_and_use_blind():
    class BlindnessProbe(Adapter):
        def __init__(self):
            super().__init__({"market.return.3m": 15.0})
            self.seen = []

        def resolve_many(self, entities, specs, request, context):
            assert set(request.__dataclass_fields__) == {"requested_as_of"}
            assert not hasattr(request, "audience") and not hasattr(request, "consumer_use")
            assert not hasattr(context, "audience") and not hasattr(context, "consumer_use")
            self.seen.append(request)
            return super().resolve_many(entities, specs, request, context)

    adapter = BlindnessProbe()
    fingerprints = []
    for audience, use in [
        ("internal", "query"),
        ("subscriber", "display"),
        ("subscriber", "context"),
    ]:
        resolver, request = _resolver(["market.return.3m"], adapter=adapter, audience=audience)
        request["consumer_use"] = use
        fingerprints.append(resolver.resolve(request)[0]["fact_fingerprint"])
    assert len(adapter.seen) == 3
    assert len(set(fingerprints)) == 1


def test_explicit_canonical_id_cannot_be_redirected():
    class RedirectIdentity:
        def normalize_many(self, entities):
            return [CanonicalEntity("security", "SEC:US-XNAS-MSFT", "us_equity")]

    resolver = DatapointResolver(
        identity_normalizer=RedirectIdentity(),
        adapters={"technicals": Adapter()},
        clock=lambda: NOW,
    )
    with pytest.raises(RequestValidationError, match="silently redirected"):
        resolver.resolve(
            {
                "entities": [{"type": "security", "id": "SEC:US-XNAS-AAPL"}],
                "field_ids": ["market.return.3m"],
                "audience": "internal",
                "consumer_use": "query",
            }
        )


def test_subscriber_projection_is_monotonic_and_strips_private_path():
    adapter = Adapter({"market.return.3m": 15.0})
    internal_resolver, internal_request = _resolver(["market.return.3m"], adapter=adapter)
    internal = internal_resolver.resolve(internal_request)[0]
    subscriber_resolver, subscriber_request = _resolver(
        ["market.return.3m"], adapter=adapter, audience="subscriber"
    )
    subscriber = subscriber_resolver.resolve(subscriber_request)[0]
    assert subscriber["value"] == internal["value"]
    assert subscriber["observed_at"] == internal["observed_at"]
    assert "owner_artifact" in internal["provenance"]
    assert "owner_artifact" not in subscriber["provenance"]
    assert "/Users/private" not in json.dumps(subscriber)


@pytest.mark.parametrize(
    "smuggled",
    [
        "/Users/private/secret.json",
        "data/private/secret.json",
        "research/private_notes.md",
        "code/private.py",
        "config/private.json",
        "contracts/private.json",
        "scripts/private.py",
        "tests/private.json",
        "site/private.json",
        "engine/private.py",
        "templates/private.html",
        "lib/private.py",
        "collectors/private.py",
        "agentos/private.md",
        "docs/private.md",
        ".github/workflows/private.yml",
        "file:///tmp/secret",
        "provider_metadata=secret",
        "credentials=secret",
    ],
)
def test_subscriber_projection_rejects_private_or_path_like_metadata(smuggled):
    class Smuggle(Adapter):
        def resolve_many(self, entities, specs, request, context):
            rows = super().resolve_many(entities, specs, request, context)
            key, result = next(iter(rows.items()))
            source = dict(result.source)
            source["source_family"] = smuggled
            return {key: replace(result, source=source)}

    resolver, request = _resolver(
        ["market.return.3m"], adapter=Smuggle(), audience="subscriber"
    )
    with pytest.raises(AdapterContractError, match="private/path-like"):
        resolver.resolve(request)


@pytest.mark.parametrize("dataset_id", ["fake.owner.output", "equity.bars.daily.stocks"])
def test_runtime_source_dataset_id_must_be_registered_and_frozen_lineage_compatible(dataset_id):
    class WrongDataset(Adapter):
        def resolve_many(self, entities, specs, request, context):
            rows = super().resolve_many(entities, specs, request, context)
            key, result = next(iter(rows.items()))
            source = dict(result.source)
            source["dataset_id"] = dataset_id
            return {key: replace(result, source=source)}

    resolver, request = _resolver(["market.return.3m"], adapter=WrongDataset())
    with pytest.raises(AdapterContractError, match="dataset_id"):
        resolver.resolve(request)


def test_runtime_source_owner_must_match_frozen_owner_but_resolver_dispositions_remain_valid():
    class WrongOwner(Adapter):
        def resolve_many(self, entities, specs, request, context):
            rows = super().resolve_many(entities, specs, request, context)
            key, result = next(iter(rows.items()))
            source = dict(result.source)
            source["owner"] = "unrelated_owner"
            return {key: replace(result, source=source)}

    resolver, request = _resolver(["market.return.3m"], adapter=WrongOwner())
    with pytest.raises(AdapterContractError, match="source owner"):
        resolver.resolve(request)

    historical, historical_request = _resolver(
        ["market.return.3m"], requested_as_of="2026-08-01T00:00:00Z"
    )
    envelope = historical.resolve(historical_request)[0]
    assert envelope["reason_code"] == "history_not_supported"
    assert envelope["source"]["owner"] == "intelligence_workspace"


def test_adapter_cannot_masquerade_as_a_resolver_disposition():
    class Masquerade(Adapter):
        def resolve_many(self, entities, specs, request, context):
            rows = super().resolve_many(entities, specs, request, context)
            key, result = next(iter(rows.items()))
            source = dict(result.source)
            source["owner"] = "intelligence_workspace"
            provenance = dict(result.provenance)
            provenance["kind"] = "resolver_disposition"
            return {key: replace(result, source=source, provenance=provenance)}

    resolver, request = _resolver(["market.return.3m"], adapter=Masquerade())
    with pytest.raises(AdapterContractError, match="forge a resolver_disposition"):
        resolver.resolve(request)


def test_superseded_entity_is_not_silently_redirected_or_read_from_owner():
    class SupersededIdentity(Identity):
        def normalize_many(self, entities):
            self.calls += 1
            return [
                CanonicalEntity(
                    type="security",
                    id=entity.id,
                    universe=entity.universe or "us_equity",
                    state="superseded",
                )
                for entity in entities
            ]

    adapter = Adapter()
    resolver = DatapointResolver(
        registry=load_registry(),
        identity_normalizer=SupersededIdentity(),
        adapters={"quote": adapter},
        clock=lambda: NOW,
    )
    envelope = resolver.resolve(
        {
            "entities": [
                {
                    "type": "security",
                    "id": "SEC:US-XNAS-AAPL",
                    "universe": "us_equity",
                }
            ],
            "field_ids": ["market.price.last"],
            "audience": "internal",
            "consumer_use": "query",
        }
    )[0]

    assert envelope["entity"]["id"] == "SEC:US-XNAS-AAPL"
    assert envelope["status"] == "unavailable"
    assert envelope["reason_code"] == "superseded_entity"
    assert adapter.calls == 0


@pytest.mark.parametrize("clock", ["2026-08-22T13:14:15Z", "2026-08-22T13:14:15.123Z"])
def test_owner_timestamp_precision_is_preserved_lexically(clock):
    class Clocked(Adapter):
        def resolve_many(self, entities, specs, request, context):
            rows = super().resolve_many(entities, specs, request, context)
            return {
                key: replace(result, observed_at=clock, effective_at=clock, as_of=clock)
                for key, result in rows.items()
            }

    resolver, request = _resolver(["market.return.3m"], adapter=Clocked())
    envelope = resolver.resolve(request)[0]
    assert envelope["observed_at"] == clock
    assert envelope["effective_at"] == clock
    assert envelope["as_of"] == clock


def test_dynamic_theme_rights_block_is_typed_and_does_not_leak_value():
    adapter = Adapter({"theme.local.memberships": ["ltheme:finviz:ai"]})
    resolver, request = _resolver(
        ["theme.local.memberships"],
        adapter=adapter,
        audience="subscriber",
        rights=lambda *_: RightsDecision(False),
    )
    envelope = resolver.resolve(request)[0]
    assert envelope["status"] == "rights_blocked"
    assert envelope["reason_code"] == "rights_blocked"
    assert envelope["value"] is None


def test_order_fingerprint_and_request_scoped_memoization():
    adapter = Adapter({"market.return.1m": 1.0, "market.return.3m": 3.0})
    resolver, request = _resolver(["market.return.3m", "market.return.1m"], adapter=adapter)
    result = resolver.resolve(request)
    assert [row["field_id"] for row in result] == ["market.return.3m", "market.return.1m"]
    assert adapter.calls == 1
    assert len({row["fact_fingerprint"] for row in result}) == 2
    # Both owner fields are dispatched in one adapter batch and share one
    # request-scoped source load.
    assert all(len(row["fact_fingerprint"]) == 64 for row in result)


def test_nonavailable_numeric_cannot_smuggle_zero():
    class Bad(Adapter):
        def resolve_many(self, entities, specs, request, context):
            row = super().resolve_many(entities, specs, request, context)
            result = next(iter(row.values()))
            return {
                next(iter(row)): AdapterResult(
                    value=0.0,
                    status="unavailable",
                    reason_code="owner_unavailable",
                    unit=result.unit,
                    observed_at=result.observed_at,
                    effective_at=result.effective_at,
                    as_of=result.as_of,
                    freshness=result.freshness,
                    quality=result.quality,
                    source=result.source,
                    provenance=result.provenance,
                )
            }

    resolver, request = _resolver(["market.return.3m"], adapter=Bad())
    with pytest.raises(AdapterContractError, match="value=null"):
        resolver.resolve(request)


@pytest.mark.parametrize(
    "changes",
    [
        {"value": None},
        {"status": "unavailable", "reason_code": "owner_unavailable"},
        {"status": "rights_blocked", "reason_code": "owner_unavailable", "value": None},
        {"status": "stale", "reason_code": "owner_unavailable", "value": None},
        {"status": "not_applicable", "reason_code": "value_missing", "value": None},
    ],
)
def test_value_schema_rejects_invalid_status_reason_value_combinations(changes):
    resolver, request = _resolver(["stage.current"])
    envelope = resolver.resolve(request)[0]
    envelope.update(changes)
    schema = json.loads(VALUE_SCHEMA_PATH.read_text(encoding="utf-8"))
    errors = list(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(envelope)
    )
    assert errors


def test_three_part_adapter_key_validates_entity_type_component():
    class WrongType(Adapter):
        def resolve_many(self, entities, specs, request, context):
            rows = super().resolve_many(entities, specs, request, context)
            (_, field_id), result = next(iter(rows.items()))
            return {("industry", entities[0].id, field_id): result}

    resolver, request = _resolver(["market.return.3m"], adapter=WrongType())
    with pytest.raises(AdapterContractError, match="mismatched entity type"):
        resolver.resolve(request)


@pytest.mark.parametrize(
    "limit_name,limit_value,entities,field_ids,match",
    [
        (
            "max_cells",
            1,
            [
                {"type": "security", "id": "SEC:US-XNAS-AAPL"},
                {"type": "security", "id": "SEC:US-XNAS-MSFT"},
            ],
            ["market.return.3m"],
            "max_cells",
        ),
        (
            "max_request_cost",
            1,
            [{"type": "security", "id": "SEC:US-XNAS-AAPL"}],
            ["market.price.last"],
            "max_request_cost",
        ),
    ],
)
def test_cell_and_cost_limits_fail_before_identity_or_adapter_io(
    limit_name, limit_value, entities, field_ids, match
):
    base = load_registry()
    limits = dict(base.limits)
    limits[limit_name] = limit_value
    registry = replace(base, limits=MappingProxyType(limits))
    identity = Identity()
    adapter = Adapter()
    resolver = DatapointResolver(
        registry=registry,
        identity_normalizer=identity,
        adapters={base.field(field_ids[0]).adapter_id: adapter},
        clock=lambda: NOW,
    )
    with pytest.raises(RequestValidationError, match=match):
        resolver.resolve(
            {
                "entities": entities,
                "field_ids": field_ids,
                "audience": "internal",
                "consumer_use": "query",
            }
        )
    assert identity.calls == 0
    assert adapter.calls == 0
