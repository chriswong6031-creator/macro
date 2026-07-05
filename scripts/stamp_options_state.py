"""scripts/stamp_options_state.py — nightly options-state stamping on the US board ledger.

Options Alpha program W1.3 / W-C (research/OPTIONS_ALPHA_MASTERPLAN.md, rulings A6/A9/A10;
W-C 2026-07-05 extends with skew/ivspread/opex/wall-dist/pin-risk columns).

Runs AFTER ``scripts.grade_us_board --nightly`` in the daily.yml render job (see the
"US Buy Board ledger" step). Given the freshly-graded + accumulated
``data/us_board_ledger/retro_grades.parquet``, it adds the nullable options-state
stamp columns (``engine.options_stamp.STAMP_COLS``) to any row that is not yet stamped and
writes the frame back.

DESIGN — mirrors ``grade_us_board._backfill_regime_stamps`` exactly (the established
schema-union / PIT-stamp pattern):

  * schema-union: missing stamp columns are added (None) so legacy rows keep nulls.
  * ONLY rows where ALL stamp columns are null get stamped — a row already stamped is
    never overwritten (backfill-does-not-overwrite-non-null; a later re-run is idempotent).
  * PIT: ``engine.options_stamp.stamp_options_state`` uses only store data with as-of ≤ the
    fire's ``as_of`` date. No lookahead.

W-C additions: the stamp_ledger pass pre-loads the skew and ivspread snapshot frames
once per run (avoiding repeated parquet reads per row) and passes them into
stamp_options_state as ``skew_df`` / ``ivspread_df``. These frames are absent locally
(gitignored R2 stores) → None is passed → all W-C cols stamp null. Coverage is printed.

This script NEVER touches grading columns or grading logic — Setup-Species Stage B owns
those (A9). It only unions in the ``opt_*`` columns. Backfill covers every existing row in
the 2026-06-15+ window (where chains/summaries exist); rows outside coverage stamp to null
and are re-tried on future runs (cheap; the coverage window only grows).

Idempotent, resilient: if the ledger is absent this is a no-op.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from engine.options_stamp import (
    STAMP_COLS,
    STAMP_COVERAGE_COLS,
    _default_chain_dates,
    _default_read_skew_snapshots,
    _default_read_ivspread_snapshots,
    stamp_options_state,
)
from lib import config

LEDGER_PATH = config.data_dir() / "us_board_ledger" / "retro_grades.parquet"

# RETRY GATE: a row is considered "unstamped" (eligible for re-stamping) when ALL
# STAMP_COVERAGE_COLS are null.  We intentionally exclude opt_opex_days from this check
# because it is calendar-derived and will be non-null on essentially every valid business date
# regardless of whether polygon_gex / skew / ivspread stores have coverage.  Without this
# exclusion, any row that receives only an opex stamp would be permanently locked out of
# future GEX/skew/ivspread fills — defeating the W1.3 design that relies on coverage-gated
# rows staying retryable as the stores grow.  See engine.options_stamp.STAMP_COVERAGE_COLS.


def _ensure_stamp_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Schema-union: add any missing stamp column as all-None (legacy rows keep nulls)."""
    for col in STAMP_COLS:
        if col not in df.columns:
            df[col] = None
    return df


def stamp_ledger(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Stamp every fully-unstamped row in-place-safe; return (df, n_newly_stamped).

    "Unstamped" is defined by STAMP_COVERAGE_COLS (all coverage-gated cols null), NOT
    STAMP_COLS — see module header.  This means a row with only opt_opex_days (calendar-
    derived, always non-null) is still considered unstamped and remains retryable when
    GEX/skew/ivspread coverage later arrives.

    A row is written (committed to the ledger) only when the stamp produces at least one
    non-null value in STAMP_COVERAGE_COLS.  A row that returns only opt_opex_days non-null
    (and all coverage-gated cols null) is left with ONLY the opt_opex_days value — it does
    NOT flip to "stamped" so future runs can fill the coverage-gated cols.

    Stamps are cached per (as_of, ticker) since a board can list a name in several
    lanes/horizons — the options state is identical for all of them.

    W-C: skew and ivspread snapshot DataFrames are loaded once per call (not per row)
    and passed into stamp_options_state to avoid repeated parquet reads.  When these
    stores are absent locally (gitignored R2) the frames are None and the W-C stamp
    columns stay null — this is correct and expected (they will be filled on the R2
    runner where the stores are present)."""
    if df.empty:
        return df, 0
    df = _ensure_stamp_columns(df.copy())

    # Retry gate: use STAMP_COVERAGE_COLS (excludes opt_opex_days) so calendar-only
    # rows remain retryable when GEX/skew/ivspread coverage later arrives.
    coverage_cols_present = [c for c in STAMP_COVERAGE_COLS if c in df.columns]
    if coverage_cols_present:
        unstamped_mask = df[coverage_cols_present].isna().all(axis=1)
    else:
        # no coverage cols present yet → all rows are unstamped
        unstamped_mask = pd.Series(True, index=df.index)
    if not unstamped_mask.any():
        return df, 0

    # chain-date list is expensive-ish (a glob) — compute once and reuse across rows
    chain_dates = _default_chain_dates()

    # W-C: pre-load snapshot frames once per run (absent locally → None; fine)
    skew_df = _default_read_skew_snapshots()
    ivspread_df = _default_read_ivspread_snapshots()

    cache: dict[tuple, dict] = {}
    newly_stamped = 0

    for idx in df.index[unstamped_mask]:
        as_of = df.at[idx, "as_of"]
        ticker = df.at[idx, "ticker"]
        key = (as_of, ticker)
        if key not in cache:
            cache[key] = stamp_options_state(
                as_of, ticker,
                chain_dates=chain_dates,
                skew_df=skew_df,
                ivspread_df=ivspread_df,
            )
        stamp = cache[key]
        # Always write opt_opex_days (calendar-derived; always available) even when
        # coverage-gated cols are null.  This lets us track OPEX proximity for all fires
        # without poisoning the retry gate.
        if stamp.get("opt_opex_days") is not None:
            df.at[idx, "opt_opex_days"] = stamp["opt_opex_days"]
        # Apply coverage-gated cols only when at least one is non-null (else the retry
        # gate stays open so a future run fills them when coverage extends).
        coverage_vals = {c: stamp[c] for c in STAMP_COVERAGE_COLS if c in stamp}
        if any(v is not None for v in coverage_vals.values()):
            for col in STAMP_COVERAGE_COLS:
                if col in stamp:
                    df.at[idx, col] = stamp[col]
            newly_stamped += 1

    return df, newly_stamped


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--ledger", default=str(LEDGER_PATH),
                    help="path to retro_grades.parquet (default: canonical)")
    args = ap.parse_args()

    ledger = Path(args.ledger)
    if not ledger.exists():
        if not args.quiet:
            print(f"[options_stamp] ledger absent ({ledger}); nothing to stamp")
        return

    df = pd.read_parquet(ledger)
    n_before = len(df)
    df, n_newly = stamp_ledger(df)

    if n_newly > 0:
        df.to_parquet(ledger, index=False)

    if not args.quiet:
        # n_unstamped uses STAMP_COVERAGE_COLS so the count reflects retryable rows
        # (rows with only opt_opex_days still count as unstamped / waiting for coverage)
        coverage_cols_present = [c for c in STAMP_COVERAGE_COLS if c in df.columns]
        n_unstamped = (
            int(df[coverage_cols_present].isna().all(axis=1).sum())
            if coverage_cols_present else n_before
        )
        print(f"[options_stamp] stamped {n_newly} newly-stamped rows; "
              f"{n_unstamped}/{n_before} rows still unstamped "
              f"(no chain/summary coverage for those as_of/ticker)")
        # W-C coverage summary
        wc_cols = ["opt_ivspread_rel", "opt_skew", "opt_skew_5d_chg",
                   "opt_opex_days", "opt_pin_risk",
                   "opt_wall_dist_up_pct", "opt_wall_dist_down_pct"]
        for col in wc_cols:
            if col in df.columns:
                n_col = int(df[col].notna().sum())
                pct = round(n_col / max(n_before, 1) * 100, 1)
                print(f"  W-C coverage [{col}]: {n_col}/{n_before} rows ({pct}%)")


if __name__ == "__main__":
    main()
