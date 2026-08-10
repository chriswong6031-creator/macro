#!/usr/bin/env python3
"""Accrue the private, future-honest SPY identity-observation ledger."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

_COMMIT = re.compile(r"[a-f0-9]{40,64}\Z")
_SNAPSHOT_KEY = re.compile(
    r"data/symbol_directory/snapshots/(\d{4}-\d{2}-\d{2})\.parquet\Z"
)
_LISTING_RECEIPT_KEY = re.compile(
    r"data/symbol_directory/receipts/snapshots/(\d{4}-\d{2}-\d{2})\.json\Z"
)


class IdentityIngestError(RuntimeError):
    """The deployed checkout could not be bound to an identity capture."""


def _git(
    root: Path,
    *args: str,
    text: bool = False,
) -> bytes | str:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            check=True,
            capture_output=True,
            text=text,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise IdentityIngestError("cannot bind identity intake to Git") from exc
    return result.stdout


def _repository_commit(root: Path) -> str:
    value = str(_git(root, "rev-parse", "HEAD", text=True)).strip()
    if not _COMMIT.fullmatch(value):
        raise IdentityIngestError("deployed checkout commit is malformed")
    return value


def _tracked_snapshot_keys(root: Path, commit: str) -> list[str]:
    output = str(
        _git(
            root,
            "ls-tree",
            "-r",
            "--name-only",
            commit,
            "--",
            "data/symbol_directory/snapshots",
            text=True,
        )
    )
    keys = sorted(line for line in output.splitlines() if line)
    if not keys or any(_SNAPSHOT_KEY.fullmatch(key) is None for key in keys):
        raise IdentityIngestError(
            "tracked symbol-directory snapshot inventory is not canonical"
        )
    if len(keys) != len(set(keys)) or len(keys) > 4_096:
        raise IdentityIngestError("tracked snapshot inventory exceeds its bound")
    return keys


def _tracked_listing_receipt_keys(root: Path, commit: str) -> frozenset[str]:
    output = str(
        _git(
            root,
            "ls-tree",
            "-r",
            "--name-only",
            commit,
            "--",
            "data/symbol_directory/receipts/snapshots",
            text=True,
        )
    )
    keys = [line for line in output.splitlines() if line]
    if any(_LISTING_RECEIPT_KEY.fullmatch(key) is None for key in keys):
        raise IdentityIngestError(
            "tracked listing completion-receipt inventory is not canonical"
        )
    if len(keys) != len(set(keys)) or len(keys) > 4_096:
        raise IdentityIngestError(
            "tracked listing completion-receipt inventory exceeds its bound"
        )
    return frozenset(keys)


def _tracked_bytes(root: Path, commit: str, key: str) -> bytes:
    body = _git(root, "show", f"{commit}:{key}")
    if not isinstance(body, bytes) or not body:
        raise IdentityIngestError(f"tracked object {key} is empty")
    return body


def ingest_identity_observations(
    repository_root: str | Path,
    *,
    store_root: str | Path | None = None,
) -> dict[str, Any]:
    """Capture every exact tracked SPY roster observation in date order."""

    root = Path(repository_root).expanduser().resolve()
    if not root.is_dir():
        raise IdentityIngestError("repository root is unavailable")

    # Pin the deployed checkout before importing the engine implementation. The
    # hourly timer can otherwise start while macro-update is replacing the
    # worktree and run old imported validators against a newly pinned commit.
    deployed_commit = _repository_commit(root)
    from engine.neuralweb import (
        market_memory_identity_observation,
        market_memory_identity_store,
    )

    if _repository_commit(root) != deployed_commit:
        raise IdentityIngestError(
            "deployed checkout changed during identity intake module loading"
        )
    store = (
        store_root
        or market_memory_identity_store.default_identity_observation_store_root(root)
    )
    keys = _tracked_snapshot_keys(root, deployed_commit)
    receipt_keys = _tracked_listing_receipt_keys(root, deployed_commit)
    expected_receipt_keys = frozenset(
        "data/symbol_directory/receipts/snapshots/"
        f"{_SNAPSHOT_KEY.fullmatch(key).group(1)}.json"
        for key in keys
    )
    if not receipt_keys.issubset(expected_receipt_keys):
        raise IdentityIngestError(
            "tracked listing completion receipt has no matching snapshot"
        )
    state = market_memory_identity_store.initialize_identity_observation_store(
        store,
        repository_root=root,
    )
    published = 0
    idempotent = 0
    operational = 0
    reconstruction = 0
    last_result = None

    for key in keys:
        snapshot_path = root / key
        receipt_path = (
            market_memory_identity_observation.infer_listing_completion_receipt_path(
                snapshot_path
            )
        )
        try:
            receipt_key = receipt_path.relative_to(root).as_posix()
        except ValueError as exc:
            raise IdentityIngestError(
                "completion receipt escapes the deployed checkout"
            ) from exc
        receipt_is_tracked = receipt_key in receipt_keys
        receipt_is_present = receipt_path.exists() or receipt_path.is_symlink()
        if receipt_is_tracked != receipt_is_present:
            raise IdentityIngestError(
                f"completion receipt {receipt_key} presence differs from the deployed commit"
            )
        bundle = market_memory_identity_observation.build_spy_listing_observation(
            snapshot_path,
            completion_receipt_path=receipt_path if receipt_is_tracked else None,
        )
        if bundle.snapshot_bytes != _tracked_bytes(root, deployed_commit, key):
            raise IdentityIngestError(
                f"snapshot {key} is not owned by the deployed checkout"
            )
        if (
            bundle.completion_receipt is not None
            and bundle.completion_receipt_bytes
            != _tracked_bytes(root, deployed_commit, receipt_key)
        ):
            raise IdentityIngestError(
                f"completion receipt {receipt_key} is not Git-owned"
            )
        result = market_memory_identity_store.capture_spy_listing_observation(
            store,
            bundle,
            repository_root=root,
        )
        last_result = result
        if result.published:
            published += 1
        else:
            idempotent += 1
        basis = result.observation.get("pit_basis")
        if basis == "live_captured":
            operational += 1
        elif basis == "public_reconstruction":
            reconstruction += 1
        else:
            raise IdentityIngestError("captured observation has an unknown PIT basis")

    if _repository_commit(root) != deployed_commit:
        raise IdentityIngestError("deployed checkout changed during identity intake")
    head = last_result.head if last_result is not None else state["head"]
    return {
        "schema": "market_memory.identity_ingest_result.v1",
        "deployed_commit": deployed_commit,
        "tracked_snapshot_count": len(keys),
        "published_count": published,
        "idempotent_count": idempotent,
        "reconstruction_count": reconstruction,
        "operational_count": operational,
        "generation_id": head["generation_id"],
        "authority": {
            "context_only": True,
            "training_eligible": False,
            "promotion_eligible": False,
        },
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Accrue private SPY symbol-directory observations"
    )
    parser.add_argument(
        "--repository-root",
        default=os.environ.get("MACRO_REPO", "/opt/macro"),
        help="reviewed Macro checkout containing the tracked roster snapshots",
    )
    parser.add_argument(
        "--store-root",
        default=None,
        help="private identity store override (tests/operators only)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = ingest_identity_observations(
        args.repository_root,
        store_root=args.store_root,
    )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
