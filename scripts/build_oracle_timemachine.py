"""Oracle P6 — Time Machine feed exporter.

Reads the pre-built oracle parquets (panel_s, panel_m, episodes_s, episodes_m)
and emits the frontend-ready JSON feed under site/oracledata/:

  tm_manifest.json          — tier metadata + node registry + chunk index
  tm_s_<YYYY-Qn>.json       — Tier-S (sector) quarterly chunk
  tm_m_<YYYYMmm>.json       — Tier-M (subsector) monthly chunk, DAILY granularity
  tm_episodes.json          — episode overlay feed + preset playlist

Tier-M chunks are now daily (all trading days, no Friday-only filter).  Chunks
are lazy-loaded per year by the UI, so per-chunk size is what matters — the total
uncompressed feed can be up to ~20 MB across all years without impacting load time.

This script runs OFF the 67-minute render path (same as build_oracle_panel.py).
Wire it into your nightly Mac cron or run manually after a panel rebuild.

Usage:
    python scripts/build_oracle_timemachine.py [--data-dir PATH]
                                               [--out-dir PATH]
                                               [--tier {s,m,all}]
                                               [--dry-run]

--data-dir  : override for the heavy data dir (default: config.data_dir()).
              Use the MAIN checkout path when running from a worktree.
--out-dir   : override for the output dir (default: site/oracledata/).
--tier      : which tier chunks to build (default: all).
--dry-run   : compute sizes only; do NOT write any files.
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
from engine.oracle.timemachine import (  # noqa: E402
    build_registry_s,
    build_registry_m,
    build_chunks_s,
    build_chunks_m,
    build_registry_f,
    build_chunks_f,
    build_episode_feed,
    build_manifest,
    rrg_transform,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

_DATA_DIR_OVERRIDE: Path | None = None


def _data_dir() -> Path:
    return _DATA_DIR_OVERRIDE if _DATA_DIR_OVERRIDE is not None else config.data_dir()


def _oracle_dir() -> Path:
    return _data_dir() / "oracle"


def _default_out_dir() -> Path:
    d = ROOT / "site" / "oracledata"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _load_parquets() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    od = _oracle_dir()
    log.info("Loading panel_s ...")
    panel_s = pd.read_parquet(od / "panel_s.parquet")
    log.info("Loading panel_m ...")
    panel_m = pd.read_parquet(od / "panel_m.parquet")
    log.info("Loading episodes_s ...")
    ep_s = pd.read_parquet(od / "episodes_s.parquet")
    log.info("Loading episodes_m ...")
    ep_m = pd.read_parquet(od / "episodes_m.parquet")
    return panel_s, panel_m, ep_s, ep_m


def _load_themes_tree() -> list[dict]:
    p = _data_dir() / "themes_heatmap" / "themes_tree.json"
    if not p.exists():
        log.warning("themes_tree.json not found: %s — theme mapping will be sparse", p)
        return []
    return json.loads(p.read_text())


def _load_names_zh() -> dict:
    p = _data_dir() / "themes_heatmap" / "names_zh.json"
    if not p.exists():
        log.warning("names_zh.json not found: %s — zh names will be null", p)
        return {}
    return json.loads(p.read_text())


def _load_baskets() -> list[dict]:
    p = ROOT / "site" / "basketdata" / "baskets.json"
    if not p.exists():
        log.warning("baskets.json not found — basket nodes will have sparse metadata")
        return []
    raw = json.loads(p.read_text())
    return raw.get("baskets", [])


def _write_json(path: Path, obj: object, dry_run: bool) -> int:
    """Serialise and (unless dry_run) write JSON; return byte count."""
    raw = json.dumps(obj, separators=(",", ":"), ensure_ascii=False)
    nbytes = len(raw.encode("utf-8"))
    if not dry_run:
        path.write_text(raw, encoding="utf-8")
    return nbytes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default=None, metavar="PATH",
                        help="Override data directory (worktree runs use MAIN checkout path)")
    parser.add_argument("--out-dir", default=None, metavar="PATH",
                        help="Override output directory (default: site/oracledata/)")
    parser.add_argument("--tier", choices=["s", "m", "f", "all"], default="all",
                        help="Which tier's chunks to build (default: all)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Compute and report sizes but do NOT write files")
    args = parser.parse_args()

    if args.data_dir:
        global _DATA_DIR_OVERRIDE
        _DATA_DIR_OVERRIDE = Path(args.data_dir)
        log.info("data dir override: %s", _DATA_DIR_OVERRIDE)

    out_dir = Path(args.out_dir) if args.out_dir else _default_out_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    log.info("Output dir: %s", out_dir)

    if args.dry_run:
        log.info("DRY RUN — no files will be written")

    # ── load inputs ────────────────────────────────────────────────────────
    panel_s, panel_m, ep_s, ep_m = _load_parquets()

    # Tier-F (factor rotation) — optional; absent parquet = tier silently omitted
    _od = _oracle_dir()
    panel_f = pd.read_parquet(_od / "panel_f.parquet") if (_od / "panel_f.parquet").exists() else pd.DataFrame()
    ep_f = pd.read_parquet(_od / "episodes_f.parquet") if (_od / "episodes_f.parquet").exists() else pd.DataFrame()

    # Desk-parity RRG coordinates (schema v3): replace the raw detection
    # features (1-day rs / accel_z) with the live rotation desk's smoothed
    # rs_ratio / rs_mom math so trails glide instead of jumping.
    log.info("Applying desk-parity RRG transform (schema v3) ...")
    panel_s = rrg_transform(panel_s)
    panel_m = rrg_transform(panel_m)
    if not panel_f.empty:
        panel_f = rrg_transform(panel_f)
    themes_tree = _load_themes_tree()
    names_zh = _load_names_zh()
    baskets_data = _load_baskets()

    # ── registries ─────────────────────────────────────────────────────────
    log.info("Building Tier-S registry ...")
    registry_s = build_registry_s(panel_s)
    log.info("Tier-S registry: %d nodes", len(registry_s))

    log.info("Building Tier-M registry ...")
    registry_m = build_registry_m(panel_m, themes_tree, names_zh, baskets_data)
    log.info("Tier-M registry: %d nodes", len(registry_m))

    registry_f = build_registry_f(panel_f) if not panel_f.empty else []
    log.info("Tier-F registry: %d nodes", len(registry_f))

    # ── chunks ─────────────────────────────────────────────────────────────
    total_bytes = 0
    chunks_s: list[dict] = []
    chunks_m: list[dict] = []
    chunks_f: list[dict] = []

    if args.tier in ("s", "all"):
        log.info("Building Tier-S quarterly chunks ...")
        chunks_s = build_chunks_s(panel_s, registry_s, period_key="Q")
        log.info("Tier-S: %d quarterly chunks", len(chunks_s))
        for chunk in chunks_s:
            fname = out_dir / f"tm_s_{chunk['period']}.json"
            chunk_obj = {"dates": chunk["dates"], "data": chunk["data"]}
            nbytes = _write_json(fname, chunk_obj, args.dry_run)
            total_bytes += nbytes
            log.info("  %s: %d dates, %.1f KB%s",
                     chunk["period"], len(chunk["dates"]), nbytes / 1024,
                     " (dry)" if args.dry_run else "")

    if args.tier in ("m", "all"):
        log.info("Building Tier-M monthly chunks ...")
        chunks_m = build_chunks_m(panel_m, registry_m, period_key="M")
        log.info("Tier-M: %d monthly chunks", len(chunks_m))
        for chunk in chunks_m:
            fname = out_dir / f"tm_m_{chunk['period']}.json"
            chunk_obj = {"dates": chunk["dates"], "data": chunk["data"]}
            nbytes = _write_json(fname, chunk_obj, args.dry_run)
            total_bytes += nbytes
            log.info("  %s: %d dates, %.1f KB%s",
                     chunk["period"], len(chunk["dates"]), nbytes / 1024,
                     " (dry)" if args.dry_run else "")

    # ── episode feed ───────────────────────────────────────────────────────
    if args.tier in ("f", "all") and not panel_f.empty:
        log.info("Building Tier-F quarterly chunks ...")
        chunks_f = build_chunks_f(panel_f, registry_f, period_key="Q")
        log.info("Tier-F: %d quarterly chunks", len(chunks_f))
        for chunk in chunks_f:
            fname = out_dir / f"tm_f_{chunk['period']}.json"
            chunk_obj = {"dates": chunk["dates"], "data": chunk["data"]}
            nbytes = _write_json(fname, chunk_obj, args.dry_run)
            total_bytes += nbytes

    log.info("Building episode feed ...")
    ep_feed = build_episode_feed(ep_m, ep_s, ep_f=ep_f if not ep_f.empty else None)
    ep_path = out_dir / "tm_episodes.json"
    nbytes = _write_json(ep_path, ep_feed, args.dry_run)
    total_bytes += nbytes
    log.info("Episodes: %d records, %d presets, %.1f KB%s",
             len(ep_feed["episodes"]), len(ep_feed["presets"]),
             nbytes / 1024, " (dry)" if args.dry_run else "")

    # ── manifest ───────────────────────────────────────────────────────────
    log.info("Writing manifest ...")
    manifest = build_manifest(registry_s, registry_m, chunks_s, chunks_m, registry_f=registry_f, chunks_f=chunks_f)
    mf_path = out_dir / "tm_manifest.json"
    nbytes = _write_json(mf_path, manifest, args.dry_run)
    total_bytes += nbytes
    log.info("Manifest: %.1f KB%s", nbytes / 1024, " (dry)" if args.dry_run else "")

    log.info("=" * 60)
    log.info("Total size: %.2f MB (%d bytes)", total_bytes / 1024 / 1024, total_bytes)
    # Tier-M chunks are daily and lazy-loaded per year by the UI; per-chunk size
    # is what matters, not the total.  Warning ceiling raised to 20 MB total.
    if total_bytes > 20 * 1024 * 1024:
        log.warning("OVER 20 MB BUDGET — check per-chunk sizes; individual chunks"
                    " should remain under 400 KB for fast lazy loading")
    else:
        log.info("Within 20 MB budget OK.")

    if not args.dry_run:
        log.info("Files written to: %s", out_dir)
        log.info("Chunk file list:")
        for f in sorted(out_dir.glob("tm_*.json")):
            log.info("  %s (%.1f KB)", f.name, f.stat().st_size / 1024)


if __name__ == "__main__":
    main()
