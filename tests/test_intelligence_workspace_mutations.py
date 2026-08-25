from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pytest

from engine.intelligence_workspace.adapters.company_intelligence import (
    CompanyIntelligenceAdapter,
)
from engine.intelligence_workspace.adapters.industry import IndustryAdapter
from engine.intelligence_workspace.adapters.stage import StageAdapter
from engine.intelligence_workspace.adapters.technicals import TechnicalsAdapter
from engine.intelligence_workspace.adapters.theme import ThemeAdapter
from engine.intelligence_workspace.consumers import (
    evaluate_stage_momentum_fixture,
    parity_projection,
)
from engine.intelligence_workspace.contracts import (
    AdapterResult,
    CanonicalEntity,
    DatapointContractError,
    RightsDecision,
)
from engine.intelligence_workspace.registry import load_registry
from engine.intelligence_workspace.resolver import (
    AdapterContractError,
    DatapointResolver,
    RequestValidationError,
)


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "config/intelligence_workspace/datapoints.v1.json"
NOW = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)
AAPL = "SEC:US-XNAS-AAPL"


class _Identity:
    def __init__(self) -> None:
        self.calls = 0

    def normalize_many(self, entities):
        self.calls += 1
        out = []
        for entity in entities:
            if entity.type == "industry":
                out.append(CanonicalEntity("industry", str(entity.id), "us_industry"))
            else:
                out.append(
                    CanonicalEntity(
                        "security",
                        str(entity.id or AAPL),
                        "us_equity",
                        alias_interpretation="current_alias_only" if entity.symbol else None,
                    )
                )
        return tuple(out)


class _StaticAdapter:
    def __init__(self, values: dict[str, Any]) -> None:
        self.values = values
        self.calls = 0

    def resolve_many(self, entities, specs, request, context):
        del request, context
        self.calls += 1
        return {
            (entity.type, entity.id, spec.field_id): _available(spec, self.values[spec.field_id])
            for entity in entities
            for spec in specs
        }


def _available(
    spec,
    value: Any,
    *,
    clock: Any = "2026-08-22T15:30:00Z",
    freshness: str = "fresh",
    source_extra: dict[str, Any] | None = None,
    provenance_extra: dict[str, Any] | None = None,
) -> AdapterResult:
    source = {
        "source_id": f"mutation_fixture.{spec.owner_field_key}",
        "owner": spec.owner_ref["owner"],
        "license_class": "internal_derived",
        "dataset_id": spec.owner_ref["dataset_id"],
    }
    source.update(source_extra or {})
    provenance = {
        "kind": "owner_derived",
        "owner_field_key": spec.owner_field_key,
        "basis": spec.basis_policy,
    }
    provenance.update(provenance_extra or {})
    return AdapterResult(
        value=value,
        status="available",
        reason_code=None,
        unit="USD" if spec.unit_policy == "owner_currency_code" else spec.unit,
        observed_at=clock,
        effective_at=clock,
        as_of=clock,
        freshness={"state": freshness, "policy": "owner_native"},
        quality={"state": "ok", "issues": []},
        source=source,
        provenance=provenance,
    )


def _resolver(adapters, *, registry=None, rights_projector=None, identity=None):
    return DatapointResolver(
        registry=registry or load_registry(),
        identity_normalizer=identity or _Identity(),
        adapters=adapters,
        rights_projector=rights_projector,
        clock=lambda: NOW,
    )


def _request(
    field_ids,
    *,
    entity: dict[str, Any] | None = None,
    audience: str = "internal",
    requested_as_of: str | None = None,
):
    payload = {
        "entities": [
            entity
            or {"type": "security", "id": AAPL, "universe": "us_equity"}
        ],
        "field_ids": list(field_ids),
        "audience": audience,
        "consumer_use": "query",
    }
    if requested_as_of is not None:
        payload["requested_as_of"] = requested_as_of
    return payload


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _stage_document(stage: int, *, current: bool = True) -> dict[str, Any]:
    return {
        "asof": "2026-08-23",
        "built": "2026-08-23T03:55:25Z",
        "stage_week_end": "2026-08-21",
        "rows": [
            {
                "ticker": "AAPL",
                "source": "live",
                "stage": stage,
                "weeks_in_stage": 7,
                "stage_current": current,
                "stage_source_asof": "2026-08-01" if not current else "2026-08-21",
                "stage_week_end": "2026-08-21",
            }
        ],
    }


def test_m01_industry_rank_member_swap_is_killed(tmp_path: Path) -> None:
    """M1 industry swap: rank-owner invariant fails because member RS (19), not rank (72), is emitted."""
    _write_json(
        tmp_path / "data/stage_analysis/industry_ranks.json",
        {
            "asof": "2026-08-23",
            "built": "2026-08-23T04:00:00Z",
            "status": "ready",
            "coverage": {"status": "ready", "freshness": {"status": "current"}},
            "regions": {
                "USA": [
                    {
                        "region": "USA",
                        "industry_id": "software",
                        "industry_percentile": 72.0,
                    }
                ]
            },
        },
    )
    _write_json(
        tmp_path / "data/stage_analysis/industry_name_pctile.json",
        {
            "asof": "2026-08-23",
            "built": "2026-08-23T04:01:00Z",
            "status": "ready",
            "coverage": {"status": "ready", "freshness": {"status": "current"}},
            "percentiles": {"AAPL": 19.0},
        },
    )

    class IndustrySwapMutant(IndustryAdapter):
        def resolve_many(self, entities, specs, request, context):
            rows = super().resolve_many(entities, specs, request, context)
            member_document, issue = self._load_json(self.member_path, "percentiles")
            assert issue is None and member_document is not None
            member_value = member_document["percentiles"]["AAPL"]
            out = {}
            for key, result in rows.items():
                source = dict(result.source)
                source["source_id"] = "stage_industry.industry_name_pctile"
                out[key] = replace(result, value=member_value, source=source)
            return out

    envelope = _resolver(
        {
            "industry": IndustrySwapMutant(
                repo_root=tmp_path,
                symbol_map_loader=lambda: {AAPL: "AAPL"},
            )
        }
    ).resolve(
        _request(
            ["industry.rank.percentile"],
            entity={"type": "industry", "id": "software", "universe": "us_industry"},
        )
    )[0]

    with pytest.raises(AssertionError, match="M1 rank/member swap"):
        assert (
            envelope["value"] == 72.0
            and envelope["source"]["source_id"] == "stage_industry.industry_ranks"
        ), "M1 rank/member swap replaced the industry-rank owner fact"


def test_m02_generated_at_freshness_laundering_is_killed(tmp_path: Path) -> None:
    """M2 generated-at freshness: explicit stale owner health cannot become fresh from resolver now."""
    _write_json(
        tmp_path / "data/stage_analysis/screener.json",
        _stage_document(2, current=False),
    )

    class GeneratedAtFreshnessMutant(StageAdapter):
        def resolve_many(self, entities, specs, request, context):
            rows = super().resolve_many(entities, specs, request, context)
            assert context.generated_at == NOW
            return {
                key: replace(
                    result,
                    value=2,
                    status="available",
                    reason_code=None,
                    freshness={"state": "fresh", "policy": "owner_native"},
                )
                for key, result in rows.items()
            }

    envelope = _resolver(
        {
            "stage": GeneratedAtFreshnessMutant(
                repo_root=tmp_path,
                symbol_map_loader=lambda: {AAPL: "AAPL"},
            )
        }
    ).resolve(_request(["stage.current"]))[0]

    with pytest.raises(AssertionError, match="M2 generated_at freshness"):
        assert (
            envelope["status"], envelope["freshness"]["state"], envelope["value"]
        ) == ("stale", "stale", None), "M2 generated_at freshness laundered stale owner health"


def test_m03_percent_ratio_drift_is_killed(tmp_path: Path) -> None:
    """M3 percent-to-ratio drift: stage/momentum consumer invariant fails when 15 percent becomes .15."""
    _write_json(
        tmp_path / "site/stockdata/AAPL.json",
        {"asof": "2026-08-22", "tech": {"ret_3m": 15.0}},
    )

    class RatioMutant(TechnicalsAdapter):
        def resolve_many(self, entities, specs, request, context):
            rows = super().resolve_many(entities, specs, request, context)
            return {key: replace(result, value=result.value / 100) for key, result in rows.items()}

    envelopes = _resolver(
        {
            "stage": _StaticAdapter({"stage.current": 2}),
            "technicals": RatioMutant(root=tmp_path, symbol_resolver=lambda _entity: "AAPL"),
        }
    ).resolve(_request(["stage.current", "market.return.3m"]))
    evaluation = evaluate_stage_momentum_fixture(envelopes)

    with pytest.raises(AssertionError, match="M3 percent/ratio drift"):
        assert evaluation["matched"], "M3 percent/ratio drift broke the percent consumer contract"


def test_m04_null_to_zero_is_killed() -> None:
    """M4 null-to-zero: missingness contract rejects zero smuggled under unavailable status."""

    class NullToZeroMutant:
        def resolve_many(self, entities, specs, request, context):
            del request, context
            spec = specs[0]
            result = replace(
                _available(spec, 0.0),
                status="unavailable",
                reason_code="owner_missing",
            )
            return {(entities[0].type, entities[0].id, spec.field_id): result}

    with pytest.raises(AdapterContractError, match="value=null"):
        _resolver({"technicals": NullToZeroMutant()}).resolve(
            _request(["market.return.3m"])
        )


def test_m05_stage_zero_laundering_is_killed(tmp_path: Path) -> None:
    """M5 Stage 0 laundering: Stage constraint invariant rejects available zero below minimum one."""
    _write_json(
        tmp_path / "data/stage_analysis/screener.json",
        _stage_document(0),
    )

    class StageZeroMutant(StageAdapter):
        def resolve_many(self, entities, specs, request, context):
            rows = super().resolve_many(entities, specs, request, context)
            return {
                key: replace(
                    result,
                    value=0,
                    status="available",
                    reason_code=None,
                    freshness={"state": "fresh", "policy": "owner_native"},
                )
                for key, result in rows.items()
            }

    with pytest.raises(AdapterContractError, match="below minimum"):
        _resolver(
            {
                "stage": StageZeroMutant(
                    repo_root=tmp_path,
                    symbol_map_loader=lambda: {AAPL: "AAPL"},
                )
            }
        ).resolve(_request(["stage.current"]))


def test_m06_current_identity_as_historical_truth_is_killed() -> None:
    """M6 current identity as history: PIT invariant fails if cutoff is stripped and owner I/O occurs."""
    owner = _StaticAdapter({"market.return.3m": 15.0})

    class HistoricalTruthMutant(DatapointResolver):
        def resolve(self, payload):
            mutated = dict(payload)
            mutated.pop("requested_as_of", None)
            return super().resolve(mutated)

    mutant = HistoricalTruthMutant(
        identity_normalizer=_Identity(),
        adapters={"technicals": owner},
        clock=lambda: NOW,
    )
    envelope = mutant.resolve(
        _request(
            ["market.return.3m"],
            entity={"type": "security", "symbol": "AAPL"},
            requested_as_of="2026-08-01T00:00:00Z",
        )
    )[0]

    with pytest.raises(AssertionError, match="M6 current alias historical truth"):
        assert (
            envelope["reason_code"] == "history_not_supported" and owner.calls == 0
        ), "M6 current alias historical truth reached the current owner"


def test_m07_subscriber_rights_leak_is_killed() -> None:
    """M7 rights leak: subscriber projection invariant fails when a denied local theme is emitted."""
    owner = _StaticAdapter({"theme.local.memberships": ["ltheme:private:alpha"]})
    envelope = _resolver(
        {"theme": owner},
        rights_projector=lambda *_: RightsDecision(True),
    ).resolve(
        _request(
            ["theme.local.memberships"],
            audience="subscriber",
        )
    )[0]

    with pytest.raises(AssertionError, match="M7 subscriber rights leak"):
        assert (
            envelope["status"], envelope["reason_code"], envelope["value"]
        ) == (
            "rights_blocked",
            "rights_blocked",
            None,
        ), "M7 subscriber rights leak emitted blocked theme structure"


def test_m08_technical_owner_bypass_recomputation_is_killed(tmp_path: Path) -> None:
    """M8 owner bypass: owner-binding invariant fails when local recomputation beats disagreeing owner 15."""
    _write_json(
        tmp_path / "site/stockdata/AAPL.json",
        {"asof": "2026-08-22", "tech": {"ret_3m": 15.0}},
    )

    class RecomputeMutant(TechnicalsAdapter):
        def resolve_many(self, entities, specs, request, context):
            rows = super().resolve_many(entities, specs, request, context)
            recomputed = (137.0 / 100.0 - 1.0) * 100.0
            return {key: replace(result, value=recomputed) for key, result in rows.items()}

    envelope = _resolver(
        {
            "technicals": RecomputeMutant(
                root=tmp_path,
                symbol_resolver=lambda _entity: "AAPL",
            )
        }
    ).resolve(_request(["market.return.3m"]))[0]

    with pytest.raises(AssertionError, match="M8 owner bypass"):
        assert envelope["value"] == 15.0, "M8 owner bypass replaced the owner-published return"


def test_m09_owner_clock_replaced_by_generation_clock_is_killed() -> None:
    """M9 clock replacement: owner event-clock invariant fails when all clocks become generated_at."""

    def reader(_request):
        return {
            "available": True,
            "status": "ready",
            "latest_event": {
                "call_date": "2026-07-31",
                "metrics": {"eps_growth_pct": 20.0},
                "field_lineage": {"metrics": {"eps_growth_pct": "earnings_history"}},
            },
        }

    class GenerationClockMutant(CompanyIntelligenceAdapter):
        def resolve_many(self, entities, specs, request, context):
            rows = super().resolve_many(entities, specs, request, context)
            return {
                key: replace(
                    result,
                    observed_at=context.generated_at,
                    effective_at=context.generated_at,
                    as_of=context.generated_at,
                )
                for key, result in rows.items()
            }

    envelope = _resolver(
        {
            "company_intelligence": GenerationClockMutant(
                symbol_map_loader=lambda: {AAPL: "AAPL"},
                reader=reader,
            )
        }
    ).resolve(_request(["earnings.latest.eps_growth_pct"]))[0]

    with pytest.raises(AssertionError, match="M9 generation clock replacement"):
        assert (
            envelope["observed_at"], envelope["effective_at"], envelope["as_of"]
        ) == (
            "2026-07-31",
            "2026-07-31",
            "2026-07-31",
        ), "M9 generation clock replacement erased the owner event clock"


def test_m10_cell_and_cost_limit_removal_is_killed() -> None:
    """M10 batch-limit removal: max-cell and max-cost pre-I/O invariants both fail when raised."""
    base = load_registry()
    identity = _Identity()
    owner = _StaticAdapter({"market.price.last": 10.0})
    request = {
        "entities": [
            {"type": "security", "id": AAPL},
            {"type": "security", "id": "SEC:US-XNAS-MSFT"},
        ],
        "field_ids": ["market.price.last"],
        "audience": "internal",
        "consumer_use": "query",
    }

    guards = (
        replace(
            base,
            limits=MappingProxyType(
                {**dict(base.limits), "max_cells": 1, "max_request_cost": 8000}
            ),
        ),
        replace(
            base,
            limits=MappingProxyType(
                {**dict(base.limits), "max_cells": 2000, "max_request_cost": 1}
            ),
        ),
    )
    mutants = (
        replace(
            guards[0],
            limits=MappingProxyType(
                {**dict(guards[0].limits), "max_cells": 2}
            ),
        ),
        replace(
            guards[1],
            limits=MappingProxyType(
                {**dict(guards[1].limits), "max_request_cost": 4}
            ),
        ),
    )
    expected = ("max_cells", "max_request_cost")

    def enforce_limit_invariant(mutant, limit_name):
        try:
            _resolver(
                {"quote": owner},
                registry=mutant,
                identity=identity,
            ).resolve(request)
        except RequestValidationError as exc:
            assert limit_name in str(exc)
            return
        raise AssertionError(f"M10 {limit_name} removal allowed owner I/O")

    for guard, mutant, limit_name in zip(guards, mutants, expected, strict=True):
        try:
            _resolver(
                {"quote": owner},
                registry=guard,
                identity=identity,
            ).resolve(request)
        except RequestValidationError as exc:
            assert limit_name in str(exc)
        else:  # pragma: no cover - the guard is the control for the mutant receipt
            raise AssertionError(f"M10 control did not enforce {limit_name}")
        with pytest.raises(AssertionError, match=f"M10 {limit_name} removal"):
            enforce_limit_invariant(mutant, limit_name)

    assert identity.calls == 2 and owner.calls == 2


def test_m11_semantic_id_type_unit_basis_mutation_is_killed(tmp_path: Path) -> None:
    """M11 semantic ID mutation: golden freeze rejects type/unit/basis drift under the same ID."""
    payload = json.loads(CATALOG.read_text(encoding="utf-8"))
    field = next(row for row in payload["fields"] if row["field_id"] == "market.return.3m")
    field.update(value_type="integer", unit="ratio", basis_policy="owner_native")
    mutant = tmp_path / "m11-mutant-catalog.json"
    mutant.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(DatapointContractError, match="frozen semantic drift"):
        load_registry(mutant)


def test_m12_subscriber_numeric_transform_is_killed() -> None:
    """M12 subscriber transform: monotonic parity invariant fails when subscriber number is rescaled."""
    adapter = _StaticAdapter({"market.return.3m": 15.0})
    internal = _resolver({"technicals": adapter}).resolve(
        _request(["market.return.3m"])
    )[0]
    subscriber = _resolver({"technicals": adapter}).resolve(
        _request(["market.return.3m"], audience="subscriber")
    )[0]

    mutant_subscriber = deepcopy(subscriber)
    mutant_subscriber["value"] = round(mutant_subscriber["value"] / 100, 4)
    internal_fact = parity_projection((internal,))[0]
    subscriber_fact = parity_projection((mutant_subscriber,))[0]

    with pytest.raises(AssertionError, match="M12 subscriber numeric transform"):
        assert (
            subscriber_fact["value"] == internal_fact["value"]
        ), "M12 subscriber numeric transform violated monotonic value parity"


def test_m13_local_theme_to_canonical_composition_is_killed() -> None:
    """M13 theme composition: direct-edge/type invariant rejects canonical theme IDs in local set."""

    class ThemeCompositionMutant(ThemeAdapter):
        def resolve_many(self, entities, specs, request, context):
            rows = super().resolve_many(entities, specs, request, context)
            return {key: replace(result, value=["theme:ai"]) for key, result in rows.items()}

    adapter = ThemeCompositionMutant(
        identity_loader=lambda: [
            {
                "node_id": "co:us:AAPL",
                "graph_kind": "company",
                "resolution_state": "RESOLVED",
                "security_id": AAPL,
            }
        ],
        edge_loader=lambda: [
            {
                "type": "MEMBER_OF",
                "src": "co:us:AAPL",
                "dst": "ltheme:finviz:ai",
                "valid_from": "2026-01-01",
                "valid_to": None,
            },
            {
                "type": "EXPRESSES",
                "src": "ltheme:finviz:ai",
                "dst": "theme:ai",
                "valid_from": "2026-01-01",
                "valid_to": None,
            },
        ],
        meta_loader=lambda: {
            "computed_at": "2026-08-23T04:00:00Z",
            "belief_time": "2026-08-23",
        },
    )

    with pytest.raises(AdapterContractError, match="non-local-theme ref"):
        _resolver({"theme": adapter}).resolve(_request(["theme.local.memberships"]))


def test_m14_score_overlay_lineage_laundering_is_killed() -> None:
    """M14 growth-lineage laundering: lineage invariant fails if score_overlay claims earnings_history."""

    def reader(_request):
        return {
            "available": True,
            "status": "ready",
            "latest_event": {
                "call_date": "2026-07-31",
                "metrics": {"revenue_growth_pct": 12.5},
                "field_lineage": {"metrics": {"revenue_growth_pct": "score_overlay"}},
            },
        }

    class LineageLaunderingMutant(CompanyIntelligenceAdapter):
        def resolve_many(self, entities, specs, request, context):
            rows = super().resolve_many(entities, specs, request, context)
            out = {}
            for key, result in rows.items():
                provenance = dict(result.provenance)
                provenance["field_lineage"] = "earnings_history"
                out[key] = replace(result, provenance=provenance)
            return out

    envelope = _resolver(
        {
            "company_intelligence": LineageLaunderingMutant(
                symbol_map_loader=lambda: {AAPL: "AAPL"},
                reader=reader,
            )
        }
    ).resolve(_request(["earnings.latest.revenue_growth_pct"]))[0]

    with pytest.raises(AssertionError, match="M14 growth lineage laundering"):
        assert (
            envelope["provenance"]["field_lineage"] == "score_overlay"
        ), "M14 growth lineage laundering replaced score_overlay provenance"
