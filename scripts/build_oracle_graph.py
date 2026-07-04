"""Build the Oracle rotation graph (O1) — edges, lead-lag tensor, routing matrix.

Reads:
  data/oracle/panel_s.parquet    — Tier S (sector ETFs, 1998→)
  data/oracle/panel_m.parquet    — Tier M (subsectors + themes + baskets, 2021→)
  data/oracle/rotation_groups.json — hand-named complex backbone (VERSION 1)

Writes (gitignored, published to R2 per D5 in the masterplan):
  data/oracle/graph_s.json       — graph built on Tier-S panel
  data/oracle/graph_m.json       — graph built on Tier-M panel

IMPORTANT: This script runs ON THE MAC off the nightly render path.  Do NOT
wire it into the render pipeline.  Artifacts should eventually be published
to R2 (per D5 in the masterplan) — that step is NOT in this PR.

Usage
-----
  python scripts/build_oracle_graph.py [--tier {s,m,all}] [--data-dir PATH]
                                        [--cut-height FLOAT] [--lag-max INT]

  --tier s/m/all     which tier to build (default: all)
  --data-dir PATH    override data directory (default: lib.config.data_dir())
  --cut-height FLOAT agglomerative cluster cut height (default: CONFIG value)
  --lag-max INT      max lead-lag (days, default: CONFIG value)

Design notes
------------
* Mirrors build_oracle_panel.py exactly in data-path resolution:
    _DATA_DIR_OVERRIDE → lib.config.data_dir() fallback, set once in main().
* Only numpy + pandas; no scipy / sklearn / networkx.
* For Tier M (354 nodes), pairwise edges are O(n^2) ~ 62k pairs — expect
  measured ~6s for all 62k Tier-M pair edges after the tail-corr fix; the stability/cluster passes add O(n^2) work — expect a few minutes total on Tier-M.  Use --tier s for fast dev iterations.
* Outputs are gitignored (graph_*.json are heavy; large panels + long history
  produce ~MB-sized JSON). They go to R2 in P7.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib import config  # noqa: E402
from engine.oracle.graph import build_graph, CONFIG  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

_DATA_DIR_OVERRIDE: Path | None = None


def _data_dir() -> Path:
    return _DATA_DIR_OVERRIDE if _DATA_DIR_OVERRIDE is not None else config.data_dir()


def _out_dir() -> Path:
    d = _data_dir() / "oracle"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _load_backbone(data_dir: Path) -> dict:
    """Load rotation_groups.json backbone."""
    p = data_dir / "oracle" / "rotation_groups.json"
    if not p.exists():
        # Fallback: check repo root data/oracle
        p = ROOT / "data" / "oracle" / "rotation_groups.json"
    if not p.exists():
        raise FileNotFoundError(
            f"rotation_groups.json not found at {p}. "
            "Ensure data/oracle/rotation_groups.json is committed to the repo."
        )
    log.info("Loading backbone: %s", p)
    return json.loads(p.read_text())


def build_tier(tier: str, args: argparse.Namespace) -> None:
    data_dir = _data_dir()
    panel_path = data_dir / "oracle" / f"panel_{tier}.parquet"

    if not panel_path.exists():
        log.error("Panel not found: %s — build it first with build_oracle_panel.py", panel_path)
        raise FileNotFoundError(panel_path)

    log.info("Loading panel_%s (%s)...", tier, panel_path)
    panel = pd.read_parquet(panel_path)
    if panel.empty:
        log.warning("Panel tier=%s is empty — skipping graph build", tier)
        return

    log.info("Panel tier=%s: %d rows, %d nodes",
             tier, len(panel),
             panel.index.get_level_values("node").nunique())

    backbone = _load_backbone(data_dir)

    # Config overrides from CLI
    cfg = dict(CONFIG)
    if args.cut_height is not None:
        cfg["CLUSTER_CUT_HEIGHT"] = args.cut_height
        log.info("Cluster cut height override: %.2f", args.cut_height)
    if args.lag_max is not None:
        cfg["LEADLAG_MAX_LAG"] = args.lag_max
        log.info("Lead-lag max override: %d", args.lag_max)

    log.info("Building graph (tier=%s)...", tier)
    graph = build_graph(panel, backbone, cfg)

    # Annotate with build metadata
    graph["_meta"] = {
        "tier": tier,
        "built_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "panel_rows": len(panel),
        "node_count": graph.get("node_count", 0),
        "asof": graph.get("asof", "unknown"),
        "backbone_version": backbone.get("_meta", {}).get("version", "unknown"),
        "args": {
            "tier": args.tier,
            "data_dir": str(args.data_dir) if args.data_dir else None,
            "cut_height": args.cut_height,
            "lag_max": args.lag_max,
        },
    }

    out = _out_dir() / f"graph_{tier}.json"
    out.write_text(json.dumps(graph, indent=2, default=str))
    log.info("Written: %s (%d bytes)", out, out.stat().st_size)

    # Print summary
    n_edges = len(graph.get("edges", []))
    n_stable = sum(1 for e in graph.get("edge_stability", []) if e.get("stable"))
    n_clusters = len(graph.get("clusters", []))
    n_routing_sources = len([k for k in graph.get("routing", {}) if not k.startswith("_")])
    log.info(
        "Summary tier=%s: %d node pairs, %d stable edges, %d clusters, %d routing sources",
        tier, n_edges, n_stable, n_clusters, n_routing_sources,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tier", choices=["s", "m", "all"], default="all",
                        help="Which tier to build (default: all)")
    parser.add_argument("--data-dir", default=None, metavar="PATH",
                        help="Override data directory (off-render-path runs from "
                             "a worktree read the MAIN checkout's stores)")
    parser.add_argument("--cut-height", type=float, default=None, metavar="FLOAT",
                        help="Agglomerative cluster cut height (default: CONFIG value)")
    parser.add_argument("--lag-max", type=int, default=None, metavar="INT",
                        help="Maximum lead-lag in days (default: CONFIG value)")
    args = parser.parse_args()

    if args.data_dir:
        global _DATA_DIR_OVERRIDE
        _DATA_DIR_OVERRIDE = Path(args.data_dir)
        log.info("data dir override: %s", _DATA_DIR_OVERRIDE)

    if args.tier in ("s", "all"):
        log.info("=== Tier S ===")
        build_tier("s", args)

    if args.tier in ("m", "all"):
        log.info("=== Tier M ===")
        build_tier("m", args)

    log.info("Done.")


if __name__ == "__main__":
    main()
