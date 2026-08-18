"""FIF-1R3 semantic closure: re-addressed truth, revision vocabulary, identity, graph bounds."""
from __future__ import annotations

import copy
from dataclasses import replace

import pytest

from engine.fundamental_forensics.financial_intelligence_packet import (
    DEFAULT_REQUESTED_METRICS,
    PACKET_MAX_METRICS,
    EntityInput,
    FilingPackageFixture,
    PacketEvidenceDigests,
    PacketQueryRequest,
    assemble_financial_intelligence_packet,
    default_packet_periods,
    load_core_registry,
    load_filing_package_fixture,
    readdress_packet,
    validate_packet_against_build_input,
    validate_packet_semantics,
    walk_formula_graph,
)
from engine.fundamental_forensics.query import PeriodRequest, QueryPolicy
from engine.fundamental_forensics.raw_ledger import RawFactLedger
from engine.fundamental_forensics.synthetic_filing_package import (
    SYNTHETIC_ENTITY_ID,
    build_multihop_revenue_fixture,
    build_synthetic_filing_package_fixture,
    filing as synthetic_filing,
    usd_fact,
)
from tests.test_fundamental_forensics_financial_intelligence_packet import (
    ROOT,
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
from engine.fundamental_forensics.raw_ledger import FactContext


CANONICAL_ISSUER_ID = "mmx.issuer.fip1"


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
    with pytest.raises(ValueError, match="requested cells do not match query-kernel result"):
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
    with pytest.raises(ValueError, match="requested cells do not match query-kernel result"):
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
    with pytest.raises(ValueError, match="requested cells do not match query-kernel result"):
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
    with pytest.raises(ValueError, match="query-kernel result|governed formula"):
        _against(readdressed)


def test_readdressed_forged_visible_query_is_rejected() -> None:
    packet = _build()
    tampered = copy.deepcopy(packet)
    tampered["query"]["source_event_cutoff"] = "2024-12-31T23:59:59Z"
    readdressed = readdress_packet(tampered)
    validate_packet_semantics(readdressed)
    with pytest.raises(ValueError, match="packet query does not match supplied request"):
        _against(readdressed)
    policy_tampered = copy.deepcopy(packet)
    policy_tampered["query"]["policy"] = "as_reported"
    readdressed = readdress_packet(policy_tampered)
    with pytest.raises(ValueError, match="packet query does not match supplied request"):
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


def test_entity_id_need_not_equal_cik_and_does_not_leak() -> None:
    EntityInput(
        entity_id=CANONICAL_ISSUER_ID,
        cik=SYNTHETIC_ENTITY_ID,
        ticker="FIP1",
        name="SYNTHETIC FILING PACKAGE CORP",
        identity_basis="synthetic_filing_package_fixture_v1",
    )
    remapped = _remap_fixture_entity(build_synthetic_filing_package_fixture(), CANONICAL_ISSUER_ID)
    assert remapped.entity.entity_id == CANONICAL_ISSUER_ID
    assert remapped.entity.cik == SYNTHETIC_ENTITY_ID
    packet = assemble_financial_intelligence_packet(
        entity=remapped.entity,
        ledger=remapped.ledger,
        filing_metadata=remapped.filing_metadata,
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
    assert packet["entity"]["entity_id"] != packet["entity"]["cik"]
    assert _cell(packet, "revenue", "FY2023")["value"] == "1060"

    foreign_ctx = FactContext(
        context_id="c-cik-as-entity",
        entity_scheme="http://www.sec.gov/CIK",
        entity_identifier=SYNTHETIC_ENTITY_ID,
        start="2023-01-01",
        end="2023-12-31",
    )
    foreign_filing = synthetic_filing(
        accession="0000999999-24-000042",
        document_id="cik-as-entity.htm",
        accepted_at="2024-02-15T16:00:00Z",
        recorded_at="2024-02-15T16:05:00Z",
        filed_at="2024-02-15",
        entity_id=SYNTHETIC_ENTITY_ID,
    )
    foreign = usd_fact(
        foreign_filing,
        "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
        foreign_ctx,
        "9",
        source_span=(0, 1),
        source_occurrence_key="cik-as-entity-revenue",
    )
    with pytest.raises(ValueError, match="entity"):
        assemble_financial_intelligence_packet(
            entity=remapped.entity,
            ledger=RawFactLedger((*remapped.ledger.events, foreign)),
            filing_metadata=remapped.filing_metadata,
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


def _remap_fixture_entity(fixture: FilingPackageFixture, canonical_id: str) -> FilingPackageFixture:
    remaining = list(fixture.ledger.events)
    old_to_new: dict[str, str] = {}
    new_by_old: dict[str, object] = {}
    while remaining:
        progress = []
        leftover = []
        for event in remaining:
            if event.revision_of and event.revision_of not in old_to_new:
                leftover.append(event)
                continue
            new_event = replace(
                event,
                source=replace(event.source, entity_id=canonical_id),
                context=replace(event.context, entity_identifier=canonical_id),
                revision_of=old_to_new[event.revision_of] if event.revision_of else None,
                occurrence_id=None,
            )
            old_to_new[event.occurrence_id] = new_event.occurrence_id
            new_by_old[event.occurrence_id] = new_event
            progress.append(event)
        if not progress:
            raise AssertionError("revision cycle while remapping entity_id")
        remaining = leftover
    new_events = tuple(new_by_old[event.occurrence_id] for event in fixture.ledger.events)
    new_meta = {
        old_to_new[old_id]: dict(payload)
        for old_id, payload in fixture.filing_metadata.items()
    }
    return FilingPackageFixture(
        entity=replace(fixture.entity, entity_id=canonical_id),
        ledger=RawFactLedger(new_events),
        filing_metadata=new_meta,
    )


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
