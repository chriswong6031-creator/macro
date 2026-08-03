"""Safety fences for the isolated dimensions-unknown B4 evidence bridge."""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest

from engine.fundamental_forensics.attested_occurrence_governance import (
    AttestedOccurrenceGovernanceError,
    build_attested_occurrence_governance_bundle,
)
from engine.fundamental_forensics.metric_registry import (
    GovernanceBundle,
    load_core_metric_registry,
)
from engine.fundamental_forensics.query import (
    BitemporalMetricQueryEngine,
    CellState,
    FilingMetadata,
    PeriodRequest,
    QueryPolicy,
)
from engine.fundamental_forensics.raw_ledger import (
    FactContext,
    FactUnit,
    RawFactLedger,
    SourceIdentity,
    make_raw_fact,
)


ROOT = Path(__file__).resolve().parents[1]
AT = "2026-08-03T12:00:00Z"
CIK = "0000320193"


def _fact(*, dimensions_known: bool = False, source: str = "sec-companyfacts"):
    return make_raw_fact(
        source=SourceIdentity(
            source=source,
            entity_id=CIK,
            accession="0000320193-25-000079",
            document_id="aapl-20250927.htm",
            body_sha256=sha256(b"companyfacts").hexdigest(),
            source_url="https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json",
        ),
        concept_qname="us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
        context=FactContext(
            context_id="companyfacts-entry-1",
            entity_scheme="http://www.sec.gov/CIK",
            entity_identifier=CIK,
            start="2024-09-29",
            end="2025-09-27",
        ),
        unit=FactUnit("USD", ("iso4217:USD",)),
        raw_token="416161000000",
        parsed_value="416161000000",
        dimensions_known=dimensions_known,
        accepted_at="2025-10-31T10:07:08Z",
        recorded_at=AT,
        source_occurrence_key="fixture-companyfacts-entry-1",
    )


def _metadata(fact):
    return {
        fact.occurrence_id: FilingMetadata(
            accession=fact.source.accession,
            document_id=fact.source.document_id,
            source_body_sha256=fact.source.body_sha256,
            available_at=fact.recorded_at,
            form="10-K",
            filed_at="2025-10-31",
        )
    }


def test_evidence_bundle_selects_unknown_dimensions_but_core_rejects_them():
    fact = _fact()
    ledger = RawFactLedger((fact,))
    metadata = _metadata(fact)
    period = PeriodRequest.duration("2024-09-29", "2025-09-27", label="FY2025")
    policy = QueryPolicy(source_snapshot_at=AT, recorded_at=AT)
    core = BitemporalMetricQueryEngine(
        ledger,
        load_core_metric_registry(ROOT),
        entities={"AAPL": CIK},
        filing_metadata=metadata,
    ).query_matrix(
        tickers=["AAPL"], metrics=["revenue"], periods=[period], policy=policy
    )
    assert core.cells[0].state is CellState.NOT_EVALUABLE
    assert "unknown_dimension_scope" in (core.cells[0].reason or "")

    bundle = build_attested_occurrence_governance_bundle(
        occurrence=fact, recorded_at=AT
    )
    evidence = BitemporalMetricQueryEngine(
        ledger,
        bundle,
        entities={"AAPL": CIK},
        filing_metadata=metadata,
    ).query_matrix(
        tickers=["AAPL"],
        metrics=["attested_occurrence"],
        periods=[period],
        policy=policy,
    )
    assert evidence.cells[0].state is CellState.VALUE
    assert evidence.cells[0].provenance.source_occurrence_ids == (
        fact.occurrence_id,
    )
    assert evidence.governance_bundle.metric(
        "attested_occurrence"
    ).dimensional_profile.mode == "dimensions_unknown_only"
    assert GovernanceBundle.from_dict(bundle.to_dict()) == bundle


@pytest.mark.parametrize(
    "fact,match",
    [
        (_fact(dimensions_known=True), "dimensions_known=false"),
        (_fact(source="sec-edgar"), "only SEC Company Facts"),
    ],
)
def test_evidence_bundle_rejects_non_companyfacts_or_known_dimensions(fact, match):
    with pytest.raises(AttestedOccurrenceGovernanceError, match=match):
        build_attested_occurrence_governance_bundle(occurrence=fact, recorded_at=AT)


def test_dimensions_unknown_profile_cannot_be_relabelled_as_core_revenue():
    fact = _fact()
    bundle = build_attested_occurrence_governance_bundle(
        occurrence=fact, recorded_at=AT
    )
    evidence = bundle.contracts[0]
    forged = replace(
        evidence,
        metric_id="revenue",
        mappings=tuple(
            replace(mapping, metric_id="revenue") for mapping in evidence.mappings
        ),
    )
    with pytest.raises(ValueError, match="restricted to the isolated"):
        GovernanceBundle(
            schema=bundle.schema,
            recorded_at=bundle.recorded_at,
            catalog=bundle.catalog,
            mapping_pack=bundle.mapping_pack,
            formula_pack=None,
            contracts=(forged,),
        )


@pytest.mark.parametrize(
    "mutation",
    (
        "label",
        "category",
        "presentation",
        "review",
        "no_result",
        "metric_rule_version",
        "mapping_rule_version",
        "catalog_version",
        "extra_contract",
    ),
)
def test_dimensions_unknown_evidence_contract_cannot_gain_semantic_authority(
    mutation,
):
    fact = _fact()
    bundle = build_attested_occurrence_governance_bundle(
        occurrence=fact, recorded_at=AT
    )
    evidence = bundle.contracts[0]
    catalog = bundle.catalog
    contracts = (evidence,)
    if mutation == "label":
        evidence = replace(evidence, label="Revenue")
    elif mutation == "category":
        evidence = replace(evidence, category="income_statement")
    elif mutation == "presentation":
        evidence = replace(
            evidence,
            presentation_constraints=replace(
                evidence.presentation_constraints, statement="income_statement"
            ),
        )
    elif mutation == "review":
        evidence = replace(
            evidence,
            review=replace(evidence.review, triggers=("manual_review",)),
        )
    elif mutation == "no_result":
        evidence = replace(
            evidence,
            no_result=replace(evidence.no_result, codes=("missing_standard_fact",)),
        )
    elif mutation == "metric_rule_version":
        evidence = replace(evidence, rule=replace(evidence.rule, version="1.0.1"))
    elif mutation == "mapping_rule_version":
        mapping = evidence.mappings[0]
        evidence = replace(
            evidence,
            mappings=(
                replace(mapping, rule=replace(mapping.rule, version="1.0.1")),
            ),
        )
    elif mutation == "catalog_version":
        assert catalog is not None
        catalog = replace(catalog, version="1.0.1")
    elif mutation == "extra_contract":
        contracts = (evidence, evidence)
    if mutation != "extra_contract":
        contracts = (evidence,)

    with pytest.raises(ValueError, match="restricted to the isolated"):
        GovernanceBundle(
            schema=bundle.schema,
            recorded_at=bundle.recorded_at,
            catalog=catalog,
            mapping_pack=bundle.mapping_pack,
            formula_pack=None,
            contracts=contracts,
        )
