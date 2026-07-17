"""scripts/stamp_options_state.py — nightly options-state stamping on the US board ledger.

Options Alpha program W1.3 / W-C (research/OPTIONS_ALPHA_MASTERPLAN.md, rulings A6/A9/A10;
W-C 2026-07-05 extends with skew/ivspread/opex/wall-dist/pin-risk columns).
Extended by P2.2 (research/LIVE_FLOW_PRODUCTION_ROADMAP_BY_FABLE.md §3 P2.2) to add four
tape-flow stamp columns from engine/tape_flow_stamp.py.
Extended by W-OVC (2026-07-17) to add opt_vanna_relief, opt_front7_charm_share,
opt_root_class — see OPTIONS_OPEX_VANNA_CHARM_ADJUDICATION.md §5 build docket.

Runs AFTER ``scripts.grade_us_board --nightly`` in the daily.yml render job (see the
"US Buy Board ledger" step). Given the freshly-graded + accumulated
``data/us_board_ledger/retro_grades.parquet``, it adds the nullable options-state and
tape-flow stamp columns (``engine.options_stamp.STAMP_COLS`` +
``engine.tape_flow_stamp.TAPE_FLOW_STAMP_COLS``) to any row that is not yet stamped and
writes the frame back.

DESIGN — mirrors ``grade_us_board._backfill_regime_stamps`` exactly (the established
schema-union / PIT-stamp pattern):

  * schema-union: missing stamp columns are added (None) so legacy rows keep nulls.
  * no-overwrite: a column family already stamped on a row is never overwritten
    (backfill-does-not-overwrite-non-null; a later re-run is idempotent).
  * PIT: readers in both stamp modules use only store data with as-of ≤ the fire's
    ``as_of`` date. No lookahead.

TWO INDEPENDENT STAMP FAMILIES, each with its OWN retry gate (merge of W-C + P2.2):

  * options-state family (W1.3 + W-C cols): a row is retryable while ALL
    ``STAMP_COVERAGE_COLS`` are null.  opt_opex_days is intentionally EXCLUDED from the
    gate — it is calendar-derived and non-null on essentially every valid business date,
    so counting it would permanently lock opex-only rows out of future
    GEX/skew/ivspread fills (the W-C retry-gate fix).
  * tape-flow family (P2.2 cols): a row is retryable while ALL
    ``TAPE_FLOW_STAMP_COLS`` are null.

  The gates are independent so one family's coverage never locks the other out.

W-C additions: the stamp_ledger pass pre-loads the skew and ivspread snapshot frames
once per run (avoiding repeated parquet reads per row) and passes them into
stamp_options_state as ``skew_df`` / ``ivspread_df``. These frames are absent locally
(gitignored R2 stores) → None is passed → all W-C cols stamp null. Coverage is printed.

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
import math
from pathlib import Path

import numpy as np
import pandas as pd

from engine.options_stamp import (
    STAMP_COLS,
    STAMP_COVERAGE_COLS,
    _default_chain_dates,
    _default_read_skew_snapshots,
    _default_read_ivspread_snapshots,
    stamp_options_state,
)
from engine.tape_flow_stamp import TAPE_FLOW_STAMP_COLS, stamp_tape_flow
from lib import config

LEDGER_PATH = config.data_dir() / "us_board_ledger" / "retro_grades.parquet"

# Combined list of ALL stamp columns (W1.3 + W-C + P2.2) — used only for schema-union.
# Retry eligibility is decided PER FAMILY (see module header), never on this union.
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
    """Stamp every eligible row; return (df, n_newly_stamped).

    Eligibility is per family (see module header):

      * options-state family: ALL ``STAMP_COVERAGE_COLS`` null → retryable.  A row is
        committed for this family only when the stamp produces at least one non-null
        coverage-gated value.  opt_opex_days (calendar-derived) is always written when
        available but never flips the row to "stamped" — future runs can still fill the
        coverage-gated cols (W-C retry-gate fix).
      * tape-flow family: ALL ``TAPE_FLOW_STAMP_COLS`` null → retryable.  Committed only
        when at least one tape value is non-null.

    ``n_newly_stamped`` counts rows where at least one family committed values
    (opex-only writes do not count).

    Stamps are cached per (as_of, ticker) since a board can list a name in several
    lanes/horizons — the options state is identical for all of them.

    W-C: skew and ivspread snapshot DataFrames are loaded once per call (not per row)
    and passed into stamp_options_state to avoid repeated parquet reads.  When these
    stores are absent locally (gitignored R2) the frames are None and the W-C stamp
    columns stay null — this is correct and expected (they will be filled on the R2
    runner where the stores are present).

    The tape-flow stamp (P2.2) adds opt_flow_breadth_group, which requires knowing the
    full group (sector peers on the same as_of date). The group is derived from the ledger
    itself (PIT-safe: the ledger is already graded before stamping runs).
    """
    if df.empty:
        return df, 0
    df = _ensure_stamp_columns(df.copy())

    # Per-family retry gates (see module header).
    coverage_cols_present = [c for c in STAMP_COVERAGE_COLS if c in df.columns]
    if coverage_cols_present:
        opts_retry_mask = df[coverage_cols_present].isna().all(axis=1)
    else:
        opts_retry_mask = pd.Series(True, index=df.index)
    tf_cols_present = [c for c in TAPE_FLOW_STAMP_COLS if c in df.columns]
    if tf_cols_present:
        tf_retry_mask = df[tf_cols_present].isna().all(axis=1)
    else:
        tf_retry_mask = pd.Series(True, index=df.index)

    eligible_mask = opts_retry_mask | tf_retry_mask
    if not eligible_mask.any():
        return df, 0

    # chain-date list is expensive-ish (a glob) — compute once and reuse across rows
    chain_dates = _default_chain_dates()

    # W-C: pre-load snapshot frames once per run (absent locally → None; fine)
    skew_df = _default_read_skew_snapshots()
    ivspread_df = _default_read_ivspread_snapshots()

    # caches: avoid re-computing stamps for same (as_of, ticker) pair
    w13_cache: dict[tuple, dict] = {}
    tf_cache: dict[tuple, dict] = {}
    # group-members cache keyed by (as_of, sector)
    group_cache: dict[tuple, list[str]] = {}

    newly_stamped = 0

    # ── W-OVC: collect per-row stamp results so opt_vanna_relief can be ranked
    # cross-sectionally per as_of before committing any W-OVC values. ─────────
    # Structure: {(as_of, ticker): stamp_dict}  (options-state family only)
    _ovc_pending: dict[tuple, dict] = {}
    # Separate map for vanna_hedge_5d values (computed per-ticker for cross-sectional ranking)
    _ovc_vhd_precomputed: dict[tuple, float | None] = {}

    for idx in df.index[eligible_mask]:
        as_of = df.at[idx, "as_of"]
        ticker = df.at[idx, "ticker"]
        sector = df.at[idx, "sector"] if "sector" in df.columns else None
        key = (as_of, ticker)
        row_committed = False

        # ── options-state family (W1.3 + W-C + W-OVC; own retry gate) ────────
        if bool(opts_retry_mask.at[idx]):
            if key not in w13_cache:
                w13_cache[key] = stamp_options_state(
                    as_of, ticker,
                    chain_dates=chain_dates,
                    skew_df=skew_df,
                    ivspread_df=ivspread_df,
                )
            stamp = w13_cache[key]
            _ovc_pending[key] = stamp  # stash for cross-sectional ranking below
            # Compute vanna_hedge_5d for this (as_of, ticker) if not already done
            if key not in _ovc_vhd_precomputed:
                from engine.options_stamp import _vanna_hedge_5d_from_summary, _default_read_summary, _as_date as _stamp_as_date
                _as_of_d = _stamp_as_date(as_of)
                _sdf = _default_read_summary(ticker)
                _ovc_vhd_precomputed[key] = _vanna_hedge_5d_from_summary(_as_of_d, _sdf) if _as_of_d else None
            # Always write opt_opex_days (calendar-derived; always available) even when
            # coverage-gated cols are null.  This lets us track OPEX proximity for all
            # fires without poisoning the retry gate.
            if stamp.get("opt_opex_days") is not None:
                df.at[idx, "opt_opex_days"] = stamp["opt_opex_days"]
            # Apply coverage-gated cols only when at least one is non-null (else the
            # retry gate stays open so a future run fills them when coverage extends).
            coverage_vals = {c: stamp[c] for c in STAMP_COVERAGE_COLS if c in stamp}
            if any(v is not None for v in coverage_vals.values()):
                for col in STAMP_COVERAGE_COLS:
                    if col in stamp:
                        df.at[idx, col] = stamp[col]
                row_committed = True

        # ── tape-flow family (P2.2; own retry gate) ───────────────────────────
        if bool(tf_retry_mask.at[idx]):
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
            if any(v is not None for v in tf_stamp.values()):
                for col in TAPE_FLOW_STAMP_COLS:
                    df.at[idx, col] = tf_stamp[col]
                row_committed = True

        if row_committed:
            newly_stamped += 1

    # ── W-OVC: cross-sectional opt_vanna_relief ranking ──────────────────────
    # opt_vanna_relief = (iv30_5d_chg < 0) AND (vanna_hedge_5d in top tercile per as_of)
    # The tercile is ranked cross-sectionally over all fires on the same as_of date
    # that were stamped in this pass. This exactly mirrors the study construction
    # (§3.1, tercile rank within date).
    #
    # Step 1: Use precomputed vanna_hedge_5d map (populated in the main loop above).
    _ovc_vhd: dict[tuple, float | None] = _ovc_vhd_precomputed

    # Step 2: Per as_of, compute the top-tercile threshold over all tickers with
    # non-null vanna_hedge_5d. Needs ≥ 3 values to have a meaningful tercile boundary.
    _vhd_by_asof: dict[str, list[float]] = {}
    for (asof_k, _tk), vhd in _ovc_vhd.items():
        if vhd is not None and math.isfinite(vhd):
            _vhd_by_asof.setdefault(str(asof_k), []).append(vhd)

    _tercile_hi: dict[str, float] = {}
    for asof_k, vals in _vhd_by_asof.items():
        if len(vals) >= 3:
            _tercile_hi[asof_k] = float(np.percentile(vals, 100.0 * 2.0 / 3.0))

    # Step 3: Compute opt_vanna_relief per eligible row and write it back.
    # Also compute iv30_5d_chg directly from the summary frame for each ticker.
    # We need iv30_5d_chg (sign) separately from vanna_hedge_5d to avoid any
    # sign confusion due to net_vex magnitude — read it from the stamp's raw values.
    for idx in df.index[eligible_mask]:
        as_of_val = df.at[idx, "as_of"]
        ticker_val = df.at[idx, "ticker"]
        key = (as_of_val, ticker_val)
        if key not in _ovc_pending:
            continue
        stamp = _ovc_pending[key]

        # Only write opt_vanna_relief if the options-state family has coverage
        coverage_vals = {c: stamp.get(c) for c in STAMP_COVERAGE_COLS if c in stamp}
        if not any(v is not None for v in coverage_vals.values()):
            continue

        vhd = _ovc_vhd.get(key)
        vanna_relief: bool | None = None
        if vhd is not None and math.isfinite(vhd):
            thr = _tercile_hi.get(str(as_of_val))
            if thr is not None:
                in_top_tercile = bool(vhd >= thr)
                # iv30_5d_chg: load the summary frame for this ticker (PIT ≤ as_of)
                # and compute latest_iv30 − iv30_5_rows_prior.
                # This is the same calculation as _vanna_hedge_5d_from_summary but
                # we only need the sign of iv30_5d_chg here.
                iv30_chg = _get_iv30_5d_chg_from_summary(
                    as_of_val, ticker_val, w13_cache.get(key, {})
                )
                if iv30_chg is not None:
                    vanna_relief = bool(iv30_chg < 0 and in_top_tercile)

        df.at[idx, "opt_vanna_relief"] = vanna_relief

    return df, newly_stamped


def _get_iv30_5d_chg_from_summary(
    as_of: str,
    ticker: str,
    stamp: dict,
) -> float | None:
    """Extract iv30_5d_chg for (as_of, ticker) from the summary parquet.

    PIT: reads only rows with index date ≤ as_of. Needs ≥ 6 such rows.
    Returns None when insufficient history or columns absent.

    We re-read the summary parquet rather than storing it in the stamp to keep
    STAMP_COLS clean (iv30_5d_chg is a transient quantity for the ranking pass).
    """
    from engine.options_stamp import _default_read_summary, _as_date
    import datetime as _dt_local

    as_of_d = _as_date(as_of)
    if as_of_d is None:
        return None
    sdf = _default_read_summary(ticker)
    if sdf is None or sdf.empty or "iv30" not in sdf.columns:
        return None
    idx_dates = [_as_date(d) for d in sdf.index]
    mask = [d is not None and d <= as_of_d for d in idx_dates]
    usable = sdf[mask]
    if len(usable) < 6:
        return None
    try:
        iv30_latest = float(usable.iloc[-1]["iv30"])
        iv30_prior = float(usable.iloc[-6]["iv30"])
    except (TypeError, ValueError, KeyError):
        return None
    if not (math.isfinite(iv30_latest) and math.isfinite(iv30_prior)):
        return None
    return iv30_latest - iv30_prior


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
        tf_cols_present = [c for c in TAPE_FLOW_STAMP_COLS if c in df.columns]
        n_tf_nonull = (
            int(df[tf_cols_present].notna().any(axis=1).sum())
            if tf_cols_present else 0
        )
        print(
            f"[options_stamp] stamped {n_newly} newly-stamped rows; "
            f"{n_unstamped}/{n_before} rows still unstamped "
            f"(no chain/summary coverage for those as_of/ticker); "
            f"tape-flow columns populated on {n_tf_nonull} rows "
            f"(null-heavy is expected while the store accrues — W1.3 precedent)"
        )
        # W-C coverage summary
        wc_cols = ["opt_ivspread_rel", "opt_skew", "opt_skew_5d_chg",
                   "opt_opex_days", "opt_pin_risk",
                   "opt_wall_dist_up_pct", "opt_wall_dist_down_pct"]
        for col in wc_cols:
            if col in df.columns:
                n_col = int(df[col].notna().sum())
                pct = round(n_col / max(n_before, 1) * 100, 1)
                print(f"  W-C coverage [{col}]: {n_col}/{n_before} rows ({pct}%)")
        # W-OVC coverage summary
        ovc_cols = ["opt_vanna_relief", "opt_front7_charm_share", "opt_root_class"]
        for col in ovc_cols:
            if col in df.columns:
                n_col = int(df[col].notna().sum())
                pct = round(n_col / max(n_before, 1) * 100, 1)
                print(f"  W-OVC coverage [{col}]: {n_col}/{n_before} rows ({pct}%)")


if __name__ == "__main__":
    main()
