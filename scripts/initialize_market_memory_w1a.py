#!/usr/bin/env python3
"""Initialize or authenticate the public W1A generation spine."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from engine.neuralweb import market_memory_pit as pit

_DISJOINT_PROFILE_ROOT = "trusted-v1"
_MAX_NAMESPACE_ENTRIES = 20_000


def _reject_symlinked_ancestor(root: Path) -> Path:
    """Keep resolution from hiding a symlink anywhere in the input path."""

    absolute = Path(os.path.abspath(root.expanduser()))
    cursor = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        cursor /= part
        try:
            metadata = os.lstat(cursor)
        except FileNotFoundError:
            break
        if stat.S_ISLNK(metadata.st_mode):
            raise pit.MarketMemoryStoreError(
                "Market Memory PIT store path contains a symlinked ancestor"
            )
    return absolute


def _require_directory_metadata(
    metadata: os.stat_result, *, owner: tuple[int, int], label: str
) -> None:
    if not stat.S_ISDIR(metadata.st_mode):
        raise pit.MarketMemoryStoreError(f"{label} is not a directory")
    if stat.S_IMODE(metadata.st_mode) != 0o700:
        raise pit.MarketMemoryStoreError(f"{label} mode is not 0700")
    if (metadata.st_uid, metadata.st_gid) != owner:
        raise pit.MarketMemoryStoreError(f"{label} ownership differs from the store")


def _require_file_metadata(
    metadata: os.stat_result, *, owner: tuple[int, int], label: str
) -> None:
    if not stat.S_ISREG(metadata.st_mode):
        raise pit.MarketMemoryStoreError(f"{label} is not a regular file")
    if metadata.st_nlink != 1:
        raise pit.MarketMemoryStoreError(f"{label} is hardlinked")
    if stat.S_IMODE(metadata.st_mode) != 0o600:
        raise pit.MarketMemoryStoreError(f"{label} mode is not 0600")
    if (metadata.st_uid, metadata.st_gid) != owner:
        raise pit.MarketMemoryStoreError(f"{label} ownership differs from the store")


def _expected_directories(files: set[Path]) -> set[Path]:
    directories: set[Path] = set()
    for relative in files:
        parent = relative.parent
        while parent != Path("."):
            directories.add(parent)
            parent = parent.parent
    return directories


def _audit_namespace(
    store: Path,
    *,
    owner: tuple[int, int],
    expected_files: set[Path],
    expected_directories: set[Path],
    require_complete: bool,
    expected_generation_files: int | None = None,
) -> None:
    """Reject every W1A-owned entry not proved by the active/prefix state."""

    pending = [store]
    entries = 0
    observed_files: set[Path] = set()
    generation_files: set[Path] = set()
    generation_shards: set[Path] = set()
    while pending:
        directory = pending.pop()
        try:
            children = os.scandir(directory)
        except OSError as exc:
            raise pit.MarketMemoryStoreError(
                "W1A namespace cannot be inspected safely"
            ) from exc
        try:
            with children:
                for entry in children:
                    entries += 1
                    if entries > _MAX_NAMESPACE_ENTRIES:
                        raise pit.MarketMemoryStoreError(
                            "W1A namespace exceeds its safe entry bound"
                        )
                    path = Path(entry.path)
                    relative = path.relative_to(store)
                    try:
                        metadata = entry.stat(follow_symlinks=False)
                    except OSError as exc:
                        raise pit.MarketMemoryStoreError(
                            "W1A namespace entry cannot be inspected safely"
                        ) from exc
                    if stat.S_ISLNK(metadata.st_mode):
                        raise pit.MarketMemoryStoreError(
                            "W1A namespace contains a symlink"
                        )
                    if relative == Path(_DISJOINT_PROFILE_ROOT):
                        _require_directory_metadata(
                            metadata, owner=owner, label="trusted-v1 profile root"
                        )
                        # trusted-v1 is a separate reviewed owner. Its reader
                        # authenticates its contents; this initializer must not
                        # inventory or edit the sibling profile.
                        continue
                    if stat.S_ISDIR(metadata.st_mode):
                        generation_directory = (
                            expected_generation_files is not None
                            and (
                                relative == Path("generations")
                                or (
                                    len(relative.parts) == 2
                                    and relative.parts[0] == "generations"
                                    and pit._SHARD.fullmatch(relative.parts[1])
                                    is not None
                                )
                            )
                        )
                        if (
                            relative not in expected_directories
                            and not generation_directory
                        ):
                            raise pit.MarketMemoryStoreError(
                                "W1A namespace contains an unowned directory"
                            )
                        _require_directory_metadata(
                            metadata, owner=owner, label=f"W1A directory {relative}"
                        )
                        if len(relative.parts) == 2 and generation_directory:
                            generation_shards.add(relative)
                        pending.append(path)
                        continue
                    generation_file = False
                    if (
                        expected_generation_files is not None
                        and len(relative.parts) == 3
                        and relative.parts[0] == "generations"
                        and pit._SHARD.fullmatch(relative.parts[1]) is not None
                        and relative.suffix == ".json"
                    ):
                        generation_id = relative.stem
                        generation_file = (
                            pit._GENERATION_ID.fullmatch(generation_id) is not None
                            and relative.parts[1]
                            == generation_id.removeprefix("mmgeneration_")[:2]
                        )
                    if generation_file:
                        _require_file_metadata(
                            metadata,
                            owner=owner,
                            label=f"W1A generation archive {relative}",
                        )
                        generation_files.add(relative)
                        if relative in expected_files:
                            observed_files.add(relative)
                        continue
                    if relative not in expected_files:
                        raise pit.MarketMemoryStoreError(
                            "W1A namespace contains an unowned file"
                        )
                    _require_file_metadata(
                        metadata, owner=owner, label=f"W1A file {relative}"
                    )
                    observed_files.add(relative)
        except OSError as exc:
            raise pit.MarketMemoryStoreError(
                "W1A namespace cannot be inspected safely"
            ) from exc
    if require_complete and observed_files != expected_files:
        if missing := expected_files - observed_files:
            label = min(str(path) for path in missing)
            raise pit.MarketMemoryStoreError(f"W1A active namespace is missing {label}")
        if observed_files - expected_files:  # pragma: no cover - loop rejects first
            raise pit.MarketMemoryStoreError(
                "W1A active namespace contains an unowned file"
            )
    if expected_generation_files is not None:
        if len(generation_files) != expected_generation_files:
            raise pit.MarketMemoryStoreError(
                "W1A generation archive count differs from active HEAD"
            )
        populated_shards = {path.parent for path in generation_files}
        if generation_shards != populated_shards:
            raise pit.MarketMemoryStoreError(
                "W1A generation archive contains an empty shard"
            )


def _partial_empty_prefix_files(store: Path) -> set[Path]:
    manifest_path = pit._store_manifest_path(store)
    manifest, _body = pit._read_canonical_object(
        manifest_path,
        limit=pit._MAX_STORE_MANIFEST_BYTES,
        label="Market Memory store manifest",
    )
    clean_manifest = pit._validate_store_manifest(manifest)
    generation = pit._new_generation(
        store_id=clean_manifest["store_id"],
        previous_generation_id=None,
        captures=[],
    )
    generation_path = pit._generation_path(store, generation["generation_id"])
    if generation_path.exists() or generation_path.is_symlink():
        existing, existing_body = pit._read_canonical_object(
            generation_path,
            limit=pit._MAX_GENERATION_BYTES,
            label="empty store generation",
        )
        clean_generation = pit._validate_generation(
            existing, store_id=clean_manifest["store_id"]
        )
        if clean_generation != generation or existing_body != pit._canonical_bytes(
            generation
        ):
            raise pit.MarketMemoryStoreError(
                "empty store generation differs from the deterministic prefix"
            )
    return {
        manifest_path.relative_to(store),
        generation_path.relative_to(store),
    }


def _complete_store_files(
    store: Path,
) -> tuple[pit.PinnedGenerationSnapshot, set[Path], int]:
    reader = pit.FileAsKnownAtReader(store)
    snapshot = reader.read_active_generation()
    expected = {
        pit._store_manifest_path(store).relative_to(store),
        pit._head_path(store).relative_to(store),
        pit._generation_path(store, snapshot.generation_id).relative_to(store),
    }

    for entry in snapshot.captures:
        # The content-bound active generation proves these exact immutable keys.
        # Packet bytes remain page-validated by the playback reader so this
        # deploy-time metadata check never grows into an unbounded full-store read.
        expected.update(
            {
                pit._query_path(store, entry.query_id).relative_to(store),
                pit._context_path(store, entry.context_id).relative_to(store),
                pit._object_path(store, entry.packet_sha256).relative_to(store),
            }
        )
    # Genesis plus exactly one immutable generation per captured query.  The
    # active generation is fully authenticated above; older generations are a
    # bounded metadata-only archive for readiness, not replayed cumulatively.
    return snapshot, expected, len(snapshot.captures) + 1


def _audit_existing_store(
    store: Path, *, owner: tuple[int, int]
) -> pit.PinnedGenerationSnapshot | None:
    head_path = pit._head_path(store)
    manifest_path = pit._store_manifest_path(store)
    expected_generation_files: int | None = None
    if head_path.exists() or head_path.is_symlink():
        snapshot, expected_files, expected_generation_files = _complete_store_files(
            store
        )
    elif manifest_path.exists() or manifest_path.is_symlink():
        snapshot = None
        expected_files = _partial_empty_prefix_files(store)
    else:
        snapshot = None
        expected_files = set()
    _audit_namespace(
        store,
        owner=owner,
        expected_files=expected_files,
        expected_directories=_expected_directories(expected_files),
        require_complete=snapshot is not None,
        expected_generation_files=expected_generation_files,
    )
    return snapshot


def initialize_w1a_store(root: str | Path) -> dict[str, Any]:
    """Create or authenticate W1A metadata without creating a capture.

    The underlying owner may finish only its deterministic empty-init prefix
    after an interrupted first attempt. Capture-bearing namespace partials,
    generation-metadata tamper, crash orphans outside published ancestry, and
    missing ancestry still fail. Packet bytes remain validated on playback read.
    """

    unresolved = _reject_symlinked_ancestor(Path(root))
    store = pit.validate_store_root(unresolved)
    try:
        pit._mkdir_durable(store)
        flags = (
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        )
        descriptor = os.open(store, flags)
    except OSError as exc:
        raise pit.MarketMemoryStoreError(
            "W1A store root cannot be initialized safely"
        ) from exc
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        opened = os.fstat(descriptor)
        named = os.lstat(store)
        if (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino):
            raise pit.MarketMemoryStoreError(
                "W1A store root changed during initialization"
            )
        owner = (opened.st_uid, opened.st_gid)
        _require_directory_metadata(opened, owner=owner, label="W1A store root")
        snapshot = _audit_existing_store(store, owner=owner)
        if snapshot is None:
            pit._initialize_or_load_store(store)
            snapshot = _audit_existing_store(store, owner=owner)
        if snapshot is None:  # pragma: no cover - postcondition defense
            raise pit.MarketMemoryStoreError(
                "W1A store initialization did not publish an active HEAD"
            )
    except pit.MarketMemoryPITError:
        raise
    except OSError as exc:
        raise pit.MarketMemoryStoreError(
            "W1A store metadata cannot be initialized safely"
        ) from exc
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)

    return {
        "schema": pit._STORE_MANIFEST_SCHEMA,
        "profile": snapshot.profile,
        "store_id": snapshot.store_id,
        "generation_id": snapshot.generation_id,
        "generation_sha256": snapshot.generation_sha256,
        "capture_count": len(snapshot.captures),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Create or authenticate W1A manifest/genesis/HEAD metadata without "
            "capturing or materializing a context."
        )
    )
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=_ROOT,
        help="reviewed repository root used only to resolve the production default",
    )
    parser.add_argument(
        "--store",
        type=Path,
        default=None,
        help="W1A store root override (deployment/tests only)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    store = args.store or pit.default_store_root(args.repository_root)
    try:
        result = initialize_w1a_store(store)
    except pit.MarketMemoryPITError as exc:
        print(f"W1A initialization rejected: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, allow_nan=False, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
