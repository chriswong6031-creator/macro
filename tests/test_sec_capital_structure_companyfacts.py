from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import threading
import time

import pandas as pd
import pytest
import requests

import collectors.base as collector_base
import collectors.sec_capital_structure as filings
import collectors.sec_capital_structure_companyfacts as companyfacts
from engine.capital_structure.source_store import ContentAddressedSourceStore, LocalStore


_TEST_TRUST: dict[str, tuple[companyfacts.CompanyFactsSigner, companyfacts.CompanyFactsHeadGuard]] = {}

SUBMISSION = b"""\
<SEC-DOCUMENT>0001234567-26-000001.txt
<SEC-HEADER>
<ACCESSION-NUMBER>0001234567-26-000001
<CENTRAL-INDEX-KEY>0001234567
<CONFORMED-SUBMISSION-TYPE>S-3
<ACCEPTANCE-DATETIME>20260801123456
<FILE-NUMBER>333-123456
</SEC-HEADER>
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


def _anchor_manifest(store, *, cik: str = "0001234567", ticker: str = "ACME"):
    raw = SUBMISSION.replace(b"0001234567", cik.encode("ascii"))
    receipt = store.put_verified(raw, media_type="text/plain")
    assert receipt is not None
    accession = f"{cik}-26-000001"
    discovery = {
        "accession": accession, "cik": cik, "ticker": ticker,
        "company_name": f"{ticker} CORP", "form": "S-3", "filing_date": "2026-08-01",
        "collection_scope": "registration_issuance",
    }
    bundle = filings.parse_submission(raw)
    record = filings.SecCapitalStructureAdapter._manifest_record(
        discovery=discovery, bundle=bundle, source_id=f"{accession}:0:complete-submission.txt",
        canonical_url=f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession}.txt",
        document_name="complete-submission.txt", document_type="S-3", document_role="complete_submission",
        sequence="0", raw=raw, receipt=receipt,
        inspection=filings.inspect_source_document(raw, filename="complete-submission.txt", document_role="complete_submission"),
        retrieved_at="2026-08-02T10:00:00Z", first_seen_at="2026-08-02T10:00:00Z",
        document_version=1, parent_manifest_id=None,
    )
    filings._validate_source_manifest(record)
    return record


def _write_anchor(root, manifest):
    anchor_path = root.parent / "source_manifest.parquet"
    anchor_path.parent.mkdir(parents=True, exist_ok=True)
    records = manifest if isinstance(manifest, list) else [manifest]
    pd.DataFrame(records).to_parquet(anchor_path, index=False)


def _payload(cik: str = "0001234567") -> bytes:
    return json.dumps({"cik": cik, "entityName": "Acme Corp", "facts": {"us-gaap": {}}}).encode()


def _adapter(
    tmp_path, monkeypatch, response: Response, *, source_store=None, source_stores=None,
    max_ciks=24, clock=None, **limits,
):
    root = tmp_path / "data" / "capital_structure" / "companyfacts"
    monkeypatch.setattr(companyfacts, "_data_root", lambda: root)
    signer = companyfacts.DeterministicTestCompanyFactsSigner("T" * 32, key_id="companyfacts-test-v1")
    guard = companyfacts.InMemoryCompanyFactsHeadGuard(signer)
    _TEST_TRUST[str(root)] = (signer, guard)
    ticks = [1.0]
    def monotonic():
        return ticks[0]
    def sleeper(delay):
        ticks[0] += delay
    return companyfacts.SecCapitalStructureCompanyFactsAdapter(
        source_store=source_store or _store(tmp_path), source_stores=source_stores,
        now_fn=clock or Clock(),
        fetcher=lambda *args, **kwargs: response, sleeper=sleeper,
        monotonic=monotonic, max_ciks_per_run=max_ciks, signer=signer, head_guard=guard, **limits,
    ), root


def _selected(root):
    pointer = json.loads((root / "coverage_receipt.json").read_text())
    receipt = json.loads((root / pointer["receipt_path"]).read_text())
    source_path, coverage_path = companyfacts._generation_paths(root, receipt["generation"])
    sources = companyfacts._records(pd.read_parquet(source_path))
    coverage = companyfacts._records(pd.read_parquet(coverage_path))
    return pointer, receipt, sources, coverage


def _load_selected(root, anchor):
    signer, guard = _TEST_TRUST[str(root)]
    head, _ = guard.read()
    return companyfacts._load_committed_bundle(
        root=root, receipt_path=root / "coverage_receipt.json", anchor_records=[anchor],
        signer=signer, head_witness=head,
    )


def _trust(root):
    return _TEST_TRUST[str(root)]


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
        anchors, [retry, fresh], now=now, max_ciks=1,
            cursor_sequence=offset, diagnostics=diagnostics,
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
    assert receipt["queue"]["anchor_verifications"] == [{
        **companyfacts._anchor_storage_binding(companyfacts._anchor_candidate(anchor)),
        "status": "verified", "error": None,
    }]
    assert sources[0]["anchor"]["complete_submission_store_id"] == anchor["storage"]["store_id"]
    assert sources[0]["anchor"]["complete_submission_object_key"] == anchor["storage"]["object_key"]
    assert not (root / "source_manifest.parquet").exists()
    assert not (root / "coverage.parquet").exists()
    loaded_sources, loaded_coverage, loaded_receipt = _load_selected(root, anchor)
    assert loaded_sources == sources
    assert loaded_coverage == coverage
    assert loaded_receipt["receipt_id"] == receipt["receipt_id"]
    assert pointer["generation_id"] == receipt["generation"]["generation_id"]


@pytest.mark.parametrize("surface", ["source_storage", "source_anchor", "receipt_anchor"])
def test_closed_contracts_reject_backend_store_namespace_mismatch(
    tmp_path, monkeypatch, surface,
):
    store = _store(tmp_path)
    anchor = _anchor_manifest(store)
    adapter, root = _adapter(tmp_path, monkeypatch, Response(_payload()), source_store=store)
    _write_anchor(root, anchor)
    adapter.fetch()
    _, receipt, sources, _ = _selected(root)
    if surface == "receipt_anchor":
        forged = deepcopy(receipt)
        forged["queue"]["anchor_verifications"][0]["backend"] = "r2"
        filename = "capital_structure_companyfacts_coverage_receipt.schema.json"
        label = "forged receipt"
    else:
        forged = deepcopy(sources[0])
        if surface == "source_storage":
            forged["storage"]["backend"] = "r2"
        else:
            forged["anchor"]["complete_submission_backend"] = "r2"
        filename = "capital_structure_companyfacts_source_manifest.schema.json"
        label = "forged source"
    with pytest.raises(companyfacts.CompanyFactsIntakeError, match="contract violation"):
        companyfacts._validate_contract(forged, filename, label=label)


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
    adapter, root = _adapter(
        tmp_path, monkeypatch, Response(_payload()), source_store=FailingStore(),
        source_stores={anchor_store.store_id: anchor_store},
    )
    _write_anchor(root, anchor)
    adapter.fetch()
    _, receipt, sources, coverage = _selected(root)
    assert receipt["status"] == "blocked"
    assert sources == []
    assert coverage[0]["state"] == "retry"


def test_missing_or_self_hashed_forged_anchor_never_calls_sec(tmp_path, monkeypatch):
    store = _store(tmp_path)
    anchor = _anchor_manifest(store)
    object_path = tmp_path / "objects" / anchor["storage"]["object_key"]
    object_path.unlink()
    adapter, root = _adapter(tmp_path, monkeypatch, Response(_payload()), source_store=store)
    called = []
    adapter._fetcher = lambda *args, **kwargs: called.append(args)
    _write_anchor(root, anchor)
    result = adapter.fetch()
    _, receipt, sources, coverage = _selected(root)
    assert called == [] and sources == []
    assert result["sec_companyfacts_intake"].iloc[0]["anchor_failed"] == 1
    assert coverage[0]["state"] == "deferred"
    assert "anchor source object is missing" in coverage[0]["error"]
    assert receipt["queue"]["anchor_verifications"][0]["status"] == "failed"

    forged_store = _store(tmp_path / "forged")
    forged = _anchor_manifest(forged_store)
    forged = deepcopy(forged)
    forged_digest = "f" * 64
    forged["document"]["content_sha256"] = forged_digest
    forged["document"]["root_locator"] = f"sha256:{forged_digest}"
    forged["storage"]["object_key"] = companyfacts.object_key_for_sha256(forged_digest)
    forged["spans"][0].update(
        span_id=f"root:{forged_digest}", text_sha256=forged_digest,
    )
    forged["manifest_id"] = filings.manifest_id_for(forged)
    forged_adapter, forged_root = _adapter(
        tmp_path / "forged", monkeypatch, Response(_payload()), source_store=forged_store,
    )
    forged_called = []
    forged_adapter._fetcher = lambda *args, **kwargs: forged_called.append(args)
    _write_anchor(forged_root, forged)
    forged_adapter.fetch()
    _, forged_receipt, forged_sources, forged_coverage = _selected(forged_root)
    assert forged_called == [] and forged_sources == []
    assert forged_coverage[0]["state"] == "deferred"
    assert forged_receipt["queue"]["anchor_verifications"][0]["content_sha256"] == forged_digest
    assert forged_receipt["queue"]["anchor_verifications"][0]["status"] == "failed"


@pytest.mark.parametrize("axis", ["cik", "accession", "form", "source_id"])
def test_reauthored_anchor_cannot_bind_different_sec_submission_bytes(
    tmp_path, monkeypatch, axis,
):
    store = _store(tmp_path)
    forged = deepcopy(_anchor_manifest(store))
    old_accession = forged["filing"]["accession"]
    if axis == "cik":
        cik = "0007654321"
        accession = f"{cik}-26-000001"
        forged["issuer"]["cik"] = cik.lstrip("0")
        forged["issuer"]["issuer_id"] = f"sec:cik:{cik}"
        forged["filing"]["accession"] = accession
        forged["source_id"] = f"{accession}:0:complete-submission.txt"
        forged["document"]["canonical_url"] = (
            f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession}.txt"
        )
    elif axis == "accession":
        accession = "0001234567-26-000002"
        forged["filing"]["accession"] = accession
        forged["source_id"] = f"{accession}:0:complete-submission.txt"
        forged["document"]["canonical_url"] = (
            f"https://www.sec.gov/Archives/edgar/data/1234567/{accession}.txt"
        )
    elif axis == "form":
        forged["filing"]["form"] = "S-1"
        forged["document"]["document_type"] = "S-1"
    else:
        forged["source_id"] = f"{old_accession}:0:forged-complete-submission.txt"
    forged["manifest_id"] = filings.manifest_id_for(forged)

    adapter, root = _adapter(tmp_path, monkeypatch, Response(_payload()), source_store=store)
    called = []
    adapter._fetcher = lambda *args, **kwargs: called.append(args)
    _write_anchor(root, forged)
    result = adapter.fetch()
    _, receipt, sources, coverage = _selected(root)
    assert called == [] and sources == []
    assert coverage[0]["state"] == "deferred"
    assert result["sec_companyfacts_intake"].iloc[0]["anchor_failed"] == 1
    assert receipt["queue"]["anchor_verifications"][0]["status"] == "failed"


@pytest.mark.parametrize("variant", ["corrupt", "backend_rebound", "store_rebound", "unknown_store"])
def test_anchor_store_resolution_is_exact_and_never_rebound(tmp_path, variant):
    store = _store(tmp_path)
    anchor = companyfacts._anchor_candidate(_anchor_manifest(store))
    assert anchor is not None

    class DeclaredStore:
        store_id = anchor["storage_store_id"]
        backend = anchor["storage_backend"]

        @staticmethod
        def get_verified(object_key, content_sha256):
            return b"corrupt"

    declared = DeclaredStore()
    stores = {anchor["storage_store_id"]: declared}
    if variant == "backend_rebound":
        declared.backend = "r2" if anchor["storage_backend"] == "local" else "local"
    elif variant == "store_rebound":
        declared.store_id = "r2_shared"
    elif variant == "unknown_store":
        stores = {}
    with pytest.raises(companyfacts.CompanyFactsAnchorVerificationError):
        companyfacts._verify_anchor_source_object(
            anchor, source_stores=stores, deadline=None, monotonic=time.monotonic,
        )


def test_anchor_verification_obeys_deadline_and_byte_budget(tmp_path, monkeypatch):
    store = _store(tmp_path)
    manifest = _anchor_manifest(store)
    anchor = companyfacts._anchor_candidate(manifest)
    assert anchor is not None

    class SlowStore:
        store_id = anchor["storage_store_id"]
        backend = anchor["storage_backend"]

        @staticmethod
        def get_verified_strict_bounded(
            object_key, content_sha256, *, expected_byte_length, max_byte_length,
        ):
            assert expected_byte_length <= max_byte_length
            time.sleep(0.15)
            return SUBMISSION

    started = time.monotonic()
    with pytest.raises(companyfacts.CompanyFactsRunBudgetExceeded, match="remaining run deadline"):
        companyfacts._verify_anchor_source_object(
            anchor, source_stores={anchor["storage_store_id"]: SlowStore()},
            deadline=started + 0.02, monotonic=time.monotonic,
        )
    assert time.monotonic() - started < 0.12

    limited, root = _adapter(
        tmp_path / "limited", monkeypatch, Response(_payload()), source_store=store,
        source_stores={store.store_id: store}, max_run_bytes=len(SUBMISSION) - 1,
    )
    called = []
    limited._fetcher = lambda *args, **kwargs: called.append(args)
    _write_anchor(root, manifest)
    with pytest.raises(companyfacts.CompanyFactsRunBudgetExceeded, match="byte budget"):
        limited.fetch()
    assert called == []
    assert not (root / "coverage_receipt.json").exists()


def test_anchor_verification_failures_produce_honest_partial_and_degraded_telemetry(tmp_path, monkeypatch):
    store = _store(tmp_path)
    first = _anchor_manifest(store, cik="0001234567", ticker="ACME")
    second = _anchor_manifest(store, cik="0007654321", ticker="BETA")
    second_path = tmp_path / "objects" / second["storage"]["object_key"]
    second_path.unlink()
    adapter, root = _adapter(
        tmp_path, monkeypatch, Response(_payload()), source_store=store, max_ciks=2,
    )
    called = []

    def fetch_by_url(url, **kwargs):
        cik = url.rsplit("CIK", 1)[-1].removesuffix(".json")
        called.append(cik)
        return Response(_payload(cik))

    adapter._fetcher = fetch_by_url
    _write_anchor(root, [first, second])
    partial = adapter.fetch()["sec_companyfacts_intake"].iloc[0]
    _, partial_receipt, partial_sources, partial_coverage = _selected(root)
    assert called == ["0001234567"]
    assert partial["status"] == partial_receipt["status"] == "partial"
    assert partial["anchor_verified"] == 1 and partial["anchor_failed"] == 1
    assert len(partial_sources) == 1
    assert {row["state"] for row in partial_coverage} == {"retrieved", "deferred"}

    one_store = _store(tmp_path / "degraded")
    one_anchor = _anchor_manifest(one_store)
    degraded, degraded_root = _adapter(
        tmp_path / "degraded", monkeypatch, Response(_payload()), source_store=one_store,
    )
    _write_anchor(degraded_root, one_anchor)
    degraded.fetch()
    (tmp_path / "degraded" / "objects" / one_anchor["storage"]["object_key"]).unlink()
    degraded._now_fn = Clock(datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc))
    degraded_called = []
    degraded._fetcher = lambda *args, **kwargs: degraded_called.append(args)
    degraded_result = degraded.fetch(full_history=True)["sec_companyfacts_intake"].iloc[0]
    _, degraded_receipt, _, degraded_coverage = _selected(degraded_root)
    assert degraded_called == []
    assert degraded_result["status"] == degraded_receipt["status"] == "degraded"
    assert degraded_receipt["population"]["stale_ciks"] == 1
    assert degraded_coverage[-1]["state"] == "deferred"


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
    if target == "_atomic_write_bytes":
        # The external witness advances before the local pointer so a failed local
        # CAS cannot expose an unwitnessed head. Recovery is deliberately fail-closed.
        with pytest.raises(companyfacts.CompanyFactsIntakeError, match="externally witnessed"):
            _load_selected(root, anchor)
        return
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

    rebound_source = deepcopy(sources[0])
    rebound_source["anchor"]["complete_submission_backend"] = "r2"
    rebound_source["anchor"]["complete_submission_store_id"] = "r2_shared"
    rebound_source["manifest_id"] = companyfacts._source_manifest_id(rebound_source)
    rebound_coverage = deepcopy(coverage[0])
    rebound_coverage["result"]["source_manifest_id"] = rebound_source["manifest_id"]
    rebound_coverage["coverage_id"] = companyfacts._coverage_id(rebound_coverage)
    with pytest.raises(companyfacts.CompanyFactsIntakeError, match="source/filing-anchor semantic binding"):
        companyfacts._validate_companyfacts_bundle(
            anchor_records=[anchor], source_records=[rebound_source], coverage_records=[rebound_coverage],
        )


def test_retry_after_global_cooldown_and_total_run_byte_budget(tmp_path, monkeypatch):
    responses = [
        Response(b"", status=429, headers={"Retry-After": "99999"}),
    ]
    adapter, _ = _adapter(tmp_path, monkeypatch, Response(_payload()))
    adapter._fetcher = lambda *args, **kwargs: responses.pop(0)
    with pytest.raises(companyfacts.CompanyFactsRunBudgetExceeded, match="cooldown"):
        adapter._fetch_companyfacts("0001234567")

    limited, _ = _adapter(
        tmp_path / "limited", monkeypatch, Response(_payload()),
        max_run_bytes=20, max_response_bytes=10_000,
    )
    limited._run_deadline = 10.0
    with pytest.raises(companyfacts.CompanyFactsRunBudgetExceeded, match="byte budget"):
        limited._fetch_companyfacts("0001234567")
    assert limited._run_bytes > limited.max_run_bytes


def test_production_requires_external_authenticated_head_before_network(tmp_path, monkeypatch):
    root = tmp_path / "data" / "capital_structure" / "companyfacts"
    monkeypatch.setattr(companyfacts, "_data_root", lambda: root)
    monkeypatch.delenv("CAPITAL_STRUCTURE_COMPANYFACTS_HEAD_HMAC_KEY", raising=False)
    monkeypatch.delenv("COMPANYFACTS_HEAD_GUARD_BUCKET", raising=False)
    monkeypatch.delenv("R2_CAPITAL_STRUCTURE_BUCKET", raising=False)
    monkeypatch.delenv("R2_BUCKET", raising=False)
    called = []
    adapter = companyfacts.SecCapitalStructureCompanyFactsAdapter(
        fetcher=lambda *args, **kwargs: called.append(args), sleeper=lambda _: None,
    )
    with pytest.raises(companyfacts.CompanyFactsIntakeError, match="production trust is unconfigured"):
        adapter.fetch()
    assert called == []


def test_production_trust_uses_shared_r2_bucket_only_when_explicitly_configured(monkeypatch):
    import engine.capital_structure.source_store as source_store

    client = object()
    monkeypatch.setenv("CAPITAL_STRUCTURE_COMPANYFACTS_HEAD_HMAC_KEY", "H" * 32)
    monkeypatch.setenv("CAPITAL_STRUCTURE_COMPANYFACTS_HEAD_KEY_ID", "")
    monkeypatch.delenv("COMPANYFACTS_HEAD_GUARD_BUCKET", raising=False)
    monkeypatch.delenv("R2_CAPITAL_STRUCTURE_BUCKET", raising=False)
    monkeypatch.setenv("R2_BUCKET", "shared-evidence")
    monkeypatch.setattr(source_store, "_capital_structure_r2_client", lambda: client)
    signer, guard = companyfacts._build_production_trust_context()
    assert signer.key_id == "companyfacts-head-v1"
    assert isinstance(guard, companyfacts.R2CompanyFactsHeadGuard)
    assert guard._bucket == "shared-evidence" and guard._client is client  # noqa: SLF001


def test_r2_head_guard_uses_r2_conditional_puts_with_service_etags(monkeypatch):
    class PreconditionFailed(RuntimeError):
        response = {
            "Error": {"Code": "PreconditionFailed"},
            "ResponseMetadata": {"HTTPStatusCode": 412},
        }

    class Body:
        def __init__(self, body):
            self.body = body

        def read(self):
            return self.body

    class R2:
        def __init__(self):
            self.body = None
            self.etag = None
            self.puts = []
            self.fail_next_put = False

        def get_object(self, **_kwargs):
            if self.body is None:
                raise KeyError("missing")
            return {"Body": Body(self.body), "ETag": self.etag}

        def put_object(self, **kwargs):
            self.puts.append(kwargs)
            if self.fail_next_put:
                self.fail_next_put = False
                raise PreconditionFailed("concurrent writer won")
            if kwargs.get("IfNoneMatch") == "*" and self.body is not None:
                raise RuntimeError("precondition failed")
            if "IfMatch" in kwargs and kwargs["IfMatch"] != self.etag:
                raise RuntimeError("precondition failed")
            self.body = kwargs["Body"]
            self.etag = f'"etag-{len(self.puts)}"'

    monkeypatch.setattr(companyfacts, "_is_not_found_error", lambda error: isinstance(error, KeyError))
    signer = companyfacts.DeterministicTestCompanyFactsSigner("R" * 32, key_id="r2-test-v1")
    client = R2()
    guard = companyfacts.R2CompanyFactsHeadGuard(client=client, bucket="test", signer=signer)
    first = {
        "schema": companyfacts.HEAD_WITNESS_SCHEMA,
        "key_id": signer.key_id,
        "sequence": 1,
        "receipt_id": "receipt:cs-companyfacts:" + "1" * 64,
        "receipt_sha256": "2" * 64,
        "receipt_byte_length": 1,
        "generation_id": "generation:cs-companyfacts:" + "3" * 64,
        "published_at": "2026-08-02T12:00:00Z",
        "previous_receipt_id": None,
    }
    first["signature"] = signer.sign(companyfacts._head_witness_payload(first))
    guard.advance(expected=None, expected_token=None, candidate=first)
    observed, token = guard.read()
    assert observed == first and token == '"etag-1"'
    assert client.puts[0]["IfNoneMatch"] == "*"

    second = {**first, "sequence": 2, "receipt_id": "receipt:cs-companyfacts:" + "4" * 64,
              "previous_receipt_id": first["receipt_id"]}
    second["signature"] = signer.sign(companyfacts._head_witness_payload(second))
    client.fail_next_put = True
    with pytest.raises(companyfacts.CompanyFactsIntakeError, match="compare-and-swap conflict"):
        guard.advance(expected=observed, expected_token=token, candidate=second)
    assert client.puts[1]["IfMatch"] == '"etag-1"'
    guard.advance(expected=observed, expected_token=token, candidate=second)
    assert client.puts[2]["IfMatch"] == '"etag-1"'
    with pytest.raises(companyfacts.CompanyFactsIntakeError, match="compare-and-swap conflict"):
        guard.advance(expected=observed, expected_token=token, candidate=second)


def test_pointer_loss_with_immutable_artifacts_fails_closed_before_network(tmp_path, monkeypatch):
    store = _store(tmp_path)
    anchor = _anchor_manifest(store)
    adapter, root = _adapter(tmp_path, monkeypatch, Response(_payload()), source_store=store)
    _write_anchor(root, anchor)
    adapter.fetch()
    (root / "coverage_receipt.json").unlink()
    called = []
    adapter._fetcher = lambda *args, **kwargs: called.append(args)
    with pytest.raises(companyfacts.CompanyFactsIntakeError, match="missing Company Facts current pointer"):
        adapter.fetch(full_history=True)
    assert called == []


def test_saved_valid_pointer_replay_and_fully_resealed_local_head_are_rejected(tmp_path, monkeypatch):
    store = _store(tmp_path)
    anchor = _anchor_manifest(store)
    adapter, root = _adapter(tmp_path, monkeypatch, Response(_payload()), source_store=store)
    _write_anchor(root, anchor)
    adapter.fetch()
    old_pointer = (root / "coverage_receipt.json").read_bytes()
    adapter.fetch(full_history=True)
    (root / "coverage_receipt.json").write_bytes(old_pointer)
    called = []
    adapter._fetcher = lambda *args, **kwargs: called.append(args)
    with pytest.raises(companyfacts.CompanyFactsIntakeError, match="externally witnessed"):
        adapter.fetch()
    assert called == []

    # Even a locally re-signed, internally consistent alternative receipt cannot
    # replace the externally witnessed head.
    signer, guard = _trust(root)
    _, current, _, _ = _selected(root)
    forged = deepcopy(current)
    forged["policy_version"] = "locally-resealed-attacker-version"
    forged["auth"]["signature"] = ""
    forged = companyfacts._sign_receipt(forged, signer=signer)
    forged_body = companyfacts._canonical_bytes(forged) + b"\n"
    forged_path = root / "receipts" / f"{forged['receipt_id'].rsplit(':', 1)[-1]}.json"
    forged_path.write_bytes(forged_body)
    pointer = {
        "schema": companyfacts.CURRENT_POINTER_SCHEMA,
        "receipt_id": forged["receipt_id"],
        "receipt_path": f"receipts/{forged_path.name}",
        "receipt_sha256": companyfacts._file_receipt(forged_path)["sha256"],
        "receipt_byte_length": len(forged_body),
        "generation_id": forged["generation"]["generation_id"],
        "published_at": forged["published_at"],
    }
    pointer["pointer_id"] = companyfacts._pointer_id(pointer)
    (root / "coverage_receipt.json").write_bytes(companyfacts._canonical_bytes(pointer) + b"\n")
    witnessed, _ = guard.read()
    with pytest.raises(companyfacts.CompanyFactsIntakeError, match="externally witnessed"):
        companyfacts._load_committed_bundle(
            root=root, receipt_path=root / "coverage_receipt.json", anchor_records=[anchor],
            signer=signer, head_witness=witnessed,
        )


def test_split_brain_external_witness_ahead_of_local_pointer_refuses_network(tmp_path, monkeypatch):
    store = _store(tmp_path)
    anchor = _anchor_manifest(store)
    adapter, root = _adapter(tmp_path, monkeypatch, Response(_payload()), source_store=store)
    _write_anchor(root, anchor)
    adapter.fetch()
    prior_pointer = (root / "coverage_receipt.json").read_bytes()
    adapter.fetch(full_history=True)
    (root / "coverage_receipt.json").write_bytes(prior_pointer)
    called = []
    adapter._fetcher = lambda *args, **kwargs: called.append(args)
    with pytest.raises(companyfacts.CompanyFactsIntakeError, match="externally witnessed"):
        adapter.fetch()
    assert called == []


def test_split_brain_local_pointer_ahead_of_external_witness_refuses_network(tmp_path, monkeypatch):
    store = _store(tmp_path)
    anchor = _anchor_manifest(store)
    adapter, root = _adapter(tmp_path, monkeypatch, Response(_payload()), source_store=store)
    _write_anchor(root, anchor)
    adapter.fetch()
    _, guard = _trust(root)
    witnessed_one, _ = guard.read()
    assert witnessed_one is not None
    adapter.fetch(full_history=True)
    # Simulate the impossible-in-normal-order crash/administrative split where a
    # local selector is newer than the remote authority. Startup must not choose
    # either side or make another SEC call.
    guard._witness = dict(witnessed_one)  # noqa: SLF001 - deterministic test fixture
    guard._version += 1  # noqa: SLF001 - deterministic test fixture
    called = []
    adapter._fetcher = lambda *args, **kwargs: called.append(args)
    with pytest.raises(companyfacts.CompanyFactsIntakeError, match="externally witnessed"):
        adapter.fetch()
    assert called == []


def test_cross_process_lease_and_external_cas_produce_one_linear_history(tmp_path, monkeypatch):
    store = _store(tmp_path)
    anchor = _anchor_manifest(store)
    seed, root = _adapter(tmp_path, monkeypatch, Response(_payload()), source_store=store)
    _write_anchor(root, anchor)
    seed.fetch()
    signer, guard = _trust(root)
    serialized_clock = Clock(datetime(2026, 8, 3, 12, tzinfo=timezone.utc))
    first = companyfacts.SecCapitalStructureCompanyFactsAdapter(
        source_store=store, signer=signer, head_guard=guard,
        now_fn=serialized_clock,
        fetcher=lambda *args, **kwargs: Response(_payload()), sleeper=lambda _: None, monotonic=lambda: 1.0,
    )
    second = companyfacts.SecCapitalStructureCompanyFactsAdapter(
        source_store=store, signer=signer, head_guard=guard,
        now_fn=serialized_clock,
        fetcher=lambda *args, **kwargs: Response(_payload()), sleeper=lambda _: None, monotonic=lambda: 1.0,
    )
    barrier = threading.Barrier(2)
    errors = []
    def run(adapter):
        try:
            barrier.wait(timeout=5)
            adapter.fetch(full_history=True)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)
    threads = [threading.Thread(target=run, args=(candidate,)) for candidate in (first, second)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    _, receipt, _, coverage = _selected(root)
    assert receipt["sequence"] == 3
    assert len(coverage) == 3
    assert sorted(json.loads(path.read_text())["sequence"] for path in (root / "receipts").glob("*.json")) == [1, 2, 3]


def test_fsync_after_replace_is_indeterminate_not_success(tmp_path, monkeypatch):
    store = _store(tmp_path)
    anchor = _anchor_manifest(store)
    adapter, root = _adapter(tmp_path, monkeypatch, Response(_payload()), source_store=store)
    _write_anchor(root, anchor)
    adapter.fetch()
    original = companyfacts._fsync_held_directory
    def fail_pointer_directory(descriptor, path):
        if path == root:
            raise OSError("injected pointer fsync failure")
        return original(descriptor, path)
    monkeypatch.setattr(companyfacts, "_fsync_held_directory", fail_pointer_directory)
    with pytest.raises(companyfacts.CompanyFactsPublishIndeterminate, match="durability is indeterminate"):
        adapter.fetch(full_history=True)


def test_startup_refuses_selected_generation_when_raw_object_is_missing(tmp_path, monkeypatch):
    store = _store(tmp_path)
    anchor = _anchor_manifest(store)
    adapter, root = _adapter(tmp_path, monkeypatch, Response(_payload()), source_store=store)
    _write_anchor(root, anchor)
    adapter.fetch()
    _, _, sources, _ = _selected(root)
    object_path = tmp_path / "objects" / sources[0]["storage"]["object_key"]
    object_path.unlink()
    called = []
    adapter._fetcher = lambda *args, **kwargs: called.append(args)
    with pytest.raises(companyfacts.CompanyFactsIntakeError, match="source object is missing"):
        adapter.fetch()
    assert called == []


@pytest.mark.parametrize("position", ["current", "historical"])
def test_selected_current_and_historical_store_mapping_cannot_rebind_store_identity(
    tmp_path, monkeypatch, position,
):
    store = _store(tmp_path)
    anchor = _anchor_manifest(store)
    adapter, root = _adapter(tmp_path, monkeypatch, Response(_payload()), source_store=store)
    _write_anchor(root, anchor)
    adapter.fetch()
    adapter.fetch(full_history=True)
    _, _, sources, _ = _selected(root)
    assert len(sources) == 2
    selected = sources[-1] if position == "current" else sources[0]
    declared_store_id = selected["storage"]["store_id"]
    calls = []

    class ReboundStore:
        store_id = "r2_shared"
        backend = selected["storage"]["backend"]

        @staticmethod
        def get_verified(object_key, content_sha256):
            calls.append((object_key, content_sha256))
            return _payload()

    with pytest.raises(companyfacts.CompanyFactsIntakeError, match="store identity is detached"):
        companyfacts._verify_selected_source_objects(
            [selected], source_stores={declared_store_id: ReboundStore()},
        )
    assert calls == []


def test_authenticated_receipt_telemetry_is_rederived_from_predecessor_delta(tmp_path, monkeypatch):
    store = _store(tmp_path)
    anchor = _anchor_manifest(store)
    adapter, root = _adapter(tmp_path, monkeypatch, Response(_payload()), source_store=store)
    _write_anchor(root, anchor)
    adapter.fetch()
    _, receipt, sources, coverage = _selected(root)
    signer, _ = _trust(root)
    forged = deepcopy(receipt)
    forged["queue"].update(
        selected_ciks=0, deferred_ciks=999, priority_order=[],
        due_by_reason={"retry_due": 0, "new_anchor": 0, "refresh_due": 0},
        selected_by_reason={"retry_due": 0, "new_anchor": 0, "refresh_due": 0},
    )
    forged["counts"].update(retrieved=0, retry=0, deferred=0, skipped_fresh=777)
    forged["auth"]["signature"] = ""
    forged = companyfacts._sign_receipt(forged, signer=signer)
    with pytest.raises(companyfacts.CompanyFactsIntakeError, match="queue telemetry|anchor verification"):
        companyfacts._validate_receipt_semantics(
            forged, anchor_records=[anchor], source_records=sources, coverage_records=coverage,
        )

    rebound = deepcopy(receipt)
    rebound["queue"]["anchor_verifications"][0]["store_id"] = "r2_shared"
    rebound["queue"]["anchor_verifications"][0]["backend"] = "r2"
    rebound["auth"]["signature"] = ""
    rebound = companyfacts._sign_receipt(rebound, signer=signer)
    with pytest.raises(companyfacts.CompanyFactsIntakeError, match="detached from selected anchor"):
        companyfacts._validate_receipt_semantics(
            rebound, anchor_records=[anchor], source_records=sources, coverage_records=coverage,
        )


def test_retry_after_is_persisted_as_the_server_deadline(tmp_path, monkeypatch):
    store = _store(tmp_path)
    anchor = _anchor_manifest(store)
    adapter, root = _adapter(tmp_path, monkeypatch, Response(b"", status=429, headers={"Retry-After": "7200"}), source_store=store)
    _write_anchor(root, anchor)
    adapter.fetch()
    _, _, _, coverage = _selected(root)
    attempted = companyfacts._parse_stamp(coverage[0]["attempted_at"], field="attempted")
    retry_after = companyfacts._parse_stamp(coverage[0]["retry_after"], field="retry_after")
    assert coverage[0]["state"] == "retry"
    assert (retry_after - attempted).total_seconds() >= 7200


def test_noop_runs_do_not_inflate_receipt_chain_and_caps_are_fail_closed(tmp_path, monkeypatch):
    store = _store(tmp_path)
    anchor = _anchor_manifest(store)
    adapter, root = _adapter(tmp_path, monkeypatch, Response(_payload()), source_store=store)
    _write_anchor(root, anchor)
    adapter.fetch()
    pointer = (root / "coverage_receipt.json").read_bytes()
    _, guard = _trust(root)
    witnessed, witness_token = guard.read()
    adapter.fetch()
    assert (root / "coverage_receipt.json").read_bytes() == pointer
    assert guard.read() == (witnessed, witness_token)
    monkeypatch.setattr(companyfacts, "MAX_RECEIPT_CHAIN_LENGTH", 1)
    blocked = adapter.fetch(full_history=True)
    heartbeat = blocked["sec_companyfacts_intake"].iloc[0]
    assert heartbeat["status"] == "checkpoint_blocked"
    assert bool(heartbeat["checkpoint_blocked"])
    assert adapter.fetch_result_status(blocked) == "blocked"
    assert (root / "coverage_receipt.json").read_bytes() == pointer
    assert guard.read() == (witnessed, witness_token)
    monkeypatch.setattr(collector_base.store, "upsert", lambda group, name, df, **kwargs: df)
    monkeypatch.setattr(collector_base, "detect_stale_series", lambda *args, **kwargs: [])
    result = collector_base.run_adapter(adapter, full_history=True)
    assert result.status == "blocked"
    breaker, _ = collector_base.update_breaker([result], probe_state={})
    assert breaker.get(adapter.name, 0) == 0


def test_root_relative_paths_refuse_parent_symlink_escapes_and_traversal(tmp_path, monkeypatch):
    root = tmp_path / "companyfacts"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "receipts").symlink_to(outside, target_is_directory=True)
    receipt_path = root / "receipts" / ("a" * 64 + ".json")
    with pytest.raises(companyfacts.CompanyFactsIntakeError, match="without following links"):
        companyfacts._write_immutable_bytes(receipt_path, b"escaped", root=root)
    assert not list(outside.iterdir())

    other_root = tmp_path / "other-companyfacts"
    other_root.mkdir()
    (other_root / "generations").symlink_to(outside, target_is_directory=True)
    descriptor = {
        "generation_id": "generation:cs-companyfacts:" + "b" * 64,
        "source_manifest": {"path": "generations/" + "b" * 64 + "/source_manifest.parquet"},
        "coverage": {"path": "generations/" + "b" * 64 + "/coverage.parquet"},
    }
    with pytest.raises(companyfacts.CompanyFactsIntakeError, match="without following links"):
        companyfacts._generation_paths(other_root, descriptor)
    with pytest.raises(companyfacts.CompanyFactsIntakeError, match="path traversal"):
        with companyfacts._open_companyfacts_parent(root, ("receipts", "..", "escaped"), create=True):
            pass

    # Exact original exploit: a missing lane root beneath an ancestor symlink
    # must not create the root or lock in the symlink target.
    inside = tmp_path / "inside"
    inside.mkdir()
    (inside / "parent").symlink_to(outside, target_is_directory=True)
    escaped_root = inside / "parent" / "companyfacts"
    with pytest.raises(companyfacts.CompanyFactsIntakeError, match="without following links"):
        with companyfacts._companyfacts_publish_lease(escaped_root):
            pass
    assert not (outside / "companyfacts").exists()

    # Swap an already-lstat'd root ancestor immediately before openat. Identity
    # and O_NOFOLLOW checks must reject the replacement before root creation.
    ancestor_race = tmp_path / "ancestor-race"
    ancestor_race.mkdir()
    (ancestor_race / "parent").mkdir()
    original_open = companyfacts.os.open
    ancestor_switched = False

    def swap_ancestor_before_open(path, flags, *args, **kwargs):
        nonlocal ancestor_switched
        if path == "parent" and kwargs.get("dir_fd") is not None and not ancestor_switched:
            ancestor_switched = True
            (ancestor_race / "parent").rmdir()
            (ancestor_race / "parent").symlink_to(outside, target_is_directory=True)
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(companyfacts.os, "open", swap_ancestor_before_open)
    with pytest.raises(companyfacts.CompanyFactsIntakeError, match="without following links"):
        with companyfacts._companyfacts_publish_lease(ancestor_race / "parent" / "companyfacts"):
            pass
    assert not (outside / "companyfacts").exists()
    monkeypatch.setattr(companyfacts.os, "open", original_open)

    # Swap a checked directory for a symlink exactly at open time.  The secure
    # descriptor walk refuses it rather than continuing into ``outside``.
    race_root = tmp_path / "race-companyfacts"
    race_root.mkdir()
    (race_root / "receipts").mkdir()
    switched = False

    def swap_before_open(path, flags, *args, **kwargs):
        nonlocal switched
        if path == "receipts" and kwargs.get("dir_fd") is not None and not switched:
            switched = True
            (race_root / "receipts").rmdir()
            (race_root / "receipts").symlink_to(outside, target_is_directory=True)
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(companyfacts.os, "open", swap_before_open)
    with pytest.raises(companyfacts.CompanyFactsIntakeError, match="without following links"):
        with companyfacts._open_companyfacts_directory(race_root, ("receipts",)):
            pass


def test_ancestor_symlink_blocks_lock_pointer_stage_generation_receipt_and_read(tmp_path):
    inside = tmp_path / "inside"
    outside = tmp_path / "outside"
    inside.mkdir()
    outside.mkdir()
    (inside / "parent").symlink_to(outside, target_is_directory=True)
    root = inside / "parent" / "companyfacts"
    digest = "c" * 64
    descriptor = {
        "generation_id": "generation:cs-companyfacts:" + digest,
        "source_manifest": {
            "path": f"generations/{digest}/source_manifest.parquet",
            "sha256": "1" * 64, "byte_length": 1,
        },
        "coverage": {
            "path": f"generations/{digest}/coverage.parquet",
            "sha256": "2" * 64, "byte_length": 1,
        },
    }
    signer = companyfacts.DeterministicTestCompanyFactsSigner("P" * 32, key_id="path-test")

    def lock():
        with companyfacts._companyfacts_publish_lease(root):
            pass

    actions = [
        lock,
        lambda: companyfacts._atomic_write_bytes(
            root / "coverage_receipt.json", b"pointer", expected_previous=None, root=root,
        ),
        lambda: companyfacts._prepare_generation(
            source_manifests=pd.DataFrame(columns=companyfacts._SOURCE_MANIFEST_COLUMNS),
            coverage=pd.DataFrame(columns=companyfacts._COVERAGE_COLUMNS), root=root,
            prior_receipt=None,
        ),
        lambda: companyfacts._install_generation(
            root, companyfacts._PreparedGeneration(
                descriptor=descriptor, stage_path=root / ".generation-stage-test",
            ),
        ),
        lambda: companyfacts._write_immutable_bytes(
            root / "receipts" / f"{digest}.json", b"receipt", root=root,
        ),
        lambda: companyfacts._load_committed_bundle(
            root=root, receipt_path=root / "coverage_receipt.json", anchor_records=[],
            signer=signer, head_witness=None,
        ),
    ]
    for action in actions:
        with pytest.raises(companyfacts.CompanyFactsIntakeError, match="without following links"):
            action()
        assert not (outside / "companyfacts").exists()


def test_held_lane_rejects_root_rename_swap_before_install_or_external_commit(
    tmp_path, monkeypatch,
):
    store = _store(tmp_path)
    anchor = _anchor_manifest(store)
    adapter, root = _adapter(tmp_path, monkeypatch, Response(_payload()), source_store=store)
    _write_anchor(root, anchor)
    signer, guard = _trust(root)
    del signer
    displaced = root.parent / "companyfacts-displaced"
    original_install = companyfacts._install_generation
    swapped = False

    def swap_then_install(root_arg, prepared, *, lane=None):
        nonlocal swapped
        assert root_arg == root and lane is not None and not swapped
        swapped = True
        root.rename(displaced)
        root.mkdir(mode=0o700)
        return original_install(root_arg, prepared, lane=lane)

    monkeypatch.setattr(companyfacts, "_install_generation", swap_then_install)
    with pytest.raises(companyfacts.CompanyFactsIntakeError, match="lane root was rebound"):
        adapter.fetch()
    assert swapped
    assert guard.read() == (None, None)
    assert list(root.iterdir()) == []
    assert not (displaced / "coverage_receipt.json").exists()
    assert list((displaced / "receipts").iterdir()) == []
    assert list((displaced / "generations").iterdir()) == []
    assert not any(path.name.startswith(".generation-stage-") for path in displaced.iterdir())


def test_held_lane_rejects_generations_directory_swap_before_install_or_external_commit(
    tmp_path, monkeypatch,
):
    store = _store(tmp_path)
    anchor = _anchor_manifest(store)
    adapter, root = _adapter(tmp_path, monkeypatch, Response(_payload()), source_store=store)
    _write_anchor(root, anchor)
    _, guard = _trust(root)
    original_install = companyfacts._install_generation
    trusted_displaced = root.parent / "trusted-generations-displaced"
    outside_origin = tmp_path / "outside-origin-generations"
    outside_origin.mkdir()
    marker = outside_origin / "marker.txt"
    marker.write_text("outside")

    def swap_then_install(root_arg, prepared, *, lane=None):
        assert lane is not None
        (root / "generations").rename(trusted_displaced)
        outside_origin.rename(root / "generations")
        return original_install(root_arg, prepared, lane=lane)

    monkeypatch.setattr(companyfacts, "_install_generation", swap_then_install)
    with pytest.raises(companyfacts.CompanyFactsIntakeError, match="generations namespace was rebound"):
        adapter.fetch()
    assert guard.read() == (None, None)
    installed_marker = root / "generations" / marker.name
    assert installed_marker.read_text() == "outside"
    assert list((root / "generations").iterdir()) == [installed_marker]
    assert list(trusted_displaced.iterdir()) == []
    assert list((root / "receipts").iterdir()) == []
    assert not (root / "coverage_receipt.json").exists()
    assert not any(path.name.startswith(".generation-stage-") for path in root.iterdir())


def test_held_stage_inode_rejects_stage_directory_swap_before_install(
    tmp_path, monkeypatch,
):
    store = _store(tmp_path)
    anchor = _anchor_manifest(store)
    adapter, root = _adapter(tmp_path, monkeypatch, Response(_payload()), source_store=store)
    _write_anchor(root, anchor)
    _, guard = _trust(root)
    original_install = companyfacts._install_generation
    outside_origin = tmp_path / "outside-origin-stage"
    outside_origin.mkdir()
    marker = outside_origin / "marker.txt"
    marker.write_text("outside")
    displaced_stage = tmp_path / "sealed-stage-displaced"
    replacement_stage = None

    def swap_then_install(root_arg, prepared, *, lane=None):
        nonlocal replacement_stage
        assert prepared.stage_path is not None and prepared.stage_fd is not None
        replacement_stage = prepared.stage_path
        prepared.stage_path.rename(displaced_stage)
        outside_origin.rename(prepared.stage_path)
        return original_install(root_arg, prepared, lane=lane)

    monkeypatch.setattr(companyfacts, "_install_generation", swap_then_install)
    with pytest.raises(companyfacts.CompanyFactsIntakeError, match="generation stage was rebound"):
        adapter.fetch()
    assert guard.read() == (None, None)
    assert replacement_stage is not None
    assert (replacement_stage / marker.name).read_text() == "outside"
    assert list((root / "receipts").iterdir()) == []
    assert list((root / "generations").iterdir()) == []
    assert not (root / "coverage_receipt.json").exists()


def test_held_lane_rejects_receipts_directory_swap_before_receipt_or_external_commit(
    tmp_path, monkeypatch,
):
    store = _store(tmp_path)
    anchor = _anchor_manifest(store)
    adapter, root = _adapter(tmp_path, monkeypatch, Response(_payload()), source_store=store)
    _write_anchor(root, anchor)
    _, guard = _trust(root)
    original_write = companyfacts._write_immutable_bytes
    trusted_displaced = root.parent / "trusted-receipts-displaced"
    outside_origin = tmp_path / "outside-origin-receipts"
    outside_origin.mkdir()
    marker = outside_origin / "marker.txt"
    marker.write_text("outside")

    def swap_then_write(path, content, *, root=None, lane=None):
        assert lane is not None and root is not None
        (root / "receipts").rename(trusted_displaced)
        outside_origin.rename(root / "receipts")
        return original_write(path, content, root=root, lane=lane)

    monkeypatch.setattr(companyfacts, "_write_immutable_bytes", swap_then_write)
    with pytest.raises(companyfacts.CompanyFactsIntakeError, match="receipts namespace was rebound"):
        adapter.fetch()
    assert guard.read() == (None, None)
    installed_marker = root / "receipts" / marker.name
    assert installed_marker.read_text() == "outside"
    assert list((root / "receipts").iterdir()) == [installed_marker]
    assert list(trusted_displaced.iterdir()) == []
    assert not (root / "coverage_receipt.json").exists()


def test_retention_audit_is_capped_rotating_and_deadline_bounded():
    records = []
    for issuer in range(10):
        cik = f"{issuer + 1:010d}"
        for revision in range(3):
            records.append({
                "manifest_id": "manifest:cs-companyfacts:" + f"{issuer * 3 + revision:064x}",
                "issuer": {"cik": cik},
                "retrieval": {"first_seen_at": f"2026-07-{revision + 1:02d}T00:00:00Z"},
            })
    first = companyfacts._retention_audit_plan(
        records, selection_as_of=datetime(2026, 8, 2, tzinfo=timezone.utc), max_objects=12,
    )
    second = companyfacts._retention_audit_plan(
        records, selection_as_of=datetime(2026, 8, 3, tzinfo=timezone.utc), max_objects=12,
    )
    assert len(first) == len(second) == 12
    assert sum(lane == "current" for _, lane in first) == 8
    assert sum(lane == "historical" for _, lane in first) == 4
    assert [row["manifest_id"] for row, _ in first] != [row["manifest_id"] for row, _ in second]
    retention = companyfacts._retention_verification(
        records, selection_as_of=datetime(2026, 8, 2, tzinfo=timezone.utc),
    )
    assert retention["eligible_objects"] == 30
    assert retention["freshness"] == "sampled"
    assert not retention["all_objects_reverified"]

    class SlowStore:
        store_id = "slow"
        backend = "local"

        @staticmethod
        def get_verified_strict_bounded(
            object_key, content_sha256, *, expected_byte_length, max_byte_length,
        ):
            assert expected_byte_length <= max_byte_length
            time.sleep(0.15)
            return b"x"

    slow_digest = companyfacts.sha256(b"x").hexdigest()
    source = {
        "storage": {
            "store_id": "slow", "backend": "local",
            "object_key": companyfacts.object_key_for_sha256(slow_digest),
        },
        "content": {"content_sha256": slow_digest, "byte_length": 1},
    }
    started = time.monotonic()
    with pytest.raises(companyfacts.CompanyFactsRunBudgetExceeded, match="remaining run deadline"):
        companyfacts._verify_selected_source_objects(
            [source], source_stores={"slow": SlowStore()}, deadline=started + 0.02,
            monotonic=time.monotonic,
        )
    assert time.monotonic() - started < 0.12


def test_retention_read_rejects_legacy_unbounded_store_without_fallback():
    payload = b"x"
    digest = companyfacts.sha256(payload).hexdigest()
    source = {
        "storage": {
            "store_id": "legacy", "backend": "local",
            "object_key": companyfacts.object_key_for_sha256(digest),
        },
        "content": {"content_sha256": digest, "byte_length": len(payload)},
    }
    calls = []

    class LegacyStore:
        store_id = "legacy"
        backend = "local"

        @staticmethod
        def get_verified(object_key, content_sha256):
            calls.append((object_key, content_sha256))
            return payload

    with pytest.raises(companyfacts.CompanyFactsIntakeError, match="lacks bounded strict-read"):
        companyfacts._verify_selected_source_objects(
            [source], source_stores={"legacy": LegacyStore()},
        )
    assert calls == []


def test_retention_declared_length_respects_aggregate_remaining_byte_budget():
    payload = b"x"
    digest = companyfacts.sha256(payload).hexdigest()
    source = {
        "storage": {
            "store_id": "bounded", "backend": "local",
            "object_key": companyfacts.object_key_for_sha256(digest),
        },
        "content": {"content_sha256": digest, "byte_length": len(payload)},
    }
    calls = []

    class BoundedStore:
        store_id = "bounded"
        backend = "local"

        @staticmethod
        def get_verified_strict_bounded(
            object_key, content_sha256, *, expected_byte_length, max_byte_length,
        ):
            calls.append((expected_byte_length, max_byte_length))
            return payload

    observed = []
    with pytest.raises(companyfacts.CompanyFactsRunBudgetExceeded, match="remaining run byte"):
        companyfacts._verify_selected_source_objects(
            [source, source], source_stores={"bounded": BoundedStore()},
            byte_observer=observed.append, remaining_byte_budget=1,
        )
    assert calls == [(1, 1)]
    assert observed == [1]


def test_generation_storage_cap_and_request_timeout_obey_remaining_budget(tmp_path, monkeypatch):
    store = _store(tmp_path)
    anchor = _anchor_manifest(store)
    adapter, root = _adapter(tmp_path, monkeypatch, Response(_payload()), source_store=store)
    _write_anchor(root, anchor)
    monkeypatch.setattr(companyfacts, "MAX_GENERATION_FILE_BYTES", 1)
    with pytest.raises(companyfacts.CompanyFactsIntakeError, match="generation file exceeds"):
        adapter.fetch()
    assert not (root / "coverage_receipt.json").exists()

    observed = []
    bounded, _ = _adapter(tmp_path / "bounded", monkeypatch, Response(_payload()))
    bounded._run_deadline = 1.1
    bounded._fetcher = lambda *args, **kwargs: (observed.append(kwargs["timeout"]) or Response(_payload()))
    assert bounded._fetch_companyfacts("0001234567") == _payload()
    assert observed and max(observed[0]) <= 0.101
