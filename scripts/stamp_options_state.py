"""scripts/stamp_options_state.py — nightly options-state stamping on the US board ledger.

Options Alpha program W1.3 (research/OPTIONS_ALPHA_MASTERPLAN.md, rulings A6/A9/A10).
Extended by P2.2 (research/LIVE_FLOW_PRODUCTION_ROADMAP_BY_FABLE.md §3 P2.2) to add four
tape-flow stamp columns from engine/tape_flow_stamp.py.

Runs AFTER ``scripts.grade_us_board --nightly`` in the daily.yml render job (see the
"US Buy Board ledger" step). Given the freshly-graded + accumulated
``data/us_board_ledger/retro_grades.parquet``, it adds the nullable options-state and
tape-flow stamp columns (``engine.options_stamp.STAMP_COLS`` +
``engine.tape_flow_stamp.TAPE_FLOW_STAMP_COLS``) to any row that is not yet stamped and
writes the frame back.

DESIGN — mirrors ``grade_us_board._backfill_regime_stamps`` exactly (the established
schema-union / PIT-stamp pattern):

  * schema-union: missing stamp columns are added (None) so legacy rows keep nulls.
  * ONLY rows where ALL stamp columns are null get stamped — a row already stamped is
    never overwritten (backfill-does-not-overwrite-non-null; a later re-run is idempotent).
  * PIT: readers in both stamp modules use only store data with as-of ≤ the fire's
    ``as_of`` date. No lookahead.

This script NEVER touches grading columns or grading logic — Setup-Species Stage B owns
those (A9). It only unions in the ``opt_*`` columns. Backfill covers every existing row in
the 2026-06-15+ window (where chains/summaries exist); rows outside coverage stamp to null
and are re-tried on future runs (cheap; the coverage window only grows).

P2.2 tape-flow columns (opt_net_signed_prem_5d_z, opt_flow_breadth_group, opt_dte_quality,
opt_crowding_flag) will be null-heavy initially because the tape_flow store starts accruing
from 2026-07-05 forward. This is correct behaviour — the W1.3 precedent: nullable,
retry-as-coverage-grows.

NOTE: opt_iv_rank_252 remains always-null (ruling A9). It reads data/thetadata_eod greeks,
which is mid-backfill and has a known dedup defect (#1363). That wiring waits for the dedup
repair and manifest-complete confirmation before being wired here.

Idempotent, resilient: if the ledger is absent this is a no-op.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from engine.options_stamp import STAMP_COLS, _default_chain_dates, stamp_options_state
from engine.tape_flow_stamp import TAPE_FLOW_STAMP_COLS, stamp_tape_flow
from lib import config

LEDGER_PATH = config.data_dir() / "us_board_ledger" / "retro_grades.parquet"

# Combined list of ALL stamp columns (W1.3 + P2.2).
# A row is considered "stamped" if ANY of these is non-null.
ALL_STAMP_COLS: list[str] = STAMP_COLS + TAPE_FLOW_STAMP_COLS


def _ensure_stamp_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Schema-union: add any missing stamp column as all-None (legacy rows keep nulls)."""
    for col in ALL_STAMP_COLS:
        if col not in df.columns:
            df[col] = None
    return df


def _build_group_members(df: pd.DataFrame, as_of: str, sector: str | None) -> list[str]:
    """Return all unique tickers in the same sector on the same as_of date.

    Used for opt_flow_breadth_group: the 'group' is defined as the set of names from the
    board ledger that share the same sector on the fire's date.
    """
    if not sector:
        return []
    mask = (df["as_of"] == as_of) & (df["sector"] == sector)
    return df.loc[mask, "ticker"].dropna().unique().tolist()


def stamp_ledger(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Stamp every fully-unstamped row; return (df, n_newly_stamped).

    Only rows where ALL stamp columns are null are stamped (never overwrites non-null).
    Stamps are cached per (as_of, ticker) since a board can list a name in several
    lanes/horizons — the options state is identical for all of them.

    The tape-flow stamp (P2.2) adds opt_flow_breadth_group, which requires knowing the
    full group (sector peers on the same as_of date). The group is derived from the ledger
    itself (PIT-safe: the ledger is already graded before stamping runs).
    """
    if df.empty:
        return df, 0
    df = _ensure_stamp_columns(df.copy())

    unstamped_mask = df[ALL_STAMP_COLS].isna().all(axis=1)
    if not unstamped_mask.any():
        return df, 0

    # chain-date list is expensive-ish (a glob) — compute once and reuse across rows
    chain_dates = _default_chain_dates()

    # caches: avoid re-computing stamps for same (as_of, ticker) pair
    w13_cache: dict[tuple, dict] = {}
    tf_cache: dict[tuple, dict] = {}
    # group-members cache keyed by (as_of, sector)
    group_cache: dict[tuple, list[str]] = {}

    newly_stamped = 0

    for idx in df.index[unstamped_mask]:
        as_of = df.at[idx, "as_of"]
        ticker = df.at[idx, "ticker"]
        sector = df.at[idx, "sector"] if "sector" in df.columns else None
        key = (as_of, ticker)

        # ── W1.3 stamp (polygon_gex + chains) ─────────────────────────────────
        if key not in w13_cache:
            w13_cache[key] = stamp_options_state(as_of, ticker, chain_dates=chain_dates)
        w13_stamp = w13_cache[key]

        # ── P2.2 tape-flow stamp ───────────────────────────────────────────────
        if key not in tf_cache:
            group_key = (as_of, sector)
            if group_key not in group_cache:
                group_cache[group_key] = _build_group_members(df, as_of, sector)
            tf_cache[key] = stamp_tape_flow(
                as_of, ticker,
                sector=sector,
                group_members=group_cache[group_key],
            )
        tf_stamp = tf_cache[key]

        # combine both stamps for the any-non-null check
        combined = {**w13_stamp, **tf_stamp}

        # apply only if at least one non-null value was produced across both stamps
        # (else leave fully-null so a future run can fill once coverage grows)
        if any(v is not None for v in combined.values()):
            for col in STAMP_COLS:
                df.at[idx, col] = w13_stamp[col]
            for col in TAPE_FLOW_STAMP_COLS:
                df.at[idx, col] = tf_stamp[col]
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
        all_cols_present = [c for c in ALL_STAMP_COLS if c in df.columns]
        n_unstamped = (
            int(df[all_cols_present].isna().all(axis=1).sum())
            if all_cols_present else n_before
        )
        tf_cols_present = [c for c in TAPE_FLOW_STAMP_COLS if c in df.columns]
        n_tf_nonull = (
            int(df[tf_cols_present].notna().any(axis=1).sum())
            if tf_cols_present else 0
        )
        print(
            f"[options_stamp] stamped {n_newly} newly-stamped rows; "
            f"{n_unstamped}/{n_before} rows still unstamped "
            f"(no chain/summary/tape-flow coverage for those as_of/ticker); "
            f"tape-flow columns populated on {n_tf_nonull} rows "
            f"(null-heavy is expected while the store accrues — W1.3 precedent)"
        )


if __name__ == "__main__":
    main()
