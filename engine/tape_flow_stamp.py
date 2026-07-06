"""engine/tape_flow_stamp.py — tape-flow stamp columns for the US board ledger.

Options Alpha program P2.2 (research/LIVE_FLOW_PRODUCTION_ROADMAP_BY_FABLE.md §3 P2.2).
Extends the W1.3 stamp writer (engine/options_stamp.py + scripts/stamp_options_state.py)
with FOUR new nullable columns sourced from the daily tape-flow store
``data/tape_flow/daily/<ROOT>.parquet`` built by the T2a pipeline (engine/tape_flow.py).

## New columns

  opt_net_signed_prem_5d_z
      5-session rolling z of ``net_signed_premium`` vs the name's own tape-flow history.
      PIT: uses only tape_flow rows with date <= fire.as_of.
      Min-history gate: 20 prior observations required; null until met (no fake z on sparse data).

  opt_flow_breadth_group
      Share of names in the fire's GROUP (its sector, from the board row) with positive
      ``net_signed_premium`` on the fire's as_of date.
      Null when group coverage in the tape_flow store is < 40% of the members queried from the
      board ledger for that date (data sparsity on early accrual).

  opt_dte_quality
      ``dte_8_30d_vol_share + dte_31_90d_vol_share`` (8-90d combined volume share) for the
      name-day — the "institutional DTE quality" proxy.
      Null when the name-day row is absent from the store.

  opt_crowding_flag
      Boolean: True if ``short_dated_otm_call_share`` for the name-day is in the top decile
      of its own PIT history (i.e. >= the 90th percentile of prior values for that root).
      ``short_dated_otm_call_share`` is derived as ``dte_0d_vol_share + dte_1_7d_vol_share``
      from the tape_flow row (0d + 1-7d out-of-the-money call volume share, a crowding proxy).
      Min-history gate: 20 prior observations required; null until met.

## PIT discipline
All four columns use ONLY tape_flow rows with date <= fire.as_of (no lookahead).
The store starts accruing nightly from 2026-07-05 forward; stamps will be null-heavy
initially. This is correct and expected (W1.3 precedent: nullable, retry-as-coverage-grows).

## opt_iv_rank_252 — EXPLICITLY DEFERRED
That column reads data/thetadata_eod greeks. The thetadata_eod store is mid-backfill and
has a known dedup defect (#1363). Wiring is deferred until the dedup repair lands and the
manifest marks the universe pass complete. It remains always-null in this writer per ruling A9.

## Schema-union / no-overwrite / backfill-pass convention
Follows the exact W1.3 pattern in scripts/stamp_options_state.py:
  - Schema-union: missing columns added as None before the pass.
  - Only fully-null rows (across ALL stamp columns including these four) are stamped.
  - A row already carrying any non-null stamp value is never overwritten.
  - Injectable readers for all disk I/O (tests pass synthetic frames).
"""
from __future__ import annotations

import datetime as _dt
import math
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

from lib import config

# ── tape-flow stamp columns (the four new P2.2 columns) ──────────────────────
TAPE_FLOW_STAMP_COLS: list[str] = [
    "opt_net_signed_prem_5d_z",   # float: 5-session rolling z of net_signed_premium (null <20 obs)
    "opt_flow_breadth_group",     # float: share of sector peers with positive net_signed_premium
    "opt_dte_quality",            # float: combined 8-90d volume share (dte_quality_share)
    "opt_crowding_flag",          # bool: short-dated OTM call share in top decile (null <20 obs)
]

# Min-history for z-score and decile gates — no fake statistics on sparse data
_MIN_HISTORY = 20

# Group-coverage floor: null breadth when < 40% of expected sector peers are in the store
_GROUP_COVERAGE_FLOOR = 0.40

# Rolling window for the 5-session net-signed-premium z-score
_NSP_ROLL_WINDOW = 5

# ── store path helper ─────────────────────────────────────────────────────────

def _tape_flow_dir() -> Path:
    return config.data_dir() / "tape_flow" / "daily"


# ── injectable readers ────────────────────────────────────────────────────────

def _default_read_tape_flow(root: str) -> pd.DataFrame | None:
    """Read the full per-name tape_flow parquet (all dates for this root)."""
    p = _tape_flow_dir() / f"{root.upper()}.parquet"
    if not p.exists():
        return None
    try:
        cols = [
            "date",
            "net_signed_premium",
            "dte_0d_vol_share",
            "dte_1_7d_vol_share",
            "dte_8_30d_vol_share",
            "dte_31_90d_vol_share",
        ]
        # read only the columns we need (store may have many z-score companions)
        avail = pd.read_parquet(p, columns=["date"]).columns.tolist()
        # build subset list, keeping only columns that exist in the file
        full_df = pd.read_parquet(p)
        needed = [c for c in cols if c in full_df.columns]
        if not needed:
            return None
        return full_df[needed]
    except Exception:  # noqa: BLE001
        return None


# ── helpers ───────────────────────────────────────────────────────────────────

def _as_date(x) -> _dt.date | None:
    if x is None:
        return None
    if isinstance(x, _dt.date) and not isinstance(x, _dt.datetime):
        return x
    try:
        return pd.Timestamp(x).date()
    except (ValueError, TypeError):
        return None


def _pit_rows(df: pd.DataFrame, as_of: _dt.date) -> pd.DataFrame:
    """Filter tape_flow DataFrame to rows with date <= as_of (PIT)."""
    if df is None or df.empty:
        return pd.DataFrame()
    date_col = pd.to_datetime(df["date"], errors="coerce").dt.date
    mask = date_col <= as_of
    return df[mask].copy()


def _safe_float(v) -> float | None:
    try:
        f = float(v)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


# ── per-column stamp computers ────────────────────────────────────────────────

def _net_signed_prem_5d_z(pit: pd.DataFrame, as_of: _dt.date) -> float | None:
    """5-session rolling z of net_signed_premium for the fire's root.

    PIT: pit contains only rows <= as_of (already filtered by caller).
    Min-history gate: requires >= _MIN_HISTORY rows before the current date
    (i.e. at least 20 prior sessions in the store — we count rows STRICTLY BEFORE
    the fire's as_of date so the gate is PIT-honest).
    Returns None when insufficient history or the value is NaN.
    """
    if pit.empty or "net_signed_premium" not in pit.columns:
        return None

    pit = pit.sort_values("date").reset_index(drop=True)
    date_col = pd.to_datetime(pit["date"], errors="coerce").dt.date

    # rows strictly before as_of = "prior history" for the gate
    prior_mask = date_col < as_of
    if prior_mask.sum() < _MIN_HISTORY:
        return None

    # compute rolling 5-session z using the full PIT series (incl. today if present)
    series = pd.to_numeric(pit["net_signed_premium"], errors="coerce")
    roll_mean = series.rolling(_NSP_ROLL_WINDOW, min_periods=_NSP_ROLL_WINDOW).mean()
    roll_std = series.rolling(_NSP_ROLL_WINDOW, min_periods=_NSP_ROLL_WINDOW).std()

    # find the row for as_of
    today_mask = date_col == as_of
    if not today_mask.any():
        return None
    idx = today_mask.idxmax()

    mean_v = _safe_float(roll_mean.iloc[idx])
    std_v = _safe_float(roll_std.iloc[idx])
    val_v = _safe_float(series.iloc[idx])
    if mean_v is None or std_v is None or val_v is None:
        return None
    if std_v == 0.0:
        return 0.0
    return round((val_v - mean_v) / std_v, 6)


def _dte_quality(pit: pd.DataFrame, as_of: _dt.date) -> float | None:
    """Combined 8-90d volume share (dte_8_30d + dte_31_90d) for the name-day.

    Null when the as_of row is absent from the PIT series.
    """
    if pit.empty:
        return None
    date_col = pd.to_datetime(pit["date"], errors="coerce").dt.date
    today = pit[date_col == as_of]
    if today.empty:
        return None
    row = today.iloc[-1]

    v8_30 = _safe_float(row.get("dte_8_30d_vol_share"))
    v31_90 = _safe_float(row.get("dte_31_90d_vol_share"))

    if v8_30 is None and v31_90 is None:
        return None
    return round((v8_30 or 0.0) + (v31_90 or 0.0), 6)


def _crowding_flag(pit: pd.DataFrame, as_of: _dt.date) -> bool | None:
    """True if the short-dated OTM call share today is in the top decile of its own PIT history.

    short_dated_otm_call_share proxy = dte_0d_vol_share + dte_1_7d_vol_share.
    Min-history gate: >= _MIN_HISTORY strictly-prior rows required; null until met.
    """
    if pit.empty:
        return None

    date_col = pd.to_datetime(pit["date"], errors="coerce").dt.date
    prior_mask = date_col < as_of
    today_mask = date_col == as_of

    if not today_mask.any():
        return None
    if prior_mask.sum() < _MIN_HISTORY:
        return None

    def _sdotm(row_or_series):
        v0 = _safe_float(
            row_or_series.get("dte_0d_vol_share")
            if hasattr(row_or_series, "get") else row_or_series["dte_0d_vol_share"]
        )
        v1 = _safe_float(
            row_or_series.get("dte_1_7d_vol_share")
            if hasattr(row_or_series, "get") else row_or_series["dte_1_7d_vol_share"]
        )
        if v0 is None and v1 is None:
            return None
        return (v0 or 0.0) + (v1 or 0.0)

    # compute the metric for today's row
    today_row = pit[today_mask].iloc[-1]
    today_val = _sdotm(today_row)
    if today_val is None:
        return None

    # compute for prior rows
    prior_df = pit[prior_mask].copy()
    prior_vals = []
    for _, r in prior_df.iterrows():
        v = _sdotm(r)
        if v is not None:
            prior_vals.append(v)

    if len(prior_vals) < _MIN_HISTORY:
        return None

    p90 = float(np.percentile(prior_vals, 90))
    return bool(today_val >= p90)


def _flow_breadth_group(
    as_of: _dt.date,
    sector: str | None,
    read_tape_flow: Callable[[str], pd.DataFrame | None],
    group_members: list[str],
) -> float | None:
    """Share of sector peers with positive net_signed_premium on as_of.

    group_members: list of tickers expected in this sector on this date (from caller).
    Coverage gate: if fewer than _GROUP_COVERAGE_FLOOR fraction of group_members have data
    in the store for as_of, return None.
    """
    if not group_members or not sector:
        return None

    positive = 0
    found = 0
    for member in group_members:
        df = read_tape_flow(member)
        if df is None or df.empty:
            continue
        pit = _pit_rows(df, as_of)
        if pit.empty:
            continue
        date_col = pd.to_datetime(pit["date"], errors="coerce").dt.date
        today_rows = pit[date_col == as_of]
        if today_rows.empty:
            continue
        found += 1
        nsp = _safe_float(today_rows.iloc[-1].get("net_signed_premium"))
        if nsp is not None and nsp > 0:
            positive += 1

    if found == 0:
        return None
    coverage = found / len(group_members)
    if coverage < _GROUP_COVERAGE_FLOOR:
        return None

    return round(positive / found, 6)


# ── main entry point ──────────────────────────────────────────────────────────

def stamp_tape_flow(
    as_of,
    ticker: str,
    sector: str | None = None,
    group_members: list[str] | None = None,
    *,
    read_tape_flow: Callable[[str], pd.DataFrame | None] | None = None,
) -> dict:
    """Return the four P2.2 nullable tape-flow stamp columns for a fire (as_of, ticker).

    All four TAPE_FLOW_STAMP_COLS are always present; any that cannot be computed (no
    data, insufficient history, coverage below floor) are None.

    Parameters
    ----------
    as_of : date string or date object for the fire.
    ticker : the option root (e.g. "AAPL").
    sector : the board row's sector label (used for group-breadth). None → breadth is null.
    group_members : list of tickers in the same sector on this date (from the board ledger).
                    None → breadth is null. Should exclude the fire's own ticker if desired,
                    though including it is harmless (self-coverage is then counted).
    read_tape_flow : injectable reader (root -> DataFrame|None). Defaults to disk reader.
    """
    d = _as_date(as_of)
    null_stamp = {c: None for c in TAPE_FLOW_STAMP_COLS}

    if d is None or not ticker:
        return null_stamp

    _read = read_tape_flow or _default_read_tape_flow

    # ── per-name series (needed for three of the four columns) ─────────────────
    own_df = _read(ticker)
    own_pit = _pit_rows(own_df, d) if own_df is not None else pd.DataFrame()

    stamp = dict(null_stamp)
    stamp["opt_net_signed_prem_5d_z"] = _net_signed_prem_5d_z(own_pit, d)
    stamp["opt_dte_quality"] = _dte_quality(own_pit, d)
    stamp["opt_crowding_flag"] = _crowding_flag(own_pit, d)

    # ── group breadth (needs the full sector member list) ──────────────────────
    stamp["opt_flow_breadth_group"] = _flow_breadth_group(
        d, sector, _read, group_members or []
    )

    return stamp
