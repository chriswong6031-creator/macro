from __future__ import annotations

import os
from pathlib import Path
import shutil
from hashlib import sha256

import pytest

from engine.fundamental_forensics.source_sync import (
    SOURCE_SYNC_PREFIX,
    SourceSyncError,
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
