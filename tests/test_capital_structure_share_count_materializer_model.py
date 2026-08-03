"""Focused adversarial tests for the pure authenticated share-count v2 model."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import hmac
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from engine.capital_structure.share_count_materializer import (
    MAX_SOURCE_BATCH,
    ShareCountMaterializerError,
    _canonical_json,
    _coverage_auth_payload,
    _coverage_generation_id,
    _coverage_receipt_identity,
    _ordered_prefix_receipt,
    compile_authenticated_companyfacts_share_count_prefix,
    fact_revision_id_for,
    ledger_receipt_id_for,
    logical_observation_id_for,
    observation_id_for,
    snapshot_fact_observation_id_for,
    source_snapshot_id_for,
    validate_share_count_observation,
    validate_share_count_ledger,
    validate_source_snapshot,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "capital_structure" / "share_count_truth" / "companyfacts_0000320193.json"
CONTRACTS = (
    "capital_structure_companyfacts_bridge_receipt.schema.json",
    "capital_structure_share_count_observation_v2.schema.json",
    "capital_structure_companyfacts_source_snapshot_v2.schema.json",
    "capital_structure_share_count_snapshot_fact_observation_v2.schema.json",
    "capital_structure_share_count_ledger_receipt_v2.schema.json",
    "capital_structure_share_count_ledger_v2.schema.json",
)


class _Verifier:
    key_id = "share-materializer-test"

    def __init__(self, secret: bytes = b"share-materializer-test-secret") -> None:
        self.secret = secret

    def sign(self, payload: bytes) -> str:
        return hmac.new(self.secret, payload, hashlib.sha256).hexdigest()

    def verify(self, payload: bytes, signature: str, *, key_id: str) -> bool:
        return key_id == self.key_id and hmac.compare_digest(self.sign(payload), signature)


def _raw(payload: dict | None = None) -> bytes:
    if payload is None:
        return FIXTURE.read_bytes()
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _manifest(raw: bytes, *, retrieved_at: str = "2025-11-01T00:00:00Z") -> dict:
    digest = hashlib.sha256(raw).hexdigest()
    record = {
        "schema": "capital_structure.companyfacts_source_manifest/v1",
        "manifest_id": "",
        "source_system": "sec_edgar_companyfacts",
        "source_id": f"sec-companyfacts:0000320193:{digest}",
        "issuer": {"issuer_id": "sec:cik:0000320193", "cik": "0000320193", "ticker": "AAPL", "aliases": []},
        "anchor": {
            "capital_structure_manifest_id": "manifest:cs:" + "a" * 64,
            "capital_structure_source_id": "0000320193-25-000001:0:complete-submission.txt",
            "complete_submission_sha256": "b" * 64,
            "complete_submission_byte_length": 1,
            "complete_submission_backend": "local",
            "complete_submission_store_id": "capital_structure_local",
            "complete_submission_object_key": "capital_structure/sec/sha256/bb/" + "b" * 64,
            "first_seen_at": "2025-10-31T00:00:00Z",
        },
        "request": {"canonical_url": "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json", "endpoint": "companyfacts", "method": "GET"},
        "retrieval": {"retrieved_at": retrieved_at, "first_seen_at": retrieved_at, "transport_status": "retrieved"},
        "content": {"media_type": "application/json", "byte_length": len(raw), "content_sha256": digest, "root_locator": f"sha256:{digest}"},
        "storage": {"backend": "local", "store_id": "capital_structure_local", "object_key": f"capital_structure/sec/sha256/{digest[:2]}/{digest}", "content_addressed": True, "retention_state": "retained"},
        "rights": {"redistribution_class": "public_source_link", "attribution_required": True, "license_note": "United States SEC EDGAR public Company Facts response"},
        "privacy": {"classification": "public", "contains_personal_data": False},
        "parser": {"eligibility": "eligible", "corruption_state": "clean", "parser_version": "companyfacts-json-cik-validator/1.0.0"},
        "spans": [{"span_id": f"root:{digest}", "locator_type": "document", "locator": f"bytes:0-{len(raw)}", "text_sha256": digest}],
        "authority": {
            "is_context_only": True, "share_count_ledger_authority": False, "instrument_authority": False,
            "capacity_authority": False, "runway_authority": False, "risk_authority": False,
            "rank_authority": False, "sizing_authority": False, "entry_authority": False, "prophet_authority": False,
        },
    }
    material = dict(record)
    material.pop("manifest_id")
    record["manifest_id"] = "manifest:cs-companyfacts:" + hashlib.sha256(_canonical_json(material)).hexdigest()
    return record


def _coverage_receipt(manifests: list[dict], verifier: _Verifier, *, sequence: int = 1) -> tuple[dict, bytes]:
    prefix = _ordered_prefix_receipt(manifests)
    empty_prefix = _ordered_prefix_receipt([])
    source_file = {"sha256": "c" * 64, "byte_length": 1}
    coverage_file = {"sha256": "d" * 64, "byte_length": 1}
    receipt = {
        "schema": "capital_structure.companyfacts_coverage_receipt/v1", "receipt_id": "",
        "selection_as_of": "2025-11-03T00:00:00Z", "published_at": "2025-11-03T00:00:00Z", "as_of": "2025-11-03T00:00:00Z",
        "sequence": sequence, "previous_receipt": None, "policy_version": "test-v1", "status": "ok",
        "generation": {"generation_id": "", "source_manifest": {"path": "", **source_file}, "coverage": {"path": "", **coverage_file}},
        "anchor_manifest_ledger": empty_prefix, "companyfacts_manifest_ledger": prefix, "coverage_ledger": empty_prefix,
        "retention_verification": {
            "policy": "bounded-retention-verification/v1", "selection_day": "2025-11-03", "eligible_objects": 0,
            "latest_objects": 0, "historical_objects": 0, "checked_current_manifest_ids": [], "checked_historical_manifest_ids": [],
            "admission_verified_manifest_ids": [], "verified_manifest_ids": [], "all_objects_reverified": False, "freshness": "sampled",
        },
        "run_byte_accounting": {"definition": "anchor-read+retention-read+sec-response+source-write-reservation+source-readback-reservation/v1", "max_bytes": 1, "anchor_verification_bytes": 0, "retention_verification_bytes": 0, "sec_response_bytes": 0, "source_store_write_reserved_bytes": 0, "source_store_readback_reserved_bytes": 0, "total_bytes": 0},
        "queue": {"max_ciks": 1, "force_refresh": False, "cursor_sequence": 0, "eligible_ciks": 1, "selected_ciks": 1, "deferred_ciks": 0, "priority_order": ["0000320193"], "due_by_reason": {"retry_due": 0, "new_anchor": 1, "refresh_due": 0}, "selected_by_reason": {"retry_due": 0, "new_anchor": 1, "refresh_due": 0}, "anchor_verifications": []},
        "counts": {"retrieved": 1, "retry": 0, "deferred": 0, "skipped_fresh": 0},
        "population": {"fresh_ciks": 1, "stale_ciks": 0, "pending_ciks": 0, "retry_ciks": 0, "deferred_ciks": 0},
        "nonclaims": ["a", "b", "c", "d", "e", "f"],
        "authority": {
            "is_context_only": True, "share_count_ledger_authority": False, "instrument_authority": False,
            "capacity_authority": False, "runway_authority": False, "risk_authority": False,
            "rank_authority": False, "sizing_authority": False, "entry_authority": False, "prophet_authority": False,
        },
        "auth": {"scheme": "hmac-sha256/v1", "key_id": verifier.key_id, "signature": ""},
    }
    generation_id = _coverage_generation_id(receipt)
    digest = generation_id.rsplit(":", 1)[-1]
    receipt["generation"] = {
        "generation_id": generation_id,
        "source_manifest": {"path": f"generations/{digest}/source_manifest.parquet", **source_file},
        "coverage": {"path": f"generations/{digest}/coverage.parquet", **coverage_file},
    }
    receipt["receipt_id"] = _coverage_receipt_identity(receipt)
    receipt["auth"]["signature"] = verifier.sign(_coverage_auth_payload(receipt))
    return receipt, _canonical_json(receipt) + b"\n"


def _reseal_receipt(receipt: dict, verifier: _Verifier) -> bytes:
    receipt["receipt_id"] = _coverage_receipt_identity(receipt)
    receipt["auth"]["signature"] = verifier.sign(_coverage_auth_payload(receipt))
    return _canonical_json(receipt) + b"\n"


def _compile(manifests: list[dict], raw_batch: list[bytes], receipt: dict, receipt_bytes: bytes, verifier: _Verifier, *, materialized_at: str = "2025-11-03T01:00:00Z", existing: dict | None = None) -> dict:
    kwargs = {}
    if existing is not None:
        kwargs["existing_ledger"] = existing
        kwargs["expected_existing_ledger_head_receipt_id"] = existing["ledger_head_receipt_id"]
    return compile_authenticated_companyfacts_share_count_prefix(
        manifests, raw_batch, receipt, coverage_receipt_bytes=receipt_bytes, coverage_receipt_verifier=verifier,
        materialized_at=materialized_at, **kwargs,
    )


def test_v2_contracts_are_closed_and_output_binds_exact_authenticated_source_identity():
    for filename in CONTRACTS:
        Draft202012Validator.check_schema(json.loads((ROOT / "contracts" / filename).read_text()))
    verifier = _Verifier()
    raw = _raw()
    manifest = _manifest(raw)
    receipt, receipt_bytes = _coverage_receipt([manifest], verifier)
    ledger = _compile([manifest], [raw], receipt, receipt_bytes, verifier)

    assert ledger["materialized_at"] == "2025-11-03T01:00:00Z"
    assert ledger["materialized_at"] == ledger["ledger_receipts"][-1]["materialized_at"]
    assert ledger["authority"]["prophet_authority"] is False
    assert len(ledger["source_snapshots"]) == len(ledger["ledger_receipts"]) == 1
    bridge = ledger["source_snapshots"][0]["bridge_receipt"]
    assert bridge["source_manifest_id"] == manifest["manifest_id"]
    assert bridge["source"]["object_key"] == manifest["storage"]["object_key"]
    assert bridge["selection"]["coverage_receipt"] == {"sha256": hashlib.sha256(receipt_bytes).hexdigest(), "byte_length": len(receipt_bytes)}
    assert bridge["selection"]["generation"] == receipt["generation"]
    assert bridge["selection"]["companyfacts_manifest_prefix"] == receipt["companyfacts_manifest_ledger"]
    assert bridge["selection"]["coverage_prefix"] == receipt["coverage_ledger"]
    assert bridge["point_in_time"] == {"source_retrieved_at": "2025-11-01T00:00:00Z", "materialized_at": "2025-11-03T01:00:00Z", "available_at": "2025-11-03T01:00:00Z", "public_available_at": None}
    for row in ledger["observations"]:
        assert row["point_in_time"]["public_available_at"] is None
        assert "raw_object_locator" not in row["evidence"]
        assert row["authority"]["trade_authority"] is False
    validate_share_count_ledger(ledger)


def test_selected_receipt_must_authenticate_exact_bytes_generation_and_manifest_prefix():
    verifier = _Verifier()
    raw, manifest = _raw(), _manifest(_raw())
    receipt, receipt_bytes = _coverage_receipt([manifest], verifier)
    manifests, raw_batch = [manifest], [raw]

    with pytest.raises(ShareCountMaterializerError, match="exact canonical"):
        _compile(manifests, raw_batch, receipt, receipt_bytes + b" ", verifier)

    forged = deepcopy(receipt)
    forged["generation"]["coverage"]["sha256"] = "e" * 64
    forged_bytes = _reseal_receipt(forged, verifier)
    with pytest.raises(ShareCountMaterializerError, match="generation identity"):
        _compile(manifests, raw_batch, forged, forged_bytes, verifier)

    prefix_forgery = deepcopy(receipt)
    prefix_forgery["companyfacts_manifest_ledger"]["prefix_sha256"] = "f" * 64
    generation_id = _coverage_generation_id(prefix_forgery)
    generation_digest = generation_id.rsplit(":", 1)[-1]
    prefix_forgery["generation"]["generation_id"] = generation_id
    prefix_forgery["generation"]["source_manifest"]["path"] = f"generations/{generation_digest}/source_manifest.parquet"
    prefix_forgery["generation"]["coverage"]["path"] = f"generations/{generation_digest}/coverage.parquet"
    prefix_bytes = _reseal_receipt(prefix_forgery, verifier)
    with pytest.raises(ShareCountMaterializerError, match="exact ordered"):
        _compile(manifests, raw_batch, prefix_forgery, prefix_bytes, verifier)

    bad_signature = deepcopy(receipt)
    bad_signature["auth"]["signature"] = "0" * 64
    with pytest.raises(ShareCountMaterializerError, match="authentication"):
        _compile(manifests, raw_batch, bad_signature, _canonical_json(bad_signature) + b"\n", verifier)


def test_raw_bytes_manifest_storage_and_anchor_bindings_fail_closed_before_fact_parse():
    verifier = _Verifier()
    raw = _raw()
    manifest = _manifest(raw)
    receipt, receipt_bytes = _coverage_receipt([manifest], verifier)

    with pytest.raises(ShareCountMaterializerError, match="raw bytes do not bind"):
        _compile([manifest], [raw + b" "], receipt, receipt_bytes, verifier)

    bad_anchor = deepcopy(manifest)
    bad_anchor["anchor"]["complete_submission_backend"] = "r2"
    material = dict(bad_anchor); material.pop("manifest_id")
    bad_anchor["manifest_id"] = "manifest:cs-companyfacts:" + hashlib.sha256(_canonical_json(material)).hexdigest()
    bad_receipt, bad_bytes = _coverage_receipt([bad_anchor], verifier)
    with pytest.raises(ShareCountMaterializerError, match="contract violation"):
        _compile([bad_anchor], [raw], bad_receipt, bad_bytes, verifier)


def test_append_only_corrections_preserve_snapshot_history_and_exact_replay_is_a_noop():
    verifier = _Verifier()
    raw_one = _raw()
    manifest_one = _manifest(raw_one, retrieved_at="2025-11-01T00:00:00Z")
    receipt_one, bytes_one = _coverage_receipt([manifest_one], verifier, sequence=1)
    first = _compile([manifest_one], [raw_one], receipt_one, bytes_one, verifier)

    payload_two = json.loads(raw_one)
    payload_two["facts"]["us-gaap"]["CommonStockSharesOutstanding"]["units"]["shares"][0]["val"] = 160000000
    raw_two = _raw(payload_two)
    manifest_two = _manifest(raw_two, retrieved_at="2025-11-02T00:00:00Z")
    receipt_two, bytes_two = _coverage_receipt([manifest_one, manifest_two], verifier, sequence=2)
    advanced = _compile(
        [manifest_one, manifest_two], [raw_two], receipt_two, bytes_two, verifier,
        materialized_at="2025-11-03T02:00:00Z", existing=first,
    )
    gaap = [row for row in advanced["observations"] if row["fact"]["name"] == "CommonStockSharesOutstanding"]
    assert [row["version"]["correction_version"] for row in gaap] == [1, 2]
    assert gaap[1]["version"]["correction_of"] == gaap[0]["observation_id"]
    assert len(advanced["source_snapshots"]) == len(advanced["ledger_receipts"]) == 2
    assert advanced["ledger_receipts"][1]["appended"]["source_manifest_ids"] == [
        manifest_two["manifest_id"],
    ]
    assert advanced["ledger_receipts"][1]["prefixes"]["source_manifests"]["count"] == 2

    replay = _compile(
        [manifest_one, manifest_two], [], receipt_two, bytes_two, verifier,
        materialized_at="2025-11-04T00:00:00Z", existing=advanced,
    )
    assert replay == advanced
    validate_share_count_ledger(advanced)


def test_materialization_pit_is_not_replaced_by_filing_or_source_clock_and_ledger_tampering_fails():
    verifier = _Verifier()
    payload = json.loads(_raw())
    payload["facts"]["us-gaap"]["CommonStockSharesOutstanding"]["units"]["shares"][0]["filed"] = "2025-11-02"
    raw = _raw(payload)
    manifest = _manifest(raw, retrieved_at="2025-11-01T00:00:00Z")
    receipt, receipt_bytes = _coverage_receipt([manifest], verifier)
    deferred = _compile([manifest], [raw], receipt, receipt_bytes, verifier, materialized_at="2025-11-01T01:00:00Z")
    assert any(row["state"]["reason"] == "materialization_precedes_filed_date" for row in deferred["observations"])

    valid = _compile([manifest], [raw], receipt, receipt_bytes, verifier)
    tampered = deepcopy(valid)
    tampered["materialized_at"] = "2025-11-03T02:00:00Z"
    with pytest.raises(ShareCountMaterializerError, match="detached from head"):
        validate_share_count_ledger(tampered)

    snapshot_tamper = deepcopy(valid)
    snapshot_tamper["source_snapshots"][0]["bridge_receipt"]["selection"]["coverage_receipt"]["sha256"] = "f" * 64
    snapshot_tamper["source_snapshots"][0]["source_snapshot_id"] = source_snapshot_id_for(snapshot_tamper["source_snapshots"][0])
    receipt_row = snapshot_tamper["ledger_receipts"][0]
    receipt_row["appended"]["source_snapshot_ids"] = [
        snapshot_tamper["source_snapshots"][0]["source_snapshot_id"],
    ]
    receipt_row["ledger_receipt_id"] = ledger_receipt_id_for(receipt_row)
    snapshot_tamper["ledger_head_receipt_id"] = receipt_row["ledger_receipt_id"]
    with pytest.raises(ShareCountMaterializerError, match="identity digest|selection"):
        validate_share_count_ledger(snapshot_tamper)


def test_existing_ledger_requires_external_head_and_authenticated_prefix_extension():
    verifier = _Verifier()
    raw = _raw()
    manifest = _manifest(raw)
    receipt, receipt_bytes = _coverage_receipt([manifest], verifier)
    ledger = _compile([manifest], [raw], receipt, receipt_bytes, verifier)
    with pytest.raises(ShareCountMaterializerError, match="requires a caller-held"):
        compile_authenticated_companyfacts_share_count_prefix(
            [manifest], [raw], receipt, coverage_receipt_bytes=receipt_bytes,
            coverage_receipt_verifier=verifier, materialized_at="2025-11-03T01:00:00Z", existing_ledger=ledger,
        )
    wrong = deepcopy(ledger)
    wrong["ledger_head_receipt_id"] = "share-count-ledger-receipt-v2:cs:" + "0" * 24
    with pytest.raises(ShareCountMaterializerError, match="head"):
        _compile([manifest], [], receipt, receipt_bytes, verifier, existing=wrong)


def test_raw_batch_is_bounded_and_cannot_skip_the_next_authenticated_manifest():
    verifier = _Verifier()
    raw_one = _raw()
    payload_two = json.loads(raw_one)
    payload_two["facts"]["dei"]["EntityPublicFloat"]["units"]["USD"][0]["val"] = 1
    raw_two = _raw(payload_two)
    manifest_one = _manifest(raw_one, retrieved_at="2025-11-01T00:00:00Z")
    manifest_two = _manifest(raw_two, retrieved_at="2025-11-02T00:00:00Z")
    receipt, receipt_bytes = _coverage_receipt([manifest_one, manifest_two], verifier, sequence=2)
    with pytest.raises(ShareCountMaterializerError, match="bounded ordered raw-byte batch"):
        _compile([manifest_one, manifest_two], [raw_one] * 25, receipt, receipt_bytes, verifier)
    with pytest.raises(ShareCountMaterializerError, match="next authenticated manifest"):
        _compile([manifest_one, manifest_two], [raw_two], receipt, receipt_bytes, verifier)


def test_observation_semantics_rederive_raw_entry_hash_metric_security_and_value():
    verifier = _Verifier()
    raw = _raw()
    manifest = _manifest(raw)
    receipt, receipt_bytes = _coverage_receipt([manifest], verifier)
    ledger = _compile([manifest], [raw], receipt, receipt_bytes, verifier)
    original = next(
        row for row in ledger["observations"]
        if row["fact"]["name"] == "CommonStockSharesOutstanding"
    )

    raw_tamper = deepcopy(original)
    raw_tamper["evidence"]["fact_entries"][0]["raw_entry"]["val"] = 999999999999
    raw_tamper["observation_id"] = observation_id_for(raw_tamper)
    with pytest.raises(ShareCountMaterializerError, match="exact raw JSON"):
        validate_share_count_observation(raw_tamper)

    value_tamper = deepcopy(original)
    value_tamper["evidence"]["fact_entries"][0]["value"] = "999999999999"
    value_tamper["reported"]["value"] = "999999999999"
    value_tamper["normalized"]["value"] = "999999999999"
    value_tamper["observation_id"] = observation_id_for(value_tamper)
    with pytest.raises(ShareCountMaterializerError, match="exact raw JSON"):
        validate_share_count_observation(value_tamper)

    metric_tamper = deepcopy(original)
    metric_tamper["metric"]["kind"] = "public_float"
    metric_tamper["logical_observation_id"] = logical_observation_id_for(metric_tamper)
    metric_tamper["fact_revision_id"] = fact_revision_id_for(metric_tamper)
    metric_tamper["observation_id"] = observation_id_for(metric_tamper)
    with pytest.raises(ShareCountMaterializerError, match="metric is detached"):
        validate_share_count_observation(metric_tamper)

    security_tamper = deepcopy(original)
    security_tamper["security_class"] = {
        "state": "not_security_specific",
        "classification": "not_security_specific",
        "raw_label": None,
        "basis": "companyfacts_fact_has_no_security_class",
    }
    security_tamper["fact_revision_id"] = fact_revision_id_for(security_tamper)
    security_tamper["observation_id"] = observation_id_for(security_tamper)
    with pytest.raises(ShareCountMaterializerError, match="security class is detached"):
        validate_share_count_observation(security_tamper)


def test_source_snapshot_rejects_fully_rehashed_observation_detached_from_bridge():
    verifier = _Verifier()
    raw = _raw()
    manifest = _manifest(raw)
    receipt, receipt_bytes = _coverage_receipt([manifest], verifier)
    ledger = _compile([manifest], [raw], receipt, receipt_bytes, verifier)
    observations = deepcopy(ledger["observations"])
    snapshot = deepcopy(ledger["source_snapshots"][0])
    row = observations[0]
    old_id = row["observation_id"]
    row["issuer_id"] = "issuer:0000000001"
    row["logical_observation_id"] = logical_observation_id_for(row)
    row["fact_revision_id"] = fact_revision_id_for(row)
    row["observation_id"] = observation_id_for(row)
    fact = next(
        item for item in snapshot["snapshot_fact_observations"]
        if item["observation_id"] == old_id
    )
    fact["logical_observation_id"] = row["logical_observation_id"]
    fact["fact_revision_id"] = row["fact_revision_id"]
    fact["observation_id"] = row["observation_id"]
    fact["snapshot_fact_observation_id"] = snapshot_fact_observation_id_for(fact)
    # Replace the old link explicitly; other fact links remain unchanged.
    for item in snapshot["fact_links"]:
        if (
            item["snapshot_fact_observation_id"] != fact["snapshot_fact_observation_id"]
            and item["logical_observation_id"]
            == ledger["observations"][0]["logical_observation_id"]
        ):
            item["logical_observation_id"] = row["logical_observation_id"]
            item["snapshot_fact_observation_id"] = fact["snapshot_fact_observation_id"]
            break
    snapshot["source_snapshot_id"] = source_snapshot_id_for(snapshot)
    with pytest.raises(ShareCountMaterializerError, match="authenticated source bridge"):
        validate_source_snapshot(snapshot, observations)


def test_rolling_receipt_commits_exact_ordered_history_and_detects_rehashed_tampering():
    verifier = _Verifier()
    raw = _raw()
    manifest = _manifest(raw)
    receipt, receipt_bytes = _coverage_receipt([manifest], verifier)
    ledger = _compile([manifest], [raw], receipt, receipt_bytes, verifier)

    reordered = deepcopy(ledger)
    appended = reordered["ledger_receipts"][0]["appended"]["observation_ids"]
    assert len(appended) > 1
    appended[0], appended[1] = appended[1], appended[0]
    reordered["ledger_receipts"][0]["ledger_receipt_id"] = ledger_receipt_id_for(
        reordered["ledger_receipts"][0],
    )
    reordered["ledger_head_receipt_id"] = reordered["ledger_receipts"][0][
        "ledger_receipt_id"
    ]
    with pytest.raises(ShareCountMaterializerError, match="next exact history suffix"):
        validate_share_count_ledger(reordered)

    forged_prefix = deepcopy(ledger)
    forged_prefix["ledger_receipts"][0]["prefixes"]["observations"][
        "rolling_sha256"
    ] = "f" * 64
    forged_prefix["ledger_receipts"][0]["ledger_receipt_id"] = ledger_receipt_id_for(
        forged_prefix["ledger_receipts"][0],
    )
    forged_prefix["ledger_head_receipt_id"] = forged_prefix["ledger_receipts"][0][
        "ledger_receipt_id"
    ]
    with pytest.raises(ShareCountMaterializerError, match="rolling prefix commitment"):
        validate_share_count_ledger(forged_prefix)


def test_authenticated_manifest_metadata_can_progress_beyond_old_512_source_cliff():
    verifier = _Verifier()
    manifests = []
    for index in range(513):
        payload = json.loads(_raw())
        payload["facts"]["dei"]["EntityPublicFloat"]["units"]["USD"][0]["val"] = index + 1
        raw = _raw(payload)
        manifests.append(_manifest(raw, retrieved_at="2025-11-01T00:00:00Z"))
    receipt, receipt_bytes = _coverage_receipt(manifests, verifier)

    with pytest.raises(
        ShareCountMaterializerError,
        match="unconsumed authenticated source prefix requires a raw-byte batch",
    ):
        _compile(manifests, [], receipt, receipt_bytes, verifier)

    assert len(manifests) > 512
    assert MAX_SOURCE_BATCH == 24
