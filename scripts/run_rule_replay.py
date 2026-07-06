"""scripts/run_rule_replay.py — NW Rails R1 governed runner.

Per §3.3 of NW_RAILS_AND_TIER1_LOBES_PROGRAM_BY_FABLE.md (RUL-P3):

  - --exp-id is REQUIRED; no --adhoc flag exists (house-law violation)
  - Loads the registry entry and reconstructs the grid from the experiment
    definition; hard-fails on any hash mismatch or missing registration
  - Loads fires from data/replay/replay_boarded.parquet (canonical data plane)
  - Applies CohortFilter, computes per-fire per-policy results via engine.rule_replay
  - Writes <exp_id>_perfire.parquet (gitignored) + <exp_id>_summary.json (git,
    vintage-stamped, includes cumulative pooled replay trial count + per-cell
    episode-cluster counts)
  - Marks experiment executed → reported via update_experiment_status

Episode-cluster definition:
  - If replay_boarded has an 'episode_id' column, cluster = episode_id.
  - Otherwise cluster = ticker + '_' + year (ticker×year fallback).
  This document states which definition was used in every run's summary JSON.

Usage
-----
python scripts/run_rule_replay.py --exp-id exit_grid_v1

Optional overrides for testing:
  --boarded-path  PATH    override replay_boarded.parquet path
  --massive-dir   PATH    override massive_stock_day directory path
  --registry-path PATH    override registry.jsonl path
  --results-dir   PATH    override results output directory
  --dry-run               print plan, skip computation and file writes
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import date, timezone, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Repo root on path
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# ---------------------------------------------------------------------------
# Canonical data path — same as replay_standout_pipeline.CANONICAL_DATA
# ---------------------------------------------------------------------------
_CANONICAL_DATA = Path("/Users/chriswong/Documents/Cluade/Macro Dashboard/data")
_MASSIVE_DIR = _CANONICAL_DATA / "massive_stock_day"
_BOARDED_PATH = _CANONICAL_DATA / "replay" / "replay_boarded.parquet"
_RESULTS_DIR = _REPO_ROOT / "data" / "rule_experiments" / "results"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("run_rule_replay")


# ---------------------------------------------------------------------------
# Import rule engine components
# ---------------------------------------------------------------------------
from engine.rule_replay import (  # noqa: E402
    CohortFilter,
    ExitPolicy,
    GovernorRefusal,
    RuleSpec,
    cohort_filter,
    replay_spec,
    serialize_results,
    VALID_HOLD_HORIZONS,
    VALID_TRAIL_STOP_PCTS,
)
from engine.rule_experiments import (  # noqa: E402
    load_experiment,
    pooled_replay_trial_count,
    update_experiment_status,
    verify_spec_hashes,
)
from engine.vintage_stamp import vintage_stamp  # noqa: E402


# ---------------------------------------------------------------------------
# Grid reconstruction from experiment definition
# ---------------------------------------------------------------------------
def _build_wait_grid_v1_specs(cohort: CohortFilter) -> list[RuleSpec]:
    """Reconstruct the WAIT-GRID-1 grid from its frozen definition (§6.1).

    10 cells:
      delay_n ∈ {1, 2, 3, 5, 10} × hold ∈ {hold(21), hold(63)}

    delay_n=1 is the production fill (next-bar-after-signal), matching the
    existing Oracle convention.  delay_n > 1 offsets the fill by that many
    additional bars to simulate waiting.
    """
    specs: list[RuleSpec] = []
    for delay_n in [1, 2, 3, 5, 10]:
        for hold_bars in [21, 63]:
            specs.append(RuleSpec(
                spec_id=f"wait_grid_v1/delay{delay_n}_hold{hold_bars}",
                cohort=cohort,
                delay_n=delay_n,
                exit=ExitPolicy.hold(hold_bars),
                horizons_ref=(126,),
            ))

    assert len(specs) == 10, f"WAIT-GRID-1 must be 10 cells, got {len(specs)}"
    return specs


def _build_exit_grid_v1_specs(cohort: CohortFilter) -> list[RuleSpec]:
    """Reconstruct the EXIT-GRID-1 grid from its frozen definition (§4).

    15 cells:
      6 holds: H in {5, 10, 21, 42, 63, 126}
      1 ema_trail: span=8, resample='3B'
      4 trail_stops: pct in {8, 12, 15, 20}
      4 barriers: {(-5,+8), (-5,+15), (-8,+15), (-8,+25)}
    """
    specs: list[RuleSpec] = []

    # 6 hold cells
    for H in sorted(VALID_HOLD_HORIZONS):
        specs.append(RuleSpec(
            spec_id=f"exit_grid_v1/hold_{H}",
            cohort=cohort,
            delay_n=1,
            exit=ExitPolicy.hold(H),
            horizons_ref=(126,),
        ))

    # 1 ema_trail cell
    specs.append(RuleSpec(
        spec_id="exit_grid_v1/ema_trail_s8",
        cohort=cohort,
        delay_n=1,
        exit=ExitPolicy.ema_trail(span=8, resample="3B"),
        horizons_ref=(126,),
    ))

    # 4 trail_stop cells
    for pct in sorted(VALID_TRAIL_STOP_PCTS):
        specs.append(RuleSpec(
            spec_id=f"exit_grid_v1/trail_stop_{pct}pct",
            cohort=cohort,
            delay_n=1,
            exit=ExitPolicy.trail_stop(pct),
            horizons_ref=(126,),
        ))

    # 4 barrier cells
    for stop_pct, target_pct in [(-5, 8), (-5, 15), (-8, 15), (-8, 25)]:
        sp_slug = str(abs(stop_pct))
        tp_slug = str(target_pct)
        specs.append(RuleSpec(
            spec_id=f"exit_grid_v1/barrier_s{sp_slug}_t{tp_slug}",
            cohort=cohort,
            delay_n=1,
            exit=ExitPolicy.barrier(float(stop_pct), float(target_pct)),
            horizons_ref=(126,),
        ))

    assert len(specs) == 15, f"Grid must be 15 cells, got {len(specs)}"
    return specs


# Grid builders registry — keyed by exp_id prefix
_GRID_BUILDERS: dict[str, Any] = {
    "exit_grid_v1": _build_exit_grid_v1_specs,
    "wait_grid_v1": _build_wait_grid_v1_specs,
}


def _build_grid(exp_id: str, exp_entry: dict) -> list[RuleSpec]:
    """Reconstruct the grid for a given experiment.

    Raises GovernorRefusal if no builder is found for this exp_id.
    """
    # Look up builder by exact match or prefix
    builder = _GRID_BUILDERS.get(exp_id)
    if builder is None:
        for prefix, b in _GRID_BUILDERS.items():
            if exp_id.startswith(prefix):
                builder = b
                break

    if builder is None:
        raise GovernorRefusal(
            f"No grid builder found for exp_id={exp_id!r}. "
            f"Known builders: {sorted(_GRID_BUILDERS.keys())}. "
            "Add a grid builder to scripts/run_rule_replay.py for this experiment."
        )

    # Build the cohort filter from the registered question/spec metadata
    # EXIT-GRID-1 cohort: verdict_type='fire' AND verdict_grade=True
    cohort = cohort_filter(
        ("eq", "verdict_type", "fire"),
        ("eq", "verdict_grade", True),
    )
    return builder(cohort)


# ---------------------------------------------------------------------------
# Price loading (split-adjusted closes from massive_stock_day)
# ---------------------------------------------------------------------------
def _load_closes(
    tickers: list[str],
    massive_dir: Path,
) -> dict[str, pd.Series]:
    """Load split-adjusted close series for the given tickers.

    Uses split_adjust() imported from scripts.replay_standout_pipeline — the
    canonical function per §3.2. Returns {} for any ticker not found.
    """
    # Import the canonical split_adjust from replay_standout_pipeline
    # (module-level function; importable per §3.2)
    try:
        from scripts.replay_standout_pipeline import split_adjust as _split_adjust
    except ImportError:
        log.warning(
            "Could not import split_adjust from scripts.replay_standout_pipeline; "
            "falling back to identity (splits NOT adjusted — test-mode only)"
        )
        def _split_adjust(s: pd.Series) -> pd.Series:  # type: ignore[misc]
            return s

    closes: dict[str, pd.Series] = {}
    missing = []
    for ticker in tickers:
        path = massive_dir / f"{ticker}.parquet"
        if not path.exists():
            missing.append(ticker)
            continue
        try:
            df = pd.read_parquet(path)
            if "close" not in df.columns:
                missing.append(ticker)
                continue
            c = df["close"].dropna()
            if not isinstance(c.index, pd.DatetimeIndex):
                c.index = pd.to_datetime(c.index)
            c = c.sort_index()
            closes[ticker] = _split_adjust(c)
        except Exception as exc:
            log.warning("Failed to load %s: %s", ticker, exc)
            missing.append(ticker)

    if missing:
        log.info(
            "Closes missing for %d/%d tickers (%.1f%%) — these fires will be censored",
            len(missing), len(tickers), 100 * len(missing) / max(1, len(tickers)),
        )
    return closes


# ---------------------------------------------------------------------------
# Episode cluster assignment
# ---------------------------------------------------------------------------
def _assign_episode_cluster(fires_df: pd.DataFrame) -> tuple[pd.Series, str]:
    """Return (cluster_series, cluster_definition_note).

    If 'episode_id' column is present, use it directly.
    Otherwise derive ticker×year from 'ticker' and 'year' (or signal_date).
    """
    if "episode_id" in fires_df.columns:
        return fires_df["episode_id"].astype(str), "episode_id column from replay_boarded"

    # Fallback: ticker × year
    ticker_col = "ticker" if "ticker" in fires_df.columns else fires_df.columns[0]
    if "year" in fires_df.columns:
        year_series = fires_df["year"].astype(str)
    else:
        date_col = "fire_date" if "fire_date" in fires_df.columns else "signal_date"
        year_series = pd.to_datetime(fires_df[date_col]).dt.year.astype(str)

    cluster = fires_df[ticker_col].astype(str) + "_" + year_series
    return cluster, "ticker×year fallback (no episode_id column)"


# ---------------------------------------------------------------------------
# Per-cell summary statistics
# ---------------------------------------------------------------------------
def _cell_stats(
    perfire: pd.DataFrame,
    cohort_fires: pd.DataFrame,
    cluster_col: str = "episode_cluster",
) -> dict[str, Any]:
    """Compute per-cell summary statistics from perfire results DataFrame."""
    n_total = len(perfire)
    if n_total == 0:
        return {
            "n_fires": 0,
            "n_censored": 0,
            "n_short_path": 0,
            "n_held_to_reference": 0,
            "short_path_pct": None,
            "held_to_reference_pct": None,
            "censoring_rate": None,
            "episode_clusters": 0,
            "wr": None,
            "mean_exit_ret": None,
            "median_exit_ret": None,
            "mean_foregone_mfe_126": None,
            "mean_avoided_mae_126": None,
            "regret_ratio": None,
        }

    # short_path: genuine truncated window (fire near end of data) — exclude from aggregates.
    # held_to_reference: trail_stop/barrier ran full window without triggering — include.
    # censored (legacy): for HOLD/EMA policies that exceeded the window — legacy exclude.
    n_short_path = int(perfire["short_path"].sum()) if "short_path" in perfire.columns else 0
    n_held_to_reference = int(perfire["held_to_reference"].sum()) if "held_to_reference" in perfire.columns else 0
    n_censored = int(perfire["censored"].sum()) if "censored" in perfire.columns else 0

    # Exclude ONLY short_path rows (plus legacy censored) from WR/return aggregates.
    # held_to_reference rows are included — their exit_ret is the reference-horizon return.
    exclude_mask = pd.Series(False, index=perfire.index)
    if "short_path" in perfire.columns:
        exclude_mask |= perfire["short_path"].astype(bool)
    if "censored" in perfire.columns:
        exclude_mask |= perfire["censored"].astype(bool)
    included = perfire[~exclude_mask]

    # Episode clusters: count distinct clusters in the perfire results
    n_clusters = 0
    if cluster_col in perfire.columns:
        n_clusters = int(perfire[cluster_col].nunique())
    elif "ticker" in perfire.columns and "fire_date" in perfire.columns:
        year_s = pd.to_datetime(perfire["fire_date"], errors="coerce").dt.year.astype(str)
        synthetic = perfire["ticker"].astype(str) + "_" + year_s
        n_clusters = int(synthetic.nunique())

    # Win rate and returns computed over all included fires (short_path and censored excluded).
    if len(included) > 0 and "exit_ret" in included.columns:
        exit_rets = pd.to_numeric(included["exit_ret"], errors="coerce").dropna()
        wr = float((exit_rets > 0).mean()) if len(exit_rets) > 0 else None
        mean_exit_ret = float(exit_rets.mean()) if len(exit_rets) > 0 else None
        median_exit_ret = float(exit_rets.median()) if len(exit_rets) > 0 else None
    else:
        wr = mean_exit_ret = median_exit_ret = None

    # Regret metrics computed over all fires (not just included — regret vs reference is
    # meaningful for all fires with a valid forward path, including held_to_reference).
    mean_foregone = None
    if "foregone_mfe_126" in perfire.columns:
        fm = pd.to_numeric(perfire["foregone_mfe_126"], errors="coerce").dropna()
        mean_foregone = float(fm.mean()) if len(fm) > 0 else None

    mean_avoided = None
    if "avoided_mae_126" in perfire.columns:
        am = pd.to_numeric(perfire["avoided_mae_126"], errors="coerce").dropna()
        mean_avoided = float(am.mean()) if len(am) > 0 else None

    # Regret ratio: avoided_mae / foregone_mfe (>1 = saved more than gave up)
    regret_ratio = None
    if mean_foregone is not None and mean_avoided is not None and mean_foregone > 0:
        regret_ratio = round(mean_avoided / mean_foregone, 4)
    elif mean_foregone is not None and mean_foregone == 0 and mean_avoided is not None:
        regret_ratio = None  # degenerate: foregone_mfe=0 means nothing was given up

    return {
        "n_fires": n_total,
        "n_censored": n_censored,
        "n_short_path": n_short_path,
        "n_held_to_reference": n_held_to_reference,
        "short_path_pct": round(n_short_path / n_total, 4) if n_total > 0 else None,
        "held_to_reference_pct": round(n_held_to_reference / n_total, 4) if n_total > 0 else None,
        "censoring_rate": round(n_censored / n_total, 4) if n_total > 0 else None,
        "episode_clusters": n_clusters,
        "wr": round(wr, 4) if wr is not None else None,
        "mean_exit_ret": round(mean_exit_ret, 4) if mean_exit_ret is not None else None,
        "median_exit_ret": round(median_exit_ret, 4) if median_exit_ret is not None else None,
        "mean_foregone_mfe_126": round(mean_foregone, 4) if mean_foregone is not None else None,
        "mean_avoided_mae_126": round(mean_avoided, 4) if mean_avoided is not None else None,
        "regret_ratio": regret_ratio,
    }


def _era_tier_splits(
    perfire: pd.DataFrame,
    cluster_col: str = "episode_cluster",
) -> dict[str, Any]:
    """Compute era-law and tier splits from perfire results."""
    result: dict[str, Any] = {}

    # ERA LAW split
    if "era_cohort" in perfire.columns:
        for era in ["verdict_grade_2021plus", "survivor_biased"]:
            sub = perfire[perfire["era_cohort"] == era]
            result[f"era_{era}"] = _cell_stats(sub, sub, cluster_col)

    # Tier cascade split (if present in perfire)
    if "tier_cascade" in perfire.columns:
        for tier in sorted(perfire["tier_cascade"].dropna().unique()):
            sub = perfire[perfire["tier_cascade"] == tier]
            result[f"tier_{tier}"] = _cell_stats(sub, sub, cluster_col)

    return result


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------
def run_experiment(
    exp_id: str,
    *,
    boarded_path: Path | None = None,
    massive_dir: Path | None = None,
    registry_path: Path | None = None,
    results_dir: Path | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Run a registered rule experiment.

    Parameters
    ----------
    exp_id        : experiment ID from the registry
    boarded_path  : override replay_boarded.parquet path
    massive_dir   : override massive_stock_day directory
    registry_path : override registry.jsonl path
    results_dir   : override output directory for results
    dry_run       : if True, print plan and return without computing

    Returns
    -------
    dict — the summary JSON payload (also written to disk unless dry_run)
    """
    t0 = time.time()
    rp = registry_path or (_REPO_ROOT / "data" / "rule_experiments" / "registry.jsonl")
    bp = boarded_path or _BOARDED_PATH
    md = massive_dir or _MASSIVE_DIR
    rd = results_dir or _RESULTS_DIR

    # ── 1. Load registry entry ──────────────────────────────────────────────
    log.info("Loading experiment %r from registry: %s", exp_id, rp)
    try:
        exp_entry = load_experiment(exp_id, rp)
    except KeyError as exc:
        raise GovernorRefusal(str(exc)) from exc

    log.info(
        "Experiment: budget=%d, status=%s, criteria=%s",
        exp_entry.get("declared_budget"),
        exp_entry.get("status"),
        exp_entry.get("verdict_criteria"),
    )

    # ── 2. Reconstruct the grid ─────────────────────────────────────────────
    log.info("Reconstructing grid for %r", exp_id)
    specs = _build_grid(exp_id, exp_entry)
    log.info("Grid: %d cells", len(specs))
    for s in specs:
        log.info("  %s  hash=%s", s.spec_id, s.content_hash()[:12])

    # ── 3. Verify EVERY spec hash against registry (hard-fail on mismatch) ──
    log.info("Verifying spec hashes against registry...")
    verify_spec_hashes(exp_entry, specs)  # raises GovernorRefusal on mismatch
    log.info("Hash verification PASSED for all %d cells.", len(specs))

    # Build registry_hashes set for replay_spec governor
    registry_hashes = set(exp_entry.get("spec_hashes", []))

    if dry_run:
        log.info("DRY RUN — stopping before data load.")
        return {"dry_run": True, "exp_id": exp_id, "n_cells": len(specs)}

    # ── 4. Load fires from replay_boarded ───────────────────────────────────
    log.info("Loading fires from %s", bp)
    if not bp.exists():
        raise FileNotFoundError(
            f"replay_boarded.parquet not found: {bp}. "
            "This is the canonical data plane. Run the replay pipeline first."
        )
    fires_full = pd.read_parquet(bp)
    log.info("Loaded %d rows from replay_boarded", len(fires_full))

    # Apply experiment's cohort filter (built from the first spec's cohort —
    # all specs share the same cohort for EXIT-GRID-1)
    primary_cohort = specs[0].cohort
    cohort_mask = primary_cohort.apply(fires_full)
    fires_df = fires_full[cohort_mask].reset_index(drop=True)
    log.info(
        "Cohort filter: %d/%d rows match (%.1f%%)",
        len(fires_df), len(fires_full), 100 * len(fires_df) / max(1, len(fires_full)),
    )

    if len(fires_df) == 0:
        raise ValueError(
            f"Cohort filter for {exp_id!r} matched 0 rows. Check the filter predicates."
        )

    # Assign episode clusters before replay (so they can be joined to perfire)
    cluster_series, cluster_defn = _assign_episode_cluster(fires_df)
    fires_df = fires_df.copy()
    fires_df["episode_cluster"] = cluster_series.values
    log.info("Episode cluster definition: %s", cluster_defn)
    log.info("Distinct episode clusters in cohort: %d", fires_df["episode_cluster"].nunique())

    # ── 5. Load closes for all tickers in cohort ────────────────────────────
    ticker_col = "ticker" if "ticker" in fires_df.columns else fires_df.columns[0]
    tickers = sorted(fires_df[ticker_col].unique())
    log.info("Loading closes for %d unique tickers...", len(tickers))
    closes = _load_closes(tickers, md)
    log.info("Loaded closes for %d/%d tickers", len(closes), len(tickers))

    coverage_frac = len(closes) / len(tickers) if tickers else 0.0

    # ── 6. Replay each spec ─────────────────────────────────────────────────
    all_perfire: dict[str, pd.DataFrame] = {}
    cell_summaries: dict[str, dict] = {}

    for spec in specs:
        log.info("Replaying spec %s...", spec.spec_id)
        try:
            pf = replay_spec(
                spec,
                fires_df,
                closes,
                registry_hashes=registry_hashes,
            )
        except Exception as exc:
            log.error("Spec %s failed entirely: %s", spec.spec_id, exc)
            # Produce an all-null cell rather than crashing
            pf = pd.DataFrame([{
                "fire_idx": None,
                "ticker": None,
                "fire_date": None,
                "exit_bar_offset": None,
                "exit_ret": None,
                "mae_to_exit": None,
                "mfe_to_exit": None,
                "holding_days": None,
                "censored": True,
                "survivorship_biased": None,
                "era_cohort": None,
                "episode_cluster": None,
            }])

        # Attach episode_cluster to perfire results by joining on fire_idx
        # (fire_idx is the original row index from fires_df)
        if "fire_idx" in pf.columns and "episode_cluster" not in pf.columns:
            cluster_map = fires_df["episode_cluster"].to_dict()
            pf["episode_cluster"] = pf["fire_idx"].map(cluster_map)

        # Also carry tier_cascade for era/tier splits
        if "tier_cascade" not in pf.columns and "tier_cascade" in fires_df.columns:
            tier_map = fires_df["tier_cascade"].to_dict()
            pf["tier_cascade"] = pf["fire_idx"].map(tier_map)

        all_perfire[spec.spec_id] = pf

        # Per-cell stats
        cell_summaries[spec.spec_id] = _cell_stats(pf, fires_df, cluster_col="episode_cluster")

        n_fires_cell = cell_summaries[spec.spec_id]["n_fires"]
        n_floor = exp_entry.get("n_floor", 300)
        if n_fires_cell < n_floor:
            log.warning(
                "Cell %s: n=%d < n_floor=%d — below minimum verdict-grade fires",
                spec.spec_id, n_fires_cell, n_floor,
            )

        log.info(
            "  %s: n=%d wr=%.3f censored=%.1f%% clusters=%d",
            spec.spec_id,
            n_fires_cell,
            cell_summaries[spec.spec_id]["wr"] or 0,
            100 * (cell_summaries[spec.spec_id]["censoring_rate"] or 0),
            cell_summaries[spec.spec_id]["episode_clusters"],
        )

    # ── 7. Build vintage stamp ──────────────────────────────────────────────
    universe_as_of = date.today().isoformat()
    stamp = vintage_stamp(
        price_plane_id="massive_stock_day_v1",
        adjustment_mode="split_adjusted_raw",
        universe_as_of=universe_as_of,
        frame="pit_massive_era_law",
        survivorship_biased=False,  # verdict_grade cohort only (2021+)
        coverage_frac=round(coverage_frac, 4),
        dead_name_coverage_pct=None,  # triggers file read
        era_law_cohort="verdict_grade_2021plus",
    )

    # ── 8. Cumulative pooled trial count ────────────────────────────────────
    cumulative_trials = pooled_replay_trial_count(rp)
    log.info("Cumulative pooled replay trial count: %d", cumulative_trials)

    # ── 9. Build summary JSON ───────────────────────────────────────────────
    run_ts = datetime.now(timezone.utc).isoformat()
    runtime_s = round(time.time() - t0, 2)

    summary: dict[str, Any] = {
        "exp_id": exp_id,
        "run_at": run_ts,
        "runtime_s": runtime_s,
        "vintage_stamp": stamp,
        "cumulative_pooled_replay_trial_count": cumulative_trials,
        "episode_cluster_definition": cluster_defn,
        "cohort_n": len(fires_df),
        "cohort_tickers": len(tickers),
        "cohort_closes_loaded": len(closes),
        "coverage_frac": round(coverage_frac, 4),
        "declared_budget": exp_entry.get("declared_budget"),
        "verdict_criteria": exp_entry.get("verdict_criteria"),
        "derived_from_surface": exp_entry.get("derived_from_surface"),
        "cells": {},
    }

    # Every cell in the declared grid appears in the summary (nulls included)
    for spec in specs:
        stats = cell_summaries[spec.spec_id]
        pf = all_perfire[spec.spec_id]
        era_tier = _era_tier_splits(pf, cluster_col="episode_cluster")
        summary["cells"][spec.spec_id] = {
            **stats,
            "spec_hash": spec.content_hash(),
            "exit_policy": spec.exit.to_dict(),
            "era_tier_splits": era_tier,
        }

    # ── 10. Write perfire.parquet (gitignored Mac-local) ───────────────────
    rd.mkdir(parents=True, exist_ok=True)
    combined_pf_parts = []
    for spec_id, pf in all_perfire.items():
        pf2 = pf.copy()
        pf2["spec_id"] = spec_id
        combined_pf_parts.append(pf2)

    if combined_pf_parts:
        combined_pf = pd.concat(combined_pf_parts, ignore_index=True)
        pf_path = rd / f"{exp_id}_perfire.parquet"
        combined_pf.to_parquet(pf_path, index=False)
        log.info("Written perfire.parquet: %s (%d rows)", pf_path, len(combined_pf))

    # ── 11. Write summary.json (git-committed, vintage-stamped) ────────────
    summary_path = rd / f"{exp_id}_summary.json"

    def _json_safe(v: Any) -> Any:
        if v is None:
            return None
        if isinstance(v, (np.bool_,)):
            return bool(v)
        if isinstance(v, bool):
            return bool(v)
        if isinstance(v, (np.integer,)):
            return int(v)
        if isinstance(v, (np.floating,)):
            return float(v) if not np.isnan(v) else None
        if isinstance(v, pd.Timestamp):
            return str(v.date())
        if isinstance(v, dict):
            return {k: _json_safe(vv) for k, vv in v.items()}
        if isinstance(v, list):
            return [_json_safe(vv) for vv in v]
        return v

    summary_clean = _json_safe(summary)
    with open(summary_path, "w", encoding="utf-8") as fh:
        json.dump(summary_clean, fh, indent=2)
    log.info("Written summary.json: %s", summary_path)

    # ── 12. Update lifecycle status ─────────────────────────────────────────
    update_experiment_status(
        exp_id,
        "executed",
        registry_path=rp,
        extra_fields={"run_at": run_ts, "runtime_s": runtime_s},
    )
    update_experiment_status(
        exp_id,
        "reported",
        registry_path=rp,
        extra_fields={"summary_path": str(summary_path), "run_at": run_ts},
    )
    log.info("Lifecycle: executed → reported for %r", exp_id)

    total_time = round(time.time() - t0, 2)
    log.info("Run complete: %s in %.1fs", exp_id, total_time)
    summary["runtime_s"] = total_time
    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "NW Rails R1 governed runner. --exp-id is required. "
            "No --adhoc flag exists (house-law violation per RUL-P3)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--exp-id",
        required=True,
        help="Registered experiment ID (must exist in registry.jsonl)",
    )
    parser.add_argument(
        "--boarded-path",
        type=Path,
        default=None,
        help=f"Override replay_boarded.parquet path (default: {_BOARDED_PATH})",
    )
    parser.add_argument(
        "--massive-dir",
        type=Path,
        default=None,
        help=f"Override massive_stock_day directory (default: {_MASSIVE_DIR})",
    )
    parser.add_argument(
        "--registry-path",
        type=Path,
        default=None,
        help="Override registry.jsonl path",
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=None,
        help=f"Override results output directory (default: {_RESULTS_DIR})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print plan without computing or writing any files",
    )

    args = parser.parse_args()

    try:
        summary = run_experiment(
            args.exp_id,
            boarded_path=args.boarded_path,
            massive_dir=args.massive_dir,
            registry_path=args.registry_path,
            results_dir=args.results_dir,
            dry_run=args.dry_run,
        )
    except GovernorRefusal as exc:
        log.error("GOVERNOR REFUSAL: %s", exc)
        return 2
    except FileNotFoundError as exc:
        log.error("DATA NOT FOUND: %s", exc)
        return 3
    except Exception as exc:
        log.exception("Unexpected error: %s", exc)
        return 1

    if args.dry_run:
        print("DRY RUN complete. No files written.")
        return 0

    # Print per-cell summary table
    print("\n=== EXIT GRID RESULTS ===")
    print(f"exp_id: {summary['exp_id']}")
    print(f"Cumulative pooled replay trial count: {summary['cumulative_pooled_replay_trial_count']}")
    print(f"Episode cluster definition: {summary['episode_cluster_definition']}")
    print(f"Cohort n_fires: {summary['cohort_n']}")
    print()
    print(
        f"{'Cell':<35} {'n_fires':>8} {'clusters':>9} {'WR':>7} {'mean_ret':>9} "
        f"{'foregone_mfe':>13} {'avoided_mae':>12} {'regret_ratio':>13} {'censor%':>8}"
    )
    print("-" * 130)
    for cell_id, stats in summary["cells"].items():
        short_id = cell_id.replace("exit_grid_v1/", "")
        print(
            f"{short_id:<35} "
            f"{str(stats.get('n_fires', 'N/A')):>8} "
            f"{str(stats.get('episode_clusters', 'N/A')):>9} "
            f"{str(stats.get('wr', 'N/A')):>7} "
            f"{str(stats.get('mean_exit_ret', 'N/A')):>9} "
            f"{str(stats.get('mean_foregone_mfe_126', 'N/A')):>13} "
            f"{str(stats.get('mean_avoided_mae_126', 'N/A')):>12} "
            f"{str(stats.get('regret_ratio', 'N/A')):>13} "
            f"{str(round(100*(stats.get('censoring_rate') or 0), 1))+'%':>8}"
        )

    print(f"\nRuntime: {summary['runtime_s']}s")
    print(f"Summary written to: {_RESULTS_DIR}/{summary['exp_id']}_summary.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
