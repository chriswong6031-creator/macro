"""Build the Oracle rotation panel (O0) — Tier S and/or Tier M.

Reads data from the Mac data stores (data/yahoo, data/massive_stock_day,
data/breadth, data/themes_heatmap, site/basketdata) and writes:

  data/oracle/panel_s.parquet   — Tier S (sector ETFs, 1998→, survivorship-clean)
  data/oracle/panel_m.parquet   — Tier M (268 subsectors + 40 themes + 46 baskets,
                                           2021-07→, survivorship-FLAGGED)
  data/oracle/manifest.json     — spans, node counts, per-tier coverage stats

IMPORTANT: This script runs ON THE MAC off the nightly render path.  Do NOT
wire it into the render pipeline.  Artifacts should eventually be published
to R2 (per D5 in the masterplan) but that step is NOT in this PR.

Usage
-----
  python scripts/build_oracle_panel.py [--tier {s,m,all}] [--start YYYY-MM-DD]
                                       [--end YYYY-MM-DD] [--limit N]

  --limit N   cap the number of member tickers loaded per sector/node (smoke
              run; does NOT change the ETF-level Tier-S spine, only member legs)

Design notes
------------
* Efficient: loads each ticker parquet at most once per tier, builds one
  wide closes/volume matrix per tier, vectorizes feature computation.
* Manifest: records schema version, spans, node counts, per-node coverage
  (fraction of members with prices in the store), and per-tier survivorship
  status.
* No network calls; offline-safe.
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
from engine.oracle.panel import (  # noqa: E402
    COLUMN_SCHEMA,
    SECTOR_ETFS,
    ETF_TO_SECTOR,
    build_panel_s,
    build_panel_m,
    build_panel_f,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# --data-dir override for off-render-path runs: the heavy stores
# (massive_stock_day) live only in the MAIN checkout's data/, while this
# script often runs from a worktree whose data/ carries just the committed
# files. Set once by main() before any build; None = config default.
_DATA_DIR_OVERRIDE: Path | None = None


def _data_dir() -> Path:
    return _DATA_DIR_OVERRIDE if _DATA_DIR_OVERRIDE is not None else config.data_dir()


def _out_dir() -> Path:
    d = _data_dir() / "oracle"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _coverage_stats(panel: pd.DataFrame, tier: str) -> dict:
    """Compute per-tier coverage statistics for the manifest."""
    if panel.empty:
        return {"tier": tier, "node_count": 0, "date_range": None,
                "rows": 0, "null_rates": {}}

    nodes = panel.index.get_level_values("node").unique().tolist()
    dates = panel.index.get_level_values("date")
    date_min = str(dates.min().date()) if len(dates) else None
    date_max = str(dates.max().date()) if len(dates) else None

    # Per-column null rate
    null_rates = {col: float(panel[col].isna().mean())
                  for col in COLUMN_SCHEMA if col in panel.columns}

    return {
        "tier": tier,
        "node_count": len(nodes),
        "nodes": nodes,
        "date_range": [date_min, date_max],
        "rows": len(panel),
        "null_rates": {k: round(v, 4) for k, v in null_rates.items()},
    }


def _member_coverage(
    nodes_members: dict[str, list[str]],
    closes_dir: Path,
) -> dict[str, float]:
    """Fraction of members in each node that have a price file."""
    out: dict[str, float] = {}
    for node, tickers in nodes_members.items():
        if not tickers:
            out[node] = 0.0
            continue
        present = sum(1 for t in tickers if (closes_dir / f"{t}.parquet").exists())
        out[node] = round(present / len(tickers), 3)
    return out


def build_s(args: argparse.Namespace) -> pd.DataFrame:
    data_dir = _data_dir()
    yahoo_dir = data_dir / "yahoo"
    massive_dir = data_dir / "massive_stock_day"
    pit_path = data_dir / "breadth" / "sp1500_pit_membership.parquet"

    if not pit_path.exists():
        log.error("PIT membership not found: %s", pit_path)
        raise FileNotFoundError(pit_path)

    log.info("Loading PIT membership (%s)...", pit_path)
    pit_membership = pd.read_parquet(pit_path)

    # Sector labels = UNION of the three current constituent files (sp500 +
    # sp400 + sp600) so the member legs cover the full current SP1500, not just
    # the S&P 500 (which silently dropped 80.6% of the PIT spine — review fix).
    # First-seen wins on the rare cross-file duplicate symbol.
    frames = []
    for sub in ("breadth", "midcap_breadth", "smallcap_breadth"):
        cp = data_dir / sub / "constituents.parquet"
        if cp.exists():
            log.info("Loading constituents (%s)...", cp)
            frames.append(pd.read_parquet(cp))
        else:
            log.warning("constituents missing: %s (label coverage shrinks)", cp)
    if frames:
        constituents = pd.concat(frames)
        constituents = constituents[~constituents.index.duplicated(keep="first")]
    else:
        constituents = pd.DataFrame(columns=["name", "sector"])

    log.info("Building Tier S panel (start=%s end=%s limit=%s)...",
             args.start or "earliest", args.end or "latest", args.limit)

    panel = build_panel_s(
        yahoo_dir=yahoo_dir,
        massive_dir=massive_dir,
        pit_membership=pit_membership,
        constituents=constituents,
        start=args.start,
        end=args.end,
        limit_tickers=args.limit,
    )

    if panel.empty:
        log.warning("Tier S panel is empty — check data paths")
    else:
        log.info("Tier S: %d rows × %d cols, nodes=%d",
                 len(panel), len(panel.columns),
                 panel.index.get_level_values("node").nunique())
        out = _out_dir() / "panel_s.parquet"
        panel.to_parquet(out)
        log.info("Written: %s", out)

    return panel


def build_m(args: argparse.Namespace) -> pd.DataFrame:
    data_dir = _data_dir()
    yahoo_dir = data_dir / "yahoo"
    massive_dir = data_dir / "massive_stock_day"
    themes_path = data_dir / "themes_heatmap" / "themes_tree.json"
    baskets_path = ROOT / "site" / "basketdata" / "baskets.json"

    if not themes_path.exists():
        log.error("themes_tree.json not found: %s", themes_path)
        raise FileNotFoundError(themes_path)

    log.info("Loading themes_tree.json...")
    themes_tree = json.loads(themes_path.read_text())

    baskets_data: list[dict] = []
    if baskets_path.exists():
        log.info("Loading baskets.json...")
        raw = json.loads(baskets_path.read_text())
        baskets_data = raw.get("baskets", [])
    else:
        log.warning("baskets.json not found — basket nodes skipped")

    log.info("Building Tier M panel (start=%s end=%s limit=%s)...",
             args.start or "2021-07-06", args.end or "latest", args.limit)

    panel = build_panel_m(
        yahoo_dir=yahoo_dir,
        massive_dir=massive_dir,
        themes_tree=themes_tree,
        baskets_data=baskets_data,
        start=args.start,
        end=args.end,
        limit_tickers=args.limit,
    )

    if panel.empty:
        log.warning("Tier M panel is empty — check data paths")
    else:
        log.info("Tier M: %d rows × %d cols, nodes=%d",
                 len(panel), len(panel.columns),
                 panel.index.get_level_values("node").nunique())
        out = _out_dir() / "panel_m.parquet"
        panel.to_parquet(out)
        log.info("Written: %s", out)

    return panel


def build_f(args: argparse.Namespace) -> pd.DataFrame:
    data_dir = _data_dir()
    yahoo_dir = data_dir / "yahoo"

    log.info("Building Tier F panel (start=%s end=%s)...",
             args.start or "2013-04-16", args.end or "latest")

    panel = build_panel_f(
        yahoo_dir=yahoo_dir,
        start=args.start or "2013-04-16",
        end=args.end,
    )

    if panel.empty:
        log.warning("Tier F panel is empty - check yahoo_dir for factor + SPY parquets")
    else:
        log.info("Tier F: %d rows x %d cols, nodes=%d",
                 len(panel), len(panel.columns),
                 panel.index.get_level_values("node").nunique())
        out = _out_dir() / "panel_f.parquet"
        panel.to_parquet(out)
        log.info("Written: %s", out)

    return panel


def write_manifest(
    panel_s: pd.DataFrame | None,
    panel_m: pd.DataFrame | None,
    panel_f: pd.DataFrame | None,
    args: argparse.Namespace,
) -> None:
    data_dir = _data_dir()
    massive_dir = data_dir / "massive_stock_day"

    manifest: dict = {
        "schema_version": 1,
        "built_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "args": {
            "tier": args.tier,
            "start": args.start,
            "end": args.end,
            "limit": args.limit,
        },
        "column_schema": COLUMN_SCHEMA,
        "sector_label_caveat": (
            "GICS sector labels = UNION of current sp500/sp400/sp600 constituent "
            "files (99.1% of ACTIVE PIT-spine tickers labeled at build time). "
            "Two biases on the per-member cohesion/breadth/turnover legs: "
            "(a) labels-applied-backward (current sector carried back in time); "
            "(b) LABEL SURVIVORSHIP — names that left the index universe before "
            "the label snapshot are unlabeled and excluded, concentrated in the "
            "earliest panel years.  ETF-level legs are unaffected."
        ),
        "survivorship_note": {
            "tier_s": (
                "ETF-level columns: survivorship-CLEAN (11 real sector ETFs, "
                "1998→).  Member-derived legs (cohesion/breadth_50/turnover_z): "
                "PIT membership intervals honored (union of ALL intervals per "
                "ticker), but restricted to names labelable today (current "
                "SP1500 union) — NOT fully survivorship-clean; see "
                "sector_label_caveat. "
                "C1/C4 columns (stochrsi_w_k/d, washout_w, cohesion_rebuild): "
                "computed on ETF close = survivorship-CLEAN back to 1998; "
                "cohesion_rebuild additionally requires cohesion_chg which is "
                "member-derived (same NULL-before-2021 caveat as cohesion)."
            ),
            "tier_m": (
                "Survivorship-FLAGGED: themes_tree.json is current-only (single commit "
                "2026-06).  Subsector and theme EW indices are reconstructed from "
                "today's member list — past composition unverified.  Basket nodes "
                "honor PIT added-dates per member (declared hindsight 2023-05-09+). "
                "NEVER promote a Tier-M backtest result without this watermark. "
                "C1/C4 oscillator columns carry the same FLAGGED status."
            ),
        },
    }

    if panel_s is not None and not panel_s.empty:
        # Per-sector member coverage vs massive store
        from engine.oracle.panel import ETF_TO_SECTOR
        # Use pit_membership to map sectors to tickers is expensive here;
        # report ETF-level coverage directly
        etf_present = {t: (data_dir / "yahoo" / f"{t}.parquet").exists()
                       for t in SECTOR_ETFS}
        manifest["tier_s"] = {
            **_coverage_stats(panel_s, "s"),
            "etf_coverage": etf_present,
        }

    if panel_m is not None and not panel_m.empty:
        manifest["tier_m"] = _coverage_stats(panel_m, "m")

    if panel_f is not None and not panel_f.empty:
        manifest["tier_f"] = _coverage_stats(panel_f, "f")

    out = _out_dir() / "manifest.json"
    out.write_text(json.dumps(manifest, indent=2, default=str))
    log.info("Manifest written: %s", out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tier", choices=["s", "m", "f", "all"], default="all",
                        help="Which tier to build (default: all)")
    parser.add_argument("--start", default=None, metavar="YYYY-MM-DD",
                        help="Start date (inclusive)")
    parser.add_argument("--end", default=None, metavar="YYYY-MM-DD",
                        help="End date (inclusive)")
    parser.add_argument("--limit", type=int, default=None, metavar="N",
                        help="Cap member ticker loads per node (smoke run)")
    parser.add_argument("--data-dir", default=None, metavar="PATH",
                        help="Override the data directory (off-render-path runs "
                             "from a worktree read the MAIN checkout's stores)")
    args = parser.parse_args()

    if args.data_dir:
        global _DATA_DIR_OVERRIDE
        _DATA_DIR_OVERRIDE = Path(args.data_dir)
        log.info("data dir override: %s", _DATA_DIR_OVERRIDE)

    panel_s: pd.DataFrame | None = None
    panel_m: pd.DataFrame | None = None
    panel_f: pd.DataFrame | None = None

    if args.tier in ("s", "all"):
        log.info("=== Tier S ===")
        panel_s = build_s(args)

    if args.tier in ("m", "all"):
        log.info("=== Tier M ===")
        panel_m = build_m(args)

    if args.tier in ("f", "all"):
        log.info("=== Tier F ===")
        panel_f = build_f(args)

    log.info("Writing manifest...")
    write_manifest(panel_s, panel_m, panel_f, args)
    log.info("Done.")


if __name__ == "__main__":
    main()
