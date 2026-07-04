"""scripts/stamp_options_state.py — nightly options-state stamping on the US board ledger.

Options Alpha program W1.3 (research/OPTIONS_ALPHA_MASTERPLAN.md, rulings A6/A9/A10).

Runs AFTER ``scripts.grade_us_board --nightly`` in the daily.yml render job (see the
"US Buy Board ledger" step). Given the freshly-graded + accumulated
``data/us_board_ledger/retro_grades.parquet``, it adds the eight nullable options-state
stamp columns (``engine.options_stamp.STAMP_COLS``) to any row that is not yet stamped and
writes the frame back.

DESIGN — mirrors ``grade_us_board._backfill_regime_stamps`` exactly (the established
schema-union / PIT-stamp pattern):

  * schema-union: missing stamp columns are added (None) so legacy rows keep nulls.
  * ONLY rows where ALL stamp columns are null get stamped — a row already stamped is
    never overwritten (backfill-does-not-overwrite-non-null; a later re-run is idempotent).
  * PIT: ``engine.options_stamp.stamp_options_state`` uses only store data with as-of ≤ the
    fire's ``as_of`` date. No lookahead.

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

from engine.options_stamp import STAMP_COLS, _default_chain_dates, stamp_options_state
from lib import config

LEDGER_PATH = config.data_dir() / "us_board_ledger" / "retro_grades.parquet"

# a row counts as "stamped" once ANY stamp column is non-null; a fully-null row is unstamped.
# (matches _backfill_regime_stamps: unstamped == all stamp cols isna)


def _ensure_stamp_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Schema-union: add any missing stamp column as all-None (legacy rows keep nulls)."""
    for col in STAMP_COLS:
        if col not in df.columns:
            df[col] = None
    return df


def stamp_ledger(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Stamp every fully-unstamped row in-place-safe; return (df, n_newly_stamped).

    Only rows where ALL stamp columns are null are stamped (never overwrites non-null).
    Stamps are cached per (as_of, ticker) since a board can list a name in several
    lanes/horizons — the options state is identical for all of them."""
    if df.empty:
        return df, 0
    df = _ensure_stamp_columns(df.copy())

    unstamped_mask = df[STAMP_COLS].isna().all(axis=1)
    if not unstamped_mask.any():
        return df, 0

    # chain-date list is expensive-ish (a glob) — compute once and reuse across rows
    chain_dates = _default_chain_dates()
    cache: dict[tuple, dict] = {}
    newly_stamped = 0

    for idx in df.index[unstamped_mask]:
        as_of = df.at[idx, "as_of"]
        ticker = df.at[idx, "ticker"]
        key = (as_of, ticker)
        if key not in cache:
            cache[key] = stamp_options_state(as_of, ticker, chain_dates=chain_dates)
        stamp = cache[key]
        # apply only if the stamp produced at least one non-null value (else leave the row
        # unstamped so a future run — once coverage extends — can fill it)
        if any(v is not None for v in stamp.values()):
            for col in STAMP_COLS:
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
        stamp_cols_present = [c for c in STAMP_COLS if c in df.columns]
        n_unstamped = (
            int(df[stamp_cols_present].isna().all(axis=1).sum())
            if stamp_cols_present else n_before
        )
        print(f"[options_stamp] stamped {n_newly} newly-stamped rows; "
              f"{n_unstamped}/{n_before} rows still unstamped "
              f"(no chain/summary coverage for those as_of/ticker)")


if __name__ == "__main__":
    main()
