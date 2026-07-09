"""scripts/build_causal_edges.py — CHF W3: Weekly bounded battery runner.

CLI
---
    python -m scripts.build_causal_edges [--root PATH] [--weekly] [--max-cells N] [--dry-run]

Reads the frontier ledger to pick the top-K unexplored/accruing cells
(deterministic value heuristic), builds EdgeSpecs, runs run_battery() with
the real TrialLedger (family=causal_scan; declares budget on first run),
and appends results to:
  data/neuralweb/causal_edges.jsonl  (append-only, keep-first by edge_id+week)
  data/neuralweb/causal_nulls.jsonl  (null library: null/forbidden/insufficient verdicts)

After each batch: verifies kill_mask_in_sync(root).  If the compiled kill mask
is stale vs causal_nulls, prints loudly and continues (the config/ regeneration
happens via a scheduled config regen or the next PR; the causal job NEVER edits
config/ at runtime — CHF-R11).

COMPILED KILL MASK BEHAVIOUR (documented in module docstring per CHF-R11)
--------------------------------------------------------------------------
The compiled kill mask in config/causal_priors.yml is the CI-synced mirror of
causal_nulls.jsonl.  At runtime this runner reads causal_nulls.jsonl DIRECTLY
and refuses to re-test any edge that already has a null row there, making the
config compiled section a mirror for CI/reader purposes only.  This satisfies
the law without requiring config/ edits from the nightly job.

RUNTIME BOUNDS
--------------
- Default max_cells = 40 per run (CHF-R8: K <= 40).
- Seeded determinism (seed=42 throughout).
- Wall-clock guard: stops dispatching new cells after 25 minutes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from engine.neuralweb.causal_frontier import (
    TARGET_FAMILIES,
    _cumulative_causal_scan_width,
    _load_jsonl,
    _load_json,
)
from engine.neuralweb.causal_inventory import (
    kill_mask_in_sync,
    compile_kill_mask,
)
from engine.neuralweb.causal_scout import (
    FAMILY as CAUSAL_SCAN_FAMILY,
    EdgeSpec,
    EnvironmentSplit,
    run_battery,
    cumulative_family_width,
)
from engine.neuralweb.causal_targets import (
    build_regime_risk_panel,
    build_entry_quality_panel,
    build_cause_panel,
    load_cause_series,
)
from engine.trial_ledger import TrialLedger

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("build_causal_edges")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_FRONTIER_PATH = Path("data") / "neuralweb" / "causal_frontier.json"
_EDGES_PATH = Path("data") / "neuralweb" / "causal_edges.jsonl"
_NULLS_PATH = Path("data") / "neuralweb" / "causal_nulls.jsonl"
_LEDGER_PATH = Path("data") / "trial_ledger.jsonl"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_MAX_CELLS = 40
WALL_CLOCK_LIMIT_SECONDS = 25 * 60   # 25 minutes
SEED = 42

# Verdicts that go into the null library
_NULL_VERDICTS = frozenset({"null", "forbidden", "insufficient_era_span", "insufficient_power", "unstable"})

# Pre-declared environment splits (CHF-R5: 2-3 splits per edge, declared at mint time)
_ENV_SPLITS = [
    EnvironmentSplit("high_vol_regime", "High volatility regime (VIX > recent median)"),
    EnvironmentSplit("low_vol_regime", "Low volatility regime (VIX <= recent median)"),
]


# ---------------------------------------------------------------------------
# Null library helpers
# ---------------------------------------------------------------------------

def _load_null_edge_ids(nulls_path: Path) -> set[str]:
    """Return set of edge_ids already in the null library (do not re-test)."""
    nulls = _load_jsonl(nulls_path)
    return {n.get("edge_id", "") for n in nulls if n.get("edge_id")}


def _load_existing_edge_keys(edges_path: Path) -> set[str]:
    """Return set of (edge_id, week_key) already committed (keep-first)."""
    edges = _load_jsonl(edges_path)
    keys = set()
    today = datetime.now(timezone.utc)
    iso_week = today.strftime("%Y-W%V")
    for e in edges:
        eid = e.get("edge_id", "")
        week = e.get("batch_week", iso_week)
        if eid:
            keys.add(f"{eid}|{week}")
    return keys


def _append_jsonl(path: Path, row: dict) -> None:
    """Append one JSON row to a JSONL file (atomic-append)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")


# ---------------------------------------------------------------------------
# Environment mask builders
# ---------------------------------------------------------------------------

def _build_env_masks(
    regime_history: pd.DataFrame | None,
    dates: pd.DatetimeIndex,
) -> dict[str, object]:
    """Build boolean environment masks aligned to a date index.

    Returns dict mapping split_id → boolean numpy array (same length as dates).
    Falls back to 50/50 split if regime data is unavailable.
    """
    import numpy as np
    n = len(dates)

    if regime_history is not None and "transition_state" in regime_history.columns:
        # High-vol regime: transition_state is WARNING or worse
        high_sev_states = {"WARNING", "DOWNGRADE", "CRISIS"}
        try:
            rh_aligned = regime_history.reindex(dates, method="ffill")
            ts_col = rh_aligned["transition_state"].fillna("STABLE").astype(str)
            high_vol = np.array([s.upper() in high_sev_states for s in ts_col], dtype=bool)
            low_vol = ~high_vol
            return {
                "high_vol_regime": high_vol,
                "low_vol_regime": low_vol,
            }
        except Exception:
            pass

    # Fallback: first half = low, second half = high
    half = n // 2
    low = np.zeros(n, dtype=bool)
    low[:half] = True
    high = ~low
    return {
        "high_vol_regime": high,
        "low_vol_regime": low,
    }


# ---------------------------------------------------------------------------
# Edge ID builder
# ---------------------------------------------------------------------------

def _make_edge_id(cause_feature_id: str, cause_col: str, target_id: str, lag: int) -> str:
    """Deterministic edge ID from (cause_feature, column, target, lag)."""
    raw = f"{cause_feature_id}|{cause_col}|{target_id}|lag{lag}"
    return "e_" + hashlib.sha1(raw.encode()).hexdigest()[:12]


# ---------------------------------------------------------------------------
# Main batch runner
# ---------------------------------------------------------------------------

def run_batch(
    root: Path,
    max_cells: int = DEFAULT_MAX_CELLS,
    dry_run: bool = False,
) -> dict:
    """Run one bounded battery batch.

    Returns summary dict with stats.
    """
    start_time = time.monotonic()
    today = datetime.now(timezone.utc)
    iso_week = today.strftime("%Y-W%V")
    asof = today.strftime("%Y-%m-%dT%H:%M:%SZ")

    log.info("build_causal_edges: starting batch (max_cells=%d, dry_run=%s, week=%s)",
             max_cells, dry_run, iso_week)

    # --- Load frontier for cell ordering ---
    frontier_path = root / _FRONTIER_PATH
    frontier = _load_json(frontier_path)
    if frontier is None:
        log.warning("build_causal_edges: frontier not found at %s — run build_causal_frontier first", frontier_path)
        frontier = {"cells": []}

    frontier_cells = frontier.get("cells", [])

    # --- Load null edge IDs (runtime kill-mask read) ---
    null_edge_ids = _load_null_edge_ids(root / _NULLS_PATH)
    existing_edge_keys = _load_existing_edge_keys(root / _EDGES_PATH)

    log.info("build_causal_edges: %d edges already in null library, %d in edges ledger",
             len(null_edge_ids), len(existing_edge_keys))

    # --- Load target panels ---
    log.info("build_causal_edges: loading target panels")
    regime_panel = build_regime_risk_panel(root)
    entry_panel = build_entry_quality_panel(root)

    target_panels: dict[str, dict[str, object]] = {}
    if regime_panel:
        target_panels["regime_risk"] = regime_panel
    if entry_panel is not None:
        target_panels["entry_quality"] = entry_panel
    else:
        log.info("build_causal_edges: entry_quality panel absent (data_absent) — skipping")

    if not target_panels:
        log.warning("build_causal_edges: no target panels available — aborting batch")
        return {"cells_run": 0, "cells_screened": 0, "cells_null": 0}

    # --- Load cause panel from inventory ---
    cause_panel = build_cause_panel(root)
    if not cause_panel:
        log.warning("build_causal_edges: no cause features available — run build_causal_inventory first")
        return {"cells_run": 0, "cells_screened": 0, "cells_null": 0}

    # --- Load regime history for environment masks ---
    regime_history: pd.DataFrame | None = None
    rh_path = root / "data" / "regime" / "regime_history.parquet"
    if rh_path.exists():
        try:
            regime_history = pd.read_parquet(rh_path)
            if not isinstance(regime_history.index, pd.DatetimeIndex):
                regime_history.index = pd.to_datetime(regime_history.index)
        except Exception as exc:
            log.warning("build_causal_edges: could not load regime_history — %s", exc)

    # --- Set up TrialLedger ---
    ledger_path = root / _LEDGER_PATH
    ledger = TrialLedger(path=ledger_path)

    # Declare budget on first run (RF-6 law: log_declared_budget before screening)
    declared_ok = ledger.log_declared_budget(
        n=max_cells,
        family=CAUSAL_SCAN_FAMILY,
        reason=f"CHF W3 weekly batch budget: K<={max_cells} cells/week (CHF-R8)",
    )
    if declared_ok:
        log.info("build_causal_edges: declared causal_scan budget n=%d", max_cells)

    # Load priors
    try:
        from engine.neuralweb.causal_scout import load_priors
        priors = load_priors(root)
    except Exception:
        priors = {}

    # --- Select cells from frontier (top-K by value_score, unexplored/accruing first) ---
    eligible_cells = [
        c for c in frontier_cells
        if c.get("state") in ("unexplored", "accruing")
        and c.get("target_family") in target_panels
        and c.get("data_present", False)
    ]

    # Deterministic ordering: by descending value_score, then lex
    eligible_cells.sort(
        key=lambda c: (-c.get("value_score", 0),
                       c.get("cause_family", ""),
                       c.get("target_family", ""),
                       c.get("environment", ""))
    )

    cells_to_run = eligible_cells[:max_cells]
    log.info("build_causal_edges: %d eligible cells, running top %d",
             len(eligible_cells), len(cells_to_run))

    # --- Statistics ---
    cells_run = 0
    cells_screened = 0
    cells_null = 0
    cells_skipped = 0

    for cell in cells_to_run:
        # Wall-clock guard
        elapsed = time.monotonic() - start_time
        if elapsed > WALL_CLOCK_LIMIT_SECONDS:
            log.warning(
                "build_causal_edges: wall-clock limit reached (%.0fs) — stopping dispatch",
                elapsed
            )
            break

        # Max-cells guard (per battery call, not per frontier cell)
        if cells_run >= max_cells:
            break

        cause_feature_id = cell.get("cause_feature_id", "")
        target_family = cell.get("target_family", "")
        environment = cell.get("environment", "full")

        # Look up cause metadata
        cause_meta = cause_panel.get(cause_feature_id)
        if cause_meta is None:
            cells_skipped += 1
            continue

        # Get target panel
        tgt_panel = target_panels.get(target_family)
        if not tgt_panel:
            cells_skipped += 1
            continue

        # Determine lag from inventory
        min_lag = cause_meta.get("min_lag_days", 1)
        lags = [max(1, min_lag), max(1, min_lag) * 3, max(1, min_lag) * 10]

        # Try each column in the cause feature
        columns_to_try = cause_meta.get("columns") or []
        if not columns_to_try:
            cells_skipped += 1
            continue

        cause_col = columns_to_try[0]  # use first column per cause feature

        # Load cause series
        cause_series = load_cause_series(cause_feature_id, cause_meta, root, cause_col)
        if cause_series is None or len(cause_series) < 25:
            log.debug("build_causal_edges: cause %s/%s has no data", cause_feature_id, cause_col)
            cells_skipped += 1
            continue

        # Guard: skip non-numeric series (string dtype, e.g. cycle phase labels)
        try:
            import numpy as np
            cause_series = cause_series.astype(float)
        except (ValueError, TypeError):
            log.debug(
                "build_causal_edges: cause %s/%s is non-numeric — skipping",
                cause_feature_id, cause_col
            )
            cells_skipped += 1
            continue

        # Run battery for each target in the target_family
        for target_id, target_series in tgt_panel.items():
            if cells_run >= max_cells:
                break

            if not isinstance(target_series, pd.Series):
                continue

            # Build edge ID
            edge_id = _make_edge_id(cause_feature_id, cause_col, target_id, lags[0])

            # Skip if in null library (runtime kill-mask check per module docstring)
            if edge_id in null_edge_ids:
                log.debug("build_causal_edges: %s in null library — skipping", edge_id)
                cells_skipped += 1
                continue

            # Skip if already committed this week (keep-first)
            week_key = f"{edge_id}|{iso_week}"
            if week_key in existing_edge_keys:
                log.debug("build_causal_edges: %s already committed this week — skipping", edge_id)
                cells_skipped += 1
                continue

            # Determine era policy
            era_policy = "require_break_2010"
            if target_family == "entry_quality":
                era_policy = "era_specific_recent_only"  # auto era_specific stamp (CHF-R6)

            # Build EdgeSpec
            spec = EdgeSpec(
                edge_id=edge_id,
                cause_id=cause_feature_id,
                target_id=target_id,
                target_type="market_series",
                lags=lags,
                cause_kind="level",
                horizon_d=21,
                environment_splits=_ENV_SPLITS[:2],  # 2 declared splits (CHF-R5)
                era_policy=era_policy,
            )

            # Build environment masks aligned to the INTERSECTION of cause and
            # target dates — NOT naively to tgt_dates length (review fix: the
            # battery aligns cause+target via pd.concat.dropna() producing an
            # intersection index; the mask must match that intersection so that
            # mask[lag:] in the battery aligns correctly with y_shifted).
            cause_dates = pd.DatetimeIndex(cause_series.index)
            tgt_dates = pd.DatetimeIndex(target_series.index)
            aligned_dates = cause_dates.intersection(tgt_dates).sort_values()
            env_masks = _build_env_masks(regime_history, aligned_dates)

            # Build environment_masks for the spec's declared splits
            spec_env_masks = {}
            for env_split in spec.environment_splits:
                aligned_mask = env_masks.get(env_split.split_id)
                if aligned_mask is not None:
                    n_aligned = len(aligned_dates)
                    n_mask = len(aligned_mask)
                    log.debug(
                        "build_causal_edges: %s split=%s mask_coverage=%d/%d",
                        edge_id, env_split.split_id,
                        int(aligned_mask.sum()) if hasattr(aligned_mask, 'sum') else -1,
                        n_aligned,
                    )
                    if n_mask != n_aligned:
                        # Should never happen since _build_env_masks returns
                        # same length as its `dates` argument — log and skip.
                        log.warning(
                            "build_causal_edges: %s split=%s mask length %d "
                            "!= aligned_dates length %d — skipping split",
                            edge_id, env_split.split_id, n_mask, n_aligned,
                        )
                        continue
                    spec_env_masks[env_split.split_id] = aligned_mask

            cells_run += 1
            log.info(
                "build_causal_edges: [%d/%d] edge=%s (cause=%s/%s, target=%s, era=%s)",
                cells_run, max_cells, edge_id,
                cause_feature_id, cause_col, target_id, era_policy
            )

            if dry_run:
                log.info("build_causal_edges: --dry-run — no writes")
                continue

            # Run battery
            try:
                result = run_battery(
                    spec,
                    cause=cause_series,
                    target=target_series,
                    priors=priors,
                    root=root,
                    environment_masks=spec_env_masks,
                    ledger=ledger,
                    hermetic=False,
                )
            except Exception as exc:
                log.warning("build_causal_edges: battery failed for %s — %s", edge_id, exc)
                cells_run -= 1  # don't count failed batteries against max_cells
                continue

            # Print cumulative width per CHF-R3
            cumw = cumulative_family_width(root)
            log.info(
                "build_causal_edges: %s → verdict=%s, support=%s, "
                "cells_logged=%d, cumulative_scan_width=%d",
                edge_id, result.verdict, result.causal_support,
                result.cells_logged, cumw
            )

            # Build row for edges.jsonl
            edge_row = {
                "edge_id": edge_id,
                "cause_feature_id": cause_feature_id,
                "cause_column": cause_col,
                "cause_family": cause_meta.get("family", "unknown"),
                "target_id": target_id,
                "target_family": target_family,
                "environment": environment,
                "verdict": result.verdict,
                "causal_support": result.causal_support,
                "concerns": result.concerns,
                "stats": result.stats,
                "splits_declared": result.splits_declared,
                "splits_tested": result.splits_tested,
                "cells_logged": result.cells_logged,
                "lags": lags,
                "era_policy": era_policy,
                "search_width_at_scan": cumw,  # Oracle promotion-scan pattern (CHF-R3)
                "batch_week": iso_week,
                "asof": result.asof,
            }

            # Append to edges.jsonl (keep-first by edge_id+week)
            _append_jsonl(root / _EDGES_PATH, edge_row)
            existing_edge_keys.add(week_key)

            # Append to nulls.jsonl if applicable
            if result.verdict in _NULL_VERDICTS:
                cells_null += 1
                null_row = {
                    "edge_id": edge_id,
                    "cause_feature_id": cause_feature_id,
                    "cause_column": cause_col,
                    "cause_family": cause_meta.get("family", "unknown"),
                    "target_id": target_id,
                    "target_family": target_family,
                    "environment": environment,
                    "failed_reason": result.verdict,
                    "verdict": result.verdict,
                    "windows": lags,
                    "environments": [e.split_id for e in spec.environment_splits],
                    "concerns": result.concerns,
                    "do_not_repropose_text": (
                        f"Edge {edge_id} ({cause_feature_id}/{cause_col} → "
                        f"{target_id}) returned verdict='{result.verdict}' "
                        f"in environment='{environment}'. "
                        f"Concerns: {'; '.join(result.concerns[:3])}. "
                        "Do not re-propose without a novel mechanism or structural change."
                    ),
                    "family": CAUSAL_SCAN_FAMILY,
                    "search_width_at_scan": cumw,
                    "scanned_at": asof,
                }
                _append_jsonl(root / _NULLS_PATH, null_row)
                null_edge_ids.add(edge_id)
            else:
                cells_screened += 1

    # --- Kill mask sync check ---
    in_sync = kill_mask_in_sync(root)
    if not in_sync:
        log.warning(
            "build_causal_edges: KILL MASK OUT OF SYNC — "
            "compiled section in config/causal_priors.yml diverges from causal_nulls.jsonl. "
            "This will be healed on the next config regen PR. "
            "The runtime null library (causal_nulls.jsonl) is the authoritative source — "
            "re-testing is blocked by the live null library, not the compiled mask."
        )
        print(
            "[build_causal_edges] WARNING: kill mask out of sync. "
            "Run 'python -m engine.neuralweb.causal_inventory' to regenerate compiled section "
            "and commit the updated config/causal_priors.yml."
        )
    else:
        log.info("build_causal_edges: kill mask in sync")

    # Final cumulative width
    final_width = cumulative_family_width(root)
    log.info(
        "build_causal_edges: batch complete — cells_run=%d screened=%d null=%d skipped=%d "
        "cumulative_scan_width=%d",
        cells_run, cells_screened, cells_null, cells_skipped, final_width
    )
    print(f"[build_causal_edges] cumulative causal_scan width: {final_width}")

    return {
        "cells_run": cells_run,
        "cells_screened": cells_screened,
        "cells_null": cells_null,
        "cells_skipped": cells_skipped,
        "cumulative_width": final_width,
        "batch_week": iso_week,
        "dry_run": dry_run,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "CHF W3: Weekly bounded battery runner. "
            "Picks top-K cells from the frontier ledger and runs CHF-R5 batteries."
        )
    )
    parser.add_argument("--root", type=Path, default=None,
                        help="Repo root (default: auto-detected)")
    parser.add_argument("--weekly", action="store_true",
                        help="Run as the weekly batch (enables batteries)")
    parser.add_argument("--max-cells", type=int, default=DEFAULT_MAX_CELLS,
                        help=f"Max cells per run (default: {DEFAULT_MAX_CELLS}, CHF-R8: K<=40)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Enumerate cells but write nothing")
    args = parser.parse_args(argv)

    if args.max_cells > 40:
        log.warning(
            "build_causal_edges: --max-cells=%d exceeds CHF-R8 bound of 40 — clamping to 40",
            args.max_cells
        )
        args.max_cells = 40

    root = args.root if args.root is not None else Path(__file__).resolve().parent.parent

    if not args.weekly and not args.dry_run:
        log.info("build_causal_edges: --weekly not set; pass --weekly to enable batteries")
        print("[build_causal_edges] --weekly not set. Pass --weekly to run batteries.")
        return 0

    try:
        summary = run_batch(root=root, max_cells=args.max_cells, dry_run=args.dry_run)
        print(
            f"[build_causal_edges] batch complete: "
            f"cells_run={summary['cells_run']}, "
            f"screened={summary['cells_screened']}, "
            f"null={summary['cells_null']}, "
            f"width={summary['cumulative_width']}"
        )
        return 0
    except Exception as exc:
        log.error("build_causal_edges: FAILED — %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
