"""Adversarial contracts for the Market Memory W1A temporal spine."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlencode

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, ValidationError

from app import market_memory as api
from engine.neuralweb import market_memory as mm
from engine.neuralweb import market_memory_pit as pit
from engine.neuralweb import market_memory_trusted as trusted
from tests.test_market_memory import (
    DYNAMIC_SOURCE_RECEIPT,
    _observe_snapshot,
    _source_for_feature,
)
from tests.test_market_memory import _as_known_at as _valid_w0_packet

ROOT = Path(__file__).resolve().parents[1]
CUTOFF = datetime(2026, 8, 7, 20, 5, tzinfo=timezone.utc)
CAPTURED_AT = CUTOFF + timedelta(seconds=30)


@pytest.fixture(autouse=True)
def _reset_context_rate_limits() -> None:
    api._reset_symbol_rate_limit_for_tests()
    yield
    api._reset_symbol_rate_limit_for_tests()


def _packet() -> mm.AsKnownAtContext:
    packet = _valid_w0_packet()
    features = deepcopy(packet["feature_receipts"])
    observed = next(row for row in features if row["status"] == "observed")
    observed.update(
        {
            "value": None,
            "status": "missing",
            "source_receipt_ids": [],
            "pit_basis": "unknown",
            "transform_version": "market_memory.missing.v1",
            "quality": {
                "status": "missing",
                "flags": ["not_captured"],
                "staleness_seconds": None,
                "imputed": False,
            },
            "missing_reason": "no_point_in_time_vintage",
        }
    )
    identity_source_ids = set(packet["identity_receipt"]["source_receipt_ids"])
    sources = [
        deepcopy(row)
        for row in packet["source_receipts"]
        if row["receipt_id"] in identity_source_ids
    ]
    return _rebuild(packet, source_receipts=sources, feature_receipts=features)


def _initialize_empty_trusted_api_store(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "trusted-v1"
    monkeypatch.setenv("MARKET_MEMORY_TRUSTED_STORE_DIR", str(root))
    state = trusted.initialize_trusted_store(root)
    assert state["capture_count"] == 0


def _rebuild(packet: mm.AsKnownAtContext, **overrides: object) -> mm.AsKnownAtContext:
    kwargs: dict[str, object] = {
        "subject": deepcopy(packet["subject"]),
        "event_time": packet["clocks"]["event_time"],
        "as_known_at": packet["clocks"]["as_known_at"],
        "mode": packet["mode"],
        "source_receipts": deepcopy(packet["source_receipts"]),
        "identity_receipt": deepcopy(packet["identity_receipt"]),
        "feature_receipts": deepcopy(packet["feature_receipts"]),
        "feature_registry_version": packet["feature_registry_version"],
        "source_registry_version": packet["source_registry_version"],
        "state_snapshot_ref": None,
        "required_domains": list(packet["required_domains"]),
    }
    kwargs.update(overrides)
    return mm.build_as_known_at_context(**kwargs)  # type: ignore[arg-type]


def _different_packet_for_same_query() -> mm.AsKnownAtContext:
    packet = _packet()
    features = deepcopy(packet["feature_receipts"])
    missing = next(row for row in features if row["status"] == "missing")
    missing["missing_reason"] = "adapter_not_implemented"
    return _rebuild(packet, feature_receipts=features)


def _later_packet(seconds: int) -> mm.AsKnownAtContext:
    packet = _packet()
    sources = deepcopy(packet["source_receipts"])
    for source in sources:
        source["age_at_cutoff_seconds"] += seconds
    cutoff = (CUTOFF + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")
    return _rebuild(packet, as_known_at=cutoff, source_receipts=sources)


def _snapshot_packet() -> mm.AsKnownAtContext:
    packet = _packet()
    sources = deepcopy(packet["source_receipts"])
    features = deepcopy(packet["feature_receipts"])
    sources.append(_source_for_feature("macro.regime_state"))
    _observe_snapshot(features, "macro.regime_state", DYNAMIC_SOURCE_RECEIPT)
    return _valid_w0_packet(
        source_receipts=sources,
        identity_receipt=deepcopy(packet["identity_receipt"]),
        feature_receipts=features,
    )


def _fixed_clock(
    monkeypatch: pytest.MonkeyPatch, value: datetime = CAPTURED_AT
) -> None:
    monkeypatch.setattr(pit, "_utc_now", lambda: value)


def _api_client(*, denied_status: int | None = None) -> TestClient:
    application = FastAPI()
    application.include_router(api.router)
    if denied_status is None:
        application.dependency_overrides[api.require_site_full_user] = lambda: {
            "id": "pit-test-user"
        }
    else:

        def denied() -> None:
            raise HTTPException(status_code=denied_status, detail="denied")

        application.dependency_overrides[api.require_site_full_user] = denied
    return TestClient(application)


def _query_url(packet: mm.AsKnownAtContext, **overrides: str) -> str:
    query = {
        "subject_id": packet["subject"]["subject_id"],
        "instrument_id": packet["subject"]["instrument_id"],
        "event_time": packet["clocks"]["event_time"],
        "as_known_at": packet["clocks"]["as_known_at"],
        "mode": packet["mode"],
    }
    query.update(overrides)
    return "/api/market-memory/v1/as-known-at?" + urlencode(query)


def _assert_private(response) -> None:
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["vary"] == "Authorization"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_capture_publishes_exact_bytes_and_both_exact_read_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _fixed_clock(monkeypatch)
    packet = _packet()

    stored = pit.capture_context(tmp_path, packet)
    receipt = stored.capture_receipt
    expected_body = pit._canonical_bytes(stored.packet)

    assert receipt["packet_sha256"] == sha256(expected_body).hexdigest()
    assert receipt["packet_sha256"] != stored.packet["context_id"].removeprefix(
        "mmctx_"
    )
    assert (tmp_path / receipt["object_key"]).read_bytes() == expected_body

    by_query = pit.FileAsKnownAtReader(tmp_path).read_stored_as_known_at(
        subject=packet["subject"],
        event_time=packet["clocks"]["event_time"],
        as_known_at=packet["clocks"]["as_known_at"],
    )
    by_context = pit.FileAsKnownAtReader(tmp_path).read_stored_context_id(
        packet["context_id"]
    )

    assert by_query == stored
    assert by_context == stored
    detached = by_query.response_payload()
    detached["context"]["authority"]["proposal_weight"] = 99
    assert (
        pit.FileAsKnownAtReader(tmp_path).read_as_known_at(
            subject=packet["subject"],
            event_time=packet["clocks"]["event_time"],
            as_known_at=packet["clocks"]["as_known_at"],
        )["authority"]["proposal_weight"]
        == 0
    )


def test_pinned_generation_reads_current_ancestor_and_rejects_crash_orphan(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _fixed_clock(monkeypatch)
    stored = pit.capture_context(tmp_path, _packet())
    reader = pit.FileAsKnownAtReader(tmp_path)
    current = reader.read_pinned_generation()
    state = pit._load_store_state(tmp_path)
    genesis_id = state.generation["previous_generation_id"]
    assert genesis_id is not None

    genesis = reader.read_pinned_generation(generation_id=genesis_id)
    assert genesis.captures == ()
    assert current.captures[0].as_dict() == pit._capture_entry(stored.capture_receipt)
    assert (
        reader.read_stored_from_pinned_generation(
            current, query_id=stored.capture_receipt["query_id"]
        )
        == stored
    )

    orphan = pit._new_generation(
        store_id=state.manifest["store_id"],
        previous_generation_id=current.generation_id,
        captures=[row.as_dict() for row in current.captures],
    )
    orphan_body = pit._canonical_bytes(orphan)
    pit._write_create_once(
        tmp_path,
        pit._generation_path(tmp_path, orphan["generation_id"]),
        orphan_body,
        label="test crash-orphan generation",
    )
    with pytest.raises(pit.MarketMemoryContextNotFound, match="not published"):
        reader.read_pinned_generation(generation_id=orphan["generation_id"])


def test_repeated_pin_rewalks_and_rejects_ancestor_tamper_under_same_head(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _fixed_clock(monkeypatch)
    pit.capture_context(tmp_path, _packet())
    reader = pit.FileAsKnownAtReader(tmp_path)
    pinned = reader.read_pinned_generation()
    state = pit._load_store_state(tmp_path)
    ancestor_id = state.generation["previous_generation_id"]
    assert ancestor_id is not None
    pit._generation_path(tmp_path, ancestor_id).unlink()

    assert pinned.generation_id == state.head["generation_id"]
    active = reader.read_active_generation()
    assert active.generation_id == state.head["generation_id"]
    assert len(active.captures) == 1
    with pytest.raises(pit.MarketMemoryStoreError, match="unavailable"):
        reader.read_pinned_generation()


@pytest.mark.parametrize("broken", ["nonempty_genesis", "missing_ancestor"])
def test_current_pin_requires_full_chain_through_empty_genesis(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, broken: str
) -> None:
    _fixed_clock(monkeypatch)
    pit.capture_context(tmp_path, _packet())
    state = pit._load_store_state(tmp_path)
    previous = None if broken == "nonempty_genesis" else "mmgeneration_" + "f" * 64
    forged = pit._new_generation(
        store_id=state.manifest["store_id"],
        previous_generation_id=previous,
        captures=state.generation["captures"],
    )
    body = pit._canonical_bytes(forged)
    pit._write_create_once(
        tmp_path,
        pit._generation_path(tmp_path, forged["generation_id"]),
        body,
        label="test broken current generation",
    )
    pit._replace_head(tmp_path, pit._new_head(forged, generation_body=body))

    message = "empty genesis" if broken == "nonempty_genesis" else "unavailable"
    with pytest.raises(pit.MarketMemoryStoreError, match=message):
        pit.FileAsKnownAtReader(tmp_path).read_pinned_generation()


def test_active_generation_ack_is_single_head_bounded_at_declared_cap(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    rows = []
    for index in range(pit._MAX_GENERATION_CAPTURES):
        digest = f"{index:064x}"
        rows.append(
            {
                "query_id": "mmquery_" + digest,
                "context_id": "mmctx_" + digest,
                "capture_id": "mmcapture_" + digest,
                "packet_sha256": digest,
            }
        )
    manifest = pit._new_store_manifest()
    generation = pit._new_generation(
        store_id=manifest["store_id"],
        previous_generation_id="mmgeneration_" + "b" * 64,
        captures=rows,
    )
    generation_body = pit._canonical_bytes(generation)
    assert len(generation_body) <= pit._MAX_GENERATION_BYTES
    pit._mkdir_durable(tmp_path)
    pit._write_create_once(
        tmp_path,
        pit._store_manifest_path(tmp_path),
        pit._canonical_bytes(manifest),
        label="cap store manifest",
    )
    pit._write_create_once(
        tmp_path,
        pit._generation_path(tmp_path, generation["generation_id"]),
        generation_body,
        label="cap store generation",
    )
    head = pit._new_head(generation, generation_body=generation_body)
    pit._replace_head(tmp_path, head)
    monkeypatch.setattr(
        pit,
        "_read_pinned_generation_from_state",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("active acknowledgement must not walk ancestry")
        ),
    )
    real_read = pit._read_canonical_object
    read_labels: list[str] = []

    def tracked_read(path, *, limit, label):
        read_labels.append(label)
        return real_read(path, limit=limit, label=label)

    monkeypatch.setattr(pit, "_read_canonical_object", tracked_read)

    active = pit.FileAsKnownAtReader(tmp_path).read_active_generation()

    assert active.generation_id == generation["generation_id"]
    assert active.generation_sha256 == head["generation_sha256"]
    assert len(active.captures) == pit._MAX_GENERATION_CAPTURES
    assert read_labels == [
        "Market Memory store manifest",
        "Market Memory store HEAD",
        "Market Memory store generation",
    ]


def test_pinned_generation_rejects_rewritten_append_history(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _fixed_clock(monkeypatch)
    pit.capture_context(tmp_path, _packet())
    monkeypatch.setattr(pit, "_utc_now", lambda: CUTOFF + timedelta(seconds=90))
    pit.capture_context(tmp_path, _later_packet(60))
    state = pit._load_store_state(tmp_path)
    first_generation_id = state.generation["previous_generation_id"]
    assert first_generation_id is not None
    first_generation, _body = pit._read_canonical_object(
        pit._generation_path(tmp_path, first_generation_id),
        limit=pit._MAX_GENERATION_BYTES,
        label="test first generation",
    )
    genesis_id = first_generation["previous_generation_id"]
    assert genesis_id is not None
    rewritten_entry = {
        "query_id": "mmquery_" + "1" * 64,
        "context_id": "mmctx_" + "2" * 64,
        "capture_id": "mmcapture_" + "3" * 64,
        "packet_sha256": "4" * 64,
    }
    rewritten = pit._new_generation(
        store_id=state.manifest["store_id"],
        previous_generation_id=genesis_id,
        captures=[rewritten_entry],
    )
    rewritten_body = pit._canonical_bytes(rewritten)
    pit._write_create_once(
        tmp_path,
        pit._generation_path(tmp_path, rewritten["generation_id"]),
        rewritten_body,
        label="test rewritten ancestor",
    )
    forged_head_generation = pit._new_generation(
        store_id=state.manifest["store_id"],
        previous_generation_id=rewritten["generation_id"],
        captures=state.generation["captures"],
    )
    forged_body = pit._canonical_bytes(forged_head_generation)
    pit._write_create_once(
        tmp_path,
        pit._generation_path(tmp_path, forged_head_generation["generation_id"]),
        forged_body,
        label="test rewritten head",
    )
    pit._replace_head(
        tmp_path,
        pit._new_head(forged_head_generation, generation_body=forged_body),
    )

    with pytest.raises(pit.MarketMemoryStoreError, match="rewrites"):
        pit.FileAsKnownAtReader(tmp_path).read_pinned_generation()


def test_pinned_generation_ancestry_has_aggregate_byte_and_cycle_bounds(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _fixed_clock(monkeypatch)
    pit.capture_context(tmp_path, _packet())
    monkeypatch.setattr(pit, "_MAX_PIN_ANCESTRY_BYTES", 1)
    with pytest.raises(pit.MarketMemoryStoreError, match="aggregate byte"):
        pit.FileAsKnownAtReader(tmp_path).read_pinned_generation()

    entry_a = {
        "query_id": "mmquery_" + "1" * 64,
        "context_id": "mmctx_" + "2" * 64,
        "capture_id": "mmcapture_" + "3" * 64,
        "packet_sha256": "4" * 64,
    }
    entry_b = {
        "query_id": "mmquery_" + "5" * 64,
        "context_id": "mmctx_" + "6" * 64,
        "capture_id": "mmcapture_" + "7" * 64,
        "packet_sha256": "8" * 64,
    }
    generation_a = {
        "generation_id": "mmgeneration_" + "a" * 64,
        "store_id": "mmstore_" + "9" * 64,
        "previous_generation_id": "mmgeneration_" + "b" * 64,
        "captures": [entry_a, entry_b],
    }
    generation_b = {
        "generation_id": "mmgeneration_" + "b" * 64,
        "store_id": generation_a["store_id"],
        "previous_generation_id": generation_a["generation_id"],
        "captures": [entry_a],
    }
    state = SimpleNamespace(
        manifest={"store_id": generation_a["store_id"]},
        head={
            "generation_id": generation_a["generation_id"],
            "generation_sha256": "c" * 64,
        },
        generation=generation_a,
    )
    monkeypatch.setattr(pit, "_MAX_PIN_ANCESTRY_BYTES", 1024 * 1024)
    monkeypatch.setattr(pit, "_validate_generation_link", lambda **_kwargs: None)
    monkeypatch.setattr(pit, "_validate_generation", lambda value, **_kwargs: value)
    monkeypatch.setattr(
        pit,
        "_read_canonical_object",
        lambda path, **_kwargs: (
            generation_b if "b" * 64 in str(path) else generation_a,
            b"{}",
        ),
    )
    with pytest.raises(pit.MarketMemoryStoreError, match="cycle"):
        pit._read_pinned_generation_from_state(
            tmp_path,
            state=state,
            profile=pit.STORE_PROFILE,
            generation_id="mmgeneration_" + "d" * 64,
        )


def test_pinned_receipt_rejects_cross_store_owner_even_when_index_matches(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _fixed_clock(monkeypatch)
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    pit.capture_context(first_root, _packet())
    second = pit.capture_context(second_root, _packet())
    first_state = pit._load_store_state(first_root)
    genesis_id = first_state.generation["previous_generation_id"]
    assert genesis_id is not None
    forged = pit._new_generation(
        store_id=first_state.manifest["store_id"],
        previous_generation_id=genesis_id,
        captures=[pit._capture_entry(second.capture_receipt)],
    )
    body = pit._canonical_bytes(forged)
    pit._write_create_once(
        first_root,
        pit._generation_path(first_root, forged["generation_id"]),
        body,
        label="test cross-owner generation",
    )
    pit._replace_head(first_root, pit._new_head(forged, generation_body=body))
    receipt_body = pit._canonical_bytes(second.capture_receipt)
    pit._query_path(first_root, second.capture_receipt["query_id"]).write_bytes(
        receipt_body
    )
    pit._context_path(first_root, second.capture_receipt["context_id"]).write_bytes(
        receipt_body
    )
    reader = pit.FileAsKnownAtReader(first_root)
    pinned = reader.read_pinned_generation()

    with pytest.raises(pit.MarketMemoryStoreError, match="another store"):
        reader.read_pinned_capture_receipt(
            pinned, query_id=second.capture_receipt["query_id"]
        )


def test_identical_retry_is_idempotent_even_when_process_clock_advances(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    packet = _packet()

    _fixed_clock(monkeypatch, CAPTURED_AT)
    first = pit.capture_context(tmp_path, packet)
    _fixed_clock(monkeypatch, CAPTURED_AT + timedelta(seconds=1))
    second = pit.capture_context(tmp_path, packet)

    assert second == first
    assert len(list(tmp_path.glob("objects/*/*.json"))) == 1
    assert len(list(tmp_path.glob("contexts/*/*.json"))) == 1
    assert len(list(tmp_path.glob("queries/*/*.json"))) == 1


def test_create_once_retry_reproves_parent_and_temp_unlink_is_durable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "store"
    parent = root / "objects" / "aa"
    pit._mkdir_durable(parent)
    path = parent / "artifact.json"
    body = b'{"value":1}'
    real_sync = pit._directory_fsync
    synced: list[Path] = []

    def track(directory: Path) -> None:
        real_sync(directory)
        synced.append(directory)

    monkeypatch.setattr(pit, "_directory_fsync", track)
    assert pit._write_create_once(root, path, body, label="fault artifact") is True
    assert synced.count(parent) >= 2
    assert not list(parent.glob(".*.tmp.*"))
    synced.clear()
    assert pit._write_create_once(root, path, body, label="fault artifact") is False
    assert parent in synced


def test_failed_head_root_fsync_retry_reproves_generation_and_root_before_ack(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _fixed_clock(monkeypatch)
    pit.capture_context(tmp_path, _packet())
    second = _later_packet(1)
    real_sync = pit._directory_fsync
    root_syncs = 0

    def fail_published_head_once(path: Path) -> None:
        nonlocal root_syncs
        if path == tmp_path:
            root_syncs += 1
            if root_syncs == 2:
                raise OSError("injected HEAD root fsync")
        real_sync(path)

    monkeypatch.setattr(pit, "_directory_fsync", fail_published_head_once)
    with pytest.raises(pit.MarketMemoryStoreError, match="advance.*HEAD"):
        pit.capture_context(tmp_path, second)

    synced: list[Path] = []

    def track(path: Path) -> None:
        real_sync(path)
        synced.append(path)

    monkeypatch.setattr(pit, "_directory_fsync", track)
    stored = pit.capture_context(tmp_path, second)
    state = pit._load_store_state(tmp_path)
    generation_parent = pit._generation_path(
        tmp_path, state.head["generation_id"]
    ).parent
    assert stored.packet["context_id"] == second["context_id"]
    assert generation_parent in synced
    assert tmp_path in synced
    assert len(state.generation["captures"]) == 2


def test_failed_head_replace_keeps_old_head_and_durably_cleans_temp(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _fixed_clock(monkeypatch)
    pit.capture_context(tmp_path, _packet())
    state = pit._load_store_state(tmp_path)
    original_head = (tmp_path / "HEAD.json").read_bytes()
    replacement = pit._new_head(
        state.generation,
        generation_body=pit._canonical_bytes(state.generation),
    )
    monkeypatch.setattr(
        pit.os,
        "replace",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            OSError("injected HEAD replace")
        ),
    )
    with pytest.raises(pit.MarketMemoryStoreError, match="advance.*HEAD"):
        pit._replace_head(tmp_path, replacement)
    assert (tmp_path / "HEAD.json").read_bytes() == original_head
    assert not list(tmp_path.glob(".HEAD.json.tmp.*"))


def test_capture_is_missing_only_and_explicitly_not_training_authoritative(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _fixed_clock(monkeypatch)

    stored = pit.capture_context(tmp_path, _packet())

    assert {row["status"] for row in stored.packet["feature_receipts"]} == {"missing"}
    assert stored.capture_receipt["evidence_policy"] == {
        "contract_validated": True,
        "source_artifacts_authenticated": False,
        "identity_artifacts_authenticated": False,
        "allowed_feature_status": "missing_only",
        "training_eligible": False,
        "promotion_eligible": False,
        "role": "context_only",
    }
    assert stored.packet["authority"]["context_only"] is True
    assert stored.packet["authority"]["proposal_weight"] == 0


def test_store_generation_proves_exact_absence_and_partial_store_is_unavailable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _fixed_clock(monkeypatch)
    packet = _packet()
    reader = pit.FileAsKnownAtReader(tmp_path)

    with pytest.raises(pit.MarketMemoryStoreError, match="manifest"):
        reader.read_as_known_at(
            subject=packet["subject"],
            event_time=packet["clocks"]["event_time"],
            as_known_at=packet["clocks"]["as_known_at"],
        )

    pit.capture_context(tmp_path, packet)
    with pytest.raises(pit.MarketMemoryContextNotFound, match="complete active"):
        reader.read_as_known_at(
            subject=packet["subject"],
            event_time=packet["clocks"]["event_time"],
            as_known_at="2026-08-07T20:05:01Z",
        )

    query_path = next(tmp_path.glob("queries/*/*.json"))
    query_path.unlink()
    with pytest.raises(pit.MarketMemoryStoreError, match="unavailable"):
        reader.read_stored_context_id(packet["context_id"])


def test_crash_after_receipts_before_head_is_not_visible_and_retry_recovers(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _fixed_clock(monkeypatch)
    packet = _packet()
    original_replace = pit._replace_head
    calls = 0

    def fail_second_head(root: Path, head: dict) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise pit.MarketMemoryStoreError("injected HEAD crash")
        original_replace(root, head)

    monkeypatch.setattr(pit, "_replace_head", fail_second_head)
    with pytest.raises(pit.MarketMemoryStoreError, match="HEAD crash"):
        pit.capture_context(tmp_path, packet)

    with pytest.raises(pit.MarketMemoryContextNotFound, match="complete active"):
        pit.FileAsKnownAtReader(tmp_path).read_stored_context_id(packet["context_id"])

    monkeypatch.setattr(pit, "_replace_head", original_replace)
    _fixed_clock(monkeypatch, CAPTURED_AT + timedelta(hours=2))
    recovered = pit.capture_context(tmp_path, packet)
    assert recovered.packet == packet
    assert len(pit._load_store_state(tmp_path).generation["captures"]) == 1


def test_retry_repairs_only_a_deterministic_empty_store_initialization(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _fixed_clock(monkeypatch)
    packet = _packet()
    original_write = pit._write_create_once
    injected = False

    def fail_empty_generation(
        root: Path, path: Path, body: bytes, *, label: str
    ) -> bool:
        nonlocal injected
        if label == "empty store generation" and not injected:
            injected = True
            raise pit.MarketMemoryStoreError("injected empty-init crash")
        return original_write(root, path, body, label=label)

    monkeypatch.setattr(pit, "_write_create_once", fail_empty_generation)
    with pytest.raises(pit.MarketMemoryStoreError, match="empty-init crash"):
        pit.capture_context(tmp_path, packet)
    assert (tmp_path / "store_manifest.json").is_file()
    assert not (tmp_path / "HEAD.json").exists()

    monkeypatch.setattr(pit, "_write_create_once", original_write)
    recovered = pit.capture_context(tmp_path, packet)
    assert recovered.packet == packet
    assert pit._load_store_state(tmp_path).generation["captures"]


def test_old_capture_remains_readable_after_current_registry_constants_advance(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _fixed_clock(monkeypatch)
    packet = _packet()
    pit.capture_context(tmp_path, packet)

    monkeypatch.setattr(
        mm, "FEATURE_REGISTRY_VERSION", "market_memory.feature_registry.future.v2"
    )
    monkeypatch.setattr(
        mm, "SOURCE_REGISTRY_VERSION", "market_memory.source_registry.future.v2"
    )

    assert (
        pit.FileAsKnownAtReader(tmp_path)
        .read_stored_context_id(packet["context_id"])
        .packet
        == packet
    )


@pytest.mark.parametrize("public_name", ["site", "site.served"])
def test_all_reader_writer_roots_reject_public_site_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, public_name: str
) -> None:
    _fixed_clock(monkeypatch)
    public_root = tmp_path / public_name / "market-memory"

    with pytest.raises(pit.MarketMemoryStoreError, match="site"):
        pit.FileAsKnownAtReader(public_root)
    with pytest.raises(pit.MarketMemoryStoreError, match="site"):
        pit.capture_context(public_root, _packet())
    with pytest.raises(pit.MarketMemoryStoreError, match="site"):
        pit.default_store_root(tmp_path / "repository" / public_name)


def test_production_api_mounts_pit_store_read_only_and_hides_writer_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MARKET_MEMORY_CONTEXT_STORE_DIR", raising=False)
    unit = (ROOT / "app" / "deploy" / "macro-api.service").read_text(encoding="utf-8")

    assert (
        "Environment=MARKET_MEMORY_CONTEXT_STORE_DIR="
        "/var/lib/macro-market-memory/public" in unit
    )
    assert "ReadOnlyPaths=/var/lib/macro-market-memory/public" in unit
    assert "InaccessiblePaths=/var/lib/macro-market-memory/state" in unit
    assert "InaccessiblePaths=-/var/lib/macro-market-memory/state" not in unit
    assert "InaccessiblePaths=-/etc/macro-market-memory.env" in unit
    assert (
        pit.default_store_root("/opt/macro")
        == Path("/var/lib/macro-market-memory/public").resolve()
    )
    update = (ROOT / "app" / "deploy" / "update.sh").read_text(encoding="utf-8")
    assert "install -d -m 0700 /var/lib/macro-market-memory/public" in update
    assert "install -d -m 0700 /var/lib/macro-market-memory/state" in update
    assert update.index(
        "install -d -m 0700 /var/lib/macro-market-memory/state"
    ) < update.index("API_UNIT_UPDATED=0")
    setup = (ROOT / "app" / "deploy" / "api-setup.sh").read_text(encoding="utf-8")
    assert "install -d -m 0700 /var/lib/macro-market-memory/public" in setup
    assert "install -d -m 0700 /var/lib/macro-market-memory/state" in setup
    assert setup.index(
        "install -d -m 0700 /var/lib/macro-market-memory/state"
    ) < setup.index("systemd-analyze verify")


def test_same_operational_query_cannot_publish_conflicting_packet(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _fixed_clock(monkeypatch)
    first = _packet()
    conflicting = _different_packet_for_same_query()
    assert conflicting["context_id"] != first["context_id"]

    pit.capture_context(tmp_path, first)
    with pytest.raises(
        pit.MarketMemoryCaptureError,
        match="already has a different immutable capture",
    ):
        pit.capture_context(tmp_path, conflicting)

    exact = pit.FileAsKnownAtReader(tmp_path).read_as_known_at(
        subject=first["subject"],
        event_time=first["clocks"]["event_time"],
        as_known_at=first["clocks"]["as_known_at"],
    )
    assert exact["context_id"] == first["context_id"]


def test_capture_rejects_backdated_operational_missingness(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # The capture is still within the packet-level 15-minute window, but its
    # source-free missing rows were last checked almost 20 minutes earlier.
    _fixed_clock(monkeypatch, CUTOFF + timedelta(minutes=14))

    with pytest.raises(
        pit.MarketMemoryCaptureError,
        match="missingness was not checked contemporaneously",
    ):
        pit.capture_context(tmp_path, _packet())
    assert not list(tmp_path.rglob("*.json"))


def test_capture_rejects_reconstruction_and_unbound_derived_snapshots(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _fixed_clock(monkeypatch)
    reconstructed = _rebuild(_packet(), mode="public_reconstruction")

    with pytest.raises(
        pit.MarketMemoryCaptureError,
        match="operational_pit packets only",
    ):
        pit.capture_context(tmp_path, reconstructed)
    with pytest.raises(
        pit.MarketMemoryCaptureError,
        match="trusted source adapters",
    ):
        pit.capture_context(tmp_path, _snapshot_packet())
    with pytest.raises(
        pit.MarketMemoryCaptureError,
        match="trusted source adapters",
    ):
        pit.capture_context(tmp_path, _valid_w0_packet())
    assert not list(tmp_path.rglob("*.json"))


def test_reader_rejects_date_only_future_and_reconstruction_queries(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _fixed_clock(monkeypatch)
    reader = pit.FileAsKnownAtReader(tmp_path)
    packet = _packet()

    with pytest.raises(pit.MarketMemoryQueryError, match="not a date-only"):
        reader.read_as_known_at(
            subject=packet["subject"],
            event_time="2026-08-07",
            as_known_at=packet["clocks"]["as_known_at"],
        )
    with pytest.raises(pit.MarketMemoryQueryError, match="cannot be in the future"):
        reader.read_as_known_at(
            subject=packet["subject"],
            event_time=packet["clocks"]["event_time"],
            as_known_at="2026-08-07T20:06:00Z",
        )
    with pytest.raises(pit.MarketMemoryQueryError, match="operational_pit"):
        pit.FileAsKnownAtReader(tmp_path, mode="public_reconstruction")


def test_exact_reader_never_falls_back_to_nearest_capture(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _fixed_clock(monkeypatch)
    packet = _packet()
    pit.capture_context(tmp_path, packet)

    with pytest.raises(pit.MarketMemoryContextNotFound):
        pit.FileAsKnownAtReader(tmp_path).read_as_known_at(
            subject=packet["subject"],
            event_time=packet["clocks"]["event_time"],
            as_known_at="2026-08-07T20:05:01Z",
        )


def test_reader_rejects_packet_and_receipt_tampering(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _fixed_clock(monkeypatch)
    packet = _packet()
    first = pit.capture_context(tmp_path / "packet-tamper", packet)
    packet_object = tmp_path / "packet-tamper" / first.capture_receipt["object_key"]
    packet_object.write_bytes(b"{}")

    with pytest.raises(pit.MarketMemoryStoreError, match="SHA-256 mismatch"):
        pit.FileAsKnownAtReader(tmp_path / "packet-tamper").read_stored_context_id(
            packet["context_id"]
        )

    second = pit.capture_context(tmp_path / "receipt-tamper", packet)
    receipt = deepcopy(second.capture_receipt)
    receipt["missing_feature_ids"] = receipt["missing_feature_ids"][:-1]
    body = pit._canonical_bytes(receipt)
    query_path = pit._query_path(tmp_path / "receipt-tamper", receipt["query_id"])
    context_path = pit._context_path(tmp_path / "receipt-tamper", receipt["context_id"])
    query_path.write_bytes(body)
    context_path.write_bytes(body)

    with pytest.raises(pit.MarketMemoryStoreError, match="capture_id"):
        pit.FileAsKnownAtReader(tmp_path / "receipt-tamper").read_stored_context_id(
            packet["context_id"]
        )


def test_crash_before_query_marker_never_partially_publishes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _fixed_clock(monkeypatch)
    packet = _packet()
    original_write = pit._write_create_once

    def crash_before_marker(root: Path, path: Path, body: bytes, *, label: str) -> bool:
        if label == "exact-query receipt":
            raise pit.MarketMemoryStoreError("injected publication crash")
        return original_write(root, path, body, label=label)

    monkeypatch.setattr(pit, "_write_create_once", crash_before_marker)
    with pytest.raises(pit.MarketMemoryStoreError, match="publication crash"):
        pit.capture_context(tmp_path, packet)

    reader = pit.FileAsKnownAtReader(tmp_path)
    with pytest.raises(pit.MarketMemoryContextNotFound):
        reader.read_stored_as_known_at(
            subject=packet["subject"],
            event_time=packet["clocks"]["event_time"],
            as_known_at=packet["clocks"]["as_known_at"],
        )
    with pytest.raises(pit.MarketMemoryContextNotFound):
        reader.read_stored_context_id(packet["context_id"])
    assert len(list(tmp_path.glob("objects/*/*.json"))) == 1
    assert len(list(tmp_path.glob("contexts/*/*.json"))) == 1
    assert not list(tmp_path.glob("queries/*/*.json"))


def test_api_exact_lookup_and_context_id_route_are_private_and_hash_bound(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _fixed_clock(monkeypatch)
    monkeypatch.setenv("MARKET_MEMORY_CONTEXT_STORE_DIR", str(tmp_path))
    _initialize_empty_trusted_api_store(monkeypatch, tmp_path)
    packet = _packet()
    stored = pit.capture_context(tmp_path, packet)
    client = _api_client()

    exact = client.get(_query_url(packet))
    by_id = client.get(f"/api/market-memory/v1/context/{packet['context_id']}")

    for response in (exact, by_id):
        assert response.status_code == 200
        _assert_private(response)
        assert response.json()["context"] == packet
        assert response.json()["capture_receipt"] == stored.capture_receipt
        assert response.headers["etag"] == (
            f'"{stored.capture_receipt["packet_sha256"]}"'
        )
        assert (
            response.headers["x-market-memory-capture-id"]
            == (stored.capture_receipt["capture_id"])
        )


def test_api_has_no_nearest_or_reconstruction_fallback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _fixed_clock(monkeypatch)
    monkeypatch.setenv("MARKET_MEMORY_CONTEXT_STORE_DIR", str(tmp_path))
    _initialize_empty_trusted_api_store(monkeypatch, tmp_path)
    packet = _packet()
    pit.capture_context(tmp_path, packet)
    client = _api_client()

    nearest = client.get(_query_url(packet, as_known_at="2026-08-07T20:05:01Z"))
    reconstruction = client.get(_query_url(packet, mode="public_reconstruction"))
    future = client.get(_query_url(packet, as_known_at="2026-08-07T20:06:00Z"))
    date_only = client.get(_query_url(packet, event_time="2026-08-07"))

    assert nearest.status_code == 404
    assert "exact" in nearest.json()["detail"].lower()
    assert reconstruction.status_code == 400
    assert "operational_pit" in reconstruction.json()["detail"]
    assert future.status_code == 400
    assert "future" in future.json()["detail"]
    assert date_only.status_code == 400
    assert "date-only" in date_only.json()["detail"]
    for response in (nearest, reconstruction, future, date_only):
        _assert_private(response)


@pytest.mark.parametrize("status", [401, 403])
@pytest.mark.parametrize("route", ["query", "context"])
def test_api_auth_fails_before_store_access_and_is_private(
    monkeypatch: pytest.MonkeyPatch, status: int, route: str
) -> None:
    packet = _packet()

    def forbidden_store_access():
        raise AssertionError("store must not be constructed before entitlement")

    monkeypatch.setattr(api, "_pit_reader", forbidden_store_access)
    url = (
        _query_url(packet)
        if route == "query"
        else f"/api/market-memory/v1/context/{packet['context_id']}"
    )

    response = _api_client(denied_status=status).get(url)

    assert response.status_code == status
    _assert_private(response)


def test_api_context_rate_limit_is_private_and_precedes_second_store_read(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _fixed_clock(monkeypatch)
    monkeypatch.setenv("MARKET_MEMORY_CONTEXT_STORE_DIR", str(tmp_path))
    _initialize_empty_trusted_api_store(monkeypatch, tmp_path)
    monkeypatch.setattr(api, "_SYMBOL_USER_LIMIT", 1)
    monkeypatch.setattr(api, "_SYMBOL_PEER_LIMIT", 10)
    packet = _packet()
    pit.capture_context(tmp_path, packet)
    client = _api_client()

    assert client.get(_query_url(packet)).status_code == 200
    blocked = client.get(f"/api/market-memory/v1/context/{packet['context_id']}")

    assert blocked.status_code == 429
    assert blocked.headers["retry-after"] == "60"
    _assert_private(blocked)


def test_api_store_failure_is_coarsened_private_and_retryable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet = _packet()

    class BrokenReader:
        mode = "operational_pit"

        def read_stored_as_known_at(self, **_kwargs):
            raise pit.MarketMemoryStoreError("sensitive internal path")

    monkeypatch.setattr(api, "_pit_reader", BrokenReader)
    response = _api_client().get(_query_url(packet))

    assert response.status_code == 503
    assert "sensitive internal path" not in response.text
    assert response.headers["retry-after"] == str(api._SYMBOL_FETCH_BUSY_RETRY_SECONDS)
    _assert_private(response)


def test_api_absent_store_is_unavailable_not_a_false_exact_miss(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _fixed_clock(monkeypatch)
    monkeypatch.setenv("MARKET_MEMORY_CONTEXT_STORE_DIR", str(tmp_path))

    response = _api_client().get(_query_url(_packet()))

    assert response.status_code == 503
    assert response.headers["retry-after"] == str(api._SYMBOL_FETCH_BUSY_RETRY_SECONDS)
    _assert_private(response)


def test_capture_context_has_one_production_writer_and_api_is_read_only() -> None:
    production_roots = (ROOT / "app", ROOT / "engine", ROOT / "scripts")
    callers: set[str] = set()
    for production_root in production_roots:
        for path in production_root.rglob("*.py"):
            if "capture_context(" in path.read_text(encoding="utf-8"):
                callers.add(path.relative_to(ROOT).as_posix())

    assert callers == {
        "engine/neuralweb/market_memory_pit.py",
        "scripts/capture_market_memory_context.py",
    }

    pit_routes = {
        route.path: route.methods
        for route in api.router.routes
        if route.path.startswith("/api/market-memory/v1/as-known-at")
        or route.path.startswith("/api/market-memory/v1/context/")
        or route.path.startswith("/api/market-memory/v1/playback/catalog")
    }
    assert pit_routes
    assert all(methods == {"GET"} for methods in pit_routes.values())


def test_w1a_production_files_do_not_cross_options_episode_ownership() -> None:
    targets = (
        ROOT / "engine" / "neuralweb" / "market_memory_pit.py",
        ROOT / "scripts" / "capture_market_memory_context.py",
        ROOT / "app" / "market_memory.py",
    )
    forbidden = (
        "engine.options_signal_episode",
        "options_signal_episode",
        "options.signal_episode",
        "outcomes_h60",
        "session_outcomes",
        "append_episodes(",
        "append_outcomes(",
        "derive_h60_outcome(",
        "u-chain",
        "u_chain",
    )

    violations = {
        path.relative_to(ROOT).as_posix(): token
        for path in targets
        for token in forbidden
        if token in path.read_text(encoding="utf-8").lower()
    }
    assert violations == {}


def _schema(name: str) -> dict:
    path = ROOT / "contracts" / "market_memory" / name
    assert path.is_file(), f"missing Market Memory contract: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


def test_as_known_at_json_schema_matches_frozen_packet_and_authority() -> None:
    schema = _schema("as_known_at.v1.schema.json")
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    packet = _packet()

    validator.validate(packet)
    drifted = deepcopy(packet)
    drifted["authority"]["proposal_weight"] = 1
    with pytest.raises(ValidationError):
        validator.validate(drifted)
