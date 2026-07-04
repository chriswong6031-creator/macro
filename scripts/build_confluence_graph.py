"""scripts/build_confluence_graph — CLI for Neural Web W4 confluence graph.

Builds data/neuralweb/confluence_graph.json from existing bus artifacts:
  - config/synapse.yml (feeds edges — structural wiring)
  - data/neuralweb/spine_index.parquet (engine nodes + co-firing lift)
  - site/basketdata/oracle_state.json (sector/episode nodes; READ-ONLY)
  - data/oracle/graph_s.json + graph_m.json (stable/leads edges; READ-ONLY)
  - data/oracle/rotation_groups.json (pair-c complex-sector mapping)
  - data/radar/theses.jsonl (thesis nodes)
  - data/regime/latest.json (pair-b, pair-f contradiction pairs)
  - data/market_state/latest.json (pair-a, pair-d)
  - site/intelligence/briefing.json (pair-e divergences — read-only ingest)
  - data/neuralweb/world_state.json (pairs a/b/d via composed truth)

HARD LAW (enforced in engine module):
    Confluence NEVER gates, NEVER ranks, NEVER raises a priority.
    All edges are display_only=True.  Cross-engine hard gates require their
    own pre-registered gauntlet (China falsification precedent).

Usage:
    python -m scripts.build_confluence_graph
    python -m scripts.build_confluence_graph --root /path/to/repo
    python -m scripts.build_confluence_graph --out /tmp/confluence_test.json

Exit codes:
    0 — artifact written (partial gaps logged but do not fail the step)
    1 — total failure to write the artifact

Designed to run AFTER 'build kernel diagnostics' in daily.yml engine job.
Resilient: caller wraps with || echo "::warning::..." so CI continues even
if this step fails.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# Allow running as a module from the repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.neuralweb.confluence import build_and_write  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("build_confluence_graph")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build data/neuralweb/confluence_graph.json — "
            "Neural Web W4 confluence graph (display-only)."
        )
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Repo root (default: auto-detected from script location).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output path (default: data/neuralweb/confluence_graph.json under root).",
    )
    args = parser.parse_args(argv)

    try:
        payload = build_and_write(root=args.root, out_path=args.out)
    except OSError as exc:
        log.error("confluence_graph: FAILED to write artifact — %s", exc)
        return 1
    except Exception as exc:  # noqa: BLE001
        log.error("confluence_graph: unexpected error — %s", exc)
        return 1

    # Summary output for CI logs
    gaps: list[str] = payload.get("gaps") or []
    nodes: list[dict] = payload.get("nodes") or []
    edges: list[dict] = payload.get("edges") or []
    contra = payload.get("contradiction_summary") or {}

    node_types: dict[str, int] = {}
    for n in nodes:
        t = n.get("type") or "unknown"
        node_types[t] = node_types.get(t, 0) + 1

    edge_types: dict[str, int] = {}
    for e in edges:
        t = e.get("edge_type") or "unknown"
        edge_types[t] = edge_types.get(t, 0) + 1

    if gaps:
        log.warning("confluence_graph: %d gap(s):", len(gaps))
        for g in gaps[:10]:
            log.warning("  - %s", g)
        if len(gaps) > 10:
            log.warning("  ... (%d more)", len(gaps) - 10)

    print(
        f"confluence_graph OK — "
        f"nodes={len(nodes)} ({node_types}) "
        f"edges={len(edges)} ({edge_types}) "
        f"contradictions={contra.get('n',0)} "
        f"gaps={len(gaps)} "
        f"produced_at={payload.get('produced_at','?')}",
        flush=True,
    )

    # Resolve output path for logging
    if args.out:
        dest = args.out
    else:
        root = args.root
        if root is None:
            root = Path(__file__).resolve().parent.parent
        dest = root / "data" / "neuralweb" / "confluence_graph.json"
    print(f"written: {dest}", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
