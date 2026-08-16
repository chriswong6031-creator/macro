"""Ingestion-truth gate: selected filings with zero durable evidence must fail."""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

import collectors.sec_capital_structure as sec
from engine.capital_structure.ingestion_health import (
    census_attempts,
    evaluate_health,
    health_exit_code,
    source_high_watermark,
)
from engine.capital_structure.source_ledger_io import read_source_ledger, source_ledger_path
from engine.capital_structure.source_store import ContentAddressedSourceStore
from engine.research_vault.r2_store import LocalStore
from scripts.check_capital_structure_health import main as health_main
from tests.test_sec_capital_structure import OneDayAdapter


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
    monkeypatch.setattr(sec, "_data_dir", lambda: tmp_path / "capital_structure")
    monkeypatch.setattr(sec, "_cik_map", lambda: {1234567: "ACME"})
    monkeypatch.setattr(sec, "_ua", lambda: "test@example.com")
    monkeypatch.setattr(sec, "PACE_SECONDS", 0)
    monkeypatch.setattr(
        sec, "due_index_dates", lambda *args, **kwargs: [date(2026, 8, 1)]
    )
    return OneDayAdapter(
        source_store=source_store,
        now_fn=lambda: datetime(2026, 8, 16, 13, 0, tzinfo=timezone.utc),
        max_filings_per_run=max_filings,
    )


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
