"""Focused hostile-input contracts for the bounded B4 history receipt reader."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
from hashlib import sha256
from pathlib import Path
import sys
import threading

import pytest

import engine.fundamental_forensics.attested_query_snapshots as attested_snapshots
from engine.fundamental_forensics.attested_query_snapshots import (
    AttestedQuerySnapshotError,
    load_attested_query_receipt_index,
    publish_attested_query_snapshot,
    reset_attested_query_receipt_index_cache,
)


ROOT = Path(__file__).resolve().parents[1]


def _b4_helpers():
    """Reuse B4's real sealed-fixture construction, not a fake receipt shape."""
    path = ROOT / "tests" / "test_fundamental_forensics_attested_query_snapshots.py"
    spec = importlib.util.spec_from_file_location("_b4_receipt_reader_fixture_helpers", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def _clear_receipt_index_cache():
    reset_attested_query_receipt_index_cache()
    yield
    reset_attested_query_receipt_index_cache()


def _published(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    helper = _b4_helpers()
    store, _base, material, conversion, _binding, prepared = helper._prepared(monkeypatch, tmp_path)
    snapshot = publish_attested_query_snapshot(
        store,
        prepared,
        attestation_materials=(material,),
        companyfacts_conversion=conversion,
    )
    return store, snapshot


class _ReceiptReadTrace:
    """Cap-only public-store proxy; record the complete serving read set."""

    def __init__(self, inner):
        self.inner = inner
        self.calls: list[str] = []
        self.bounded_calls: list[tuple[str, int]] = []

    def get_bytes(self, key):
        return self.inner.get_bytes(key)

    def get_bytes_strict(self, key):
        del key
        raise AssertionError("receipt reader must never invoke legacy strict reads")

    def get_bytes_strict_bounded(self, key, maximum_bytes):
        self.calls.append(key)
        self.bounded_calls.append((key, maximum_bytes))
        return self.inner.get_bytes_strict_bounded(key, maximum_bytes)

    def put_bytes(self, key, data, content_type="application/octet-stream"):
        return self.inner.put_bytes(key, data, content_type)

    def list_prefix(self, prefix):
        return self.inner.list_prefix(prefix)

    def exists(self, key):
        return self.inner.exists(key)

    def upload_time(self, key):
        return self.inner.upload_time(key)


def test_receipt_reader_reads_only_pointer_manifest_bindings_and_coverage(monkeypatch, tmp_path):
    store, snapshot = _published(monkeypatch, tmp_path)
    artifacts = {item["role"]: item for item in snapshot.manifest["objects"]}
    proxy = _ReceiptReadTrace(store)

    index = load_attested_query_receipt_index(proxy)

    assert index.snapshot_id == snapshot.snapshot_id
    assert index.base_snapshot_id == snapshot.base_snapshot_id
    assert index.query_hash == snapshot.manifest["base_snapshot"]["query_hash"]
    assert proxy.calls == [
        attested_snapshots._latest_key(),
        snapshot.manifest_key,
        artifacts["bindings_json"]["object_key"],
        artifacts["coverage_json"]["object_key"],
    ]
    assert proxy.bounded_calls[-2:] == [
        (artifacts["bindings_json"]["object_key"], artifacts["bindings_json"]["byte_length"]),
        (artifacts["coverage_json"]["object_key"], artifacts["coverage_json"]["byte_length"]),
    ]
    assert all("query-snapshots/v1" not in key for key in proxy.calls)
    assert artifacts["attestations_json"]["object_key"] not in set(proxy.calls)
    assert artifacts["companyfacts_conversion_json"]["object_key"] not in set(proxy.calls)
    with pytest.raises(TypeError):
        index.manifest["nonclaims"]["trading_authority"] = True
    with pytest.raises(TypeError):
        index.roots[0]["status"] = "all_leaves_attested"
    assert index.root_ids == tuple(root["root_cell_id"] for root in index.roots)
    assert tuple(index.roots_by_id) == index.root_ids
    with pytest.raises(TypeError):
        index.roots_by_id[index.root_ids[0]] = index.roots[0]
    with pytest.raises(TypeError):
        index.bindings_by_occurrence["forged"] = {}
    with pytest.raises(TypeError):
        index.attestations_by_id["forged"] = {}

    # Latest always re-reads the independent pointer and canonical manifest,
    # even when the immutable compact payload index itself is a cache hit.
    proxy.calls.clear()
    proxy.bounded_calls.clear()
    assert load_attested_query_receipt_index(proxy).snapshot_id == snapshot.snapshot_id
    assert proxy.calls == [
        attested_snapshots._latest_key(),
        snapshot.manifest_key,
        artifacts["bindings_json"]["object_key"],
        artifacts["coverage_json"]["object_key"],
    ]
    assert len(proxy.bounded_calls) == 4

    reset_attested_query_receipt_index_cache()
    proxy.calls.clear()
    proxy.bounded_calls.clear()
    assert load_attested_query_receipt_index(proxy, snapshot_id=snapshot.snapshot_id).snapshot_id == snapshot.snapshot_id
    assert proxy.calls == [
        snapshot.manifest_key,
        artifacts["bindings_json"]["object_key"],
        artifacts["coverage_json"]["object_key"],
    ]


def test_receipt_reader_preserves_real_partial_and_non_evaluable_coverage(monkeypatch, tmp_path):
    helper = _b4_helpers()
    store, base, material, conversion, prepared = helper._mixed_coverage_prepared(monkeypatch, tmp_path)
    snapshot = publish_attested_query_snapshot(
        store,
        prepared,
        attestation_materials=(material,),
        companyfacts_conversion=conversion,
    )

    index = load_attested_query_receipt_index(store, snapshot_id=snapshot.snapshot_id)
    root_by_metric = {cell.metric_id: cell.cell_id for cell in base.matrix.cells}
    assert {root["root_cell_id"]: root["status"] for root in index.roots} == {
        root_by_metric["gross_margin"]: "partially_attested",
        root_by_metric["revenue"]: "all_leaves_attested",
        root_by_metric["gross_profit"]: "not_attested",
        root_by_metric["net_income_loss"]: "not_evaluable",
    }
    assert index.manifest["coverage_summary"] == snapshot.manifest["coverage_summary"]
    assert set(index.bindings_by_occurrence) == {
        occurrence_id
        for root in index.roots
        for occurrence_id in root["attested_occurrence_ids"]
    }
    assert set(index.attestations_by_id) == {
        binding["attestation_id"] for binding in index.bindings_by_occurrence.values()
    }


def _forge_snapshot_with_payload(
    store,
    snapshot,
    *,
    role: str,
    payload: bytes,
    declared_byte_length: int | None = None,
) -> str:
    """Construct a content-addressed but reader-hostile receipt variant."""
    manifest = attested_snapshots._thaw(snapshot.manifest)
    digest = sha256(payload).hexdigest()
    for artifact in manifest["objects"]:
        if artifact["role"] == role:
            artifact.update(
                object_key=attested_snapshots._object_key(digest),
                sha256=digest,
                byte_length=len(payload) if declared_byte_length is None else declared_byte_length,
            )
            break
    else:  # pragma: no cover - fixture is an actual B4 receipt.
        raise AssertionError(f"missing artifact role: {role}")
    body = dict(manifest)
    body.pop("snapshot_id")
    snapshot_id = attested_snapshots._identity(body)
    manifest["snapshot_id"] = snapshot_id
    manifest_payload = attested_snapshots._manifest_bytes(manifest)
    artifact = next(item for item in manifest["objects"] if item["role"] == role)
    assert store.put_bytes(artifact["object_key"], payload, content_type="application/json") is True
    assert store.put_bytes(
        attested_snapshots._manifest_key(snapshot_id),
        manifest_payload,
        content_type="application/json",
    ) is True
    return snapshot_id


def test_receipt_reader_rejects_digest_noncanonical_and_crosswired_payloads(monkeypatch, tmp_path):
    store, snapshot = _published(monkeypatch, tmp_path)
    bindings_artifact = next(item for item in snapshot.manifest["objects"] if item["role"] == "bindings_json")

    # An in-place mutable-store corruption fails before any JSON interpretation.
    assert store.put_bytes(bindings_artifact["object_key"], b"{}", content_type="application/json") is True
    with pytest.raises(AttestedQuerySnapshotError, match="exact bounded read contract"):
        load_attested_query_receipt_index(store, snapshot_id=snapshot.snapshot_id)

    # Restore a real receipt for content-addressed variants below.
    store, snapshot = _published(monkeypatch, tmp_path / "variants")
    bindings_artifact = next(item for item in snapshot.manifest["objects"] if item["role"] == "bindings_json")
    parsed = json.loads(store.get_bytes_strict(bindings_artifact["object_key"]))
    noncanonical = json.dumps(
        {"schema": parsed["schema"], "items": parsed["items"]},
        separators=(",", ":"),
        sort_keys=False,
    ).encode("utf-8")
    noncanonical_id = _forge_snapshot_with_payload(
        store,
        snapshot,
        role="bindings_json",
        payload=noncanonical,
    )
    with pytest.raises(AttestedQuerySnapshotError, match="bindings payload is not canonical"):
        load_attested_query_receipt_index(store, snapshot_id=noncanonical_id)

    parsed["items"][0]["companyfacts"]["cik"] = "0000000002"
    crosswired_payload = attested_snapshots._binding_payload(parsed["items"])
    crosswired_id = _forge_snapshot_with_payload(
        store,
        snapshot,
        role="bindings_json",
        payload=crosswired_payload,
    )
    with pytest.raises(AttestedQuerySnapshotError, match="does not bind manifest Company Facts identity"):
        load_attested_query_receipt_index(store, snapshot_id=crosswired_id)

    coverage_artifact = next(item for item in snapshot.manifest["objects"] if item["role"] == "coverage_json")
    coverage = json.loads(store.get_bytes_strict(coverage_artifact["object_key"]))
    coverage["items"][0]["status"] = "not_attested"
    bad_status_id = _forge_snapshot_with_payload(
        store,
        snapshot,
        role="coverage_json",
        payload=attested_snapshots._coverage_payload(coverage["items"]),
    )
    with pytest.raises(AttestedQuerySnapshotError, match="status is invalid"):
        load_attested_query_receipt_index(store, snapshot_id=bad_status_id)

    coverage = json.loads(store.get_bytes_strict(coverage_artifact["object_key"]))
    coverage["items"].append(coverage["items"][0])
    duplicate_root_id = _forge_snapshot_with_payload(
        store,
        snapshot,
        role="coverage_json",
        payload=attested_snapshots._coverage_payload(coverage["items"]),
    )
    with pytest.raises(AttestedQuerySnapshotError, match="uniquely canonical"):
        load_attested_query_receipt_index(store, snapshot_id=duplicate_root_id)


def test_warmed_latest_cache_never_masks_a_corrupt_pointer_or_manifest(monkeypatch, tmp_path):
    store, snapshot = _published(monkeypatch, tmp_path)
    assert load_attested_query_receipt_index(store).snapshot_id == snapshot.snapshot_id
    assert store.put_bytes(snapshot.manifest_key, b"{}", content_type="application/json") is True
    with pytest.raises(AttestedQuerySnapshotError, match="manifest"):
        load_attested_query_receipt_index(store)

    store, snapshot = _published(monkeypatch, tmp_path / "pointer")
    assert load_attested_query_receipt_index(store).snapshot_id == snapshot.snapshot_id
    assert store.put_bytes(attested_snapshots._latest_key(), b"{}", content_type="application/json") is True
    with pytest.raises(AttestedQuerySnapshotError, match="pointer"):
        load_attested_query_receipt_index(store)


@pytest.mark.parametrize(("role", "latest"), [
    ("bindings_json", True),
    ("coverage_json", True),
    ("bindings_json", False),
    ("coverage_json", False),
])
def test_warmed_cache_never_masks_compact_artifact_corruption(monkeypatch, tmp_path, role, latest):
    store, snapshot = _published(monkeypatch, tmp_path / f"{role}-{latest}")
    kwargs = {} if latest else {"snapshot_id": snapshot.snapshot_id}
    assert load_attested_query_receipt_index(store, **kwargs).snapshot_id == snapshot.snapshot_id
    artifact = next(item for item in snapshot.manifest["objects"] if item["role"] == role)
    assert store.put_bytes(artifact["object_key"], b"{}", content_type="application/json") is True
    with pytest.raises(AttestedQuerySnapshotError, match="exact bounded read contract"):
        load_attested_query_receipt_index(store, **kwargs)


def test_reader_uses_cap_only_public_store_with_declared_length_before_payload_parsing(monkeypatch, tmp_path):
    store, snapshot = _published(monkeypatch, tmp_path)
    forged_id = _forge_snapshot_with_payload(
        store,
        snapshot,
        role="bindings_json",
        payload=b"x",
        declared_byte_length=0,
    )
    proxy = _ReceiptReadTrace(store)
    with pytest.raises(AttestedQuerySnapshotError, match="strict bounded read failed"):
        load_attested_query_receipt_index(proxy, snapshot_id=forged_id)
    assert proxy.bounded_calls == [
        (
            attested_snapshots._manifest_key(forged_id),
            attested_snapshots.HARD_MAX_ATTESTED_SNAPSHOT_MANIFEST_BYTES,
        ),
        (
            attested_snapshots._object_key(sha256(b"x").hexdigest()),
            0,
        ),
    ]


def test_reader_refuses_compact_artifact_budget_before_any_compact_read(monkeypatch, tmp_path):
    store, snapshot = _published(monkeypatch, tmp_path)
    forged_id = _forge_snapshot_with_payload(
        store,
        snapshot,
        role="bindings_json",
        payload=b"x",
        declared_byte_length=attested_snapshots.HARD_MAX_ATTESTED_RECEIPT_COMPACT_BYTES + 1,
    )
    proxy = _ReceiptReadTrace(store)

    with pytest.raises(AttestedQuerySnapshotError, match="compact artifacts exceed serving byte budget"):
        load_attested_query_receipt_index(proxy, snapshot_id=forged_id)

    assert proxy.calls == [attested_snapshots._manifest_key(forged_id)]


def test_reader_refuses_decoded_index_over_hard_budget_without_caching(monkeypatch, tmp_path):
    store, snapshot = _published(monkeypatch, tmp_path)
    monkeypatch.setattr(attested_snapshots, "HARD_MAX_ATTESTED_RECEIPT_DECODED_INDEX_BYTES", 1)

    with pytest.raises(AttestedQuerySnapshotError, match="decoded index exceeds serving budget"):
        load_attested_query_receipt_index(store, snapshot_id=snapshot.snapshot_id)

    assert not attested_snapshots._RECEIPT_INDEX_CACHE
    assert attested_snapshots._RECEIPT_INDEX_CACHE_BYTES == 0


def test_concurrent_cold_loads_share_one_compact_download_and_parse(monkeypatch, tmp_path):
    store, snapshot = _published(monkeypatch, tmp_path)
    artifacts = {item["role"]: item for item in snapshot.manifest["objects"]}
    binding_key = artifacts["bindings_json"]["object_key"]
    coverage_key = artifacts["coverage_json"]["object_key"]
    entered_compact_read = threading.Event()
    release_compact_read = threading.Event()
    follower_waiting = threading.Event()
    parsed: list[object] = []

    class BlockingCapOnlyTrace(_ReceiptReadTrace):
        def get_bytes_strict_bounded(self, key, maximum_bytes):
            self.calls.append(key)
            self.bounded_calls.append((key, maximum_bytes))
            if key == binding_key and not entered_compact_read.is_set():
                entered_compact_read.set()
                assert release_compact_read.wait(timeout=5)
            return self.inner.get_bytes_strict_bounded(key, maximum_bytes)

    proxy = BlockingCapOnlyTrace(store)
    stripe = attested_snapshots._ReceiptIndexFlightStripe(lock=threading.RLock())
    original_parse = attested_snapshots._receipt_index_from_manifest
    original_event = attested_snapshots.Event

    class TrackingEvent:
        def __init__(self):
            self.inner = original_event()

        def set(self):
            self.inner.set()

        def wait(self, timeout=None):
            follower_waiting.set()
            return self.inner.wait(timeout)

    def count_parse(*args, **kwargs):
        parsed.append(object())
        return original_parse(*args, **kwargs)

    monkeypatch.setattr(attested_snapshots, "_receipt_singleflight_stripe", lambda _store, *, snapshot_id: stripe)
    monkeypatch.setattr(attested_snapshots, "_receipt_index_from_manifest", count_parse)
    monkeypatch.setattr(attested_snapshots, "Event", TrackingEvent)
    # The follower must receive its leader's active-flight result, not merely
    # discover an LRU entry after the leader happened to cache it.
    monkeypatch.setattr(attested_snapshots, "_RECEIPT_INDEX_CACHE_MAX_BYTES", 0)
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(
            load_attested_query_receipt_index,
            proxy,
            snapshot_id=snapshot.snapshot_id,
        )
        assert entered_compact_read.wait(timeout=5)
        second = executor.submit(
            load_attested_query_receipt_index,
            proxy,
            snapshot_id=snapshot.snapshot_id,
        )
        assert follower_waiting.wait(timeout=5)
        release_compact_read.set()
        first_index = first.result(timeout=5)
        second_index = second.result(timeout=5)

    assert first_index is second_index
    assert len(parsed) == 1
    assert proxy.calls.count(binding_key) == 1
    assert proxy.calls.count(coverage_key) == 1


def test_oversized_receipt_index_bypasses_the_bounded_cache(monkeypatch, tmp_path):
    store, snapshot = _published(monkeypatch, tmp_path)
    proxy = _ReceiptReadTrace(store)
    monkeypatch.setattr(attested_snapshots, "_RECEIPT_INDEX_CACHE_MAX_BYTES", 1)

    assert load_attested_query_receipt_index(proxy, snapshot_id=snapshot.snapshot_id).snapshot_id == snapshot.snapshot_id
    first_read_set = list(proxy.calls)
    proxy.calls.clear()
    assert load_attested_query_receipt_index(proxy, snapshot_id=snapshot.snapshot_id).snapshot_id == snapshot.snapshot_id
    assert proxy.calls == first_read_set
    assert len(first_read_set) == 3
