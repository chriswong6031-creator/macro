"""Adversarial contract tests for the bitemporal metric query kernel."""
from __future__ import annotations

from collections.abc import Sequence
import csv
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext
import hashlib
from itertools import repeat
import json
from pathlib import Path

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
    CellNode,
    CellProvenance,
    CellState,
    EvaluationPolicy,
    FilingMetadata,
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
        entities={"AAA": ENTITY_A, "BBB": ENTITY_B},
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
    direct_dependencies = tuple(
        node
        for node in cell.dependency_nodes
        if node.cell_id in cell.provenance.dependency_cell_ids
    )
    assert len(direct_dependencies) == 2
    assert cell.provenance.dependency_cell_ids == tuple(
        item.cell_id
        for metric_id in ("revenue", "gross_profit")
        for item in direct_dependencies
        if item.metric_id == metric_id
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


def test_future_mapping_and_formula_governance_are_opaque_and_do_not_evaluate_dependencies() -> None:
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
        mappings=(replace(base_mapping, rule=future_rule),),
    )
    fact = _fact()
    direct = _engine(fact, registry=future_mapping_registry).query_cell(
        "AAA", "revenue", PERIOD, _policy()
    )

    assert direct.state is CellState.MISSING
    assert direct.reason == "governance unavailable at recorded_at cutoff"
    assert direct.provenance.mapping_rule_id is None
    assert direct.provenance.mapping_digest is None
    assert direct.provenance.source_occurrence_ids == ()
    assert direct.provenance.concept_qname is None
    assert fact.occurrence_id not in direct.to_dict().__repr__()

    # Mapping availability is checked before request semantics too; otherwise
    # an invalid request becomes a side channel for a future rule's presence.
    direct_invalid_period = _engine(fact, registry=future_mapping_registry).query_cell(
        "AAA", "revenue", PeriodRequest.instant("2025-12-31"), _policy()
    )
    assert direct_invalid_period.state is CellState.MISSING
    assert direct_invalid_period.reason == "governance unavailable at recorded_at cutoff"
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
        MetricMatrix(
            policy=policy,
            entities=(QueryEntity("AAA", ENTITY_A),),
            metric_ids=("revenue",),
            periods=(PERIOD,),
            cells=(replace(good, entity_id=ENTITY_B, cell_id=None),),
            registry_receipt={},
        )
    with pytest.raises(QueryValidationError, match="unique entity_ids"):
        MetricMatrix(
            policy=policy,
            entities=(QueryEntity("AAA", ENTITY_A), QueryEntity("BBB", ENTITY_A)),
            metric_ids=("revenue",),
            periods=(PERIOD,),
            cells=(),
            registry_receipt={},
        )


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
    assert matrix.registry_receipt == baseline.registry_receipt
    assert matrix.query_hash == baseline.query_hash
    for metric_id in ("future_private_metric", "truly_unknown_metric"):
        with pytest.raises(UnsupportedMetricError, match="unsupported metric"):
            _engine(fact, registry=registry_with_future_catalog_member).query_cell(
                "AAA", metric_id, PERIOD, _policy()
            )

    policy = _policy()
    base_matrix = _engine(_fact(value="-42")).query_matrix(
        tickers=("AAA",),
        metrics=("revenue",),
        periods=(PERIOD,),
        policy=policy,
    )
    base_cell = base_matrix.cells[0]
    provenance_metadata = FilingMetadata(
        accession="@evil",
        document_id=base_cell.provenance.document_id,
        source_body_sha256=base_cell.provenance.source_body_sha256,
        available_at=base_cell.provenance.filing_metadata_available_at,
        form=base_cell.provenance.form,
        filed_at=base_cell.provenance.filed_at,
    )
    provenance = replace(
        base_cell.provenance,
        accession="@evil",
        filing_metadata_content_sha256=provenance_metadata.content_sha256,
    )
    cell = MetricCell(
        ticker="AAA",
        entity_id="=2+2",
        metric_id="revenue",
        period=PERIOD,
        state=CellState.VALUE,
        value=Decimal("-42"),
        unit="USD",
        provenance=provenance,
    )
    export = MetricMatrix(
        policy=policy,
        entities=(QueryEntity("AAA", "=2+2"),),
        metric_ids=("revenue",),
        periods=(PERIOD,),
        cells=(cell,),
        registry_receipt=base_matrix.registry_receipt,
    ).export_csv()
    row = list(csv.reader(export.payload.decode("utf-8").splitlines()))[1]
    assert row[2] == "'=2+2"
    assert row[10] == "-42"
    assert row[13] == "'@evil"


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
    assert extended_matrix.registry_receipt == baseline_matrix.registry_receipt
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
            ConceptAlias("us-gaap", "DistinctRevenueConcept", 10, 2009, 2026),
        ),
    )
    custom = _replace_contract(
        registry,
        "revenue",
        mappings=revenue.mappings + (second_mapping,),
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


def test_formula_cell_identity_and_exports_embed_complete_dependency_receipts() -> None:
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
    csv_rows = list(csv.DictReader(matrix.export_csv().payload.decode("utf-8").splitlines()))
    csv_receipt = json.loads(csv_rows[0]["provenance_receipt"])
    assert csv_receipt == matrix.cells[0].provenance.to_dict()
    assert len(csv_receipt["dependency_receipts"]) == 2
    assert json.loads(matrix.export_json().payload)["cells"][0]["provenance"][
        "dependency_receipts"
    ] == csv_receipt["dependency_receipts"]


def test_formula_receipts_reject_forged_ids_entities_cutoffs_and_duplicate_metrics() -> None:
    formula = _engine(
        _fact(value="100"),
        _fact(concept="GrossProfit", value="40"),
    ).query_cell("AAA", "gross_margin", PERIOD, _policy())
    first, second = formula.provenance.dependency_cells

    with pytest.raises(QueryValidationError, match="dependency_cell_ids do not match"):
        replace(formula.provenance, dependency_cell_ids=("metric_cell_forged",))

    wrong_entity = replace(
        first,
        ticker="BBB",
        entity_id=ENTITY_B,
        cell_id=None,
    )
    wrong_entity_provenance = replace(
        formula.provenance,
        dependency_cell_ids=(),
        dependency_cells=(wrong_entity, second),
    )
    with pytest.raises(QueryValidationError, match="match the formula cell entity"):
        replace(formula, provenance=wrong_entity_provenance, cell_id=None)

    later_dependency_provenance = replace(
        first.provenance,
        recorded_cutoff_at="2026-08-06T00:00:00Z",
    )
    later_dependency = replace(
        first,
        provenance=later_dependency_provenance,
        cell_id=None,
    )
    with pytest.raises(QueryValidationError, match="policy/cutoffs"):
        replace(
            formula.provenance,
            dependency_cell_ids=(),
            dependency_cells=(later_dependency, second),
        )

    duplicate_metric = replace(second, metric_id=first.metric_id, cell_id=None)
    duplicate_metric_provenance = replace(
        formula.provenance,
        dependency_cell_ids=(),
        dependency_cells=(first, duplicate_metric),
    )
    with pytest.raises(QueryValidationError, match="unique metric_ids"):
        replace(formula, provenance=duplicate_metric_provenance, cell_id=None)

    missing_reason = "forged_missing_dependency"
    missing_dependency = replace(
        first,
        state=CellState.MISSING,
        value=None,
        provenance=replace(first.provenance, reason=missing_reason),
        reason=missing_reason,
        cell_id=None,
    )
    missing_dependency_provenance = replace(
        formula.provenance,
        dependency_cell_ids=(),
        dependency_cells=(missing_dependency, second),
    )
    with pytest.raises(QueryValidationError, match="value dependency receipts"):
        replace(formula, provenance=missing_dependency_provenance, cell_id=None)


def test_matrix_rejects_absent_mismatched_and_nested_registry_receipts() -> None:
    direct_matrix = _engine(_fact()).query_matrix(
        tickers=("AAA",),
        metrics=("revenue",),
        periods=(PERIOD,),
        policy=_policy(),
    )
    with pytest.raises(QueryValidationError, match="catalog receipt"):
        replace(direct_matrix, registry_receipt={})
    wrong_catalog_receipt = dict(direct_matrix.registry_receipt)
    wrong_catalog_receipt["catalog_id"] = "different_catalog"
    with pytest.raises(QueryValidationError, match="catalog receipt"):
        replace(direct_matrix, registry_receipt=wrong_catalog_receipt)
    wrong_direct_receipt = dict(direct_matrix.registry_receipt)
    wrong_direct_receipt["mapping_pack_content_sha256"] = "0" * 64
    with pytest.raises(QueryValidationError, match="mapping pack receipt"):
        replace(direct_matrix, registry_receipt=wrong_direct_receipt)

    formula_matrix = _engine(
        _fact(value="100"),
        _fact(concept="GrossProfit", value="40"),
    ).query_matrix(
        tickers=("AAA",),
        metrics=("gross_margin",),
        periods=(PERIOD,),
        policy=_policy(),
    )
    wrong_nested_receipt = dict(formula_matrix.registry_receipt)
    wrong_nested_receipt["mapping_pack_content_sha256"] = "0" * 64
    formula_cell = formula_matrix.cells[0]
    forged_top = replace(
        formula_cell,
        provenance=replace(
            formula_cell.provenance,
            mapping_pack_digest="0" * 64,
        ),
        cell_id=None,
    )
    with pytest.raises(QueryValidationError, match="mapping pack receipt"):
        replace(
            formula_matrix,
            cells=(forged_top,),
            registry_receipt=wrong_nested_receipt,
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
            formula.provenance,
            dependency_cell_ids=(),
            dependency_cells=repeat(formula.provenance.dependency_cells[0]),
        )


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
    assert cell.to_dict()["period"]["kind"] == kind.value


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
