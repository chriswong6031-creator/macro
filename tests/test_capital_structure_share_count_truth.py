"""Adversarial contract tests for the SEC observed share-count truth plane."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from engine.capital_structure.share_count_truth import (
    ShareCountTruthError,
    compile_share_count_observations,
    observation_id_for,
    source_acquisition_unavailable_result,
    validate_share_count_history,
)
from scripts.compile_capital_structure_share_counts import main


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "capital_structure" / "share_count_truth" / "companyfacts_0000320193.json"
SCHEMA_PATH = ROOT / "contracts" / "capital_structure_share_count_observation.schema.json"


def _source_bytes() -> bytes:
    return FIXTURE.read_bytes()


def _payload(source_bytes: bytes | None = None) -> dict:
    return json.loads((source_bytes or _source_bytes()).decode("utf-8"))


def _receipt(source_bytes: bytes | None = None, **overrides) -> dict:
    raw = source_bytes or _source_bytes()
    receipt = {
        "source_system": "sec_companyfacts",
        "acquisition_state": "provided_snapshot",
        "issuer_id": "issuer:0000320193",
        "source_url": "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json",
        "source_payload_sha256": hashlib.sha256(raw).hexdigest(),
        "source_retrieved_at": "2025-11-01T00:00:00Z",
        "system_available_at": "2025-11-01T00:03:00Z",
    }
    receipt.update(overrides)
    return receipt


def _compile(source_bytes: bytes | None = None, *, existing=()):
    raw = source_bytes or _source_bytes()
    return compile_share_count_observations(raw, _receipt(raw), existing_observations=existing)


def _schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _validate(record: dict) -> list[str]:
    validator = Draft202012Validator(_schema(), format_checker=FormatChecker())
    return [error.message for error in validator.iter_errors(record)]


def _with_payload(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


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
        assert row["state"] == {"disposition": "observed", "reason": "direct_sec_companyfacts_fact"}
        assert row["point_in_time"]["available_at"] == "2025-11-01T00:03:00Z"
        assert row["source_acquisition"]["collector_state"] == "not_implemented_in_share_count_truth_wave"
        assert row["authority"] == {
            "is_context_only": True, "rank_authority": False, "sizing_authority": False,
            "entry_authority": False, "trade_authority": False, "prophet_authority": False,
        }

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
    with pytest.raises(ShareCountTruthError, match="payload hash"):
        compile_share_count_observations(raw, _receipt(raw, source_payload_sha256="a" * 64))
    with pytest.raises(ShareCountTruthError, match="cannot precede"):
        compile_share_count_observations(
            raw,
            _receipt(raw, source_retrieved_at="2025-11-01T00:04:00Z", system_available_at="2025-11-01T00:03:00Z"),
        )


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
    original = _compile()["observations"]
    payload = _payload()
    payload["facts"]["us-gaap"]["CommonStockSharesOutstanding"]["units"]["shares"][0]["val"] = 155000000
    changed = _compile(_with_payload(payload), existing=original)["observations"]
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

    idempotent = _compile(_with_payload(payload), existing=changed)
    assert idempotent["counts"]["new_observations"] == 0
    assert idempotent["observations"] == changed


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
