"""Ingest the trusted CPIAUCSL ALFRED snapshot into private Market Memory state.

This is the sole production intake command for the W1B.0 source pilot.  It does
not parse, validate, transform, or persist source bytes itself; those duties
remain in :mod:`engine.neuralweb.market_memory_sources`.  The command exposes no
HTTP route and prints only a bounded generation receipt, never source rows.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

_RELEASE_TARGET_ROOT = _REPO / "data" / "fred_vintage" / "release_targets"
_DEFAULT_MANIFEST = _RELEASE_TARGET_ROOT / "manifest.json"
_DEFAULT_ARTIFACT = _RELEASE_TARGET_ROOT / "CPIAUCSL_all_vintages.parquet"
_DEFAULT_STORE_ROOT = Path("/var/lib/macro-market-memory/state/sources")

log = logging.getLogger(__name__)


def ingest_market_memory_sources(
    *,
    store_root: str | Path = _DEFAULT_STORE_ROOT,
    manifest_path: str | Path = _DEFAULT_MANIFEST,
    artifact_path: str | Path = _DEFAULT_ARTIFACT,
) -> dict[str, Any]:
    """Call the engine-owned CPIAUCSL intake and return a safe run receipt."""

    # Import lazily so ``--help`` and deployment syntax checks remain usable
    # during a rolling checkout, while an actual run still fails closed if the
    # reviewed engine API is unavailable.
    from engine.neuralweb.market_memory_sources import intake_alfred_cpiaucsl

    stored = intake_alfred_cpiaucsl(
        store_root,
        manifest_path=manifest_path,
        artifact_path=artifact_path,
    )
    return {
        "schema": "market_memory.source_intake_run.v1",
        "status": "created" if stored.created else "already_present",
        "source_id": "fred_alfred:CPIAUCSL",
        "generation_id": stored.generation_id,
        "created": stored.created,
    }


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest the trusted CPIAUCSL ALFRED snapshot into private state"
    )
    parser.add_argument(
        "--store-root",
        type=Path,
        default=_DEFAULT_STORE_ROOT,
        help="Private source-store root (default: %(default)s)",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=_DEFAULT_MANIFEST,
        help="Canonical release-target collection manifest",
    )
    parser.add_argument(
        "--artifact",
        type=Path,
        default=_DEFAULT_ARTIFACT,
        help="Canonical CPIAUCSL all-vintages parquet",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        receipt = ingest_market_memory_sources(
            store_root=args.store_root,
            manifest_path=args.manifest,
            artifact_path=args.artifact,
        )
    except (ImportError, OSError, RuntimeError, ValueError) as exc:
        # Keep journald useful without echoing source rows, artifact contents,
        # private paths, or a validator message that might include any of them.
        log.error("Market Memory source intake failed (%s)", type(exc).__name__)
        return 1
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    raise SystemExit(main())
