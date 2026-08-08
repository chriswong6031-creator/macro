from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
from hashlib import sha256
from types import MappingProxyType

import pytest

import engine.fundamental_forensics.source_sync as source_sync_mod
from engine.fundamental_forensics.source_sync import (
    SOURCE_SYNC_PREFIX,
    SourceObjectWitness,
    SourceSyncError,
    VerifiedSourceSnapshot,
    load_pinned_source_snapshot_strict,
    read_pinned_source_snapshot_file_strict,
    restore_source_roots,
    source_object_key_for_sha256,
    sync_source_roots,
)
from engine.fundamental_forensics.models import canonical_json
from engine.research_vault.r2_store import LocalStore


SNAPSHOT_AT = "2026-08-01T12:00:00Z"


def _roots(tmp_path: Path) -> tuple[Path, Path]:
    raw = tmp_path / "raw"
    archive = tmp_path / "archive"
    (raw / "0000000001" / "submissions").mkdir(parents=True)
    (raw / "0000000001" / "submissions" / "latest.json").write_bytes(b'{"sha256":"a"}')
    (raw / "0000000001" / "submissions" / "a.json.gz").write_bytes(b"compressed-submissions")
    (archive / "objects" / "sha256" / "ab").mkdir(parents=True)
    (archive / "objects" / "sha256" / "ab" / "abcdef.bin.gz").write_bytes(b"archive-source")
    (archive / "manifests" / "0000000001" / "0000000001-26-000001").mkdir(parents=True)
    (archive / "manifests" / "0000000001" / "0000000001-26-000001" / "manifest.json").write_bytes(
        b'{"manifest":"fixture"}'
    )
    return raw, archive


class _ConditionalProxy:
    """Expose CAS writes while making any legacy overwrite a test failure."""

    def __init__(self, inner: LocalStore) -> None:
        self.inner = inner
        self.conditional_calls: list[tuple[str, bytes, str | None, str]] = []
        self.unconditional_put_calls = 0

    def get_bytes(self, key: str):
        return self.inner.get_bytes(key)

    def get_bytes_strict(self, key: str):
        return self.inner.get_bytes_strict(key)

    def get_bytes_strict_bounded(self, key: str, maximum_bytes: int):
        return self.inner.get_bytes_strict_bounded(key, maximum_bytes)

    def get_bytes_strict_bounded_versioned(self, key: str, maximum_bytes: int):
        return self.inner.get_bytes_strict_bounded_versioned(key, maximum_bytes)

    def validate_strict_conditional_write_capability(self):
        return self.inner.validate_strict_conditional_write_capability()

    def put_bytes_strict_conditional(
        self,
        key: str,
        data: bytes,
        *,
        expected_version: str | None,
        content_type: str = "application/octet-stream",
    ):
        self.conditional_calls.append((key, data, expected_version, content_type))
        return self.inner.put_bytes_strict_conditional(
            key,
            data,
            expected_version=expected_version,
            content_type=content_type,
        )

    def put_bytes(self, key: str, data: bytes, content_type: str = "application/octet-stream"):
        del key, data, content_type
        self.unconditional_put_calls += 1
        raise AssertionError("source sync must not invoke legacy put_bytes")

    def list_prefix(self, prefix: str):
        return self.inner.list_prefix(prefix)

    def exists(self, key: str):
        return self.inner.exists(key)

    def upload_time(self, key: str):
        return self.inner.upload_time(key)


class _AmbiguousImmutableCreateProxy(_ConditionalProxy):
    """Commit one create then surface an ambiguous response to the caller."""

    def __init__(self, inner: LocalStore, *, target_key: str, result: bool | Exception) -> None:
        super().__init__(inner)
        self.target_key = target_key
        self.result = result
        self.triggered = False

    def put_bytes_strict_conditional(self, key, data, *, expected_version, content_type="application/octet-stream"):
        self.conditional_calls.append((key, data, expected_version, content_type))
        if key == self.target_key and not self.triggered:
            assert expected_version is None
            assert self.inner.put_bytes_strict_conditional(
                key,
                data,
                expected_version=expected_version,
                content_type=content_type,
            ) is True
            self.triggered = True
            if isinstance(self.result, Exception):
                raise self.result
            return self.result
        return self.inner.put_bytes_strict_conditional(
            key,
            data,
            expected_version=expected_version,
            content_type=content_type,
        )


class _ReadOnlyStrictProxy:
    """Legacy strict adapter shape without the required conditional writer."""

    def __init__(self, inner: LocalStore) -> None:
        self.inner = inner
        self.put_calls = 0

    def get_bytes(self, key: str):
        return self.inner.get_bytes(key)

    def get_bytes_strict(self, key: str):
        return self.inner.get_bytes_strict(key)

    def get_bytes_strict_bounded(self, key: str, maximum_bytes: int):
        return self.inner.get_bytes_strict_bounded(key, maximum_bytes)

    def put_bytes(self, key: str, data: bytes, content_type: str = "application/octet-stream"):
        del key, data, content_type
        self.put_calls += 1
        return False

    def list_prefix(self, prefix: str):
        return self.inner.list_prefix(prefix)

    def exists(self, key: str):
        return self.inner.exists(key)

    def upload_time(self, key: str):
        return self.inner.upload_time(key)


def test_private_source_sync_round_trips_exact_raw_and_archive_trees(tmp_path: Path):
    raw, archive = _roots(tmp_path)
    source_copy = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in sorted(tmp_path.rglob("*"))
        if path.is_file()
    }
    store = LocalStore(tmp_path / "private-store")

    snapshot = sync_source_roots(
        raw_root=raw,
        archive_root=archive,
        store=store,
        snapshot_at=SNAPSHOT_AT,
    )

    assert snapshot.file_count == len(source_copy)
    assert snapshot.total_bytes == sum(len(value) for value in source_copy.values())
    assert snapshot.manifest_key.startswith(f"{SOURCE_SYNC_PREFIX}/manifests/")
    assert store.get_bytes(f"{SOURCE_SYNC_PREFIX}/latest.json") is not None

    shutil.rmtree(raw)
    shutil.rmtree(archive)
    restored = restore_source_roots(raw_root=raw, archive_root=archive, store=store)
    assert restored.snapshot == snapshot
    assert restored.restored_files == len(source_copy)
    assert restored.current_files == 0
    for relative, content in source_copy.items():
        assert (tmp_path / relative).read_bytes() == content

    current = restore_source_roots(raw_root=raw, archive_root=archive, store=store)
    assert current.restored_files == 0
    assert current.current_files == len(source_copy)


def test_source_sync_uses_only_create_cas_and_never_legacy_put(tmp_path: Path):
    raw, archive = _roots(tmp_path)
    inner = LocalStore(tmp_path / "private-store")
    store = _ConditionalProxy(inner)

    snapshot = sync_source_roots(
        raw_root=raw,
        archive_root=archive,
        store=store,
        snapshot_at=SNAPSHOT_AT,
    )

    manifest = json.loads(inner.get_bytes(snapshot.manifest_key) or b"{}")
    immutable_keys = [
        entry["object_key"]
        for tree in manifest["trees"]
        for entry in tree["entries"]
    ] + [snapshot.manifest_key]
    assert [call[0] for call in store.conditional_calls] == immutable_keys + [
        f"{SOURCE_SYNC_PREFIX}/latest.json"
    ]
    assert all(call[2] is None for call in store.conditional_calls)
    assert store.unconditional_put_calls == 0


def test_source_sync_rejects_legacy_store_before_any_write(tmp_path: Path):
    raw, archive = _roots(tmp_path)
    inner = LocalStore(tmp_path / "private-store")
    legacy = _ReadOnlyStrictProxy(inner)

    with pytest.raises(SourceSyncError, match="StrictConditionalWriteStore"):
        sync_source_roots(
            raw_root=raw,
            archive_root=archive,
            store=legacy,
            snapshot_at=SNAPSHOT_AT,
        )

    assert legacy.put_calls == 0
    assert inner.list_prefix(SOURCE_SYNC_PREFIX) == []


def test_source_sync_reconciles_ambiguous_immutable_create_by_exact_readback(tmp_path: Path):
    raw, archive = _roots(tmp_path)
    target = raw / "0000000001" / "submissions" / "latest.json"
    digest = sha256(target.read_bytes()).hexdigest()
    key = f"{SOURCE_SYNC_PREFIX}/objects/sha256/{digest[:2]}/{digest}.bin"
    inner = LocalStore(tmp_path / "private-store")
    store = _AmbiguousImmutableCreateProxy(
        inner,
        target_key=key,
        result=TimeoutError("conditional create acknowledgement lost"),
    )

    snapshot = sync_source_roots(
        raw_root=raw,
        archive_root=archive,
        store=store,
        snapshot_at=SNAPSHOT_AT,
    )

    assert store.triggered
    assert inner.get_bytes(snapshot.manifest_key) is not None
    assert store.unconditional_put_calls == 0


def test_source_sync_rejects_immutable_collision_without_overwrite(tmp_path: Path):
    raw, archive = _roots(tmp_path)
    target = raw / "0000000001" / "submissions" / "latest.json"
    digest = sha256(target.read_bytes()).hexdigest()
    key = f"{SOURCE_SYNC_PREFIX}/objects/sha256/{digest[:2]}/{digest}.bin"
    inner = LocalStore(tmp_path / "private-store")
    winner = target.read_bytes().replace(b'"a"', b'"b"')
    assert len(winner) == len(target.read_bytes())
    assert inner.put_bytes_strict_conditional(
        key,
        winner,
        expected_version=None,
        content_type="application/json",
    ) is True
    store = _ConditionalProxy(inner)

    with pytest.raises(SourceSyncError, match="immutable object collision"):
        sync_source_roots(
            raw_root=raw,
            archive_root=archive,
            store=store,
            snapshot_at=SNAPSHOT_AT,
        )

    assert inner.get_bytes(key) == winner
    assert inner.get_bytes(f"{SOURCE_SYNC_PREFIX}/latest.json") is None
    assert store.unconditional_put_calls == 0


def test_source_sync_stale_pointer_is_rejected_without_replacing_newer_latest(tmp_path: Path):
    raw, archive = _roots(tmp_path)
    inner = LocalStore(tmp_path / "private-store")
    store = _ConditionalProxy(inner)
    first = sync_source_roots(
        raw_root=raw,
        archive_root=archive,
        store=store,
        snapshot_at="2026-08-01T12:00:00Z",
    )
    (raw / "0000000001" / "submissions" / "latest.json").write_bytes(b'{"sha256":"b"}')
    second = sync_source_roots(
        raw_root=raw,
        archive_root=archive,
        store=store,
        snapshot_at="2026-08-01T12:01:00Z",
    )

    with pytest.raises(SourceSyncError, match="stale source snapshot"):
        source_sync_mod._publish_pointer(store, first)

    latest = json.loads(inner.get_bytes(f"{SOURCE_SYNC_PREFIX}/latest.json") or b"{}")
    assert latest["snapshot_id"] == second.snapshot_id
    assert store.unconditional_put_calls == 0


def test_source_sync_immutable_only_mode_leaves_latest_absent_or_unchanged(tmp_path: Path):
    raw, archive = _roots(tmp_path)
    store = LocalStore(tmp_path / "private-store")
    sealed = sync_source_roots(
        raw_root=raw,
        archive_root=archive,
        store=store,
        snapshot_at="2026-08-01T12:00:00Z",
        publish_latest=False,
    )
    assert store.get_bytes(sealed.manifest_key) is not None
    assert store.get_bytes(f"{SOURCE_SYNC_PREFIX}/latest.json") is None

    published = sync_source_roots(
        raw_root=raw,
        archive_root=archive,
        store=store,
        snapshot_at="2026-08-01T12:01:00Z",
    )
    (raw / "0000000001" / "submissions" / "latest.json").write_bytes(b'{"sha256":"b"}')
    later_sealed = sync_source_roots(
        raw_root=raw,
        archive_root=archive,
        store=store,
        snapshot_at="2026-08-01T12:02:00Z",
        publish_latest=False,
    )
    assert later_sealed.snapshot_id != published.snapshot_id
    latest = json.loads(store.get_bytes(f"{SOURCE_SYNC_PREFIX}/latest.json") or b"{}")
    assert latest["snapshot_id"] == published.snapshot_id


def test_source_sync_omits_only_the_companyfacts_coordination_lock(tmp_path: Path):
    raw, archive = _roots(tmp_path)
    lock = archive / "wave3_companyfacts" / ".manifest_publish.lock"
    lock.parent.mkdir(parents=True)
    lock.write_bytes(b"")
    store = LocalStore(tmp_path / "private-store")

    snapshot = sync_source_roots(
        raw_root=raw,
        archive_root=archive,
        store=store,
        snapshot_at=SNAPSHOT_AT,
    )
    manifest = json.loads(store.get_bytes(snapshot.manifest_key) or b"{}")
    entries = {
        (tree["kind"], entry["relative_path"])
        for tree in manifest["trees"]
        for entry in tree["entries"]
    }
    assert ("archive", "wave3_companyfacts/.manifest_publish.lock") not in entries

    lock.write_bytes(b"unexpected lock payload")
    with pytest.raises(SourceSyncError, match="coordination lock must be empty"):
        sync_source_roots(
            raw_root=raw,
            archive_root=archive,
            store=store,
            snapshot_at="2026-08-01T12:00:01Z",
        )
    lock.write_bytes(b"")
    (archive / ".unexpected.lock").write_bytes(b"")
    with pytest.raises(SourceSyncError, match="unsafe relative path"):
        sync_source_roots(
            raw_root=raw,
            archive_root=archive,
            store=store,
            snapshot_at="2026-08-01T12:00:02Z",
        )


def test_pinned_strict_reader_maps_local_archive_paths_to_exact_outer_objects(tmp_path: Path):
    raw, archive = _roots(tmp_path)
    store = LocalStore(tmp_path / "private-store")
    snapshot = sync_source_roots(
        raw_root=raw,
        archive_root=archive,
        store=store,
        snapshot_at=SNAPSHOT_AT,
    )

    pinned = load_pinned_source_snapshot_strict(
        store=store, snapshot_id=snapshot.snapshot_id
    )
    receipt = read_pinned_source_snapshot_file_strict(
        store=store,
        snapshot=pinned,
        kind="archive",
        relative_path="manifests/0000000001/0000000001-26-000001/manifest.json",
    )
    member = read_pinned_source_snapshot_file_strict(
        store=store,
        snapshot=pinned,
        kind="archive",
        relative_path="objects/sha256/ab/abcdef.bin.gz",
    )
    raw_read = read_pinned_source_snapshot_file_strict(
        store=store,
        snapshot=pinned,
        kind="raw",
        relative_path="0000000001/submissions/latest.json",
    )

    assert receipt.content == b'{"manifest":"fixture"}'
    assert member.content == b"archive-source"
    assert raw_read.content == b'{"sha256":"a"}'
    assert receipt.witness.snapshot_id == snapshot.snapshot_id
    assert receipt.witness.kind == "archive"
    assert receipt.witness.relative_path.endswith("/manifest.json")
    assert receipt.witness.object_key.startswith(f"{SOURCE_SYNC_PREFIX}/objects/sha256/")
    assert receipt.witness.object_key != receipt.witness.relative_path
    assert receipt.witness.byte_length == len(receipt.content)
    assert receipt.witness.sha256 == sha256(receipt.content).hexdigest()
    assert receipt.witness.content_type == "application/json"
    assert member.witness.content_type == "application/gzip"
    assert pinned.manifest_key == snapshot.manifest_key
    assert pinned.snapshot_id == snapshot.snapshot_id


def test_pinned_strict_reader_fails_closed_for_missing_tampered_and_too_small_reads(tmp_path: Path):
    raw, archive = _roots(tmp_path)
    store = LocalStore(tmp_path / "private-store")
    snapshot = sync_source_roots(
        raw_root=raw,
        archive_root=archive,
        store=store,
        snapshot_at=SNAPSHOT_AT,
    )
    pinned = load_pinned_source_snapshot_strict(store=store, snapshot_id=snapshot.snapshot_id)
    relative = "objects/sha256/ab/abcdef.bin.gz"
    witness = pinned.entry_for(kind="archive", relative_path=relative)

    with pytest.raises(SourceSyncError, match="requested read limit"):
        read_pinned_source_snapshot_file_strict(
            store=store, snapshot=pinned, kind="archive", relative_path=relative, max_bytes=1
        )

    store._p(witness.object_key).unlink()
    with pytest.raises(SourceSyncError, match="object not found"):
        read_pinned_source_snapshot_file_strict(
            store=store, snapshot=pinned, kind="archive", relative_path=relative
        )

    # Recreate exactly the mapped outer key with different bytes: source path
    # lookup still succeeds, but the immutable outer digest must not.
    assert store.put_bytes(witness.object_key, b"tampered")
    with pytest.raises(SourceSyncError, match="exact checksum"):
        read_pinned_source_snapshot_file_strict(
            store=store, snapshot=pinned, kind="archive", relative_path=relative
        )


def test_pinned_strict_loader_rejects_duplicate_kind_path_before_any_source_read(tmp_path: Path):
    raw, archive = _roots(tmp_path)
    store = LocalStore(tmp_path / "private-store")
    snapshot = sync_source_roots(
        raw_root=raw,
        archive_root=archive,
        store=store,
        snapshot_at=SNAPSHOT_AT,
    )
    manifest = json.loads(store.get_bytes(snapshot.manifest_key) or b"{}")
    archive_tree = next(tree for tree in manifest["trees"] if tree["kind"] == "archive")
    archive_tree["entries"].append(dict(archive_tree["entries"][0]))
    archive_tree["entries"].sort(key=lambda entry: entry["relative_path"])
    body = {key: value for key, value in manifest.items() if key != "snapshot_id"}
    duplicate_id = "ffsecsrc_" + sha256(canonical_json(body).encode("utf-8")).hexdigest()
    duplicate_manifest = {**body, "snapshot_id": duplicate_id}
    assert store.put_bytes(
        f"{SOURCE_SYNC_PREFIX}/manifests/{duplicate_id}.json",
        canonical_json(duplicate_manifest).encode("utf-8"),
    )

    with pytest.raises(SourceSyncError, match="duplicate path"):
        load_pinned_source_snapshot_strict(store=store, snapshot_id=duplicate_id)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("relative_path", "objects//sha256/ab/abcdef.bin.gz", "not canonical"),
        ("relative_path", 5, "must be a string"),
        ("content_type", "text/html", "content type does not match"),
    ],
)
def test_pinned_strict_loader_rejects_noncanonical_typed_or_mislabeled_entries(
    tmp_path: Path, field, value, message
):
    raw, archive = _roots(tmp_path)
    store = LocalStore(tmp_path / "private-store")
    snapshot = sync_source_roots(
        raw_root=raw, archive_root=archive, store=store, snapshot_at=SNAPSHOT_AT
    )
    manifest = json.loads(store.get_bytes(snapshot.manifest_key) or b"{}")
    archive_tree = next(tree for tree in manifest["trees"] if tree["kind"] == "archive")
    archive_tree["entries"][0][field] = value
    archive_tree["entries"].sort(key=lambda entry: str(entry["relative_path"]))
    body = {key: item for key, item in manifest.items() if key != "snapshot_id"}
    forged_id = "ffsecsrc_" + sha256(canonical_json(body).encode("utf-8")).hexdigest()
    forged = {**body, "snapshot_id": forged_id}
    assert store.put_bytes(
        f"{SOURCE_SYNC_PREFIX}/manifests/{forged_id}.json",
        canonical_json(forged).encode("utf-8"),
    )

    with pytest.raises(SourceSyncError, match=message):
        load_pinned_source_snapshot_strict(store=store, snapshot_id=forged_id)


def test_pinned_file_read_reloads_manifest_and_ignores_forgeable_session_mapping(tmp_path: Path):
    raw, archive = _roots(tmp_path)
    store = LocalStore(tmp_path / "private-store")
    snapshot = sync_source_roots(
        raw_root=raw, archive_root=archive, store=store, snapshot_at=SNAPSHOT_AT
    )
    pinned = load_pinned_source_snapshot_strict(store=store, snapshot_id=snapshot.snapshot_id)
    fake_content = b"caller-directed-content"
    fake_digest = sha256(fake_content).hexdigest()
    fake_key = f"{SOURCE_SYNC_PREFIX}/objects/sha256/{fake_digest[:2]}/{fake_digest}.bin"
    assert store.put_bytes(fake_key, fake_content)
    forged = VerifiedSourceSnapshot(
        snapshot=pinned.snapshot,
        manifest_sha256=pinned.manifest_sha256,
        manifest_byte_length=pinned.manifest_byte_length,
        entries_by_path=MappingProxyType(
            {
                ("archive", "redirect.bin"): SourceObjectWitness(
                    snapshot_id=pinned.snapshot_id,
                    kind="archive",
                    relative_path="redirect.bin",
                    object_key=fake_key,
                    sha256=fake_digest,
                    byte_length=len(fake_content),
                    content_type="application/octet-stream",
                )
            }
        ),
        _seal=source_sync_mod._VERIFIED_SNAPSHOT_SEAL,
    )

    with pytest.raises(SourceSyncError, match="does not contain"):
        read_pinned_source_snapshot_file_strict(
            store=store,
            snapshot=forged,
            kind="archive",
            relative_path="redirect.bin",
        )


class _BadReadbackStore(LocalStore):
    def get_bytes_strict_bounded(self, key: str, maximum_bytes: int) -> bytes | None:
        value = super().get_bytes_strict_bounded(key, maximum_bytes)
        if value is not None and "/objects/sha256/" in key:
            return value[:-1] + (b"x" if value[-1:] != b"x" else b"y")
        return value


def test_sync_fails_closed_before_latest_pointer_when_object_readback_changes(tmp_path: Path):
    raw, archive = _roots(tmp_path)
    store = _BadReadbackStore(tmp_path / "private-store")

    with pytest.raises(SourceSyncError, match="read-back mismatch"):
        sync_source_roots(
            raw_root=raw,
            archive_root=archive,
            store=store,
            snapshot_at=SNAPSHOT_AT,
        )

    assert LocalStore(tmp_path / "private-store").get_bytes(
        f"{SOURCE_SYNC_PREFIX}/latest.json"
    ) is None


def test_sync_rejects_symlink_and_strict_size_ceiling(tmp_path: Path):
    raw, archive = _roots(tmp_path)
    outside = tmp_path / "outside.json"
    outside.write_text("do not traverse", encoding="utf-8")
    os.symlink(outside, raw / "0000000001" / "submissions" / "escape.json")

    with pytest.raises(SourceSyncError, match="symlink"):
        sync_source_roots(
            raw_root=raw,
            archive_root=archive,
            store=LocalStore(tmp_path / "private-store"),
            snapshot_at=SNAPSHOT_AT,
        )

    (raw / "0000000001" / "submissions" / "escape.json").unlink()
    with pytest.raises(SourceSyncError, match="per-file limit"):
        sync_source_roots(
            raw_root=raw,
            archive_root=archive,
            store=LocalStore(tmp_path / "private-store"),
            snapshot_at=SNAPSHOT_AT,
            max_file_bytes=4,
            max_total_bytes=4,
        )


def test_restore_rejects_traversal_manifest_before_writing_local_tree(tmp_path: Path):
    raw = tmp_path / "raw"
    archive = tmp_path / "archive"
    store = LocalStore(tmp_path / "private-store")
    body = {
        "schema": "fundamental_forensics.sec_source_snapshot/v1",
        "prefix": SOURCE_SYNC_PREFIX,
        "snapshot_at": "2026-08-01T12:00:00.000000Z",
        "trees": [
            {
                "kind": "raw",
                "entries": [
                    {
                        "relative_path": "../outside.json",
                        "object_key": f"{SOURCE_SYNC_PREFIX}/objects/sha256/aa/" + "a" * 64 + ".bin",
                        "sha256": "a" * 64,
                        "byte_length": 1,
                        "content_type": "application/json",
                    }
                ],
            },
            {"kind": "archive", "entries": []},
        ],
    }
    snapshot_id = "ffsecsrc_" + sha256(canonical_json(body).encode("utf-8")).hexdigest()
    unsafe = {**body, "snapshot_id": snapshot_id}
    key = f"{SOURCE_SYNC_PREFIX}/manifests/{snapshot_id}.json"
    assert store.put_bytes(key, canonical_json(unsafe).encode("utf-8"))

    with pytest.raises(SourceSyncError, match="unsafe relative path"):
        restore_source_roots(
            raw_root=raw,
            archive_root=archive,
            store=store,
            snapshot_id=snapshot_id,
        )

    assert not raw.exists()
    assert not archive.exists()
    assert not (tmp_path / "outside.json").exists()


class _CountingRestoreStore(LocalStore):
    """Count object GETs so a skipped download is proven, not assumed."""

    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self.object_gets: list[str] = []

    def get_bytes(self, key: str):
        if "/objects/sha256/" in key:
            self.object_gets.append(key)
        return super().get_bytes(key)


def test_verify_local_restore_trusts_a_hash_equal_warm_file_and_heals_a_corrupt_one(tmp_path: Path):
    """The off-render lane keeps its store OUTSIDE the checkout, so most files are warm.

    Default restore still pulls every byte from R2 (operator recovery); verify_local
    replaces only the byte SOURCE with local disk under the same manifest-bound hash.
    """
    raw, archive = _roots(tmp_path)
    store = _CountingRestoreStore(tmp_path / "private-store")
    snapshot = sync_source_roots(
        raw_root=raw, archive_root=archive, store=store, snapshot_at=SNAPSHOT_AT
    )

    store.object_gets.clear()
    cold = restore_source_roots(raw_root=raw, archive_root=archive, store=store)
    assert cold.current_files == snapshot.file_count
    assert len(store.object_gets) == snapshot.file_count

    store.object_gets.clear()
    warm = restore_source_roots(
        raw_root=raw, archive_root=archive, store=store, verify_local=True
    )
    assert warm.current_files == snapshot.file_count
    assert warm.restored_files == 0
    assert store.object_gets == []

    victim = raw / "0000000001" / "submissions" / "latest.json"
    original = victim.read_bytes()
    victim.write_bytes(b"corrupted-local-copy")
    store.object_gets.clear()
    healed = restore_source_roots(
        raw_root=raw, archive_root=archive, store=store, verify_local=True
    )
    assert healed.restored_files == 1
    assert healed.current_files == snapshot.file_count - 1
    assert len(store.object_gets) == 1
    assert victim.read_bytes() == original


def test_incremental_sync_creates_only_new_objects_but_still_enumerates_every_file(tmp_path: Path):
    raw, archive = _roots(tmp_path)
    inner = LocalStore(tmp_path / "private-store")
    store = _ConditionalProxy(inner)
    first = sync_source_roots(
        raw_root=raw, archive_root=archive, store=store, snapshot_at=SNAPSHOT_AT
    )

    new_bytes = b"new-compressed-submissions"
    (raw / "0000000001" / "submissions" / "b.json.gz").write_bytes(new_bytes)
    store.conditional_calls.clear()
    second = sync_source_roots(
        raw_root=raw,
        archive_root=archive,
        store=store,
        snapshot_at="2026-08-02T12:00:00Z",
        skip_objects_in_latest_manifest=True,
    )

    assert second.file_count == first.file_count + 1
    assert [call[0] for call in store.conditional_calls] == [
        source_object_key_for_sha256(sha256(new_bytes).hexdigest()),
        second.manifest_key,
        f"{SOURCE_SYNC_PREFIX}/latest.json",
    ]

    # Manifest completeness is unchanged: the new snapshot still restores the whole tree.
    shutil.rmtree(raw)
    shutil.rmtree(archive)
    restored = restore_source_roots(raw_root=raw, archive_root=archive, store=inner)
    assert restored.snapshot == second
    assert restored.restored_files == second.file_count
    assert (raw / "0000000001" / "submissions" / "b.json.gz").read_bytes() == new_bytes
    assert (archive / "objects" / "sha256" / "ab" / "abcdef.bin.gz").read_bytes() == b"archive-source"


def test_incremental_sync_is_a_full_sync_when_no_latest_snapshot_exists(tmp_path: Path):
    raw, archive = _roots(tmp_path)
    store = _ConditionalProxy(LocalStore(tmp_path / "private-store"))

    snapshot = sync_source_roots(
        raw_root=raw,
        archive_root=archive,
        store=store,
        snapshot_at=SNAPSHOT_AT,
        skip_objects_in_latest_manifest=True,
    )

    keys = [call[0] for call in store.conditional_calls]
    assert len(keys) == snapshot.file_count + 2
    assert keys[-2:] == [snapshot.manifest_key, f"{SOURCE_SYNC_PREFIX}/latest.json"]


def test_incremental_modes_reject_a_non_boolean_switch(tmp_path: Path):
    raw, archive = _roots(tmp_path)
    store = LocalStore(tmp_path / "private-store")

    with pytest.raises(SourceSyncError, match="skip_objects_in_latest_manifest must be a boolean"):
        sync_source_roots(
            raw_root=raw,
            archive_root=archive,
            store=store,
            snapshot_at=SNAPSHOT_AT,
            skip_objects_in_latest_manifest="yes",
        )
    with pytest.raises(SourceSyncError, match="verify_local must be a boolean"):
        restore_source_roots(
            raw_root=raw, archive_root=archive, store=store, verify_local="yes"
        )
