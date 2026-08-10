"""Adversarial tests for the bounded SPY listing observation projector."""

from __future__ import annotations

import copy
import gc
import hashlib
import json
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pytest
from jsonschema import Draft202012Validator

from engine.neuralweb import market_memory
from engine.neuralweb import market_memory_identity_observation as observation
from lib import symbol_directory_receipts as source_receipts

_ROOT = Path(__file__).resolve().parent.parent
_SNAPSHOTS = _ROOT / "data" / "symbol_directory" / "snapshots"
_NASDAQ_ROWS = 5_000
_OTHER_ROWS = 6_500
_TOTAL_ROWS = _NASDAQ_ROWS + _OTHER_ROWS


@pytest.fixture(autouse=True)
def _release_arrow_pool_after_test():
    """Keep the adversarial multi-parquet lane within the CI pack memory bound."""

    yield
    gc.collect()
    pa.default_memory_pool().release_unused()


def _frame(date_partition: str, *, spy: bool = True) -> pd.DataFrame:
    symbols = [f"N{index:07d}" for index in range(_NASDAQ_ROWS)] + [
        f"O{index:07d}" for index in range(_OTHER_ROWS - 1)
    ]
    names = [f"Nasdaq Synthetic {index}" for index in range(_NASDAQ_ROWS)] + [
        f"Other Synthetic {index}" for index in range(_OTHER_ROWS - 1)
    ]
    exchanges = ["NASDAQ"] * _NASDAQ_ROWS + ["N"] * (_OTHER_ROWS - 1)
    etfs = [False] * (_TOTAL_ROWS - 1)
    sources = ["nasdaqlisted"] * _NASDAQ_ROWS + ["otherlisted"] * (_OTHER_ROWS - 1)
    symbols.append("SPY" if spy else "DIA")
    names.append(
        "SPDR S&P 500 ETF Trust"
        if spy
        else "SPDR Dow Jones Industrial Average ETF Trust"
    )
    exchanges.append("P")
    etfs.append(True)
    sources.append("otherlisted")
    rows = len(symbols)
    return pd.DataFrame(
        {
            "date": [date_partition] * rows,
            "symbol": symbols,
            "security_name": names,
            "exchange": exchanges,
            "etf": etfs,
            "test_issue": [False] * rows,
            "is_preferred": [False] * rows,
            "source": sources,
        }
    )


def _write_snapshot(
    tmp_path: Path,
    date_partition: str,
    *,
    frame: pd.DataFrame | None = None,
) -> Path:
    path = tmp_path / "symbol_directory" / "snapshots" / f"{date_partition}.parquet"
    source_receipts.durable_atomic_write_parquet(
        _frame(date_partition) if frame is None else frame,
        path,
    )
    return path


def _source_fetches(
    date_partition: str,
) -> tuple[
    tuple[str, source_receipts.SourceFetch[str]],
    tuple[str, source_receipts.SourceFetch[str]],
]:
    return (
        (
            source_receipts.NASDAQ_LISTED_SOURCE_ID,
            source_receipts.SourceFetch(
                value="decoded Nasdaq response",
                content=b"exact Nasdaq response bytes\r\n",
                requested_url="https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt",
                started_at=f"{date_partition}T00:00:01.000000Z",
                completed_at=f"{date_partition}T00:00:01.100000Z",
            ),
        ),
        (
            source_receipts.OTHER_LISTED_SOURCE_ID,
            source_receipts.SourceFetch(
                value="decoded other response",
                content=b"exact other response bytes\r\n",
                requested_url="https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt",
                started_at=f"{date_partition}T00:00:02.000000Z",
                completed_at=f"{date_partition}T00:00:02.100000Z",
            ),
        ),
    )


def _write_receipt(
    artifact: Path,
    *,
    date_partition: str,
    collector_completed_at: str | None = None,
    spy: bool = True,
) -> tuple[Path, dict]:
    receipt = source_receipts.build_symbol_directory_completion_receipt(
        kind="listing_snapshot",
        observation_date=date_partition,
        artifact_path=artifact,
        source_fetches=_source_fetches(date_partition),
        collector_started_at=f"{date_partition}T00:00:00.000000Z",
        collector_completed_at=(
            collector_completed_at or f"{date_partition}T00:00:04.000000Z"
        ),
        pre_dedupe_rows=_TOTAL_ROWS,
        duplicate_occurrences=0,
        duplicate_key_count=0,
        source_row_counts=(
            (source_receipts.NASDAQ_LISTED_SOURCE_ID, _NASDAQ_ROWS),
            (source_receipts.OTHER_LISTED_SOURCE_ID, _OTHER_ROWS),
        ),
        pre_dedupe_spy_occurrences=(
            (
                {
                    "source_id": source_receipts.OTHER_LISTED_SOURCE_ID,
                    "symbol": "SPY",
                    "security_name": "SPDR S&P 500 ETF Trust",
                    "exchange": "P",
                    "etf": True,
                    "test_issue": False,
                    "is_preferred": False,
                },
            )
            if spy
            else ()
        ),
        non_authoritative_footers=(
            source_receipts.footer_diagnostic(
                source_id=source_receipts.NASDAQ_LISTED_SOURCE_ID,
                text=f"File Creation Time: {date_partition} 00:00:01",
            ),
            source_receipts.footer_diagnostic(
                source_id=source_receipts.OTHER_LISTED_SOURCE_ID,
                text=f"File Creation Time: {date_partition} 00:00:02",
            ),
        ),
    )
    sidecar = source_receipts.completion_receipt_path(
        artifact.parent.parent,
        kind="listing_snapshot",
        observation_date=date_partition,
    )
    source_receipts.write_symbol_directory_completion_receipt(
        sidecar,
        receipt,
        artifact,
        expected_kind="listing_snapshot",
    )
    return sidecar, receipt


def _fixed_clock(monkeypatch: pytest.MonkeyPatch, timestamp: str) -> None:
    value = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    monkeypatch.setattr(observation, "_utc_now", lambda: value)


def _all_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | set().union(*(_all_keys(item) for item in value.values()))
    if isinstance(value, list):
        return set().union(*(_all_keys(item) for item in value)) if value else set()
    return set()


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()


def _rebind_attacked_receipt(
    bundle: observation.SpyListingObservation,
    mutate,
    *,
    body_override: bytes | None = None,
) -> observation.SpyListingObservation:
    receipt = copy.deepcopy(bundle.completion_receipt)
    assert receipt is not None
    mutate(receipt)
    receipt["receipt_id"] = source_receipts._receipt_id(receipt)
    body = body_override or (_canonical(receipt) + b"\n")
    projected = copy.deepcopy(bundle.observation)
    reference = projected["completion_receipt"]
    reference.update(
        {
            "schema": receipt["schema"],
            "profile": receipt["profile"],
            "receipt_id": receipt["receipt_id"],
            "sha256": hashlib.sha256(body).hexdigest(),
            "bytes": len(body),
        }
    )
    projected["source_observation_id"] = observation._source_observation_id(projected)
    return replace(
        bundle,
        completion_receipt=receipt,
        completion_receipt_bytes=body,
        observation=projected,
        observation_bytes=_canonical(projected),
    )


def test_all_legacy_tracked_snapshots_remain_reconstruction_observations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fixed_clock(monkeypatch, "2026-08-10T20:00:00.000000Z")
    paths = [
        path
        for path in sorted(_SNAPSHOTS.glob("*.parquet"))
        if date.fromisoformat(path.stem) <= observation.OPERATIONAL_RECEIPT_CUTOFF
    ]
    assert paths

    bundles = [observation.build_spy_listing_observation(path) for path in paths]

    assert {bundle.observation["pit_basis"] for bundle in bundles} == {
        "public_reconstruction"
    }
    assert {bundle.observation["operational"] for bundle in bundles} == {False}
    assert {bundle.observation["listing_state"] for bundle in bundles} == {
        "present_in_snapshot"
    }
    assert len({bundle.listing_object["listing_object_id"] for bundle in bundles}) == 1
    assert len(
        {bundle.observation["source_observation_id"] for bundle in bundles}
    ) == len(paths)
    assert all(bundle.completion_receipt is None for bundle in bundles)


def test_listing_object_and_observation_schemas_validate_exact_outputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fixed_clock(monkeypatch, "2026-08-10T20:00:00.000000Z")
    bundle = observation.build_spy_listing_observation(
        _SNAPSHOTS / "2026-08-10.parquet"
    )
    for filename, payload in (
        ("spy_listing_object.v1.schema.json", bundle.listing_object),
        ("spy_listing_observation.v1.schema.json", bundle.observation),
    ):
        schema = json.loads(
            (_ROOT / "contracts" / "market_memory" / filename).read_text()
        )
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(payload)


def test_snapshot_gap_is_not_absence_and_complete_absence_is_not_delisting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fixed_clock(monkeypatch, "2026-08-12T01:00:00.000000Z")
    missing = tmp_path / "symbol_directory" / "snapshots" / "2026-08-11.parquet"
    with pytest.raises(observation.SnapshotMissing) as error:
        observation.build_spy_listing_observation(missing)
    assert error.value.status == "snapshot_missing"

    absent_path = _write_snapshot(
        tmp_path, "2026-08-12", frame=_frame("2026-08-12", spy=False)
    )
    bundle = observation.build_spy_listing_observation(absent_path)

    assert bundle.listing_object["state"] == "symbol_absent_from_complete_snapshot"
    assert bundle.listing_object["listing"] is None
    assert bundle.listing_object["semantic_limits"]["delisting"] is False
    assert bundle.listing_object["semantic_limits"]["listing_continuity"] is False
    assert "delisted" not in json.dumps(bundle.observation).lower()


def test_prospective_receipt_is_operational_only_at_post_read_process_clock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact = _write_snapshot(tmp_path, "2026-08-11")
    sidecar, receipt = _write_receipt(artifact, date_partition="2026-08-11")
    _fixed_clock(monkeypatch, "2026-08-11T00:00:05.000000Z")

    bundle = observation.build_spy_listing_observation(
        artifact, completion_receipt_path=sidecar
    )

    assert bundle.completion_receipt == receipt
    assert bundle.observation["pit_basis"] == "live_captured"
    assert bundle.observation["operational"] is True
    assert bundle.observation["measurement_time"] == "2026-08-11T00:00:04.000000Z"
    assert bundle.observation["available_at"] == "2026-08-11T00:00:05.000000Z"
    assert bundle.observation["observed_at"] == "2026-08-11T00:00:05.000000Z"
    assert receipt["evidence_policy"]["source_response_integrity"] == (
        "sha256_bytes_commitment_at_capture.v1"
    )
    assert receipt["evidence_policy"]["source_response_bytes_retained"] is False
    assert receipt["evidence_policy"]["source_response_replay_verifiable"] is False
    assert bundle.observation["partition_bounds"] == {
        "precision": "date_partition",
        "lower_bound": "2026-08-11T00:00:00.000000Z",
        "upper_bound_exclusive": "2026-08-12T00:00:00.000000Z",
    }


def test_valid_legacy_cutoff_receipt_cannot_retroactively_upgrade_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact = _write_snapshot(tmp_path, "2026-08-10")
    sidecar, _receipt = _write_receipt(artifact, date_partition="2026-08-10")
    _fixed_clock(monkeypatch, "2026-08-10T00:00:05.000000Z")

    with pytest.raises(
        observation.MarketMemoryIdentityObservationError,
        match="cutoff|legacy",
    ):
        observation.build_spy_listing_observation(
            artifact, completion_receipt_path=sidecar
        )


def test_spy_absence_cannot_be_upgraded_but_remains_reconstruction_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact = _write_snapshot(
        tmp_path,
        "2026-08-11",
        frame=_frame("2026-08-11", spy=False),
    )
    with pytest.raises(
        source_receipts.ReceiptValidationError,
        match="requires exactly one SPY occurrence",
    ):
        _write_receipt(artifact, date_partition="2026-08-11", spy=False)
    _fixed_clock(monkeypatch, "2026-08-11T00:00:05.000000Z")

    bundle = observation.build_spy_listing_observation(artifact)

    assert bundle.observation["operational"] is False
    assert bundle.observation["pit_basis"] == "public_reconstruction"
    assert bundle.observation["listing_state"] == (
        "symbol_absent_from_complete_snapshot"
    )
    assert bundle.listing_object["listing"] is None
    assert bundle.listing_object["semantic_limits"]["delisting"] is False
    assert bundle.listing_object["semantic_limits"]["listing_continuity"] is False


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value["authority"].__setitem__("may_trade", True),
        lambda value: value.__setitem__("schema", "attacker.receipt.v1"),
        lambda value: value.__setitem__("profile", "attacker.profile.v1"),
        lambda value: value["producer"].__setitem__("version", "attacker.v1"),
        lambda value: value["sources"][0].__setitem__(
            "requested_url", "https://attacker.invalid/symbols"
        ),
        lambda value: value["completeness"].__setitem__("status", "partial"),
        lambda value: value["evidence_policy"].__setitem__(
            "source_response_bytes_retained", True
        ),
    ],
)
def test_recomputed_receipt_id_cannot_bypass_full_source_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutate,
) -> None:
    artifact = _write_snapshot(tmp_path, "2026-08-11")
    sidecar, _receipt = _write_receipt(artifact, date_partition="2026-08-11")
    _fixed_clock(monkeypatch, "2026-08-11T00:00:05.000000Z")
    valid = observation.build_spy_listing_observation(
        artifact, completion_receipt_path=sidecar
    )
    attacked = _rebind_attacked_receipt(valid, mutate)

    with pytest.raises(
        observation.MarketMemoryIdentityObservationError,
        match="full exact-byte source validation",
    ):
        observation.validate_spy_listing_observation(attacked)


def test_partial_present_or_orphan_receipt_is_fatal_never_a_downgrade(
    tmp_path: Path,
) -> None:
    artifact = _write_snapshot(tmp_path, "2026-08-11")
    sidecar = observation.infer_listing_completion_receipt_path(artifact)
    sidecar.parent.mkdir(parents=True)
    sidecar.write_text('{"schema":"symbol_directory.completion_receipt.v1"}')

    with pytest.raises(
        observation.MarketMemoryIdentityObservationError,
        match="receipt",
    ):
        observation.build_spy_listing_observation(artifact)

    orphan = tmp_path / "orphan" / "snapshots" / "2026-08-12.parquet"
    orphan_sidecar = observation.infer_listing_completion_receipt_path(orphan)
    orphan_sidecar.parent.mkdir(parents=True)
    orphan_sidecar.write_text('{"schema":"symbol_directory.completion_receipt.v1"}')
    with pytest.raises(observation.SnapshotMissing):
        observation.build_spy_listing_observation(orphan)


def test_receipt_cannot_backdate_market_memory_observation_clock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact = _write_snapshot(tmp_path, "2026-08-11")
    sidecar, _receipt = _write_receipt(artifact, date_partition="2026-08-11")
    _fixed_clock(monkeypatch, "2026-08-11T00:00:03.999999Z")

    with pytest.raises(
        observation.MarketMemoryIdentityObservationError,
        match="before collector completion",
    ):
        observation.build_spy_listing_observation(
            artifact, completion_receipt_path=sidecar
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("exchange", "N", "anchor"),
        ("etf", False, "anchor"),
        ("test_issue", True, "anchor"),
        ("is_preferred", True, "anchor"),
        ("source", "nasdaqlisted", "anchor"),
    ],
)
def test_rejects_spy_anchor_drift(
    tmp_path: Path,
    field: str,
    value: object,
    message: str,
) -> None:
    frame = _frame("2026-08-11")
    frame.loc[frame["symbol"] == "SPY", field] = value
    path = _write_snapshot(tmp_path, "2026-08-11", frame=frame)

    with pytest.raises(observation.MarketMemoryIdentityObservationError, match=message):
        observation.build_spy_listing_observation(path)


def test_rejects_duplicate_spy_and_partition_date_drift(tmp_path: Path) -> None:
    duplicate = pd.concat(
        [_frame("2026-08-11"), _frame("2026-08-11").tail(1)],
        ignore_index=True,
    )
    duplicate_path = _write_snapshot(
        tmp_path / "duplicate", "2026-08-11", frame=duplicate
    )
    with pytest.raises(
        observation.MarketMemoryIdentityObservationError, match="duplicate"
    ):
        observation.build_spy_listing_observation(duplicate_path)

    wrong_date = _frame("2026-08-11")
    wrong_date.loc[0, "date"] = "2026-08-10"
    wrong_date_path = _write_snapshot(
        tmp_path / "wrong-date", "2026-08-11", frame=wrong_date
    )
    with pytest.raises(
        observation.MarketMemoryIdentityObservationError,
        match="date partition",
    ):
        observation.build_spy_listing_observation(wrong_date_path)


def test_same_source_retry_keeps_ids_while_new_date_is_a_new_observation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first_path = _write_snapshot(tmp_path, "2026-08-11")
    second_path = _write_snapshot(tmp_path, "2026-08-12")
    _fixed_clock(monkeypatch, "2026-08-12T01:00:00.000000Z")
    first = observation.build_spy_listing_observation(first_path)
    _fixed_clock(monkeypatch, "2026-08-12T02:00:00.000000Z")
    retry = observation.build_spy_listing_observation(first_path)
    second = observation.build_spy_listing_observation(second_path)

    assert (
        retry.observation["source_observation_id"]
        == first.observation["source_observation_id"]
    )
    assert retry.observation["observed_at"] != first.observation["observed_at"]
    assert (
        second.listing_object["listing_object_id"]
        == first.listing_object["listing_object_id"]
    )
    assert (
        second.observation["source_observation_id"]
        != first.observation["source_observation_id"]
    )


def test_symlinks_arbitrary_sidecars_and_canary_config_drift_fail_closed(
    tmp_path: Path,
) -> None:
    artifact = _write_snapshot(tmp_path, "2026-08-11")
    symlink = artifact.with_name("2026-08-12.parquet")
    symlink.symlink_to(artifact)
    with pytest.raises(
        observation.MarketMemoryIdentityObservationError,
        match="non-symlink",
    ):
        observation.build_spy_listing_observation(symlink)

    arbitrary = tmp_path / "receipt.json"
    arbitrary.write_text("{}")
    with pytest.raises(
        observation.MarketMemoryIdentityObservationError,
        match="canonical sidecar",
    ):
        observation.build_spy_listing_observation(
            artifact, completion_receipt_path=arbitrary
        )

    config = json.loads(
        observation.market_memory_identity.DEFAULT_CONFIG_PATH.read_text()
    )
    config["subject"]["instrument_id"] = "mmsecurity_" + "0" * 64
    drifted_config = tmp_path / "drifted-canary.json"
    drifted_config.write_text(json.dumps(config))
    with pytest.raises(
        observation.MarketMemoryIdentityObservationError,
        match="anchor",
    ):
        observation.build_spy_listing_observation(artifact, config_path=drifted_config)


def test_listing_lane_excludes_cik_and_keeps_every_authority_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fixed_clock(monkeypatch, "2026-08-10T20:00:00.000000Z")
    bundle = observation.build_spy_listing_observation(
        _SNAPSHOTS / "2026-08-10.parquet"
    )
    payload = {
        "listing_object": bundle.listing_object,
        "observation": bundle.observation,
    }
    keys = {key.lower() for key in _all_keys(payload)}

    assert not {"cik", "sec_registrant_ref", "issuer_id"}.intersection(keys)
    assert bundle.listing_object["authority"] == dict(market_memory.AUTHORITY)
    assert bundle.observation["authority"] == dict(market_memory.AUTHORITY)
    assert all(
        value is False
        for key, value in bundle.observation["authority"].items()
        if key.startswith("may_")
    )
    assert bundle.observation["evidence_policy"]["training_eligible"] is False
    assert bundle.observation["evidence_policy"]["promotion_eligible"] is False
    forbidden_outside_authority = {
        "options",
        "outcome",
        "prophet",
        "rank",
        "gate",
        "size",
        "trade",
    }
    keys_without_authority = _all_keys(
        {key: value for key, value in payload.items() if key != "authority"}
    )
    assert not forbidden_outside_authority.intersection(
        {key.lower() for key in keys_without_authority}
    )


def test_validation_rejects_detached_object_or_observation_tamper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fixed_clock(monkeypatch, "2026-08-10T20:00:00.000000Z")
    bundle = observation.build_spy_listing_observation(
        _SNAPSHOTS / "2026-08-10.parquet"
    )
    object_tamper = bundle.detached()
    object_tamper.listing_object["listing"]["mic"] = "XNYS"
    with pytest.raises(observation.MarketMemoryIdentityObservationError):
        observation.validate_spy_listing_observation(object_tamper)

    observation_tamper = bundle.detached()
    observation_tamper.observation["operational"] = True
    with pytest.raises(observation.MarketMemoryIdentityObservationError):
        observation.validate_spy_listing_observation(observation_tamper)


def test_validation_requires_exact_nonempty_bounded_bytes_before_projection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact = _write_snapshot(tmp_path, "2026-08-11")
    sidecar, _receipt = _write_receipt(artifact, date_partition="2026-08-11")
    _fixed_clock(monkeypatch, "2026-08-11T00:00:05.000000Z")
    bundle = observation.build_spy_listing_observation(
        artifact, completion_receipt_path=sidecar
    )

    for field in (
        "snapshot_bytes",
        "listing_object_bytes",
        "observation_bytes",
        "completion_receipt_bytes",
    ):
        attacked = replace(bundle, **{field: bytearray(getattr(bundle, field))})
        with pytest.raises(
            observation.MarketMemoryIdentityObservationError,
            match="exact immutable bytes",
        ):
            observation.validate_spy_listing_observation(attacked)

    for field in (
        "snapshot_bytes",
        "listing_object_bytes",
        "observation_bytes",
        "completion_receipt_bytes",
    ):
        attacked = replace(bundle, **{field: b""})
        with pytest.raises(
            observation.MarketMemoryIdentityObservationError,
            match="empty or exceeds",
        ):
            observation.validate_spy_listing_observation(attacked)

    oversized = replace(
        bundle,
        observation_bytes=b"x" * (observation._MAX_OBSERVATION_BYTES + 1),
    )
    with pytest.raises(
        observation.MarketMemoryIdentityObservationError,
        match="empty or exceeds",
    ):
        observation.validate_spy_listing_observation(oversized)
