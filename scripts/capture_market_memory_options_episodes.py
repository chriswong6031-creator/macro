"""Capture or replay the sole admitted Market Memory production-record class."""

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

from engine.neuralweb import market_memory_production_records as production_records

_COMMIT = re.compile(r"[a-f0-9]{40}(?:[a-f0-9]{24})?\Z")


class MarketMemoryProductionRecordCliError(RuntimeError):
    """The deployed capture/replay command cannot prove its exact input."""


def _git_environment() -> dict[str, str]:
    return {
        key: value for key, value in os.environ.items() if not key.startswith("GIT_")
    }


def _repository_commit(repository_root: Path) -> str:
    try:
        result = subprocess.run(
            [
                "git",
                "-c",
                f"safe.directory={repository_root}",
                "-C",
                str(repository_root),
                "rev-parse",
                "--verify",
                "HEAD^{commit}",
            ],
            check=True,
            capture_output=True,
            timeout=30,
            env=_git_environment(),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise MarketMemoryProductionRecordCliError(
            "cannot resolve the deployed repository commit"
        ) from exc
    try:
        commit = result.stdout.decode("ascii").strip()
    except UnicodeDecodeError as exc:
        raise MarketMemoryProductionRecordCliError(
            "deployed repository commit is not ASCII"
        ) from exc
    if _COMMIT.fullmatch(commit) is None:
        raise MarketMemoryProductionRecordCliError(
            "deployed repository commit is malformed"
        )
    return commit


def _committed_source_bytes(repository_root: Path, *, commit: str) -> bytes:
    object_name = f"{commit}:{production_records.SOURCE_ARTIFACT_REL}"
    try:
        size_result = subprocess.run(
            [
                "git",
                "-c",
                f"safe.directory={repository_root}",
                "-C",
                str(repository_root),
                "cat-file",
                "-s",
                object_name,
            ],
            check=True,
            capture_output=True,
            timeout=30,
            env=_git_environment(),
        )
        size = int(size_result.stdout.decode("ascii").strip())
    except (OSError, subprocess.SubprocessError, UnicodeDecodeError, ValueError) as exc:
        raise MarketMemoryProductionRecordCliError(
            "cannot size the exact committed options episode ledger"
        ) from exc
    if not 1 <= size <= production_records.MAX_SOURCE_BYTES:
        raise MarketMemoryProductionRecordCliError(
            "committed options episode ledger exceeds its byte bound"
        )
    try:
        result = subprocess.run(
            [
                "git",
                "-c",
                f"safe.directory={repository_root}",
                "-C",
                str(repository_root),
                "cat-file",
                "blob",
                object_name,
            ],
            check=True,
            capture_output=True,
            timeout=60,
            env=_git_environment(),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise MarketMemoryProductionRecordCliError(
            "cannot read the exact committed options episode ledger"
        ) from exc
    body = result.stdout
    if len(body) != size:
        raise MarketMemoryProductionRecordCliError(
            "committed options episode ledger size changed during read"
        )
    return body


def capture_deployed_options_episodes(
    repository_root: str | Path,
    *,
    store_root: str | Path | None = None,
) -> dict[str, Any]:
    """Capture the immutable Git object at deployed HEAD, never worktree bytes."""

    repository = Path(repository_root).expanduser().resolve()
    commit = _repository_commit(repository)
    source_body = _committed_source_bytes(repository, commit=commit)
    destination = (
        production_records.validate_production_record_store_root(
            Path(store_root).expanduser(), repository_root=repository
        )
        if store_root is not None
        else production_records.default_production_record_store_root(repository)
    )
    stored = production_records.capture_options_episode_source(
        destination,
        source_body=source_body,
        source_commit=commit,
    )
    result = production_records.capture_result_payload(stored)
    result["deployed_commit"] = commit
    return result


def replay_deployed_options_episode(
    repository_root: str | Path,
    *,
    episode_id: str,
    as_known_at: str,
    store_root: str | Path | None = None,
    generation_id: str | None = None,
) -> dict[str, Any]:
    """Run the private exact-as-known-at developer/admin replay path."""

    repository = Path(repository_root).expanduser().resolve()
    destination = (
        production_records.validate_production_record_store_root(
            Path(store_root).expanduser(), repository_root=repository
        )
        if store_root is not None
        else production_records.default_production_record_store_root(repository)
    )
    return production_records.replay_production_record_as_known_at(
        destination,
        episode_id=episode_id,
        as_known_at=as_known_at,
        generation_id=generation_id,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Capture the committed options episode production-record class, or "
            "run an exact private as-known-at replay"
        )
    )
    parser.add_argument("--repository-root", type=Path, default=_ROOT)
    parser.add_argument("--store-root", type=Path)
    parser.add_argument("--replay-episode-id")
    parser.add_argument("--as-known-at")
    parser.add_argument("--generation-id")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    replay_requested = (
        args.replay_episode_id is not None or args.as_known_at is not None
    )
    if replay_requested:
        if args.replay_episode_id is None or args.as_known_at is None:
            raise SystemExit(
                "--replay-episode-id and --as-known-at must be supplied together"
            )
        result = replay_deployed_options_episode(
            args.repository_root,
            episode_id=args.replay_episode_id,
            as_known_at=args.as_known_at,
            store_root=args.store_root,
            generation_id=args.generation_id,
        )
    else:
        if args.generation_id is not None:
            raise SystemExit("--generation-id is valid only for replay")
        result = capture_deployed_options_episodes(
            args.repository_root,
            store_root=args.store_root,
        )
    print(json.dumps(result, allow_nan=False, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
