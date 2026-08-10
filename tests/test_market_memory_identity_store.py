"""Crash, tamper, and idempotency tests for the private identity-v1 store."""

from __future__ import annotations

import copy
import gc
import hashlib
import json
import stat
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from engine.neuralweb import market_memory
from engine.neuralweb import market_memory_identity_observation as observation
from engine.neuralweb import market_memory_identity_store as store
from lib import symbol_directory_receipts

_ROOT = Path(__file__).resolve().parent.parent
_SNAPSHOTS = _ROOT / "data" / "symbol_directory" / "snapshots"


@pytest.fixture(autouse=True)
def _release_arrow_pool_after_test():
    """Keep repeated tamper-store reconstruction inside the CI memory bound."""

    yield
    gc.collect()
    pa.default_memory_pool().release_unused()


def _fixed_clock(monkeypatch: pytest.MonkeyPatch, timestamp: str) -> None:
    value = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    monkeypatch.setattr(observation, "_utc_now", lambda: value)


def _frame(date_partition: str, *, spy: bool = True) -> pd.DataFrame:
    ordinary_rows = 7_999 if spy else 8_000
    symbols = [f"N{index:07d}" for index in range(ordinary_rows)]
    names = [f"Synthetic {index}" for index in range(ordinary_rows)]
    exchanges = ["NASDAQ"] * ordinary_rows
    etfs = [False] * ordinary_rows
    sources = ["nasdaqlisted"] * ordinary_rows
    if spy:
        symbols.append("SPY")
        names.append("SPDR S&P 500 ETF Trust")
        exchanges.append("P")
        etfs.append(True)
        sources.append("otherlisted")
    else:
        symbols[-1] = "DIA"
        names[-1] = "SPDR Dow Jones Industrial Average ETF Trust"
        exchanges[-1] = "P"
        etfs[-1] = True
        sources[-1] = "otherlisted"
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
    symbol_directory_receipts.durable_atomic_write_parquet(
        _frame(date_partition) if frame is None else frame,
        path,
    )
    return path


def _write_operational_receipt(
    artifact: Path, *, date_partition: str, spy: bool
) -> Path:
    fetches = (
        (
            symbol_directory_receipts.NASDAQ_LISTED_SOURCE_ID,
            symbol_directory_receipts.SourceFetch(
                value="nasdaq",
                content=b"exact nasdaq bytes",
                requested_url="https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt",
                started_at=f"{date_partition}T00:00:01.000000Z",
                completed_at=f"{date_partition}T00:00:01.100000Z",
            ),
        ),
        (
            symbol_directory_receipts.OTHER_LISTED_SOURCE_ID,
            symbol_directory_receipts.SourceFetch(
                value="other",
                content=b"exact other bytes",
                requested_url="https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt",
                started_at=f"{date_partition}T00:00:02.000000Z",
                completed_at=f"{date_partition}T00:00:02.100000Z",
            ),
        ),
    )
    occurrences = (
        (
            {
                "source_id": symbol_directory_receipts.OTHER_LISTED_SOURCE_ID,
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
    )
    receipt = symbol_directory_receipts.build_symbol_directory_completion_receipt(
        kind="listing_snapshot",
        observation_date=date_partition,
        artifact_path=artifact,
        source_fetches=fetches,
        collector_started_at=f"{date_partition}T00:00:00.000000Z",
        collector_completed_at=f"{date_partition}T00:00:04.000000Z",
        pre_dedupe_rows=8_000,
        duplicate_occurrences=0,
        duplicate_key_count=0,
        source_row_counts=(
            (symbol_directory_receipts.NASDAQ_LISTED_SOURCE_ID, 7_999),
            (symbol_directory_receipts.OTHER_LISTED_SOURCE_ID, 1),
        ),
        pre_dedupe_spy_occurrences=occurrences,
        non_authoritative_footers=(
            symbol_directory_receipts.footer_diagnostic(
                source_id=symbol_directory_receipts.NASDAQ_LISTED_SOURCE_ID,
                text=f"File Creation Time: {date_partition} 00:00:01",
            ),
            symbol_directory_receipts.footer_diagnostic(
                source_id=symbol_directory_receipts.OTHER_LISTED_SOURCE_ID,
                text=f"File Creation Time: {date_partition} 00:00:02",
            ),
        ),
    )
    sidecar = symbol_directory_receipts.completion_receipt_path(
        artifact.parent.parent,
        kind="listing_snapshot",
        observation_date=date_partition,
    )
    symbol_directory_receipts.write_symbol_directory_completion_receipt(
        sidecar,
        receipt,
        artifact,
        expected_kind="listing_snapshot",
    )
    return sidecar


def _attack_receipt_bundle(
    bundle: observation.SpyListingObservation,
    *,
    raw_body: bytes | None = None,
    may_trade: bool = False,
) -> observation.SpyListingObservation:
    receipt = copy.deepcopy(bundle.completion_receipt)
    assert receipt is not None
    if may_trade:
        receipt["authority"]["may_trade"] = True
        receipt["receipt_id"] = symbol_directory_receipts._receipt_id(receipt)
    body = raw_body or (_canonical(receipt) + b"\n")
    projected = copy.deepcopy(bundle.observation)
    projected["completion_receipt"].update(
        {
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


def _bundle(
    monkeypatch: pytest.MonkeyPatch,
    *,
    timestamp: str = "2026-08-10T20:00:00.000000Z",
    path: Path | None = None,
) -> observation.SpyListingObservation:
    _fixed_clock(monkeypatch, timestamp)
    return observation.build_spy_listing_observation(
        path or (_SNAPSHOTS / "2026-08-10.parquet")
    )


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()


def _all_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | set().union(*(_all_keys(item) for item in value.values()))
    if isinstance(value, list):
        return set().union(*(_all_keys(item) for item in value)) if value else set()
    return set()


def test_imports_all_legacy_snapshots_without_operational_upgrade(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "identity-v1"
    _fixed_clock(monkeypatch, "2026-08-10T20:00:00.000000Z")
    paths = [
        path
        for path in sorted(_SNAPSHOTS.glob("*.parquet"))
        if date.fromisoformat(path.stem) <= observation.OPERATIONAL_RECEIPT_CUTOFF
    ]
    assert paths
    results = [
        store.capture_spy_listing_observation(
            root, observation.build_spy_listing_observation(path)
        )
        for path in paths
    ]
    snapshot = store.load_identity_observation_store(root)

    assert len(results) == len(paths)
    assert all(result.published for result in results)
    assert snapshot.head["capture_count"] == len(paths)
    assert len(snapshot.captures) == len(paths)
    assert {item.observation["pit_basis"] for item in snapshot.captures} == {
        "public_reconstruction"
    }
    assert {item.observation["operational"] for item in snapshot.captures} == {False}
    assert (
        len({item.observation["listing_object_id"] for item in snapshot.captures}) == 1
    )


def test_same_source_retry_is_noop_but_next_date_same_content_appends(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first_path = _write_snapshot(tmp_path / "source", "2026-08-11")
    second_path = _write_snapshot(tmp_path / "source", "2026-08-12")
    root = tmp_path / "identity-v1"
    first_bundle = _bundle(
        monkeypatch,
        timestamp="2026-08-12T01:00:00.000000Z",
        path=first_path,
    )
    first = store.capture_spy_listing_observation(root, first_bundle)
    retry_bundle = _bundle(
        monkeypatch,
        timestamp="2026-08-12T02:00:00.000000Z",
        path=first_path,
    )
    retry = store.capture_spy_listing_observation(root, retry_bundle)
    second_bundle = _bundle(
        monkeypatch,
        timestamp="2026-08-12T03:00:00.000000Z",
        path=second_path,
    )
    second = store.capture_spy_listing_observation(root, second_bundle)

    assert first.published is True
    assert retry.published is False
    assert retry.observation["observed_at"] == first.observation["observed_at"]
    assert retry.head["capture_count"] == 1
    assert second.published is True
    assert second.head["capture_count"] == 2
    assert (
        second.observation["listing_object_id"]
        == first.observation["listing_object_id"]
    )
    assert (
        second.observation["source_observation_id"]
        != first.observation["source_observation_id"]
    )


def test_same_operational_receipt_retry_is_noop_and_keeps_first_clock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact = _write_snapshot(tmp_path / "source", "2026-08-11")
    sidecar = _write_operational_receipt(
        artifact, date_partition="2026-08-11", spy=True
    )
    root = tmp_path / "identity-v1"
    _fixed_clock(monkeypatch, "2026-08-11T00:00:05.000000Z")
    first_bundle = observation.build_spy_listing_observation(
        artifact, completion_receipt_path=sidecar
    )
    first = store.capture_spy_listing_observation(root, first_bundle)
    _fixed_clock(monkeypatch, "2026-08-11T00:00:06.000000Z")
    retry_bundle = observation.build_spy_listing_observation(
        artifact, completion_receipt_path=sidecar
    )
    retry = store.capture_spy_listing_observation(root, retry_bundle)

    assert retry.published is False
    assert (
        retry.observation["source_observation_id"]
        == first.observation["source_observation_id"]
    )
    assert retry.observation["observed_at"] == "2026-08-11T00:00:05.000000Z"
    assert retry.head["capture_count"] == 1


@pytest.mark.parametrize(
    "stage",
    [
        "source_artifact",
        "listing_object",
        "upstream_receipt",
        "prepared",
        "capture_receipt",
        "generation",
    ],
)
def test_every_pre_head_crash_prefix_is_invisible_and_retryable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
) -> None:
    root = tmp_path / stage / "identity-v1"
    bundle = _bundle(monkeypatch)

    def crash(current: str) -> None:
        if current == stage:
            raise RuntimeError(f"crash after {stage}")

    monkeypatch.setattr(store, "_fault_injection_point", crash)
    with pytest.raises(RuntimeError, match=stage):
        store.capture_spy_listing_observation(root, bundle)

    invisible = store.load_identity_observation_store(root)
    assert invisible.head["capture_count"] == 0
    assert invisible.captures == ()

    monkeypatch.setattr(store, "_fault_injection_point", lambda _step: None)
    later_bundle = _bundle(monkeypatch, timestamp="2026-08-10T21:00:00.000000Z")
    recovered = store.capture_spy_listing_observation(root, later_bundle)
    assert recovered.published is True
    assert recovered.head["capture_count"] == 1
    assert recovered.observation["observed_at"] == "2026-08-10T20:00:00.000000Z"


def test_prepared_record_preserves_first_clock_across_later_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "identity-v1"
    first = _bundle(monkeypatch, timestamp="2026-08-10T20:00:00.000000Z")

    def crash_after_prepared(stage: str) -> None:
        if stage == "prepared":
            raise RuntimeError("prepared crash")

    monkeypatch.setattr(store, "_fault_injection_point", crash_after_prepared)
    with pytest.raises(RuntimeError, match="prepared crash"):
        store.capture_spy_listing_observation(root, first)
    assert store.load_identity_observation_store(root).head["capture_count"] == 0

    later = _bundle(monkeypatch, timestamp="2026-08-10T21:00:00.000000Z")
    monkeypatch.setattr(store, "_fault_injection_point", lambda _step: None)
    result = store.capture_spy_listing_observation(root, later)

    assert result.observation["observed_at"] == "2026-08-10T20:00:00.000000Z"
    assert result.observation["available_at"] == "2026-08-10T20:00:00.000000Z"
    assert result.capture_receipt["captured_at"] == "2026-08-10T20:00:00.000000Z"


def test_crash_after_head_is_visible_and_retry_is_noop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "identity-v1"
    bundle = _bundle(monkeypatch)

    def crash_after_head(stage: str) -> None:
        if stage == "head":
            raise RuntimeError("head crash")

    monkeypatch.setattr(store, "_fault_injection_point", crash_after_head)
    with pytest.raises(RuntimeError, match="head crash"):
        store.capture_spy_listing_observation(root, bundle)

    visible = store.load_identity_observation_store(root)
    assert visible.head["capture_count"] == 1
    monkeypatch.setattr(store, "_fault_injection_point", lambda _step: None)
    retry = store.capture_spy_listing_observation(root, bundle)
    assert retry.published is False
    assert retry.head["capture_count"] == 1


@pytest.mark.parametrize(
    "target",
    [
        "source_artifact",
        "listing_object",
        "prepared_record",
        "capture_receipt",
        "generation",
        "head",
    ],
)
def test_visible_source_object_receipt_generation_and_head_tamper_is_fatal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    target: str,
) -> None:
    root = tmp_path / target / "identity-v1"
    result = store.capture_spy_listing_observation(root, _bundle(monkeypatch))
    receipt = result.capture_receipt
    if target == "source_artifact":
        path = root / receipt["source_artifact"]["object_key"]
        body = bytearray(path.read_bytes())
        body[len(body) // 2] ^= 1
        path.write_bytes(bytes(body))
    elif target == "listing_object":
        path = root / receipt["listing_object"]["object_key"]
        value = json.loads(path.read_bytes())
        value["listing"]["security_name"] = "Tampered Trust"
        path.write_bytes(_canonical(value))
    elif target == "prepared_record":
        path = root / receipt["prepared_record"]["object_key"]
        path.write_bytes(path.read_bytes() + b" ")
    elif target == "capture_receipt":
        path = (
            root
            / "captures"
            / receipt["capture_id"].removeprefix("mmidscan_")[:2]
            / f"{receipt['capture_id']}.json"
        )
        path.write_bytes(path.read_bytes() + b" ")
    elif target == "generation":
        path = (
            root
            / "generations"
            / result.generation["generation_id"].removeprefix("mmidgen_")[:2]
            / f"{result.generation['generation_id']}.json"
        )
        path.write_bytes(path.read_bytes() + b" ")
    else:
        path = root / "HEAD.json"
        path.write_bytes(path.read_bytes() + b" ")

    with pytest.raises(store.MarketMemoryIdentityStoreError):
        store.load_identity_observation_store(root)


def test_generation_requires_exact_complete_ancestry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "identity-v1"
    first_path = _write_snapshot(tmp_path / "source", "2026-08-11")
    second_path = _write_snapshot(tmp_path / "source", "2026-08-12")
    first = store.capture_spy_listing_observation(
        root,
        _bundle(monkeypatch, timestamp="2026-08-12T01:00:00.000000Z", path=first_path),
    )
    store.capture_spy_listing_observation(
        root,
        _bundle(monkeypatch, timestamp="2026-08-12T02:00:00.000000Z", path=second_path),
    )
    previous_id = first.generation["generation_id"]
    previous_path = (
        root
        / "generations"
        / previous_id.removeprefix("mmidgen_")[:2]
        / f"{previous_id}.json"
    )
    previous_path.unlink()

    with pytest.raises(store.MarketMemoryIdentityStoreError, match="generation"):
        store.load_identity_observation_store(root)


def test_date_conflict_is_fatal_but_next_complete_absence_is_observed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first_path = _write_snapshot(tmp_path / "first", "2026-08-11")
    conflict_frame = _frame("2026-08-11")
    conflict_frame.loc[conflict_frame["symbol"] == "SPY", "security_name"] = (
        "Changed Source Name"
    )
    conflict_path = _write_snapshot(
        tmp_path / "conflict", "2026-08-11", frame=conflict_frame
    )
    absent_path = _write_snapshot(
        tmp_path / "absent", "2026-08-12", frame=_frame("2026-08-12", spy=False)
    )
    root = tmp_path / "identity-v1"
    store.capture_spy_listing_observation(
        root,
        _bundle(monkeypatch, timestamp="2026-08-12T01:00:00.000000Z", path=first_path),
    )
    with pytest.raises(
        store.MarketMemoryIdentityCaptureError,
        match="different observation|date",
    ):
        store.capture_spy_listing_observation(
            root,
            _bundle(
                monkeypatch,
                timestamp="2026-08-12T02:00:00.000000Z",
                path=conflict_path,
            ),
        )
    absent = store.capture_spy_listing_observation(
        root,
        _bundle(
            monkeypatch,
            timestamp="2026-08-12T03:00:00.000000Z",
            path=absent_path,
        ),
    )

    assert absent.observation["listing_state"] == (
        "symbol_absent_from_complete_snapshot"
    )
    assert "delist" not in json.dumps(absent.observation).lower()
    assert absent.head["capture_count"] == 2


def test_receipt_backed_operational_absence_persists_without_delist_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact = _write_snapshot(
        tmp_path / "source",
        "2026-08-11",
        frame=_frame("2026-08-11", spy=False),
    )
    sidecar = _write_operational_receipt(
        artifact, date_partition="2026-08-11", spy=False
    )
    _fixed_clock(monkeypatch, "2026-08-11T00:00:05.000000Z")
    bundle = observation.build_spy_listing_observation(
        artifact, completion_receipt_path=sidecar
    )
    root = tmp_path / "identity-v1"

    result = store.capture_spy_listing_observation(root, bundle)
    loaded = store.load_identity_observation_store(root)

    assert result.observation["operational"] is True
    assert result.observation["listing_state"] == (
        "symbol_absent_from_complete_snapshot"
    )
    assert loaded.captures[0].listing_object["semantic_limits"]["delisting"] is False
    assert (
        loaded.captures[0].listing_object["semantic_limits"]["listing_continuity"]
        is False
    )
    assert "delist" not in json.dumps(result.observation).lower()


@pytest.mark.parametrize(
    ("raw_body", "may_trade"),
    [(b"not json", False), (None, True)],
)
def test_malformed_or_rebound_privileged_receipt_never_advances_head(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    raw_body: bytes | None,
    may_trade: bool,
) -> None:
    artifact = _write_snapshot(tmp_path / "source", "2026-08-11")
    sidecar = _write_operational_receipt(
        artifact, date_partition="2026-08-11", spy=True
    )
    _fixed_clock(monkeypatch, "2026-08-11T00:00:05.000000Z")
    valid = observation.build_spy_listing_observation(
        artifact, completion_receipt_path=sidecar
    )
    attacked = _attack_receipt_bundle(valid, raw_body=raw_body, may_trade=may_trade)
    root = tmp_path / "identity-v1"
    store.initialize_identity_observation_store(root)

    with pytest.raises(
        store.MarketMemoryIdentityCaptureError,
        match="candidate SPY listing observation is invalid",
    ):
        store.capture_spy_listing_observation(root, attacked)

    snapshot = store.load_identity_observation_store(root)
    assert snapshot.head["capture_count"] == 0
    assert snapshot.captures == ()
    assert not (root / "prepared").exists()


def test_root_and_internal_symlinks_or_public_permissions_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(store.MarketMemoryIdentityStoreError, match="too broad"):
        store.initialize_identity_observation_store("/")
    with pytest.raises(store.MarketMemoryIdentityStoreError):
        store.initialize_identity_observation_store(Path.home())
    with pytest.raises(store.MarketMemoryIdentityStoreError, match="repository"):
        store.initialize_identity_observation_store(_ROOT, repository_root=_ROOT)
    repository = tmp_path / "repository"
    repository.mkdir(mode=0o700)
    for publicish_child in ("data", "contracts"):
        with pytest.raises(store.MarketMemoryIdentityStoreError, match="inside"):
            store.initialize_identity_observation_store(
                repository / publicish_child / "identity-v1",
                repository_root=repository,
            )
    for production_collision in (
        "/var/lib/macro-market-memory",
        "/var/lib/macro-market-memory/state",
        "/var/lib/macro-market-memory/public/trusted-v1",
        "/var/lib/macro-market-memory/state/sources",
        "/var/lib/macro-market-memory/state/identity-v1/child",
    ):
        with pytest.raises(store.MarketMemoryIdentityStoreError, match="exact private"):
            store.validate_identity_observation_store_root(production_collision)

    real_root = tmp_path / "real"
    real_root.mkdir(mode=0o700)
    symlink_root = tmp_path / "linked"
    symlink_root.symlink_to(real_root, target_is_directory=True)
    with pytest.raises(store.MarketMemoryIdentityStoreError, match="symlink"):
        store.initialize_identity_observation_store(symlink_root)

    lax_root = tmp_path / "lax"
    lax_root.mkdir(mode=0o755)
    with pytest.raises(store.MarketMemoryIdentityStoreError, match="group/other"):
        store.initialize_identity_observation_store(lax_root)

    root = tmp_path / "identity-v1"
    result = store.capture_spy_listing_observation(root, _bundle(monkeypatch))
    object_root = root / "listing_objects"
    relocated = root / "listing_objects-real"
    object_root.rename(relocated)
    object_root.symlink_to(relocated, target_is_directory=True)
    assert result.head["capture_count"] == 1
    with pytest.raises(store.MarketMemoryIdentityStoreError, match="symlink"):
        store.load_identity_observation_store(root)


def test_mutable_bundle_bytes_fail_before_store_or_prepared_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "identity-v1"
    bundle = _bundle(monkeypatch)
    attacked = replace(bundle, snapshot_bytes=bytearray(bundle.snapshot_bytes))

    with pytest.raises(
        store.MarketMemoryIdentityCaptureError,
        match="candidate SPY listing observation is invalid",
    ):
        store.capture_spy_listing_observation(root, attacked)

    assert not root.exists()


def test_store_files_are_private_and_no_cik_or_authority_promotion_leaks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "identity-v1"
    result = store.capture_spy_listing_observation(root, _bundle(monkeypatch))
    snapshot = store.load_identity_observation_store(root)
    payload = {
        "manifest": snapshot.manifest,
        "generation": snapshot.generation,
        "capture": result.capture_receipt,
    }

    assert stat.S_IMODE(root.stat().st_mode) == 0o700
    for path in root.rglob("*"):
        if path.is_file():
            assert stat.S_IMODE(path.stat().st_mode) & 0o077 == 0
    assert not {"cik", "sec_registrant_ref", "issuer_id"}.intersection(
        {key.lower() for key in _all_keys(payload)}
    )
    for authority in (
        snapshot.manifest["authority"],
        result.capture_receipt["authority"],
        result.observation["authority"],
    ):
        assert authority == dict(market_memory.AUTHORITY)
        assert all(
            value is False for key, value in authority.items() if key.startswith("may_")
        )
    assert result.capture_receipt["evidence_policy"]["training_eligible"] is False
    assert result.capture_receipt["evidence_policy"]["promotion_eligible"] is False


def test_prepared_capture_and_store_receipt_schemas_validate_exact_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "identity-v1"
    result = store.capture_spy_listing_observation(root, _bundle(monkeypatch))
    snapshot = store.load_identity_observation_store(root)
    prepared_path = root / result.capture_receipt["prepared_record"]["object_key"]
    prepared = json.loads(prepared_path.read_bytes())

    prepared_schema = json.loads(
        (
            _ROOT
            / "contracts"
            / "market_memory"
            / "identity_observation_prepared.v1.schema.json"
        ).read_text()
    )
    capture_schema = json.loads(
        (
            _ROOT
            / "contracts"
            / "market_memory"
            / "identity_observation_capture_receipt.v1.schema.json"
        ).read_text()
    )
    store_schema = json.loads(
        (
            _ROOT
            / "contracts"
            / "market_memory"
            / "identity_observation_store_receipts.v1.schema.json"
        ).read_text()
    )
    observation_schema = json.loads(
        (
            _ROOT
            / "contracts"
            / "market_memory"
            / "spy_listing_observation.v1.schema.json"
        ).read_text()
    )
    registry = Registry().with_resource(
        observation_schema["$id"], Resource.from_contents(observation_schema)
    )
    for schema in (prepared_schema, capture_schema, store_schema):
        Draft202012Validator.check_schema(schema)
    prepared_validator = Draft202012Validator(prepared_schema, registry=registry)
    capture_validator = Draft202012Validator(capture_schema, registry=registry)
    prepared_validator.validate(prepared)
    capture_validator.validate(result.capture_receipt)
    receipt_validator = Draft202012Validator(store_schema)
    receipt_validator.validate(snapshot.manifest)
    receipt_validator.validate(snapshot.generation)
    receipt_validator.validate(snapshot.head)

    prepared_with_cik = copy.deepcopy(prepared)
    prepared_with_cik["observation"]["cik"] = 884394
    assert list(prepared_validator.iter_errors(prepared_with_cik))
    capture_with_cik = copy.deepcopy(result.capture_receipt)
    capture_with_cik["observation"]["cik"] = 884394
    assert list(capture_validator.iter_errors(capture_with_cik))
    prepared_with_false_authentication = copy.deepcopy(prepared)
    prepared_with_false_authentication["evidence_policy"][
        "completion_receipt_authenticated"
    ] = True
    assert list(prepared_validator.iter_errors(prepared_with_false_authentication))
    prepared_with_fabricated_receipt = copy.deepcopy(prepared)
    prepared_with_fabricated_receipt["completion_receipt_id"] = "sdreceipt_" + "0" * 64
    assert list(prepared_validator.iter_errors(prepared_with_fabricated_receipt))
    capture_with_false_authentication = copy.deepcopy(result.capture_receipt)
    capture_with_false_authentication["evidence_policy"][
        "completion_receipt_authenticated"
    ] = True
    assert list(capture_validator.iter_errors(capture_with_false_authentication))
    capture_with_fabricated_receipt = copy.deepcopy(result.capture_receipt)
    capture_with_fabricated_receipt["upstream_receipt"] = {
        "receipt_id": "sdreceipt_" + "0" * 64,
        "sha256": "0" * 64,
        "bytes": 1,
        "object_key": "upstream_receipts/00/" + "0" * 64 + ".json",
    }
    assert list(capture_validator.iter_errors(capture_with_fabricated_receipt))

    operational_artifact = _write_snapshot(tmp_path, "2026-08-11")
    operational_sidecar = _write_operational_receipt(
        operational_artifact,
        date_partition="2026-08-11",
        spy=True,
    )
    _fixed_clock(monkeypatch, "2026-08-11T00:00:05.000000Z")
    operational_bundle = observation.build_spy_listing_observation(
        operational_artifact,
        completion_receipt_path=operational_sidecar,
    )
    operational_root = tmp_path / "operational-identity-v1"
    operational_result = store.capture_spy_listing_observation(
        operational_root,
        operational_bundle,
    )
    operational_prepared_path = (
        operational_root
        / operational_result.capture_receipt["prepared_record"]["object_key"]
    )
    prepared_validator.validate(json.loads(operational_prepared_path.read_bytes()))
    capture_validator.validate(operational_result.capture_receipt)

    contradictory_generation = copy.deepcopy(snapshot.generation)
    contradictory_generation["captures"][0]["pit_basis"] = "live_captured"
    contradictory_generation["captures"][0]["operational"] = False
    assert list(receipt_validator.iter_errors(contradictory_generation))


def test_default_root_is_fixed_private_state_not_repository_data() -> None:
    assert store.default_identity_observation_store_root(_ROOT) == Path(
        "/var/lib/macro-market-memory/state/identity-v1"
    )
