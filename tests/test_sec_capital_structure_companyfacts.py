from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json

import pandas as pd
import pytest
import requests

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


class Clock:
    """A strictly increasing UTC source clock, including repeated test calls."""

    def __init__(self, start: datetime | None = None):
        self.value = start or datetime(2026, 8, 2, 12, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        current = self.value
        self.value += timedelta(seconds=1)
        return current


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
    anchor_path = root.parent / "source_manifest.parquet"
    anchor_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([manifest]).to_parquet(anchor_path, index=False)


def _payload(cik: str = "0001234567") -> bytes:
    return json.dumps({"cik": cik, "entityName": "Acme Corp", "facts": {"us-gaap": {}}}).encode()


def _adapter(tmp_path, monkeypatch, response: Response, *, source_store=None, max_ciks=24, clock=None, **limits):
    root = tmp_path / "data" / "capital_structure" / "companyfacts"
    monkeypatch.setattr(companyfacts, "_data_root", lambda: root)
    return companyfacts.SecCapitalStructureCompanyFactsAdapter(
        source_store=source_store or _store(tmp_path), now_fn=clock or Clock(),
        fetcher=lambda *args, **kwargs: response, sleeper=lambda _: None,
        monotonic=lambda: 1.0, max_ciks_per_run=max_ciks, **limits,
    ), root


def _selected(root):
    pointer = json.loads((root / "coverage_receipt.json").read_text())
    receipt = json.loads((root / pointer["receipt_path"]).read_text())
    source_path, coverage_path = companyfacts._generation_paths(root, receipt["generation"])
    sources = companyfacts._records(pd.read_parquet(source_path))
    coverage = companyfacts._records(pd.read_parquet(coverage_path))
    return pointer, receipt, sources, coverage


def _load_selected(root, anchor):
    return companyfacts._load_committed_bundle(
        root=root, receipt_path=root / "coverage_receipt.json", anchor_records=[anchor],
    )


def _coverage_row(*, cik: str, anchor_id: str, state: str, attempted_at: str, attempt_count: int = 1):
    row = {
        "schema": companyfacts.COVERAGE_ROW_SCHEMA,
        "cik": cik,
        "anchor_manifest_id": anchor_id,
        "anchor_first_seen_at": "2026-08-01T12:00:00Z",
        "attempted_at": attempted_at,
        "attempt_count": attempt_count,
        "queue_reason": "new_anchor" if attempt_count == 1 else "retry_due",
        "state": state,
        "retry_after": None if state == "retrieved" else "2026-08-02T11:00:00Z",
        "error": None if state == "retrieved" else "network",
        "result": {
            "source_manifest_id": "manifest:cs-companyfacts:" + "a" * 64 if state == "retrieved" else None,
            "content_sha256": "a" * 64 if state == "retrieved" else None,
            "byte_length": 1 if state == "retrieved" else None,
        },
    }
    row["attempt_id"] = companyfacts._attempt_id(row)
    row["coverage_id"] = companyfacts._coverage_id(row)
    return row


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


def test_queue_is_bounded_deterministic_and_nonempty_lanes_progress():
    now = _now()
    anchors = {
        "0000000001": {"first_seen_at": now - timedelta(days=2), "manifest_id": "manifest:cs:" + "1" * 64, "source_id": "a", "content_sha256": "1" * 64},
        "0000000002": {"first_seen_at": now - timedelta(days=9), "manifest_id": "manifest:cs:" + "2" * 64, "source_id": "b", "content_sha256": "2" * 64},
        "0000000003": {"first_seen_at": now - timedelta(days=1), "manifest_id": "manifest:cs:" + "3" * 64, "source_id": "c", "content_sha256": "3" * 64},
    }
    retry = _coverage_row(cik="0000000001", anchor_id=anchors["0000000001"]["manifest_id"], state="retry", attempted_at="2026-08-01T10:00:00Z")
    fresh = _coverage_row(cik="0000000002", anchor_id=anchors["0000000002"]["manifest_id"], state="retrieved", attempted_at="2026-07-20T10:00:00Z")
    selected_lanes = set()
    for offset in range(4):
        diagnostics = {}
        queue, deferred, skipped_fresh = companyfacts.select_companyfacts_queue(
            anchors, [retry, fresh], now=now + timedelta(days=offset), max_ciks=1, diagnostics=diagnostics,
        )
        assert len(queue) == 1
        assert deferred >= 2
        assert skipped_fresh == 0
        assert sum(diagnostics["selected_by_reason"].values()) == 1
        selected_lanes.add(queue[0]["queue_reason"])
    assert selected_lanes == {"retry_due", "new_anchor", "refresh_due"}


def test_publish_uses_immutable_generation_receipt_and_tiny_pointer(tmp_path, monkeypatch):
    store = _store(tmp_path)
    anchor = _anchor_manifest(store)
    adapter, root = _adapter(tmp_path, monkeypatch, Response(_payload()), source_store=store)
    _write_anchor(root, anchor)
    result = adapter.fetch()
    pointer, receipt, sources, coverage = _selected(root)
    assert result["sec_companyfacts_intake"].iloc[0]["status"] == "ok"
    assert pointer["schema"] == companyfacts.CURRENT_POINTER_SCHEMA
    assert receipt["sequence"] == 1 and receipt["previous_receipt"] is None
    assert receipt["status"] == "ok"
    assert len(sources) == len(coverage) == 1
    assert not (root / "source_manifest.parquet").exists()
    assert not (root / "coverage.parquet").exists()
    loaded_sources, loaded_coverage, loaded_receipt = _load_selected(root, anchor)
    assert loaded_sources == sources
    assert loaded_coverage == coverage
    assert loaded_receipt["receipt_id"] == receipt["receipt_id"]
    assert pointer["generation_id"] == receipt["generation"]["generation_id"]


def test_force_refresh_appends_history_and_authenticates_full_chain(tmp_path, monkeypatch):
    store = _store(tmp_path)
    anchor = _anchor_manifest(store)
    adapter, root = _adapter(tmp_path, monkeypatch, Response(_payload()), source_store=store)
    _write_anchor(root, anchor)
    adapter.fetch()
    pointer_one, receipt_one, _, coverage_one = _selected(root)
    adapter.fetch(full_history=True)
    pointer_two, receipt_two, sources_two, coverage_two = _selected(root)
    assert pointer_one != pointer_two
    assert receipt_two["sequence"] == 2
    assert receipt_two["previous_receipt"]["receipt_id"] == receipt_one["receipt_id"]
    assert receipt_two["generation"]["generation_id"] != receipt_one["generation"]["generation_id"]
    assert companyfacts._parse_stamp(receipt_one["published_at"], field="test") <= companyfacts._parse_stamp(
        receipt_two["selection_as_of"], field="test"
    )
    assert len(sources_two) == len(coverage_two) == 2
    assert coverage_two[0] == coverage_one[0]
    assert coverage_two[1]["queue_reason"] == "refresh_due"
    assert len({row["attempt_id"] for row in coverage_two}) == 2
    assert _load_selected(root, anchor)[2]["sequence"] == 2


def test_deferred_and_no_anchor_statuses_are_honest(tmp_path, monkeypatch):
    store = _store(tmp_path)
    anchor = _anchor_manifest(store)
    adapter, root = _adapter(tmp_path, monkeypatch, Response(b"not json"), source_store=store)
    _write_anchor(root, anchor)
    adapter.fetch()
    _, receipt, sources, coverage = _selected(root)
    assert receipt["status"] == "blocked"
    assert sources == []
    assert coverage[0]["state"] == "deferred"
    assert receipt["population"] == {"fresh_ciks": 0, "stale_ciks": 0, "pending_ciks": 1, "retry_ciks": 0, "deferred_ciks": 1}

    no_anchor, empty_root = _adapter(tmp_path / "empty", monkeypatch, Response(_payload()))
    called = []
    no_anchor._fetcher = lambda *args, **kwargs: called.append(args)
    result = no_anchor.fetch()
    _, empty_receipt, empty_sources, empty_coverage = _selected(empty_root)
    assert called == []
    assert result["sec_companyfacts_intake"].iloc[0]["status"] == "no_eligible_anchors"
    assert empty_receipt["status"] == "no_eligible_anchors"
    assert empty_sources == empty_coverage == []


def test_status_taxonomy_covers_complete_partial_stale_and_blocked_populations():
    assert companyfacts._coverage_status(eligible_ciks=2, population={"fresh_ciks": 2, "stale_ciks": 0, "pending_ciks": 0}) == "ok"
    assert companyfacts._coverage_status(eligible_ciks=2, population={"fresh_ciks": 1, "stale_ciks": 0, "pending_ciks": 1}) == "partial"
    assert companyfacts._coverage_status(eligible_ciks=1, population={"fresh_ciks": 0, "stale_ciks": 1, "pending_ciks": 0}) == "degraded"
    assert companyfacts._coverage_status(eligible_ciks=1, population={"fresh_ciks": 0, "stale_ciks": 0, "pending_ciks": 1}) == "blocked"


def test_source_store_failure_is_retry_not_manifest(tmp_path, monkeypatch):
    class FailingStore:
        def put_verified(self, raw, *, media_type):
            return None

    anchor_store = _store(tmp_path)
    anchor = _anchor_manifest(anchor_store)
    adapter, root = _adapter(tmp_path, monkeypatch, Response(_payload()), source_store=FailingStore())
    _write_anchor(root, anchor)
    adapter.fetch()
    _, receipt, sources, coverage = _selected(root)
    assert receipt["status"] == "blocked"
    assert sources == []
    assert coverage[0]["state"] == "retry"


@pytest.mark.parametrize("target", ["_install_generation", "_write_immutable_bytes", "_atomic_write_bytes"])
def test_last_good_selection_survives_each_publish_stage_fault(tmp_path, monkeypatch, target):
    store = _store(tmp_path)
    anchor = _anchor_manifest(store)
    adapter, root = _adapter(tmp_path, monkeypatch, Response(_payload()), source_store=store)
    _write_anchor(root, anchor)
    adapter.fetch()
    prior_pointer = (root / "coverage_receipt.json").read_bytes()

    def explode(*args, **kwargs):
        raise OSError(f"injected {target} fault")

    monkeypatch.setattr(companyfacts, target, explode)
    with pytest.raises(OSError, match="injected"):
        adapter.fetch(full_history=True)
    assert (root / "coverage_receipt.json").read_bytes() == prior_pointer
    loaded_sources, loaded_coverage, loaded_receipt = _load_selected(root, anchor)
    assert len(loaded_sources) == len(loaded_coverage) == 1
    assert loaded_receipt["sequence"] == 1


def test_startup_refuses_tampered_pointer_or_selected_generation_before_network(tmp_path, monkeypatch):
    store = _store(tmp_path)
    anchor = _anchor_manifest(store)
    adapter, root = _adapter(tmp_path, monkeypatch, Response(_payload()), source_store=store)
    _write_anchor(root, anchor)
    adapter.fetch()
    pointer, receipt, _, _ = _selected(root)
    prior_pointer_body = (root / "coverage_receipt.json").read_bytes()
    pointer["pointer_id"] = "pointer:cs-companyfacts:" + "0" * 64
    (root / "coverage_receipt.json").write_bytes(companyfacts._canonical_bytes(pointer) + b"\n")
    called = []
    adapter._fetcher = lambda *args, **kwargs: called.append(args)
    with pytest.raises(companyfacts.CompanyFactsIntakeError, match="pointer.*identity"):
        adapter.fetch()
    assert called == []

    # Restore the immutable selector, then corrupt an exact selected-generation file.
    pointer_path = root / "coverage_receipt.json"
    pointer_path.write_bytes(prior_pointer_body)
    _, coverage_path = companyfacts._generation_paths(root, receipt["generation"])
    coverage_path.write_bytes(b"corrupt")
    with pytest.raises(companyfacts.CompanyFactsIntakeError, match="exact-byte"):
        adapter.fetch()


def test_body_identity_and_cross_ledger_semantics_are_fail_closed(tmp_path, monkeypatch):
    store = _store(tmp_path)
    anchor = _anchor_manifest(store)
    adapter, root = _adapter(tmp_path, monkeypatch, Response(_payload()), source_store=store)
    _write_anchor(root, anchor)
    adapter.fetch()
    _, _, sources, coverage = _selected(root)

    bad_attempt = deepcopy(coverage[0])
    bad_attempt["attempt_id"] = "attempt:cs-companyfacts:" + "0" * 64
    bad_attempt["coverage_id"] = companyfacts._coverage_id(bad_attempt)
    with pytest.raises(companyfacts.CompanyFactsIntakeError, match="logical attempt body identity"):
        companyfacts._validate_companyfacts_bundle(
            anchor_records=[anchor], source_records=sources, coverage_records=[bad_attempt],
        )

    bad_source = deepcopy(sources[0])
    bad_source["source_id"] = "sec-companyfacts:0001234567:" + "0" * 64
    bad_source["manifest_id"] = companyfacts._source_manifest_id(bad_source)
    bad_coverage = deepcopy(coverage[0])
    bad_coverage["result"]["source_manifest_id"] = bad_source["manifest_id"]
    bad_coverage["coverage_id"] = companyfacts._coverage_id(bad_coverage)
    with pytest.raises(companyfacts.CompanyFactsIntakeError, match="source_id/CIK/hash binding"):
        companyfacts._validate_companyfacts_bundle(
            anchor_records=[anchor], source_records=[bad_source], coverage_records=[bad_coverage],
        )


def test_retry_after_global_cooldown_and_total_run_byte_budget(tmp_path, monkeypatch):
    responses = [
        Response(b"", status=429, headers={"Retry-After": "99999"}),
        Response(b"", status=429, headers={"Retry-After": "99999"}),
        Response(b"", status=429, headers={"Retry-After": "99999"}),
        Response(_payload()),
    ]
    sleeps = []
    adapter, _ = _adapter(tmp_path, monkeypatch, Response(_payload()))
    adapter._fetcher = lambda *args, **kwargs: responses.pop(0)
    adapter._sleep = sleeps.append
    with pytest.raises(requests.HTTPError):
        adapter._fetch_companyfacts("0001234567")
    assert adapter._fetch_companyfacts("0001234567") == _payload()
    assert any(delay == companyfacts.MAX_RETRY_COOLDOWN_SECONDS for delay in sleeps)

    limited, _ = _adapter(
        tmp_path / "limited", monkeypatch, Response(_payload()),
        max_run_bytes=20, max_response_bytes=10_000,
    )
    limited._run_deadline = 10.0
    with pytest.raises(companyfacts.CompanyFactsRunBudgetExceeded, match="byte budget"):
        limited._fetch_companyfacts("0001234567")
    assert limited._run_bytes > limited.max_run_bytes
