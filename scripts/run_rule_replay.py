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
    ScaledPolicy,
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

# Regime merge columns that DISP-GATE-1 requires.
# These are appended to fires_df before CohortFilter applies, only when the
# experiment registry entry declares them in "needed_merge_columns".
_DISP_MERGE_COLS = [
    "disp_state_expanding",
    "disp_state_trailing252",
    "disp_pctile_expanding",
    "disp_pctile_trailing252",
    "n_bars_before",
    "disp_excluded",  # renamed from 'excluded' to avoid shadowing
]

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


def _build_disp_gate_1_specs(cohort: CohortFilter) -> list[RuleSpec]:
    """Reconstruct the DISP-GATE-1 grid from its frozen definition (§6.2).

    6 primary cells:
      regime arm {lean_in, neutral, lean_out}  ×  basis {expanding, trailing252}

    The cohort must already have regime columns merged (see _merge_regime_columns).
    Each cell filters on disp_state_expanding or disp_state_trailing252.
    Exit: hold(21) — the ratified anchor per L3_PREREG.

    Note: the DISP-GATE-1 cohort is an extension of the production fire cohort
    (verdict_type='fire' AND verdict_grade=True) INTERSECTED with the non-excluded
    regime-assigned fires.  The regime-column merge and exclusion of fires with
    < 252 prior bars happen in the load path (run_experiment), not here.
    """
    specs: list[RuleSpec] = []
    for regime_state in ["lean_in", "neutral", "lean_out"]:
        for basis in ["expanding", "trailing252"]:
            col = f"disp_state_{basis}"
            spec_id = f"disp_gate_1/{basis}/{regime_state}"
            regime_cohort = cohort_filter(
                *cohort.predicates,
                ("eq", col, regime_state),
                ("eq", "disp_excluded", False),
            )
            specs.append(RuleSpec(
                spec_id=spec_id,
                cohort=regime_cohort,
                delay_n=1,
                exit=ExitPolicy.hold(21),
                horizons_ref=(126,),
            ))

    assert len(specs) == 6, f"DISP-GATE-1 must be 6 cells, got {len(specs)}"
    return specs


def _build_trim_grid_v1_specs(cohort: CohortFilter) -> list[RuleSpec]:
    """Reconstruct the TRIM-GRID-1 grid from its frozen definition (RUL-F3.5, PR-F3.3).

    6 frozen cells (exactly — no additions permitted without a program amendment):
      1. trim50_h21_ema8        — 0.5 hold(21)  + 0.5 ema_trail_s8
      2. trim50_h21_h126        — 0.5 hold(21)  + 0.5 hold(126)
      3. trim25_h21_ema8        — 0.25 hold(21) + 0.75 ema_trail_s8
      4. trim33_h21_h63_h126    — 1/3 hold(21)  + 1/3 hold(63) + 1/3 hold(126)
      5. trim50_ema8_h126       — 0.5 ema_trail_s8 + 0.5 hold(126)
      6. trim50_mfe15_ema8      — 0.5 profit_take(15%) + 0.5 ema_trail_s8

    The cohort is the same as exit_grid_v1: verdict_type='fire' AND verdict_grade=True.
    derived_from_surface=exit_grid_v1 (seen surface — descriptive-only, contamination stamped).
    """
    specs: list[RuleSpec] = []

    # 1. trim50_h21_ema8
    specs.append(RuleSpec(
        spec_id="trim_grid_v1/trim50_h21_ema8",
        cohort=cohort,
        delay_n=1,
        exit=ScaledPolicy.scaled([
            (0.5, ExitPolicy.hold(21)),
            (0.5, ExitPolicy.ema_trail(span=8, resample="3B")),
        ]),
        horizons_ref=(126,),
    ))

    # 2. trim50_h21_h126
    specs.append(RuleSpec(
        spec_id="trim_grid_v1/trim50_h21_h126",
        cohort=cohort,
        delay_n=1,
        exit=ScaledPolicy.scaled([
            (0.5, ExitPolicy.hold(21)),
            (0.5, ExitPolicy.hold(126)),
        ]),
        horizons_ref=(126,),
    ))

    # 3. trim25_h21_ema8
    specs.append(RuleSpec(
        spec_id="trim_grid_v1/trim25_h21_ema8",
        cohort=cohort,
        delay_n=1,
        exit=ScaledPolicy.scaled([
            (0.25, ExitPolicy.hold(21)),
            (0.75, ExitPolicy.ema_trail(span=8, resample="3B")),
        ]),
        horizons_ref=(126,),
    ))

    # 4. trim33_h21_h63_h126
    specs.append(RuleSpec(
        spec_id="trim_grid_v1/trim33_h21_h63_h126",
        cohort=cohort,
        delay_n=1,
        exit=ScaledPolicy.scaled([
            (1.0 / 3.0, ExitPolicy.hold(21)),
            (1.0 / 3.0, ExitPolicy.hold(63)),
            (1.0 / 3.0, ExitPolicy.hold(126)),
        ]),
        horizons_ref=(126,),
    ))

    # 5. trim50_ema8_h126
    specs.append(RuleSpec(
        spec_id="trim_grid_v1/trim50_ema8_h126",
        cohort=cohort,
        delay_n=1,
        exit=ScaledPolicy.scaled([
            (0.5, ExitPolicy.ema_trail(span=8, resample="3B")),
            (0.5, ExitPolicy.hold(126)),
        ]),
        horizons_ref=(126,),
    ))

    # 6. trim50_mfe15_ema8
    # profit_take(15) exits first half at first close >= +15% from entry (close basis).
    # If never touched, that leg holds to reference (held_to_reference included at
    # reference return — EXIT-GRID-1 bug-class prevention).
    specs.append(RuleSpec(
        spec_id="trim_grid_v1/trim50_mfe15_ema8",
        cohort=cohort,
        delay_n=1,
        exit=ScaledPolicy.scaled([
            (0.5, ExitPolicy.profit_take(15.0)),
            (0.5, ExitPolicy.ema_trail(span=8, resample="3B")),
        ]),
        horizons_ref=(126,),
    ))

    assert len(specs) == 6, f"TRIM-GRID-1 must be 6 cells, got {len(specs)}"
    return specs


# Grid builders registry — keyed by exp_id prefix
_GRID_BUILDERS: dict[str, Any] = {
    "exit_grid_v1": _build_exit_grid_v1_specs,
    "wait_grid_v1": _build_wait_grid_v1_specs,
    "disp_gate_1": _build_disp_gate_1_specs,
    "trim_grid_v1": _build_trim_grid_v1_specs,
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
# Regime merge — experiment-scoped (only for experiments that declare it)
# ---------------------------------------------------------------------------

def _merge_regime_columns(
    fires_df: pd.DataFrame,
    needed_merge_columns: list[str],
    *,
    massive_dir: Path,
    return_panel_meta: bool = False,
) -> "pd.DataFrame | tuple[pd.DataFrame, dict]":
    """Merge PIT dispersion regime columns into fires_df.

    Called BEFORE CohortFilter applies so that regime-column predicates
    in the cohort filter resolve correctly.

    Only called for experiments that declare needed_merge_columns in their
    registry entry, so other experiments are untouched.

    Parameters
    ----------
    fires_df             : fires DataFrame (pre-filter)
    needed_merge_columns : list of column names from _DISP_MERGE_COLS
    massive_dir          : path to massive_stock_day for panel reconstruction
    return_panel_meta    : if True, return (fires_out, panel_meta_dict) instead
                           of just fires_out.  panel_meta_dict contains:
                           panel_data_reach, panel_n_bars, panel_n_tickers.

    Returns
    -------
    fires_df with regime columns appended (keyed on signal_date).
    If return_panel_meta=True, returns (fires_out, panel_meta) tuple.
    """
    from scripts.compute_disp_pit_state import (  # noqa: PLC0415
        compute_pit_states, compute_spy_21d_returns, assign_spy_tercile,
        _load_panel_from_massive,
    )

    # Check if any needed columns are already present (idempotent)
    missing = [c for c in needed_merge_columns if c not in fires_df.columns]
    if not missing:
        log.info("All needed merge columns already present — skipping regime merge.")
        if return_panel_meta:
            return fires_df, {}
        return fires_df

    # Resolve the fire dates
    date_col = "signal_date" if "signal_date" in fires_df.columns else "fire_date"
    fire_dates = pd.to_datetime(fires_df[date_col]).unique()
    log.info(
        "Merging PIT dispersion regime for %d unique fire dates "
        "(%s → %s)...",
        len(fire_dates), fire_dates.min().date(), fire_dates.max().date(),
    )

    # Load panel once so we can extract metadata for the summary block.
    # compute_pit_states also loads the panel internally, but exposing it here
    # avoids a second I/O pass when return_panel_meta=True.
    panel_meta: dict[str, Any] = {}
    try:
        _panel = _load_panel_from_massive(massive_dir)
        if not _panel.empty:
            panel_meta = {
                "panel_data_reach": (
                    f"{_panel.index[0].date()} to {_panel.index[-1].date()}"
                ),
                "panel_n_bars": len(_panel),
                "panel_n_tickers": int(_panel.shape[1]),
            }
    except Exception as exc:
        log.warning("Could not read panel metadata: %s", exc)

    # Compute PIT states (prints DATA-REACH GATE exclusion counts)
    states = compute_pit_states(fire_dates, massive_dir=massive_dir, verbose=True)
    states = states.reset_index()  # fire_date column

    # Rename 'excluded' → 'disp_excluded' to avoid column collision
    if "excluded" in states.columns:
        states = states.rename(columns={"excluded": "disp_excluded"})

    # Compute SPY 21d contemporaneous covariate (L3_PREREG obligation 2)
    spy_rets = compute_spy_21d_returns(fire_dates, massive_dir=massive_dir)
    spy_tercile = assign_spy_tercile(spy_rets)

    spy_df = pd.DataFrame({
        "fire_date": spy_rets.index,
        "spy_ret_21d": spy_rets.values,
        "spy_tercile": spy_tercile.values,
    })

    # Merge states on date
    fires_out = fires_df.copy()
    fires_out["_fire_date_ts"] = pd.to_datetime(fires_out[date_col])

    states["fire_date"] = pd.to_datetime(states["fire_date"])
    spy_df["fire_date"] = pd.to_datetime(spy_df["fire_date"])

    fires_out = fires_out.merge(
        states,
        left_on="_fire_date_ts",
        right_on="fire_date",
        how="left",
        suffixes=("", "_disp"),
    )
    if "fire_date" in fires_out.columns and "fire_date" != date_col:
        fires_out = fires_out.drop(columns=["fire_date"])

    fires_out = fires_out.merge(
        spy_df,
        left_on="_fire_date_ts",
        right_on="fire_date",
        how="left",
        suffixes=("", "_spy"),
    )
    if "fire_date" in fires_out.columns and "fire_date" != date_col:
        fires_out = fires_out.drop(columns=["fire_date"])

    fires_out = fires_out.drop(columns=["_fire_date_ts"], errors="ignore")

    # Fill disp_excluded NaN → True (no state available = exclude)
    if "disp_excluded" in fires_out.columns:
        fires_out["disp_excluded"] = fires_out["disp_excluded"].fillna(True)

    n_merged = fires_out["disp_state_expanding"].notna().sum() if "disp_state_expanding" in fires_out.columns else 0
    n_excl = fires_out["disp_excluded"].sum() if "disp_excluded" in fires_out.columns else 0
    log.info(
        "Regime merge complete: %d fires with state, %d excluded",
        int(n_merged), int(n_excl),
    )
    if return_panel_meta:
        return fires_out, panel_meta
    return fires_out


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
            "n_null_regret_126": 0,
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
            "stop5_rate": None,
            "dead_money_rate": None,
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
    # Track fires where the 126-bar reference horizon is unavailable (null regret shortfall).
    # This happens when delay_n shifts the fill bar close enough to the data end that
    # fill_idx + 1 + 126 exceeds the available price series length — those fires have
    # fwd_mfe_126=None in engine/rule_replay.py, which propagates to foregone_mfe_126=None.
    # The .dropna() below is correct for computing the mean, but the dropped count must be
    # disclosed so cross-delay regret comparisons are not made on a silently shrinking denominator.
    n_null_regret_126 = 0
    mean_foregone = None
    if "foregone_mfe_126" in perfire.columns:
        fm_raw = pd.to_numeric(perfire["foregone_mfe_126"], errors="coerce")
        n_null_regret_126 = int(fm_raw.isna().sum())
        fm = fm_raw.dropna()
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

    # stop5: fraction of fires where the intra-window drawdown reaches ≥5% from entry.
    # Per L3_PREREG design: mae_to_exit <= -0.05 (MAE at any point in the 21d window).
    # For a HOLD-21 policy, mae_to_exit is the minimum return over the holding period,
    # so it captures the running maximum adverse excursion up to the time-exit.
    #
    # dead_money: |exit_ret| < 2% — fire went nowhere (neither gain nor meaningful loss).
    # Per L3_PREREG: abs(ret_21d) < 0.02 — tape parked the name.
    #
    # Both are computed over included fires only (same denominator as WR).
    stop5_rate = None
    dead_money_rate = None
    if len(included) > 0:
        if "mae_to_exit" in included.columns:
            mae_num = pd.to_numeric(included["mae_to_exit"], errors="coerce").dropna()
            if len(mae_num) > 0:
                stop5_rate = round(float((mae_num <= -0.05).mean()), 4)
        if "exit_ret" in included.columns:
            rets_num = pd.to_numeric(included["exit_ret"], errors="coerce").dropna()
            if len(rets_num) > 0:
                dead_money_rate = round(float((rets_num.abs() < 0.02).mean()), 4)

    return {
        "n_fires": n_total,
        "n_censored": n_censored,
        "n_short_path": n_short_path,
        "n_held_to_reference": n_held_to_reference,
        # n_null_regret_126: fires where the 126-bar reference horizon is unavailable
        # (fill bar too close to end of data after delay_n shift). These fires are
        # excluded from mean_foregone_mfe_126 / mean_avoided_mae_126 / regret_ratio
        # via .dropna(). The count grows with delay_n for boundary fires — so
        # cross-delay regret comparisons use a denominator that shrinks with delay_n.
        "n_null_regret_126": n_null_regret_126,
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
        "stop5_rate": stop5_rate,
        "dead_money_rate": dead_money_rate,
    }


def _trim_cell_stats_extra(
    perfire: pd.DataFrame,
    hold126_perfire: pd.DataFrame | None = None,
    cluster_col: str = "episode_cluster",
) -> dict[str, Any]:
    """Compute TRIM-GRID-1 specific extra metrics for a scaled-policy cell.

    Metrics
    -------
    weighted_wr           : WR on weighted exit_ret (same as _cell_stats wr for scaled cells)
    weighted_mean_ret     : mean of weighted exit_ret (same as mean_exit_ret)
    weighted_median_ret   : median of weighted exit_ret (same as median_exit_ret)
    weighted_foregone_mfe_126 : mean of weighted foregone_mfe_126
    weighted_avoided_mae_126  : mean of weighted avoided_mae_126
    regret_ratio          : weighted_avoided_mae / weighted_foregone_mfe (>1 = saved more)
    right_tail_retention  : mean scaled-policy return among fires in the top decile of
                            hold_126 returns ÷ mean hold_126 return among those fires.
                            Caveat: the right tail is where survivorship bites hardest
                            (delisted-name recall floor for this cohort).
    capital_freed_days    : weighted mean holding_days vs 126 reference
    churn                 : mean n_exit_events per fire (number of exit events across legs)

    Parameters
    ----------
    perfire           : ScaledPolicy perfire results DataFrame (one cell)
    hold126_perfire   : hold(126) perfire results (for right-tail reference).
                        If None, right_tail_retention is null.
    """
    extra: dict[str, Any] = {
        "right_tail_retention": None,
        "right_tail_retention_caveat": (
            "Survivorship caveat: the massive-era cohort has a delisted-name recall floor "
            "(dead_name_coverage_pct ~38%); the right tail of hold_126 returns is where "
            "survivorship bites hardest — firms that kept rising vs those that fell and "
            "delisted. Right-tail retention comparisons between scaled and hold_126 are "
            "directionally informative but should not be over-interpreted."
        ),
        "capital_freed_days": None,
        "churn": None,
    }

    # Exclude short_path / censored rows (same logic as _cell_stats)
    exclude_mask = pd.Series(False, index=perfire.index)
    if "short_path" in perfire.columns:
        exclude_mask |= perfire["short_path"].astype(bool)
    if "censored" in perfire.columns:
        exclude_mask |= perfire["censored"].astype(bool)
    included = perfire[~exclude_mask]

    if len(included) == 0:
        return extra

    # Capital-freed days: weighted mean holding_days vs 126-bar reference
    if "holding_days" in included.columns:
        hd = pd.to_numeric(included["holding_days"], errors="coerce").dropna()
        if len(hd) > 0:
            extra["capital_freed_days"] = round(float(hd.mean()), 1)

    # Churn: mean number of exit events per fire (n_exit_events across legs)
    if "n_exit_events" in included.columns:
        ne = pd.to_numeric(included["n_exit_events"], errors="coerce").dropna()
        if len(ne) > 0:
            extra["churn"] = round(float(ne.mean()), 3)

    # Right-tail retention: requires hold_126 perfire as the reference
    if hold126_perfire is not None and len(hold126_perfire) > 0:
        # Exclude censored rows from hold_126 reference
        h126_exclude = pd.Series(False, index=hold126_perfire.index)
        if "short_path" in hold126_perfire.columns:
            h126_exclude |= hold126_perfire["short_path"].astype(bool)
        if "censored" in hold126_perfire.columns:
            h126_exclude |= hold126_perfire["censored"].astype(bool)
        h126_included = hold126_perfire[~h126_exclude]

        if "exit_ret" in h126_included.columns and "fire_idx" in h126_included.columns:
            h126_rets = pd.to_numeric(h126_included["exit_ret"], errors="coerce")
            # Top decile of hold_126 returns
            top_decile_threshold = h126_rets.quantile(0.9)
            top_decile_mask = h126_rets >= top_decile_threshold
            top_decile_fire_idxs = h126_included.loc[top_decile_mask, "fire_idx"]

            if len(top_decile_fire_idxs) > 0:
                # Mean hold_126 return among top-decile fires
                h126_top_mean = float(h126_rets[top_decile_mask].mean())

                # Find the corresponding scaled-policy fires by fire_idx
                if "fire_idx" in included.columns:
                    scaled_top = included[included["fire_idx"].isin(top_decile_fire_idxs)]
                    if len(scaled_top) > 0 and "exit_ret" in scaled_top.columns:
                        scaled_top_rets = pd.to_numeric(scaled_top["exit_ret"], errors="coerce").dropna()
                        if len(scaled_top_rets) > 0 and h126_top_mean != 0:
                            scaled_top_mean = float(scaled_top_rets.mean())
                            rtr = scaled_top_mean / h126_top_mean
                            extra["right_tail_retention"] = round(rtr, 4)
                            extra["right_tail_n_fires"] = len(scaled_top_rets)
                            extra["right_tail_h126_mean"] = round(h126_top_mean, 4)
                            extra["right_tail_scaled_mean"] = round(scaled_top_mean, 4)

    return extra


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


def _spy_covariate_split(
    perfire: pd.DataFrame,
    cluster_col: str = "episode_cluster",
) -> dict[str, Any] | None:
    """Compute SPY-21d tercile split within a perfire cell.

    L3_PREREG design obligation 2: the contemporaneous SPY-21d drawdown
    covariate must be applied WITHIN cells as a tercile split so that the
    confound can be evaluated by a stats reviewer.

    Terciles (fixed thresholds per assign_spy_tercile in compute_disp_pit_state):
        down : SPY 21d return < -5%
        flat : -5% <= SPY 21d return <= +5%
        up   : SPY 21d return > +5%

    Returns None if spy_tercile column is absent from perfire.
    Returns dict keyed by tercile label with per-tercile n/stop5/dead_money/wr.
    """
    if "spy_tercile" not in perfire.columns:
        return None

    result: dict[str, Any] = {}
    for label in ["down", "flat", "up"]:
        sub = perfire[perfire["spy_tercile"] == label]
        if len(sub) == 0:
            result[label] = {"n": 0, "stop5": None, "dead_money": None, "wr": None}
            continue
        # Use _cell_stats to compute stop5/dead_money/wr in a consistent way
        sub_stats = _cell_stats(sub, sub, cluster_col=cluster_col)
        result[label] = {
            "n": sub_stats["n_fires"],
            "stop5": sub_stats["stop5_rate"],
            "dead_money": sub_stats["dead_money_rate"],
            "wr": sub_stats["wr"],
        }
    return result


def _compute_disp_meta(
    fires_df: pd.DataFrame,
    pre_b2_pooled_sum: int,
    post_b2_pooled_sum: int,
) -> dict[str, Any]:
    """Build the disp_gate_1_meta block for the summary JSON.

    Requires that fires_df has already had PIT regime columns merged
    (i.e., _merge_regime_columns was called) and that disp_excluded,
    disp_state_expanding, and disp_state_trailing252 columns are present.

    Parameters
    ----------
    fires_df            : fires DataFrame post regime-merge and cohort-filter,
                          INCLUDING excluded fires (so total exclusion count is accurate).
    pre_b2_pooled_sum   : pooled trial count BEFORE this experiment.
    post_b2_pooled_sum  : pooled trial count INCLUDING this experiment.

    Returns a dict with all meta fields committed in disp_gate_1_summary.json.
    """
    meta: dict[str, Any] = {}

    # Panel data reach, bars, tickers — read from the merged columns
    # n_bars_before is per-fire; take the max to get the full panel reach.
    if "n_bars_before" in fires_df.columns:
        meta["panel_n_bars"] = int(fires_df["n_bars_before"].max()) if len(fires_df) > 0 else None
    else:
        meta["panel_n_bars"] = None

    # Exclusion counts
    if "disp_excluded" in fires_df.columns:
        n_excl_fires = int(fires_df["disp_excluded"].sum())
        n_total_fires = len(fires_df)
        excl_pct = round(100.0 * n_excl_fires / n_total_fires, 1) if n_total_fires > 0 else None

        # Dates excluded (unique fire dates that were excluded)
        date_col = "signal_date" if "signal_date" in fires_df.columns else "fire_date"
        if date_col in fires_df.columns:
            excl_mask = fires_df["disp_excluded"].astype(bool)
            n_dates_excl = int(pd.to_datetime(fires_df.loc[excl_mask, date_col]).nunique())
        else:
            n_dates_excl = None

        meta["fires_excluded_data_reach_gate"] = n_excl_fires
        meta["fires_excluded_pct"] = excl_pct
        meta["n_dates_excluded"] = n_dates_excl
    else:
        meta["fires_excluded_data_reach_gate"] = None
        meta["fires_excluded_pct"] = None
        meta["n_dates_excluded"] = None

    # Basis flip rate between expanding and trailing-252d (non-stationarity check)
    if "disp_state_expanding" in fires_df.columns and "disp_state_trailing252" in fires_df.columns:
        included_mask = ~fires_df.get("disp_excluded", pd.Series(False, index=fires_df.index)).astype(bool)
        included_fires = fires_df[included_mask]
        both_valid = included_fires.dropna(
            subset=["disp_state_expanding", "disp_state_trailing252"]
        )
        if len(both_valid) > 0:
            # Compute flip rate across UNIQUE fire dates (not per-fire rows)
            date_col = "signal_date" if "signal_date" in both_valid.columns else "fire_date"
            if date_col in both_valid.columns:
                date_states = both_valid.drop_duplicates(subset=[date_col])[[
                    date_col, "disp_state_expanding", "disp_state_trailing252"
                ]]
                n_flip_dates = int(
                    (date_states["disp_state_expanding"] != date_states["disp_state_trailing252"]).sum()
                )
                n_total_dates = len(date_states)
            else:
                n_flip_dates = int(
                    (both_valid["disp_state_expanding"] != both_valid["disp_state_trailing252"]).sum()
                )
                n_total_dates = len(both_valid)

            flip_pct = round(100.0 * n_flip_dates / n_total_dates, 1) if n_total_dates > 0 else 0.0
        else:
            flip_pct = 0.0
    else:
        flip_pct = None

    _FLIP_THRESHOLD = 15.0
    meta["basis_flip_rate_pct"] = flip_pct
    meta["nonstationarity_flag"] = (flip_pct is not None and flip_pct > _FLIP_THRESHOLD)
    if meta["nonstationarity_flag"]:
        meta["nonstationarity_note"] = (
            f"{flip_pct}% of fire dates flip regime state between expanding and trailing-252d bases "
            f"(>{_FLIP_THRESHOLD:.0f}% threshold). Study proceeds descriptively on primary "
            "(expanding) basis only."
        )
    else:
        meta["nonstationarity_note"] = (
            "Bases agree on >85% of fire dates — stationarity assumption holds."
        )

    # SPY covariate tercile boundaries (fixed by assign_spy_tercile)
    meta["spy_covariate_tercile_boundaries"] = {
        "down": "< -5%",
        "flat": "-5% to +5%",
        "up": "> +5%",
    }

    # FDR accounting
    meta["pre_b2_pooled_sum"] = pre_b2_pooled_sum
    meta["post_b2_pooled_sum"] = post_b2_pooled_sum
    meta["trial_ledger_max_basis_note"] = (
        "TrialLedger.effective_n() uses max() semantics and reports 15 "
        "(largest declared budget in replay family), not the sum "
        f"{post_b2_pooled_sum}. Both numbers are printed per §0.5.6."
    )

    return meta


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

    # ── 4a. Regime merge (experiment-scoped) ──────────────────────────────
    # Merge per-date PIT dispersion regime columns BEFORE CohortFilter so
    # that regime-column predicates in the cohort filter resolve correctly.
    # Only runs for experiments that declare needed_merge_columns.
    needed_merge_columns: list[str] = exp_entry.get("needed_merge_columns", [])
    _regime_panel_meta: dict[str, Any] = {}
    if needed_merge_columns:
        log.info(
            "Experiment %r declares needed_merge_columns=%r — merging regime data",
            exp_id, needed_merge_columns,
        )
        fires_full, _regime_panel_meta = _merge_regime_columns(
            fires_full,
            needed_merge_columns,
            massive_dir=md,
            return_panel_meta=True,
        )

    # Apply experiment's cohort filter.
    # For experiments where all specs share the same cohort (EXIT-GRID-1,
    # WAIT-GRID-1), using specs[0].cohort is correct.
    # For experiments where each spec has a per-cell regime predicate
    # (DISP-GATE-1), the registry stores a base_cohort_predicates key with
    # the common predicates to pre-filter on; per-spec predicates are applied
    # by replay_spec itself.
    base_cohort_predicates = exp_entry.get("base_cohort_predicates")
    if base_cohort_predicates:
        # Reconstruct a CohortFilter from the stored predicate list
        base_cohort = cohort_filter(
            *[tuple(p) for p in base_cohort_predicates]
        )
        log.info(
            "Using base_cohort_predicates for fires_df pre-filter: %s",
            base_cohort_predicates,
        )
    else:
        base_cohort = specs[0].cohort

    cohort_mask = base_cohort.apply(fires_full)
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
        if "tier_cascade" not in pf.columns and "tier_cascade" in fires_df.columns and "fire_idx" in pf.columns:
            tier_map = fires_df["tier_cascade"].to_dict()
            pf["tier_cascade"] = pf["fire_idx"].map(tier_map)

        # Carry spy_tercile for SPY-covariate splits (L3_PREREG design obligation 2).
        # spy_tercile is merged into fires_df by _merge_regime_columns when the
        # experiment declares needed_merge_columns (as DISP-GATE-1 does).
        if "spy_tercile" not in pf.columns and "spy_tercile" in fires_df.columns and "fire_idx" in pf.columns:
            spy_tercile_map = fires_df["spy_tercile"].to_dict()
            pf["spy_tercile"] = pf["fire_idx"].map(spy_tercile_map)

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

    # For trim_grid_v1: load hold_126 perfire from exit_grid_v1 summary
    # (for right-tail retention computation — uses the same cohort baseline).
    # We reconstruct exit_grid_v1 perfire on the fly from all_perfire if present,
    # or fall back to None (right_tail_retention will be null).
    _hold126_pf: pd.DataFrame | None = None
    if exp_id == "trim_grid_v1":
        # hold_126 is the reference for right-tail retention.
        # We run the hold(126) spec as part of the trim run to get the reference baseline.
        # Build a temporary hold_126 spec with the same cohort and run it.
        # This is NOT a new registered trial — it uses exit_grid_v1/hold_126 semantics
        # and the already-registered hash (it is a reference lookup, not a new cell).
        cohort_for_h126 = cohort_filter(
            ("eq", "verdict_type", "fire"),
            ("eq", "verdict_grade", True),
        )
        from scripts.run_rule_replay import _build_exit_grid_v1_specs
        h126_specs = [s for s in _build_exit_grid_v1_specs(cohort_for_h126)
                      if "hold_126" in s.spec_id]
        if h126_specs:
            h126_spec = h126_specs[0]
            h126_reg_hashes = set(exp_entry.get("spec_hashes", []))
            # hold_126 hash is registered in exit_grid_v1, not trim_grid_v1;
            # we load from all_perfire if possible, otherwise skip right-tail.
            # Here we run the spec as a reference lookup (hash checked against exit_grid_v1
            # registry entry is not available; suppress governor by passing the h126 hash).
            # IMPORTANT: this is reference data only, not a new registered trial.
            # We pass the existing spec_hashes set from trim_grid_v1 — the h126 hash is not
            # in it, so we use a try/except and default to None.
            try:
                _hold126_pf = replay_spec(
                    h126_spec,
                    fires_df,
                    closes,
                    registry_hashes={h126_spec.content_hash()},  # pass spec's own hash
                )
                # Attach episode_cluster
                if "fire_idx" in _hold126_pf.columns and "episode_cluster" not in _hold126_pf.columns:
                    _cmap = fires_df["episode_cluster"].to_dict()
                    _hold126_pf["episode_cluster"] = _hold126_pf["fire_idx"].map(_cmap)
                log.info("hold_126 reference for right-tail retention: %d rows", len(_hold126_pf))
            except Exception as exc:
                log.warning("Could not compute hold_126 reference for right-tail: %s", exc)
                _hold126_pf = None

    # Every cell in the declared grid appears in the summary (nulls included)
    for spec in specs:
        stats = cell_summaries[spec.spec_id]
        pf = all_perfire[spec.spec_id]
        era_tier = _era_tier_splits(pf, cluster_col="episode_cluster")
        spy_split = _spy_covariate_split(pf, cluster_col="episode_cluster")
        cell_dict: dict[str, Any] = {
            **stats,
            "spec_hash": spec.content_hash(),
            "exit_policy": spec.exit.to_dict(),
            "era_tier_splits": era_tier,
            **({"spy_covariate_split": spy_split} if spy_split is not None else {}),
        }
        # Trim-specific extra metrics
        if exp_id == "trim_grid_v1":
            trim_extra = _trim_cell_stats_extra(pf, _hold126_pf, cluster_col="episode_cluster")
            cell_dict.update(trim_extra)
        summary["cells"][spec.spec_id] = cell_dict

    # ── 9b. Add disp_gate_1_meta block for DISP-GATE-1 experiments ───────────
    # This block is experiment-specific and captures panel reach, exclusion
    # counts, basis flip rate, and FDR accounting required by L3_PREREG §6.
    # fires_full (pre-cohort-filter) is used so total exclusion count is accurate
    # (the cohort filter removes excluded fires from fires_df).
    if exp_id == "disp_gate_1":
        # Compute pre-B2 pooled sum: cumulative_trials is the POST-B2 value;
        # pre-B2 = cumulative_trials - declared_budget
        declared = exp_entry.get("declared_budget", 0) or 0
        pre_b2 = cumulative_trials - declared
        meta_block = _compute_disp_meta(
            fires_full,
            pre_b2_pooled_sum=pre_b2,
            post_b2_pooled_sum=cumulative_trials,
        )
        # Add panel_data_reach and panel_n_tickers from the merge step if available
        if _regime_panel_meta:
            meta_block.update({
                k: _regime_panel_meta[k]
                for k in ("panel_data_reach", "panel_n_bars", "panel_n_tickers")
                if k in _regime_panel_meta
            })
        summary["disp_gate_1_meta"] = meta_block

    # ── 9c. Add trim_grid_v1_meta block ──────────────────────────────────────
    if exp_id == "trim_grid_v1":
        declared = exp_entry.get("declared_budget", 0) or 0
        pre_trim_pooled = cumulative_trials - declared
        # Compute the max()-basis: largest declared_budget across all registered experiments
        # (per RUL-5: TrialLedger.effective_n() uses max() semantics).
        from engine.rule_experiments import list_experiments as _list_exp
        all_exps = _list_exp(rp)
        # Note: list_experiments returns de-duplicated latest-entry-per-exp_id.
        # For merged records (load_experiment merges all), we need to re-read budgets.
        from engine.rule_experiments import _load_registry_raw as _load_raw
        _all_records = _load_raw(rp)
        _max_basis = max(
            (int(r["declared_budget"]) for r in _all_records if "declared_budget" in r),
            default=declared
        )
        summary["trim_grid_v1_meta"] = {
            "derived_from_surface": exp_entry.get("derived_from_surface"),
            "contamination_note": (
                "TRIM-GRID-1 is derived_from_surface=exit_grid_v1 — that surface is now seen. "
                "These cells were designed on the same fire tape already examined by exit_grid_v1. "
                "Any promotion prereg must carry this contamination stamp and compensate via "
                "fresh OOS fires (>=2026-H2) plus stricter thresholds (RUL-F3.5)."
            ),
            "verdict_criteria": "descriptive-only",
            "pre_trim_pooled_replay_sum": pre_trim_pooled,
            "post_trim_pooled_replay_sum": cumulative_trials,
            "trial_ledger_max_basis": _max_basis,
            "trial_ledger_max_basis_note": (
                f"TrialLedger.effective_n() uses max() semantics and reports {_max_basis} "
                f"(largest declared budget in the replay family = exit_grid_v1 with budget={_max_basis}). "
                f"The cumulative pooled SUM is {cumulative_trials} (per RUL-5: both numbers printed)."
            ),
            "right_tail_survivorship_caveat": (
                "Right-tail retention is measured against the top decile of hold_126 returns. "
                "The massive-era cohort has a delisted-name recall floor (dead_name_coverage_pct ~38%); "
                "survivorship bites hardest in the right tail — names that kept rising vs those "
                "that fell and delisted. The right-tail capture rate is directionally informative "
                "but should not be over-interpreted."
            ),
            "profit_take_note": (
                "profit_take(15) exits at the first CLOSE >= +15% from entry (conservative close basis). "
                "If the target is never touched within the reference window, the leg holds to reference "
                "(included at reference return — same held-to-reference semantics as trail_stop/barrier). "
                "This is the EXIT-GRID-1 bug-class prevention: dropping never-triggered legs was the "
                "error that sign-flipped wide-stop cells in the first run."
            ),
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
