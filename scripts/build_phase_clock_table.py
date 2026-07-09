"""scripts/build_phase_clock_table.py — Phase-clock empirical survival table.

Builds data/cycle_pattern/phase_clock_survival.parquet: for each
(family x phase_state x age_bucket) cell over the BACKTEST cohort, the
empirical remaining-time-to-turn distribution and conditional turn probabilities.

DESIGN (PREREGISTRATION.md §18, PHASE-CLOCK-1):
  Cohort : BACKTEST rows only (state_monthly.hazard_epoch == 'price_c4414dcb'),
           restricted to the 3 KM-baseline families (us_sector, country, cn_sector),
           AND where osc_missing == False (oscillator available).
  Embargo: rows with date >= 2024-01-01 are NOT used for the table
           (holdout embargo per §18 and outcomes.py docstring).
  Age buckets: 0-6 m / 6-18 m / 18+ m (months from leg_open_date — age_m column
               of the hazard panel, which is the same metric).
  Phase states: from engine.cycle_pattern.phase_clock.classify_array().
  Outcomes (ruling A6 independence): y3, y6 turn-event labels from the hazard panel
               data/hazard/panel_price_c4414dcb.parquet — these ARE the same labels
               the graders use (realized_extrema_turns, freq=M, min_move_pct=20).
               We also compute P(turn<=12m) from (event_date - date) < 12 months.
  N threshold: cells with N_legs < 8 unique confirmed legs pool to (family x phase_state);
               if still < 8, pool to family level. Pooling is flagged per row.
  Per-cell metrics:
    p25_m / p50_m / p75_m: percentiles of (event_date - date) in months,
                            computed on NON-CENSORED rows (censored==0),
                            clipped at 0 from below (negative = turn imminent).
    p_turn_3m / p_turn_6m / p_turn_12m: empirical probabilities.
    n_obs: row count in cell.
    n_turns: unique confirmed turns (unique legs with censored==0).
    pooling: '' / 'state' / 'family'.

Rerunnable and deterministic: given the same input parquets, the output is
frame-equal (sorted by family/phase_state/age_bucket/direction; same seed/dtypes).

Pure numpy/pandas. No sklearn/statsmodels/scipy.stats.

Usage:
  python scripts/build_phase_clock_table.py
  python scripts/build_phase_clock_table.py --smoke   (no file write)
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

_REPO = Path(__file__).parent.parent.resolve()
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from engine.cycle_pattern.phase_clock import VALID_STATES, UNKNOWN_STATE, classify_array  # noqa: E402

# ─────────────────────────────────────────────────────────────────────────────
# FROZEN paths and parameters
# ─────────────────────────────────────────────────────────────────────────────
STATE_MONTHLY_PATH = _REPO / "data" / "cycle_pattern" / "state_monthly.parquet"
HAZARD_PANEL_PATH = _REPO / "data" / "hazard" / "panel_price_c4414dcb.parquet"
OUTPUT_PATH = _REPO / "data" / "cycle_pattern" / "phase_clock_survival.parquet"

HAZARD_EPOCH = "price_c4414dcb"
EMBARGO_DATE = pd.Timestamp("2024-01-01")
KM_FAMILIES = ("us_sector", "country", "cn_sector")
MIN_TURNS_CELL = 8         # min unique confirmed turns before pooling (§18)
DAYS_PER_MONTH = 30.4375   # standard month-length for remaining_m computation

# Age bucket definitions (§18: 0-6, 6-18, 18+)
AGE_BUCKET_LABELS = ("0-6m", "6-18m", "18+m")


def _age_bucket(age_m: np.ndarray) -> np.ndarray:
    """Map age_m (months) to the 3 phase-clock age buckets."""
    buckets = np.empty(len(age_m), dtype=object)
    buckets[age_m < 6] = "0-6m"
    buckets[(age_m >= 6) & (age_m < 18)] = "6-18m"
    buckets[age_m >= 18] = "18+m"
    buckets[np.isnan(age_m)] = "unknown"
    return buckets


def _remaining_m(event_date: pd.Series, obs_date: pd.Series) -> np.ndarray:
    """Remaining months to turn = (event_date - obs_date) in months. Can be negative
    when the turn already occurred by the observation row (the panel continues to
    include rows for a few months after the turn to allow lagged readings)."""
    return (event_date - obs_date).dt.days.to_numpy(float) / DAYS_PER_MONTH


def build_merged_panel() -> pd.DataFrame:
    """Load and merge state_monthly + hazard panel, return the BACKTEST cohort.

    Join key: (native_id.upper(), family, date).
    Restricts to: hazard_epoch == HAZARD_EPOCH, family in KM_FAMILIES,
                  osc_missing == False, date < EMBARGO_DATE.
    """
    state = pd.read_parquet(STATE_MONTHLY_PATH)
    hp = pd.read_parquet(HAZARD_PANEL_PATH)

    # Derive join keys
    state["_fam"] = state["entity_id"].str.split(":").str[0]
    state["_id"] = state["native_id"].str.upper()
    hp["_id"] = hp["id"].str.upper()

    # Restrict state to KM families and backtest cohort
    state3 = state[
        (state["_fam"].isin(KM_FAMILIES)) &
        (state["hazard_epoch"] == HAZARD_EPOCH) &
        (~state["osc_missing"])
    ].copy()

    # Join: bring in age_m, y3, y6, censored, event_date, direction from hazard panel
    hp_cols = ["date", "_id", "family", "direction", "y3", "y6", "censored",
               "event_date", "age_m", "leg_open_date"]
    merged = state3.merge(
        hp[hp_cols],
        left_on=["date", "_id", "_fam"],
        right_on=["date", "_id", "family"],
        how="inner",
    )

    # Apply embargo
    merged = merged[merged["date"] < EMBARGO_DATE].copy()

    # Resolve ambiguous columns created by the merge.
    # 'direction' comes from both state_monthly (_x) and hazard panel (_y).
    # The hazard panel's direction is authoritative (it owns y3/y6/censored).
    if "direction_y" in merged.columns:
        merged = merged.rename(columns={"direction_y": "direction"})
    if "direction_x" in merged.columns:
        merged = merged.drop(columns=["direction_x"])

    # Classify phase_clock state
    merged["phase_state"] = classify_array(
        merged["mmacd_sign"].to_numpy(float),
        merged["mmacd_slope"].to_numpy(float),
        merged["mstoch_k"].to_numpy(float),
        merged["mstoch_d"].to_numpy(float),
        # osc_missing is already filtered to False above, but pass zeros for safety
        np.zeros(len(merged), dtype=bool),
    )

    # Age bucket — use age_m from the HAZARD panel (age_m_y after merge, which is the
    # leg-age-in-months metric the KM baseline uses; state_monthly's age_m_x is identical
    # but we disambiguate explicitly to be safe).
    age_col = "age_m_y" if "age_m_y" in merged.columns else "age_m"
    merged["age_bucket_pc"] = _age_bucket(merged[age_col].to_numpy(float))
    # Also rename to drop the suffix for downstream code clarity
    merged = merged.rename(columns={age_col: "age_m_hz"})

    # Remaining months to turn (for percentile computation on non-censored rows)
    merged["remaining_m"] = _remaining_m(
        pd.to_datetime(merged["event_date"]),
        pd.to_datetime(merged["date"]),
    )

    # P(turn<=12m): remaining_m <= 12
    # For censored rows (leg still open), treat as not turning within 12m (conservative)
    merged["y12"] = np.where(
        merged["censored"] == 0,
        (merged["remaining_m"] <= 12.0).astype(float),
        0.0,
    )

    return merged.reset_index(drop=True)


def _cell_stats(rows: pd.DataFrame) -> dict:
    """Compute per-cell survival statistics."""
    n_obs = len(rows)
    confirmed = rows[rows["censored"] == 0].copy()
    n_turns = confirmed.groupby(["_id", "leg_open_date"]).ngroups if len(confirmed) > 0 else 0

    # Percentile distribution of remaining_m among confirmed (censored==0) rows,
    # clipped at 0 from below.
    if len(confirmed) > 0:
        rm = confirmed["remaining_m"].to_numpy(float)
        rm_pos = np.clip(rm, 0.0, None)  # turn-imminent rows clipped to 0
        p25 = float(np.percentile(rm_pos, 25))
        p50 = float(np.percentile(rm_pos, 50))
        p75 = float(np.percentile(rm_pos, 75))
    else:
        p25 = p50 = p75 = float("nan")

    p_turn_3m = float(rows["y3"].mean()) if n_obs > 0 else float("nan")
    p_turn_6m = float(rows["y6"].mean()) if n_obs > 0 else float("nan")
    p_turn_12m = float(rows["y12"].mean()) if n_obs > 0 else float("nan")

    return {
        "n_obs": n_obs,
        "n_turns": n_turns,
        "p25_m": round(p25, 3),
        "p50_m": round(p50, 3),
        "p75_m": round(p75, 3),
        "p_turn_3m": round(p_turn_3m, 4),
        "p_turn_6m": round(p_turn_6m, 4),
        "p_turn_12m": round(p_turn_12m, 4),
    }


def build_survival_table(panel: pd.DataFrame) -> pd.DataFrame:
    """Build the (family x direction x phase_state x age_bucket) survival table
    with N-threshold pooling.

    Pooling hierarchy (§18):
      1. Compute cell at (family, direction, phase_state, age_bucket).
      2. If n_turns < MIN_TURNS_CELL: pool to (family, direction, phase_state).
      3. If still n_turns < MIN_TURNS_CELL: pool to (family, direction).
    'pooling' column flags the level used: '' | 'state' | 'family'.
    """
    records = []
    families = sorted(panel["family"].unique())
    directions = ["up", "down"]
    states = list(VALID_STATES)
    age_buckets = list(AGE_BUCKET_LABELS)

    for fam in families:
        for dir_ in directions:
            # Pre-aggregate at various levels for pooling fallback
            fam_dir = panel[(panel["family"] == fam) & (panel["direction"] == dir_)]
            if len(fam_dir) == 0:
                continue
            # family-direction level pool
            fam_dir_stats = _cell_stats(fam_dir)
            # phase_state level pools
            state_pools: dict[str, dict] = {}
            for st in states:
                sub_s = fam_dir[fam_dir["phase_state"] == st]
                state_pools[st] = _cell_stats(sub_s) if len(sub_s) > 0 else None

            for st in states:
                for ab in age_buckets:
                    sub = fam_dir[
                        (fam_dir["phase_state"] == st) &
                        (fam_dir["age_bucket_pc"] == ab)
                    ]
                    if len(sub) == 0:
                        # No data for this cell — use pooled stats but mark pooling
                        # Check if state-level pool has data
                        if state_pools[st] is not None and state_pools[st]["n_obs"] > 0:
                            cell = dict(state_pools[st])
                            pooling = "state"
                        else:
                            cell = dict(fam_dir_stats)
                            pooling = "family"
                    else:
                        cell = _cell_stats(sub)
                        if cell["n_turns"] < MIN_TURNS_CELL:
                            # Pool up to state level
                            sp = state_pools[st]
                            if sp is not None and sp["n_turns"] >= MIN_TURNS_CELL:
                                cell = dict(sp)
                                pooling = "state"
                            else:
                                # Pool to family-direction level
                                cell = dict(fam_dir_stats)
                                pooling = "family"
                        else:
                            pooling = ""

                    records.append({
                        "family": fam,
                        "direction": dir_,
                        "phase_state": st,
                        "age_bucket": ab,
                        "pooling": pooling,
                        **cell,
                    })

    df = pd.DataFrame(records)
    df = df.sort_values(
        ["family", "direction", "phase_state", "age_bucket"], kind="stable"
    ).reset_index(drop=True)
    return df


def main(smoke: bool = False) -> None:
    """Build and write the phase-clock survival table."""
    t0 = time.monotonic()
    print("build_phase_clock_table: loading and merging panel …")
    panel = build_merged_panel()
    print(
        f"  merged panel: {len(panel)} rows, "
        f"{panel['family'].nunique()} families, "
        f"{panel['phase_state'].value_counts().to_dict()}"
    )

    print("building survival table …")
    table = build_survival_table(panel)
    print(f"  table: {len(table)} rows, {(table['pooling']=='').sum()} full-cell / "
          f"{(table['pooling']=='state').sum()} state-pooled / "
          f"{(table['pooling']=='family').sum()} family-pooled")

    if not smoke:
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        table.to_parquet(OUTPUT_PATH, index=False)
        print(f"  wrote {OUTPUT_PATH}")
    else:
        print("  --smoke: no file written")

    elapsed = time.monotonic() - t0
    print(f"  elapsed: {elapsed:.1f}s")
    return table


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true", help="dry run, no file write")
    args = parser.parse_args()
    main(smoke=args.smoke)
