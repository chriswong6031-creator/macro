"""Contract tests for the dedicated institutional 13F evidence store."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

import jsonschema
import pytest

from engine.institutional_census.models import content_object_key
from engine.institutional_census.storage import (
    Institutional13FStorageError,
    build_institutional_13f_store,
    load_raw_evidence,
    publish_raw_evidence,
)
from engine.research_vault.r2_store import LocalStore


ROOT = Path(__file__).resolve().parents[1]
ACCESSION = "0001067983-26-000123"
PAYLOAD = b"<SEC-DOCUMENT>institutional census fixture</SEC-DOCUMENT>\n"


def _publish(store, *, retained_at: str = "2026-08-07T17:00:00Z"):
    return publish_raw_evidence(
        store,
        accession=ACCESSION,
        filer_cik="1067983",
        form="13F-HR",
        report_period="2026-06-30",
        accepted_at="2026-08-07T16:30:00Z",
        retained_at=retained_at,
        source_url=(
            "https://www.sec.gov/Archives/edgar/data/1067983/"
            "000106798326000123/0001067983-26-000123.txt"
        ),
        payload=PAYLOAD,
        producer_version="census-parser-v1",
    )


class _ConditionalProxy:
    def __init__(self, inner: LocalStore, *, lose_first_ack: bool = False) -> None:
        self.inner = inner
        self.lose_first_ack = lose_first_ack
        self.conditional_calls: list[str] = []

    def get_bytes(self, key):
        return self.inner.get_bytes(key)

    def get_bytes_strict(self, key):
        return self.inner.get_bytes_strict(key)

    def get_bytes_strict_bounded(self, key, maximum_bytes):
        return self.inner.get_bytes_strict_bounded(key, maximum_bytes)

    def get_bytes_strict_bounded_versioned(self, key, maximum_bytes):
        return self.inner.get_bytes_strict_bounded_versioned(key, maximum_bytes)

    def validate_strict_conditional_write_capability(self):
        return self.inner.validate_strict_conditional_write_capability()

    def put_bytes_strict_conditional(
        self, key, data, *, expected_version, content_type="application/octet-stream"
    ):
        self.conditional_calls.append(key)
        result = self.inner.put_bytes_strict_conditional(
            key,
            data,
            expected_version=expected_version,
            content_type=content_type,
        )
        if self.lose_first_ack:
            self.lose_first_ack = False
            raise TimeoutError("simulated lost acknowledgement")
        return result

    def put_bytes(self, key, data, content_type="application/octet-stream"):
        return self.inner.put_bytes(key, data, content_type)

    def list_prefix(self, prefix):
        return self.inner.list_prefix(prefix)

    def exists(self, key):
        return self.inner.exists(key)

    def upload_time(self, key):
        return self.inner.upload_time(key)


def test_factory_has_no_generic_or_research_r2_fallback(tmp_path: Path) -> None:
    generic_only = {
        "R2_ENDPOINT": "https://generic.invalid",
        "R2_ACCESS_KEY_ID": "generic-ak",
        "R2_SECRET_ACCESS_KEY": "generic-sk",
        "R2_RESEARCH_BUCKET": "research",
    }
    with pytest.raises(Institutional13FStorageError, match="INSTITUTIONAL_13F_R2_ENDPOINT"):
        build_institutional_13f_store(environment=generic_only)

    local = build_institutional_13f_store(
        local_dir=tmp_path / "explicit-local",
        environment=generic_only,
    )
    assert isinstance(local, LocalStore)


def test_publish_raw_evidence_round_trips_and_validates_json_schema(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "store")
    receipt = _publish(store)

    assert receipt.filer_cik == "0001067983"
    assert receipt.clocks.report_period == "2026-06-30"
    assert receipt.raw_object.sha256 == sha256(PAYLOAD).hexdigest()
    assert receipt.raw_object.object_key == content_object_key(
        sha256(PAYLOAD).hexdigest(), content_type="application/octet-stream"
    )
    restored, payload = load_raw_evidence(store, receipt.object_key)
    assert restored == receipt
    assert payload == PAYLOAD

    schema = json.loads(
        (ROOT / "contracts/institutional_13f_raw_receipt.v1.schema.json").read_text()
    )
    jsonschema.Draft202012Validator(schema).validate(receipt.to_dict())


def test_raw_publication_is_idempotent_and_never_overwrites(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "store")
    first = _publish(store)
    keys_after_first = sorted(store.list_prefix("smart-money/13f/evidence/v1/"))
    second = _publish(store)

    assert second == first
    assert sorted(store.list_prefix("smart-money/13f/evidence/v1/")) == keys_after_first
    assert len(keys_after_first) == 2


def test_lost_create_acknowledgement_reconciles_only_exact_bytes(tmp_path: Path) -> None:
    proxy = _ConditionalProxy(LocalStore(tmp_path / "store"), lose_first_ack=True)
    receipt = _publish(proxy)

    assert load_raw_evidence(proxy, receipt.object_key)[1] == PAYLOAD
    assert len(proxy.conditional_calls) == 2


def test_content_address_collision_is_terminal_and_receipt_is_not_written(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "store")
    digest = sha256(PAYLOAD).hexdigest()
    raw_key = content_object_key(digest, content_type="application/octet-stream")
    assert store.put_bytes(raw_key, b"different")

    with pytest.raises(Institutional13FStorageError, match="collision"):
        _publish(store)

    assert store.list_prefix("smart-money/13f/evidence/v1/filings/") == []


def test_load_rejects_tampered_raw_bytes_and_noncanonical_receipt(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "store")
    receipt = _publish(store)
    assert store.put_bytes(receipt.raw_object.object_key, b"tampered")
    with pytest.raises(Institutional13FStorageError, match="digest or byte length"):
        load_raw_evidence(store, receipt.object_key)

    # Restore the raw object, then prove that semantically equivalent pretty
    # JSON is not accepted as an authoritative receipt encoding.
    assert store.put_bytes(receipt.raw_object.object_key, PAYLOAD)
    pretty = json.dumps(receipt.to_dict(), indent=2, sort_keys=True).encode("utf-8")
    assert store.put_bytes(receipt.object_key, pretty, "application/json")
    with pytest.raises(Institutional13FStorageError, match="canonically encoded"):
        load_raw_evidence(store, receipt.object_key)


def test_system_clock_cannot_predate_public_acceptance(tmp_path: Path) -> None:
    with pytest.raises(Institutional13FStorageError, match="retained_at cannot predate"):
        _publish(LocalStore(tmp_path / "store"), retained_at="2026-08-07T16:00:00Z")
