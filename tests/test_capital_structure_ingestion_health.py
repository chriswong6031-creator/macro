"""Ingestion-truth gate: selected filings with zero durable evidence must fail."""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

import collectors.sec_capital_structure as sec
from engine.capital_structure.ingestion_health import (
    calculate_horizon,
    census_attempts,
    evaluate_health,
    health_exit_code,
    source_high_watermark,
)
from engine.capital_structure.source_ledger_io import read_source_ledger, source_ledger_path
from engine.capital_structure.source_store import ContentAddressedSourceStore
from engine.research_vault.r2_store import LocalStore
from scripts.check_capital_structure_health import main as health_main
from tests.test_sec_capital_structure import INDEX, OneDayAdapter


ACCESSION = "0001234567-26-000001"


class FailingSourceStore:
    last_failure = None
    store_id = "capital_structure_local"

    def put_verified(self, raw, media_type="application/octet-stream"):
        return None


class ReadbackFailStore:
    last_put_error = None

    def put_bytes(self, key, data, content_type="application/octet-stream"):
        return True

    def get_bytes(self, key):
        return None

    def get_bytes_strict_bounded(self, key, *, expected_byte_length, max_byte_length):
        raise RuntimeError("forced exact-length readback failure")


def _prepare_adapter(tmp_path, monkeypatch, source_store, *, max_filings=1):
    business_day_index = INDEX
    for filing_date in ("20260801", "20260802", "20260803", "20260804", "20260805"):
        business_day_index = business_day_index.replace(filing_date, "20260814")
    monkeypatch.setattr(
        OneDayAdapter,
        "_fetch_index",
        lambda self, value, ua: business_day_index,
    )
    monkeypatch.setattr(sec, "_data_dir", lambda: tmp_path / "capital_structure")
    monkeypatch.setattr(sec, "_cik_map", lambda: {1234567: "ACME"})
    monkeypatch.setattr(sec, "_ua", lambda: "test@example.com")
    monkeypatch.setattr(sec, "PACE_SECONDS", 0)
    monkeypatch.setattr(
        sec, "due_index_dates", lambda *args, **kwargs: [date(2026, 8, 14)]
    )
    adapter = OneDayAdapter(
        source_store=source_store,
        now_fn=lambda: datetime(2026, 8, 16, 13, 0, tzinfo=timezone.utc),
        max_filings_per_run=max_filings,
    )
    adapter.latest_filings_enabled = False
    return adapter


def test_broken_storage_path_fails_the_health_gate(tmp_path, monkeypatch):
    """An all-storage-failure run cannot finish green."""
    adapter = _prepare_adapter(tmp_path, monkeypatch, FailingSourceStore())
    heartbeat = adapter.fetch()["sec_evidence__ingest"]
    assert int(heartbeat.iloc[0]["retrieved"]) == 0

    root = tmp_path / "capital_structure"
    record = evaluate_health(root, generated_at="2026-08-16T14:00:00+00:00")
    assert record["verdict"] == "fail"
    assert record["counters"]["selected"] >= 1
    assert record["counters"]["verified_retained_sources"] == 0
    assert record["counters"]["manifested_sources"] == 0
    assert record["counters"]["storage_deferred"] >= 1
    assert health_exit_code(record) == 1
    assert health_main(["--root", str(root)]) == 1
    health = json.loads((root / "health.json").read_text())
    assert health["verdict"] == "fail"
    assert health["compiler_generated_at"] != health["latest_source_retrieved_at"] or (
        health["compiler_generated_at"] is None and health["latest_source_retrieved_at"] is None
    )


def test_broken_readback_path_fails_the_health_gate(tmp_path, monkeypatch):
    store = ContentAddressedSourceStore(
        ReadbackFailStore(), backend="local", store_id="capital_structure_local"
    )
    adapter = _prepare_adapter(tmp_path, monkeypatch, store)
    adapter.fetch()

    root = tmp_path / "capital_structure"
    attempts = pd.read_parquet(root / "retrieval_attempts.parquet")
    assert attempts.iloc[0]["state"] == "storage_deferred"
    assert attempts.iloc[0]["storage_operation"] == "GetObject"
    assert "readback" in str(attempts.iloc[0]["error"])
    assert read_source_ledger(source_ledger_path(root)) == []
    record = evaluate_health(root, generated_at="2026-08-16T14:00:00+00:00")
    assert record["verdict"] == "fail"
    assert health_exit_code(record) == 1
    census = record["census"]
    assert census
    row = census[0]
    for field in (
        "stage", "outcome", "error_class", "error_fingerprint", "http_status",
        "storage_operation", "lane", "count", "first_occurrence", "latest_occurrence",
    ):
        assert field in row
    assert row["stage"] == "storage"
    assert row["outcome"] == "storage_deferred"
    assert row["storage_operation"] == "GetObject"


def test_already_known_queue_is_proven_no_new_work(tmp_path, monkeypatch):
    store = ContentAddressedSourceStore(
        LocalStore(tmp_path / "objects"), backend="local"
    )
    adapter = _prepare_adapter(tmp_path, monkeypatch, store, max_filings=10)
    first = adapter.fetch()["sec_evidence__ingest"]
    second = adapter.fetch()["sec_evidence__ingest"]
    assert int(first.iloc[0]["retrieved"]) > 0
    assert int(second.iloc[0]["retrieved"]) == 0

    root = tmp_path / "capital_structure"
    ingestion = json.loads((root / "ingestion_run.json").read_text())
    assert ingestion["verdict"] == "no_new_work"
    assert ingestion["no_new_work_proven"] is True
    assert ingestion["counters"]["selected"] == 0
    record = evaluate_health(root, generated_at="2026-08-16T14:00:00+00:00")
    assert record["verdict"] == "no_new_work"
    assert health_exit_code(record) == 0
    assert health_main(["--root", str(root)]) == 0


def test_happy_path_advances_watermark_and_compiles_the_accession(tmp_path, monkeypatch):
    store = ContentAddressedSourceStore(
        LocalStore(tmp_path / "objects"), backend="local"
    )
    adapter = _prepare_adapter(tmp_path, monkeypatch, store, max_filings=1)
    adapter.fetch()

    root = tmp_path / "capital_structure"
    ingestion = json.loads((root / "ingestion_run.json").read_text())
    before = ingestion["source_high_watermark_before"]
    after = ingestion["source_high_watermark_after"]
    assert before["source_manifest_count"] == 0
    assert after["source_manifest_count"] > 0
    assert after["latest_retrieved_at"]
    assert ingestion["verdict"] == "ok"
    assert ingestion["counters"]["selected"] >= 1
    assert ingestion["counters"]["retrieved"] >= 1
    assert ingestion["counters"]["verified_retained_sources"] >= 1
    assert ingestion["counters"]["manifested_sources"] > 0

    manifests = read_source_ledger(source_ledger_path(root))
    accessions = {
        (record.get("filing") or {}).get("accession") for record in manifests
    }
    assert ACCESSION in accessions
    digest = next(
        (record.get("document") or {}).get("content_sha256")
        for record in manifests
        if (record.get("document") or {}).get("document_role") == "complete_submission"
        and (record.get("filing") or {}).get("accession") == ACCESSION
    )
    retained = store.get_verified(
        next(
            (record.get("storage") or {}).get("object_key")
            for record in manifests
            if (record.get("filing") or {}).get("accession") == ACCESSION
            and (record.get("document") or {}).get("document_role") == "complete_submission"
        ),
        digest,
    )
    assert retained

    from scripts.compile_capital_structure_events import compile_from_disk

    compiled = compile_from_disk(
        root=root, generated_at="2026-08-16T15:00:00+00:00"
    )
    assert compiled["events"] >= 1
    events = pd.read_parquet(root / "event_versions.parquet")
    assert ACCESSION in set(events["accession"].astype(str))

    telemetry = json.loads((root / "telemetry.json").read_text())
    record = evaluate_health(root, generated_at="2026-08-16T16:00:00+00:00")
    assert record["verdict"] == "ok"
    assert record["compiler_generated_at"] == telemetry["as_of"]
    assert record["latest_source_retrieved_at"] == after["latest_retrieved_at"]
    assert record["compiler_generated_at"] != record["latest_source_retrieved_at"]
    assert record["counters"]["compiled_events"] == telemetry["counts"]["event_versions"]
    assert health_exit_code(record) == 0
    assert health_main(["--root", str(root)]) == 0


def test_health_error_annotation_starts_the_line(tmp_path, monkeypatch, capsys):
    adapter = _prepare_adapter(tmp_path, monkeypatch, FailingSourceStore())
    adapter.fetch()
    code = health_main(["--root", str(tmp_path / "capital_structure")])
    assert code == 1
    lines = [line for line in capsys.readouterr().out.splitlines() if "::error" in line]
    assert lines and all(line.startswith("::error") for line in lines)


def test_census_groups_storage_failures_with_http_and_operation():
    rows = census_attempts([
        {
            "state": "storage_deferred",
            "error": "RuntimeError: source-store write/readback verification failed "
                     "(operation=PutObject store_id=r2_capital_structure http_status=403 "
                     "reason=put-failed): Access Denied",
            "error_class": "ClientError",
            "http_status": 403,
            "storage_operation": "PutObject",
            "retrieval_lane": "registration",
            "attempted_at": "2026-08-08T01:00:00Z",
        },
        {
            "state": "storage_deferred",
            "error": "RuntimeError: source-store write/readback verification failed "
                     "(operation=PutObject store_id=r2_capital_structure http_status=403 "
                     "reason=put-failed): Access Denied",
            "error_class": "ClientError",
            "http_status": 403,
            "storage_operation": "PutObject",
            "retrieval_lane": "registration",
            "attempted_at": "2026-08-14T01:19:50Z",
        },
    ])
    assert len(rows) == 1
    assert rows[0]["count"] == 2
    assert rows[0]["http_status"] == 403
    assert rows[0]["storage_operation"] == "PutObject"
    assert rows[0]["first_occurrence"] == "2026-08-08T01:00:00Z"
    assert rows[0]["latest_occurrence"] == "2026-08-14T01:19:50Z"


def test_source_high_watermark_is_independent_of_compiler_generation_time():
    manifests = [
        {
            "document": {"document_role": "complete_submission"},
            "retrieval": {"retrieved_at": "2026-08-02T00:32:54Z"},
            "filing": {"filing_date": "2026-07-31"},
        }
    ]
    watermark = source_high_watermark(manifests)
    assert watermark["latest_retrieved_at"] == "2026-08-02T00:32:54Z"
    assert watermark["latest_filing_date"] == "2026-07-31"
    assert watermark["source_manifest_count"] == 1


def _horizon_manifest(filing_date: str) -> dict:
    return {
        "filing": {
            "accession": "0000000001-26-000001",
            "filing_date": filing_date,
            "file_number": "333-123",
            "file_number_provenance": {
                "state": "observed",
                "value": "333-123",
                "candidate_values": ["333-123"],
                "sources": ["sec_header_file_number"],
            },
        },
        "document": {"document_role": "complete_submission"},
        "parser": {"eligibility": "eligible", "corruption_state": "clean"},
        "retrieval": {"retrieved_at": f"{filing_date}T23:00:00Z"},
    }


def _horizon_receipt(
    *, arrivals: int = 100, capacity: int = 160,
    pending: int = 100, selected: int = 100,
) -> dict:
    unserved = pending - selected
    return {
        "policy_version": "fixture-policy/1",
        "latest_discovered_in_policy_filing_date": "2026-08-20",
        "latest_discovered_in_policy_observed_at": "2026-08-20T22:00:00Z",
        "live_tail_arrivals_current_run": arrivals,
        "live_tail_effective_capacity": capacity,
        "live_tail_arrival_overflow": max(0, arrivals - capacity),
        "live_tail_pending_before_selection": pending,
        "live_tail_selected": selected,
        "live_tail_unserved_after_selection": unserved,
        "work_classes": [{
            "work_class": "LIVE_TAIL",
            "reserved_slots": 160,
            "spill_in_slots": max(0, capacity - 160),
            "current_run_arrivals": arrivals,
            "pending_count": pending,
            "selected_count": selected,
        }],
    }


def _calculate_horizon(
    *, discovered: str = "2026-08-20", retained: str = "2026-08-20",
    compiled: str = "2026-08-20", latest_status: str = "complete",
    receipt: dict | None = None,
) -> dict:
    completed = [
        stamp.date().isoformat()
        for stamp in pd.bdate_range("2026-08-03", "2026-08-20")
    ]
    coverage = [
        {
            "index_date": index_date,
            "status": "complete",
            "policy_version": "fixture-policy/1",
        }
        for index_date in completed
    ]
    if latest_status != "complete":
        coverage.append({
            "index_date": "2026-08-21",
            "status": latest_status,
            "policy_version": "fixture-policy/1",
        })
    return calculate_horizon(
        discovery=[{
            "accession": "0000000001-26-000001",
            "filing_date": discovered,
            "_first_seen": f"{discovered}T22:00:00Z",
        }],
        index_coverage=coverage,
        manifests=[_horizon_manifest(retained)],
        events=[{"filing_date": compiled}],
        telemetry={
            "generation_id": "generation:cs:" + "c" * 24,
            "as_of": "2026-08-21T01:00:00Z",
        },
        queue_receipt=receipt or _horizon_receipt(),
        calculated_at="2026-08-21T01:01:00Z",
    )


def test_horizon_current_requires_discovery_retention_and_compile_parity():
    horizon = _calculate_horizon()
    assert horizon["state"] == "current"
    assert horizon["reason_codes"] == []
    assert set(horizon["watermarks"].values()) >= {"2026-08-20"}
    assert horizon["live_tail"] == {
        "live_tail_arrivals_current_run": 100,
        "live_tail_effective_capacity": 160,
        "live_tail_arrival_overflow": 0,
        "live_tail_pending_before_selection": 100,
        "live_tail_selected": 100,
        "live_tail_unserved_after_selection": 0,
    }


def test_horizon_counts_verified_legacy_root_as_retained_before_provenance_backfill():
    manifest = _horizon_manifest("2026-08-20")
    del manifest["filing"]["file_number_provenance"]
    horizon = calculate_horizon(
        discovery=[{
            "accession": "0000000001-26-000001",
            "filing_date": "2026-08-20",
            "_first_seen": "2026-08-20T22:00:00Z",
        }],
        index_coverage=[{
            "index_date": "2026-08-20", "status": "complete",
            "policy_version": "fixture-policy/1",
        }],
        manifests=[manifest],
        events=[{"filing_date": "2026-08-20"}],
        telemetry={
            "generation_id": "generation:cs:" + "c" * 24,
            "as_of": "2026-08-21T01:00:00Z",
        },
        queue_receipt=_horizon_receipt(),
        calculated_at="2026-08-21T01:01:00Z",
    )
    assert horizon["state"] == "current"
    assert horizon["watermarks"]["latest_eligible_retained_filing_date"] == "2026-08-20"


def test_retained_watermark_clock_belongs_to_the_newest_filing_date():
    newest = _horizon_manifest("2026-08-20")
    newest["retrieval"]["retrieved_at"] = "2026-08-20T23:00:00Z"
    older_later = _horizon_manifest("2026-07-31")
    older_later["retrieval"]["retrieved_at"] = "2026-08-21T23:00:00Z"
    horizon = calculate_horizon(
        discovery=[],
        index_coverage=[{
            "index_date": "2026-08-20", "status": "complete",
            "policy_version": "fixture-policy/1",
        }],
        manifests=[newest, older_later],
        events=[{"filing_date": "2026-08-20"}],
        telemetry={
            "generation_id": "generation:cs:" + "c" * 24,
            "as_of": "2026-08-21T01:00:00Z",
        },
        queue_receipt=_horizon_receipt(),
        calculated_at="2026-08-21T01:01:00Z",
    )
    assert horizon["state"] == "current"
    assert horizon["watermarks"]["latest_eligible_retained_filing_date"] == "2026-08-20"
    assert horizon["watermarks"]["latest_eligible_retained_retrieved_at"] == "2026-08-20T23:00:00Z"


def test_retained_watermark_clock_uses_utc_instant_not_lexicographic_offset():
    earlier = _horizon_manifest("2026-08-20")
    earlier["retrieval"]["retrieved_at"] = "2026-08-21T01:00:00+10:00"
    later = _horizon_manifest("2026-08-20")
    later["retrieval"]["retrieved_at"] = "2026-08-20T23:00:00Z"
    horizon = calculate_horizon(
        discovery=[],
        index_coverage=[{
            "index_date": "2026-08-20", "status": "complete",
            "policy_version": "fixture-policy/1",
        }],
        manifests=[earlier, later], events=[{"filing_date": "2026-08-20"}],
        telemetry={
            "generation_id": "generation:cs:" + "c" * 24,
            "as_of": "2026-08-21T01:00:00Z",
        },
        queue_receipt=_horizon_receipt(),
        calculated_at="2026-08-21T01:01:00Z",
    )
    assert horizon["state"] == "current"
    assert horizon["watermarks"]["latest_eligible_retained_retrieved_at"] == "2026-08-20T23:00:00Z"


def test_horizon_invalid_or_missing_bound_clocks_are_unavailable():
    invalid_sibling = _horizon_manifest("2026-08-20")
    invalid_sibling["retrieval"]["retrieved_at"] = "0000"
    valid_sibling = _horizon_manifest("2026-08-20")
    valid_sibling["retrieval"]["retrieved_at"] = "2026-08-20T23:00:00Z"
    receipt = _horizon_receipt()
    receipt["latest_discovered_in_policy_observed_at"] = None
    horizon = calculate_horizon(
        discovery=[],
        index_coverage=[{
            "index_date": "2026-08-20", "status": "complete",
            "policy_version": "fixture-policy/1",
        }],
        manifests=[invalid_sibling, valid_sibling],
        events=[{"filing_date": "2026-08-20"}],
        telemetry={
            "generation_id": "generation:cs:" + "c" * 24,
            "as_of": "2026-08-21T01:00:00Z",
        },
        queue_receipt=receipt,
        calculated_at="2026-08-21T01:01:00Z",
    )
    assert horizon["state"] == "unavailable"
    assert "discovered_observed_at_missing" in horizon["reason_codes"]
    assert "retained_observed_at_invalid" in horizon["reason_codes"]


def test_horizon_missing_retained_clock_is_unavailable():
    manifest = _horizon_manifest("2026-08-20")
    manifest["retrieval"]["retrieved_at"] = None
    horizon = calculate_horizon(
        discovery=[],
        index_coverage=[{
            "index_date": "2026-08-20", "status": "complete",
            "policy_version": "fixture-policy/1",
        }],
        manifests=[manifest], events=[{"filing_date": "2026-08-20"}],
        telemetry={
            "generation_id": "generation:cs:" + "c" * 24,
            "as_of": "2026-08-21T01:00:00Z",
        },
        queue_receipt=_horizon_receipt(),
        calculated_at="2026-08-21T01:01:00Z",
    )
    assert horizon["state"] == "unavailable"
    assert "retained_observed_at_missing" in horizon["reason_codes"]


def test_horizon_lag_reports_fourteen_completed_sec_sessions_not_calendar_days():
    horizon = _calculate_horizon(retained="2026-07-31", compiled="2026-07-31")
    assert horizon["state"] == "lagging"
    assert "retained_behind_discovery" in horizon["reason_codes"]
    assert "compiled_behind_retained_or_discovery" in horizon["reason_codes"]
    assert horizon["gaps"]["discovery_to_retained_completed_sessions"] == 14
    assert horizon["gaps"]["retained_to_compiled_completed_sessions"] == 0


def test_horizon_capacity_degradation_uses_explicit_arrival_and_unserved_metrics():
    horizon = _calculate_horizon(
        receipt=_horizon_receipt(
            arrivals=199, capacity=180, pending=1320, selected=180,
        )
    )
    assert horizon["state"] == "degraded_capacity"
    assert horizon["live_tail"]["live_tail_arrival_overflow"] == 19
    assert horizon["live_tail"]["live_tail_unserved_after_selection"] == 1140
    assert "live_tail_arrival_overflow" in horizon["reason_codes"]
    assert "live_tail_unserved_after_selection" in horizon["reason_codes"]


@pytest.mark.parametrize(
    ("arrivals", "pending", "selected", "state", "overflow"),
    [
        (500, 500, 500, "current", 0),
        (501, 501, 500, "degraded_capacity", 1),
    ],
)
def test_w2b_horizon_keeps_the_500_arrival_boundary_honest(
    arrivals: int, pending: int, selected: int, state: str, overflow: int,
):
    horizon = _calculate_horizon(
        receipt=_horizon_receipt(
            arrivals=arrivals, capacity=500, pending=pending, selected=selected,
        )
    )

    assert horizon["state"] == state
    assert horizon["live_tail"]["live_tail_arrival_overflow"] == overflow
    assert horizon["live_tail"]["live_tail_unserved_after_selection"] == overflow
    assert ("live_tail_arrival_overflow" in horizon["reason_codes"]) is (overflow > 0)


def test_w2b_zero_arrival_overflow_does_not_hide_inherited_live_debt():
    horizon = _calculate_horizon(
        receipt=_horizon_receipt(
            arrivals=485, capacity=500, pending=1_342, selected=500,
        )
    )

    assert horizon["state"] == "degraded_capacity"
    assert horizon["live_tail"]["live_tail_arrival_overflow"] == 0
    assert horizon["live_tail"]["live_tail_unserved_after_selection"] == 842
    assert "live_tail_arrival_overflow" not in horizon["reason_codes"]
    assert "live_tail_unserved_after_selection" in horizon["reason_codes"]


def test_horizon_exposes_run_scoped_work_class_retrieval_progress():
    receipt = _horizon_receipt()
    receipt["work_classes"].extend([
        {
            "work_class": "RECOVERY", "pending_count": 20,
            "selected_count": 20, "deferred_count": 0,
        },
        {
            "work_class": "HISTORICAL_BACKFILL", "pending_count": 1000,
            "selected_count": 20, "deferred_count": 980,
        },
    ])
    horizon = calculate_horizon(
        discovery=[],
        index_coverage=[{
            "index_date": "2026-08-20", "status": "complete",
            "policy_version": "fixture-policy/1",
        }],
        manifests=[_horizon_manifest("2026-08-20")],
        events=[{"filing_date": "2026-08-20"}],
        telemetry={
            "generation_id": "generation:cs:" + "c" * 24,
            "as_of": "2026-08-21T01:00:00Z",
        },
        queue_receipt=receipt,
        ingestion_run={"work_classes": [
            {
                "work_class": "LIVE_TAIL", "retrieved_count": 99,
                "parser_deferred_count": 0, "storage_deferred_count": 0,
                "transient_error_count": 1,
            },
            {
                "work_class": "RECOVERY", "retrieved_count": 18,
                "parser_deferred_count": 1, "storage_deferred_count": 1,
                "transient_error_count": 0,
            },
            {
                "work_class": "HISTORICAL_BACKFILL", "retrieved_count": 20,
                "parser_deferred_count": 0, "storage_deferred_count": 0,
                "transient_error_count": 0,
            },
        ]},
        calculated_at="2026-08-21T01:01:00Z",
    )
    classes = {row["work_class"]: row for row in horizon["work_classes"]}
    assert classes["LIVE_TAIL"]["retrieved_count"] == 99
    assert classes["RECOVERY"]["storage_deferred_count"] == 1
    assert classes["HISTORICAL_BACKFILL"] == {
        "work_class": "HISTORICAL_BACKFILL", "pending_count": 1000,
        "selected_count": 20, "deferred_count": 980,
        "retrieved_count": 20, "parser_deferred_count": 0,
        "storage_deferred_count": 0, "transient_error_count": 0,
    }


def test_horizon_discovery_retry_outranks_capacity_and_lagging_states():
    horizon = _calculate_horizon(
        retained="2026-07-31",
        compiled="2026-07-31",
        latest_status="retry",
        receipt=_horizon_receipt(
            arrivals=199, capacity=180, pending=1320, selected=180,
        ),
    )
    assert horizon["state"] == "degraded_discovery"
    assert horizon["watermarks"]["latest_expected_sec_index_date"] == "2026-08-21"
    assert horizon["watermarks"]["latest_expected_sec_index_status"] == "retry"
    assert "latest_expected_index_not_complete" in horizon["reason_codes"]


def _w2d_receipt(*, filing_date: str, observed_at: str) -> dict:
    receipt = _horizon_receipt()
    receipt["discovery_clock_policy_version"] = (
        "capital-structure-sec-discovery-clock/1.0.0"
    )
    receipt["latest_discovered_in_policy_filing_date"] = filing_date
    receipt["latest_discovered_in_policy_observed_at"] = observed_at
    return receipt


def _w2d_horizon(
    *,
    calculated_at: str,
    filing_date: str,
    daily_rows: list[dict],
    overlay_rows: list[dict],
) -> dict:
    policy = "fixture-policy/1"
    coverage = [
        row | {"policy_version": policy}
        for row in [*daily_rows, *overlay_rows]
    ]
    return calculate_horizon(
        discovery=[],
        index_coverage=coverage,
        manifests=[_horizon_manifest(filing_date)],
        events=[{"filing_date": filing_date}],
        telemetry={
            "generation_id": "generation:cs:" + "d" * 24,
            "as_of": calculated_at,
        },
        queue_receipt=_w2d_receipt(
            filing_date=filing_date, observed_at=calculated_at,
        ) | {"policy_version": policy},
        calculated_at=calculated_at,
    )


def test_w2d_monday_evening_ignores_not_yet_ready_monday_index_but_requires_overlay():
    horizon = _w2d_horizon(
        calculated_at="2026-08-24T22:30:00Z",  # Monday 18:30 ET
        filing_date="2026-08-24",
        daily_rows=[
            {"coverage_kind": "daily_index", "index_date": "2026-08-21", "status": "complete"},
            {"coverage_kind": "daily_index", "index_date": "2026-08-24", "status": "retry"},
        ],
        overlay_rows=[{
            "coverage_kind": "latest_filings", "index_date": "2026-08-24",
            "status": "complete", "observed_through": "2026-08-24T22:29:59Z",
        }],
    )

    assert horizon["state"] == "current"
    assert horizon["watermarks"]["latest_expected_sec_index_date"] == "2026-08-21"
    assert horizon["watermarks"]["latest_expected_sec_index_status"] == "complete"
    assert horizon["watermarks"]["latest_expected_realtime_filing_date"] == "2026-08-24"
    assert horizon["watermarks"]["latest_filings_status"] == "complete"
    assert "latest_expected_index_not_complete" not in horizon["reason_codes"]


def test_w2d_overlay_unavailable_degrades_even_when_daily_reconciliation_is_complete():
    horizon = _w2d_horizon(
        calculated_at="2026-08-24T22:30:00Z",
        filing_date="2026-08-24",
        daily_rows=[{
            "coverage_kind": "daily_index", "index_date": "2026-08-21",
            "status": "complete",
        }],
        overlay_rows=[{
            "coverage_kind": "latest_filings", "index_date": "2026-08-24",
            "status": "retry", "observed_through": None,
            "last_error": "HTTPError: HTTP 503",
        }],
    )

    assert horizon["state"] == "degraded_discovery"
    assert "latest_filings_observation_not_complete" in horizon["reason_codes"]


def test_w2d_missing_overlay_never_false_currents_on_yesterdays_index():
    horizon = _w2d_horizon(
        calculated_at="2026-08-24T22:30:00Z",
        filing_date="2026-08-24",
        daily_rows=[{
            "coverage_kind": "daily_index", "index_date": "2026-08-21",
            "status": "complete",
        }],
        overlay_rows=[],
    )

    assert horizon["state"] == "degraded_discovery"
    assert "latest_filings_observation_missing" in horizon["reason_codes"]


def test_w2d_after_readiness_missing_prior_day_daily_index_degrades():
    horizon = _w2d_horizon(
        calculated_at="2026-08-25T10:30:00Z",  # Tuesday 06:30 ET
        filing_date="2026-08-25",
        daily_rows=[{
            "coverage_kind": "daily_index", "index_date": "2026-08-24",
            "status": "retry",
        }],
        overlay_rows=[{
            "coverage_kind": "latest_filings", "index_date": "2026-08-25",
            "status": "complete", "observed_through": "2026-08-25T10:29:59Z",
        }],
    )

    assert horizon["state"] == "degraded_discovery"
    assert horizon["watermarks"]["latest_expected_sec_index_date"] == "2026-08-24"
    assert "latest_expected_index_not_complete" in horizon["reason_codes"]


@pytest.mark.parametrize(
    ("calculated_at", "expected_day"),
    [
        ("2026-08-29T16:00:00Z", "2026-08-28"),  # Saturday noon ET
        ("2026-09-07T22:30:00Z", "2026-09-04"),  # Labor Day evening ET
    ],
)
def test_w2d_weekend_and_holiday_use_last_real_filing_day(
    calculated_at: str, expected_day: str,
):
    horizon = _w2d_horizon(
        calculated_at=calculated_at,
        filing_date=expected_day,
        daily_rows=[{
            "coverage_kind": "daily_index", "index_date": expected_day,
            "status": "complete",
        }],
        overlay_rows=[{
            "coverage_kind": "latest_filings", "index_date": expected_day,
            "status": "complete", "observed_through": calculated_at,
        }],
    )

    assert horizon["state"] == "current"
    assert horizon["watermarks"]["latest_expected_realtime_filing_date"] == expected_day


def test_horizon_observed_sec_closed_day_is_not_a_discovery_failure():
    receipt = _horizon_receipt()
    completed = [
        {
            "index_date": "2026-08-20", "status": "complete",
            "policy_version": "fixture-policy/1",
        },
        {
            "index_date": "2026-08-21", "status": "not_published",
            "last_error": "SEC calendar closure: observed US federal holiday",
            "policy_version": "fixture-policy/1",
        },
    ]
    horizon = calculate_horizon(
        discovery=[], index_coverage=completed,
        manifests=[_horizon_manifest("2026-08-20")],
        events=[{"filing_date": "2026-08-20"}],
        telemetry={
            "generation_id": "generation:cs:" + "c" * 24,
            "as_of": "2026-08-21T01:00:00Z",
        },
        queue_receipt=receipt, calculated_at="2026-08-21T01:01:00Z",
    )
    assert horizon["state"] == "current"
    assert horizon["watermarks"]["latest_expected_sec_index_date"] == "2026-08-21"
    assert horizon["watermarks"]["latest_expected_sec_index_status"] == "not_published"
    assert "latest_expected_index_not_complete" not in horizon["reason_codes"]


def test_horizon_terminal_weekday_404_is_degraded_not_a_proven_closure():
    completed = [
        {
            "index_date": "2026-08-20", "status": "complete",
            "policy_version": "fixture-policy/1",
        },
        {
            "index_date": "2026-08-21", "status": "not_published",
            "last_error": "IndexNotPublished: SEC daily index HTTP 404: 2026-08-21",
            "policy_version": "fixture-policy/1",
        },
    ]
    horizon = calculate_horizon(
        discovery=[], index_coverage=completed,
        manifests=[_horizon_manifest("2026-08-20")],
        events=[{"filing_date": "2026-08-20"}],
        telemetry={
            "generation_id": "generation:cs:" + "c" * 24,
            "as_of": "2026-08-21T01:00:00Z",
        },
        queue_receipt=_horizon_receipt(),
        calculated_at="2026-08-21T01:01:00Z",
    )
    assert horizon["state"] == "degraded_discovery"
    assert "latest_expected_index_not_observed" in horizon["reason_codes"]


def test_horizon_invalid_coverage_date_is_unavailable_not_false_current():
    horizon = calculate_horizon(
        discovery=[],
        index_coverage=[{
            "index_date": "not-a-date", "status": "complete",
            "policy_version": "fixture-policy/1",
        }],
        manifests=[_horizon_manifest("2026-08-20")],
        events=[{"filing_date": "2026-08-20"}],
        telemetry={
            "generation_id": "generation:cs:" + "c" * 24,
            "as_of": "2026-08-21T01:00:00Z",
        },
        queue_receipt=_horizon_receipt(),
        calculated_at="2026-08-21T01:01:00Z",
    )
    assert horizon["state"] == "unavailable"
    assert "discovery_coverage_date_invalid" in horizon["reason_codes"]
    assert horizon["watermarks"]["latest_expected_sec_index_date"] is None


def test_horizon_invalid_retained_or_compiled_filing_date_is_unavailable():
    bad_manifest = _horizon_manifest("2026-08-20")
    bad_manifest["filing"]["filing_date"] = "2026-99-99"
    horizon = calculate_horizon(
        discovery=[],
        index_coverage=[{
            "index_date": "2026-08-20", "status": "complete",
            "policy_version": "fixture-policy/1",
        }],
        manifests=[bad_manifest],
        events=[{"filing_date": "not-a-date"}],
        telemetry={
            "generation_id": "generation:cs:" + "c" * 24,
            "as_of": "2026-08-21T01:00:00Z",
        },
        queue_receipt=_horizon_receipt(),
        calculated_at="2026-08-21T01:01:00Z",
    )
    assert horizon["state"] == "unavailable"
    assert "retained_watermark_invalid" in horizon["reason_codes"]
    assert "compiled_watermark_invalid" in horizon["reason_codes"]


def test_missing_helpers_normalize_pandas_na_without_ambiguous_truth_value():
    from engine.capital_structure.ingestion_health import _opt_int, _opt_str

    assert _opt_str(pd.NA) is None
    assert _opt_int(pd.NA) is None


def test_horizon_missing_legacy_work_class_receipt_is_unavailable_not_fresh():
    horizon = _calculate_horizon(receipt={"policy_version": "fixture-policy/1"})
    assert horizon["state"] == "unavailable"
    assert "live_tail_metrics_unavailable" in horizon["reason_codes"]
    assert all(value is None for value in horizon["live_tail"].values())
