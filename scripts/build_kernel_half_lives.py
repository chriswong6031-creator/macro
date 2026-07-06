"""scripts/build_kernel_half_lives — CLI for W2 "Measured Half-Lives".

Reads kernel_estimates.parquet + spine_index.parquet, fits per-family
decay curves (holding-horizon only; staleness declared unmeasured),
writes data/neuralweb/half_life.json.

PLACEMENT: daily.yml — between build_kernel_diagnostics and Confluence Graph.
OFF RENDER PATH: build_site.py reads the resulting JSON for display only.

SENTINEL LAW: this script ALWAYS writes half_life.json, even if all families
are null.  The "status":"fit_ran" key in the artifact distinguishes a
successful (all-null) run from a crashed job that wrote nothing.

Usage:
  python -m scripts.build_kernel_half_lives
  python -m scripts.build_kernel_half_lives --root /path/to/repo
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="W2 Signal Commons — measured holding-horizon half-lives"
    )
    parser.add_argument(
        "--root",
        default=None,
        help="Repository root (default: auto-detect via lib.config)",
    )
    args = parser.parse_args(argv)
    root = Path(args.root) if args.root else None

    try:
        from engine.neuralweb.half_life import write_half_lives  # noqa: PLC0415
        stats = write_half_lives(root)
        log.info(
            "half_lives: wrote %d families (%d measured) to %s",
            stats.get("n_families", 0),
            stats.get("n_measured", 0),
            stats.get("output_path", "?"),
        )
        print(
            f"[half_lives] {stats.get('n_families', 0)} families "
            f"({stats.get('n_measured', 0)} measured) "
            f"→ {stats.get('output_path', '?')}",
            flush=True,
        )
        if stats.get("n_measured", 0) == 0:
            # Expected: all-null result per B2/B4 findings; emit info not warning
            print(
                "[half_lives] INFO: all families unmeasured — expected (edge non-decaying "
                "or insufficient horizon points). This is the honest null.",
                flush=True,
            )
        return 0
    except Exception as e:  # noqa: BLE001
        log.error("half_lives: FAILED: %s", e, exc_info=True)
        print(f"[half_lives] FAILED: {e}", flush=True, file=sys.stderr)
        # SENTINEL: attempt to write a minimal status artifact even on failure
        try:
            import json
            from datetime import datetime, timezone

            if root is not None:
                out_dir = Path(root) / "data" / "neuralweb"
            else:
                try:
                    from lib import config  # noqa: PLC0415
                    out_dir = config.data_dir() / "neuralweb"
                except Exception:  # noqa: BLE001
                    out_dir = Path("data") / "neuralweb"

            out_dir.mkdir(parents=True, exist_ok=True)
            sentinel_payload = {
                "families": {},
                "status": "fit_failed",
                "produced_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "error": str(e),
            }
            (out_dir / "half_life.json").write_text(
                json.dumps(sentinel_payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            print("[half_lives] wrote sentinel half_life.json (status=fit_failed)", flush=True)
        except Exception as sentinel_err:  # noqa: BLE001
            log.error("half_lives: sentinel write also failed: %s", sentinel_err)

        # Emit ::warning so CI sees it but stays green (resilient wrapper pattern)
        print(
            f"::warning title=build_kernel_half_lives::FAILED — {e}",
            flush=True,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
