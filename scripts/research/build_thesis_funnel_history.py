"""LT-4 Thesis Funnel History — nightly append hook (append-only longitudinal store).

Program: LT External Foundation — LT-4 Thesis Funnel Shadow.
Reference: research/long_hold/LT4_FUNNEL_SHADOW_REPORT.md §Experiment clock
Ruling: RUL-T3-4 (program amendment — nightly append step; conditional on benchmark gate).

DISPLAY-ONLY. This module appends one row per (ticker, snapshot_date) to
data/research/thesis_funnel_history.parquet using keep-FIRST-per-(ticker,date)
semantics: a same-date re-run is a no-op; no prior-date row is ever mutated.

Survivorship-caveat (frozen in synapse.yml notes):
  Delisted names exit the fundamentals_panel universe silently. Their terminal
  state is NOT recorded here — they simply stop appearing. Longitudinal consumers
  MUST treat the population as a varying survivor cohort, not a closed panel.

Firewall (LH-R1 — STANDING; reproduced here for every reader):
  This artifact MUST NOT feed:
    - entry-stack z-scores
    - board ordering (us_standouts or any variant)
    - top-setups gates (setup_species / setup_quality / any ranked funnel)
    - alert triage or push floor

Nightly-only write law:
  The history write is gated on the --write-history flag, which is passed ONLY
  from the daily.yml engine job.  On-demand / smoke / dry-run invocations never
  write to history.

Output:
  data/research/thesis_funnel_history.parquet

Synapse: config/synapse.yml
  tier: display
  horizon_role: hold_thesis
  fdr_family: long_hold
  scored_path_surfaces: []
"""
from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    pass

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_HISTORY_PARQUET = _REPO_ROOT / "data" / "research" / "thesis_funnel_history.parquet"

# State columns kept in the history store — compact, state-relevant fields only.
# Full funnel flags are preserved so cross-section analysis can dissect transitions.
_HISTORY_COLUMNS = [
    "ticker",
    "snapshot_date",         # calendar date (str YYYY-MM-DD) from as_of
    "state",
    "state_reason",
    "s1_dilution_fired",
    "s2_moat_falsifier_fired",
    "s3_solvency_fired",
    "s3_altman_z",
    "s4_coverage_fired",
    "s4_n_computable",
    "piotroski_score",
    "piotroski_of",
    "capital_allocation_delta",
    "_display_only",
    "_horizon_role",
    "_version",
    "_survivorship_caveat",
]

# Drift alert threshold: 5 percentage-point shift in any state's share triggers a warning.
_DRIFT_THRESHOLD_PP = 5.0

# Coverage-delta sentinel: columns to track for period_end coverage confounder warnings.
# These count how many tickers have a computable value (non-null).
_COVERAGE_SENTINEL_COLS = ["piotroski_score", "s3_altman_z", "s4_n_computable"]


def _prior_state_proportions(history: pd.DataFrame, snapshot_date: str) -> dict[str, float]:
    """Return state proportions from the most recent date strictly before snapshot_date."""
    if history is None or history.empty:
        return {}
    prior = history[history["snapshot_date"].astype(str) < snapshot_date]
    if prior.empty:
        return {}
    latest_prior = prior["snapshot_date"].max()
    subset = prior[prior["snapshot_date"] == latest_prior]
    total = len(subset)
    if total == 0:
        return {}
    counts = subset["state"].value_counts()
    return {str(k): 100.0 * int(v) / total for k, v in counts.items()}


def _coverage_delta(
    history: pd.DataFrame,
    snapshot_df: pd.DataFrame,
    snapshot_date: str,
) -> dict[str, float]:
    """Return fractional coverage delta for sentinel columns vs the prior snapshot."""
    if history is None or history.empty:
        return {}
    prior = history[history["snapshot_date"].astype(str) < snapshot_date]
    if prior.empty:
        return {}
    latest_prior = prior["snapshot_date"].max()
    prior_subset = prior[prior["snapshot_date"] == latest_prior]
    deltas: dict[str, float] = {}
    for col in _COVERAGE_SENTINEL_COLS:
        if col not in snapshot_df.columns or col not in prior_subset.columns:
            continue
        curr_cov = float(snapshot_df[col].notna().mean()) if len(snapshot_df) > 0 else 0.0
        prev_cov = float(prior_subset[col].notna().mean()) if len(prior_subset) > 0 else 0.0
        deltas[col] = round(curr_cov - prev_cov, 4)
    return deltas


def _print_drift_block(
    snapshot_proportions: dict[str, float],
    prior_proportions: dict[str, float],
    coverage_deltas: dict[str, float],
    snapshot_date: str,
) -> None:
    """Print a drift block to stdout (always) and log drift warnings when >threshold."""
    all_states = set(snapshot_proportions) | set(prior_proportions)
    drifted = False
    drift_lines: list[str] = []
    for state in sorted(all_states):
        curr_pct = snapshot_proportions.get(state, 0.0)
        prev_pct = prior_proportions.get(state, 0.0)
        delta = curr_pct - prev_pct
        flag = " *** DRIFT" if abs(delta) >= _DRIFT_THRESHOLD_PP else ""
        drift_lines.append(f"  {state:<35}  {curr_pct:6.2f}%  (prev {prev_pct:6.2f}%  delta {delta:+.2f}pp){flag}")
        if abs(delta) >= _DRIFT_THRESHOLD_PP:
            drifted = True

    print(f"\n=== THESIS FUNNEL STATE-PROPORTION DRIFT  ({snapshot_date}) ===")
    for line in drift_lines:
        print(line)

    if coverage_deltas:
        print(f"\n--- Coverage-artifact confounder check (LT-4 protocol) ---")
        for col, delta in coverage_deltas.items():
            flag = " *** COVERAGE SHIFT" if abs(delta) >= 0.05 else ""
            print(f"  {col:<30}  coverage delta {delta:+.4f}{flag}")
        print("  (Non-zero coverage delta can confound apparent state drift;")
        print("   check LT-1 period_end backfill and fundamentals_panel expansion.)")

    if drifted:
        log.warning(
            "thesis_funnel_history: state-proportion drift >%.1fpp detected for %s — "
            "check coverage-artifact confounders (LT-1/period_end) before reading as real.",
            _DRIFT_THRESHOLD_PP,
            snapshot_date,
        )


def _prepare_history_rows(snapshot_df: pd.DataFrame, snapshot_date: str) -> pd.DataFrame:
    """Build the history rows DataFrame from the snapshot, with sentinel fields."""
    df = snapshot_df.copy()
    df["snapshot_date"] = snapshot_date
    df["_survivorship_caveat"] = (
        "Delisted names exit the fundamentals_panel universe silently. "
        "Terminal transitions are invisible. Population is a varying survivor cohort."
    )
    # Keep only the columns defined in _HISTORY_COLUMNS (some may be absent in edge cases)
    keep = [c for c in _HISTORY_COLUMNS if c in df.columns]
    # Ensure snapshot_date is always present
    if "snapshot_date" not in keep:
        keep = ["ticker", "snapshot_date"] + [c for c in keep if c not in ("ticker", "snapshot_date")]
    return df[keep].copy()


def append_history(
    snapshot_df: pd.DataFrame,
    snapshot_date: str | None = None,
    history_path: Path | None = None,
    *,
    dry_run: bool = False,
) -> dict[str, object]:
    """Append snapshot rows to the history store (keep-FIRST per ticker+date).

    Parameters
    ----------
    snapshot_df:
        The DataFrame produced by build_thesis_funnel_snapshot._build().
    snapshot_date:
        The as_of date string (YYYY-MM-DD). Defaults to today.
    history_path:
        Override the history parquet path (used by tests).
    dry_run:
        If True, compute everything but write nothing.

    Returns a summary dict with keys:
      snapshot_date, n_tickers, n_written, n_skipped (already logged),
      drift_detected, coverage_deltas, state_proportions_curr.
    """
    if snapshot_date is None:
        snapshot_date = str(date.today())

    if history_path is None:
        history_path = _HISTORY_PARQUET

    if snapshot_df is None or snapshot_df.empty:
        log.warning("thesis_funnel_history: snapshot is empty — nothing to append")
        return {
            "snapshot_date": snapshot_date,
            "n_tickers": 0,
            "n_written": 0,
            "n_skipped": 0,
            "drift_detected": False,
            "coverage_deltas": {},
            "state_proportions_curr": {},
        }

    # Load existing history
    history: pd.DataFrame | None = None
    if history_path.exists():
        try:
            history = pd.read_parquet(history_path)
        except Exception as exc:  # noqa: BLE001
            log.warning("thesis_funnel_history: could not load existing history: %s", exc)

    # Determine which tickers are already logged for this snapshot_date
    already_logged: set[str] = set()
    if history is not None and not history.empty and "snapshot_date" in history.columns and "ticker" in history.columns:
        mask = history["snapshot_date"].astype(str) == snapshot_date
        already_logged = set(history.loc[mask, "ticker"].astype(str))

    # Build state proportions for drift check BEFORE filtering new rows
    curr_proportions: dict[str, float] = {}
    total = len(snapshot_df)
    if total > 0 and "state" in snapshot_df.columns:
        counts = snapshot_df["state"].value_counts()
        curr_proportions = {str(k): 100.0 * int(v) / total for k, v in counts.items()}

    # Prior proportions and coverage deltas
    prior_proportions = _prior_state_proportions(history, snapshot_date)
    cov_deltas = _coverage_delta(history, snapshot_df, snapshot_date)

    # Drift block — print always when prior exists, or when this is the first write
    if prior_proportions:
        _print_drift_block(curr_proportions, prior_proportions, cov_deltas, snapshot_date)
    else:
        log.info("thesis_funnel_history: first snapshot — no prior to compare drift against")

    # Filter to only new (ticker, date) pairs
    new_rows_df = snapshot_df[~snapshot_df["ticker"].astype(str).isin(already_logged)].copy()
    n_skipped = len(already_logged)
    n_new = len(new_rows_df)

    if n_new == 0:
        log.info(
            "thesis_funnel_history: all %d tickers already logged for %s (keep-first, no-op)",
            len(already_logged), snapshot_date,
        )
        drift_detected = prior_proportions and any(
            abs(curr_proportions.get(s, 0.0) - prior_proportions.get(s, 0.0)) >= _DRIFT_THRESHOLD_PP
            for s in set(curr_proportions) | set(prior_proportions)
        )
        return {
            "snapshot_date": snapshot_date,
            "n_tickers": len(snapshot_df),
            "n_written": 0,
            "n_skipped": n_skipped,
            "drift_detected": drift_detected,
            "coverage_deltas": cov_deltas,
            "state_proportions_curr": curr_proportions,
        }

    # Build rows for the history parquet
    new_history_rows = _prepare_history_rows(new_rows_df, snapshot_date)

    # Merge with existing history
    if not dry_run:
        merged = (
            pd.concat([history, new_history_rows], ignore_index=True)
            if history is not None
            else new_history_rows.copy()
        )
        history_path.parent.mkdir(parents=True, exist_ok=True)
        merged.to_parquet(history_path, index=False)
        log.info(
            "thesis_funnel_history: appended %d new rows for %s (skipped %d already-logged)",
            n_new, snapshot_date, n_skipped,
        )
    else:
        log.info(
            "thesis_funnel_history: --dry-run; would append %d rows for %s",
            n_new, snapshot_date,
        )

    drift_detected = bool(
        prior_proportions
        and any(
            abs(curr_proportions.get(s, 0.0) - prior_proportions.get(s, 0.0)) >= _DRIFT_THRESHOLD_PP
            for s in set(curr_proportions) | set(prior_proportions)
        )
    )

    return {
        "snapshot_date": snapshot_date,
        "n_tickers": len(snapshot_df),
        "n_written": n_new,
        "n_skipped": n_skipped,
        "drift_detected": drift_detected,
        "coverage_deltas": cov_deltas,
        "state_proportions_curr": curr_proportions,
    }
