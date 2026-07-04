"""scripts/build_kernel_diagnostics — CLI for Neural Web W3 PR3 diagnostics.

Runs BOTH diagnostics in sequence:
  A. decay curves  → data/neuralweb/kernel_families.json
  B. lagging-signal detector → data/neuralweb/lagging_signals.json

Each step is resilient: a failure in one step is logged + reported but does
NOT abort the other step.  The script exits 0 unless BOTH steps fail.

Usage:
  python -m scripts.build_kernel_diagnostics
  python -m scripts.build_kernel_diagnostics --root /path/to/repo
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


def _run_decay(root: Path | str | None) -> bool:
    """Run decay-curve diagnostics.  Returns True on success."""
    try:
        from engine.neuralweb.decay import write_families  # noqa: PLC0415
        stats = write_families(root)
        log.info(
            "decay: wrote %d families to %s (generated_from=%s)",
            stats.get("n_families", 0),
            stats.get("output_path", "?"),
            stats.get("generated_from", "?"),
        )
        print(
            f"[decay] {stats.get('n_families', 0)} families "
            f"→ {stats.get('output_path', '?')}",
            flush=True,
        )
        return True
    except Exception as e:  # noqa: BLE001
        log.error("decay step failed: %s", e, exc_info=True)
        print(f"[decay] FAILED: {e}", flush=True)
        return False


def _run_lagging(root: Path | str | None) -> bool:
    """Run lagging-signal detector.  Returns True on success."""
    try:
        from engine.neuralweb.lagging import write_lagging  # noqa: PLC0415
        stats = write_lagging(root)
        log.info(
            "lagging: wrote %d families / %d recent fires to %s (gaps: %d)",
            stats.get("n_families", 0),
            stats.get("total_recent_fires", 0),
            stats.get("output_path", "?"),
            len(stats.get("gaps", [])),
        )
        print(
            f"[lagging] {stats.get('n_families', 0)} families / "
            f"{stats.get('total_recent_fires', 0)} recent fires "
            f"→ {stats.get('output_path', '?')} "
            f"(gaps: {len(stats.get('gaps', []))})",
            flush=True,
        )
        return True
    except Exception as e:  # noqa: BLE001
        log.error("lagging step failed: %s", e, exc_info=True)
        print(f"[lagging] FAILED: {e}", flush=True)
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Neural Web W3 PR3 — decay curves + lagging-signal detector"
    )
    parser.add_argument(
        "--root",
        default=None,
        help="Repository root (default: auto-detect via lib.config)",
    )
    args = parser.parse_args(argv)
    root = Path(args.root) if args.root else None

    ok_decay = _run_decay(root)
    ok_lagging = _run_lagging(root)

    if ok_decay and ok_lagging:
        log.info("build_kernel_diagnostics: both steps complete")
        return 0
    elif not ok_decay and not ok_lagging:
        log.error("build_kernel_diagnostics: both steps FAILED")
        return 1
    else:
        failed = "decay" if not ok_decay else "lagging"
        log.warning("build_kernel_diagnostics: %s step failed (partial success)", failed)
        # Exit 0 — resilient wrapper; partial success is reported via warnings
        return 0


if __name__ == "__main__":
    sys.exit(main())
