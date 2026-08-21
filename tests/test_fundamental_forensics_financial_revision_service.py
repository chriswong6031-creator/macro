"""FIF-2B: cutoff-safe revision projection over the frozen FIP assembler."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from dataclasses import replace
from datetime import datetime, timezone

from engine.fundamental_forensics.financial_intelligence_packet import (
    EntityInput,
    PacketEvidenceDigests,
    PacketQueryRequest,
    assemble_financial_intelligence_packet,
    canonical_json,
    sha256_file,
)
from engine.fundamental_forensics.query import PeriodRequest, QueryPolicy
from engine.fundamental_forensics.query_service import (
    CanonicalEntityBinding,
    FinancialQueryAdmissionError,
    FinancialQueryDataset,
    FinancialQueryUnavailableError,
    UnavailableFinancialQueryProvider,
    execute_financial_query,
    fip1_fixture_dataset,
)
from engine.fundamental_forensics.revision_service import (
    FinancialPacketDataset,
    UnavailableFinancialPacketProvider,
    execute_financial_revisions,
    fip1_packet_dataset,
    packet_dataset_from_fixture,
)
from engine.fundamental_forensics.synthetic_filing_package import (
    build_multihop_revenue_fixture,
)

ROOT = Path(__file__).resolve().parents[1]
_REVISION_SCHEMA = "fundamental_forensics.financial_revision_request/v1"
_QUERY_SCHEMA = "fundamental_forensics.financial_query_request/v1"

T0_SOURCE = "2024-01-01T00:00:00Z"
T1_SOURCE = "2024-12-31T23:59:59Z"
T2_SOURCE = "2025-12-31T23:59:59Z"
T2_RECORDED = "2026-08-03T12:00:00Z"
T3_SOURCE = "2025-12-31T23:59:59Z"
T3_RECORDED = "2026-08-05T12:00:02Z"
HOP_C_SOURCE = "2026-08-05T12:00:02Z"
HOP_B_SYSTEM_READY = "2026-08-04T17:59:59Z"
DELAYED_MAPPING_AFTER = "2026-08-07T00:00:00Z"

FY2023 = {"kind": "duration", "start": "2023-01-01", "end": "2023-12-31", "label": "FY2023"}
AR_INSTANT = {"kind": "instant", "start": None, "end": "2023-12-31", "label": "2023-12-31"}
FY2023_PERIOD = PeriodRequest.duration("2023-01-01", "2023-12-31", label="FY2023")
AR_PERIOD = PeriodRequest.instant("2023-12-31", label="2023-12-31")

# FIF-2A / PR #5983 accepted kernel query_hash pins. Shared admission must not move them.
_HASH_AS_REPORTED_T1_T2 = "358d44741632d74ff76dd8771bb78b34295a08d62d2a0a8566a6abe5feac1442"
_HASH_LATEST_KNOWN_T1_T2 = "191c49a37998052f17eec78113b5bd8bf0dcaaa52239c406cdb4c27cda5ad1a7"
_HASH_LATEST_KNOWN_T3 = "83df03e99f570bacfab94fc9373861f14c1895c9aa9435b7dd7249a13c1e67fa"
_HASH_LATEST_RESTATED_T3 = "c1095c7994c67f11ed602d15c2956bc24271cdce4d39d7869ed642713a6ed549"
_HASH_MIXED_T3 = "5513f17260f98d261920d658be25bf319ace90a0580ad8f2e94931c518c5a20b"


def _make_request(
    *,
    schema: str = _REVISION_SCHEMA,
    entity_id: str = "mmx.issuer.fip1",
    policy: dict | None = None,
    metric_ids: list | None = None,
    periods: list | None = None,
) -> bytes:
    if policy is None:
        policy = {
            "selection": "latest_known_as_of",
            "source_snapshot_at": T3_SOURCE,
            "recorded_at": T3_RECORDED,
        }
    if metric_ids is None:
        metric_ids = ["revenue"]
    if periods is None:
        periods = [FY2023]
    return json.dumps(
        {
            "schema": schema,
            "entity_id": entity_id,
            "policy": policy,
            "metric_ids": metric_ids,
            "periods": periods,
        },
        separators=(",", ":"),
    ).encode("utf-8")


def _fip1_provider(resolved_calls: list | None = None):
    dataset = fip1_packet_dataset(ROOT)

    class _Provider:
        def resolve(self, entity_id: str) -> FinancialPacketDataset:
            if resolved_calls is not None:
                resolved_calls.append(entity_id)
            if entity_id == "mmx.issuer.fip1":
                return dataset
            raise FinancialQueryAdmissionError(400, "unknown entity")

    return _Provider()


def _direct_packet(
    *,
    metric_ids: tuple[str, ...],
    periods: tuple[PeriodRequest, ...],
    source_snapshot_at: str,
    recorded_at: str,
    selection: str = "latest_known_as_of",
    dataset: FinancialPacketDataset | None = None,
) -> dict:
    loaded = dataset if dataset is not None else fip1_packet_dataset(ROOT)
    return assemble_financial_intelligence_packet(
        entity=loaded.entity,
        ledger=loaded.ledger,
        filing_metadata=loaded.filing_metadata,
        query_request=PacketQueryRequest(
            policy=QueryPolicy(
                source_snapshot_at=source_snapshot_at,
                recorded_at=recorded_at,
                selection=selection,
            ),
            metrics=metric_ids,
            periods=periods,
        ),
        metric_registry=loaded.registry,
        context=loaded.context,
        input_digests=loaded.input_digests,
    )


def _t3_latest(**kwargs):
    policy = {
        "selection": "latest_known_as_of",
        "source_snapshot_at": T3_SOURCE,
        "recorded_at": T3_RECORDED,
    }
    policy.update(kwargs.pop("policy_update", {}))
    return _make_request(policy=policy, **kwargs)


# ---------------------------------------------------------------------------
# Direct packet vs HTTP projection
# ---------------------------------------------------------------------------


def test_http_revisions_equal_direct_packet_revisions() -> None:
    provider = _fip1_provider()
    body = _t3_latest()
    result = execute_financial_revisions(body=body, provider=provider)
    packet = _direct_packet(
        metric_ids=("revenue",),
        periods=(FY2023_PERIOD,),
        source_snapshot_at=T3_SOURCE,
        recorded_at=T3_RECORDED,
    )
    assert result.envelope["revisions"] == packet["revisions"]
    assert canonical_json(result.envelope["revisions"]) == canonical_json(packet["revisions"])
    assert result.envelope["packet_ref"]["packet_id"] == packet["packet_id"]
    assert result.envelope["packet_ref"]["content_sha256"] == packet["content_sha256"]
    assert (
        result.envelope["packet_ref"]["governance_bundle_id"]
        == packet["governance"]["governance_bundle_id"]
    )


def test_t2_does_not_leak_t3_revision_or_value() -> None:
    body = _make_request(
        policy={
            "selection": "latest_known_as_of",
            "source_snapshot_at": T2_SOURCE,
            "recorded_at": T2_RECORDED,
        }
    )
    result = execute_financial_revisions(body=body, provider=_fip1_provider())
    packet = _direct_packet(
        metric_ids=("revenue",),
        periods=(FY2023_PERIOD,),
        source_snapshot_at=T2_SOURCE,
        recorded_at=T2_RECORDED,
    )
    assert packet["revisions"] == []
    assert result.envelope["revisions"] == []
    blob = result.body.decode("utf-8")
    assert "1060" not in blob
    assert result.envelope["revisions"] == packet["revisions"]


def test_t3_emits_1050_to_1060_revenue_revision() -> None:
    result = execute_financial_revisions(body=_t3_latest(), provider=_fip1_provider())
    rows = [row for row in result.envelope["revisions"] if row["metric_id"] == "revenue"]
    assert rows
    revenue = rows[0]
    assert revenue["root_value"] == "1050"
    assert revenue["prior_value"] == "1050"
    assert revenue["revised_value"] == "1060"
    assert revenue["revision_hop"] == 1
    assert "1060" in result.body.decode("utf-8")


def test_t3_accounts_receivable_revision_matches_packet() -> None:
    body = _t3_latest(
        metric_ids=["revenue", "accounts_receivable_net"],
        periods=[FY2023, AR_INSTANT],
    )
    result = execute_financial_revisions(body=body, provider=_fip1_provider())
    packet = _direct_packet(
        metric_ids=("revenue", "accounts_receivable_net"),
        periods=(FY2023_PERIOD, AR_PERIOD),
        source_snapshot_at=T3_SOURCE,
        recorded_at=T3_RECORDED,
    )
    assert result.envelope["revisions"] == packet["revisions"]
    ar_rows = [row for row in result.envelope["revisions"] if row["metric_id"] == "accounts_receivable_net"]
    assert ar_rows
    assert ar_rows[0]["root_value"] == "120"
    assert ar_rows[0]["revised_value"] == "121"


def test_revenue_only_request_excludes_ar_revisions() -> None:
    result = execute_financial_revisions(body=_t3_latest(), provider=_fip1_provider())
    assert result.envelope["revisions"]
    assert all(row["metric_id"] == "revenue" for row in result.envelope["revisions"])


def test_multihop_preserves_root_prior_revised() -> None:
    fixture = build_multihop_revenue_fixture()
    dataset = packet_dataset_from_fixture(ROOT, fixture)

    class _Provider:
        def resolve(self, entity_id: str) -> FinancialPacketDataset:
            if entity_id != "mmx.issuer.fip1":
                raise FinancialQueryAdmissionError(400, "unknown entity")
            return dataset

    body = _make_request(
        policy={
            "selection": "latest_known_as_of",
            "source_snapshot_at": HOP_C_SOURCE,
            "recorded_at": T3_RECORDED,
        }
    )
    result = execute_financial_revisions(body=body, provider=_Provider())
    packet = _direct_packet(
        metric_ids=("revenue",),
        periods=(FY2023_PERIOD,),
        source_snapshot_at=HOP_C_SOURCE,
        recorded_at=T3_RECORDED,
        dataset=dataset,
    )
    assert result.envelope["revisions"] == packet["revisions"]
    hops = {row["revision_hop"]: row for row in result.envelope["revisions"] if row["metric_id"] == "revenue"}
    assert 1 in hops and 2 in hops
    hop1 = hops[1]
    hop2 = hops[2]
    assert hop1["root_value"] == "1050"
    assert hop1["prior_value"] == "1050"
    assert hop1["revised_value"] == "1060"
    assert hop1["root_occurrence_id"] == hop1["parent_occurrence_id"]
    assert hop2["root_value"] == "1050"
    assert hop2["prior_value"] == "1060"
    assert hop2["revised_value"] == "1070"
    assert hop2["lineage_occurrence_ids"] == [
        hop2["root_occurrence_id"],
        hop2["parent_occurrence_id"],
        hop2["revised_occurrence_id"],
    ]
    assert hop2["root_occurrence_id"] == hop1["root_occurrence_id"]
    assert hop2["parent_occurrence_id"] == hop1["revised_occurrence_id"]
    assert hop2["lineage_occurrence_ids"] != [
        hop2["root_occurrence_id"],
        hop2["revised_occurrence_id"],
    ]


def test_multihop_hides_hop_c_before_lineage_readiness() -> None:
    fixture = build_multihop_revenue_fixture()
    dataset = packet_dataset_from_fixture(ROOT, fixture)

    class _Provider:
        def resolve(self, entity_id: str) -> FinancialPacketDataset:
            return dataset

    body = _make_request(
        policy={
            "selection": "latest_known_as_of",
            "source_snapshot_at": T2_SOURCE,
            "recorded_at": T2_RECORDED,
        }
    )
    result = execute_financial_revisions(body=body, provider=_Provider())
    assert result.envelope["revisions"] == []
    assert "1070" not in result.body.decode("utf-8")


def test_multihop_intermediate_shows_b_hides_c_until_system_ready() -> None:
    fixture = build_multihop_revenue_fixture()
    dataset = packet_dataset_from_fixture(ROOT, fixture)

    class _Provider:
        def resolve(self, entity_id: str) -> FinancialPacketDataset:
            return dataset

    intermediate = _make_request(
        policy={
            "selection": "latest_known_as_of",
            "source_snapshot_at": HOP_C_SOURCE,
            "recorded_at": HOP_B_SYSTEM_READY,
        }
    )
    mid = execute_financial_revisions(body=intermediate, provider=_Provider())
    mid_packet = _direct_packet(
        metric_ids=("revenue",),
        periods=(FY2023_PERIOD,),
        source_snapshot_at=HOP_C_SOURCE,
        recorded_at=HOP_B_SYSTEM_READY,
        dataset=dataset,
    )
    assert mid.envelope["revisions"] == mid_packet["revisions"]
    hops = {
        row["revision_hop"]: row
        for row in mid.envelope["revisions"]
        if row["metric_id"] == "revenue"
    }
    assert 1 in hops
    assert 2 not in hops
    assert hops[1]["revised_value"] == "1060"
    blob = mid.body.decode("utf-8")
    assert "1060" in blob
    assert "1070" not in blob

    later = _make_request(
        policy={
            "selection": "latest_known_as_of",
            "source_snapshot_at": HOP_C_SOURCE,
            "recorded_at": T3_RECORDED,
        }
    )
    after = execute_financial_revisions(body=later, provider=_Provider())
    after_packet = _direct_packet(
        metric_ids=("revenue",),
        periods=(FY2023_PERIOD,),
        source_snapshot_at=HOP_C_SOURCE,
        recorded_at=T3_RECORDED,
        dataset=dataset,
    )
    assert after.envelope["revisions"] == after_packet["revisions"]
    later_hops = {
        row["revision_hop"]: row
        for row in after.envelope["revisions"]
        if row["metric_id"] == "revenue"
    }
    assert 2 in later_hops
    assert later_hops[2]["prior_value"] == "1060"
    assert later_hops[2]["revised_value"] == "1070"


def test_delayed_mapping_hides_revision_until_mapping_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.test_fundamental_forensics_financial_intelligence_packet_r3 import (
        FUTURE_CONCEPT_QNAME,
        _mini_revision_fixture,
        _register_future_concept,
        _registry_with_future_revenue_mapping,
    )

    _register_future_concept(monkeypatch)
    fixture = _mini_revision_fixture(
        child_recorded="2026-08-04T12:00:00Z",
        parent_recorded="2024-02-15T16:05:00Z",
        concept=FUTURE_CONCEPT_QNAME,
    )
    delayed_registry = _registry_with_future_revenue_mapping(
        datetime(2026, 8, 6, tzinfo=timezone.utc)
    )
    dataset = replace(
        packet_dataset_from_fixture(ROOT, fixture),
        registry=delayed_registry,
    )

    class _Provider:
        def resolve(self, entity_id: str) -> FinancialPacketDataset:
            return dataset

    before_body = _make_request(
        policy={
            "selection": "latest_known_as_of",
            "source_snapshot_at": T3_SOURCE,
            "recorded_at": T3_RECORDED,
        }
    )
    before = execute_financial_revisions(body=before_body, provider=_Provider())
    before_packet = _direct_packet(
        metric_ids=("revenue",),
        periods=(FY2023_PERIOD,),
        source_snapshot_at=T3_SOURCE,
        recorded_at=T3_RECORDED,
        dataset=dataset,
    )
    assert before.envelope["revisions"] == before_packet["revisions"] == []
    assert [row for row in before.envelope["revisions"] if row["metric_id"] == "revenue"] == []

    after_body = _make_request(
        policy={
            "selection": "latest_known_as_of",
            "source_snapshot_at": T3_SOURCE,
            "recorded_at": DELAYED_MAPPING_AFTER,
        }
    )
    after = execute_financial_revisions(body=after_body, provider=_Provider())
    after_packet = _direct_packet(
        metric_ids=("revenue",),
        periods=(FY2023_PERIOD,),
        source_snapshot_at=T3_SOURCE,
        recorded_at=DELAYED_MAPPING_AFTER,
        dataset=dataset,
    )
    assert after.envelope["revisions"] == after_packet["revisions"]
    rows = [row for row in after.envelope["revisions"] if row["metric_id"] == "revenue"]
    assert len(rows) == 1
    assert rows[0]["root_value"] == "1050"
    assert rows[0]["prior_value"] == "1050"
    assert rows[0]["revised_value"] == "1060"


def test_future_metric_contract_does_not_change_historical_unsupported_semantics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dataclasses import replace
    from datetime import datetime, timezone

    from engine.fundamental_forensics import metric_registry as registry_module
    from engine.fundamental_forensics.metric_registry import ConceptAlias, KnownConcept

    historical_t = T3_RECORDED
    future_at = datetime(2026, 8, 6, 0, 0, tzinfo=timezone.utc)
    body = _make_request(
        metric_ids=["future_metric"],
        policy={
            "selection": "latest_known_as_of",
            "source_snapshot_at": T3_SOURCE,
            "recorded_at": historical_t,
        },
    )

    class _R1:
        def resolve(self, entity_id: str) -> FinancialPacketDataset:
            return fip1_packet_dataset(ROOT)

    with pytest.raises(FinancialQueryAdmissionError) as r1:
        execute_financial_revisions(body=body, provider=_R1())
    assert r1.value.status_code == 400
    assert r1.value.detail == "unsupported metric"

    base = fip1_packet_dataset(ROOT)
    revenue = base.registry.metric("revenue")
    mapping = revenue.mappings[0]
    future_concept = "FutureMetricNotYetGoverned"
    monkeypatch.setitem(
        registry_module.KNOWN_CONCEPT_ALLOWLIST,
        ("us-gaap", future_concept),
        KnownConcept(
            taxonomy="us-gaap",
            concept=future_concept,
            taxonomy_version_start=2009,
            taxonomy_version_end=2026,
            period_kind="duration",
            contract_units=("USD",),
        ),
    )
    future_contract = replace(
        revenue,
        metric_id="future_metric",
        label="FUTURE LEAK LABEL",
        rule=replace(
            revenue.rule,
            rule_id="metric.future_metric/v1",
            available_at=future_at,
        ),
        mappings=(
            replace(
                mapping,
                metric_id="future_metric",
                rule=replace(
                    mapping.rule,
                    rule_id="mapping.future_metric/v1",
                    available_at=future_at,
                ),
                taxonomy_concept_aliases=(
                    ConceptAlias("us-gaap", future_concept, 10, 2009, 2026),
                ),
            ),
        ),
        formula=None,
        declared_formula_dependencies=(),
    )
    r2_registry = replace(base.registry, contracts=base.registry.contracts + (future_contract,))
    r2_dataset = replace(base, registry=r2_registry)
    assert "future_metric" in r2_registry.metric_ids

    class _R2:
        def resolve(self, entity_id: str) -> FinancialPacketDataset:
            return r2_dataset

    with pytest.raises(FinancialQueryAdmissionError) as r2:
        execute_financial_revisions(body=body, provider=_R2())
    assert r2.value.status_code == 400
    assert r2.value.detail == "unsupported metric"


def test_source_misbound_dataset_is_unavailable() -> None:
    fip1 = fip1_packet_dataset(ROOT)
    misbound = FinancialPacketDataset(
        binding=CanonicalEntityBinding(
            entity_id="mmx.issuer.fip1",
            cik="0000111111",
            ticker="FIP1",
            source_entity_id="0000111111",
        ),
        entity=fip1.entity,
        ledger=fip1.ledger,
        filing_metadata=fip1.filing_metadata,
        registry=fip1.registry,
        context=fip1.context,
        input_digests=fip1.input_digests,
    )

    class _SourceMisbound:
        def resolve(self, entity_id: str) -> FinancialPacketDataset:
            return misbound

    with pytest.raises(FinancialQueryUnavailableError):
        execute_financial_revisions(body=_t3_latest(), provider=_SourceMisbound())


def test_same_source_wrong_canonical_entity_is_unavailable() -> None:
    fip1 = fip1_packet_dataset(ROOT)
    misbound = FinancialPacketDataset(
        binding=fip1.binding,
        entity=EntityInput(
            entity_id="mmx.issuer.other",
            cik="0000999999",
            ticker="FIP1",
            name=fip1.entity.name,
            identity_basis=fip1.entity.identity_basis,
            source_entity_id="0000999999",
        ),
        ledger=fip1.ledger,
        filing_metadata=fip1.filing_metadata,
        registry=fip1.registry,
        context=fip1.context,
        input_digests=fip1.input_digests,
    )

    class _WrongCanonical:
        def resolve(self, entity_id: str) -> FinancialPacketDataset:
            return misbound

    with pytest.raises(FinancialQueryUnavailableError):
        execute_financial_revisions(body=_t3_latest(), provider=_WrongCanonical())


def test_unavailable_provider_raises_unavailable_error() -> None:
    with pytest.raises(FinancialQueryUnavailableError):
        execute_financial_revisions(
            body=_t3_latest(),
            provider=UnavailableFinancialPacketProvider(),
        )


def test_provider_not_called_before_admission() -> None:
    calls: list[str] = []

    class _TrackingProvider:
        def resolve(self, entity_id: str) -> FinancialPacketDataset:
            calls.append(entity_id)
            raise FinancialQueryUnavailableError()

    with pytest.raises(FinancialQueryAdmissionError):
        execute_financial_revisions(body=b"x" * 65537, provider=_TrackingProvider())
    assert calls == []


def test_duplicate_period_label_is_400_before_provider_resolve() -> None:
    calls: list[str] = []
    factory_calls: list[str] = []

    class _TrackingProvider:
        def resolve(self, entity_id: str) -> FinancialPacketDataset:
            calls.append(entity_id)
            return fip1_packet_dataset(ROOT)

    def _factory():
        factory_calls.append("opened")
        return _TrackingProvider()

    body = _t3_latest(
        periods=[
            {"kind": "duration", "start": "2023-01-01", "end": "2023-12-31", "label": "FY2023"},
            {"kind": "duration", "start": "2024-01-01", "end": "2024-12-31", "label": "FY2023"},
        ]
    )
    with pytest.raises(FinancialQueryAdmissionError) as exc_info:
        execute_financial_revisions(body=body, provider_factory=_factory)
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "request contract violation"
    assert factory_calls == []
    assert calls == []


def test_unsupported_metric_raises_400() -> None:
    body = _t3_latest(metric_ids=["revenue", "not_a_real_metric_xyz"])
    with pytest.raises(FinancialQueryAdmissionError) as exc_info:
        execute_financial_revisions(body=body, provider=_fip1_provider())
    assert exc_info.value.status_code == 400
    assert "unsupported metric" in exc_info.value.detail


def test_wrong_request_schema_is_400() -> None:
    body = _make_request(schema=_QUERY_SCHEMA)
    with pytest.raises(FinancialQueryAdmissionError) as exc_info:
        execute_financial_revisions(body=body, provider=UnavailableFinancialPacketProvider())
    assert exc_info.value.status_code == 400


def test_two_calls_with_changed_wall_clock_produce_identical_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import time

    provider = _fip1_provider()
    body = _t3_latest()
    monkeypatch.setattr(time, "time", lambda: 1_700_000_000.0)
    r1 = execute_financial_revisions(body=body, provider=provider)
    monkeypatch.setattr(time, "time", lambda: 1_800_000_000.0)
    r2 = execute_financial_revisions(body=body, provider=provider)
    assert r1.body == r2.body
    assert r1.sha256 == r2.sha256
    assert r1.envelope["packet_ref"]["packet_id"] == r2.envelope["packet_ref"]["packet_id"]
    assert r1.envelope["revisions"] == r2.envelope["revisions"]


def test_execute_does_not_append_to_the_ledger() -> None:
    provider = _fip1_provider()
    dataset = fip1_packet_dataset(ROOT)
    before = len(dataset.ledger.events)

    class _SpyProvider:
        def resolve(self, entity_id: str) -> FinancialPacketDataset:
            resolved = provider.resolve(entity_id)

            def _forbidden_write(*args, **kwargs):
                raise AssertionError("revisions must not append to the ledger")

            object.__setattr__(resolved.ledger, "append", _forbidden_write)
            object.__setattr__(resolved.ledger, "extend", _forbidden_write)
            return resolved

    execute_financial_revisions(body=_t3_latest(), provider=_SpyProvider())
    assert len(dataset.ledger.events) == before


def test_execute_does_not_open_the_network(monkeypatch: pytest.MonkeyPatch) -> None:
    import socket

    def _forbidden_socket(*args, **kwargs):
        raise AssertionError("revisions must not open a network socket")

    monkeypatch.setattr(socket, "socket", _forbidden_socket)
    execute_financial_revisions(body=_t3_latest(), provider=_fip1_provider())


def test_envelope_entity_is_canonical_mastermind_binding() -> None:
    result = execute_financial_revisions(body=_t3_latest(), provider=_fip1_provider())
    entity = result.envelope["entity"]
    assert entity["entity_id"] == "mmx.issuer.fip1"
    assert entity["cik"] == "0000999999"
    assert entity["ticker"] == "FIP1"
    assert entity["source_entity_id"] == "0000999999"
    assert result.envelope["schema"] == "fundamental_forensics.financial_revision_response/v1"
    assert result.envelope["authority"] == {"class": "context_only", "display_only": True}


def test_fip1_canonical_entity_does_not_rewrite_raw_identity() -> None:
    dataset = fip1_packet_dataset(ROOT)
    assert dataset.entity.entity_id == "mmx.issuer.fip1"
    assert dataset.entity.cik == "0000999999"
    assert dataset.entity.source_entity_id == "0000999999"
    assert dataset.entity.ticker == "FIP1"
    event = dataset.ledger.events[0]
    assert event.source.entity_id == "0000999999"
    assert event.context.entity_identifier == "0000999999"
    result = execute_financial_revisions(body=_t3_latest(), provider=_fip1_provider())
    packet = _direct_packet(
        metric_ids=("revenue",),
        periods=(FY2023_PERIOD,),
        source_snapshot_at=T3_SOURCE,
        recorded_at=T3_RECORDED,
    )
    assert packet["entity"]["entity_id"] == "mmx.issuer.fip1"
    assert packet["entity"]["cik"] == "0000999999"
    assert result.envelope["packet_ref"]["packet_id"] == packet["packet_id"]


def test_arbitrary_fixture_does_not_claim_committed_fip1_digest() -> None:
    committed = fip1_packet_dataset(ROOT)
    committed_digest = sha256_file(
        ROOT / "tests" / "fixtures" / "fundamental_forensics" / "filing_package_raw_ledger_v1.json"
    )
    assert committed.input_digests.filing_package_fixture_sha256 == committed_digest
    fixture = build_multihop_revenue_fixture()
    arbitrary = packet_dataset_from_fixture(ROOT, fixture)
    assert arbitrary.input_digests == PacketEvidenceDigests()
    assert arbitrary.input_digests.filing_package_fixture_sha256 is None
    assert arbitrary.input_digests.filing_package_fixture_sha256 != committed_digest
    later = _direct_packet(
        metric_ids=("revenue",),
        periods=(FY2023_PERIOD,),
        source_snapshot_at=HOP_C_SOURCE,
        recorded_at=T3_RECORDED,
        dataset=arbitrary,
    )
    assert later["receipts"]["filing_package_fixture_sha256"] is None
    assert later["receipts"]["filing_package_fixture_sha256"] != committed_digest


# ---------------------------------------------------------------------------
# FIF-2A #5983 regression after shared admission
# ---------------------------------------------------------------------------


def _query_hash(*, selection: str, source: str, recorded: str, metric_ids: list, periods: list) -> str:
    class _P:
        def resolve(self, entity_id: str) -> FinancialQueryDataset:
            return fip1_fixture_dataset(ROOT)

    body = json.dumps(
        {
            "schema": _QUERY_SCHEMA,
            "entity_id": "mmx.issuer.fip1",
            "policy": {
                "selection": selection,
                "source_snapshot_at": source,
                "recorded_at": recorded,
            },
            "metric_ids": metric_ids,
            "periods": periods,
        },
        separators=(",", ":"),
    ).encode("utf-8")
    result = execute_financial_query(body=body, provider=_P())
    return result.envelope["receipt"]["query_hash"]


def test_fif2a_query_hashes_unchanged_after_shared_admission() -> None:
    metrics = ["revenue", "gross_margin"]
    fy = [FY2023]
    assert (
        _query_hash(
            selection="as_reported",
            source=T1_SOURCE,
            recorded=T2_RECORDED,
            metric_ids=metrics,
            periods=fy,
        )
        == _HASH_AS_REPORTED_T1_T2
    )
    assert (
        _query_hash(
            selection="latest_known_as_of",
            source=T1_SOURCE,
            recorded=T2_RECORDED,
            metric_ids=metrics,
            periods=fy,
        )
        == _HASH_LATEST_KNOWN_T1_T2
    )
    assert (
        _query_hash(
            selection="latest_known_as_of",
            source=T3_SOURCE,
            recorded=T3_RECORDED,
            metric_ids=metrics,
            periods=fy,
        )
        == _HASH_LATEST_KNOWN_T3
    )
    assert (
        _query_hash(
            selection="latest_restated",
            source=T3_SOURCE,
            recorded=T3_RECORDED,
            metric_ids=metrics,
            periods=fy,
        )
        == _HASH_LATEST_RESTATED_T3
    )
    mixed = _query_hash(
        selection="latest_known_as_of",
        source=T3_SOURCE,
        recorded=T3_RECORDED,
        metric_ids=["revenue", "accounts_receivable_net"],
        periods=[FY2023, AR_INSTANT],
    )
    assert mixed == _HASH_MIXED_T3
