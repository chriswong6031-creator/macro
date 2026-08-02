from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json

import pandas as pd
import pytest

import collectors.sec_capital_structure as filings
import collectors.sec_capital_structure_companyfacts as companyfacts
from engine.capital_structure.source_store import ContentAddressedSourceStore, LocalStore


SUBMISSION = b"""\
<SEC-DOCUMENT>0001234567-26-000001.txt
<ACCEPTANCE-DATETIME>20260801123456
<FILE-NUMBER>333-123456
<DOCUMENT>
<TYPE>S-3
<SEQUENCE>1
<FILENAME>forms3.htm
<TEXT><html><body>Registration statement.</body></html></TEXT>
</DOCUMENT>
"""


class Response:
    def __init__(self, body: bytes, *, status: int = 200, headers: dict | None = None):
        self.body = body
        self.status_code = status
        self.headers = headers or {}
        self.closed = False

    def iter_content(self, *, chunk_size: int):
        for index in range(0, len(self.body), chunk_size):
            yield self.body[index:index + chunk_size]

    def close(self):
        self.closed = True


def _now() -> datetime:
    return datetime(2026, 8, 2, 12, 0, tzinfo=timezone.utc)


def _store(tmp_path):
    return ContentAddressedSourceStore(LocalStore(tmp_path / "objects"))


def _anchor_manifest(store):
    receipt = store.put_verified(SUBMISSION, media_type="text/plain")
    assert receipt is not None
    discovery = {
        "accession": "0001234567-26-000001", "cik": "0001234567", "ticker": "ACME",
        "company_name": "ACME CORP", "form": "S-3", "filing_date": "2026-08-01",
        "collection_scope": "registration_issuance",
    }
    bundle = filings.parse_submission(SUBMISSION)
    record = filings.SecCapitalStructureAdapter._manifest_record(
        discovery=discovery, bundle=bundle, source_id="0001234567-26-000001:0:complete-submission.txt",
        canonical_url="https://www.sec.gov/Archives/edgar/data/1234567/0001234567-26-000001.txt",
        document_name="complete-submission.txt", document_type="S-3", document_role="complete_submission",
        sequence="0", raw=SUBMISSION, receipt=receipt,
        inspection=filings.inspect_source_document(SUBMISSION, filename="complete-submission.txt", document_role="complete_submission"),
        retrieved_at="2026-08-02T10:00:00Z", first_seen_at="2026-08-02T10:00:00Z",
        document_version=1, parent_manifest_id=None,
    )
    filings._validate_source_manifest(record)
    return record


def _write_anchor(root, manifest):
    path = root.parent / "source_manifest.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([manifest]).to_parquet(path, index=False)


def _payload(cik: str = "0001234567") -> bytes:
    return json.dumps({"cik": cik, "entityName": "Acme Corp", "facts": {"us-gaap": {}}}).encode()


def _adapter(tmp_path, monkeypatch, response: Response, *, source_store=None, max_ciks=24):
    root = tmp_path / "data" / "capital_structure" / "companyfacts"
    monkeypatch.setattr(companyfacts, "_data_root", lambda: root)
    return companyfacts.SecCapitalStructureCompanyFactsAdapter(
        source_store=source_store or _store(tmp_path), now_fn=_now,
        fetcher=lambda *args, **kwargs: response, sleeper=lambda _: None,
        monotonic=lambda: 1.0, max_ciks_per_run=max_ciks,
    ), root


def test_companyfacts_url_and_stream_admission_are_cik_bound():
    assert companyfacts.companyfacts_url("1234567").endswith("CIK0001234567.json")
    assert companyfacts.stream_companyfacts_response(
        Response(_payload()), cik="0001234567", url=companyfacts.companyfacts_url("1234567"), limit=10000
    ) == _payload()
    with pytest.raises(companyfacts.CompanyFactsDeferred, match="CIK does not match"):
        companyfacts.stream_companyfacts_response(
            Response(_payload("0000000001")), cik="0001234567", url="https://data.sec.gov/example", limit=10000
        )


def test_stream_rejects_declared_and_actual_oversize():
    with pytest.raises(companyfacts.CompanyFactsResponseTooLarge):
        companyfacts.stream_companyfacts_response(
            Response(_payload(), headers={"Content-Length": "200"}), cik="0001234567", url="https://data.sec.gov/example", limit=20
        )
    with pytest.raises(companyfacts.CompanyFactsResponseTooLarge):
        companyfacts.stream_companyfacts_response(
            Response(_payload()), cik="0001234567", url="https://data.sec.gov/example", limit=20
        )


def test_verified_anchor_selection_is_unique_and_rejects_unverified(tmp_path):
    store = _store(tmp_path)
    valid = _anchor_manifest(store)
    duplicate = json.loads(json.dumps(valid))
    duplicate["retrieval"]["first_seen_at"] = "2026-08-03T10:00:00Z"
    duplicate["manifest_id"] = filings.manifest_id_for({key: value for key, value in duplicate.items() if key != "manifest_id"})
    unverified = json.loads(json.dumps(valid))
    unverified["storage"]["retention_state"] = "missing"
    unverified["manifest_id"] = filings.manifest_id_for({key: value for key, value in unverified.items() if key != "manifest_id"})
    anchors = companyfacts._verified_complete_submission_anchors([valid, duplicate, unverified])
    assert list(anchors) == ["0001234567"]
    assert anchors["0001234567"]["manifest_id"] == valid["manifest_id"]


def test_queue_is_bounded_deterministic_and_retries_before_new():
    now = _now()
    anchors = {
        "0000000001": {"first_seen_at": now - timedelta(days=2), "manifest_id": "manifest:cs:" + "1" * 64, "source_id": "a", "content_sha256": "1" * 64},
        "0000000002": {"first_seen_at": now - timedelta(days=1), "manifest_id": "manifest:cs:" + "2" * 64, "source_id": "b", "content_sha256": "2" * 64},
    }
    retry = {
        "schema": companyfacts.COVERAGE_ROW_SCHEMA, "cik": "0000000002", "anchor_manifest_id": anchors["0000000002"]["manifest_id"],
        "anchor_first_seen_at": "2026-08-01T12:00:00Z", "attempted_at": "2026-08-01T12:00:00Z", "attempt_count": 1,
        "queue_reason": "new_anchor", "state": "retry", "retry_after": "2026-08-02T11:00:00Z", "error": "network",
        "result": {"source_manifest_id": None, "content_sha256": None, "byte_length": None},
    }
    retry["coverage_id"] = companyfacts._coverage_id(retry)
    queue, deferred, skipped_fresh = companyfacts.select_companyfacts_queue(anchors, [retry], now=now, max_ciks=1)
    assert [row["cik"] for row in queue] == ["0000000002"]
    assert deferred == 1
    assert skipped_fresh == 0


def test_adapter_retains_source_manifest_coverage_and_telemetry_last(tmp_path, monkeypatch):
    store = _store(tmp_path)
    adapter, root = _adapter(tmp_path, monkeypatch, Response(_payload()), source_store=store)
    _write_anchor(root, _anchor_manifest(store))
    result = adapter.fetch()
    assert result["sec_companyfacts_intake"].iloc[0]["retrieved"] == 1
    manifest_path = root / "source_manifest.parquet"
    coverage_path = root / "coverage.parquet"
    receipt_path = root / "coverage_receipt.json"
    manifest = pd.read_parquet(manifest_path).iloc[0].to_dict()
    coverage = pd.read_parquet(coverage_path).iloc[0].to_dict()
    receipt = json.loads(receipt_path.read_text())
    assert manifest["schema"] == companyfacts.SOURCE_MANIFEST_SCHEMA
    assert manifest["source_id"].startswith("sec-companyfacts:0001234567:")
    assert coverage["state"] == "retrieved"
    assert coverage["result"]["source_manifest_id"] == manifest["manifest_id"]
    assert receipt["companyfacts_manifest_ledger"] == companyfacts._ledger_receipt(companyfacts._records(pd.read_parquet(manifest_path)))
    assert receipt["coverage_ledger"] == companyfacts._ledger_receipt(companyfacts._records(pd.read_parquet(coverage_path)))
    assert receipt["authority"]["share_count_ledger_authority"] is False
    assert any("share-count" in item.lower() for item in receipt["nonclaims"])
    assert any("prophet" in item.lower() for item in receipt["nonclaims"])


def test_adapter_defers_invalid_json_without_source_manifest(tmp_path, monkeypatch):
    store = _store(tmp_path)
    adapter, root = _adapter(tmp_path, monkeypatch, Response(b"not json"), source_store=store)
    _write_anchor(root, _anchor_manifest(store))
    adapter.fetch()
    coverage = pd.read_parquet(root / "coverage.parquet").iloc[0].to_dict()
    assert coverage["state"] == "deferred"
    assert coverage["result"]["source_manifest_id"] is None
    assert pd.read_parquet(root / "source_manifest.parquet").empty


def test_adapter_no_anchors_makes_no_network_call_and_receipts_empty(tmp_path, monkeypatch):
    called = []
    adapter, root = _adapter(tmp_path, monkeypatch, Response(_payload()))
    adapter._fetcher = lambda *args, **kwargs: called.append(args)  # pragma: no cover - must not execute
    result = adapter.fetch()
    receipt = json.loads((root / "coverage_receipt.json").read_text())
    assert called == []
    assert result["sec_companyfacts_intake"].iloc[0]["eligible_ciks"] == 0
    assert receipt["status"] == "no_eligible_anchors"
    assert receipt["companyfacts_manifest_ledger"]["record_count"] == 0


def test_source_store_failure_is_retry_not_manifest(tmp_path, monkeypatch):
    class FailingStore:
        def put_verified(self, raw, *, media_type):
            return None

    adapter, root = _adapter(tmp_path, monkeypatch, Response(_payload()), source_store=FailingStore())
    _write_anchor(root, _anchor_manifest(_store(tmp_path)))
    adapter.fetch()
    row = pd.read_parquet(root / "coverage.parquet").iloc[0].to_dict()
    assert row["state"] == "retry"
    assert row["result"]["source_manifest_id"] is None


def test_receipt_is_not_published_if_ledger_pair_fails(tmp_path, monkeypatch):
    store = _store(tmp_path)
    adapter, root = _adapter(tmp_path, monkeypatch, Response(_payload()), source_store=store)
    _write_anchor(root, _anchor_manifest(store))
    original = companyfacts._encoded_parquet
    calls = {"count": 0}

    def fail_second(frame, target):
        calls["count"] += 1
        if calls["count"] == 2:
            raise OSError("coverage staging failed")
        return original(frame, target)

    monkeypatch.setattr(companyfacts, "_encoded_parquet", fail_second)
    with pytest.raises(OSError, match="coverage staging failed"):
        adapter.fetch()
    assert not (root / "coverage_receipt.json").exists()
