"""FIF-2A service-layer tests: admission, kernel invocation, determinism."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from engine.fundamental_forensics.financial_intelligence_packet import canonical_json
from engine.fundamental_forensics.query import (
    BitemporalMetricQueryEngine,
    CellState,
    PeriodRequest,
    QueryBounds,
    QueryPolicy,
)
from engine.fundamental_forensics.query_service import (
    CanonicalEntityBinding,
    FinancialQueryAdmissionError,
    FinancialQueryDataset,
    FinancialQueryUnavailableError,
    UnavailableFinancialQueryProvider,
    execute_financial_query,
    fip1_fixture_dataset,
)

ROOT = Path(__file__).resolve().parents[1]

# Clock constants mirroring test_fundamental_forensics_financial_intelligence_packet_r2.py
T0_SOURCE = "2024-01-01T00:00:00Z"
T1_SOURCE = "2024-12-31T23:59:59Z"
T2_SOURCE = "2025-12-31T23:59:59Z"
T2_RECORDED = "2026-08-03T12:00:00Z"
T3_SOURCE = "2025-12-31T23:59:59Z"
T3_RECORDED = "2026-08-05T12:00:02Z"


def _make_request(
    *,
    schema: str = "fundamental_forensics.financial_query_request/v1",
    entity_id: str = "mmx.issuer.fip1",
    policy: dict | None = None,
    metric_ids: list | None = None,
    periods: list | None = None,
    extra_fields: dict | None = None,
) -> bytes:
    if policy is None:
        policy = {
            "selection": "latest_known_as_of",
            "source_snapshot_at": T1_SOURCE,
            "recorded_at": T2_RECORDED,
        }
    if metric_ids is None:
        metric_ids = ["revenue"]
    if periods is None:
        periods = [{"kind": "duration", "start": "2023-01-01", "end": "2023-12-31", "label": "FY2023"}]
    obj: dict = {
        "schema": schema,
        "entity_id": entity_id,
        "policy": policy,
        "metric_ids": metric_ids,
        "periods": periods,
    }
    if extra_fields:
        obj.update(extra_fields)
    return json.dumps(obj, separators=(",", ":")).encode("utf-8")


def _fip1_provider(resolved_calls: list | None = None):
    """Return a provider that injects the FIP1 fixture dataset."""
    dataset = fip1_fixture_dataset(ROOT)

    class _FIP1Provider:
        def resolve(self, entity_id: str) -> FinancialQueryDataset:
            if resolved_calls is not None:
                resolved_calls.append(entity_id)
            if entity_id == "mmx.issuer.fip1":
                return dataset
            raise FinancialQueryAdmissionError(400, "unknown entity")

    return _FIP1Provider()


# ---------------------------------------------------------------------------
# Admission: structural rejection
# ---------------------------------------------------------------------------


def test_admission_rejects_body_over_64kib() -> None:
    body = b"x" * 65537
    with pytest.raises(FinancialQueryAdmissionError) as exc_info:
        execute_financial_query(body=body, provider=UnavailableFinancialQueryProvider())
    assert exc_info.value.status_code == 413


def test_admission_rejects_non_utf8() -> None:
    body = b"\xff\xfe"
    with pytest.raises(FinancialQueryAdmissionError) as exc_info:
        execute_financial_query(body=body, provider=UnavailableFinancialQueryProvider())
    assert exc_info.value.status_code == 400
    assert "malformed" in exc_info.value.detail


def test_admission_rejects_binary_float() -> None:
    body = b'{"schema":"fundamental_forensics.financial_query_request/v1","entity_id":"mmx.issuer.fip1","policy":{"selection":"latest_known_as_of","source_snapshot_at":"2024-12-31T23:59:59Z","recorded_at":"2026-08-03T12:00:00Z"},"metric_ids":["revenue"],"periods":[{"kind":"duration","start":1.5,"end":"2023-12-31","label":"FY2023"}]}'
    with pytest.raises(FinancialQueryAdmissionError) as exc_info:
        execute_financial_query(body=body, provider=UnavailableFinancialQueryProvider())
    assert exc_info.value.status_code == 400
    assert "malformed" in exc_info.value.detail


def test_admission_rejects_nan_constant() -> None:
    body = b'{"schema":"fundamental_forensics.financial_query_request/v1","entity_id":"mmx.issuer.fip1","policy":{"selection":"latest_known_as_of","source_snapshot_at":"2024-12-31T23:59:59Z","recorded_at":"2026-08-03T12:00:00Z"},"metric_ids":["revenue"],"periods":[{"kind":"duration","start":"2023-01-01","end":"2023-12-31","label":"FY2023"}],"bad":NaN}'
    with pytest.raises(FinancialQueryAdmissionError) as exc_info:
        execute_financial_query(body=body, provider=UnavailableFinancialQueryProvider())
    assert exc_info.value.status_code == 400


def test_admission_rejects_duplicate_json_keys() -> None:
    body = b'{"schema":"fundamental_forensics.financial_query_request/v1","entity_id":"mmx.issuer.fip1","entity_id":"dup","policy":{"selection":"latest_known_as_of","source_snapshot_at":"2024-12-31T23:59:59Z","recorded_at":"2026-08-03T12:00:00Z"},"metric_ids":["revenue"],"periods":[{"kind":"duration","start":"2023-01-01","end":"2023-12-31","label":"FY2023"}]}'
    with pytest.raises(FinancialQueryAdmissionError) as exc_info:
        execute_financial_query(body=body, provider=UnavailableFinancialQueryProvider())
    assert exc_info.value.status_code == 400
    assert "duplicate json key" in exc_info.value.detail


def test_admission_rejects_extra_root_fields() -> None:
    body = _make_request(extra_fields={"unexpected": "value"})
    with pytest.raises(FinancialQueryAdmissionError) as exc_info:
        execute_financial_query(body=body, provider=UnavailableFinancialQueryProvider())
    assert exc_info.value.status_code == 400
    assert "request contract violation" in exc_info.value.detail


def test_admission_rejects_missing_root_field() -> None:
    obj = {
        "schema": "fundamental_forensics.financial_query_request/v1",
        "entity_id": "mmx.issuer.fip1",
        "policy": {"selection": "latest_known_as_of", "source_snapshot_at": T1_SOURCE, "recorded_at": T2_RECORDED},
        # missing metric_ids and periods
    }
    body = json.dumps(obj, separators=(",", ":")).encode("utf-8")
    with pytest.raises(FinancialQueryAdmissionError) as exc_info:
        execute_financial_query(body=body, provider=UnavailableFinancialQueryProvider())
    assert exc_info.value.status_code == 400
    assert "request contract violation" in exc_info.value.detail


def test_admission_rejects_wrong_schema() -> None:
    body = _make_request(schema="wrong_schema/v1")
    with pytest.raises(FinancialQueryAdmissionError) as exc_info:
        execute_financial_query(body=body, provider=UnavailableFinancialQueryProvider())
    assert exc_info.value.status_code == 400


def test_admission_rejects_trailing_content() -> None:
    body = _make_request() + b" trailing"
    with pytest.raises(FinancialQueryAdmissionError) as exc_info:
        execute_financial_query(body=body, provider=UnavailableFinancialQueryProvider())
    assert exc_info.value.status_code == 400
    assert "malformed" in exc_info.value.detail


def test_admission_rejects_unknown_policy() -> None:
    body = _make_request(policy={
        "selection": "not_a_real_policy",
        "source_snapshot_at": T1_SOURCE,
        "recorded_at": T2_RECORDED,
    })
    with pytest.raises(FinancialQueryAdmissionError) as exc_info:
        execute_financial_query(body=body, provider=UnavailableFinancialQueryProvider())
    assert exc_info.value.status_code == 400
    assert "invalid policy" in exc_info.value.detail


def test_admission_rejects_missing_cutoff() -> None:
    body = _make_request(policy={
        "selection": "latest_known_as_of",
        "source_snapshot_at": "",
        "recorded_at": T2_RECORDED,
    })
    with pytest.raises(FinancialQueryAdmissionError) as exc_info:
        execute_financial_query(body=body, provider=UnavailableFinancialQueryProvider())
    assert exc_info.value.status_code == 400
    assert "missing cutoff" in exc_info.value.detail


def test_admission_rejects_policy_with_extra_fields() -> None:
    body = _make_request(policy={
        "selection": "latest_known_as_of",
        "source_snapshot_at": T1_SOURCE,
        "recorded_at": T2_RECORDED,
        "extra_key": "oops",
    })
    with pytest.raises(FinancialQueryAdmissionError) as exc_info:
        execute_financial_query(body=body, provider=UnavailableFinancialQueryProvider())
    assert exc_info.value.status_code == 400
    assert "request contract violation" in exc_info.value.detail


def test_admission_rejects_duplicate_metric_ids() -> None:
    body = _make_request(metric_ids=["revenue", "revenue"])
    with pytest.raises(FinancialQueryAdmissionError) as exc_info:
        execute_financial_query(body=body, provider=UnavailableFinancialQueryProvider())
    assert exc_info.value.status_code == 400
    assert "duplicate metric" in exc_info.value.detail


def test_admission_rejects_empty_metric_ids() -> None:
    body = _make_request(metric_ids=[])
    with pytest.raises(FinancialQueryAdmissionError) as exc_info:
        execute_financial_query(body=body, provider=UnavailableFinancialQueryProvider())
    assert exc_info.value.status_code == 400


def test_admission_rejects_non_string_metric() -> None:
    body = _make_request(metric_ids=[123])
    with pytest.raises(FinancialQueryAdmissionError) as exc_info:
        execute_financial_query(body=body, provider=UnavailableFinancialQueryProvider())
    assert exc_info.value.status_code == 400
    assert "request contract violation" in exc_info.value.detail


def test_admission_rejects_instant_period() -> None:
    body = _make_request(periods=[{"kind": "instant", "start": "", "end": "2023-12-31", "label": "Q4"}])
    with pytest.raises(FinancialQueryAdmissionError) as exc_info:
        execute_financial_query(body=body, provider=UnavailableFinancialQueryProvider())
    assert exc_info.value.status_code == 400
    assert "invalid period" in exc_info.value.detail


def test_admission_rejects_duplicate_semantic_periods() -> None:
    body = _make_request(periods=[
        {"kind": "duration", "start": "2023-01-01", "end": "2023-12-31", "label": "FY2023"},
        {"kind": "duration", "start": "2023-01-01", "end": "2023-12-31", "label": "FY2023-dup"},
    ])
    with pytest.raises(FinancialQueryAdmissionError) as exc_info:
        execute_financial_query(body=body, provider=UnavailableFinancialQueryProvider())
    assert exc_info.value.status_code == 400
    assert "duplicate period" in exc_info.value.detail


def test_admission_rejects_more_than_50_metrics() -> None:
    metric_ids = [f"metric_{i}" for i in range(51)]
    body = _make_request(metric_ids=metric_ids)
    with pytest.raises(FinancialQueryAdmissionError) as exc_info:
        execute_financial_query(body=body, provider=UnavailableFinancialQueryProvider())
    assert exc_info.value.status_code == 413
    assert "request exceeds transport bound" in exc_info.value.detail


def test_transport_cell_bound_is_exactly_max_metrics_times_max_periods() -> None:
    from engine.fundamental_forensics.query_service import MAX_CELLS, MAX_METRIC_IDS, MAX_PERIODS

    assert MAX_METRIC_IDS * MAX_PERIODS == MAX_CELLS


# ---------------------------------------------------------------------------
# Provider: unavailable default and unknown entity
# ---------------------------------------------------------------------------


def test_misbound_provider_is_unavailable() -> None:
    """A provider that returns a different canonical entity must not 200."""
    fip1 = fip1_fixture_dataset(ROOT)

    class _Misbound:
        def resolve(self, entity_id: str) -> FinancialQueryDataset:
            return fip1

    body = _make_request(entity_id="mmx.issuer.someoneelse")
    with pytest.raises(FinancialQueryUnavailableError):
        execute_financial_query(body=body, provider=_Misbound())


def test_unavailable_provider_raises_unavailable_error() -> None:
    body = _make_request()
    with pytest.raises(FinancialQueryUnavailableError):
        execute_financial_query(body=body, provider=UnavailableFinancialQueryProvider())


def test_provider_not_called_before_admission() -> None:
    """Provider.resolve must not be called until admission has succeeded."""
    calls: list[str] = []

    class _TrackingProvider:
        def resolve(self, entity_id: str) -> FinancialQueryDataset:
            calls.append(entity_id)
            raise FinancialQueryUnavailableError()

    # Body that fails admission (too big)
    big_body = b"x" * 65537
    with pytest.raises(FinancialQueryAdmissionError):
        execute_financial_query(body=big_body, provider=_TrackingProvider())

    assert calls == [], "resolve must not be called before admission"


def test_unsupported_metric_raises_400() -> None:
    provider = _fip1_provider()
    body = _make_request(metric_ids=["revenue", "not_a_real_metric_xyz"])
    with pytest.raises(FinancialQueryAdmissionError) as exc_info:
        execute_financial_query(body=body, provider=provider)
    assert exc_info.value.status_code == 400
    assert "unsupported metric" in exc_info.value.detail


# ---------------------------------------------------------------------------
# Golden receipt: execute_financial_query vs engine.query_matrix
# ---------------------------------------------------------------------------


def _direct_matrix(
    *,
    source_snapshot_at: str,
    recorded_at: str,
    selection: str = "latest_known_as_of",
    metric_ids: list[str],
    periods: list[PeriodRequest],
) -> object:
    """Run the engine directly for comparison."""
    dataset = fip1_fixture_dataset(ROOT)
    binding = dataset.binding
    policy = QueryPolicy(
        source_snapshot_at=source_snapshot_at,
        recorded_at=recorded_at,
        selection=selection,
    )
    engine = BitemporalMetricQueryEngine(
        ledger=dataset.ledger,
        registry=dataset.registry,
        entities={binding.ticker: binding.source_entity_id},
        filing_metadata=dataset.filing_metadata,
        bounds=QueryBounds(max_tickers=1, max_metrics=50, max_periods=8, max_cells=400),
    )
    return engine.query_matrix(
        tickers=[binding.ticker],
        metrics=metric_ids,
        periods=periods,
        policy=policy,
    )


def test_receipt_equals_direct_matrix_to_dict() -> None:
    provider = _fip1_provider()
    body = _make_request(
        metric_ids=["revenue", "gross_margin"],
        periods=[{"kind": "duration", "start": "2023-01-01", "end": "2023-12-31", "label": "FY2023"}],
        policy={
            "selection": "latest_known_as_of",
            "source_snapshot_at": T1_SOURCE,
            "recorded_at": T2_RECORDED,
        },
    )
    result = execute_financial_query(body=body, provider=provider)
    period_req = PeriodRequest.duration("2023-01-01", "2023-12-31", label="FY2023")
    matrix = _direct_matrix(
        source_snapshot_at=T1_SOURCE,
        recorded_at=T2_RECORDED,
        metric_ids=["revenue", "gross_margin"],
        periods=[period_req],
    )
    assert result.envelope["receipt"] == matrix.to_dict()
    assert result.envelope["receipt"]["query_hash"] == matrix.query_hash


def test_receipt_cells_and_nodes_match_direct_matrix() -> None:
    provider = _fip1_provider()
    body = _make_request(
        metric_ids=["revenue", "gross_margin"],
        periods=[{"kind": "duration", "start": "2023-01-01", "end": "2023-12-31", "label": "FY2023"}],
        policy={
            "selection": "latest_known_as_of",
            "source_snapshot_at": T1_SOURCE,
            "recorded_at": T2_RECORDED,
        },
    )
    result = execute_financial_query(body=body, provider=provider)
    period_req = PeriodRequest.duration("2023-01-01", "2023-12-31", label="FY2023")
    matrix = _direct_matrix(
        source_snapshot_at=T1_SOURCE,
        recorded_at=T2_RECORDED,
        metric_ids=["revenue", "gross_margin"],
        periods=[period_req],
    )
    receipt = result.envelope["receipt"]
    expected = matrix.to_dict()
    assert receipt["root_cell_ids"] == expected["root_cell_ids"]
    assert receipt["nodes"] == expected["nodes"]
    assert receipt["governance_bundle"] == expected["governance_bundle"]


# ---------------------------------------------------------------------------
# T0/T1/T2/T3 temporal correctness
# ---------------------------------------------------------------------------


def _run(source: str, recorded: str, selection: str = "latest_known_as_of") -> dict:
    provider = _fip1_provider()
    body = _make_request(
        metric_ids=["revenue"],
        periods=[{"kind": "duration", "start": "2023-01-01", "end": "2023-12-31", "label": "FY2023"}],
        policy={
            "selection": selection,
            "source_snapshot_at": source,
            "recorded_at": recorded,
        },
    )
    result = execute_financial_query(body=body, provider=provider)
    cells = result.envelope["receipt"]["nodes"]
    # Find the revenue FY2023 root cell
    receipt = result.envelope["receipt"]
    root_ids = set(receipt["root_cell_ids"])
    revenue_nodes = [
        n for n in receipt["nodes"]
        if n["cell_id"] in root_ids and n.get("metric_id") == "revenue"
    ]
    assert len(revenue_nodes) == 1, f"Expected 1 revenue node, got {len(revenue_nodes)}"
    return revenue_nodes[0]


def test_t0_latest_known_as_of_fy2023_revenue_missing() -> None:
    node = _run(T0_SOURCE, T2_RECORDED)
    assert node["state"] == "missing"


def test_t1_latest_known_as_of_fy2023_revenue_1050() -> None:
    node = _run(T1_SOURCE, T2_RECORDED)
    assert node["state"] == "value"
    assert node["value"] == "1050"


def test_t2_latest_known_as_of_fy2023_revenue_1050_not_1060() -> None:
    node = _run(T2_SOURCE, T2_RECORDED)
    assert node["state"] == "value"
    assert node["value"] == "1050"
    # 1060 must not appear in this receipt
    body_str = json.dumps(execute_financial_query(
        body=_make_request(
            metric_ids=["revenue"],
            periods=[{"kind": "duration", "start": "2023-01-01", "end": "2023-12-31", "label": "FY2023"}],
            policy={"selection": "latest_known_as_of", "source_snapshot_at": T2_SOURCE, "recorded_at": T2_RECORDED},
        ),
        provider=_fip1_provider(),
    ).envelope)
    assert "1060" not in body_str


def test_t3_latest_known_as_of_fy2023_revenue_1060() -> None:
    node = _run(T3_SOURCE, T3_RECORDED)
    assert node["state"] == "value"
    assert node["value"] == "1060"


def test_as_reported_t1_source_t2_recorded_fy2023_revenue_1050() -> None:
    node = _run(T1_SOURCE, T2_RECORDED, selection="as_reported")
    assert node["state"] == "value"
    assert node["value"] == "1050"


def test_latest_restated_t2_source_t2_recorded_fy2023_revenue_missing() -> None:
    node = _run(T2_SOURCE, T2_RECORDED, selection="latest_restated")
    assert node["state"] == "missing"


def test_latest_restated_t3_source_t3_recorded_fy2023_revenue_1060() -> None:
    node = _run(T3_SOURCE, T3_RECORDED, selection="latest_restated")
    assert node["state"] == "value"
    assert node["value"] == "1060"


# ---------------------------------------------------------------------------
# Direct metric, formula, and missing cell paths
# ---------------------------------------------------------------------------


def test_direct_revenue_cell_has_provenance_direct() -> None:
    provider = _fip1_provider()
    body = _make_request(
        metric_ids=["revenue"],
        periods=[{"kind": "duration", "start": "2023-01-01", "end": "2023-12-31", "label": "FY2023"}],
        policy={"selection": "latest_known_as_of", "source_snapshot_at": T1_SOURCE, "recorded_at": T2_RECORDED},
    )
    result = execute_financial_query(body=body, provider=provider)
    receipt = result.envelope["receipt"]
    root_ids = set(receipt["root_cell_ids"])
    revenue_nodes = [n for n in receipt["nodes"] if n["cell_id"] in root_ids and n.get("metric_id") == "revenue"]
    assert len(revenue_nodes) == 1
    # provenance.kind is in the nested provenance dict
    assert revenue_nodes[0]["provenance"]["kind"] == "direct"


def test_formula_gross_margin_cell_has_provenance_formula() -> None:
    provider = _fip1_provider()
    body = _make_request(
        metric_ids=["gross_margin"],
        periods=[{"kind": "duration", "start": "2023-01-01", "end": "2023-12-31", "label": "FY2023"}],
        policy={"selection": "latest_known_as_of", "source_snapshot_at": T1_SOURCE, "recorded_at": T2_RECORDED},
    )
    result = execute_financial_query(body=body, provider=provider)
    receipt = result.envelope["receipt"]
    root_ids = set(receipt["root_cell_ids"])
    gm_nodes = [n for n in receipt["nodes"] if n["cell_id"] in root_ids and n.get("metric_id") == "gross_margin"]
    assert len(gm_nodes) == 1
    assert gm_nodes[0]["provenance"]["kind"] == "formula"


def test_missing_t0_revenue_cell_state_is_missing() -> None:
    provider = _fip1_provider()
    body = _make_request(
        metric_ids=["revenue"],
        periods=[{"kind": "duration", "start": "2023-01-01", "end": "2023-12-31", "label": "FY2023"}],
        policy={"selection": "latest_known_as_of", "source_snapshot_at": T0_SOURCE, "recorded_at": T2_RECORDED},
    )
    result = execute_financial_query(body=body, provider=provider)
    receipt = result.envelope["receipt"]
    root_ids = set(receipt["root_cell_ids"])
    revenue_nodes = [n for n in receipt["nodes"] if n["cell_id"] in root_ids and n.get("metric_id") == "revenue"]
    assert len(revenue_nodes) == 1
    assert revenue_nodes[0]["state"] == "missing"


# ---------------------------------------------------------------------------
# Determinism: identical bytes across wall-clock changes
# ---------------------------------------------------------------------------


def test_two_calls_with_changed_wall_clock_produce_identical_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    import time

    provider = _fip1_provider()
    body = _make_request(
        metric_ids=["revenue"],
        periods=[{"kind": "duration", "start": "2023-01-01", "end": "2023-12-31", "label": "FY2023"}],
        policy={"selection": "latest_known_as_of", "source_snapshot_at": T1_SOURCE, "recorded_at": T2_RECORDED},
    )

    monkeypatch.setattr(time, "time", lambda: 1_700_000_000.0)
    r1 = execute_financial_query(body=body, provider=provider)

    monkeypatch.setattr(time, "time", lambda: 1_800_000_000.0)
    r2 = execute_financial_query(body=body, provider=provider)

    assert r1.body == r2.body
    assert r1.sha256 == r2.sha256


# ---------------------------------------------------------------------------
# Envelope identity: canonical binding in envelope.entity, source id in receipt
# ---------------------------------------------------------------------------


def test_envelope_entity_contains_canonical_mastermind_binding() -> None:
    provider = _fip1_provider()
    body = _make_request()
    result = execute_financial_query(body=body, provider=provider)
    entity = result.envelope["entity"]
    assert entity["entity_id"] == "mmx.issuer.fip1"
    assert entity["cik"] == "0000999999"
    assert entity["ticker"] == "FIP1"
    assert entity["source_entity_id"] == "0000999999"


def test_receipt_entities_keep_source_entity_id() -> None:
    provider = _fip1_provider()
    body = _make_request()
    result = execute_financial_query(body=body, provider=provider)
    receipt = result.envelope["receipt"]
    assert receipt["entities"], "kernel receipt must carry source-native entities"
    for entity_entry in receipt["entities"]:
        assert entity_entry["entity_id"] == "0000999999"


# ---------------------------------------------------------------------------
# Coverage counts are derived from matrix.cells
# ---------------------------------------------------------------------------


def test_coverage_counts_match_cell_states() -> None:
    provider = _fip1_provider()
    # Use T0_SOURCE so revenue is missing
    body = _make_request(
        metric_ids=["revenue"],
        periods=[{"kind": "duration", "start": "2023-01-01", "end": "2023-12-31", "label": "FY2023"}],
        policy={"selection": "latest_known_as_of", "source_snapshot_at": T0_SOURCE, "recorded_at": T2_RECORDED},
    )
    result = execute_financial_query(body=body, provider=provider)
    cov = result.envelope["coverage"]
    assert cov["requested_cells"] == 1
    assert cov["missing_cells"] == 1
    assert cov["value_cells"] == 0


# ---------------------------------------------------------------------------
# Response size: measure 50×8 envelope (or all-registry-capped)
# ---------------------------------------------------------------------------


def test_fip1_max_envelope_under_8mib() -> None:
    from engine.fundamental_forensics.financial_intelligence_packet import load_core_registry

    registry = load_core_registry(ROOT)
    all_metrics = list(registry.metric_ids)
    capped_metrics = all_metrics[: min(50, len(all_metrics))]
    assert len(capped_metrics) == 50
    periods = [
        {"kind": "duration", "start": f"{year}-01-01", "end": f"{year}-12-31", "label": f"FY{year}"}
        for year in range(2017, 2025)
    ]
    assert len(periods) == 8
    assert len(capped_metrics) * len(periods) <= 400

    provider = _fip1_provider()
    body = _make_request(
        metric_ids=capped_metrics,
        periods=periods,
        policy={"selection": "latest_known_as_of", "source_snapshot_at": T3_SOURCE, "recorded_at": T3_RECORDED},
    )
    result = execute_financial_query(body=body, provider=provider)
    size = len(result.body)
    assert size < 8 * 1024 * 1024, f"Envelope is {size} bytes, exceeds 8 MiB limit"
    # Report size in output for EVIDENCE
    print(f"\nFIP1 {len(capped_metrics)}×{len(periods)} envelope size: {size} bytes")


def test_nine_periods_exceeds_transport_bound() -> None:
    periods = [
        {"kind": "duration", "start": f"{year}-01-01", "end": f"{year}-12-31", "label": f"FY{year}"}
        for year in range(2016, 2025)
    ]
    body = _make_request(periods=periods)
    with pytest.raises(FinancialQueryAdmissionError) as exc_info:
        execute_financial_query(body=body, provider=UnavailableFinancialQueryProvider())
    assert exc_info.value.status_code == 413
    assert exc_info.value.detail == "request exceeds transport bound"


def test_execute_does_not_append_to_the_ledger() -> None:
    provider = _fip1_provider()
    dataset = fip1_fixture_dataset(ROOT)
    before = len(dataset.ledger.events)

    class _SpyProvider:
        def resolve(self, entity_id: str) -> FinancialQueryDataset:
            resolved = provider.resolve(entity_id)

            def _forbidden_write(*args, **kwargs):
                raise AssertionError("query must not append to the ledger")

            object.__setattr__(resolved.ledger, "append", _forbidden_write)
            object.__setattr__(resolved.ledger, "extend", _forbidden_write)
            return resolved

    execute_financial_query(body=_make_request(), provider=_SpyProvider())
    assert len(dataset.ledger.events) == before


def test_execute_does_not_open_the_network(monkeypatch: pytest.MonkeyPatch) -> None:
    import socket

    def _forbidden_socket(*args, **kwargs):
        raise AssertionError("query must not open a network socket")

    monkeypatch.setattr(socket, "socket", _forbidden_socket)
    execute_financial_query(body=_make_request(), provider=_fip1_provider())
