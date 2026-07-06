"""CLI wrapper: build the NW lobe-status health artifact.

Usage
-----
    python -m scripts.build_neuralweb_health [--root REPO_ROOT]
    python -m scripts.build_neuralweb_health --refresh-cortex [--root REPO_ROOT]

Modes
-----
Full build (default):
    Builds the complete health.json from synapse.yml + all lobe artifacts.
    cortex_source = 'previous_run' (reads the last committed cortex memo).
    Writes data/neuralweb/health.json + site/neuralwebdata/health.json.

Cortex refresh (--refresh-cortex):
    Loads existing data/neuralweb/health.json.
    Recomputes ONLY the cortex section + overall_status + produced_at.
    Sets cortex_source = 'current_run' (current run's memo is now present).
    Rewrites both copies.
    Falls back to a full build if no existing health.json found.

Exit codes
----------
0 — artifact written (partial per-lobe gaps are logged but do not cause non-zero exit).
0 — synapse.yml missing → exits 0 with a warning (fail-open).
1 — total failure to write the artifact.

Resilient: intended to be called as:
    python -m scripts.build_neuralweb_health || echo "::warning::..."
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.neuralweb.health import build, refresh_cortex, write  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("build_neuralweb_health")


def _repo_root(given: Path | None) -> Path:
    if given is not None:
        return given.resolve()
    return Path(__file__).resolve().parent.parent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build data/neuralweb/health.json — NW lobe-status surface."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Repo root (default: auto-detected from script location).",
    )
    parser.add_argument(
        "--refresh-cortex",
        action="store_true",
        help=(
            "Load existing health.json and recompute only the cortex section "
            "+ overall_status + produced_at (cortex_source='current_run'). "
            "Falls back to full build if no existing health.json."
        ),
    )
    args = parser.parse_args(argv)
    root = _repo_root(args.root)

    try:
        if args.refresh_cortex:
            data_path = root / "data" / "neuralweb" / "health.json"
            if data_path.exists():
                try:
                    existing = json.loads(data_path.read_text(encoding="utf-8"))
                    payload = refresh_cortex(existing, root=root)
                    log.info("build_neuralweb_health: refresh-cortex mode (cortex_source=current_run)")
                except Exception as exc:  # noqa: BLE001
                    log.warning("build_neuralweb_health: refresh-cortex load/merge failed (%s); falling back to full build", exc)
                    payload = build(root=root, cortex_source="current_run")
            else:
                log.warning("build_neuralweb_health: no existing health.json for --refresh-cortex; running full build")
                payload = build(root=root, cortex_source="current_run")
        else:
            payload = build(root=root, cortex_source="previous_run")
            log.info("build_neuralweb_health: full build (cortex_source=previous_run)")

        write(payload, root=root)

        overall = payload.get("overall_status", "?")
        counts = payload.get("summary_counts", {})
        log.info(
            "build_neuralweb_health: done — overall=%s lobes=%d stale=%d missing=%d",
            overall,
            counts.get("total_lobes", 0),
            counts.get("stale", 0),
            counts.get("missing", 0),
        )
        return 0

    except Exception as exc:  # noqa: BLE001
        log.error("build_neuralweb_health: FAILED — %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
