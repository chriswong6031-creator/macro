"""Build Oracle Pattern Memory (O3) — base rates + active episode analogues.

Reads:
  data/oracle/episodes_s.parquet
  data/oracle/episodes_m.parquet
  data/oracle/panel_s.parquet      (for RS trajectories)

Writes:
  data/oracle/memory_base_rates.json
  data/oracle/memory_active_analogues.json

Usage
-----
  python scripts/build_oracle_memory.py [--data-dir /path/to/data]
                                         [--k 7]
                                         [--tier {s,m,all}]

Design
------
* build_base_rates() produces the printed-truths tables per the P4 spec.
* find_analogues() computes kNN for each currently-ACTIVE episode
  (exhausted_date is NaT/null) — these are the episodes that are live today.
* Descriptive layer only (R4): no predictive claims; every aggregate carries
  "descriptive — analogue history, not a forecast."
* Hermetic on the Mac's canonical data/ store; no network calls.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.oracle.memory import (  # noqa: E402
    MEMORY_CFG,
    build_base_rates,
    find_analogues,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# JSON serialisation helpers
# ---------------------------------------------------------------------------

class _SafeEncoder(json.JSONEncoder):
    """Serialise numpy / pandas scalars + NaN → null."""
    def default(self, obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return None if np.isnan(obj) else float(obj)
        if isinstance(obj, np.bool_):
            return bool(obj)
        if isinstance(obj, (pd.Timestamp,)):
            return str(obj)[:10]
        return super().default(obj)

    def encode(self, obj):
        # Intercept NaN/Inf floats at the Python level
        if isinstance(obj, float):
            if obj != obj:  # NaN
                return "null"
            if obj == float("inf") or obj == float("-inf"):
                return "null"
        return super().encode(obj)

    def iterencode(self, obj, _one_shot=False):
        # Walk the dict/list tree and replace float NaN/Inf with None
        obj = _fix_floats(obj)
        return super().iterencode(obj, _one_shot)


def _fix_floats(obj):
    """Recursively replace NaN/Inf floats with None for JSON safety."""
    if isinstance(obj, dict):
        return {k: _fix_floats(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_fix_floats(v) for v in obj]
    if isinstance(obj, float):
        if obj != obj or obj == float("inf") or obj == float("-inf"):
            return None
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return None if (obj != obj) else float(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    return obj


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(_fix_floats(data), f, indent=2, ensure_ascii=False)
    log.info("Wrote %s (%.1f KB)", path, path.stat().st_size / 1024)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Oracle Pattern Memory (O3)")
    parser.add_argument(
        "--data-dir",
        default=str(ROOT / "data"),
        help="Root data directory (default: repo-root/data)",
    )
    parser.add_argument(
        "--k", type=int, default=MEMORY_CFG["k"],
        help=f"Number of analogues per active episode (default: {MEMORY_CFG['k']})",
    )
    parser.add_argument(
        "--tier", choices=["s", "m", "all"], default="all",
        help="Which episode tier to build analogues for (default: all)",
    )
    args = parser.parse_args(argv)

    data_dir = Path(args.data_dir)
    oracle_dir = data_dir / "oracle"

    # ---- Load episodes ----
    ep_s_path = oracle_dir / "episodes_s.parquet"
    ep_m_path = oracle_dir / "episodes_m.parquet"
    panel_s_path = oracle_dir / "panel_s.parquet"

    episodes_s: pd.DataFrame | None = None
    episodes_m: pd.DataFrame | None = None
    panel_s: pd.DataFrame | None = None

    if ep_s_path.exists():
        episodes_s = pd.read_parquet(ep_s_path)
        log.info("Loaded episodes_s: %d rows", len(episodes_s))
    else:
        log.warning("episodes_s.parquet not found at %s", ep_s_path)
        episodes_s = pd.DataFrame()

    if ep_m_path.exists():
        episodes_m = pd.read_parquet(ep_m_path)
        log.info("Loaded episodes_m: %d rows", len(episodes_m))
    else:
        log.warning("episodes_m.parquet not found at %s", ep_m_path)
        episodes_m = pd.DataFrame()

    if panel_s_path.exists():
        panel_s = pd.read_parquet(panel_s_path)
        log.info("Loaded panel_s: %d rows", len(panel_s))
    else:
        log.warning("panel_s.parquet not found at %s", panel_s_path)

    # ---- 1. Base rates ----
    log.info("Building base rates...")
    base_rates = build_base_rates(episodes_s, episodes_m)
    n_tables = len(base_rates.get("tables", []))
    log.info("Base rates: %d cells", n_tables)

    # Print thin-cell summary
    thin_cells = [t for t in base_rates.get("tables", []) if t.get("thin")]
    log.info("Thin cells (n<20): %d / %d", len(thin_cells), n_tables)

    # Print S3 error rates summary
    for tier_label, s3 in base_rates.get("s3_error_rates", {}).items():
        log.info(
            "S3 tier=%s: onset→confirmed=%.1f%%, false_start(5d)=%.1f%%, "
            "lag_confirmed_mean=%.1fd",
            tier_label,
            (s3.get("onset_to_confirmed_rate") or 0) * 100,
            (s3.get("false_start_rate_5d") or 0) * 100,
            s3.get("detection_lag_confirmed_days_mean") or 0,
        )

    br_path = oracle_dir / "memory_base_rates.json"
    _write_json(br_path, base_rates)

    # ---- 2. Active episode analogues ----
    log.info("Finding analogues for active episodes...")

    active_results: list[dict] = []

    # Build combined catalog for analogue search
    # Each active episode is matched against its OWN tier's catalog
    # (Tier-S actives → episodes_s; Tier-M actives → episodes_m)
    tier_configs = []
    if args.tier in ("s", "all") and episodes_s is not None and not episodes_s.empty:
        tier_configs.append(("s", episodes_s, panel_s))
    if args.tier in ("m", "all") and episodes_m is not None and not episodes_m.empty:
        tier_configs.append(("m", episodes_m, None))  # panel_m not required for P4

    total_active = 0
    for tier_label, eps_df, ep_panel in tier_configs:
        active_eps = eps_df[eps_df["exhausted_date"].isna()].copy()
        n_active = len(active_eps)
        total_active += n_active
        log.info("Tier %s: %d active episodes", tier_label, n_active)

        for _, ep_row in active_eps.iterrows():
            query = ep_row.to_dict()
            result = find_analogues(
                query=query,
                catalog=eps_df,
                panel=ep_panel,
                k=args.k,
            )
            result["tier"] = tier_label
            active_results.append(result)

            # Log a brief summary
            agg = result.get("aggregate", {})
            log.info(
                "  %s (%s %s): %d analogues, leakage_excluded=%d, "
                "median_da_21d=%.3f",
                query.get("episode_id", "?"),
                tier_label,
                query.get("direction", "?"),
                agg.get("k", 0),
                result.get("leakage_excluded", 0),
                agg.get("median_da_21d") or float("nan"),
            )

    output = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "n_active_total": total_active,
            "tier_filter": args.tier,
            "k": args.k,
            "description": (
                "Analogue history for currently-active Oracle rotation episodes. "
                "DESCRIPTIVE LAYER — analogue history, not a forecast. "
                "R4 compliant: no predictive claims; onset-tier surfaces must "
                "print S3 error rates."
            ),
        },
        "active_analogues": active_results,
    }

    aa_path = oracle_dir / "memory_active_analogues.json"
    _write_json(aa_path, output)

    # ---- Summary report ----
    log.info("=" * 60)
    log.info("Oracle Memory build complete")
    log.info("  Base-rate tables : %d cells (%d thin)", n_tables, len(thin_cells))
    log.info("  Active episodes  : %d", total_active)
    log.info("  Analogues written: %s", aa_path)
    log.info("  Base rates written: %s", br_path)

    # Print example analogue set for one June 2026 episode (ids + scores)
    if active_results:
        example = active_results[0]
        log.info("-" * 60)
        log.info(
            "EXAMPLE: query=%s (%s) onset=%s",
            example.get("query_episode_id", "?"),
            example.get("query_direction", "?"),
            example.get("query_onset_date", "?"),
        )
        log.info("  Leakage excluded: %d", example.get("leakage_excluded", 0))
        for a in example.get("analogues", []):
            log.info(
                "    %s  dist=%.4f  same_node=%s  da_21d=%s",
                a.get("episode_id", "?"),
                a.get("distance", float("nan")),
                a.get("same_node", False),
                a.get("outcomes", {}).get("da_21d"),
            )
        agg = example.get("aggregate", {})
        log.info(
            "  Aggregate: k=%d  median_da_21d=%s  (descriptive — analogue history, not a forecast)",
            agg.get("k", 0),
            agg.get("median_da_21d"),
        )
    log.info("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
