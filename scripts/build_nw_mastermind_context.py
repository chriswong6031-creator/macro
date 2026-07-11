"""Thin CLI wrapper: compose Neural Web → Mastermind context artifact.

Usage
-----
    python -m scripts.build_nw_mastermind_context [--root REPO_ROOT]

Exit codes
----------
0 — artifact written (partial gaps are printed but do not cause non-zero exit).
1 — total failure to write the artifact.

Resilient: the caller wraps with
    || echo "::warning::build_nw_mastermind_context failed (non-fatal)"
so CI continues even if this step fails.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.neuralweb.mastermind_context import build_and_write  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("build_nw_mastermind_context")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compose data/neuralweb/mastermind_context.json from NW stores."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Repo root (default: auto-detected from script location).",
    )
    args = parser.parse_args(argv)

    try:
        payload = build_and_write(root=args.root)
    except OSError as exc:
        log.error("mastermind_context: FAILED to write artifact — %s", exc)
        return 1
    except Exception as exc:  # noqa: BLE001
        log.error("mastermind_context: unexpected error — %s", exc)
        return 1

    gaps: list[str] = payload.get("gap_notes") or []
    if gaps:
        print(f"mastermind_context: PARTIAL — {len(gaps)} gap(s):")
        for g in gaps:
            print(f"  - {g}")
    else:
        print("mastermind_context: all sources read OK — no gaps")

    # Summary line for CI log visibility
    candidate_count = len(payload.get("candidate_context") or {})
    lobe_count = len(payload.get("lobes") or {})
    manifest_count = len(payload.get("lobe_manifest") or [])
    produced_at = payload.get("produced_at") or "?"
    print(
        f"mastermind_context OK — lobes={lobe_count} manifest={manifest_count} "
        f"candidates={candidate_count} gaps={len(gaps)} produced_at={produced_at}"
    )

    root = args.root if args.root else Path(__file__).resolve().parent.parent
    canonical = root / "data" / "neuralweb" / "mastermind_context.json"
    site_copy = root / "site" / "neuralwebdata" / "mastermind_context.json"
    print(f"written: {canonical}")
    print(f"written: {site_copy}")

    # NW→dashboards export lane (written by build_and_write, fail-open)
    plane_canonical = root / "data" / "neuralweb" / "market_plane.json"
    plane_site = root / "site" / "neuralwebdata" / "market_plane.json"
    if plane_canonical.exists():
        try:
            import json  # noqa: PLC0415
            plane = json.loads(plane_canonical.read_text(encoding="utf-8"))
            plane_gaps = plane.get("gaps") or []
            print(
                f"market_plane OK — asof={plane.get('asof')} stale={plane.get('stale')} "
                f"gaps={len(plane_gaps)} bytes={plane_canonical.stat().st_size}"
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("market_plane: summary read failed — %s", exc)
        print(f"written: {plane_canonical}")
        print(f"written: {plane_site}")
    else:
        print("::warning::market_plane.json not written (see log — non-fatal)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
