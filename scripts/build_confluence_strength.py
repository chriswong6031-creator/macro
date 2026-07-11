"""scripts/build_confluence_strength — CLI for confluence strength + sequence + discovery.

Runs three steps in sequence after build_confluence_graph:
  1. confluence_strength  → data/neuralweb/confluence_strength.json  (R-V4-6)
  2. confluence_sequence  → data/neuralweb/confluence_tape.jsonl
                          + data/neuralweb/confluence_sequence.json  (R-V4-7)
  3. confluence_discovery → data/neuralweb/confluence_candidates.jsonl (R-V4-8)

Each step is fail-open: an exception logs a warning and allows the next step
to proceed.  Timing is printed per step (total budget target: < 30s on synthetic).

HARD LAW:
  All outputs are display-only.  No LLM anywhere.  Never gates, ranks, or raises.
  rotation-state × cycle-position pair is DON'T-TEST (DO_NOT_REBUILD).

Exit codes:
    0 — at least partial success (partial gaps are non-fatal)
    1 — total failure (all three steps failed)

Usage:
    python -m scripts.build_confluence_strength
    python -m scripts.build_confluence_strength --root /path/to/repo
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.neuralweb.confluence_strength import build_and_write as strength_write  # noqa: E402
from engine.neuralweb.confluence_sequence import (  # noqa: E402
    append_tape_and_build_sequence,
)
from engine.neuralweb.confluence_discovery import build_and_write as discovery_write  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("build_confluence_strength")


def _tick(label: str) -> float:
    """Print a timing tick start marker and return start time."""
    t = time.perf_counter()
    log.info("[timing] START %s", label)
    return t


def _tock(label: str, t0: float) -> None:
    elapsed = time.perf_counter() - t0
    log.info("[timing] END %s %.3fs", label, elapsed)
    print(f"[timing] {label}: {elapsed:.3f}s", flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build confluence strength + sequence + discovery artifacts."
    )
    parser.add_argument("--root", type=Path, default=None)
    args = parser.parse_args(argv)

    root = args.root
    if root is None:
        root = Path(__file__).resolve().parent.parent

    any_success = False
    total_t0 = time.perf_counter()

    # ── Step 1: confluence strength ──────────────────────────────────────────
    strength_payload: dict | None = None
    t0 = _tick("confluence_strength")
    try:
        strength_payload = strength_write(root=root)
        n_rows = len(strength_payload.get("rows") or [])
        n_gaps = len(strength_payload.get("gaps") or [])
        print(
            f"confluence_strength OK — rows={n_rows} gaps={n_gaps}",
            flush=True,
        )
        any_success = True
    except Exception as exc:  # noqa: BLE001
        log.warning("confluence_strength: FAILED — %s (non-fatal)", exc)
        print(f"::warning title=confluence_strength::FAILED: {exc}", flush=True)
        strength_payload = {"rows": [], "gaps": [str(exc)]}
    _tock("confluence_strength", t0)

    # ── Step 2: confluence sequence ──────────────────────────────────────────
    t0 = _tick("confluence_sequence")
    try:
        seq_payload = append_tape_and_build_sequence(
            strength_payload=strength_payload or {"rows": [], "gaps": []},
            root=root,
        )
        n_subjects = len(seq_payload.get("subjects") or [])
        n_pairs = len(seq_payload.get("contradiction_pairs") or [])
        n_tape = seq_payload.get("n_tape_rows", 0)
        n_gaps = len(seq_payload.get("gaps") or [])
        print(
            f"confluence_sequence OK — subjects={n_subjects} pairs={n_pairs} "
            f"tape_rows={n_tape} gaps={n_gaps}",
            flush=True,
        )
        any_success = True
    except Exception as exc:  # noqa: BLE001
        log.warning("confluence_sequence: FAILED — %s (non-fatal)", exc)
        print(f"::warning title=confluence_sequence::FAILED: {exc}", flush=True)
    _tock("confluence_sequence", t0)

    # ── Step 3: confluence discovery ─────────────────────────────────────────
    t0 = _tick("confluence_discovery")
    try:
        candidates = discovery_write(root=root)
        n_candidates = len(candidates)
        n_accruing = sum(1 for c in candidates if c.get("state") == "accruing")
        n_cands = sum(1 for c in candidates if c.get("state") == "candidate")
        print(
            f"confluence_discovery OK — candidates={n_candidates} "
            f"(accruing={n_accruing} candidate={n_cands})",
            flush=True,
        )
        any_success = True
    except Exception as exc:  # noqa: BLE001
        log.warning("confluence_discovery: FAILED — %s (non-fatal)", exc)
        print(f"::warning title=confluence_discovery::FAILED: {exc}", flush=True)
    _tock("confluence_discovery", t0)

    total_elapsed = time.perf_counter() - total_t0
    print(f"[timing] total: {total_elapsed:.3f}s", flush=True)

    if not any_success:
        log.error("All three confluence strength steps failed.")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
