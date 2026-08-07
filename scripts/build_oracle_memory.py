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
                                         [--analogues-only]

  --analogues-only  build ONLY memory_active_analogues.json; never reads or
                    writes memory_base_rates.json.  This is the half that
                    oracle_nightly runs (its Step 4a hand-rolls base rates from
                    the gauntlet p3_results and must not be overwritten here).

Design
------
* build_base_rates() produces the printed-truths tables per the P4 spec.
* find_analogues() computes kNN for each currently-ACTIVE episode
  (exhausted_date is NaT/null) — these are the episodes that are live today.
* Descriptive layer only (R4): no predictive claims; every aggregate carries
  "descriptive — analogue history, not a forecast."
* Hermetic on the Mac's canonical data/ store; no network calls.

ARTIFACT SHAPE (memory_active_analogues.json)
---------------------------------------------
Top-level keys are episode_ids, plus a reserved "meta" key.  This is the shape
the ONLY production reader wants: engine/oracle/live.py does

    analogues_meta.get(ep_item.get("episode_id") or "")

to fill oracle_state.json active_episodes[].analogues.  Episode ids are
"NODE::direction::YYYY-MM-DD::n", so they cannot collide with "meta".
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
# Inputs
# ---------------------------------------------------------------------------

def load_inputs(
    oracle_dir: Path,
    *,
    need_panel: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame | None]:
    """Load the episode catalogs + Tier-S panel.

    Missing episode parquets degrade to EMPTY frames (never raise) — the
    callers treat "no episodes" as "nothing to build", not as a crash.
    A missing panel degrades to None: find_analogues then skips the DTW leg
    and falls back to the calendar-day leakage filter.
    """
    ep_s_path = oracle_dir / "episodes_s.parquet"
    ep_m_path = oracle_dir / "episodes_m.parquet"
    panel_s_path = oracle_dir / "panel_s.parquet"

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

    panel_s: pd.DataFrame | None = None
    if not need_panel:
        return episodes_s, episodes_m, None
    if panel_s_path.exists():
        panel_s = pd.read_parquet(panel_s_path)
        log.info("Loaded panel_s: %d rows", len(panel_s))
    else:
        log.warning("panel_s.parquet not found at %s", panel_s_path)

    return episodes_s, episodes_m, panel_s


# ---------------------------------------------------------------------------
# Active-episode analogues (the half oracle_nightly Step 20 runs)
# ---------------------------------------------------------------------------

ANALOGUES_SCHEMA = "oracle_memory_active_analogues.v2"


def build_active_analogues(
    episodes_s: pd.DataFrame | None,
    episodes_m: pd.DataFrame | None,
    panel_s: pd.DataFrame | None,
    *,
    k: int = MEMORY_CFG["k"],
    tier: str = "all",
) -> dict:
    """kNN analogues for every currently-ACTIVE episode, keyed by episode_id.

    Each active episode is matched against its OWN tier's catalog
    (Tier-S actives → episodes_s; Tier-M actives → episodes_m).  The leakage
    law lives inside find_analogues(), not here.

    Returns the artifact payload: {"meta": {...}, "<episode_id>": {...}, ...}.
    """
    tier_configs: list[tuple[str, pd.DataFrame, pd.DataFrame | None]] = []
    if tier in ("s", "all") and episodes_s is not None and not episodes_s.empty:
        tier_configs.append(("s", episodes_s, panel_s))
    if tier in ("m", "all") and episodes_m is not None and not episodes_m.empty:
        tier_configs.append(("m", episodes_m, None))  # panel_m not required for P4

    blocks: dict[str, dict] = {}
    episode_ids: list[str] = []
    total_active = 0

    for tier_label, eps_df, ep_panel in tier_configs:
        if "exhausted_date" not in eps_df.columns:
            log.warning(
                "Tier %s: no exhausted_date column — cannot select active episodes, skipping",
                tier_label,
            )
            continue
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
                k=k,
            )
            result["tier"] = tier_label
            ep_id = str(result.get("query_episode_id") or "")
            if not ep_id:
                log.warning("Tier %s: active episode with empty episode_id — skipped", tier_label)
                continue
            if ep_id in blocks:
                # Keep-first; an id collision across tiers would silently
                # overwrite one episode's analogue history with another's.
                log.warning("Duplicate episode_id %s — keeping first block", ep_id)
                continue
            blocks[ep_id] = result
            episode_ids.append(ep_id)

            # Log a brief summary
            agg = result.get("aggregate", {})
            log.info(
                "  %s (%s %s): %d analogues, leakage_excluded=%d, "
                "median_da_21d=%.3f",
                ep_id or "?",
                tier_label,
                query.get("direction", "?"),
                agg.get("k", 0),
                result.get("leakage_excluded", 0),
                agg.get("median_da_21d") or float("nan"),
            )

    meta = {
        "schema": ANALOGUES_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_active_total": total_active,
        "n_blocks": len(blocks),
        "tier_filter": tier,
        "k": k,
        "episode_ids": episode_ids,
        "description": (
            "Analogue history for currently-active Oracle rotation episodes, keyed "
            "by episode_id. DESCRIPTIVE LAYER — analogue history, not a forecast. "
            "R4 compliant: no predictive claims; onset-tier surfaces must "
            "print S3 error rates."
        ),
        "shape_note": (
            "Top-level keys are episode_ids plus this reserved 'meta' key; "
            "engine/oracle/live.py reads the artifact as "
            "analogues_meta.get(episode_id)."
        ),
    }
    return {"meta": meta, **blocks}


def run_analogues(
    data_dir: Path | str,
    *,
    k: int = MEMORY_CFG["k"],
    tier: str = "all",
    dry_run: bool = False,
) -> dict:
    """Load → build → write memory_active_analogues.json.  Never raises on
    missing inputs; returns a summary dict the caller logs.

    Summary keys: ok, skipped (str|None), n_active, n_blocks, path, bytes,
    payload (the artifact dict, or None when skipped).
    """
    oracle_dir = Path(data_dir) / "oracle"
    episodes_s, episodes_m, panel_s = load_inputs(oracle_dir)

    s_empty = episodes_s is None or episodes_s.empty
    m_empty = episodes_m is None or episodes_m.empty
    aa_path = oracle_dir / "memory_active_analogues.json"

    if s_empty and m_empty:
        return {
            "ok": False,
            "skipped": "no episode catalogs (episodes_s/episodes_m parquet missing or empty)",
            "n_active": 0,
            "n_blocks": 0,
            "path": str(aa_path),
            "bytes": 0,
            "payload": None,
        }

    payload = build_active_analogues(
        episodes_s, episodes_m, panel_s, k=k, tier=tier
    )
    n_blocks = len(payload) - 1  # minus "meta"
    n_active = payload["meta"]["n_active_total"]

    if dry_run:
        log.info("DRY-RUN: would write %s (%d blocks)", aa_path, n_blocks)
        return {
            "ok": True, "skipped": None, "n_active": n_active,
            "n_blocks": n_blocks, "path": str(aa_path), "bytes": 0,
            "payload": payload,
        }

    _write_json(aa_path, payload)
    return {
        "ok": True,
        "skipped": None,
        "n_active": n_active,
        "n_blocks": n_blocks,
        "path": str(aa_path),
        "bytes": aa_path.stat().st_size,
        "payload": payload,
    }


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
    parser.add_argument(
        "--analogues-only", action="store_true",
        help="Build ONLY memory_active_analogues.json; never read or write "
             "memory_base_rates.json (oracle_nightly Step 4a owns that artifact).",
    )
    args = parser.parse_args(argv)

    data_dir = Path(args.data_dir)
    oracle_dir = data_dir / "oracle"

    n_tables = 0
    thin_cells: list = []
    br_path: Path | None = None

    if args.analogues_only:
        log.info("--analogues-only: base rates SKIPPED (memory_base_rates.json untouched)")
    else:
        episodes_s, episodes_m, _ = load_inputs(oracle_dir, need_panel=False)

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
    summary = run_analogues(data_dir, k=args.k, tier=args.tier)
    if summary["skipped"]:
        log.warning("Analogues SKIPPED: %s", summary["skipped"])

    aa_path = Path(summary["path"])
    active_results = list((summary.get("payload") or {}).values())
    active_results = [r for r in active_results if isinstance(r, dict) and "analogues" in r]
    total_active = summary["n_active"]

    # ---- Summary report ----
    log.info("=" * 60)
    log.info("Oracle Memory build complete")
    if br_path is not None:
        log.info("  Base-rate tables : %d cells (%d thin)", n_tables, len(thin_cells))
        log.info("  Base rates written: %s", br_path)
    log.info("  Active episodes  : %d", total_active)
    log.info("  Analogue blocks  : %d", summary["n_blocks"])
    if not summary["skipped"]:
        log.info("  Analogues written: %s", aa_path)

    # Print example analogue set for one active episode (ids + scores)
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
