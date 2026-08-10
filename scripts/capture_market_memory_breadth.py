"""Capture one exact current-tip breadth actual output into the private store.

This is the sole production writer wrapper for W1B.3A. It accepts no packet,
clock, session, feature, or authority override: the current reviewed Git tip is
stable-read by the projector, and the store owns the first durable observation
clock.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from engine.neuralweb import (
    market_memory_actual_output_store as actual_output_store,
)
from engine.neuralweb import market_memory_breadth_observation as breadth

_COMMIT = re.compile(r"[a-f0-9]{40}(?:[a-f0-9]{24})?\Z")


class MarketMemoryBreadthCaptureCliError(RuntimeError):
    """The deployed checkout cannot establish one exact breadth capture."""


def _repository_commit(repository_root: Path) -> str:
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(repository_root),
                "rev-parse",
                "--verify",
                "HEAD^{commit}",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise MarketMemoryBreadthCaptureCliError(
            "cannot resolve the deployed repository commit"
        ) from exc
    commit = result.stdout.strip()
    if not _COMMIT.fullmatch(commit):
        raise MarketMemoryBreadthCaptureCliError(
            "deployed repository commit is malformed"
        )
    return commit


def capture_current_breadth(
    repository_root: str | Path,
    *,
    store_root: str | Path | None = None,
) -> dict[str, Any]:
    """Project and durably capture the current reviewed breadth tip."""

    root = Path(repository_root).expanduser().resolve()
    commit = _repository_commit(root)
    bundle = breadth.build_current_breadth_snapshot(root, pinned_commit=commit)
    destination = (
        actual_output_store.validate_actual_output_store_root(
            Path(store_root).expanduser(), repository_root=root
        )
        if store_root is not None
        else actual_output_store.default_breadth_actual_output_store_root(root)
    )
    stored = actual_output_store.capture_breadth_actual_output(
        destination,
        bundle=bundle,
    )
    receipt = stored.capture_receipt
    return {
        "schema": "market_memory.breadth_capture_result.v1",
        "deployed_commit": commit,
        "store_profile": actual_output_store.STORE_PROFILE,
        "generation_id": stored.generation_id,
        "capture_id": receipt["capture_id"],
        "source_observation_id": stored.bundle.source_observation[
            "source_observation_id"
        ],
        "snapshot_id": stored.bundle.feature_object["snapshot_id"],
        "session": stored.bundle.feature_object["session"],
        "first_observed_at": receipt["clocks"]["first_observed_at"],
        "available_at": receipt["clocks"]["available_at"],
        "authority": {
            "context_only": receipt["authority"]["context_only"],
            "training_eligible": receipt["evidence_policy"]["training_eligible"],
            "promotion_eligible": receipt["evidence_policy"]["promotion_eligible"],
        },
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Capture private current-tip Market Memory breadth evidence"
    )
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=_ROOT,
        help="reviewed Macro checkout containing the canonical breadth inputs",
    )
    parser.add_argument(
        "--store-root",
        type=Path,
        default=None,
        help="private breadth store override (tests/operators only)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = capture_current_breadth(
        args.repository_root,
        store_root=args.store_root,
    )
    print(
        json.dumps(
            result,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
