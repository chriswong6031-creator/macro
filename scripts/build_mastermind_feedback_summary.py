"""Thin CLI wrapper: build Mastermind → NW reverse feedback summary artifact.

Usage
-----
    python -m scripts.build_mastermind_feedback_summary [--root REPO_ROOT]

Exit codes
----------
0 — artifact written (gaps are printed but do not cause non-zero exit).
    Also exits 0 when source is absent/stale (graceful degradation per FB-R14).
1 — total failure to write the artifact (OSError only).

Resilient: the caller wraps with
    || echo "::warning::build_mastermind_feedback_summary failed (non-fatal)"
so CI continues even if this step fails.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.neuralweb.mastermind_feedback import build_and_write  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("build_mastermind_feedback_summary")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build data/governance/mastermind_feedback_summary.json "
            "from site/mastermind/nw_feedback.json (Mastermind → NW reverse bridge)."
        )
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
        log.error("mastermind_feedback: FAILED to write artifact — %s", exc)
        return 1
    except Exception as exc:  # noqa: BLE001
        log.error("mastermind_feedback: unexpected error — %s", exc)
        return 1

    state = payload.get("state", "unknown")
    gaps: list[str] = payload.get("gap_notes") or []

    if gaps:
        print(f"mastermind_feedback: state={state} — {len(gaps)} gap(s):")
        for g in gaps:
            print(f"  - {g}")
    else:
        print(f"mastermind_feedback: state={state} — no gaps")

    # Summary line for CI log visibility
    totals = payload.get("totals") or {}
    n_books = totals.get("n_books", 0) if isinstance(totals, dict) else 0
    per_book = payload.get("per_book") or []
    produced_at = payload.get("generated_utc", "?")
    source_schema = payload.get("source_schema", "?")
    print(
        f"mastermind_feedback OK — state={state} books={n_books} "
        f"per_book={len(per_book)} gaps={len(gaps)} "
        f"source_schema={source_schema} produced_at={produced_at}"
    )

    root = args.root if args.root else Path(__file__).resolve().parent.parent
    out_path = root / "data" / "governance" / "mastermind_feedback_summary.json"
    print(f"written: {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
