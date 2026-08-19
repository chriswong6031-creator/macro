"""FIF-1R3 semantic closure: re-addressed truth, revision vocabulary, identity, graph bounds."""
from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
from dataclasses import replace

import pytest

from engine.fundamental_forensics.financial_intelligence_packet import (
    DEFAULT_REQUESTED_METRICS,
    PACKET_MAX_METRICS,
    PACKET_MAX_PERIODS,
    PACKET_MAX_REVISIONS,
    PACKET_MAX_REVISION_LINEAGE_DEPTH,
    EntityInput,
    FilingPackageFixture,
    PacketEvidenceDigests,
    PacketQueryRequest,
    assemble_financial_intelligence_packet,
    canonical_packet_bytes,
    default_packet_periods,
    load_core_registry,
    load_filing_package_fixture,
    load_packet_schema,
    readdress_packet,
    validate_packet,
    validate_packet_against_build_input,
    validate_packet_semantics,
    walk_formula_graph,
)
from engine.fundamental_forensics import financial_intelligence_packet as packet_module
from engine.fundamental_forensics import metric_registry as registry_module
from engine.fundamental_forensics.metric_registry import (
    ConceptAlias,
    ImmutableRule,
    KnownConcept,
    MappingRule,
)
from engine.fundamental_forensics.query import PeriodRequest, QueryPolicy
from engine.fundamental_forensics.raw_ledger import (
    FactContext,
    FactEventType,
    RawFactLedger,
    utc_text,
)
from engine.fundamental_forensics.synthetic_filing_package import (
    SYNTHETIC_ENTITY_ID,
    build_multihop_revenue_fixture,
    build_synthetic_filing_package_fixture,
    filing as synthetic_filing,
    usd_fact,
    _metadata_for,
)
from tests.test_fundamental_forensics_financial_intelligence_packet import (
    ROOT,
    SCHEMA_PATH,
    _build,
    _cell,
    _context,
    _input_digests,
)
from tests.test_fundamental_forensics_financial_intelligence_packet_r2 import (
    LEDGER_PATH,
    T3_RECORDED,
    T3_SOURCE,
)


CANONICAL_ISSUER_ID = "mmx.issuer.fip1"
FUTURE_CONCEPT = "RevenueFromContractWithCustomerIncludingAssessedTax"
FUTURE_CONCEPT_QNAME = f"us-gaap:{FUTURE_CONCEPT}"
FUTURE_METRIC_ID = "future_metric"
FUTURE_METRIC_LABEL = "FUTURE LEAK LABEL"


def _register_future_concept(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(
        registry_module.KNOWN_CONCEPT_ALLOWLIST,
        ("us-gaap", FUTURE_CONCEPT),
        KnownConcept(
            taxonomy="us-gaap",
            concept=FUTURE_CONCEPT,
            taxonomy_version_start=2009,
            taxonomy_version_end=2026,
            period_kind="duration",
            contract_units=("USD",),
        ),
    )


def _registry_with_future_revenue_mapping(available_at: datetime):
    registry = load_core_registry(ROOT)
    future_mapping = MappingRule(
        metric_id="revenue",
        rule=ImmutableRule(
            rule_id="mapping.revenue.including_assessed_tax.future/v1",
            version="1.0.0",
            available_at=available_at,
            confidence="A",
        ),
        taxonomy_concept_aliases=(
            ConceptAlias("us-gaap", FUTURE_CONCEPT, 99, 2009, 2026),
        ),
    )
    return replace(
        registry,
        contracts=tuple(
            replace(contract, mappings=contract.mappings + (future_mapping,))
            if contract.metric_id == "revenue"
            else contract
            for contract in registry.contracts
        ),
    )


def _registry_with_future_metric_contract(available_at: datetime):
    registry = load_core_registry(ROOT)
    assert FUTURE_METRIC_ID not in registry.metric_ids
    base = registry.metric("revenue")
    mapping = base.mappings[0]
    future = replace(
        base,
        metric_id=FUTURE_METRIC_ID,
        label=FUTURE_METRIC_LABEL,
        rule=replace(
            base.rule,
            rule_id="metric.future_metric/v1",
            available_at=available_at,
        ),
        mappings=(
            replace(
                mapping,
                metric_id=FUTURE_METRIC_ID,
                rule=replace(
                    mapping.rule,
                    rule_id="mapping.future_metric/v1",
                    available_at=available_at,
                ),
                taxonomy_concept_aliases=(
                    ConceptAlias("us-gaap", FUTURE_CONCEPT, 10, 2009, 2026),
                ),
            ),
        ),
        formula=None,
        declared_formula_dependencies=(),
    )
    return replace(registry, contracts=registry.contracts + (future,))


def _against(packet, *, fixture=None, **build_kwargs) -> None:
    loaded = fixture if fixture is not None else load_filing_package_fixture(LEDGER_PATH)
    policy = build_kwargs.get("policy", "latest_known_as_of")
    source_event_cutoff = build_kwargs.get("source_event_cutoff", "2025-12-31T23:59:59Z")
    system_recorded_cutoff = build_kwargs.get("system_recorded_cutoff", "2026-08-05T12:00:02Z")
    metrics = build_kwargs.get("metrics")
    periods = build_kwargs.get("periods")
    validate_packet_against_build_input(
        packet,
        entity=loaded.entity,
        ledger=loaded.ledger,
        filing_metadata=loaded.filing_metadata,
        query_request=PacketQueryRequest(
            policy=QueryPolicy(
                source_snapshot_at=source_event_cutoff,
                recorded_at=system_recorded_cutoff,
                selection=policy,
            ),
            metrics=metrics or DEFAULT_REQUESTED_METRICS,
            periods=periods or default_packet_periods(),
        ),
        metric_registry=load_core_registry(ROOT),
        context=_context(),
        input_digests=build_kwargs.get("input_digests", _input_digests()),
    )


def test_readdressed_forged_direct_value_is_rejected() -> None:
    packet = _build()
    tampered = copy.deepcopy(packet)
    cell = next(
        item
        for item in tampered["cells"]
        if item["metric_id"] == "revenue" and item["period"].get("label") == "FY2023"
    )
    assert cell["value"] == "1060"
    cell["value"] = "9999"
    readdressed = readdress_packet(tampered)
    validate_packet_semantics(readdressed)
    with pytest.raises(ValueError, match="packet body does not match reconstructed build inputs"):
        _against(readdressed)


def test_readdressed_forged_formula_value_is_rejected() -> None:
    packet = _build()
    tampered = copy.deepcopy(packet)
    cell = next(
        item
        for item in tampered["cells"]
        if item["metric_id"] == "gross_margin" and item["period"].get("label") == "FY2023"
    )
    assert cell["value"] is not None
    cell["value"] = "0.5"
    readdressed = readdress_packet(tampered)
    validate_packet_semantics(readdressed)
    with pytest.raises(ValueError, match="packet body does not match reconstructed build inputs"):
        _against(readdressed)


def _recompute_packet_coverage_inplace(packet: dict) -> None:
    from engine.fundamental_forensics.financial_intelligence_packet import _coverage

    query = packet["query"]
    packet["coverage"] = _coverage(
        tuple(query["requested_metrics"]),
        len(query["requested_periods"]),
        packet["cells"],
        packet["evidence_cells"],
        packet.get("revisions") or [],
        list((packet.get("coverage") or {}).get("unmapped_extension_concepts") or []),
    )
    audited = [*packet["cells"], *packet["evidence_cells"]]
    packet["receipts"]["source_receipt_count"] = sum(
        len(cell.get("source_occurrence_ids") or []) for cell in audited
    )
    packet["receipts"]["governance_receipt_count"] = sum(
        1
        for cell in audited
        if cell.get("mapping_rule_digest") or cell.get("formula_rule_digest")
    )


def test_readdressed_forged_formula_digest_and_dependencies_are_rejected() -> None:
    packet = _build()
    digest_tampered = copy.deepcopy(packet)
    formula = next(
        item
        for item in digest_tampered["cells"]
        if item["metric_id"] == "gross_margin" and item["period"].get("label") == "FY2023"
    )
    formula["formula_rule_digest"] = "0" * 64
    _recompute_packet_coverage_inplace(digest_tampered)
    readdressed = readdress_packet(digest_tampered)
    validate_packet_semantics(readdressed)
    with pytest.raises(ValueError, match="packet body does not match reconstructed build inputs"):
        _against(readdressed)

    dep_tampered = copy.deepcopy(packet)
    formula = next(
        item
        for item in dep_tampered["cells"]
        if item["metric_id"] == "gross_margin" and item["period"].get("label") == "FY2023"
    )
    formula["dependency_cell_ids"] = list(reversed(formula["dependency_cell_ids"]))
    _recompute_packet_coverage_inplace(dep_tampered)
    readdressed = readdress_packet(dep_tampered)
    with pytest.raises(ValueError, match="packet body does not match reconstructed build inputs"):
        _against(readdressed)


def test_readdressed_forged_visible_query_is_rejected() -> None:
    packet = _build()
    tampered = copy.deepcopy(packet)
    tampered["query"]["source_event_cutoff"] = "2024-12-31T23:59:59Z"
    readdressed = readdress_packet(tampered)
    validate_packet_semantics(readdressed)
    with pytest.raises(ValueError, match="packet body does not match reconstructed build inputs"):
        _against(readdressed)
    policy_tampered = copy.deepcopy(packet)
    policy_tampered["query"]["policy"] = "as_reported"
    readdressed = readdress_packet(policy_tampered)
    with pytest.raises(ValueError, match="packet body does not match reconstructed build inputs"):
        _against(readdressed)


def test_readdressed_forged_coverage_count_is_rejected() -> None:
    packet = _build()
    tampered = copy.deepcopy(packet)
    tampered["coverage"]["source_trace_complete_count"] = (
        tampered["coverage"]["source_trace_complete_count"] + 1
    )
    readdressed = readdress_packet(tampered)
    with pytest.raises(ValueError, match="coverage fields do not recompute"):
        validate_packet_semantics(readdressed)


def test_multihop_revision_separates_root_prior_and_revised() -> None:
    fixture = build_multihop_revenue_fixture()
    by_key = {event.source_occurrence_key: event for event in fixture.ledger.events}
    root = by_key["fy2023-revenue-original"]
    prior = by_key["fy2023-revenue-restated"]
    revised = by_key["fy2023-revenue-amendment-c"]
    packet = _build(
        fixture=fixture,
        metrics=("revenue",),
        periods=(PeriodRequest.duration("2023-01-01", "2023-12-31", label="FY2023"),),
        source_event_cutoff="2026-08-05T12:00:02Z",
        system_recorded_cutoff=T3_RECORDED,
        input_digests=PacketEvidenceDigests(),
    )
    hops = [row for row in packet["revisions"] if row["metric_id"] == "revenue"]
    hop1 = next(row for row in hops if row["revision_hop"] == 1)
    hop2 = next(row for row in hops if row["revision_hop"] == 2)
    assert hop1["event_type"] == "restatement"
    assert hop1["root_value"] == hop1["prior_value"] == "1050"
    assert hop1["revised_value"] == "1060"
    assert hop1["root_accession"] == hop1["prior_accession"] == root.source.accession
    assert hop1["revised_accession"] == prior.source.accession
    assert hop1["root_occurrence_id"] == hop1["parent_occurrence_id"] == root.occurrence_id
    assert hop1["revised_occurrence_id"] == prior.occurrence_id
    assert hop1["absolute_delta"] == "10"
    assert hop1["lineage_occurrence_ids"] == [root.occurrence_id, prior.occurrence_id]
    assert hop2["event_type"] == "amendment"
    assert hop2["root_value"] == "1050"
    assert hop2["prior_value"] == "1060"
    assert hop2["revised_value"] == "1070"
    assert hop2["root_accession"] == root.source.accession
    assert hop2["prior_accession"] == prior.source.accession
    assert hop2["revised_accession"] == revised.source.accession
    assert hop2["root_occurrence_id"] == root.occurrence_id
    assert hop2["parent_occurrence_id"] == prior.occurrence_id
    assert hop2["revised_occurrence_id"] == revised.occurrence_id
    assert hop2["absolute_delta"] == "10"
    assert hop2["lineage_occurrence_ids"] == [
        root.occurrence_id,
        prior.occurrence_id,
        revised.occurrence_id,
    ]
    assert hop2["uses_later_reported_revision"] is True
    assert "uses_later_restatement" not in hop2
    assert _cell(packet, "revenue", "FY2023")["value"] == "1070"


def test_canonical_issuer_binds_to_source_native_cik_without_rewriting_raw_identity() -> None:
    fixture = build_synthetic_filing_package_fixture()
    original_occurrence_ids = [event.occurrence_id for event in fixture.ledger.events]
    raw = fixture.ledger.events[0]
    assert raw.source.entity_id == SYNTHETIC_ENTITY_ID
    assert raw.context.entity_identifier == SYNTHETIC_ENTITY_ID
    assert raw.context.entity_scheme == "http://www.sec.gov/CIK"

    entity = EntityInput(
        entity_id=CANONICAL_ISSUER_ID,
        cik=SYNTHETIC_ENTITY_ID,
        ticker="FIP1",
        name="SYNTHETIC FILING PACKAGE CORP",
        identity_basis="synthetic_filing_package_fixture_v1",
        source_entity_id=SYNTHETIC_ENTITY_ID,
    )
    packet = assemble_financial_intelligence_packet(
        entity=entity,
        ledger=fixture.ledger,
        filing_metadata=fixture.filing_metadata,
        query_request=PacketQueryRequest(
            policy=QueryPolicy(
                source_snapshot_at=T3_SOURCE,
                recorded_at=T3_RECORDED,
                selection="latest_known_as_of",
            ),
            metrics=("revenue",),
            periods=(PeriodRequest.duration("2023-01-01", "2023-12-31", label="FY2023"),),
        ),
        metric_registry=load_core_registry(ROOT),
        context=_context(),
        input_digests=PacketEvidenceDigests(),
    )
    assert packet["entity"]["entity_id"] == CANONICAL_ISSUER_ID
    assert packet["entity"]["cik"] == SYNTHETIC_ENTITY_ID
    assert packet["entity"]["source_entity_id"] == SYNTHETIC_ENTITY_ID
    assert packet["entity"]["entity_id"] != packet["entity"]["cik"]
    assert _cell(packet, "revenue", "FY2023")["value"] == "1060"
    assert packet["receipts"]["source_receipt_count"] >= 1
    assert [event.occurrence_id for event in fixture.ledger.events] == original_occurrence_ids
    assert fixture.ledger.events[0].source.entity_id == SYNTHETIC_ENTITY_ID
    assert fixture.ledger.events[0].context.entity_identifier == SYNTHETIC_ENTITY_ID

    foreign_ctx = FactContext(
        context_id="c-cik-as-entity",
        entity_scheme="http://www.sec.gov/CIK",
        entity_identifier="0000000042",
        start="2023-01-01",
        end="2023-12-31",
    )
    foreign_filing = synthetic_filing(
        accession="0000000042-24-000042",
        document_id="cik-as-entity.htm",
        accepted_at="2024-02-15T16:00:00Z",
        recorded_at="2024-02-15T16:05:00Z",
        filed_at="2024-02-15",
        entity_id="0000000042",
    )
    foreign = usd_fact(
        foreign_filing,
        "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
        foreign_ctx,
        "9",
        source_span=(0, 1),
        source_occurrence_key="cik-as-entity-revenue",
    )
    with pytest.raises(ValueError, match="source binding"):
        assemble_financial_intelligence_packet(
            entity=entity,
            ledger=RawFactLedger((*fixture.ledger.events, foreign)),
            filing_metadata=fixture.filing_metadata,
            query_request=PacketQueryRequest(
                policy=QueryPolicy(
                    source_snapshot_at=T3_SOURCE,
                    recorded_at=T3_RECORDED,
                    selection="latest_known_as_of",
                ),
                metrics=("revenue",),
                periods=(PeriodRequest.duration("2023-01-01", "2023-12-31", label="FY2023"),),
            ),
            metric_registry=load_core_registry(ROOT),
            context=_context(),
            input_digests=PacketEvidenceDigests(),
        )

    wrong_binding = replace(entity, source_entity_id="0000000002")
    with pytest.raises(ValueError, match="source binding"):
        assemble_financial_intelligence_packet(
            entity=wrong_binding,
            ledger=fixture.ledger,
            filing_metadata=fixture.filing_metadata,
            query_request=PacketQueryRequest(
                policy=QueryPolicy(
                    source_snapshot_at=T3_SOURCE,
                    recorded_at=T3_RECORDED,
                    selection="latest_known_as_of",
                ),
                metrics=("revenue",),
                periods=(PeriodRequest.duration("2023-01-01", "2023-12-31", label="FY2023"),),
            ),
            metric_registry=load_core_registry(ROOT),
            context=_context(),
            input_digests=PacketEvidenceDigests(),
        )


def test_reconvergent_formula_graph_is_linear_in_nodes_and_edges() -> None:
    layers = 8
    width = 8
    evidence = []
    directs = [_direct_cell(f"leaf-{i}") for i in range(width)]
    previous = [cell["cell_id"] for cell in directs]
    evidence.extend(directs)
    for layer in range(layers - 1, 0, -1):
        current = []
        for i in range(width):
            cell = _formula_cell(f"n-{layer}-{i}", list(previous))
            evidence.append(cell)
            current.append(cell["cell_id"])
        previous = current
    requested = [_formula_cell(f"n-0-{i}", list(previous)) for i in range(width)]
    stats = walk_formula_graph(requested, evidence)
    assert stats.node_count == layers * width + width
    assert stats.edge_count == layers * width * width
    assert stats.node_visits == stats.node_count
    assert stats.edge_visits == stats.edge_count
    assert stats.node_visits <= stats.node_count
    assert stats.edge_visits <= stats.edge_count


def test_request_rejects_unbounded_metric_iterable_before_materializing() -> None:
    period = PeriodRequest.duration("2023-01-01", "2023-12-31", label="FY2023")
    policy = QueryPolicy(
        source_snapshot_at=T3_SOURCE,
        recorded_at=T3_RECORDED,
        selection="latest_known_as_of",
    )

    def infinite_metrics():
        n = 0
        while True:
            yield f"metric_{n}"
            n += 1

    with pytest.raises(ValueError, match="PACKET_MAX_METRICS"):
        PacketQueryRequest(policy=policy, metrics=infinite_metrics(), periods=(period,))

    def infinite_periods():
        n = 0
        while True:
            yield PeriodRequest.duration("2023-01-01", "2023-12-31", label=f"FY{n}")
            n += 1

    with pytest.raises(ValueError, match="PACKET_MAX_PERIODS"):
        PacketQueryRequest(
            policy=policy,
            metrics=("revenue",),
            periods=infinite_periods(),
        )
    assert PACKET_MAX_METRICS >= 1
    assert PACKET_MAX_PERIODS >= 1


def test_future_rule_does_not_rewrite_historical_packet_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _register_future_concept(monkeypatch)
    registry = load_core_registry(ROOT)
    cutoff = T3_RECORDED
    fixture = load_filing_package_fixture(LEDGER_PATH)
    r1_packet = assemble_financial_intelligence_packet(
        entity=fixture.entity,
        ledger=fixture.ledger,
        filing_metadata=fixture.filing_metadata,
        query_request=PacketQueryRequest(
            policy=QueryPolicy(
                source_snapshot_at=T3_SOURCE,
                recorded_at=cutoff,
                selection="latest_known_as_of",
            ),
            metrics=DEFAULT_REQUESTED_METRICS,
            periods=default_packet_periods(),
        ),
        metric_registry=registry,
        context=_context(),
        input_digests=_input_digests(),
    )
    extended = _registry_with_future_revenue_mapping(
        datetime(2026, 8, 7, tzinfo=timezone.utc)
    )
    r2_at_t = assemble_financial_intelligence_packet(
        entity=fixture.entity,
        ledger=fixture.ledger,
        filing_metadata=fixture.filing_metadata,
        query_request=PacketQueryRequest(
            policy=QueryPolicy(
                source_snapshot_at=T3_SOURCE,
                recorded_at=cutoff,
                selection="latest_known_as_of",
            ),
            metrics=DEFAULT_REQUESTED_METRICS,
            periods=default_packet_periods(),
        ),
        metric_registry=extended,
        context=_context(),
        input_digests=_input_digests(),
    )
    assert r1_packet["cells"] == r2_at_t["cells"]
    assert r1_packet["evidence_cells"] == r2_at_t["evidence_cells"]
    assert r1_packet["revisions"] == r2_at_t["revisions"]
    assert r1_packet["governance"]["governance_bundle_id"] == r2_at_t["governance"]["governance_bundle_id"]
    assert canonical_packet_bytes(r1_packet) == canonical_packet_bytes(r2_at_t)
    assert r1_packet["content_sha256"] == r2_at_t["content_sha256"]
    assert r1_packet["packet_id"] == r2_at_t["packet_id"]
    later = assemble_financial_intelligence_packet(
        entity=fixture.entity,
        ledger=fixture.ledger,
        filing_metadata=fixture.filing_metadata,
        query_request=PacketQueryRequest(
            policy=QueryPolicy(
                source_snapshot_at=T3_SOURCE,
                recorded_at="2026-08-08T00:00:00Z",
                selection="latest_known_as_of",
            ),
            metrics=DEFAULT_REQUESTED_METRICS,
            periods=default_packet_periods(),
        ),
        metric_registry=extended,
        context=_context(),
        input_digests=_input_digests(),
    )
    assert later["governance"]["governance_bundle_id"] != r1_packet["governance"]["governance_bundle_id"]


def test_future_metric_contract_does_not_rewrite_historical_packet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _register_future_concept(monkeypatch)
    r1 = load_core_registry(ROOT)
    assert FUTURE_METRIC_ID not in r1.metric_ids
    cutoff = T3_RECORDED
    fixture = load_filing_package_fixture(LEDGER_PATH)
    request = PacketQueryRequest(
        policy=QueryPolicy(
            source_snapshot_at=T3_SOURCE,
            recorded_at=cutoff,
            selection="latest_known_as_of",
        ),
        metrics=DEFAULT_REQUESTED_METRICS + (FUTURE_METRIC_ID,),
        periods=default_packet_periods(),
    )
    r1_packet = assemble_financial_intelligence_packet(
        entity=fixture.entity,
        ledger=fixture.ledger,
        filing_metadata=fixture.filing_metadata,
        query_request=request,
        metric_registry=r1,
        context=_context(),
        input_digests=_input_digests(),
    )
    r2 = _registry_with_future_metric_contract(
        datetime(2026, 8, 7, tzinfo=timezone.utc)
    )
    assert FUTURE_METRIC_ID in r2.metric_ids
    r2_at_t = assemble_financial_intelligence_packet(
        entity=fixture.entity,
        ledger=fixture.ledger,
        filing_metadata=fixture.filing_metadata,
        query_request=request,
        metric_registry=r2,
        context=_context(),
        input_digests=_input_digests(),
    )
    future_cells = [
        cell for cell in r1_packet["cells"] if cell["metric_id"] == FUTURE_METRIC_ID
    ]
    assert future_cells
    assert all(cell["label"] == FUTURE_METRIC_ID for cell in future_cells)
    assert all(cell["statement_family"] == "unmapped" for cell in future_cells)
    assert all(cell["non_value_state"] == "unsupported" for cell in future_cells)
    assert r1_packet["cells"] == r2_at_t["cells"]
    assert r1_packet["evidence_cells"] == r2_at_t["evidence_cells"]
    assert r1_packet["revisions"] == r2_at_t["revisions"]
    assert r1_packet["governance"]["governance_bundle_id"] == r2_at_t["governance"]["governance_bundle_id"]
    assert canonical_packet_bytes(r1_packet) == canonical_packet_bytes(r2_at_t)
    assert r1_packet["content_sha256"] == r2_at_t["content_sha256"]
    assert r1_packet["packet_id"] == r2_at_t["packet_id"]
    historical_blob = canonical_packet_bytes(r1_packet).decode("utf-8")
    assert FUTURE_METRIC_LABEL not in historical_blob
    expected_statement = r2.metric(FUTURE_METRIC_ID).presentation_constraints.statement
    assert expected_statement != "unmapped"
    monkeypatch.setattr(registry_module, "MAX_GOVERNANCE_BUNDLE_METRICS", 51)
    later_request = PacketQueryRequest(
        policy=QueryPolicy(
            source_snapshot_at=T3_SOURCE,
            recorded_at="2026-08-08T00:00:00Z",
            selection="latest_known_as_of",
        ),
        metrics=DEFAULT_REQUESTED_METRICS + (FUTURE_METRIC_ID,),
        periods=default_packet_periods(),
    )
    later = assemble_financial_intelligence_packet(
        entity=fixture.entity,
        ledger=fixture.ledger,
        filing_metadata=fixture.filing_metadata,
        query_request=later_request,
        metric_registry=r2,
        context=_context(),
        input_digests=_input_digests(),
    )
    later_future = [
        cell for cell in later["cells"] if cell["metric_id"] == FUTURE_METRIC_ID
    ]
    assert later_future
    assert all(cell["label"] == FUTURE_METRIC_LABEL for cell in later_future)
    assert all(cell["statement_family"] == expected_statement for cell in later_future)
    assert all(cell["non_value_state"] != "unsupported" for cell in later_future)
    assert later["governance"]["governance_bundle_id"] != r1_packet["governance"]["governance_bundle_id"]
    assert later["content_sha256"] != r1_packet["content_sha256"]
    assert later["packet_id"] != r1_packet["packet_id"]


def _mini_revision_fixture(
    *,
    child_recorded: str,
    parent_recorded: str,
    hops: int = 1,
    concept: str = "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
):
    fy2023 = FactContext(
        context_id="c-fy2023",
        entity_scheme="http://www.sec.gov/CIK",
        entity_identifier=SYNTHETIC_ENTITY_ID,
        start="2023-01-01",
        end="2023-12-31",
    )
    original_filing = synthetic_filing(
        accession="0000999999-24-000010",
        document_id="fip1-20231231.htm",
        accepted_at="2024-02-15T16:00:00Z",
        recorded_at=parent_recorded,
        filed_at="2024-02-15",
    )
    restated_filing = synthetic_filing(
        accession="0000999999-25-000010",
        document_id="fip1-20241231.htm",
        accepted_at="2025-02-15T16:00:00Z",
        recorded_at=child_recorded,
        filed_at="2025-02-15",
    )
    original = usd_fact(
        original_filing,
        concept,
        fy2023,
        "1050",
        source_span=(0, 1),
        source_occurrence_key="fy2023-revenue-original",
        recorded_at=parent_recorded,
    )
    restated = usd_fact(
        restated_filing,
        concept,
        fy2023,
        "1060",
        source_span=(0, 2),
        source_occurrence_key="fy2023-revenue-restated",
        event_type=FactEventType.RESTATEMENT,
        revision_of=original.occurrence_id,
        recorded_at=child_recorded,
    )
    events = [original, restated]
    filings = {"24-000010": original_filing, "25-000010": restated_filing}
    if hops >= 2:
        third_filing = synthetic_filing(
            accession="0000999999-25-000011",
            document_id="fip1-2023-amend.htm",
            accepted_at="2025-11-15T16:00:00Z",
            recorded_at="2026-08-04T18:00:00Z",
            filed_at="2025-11-15",
        )
        third = usd_fact(
            third_filing,
            concept,
            fy2023,
            "1070",
            source_span=(0, 3),
            source_occurrence_key="fy2023-revenue-amendment-c",
            event_type=FactEventType.AMENDMENT,
            revision_of=restated.occurrence_id,
            recorded_at="2026-08-04T18:00:00Z",
        )
        events.append(third)
        filings["25-000011"] = third_filing
    if hops >= 3:
        fourth_filing = synthetic_filing(
            accession="0000999999-25-000012",
            document_id="fip1-2023-amend-d.htm",
            accepted_at="2025-12-15T16:00:00Z",
            recorded_at="2026-08-04T19:00:00Z",
            filed_at="2025-12-15",
        )
        fourth = usd_fact(
            fourth_filing,
            concept,
            fy2023,
            "1080",
            source_span=(0, 4),
            source_occurrence_key="fy2023-revenue-amendment-d",
            event_type=FactEventType.AMENDMENT,
            revision_of=events[-1].occurrence_id,
            recorded_at="2026-08-04T19:00:00Z",
        )
        events.append(fourth)
        filings["25-000012"] = fourth_filing
    if hops > 3:
        base_accepted = datetime(2025, 12, 15, 16, 0, tzinfo=timezone.utc)
        base_recorded = datetime(2026, 8, 4, 19, 0, tzinfo=timezone.utc)
        for hop in range(4, hops + 1):
            accepted = utc_text(base_accepted + timedelta(minutes=hop))
            recorded = utc_text(base_recorded + timedelta(minutes=hop))
            accession = f"0000999999-25-{hop + 10:06d}"
            extra_filing = synthetic_filing(
                accession=accession,
                document_id=f"fip1-2023-amend-{hop:03d}.htm",
                accepted_at=accepted,
                recorded_at=recorded,
                filed_at="2025-12-15",
            )
            extra = usd_fact(
                extra_filing,
                concept,
                fy2023,
                str(1080 + hop),
                source_span=(0, hop + 1),
                source_occurrence_key=f"fy2023-revenue-amendment-{hop}",
                event_type=FactEventType.AMENDMENT,
                revision_of=events[-1].occurrence_id,
                recorded_at=recorded,
            )
            events.append(extra)
            filings[accession.split("-", 1)[-1]] = extra_filing
    events_t = tuple(events)
    entity = EntityInput(
        entity_id=SYNTHETIC_ENTITY_ID,
        cik=SYNTHETIC_ENTITY_ID,
        ticker="FIP1",
        name="SYNTHETIC FILING PACKAGE CORP",
        identity_basis="synthetic_filing_package_fixture_v1",
        source_entity_id=SYNTHETIC_ENTITY_ID,
    )
    return FilingPackageFixture(
        entity=entity,
        ledger=RawFactLedger(events_t),
        filing_metadata=_metadata_for(events_t, filings),
    )


def test_revision_row_requires_complete_lineage_on_both_clocks() -> None:
    fixture = _mini_revision_fixture(
        child_recorded="2026-08-05T10:00:00Z",
        parent_recorded="2026-08-05T11:00:00Z",
    )
    before_parent = assemble_financial_intelligence_packet(
        entity=fixture.entity,
        ledger=fixture.ledger,
        filing_metadata=fixture.filing_metadata,
        query_request=PacketQueryRequest(
            policy=QueryPolicy(
                source_snapshot_at="2025-12-31T23:59:59Z",
                recorded_at="2026-08-05T10:30:00Z",
                selection="latest_known_as_of",
            ),
            metrics=("revenue",),
            periods=(PeriodRequest.duration("2023-01-01", "2023-12-31", label="FY2023"),),
        ),
        metric_registry=load_core_registry(ROOT),
        context=_context(),
        input_digests=PacketEvidenceDigests(),
    )
    assert before_parent["revisions"] == []
    assert _cell(before_parent, "revenue", "FY2023")["value"] is None
    blob = canonical_packet_bytes(before_parent).decode("utf-8")
    assert fixture.ledger.events[1].occurrence_id not in blob
    after_parent = assemble_financial_intelligence_packet(
        entity=fixture.entity,
        ledger=fixture.ledger,
        filing_metadata=fixture.filing_metadata,
        query_request=PacketQueryRequest(
            policy=QueryPolicy(
                source_snapshot_at="2025-12-31T23:59:59Z",
                recorded_at="2026-08-05T11:01:00Z",
                selection="latest_known_as_of",
            ),
            metrics=("revenue",),
            periods=(PeriodRequest.duration("2023-01-01", "2023-12-31", label="FY2023"),),
        ),
        metric_registry=load_core_registry(ROOT),
        context=_context(),
        input_digests=PacketEvidenceDigests(),
    )
    assert len(after_parent["revisions"]) == 1
    assert after_parent["revisions"][0]["revised_value"] == "1060"


def test_normalized_revision_waits_for_cutoff_visible_mapping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _register_future_concept(monkeypatch)
    fixture = _mini_revision_fixture(
        child_recorded="2026-08-04T12:00:00Z",
        parent_recorded="2024-02-15T16:05:00Z",
        concept=FUTURE_CONCEPT_QNAME,
    )
    delayed = _registry_with_future_revenue_mapping(
        datetime(2026, 8, 6, tzinfo=timezone.utc)
    )
    before = assemble_financial_intelligence_packet(
        entity=fixture.entity,
        ledger=fixture.ledger,
        filing_metadata=fixture.filing_metadata,
        query_request=PacketQueryRequest(
            policy=QueryPolicy(
                source_snapshot_at="2025-12-31T23:59:59Z",
                recorded_at="2026-08-05T12:00:02Z",
                selection="latest_known_as_of",
            ),
            metrics=("revenue",),
            periods=(PeriodRequest.duration("2023-01-01", "2023-12-31", label="FY2023"),),
        ),
        metric_registry=delayed,
        context=_context(),
        input_digests=PacketEvidenceDigests(),
    )
    assert [row for row in before["revisions"] if row["metric_id"] == "revenue"] == []
    after = assemble_financial_intelligence_packet(
        entity=fixture.entity,
        ledger=fixture.ledger,
        filing_metadata=fixture.filing_metadata,
        query_request=PacketQueryRequest(
            policy=QueryPolicy(
                source_snapshot_at="2025-12-31T23:59:59Z",
                recorded_at="2026-08-07T00:00:00Z",
                selection="latest_known_as_of",
            ),
            metrics=("revenue",),
            periods=(PeriodRequest.duration("2023-01-01", "2023-12-31", label="FY2023"),),
        ),
        metric_registry=delayed,
        context=_context(),
        input_digests=PacketEvidenceDigests(),
    )
    rows = [row for row in after["revisions"] if row["metric_id"] == "revenue"]
    assert len(rows) == 1
    assert rows[0]["revised_value"] == "1060"


def test_readdressed_full_body_tamper_matrix_is_rejected() -> None:
    packet = _build()
    mutations = {
        "entity.name": lambda body: body["entity"].__setitem__("name", "FORGED CORP"),
        "entity.identity_basis": lambda body: body["entity"].__setitem__(
            "identity_basis", "forged_basis"
        ),
        "entity.source_entity_id": lambda body: body["entity"].__setitem__(
            "source_entity_id", "0000000002"
        ),
        "periods": lambda body: body["periods"].__setitem__(0, {**body["periods"][0], "label": "FYX"}),
        "governance.query_engine_version": lambda body: body["governance"].__setitem__(
            "query_engine_version", "forged-engine"
        ),
        "governance.governance_bundle_id": lambda body: body["governance"].__setitem__(
            "governance_bundle_id", "0" * 64
        ),
        "limitations": lambda body: body["limitations"].__setitem__(0, "forged limitation"),
        "authority": lambda body: body["authority"].__setitem__("class", "tradeable"),
        "disclosure_changes": lambda body: body.__setitem__("disclosure_changes", [{"x": 1}]),
        "receipts": lambda body: body["receipts"].__setitem__("source_receipt_count", 0),
    }
    for name, mutate in mutations.items():
        tampered = copy.deepcopy(packet)
        try:
            mutate(tampered)
        except Exception as exc:  # noqa: BLE001
            raise AssertionError(f"mutation {name} failed to apply") from exc
        if name == "authority":
            with pytest.raises(ValueError):
                validate_packet_semantics(readdress_packet(tampered))
            continue
        if name == "receipts":
            with pytest.raises(ValueError, match="source_receipt_count|packet body"):
                readdressed = readdress_packet(tampered)
                try:
                    validate_packet_semantics(readdressed)
                except ValueError:
                    raise
                _against(readdressed)
            continue
        readdressed = readdress_packet(tampered)
        if name != "disclosure_changes":
            validate_packet_semantics(readdressed)
        with pytest.raises(ValueError, match="packet body|schema|authority|disclosure"):
            _against(readdressed)
    assert packet["disclosure_changes"] == []


def test_revision_ceiling_fails_during_accumulation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(packet_module, "PACKET_MAX_REVISIONS", 1)
    one = _mini_revision_fixture(
        child_recorded="2026-08-04T12:00:00Z",
        parent_recorded="2024-02-15T16:05:00Z",
        hops=1,
    )
    assemble_financial_intelligence_packet(
        entity=one.entity,
        ledger=one.ledger,
        filing_metadata=one.filing_metadata,
        query_request=PacketQueryRequest(
            policy=QueryPolicy(
                source_snapshot_at=T3_SOURCE,
                recorded_at=T3_RECORDED,
                selection="latest_known_as_of",
            ),
            metrics=("revenue",),
            periods=(PeriodRequest.duration("2023-01-01", "2023-12-31", label="FY2023"),),
        ),
        metric_registry=load_core_registry(ROOT),
        context=_context(),
        input_digests=PacketEvidenceDigests(),
    )
    two = _mini_revision_fixture(
        child_recorded="2026-08-04T12:00:00Z",
        parent_recorded="2024-02-15T16:05:00Z",
        hops=2,
    )
    with pytest.raises(ValueError, match="PACKET_MAX_REVISIONS"):
        assemble_financial_intelligence_packet(
            entity=two.entity,
            ledger=two.ledger,
            filing_metadata=two.filing_metadata,
            query_request=PacketQueryRequest(
                policy=QueryPolicy(
                    source_snapshot_at=T3_SOURCE,
                    recorded_at=T3_RECORDED,
                    selection="latest_known_as_of",
                ),
                metrics=("revenue",),
                periods=(PeriodRequest.duration("2023-01-01", "2023-12-31", label="FY2023"),),
            ),
            metric_registry=load_core_registry(ROOT),
            context=_context(),
            input_digests=PacketEvidenceDigests(),
        )


def test_packet_refuses_revision_lineage_deeper_than_v1_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(packet_module, "PACKET_MAX_REVISION_LINEAGE_DEPTH", 2)
    within = _mini_revision_fixture(
        child_recorded="2026-08-04T12:00:00Z",
        parent_recorded="2024-02-15T16:05:00Z",
        hops=2,
    )
    assemble_financial_intelligence_packet(
        entity=within.entity,
        ledger=within.ledger,
        filing_metadata=within.filing_metadata,
        query_request=PacketQueryRequest(
            policy=QueryPolicy(
                source_snapshot_at=T3_SOURCE,
                recorded_at=T3_RECORDED,
                selection="latest_known_as_of",
            ),
            metrics=("revenue",),
            periods=(PeriodRequest.duration("2023-01-01", "2023-12-31", label="FY2023"),),
        ),
        metric_registry=load_core_registry(ROOT),
        context=_context(),
        input_digests=PacketEvidenceDigests(),
    )
    too_deep = _mini_revision_fixture(
        child_recorded="2026-08-04T12:00:00Z",
        parent_recorded="2024-02-15T16:05:00Z",
        hops=3,
    )
    assert too_deep.ledger.lineage_depth(too_deep.ledger.events[-1].occurrence_id) == 3
    with pytest.raises(ValueError, match="PACKET_MAX_REVISION_LINEAGE_DEPTH"):
        assemble_financial_intelligence_packet(
            entity=too_deep.entity,
            ledger=too_deep.ledger,
            filing_metadata=too_deep.filing_metadata,
            query_request=PacketQueryRequest(
                policy=QueryPolicy(
                    source_snapshot_at=T3_SOURCE,
                    recorded_at=T3_RECORDED,
                    selection="latest_known_as_of",
                ),
                metrics=("revenue",),
                periods=(PeriodRequest.duration("2023-01-01", "2023-12-31", label="FY2023"),),
            ),
            metric_registry=load_core_registry(ROOT),
            context=_context(),
            input_digests=PacketEvidenceDigests(),
        )


def _assemble_revision_packet(fixture) -> dict:
    return assemble_financial_intelligence_packet(
        entity=fixture.entity,
        ledger=fixture.ledger,
        filing_metadata=fixture.filing_metadata,
        query_request=PacketQueryRequest(
            policy=QueryPolicy(
                source_snapshot_at=T3_SOURCE,
                recorded_at=T3_RECORDED,
                selection="latest_known_as_of",
            ),
            metrics=("revenue",),
            periods=(PeriodRequest.duration("2023-01-01", "2023-12-31", label="FY2023"),),
        ),
        metric_registry=load_core_registry(ROOT),
        context=_context(),
        input_digests=PacketEvidenceDigests(),
    )


def test_packet_accepts_real_v1_revision_lineage_depth_63() -> None:
    schema = load_packet_schema(SCHEMA_PATH)
    revision_schema = schema["$defs"]["revision"]["properties"]
    assert PACKET_MAX_REVISION_LINEAGE_DEPTH == 63
    assert revision_schema["revision_hop"]["maximum"] == 63
    assert revision_schema["lineage_occurrence_ids"]["maxItems"] == 64
    fixture = _mini_revision_fixture(
        child_recorded="2026-08-04T12:00:00Z",
        parent_recorded="2024-02-15T16:05:00Z",
        hops=63,
    )
    tip = fixture.ledger.events[-1]
    assert fixture.ledger.lineage_depth(tip.occurrence_id) == 63
    packet = _assemble_revision_packet(fixture)
    validate_packet(packet, schema)
    hops = packet["revisions"]
    deepest = max(hops, key=lambda row: row["revision_hop"])
    assert deepest["revision_hop"] == 63
    assert len(deepest["lineage_occurrence_ids"]) == 64
    assert deepest["revised_occurrence_id"] == tip.occurrence_id
    assert hops[-1]["revision_hop"] == 63


def test_packet_refuses_real_v1_revision_lineage_depth_64(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schema = load_packet_schema(SCHEMA_PATH)
    assert PACKET_MAX_REVISION_LINEAGE_DEPTH == 63
    assert schema["$defs"]["revision"]["properties"]["revision_hop"]["maximum"] == 63
    fixture = _mini_revision_fixture(
        child_recorded="2026-08-04T12:00:00Z",
        parent_recorded="2024-02-15T16:05:00Z",
        hops=64,
    )
    tip = fixture.ledger.events[-1]
    assert fixture.ledger.lineage_depth(tip.occurrence_id) == 64
    emitted_hops: list[int] = []
    original_append = packet_module._append_bounded

    def _record_append(records, item, *, maximum, message):
        hop = item.get("revision_hop") if isinstance(item, dict) else None
        if hop is not None:
            emitted_hops.append(hop)
        return original_append(records, item, maximum=maximum, message=message)

    monkeypatch.setattr(packet_module, "_append_bounded", _record_append)
    with pytest.raises(
        ValueError,
        match=r"revision lineage depth exceeds PACKET_MAX_REVISION_LINEAGE_DEPTH 63",
    ):
        _assemble_revision_packet(fixture)
    assert 64 not in emitted_hops
    assert emitted_hops
    assert max(emitted_hops) == 63


def test_packet_revision_lookup_is_bounded_independently_of_row_ceiling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    emitting = _mini_revision_fixture(
        child_recorded="2026-08-04T12:00:00Z",
        parent_recorded="2024-02-15T16:05:00Z",
        hops=1,
    )
    noise_filing = synthetic_filing(
        accession="0000999999-99-000099",
        document_id="fip1-noise.htm",
        accepted_at="2024-02-15T16:00:00Z",
        recorded_at="2024-02-15T16:05:00Z",
        filed_at="2024-02-15",
    )
    non_emitting_revisions = 2048
    noise_events: list = []
    for index in range(non_emitting_revisions):
        ctx = FactContext(
            context_id=f"c-noise-{index}",
            entity_scheme="http://www.sec.gov/CIK",
            entity_identifier=SYNTHETIC_ENTITY_ID,
            start="1999-01-01",
            end="1999-12-31",
        )
        root = usd_fact(
            noise_filing,
            "custom:AdversarialRevisionNoise",
            ctx,
            "1",
            source_span=(index * 2, index * 2 + 1),
            source_occurrence_key=f"noise-{index}-root",
        )
        child = usd_fact(
            noise_filing,
            "custom:AdversarialRevisionNoise",
            ctx,
            "2",
            source_span=(index * 2 + 1, index * 2 + 2),
            source_occurrence_key=f"noise-{index}-child",
            event_type=FactEventType.RESTATEMENT,
            revision_of=root.occurrence_id,
        )
        noise_events.extend((root, child))
    events = emitting.ledger.events + tuple(noise_events)
    ledger = RawFactLedger(events)
    metadata = dict(emitting.filing_metadata)
    for event in noise_events:
        metadata[event.occurrence_id] = {
            "accession": event.source.accession,
            "document_id": event.source.document_id,
            "source_body_sha256": event.source.body_sha256,
            "available_at": utc_text(event.clocks.recorded_at),
            "form": "10-K",
            "filed_at": "2024-02-15",
        }
    chain_calls: list[str] = []
    original_chain = RawFactLedger.revision_chain

    def counted_chain(self, occurrence_id, *args, **kwargs):
        chain_calls.append(occurrence_id)
        return original_chain(self, occurrence_id, *args, **kwargs)

    monkeypatch.setattr(RawFactLedger, "revision_chain", counted_chain)
    index = ledger._events_by_id
    packet = assemble_financial_intelligence_packet(
        entity=emitting.entity,
        ledger=ledger,
        filing_metadata=metadata,
        query_request=PacketQueryRequest(
            policy=QueryPolicy(
                source_snapshot_at=T3_SOURCE,
                recorded_at=T3_RECORDED,
                selection="latest_known_as_of",
            ),
            metrics=("revenue",),
            periods=(PeriodRequest.duration("2023-01-01", "2023-12-31", label="FY2023"),),
        ),
        metric_registry=load_core_registry(ROOT),
        context=_context(),
        input_digests=PacketEvidenceDigests(),
    )
    emitting_child = emitting.ledger.events[1].occurrence_id
    assert ledger._events_by_id is index
    assert len(index) == len(events)
    assert set(chain_calls) == {emitting_child}
    assert 1 <= len(chain_calls) <= 2
    assert len(packet["revisions"]) == 1
    assert len(packet["revisions"]) < PACKET_MAX_REVISIONS
    assert non_emitting_revisions > PACKET_MAX_REVISIONS
    assert PACKET_MAX_REVISION_LINEAGE_DEPTH >= 1


def test_extension_ceiling_fails_during_accumulation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(packet_module, "PACKET_MAX_UNMAPPED_EXTENSIONS", 1)
    packet = _build(metrics=("CustomerCount",), periods=(PeriodRequest.instant("2024-12-31", label="2024-12-31"),))
    assert packet["coverage"]["unmapped_extension_concept_count"] == 1
    monkeypatch.setattr(packet_module, "PACKET_MAX_UNMAPPED_EXTENSIONS", 0)
    with pytest.raises(ValueError, match="PACKET_MAX_UNMAPPED_EXTENSIONS"):
        _build(metrics=("CustomerCount",), periods=(PeriodRequest.instant("2024-12-31", label="2024-12-31"),))


def _direct_cell(cell_id: str) -> dict:
    return {
        "cell_id": cell_id,
        "metric_id": cell_id,
        "value": "1",
        "non_value_state": None,
        "provenance_kind": "direct",
        "dependency_cell_ids": [],
        "source_occurrence_ids": [f"occ-{cell_id}"],
        "accession": "0000999999-24-000010",
        "source_digest": "a" * 64,
        "mapping_rule_id": "map.x",
        "mapping_rule_digest": "b" * 64,
        "period": {"label": "FY2023"},
        "coverage_state": "source_trace_complete",
    }


def _formula_cell(cell_id: str, deps: list[str]) -> dict:
    return {
        "cell_id": cell_id,
        "metric_id": cell_id,
        "value": "1",
        "non_value_state": None,
        "provenance_kind": "formula",
        "dependency_cell_ids": deps,
        "formula_rule_id": "formula.x",
        "formula_rule_digest": "c" * 64,
        "period": {"label": "FY2023"},
        "coverage_state": "source_trace_complete",
    }
