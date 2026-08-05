"""Security boundary tests for the public authenticated Company Facts read."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import inspect
import json

import pandas as pd
import pytest

import collectors.sec_capital_structure as filings
import collectors.sec_capital_structure_companyfacts as companyfacts
import engine.capital_structure.companyfacts_authenticated_read as authenticated_read
from engine.capital_structure.companyfacts_authenticated_read import (
    load_authenticated_companyfacts_snapshot,
)
from engine.capital_structure.source_store import ContentAddressedSourceStore, LocalStore
from engine.capital_structure.source_ledger_io import (
    encode_source_ledger,
    read_source_ledger,
    source_ledger_path,
)


def _write_ledger(path, records):
    """Write a source-manifest ledger fixture, bypassing the validating writer.

    Fixtures deliberately include ledgers the identity law rejects.
    """
    path.write_bytes(encode_source_ledger(list(records)))


_SUBMISSION = b"""\
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


class _Response:
    def __init__(self, body: bytes) -> None:
        self.body = body
        self.status_code = 200
        self.headers: dict[str, str] = {}

    def iter_content(self, *, chunk_size: int):
        for index in range(0, len(self.body), chunk_size):
            yield self.body[index:index + chunk_size]

    def close(self) -> None:
        return None


class _Clock:
    def __init__(self) -> None:
        self.value = datetime(2026, 8, 2, 12, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        result = self.value
        self.value += timedelta(seconds=1)
        return result


def _anchor_manifest(store: ContentAddressedSourceStore) -> dict:
    receipt = store.put_verified(_SUBMISSION, media_type="text/plain")
    assert receipt is not None
    discovery = {
        "accession": "0001234567-26-000001", "cik": "0001234567", "ticker": "ACME",
        "company_name": "ACME CORP", "form": "S-3", "filing_date": "2026-08-01",
        "collection_scope": "registration_issuance",
    }
    record = filings.SecCapitalStructureAdapter._manifest_record(
        discovery=discovery, bundle=filings.parse_submission(_SUBMISSION),
        source_id="0001234567-26-000001:0:complete-submission.txt",
        canonical_url="https://www.sec.gov/Archives/edgar/data/1234567/0001234567-26-000001.txt",
        document_name="complete-submission.txt", document_type="S-3",
        document_role="complete_submission", sequence="0", raw=_SUBMISSION, receipt=receipt,
        inspection=filings.inspect_source_document(
            _SUBMISSION, filename="complete-submission.txt", document_role="complete_submission",
        ),
        retrieved_at="2026-08-02T10:00:00Z", first_seen_at="2026-08-02T10:00:00Z",
        document_version=1, parent_manifest_id=None,
    )
    filings._validate_source_manifest(record)
    return record


def _selected(tmp_path, monkeypatch):
    root = tmp_path / "data" / "capital_structure" / "companyfacts"
    monkeypatch.setattr(companyfacts, "_data_root", lambda: root)
    store = ContentAddressedSourceStore(LocalStore(tmp_path / "objects"))
    anchor = _anchor_manifest(store)
    (root.parent).mkdir(parents=True, exist_ok=True)
    _write_ledger(source_ledger_path(root.parent), [anchor])
    signer = companyfacts.DeterministicTestCompanyFactsSigner(
        "R" * 32, key_id="companyfacts-authenticated-read-test-v1",
    )
    guard = companyfacts.InMemoryCompanyFactsHeadGuard(signer)
    adapter = companyfacts.SecCapitalStructureCompanyFactsAdapter(
        source_store=store, signer=signer, head_guard=guard, now_fn=_Clock(),
        fetcher=lambda *args, **kwargs: _Response(
            b'{"cik":"0001234567","entityName":"Acme Corp","facts":{"us-gaap":{}}}'
        ),
    )
    adapter.fetch()
    return root, anchor, signer, guard, adapter


def _load(root, anchor, signer, guard, **kwargs):
    return authenticated_read._load_authenticated_companyfacts_snapshot(
        root=root, anchor_records=[anchor], signer=signer, head_guard=guard,
        **kwargs,
    )


def test_authenticated_read_returns_selected_immutable_metadata_without_network(
    tmp_path, monkeypatch,
):
    root, anchor, signer, guard, _adapter = _selected(tmp_path, monkeypatch)

    def forbidden(*args, **kwargs):
        raise AssertionError("authenticated metadata read must not fetch SEC or source objects")

    monkeypatch.setattr(companyfacts.requests, "get", forbidden)
    monkeypatch.setattr(companyfacts, "_verify_selected_source_objects", forbidden)
    monkeypatch.setattr(
        companyfacts, "_build_production_trust_context", lambda: (signer, guard),
    )
    snapshot = load_authenticated_companyfacts_snapshot()

    head, _ = guard.read()
    assert head is not None
    assert len(snapshot.manifests) == len(snapshot.coverage_rows) == 1
    assert snapshot.selected_coverage_receipt.receipt_id == head["receipt_id"]
    assert snapshot.selected_coverage_receipt.receipt_path.endswith(".json")
    assert snapshot.selected_coverage_receipt.generation_id == head["generation_id"]
    assert snapshot.selected_coverage_receipt.sequence == head["sequence"]
    assert snapshot.selected_coverage_receipt.source_manifest_descriptor["path"].endswith(
        "/source_manifest.parquet"
    )
    assert snapshot.selected_coverage_receipt.coverage_descriptor["path"].endswith(
        "/coverage.parquet"
    )
    assert snapshot.selected_coverage_receipt.manifest_prefix["record_count"] == 1
    assert snapshot.selected_coverage_receipt.coverage_prefix["record_count"] == 1
    assert snapshot.selected_coverage_receipt_record["receipt_id"] == head["receipt_id"]
    assert snapshot.selected_coverage_receipt_bytes == (
        root / snapshot.selected_coverage_receipt.receipt_path
    ).read_bytes()
    assert snapshot.observed_head["signature"] == head["signature"]


def test_public_loader_exposes_no_trust_or_filesystem_injection():
    assert set(inspect.signature(load_authenticated_companyfacts_snapshot).parameters) == {
        "max_read_seconds",
    }
    assert authenticated_read.__all__ == [
        "CompanyFactsAuthenticatedSnapshot",
        "CompanyFactsSelectedCoverageReceipt",
        "load_authenticated_companyfacts_snapshot",
    ]


def test_authenticated_read_rejects_pointer_race(tmp_path, monkeypatch):
    root, anchor, signer, guard, _adapter = _selected(tmp_path, monkeypatch)
    original = companyfacts.read_companyfacts_authenticated_current_pointer_snapshot
    calls = 0

    def pointer_race(*args, **kwargs):
        nonlocal calls
        snapshot = original(*args, **kwargs)
        calls += 1
        if calls == 2:
            assert snapshot is not None
            # Identical bytes with a changed metadata fingerprint are still a
            # selector race and must not be silently accepted.
            (root / "coverage_receipt.json").write_bytes(snapshot[0])
            return original(*args, **kwargs)
        return snapshot

    monkeypatch.setattr(
        companyfacts, "read_companyfacts_authenticated_current_pointer_snapshot", pointer_race,
    )
    with pytest.raises(companyfacts.CompanyFactsIntakeError, match="pointer changed"):
        _load(root, anchor, signer, guard)


def test_authenticated_read_rejects_external_head_race(tmp_path, monkeypatch):
    root, anchor, signer, guard, _adapter = _selected(tmp_path, monkeypatch)

    class HeadRace:
        def __init__(self) -> None:
            self.calls = 0

        def read(self):
            head, token = guard.read()
            self.calls += 1
            return head, token if self.calls == 1 else f"race-{token}"

    with pytest.raises(companyfacts.CompanyFactsIntakeError, match="head changed"):
        _load(root, anchor, signer, HeadRace())


def test_authenticated_read_rejects_signed_chain_tampering(tmp_path, monkeypatch):
    root, anchor, signer, guard, adapter = _selected(tmp_path, monkeypatch)
    adapter.fetch(full_history=True)
    pointer = json.loads((root / "coverage_receipt.json").read_text())
    current = json.loads((root / pointer["receipt_path"]).read_text())
    previous = current["previous_receipt"]
    assert previous is not None
    path = root / previous["path"]
    body = path.read_bytes()
    path.write_bytes(body[:-1] + b" ")

    with pytest.raises(companyfacts.CompanyFactsIntakeError, match="receipt exact-byte"):
        _load(root, anchor, signer, guard)


@pytest.mark.parametrize("artifact", ["source_manifest", "coverage"])
def test_authenticated_read_rejects_generation_and_prefix_tampering(
    tmp_path, monkeypatch, artifact,
):
    root, anchor, signer, guard, _adapter = _selected(tmp_path, monkeypatch)
    pointer = json.loads((root / "coverage_receipt.json").read_text())
    receipt = json.loads((root / pointer["receipt_path"]).read_text())
    path = root / receipt["generation"][artifact]["path"]
    body = path.read_bytes()
    path.write_bytes(body[:-1] + bytes([body[-1] ^ 1]))

    with pytest.raises(companyfacts.CompanyFactsIntakeError, match="exact-byte"):
        _load(root, anchor, signer, guard)


def test_authenticated_read_fails_closed_without_trust(tmp_path, monkeypatch):
    monkeypatch.delenv("CAPITAL_STRUCTURE_COMPANYFACTS_HEAD_HMAC_KEY", raising=False)
    monkeypatch.delenv("CAPITAL_STRUCTURE_COMPANYFACTS_HEAD_KEY_ID", raising=False)
    monkeypatch.delenv("COMPANYFACTS_HEAD_GUARD_BUCKET", raising=False)
    monkeypatch.delenv("R2_CAPITAL_STRUCTURE_BUCKET", raising=False)
    monkeypatch.delenv("R2_BUCKET", raising=False)

    with pytest.raises(companyfacts.CompanyFactsIntakeError, match="production trust is unconfigured"):
        load_authenticated_companyfacts_snapshot()


def test_authenticated_read_held_lease_expires_inside_read_budget(tmp_path, monkeypatch):
    root, anchor, signer, guard, _adapter = _selected(tmp_path, monkeypatch)

    class Monotonic:
        value = 0.0

        def __call__(self):
            return self.value

    clock = Monotonic()

    def sleeper(delay):
        clock.value += delay

    with companyfacts._companyfacts_publish_lease(root):
        with pytest.raises(
            companyfacts.CompanyFactsRunBudgetExceeded,
            match="authenticated read lease acquisition exceeded",
        ):
            _load(
                root, anchor, signer, guard, max_read_seconds=1,
                monotonic=clock, sleeper=sleeper,
            )


def test_authenticated_read_slow_trust_construction_expires(tmp_path, monkeypatch):
    root, anchor, signer, guard, _adapter = _selected(tmp_path, monkeypatch)

    class Monotonic:
        value = 0.0

        def __call__(self):
            return self.value

    clock = Monotonic()

    def slow_trust(**kwargs):
        clock.value = 2.0
        return signer, guard

    monkeypatch.setattr(authenticated_read, "_resolve_trust", slow_trust)
    with pytest.raises(
        companyfacts.CompanyFactsRunBudgetExceeded,
        match="trust construction exceeded",
    ):
        authenticated_read._load_authenticated_companyfacts_snapshot(
            root=root, anchor_records=[anchor], max_read_seconds=1, monotonic=clock,
        )


def test_authenticated_read_slow_parquet_decode_expires(tmp_path, monkeypatch):
    root, anchor, signer, guard, _adapter = _selected(tmp_path, monkeypatch)

    class Monotonic:
        value = 0.0

        def __call__(self):
            return self.value

    clock = Monotonic()
    original = companyfacts._read_ledger_bytes

    def slow_decode(body, columns, *, label):
        frame = original(body, columns, label=label)
        if label == "committed source manifest":
            clock.value = 2.0
        return frame

    monkeypatch.setattr(companyfacts, "_read_ledger_bytes", slow_decode)
    with pytest.raises(
        companyfacts.CompanyFactsRunBudgetExceeded,
        match="source manifest parquet decode exceeded",
    ):
        _load(
            root, anchor, signer, guard, max_read_seconds=1,
            monotonic=clock, sleeper=lambda delay: None,
        )


def test_authenticated_read_snapshot_is_deeply_immutable(tmp_path, monkeypatch):
    root, anchor, signer, guard, _adapter = _selected(tmp_path, monkeypatch)
    snapshot = _load(root, anchor, signer, guard)

    with pytest.raises(TypeError):
        snapshot.manifests[0]["issuer"]["cik"] = "0000000001"
    with pytest.raises(TypeError):
        snapshot.selected_coverage_receipt.coverage_prefix["record_count"] = 99
    with pytest.raises(TypeError):
        snapshot.selected_coverage_receipt.source_manifest_descriptor["path"] = "forged"
    with pytest.raises(TypeError):
        snapshot.selected_coverage_receipt_record["sequence"] = 99
    with pytest.raises(AttributeError):
        snapshot.coverage_rows.append({})

    reloaded = _load(root, anchor, signer, guard)
    assert reloaded.manifests[0]["issuer"]["cik"] == "0001234567"
    assert reloaded.selected_coverage_receipt.coverage_prefix["record_count"] == 1
