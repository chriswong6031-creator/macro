"""Adversarial contract tests for the SEC observed share-count truth plane."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import inspect
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from engine.capital_structure.share_count_truth import (
    ShareCountTruthError,
    compile_share_count_observations,
    ledger_receipt_id_for,
    observation_id_for,
    source_acquisition_unavailable_result,
    snapshot_fact_observation_id_for,
    source_snapshot_id_for,
    validate_share_count_ledger,
    validate_source_snapshot,
    validate_snapshot_fact_observation,
    validate_share_count_history,
)
from scripts.compile_capital_structure_share_counts import main


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "capital_structure" / "share_count_truth" / "companyfacts_0000320193.json"
SCHEMA_PATH = ROOT / "contracts" / "capital_structure_share_count_observation.schema.json"
RECEIPT_SCHEMA_PATH = ROOT / "contracts" / "capital_structure_companyfacts_source_receipt.schema.json"
SNAPSHOT_SCHEMA_PATH = ROOT / "contracts" / "capital_structure_companyfacts_source_snapshot.schema.json"
SNAPSHOT_FACT_SCHEMA_PATH = ROOT / "contracts" / "capital_structure_share_count_snapshot_fact_observation.schema.json"
LEDGER_RECEIPT_SCHEMA_PATH = ROOT / "contracts" / "capital_structure_share_count_ledger_receipt.schema.json"


def _source_bytes() -> bytes:
    return FIXTURE.read_bytes()


def _payload(source_bytes: bytes | None = None) -> dict:
    return json.loads((source_bytes or _source_bytes()).decode("utf-8"))


def _receipt(source_bytes: bytes | None = None, **overrides) -> dict:
    raw = source_bytes or _source_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    receipt = {
        "schema": "capital_structure.companyfacts_source_receipt.v1",
        "version": 1,
        "source_system": "sec_companyfacts",
        "acquisition_state": "provided_snapshot",
        "issuer_id": "issuer:0000320193",
        "source_url": "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json",
        "source_payload_sha256": digest,
        "raw_object_locator": f"capital_structure/sec/companyfacts/sha256/{digest[:2]}/{digest}",
        "manifest_locator": f"companyfacts-manifest:cs:{digest}",
        "source_retrieved_at": "2025-11-01T00:00:00Z",
        "system_available_at": "2025-11-01T00:03:00Z",
    }
    receipt.update(overrides)
    return receipt


def _compile(source_bytes: bytes | None = None, *, existing=None, **receipt_overrides):
    raw = source_bytes or _source_bytes()
    return compile_share_count_observations(
        raw, _receipt(raw, **receipt_overrides), existing_ledger=existing,
    )


def _schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _receipt_schema() -> dict:
    return json.loads(RECEIPT_SCHEMA_PATH.read_text(encoding="utf-8"))


def _snapshot_schema() -> dict:
    return json.loads(SNAPSHOT_SCHEMA_PATH.read_text(encoding="utf-8"))


def _snapshot_fact_schema() -> dict:
    return json.loads(SNAPSHOT_FACT_SCHEMA_PATH.read_text(encoding="utf-8"))


def _ledger_receipt_schema() -> dict:
    return json.loads(LEDGER_RECEIPT_SCHEMA_PATH.read_text(encoding="utf-8"))


def _validate(record: dict) -> list[str]:
    validator = Draft202012Validator(_schema(), format_checker=FormatChecker())
    return [error.message for error in validator.iter_errors(record)]


def _with_payload(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _rebind_snapshot_and_ledger_receipts(ledger: dict, snapshot_index: int = -1) -> None:
    """Recompute every local digest after an adversarial snapshot mutation."""
    snapshot = ledger["source_snapshots"][snapshot_index]
    old_snapshot_id = snapshot["source_snapshot_id"]
    snapshot["fact_links"] = [
        {
            "logical_observation_id": fact["logical_observation_id"],
            "snapshot_fact_observation_id": fact["snapshot_fact_observation_id"],
        }
        for fact in snapshot["snapshot_fact_observations"]
    ]
    snapshot["source_snapshot_id"] = source_snapshot_id_for(snapshot)
    new_snapshot_id = snapshot["source_snapshot_id"]
    if ledger["source_acquisition"]["source_snapshot_id"] == old_snapshot_id:
        ledger["source_acquisition"]["source_snapshot_id"] = new_snapshot_id

    predecessor = None
    for receipt in ledger["ledger_receipts"]:
        receipt["source_snapshot_ids"] = [
            new_snapshot_id if value == old_snapshot_id else value
            for value in receipt["source_snapshot_ids"]
        ]
        receipt["predecessor_ledger_receipt_id"] = predecessor
        receipt["ledger_receipt_id"] = ledger_receipt_id_for(receipt)
        predecessor = receipt["ledger_receipt_id"]
    ledger["ledger_head_receipt_id"] = predecessor


def test_contract_is_strict_and_three_named_sec_facts_are_preserved_separately():
    Draft202012Validator.check_schema(_schema())
    result = _compile()
    rows = result["observations"]
    assert len(rows) == 3
    assert {row["metric"]["kind"] for row in rows} == {
        "common_shares_outstanding", "public_float",
    }
    assert {row["fact"]["name"] for row in rows} == {
        "CommonStockSharesOutstanding", "EntityCommonStockSharesOutstanding", "EntityPublicFloat",
    }
    for row in rows:
        assert not _validate(row)
        assert row["fact_revision_id"].startswith("share-count-revision:cs:")
        assert row["state"] == {"disposition": "observed", "reason": "direct_sec_companyfacts_fact"}
        assert row["point_in_time"]["available_at"] == "2025-11-01T00:03:00Z"
        assert row["source_acquisition"]["collector_state"] == "not_implemented_in_share_count_truth_wave"
        assert row["authority"] == {
            "is_context_only": True, "rank_authority": False, "sizing_authority": False,
            "entry_authority": False, "trade_authority": False, "prophet_authority": False,
        }
        assert row["evidence"]["source_receipt_schema"] == "capital_structure.companyfacts_source_receipt.v1"
        assert row["evidence"]["raw_object_locator"].endswith(row["evidence"]["source_payload_sha256"])

    gaap = next(row for row in rows if row["fact"]["name"] == "CommonStockSharesOutstanding")
    assert gaap["reported"] == {"value": "150000000", "unit": "shares", "scale": "1"}
    assert gaap["normalized"] == {"value": "150000000", "unit": "shares", "scale": "1", "state": "observed"}
    assert gaap["security_class"]["classification"] == "common_stock"
    assert gaap["evidence"]["fact_entries"][0]["json_pointer"] == "/facts/us-gaap/CommonStockSharesOutstanding/units/shares/0"

    public_float = next(row for row in rows if row["metric"]["kind"] == "public_float")
    assert public_float["reported"]["value"] == "2580000000000"
    assert public_float["reported"]["unit"] == "USD"
    assert public_float["security_class"] == {
        "state": "not_security_specific", "classification": "not_security_specific",
        "raw_label": None, "basis": "companyfacts_fact_has_no_security_class",
    }


def test_unexpected_unit_is_retained_as_deferred_not_silently_reinterpreted():
    payload = _payload()
    payload["facts"]["us-gaap"]["CommonStockSharesOutstanding"]["units"] = {
        "USD": payload["facts"]["us-gaap"]["CommonStockSharesOutstanding"]["units"]["shares"]
    }
    rows = _compile(_with_payload(payload))["observations"]
    row = next(row for row in rows if row["fact"]["name"] == "CommonStockSharesOutstanding")
    assert row["state"] == {"disposition": "deferred", "reason": "unexpected_unit"}
    assert row["reported"] == {"value": "150000000", "unit": "USD", "scale": "1"}
    assert row["normalized"] == {"value": None, "unit": None, "scale": None, "state": "deferred"}
    assert not _validate(row)


def test_same_fact_slot_with_multiple_values_is_ambiguous_not_latest_wins():
    payload = _payload()
    entries = payload["facts"]["us-gaap"]["CommonStockSharesOutstanding"]["units"]["shares"]
    duplicate = deepcopy(entries[0])
    duplicate["val"] = 160000000
    entries.append(duplicate)
    rows = _compile(_with_payload(payload))["observations"]
    row = next(row for row in rows if row["fact"]["name"] == "CommonStockSharesOutstanding")
    assert row["state"] == {"disposition": "ambiguous", "reason": "multiple_distinct_values_for_fact_slot"}
    assert row["reported"]["value"] is None
    assert row["normalized"] == {"value": None, "unit": None, "scale": None, "state": "ambiguous"}
    assert len(row["evidence"]["fact_entries"]) == 2
    assert not _validate(row)


def test_same_value_with_distinct_xbrl_context_is_ambiguous_not_arbitrarily_selected():
    payload = _payload()
    entries = payload["facts"]["us-gaap"]["CommonStockSharesOutstanding"]["units"]["shares"]
    duplicate = deepcopy(entries[0])
    duplicate["frame"] = "CY2025Q4I"
    entries.append(duplicate)
    rows = _compile(_with_payload(payload))["observations"]
    row = next(row for row in rows if row["fact"]["name"] == "CommonStockSharesOutstanding")
    assert row["state"] == {"disposition": "ambiguous", "reason": "multiple_distinct_contexts_for_fact_slot"}
    assert {entry["frame"] for entry in row["evidence"]["fact_entries"]} == {"CY2025Q3I", "CY2025Q4I"}
    assert not _validate(row)


def test_invalid_source_hash_and_temporal_receipt_fail_closed():
    raw = _source_bytes()
    wrong_hash = "a" * 64
    with pytest.raises(ShareCountTruthError, match="payload hash"):
        compile_share_count_observations(raw, _receipt(
            raw,
            source_payload_sha256=wrong_hash,
            raw_object_locator=f"capital_structure/sec/companyfacts/sha256/{wrong_hash[:2]}/{wrong_hash}",
            manifest_locator=f"companyfacts-manifest:cs:{wrong_hash}",
        ))
    with pytest.raises(ShareCountTruthError, match="cannot precede"):
        compile_share_count_observations(
            raw,
            _receipt(raw, source_retrieved_at="2025-11-01T00:04:00Z", system_available_at="2025-11-01T00:03:00Z"),
        )


def test_closed_receipt_requires_version_and_durable_raw_object_manifest_locators():
    Draft202012Validator.check_schema(_receipt_schema())
    Draft202012Validator.check_schema(_snapshot_schema())
    Draft202012Validator.check_schema(_snapshot_fact_schema())
    Draft202012Validator.check_schema(_ledger_receipt_schema())
    raw = _source_bytes()
    receipt = _receipt(raw)
    receipt["unexpected"] = True
    with pytest.raises(ShareCountTruthError, match="(?i)additional properties"):
        compile_share_count_observations(raw, receipt)

    missing_manifest = _receipt(raw)
    missing_manifest.pop("manifest_locator")
    with pytest.raises(ShareCountTruthError, match="manifest_locator"):
        compile_share_count_observations(raw, missing_manifest)

    non_content_addressed = _receipt(raw, raw_object_locator="capital_structure/sec/companyfacts/latest")
    with pytest.raises(ShareCountTruthError, match="raw_object_locator"):
        compile_share_count_observations(raw, non_content_addressed)

    detached_manifest = _receipt(raw, manifest_locator="companyfacts-manifest:cs:" + ("a" * 64))
    with pytest.raises(ShareCountTruthError, match="manifest_locator"):
        compile_share_count_observations(raw, detached_manifest)


def test_internal_ledger_receipt_contract_does_not_claim_external_nonrepudiation():
    description = _ledger_receipt_schema()["description"].lower()
    assert "not an external timestamp" in description
    assert "non-repudiation witness" in description
    assert "signature" not in _ledger_receipt_schema()["properties"]


def test_source_available_before_a_fact_was_filed_is_deferred_not_backdated():
    raw = _source_bytes()
    result = compile_share_count_observations(
        raw,
        _receipt(raw, source_retrieved_at="2025-10-30T00:00:00Z", system_available_at="2025-10-30T00:01:00Z"),
    )
    assert {row["state"]["reason"] for row in result["observations"]} == {
        "system_availability_precedes_filed_date"
    }
    assert all(row["normalized"]["state"] == "deferred" for row in result["observations"])


def test_observation_schema_fences_authority_and_correction_lineage():
    original = _compile()["observations"]
    row = deepcopy(original[0])
    row["authority"]["prophet_authority"] = True
    assert any("False was expected" in message for message in _validate(row))

    row = deepcopy(original[0])
    row["version"]["correction_version"] = 2
    assert any("is not of type 'string'" in message for message in _validate(row))


def test_changed_snapshot_creates_a_nonbranching_immutable_correction_lineage():
    original_ledger = _compile()
    original = original_ledger["observations"]
    payload = _payload()
    payload["facts"]["us-gaap"]["CommonStockSharesOutstanding"]["units"]["shares"][0]["val"] = 155000000
    changed_ledger = _compile(
        _with_payload(payload),
        existing=original_ledger,
        source_retrieved_at="2025-11-02T00:00:00Z",
        system_available_at="2025-11-02T00:03:00Z",
    )
    changed = changed_ledger["observations"]
    gaap = [row for row in changed if row["fact"]["name"] == "CommonStockSharesOutstanding"]
    assert len(gaap) == 2
    gaap.sort(key=lambda row: row["version"]["correction_version"])
    assert gaap[0]["version"] == {"immutable_record": True, "correction_version": 1, "correction_of": None}
    assert gaap[1]["version"] == {
        "immutable_record": True, "correction_version": 2, "correction_of": gaap[0]["observation_id"],
    }
    assert gaap[1]["relationships"]["supersedes"] == [gaap[0]["observation_id"]]
    validate_share_count_history(changed)

    broken = deepcopy(changed)
    wrong_predecessor = next(
        row["observation_id"] for row in broken
        if row["fact"]["name"] == "EntityPublicFloat" and row["version"]["correction_version"] == 1
    )
    for row in broken:
        if row["fact"]["name"] == "CommonStockSharesOutstanding" and row["version"]["correction_version"] == 2:
            row["relationships"]["supersedes"] = [wrong_predecessor]
            row["version"]["correction_of"] = wrong_predecessor
            row["observation_id"] = observation_id_for(row)
    with pytest.raises(ShareCountTruthError, match="must supersede exactly"):
        validate_share_count_history(broken)

    idempotent = _compile(
        _with_payload(payload),
        existing=changed_ledger,
        source_retrieved_at="2025-11-02T00:00:00Z",
        system_available_at="2025-11-02T00:03:00Z",
    )
    assert idempotent["observations"] == changed


def test_legacy_existing_observations_input_is_not_an_ingest_path():
    assert "existing_observations" not in inspect.signature(
        compile_share_count_observations,
    ).parameters
    with pytest.raises(TypeError, match="existing_observations"):
        compile_share_count_observations(
            _source_bytes(), _receipt(), existing_observations=[],
        )


def test_distinct_same_slot_revision_requires_both_source_clocks_after_predecessor():
    original = _compile(
        source_retrieved_at="2025-10-31T00:00:00Z",
        system_available_at="2025-11-01T00:03:00Z",
    )
    payload = _payload()
    payload["facts"]["us-gaap"]["CommonStockSharesOutstanding"]["units"]["shares"][0]["val"] = 155000000
    changed_raw = _with_payload(payload)

    with pytest.raises(ShareCountTruthError, match="correction source_retrieved_at must be strictly later"):
        _compile(
            changed_raw,
            existing=original,
            source_retrieved_at="2025-10-31T00:00:00Z",
            system_available_at="2025-11-01T00:03:00Z",
        )
    with pytest.raises(ShareCountTruthError, match="correction system_available_at must be strictly later"):
        _compile(
            changed_raw,
            existing=original,
            source_retrieved_at="2025-11-01T00:00:00Z",
            system_available_at="2025-11-01T00:03:00Z",
        )

    valid = _compile(
        changed_raw,
        existing=original,
        source_retrieved_at="2025-11-02T00:00:00Z",
        system_available_at="2025-11-02T00:03:00Z",
    )
    history = deepcopy(valid["observations"])
    correction = next(row for row in history if row["version"]["correction_version"] == 2)
    correction["point_in_time"]["source_retrieved_at"] = "2025-11-01T00:00:00Z"
    correction["point_in_time"]["system_available_at"] = "2025-11-01T00:03:00Z"
    correction["point_in_time"]["available_at"] = "2025-11-01T00:03:00Z"
    correction["observation_id"] = observation_id_for(correction)
    with pytest.raises(ShareCountTruthError, match="correction system_available_at must be strictly later"):
        validate_share_count_history(history)


def test_snapshot_local_semantics_are_exactly_rederived_from_canonical_evidence():
    ledger = _compile()
    tampered = deepcopy(ledger)
    fact = tampered["source_snapshots"][0]["snapshot_fact_observations"][0]
    fact["state"] = {"disposition": "deferred", "reason": "missing_value"}
    fact["normalized"] = {
        "value": None, "unit": None, "scale": None, "state": "deferred",
    }
    fact["snapshot_fact_observation_id"] = snapshot_fact_observation_id_for(fact)
    _rebind_snapshot_and_ledger_receipts(tampered)
    with pytest.raises(ShareCountTruthError, match="does not match re-derived receipt-local semantics"):
        validate_share_count_ledger(tampered)

    canonical_tampered = deepcopy(ledger)
    canonical = canonical_tampered["observations"][0]
    canonical["evidence"]["fact_entries"][0]["source_issue"] = "unexpected_unit"
    canonical["observation_id"] = observation_id_for(canonical)
    snapshot_fact = canonical_tampered["source_snapshots"][0]["snapshot_fact_observations"][0]
    snapshot_fact["observation_id"] = canonical["observation_id"]
    snapshot_fact["snapshot_fact_observation_id"] = snapshot_fact_observation_id_for(snapshot_fact)
    _rebind_snapshot_and_ledger_receipts(canonical_tampered)
    with pytest.raises(ShareCountTruthError, match="source_issue is not re-derived"):
        validate_share_count_ledger(canonical_tampered)


def test_every_canonical_observation_requires_a_snapshot_anchor():
    original = _compile()
    payload = _payload()
    payload["facts"]["us-gaap"]["CommonStockSharesOutstanding"]["units"]["shares"][0]["val"] = 155000000
    ledger = _compile(
        _with_payload(payload),
        existing=original,
        source_retrieved_at="2025-11-02T00:00:00Z",
        system_available_at="2025-11-02T00:03:00Z",
    )
    correction_id = next(
        row["observation_id"] for row in ledger["observations"]
        if row["version"]["correction_version"] == 2
    )
    tampered = deepcopy(ledger)
    current = tampered["source_snapshots"][-1]
    current["snapshot_fact_observations"] = [
        fact for fact in current["snapshot_fact_observations"]
        if fact["observation_id"] != correction_id
    ]
    _rebind_snapshot_and_ledger_receipts(tampered)
    with pytest.raises(ShareCountTruthError, match="every canonical observation must be referenced"):
        validate_share_count_ledger(tampered)


def test_same_second_and_late_unrelated_issuer_receipts_append_a_bound_ordered_chain():
    first = _compile()
    payload = _payload()
    payload["cik"] = 789019
    second_raw = _with_payload(payload)
    second = compile_share_count_observations(
        second_raw,
        _receipt(
            second_raw,
            issuer_id="issuer:0000789019",
            source_url="https://data.sec.gov/api/xbrl/companyfacts/CIK0000789019.json",
        ),
        existing_ledger=first,
    )

    receipts = second["ledger_receipts"]
    assert len(receipts) == len(second["source_snapshots"]) == 2
    assert [receipt["sequence"] for receipt in receipts] == [1, 2]
    assert receipts[0]["committed_at"] == receipts[1]["committed_at"] == "2025-11-01T00:03:00Z"
    assert receipts[1]["predecessor_ledger_receipt_id"] == receipts[0]["ledger_receipt_id"]
    assert receipts[0]["observation_ids"] == [row["observation_id"] for row in first["observations"]]
    assert receipts[1]["observation_ids"] == [row["observation_id"] for row in second["observations"]]
    assert receipts[1]["source_snapshot_ids"] == [
        snapshot["source_snapshot_id"] for snapshot in second["source_snapshots"]
    ]
    assert second["ledger_head_receipt_id"] == receipts[-1]["ledger_receipt_id"]
    validate_share_count_ledger(second)

    late_payload = _payload()
    late_payload["cik"] = 789020
    late_raw = _with_payload(late_payload)
    late = compile_share_count_observations(
        late_raw,
        _receipt(
            late_raw,
            issuer_id="issuer:0000789020",
            source_url="https://data.sec.gov/api/xbrl/companyfacts/CIK0000789020.json",
            source_retrieved_at="2025-10-30T00:00:00Z",
            system_available_at="2025-10-30T00:03:00Z",
        ),
        existing_ledger=second,
    )
    late_receipt = late["ledger_receipts"][-1]
    assert late_receipt["sequence"] == 3
    assert late_receipt["predecessor_ledger_receipt_id"] == receipts[-1]["ledger_receipt_id"]
    assert late_receipt["committed_at"] == receipts[-1]["committed_at"]
    assert late_receipt["source_snapshot_ids"] == [
        snapshot["source_snapshot_id"] for snapshot in late["source_snapshots"]
    ]
    validate_share_count_ledger(late)

    forged = deepcopy(late)
    forged_receipt = forged["ledger_receipts"][-1]
    forged_receipt["predecessor_ledger_receipt_id"] = "share-count-ledger-receipt:cs:" + ("f" * 24)
    forged_receipt["ledger_receipt_id"] = ledger_receipt_id_for(forged_receipt)
    forged["ledger_head_receipt_id"] = forged_receipt["ledger_receipt_id"]
    with pytest.raises(ShareCountTruthError, match="predecessor chain is broken"):
        validate_share_count_ledger(forged)


def test_p0_deferred_then_later_observed_is_snapshot_local_not_a_false_fact_correction():
    raw = _source_bytes()
    early = compile_share_count_observations(
        raw,
        _receipt(raw, source_retrieved_at="2025-10-30T00:00:00Z", system_available_at="2025-10-30T00:01:00Z"),
    )
    assert early["counts"]["current_snapshot"] == {
        "snapshot_fact_observations": 3, "observed": 0, "deferred": 3, "ambiguous": 0,
    }
    assert all(row["state"]["disposition"] == "deferred" for row in early["observations"])

    later = compile_share_count_observations(
        raw,
        _receipt(raw, source_retrieved_at="2025-11-02T01:00:00Z", system_available_at="2025-11-02T01:04:00Z"),
        existing_ledger=early,
    )
    # Same direct facts: the canonical correction chain is unchanged and keeps
    # its original deferred evidence, while the later source snapshot records
    # independently observed availability and normalized values.
    assert len(later["observations"]) == 3
    assert len(later["source_snapshots"]) == 2
    assert all(row["state"]["disposition"] == "deferred" for row in later["observations"])
    current = later["source_snapshots"][-1]
    facts = current["snapshot_fact_observations"]
    assert all(fact["state"]["disposition"] == "observed" for fact in facts)
    assert all(fact["normalized"]["state"] == "observed" for fact in facts)
    assert {fact["observation_id"] for fact in facts} == {row["observation_id"] for row in later["observations"]}
    assert later["counts"]["current_snapshot"] == {
        "snapshot_fact_observations": 3, "observed": 3, "deferred": 0, "ambiguous": 0,
    }
    validate_share_count_ledger(later)


def test_p1_whole_snapshot_metadata_hash_and_receipt_clock_refresh_preserves_fact_history_and_links_snapshot_facts():
    original = _compile()
    payload = _payload()
    payload["entityName"] = "Example Issuer (issuer-root metadata refreshed)"
    refreshed_raw = _with_payload(payload)
    refreshed = compile_share_count_observations(
        refreshed_raw,
        _receipt(
            refreshed_raw,
            source_retrieved_at="2025-11-02T01:00:00Z",
            system_available_at="2025-11-02T01:04:00Z",
        ),
        existing_ledger=original,
    )

    assert refreshed["observations"] == original["observations"]
    assert len(refreshed["source_snapshots"]) == 2
    snapshot = refreshed["source_snapshots"][-1]
    assert snapshot["source_receipt"]["source_payload_sha256"] == hashlib.sha256(refreshed_raw).hexdigest()
    assert snapshot["source_snapshot_id"] != original["source_snapshots"][0]["source_snapshot_id"]
    assert len(snapshot["fact_links"]) == len(snapshot["snapshot_fact_observations"]) == 3
    assert {link["snapshot_fact_observation_id"] for link in snapshot["fact_links"]} == {
        fact["snapshot_fact_observation_id"] for fact in snapshot["snapshot_fact_observations"]
    }
    assert {fact["observation_id"] for fact in snapshot["snapshot_fact_observations"]} == {
        row["observation_id"] for row in refreshed["observations"]
    }
    for fact in snapshot["snapshot_fact_observations"]:
        validate_snapshot_fact_observation(fact)
        assert fact["fact_entry_sha256s"] == sorted(set(fact["fact_entry_sha256s"]))
    validate_source_snapshot(snapshot, refreshed["observations"])
    validate_share_count_ledger(refreshed)


def test_p2_cross_ledger_tampering_cannot_rebind_snapshot_facts_or_links():
    ledger = _compile()
    tampered = deepcopy(ledger)
    snapshot = tampered["source_snapshots"][0]
    fact = snapshot["snapshot_fact_observations"][0]
    fact["fact_entry_sha256s"] = ["b" * 64]
    fact["snapshot_fact_observation_id"] = snapshot_fact_observation_id_for(fact)
    snapshot["source_snapshot_id"] = source_snapshot_id_for(snapshot)
    with pytest.raises(ShareCountTruthError, match="hashes do not match"):
        validate_share_count_ledger(tampered)

    duplicated = deepcopy(ledger)
    snapshot = duplicated["source_snapshots"][0]
    snapshot["fact_links"].append(deepcopy(snapshot["fact_links"][0]))
    snapshot["source_snapshot_id"] = source_snapshot_id_for(snapshot)
    with pytest.raises(ShareCountTruthError, match="multiple links"):
        validate_share_count_ledger(duplicated)

    receipt_rebound = deepcopy(ledger)
    snapshot = receipt_rebound["source_snapshots"][0]
    fact = snapshot["snapshot_fact_observations"][0]
    fact["source_receipt_id"] = "companyfacts-receipt:cs:" + ("f" * 24)
    fact["snapshot_fact_observation_id"] = snapshot_fact_observation_id_for(fact)
    snapshot["fact_links"][0]["snapshot_fact_observation_id"] = fact["snapshot_fact_observation_id"]
    snapshot["source_snapshot_id"] = source_snapshot_id_for(snapshot)
    with pytest.raises(ShareCountTruthError, match="receipt does not match"):
        validate_share_count_ledger(receipt_rebound)

    detached = deepcopy(ledger)
    snapshot = detached["source_snapshots"][0]
    snapshot["source_snapshot_id"] = "companyfacts-snapshot:cs:" + ("0" * 24)
    with pytest.raises(ShareCountTruthError, match="ID digest"):
        validate_share_count_ledger(detached)


def test_explicit_no_source_result_and_cli_do_not_claim_collector_coverage(capsys, tmp_path):
    result = source_acquisition_unavailable_result()
    assert result["status"] == "unavailable"
    assert result["source_acquisition"] == {
        "state": "unavailable",
        "collector_state": "not_implemented_in_share_count_truth_wave",
        "reason": "no_retained_companyfacts_snapshot_supplied",
    }
    assert main([]) == 0
    rendered = json.loads(capsys.readouterr().out)
    assert rendered["status"] == "unavailable"

    source_path = tmp_path / "companyfacts.json"
    receipt_path = tmp_path / "receipt.json"
    output_path = tmp_path / "observations.json"
    source_path.write_bytes(_source_bytes())
    receipt_path.write_text(json.dumps(_receipt()), encoding="utf-8")
    assert main([
        "--source-json", str(source_path), "--receipt-json", str(receipt_path),
        "--output", str(output_path),
    ]) == 0
    compiled = json.loads(output_path.read_text(encoding="utf-8"))
    assert compiled["status"] == "ok"
    assert len(compiled["observations"]) == 3
    assert len(compiled["source_snapshots"]) == 1
    validate_share_count_ledger(compiled)

    reingested_path = tmp_path / "reingested-ledger.json"
    assert main([
        "--source-json", str(source_path), "--receipt-json", str(receipt_path),
        "--existing-ledger-json", str(output_path), "--output", str(reingested_path),
    ]) == 0
    reingested = json.loads(reingested_path.read_text(encoding="utf-8"))
    assert reingested == compiled
