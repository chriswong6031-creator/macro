"""Adversarial contract tests for the bitemporal metric query kernel."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
import csv
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext
import hashlib
from itertools import repeat
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from engine.fundamental_forensics.metric_registry import (
    ConceptAlias,
    ImmutableRule,
    MappingRule,
    load_core_metric_registry,
)
import engine.fundamental_forensics.query as query_module
from engine.fundamental_forensics.query import (
    BitemporalMetricQueryEngine,
    BitemporalPolicy,
    CellProvenance,
    CellState,
    EvaluationPolicy,
    HARD_MAX_RECEIPT_NODES,
    MetricCell,
    MetricMatrix,
    PeriodRequest,
    ProvenanceKind,
    QueryBounds,
    QueryBoundsError,
    QueryEntity,
    QueryPolicy,
    QueryValidationError,
    UnsupportedConceptError,
    UnsupportedMetricError,
)
from engine.fundamental_forensics.periods import PeriodKind
from engine.fundamental_forensics.raw_ledger import (
    FactContext,
    FactEventType,
    FactUnit,
    RawFactLedger,
    SourceIdentity,
    make_raw_fact,
)


ROOT = Path(__file__).resolve().parents[1]
ENTITY_A = "0000000001"
ENTITY_B = "0000000002"
PERIOD = PeriodRequest.duration("2025-01-01", "2025-12-31", label="FY2025")


def _body(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _fact(
    *,
    entity_id: str = ENTITY_A,
    concept: str = "RevenueFromContractWithCustomerExcludingAssessedTax",
    value: str | None = "100",
    accession: str = "0000000001-26-000001",
    document_id: str = "fixture-10k.htm",
    accepted_at: str = "2026-08-02T01:00:00Z",
    recorded_at: str = "2026-08-02T02:00:00Z",
    event_type: FactEventType = FactEventType.FILED,
    revision_of: str | None = None,
    source_span: tuple[int, int] = (0, 8),
    unit: FactUnit | None = None,
    context: FactContext | None = None,
    is_nil: bool = False,
    mapping_available_at: str | None = None,
    computed_at: str | None = None,
    published_at: str | None = None,
    dimensions_known: bool = True,
    decimals: str | None = None,
    precision: str | None = None,
):
    return make_raw_fact(
        source=SourceIdentity(
            source="sec-edgar",
            entity_id=entity_id,
            accession=accession,
            document_id=document_id,
            body_sha256=_body(f"{entity_id}:{accession}:{document_id}"),
            source_url=f"https://www.sec.gov/Archives/{accession}",
        ),
        concept_qname=f"us-gaap:{concept}",
        context=context
        or FactContext(
            context_id=f"ctx-{entity_id}",
            entity_scheme="http://www.sec.gov/CIK",
            entity_identifier=entity_id,
            start="2025-01-01",
            end="2025-12-31",
        ),
        unit=unit or FactUnit("USD", ["iso4217:USD"]),
        raw_token=None if is_nil else value,
        parsed_value=None if is_nil else value,
        is_nil=is_nil,
        dimensions_known=dimensions_known,
        decimals=decimals,
        precision=precision,
        source_span=source_span,
        accepted_at=accepted_at,
        recorded_at=recorded_at,
        mapping_available_at=mapping_available_at,
        computed_at=computed_at,
        published_at=published_at,
        event_type=event_type,
        revision_of=revision_of,
    )


def _engine(*facts, bounds: QueryBounds | None = None, registry=None, **kwargs):
    entities = kwargs.pop("entities", {"AAA": ENTITY_A, "BBB": ENTITY_B})
    if "filing_metadata" not in kwargs:
        kwargs["filing_metadata"] = {
            fact.occurrence_id: {
                "accession": fact.source.accession,
                "document_id": fact.source.document_id,
                "source_body_sha256": fact.source.body_sha256,
                "available_at": fact.recorded_at,
                "form": "10-K",
            }
            for fact in facts
        }
    return BitemporalMetricQueryEngine(
        RawFactLedger(tuple(facts)),
        registry or load_core_metric_registry(ROOT),
        entities=entities,
        bounds=bounds,
        **kwargs,
    )


def _policy(
    *,
    source: str = "2026-08-05T00:00:00Z",
    recorded: str = "2026-08-05T00:00:00Z",
    selection: BitemporalPolicy = BitemporalPolicy.LATEST_KNOWN_AS_OF,
) -> QueryPolicy:
    return QueryPolicy(source_snapshot_at=source, recorded_at=recorded, selection=selection)


def _replace_contract(registry, metric_id: str, **changes):
    return replace(
        registry,
        contracts=tuple(
            replace(contract, **changes) if contract.metric_id == metric_id else contract
            for contract in registry.contracts
        ),
    )


def test_policy_rejects_missing_or_naive_mandatory_cutoffs() -> None:
    assert QueryPolicy(
        source_snapshot_at="2026-08-02T00:00:00Z",
        recorded_at="2026-08-02T00:00:00Z",
        selection="latest-known-as-of",
    ).selection is BitemporalPolicy.LATEST_KNOWN_AS_OF
    with pytest.raises(QueryValidationError, match="source_snapshot_at is required"):
        QueryPolicy(source_snapshot_at=None, recorded_at="2026-08-02T00:00:00Z")
    with pytest.raises(QueryValidationError, match="recorded_at is required"):
        QueryPolicy(source_snapshot_at="2026-08-02T00:00:00Z", recorded_at=None)
    with pytest.raises(QueryValidationError, match="timezone"):
        QueryPolicy(source_snapshot_at="2026-08-02T00:00:00", recorded_at="2026-08-02T00:00:00Z")


def test_as_reported_latest_known_and_latest_restated_are_cutoff_safe() -> None:
    original = _fact(value="100", accepted_at="2026-08-02T01:00:00Z", recorded_at="2026-08-02T02:00:00Z")
    restated = _fact(
        value="110",
        accession="0000000001-26-000002",
        document_id="fixture-10ka.htm",
        accepted_at="2026-08-03T01:00:00Z",
        recorded_at="2026-08-04T02:00:00Z",
        event_type=FactEventType.RESTATEMENT,
        revision_of=original.occurrence_id,
    )
    engine = _engine(original, restated)

    source_before_restatement = engine.query_cell(
        "AAA",
        "revenue",
        PERIOD,
        _policy(source="2026-08-02T23:59:59Z", recorded="2026-08-05T00:00:00Z"),
    )
    system_before_restatement = engine.query_cell(
        "AAA",
        "revenue",
        PERIOD,
        _policy(source="2026-08-05T00:00:00Z", recorded="2026-08-03T00:00:00Z"),
    )
    latest = engine.query_cell("AAA", "revenue", PERIOD, _policy())
    as_reported = engine.query_cell(
        "AAA",
        "revenue",
        PERIOD,
        _policy(selection=BitemporalPolicy.AS_REPORTED),
    )
    latest_restated = engine.query_cell(
        "AAA",
        "revenue",
        PERIOD,
        _policy(selection=BitemporalPolicy.LATEST_RESTATED),
    )

    # The future source event cannot leak merely because the system cutoff is later.
    assert source_before_restatement.state is CellState.VALUE
    assert source_before_restatement.value == 100
    # Nor can a source-known restatement leak before its system recording readiness.
    assert system_before_restatement.state is CellState.VALUE
    assert system_before_restatement.value == 100
    assert latest.value == latest_restated.value == 110
    assert as_reported.value == 100
    assert latest.provenance.accession == restated.source.accession
    assert as_reported.provenance.accession == original.source.accession


def test_system_cutoff_gates_mapping_compute_and_publication_clocks() -> None:
    fact = _fact(
        mapping_available_at="2026-08-03T01:00:00Z",
        computed_at="2026-08-04T01:00:00Z",
        published_at="2026-08-05T01:00:00Z",
    )
    engine = _engine(fact)
    before_publish = engine.query_cell(
        "AAA",
        "revenue",
        PERIOD,
        _policy(source="2026-08-06T00:00:00Z", recorded="2026-08-04T12:00:00Z"),
    )
    after_publish = engine.query_cell(
        "AAA",
        "revenue",
        PERIOD,
        _policy(source="2026-08-06T00:00:00Z", recorded="2026-08-06T00:00:00Z"),
    )
    assert before_publish.state is CellState.MISSING
    assert before_publish.reason == (
        "missing_standard_fact: no governed concept alias supplied an exact eligible source interval"
    )
    assert before_publish.provenance.source_occurrence_ids == ()
    assert before_publish.provenance.accepted_at is None
    assert before_publish.provenance.system_ready_at is None
    assert after_publish.state is CellState.VALUE
    assert after_publish.provenance.published_at == datetime(2026, 8, 5, 1, tzinfo=timezone.utc)


def test_revision_parent_must_be_available_under_both_clocks() -> None:
    # The source-time order is valid, but the original was retained later than
    # the child.  The query plane must not select a revision before every
    # lineage parent was system-available.
    original = _fact(
        value="100",
        accepted_at="2026-08-02T01:00:00Z",
        recorded_at="2026-08-04T02:00:00Z",
    )
    restated = _fact(
        value="110",
        accession="0000000001-26-000003",
        document_id="fixture-10ka.htm",
        accepted_at="2026-08-03T01:00:00Z",
        recorded_at="2026-08-03T02:00:00Z",
        event_type=FactEventType.RESTATEMENT,
        revision_of=original.occurrence_id,
    )
    engine = _engine(original, restated)
    # Parent is only recorded after this point; no source group is eligible.
    before_parent = engine.query_cell(
        "AAA",
        "revenue",
        PERIOD,
        _policy(source="2026-08-04T00:00:00Z", recorded="2026-08-03T12:00:00Z"),
    )
    assert before_parent.state is CellState.MISSING
    assert before_parent.reason == (
        "missing_standard_fact: no governed concept alias supplied an exact eligible source interval"
    )
    assert before_parent.provenance.source_occurrence_ids == ()
    assert before_parent.provenance.accepted_at is None
    assert before_parent.provenance.system_ready_at is None


def test_as_reported_uses_lineage_root_when_source_clocks_tie() -> None:
    original = _fact(value="100")
    amendment = _fact(
        value="105",
        accession="0000000001-26-000007",
        document_id="fixture-10ka.htm",
        event_type=FactEventType.AMENDMENT,
        revision_of=original.occurrence_id,
    )
    engine = _engine(original, amendment)
    as_reported = engine.query_cell(
        "AAA", "revenue", PERIOD, _policy(selection=BitemporalPolicy.AS_REPORTED)
    )
    latest = engine.query_cell("AAA", "revenue", PERIOD, _policy())

    assert as_reported.value == 100
    assert latest.value == 105


def test_conflicting_duplicates_fail_closed_and_withdrawn_vintage_is_missing() -> None:
    first = _fact(value="100", source_span=(0, 3))
    conflict = _fact(value="999", source_span=(20, 23))
    conflict_cell = _engine(first, conflict).query_cell("AAA", "revenue", PERIOD, _policy())
    assert conflict_cell.state is CellState.NOT_EVALUABLE
    assert "conflicting duplicate" in (conflict_cell.reason or "")

    original = _fact(value="100")
    amended = _fact(
        value="105",
        accession="0000000001-26-000004",
        document_id="fixture-10ka.htm",
        accepted_at="2026-08-03T01:00:00Z",
        recorded_at="2026-08-03T02:00:00Z",
        event_type=FactEventType.AMENDMENT,
        revision_of=original.occurrence_id,
    )
    withdrawn = _fact(
        value=None,
        accession="0000000001-26-000005",
        document_id="fixture-10ka.htm",
        accepted_at="2026-08-04T01:00:00Z",
        recorded_at="2026-08-04T02:00:00Z",
        event_type=FactEventType.WITHDRAWN,
        revision_of=amended.occurrence_id,
        is_nil=True,
    )
    amended_cell = _engine(original, amended).query_cell(
        "AAA",
        "revenue",
        PERIOD,
        _policy(source="2026-08-03T12:00:00Z", recorded="2026-08-03T12:00:00Z"),
    )
    withdrawn_cell = _engine(original, amended, withdrawn).query_cell("AAA", "revenue", PERIOD, _policy())
    assert amended_cell.state is CellState.VALUE
    assert amended_cell.value == 105
    assert withdrawn_cell.state is CellState.MISSING
    assert "withdrawn" in (withdrawn_cell.reason or "")


def test_governed_formula_propagates_dependency_clocks_and_receipts() -> None:
    revenue = _fact(
        concept="RevenueFromContractWithCustomerExcludingAssessedTax",
        value="100",
        accepted_at="2026-08-02T01:00:00Z",
        recorded_at="2026-08-02T02:00:00Z",
    )
    gross_profit = _fact(
        concept="GrossProfit",
        value="40",
        accepted_at="2026-08-02T03:00:00Z",
        recorded_at="2026-08-02T04:00:00Z",
    )
    cell = _engine(revenue, gross_profit).query_cell("AAA", "gross_margin", PERIOD, _policy())

    assert cell.state is CellState.VALUE
    assert cell.value == Decimal("0.4")
    assert cell.unit == "ratio"
    assert cell.provenance.formula_rule_id == "formula.gross_margin/v1"
    assert cell.provenance.formula_digest
    assert set(cell.provenance.mapping_rule_ids) == {
        "mapping.gross_profit/v1",
        "mapping.revenue/v1",
    }
    assert cell.provenance.mapping_digests
    assert cell.provenance.kind is ProvenanceKind.FORMULA
    assert (
        cell.provenance.evaluation_policy
        is EvaluationPolicy.ON_DEMAND_CUTOFF_PROJECTION
    )
    assert cell.provenance.mapping_available_at is None
    assert cell.provenance.governance_available_at == datetime(2026, 8, 2, tzinfo=timezone.utc)
    assert cell.provenance.accepted_at is None
    assert cell.provenance.recorded_at is None
    assert cell.provenance.computed_at is None
    assert cell.provenance.published_at is None
    dependency_by_id = {node.cell_id: node for node in cell.dependency_nodes}
    direct_dependencies = tuple(
        dependency_by_id[cell_id]
        for cell_id in cell.provenance.dependency_cell_ids
    )
    assert len(direct_dependencies) == 2
    # The governed formula definition is the authority for pointer order, not
    # the canonical cell-ID ordering used by the flat node table.
    assert tuple(item.metric_id for item in direct_dependencies) == (
        "gross_profit",
        "revenue",
    )
    assert {
        item.provenance.accepted_at for item in direct_dependencies
    } == {
        datetime(2026, 8, 2, 1, tzinfo=timezone.utc),
        datetime(2026, 8, 2, 3, tzinfo=timezone.utc),
    }
    receipt = cell.to_dict()
    assert receipt["root_cell_id"] == cell.cell_id
    assert len(receipt["nodes"]) == 3
    assert all("dependency_receipts" not in item["provenance"] for item in receipt["nodes"])
    assert MetricCell.from_dict(receipt).to_dict() == receipt


def test_accession_metadata_adapter_supplies_filed_date_without_backdating_acceptance() -> None:
    fact = _fact(
        document_id="opaque-filing-body.htm",
        mapping_available_at="2026-08-02T03:00:00Z",
    )
    cell = _engine(
        fact,
        filing_metadata={
            fact.source.accession: {
                "form": "10-K",
                "filed_at": "2026-08-01",
                "available_at": "2026-08-02T03:00:00Z",
            }
        },
    ).query_cell("AAA", "revenue", PERIOD, _policy())

    assert cell.state is CellState.VALUE
    assert cell.provenance.form == "10-K"
    assert cell.provenance.filed_at and cell.provenance.filed_at.isoformat() == "2026-08-01"
    assert cell.provenance.accepted_at == datetime(2026, 8, 2, 1, tzinfo=timezone.utc)
    assert cell.provenance.mapping_available_at == datetime(2026, 8, 2, 3, tzinfo=timezone.utc)
    assert cell.provenance.governance_available_at == datetime(2026, 8, 2, tzinfo=timezone.utc)


def test_period_normalization_and_ending_instant_formula_alignment() -> None:
    revenue = _fact(value="100")
    receivable = _fact(
        concept="AccountsReceivableNetCurrent",
        value="25",
        context=FactContext(
            context_id="instant",
            entity_scheme="http://www.sec.gov/CIK",
            entity_identifier=ENTITY_A,
            instant="2025-12-31",
        ),
    )
    cell = _engine(revenue, receivable).query_cell("AAA", "receivables_to_revenue", PERIOD, _policy())
    assert cell.state is CellState.VALUE
    assert cell.value == Decimal("0.25")
    assert cell.provenance.formula_rule_id == "formula.receivables_to_revenue/v1"


def test_formula_division_by_zero_is_not_evaluable_not_a_numeric_zero() -> None:
    instant = PeriodRequest.instant("2025-12-31", fiscal_year=2025, fiscal_quarter=4)
    assets = _fact(
        concept="AssetsCurrent",
        value="100",
        context=FactContext(
            context_id="assets-instant",
            entity_scheme="http://www.sec.gov/CIK",
            entity_identifier=ENTITY_A,
            instant="2025-12-31",
        ),
    )
    liabilities = _fact(
        concept="LiabilitiesCurrent",
        value="0",
        context=FactContext(
            context_id="liabilities-instant",
            entity_scheme="http://www.sec.gov/CIK",
            entity_identifier=ENTITY_A,
            instant="2025-12-31",
        ),
    )
    cell = _engine(assets, liabilities).query_cell("AAA", "current_ratio", instant, _policy())
    assert cell.state is CellState.NOT_EVALUABLE
    assert cell.value is None
    assert cell.reason == "division_by_zero"


def test_cross_company_matrix_export_is_deterministic_and_receipt_complete() -> None:
    left = _fact(entity_id=ENTITY_A, value="100")
    right = _fact(entity_id=ENTITY_B, value="200")
    matrix = _engine(left, right).query_matrix(
        tickers=("BBB", "AAA"),
        metrics=("revenue",),
        periods=(PERIOD,),
        policy=_policy(),
    )
    json_one, json_two = matrix.export_json(), matrix.export_json()
    csv_one, csv_two = matrix.export_csv(), matrix.export_csv()

    assert [cell.ticker for cell in matrix.cells] == ["AAA", "BBB"]
    assert [cell.value for cell in matrix.cells] == [100, 200]
    assert json_one.payload == json_two.payload and json_one.sha256 == json_two.sha256
    assert csv_one.payload == csv_two.payload and csv_one.sha256 == csv_two.sha256
    assert matrix.query_hash in json_one.payload.decode("utf-8")
    assert csv_one.payload.decode("utf-8").startswith(
        "query_hash,receipt_authority,proof_scope,selection_proof,governance_bundle_id,root_cell_id,"
    )
    assert MetricMatrix.from_dict(json.loads(json_one.payload)).query_hash == matrix.query_hash


def test_strict_bounds_and_unsupported_metric_or_concept_fail_safely() -> None:
    engine = _engine(_fact(), _fact(entity_id=ENTITY_B), bounds=QueryBounds(max_tickers=1))
    with pytest.raises(QueryBoundsError, match="max_tickers"):
        engine.query_matrix(
            tickers=("AAA", "BBB"),
            metrics=("revenue",),
            periods=(PERIOD,),
            policy=_policy(),
        )
    with pytest.raises(UnsupportedMetricError, match="unsupported metric"):
        engine.query_cell("AAA", "issuer_extension_metric", PERIOD, _policy())
    with pytest.raises(UnsupportedConceptError, match="unsupported"):
        engine.query_concept("issuer:UnauditedMagicMetric", _policy())
    with pytest.raises(QueryBoundsError, match="hard safety"):
        QueryBounds(max_periods=33)


def test_ungoverned_concept_cannot_be_used_as_a_fallback() -> None:
    ungoverned = _fact(concept="IssuerSpecificRevenue", value="777")
    cell = _engine(ungoverned).query_cell("AAA", "revenue", PERIOD, _policy())
    assert cell.state is CellState.MISSING
    assert "governed concept alias" in (cell.reason or "")


def test_temporally_ineligible_raw_facts_are_opaque_before_all_structure_checks() -> None:
    future_unknown_dimension = _fact(
        value="100",
        accepted_at="2026-08-06T01:00:00Z",
        recorded_at="2026-08-06T02:00:00Z",
        dimensions_known=False,
    )
    before = _engine(future_unknown_dimension).query_cell(
        "AAA", "revenue", PERIOD, _policy(source="2026-08-05T00:00:00Z", recorded="2026-08-05T00:00:00Z")
    )
    after = _engine(future_unknown_dimension).query_cell(
        "AAA", "revenue", PERIOD, _policy(source="2026-08-07T00:00:00Z", recorded="2026-08-07T00:00:00Z")
    )

    assert before.state is CellState.MISSING
    assert before.reason == (
        "missing_standard_fact: no governed concept alias supplied an exact eligible source interval"
    )
    assert before.provenance.source_occurrence_ids == ()
    assert before.provenance.accepted_at is None
    assert before.provenance.system_ready_at is None
    assert future_unknown_dimension.occurrence_id not in before.to_dict().__repr__()
    assert after.state is CellState.NOT_EVALUABLE
    assert after.reason and after.reason.startswith("unknown_dimension_scope")
    assert after.provenance.source_ready_at == future_unknown_dimension.accepted_at
    assert after.provenance.system_ready_at == future_unknown_dimension.recorded_at
    assert after.provenance.source_occurrence_ids == (
        future_unknown_dimension.occurrence_id,
    )
    assert after.provenance.mapping_rule_id == "mapping.revenue/v1"
    assert after.provenance.mapping_digest


def test_future_mapping_is_append_only_and_future_formula_stays_opaque() -> None:
    registry = load_core_metric_registry(ROOT)
    revenue = registry.metric("revenue")
    base_mapping = revenue.mappings[0]
    future_rule = replace(
        base_mapping.rule,
        rule_id="mapping.revenue.future/v1",
        available_at=datetime(2026, 8, 7, tzinfo=timezone.utc),
    )
    future_mapping_registry = _replace_contract(
        registry,
        "revenue",
        # New governance is append-only.  Replacing the visible mapping would
        # make an old formula invalid rather than demonstrate cutoff opacity.
        mappings=revenue.mappings + (replace(base_mapping, rule=future_rule),),
    )
    fact = _fact()
    direct = _engine(fact, registry=future_mapping_registry).query_cell(
        "AAA", "revenue", PERIOD, _policy()
    )

    assert direct.state is CellState.VALUE
    assert direct.provenance.mapping_rule_id == "mapping.revenue/v1"
    assert direct.provenance.mapping_digest
    assert direct.provenance.source_occurrence_ids == (fact.occurrence_id,)
    assert direct.provenance.concept_qname == fact.concept_qname

    # The visible mapping set is projected before request semantics, but an
    # invalid period never claims a selected alias or raw occurrence.
    direct_invalid_period = _engine(fact, registry=future_mapping_registry).query_cell(
        "AAA", "revenue", PeriodRequest.instant("2025-12-31"), _policy()
    )
    assert direct_invalid_period.state is CellState.NOT_EVALUABLE
    assert direct_invalid_period.reason == (
        "outside_period_constraint: metric requires duration, requested instant"
    )
    assert direct_invalid_period.provenance.mapping_rule_id is None

    gross_margin = registry.metric("gross_margin")
    assert gross_margin.formula is not None
    future_formula = replace(
        gross_margin.formula,
        rule=replace(
            gross_margin.formula.rule,
            rule_id="formula.gross_margin.future/v1",
            available_at=datetime(2026, 8, 7, tzinfo=timezone.utc),
        ),
    )
    future_formula_registry = _replace_contract(registry, "gross_margin", formula=future_formula)
    revenue_fact = _fact(value="100")
    gross_profit = _fact(concept="GrossProfit", value="40")
    formula = _engine(revenue_fact, gross_profit, registry=future_formula_registry).query_cell(
        "AAA", "gross_margin", PERIOD, _policy()
    )

    assert formula.state is CellState.MISSING
    assert formula.reason == "governance unavailable at recorded_at cutoff"
    assert formula.provenance.formula_rule_id is None
    assert formula.provenance.formula_digest is None
    assert formula.provenance.dependency_cell_ids == ()
    assert formula.provenance.source_occurrence_ids == ()


def test_future_high_priority_alias_does_not_suppress_visible_governed_fallback() -> None:
    registry = load_core_metric_registry(ROOT)
    revenue = registry.metric("revenue")
    base_mapping = revenue.mappings[0]
    primary, _, fallback = base_mapping.taxonomy_concept_aliases
    future_mapping = MappingRule(
        metric_id="revenue",
        rule=ImmutableRule(
            rule_id="mapping.revenue.primary_future/v1",
            version="1.0.0",
            available_at=datetime(2026, 8, 7, tzinfo=timezone.utc),
            confidence="A",
        ),
        taxonomy_concept_aliases=(primary,),
    )
    fallback_mapping = MappingRule(
        metric_id="revenue",
        rule=ImmutableRule(
            rule_id="mapping.revenue.fallback_visible/v1",
            version="1.0.0",
            available_at=datetime(2026, 8, 2, tzinfo=timezone.utc),
            confidence="A",
        ),
        taxonomy_concept_aliases=(fallback,),
    )
    custom = _replace_contract(
        registry, "revenue", mappings=(future_mapping, fallback_mapping)
    )
    cell = _engine(_fact(concept="Revenues", value="77"), registry=custom).query_cell(
        "AAA", "revenue", PERIOD, _policy()
    )

    assert cell.state is CellState.VALUE
    assert cell.value == Decimal("77")
    assert cell.provenance.mapping_rule_id == "mapping.revenue.fallback_visible/v1"
    assert cell.provenance.mapping_digest  # Exact visible rule digest, independent of future content.


def test_mixed_segmented_and_consolidated_inventory_selects_safe_consolidated_fact() -> None:
    segmented = _fact(
        value="999",
        source_span=(20, 30),
        context=FactContext(
            context_id="segmented",
            entity_scheme="http://www.sec.gov/CIK",
            entity_identifier=ENTITY_A,
            start="2025-01-01",
            end="2025-12-31",
            explicit_dimensions={"us-gaap:StatementBusinessSegmentsAxis": "us-gaap:EuropeSegmentMember"},
        ),
    )
    consolidated = _fact(value="100", source_span=(0, 8))
    cell = _engine(segmented, consolidated).query_cell("AAA", "revenue", PERIOD, _policy())

    assert cell.state is CellState.VALUE
    assert cell.value == Decimal("100")
    assert cell.provenance.source_occurrence_ids == (consolidated.occurrence_id,)


def test_equal_precedence_sibling_revisions_and_withdrawals_fail_closed_without_hash_choice() -> None:
    root = _fact(value="100")
    left = _fact(
        value="110",
        accession="0000000001-26-000101",
        document_id="left-10ka.htm",
        accepted_at="2026-08-03T01:00:00Z",
        recorded_at="2026-08-03T02:00:00Z",
        event_type=FactEventType.AMENDMENT,
        revision_of=root.occurrence_id,
    )
    right = _fact(
        value="120",
        accession="0000000001-26-000102",
        document_id="right-10ka.htm",
        accepted_at="2026-08-03T01:00:00Z",
        recorded_at="2026-08-03T02:00:00Z",
        event_type=FactEventType.RESTATEMENT,
        revision_of=root.occurrence_id,
    )
    siblings = _engine(root, left, right).query_cell("AAA", "revenue", PERIOD, _policy())
    assert siblings.state is CellState.NOT_EVALUABLE
    assert siblings.reason == "ambiguous equal-precedence source vintages cannot be selected"
    assert set(siblings.provenance.source_occurrence_ids) == {
        root.occurrence_id,
        left.occurrence_id,
        right.occurrence_id,
    }

    withdrawn = _fact(
        value=None,
        is_nil=True,
        accession="0000000001-26-000103",
        document_id="withdrawn-10ka.htm",
        accepted_at="2026-08-03T01:00:00Z",
        recorded_at="2026-08-03T02:00:00Z",
        event_type=FactEventType.WITHDRAWN,
        revision_of=root.occurrence_id,
    )
    withdrawal_sibling = _engine(root, left, withdrawn).query_cell(
        "AAA", "revenue", PERIOD, _policy()
    )
    assert withdrawal_sibling.state is CellState.NOT_EVALUABLE
    assert withdrawal_sibling.reason == "ambiguous equal-precedence source vintages cannot be selected"


def test_unlinked_filed_groups_never_become_a_timestamp_selected_revision() -> None:
    original = _fact(value="100")
    unlinked_later = _fact(
        value="7",
        accession="0000000001-26-000104",
        document_id="later-10k.htm",
        accepted_at="2026-08-03T01:00:00Z",
        recorded_at="2026-08-03T02:00:00Z",
    )
    cell = _engine(original, unlinked_later).query_cell("AAA", "revenue", PERIOD, _policy())

    assert cell.state is CellState.NOT_EVALUABLE
    assert cell.reason == "unlinked source vintages require an explicit typed revision lineage"


def test_latest_restated_is_distinct_from_latest_known_and_ignores_parser_corrections() -> None:
    original = _fact(value="100")
    restated = _fact(
        value="110",
        accession="0000000001-26-000105",
        document_id="restated-10ka.htm",
        accepted_at="2026-08-03T01:00:00Z",
        recorded_at="2026-08-03T02:00:00Z",
        event_type=FactEventType.RESTATEMENT,
        revision_of=original.occurrence_id,
    )
    parser_correction = _fact(
        value="120",
        accession="0000000001-26-000106",
        document_id="parser-correction-10ka.htm",
        accepted_at="2026-08-04T01:00:00Z",
        recorded_at="2026-08-04T02:00:00Z",
        event_type=FactEventType.PARSER_CORRECTION,
        revision_of=restated.occurrence_id,
    )
    engine = _engine(original, restated, parser_correction)
    latest = engine.query_cell("AAA", "revenue", PERIOD, _policy())
    restated_only = engine.query_cell(
        "AAA", "revenue", PERIOD, _policy(selection=BitemporalPolicy.LATEST_RESTATED)
    )
    no_reported_revision = _engine(original).query_cell(
        "AAA", "revenue", PERIOD, _policy(selection=BitemporalPolicy.LATEST_RESTATED)
    )

    assert latest.value == Decimal("120")
    assert restated_only.value == Decimal("110")
    assert no_reported_revision.state is CellState.MISSING
    assert no_reported_revision.reason == "no eligible explicitly typed reported revision vintage"


def test_formula_requires_a_shared_attested_revision_basis() -> None:
    revenue = _fact(value="100")
    gross_profit = _fact(concept="GrossProfit", value="40")
    gross_profit_restatement = _fact(
        concept="GrossProfit",
        value="60",
        accession="0000000001-26-000107",
        document_id="gross-profit-10ka.htm",
        accepted_at="2026-08-03T01:00:00Z",
        recorded_at="2026-08-03T02:00:00Z",
        event_type=FactEventType.RESTATEMENT,
        revision_of=gross_profit.occurrence_id,
    )
    mixed = _engine(revenue, gross_profit, gross_profit_restatement).query_cell(
        "AAA", "gross_margin", PERIOD, _policy()
    )

    assert mixed.state is CellState.NOT_EVALUABLE
    assert mixed.reason and mixed.reason.startswith("incompatible_revision_basis")


def test_formula_decimal_context_is_ambient_independent_and_overflow_is_not_evaluable() -> None:
    revenue = _fact(value="3")
    gross_profit = _fact(concept="GrossProfit", value="1")
    engine = _engine(revenue, gross_profit)
    with localcontext() as context:
        context.prec = 6
        low_precision = engine.query_cell("AAA", "gross_margin", PERIOD, _policy())
    with localcontext() as context:
        context.prec = 80
        high_precision = engine.query_cell("AAA", "gross_margin", PERIOD, _policy())

    assert low_precision.state is high_precision.state is CellState.VALUE
    assert low_precision.value == high_precision.value == Decimal("0.3333333333333333333333333333333333")
    assert low_precision.cell_id == high_precision.cell_id

    overflow = _engine(
        _fact(value="1E-6143"),
        _fact(concept="GrossProfit", value="1E+6144"),
    ).query_cell("AAA", "gross_margin", PERIOD, _policy())
    assert overflow.state is CellState.NOT_EVALUABLE
    assert overflow.reason == "formula numeric result violates the fixed decimal contract"


def test_receipts_and_cells_reject_forged_identity_future_clocks_and_matrix_mismatch() -> None:
    policy = _policy()
    good = _engine(_fact(value="1")).query_cell("AAA", "revenue", PERIOD, policy)
    base_provenance = good.provenance
    with pytest.raises(QueryValidationError, match="cell_id"):
        MetricCell(
            governance_bundle=good.governance_bundle,
            ticker="AAA",
            entity_id=ENTITY_A,
            metric_id="revenue",
            period=PERIOD,
            state=CellState.VALUE,
            value=Decimal("1"),
            unit="USD",
            provenance=base_provenance,
            cell_id="metric_cell_forged",
        )
    with pytest.raises(QueryValidationError, match="binary float"):
        MetricCell(
            governance_bundle=good.governance_bundle,
            ticker="AAA",
            entity_id=ENTITY_A,
            metric_id="revenue",
            period=PERIOD,
            state=CellState.VALUE,
            value=0.1,
            unit="USD",
            provenance=base_provenance,
        )
    with pytest.raises(QueryValidationError, match="exceeds source_snapshot_at"):
        CellProvenance(
            kind=ProvenanceKind.OPAQUE,
            evaluation_policy=None,
            policy=policy.selection,
            source_snapshot_at=policy.source_snapshot_at,
            recorded_cutoff_at=policy.recorded_at,
            accepted_at="2026-08-06T00:00:00Z",
        )
    with pytest.raises(QueryValidationError, match="opaque provenance cannot expose"):
        CellProvenance(
            kind=ProvenanceKind.OPAQUE,
            evaluation_policy=None,
            policy=policy.selection,
            source_snapshot_at=policy.source_snapshot_at,
            recorded_cutoff_at=policy.recorded_at,
            source="invented-source-detail",
            reason="opaque result",
        )
    with pytest.raises(QueryValidationError, match="opaque provenance cannot expose"):
        CellProvenance(
            kind=ProvenanceKind.OPAQUE,
            evaluation_policy=None,
            policy=policy.selection,
            source_snapshot_at=policy.source_snapshot_at,
            recorded_cutoff_at=policy.recorded_at,
            source_entity_id=ENTITY_A,
            reason="opaque result",
        )
    with pytest.raises(QueryValidationError, match="direct source entity does not match"):
        replace(
            good,
            provenance=replace(base_provenance, source_entity_id=ENTITY_B),
            cell_id=None,
        )
    with pytest.raises(QueryValidationError, match="direct provenance is incomplete"):
        replace(
            base_provenance,
            mapping_rule_id=None,
            mapping_rule_version=None,
            mapping_digest=None,
            mapping_rule_ids=(),
            mapping_rule_versions=(),
            mapping_digests=(),
        )
    with pytest.raises(QueryValidationError, match="membership"):
        other_good = _engine(
            _fact(entity_id=ENTITY_B), entities={"AAA": ENTITY_B}
        ).query_cell("AAA", "revenue", PERIOD, policy)
        MetricMatrix(
            governance_bundle=good.governance_bundle,
            policy=policy,
            entities=(QueryEntity("AAA", ENTITY_A),),
            metric_ids=("revenue",),
            periods=(PERIOD,),
            cells=(other_good,),
        )
    with pytest.raises(QueryValidationError, match="unique entity_ids"):
        MetricMatrix(
            governance_bundle=good.governance_bundle,
            policy=policy,
            entities=(QueryEntity("AAA", ENTITY_A), QueryEntity("BBB", ENTITY_A)),
            metric_ids=("revenue",),
            periods=(PERIOD,),
            cells=(),
        )


def test_direct_value_receipts_reject_withdrawn_and_policy_inconsistent_raw_evidence() -> None:
    good = _engine(_fact(value="1")).query_cell("AAA", "revenue", PERIOD, _policy())
    selected = good.provenance.selected_raw_fact
    assert selected is not None

    withdrawn = _fact(
        value=None,
        is_nil=True,
        event_type=FactEventType.WITHDRAWN,
        revision_of=selected.occurrence_id,
    )
    withdrawn_provenance = replace(
        good.provenance,
        selected_raw_fact=withdrawn,
        source_occurrence_ids=(withdrawn.occurrence_id,),
    )
    with pytest.raises(QueryValidationError, match="cannot select a withdrawn raw fact"):
        replace(good, provenance=withdrawn_provenance, cell_id=None)

    # The same semantic guard must run when a receipt arrives over the wire,
    # after the forged raw occurrence and node identity are made canonical.
    withdrawn_node = replace(
        good.root_node,
        provenance=withdrawn_provenance,
        cell_id=None,
    )
    forged_wire = good.to_dict()
    forged_wire["root_cell_id"] = withdrawn_node.cell_id
    forged_wire["nodes"] = [withdrawn_node.to_dict()]
    with pytest.raises(QueryValidationError, match="cannot select a withdrawn raw fact"):
        MetricCell.from_dict(forged_wire)

    amendment = _fact(
        value="1",
        event_type=FactEventType.AMENDMENT,
        revision_of=selected.occurrence_id,
    )
    with pytest.raises(QueryValidationError, match="as_reported value must select"):
        replace(
            good,
            provenance=replace(
                good.provenance,
                policy=BitemporalPolicy.AS_REPORTED,
                selected_raw_fact=amendment,
                source_occurrence_ids=(amendment.occurrence_id,),
            ),
            cell_id=None,
        )
    with pytest.raises(QueryValidationError, match="latest_restated value must select"):
        replace(
            good,
            provenance=replace(
                good.provenance,
                policy=BitemporalPolicy.LATEST_RESTATED,
            ),
            cell_id=None,
        )


def test_period_rejection_receipts_cannot_invent_source_evidence() -> None:
    engine = _engine(
        _fact(value="100"),
        _fact(concept="GrossProfit", value="40"),
    )
    invalid_period = PeriodRequest.instant("2025-12-31")
    for metric_id in ("revenue", "gross_margin"):
        cell = engine.query_cell("AAA", metric_id, invalid_period, _policy())
        assert cell.state is CellState.NOT_EVALUABLE
        forged_provenance = replace(
            cell.provenance,
            source="invented-source",
            accession="invented-accession",
            document_id="invented-document",
            source_url="https://example.invalid/invented",
            source_body_sha256="1" * 64,
            source_ready_at="2026-08-02T01:00:00Z",
            system_ready_at="2026-08-02T02:00:00Z",
            source_occurrence_ids=(
                ("rawfact_invented",)
                if cell.provenance.kind is ProvenanceKind.DIRECT
                else ()
            ),
        )
        with pytest.raises(
            QueryValidationError,
            match="period rejection provenance must be governance-only",
        ):
            replace(cell, provenance=forged_provenance, cell_id=None)

        forged_node = replace(
            cell.root_node,
            provenance=forged_provenance,
            cell_id=None,
        )
        forged_wire = cell.to_dict()
        forged_wire["root_cell_id"] = forged_node.cell_id
        forged_wire["nodes"] = [forged_node.to_dict()]
        with pytest.raises(
            QueryValidationError,
            match="period rejection provenance must be governance-only",
        ):
            MetricCell.from_dict(forged_wire)


def test_period_rejection_precedes_taxonomy_alias_year_applicability() -> None:
    cell = _engine().query_cell(
        "AAA",
        "revenue",
        PeriodRequest.instant("2030-12-31"),
        _policy(),
    )

    assert cell.state is CellState.NOT_EVALUABLE
    assert cell.reason == (
        "outside_period_constraint: metric requires duration, requested instant"
    )
    assert MetricCell.from_dict(cell.to_dict()).to_dict() == cell.to_dict()


def test_matrix_receipt_projects_future_registry_content_and_csv_escapes_text_only() -> None:
    registry = load_core_metric_registry(ROOT)
    future_contract = replace(
        registry.metric("net_income_loss"),
        metric_id="future_private_metric",
        rule=replace(
            registry.metric("net_income_loss").rule,
            rule_id="metric.future_private_metric/v1",
            available_at=datetime(2026, 8, 7, tzinfo=timezone.utc),
        ),
        mappings=(),
        formula=None,
    )
    registry_with_future_catalog_member = replace(
        registry, contracts=registry.contracts + (future_contract,)
    )
    fact = _fact()
    baseline = _engine(fact, registry=registry).query_matrix(
        tickers=("AAA",), metrics=("revenue",), periods=(PERIOD,), policy=_policy()
    )
    matrix = _engine(fact, registry=registry_with_future_catalog_member).query_matrix(
        tickers=("AAA",), metrics=("revenue",), periods=(PERIOD,), policy=_policy()
    )
    assert matrix.governance_bundle.to_dict() == baseline.governance_bundle.to_dict()
    assert matrix.query_hash == baseline.query_hash
    for metric_id in ("future_private_metric", "truly_unknown_metric"):
        with pytest.raises(UnsupportedMetricError, match="unsupported metric"):
            _engine(fact, registry=registry_with_future_catalog_member).query_cell(
                "AAA", metric_id, PERIOD, _policy()
            )

    policy = _policy()
    escaped_fact = _fact(entity_id="=2+2", accession="@evil", value="-42")
    escaped_matrix = _engine(
        escaped_fact, entities={"AAA": "=2+2"}
    ).query_matrix(
        tickers=("AAA",),
        metrics=("revenue",),
        periods=(PERIOD,),
        policy=policy,
    )
    row = next(csv.DictReader(escaped_matrix.export_csv().payload.decode("utf-8").splitlines()))
    assert row["receipt_authority"] == "json_sidecar_required"
    assert row["entity_id"] == "'=2+2"
    assert row["value"] == "-42"
    assert row["accession"] == "'@evil"


def test_query_bounds_are_checked_before_sequence_materialization_and_engine_uses_period_index() -> None:
    class ExplodingSequence(Sequence[str]):
        def __len__(self) -> int:
            return 2

        def __getitem__(self, index: int) -> str:
            raise AssertionError("oversized input must not be materialized")

    engine = _engine(_fact(), bounds=QueryBounds(max_tickers=1))
    with pytest.raises(QueryBoundsError, match="max_tickers"):
        engine.query_matrix(
            tickers=ExplodingSequence(),
            metrics=("revenue",),
            periods=(PERIOD,),
            policy=_policy(),
        )
    indexed = _engine(
        _fact(),
        _fact(
            entity_id=ENTITY_B,
            accession="0000000002-26-000108",
            document_id="other-10k.htm",
        ),
    )
    assert indexed._events_for_alias(  # type: ignore[attr-defined]  # index contract pin
        QueryEntity("AAA", ENTITY_A),
        indexed.registry.metric("revenue").mappings[0].taxonomy_concept_aliases[0],
        PERIOD,
    ) == (indexed.ledger.events[0],)


def test_cutoff_projection_is_stable_under_unrelated_future_pack_extensions() -> None:
    registry = load_core_metric_registry(ROOT)
    revenue_contract = registry.metric("revenue")
    future_mapping = MappingRule(
        metric_id="revenue",
        rule=ImmutableRule(
            rule_id="mapping.revenue.future_extension/v1",
            version="1.0.0",
            available_at=datetime(2026, 8, 7, tzinfo=timezone.utc),
            confidence="A",
        ),
        taxonomy_concept_aliases=(
            ConceptAlias(
                taxonomy="us-gaap",
                concept="FutureRevenueExtension",
                priority=1,
                taxonomy_version_start=2027,
                taxonomy_version_end=2100,
            ),
        ),
    )
    extended_revenue = replace(
        revenue_contract,
        mappings=revenue_contract.mappings + (future_mapping,),
    )
    gross_margin = registry.metric("gross_margin")
    assert gross_margin.formula is not None
    future_metric_rule = replace(
        gross_margin.rule,
        rule_id="metric.future_ratio/v1",
        available_at=datetime(2026, 8, 7, tzinfo=timezone.utc),
    )
    future_formula = replace(
        gross_margin.formula,
        metric_id="future_ratio",
        rule=replace(
            gross_margin.formula.rule,
            rule_id="formula.future_ratio/v1",
            available_at=datetime(2026, 8, 7, tzinfo=timezone.utc),
        ),
    )
    future_formula_contract = replace(
        gross_margin,
        metric_id="future_ratio",
        rule=future_metric_rule,
        formula=future_formula,
    )
    extended_contracts = tuple(
        extended_revenue if item.metric_id == "revenue" else item
        for item in registry.contracts
    ) + (future_formula_contract,)
    extended_registry = replace(
        registry,
        catalog_version="99.0.0",
        catalog_content_sha256="1" * 64,
        mapping_pack_version="99.0.0",
        mapping_pack_content_sha256="2" * 64,
        formula_pack_version="99.0.0",
        formula_pack_content_sha256="3" * 64,
        contracts=extended_contracts,
    )
    revenue_fact = _fact(value="100")
    gross_profit_fact = _fact(concept="GrossProfit", value="40")
    baseline_engine = _engine(revenue_fact, gross_profit_fact, registry=registry)
    extended_engine = _engine(revenue_fact, gross_profit_fact, registry=extended_registry)

    for metric_id in ("revenue", "gross_margin"):
        baseline = baseline_engine.query_cell("AAA", metric_id, PERIOD, _policy())
        extended = extended_engine.query_cell("AAA", metric_id, PERIOD, _policy())
        assert extended.to_dict() == baseline.to_dict()
        assert extended.cell_id == baseline.cell_id

    baseline_matrix = baseline_engine.query_matrix(
        tickers=("AAA",),
        metrics=("revenue", "gross_margin"),
        periods=(PERIOD,),
        policy=_policy(),
    )
    extended_matrix = extended_engine.query_matrix(
        tickers=("AAA",),
        metrics=("revenue", "gross_margin"),
        periods=(PERIOD,),
        policy=_policy(),
    )
    assert (
        extended_matrix.governance_bundle.to_dict()
        == baseline_matrix.governance_bundle.to_dict()
    )
    assert extended_matrix.query_hash == baseline_matrix.query_hash
    revenue_cell = next(
        item for item in extended_matrix.cells if item.metric_id == "revenue"
    )
    assert revenue_cell.provenance.metric_rule_digest
    assert revenue_cell.provenance.mapping_digest

    with pytest.raises(UnsupportedConceptError, match="unsupported or ambiguous"):
        extended_engine.query_concept("us-gaap:FutureRevenueExtension", _policy())
    with pytest.raises(UnsupportedConceptError, match="unsupported or ambiguous"):
        extended_engine.query_concept("issuer:TrulyUnknownConcept", _policy())
    for metric_id in ("future_ratio", "truly_unknown_metric"):
        with pytest.raises(UnsupportedMetricError, match="unsupported metric"):
            extended_engine.query_cell("AAA", metric_id, PERIOD, _policy())


def test_pre_catalog_cutoff_exposes_no_registry_identity_or_receipt() -> None:
    engine = _engine(_fact())
    before_catalog = _policy(
        source="2026-08-01T00:00:00Z",
        recorded="2026-08-01T00:00:00Z",
    )
    projection = engine._registry_projection(before_catalog)  # type: ignore[attr-defined]

    assert dict(projection.receipt) == {}
    assert projection.catalog_digest is None
    assert projection.mapping_pack_digest is None
    assert projection.formula_pack_digest is None
    assert dict(projection.contracts_by_metric) == {}
    assert dict(projection.contract_digests) == {}
    assert dict(projection.mapping_digests) == {}
    assert dict(projection.formula_digests) == {}
    with pytest.raises(UnsupportedMetricError, match="unsupported metric"):
        engine.query_cell("AAA", "revenue", PERIOD, before_catalog)
    with pytest.raises(UnsupportedConceptError, match="unsupported or ambiguous"):
        engine.query_concept(
            "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
            before_catalog,
        )


def test_equal_priorities_across_distinct_visible_mappings_fail_closed() -> None:
    registry = load_core_metric_registry(ROOT)
    revenue = registry.metric("revenue")
    second_mapping = MappingRule(
        metric_id="revenue",
        rule=ImmutableRule(
            rule_id="mapping.revenue.second_visible/v1",
            version="1.0.0",
            available_at=datetime(2026, 8, 2, tzinfo=timezone.utc),
            confidence="A",
        ),
        taxonomy_concept_aliases=(
            # The governed allowlist remains closed-world even in a conflict
            # fixture; use a known duration/USD concept at the tied priority.
            ConceptAlias("us-gaap", "GrossProfit", 10, 2009, 2026),
        ),
    )
    # A bundle rejects duplicate aliases across all visible contracts.  Keep
    # this fixture minimal so the distinct, known alias is only governed here.
    custom = replace(
        registry,
        contracts=(replace(revenue, mappings=revenue.mappings + (second_mapping,)),),
    )
    cell = _engine(_fact(), registry=custom).query_cell(
        "AAA", "revenue", PERIOD, _policy()
    )

    assert cell.state is CellState.NOT_EVALUABLE
    assert cell.reason == "ambiguous governed alias priorities across visible mapping rules"
    assert cell.provenance.mapping_rule_id is None
    assert set(cell.provenance.mapping_rule_ids) == {
        "mapping.revenue/v1",
        "mapping.revenue.second_visible/v1",
    }
    assert len(cell.provenance.mapping_digests) == 2

    for forged_state, forged_reason in (
        (
            CellState.MISSING,
            "missing_standard_fact: no governed concept alias supplied an exact eligible source interval",
        ),
        (
            CellState.NOT_EVALUABLE,
            "visible source history exceeds the synchronous per-cell bound",
        ),
    ):
        with pytest.raises(
            QueryValidationError,
            match="alias-priority precedence",
        ):
            replace(
                cell,
                state=forged_state,
                reason=forged_reason,
                provenance=replace(cell.provenance, reason=forged_reason),
                cell_id=None,
            )

    restated_cell = _engine(_fact(), registry=custom).query_cell(
        "AAA",
        "revenue",
        PERIOD,
        _policy(selection=BitemporalPolicy.LATEST_RESTATED),
    )
    with pytest.raises(
        QueryValidationError,
        match="alias-priority precedence",
    ):
        replace(
            restated_cell,
            state=CellState.MISSING,
            reason="no eligible explicitly typed reported revision vintage",
            provenance=replace(
                restated_cell.provenance,
                reason="no eligible explicitly typed reported revision vintage",
            ),
            cell_id=None,
        )

    selected_nil = _engine(_fact(value=None, is_nil=True)).query_cell(
        "AAA", "revenue", PERIOD, _policy()
    )
    with pytest.raises(
        QueryValidationError,
        match="alias-priority precedence",
    ):
        replace(
            cell,
            state=CellState.MISSING,
            reason="selected source fact has no numeric value",
            provenance=replace(
                cell.provenance,
                reason="selected source fact has no numeric value",
                mapping_rule_id=selected_nil.provenance.mapping_rule_id,
                mapping_rule_version=selected_nil.provenance.mapping_rule_version,
                mapping_digest=selected_nil.provenance.mapping_digest,
                concept_qname=selected_nil.provenance.concept_qname,
                taxonomy=selected_nil.provenance.taxonomy,
                concept=selected_nil.provenance.concept,
                alias_priority=selected_nil.provenance.alias_priority,
                source_ready_at=selected_nil.provenance.source_ready_at,
                system_ready_at=selected_nil.provenance.system_ready_at,
                source_occurrence_ids=("rawfact_invented",),
            ),
            cell_id=None,
        )


def test_absent_and_cutoff_hidden_metadata_are_receipt_identical() -> None:
    fact = _fact(document_id="marketing-10k.htm")
    no_metadata = _engine(fact, filing_metadata={}).query_cell(
        "AAA", "revenue", PERIOD, _policy()
    )
    hidden_metadata = _engine(
        fact,
        filing_metadata={
            fact.occurrence_id: {
                "accession": fact.source.accession,
                "document_id": fact.source.document_id,
                "source_body_sha256": fact.source.body_sha256,
                "available_at": "2026-08-06T00:00:00Z",
                "form": "10-K",
                "filed_at": "2026-08-01",
            }
        },
    ).query_cell("AAA", "revenue", PERIOD, _policy())

    assert no_metadata.state is CellState.NOT_EVALUABLE
    assert no_metadata.reason == "filing form is unavailable or outside the governed metric contract"
    assert no_metadata.to_dict() == hidden_metadata.to_dict()
    assert no_metadata.cell_id == hidden_metadata.cell_id
    assert no_metadata.provenance.form is None
    assert no_metadata.provenance.filing_metadata_available_at is None
    assert no_metadata.provenance.filing_metadata_content_sha256 is None
    assert no_metadata.provenance.source_body_sha256 == fact.source.body_sha256

    future_fact = _fact(
        accepted_at="2026-08-06T01:00:00Z",
        recorded_at="2026-08-06T02:00:00Z",
    )
    source_hidden_policy = _policy(
        source="2026-08-05T00:00:00Z",
        recorded="2026-08-08T00:00:00Z",
    )
    with_future_source = _engine(future_fact).query_cell(
        "AAA", "revenue", PERIOD, source_hidden_policy
    )
    without_source = _engine().query_cell(
        "AAA", "revenue", PERIOD, source_hidden_policy
    )
    assert with_future_source.to_dict() == without_source.to_dict()
    assert with_future_source.cell_id == without_source.cell_id


def test_visible_metadata_is_frozen_bound_and_clocked_at_engine_construction() -> None:
    fact = _fact(document_id="opaque-document.htm")
    inner = {
        "accession": fact.source.accession,
        "document_id": fact.source.document_id,
        "source_body_sha256": fact.source.body_sha256,
        "available_at": "2026-08-02T03:00:00Z",
        "form": "10-K",
        "filed_at": "2026-08-01",
    }
    supplied = {fact.occurrence_id: inner}
    engine = _engine(fact, filing_metadata=supplied)
    before = engine.query_cell("AAA", "revenue", PERIOD, _policy())

    inner["form"] = "10-Q"
    inner["available_at"] = "2026-08-04T00:00:00Z"
    supplied.clear()
    after = engine.query_cell("AAA", "revenue", PERIOD, _policy())

    assert before.to_dict() == after.to_dict()
    assert before.state is CellState.VALUE
    assert before.provenance.form == "10-K"
    assert before.provenance.source_body_sha256 == fact.source.body_sha256
    assert before.provenance.filing_metadata_available_at == datetime(
        2026, 8, 2, 3, tzinfo=timezone.utc
    )
    assert before.provenance.filing_metadata_content_sha256
    assert before.provenance.system_ready_at == datetime(
        2026, 8, 2, 3, tzinfo=timezone.utc
    )


def test_metadata_rejects_wrong_binding_digest_clock_and_late_resolver() -> None:
    fact = _fact()
    base = {
        "accession": fact.source.accession,
        "document_id": fact.source.document_id,
        "source_body_sha256": fact.source.body_sha256,
        "available_at": fact.recorded_at,
        "form": "10-K",
    }
    with pytest.raises(QueryValidationError, match="binding does not match"):
        _engine(
            fact,
            filing_metadata={
                fact.occurrence_id: {**base, "source_body_sha256": "f" * 64}
            },
        )
    with pytest.raises(QueryValidationError, match="content_sha256 does not match"):
        _engine(
            fact,
            filing_metadata={
                fact.occurrence_id: {**base, "content_sha256": "0" * 64}
            },
        )
    with pytest.raises(QueryValidationError, match="cannot precede source acceptance"):
        _engine(
            fact,
            filing_metadata={
                fact.occurrence_id: {
                    **base,
                    "available_at": "2026-08-02T00:00:00Z",
                }
            },
        )

    class LateResolver:
        def metadata_for_fact(self, _fact_value):
            return base

    with pytest.raises(QueryValidationError, match="construction-time mapping"):
        _engine(fact, filing_metadata=LateResolver())

    good = _engine(fact).query_cell("AAA", "revenue", PERIOD, _policy())
    with pytest.raises(QueryValidationError, match="content_sha256 does not match"):
        replace(good.provenance, filing_metadata_content_sha256="0" * 64)


def test_formula_cell_identity_and_exports_embed_complete_flat_dependency_dag() -> None:
    first_engine = _engine(
        _fact(value="100"),
        _fact(concept="GrossProfit", value="40"),
    )
    second_engine = _engine(
        _fact(value="200"),
        _fact(concept="GrossProfit", value="80"),
    )
    first = first_engine.query_cell("AAA", "gross_margin", PERIOD, _policy())
    second = second_engine.query_cell("AAA", "gross_margin", PERIOD, _policy())
    assert first.value == second.value == Decimal("0.4")
    assert first.cell_id != second.cell_id
    assert first.provenance.dependency_cell_ids != second.provenance.dependency_cell_ids

    matrix = first_engine.query_matrix(
        tickers=("AAA",),
        metrics=("gross_margin",),
        periods=(PERIOD,),
        policy=_policy(),
    )
    csv_row = next(csv.DictReader(matrix.export_csv().payload.decode("utf-8").splitlines()))
    json_receipt = json.loads(matrix.export_json().payload)
    root_id = matrix.cells[0].cell_id

    # CSV is deliberately a flat, human-readable projection.  The canonical
    # proof is the JSON sidecar: one bundle plus one flat DAG shared by roots.
    assert csv_row["receipt_authority"] == "json_sidecar_required"
    assert csv_row["root_cell_id"] == root_id
    assert json_receipt["root_cell_ids"] == [root_id]
    assert json_receipt["governance_bundle"]["content_id"] == matrix.governance_bundle.content_id
    assert {node["cell_id"] for node in json_receipt["nodes"]} == {
        node.cell_id for node in matrix.cells[0].nodes
    }
    root_wire = next(node for node in json_receipt["nodes"] if node["cell_id"] == root_id)
    assert root_wire["provenance"]["dependency_cell_ids"] == list(
        matrix.cells[0].provenance.dependency_cell_ids
    )
    assert "dependency_receipts" not in root_wire["provenance"]
    assert MetricMatrix.from_dict(json_receipt).to_dict() == json_receipt


def test_matrix_constructor_and_parser_share_the_exact_wire_budget(monkeypatch) -> None:
    matrix = _engine(_fact()).query_matrix(
        tickers=("AAA",),
        metrics=("revenue",),
        periods=(PERIOD,),
        policy=_policy(),
    )
    receipt = matrix.to_dict()
    exact_cost = query_module._json_wire_cost(
        receipt,
        field_name="metric_matrix_receipt",
    )

    monkeypatch.setattr(query_module, "HARD_MAX_RECEIPT_WIRE_BYTES", exact_cost)
    assert replace(matrix).query_hash == matrix.query_hash
    assert MetricMatrix.from_dict(receipt).query_hash == matrix.query_hash

    monkeypatch.setattr(
        query_module,
        "HARD_MAX_RECEIPT_WIRE_BYTES",
        exact_cost - 1,
    )
    with pytest.raises(QueryBoundsError, match="receipt byte safety limit"):
        replace(matrix)
    with pytest.raises(QueryBoundsError, match="receipt byte safety limit"):
        MetricMatrix.from_dict(receipt)


def test_matrix_wire_budget_counts_canonical_json_escape_expansion(monkeypatch) -> None:
    escaped_fact = replace(
        _fact(),
        raw_token=("\x00\"\\" * 5_000),
        parsed_value="100",
        occurrence_id=None,
    )
    matrix = _engine(escaped_fact).query_matrix(
        tickers=("AAA",),
        metrics=("revenue",),
        periods=(PERIOD,),
        policy=_policy(),
    )
    receipt = matrix.to_dict()
    actual_wire_bytes = len(query_module.canonical_json(receipt).encode("utf-8"))
    admitted_wire_bytes = query_module._json_wire_cost(
        receipt,
        field_name="metric_matrix_receipt",
    )

    assert admitted_wire_bytes >= actual_wire_bytes
    assert len(query_module.canonical_json(escaped_fact.raw_token).encode("utf-8")) > (
        len(escaped_fact.raw_token.encode("utf-8")) * 2
    )

    monkeypatch.setattr(
        query_module,
        "HARD_MAX_RECEIPT_WIRE_BYTES",
        actual_wire_bytes - 1,
    )
    with pytest.raises(QueryBoundsError, match="receipt byte safety limit"):
        replace(matrix)
    with pytest.raises(QueryBoundsError, match="receipt byte safety limit"):
        MetricMatrix.from_dict(receipt)


def test_receipt_count_limits_precede_aggregate_byte_walk(monkeypatch) -> None:
    cell = _engine(_fact()).query_cell("AAA", "revenue", PERIOD, _policy())
    cell_wire = cell.to_dict()
    cell_wire["nodes"] = [None] * (HARD_MAX_RECEIPT_NODES + 1)

    def byte_walk_must_not_run(*args, **kwargs):
        raise AssertionError("aggregate byte walk ran before limit+1 admission")

    monkeypatch.setattr(query_module, "_admit_json_wire", byte_walk_must_not_run)
    with pytest.raises(QueryBoundsError, match="item safety limit"):
        MetricCell.from_dict(cell_wire)

    matrix = _engine(_fact()).query_matrix(
        tickers=("AAA",),
        metrics=("revenue",),
        periods=(PERIOD,),
        policy=_policy(),
    )
    matrix_wire = matrix.to_dict()
    matrix_wire["nodes"] = [None] * (query_module.HARD_MAX_MATRIX_NODES + 1)
    with pytest.raises(QueryBoundsError, match="item safety limit"):
        MetricMatrix.from_dict(matrix_wire)


def test_shared_receipt_subgraph_cannot_bypass_depth_limit() -> None:
    def node(identifier: str, dependencies: tuple[str, ...] = ()):
        return SimpleNamespace(
            cell_id=identifier,
            provenance=SimpleNamespace(dependency_cell_ids=dependencies),
        )

    nodes = {
        "root": node("root", ("X", "A")),
        "X": node("X", ("Y",)),
        "Y": node("Y"),
        "A": node("A", ("B",)),
        "B": node("B", ("X",)),
    }
    with pytest.raises(QueryBoundsError, match="depth safety limit 4"):
        query_module._validate_receipt_graph(
            root_cell_ids=("root",),
            nodes=nodes,
            maximum_nodes=10,
            maximum_edges=10,
            maximum_depth=4,
        )


def test_formula_flat_receipts_reject_forged_ids_entities_cutoffs_and_dependency_order() -> None:
    formula = _engine(
        _fact(value="100"),
        _fact(concept="GrossProfit", value="40"),
    ).query_cell("AAA", "gross_margin", PERIOD, _policy())
    dependency_by_id = {node.cell_id: node for node in formula.dependency_nodes}
    first, second = (
        dependency_by_id[cell_id] for cell_id in formula.provenance.dependency_cell_ids
    )

    with pytest.raises(QueryValidationError, match="dependency_cell_id does not identify a node"):
        replace(
            formula,
            provenance=replace(
                formula.provenance, dependency_cell_ids=("metric_cell_forged",)
            ),
            cell_id=None,
        )

    # Use a separately valid direct node; changing a node's entity in-place
    # would only prove the direct raw-fact binding, not formula join safety.
    wrong_entity = _engine(
        _fact(entity_id=ENTITY_B, concept="GrossProfit", value="40"),
        entities={"AAA": ENTITY_B},
    ).query_cell("AAA", "gross_profit", PERIOD, _policy()).root_node
    wrong_entity_provenance = replace(
        formula.provenance,
        dependency_cell_ids=(wrong_entity.cell_id, second.cell_id),
    )
    with pytest.raises(QueryValidationError, match="formula dependency entity does not match"):
        replace(
            formula,
            provenance=wrong_entity_provenance,
            dependency_nodes=(wrong_entity, second),
            cell_id=None,
        )

    later_dependency_provenance = replace(
        first.provenance,
        recorded_cutoff_at="2026-08-06T00:00:00Z",
    )
    later_dependency = replace(
        first,
        provenance=later_dependency_provenance,
        cell_id=None,
    )
    with pytest.raises(QueryValidationError, match="cutoff does not match governance bundle"):
        replace(
            formula,
            provenance=replace(
                formula.provenance,
                dependency_cell_ids=(later_dependency.cell_id, second.cell_id),
            ),
            dependency_nodes=(later_dependency, second),
            cell_id=None,
        )

    different_policy_dependency = replace(
        first,
        provenance=replace(
            first.provenance,
            source_snapshot_at="2026-08-04T00:00:00Z",
        ),
        cell_id=None,
    )
    with pytest.raises(QueryValidationError, match="formula dependency policy/cutoffs"):
        replace(
            formula,
            provenance=replace(
                formula.provenance,
                dependency_cell_ids=(different_policy_dependency.cell_id, second.cell_id),
            ),
            dependency_nodes=(different_policy_dependency, second),
            cell_id=None,
        )

    duplicate_metric = _engine(
        _fact(concept="GrossProfit", value="41", source_span=(9, 17))
    ).query_cell("AAA", "gross_profit", PERIOD, _policy()).root_node
    with pytest.raises(QueryValidationError, match="dependency metric IDs/order"):
        replace(
            formula,
            provenance=replace(
                formula.provenance,
                dependency_cell_ids=(first.cell_id, duplicate_metric.cell_id),
            ),
            dependency_nodes=(first, duplicate_metric),
            cell_id=None,
        )

    # A parent cannot suppress a governed value result while retaining its
    # otherwise valid dependency graph and exact source summaries.
    with pytest.raises(QueryValidationError, match="formula cell result does not recompute"):
        replace(
            formula,
            state=CellState.MISSING,
            value=None,
            reason="forged_missing_dependency",
            provenance=replace(
                formula.provenance, reason="forged_missing_dependency"
            ),
            cell_id=None,
        )


def test_formula_receipt_binds_selected_mapping_and_rejects_direct_only_fields() -> None:
    formula = _engine(
        _fact(value="100"),
        _fact(concept="GrossProfit", value="40"),
    ).query_cell("AAA", "gross_margin", PERIOD, _policy())
    dependencies = {
        node.metric_id: node for node in formula.dependency_nodes
    }
    revenue = dependencies["revenue"].provenance
    gross_profit = dependencies["gross_profit"].provenance

    assert formula.provenance.mapping_rule_id is None
    assert formula.provenance.mapping_rule_version == "1.0.0"
    assert formula.provenance.mapping_digest is None

    with pytest.raises(
        QueryValidationError,
        match="formula selected mapping summary does not match dependencies",
    ):
        replace(
            formula,
            provenance=replace(
                formula.provenance,
                mapping_rule_id=revenue.mapping_rule_id,
                mapping_digest=gross_profit.mapping_digest,
            ),
            cell_id=None,
        )

    with pytest.raises(
        QueryValidationError,
        match="formula selected mapping summary does not match dependencies",
    ):
        replace(
            formula,
            provenance=replace(
                formula.provenance,
                mapping_rule_version=None,
            ),
            cell_id=None,
        )

    for forged_field, forged_value in (
        ("accepted_at", "2026-07-01T01:00:00Z"),
        ("recorded_at", "2026-07-01T02:00:00Z"),
        ("mapping_available_at", "2026-07-01T03:00:00Z"),
        ("concept_qname", "us-gaap:GrossProfit"),
        ("taxonomy", "us-gaap"),
        ("concept", "GrossProfit"),
        ("alias_priority", 1),
        ("source_occurrence_ids", ("rawfact_invented",)),
    ):
        with pytest.raises(
            QueryValidationError,
            match="formula provenance cannot contain direct source receipts",
        ):
            replace(formula.provenance, **{forged_field: forged_value})


def test_normalized_receipts_cannot_omit_visible_governance_pack_lanes() -> None:
    direct = _engine(_fact()).query_cell("AAA", "revenue", PERIOD, _policy())
    assert direct.provenance.formula_pack_version is not None
    assert direct.provenance.formula_pack_digest is not None
    with pytest.raises(
        QueryValidationError,
        match="formula pack receipt does not match governance bundle",
    ):
        replace(
            direct,
            provenance=replace(
                direct.provenance,
                formula_pack_version=None,
                formula_pack_digest=None,
            ),
            cell_id=None,
        )

    formula = _engine(
        _fact(value="100"),
        _fact(concept="GrossProfit", value="40"),
    ).query_cell("AAA", "gross_margin", PERIOD, _policy())
    assert formula.provenance.mapping_pack_version is not None
    assert formula.provenance.mapping_pack_digest is not None
    with pytest.raises(
        QueryValidationError,
        match="mapping pack receipt does not match governance bundle",
    ):
        replace(
            formula,
            provenance=replace(
                formula.provenance,
                mapping_pack_version=None,
                mapping_pack_digest=None,
            ),
            cell_id=None,
        )


def test_non_value_receipts_bind_kernel_outcome_and_provenance_units() -> None:
    direct = _engine().query_cell("AAA", "revenue", PERIOD, _policy())
    assert direct.state is CellState.MISSING
    assert direct.unit == "USD"
    assert direct.provenance.unit is None

    with pytest.raises(
        QueryValidationError,
        match="direct non-value state/reason does not match a governed kernel outcome",
    ):
        replace(
            direct,
            state=CellState.NOT_EVALUABLE,
            reason="invented_failure",
            provenance=replace(direct.provenance, reason="invented_failure"),
            cell_id=None,
        )
    with pytest.raises(
        QueryValidationError,
        match="direct non-opaque cell unit does not match metric contract",
    ):
        replace(direct, unit="shares", cell_id=None)
    with pytest.raises(
        QueryValidationError,
        match="direct provenance unit does not match cell unit",
    ):
        replace(
            direct,
            provenance=replace(direct.provenance, unit="FORGED_UNIT"),
            cell_id=None,
        )
    with pytest.raises(
        QueryValidationError,
        match="direct alias-evidence outcome has an invalid provenance shape",
    ):
        replace(
            direct,
            reason="selected source vintage is withdrawn",
            provenance=replace(
                direct.provenance,
                reason="selected source vintage is withdrawn",
            ),
            cell_id=None,
        )

    formula = _engine(_fact()).query_cell(
        "AAA", "gross_margin", PERIOD, _policy()
    )
    assert formula.state is CellState.MISSING
    assert formula.unit == formula.provenance.unit == "ratio"
    with pytest.raises(
        QueryValidationError,
        match="formula provenance unit does not match output unit",
    ):
        replace(
            formula,
            provenance=replace(formula.provenance, unit="FORGED_UNIT"),
            cell_id=None,
        )


def test_direct_non_value_receipts_bind_policy_and_alias_year() -> None:
    latest_restated = _engine().query_cell(
        "AAA",
        "revenue",
        PERIOD,
        _policy(selection=BitemporalPolicy.LATEST_RESTATED),
    )
    generic_missing = (
        "missing_standard_fact: no governed concept alias supplied an exact eligible source interval"
    )
    with pytest.raises(
        QueryValidationError,
        match="generic source absence contradicts latest_restated policy",
    ):
        replace(
            latest_restated,
            reason=generic_missing,
            provenance=replace(latest_restated.provenance, reason=generic_missing),
            cell_id=None,
        )

    future_period = PeriodRequest.duration("2030-01-01", "2030-12-31")
    future_missing = _engine().query_cell(
        "AAA", "revenue", future_period, _policy()
    )
    assert future_missing.reason == (
        "no governed concept alias applies to the requested taxonomy period"
    )
    for forged_state, forged_reason in (
        (CellState.MISSING, generic_missing),
        (
            CellState.NOT_EVALUABLE,
            "visible source history exceeds the synchronous per-cell bound",
        ),
    ):
        with pytest.raises(
            QueryValidationError,
            match="requires an applicable governed alias",
        ):
            replace(
                future_missing,
                state=forged_state,
                reason=forged_reason,
                provenance=replace(
                    future_missing.provenance,
                    reason=forged_reason,
                ),
                cell_id=None,
            )
    future_restated = _engine().query_cell(
        "AAA",
        "revenue",
        future_period,
        _policy(selection=BitemporalPolicy.LATEST_RESTATED),
    )
    with pytest.raises(
        QueryValidationError,
        match="requires an applicable governed alias",
    ):
        replace(
            future_restated,
            reason="no eligible explicitly typed reported revision vintage",
            provenance=replace(
                future_restated.provenance,
                reason="no eligible explicitly typed reported revision vintage",
            ),
            cell_id=None,
        )

    original = _fact(value="100")
    amended = _fact(
        value="105",
        accession="0000000001-26-000004",
        document_id="fixture-10ka.htm",
        accepted_at="2026-08-03T01:00:00Z",
        recorded_at="2026-08-03T02:00:00Z",
        event_type=FactEventType.AMENDMENT,
        revision_of=original.occurrence_id,
    )
    withdrawn = _fact(
        value=None,
        accession="0000000001-26-000005",
        document_id="fixture-10ka.htm",
        accepted_at="2026-08-04T01:00:00Z",
        recorded_at="2026-08-04T02:00:00Z",
        event_type=FactEventType.WITHDRAWN,
        revision_of=amended.occurrence_id,
        is_nil=True,
    )
    withdrawn_cell = _engine(original, amended, withdrawn).query_cell(
        "AAA", "revenue", PERIOD, _policy()
    )
    assert withdrawn_cell.reason == "selected source vintage is withdrawn"
    with pytest.raises(
        QueryValidationError,
        match="withdrawn source outcome contradicts as_reported policy",
    ):
        replace(
            withdrawn_cell,
            provenance=replace(
                withdrawn_cell.provenance,
                policy=BitemporalPolicy.AS_REPORTED,
            ),
            cell_id=None,
        )

    nil_cell = _engine(_fact(value=None, is_nil=True)).query_cell(
        "AAA", "revenue", PERIOD, _policy()
    )
    assert nil_cell.reason == "selected source fact has no numeric value"
    with pytest.raises(
        QueryValidationError,
        match="outside its governed taxonomy-year range",
    ):
        replace(
            nil_cell,
            provenance=replace(
                nil_cell.provenance,
                concept_qname="us-gaap:SalesRevenueNet",
                taxonomy="us-gaap",
                concept="SalesRevenueNet",
                alias_priority=20,
            ),
            cell_id=None,
        )


def test_matrix_rejects_absent_mismatched_and_nested_governance_receipts() -> None:
    direct_matrix = _engine(_fact()).query_matrix(
        tickers=("AAA",),
        metrics=("revenue",),
        periods=(PERIOD,),
        policy=_policy(),
    )
    missing_bundle = json.loads(json.dumps(direct_matrix.to_dict()))
    del missing_bundle["governance_bundle"]
    with pytest.raises(QueryValidationError, match="missing required field"):
        MetricMatrix.from_dict(missing_bundle)

    wrong_catalog = json.loads(json.dumps(direct_matrix.to_dict()))
    wrong_catalog["governance_bundle"]["catalog"]["identifier"] = "different_catalog"
    with pytest.raises(QueryValidationError, match="invalid governance bundle"):
        MetricMatrix.from_dict(wrong_catalog)

    wrong_mapping_pack = json.loads(json.dumps(direct_matrix.to_dict()))
    wrong_mapping_pack["governance_bundle"]["mapping_pack"]["version"] = "9.9.9"
    with pytest.raises(QueryValidationError, match="invalid governance bundle"):
        MetricMatrix.from_dict(wrong_mapping_pack)

    formula_matrix = _engine(
        _fact(value="100"),
        _fact(concept="GrossProfit", value="40"),
    ).query_matrix(
        tickers=("AAA",),
        metrics=("gross_margin",),
        periods=(PERIOD,),
        policy=_policy(),
    )
    formula_cell = formula_matrix.cells[0]
    with pytest.raises(QueryValidationError, match="mapping pack receipt"):
        replace(
            formula_cell,
            provenance=replace(
                formula_cell.provenance,
                mapping_pack_digest="0" * 64,
            ),
            cell_id=None,
        )


def test_public_iterables_text_and_provenance_receipts_are_strictly_bounded() -> None:
    class LyingLength:
        def __init__(self) -> None:
            self.reads = 0

        def __len__(self) -> int:
            return 0

        def __iter__(self):
            for value in ("AAA", "BBB", "CCC"):
                self.reads += 1
                yield value

    class HostileIterator:
        def __len__(self) -> int:
            return 1

        def __iter__(self):
            yield "AAA"
            raise RuntimeError("iterator exploded")

    engine = _engine(_fact(), bounds=QueryBounds(max_tickers=1))
    lying = LyingLength()
    with pytest.raises(QueryBoundsError, match="max_tickers"):
        engine.query_matrix(
            tickers=lying,
            metrics=("revenue",),
            periods=(PERIOD,),
            policy=_policy(),
        )
    assert lying.reads == 2
    with pytest.raises(QueryValidationError, match="bounded iterable"):
        engine.query_matrix(
            tickers=HostileIterator(),
            metrics=("revenue",),
            periods=(PERIOD,),
            policy=_policy(),
        )
    with pytest.raises(QueryValidationError, match="text safety limit"):
        engine.query_cell("A" * 5000, "revenue", PERIOD, _policy())

    direct = engine.query_cell("AAA", "revenue", PERIOD, _policy())
    with pytest.raises(QueryBoundsError, match="item safety limit"):
        replace(direct.provenance, source_occurrence_ids=repeat("rawfact_x"))

    formula = _engine(
        _fact(value="100"),
        _fact(concept="GrossProfit", value="40"),
    ).query_cell("AAA", "gross_margin", PERIOD, _policy())
    with pytest.raises(QueryBoundsError, match="item safety limit"):
        replace(
            formula,
            dependency_nodes=repeat(formula.dependency_nodes[0]),
            cell_id=None,
        )


def test_public_mapping_adapters_stop_at_limit_plus_one() -> None:
    class LyingMapping(Mapping):
        def __init__(self, pairs):
            self.pairs = tuple(pairs)
            self.reads = 0

        def __len__(self) -> int:
            return 0

        def __iter__(self):
            for key, _ in self.pairs:
                self.reads += 1
                yield key

        def __getitem__(self, key):
            return dict(self.pairs)[key]

    fact = _fact()
    policy = LyingMapping(
        (
            ("source_snapshot_at", "2026-08-05T00:00:00Z"),
            ("recorded_at", "2026-08-05T00:00:00Z"),
            ("selection", "latest_known_as_of"),
            ("invented", "must-not-be-read-past"),
        )
    )
    with pytest.raises(QueryBoundsError, match="item safety limit 3"):
        _engine(fact).query_cell("AAA", "revenue", PERIOD, policy)
    assert policy.reads == 4

    entity = LyingMapping(
        (("ticker", "AAA"), ("entity_id", ENTITY_A), ("invented", "x"))
    )
    with pytest.raises(QueryBoundsError, match="item safety limit 2"):
        _engine(fact, entities=(entity,))
    assert entity.reads == 3

    period = LyingMapping(
        (("kind", "duration"), ("end", "2025-12-31"))
        + tuple((f"invented_{index}", index) for index in range(8))
    )
    with pytest.raises(QueryBoundsError, match="item safety limit 9"):
        _engine(fact).query_cell("AAA", "revenue", period, _policy())
    assert period.reads == 10

    metadata = LyingMapping(
        (("available_at", fact.recorded_at),)
        + tuple((f"invented_{index}", index) for index in range(8))
    )
    with pytest.raises(QueryBoundsError, match="item safety limit 8"):
        _engine(fact, filing_metadata={fact.occurrence_id: metadata})
    assert metadata.reads == 9


def test_visible_source_history_bound_is_post_cutoff_and_never_truncates() -> None:
    visible = tuple(
        _fact(value="100", source_span=(index * 10, index * 10 + 3))
        for index in range(3)
    )
    bounded = _engine(
        *visible,
        bounds=QueryBounds(max_visible_source_events_per_cell=2),
    ).query_cell("AAA", "revenue", PERIOD, _policy())
    assert bounded.state is CellState.NOT_EVALUABLE
    assert bounded.reason == "visible source history exceeds the synchronous per-cell bound"
    assert bounded.provenance.source_occurrence_ids == ()
    assert bounded.provenance.source_ready_at is None
    assert bounded.provenance.system_ready_at is None

    across_aliases = _engine(
        _fact(value="100"),
        _fact(concept="Revenues", value="100", source_span=(20, 23)),
        bounds=QueryBounds(max_visible_source_events_per_cell=1),
    ).query_cell("AAA", "revenue", PERIOD, _policy())
    assert across_aliases.state is CellState.NOT_EVALUABLE
    assert across_aliases.reason == bounded.reason
    assert across_aliases.provenance.source_occurrence_ids == ()
    assert across_aliases.provenance.concept_qname is None
    assert across_aliases.provenance.mapping_rule_id is None

    original = _fact(value="100", source_span=(0, 3))
    future = tuple(
        _fact(
            value=str(200 + index),
            accession=f"0000000001-26-9{index:05d}",
            document_id=f"future-{index}.htm",
            accepted_at="2026-08-06T01:00:00Z",
            recorded_at="2026-08-06T02:00:00Z",
            source_span=(index * 10 + 10, index * 10 + 13),
        )
        for index in range(8)
    )
    one_bound = QueryBounds(max_visible_source_events_per_cell=1)
    baseline = _engine(original, bounds=one_bound).query_cell(
        "AAA", "revenue", PERIOD, _policy()
    )
    with_future = _engine(original, *future, bounds=one_bound).query_cell(
        "AAA", "revenue", PERIOD, _policy()
    )
    assert with_future.to_dict() == baseline.to_dict()
    assert with_future.cell_id == baseline.cell_id


@pytest.mark.parametrize(
    ("kind", "kwargs"),
    (
        (PeriodKind.DURATION, {}),
        (PeriodKind.FISCAL_QUARTER, {"fiscal_year": 2025, "fiscal_quarter": 1}),
        (PeriodKind.YTD, {"fiscal_year": 2025, "fiscal_quarter": 3}),
        (PeriodKind.ANNUAL, {"fiscal_year": 2025}),
        (PeriodKind.DIRECT_Q4, {"fiscal_year": 2025, "fiscal_quarter": 4}),
        (PeriodKind.DERIVED_Q4, {"fiscal_year": 2025, "fiscal_quarter": 4}),
        (PeriodKind.TTM, {}),
        (PeriodKind.STUB, {}),
    ),
)
def test_all_noninstant_typed_periods_use_raw_duration_index_and_keep_exact_kind(
    kind: PeriodKind,
    kwargs: dict[str, int],
) -> None:
    period = PeriodRequest(
        kind=kind,
        start="2025-01-01",
        end="2025-12-31",
        **kwargs,
    )
    cell = _engine(_fact()).query_cell("AAA", "revenue", period, _policy())
    assert cell.state is CellState.VALUE
    assert cell.period.kind is kind
    receipt = cell.to_dict()
    root_wire = next(
        node for node in receipt["nodes"] if node["cell_id"] == receipt["root_cell_id"]
    )
    assert root_wire["period"]["kind"] == kind.value


def test_unit_trust_is_exact_and_mapping_before_recording_is_valid() -> None:
    governed = _engine(
        _fact(unit=FactUnit("USD", ["iso4217:USD"]), value="100")
    ).query_cell("AAA", "revenue", PERIOD, _policy())
    spoofed_usd = _engine(
        _fact(unit=FactUnit("USD", ["evil:USD"]), value="100")
    ).query_cell("AAA", "revenue", PERIOD, _policy())
    spoofed_shares = _engine(
        _fact(
            concept="WeightedAverageNumberOfSharesOutstandingBasic",
            unit=FactUnit("shares", ["evil:shares"]),
            value="100",
        )
    ).query_cell("AAA", "basic_weighted_average_shares", PERIOD, _policy())

    assert governed.state is CellState.VALUE
    for rejected in (spoofed_usd, spoofed_shares):
        assert rejected.state is CellState.NOT_EVALUABLE
        assert rejected.reason and rejected.reason.startswith("unexpected_unit")
        assert rejected.provenance.source_occurrence_ids
        assert rejected.provenance.mapping_digest

    early_mapping = _engine(
        _fact(
            mapping_available_at="2026-08-02T01:30:00Z",
            recorded_at="2026-08-02T02:00:00Z",
        )
    ).query_cell("AAA", "revenue", PERIOD, _policy())
    assert early_mapping.state is CellState.VALUE
    assert early_mapping.provenance.mapping_available_at == datetime(
        2026, 8, 2, 1, 30, tzinfo=timezone.utc
    )
    assert early_mapping.provenance.recorded_at == datetime(
        2026, 8, 2, 2, tzinfo=timezone.utc
    )


def test_duplicate_intervals_preserve_source_precision_under_hostile_ambient_context() -> None:
    exact_left = _fact(
        value="1234567890123456789012345678901234567891",
        decimals="INF",
        source_span=(0, 8),
    )
    exact_right = _fact(
        value="1234567890123456789012345678901234567892",
        decimals="INF",
        source_span=(20, 28),
    )
    huge = "9" * 80
    tolerant_left = _fact(value=huge, decimals="10000", source_span=(0, 8))
    tolerant_right = _fact(value=huge, decimals="10000", source_span=(20, 28))

    with localcontext() as context:
        context.prec = 5
        conflict = _engine(exact_left, exact_right).query_cell(
            "AAA", "revenue", PERIOD, _policy()
        )
        agreement = _engine(tolerant_left, tolerant_right).query_cell(
            "AAA", "revenue", PERIOD, _policy()
        )
    assert conflict.state is CellState.NOT_EVALUABLE
    assert conflict.reason == "conflicting duplicate raw facts cannot be selected"
    assert agreement.state is CellState.VALUE
    assert agreement.value == Decimal(huge)


def test_duplicate_and_revision_arbitration_have_linear_operation_counts(monkeypatch) -> None:
    duplicate_count = 256
    duplicates = tuple(
        _fact(
            value="1234567890123456789012345678901234567890",
            decimals="INF",
            source_span=(index * 10, index * 10 + 8),
        )
        for index in range(duplicate_count)
    )
    interval_calls = 0
    original_interval = query_module._duplicate_interval

    def counted_interval(item):
        nonlocal interval_calls
        interval_calls += 1
        return original_interval(item)

    monkeypatch.setattr(query_module, "_duplicate_interval", counted_interval)
    duplicate_cell = _engine(*duplicates).query_cell(
        "AAA", "revenue", PERIOD, _policy()
    )
    assert duplicate_cell.state is CellState.VALUE
    assert interval_calls == duplicate_count

    chain: list = []
    parent_id = None
    start = datetime(2026, 8, 2, 1, tzinfo=timezone.utc)
    revision_count = 128
    for index in range(revision_count):
        accepted = start + timedelta(minutes=index)
        event = _fact(
            value=str(index + 1),
            accession=f"0000000001-26-8{index:05d}",
            document_id=f"revision-{index}.htm",
            accepted_at=accepted.isoformat(),
            recorded_at=(accepted + timedelta(seconds=30)).isoformat(),
            event_type=(
                FactEventType.FILED if index == 0 else FactEventType.PARSER_CORRECTION
            ),
            revision_of=parent_id,
        )
        chain.append(event)
        parent_id = event.occurrence_id
    engine = _engine(*chain)
    readiness_calls = 0
    lineage_id_calls = 0
    original_readiness = engine._group_readiness  # type: ignore[attr-defined]
    original_lineage_ids = engine._lineage_ids_for  # type: ignore[attr-defined]

    def counted_readiness(group):
        nonlocal readiness_calls
        readiness_calls += 1
        return original_readiness(group)

    def counted_lineage_ids(group):
        nonlocal lineage_id_calls
        lineage_id_calls += 1
        return original_lineage_ids(group)

    monkeypatch.setattr(engine, "_group_readiness", counted_readiness)
    monkeypatch.setattr(engine, "_lineage_ids_for", counted_lineage_ids)
    latest = engine.query_cell("AAA", "revenue", PERIOD, _policy())
    assert latest.state is CellState.VALUE
    assert latest.value == Decimal(revision_count)
    assert readiness_calls == revision_count
    assert lineage_id_calls == 1
