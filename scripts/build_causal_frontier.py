"""scripts/build_causal_frontier.py — CHF W3: Nightly frontier + surprise + lab state.

Nightly drift-only step (no batteries, no LLM, no TrialLedger writes).

Produces:
  data/neuralweb/causal_frontier.json          — coverage map with value scores
  data/neuralweb/causal_surprise_queue.jsonl   — surprise tickets (absent sources → none)
  data/neuralweb/causal_lab_state.json         — heartbeat + funnel + frontier summary
  site/neuralwebdata/causal_lab_state.json     — byte-identical site copy

Usage
-----
    python -m scripts.build_causal_frontier [--root PATH]

Exit codes
----------
0 — all artifacts written.
1 — unexpected failure (partial writes may exist).

The caller may wrap with:
    || echo "::warning::build_causal_frontier failed (non-fatal)"
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.neuralweb.causal_frontier import (
    _EDGES_PATH,
    _FRONTIER_PATH,
    _LAB_STATE_PATH,
    _SITE_LAB_STATE_PATH,
    _SURPRISE_QUEUE_PATH,
    build_all,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("build_causal_frontier")


def _write_json(path: Path, data: dict) -> None:
    """Write JSON artifact (creates parent dirs)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    """Write JSONL artifact (creates parent dirs, full overwrite)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(r, default=str) for r in rows]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "CHF W3: Nightly frontier + surprise queue + lab state builder. "
            "No batteries, no LLM — deterministic drift-only step."
        )
    )
    parser.add_argument("--root", type=Path, default=None,
                        help="Repo root (default: auto-detected from script location)")
    args = parser.parse_args(argv)

    root = args.root if args.root is not None else Path(__file__).resolve().parent.parent

    log.info("build_causal_frontier: root=%s", root)

    try:
        frontier, surprise_queue, lab_state = build_all(root=root)
    except Exception as exc:
        log.error("build_causal_frontier: FAILED — %s", exc)
        return 1

    # Write frontier
    frontier_path = root / _FRONTIER_PATH
    try:
        _write_json(frontier_path, frontier)
        log.info("build_causal_frontier: wrote %s (%d cells)", frontier_path, frontier.get("total_cells", 0))
    except Exception as exc:
        log.error("build_causal_frontier: could not write frontier — %s", exc)
        return 1

    # Write surprise queue
    sq_path = root / _SURPRISE_QUEUE_PATH
    try:
        _write_jsonl(sq_path, surprise_queue)
        log.info("build_causal_frontier: wrote %s (%d tickets)", sq_path, len(surprise_queue))
    except Exception as exc:
        log.error("build_causal_frontier: could not write surprise queue — %s", exc)
        return 1

    # Write lab state (data/ copy)
    lab_state_path = root / _LAB_STATE_PATH
    lab_state_json = json.dumps(lab_state, indent=2, default=str)
    try:
        lab_state_path.parent.mkdir(parents=True, exist_ok=True)
        lab_state_path.write_text(lab_state_json, encoding="utf-8")
        log.info("build_causal_frontier: wrote %s", lab_state_path)
    except Exception as exc:
        log.error("build_causal_frontier: could not write lab_state (data/) — %s", exc)
        return 1

    # Write lab state (site/ copy — byte-identical)
    site_path = root / _SITE_LAB_STATE_PATH
    try:
        site_path.parent.mkdir(parents=True, exist_ok=True)
        site_path.write_text(lab_state_json, encoding="utf-8")
        log.info("build_causal_frontier: wrote site copy %s", site_path)
    except Exception as exc:
        log.error("build_causal_frontier: could not write lab_state (site/) — %s", exc)
        return 1

    # Print summary
    width = frontier.get("cumulative_causal_scan_width", 0)
    state_summary = frontier.get("state_summary", {})
    print(
        f"[build_causal_frontier] frontier: {frontier.get('total_cells', 0)} cells "
        f"({state_summary}), surprise_queue: {len(surprise_queue)} tickets, "
        f"cumulative_scan_width: {width}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
