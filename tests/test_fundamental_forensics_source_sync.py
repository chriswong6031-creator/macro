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
    def get_bytes(self, key: str) -> bytes | None:
        value = super().get_bytes(key)
        if value is not None and "/objects/sha256/" in key:
            return value + b"corrupt-readback"
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
