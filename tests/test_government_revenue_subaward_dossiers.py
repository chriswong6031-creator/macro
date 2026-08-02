"""Contract tests for the pure, receipt-bound subaward dossier projector."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from jsonschema import Draft202012Validator, FormatChecker

import collectors.usaspending_subawards as collector_contract
import engine.government_revenue.subaward_dossiers as dossier_engine

from engine.government_revenue.subaward_dossiers import (
    AUTHORITY,
    MAX_DESCRIPTION_BYTES,
    MAX_SUBAWARD_RECORDS,
    build_subaward_dossier_payload,
    is_valid_subaward_dossier_payload,
    subaward_dossier_content_id,
)


SCHEMA_PATH = (
    Path(__file__).resolve().parents[1]
    / "contracts"
    / "government_revenue"
    / "government_subaward_dossiers.v1.schema.json"
)
SNAPSHOT_COLUMNS = (
    "parent_generated_award_id",
    "subaward_id",
    "subaward_number",
    "action_date",
    "reported_subaward_amount",
    "description",
    "subrecipient_name",
    "subaward_state_sha256",
    "known_at",
    "effective_at",
    "first_seen_at",
    "source_url",
    "source_receipt_id",
    "source_response_sha256",
    "receipt_verified",
)
PRIMES = {"PRIME_ONE": "generated:prime-one"}


def _install_collector_contract(monkeypatch) -> None:
    monkeypatch.setitem(
        sys.modules,
        "collectors.usaspending_subawards",
        SimpleNamespace(
            SUBAWARD_SNAPSHOT_COLUMNS=SNAPSHOT_COLUMNS,
            subaward_projection_generation_matches=lambda state, frame: (
                state.get("projection_generation_id") == "generation-good"
                and state.get("subaward_snapshots_row_count") == len(frame)
            ),
            subaward_parent_coverage_semantic_sha256=lambda parents: "coverage-good",
            _subaward_state_sha256=collector_contract._subaward_state_sha256,
        ),
    )


def _source_row(
    native_id: str,
    *,
    displayed: str = "DISPLAY-REPEATS",
    action_date: str = "2026-07-20",
    description: str = "Official reported subaward",
    known_at: str = "2026-08-02T01:00:00+00:00",
) -> dict:
    return {
        "parent_generated_award_id": "PRIME_ONE",
        "subaward_id": native_id,
        "subaward_number": displayed,
        "action_date": action_date,
        "reported_subaward_amount": 125.0,
        "description": description,
        "subrecipient_name": "Atlas Systems",
        "subaward_state_sha256": None,
        "known_at": known_at,
        "effective_at": action_date,
        "first_seen_at": known_at,
        "source_url": collector_contract.SUBAWARDS_URL,
        "source_receipt_id": None,
        "source_response_sha256": None,
        "receipt_verified": True,
    }


def _write_bundle(tmp_path: Path, rows: list[dict], *, generation: str = "generation-good") -> None:
    data_dir = tmp_path / "data" / "government_revenue"
    data_dir.mkdir(parents=True, exist_ok=True)
    normalized_rows = [dict(row) for row in rows]
    by_clock: dict[str, list[dict]] = {}
    for row in normalized_rows:
        by_clock.setdefault(str(row["known_at"]), []).append(row)
    if any(len(group) > 500 for group in by_clock.values()):
        raise ValueError("test bundle clock groups must honor the 500-row parent cap")

    detail_receipts: list[dict] = []
    receipt_ids_by_clock: dict[str, list[str]] = {}
    for observed_at, group in sorted(by_clock.items()):
        receipt_ids_by_clock[observed_at] = []
        for page, offset in enumerate(range(0, len(group), 100), 1):
            chunk = group[offset:offset + 100]
            request = {
                "award_id": "PRIME_ONE",
                "page": page,
                "limit": 100,
                "sort": "action_date",
                "order": "desc",
            }
            response = {
                "page_metadata": {"page": page},
                "results": [
                    {
                        "id": row["subaward_id"],
                        "subaward_number": row["subaward_number"],
                        "action_date": row["action_date"],
                        "amount": row["reported_subaward_amount"],
                        "description": row["description"],
                        "recipient_name": row["subrecipient_name"],
                    }
                    for row in chunk
                ],
            }
            receipt = collector_contract.UsaspendingSubawardsCollector._receipt(
                rail="subaward_detail",
                endpoint=collector_contract.SUBAWARDS_URL,
                request_payload=request,
                response_payload=response,
                parent_generated_award_id="PRIME_ONE",
                observed_at=observed_at,
                page=page,
                record_count=len(chunk),
            )
            detail_receipts.append(receipt)
            receipt_ids_by_clock[observed_at].append(receipt["receipt_id"])
            for row in chunk:
                row["source_receipt_id"] = receipt["receipt_id"]
                row["source_response_sha256"] = receipt["response_sha256"]
                row["subaward_state_sha256"] = collector_contract._subaward_state_sha256(row)

    current_clock = max(by_clock) if by_clock else "2026-08-02T01:00:00+00:00"
    current_rows = by_clock.get(current_clock, [])
    count_endpoint = collector_contract.SUBAWARD_COUNT_URL.format(award_id="PRIME_ONE")
    count_receipt = collector_contract.UsaspendingSubawardsCollector._receipt(
        rail="subaward_count",
        endpoint=count_endpoint,
        request_payload={"method": "GET", "endpoint": count_endpoint},
        response_payload={"subawards": len(current_rows)},
        parent_generated_award_id="PRIME_ONE",
        observed_at=current_clock,
        page=None,
        record_count=1,
        reported_subaward_count=len(current_rows),
    )
    pd.DataFrame(normalized_rows, columns=SNAPSHOT_COLUMNS).to_parquet(
        data_dir / "subaward_snapshots.parquet", index=False
    )
    (data_dir / "subaward_collection_receipts.jsonl").write_text(
        "\n".join(json.dumps(row) for row in (count_receipt, *detail_receipts)) + "\n",
        encoding="utf-8",
    )
    (data_dir / "subaward_projection_state.json").write_text(
        json.dumps({
            "contract": "government_revenue.subaward_projection_state.v1",
            "schema_version": "1.0.0",
            "activation_state": "live",
            "bounded_collection_complete": True,
            "projection_eligible": True,
            "projection_generation_id": generation,
            "subaward_snapshots_row_count": len(normalized_rows),
            "parent_coverage_semantic_sha256": "coverage-good",
            "public_downstream_row_cap": 2000,
            "selected_parent_count": 1,
            "parents": [{
                "parent_generated_award_id": "PRIME_ONE",
                "subaward_count": len(current_rows),
                "count_verified": True,
                "high_count_parent": False,
                "collection_state": "complete" if current_rows else "zero",
                "detail_rows": len(current_rows),
                "pages_fetched": (len(current_rows) + 99) // 100,
                "source_exhausted": True,
                "count_receipt_id": count_receipt["receipt_id"],
                "count_receipt_binding": {
                    "receipt_id": count_receipt["receipt_id"],
                    "rail": "subaward_count",
                    "parent_generated_award_id": "PRIME_ONE",
                    "reported_subaward_count": len(current_rows),
                },
                "detail_receipt_ids": receipt_ids_by_clock.get(current_clock, []),
            }],
        }),
        encoding="utf-8",
    )
    (data_dir / "subaward_ingest_status.json").write_text(
        json.dumps({
            "contract": "government_revenue.subaward_ingest_status.v1",
            "schema_version": "1.0.0",
            "projection_generation_id": generation,
            "status": "ok",
            "partial": False,
            "collection_complete": True,
            "projection_eligible": True,
            "bounded": True,
            "source_only": True,
            "daily_lane": True,
            "errors": [],
            "effective_at": "2026-07-20",
            "observed_at": current_clock,
        }),
        encoding="utf-8",
    )


def test_empty_first_state_covers_every_exact_prime_and_validates(tmp_path: Path) -> None:
    primes = {"PRIME_TWO": "generated:two", "PRIME_ONE": "generated:one"}
    payload = build_subaward_dossier_payload(
        tmp_path,
        prime_award_key_by_generated_id=primes,
        as_of="2026-08-02",
    )

    assert payload["contract"] == "government_subaward_dossiers.v1"
    assert payload["schema_version"] == "1.0.0"
    assert payload["source_coverage"]["status"] == "unavailable"
    assert payload["subawards"] == []
    assert {
        row["parent_generated_award_id"]: row["award_key"] for row in payload["primes"]
    } == primes
    assert all(row["coverage"]["status"] == "unavailable" for row in payload["primes"])
    assert is_valid_subaward_dossier_payload(payload)


def test_partial_bundle_is_rejected(tmp_path: Path) -> None:
    data_dir = tmp_path / "data" / "government_revenue"
    data_dir.mkdir(parents=True)
    pd.DataFrame(columns=SNAPSHOT_COLUMNS).to_parquet(
        data_dir / "subaward_snapshots.parquet", index=False
    )

    with pytest.raises(ValueError, match="partial"):
        build_subaward_dossier_payload(
            tmp_path, prime_award_key_by_generated_id=PRIMES, as_of="2026-08-02"
        )


def test_generation_and_receipt_mismatches_fail_closed(tmp_path: Path, monkeypatch) -> None:
    _install_collector_contract(monkeypatch)
    _write_bundle(tmp_path, [_source_row("native-1")], generation="generation-wrong")
    with pytest.raises(ValueError, match="activation generation"):
        build_subaward_dossier_payload(tmp_path, prime_award_key_by_generated_id=PRIMES)

    _write_bundle(tmp_path, [_source_row("native-1")])
    snapshots = pd.read_parquet(
        tmp_path / "data" / "government_revenue" / "subaward_snapshots.parquet"
    )
    snapshots.loc[0, "source_response_sha256"] = "c" * 64
    snapshots.to_parquet(
        tmp_path / "data" / "government_revenue" / "subaward_snapshots.parquet",
        index=False,
    )
    with pytest.raises(ValueError, match="response hash"):
        build_subaward_dossier_payload(tmp_path, prime_award_key_by_generated_id=PRIMES)


def test_receipt_request_endpoint_identity_and_row_state_fail_closed(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _install_collector_contract(monkeypatch)
    data_dir = tmp_path / "data" / "government_revenue"

    def mutate_detail(mutator) -> None:
        receipts_path = data_dir / "subaward_collection_receipts.jsonl"
        receipts = [json.loads(line) for line in receipts_path.read_text().splitlines()]
        detail = next(row for row in receipts if row["rail"] == "subaward_detail")
        old_id = detail["receipt_id"]
        mutator(detail)
        detail["receipt_id"] = dossier_engine._receipt_content_id(detail)
        receipts_path.write_text(
            "\n".join(json.dumps(row) for row in receipts) + "\n", encoding="utf-8"
        )
        snapshots_path = data_dir / "subaward_snapshots.parquet"
        snapshots = pd.read_parquet(snapshots_path)
        snapshots.loc[snapshots["source_receipt_id"] == old_id, "source_receipt_id"] = (
            detail["receipt_id"]
        )
        snapshots.to_parquet(snapshots_path, index=False)
        state_path = data_dir / "subaward_projection_state.json"
        state = json.loads(state_path.read_text())
        state["parents"][0]["detail_receipt_ids"] = [detail["receipt_id"]]
        state_path.write_text(json.dumps(state))

    _write_bundle(tmp_path, [_source_row("native-1")])
    mutate_detail(
        lambda receipt: receipt.update(
            endpoint="https://api.usaspending.gov/api/v2/awards/not-subawards/"
        )
    )
    with pytest.raises(ValueError, match="endpoint, page, or row count"):
        build_subaward_dossier_payload(tmp_path, prime_award_key_by_generated_id=PRIMES)

    _write_bundle(tmp_path, [_source_row("native-1")])
    mutate_detail(lambda receipt: receipt.update(request_sha256="0" * 64))
    with pytest.raises(ValueError, match="request hash mismatch"):
        build_subaward_dossier_payload(tmp_path, prime_award_key_by_generated_id=PRIMES)

    _write_bundle(tmp_path, [_source_row("native-1")])
    snapshots_path = data_dir / "subaward_snapshots.parquet"
    snapshots = pd.read_parquet(snapshots_path)
    snapshots.loc[0, "reported_subaward_amount"] = 999.0
    snapshots.to_parquet(snapshots_path, index=False)
    with pytest.raises(ValueError, match="state hash mismatch"):
        build_subaward_dossier_payload(tmp_path, prime_award_key_by_generated_id=PRIMES)


def test_native_identity_survives_duplicate_display_number_and_utf8_cap(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _install_collector_contract(monkeypatch)
    _write_bundle(
        tmp_path,
        [
            _source_row("native-1", description="界" * 900),
            _source_row("native-2", action_date="2026-07-21"),
        ],
    )
    payload = build_subaward_dossier_payload(
        tmp_path, prime_award_key_by_generated_id=PRIMES, as_of="2026-08-02"
    )

    assert len(payload["subawards"]) == 2
    assert len({row["subaward_key"] for row in payload["subawards"]}) == 2
    assert {
        row["identity"]["source_subaward_id"] for row in payload["subawards"]
    } == {"native-1", "native-2"}
    assert {
        row["identity"]["displayed_subaward_number"] for row in payload["subawards"]
    } == {"DISPLAY-REPEATS"}
    assert {row["reported_amount"]["amount"] for row in payload["subawards"]} == {125.0}
    truncated = next(
        row for row in payload["subawards"] if row["identity"]["source_subaward_id"] == "native-1"
    )
    assert truncated["description_truncated"] is True
    assert len(truncated["description"].encode("utf-8")) <= MAX_DESCRIPTION_BYTES
    assert "token=secret" not in json.dumps(payload)


def test_public_cap_content_identity_schema_and_non_authority(tmp_path: Path, monkeypatch) -> None:
    _install_collector_contract(monkeypatch)
    rows = [
        _source_row(
            f"native-{index}",
            action_date=f"2026-07-{1 + index % 28:02d}",
            known_at=f"2026-08-{1 + index // 500:02d}T01:00:00+00:00",
        )
        for index in range(MAX_SUBAWARD_RECORDS + 1)
    ]
    _write_bundle(tmp_path, rows)
    payload = build_subaward_dossier_payload(
        tmp_path, prime_award_key_by_generated_id=PRIMES, as_of="2026-08-02"
    )

    assert len(payload["subawards"]) == MAX_SUBAWARD_RECORDS
    assert payload["source_coverage"]["truncated_by_artifact_cap"] is True
    assert payload["source_coverage"]["records_dropped"] == 1
    assert payload["content_id"].startswith("grsd1-")
    assert payload["content_id"] == subaward_dossier_content_id(payload)
    reassembled = json.loads(json.dumps(payload))
    reassembled["generated_at"] = "2030-01-01T00:00:00+00:00"
    assert subaward_dossier_content_id(reassembled) == payload["content_id"]

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    assert payload["authority"] == AUTHORITY
    assert all(value is False for key, value in AUTHORITY.items() if key.startswith("can_"))
    rendered = json.dumps(payload).casefold()
    for forbidden in ("issuer", "ticker", "company metric", "rollup", "signal score"):
        assert forbidden not in rendered
    assert "not a federal obligation, outlay, prime-award value" in rendered


def test_validator_rejects_parent_envelope_and_content_tampering(tmp_path: Path) -> None:
    payload = build_subaward_dossier_payload(
        tmp_path, prime_award_key_by_generated_id=PRIMES, as_of="2026-08-02"
    )
    payload["primes"][0]["award_key"] = "generated:not-prime"
    assert not is_valid_subaward_dossier_payload(payload)

    payload = build_subaward_dossier_payload(
        tmp_path, prime_award_key_by_generated_id=PRIMES, as_of="2026-08-02"
    )
    payload["content_id"] = "grsd1-" + "0" * 24
    assert not is_valid_subaward_dossier_payload(payload)


def test_append_versioned_identity_projects_latest_receipt_bound_state(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _install_collector_contract(monkeypatch)
    old = _source_row("native-1", description="state A")
    old.update(
        known_at="2026-08-01T01:00:00+00:00",
        first_seen_at="2026-08-01T01:00:00+00:00",
    )
    new = _source_row("native-1", description="state B")
    new.update(
        known_at="2026-08-02T01:00:00+00:00",
        first_seen_at="2026-08-01T01:00:00+00:00",
    )
    _write_bundle(tmp_path, [old, new])
    data_dir = tmp_path / "data" / "government_revenue"

    payload = build_subaward_dossier_payload(
        tmp_path, prime_award_key_by_generated_id=PRIMES, as_of="2026-08-02"
    )

    assert len(payload["subawards"]) == 1
    assert payload["subawards"][0]["description"] == "state B"
    latest_receipt_id = payload["subawards"][0]["provenance"]["receipt_id"]

    snapshots_path = data_dir / "subaward_snapshots.parquet"
    snapshots = pd.read_parquet(snapshots_path)
    latest_mask = snapshots["source_receipt_id"] == latest_receipt_id
    snapshots.loc[latest_mask, "known_at"] = "2026-08-01T01:00:00+00:00"
    receipts_path = data_dir / "subaward_collection_receipts.jsonl"
    receipts = [json.loads(line) for line in receipts_path.read_text().splitlines()]
    latest_receipt = next(row for row in receipts if row["receipt_id"] == latest_receipt_id)
    latest_receipt["observed_at"] = "2026-08-01T01:00:00+00:00"
    conflict_receipt_id = dossier_engine._receipt_content_id(latest_receipt)
    latest_receipt["receipt_id"] = conflict_receipt_id
    snapshots.loc[latest_mask, "source_receipt_id"] = conflict_receipt_id
    snapshots.to_parquet(snapshots_path, index=False)
    receipts_path.write_text(
        "\n".join(json.dumps(row) for row in receipts) + "\n", encoding="utf-8"
    )
    state_path = data_dir / "subaward_projection_state.json"
    state = json.loads(state_path.read_text())
    state["parents"][0]["detail_receipt_ids"] = [conflict_receipt_id]
    state_path.write_text(json.dumps(state))
    with pytest.raises(ValueError, match="conflicting states at the same evidence clock"):
        build_subaward_dossier_payload(
            tmp_path, prime_award_key_by_generated_id=PRIMES, as_of="2026-08-02"
        )


def test_ineligible_or_raw_source_bundle_is_rejected(tmp_path: Path, monkeypatch) -> None:
    _install_collector_contract(monkeypatch)
    _write_bundle(tmp_path, [_source_row("native-1")])
    data_dir = tmp_path / "data" / "government_revenue"
    status_path = data_dir / "subaward_ingest_status.json"
    status = json.loads(status_path.read_text())
    status["partial"] = True
    status_path.write_text(json.dumps(status))
    with pytest.raises(ValueError, match="publication-eligible"):
        build_subaward_dossier_payload(tmp_path, prime_award_key_by_generated_id=PRIMES)

    status["partial"] = False
    status_path.write_text(json.dumps(status))
    receipts_path = data_dir / "subaward_collection_receipts.jsonl"
    receipts = [json.loads(line) for line in receipts_path.read_text().splitlines()]
    receipts[0]["raw_response_body"] = {"do": "not persist"}
    receipts_path.write_text("\n".join(json.dumps(row) for row in receipts) + "\n")
    with pytest.raises(ValueError, match="forbidden raw or secret-shaped key"):
        build_subaward_dossier_payload(tmp_path, prime_award_key_by_generated_id=PRIMES)


def test_real_collector_generation_contract_is_consumed(tmp_path: Path) -> None:
    from collectors.usaspending_subawards import (
        subaward_parent_coverage_semantic_sha256,
        subaward_projection_generation,
    )

    _write_bundle(tmp_path, [_source_row("101")])
    data_dir = tmp_path / "data" / "government_revenue"
    snapshot_path = data_dir / "subaward_snapshots.parquet"
    frame = pd.read_parquet(snapshot_path)
    generation = subaward_projection_generation(frame)
    state_path = data_dir / "subaward_projection_state.json"
    state = json.loads(state_path.read_text())
    state.update(generation)
    state["parent_coverage_semantic_sha256"] = subaward_parent_coverage_semantic_sha256(
        state["parents"]
    )
    state_path.write_text(json.dumps(state))
    status_path = data_dir / "subaward_ingest_status.json"
    status = json.loads(status_path.read_text())
    status["projection_generation_id"] = generation["projection_generation_id"]
    status_path.write_text(json.dumps(status))

    payload = build_subaward_dossier_payload(
        tmp_path, prime_award_key_by_generated_id=PRIMES, as_of="2026-08-02"
    )

    assert payload["subawards"][0]["identity"]["source_subaward_id"] == "101"
    assert payload["subawards"][0]["reported_amount"]["amount"] == 125.0


def test_high_count_parent_keeps_verified_count_without_inventing_details(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _install_collector_contract(monkeypatch)
    _write_bundle(tmp_path, [])
    data_dir = tmp_path / "data" / "government_revenue"
    receipts_path = data_dir / "subaward_collection_receipts.jsonl"
    receipts = [json.loads(line) for line in receipts_path.read_text().splitlines()]
    receipts[0]["reported_subaward_count"] = 900
    receipts[0]["receipt_id"] = dossier_engine._receipt_content_id(receipts[0])
    receipts_path.write_text("\n".join(json.dumps(row) for row in receipts) + "\n")
    state_path = data_dir / "subaward_projection_state.json"
    state = json.loads(state_path.read_text())
    parent = state["parents"][0]
    parent.update(
        subaward_count=900,
        high_count_parent=True,
        collection_state="high_count_count_only",
        detail_rows=0,
        pages_fetched=0,
        source_exhausted=False,
        detail_receipt_ids=[],
        count_receipt_id=receipts[0]["receipt_id"],
    )
    parent["count_receipt_binding"]["receipt_id"] = receipts[0]["receipt_id"]
    parent["count_receipt_binding"]["reported_subaward_count"] = 900
    state_path.write_text(json.dumps(state))

    payload = build_subaward_dossier_payload(
        tmp_path, prime_award_key_by_generated_id=PRIMES, as_of="2026-08-02"
    )

    coverage = payload["primes"][0]["coverage"]
    assert payload["subawards"] == []
    assert coverage["status"] == "partial"
    assert coverage["reported_count"] == 900
    assert coverage["records_published"] == 0
    assert coverage["truncated_by_collection_policy"] is True


def test_impossible_complete_high_count_parent_fails_closed(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _install_collector_contract(monkeypatch)
    _write_bundle(tmp_path, [_source_row("native-1")])
    data_dir = tmp_path / "data" / "government_revenue"
    receipts_path = data_dir / "subaward_collection_receipts.jsonl"
    receipts = [json.loads(line) for line in receipts_path.read_text().splitlines()]
    count_receipt = next(row for row in receipts if row["rail"] == "subaward_count")
    old_count_id = count_receipt["receipt_id"]
    count_receipt["reported_subaward_count"] = 501
    count_receipt["receipt_id"] = dossier_engine._receipt_content_id(count_receipt)
    receipts_path.write_text(
        "\n".join(json.dumps(row) for row in receipts) + "\n", encoding="utf-8"
    )
    state_path = data_dir / "subaward_projection_state.json"
    state = json.loads(state_path.read_text())
    parent = state["parents"][0]
    parent["subaward_count"] = 501
    parent["count_receipt_id"] = count_receipt["receipt_id"]
    parent["count_receipt_binding"].update(
        receipt_id=count_receipt["receipt_id"], reported_subaward_count=501
    )
    assert old_count_id != count_receipt["receipt_id"]
    state_path.write_text(json.dumps(state))

    with pytest.raises(ValueError, match="complete subaward parent coverage"):
        build_subaward_dossier_payload(tmp_path, prime_award_key_by_generated_id=PRIMES)
