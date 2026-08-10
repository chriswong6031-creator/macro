"""Capture one current SPY raw-close technical actual output privately.

This is the sole W1B.3B production writer.  The source URLs, symbol, feature,
calendar, identity, entitlement record, authority, and clocks are owned by the
reviewed projector/store contracts; callers may not override them.
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

from engine.neuralweb import market_memory_technical_observation as technical
from engine.neuralweb import market_memory_technical_store as technical_store

_COMMIT = re.compile(r"[a-f0-9]{40}(?:[a-f0-9]{24})?\Z")


class MarketMemoryTechnicalCaptureCliError(RuntimeError):
    """The deployed checkout cannot establish one exact technical capture."""


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
        raise MarketMemoryTechnicalCaptureCliError(
            "cannot resolve the deployed repository commit"
        ) from exc
    commit = result.stdout.strip()
    if not _COMMIT.fullmatch(commit):
        raise MarketMemoryTechnicalCaptureCliError(
            "deployed repository commit is malformed"
        )
    return commit


def capture_current_technical(
    repository_root: str | Path,
    *,
    store_root: str | Path | None = None,
) -> dict[str, Any]:
    """Fetch, project, and durably capture the current reviewed SPY tip."""

    root = Path(repository_root).expanduser().resolve()
    commit = _repository_commit(root)
    bundle = technical.build_current_spy_raw_close_ratio(
        root,
        pinned_commit=commit,
    )
    destination = (
        technical_store.validate_technical_actual_output_store_root(
            Path(store_root).expanduser(), repository_root=root
        )
        if store_root is not None
        else technical_store.default_technical_actual_output_store_root(root)
    )
    stored = technical_store.capture_technical_actual_output(
        destination,
        bundle=bundle,
    )
    receipt = stored.capture_receipt
    feature = stored.bundle.feature_object
    state = feature["state"]
    return {
        "schema": "market_memory.technical_capture_result.v1",
        "deployed_commit": commit,
        "store_profile": technical_store.STORE_PROFILE,
        "generation_id": stored.generation_id,
        "capture_id": receipt["capture_id"],
        "source_observation_id": stored.bundle.source_observation[
            "source_observation_id"
        ],
        "snapshot_id": feature["snapshot_id"],
        "session": feature["session"],
        "first_observed_at": receipt["clocks"]["first_observed_at"],
        "available_at": receipt["clocks"]["available_at"],
        "feature": state["feature"],
        "value": state["value"],
        "price_basis": {
            "raw_unadjusted": feature["price_basis"]["raw_unadjusted"],
            "split_adjusted": feature["price_basis"]["split_adjusted"],
            "dividend_adjusted": feature["price_basis"]["dividend_adjusted"],
            "economic_return": feature["price_basis"]["economic_return"],
        },
        "authority": {
            "context_only": receipt["authority"]["context_only"],
            "training_eligible": receipt["evidence_policy"]["training_eligible"],
            "promotion_eligible": receipt["evidence_policy"]["promotion_eligible"],
        },
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Capture private current-tip Market Memory technical evidence"
    )
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=_ROOT,
        help="reviewed Macro checkout containing pinned identity/calendar evidence",
    )
    parser.add_argument(
        "--store-root",
        type=Path,
        default=None,
        help="private technical store override (tests/operators only)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = capture_current_technical(
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
