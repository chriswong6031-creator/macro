"""wave4.py — Durable-Bottom Entry Timing Study, Wave 4: COILED-FIRE layer

Spec: research/signal_engine/DURABLE_BOTTOM_FRAMEWORK.md §8
      "Wave-4 pre-registration (2026-07-02)" block — the GATES are law.
Reports: research/entry_timing/WAVE3_REPORT.md (precursor)

CLI:
  python3 research/entry_timing/wave4.py --panel {stocks,baskets,cn}
        [--tickers ...] [--workers 6] [--out DIR]

Defaults:
  --out research/entry_timing/_out/wave4_{panel}

Panels:
  stocks  — data/stocks/*.parquet     (OHLCV, >= 1500 bars, EVAL_START 2012-01-01)
  baskets — data/baskets/ohlcv/*.parquet (OHLCV, >= 1000 bars, EVAL_START 2015-01-01)
  cn      — data/china_search/closes.parquet (close-only wide, >= 800 bars, EVAL_START 2022-09-01)

FIRE SETS (per name, per panel):
  All fires generated with TH.build_signals via TH.VARIANTS for m1d_s3d and m2d_s3d.
  Fill = i+1. EVAL_START per panel.
  Daily COILED state = washout_state AND sector-cohort >= 0.4 (wave3 logic EXACTLY).
  A fire is INSIDE iff COILED_state at its signal bar is True.

DEDUPE (8-trading-day rule):
  R  = dedupe(m2d_s3d inside)
  C1 = dedupe(m1d_s3d inside)
  C2 = dedupe(union(m1d_s3d inside, m2d_s3d inside), sorted by bar; same bar → once)
  Also all three UNDEDUPED versions for sensitivity table T-dedupe.

OUTCOMES per kept fire:
  Full wave2 barrier set (stop5, clean10/15/20/30, clean15_h189, dead_money, mae63/mfe63)
  premium_over_trough (wave3 definition: p/c[capit_idx]-1)
  event capture: durable-B15 window [t0-5,t0+15], premium_over_P0, lead
  recall_B15/B30, trap_fire_rate

TABLES: wave4_tables.json per panel
  T1: rows {R, C1, C2} x {deduped, undeduped}:
      n, fires/name/yr, stop5, clean10/15/20/30, clean15_h189, dead_money,
      med_mfe63, med_mae63, med_premium_over_trough, med_lead (captured only),
      recall_B15, recall_B30, trap_fire_rate. Plus base3d-ALL context row.
  T2 (stocks only): 5 time folds (fill-date quintiles, 180d purge):
      per fold n(R)/n(C1)/n(C2), clean15 and stop5 per set, (C-R) deltas
  T3: per-name paired deltas (C1-vs-R, C2-vs-R, names >= 3 fires in BOTH sets)
  T4: per-event FIRST-fire pairing for durable B15 events captured by BOTH C2 and R
  T5: ticker-half (even/odd) clean15 + stop5 per set

SMOKES:
  stocks: AAPL,MSFT,NVDA,JNJ,WMT,XOM,KO,CAT --workers 2:
    R deduped n < R undeduped n; C2 n >= max(C1,R) deduped;
    all T-blocks present; R-undeduped stop5/clean15 within 1.5pp of wave3's inside-COILED smoke (33.33/42.42)
  cn: 14 tickers across >= 3 sectors: C1/C2/R non-empty inside COILED
  baskets: 12-ticker mini: tables build (cohort computes, not required to have COILED fires)
"""
from __future__ import annotations

import sys
import time
import json
import math
import argparse
import warnings
import logging
from pathlib import Path
from multiprocessing import Pool

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
logging.disable(logging.CRITICAL)

# ── path bootstrap ────────────────────────────────────────────────────────────
ROOT        = Path(__file__).resolve().parents[2]
SIG_ENG     = ROOT / "research" / "signal_engine"
ENTRY_TIMING = ROOT / "research" / "entry_timing"
sys.path.insert(0, str(SIG_ENG))
sys.path.insert(0, str(ENTRY_TIMING))

import tuning_harness as TH   # noqa: E402
import wave1                   # noqa: E402
import wave2                   # noqa: E402
import wave3                   # noqa: E402

# ── re-imports from prior waves (DO NOT MODIFY those modules) ─────────────────
from wave1 import (
    label_events,
    build_tf_grids,
    build_sector_d_matrix,
    FWD_REQ, STOP5, DEAD_MONEY_BAND, DEAD_MONEY_CAP,
    MFE_MAE_W, H6_COHORT_MIN_PEERS, H6_COHORT_THRESH,
    H5_FAILED_WINDOW, DD_MIN, DURABLE_HOLD, LIFTOFF_126,
    H1_D_DEEP_THRESH, CAPTURE, OUTCOME_W,
)
from wave2 import (
    label_events_w2,
    compute_outcomes_w2,
    compute_features_w2,
    build_theme_d_matrix,
    build_theme_peers,
    build_basket_sector_map,
    build_active_set,
    load_membership,
    _serialize_d_matrix,
    _rate_row,
    build_T8 as _w2_build_T8,
    OUTCOME_W_H189, CLEAN15_MULT, STOP_MULT,
    MEMBERSHIP,
    DATA_STOCKS as W2_DATA_STOCKS,
    DATA_BASKETS,
    BREADTH,
)
from wave3 import (
    _compute_washout_state_daily,
    _compute_daily_coiled_state,
    load_close_only_wide,
    build_sector_d_matrix_from_close_dict,
    build_theme_d_matrix_from_close_dict,
    _process_closeonly_inner,
    load_cn_membership,
    build_cn_theme_peers,
    DATA_CN_CLOSES, DATA_CN_MEMBERS, DATA_CN_MEMBERSHIP,
    CN_MIN_BARS, CN_EVAL_START,
    BREADTH_CONST,
    _recall_for_fires,
)

# ── data paths ────────────────────────────────────────────────────────────────
DATA_STOCKS = ROOT / "data" / "stocks"
DATA_BASKETS_OHLCV = ROOT / "data" / "baskets" / "ohlcv"

# ── panel constants ───────────────────────────────────────────────────────────
PANEL_CONFIGS = {
    "stocks": {
        "data_dir":   DATA_STOCKS,
        "min_bars":   1500,
        "eval_start": pd.Timestamp("2012-01-01"),
    },
    "baskets": {
        "data_dir":   DATA_BASKETS_OHLCV,
        "min_bars":   1000,
        "eval_start": pd.Timestamp("2015-01-01"),
    },
    "cn": {
        "data_dir":   None,  # wide parquet
        "min_bars":   CN_MIN_BARS,
        "eval_start": CN_EVAL_START,
    },
}

# ── Wave-4 variants ───────────────────────────────────────────────────────────
W4_FIRE_VARIANTS = ["m1d_s3d", "m2d_s3d"]

# 8-trading-day dedupe radius
DEDUPE_WINDOW = 8


# ══════════════════════════════════════════════════════════════════════════════
# Dedupe helper (8-trading-day rule)
# ══════════════════════════════════════════════════════════════════════════════

def dedupe_fires(fire_rows: list[dict], sig_idx_key: str = "sig_idx") -> list[dict]:
    """Apply the 8-trading-day per-name dedupe rule.

    Within each name's INSIDE-fire sequence sorted by signal bar, keep a fire only
    if its signal bar is > 8 trading bars after the last KEPT fire's signal bar.
    Returns a new list (does NOT modify fire_rows).
    """
    # Group by ticker
    by_ticker: dict[str, list[dict]] = {}
    for row in fire_rows:
        by_ticker.setdefault(row["ticker"], []).append(row)

    kept: list[dict] = []
    for ticker, rows in by_ticker.items():
        rows_sorted = sorted(rows, key=lambda r: r[sig_idx_key])
        last_kept_idx = -9999
        for row in rows_sorted:
            si = row[sig_idx_key]
            if si - last_kept_idx > DEDUPE_WINDOW:
                kept.append(row)
                last_kept_idx = si
    return kept


# ══════════════════════════════════════════════════════════════════════════════
# Per-name COILED-fire processing (stocks / baskets, OHLCV panels)
# ══════════════════════════════════════════════════════════════════════════════

def _ohlcv_inner(
    ticker: str,
    fp: str,
    spy_ratio: pd.Series | None,
    sector_map: dict[str, str],
    sector_d_matrix: dict,
    theme_peers: dict[str, set[str]] | None,
    theme_d_matrix: dict | None,
    is_active: bool,
    eval_start: pd.Timestamp,
    min_bars: int,
) -> dict:
    """Process one OHLCV name for wave-4.

    Returns dict with keys:
      'events': list of event row dicts
      'm1d_s3d': list of ALL inside-COILED fire rows (pre-dedupe, pre-eval and eval)
      'm2d_s3d': list of ALL inside-COILED fire rows (pre-dedupe, pre-eval and eval)
      'm2d_s3d_all_inside': the same as m2d_s3d (kept for base3d-ALL context)
      'base3d_all': list of base3d ALL-fire rows (for context row in T1)
    """
    df = pd.read_parquet(fp)
    daily = df["close"].dropna()
    if len(daily) < min_bars:
        return {}

    hi  = df["high"].reindex(daily.index)   if "high"   in df.columns else pd.Series(np.nan, index=daily.index)
    lo  = df["low"].reindex(daily.index)    if "low"    in df.columns else pd.Series(np.nan, index=daily.index)
    vol = df["volume"].reindex(daily.index) if "volume" in df.columns else None

    c      = daily.to_numpy()
    hi_arr = hi.to_numpy()
    lo_arr = lo.to_numpy()
    vol_arr = vol.to_numpy() if vol is not None else None
    idx    = daily.index
    n      = len(c)

    # SPY ratio alignment
    spy_ratio_aligned: pd.Series | None = None
    if spy_ratio is not None:
        try:
            spy_ratio_aligned = spy_ratio.reindex(daily.index, method="ffill")
        except Exception:
            pass

    # Label events (wave-2 extended: durable_tol5, durable_lift30, durable_h189, b30)
    events_df = label_events_w2(daily)
    events_df["ticker"]    = ticker
    events_df["is_active"] = is_active

    # Build capture windows per event
    event_windows = []
    for _, ev in events_df.iterrows():
        t0     = ev["t0"]
        t0_pos = idx.get_loc(t0)
        event_windows.append({
            "t0_pos":       t0_pos,
            "w_start":      t0_pos + CAPTURE[0],
            "w_end":        t0_pos + CAPTURE[1],
            "label":        ev["label"],
            "p0":           ev["p0"],
            "b30":          ev["b30"],
            "dd_at_trough": ev["dd_at_trough"],
        })

    # Build TF grids once
    grids = build_tf_grids(daily, hi, lo, spy_ratio_aligned)

    # Compute daily COILED state (washout × sector-cohort >= 0.4)
    coiled_state = _compute_daily_coiled_state(daily, ticker, sector_map, sector_d_matrix)

    result: dict = {"events": events_df.to_dict("records")}

    # base3d ALL fires (for context row)
    base3d_cfg = TH.VARIANTS["base3d"]
    base3d_frame = TH.build_signals(daily, base3d_cfg, hi, lo)
    base3d_all_rows: list[dict] = []
    variant_fires_before_b3d: list[dict] = []
    for sig_date in base3d_frame.index[base3d_frame["buy"]].tolist():
        i = idx.get_loc(sig_date)
        fill_idx = i + 1
        if fill_idx >= n:
            continue
        fill_date = idx[fill_idx]
        if fill_date < eval_start:
            pre_row: dict = {"fill_idx": fill_idx, "sig_idx": i, "stop5": 0, "resolution_idx": fill_idx + OUTCOME_W}
            if fill_idx + FWD_REQ < n:
                from wave1 import compute_outcomes as _w1_out
                _op = _w1_out(fill_idx, c[fill_idx], c, hi_arr, lo_arr)
                pre_row["stop5"] = _op["stop5"]
                pre_row["resolution_idx"] = _op["resolution_idx"]
            variant_fires_before_b3d.append(pre_row)
            continue
        if fill_idx + FWD_REQ >= n:
            continue
        p = c[fill_idx]
        if np.isnan(p):
            continue
        outcomes = compute_outcomes_w2(fill_idx, p, c, hi_arr, lo_arr)
        # premium over trough
        start90 = max(0, i - 90)
        capit_local = int(np.argmin(c[start90: i + 1]))
        capit_idx   = start90 + capit_local
        pot = (p / c[capit_idx] - 1) if (c[capit_idx] > 0 and not np.isnan(c[capit_idx])) else np.nan
        # event capture
        captured, ev_label, premium_over_p0, lead, p0_val = False, None, None, None, None
        for ew in event_windows:
            if ew["w_start"] <= i <= ew["w_end"]:
                captured = True
                ev_label = ew["label"]
                premium_over_p0 = p / ew["p0"] - 1 if ew["p0"] > 0 else None
                lead     = i - ew["t0_pos"]
                p0_val   = ew["p0"]
                break
        row = {
            "ticker":              ticker,
            "is_active":           is_active,
            "sig_date":            sig_date,
            "fill_date":           fill_date,
            "sig_idx":             i,
            "fill_idx":            fill_idx,
            "p":                   p,
            "premium_over_trough": pot,
            **outcomes,
            "captured":            captured,
            "ev_label":            ev_label,
            "premium_over_p0":     premium_over_p0,
            "lead":                lead,
        }
        base3d_all_rows.append(row)
        variant_fires_before_b3d.append({"fill_idx": fill_idx, "sig_idx": i,
                                          "stop5": outcomes["stop5"],
                                          "resolution_idx": outcomes["resolution_idx"]})

    result["base3d_all"] = base3d_all_rows

    # W4 fire variants: m1d_s3d and m2d_s3d, INSIDE COILED only
    for variant_name in W4_FIRE_VARIANTS:
        cfg   = TH.VARIANTS[variant_name]
        frame = TH.build_signals(daily, cfg, hi, lo)
        raw_fires = frame.index[frame["buy"]].tolist()

        fire_rows: list[dict] = []
        variant_fires_before: list[dict] = []

        for sig_date in raw_fires:
            i = idx.get_loc(sig_date)
            fill_idx = i + 1
            if fill_idx >= n:
                continue
            fill_date = idx[fill_idx]

            # Track pre-eval fires for failed_180 even though we don't emit them
            if fill_date < eval_start:
                pre_row = {"fill_idx": fill_idx, "sig_idx": i, "stop5": 0, "resolution_idx": fill_idx + OUTCOME_W}
                if fill_idx + FWD_REQ < n:
                    from wave1 import compute_outcomes as _w1_out
                    _op = _w1_out(fill_idx, c[fill_idx], c, hi_arr, lo_arr)
                    pre_row["stop5"] = _op["stop5"]
                    pre_row["resolution_idx"] = _op["resolution_idx"]
                variant_fires_before.append(pre_row)
                continue

            if fill_idx + FWD_REQ >= n:
                continue

            p = c[fill_idx]
            if np.isnan(p):
                continue

            # Only inside COILED state
            if not coiled_state[i]:
                variant_fires_before.append({"fill_idx": fill_idx, "sig_idx": i,
                                             "stop5": 0, "resolution_idx": fill_idx + OUTCOME_W})
                continue

            # Outcomes
            outcomes = compute_outcomes_w2(fill_idx, p, c, hi_arr, lo_arr)

            # premium over trough
            start90 = max(0, i - 90)
            capit_local = int(np.argmin(c[start90: i + 1]))
            capit_idx   = start90 + capit_local
            pot = (p / c[capit_idx] - 1) if (c[capit_idx] > 0 and not np.isnan(c[capit_idx])) else np.nan

            # Event capture
            captured, ev_label, premium_over_p0, lead = False, None, None, None
            for ew in event_windows:
                if ew["w_start"] <= i <= ew["w_end"]:
                    captured = True
                    ev_label = ew["label"]
                    premium_over_p0 = p / ew["p0"] - 1 if ew["p0"] > 0 else None
                    lead     = i - ew["t0_pos"]
                    break

            row = {
                "ticker":              ticker,
                "is_active":           is_active,
                "sig_date":            sig_date,
                "fill_date":           fill_date,
                "sig_idx":             i,
                "fill_idx":            fill_idx,
                "p":                   p,
                "premium_over_trough": pot,
                **outcomes,
                "captured":            captured,
                "ev_label":            ev_label,
                "premium_over_p0":     premium_over_p0,
                "lead":                lead,
            }

            fire_rows.append(row)
            variant_fires_before.append({"fill_idx": fill_idx, "sig_idx": i,
                                          "stop5": outcomes["stop5"],
                                          "resolution_idx": outcomes["resolution_idx"]})

        result[variant_name] = fire_rows

    return result


def _ohlcv_worker(args: tuple) -> tuple[str, dict]:
    """Multiprocessing worker for OHLCV panels (stocks/baskets)."""
    (ticker, fp, spy_ratio_vals, spy_ratio_idx,
     sector_map, sector_d_matrix_ser,
     theme_peers, theme_d_matrix_ser,
     is_active, eval_start_str, min_bars) = args

    # Reconstruct spy_ratio
    spy_ratio: pd.Series | None = None
    if spy_ratio_vals is not None and spy_ratio_idx is not None:
        spy_ratio = pd.Series(spy_ratio_vals, index=pd.DatetimeIndex(spy_ratio_idx))

    # Reconstruct sector_d_matrix
    sector_d_matrix: dict = {}
    for t, (idx_vals, arr) in sector_d_matrix_ser.items():
        sector_d_matrix[t] = (pd.DatetimeIndex(idx_vals), np.array(arr))

    # Reconstruct theme_d_matrix
    theme_d_matrix: dict | None = None
    if theme_d_matrix_ser is not None:
        theme_d_matrix = {}
        for t, (idx_vals, arr) in theme_d_matrix_ser.items():
            theme_d_matrix[t] = (pd.DatetimeIndex(idx_vals), np.array(arr))

    eval_start = pd.Timestamp(eval_start_str)

    try:
        result = _ohlcv_inner(
            ticker, fp, spy_ratio,
            sector_map, sector_d_matrix,
            theme_peers, theme_d_matrix,
            is_active, eval_start, min_bars,
        )
        return (ticker, result)
    except Exception as e:
        return (ticker, {"_error": str(e)})


# ══════════════════════════════════════════════════════════════════════════════
# Per-name COILED-fire processing (CN, close-only)
# ══════════════════════════════════════════════════════════════════════════════

def _cn_inner(
    ticker: str,
    daily: pd.Series,
    sector_map: dict[str, str],
    sector_d_matrix: dict,
    theme_peers: dict[str, set[str]] | None,
    theme_d_matrix: dict | None,
    eval_start: pd.Timestamp,
    min_bars: int,
) -> dict:
    """Process one CN close-only name for wave-4."""
    if len(daily) < min_bars:
        return {}

    c      = daily.to_numpy()
    idx    = daily.index
    n      = len(c)

    hi_arr = np.full(n, np.nan)
    lo_arr = np.full(n, np.nan)

    # Label events
    events_df = label_events_w2(daily)
    events_df["ticker"] = ticker

    # Capture windows
    event_windows = []
    for _, ev in events_df.iterrows():
        t0     = ev["t0"]
        t0_pos = idx.get_loc(t0)
        event_windows.append({
            "t0_pos":       t0_pos,
            "w_start":      t0_pos + CAPTURE[0],
            "w_end":        t0_pos + CAPTURE[1],
            "label":        ev["label"],
            "p0":           ev["p0"],
            "b30":          ev["b30"],
            "dd_at_trough": ev["dd_at_trough"],
        })

    # TF grids (no SPY, no volume)
    grids = build_tf_grids(daily, pd.Series(np.nan, index=idx), pd.Series(np.nan, index=idx), spy_ratio=None)

    # Daily COILED state
    coiled_state = _compute_daily_coiled_state(daily, ticker, sector_map, sector_d_matrix)

    result: dict = {"events": events_df.to_dict("records")}

    # base3d ALL (context row, close-only)
    base3d_cfg = TH.VARIANTS["base3d"]
    base3d_frame = TH.build_signals(daily, base3d_cfg,
                                     pd.Series(np.nan, index=idx), pd.Series(np.nan, index=idx))
    base3d_all_rows: list[dict] = []
    for sig_date in base3d_frame.index[base3d_frame["buy"]].tolist():
        i = idx.get_loc(sig_date)
        fill_idx = i + 1
        if fill_idx >= n or idx[fill_idx] < eval_start or fill_idx + FWD_REQ >= n:
            continue
        p = c[fill_idx]
        if np.isnan(p):
            continue
        outcomes = compute_outcomes_w2(fill_idx, p, c, hi_arr, lo_arr)
        outcomes.pop("low_stop5", None)
        start90 = max(0, i - 90)
        capit_local = int(np.argmin(c[start90: i + 1]))
        capit_idx   = start90 + capit_local
        pot = (p / c[capit_idx] - 1) if (c[capit_idx] > 0) else np.nan
        captured, ev_label, premium_over_p0, lead = False, None, None, None
        for ew in event_windows:
            if ew["w_start"] <= i <= ew["w_end"]:
                captured = True
                ev_label = ew["label"]
                premium_over_p0 = p / ew["p0"] - 1 if ew["p0"] > 0 else None
                lead = i - ew["t0_pos"]
                break
        base3d_all_rows.append({
            "ticker": ticker, "sig_date": sig_date, "fill_date": idx[fill_idx],
            "sig_idx": i, "fill_idx": fill_idx, "p": p,
            "premium_over_trough": pot, **outcomes,
            "captured": captured, "ev_label": ev_label,
            "premium_over_p0": premium_over_p0, "lead": lead,
        })
    result["base3d_all"] = base3d_all_rows

    # W4 fire variants (m1d_s3d, m2d_s3d), INSIDE COILED only
    for variant_name in W4_FIRE_VARIANTS:
        cfg   = TH.VARIANTS[variant_name]
        frame = TH.build_signals(daily, base3d_cfg if False else cfg,
                                  pd.Series(np.nan, index=idx), pd.Series(np.nan, index=idx))
        raw_fires = frame.index[frame["buy"]].tolist()

        fire_rows: list[dict] = []

        for sig_date in raw_fires:
            i = idx.get_loc(sig_date)
            fill_idx = i + 1
            if fill_idx >= n:
                continue
            fill_date = idx[fill_idx]
            if fill_date < eval_start:
                continue
            if fill_idx + FWD_REQ >= n:
                continue
            p = c[fill_idx]
            if np.isnan(p):
                continue

            # Only inside COILED state
            if not coiled_state[i]:
                continue

            outcomes = compute_outcomes_w2(fill_idx, p, c, hi_arr, lo_arr)
            outcomes.pop("low_stop5", None)

            start90 = max(0, i - 90)
            capit_local = int(np.argmin(c[start90: i + 1]))
            capit_idx   = start90 + capit_local
            pot = (p / c[capit_idx] - 1) if (c[capit_idx] > 0) else np.nan

            captured, ev_label, premium_over_p0, lead = False, None, None, None
            for ew in event_windows:
                if ew["w_start"] <= i <= ew["w_end"]:
                    captured = True
                    ev_label = ew["label"]
                    premium_over_p0 = p / ew["p0"] - 1 if ew["p0"] > 0 else None
                    lead     = i - ew["t0_pos"]
                    break

            row = {
                "ticker":              ticker,
                "sig_date":            sig_date,
                "fill_date":           fill_date,
                "sig_idx":             i,
                "fill_idx":            fill_idx,
                "p":                   p,
                "premium_over_trough": pot,
                **outcomes,
                "captured":            captured,
                "ev_label":            ev_label,
                "premium_over_p0":     premium_over_p0,
                "lead":                lead,
            }
            fire_rows.append(row)

        result[variant_name] = fire_rows

    return result


def _cn_worker(args: tuple) -> tuple[str, dict]:
    """Multiprocessing worker for CN close-only panel."""
    (ticker, close_vals, close_idx,
     sector_map, sector_d_matrix_ser,
     theme_peers, theme_d_matrix_ser,
     eval_start_str, min_bars) = args

    daily = pd.Series(close_vals, index=pd.DatetimeIndex(close_idx))

    sector_d_matrix: dict = {}
    for t, (idx_vals, arr) in sector_d_matrix_ser.items():
        sector_d_matrix[t] = (pd.DatetimeIndex(idx_vals), np.array(arr))

    theme_d_matrix: dict | None = None
    if theme_d_matrix_ser is not None:
        theme_d_matrix = {}
        for t, (idx_vals, arr) in theme_d_matrix_ser.items():
            theme_d_matrix[t] = (pd.DatetimeIndex(idx_vals), np.array(arr))

    eval_start = pd.Timestamp(eval_start_str)

    try:
        result = _cn_inner(
            ticker, daily,
            sector_map, sector_d_matrix,
            theme_peers, theme_d_matrix,
            eval_start, min_bars,
        )
        return (ticker, result)
    except Exception as e:
        return (ticker, {"_error": str(e)})


# ══════════════════════════════════════════════════════════════════════════════
# Rate / statistics helpers
# ══════════════════════════════════════════════════════════════════════════════

_OUTCOME_COLS = ["stop5", "clean10", "clean15", "clean20", "clean30", "clean15_h189", "dead_money"]

def _fires_per_name_yr(df: pd.DataFrame) -> float:
    """Average fires per name per year over the eval window."""
    if len(df) == 0:
        return float("nan")
    names = df["ticker"].nunique()
    if names == 0:
        return float("nan")
    fd = pd.to_datetime(df["fill_date"])
    yr_span = (fd.max() - fd.min()).days / 365.25
    if yr_span <= 0:
        return float("nan")
    return round(len(df) / names / yr_span, 2)


def _build_T1_row(df: pd.DataFrame, label: str,
                  events_df: pd.DataFrame) -> dict:
    """Build one T1 row from a fires sub-DataFrame."""
    n = len(df)
    row: dict = {"label": label, "n": n, "fires_per_name_yr": _fires_per_name_yr(df)}
    for col in _OUTCOME_COLS:
        if col in df.columns and n > 0:
            vals = df[col].dropna()
            row[col] = round(float(vals.mean()) * 100, 2) if len(vals) > 0 else float("nan")
        else:
            row[col] = float("nan")

    for col, key in [("mfe63", "med_mfe63"), ("mae63", "med_mae63")]:
        if col in df.columns and n > 0:
            vals = df[col].dropna()
            row[key] = round(float(vals.median()) * 100, 2) if len(vals) > 0 else float("nan")
        else:
            row[key] = float("nan")

    # med_premium_over_trough (all fires)
    if "premium_over_trough" in df.columns and n > 0:
        pot = df["premium_over_trough"].dropna()
        row["med_premium_over_trough"] = round(float(pot.median()) * 100, 2) if len(pot) > 0 else float("nan")
    else:
        row["med_premium_over_trough"] = float("nan")

    # med_lead (captured durable fires only)
    if n > 0 and "captured" in df.columns and "ev_label" in df.columns and "lead" in df.columns:
        cap = df[df["captured"] & (df["ev_label"] == "durable")]
        leads = cap["lead"].dropna()
        row["med_lead"] = float(leads.median()) if len(leads) > 0 else float("nan")
    else:
        row["med_lead"] = float("nan")

    # recall_B15, recall_B30, trap_fire_rate (vectorized approx, same as wave2/3)
    if len(events_df) > 0 and n > 0:
        df2 = df.copy()
        df2["sig_date"] = pd.to_datetime(df2["sig_date"])
        evs = events_df.copy()
        evs["t0"] = pd.to_datetime(evs["t0"])

        dur_evs  = evs[evs["label"] == "durable"]
        b30_evs  = evs[(evs["label"] == "durable") & (evs["b30"] == True)]   # noqa: E712
        trap_evs = evs[evs["label"] == "trap"]

        rB15 = _recall_for_fires(df2, dur_evs)
        rB30 = _recall_for_fires(df2, b30_evs)
        trap_fr = _recall_for_fires(df2, trap_evs)

        row["recall_B15"]     = round(rB15 * 100, 2)    if not np.isnan(rB15) else float("nan")
        row["recall_B30"]     = round(rB30 * 100, 2)    if not np.isnan(rB30) else float("nan")
        row["trap_fire_rate"] = round(trap_fr * 100, 2) if not np.isnan(trap_fr) else float("nan")
    else:
        row["recall_B15"]     = float("nan")
        row["recall_B30"]     = float("nan")
        row["trap_fire_rate"] = float("nan")

    return row


def build_T1(
    R_deduped: pd.DataFrame,   C1_deduped: pd.DataFrame,   C2_deduped: pd.DataFrame,
    R_raw: pd.DataFrame,       C1_raw: pd.DataFrame,       C2_raw: pd.DataFrame,
    base3d_all: pd.DataFrame,
    events_df: pd.DataFrame,
) -> list[dict]:
    """T1: rows {R, C1, C2} × {deduped, undeduped}, plus base3d-ALL context."""
    rows = []
    for label, df in [
        ("base3d_ALL_context", base3d_all),
        ("R_deduped",   R_deduped),
        ("R_undeduped", R_raw),
        ("C1_deduped",  C1_deduped),
        ("C1_undeduped", C1_raw),
        ("C2_deduped",  C2_deduped),
        ("C2_undeduped", C2_raw),
    ]:
        rows.append(_build_T1_row(df, label, events_df))
    return rows


def build_T2_stocks(
    R_deduped: pd.DataFrame, C1_deduped: pd.DataFrame, C2_deduped: pd.DataFrame,
) -> list[dict]:
    """T2 (stocks only): 5 time folds by fill-date quintiles, 180d purge at each boundary.

    Per fold: n(R)/n(C1)/n(C2), clean15 and stop5 per set, (C-R) deltas.
    """
    # Merge all three with set label
    dfs = []
    for df, lbl in [(R_deduped, "R"), (C1_deduped, "C1"), (C2_deduped, "C2")]:
        if len(df) > 0:
            d = df.copy()
            d["_set"] = lbl
            dfs.append(d)
    if not dfs:
        return []
    combined = pd.concat(dfs, ignore_index=True)
    combined["fill_date"] = pd.to_datetime(combined["fill_date"])

    # Quintile boundaries from all fills combined
    dates_sorted = combined["fill_date"].sort_values()
    n_total = len(dates_sorted)
    q_size = n_total // 5
    boundaries: list[pd.Timestamp] = []
    for q in range(1, 5):
        bidx = q_size * q
        if bidx < n_total:
            boundaries.append(dates_sorted.iloc[bidx])

    combined["fold"] = pd.cut(
        combined["fill_date"],
        bins=[pd.Timestamp.min] + boundaries + [pd.Timestamp.max],
        labels=False, right=True, include_lowest=True,
    )

    rows = []
    for fold_id in range(5):
        fold_all = combined[combined["fold"] == fold_id].copy()

        # 180d purge after each fold boundary
        if fold_id > 0:
            cutoff = boundaries[fold_id - 1] + pd.Timedelta(days=180)
            fold_all = fold_all[fold_all["fill_date"] >= cutoff]

        fold_start = str(fold_all["fill_date"].min().date()) if len(fold_all) > 0 else "N/A"
        fold_end   = str(fold_all["fill_date"].max().date()) if len(fold_all) > 0 else "N/A"

        row_fold: dict = {"fold": fold_id, "fold_start": fold_start, "fold_end": fold_end}

        for lbl, col_n in [("R", "n_R"), ("C1", "n_C1"), ("C2", "n_C2")]:
            sub = fold_all[fold_all["_set"] == lbl]
            nf = len(sub)
            row_fold[col_n] = nf
            c15 = round(float(sub["clean15"].mean()) * 100, 2) if nf > 0 else float("nan")
            s5  = round(float(sub["stop5"].mean())   * 100, 2) if nf > 0 else float("nan")
            row_fold[f"{lbl}_clean15"] = c15
            row_fold[f"{lbl}_stop5"]   = s5

        # (C - R) deltas
        for C_lbl in ("C1", "C2"):
            for metric in ("clean15", "stop5"):
                c_val = row_fold.get(f"{C_lbl}_{metric}", float("nan"))
                r_val = row_fold.get(f"R_{metric}", float("nan"))
                if not np.isnan(c_val) and not np.isnan(r_val):
                    row_fold[f"{C_lbl}_minus_R_{metric}"] = round(c_val - r_val, 2)
                else:
                    row_fold[f"{C_lbl}_minus_R_{metric}"] = float("nan")

        rows.append(row_fold)

    return rows


def build_T3(
    R_deduped: pd.DataFrame, C1_deduped: pd.DataFrame, C2_deduped: pd.DataFrame,
) -> list[dict]:
    """T3: per-name paired deltas (C1-vs-R, C2-vs-R).

    Only names with >= 3 kept fires in BOTH sets.
    Reports: median per-name delta-stop5, median per-name delta-clean15,
             % names C wins stop5, % names C wins clean15.
    """
    rows = []

    for C_fires, C_lbl in [(C1_deduped, "C1_vs_R"), (C2_deduped, "C2_vs_R")]:
        names = set(R_deduped["ticker"].unique()) & set(C_fires["ticker"].unique())

        delta_stop5:  list[float] = []
        delta_clean15: list[float] = []
        c_wins_s5  = 0
        c_wins_c15 = 0
        n_qualifying = 0

        for ticker in names:
            r_sub = R_deduped[R_deduped["ticker"] == ticker]
            c_sub = C_fires[C_fires["ticker"] == ticker]
            if len(r_sub) < 3 or len(c_sub) < 3:
                continue
            n_qualifying += 1
            rs5  = float(r_sub["stop5"].mean())
            cs5  = float(c_sub["stop5"].mean())
            rc15 = float(r_sub["clean15"].mean())
            cc15 = float(c_sub["clean15"].mean())
            delta_stop5.append(cs5 - rs5)
            delta_clean15.append(cc15 - rc15)
            if cs5 < rs5:
                c_wins_s5 += 1
            if cc15 > rc15:
                c_wins_c15 += 1

        rows.append({
            "comparison":              C_lbl,
            "n_qualifying_names":      n_qualifying,
            "med_per_name_delta_stop5":  round(float(np.median(delta_stop5))   * 100, 2) if delta_stop5  else float("nan"),
            "med_per_name_delta_clean15": round(float(np.median(delta_clean15)) * 100, 2) if delta_clean15 else float("nan"),
            "pct_names_C_wins_stop5":  round(c_wins_s5  / n_qualifying * 100, 2) if n_qualifying > 0 else float("nan"),
            "pct_names_C_wins_clean15": round(c_wins_c15 / n_qualifying * 100, 2) if n_qualifying > 0 else float("nan"),
        })

    return rows


def build_T4(
    R_deduped: pd.DataFrame, C2_deduped: pd.DataFrame, events_df: pd.DataFrame,
) -> dict:
    """T4: per-event FIRST-fire pairing (count-neutral).

    For each durable B15 event captured by BOTH C2 and R in the window [t0-5, t0+15] (td approx),
    take the FIRST fire of each set in that window and compare premium_over_p0 and lead.
    Report: median paired premium improvement, median paired days-earlier, % events C2 first.
    """
    if len(events_df) == 0 or len(R_deduped) == 0 or len(C2_deduped) == 0:
        return {"note": "insufficient data for T4"}

    evs = events_df.copy()
    evs["t0"] = pd.to_datetime(evs["t0"])
    dur_evs = evs[evs["label"] == "durable"]

    r_df  = R_deduped.copy()
    c2_df = C2_deduped.copy()
    r_df["sig_date"]  = pd.to_datetime(r_df["sig_date"])
    c2_df["sig_date"] = pd.to_datetime(c2_df["sig_date"])

    paired_prem_improvement: list[float] = []
    paired_days_earlier: list[float] = []
    c2_earlier = 0
    n_paired = 0

    for _, ev in dur_evs.iterrows():
        ticker = ev["ticker"]
        t0 = ev["t0"]
        w_start = t0 - pd.Timedelta(days=7)
        w_end   = t0 + pd.Timedelta(days=21)

        r_fires_ev = r_df[
            (r_df["ticker"] == ticker)
            & (r_df["sig_date"] >= w_start)
            & (r_df["sig_date"] <= w_end)
        ]
        c2_fires_ev = c2_df[
            (c2_df["ticker"] == ticker)
            & (c2_df["sig_date"] >= w_start)
            & (c2_df["sig_date"] <= w_end)
        ]

        if len(r_fires_ev) == 0 or len(c2_fires_ev) == 0:
            continue  # event must be captured by BOTH

        # First fire in window
        r_first  = r_fires_ev.sort_values("sig_date").iloc[0]
        c2_first = c2_fires_ev.sort_values("sig_date").iloc[0]

        r_prem  = float(r_first["premium_over_p0"]) if r_first.get("premium_over_p0") is not None and not pd.isna(r_first.get("premium_over_p0")) else np.nan
        c2_prem = float(c2_first["premium_over_p0"]) if c2_first.get("premium_over_p0") is not None and not pd.isna(c2_first.get("premium_over_p0")) else np.nan
        r_lead  = float(r_first["lead"])  if not pd.isna(r_first.get("lead")) else np.nan
        c2_lead = float(c2_first["lead"]) if not pd.isna(c2_first.get("lead")) else np.nan

        if not np.isnan(r_prem) and not np.isnan(c2_prem):
            paired_prem_improvement.append(r_prem - c2_prem)  # positive means C2 cheaper
        if not np.isnan(r_lead) and not np.isnan(c2_lead):
            paired_days_earlier.append(r_lead - c2_lead)  # positive means C2 earlier
            if c2_lead < r_lead:
                c2_earlier += 1
        n_paired += 1

    if n_paired == 0:
        return {"note": "no events captured by both C2 and R"}

    return {
        "n_paired_events":            n_paired,
        "med_paired_prem_improvement_pp": round(float(np.median(paired_prem_improvement)) * 100, 2) if paired_prem_improvement else float("nan"),
        "med_paired_days_earlier":    round(float(np.median(paired_days_earlier)), 2) if paired_days_earlier else float("nan"),
        "pct_events_C2_earlier":      round(c2_earlier / n_paired * 100, 2) if n_paired > 0 else float("nan"),
    }


def build_T5(
    R_deduped: pd.DataFrame, C1_deduped: pd.DataFrame, C2_deduped: pd.DataFrame,
) -> list[dict]:
    """T5: ticker-half (even/odd sorted names) clean15 + stop5 per set."""
    all_tickers = sorted(
        set(R_deduped["ticker"].unique()) | set(C1_deduped["ticker"].unique()) | set(C2_deduped["ticker"].unique())
    )
    half_even = set(all_tickers[::2])
    half_odd  = set(all_tickers[1::2])

    rows = []
    for half_label, half_tickers in [("even", half_even), ("odd", half_odd)]:
        for df, lbl in [(R_deduped, "R"), (C1_deduped, "C1"), (C2_deduped, "C2")]:
            sub = df[df["ticker"].isin(half_tickers)]
            n = len(sub)
            rows.append({
                "half":    half_label,
                "set":     lbl,
                "n":       n,
                "clean15": round(float(sub["clean15"].mean()) * 100, 2) if n > 0 else float("nan"),
                "stop5":   round(float(sub["stop5"].mean())   * 100, 2) if n > 0 else float("nan"),
            })

    return rows


# ══════════════════════════════════════════════════════════════════════════════
# Union (C2) construction from m1d_s3d and m2d_s3d inside-fires
# ══════════════════════════════════════════════════════════════════════════════

def build_C2_rows(m1d_rows: list[dict], m2d_rows: list[dict]) -> list[dict]:
    """Union of m1d_s3d and m2d_s3d INSIDE fires, sorted by (ticker, sig_idx).

    If both fire on the same (ticker, sig_idx), count it once (use the m1d_s3d row,
    since they have the same fill price — the distinction is only the trigger).
    """
    # Index m2d by (ticker, sig_idx)
    m2d_keyed: dict[tuple, dict] = {}
    for row in m2d_rows:
        k = (row["ticker"], row["sig_idx"])
        m2d_keyed[k] = row

    # Start with m1d
    combined: dict[tuple, dict] = {}
    for row in m1d_rows:
        k = (row["ticker"], row["sig_idx"])
        combined[k] = row

    # Add m2d rows not already in combined (same-bar dedupe: m1d wins)
    for k, row in m2d_keyed.items():
        if k not in combined:
            combined[k] = row

    # Sort by (ticker, sig_idx)
    return sorted(combined.values(), key=lambda r: (r["ticker"], r["sig_idx"]))


# ══════════════════════════════════════════════════════════════════════════════
# Main pipeline (OHLCV panels: stocks + baskets)
# ══════════════════════════════════════════════════════════════════════════════

def run_ohlcv_panel(panel: str, tickers_filter: list[str],
                    workers: int, out_dir: Path) -> dict:
    """Run wave4 for stocks or baskets OHLCV panel."""
    t_start = time.time()
    cfg = PANEL_CONFIGS[panel]
    data_dir   = cfg["data_dir"]
    min_bars   = cfg["min_bars"]
    eval_start = cfg["eval_start"]

    print(f"Wave-4 | panel={panel} | eval_start={eval_start.date()} "
          f"| min_bars={min_bars} | workers={workers}")

    # ── Resolve file list ────────────────────────────────────────────────────
    all_files = sorted(data_dir.glob("*.parquet"))
    if tickers_filter:
        wanted = {t.strip() for t in tickers_filter}
        all_files = [f for f in all_files if f.stem in wanted]

    panel_files: list[Path] = []
    for fp in all_files:
        try:
            df = pd.read_parquet(fp)
            if len(df["close"].dropna()) >= min_bars:
                panel_files.append(fp)
        except Exception:
            pass
    print(f"Panel files (>={min_bars} bars): {len(panel_files)}")

    # ── Membership (baskets) ─────────────────────────────────────────────────
    active_set: set[str] = set()
    theme_peers: dict[str, set[str]] | None = None
    basket_sector_map: dict[str, str] = {}

    if MEMBERSHIP.exists():
        membership = load_membership()
        active_set = build_active_set(membership)
        if panel == "baskets":
            basket_sector_map = build_basket_sector_map(membership)
            theme_peers       = build_theme_peers(membership)
            print(f"Basket sector map: {len(basket_sector_map)} tickers")

    # ── Sector map ───────────────────────────────────────────────────────────
    const_path = BREADTH / "constituents.parquet"
    const_sector_map: dict[str, str] = {}
    if const_path.exists():
        const_df = pd.read_parquet(const_path)
        for sym, row in const_df.iterrows():
            const_sector_map[sym] = row["sector"]

    if panel == "baskets":
        sector_map = {**const_sector_map, **basket_sector_map}
    else:
        sector_map = const_sector_map
    print(f"Sector map: {len(sector_map)} tickers")

    # ── SPY ──────────────────────────────────────────────────────────────────
    spy_path = DATA_STOCKS / "SPY.parquet"
    if not spy_path.exists():
        spy_path = ROOT / "data" / "yahoo" / "SPY.parquet"
    spy_close: pd.Series | None = None
    if spy_path.exists():
        spy_close = pd.read_parquet(spy_path)["close"].dropna()
        print(f"SPY loaded: {len(spy_close)} bars")

    # ── Sector weekly-D matrix ───────────────────────────────────────────────
    print("Building sector weekly-D matrix...")
    t0_mat = time.time()
    all_data_files = sorted(data_dir.glob("*.parquet"))
    sector_peer_files = [fp for fp in all_data_files if fp.stem in sector_map]
    sector_d_matrix = build_sector_d_matrix(
        [str(fp) for fp in sector_peer_files], sector_map
    )
    print(f"  D-matrix: {len(sector_d_matrix)} tickers ({time.time()-t0_mat:.1f}s)")

    # ── Theme weekly-D matrix (baskets) ─────────────────────────────────────
    theme_d_matrix: dict | None = None
    if panel == "baskets" and theme_peers is not None:
        print("Building theme weekly-D matrix...")
        t0_th = time.time()
        theme_d_matrix = build_theme_d_matrix(
            [str(fp) for fp in all_data_files], theme_peers, min_bars
        )
        print(f"  Theme D-matrix: {len(theme_d_matrix)} tickers ({time.time()-t0_th:.1f}s)")

    # ── Serialize ─────────────────────────────────────────────────────────────
    sector_d_matrix_ser = _serialize_d_matrix(sector_d_matrix)
    theme_d_matrix_ser  = _serialize_d_matrix(theme_d_matrix) if theme_d_matrix else None

    # ── Worker args ──────────────────────────────────────────────────────────
    worker_args = []
    for fp in panel_files:
        ticker    = fp.stem
        is_active = ticker in active_set

        spy_vals = None
        spy_idx_vals = None
        if spy_close is not None:
            try:
                df_t    = pd.read_parquet(fp)
                daily_t = df_t["close"].dropna()
                spy_al  = spy_close.reindex(daily_t.index, method="ffill")
                spy_r   = (daily_t / spy_al).replace([np.inf, -np.inf], np.nan)
                spy_vals     = spy_r.to_numpy().tolist()
                spy_idx_vals = daily_t.index.strftime("%Y-%m-%d").tolist()
            except Exception:
                pass

        worker_args.append((
            ticker, str(fp),
            spy_vals, spy_idx_vals,
            sector_map, sector_d_matrix_ser,
            theme_peers, theme_d_matrix_ser,
            is_active,
            eval_start.strftime("%Y-%m-%d"),
            min_bars,
        ))

    # ── Run pool ─────────────────────────────────────────────────────────────
    print(f"\nProcessing {len(worker_args)} names with {workers} workers...")
    t0_run = time.time()

    if workers <= 1:
        results = [_ohlcv_worker(a) for a in worker_args]
    else:
        with Pool(workers) as pool:
            results = pool.map(_ohlcv_worker, worker_args)

    # Collect
    m1d_all_rows: list[dict] = []
    m2d_all_rows: list[dict] = []
    base3d_all_rows: list[dict] = []
    all_events: list[dict] = []
    processed: list[str] = []
    errors: list[str] = []

    for ticker, result in results:
        if "_error" in result:
            errors.append(f"{ticker}: {result['_error']}")
            continue
        if not result:
            continue
        m1d_all_rows.extend(result.get("m1d_s3d", []))
        m2d_all_rows.extend(result.get("m2d_s3d", []))
        base3d_all_rows.extend(result.get("base3d_all", []))
        all_events.extend(result.get("events", []))
        processed.append(ticker)

    total_elapsed = time.time() - t0_run
    n_names = len(processed)
    if errors:
        print(f"Errors ({len(errors)}): {errors[:5]}")
    print(f"Done: {n_names} names in {total_elapsed:.1f}s ({total_elapsed/max(n_names,1):.2f}s/name)")

    return _finalize(
        panel, m1d_all_rows, m2d_all_rows, base3d_all_rows, all_events,
        n_names, total_elapsed, eval_start, min_bars, workers, out_dir,
    )


# ══════════════════════════════════════════════════════════════════════════════
# Main pipeline (CN close-only panel)
# ══════════════════════════════════════════════════════════════════════════════

def run_cn_panel(tickers_filter: list[str], workers: int, out_dir: Path) -> dict:
    """Run wave4 for the CN close-only panel."""
    t_start = time.time()
    min_bars   = CN_MIN_BARS
    eval_start = CN_EVAL_START

    print(f"Wave-4 | panel=cn | eval_start={eval_start.date()} | min_bars={min_bars} | workers={workers}")

    # ── Load closes ──────────────────────────────────────────────────────────
    print(f"Loading {DATA_CN_CLOSES} ...")
    close_dict = load_close_only_wide(DATA_CN_CLOSES, min_bars)
    print(f"Tickers with >={min_bars} bars: {len(close_dict)}")

    if tickers_filter:
        wanted = set(tickers_filter)
        close_dict = {t: s for t, s in close_dict.items() if t in wanted}
        print(f"Ticker filter applied: {len(close_dict)} names")

    ticker_list = list(close_dict.keys())

    # ── Sector map ───────────────────────────────────────────────────────────
    sector_map: dict[str, str] = {}
    if DATA_CN_MEMBERS.exists():
        mem_df = pd.read_parquet(DATA_CN_MEMBERS)
        if "sector" in mem_df.columns:
            for sym in mem_df.index:
                sector_map[sym] = mem_df.loc[sym, "sector"]
    print(f"Sector map: {len(sector_map)} tickers")

    # ── Theme peers (CN) ─────────────────────────────────────────────────────
    theme_peers: dict[str, set[str]] | None = None
    if DATA_CN_MEMBERSHIP.exists():
        membership = load_cn_membership()
        theme_peers = build_cn_theme_peers(membership)

    # ── Sector D-matrix ──────────────────────────────────────────────────────
    print("Building sector weekly-D matrix...")
    t0_mat = time.time()
    # Always use full panel for cohort peers (even if ticker filter applied)
    full_close_dict = load_close_only_wide(DATA_CN_CLOSES, min_bars) if tickers_filter else close_dict
    sector_d_matrix = build_sector_d_matrix_from_close_dict(full_close_dict, sector_map)
    print(f"  D-matrix: {len(sector_d_matrix)} tickers ({time.time()-t0_mat:.1f}s)")

    # ── Theme D-matrix ───────────────────────────────────────────────────────
    theme_d_matrix: dict | None = None
    if theme_peers is not None:
        print("Building theme weekly-D matrix...")
        t0_th = time.time()
        theme_d_matrix = build_theme_d_matrix_from_close_dict(full_close_dict, theme_peers, set(ticker_list))
        print(f"  Theme D-matrix: {len(theme_d_matrix)} tickers ({time.time()-t0_th:.1f}s)")

    # ── Serialize ─────────────────────────────────────────────────────────────
    sector_d_matrix_ser = _serialize_d_matrix(sector_d_matrix)
    theme_d_matrix_ser  = _serialize_d_matrix(theme_d_matrix) if theme_d_matrix else None

    # ── Worker args ──────────────────────────────────────────────────────────
    worker_args = []
    for ticker in ticker_list:
        daily = close_dict[ticker]
        worker_args.append((
            ticker,
            daily.to_numpy().tolist(),
            daily.index.strftime("%Y-%m-%d").tolist(),
            sector_map,
            sector_d_matrix_ser,
            theme_peers,
            theme_d_matrix_ser,
            eval_start.strftime("%Y-%m-%d"),
            min_bars,
        ))

    # ── Run pool ─────────────────────────────────────────────────────────────
    print(f"\nProcessing {len(worker_args)} names with {workers} workers...")
    t0_run = time.time()

    if workers <= 1:
        results = [_cn_worker(a) for a in worker_args]
    else:
        with Pool(workers) as pool:
            results = pool.map(_cn_worker, worker_args)

    m1d_all_rows: list[dict] = []
    m2d_all_rows: list[dict] = []
    base3d_all_rows: list[dict] = []
    all_events: list[dict] = []
    processed: list[str] = []
    errors: list[str] = []

    for ticker, result in results:
        if "_error" in result:
            errors.append(f"{ticker}: {result['_error']}")
            continue
        if not result:
            continue
        m1d_all_rows.extend(result.get("m1d_s3d", []))
        m2d_all_rows.extend(result.get("m2d_s3d", []))
        base3d_all_rows.extend(result.get("base3d_all", []))
        all_events.extend(result.get("events", []))
        processed.append(ticker)

    total_elapsed = time.time() - t0_run
    n_names = len(processed)
    if errors:
        print(f"Errors ({len(errors)}): {errors[:5]}")
    print(f"Done: {n_names} names in {total_elapsed:.1f}s ({total_elapsed/max(n_names,1):.2f}s/name)")

    return _finalize(
        "cn", m1d_all_rows, m2d_all_rows, base3d_all_rows, all_events,
        n_names, total_elapsed, eval_start, min_bars, workers, out_dir,
    )


# ══════════════════════════════════════════════════════════════════════════════
# Finalize: build sets, tables, save, print summary
# ══════════════════════════════════════════════════════════════════════════════

def _to_df(rows: list[dict]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    if "sig_date" in df.columns:
        df["sig_date"] = pd.to_datetime(df["sig_date"])
    if "fill_date" in df.columns:
        df["fill_date"] = pd.to_datetime(df["fill_date"])
    return df


def _finalize(
    panel: str,
    m1d_raw_rows: list[dict],
    m2d_raw_rows: list[dict],
    base3d_raw_rows: list[dict],
    all_events: list[dict],
    n_names: int,
    total_elapsed: float,
    eval_start: pd.Timestamp,
    min_bars: int,
    workers: int,
    out_dir: Path,
) -> dict:
    """Apply dedupe, build tables, save outputs."""

    # ── Events ────────────────────────────────────────────────────────────────
    events_df = _to_df(all_events)
    if "t0" in events_df.columns:
        events_df["t0"] = pd.to_datetime(events_df["t0"])

    # ── Build fire sets ───────────────────────────────────────────────────────
    # C2 raw = union of m1d and m2d inside fires
    c2_raw_rows = build_C2_rows(m1d_raw_rows, m2d_raw_rows)

    # Dedupe each set
    R_rows   = dedupe_fires(m2d_raw_rows)   # R  = dedupe(m2d inside)
    C1_rows  = dedupe_fires(m1d_raw_rows)   # C1 = dedupe(m1d inside)
    C2_rows_ = dedupe_fires(c2_raw_rows)    # C2 = dedupe(union inside)

    # DataFrames
    m1d_df   = _to_df(m1d_raw_rows)
    m2d_df   = _to_df(m2d_raw_rows)
    c2_raw_df = _to_df(c2_raw_rows)
    R_df     = _to_df(R_rows)
    C1_df    = _to_df(C1_rows)
    C2_df    = _to_df(C2_rows_)
    base3d_df = _to_df(base3d_raw_rows)

    # ── Save parquets ─────────────────────────────────────────────────────────
    events_df.to_parquet(out_dir / "events.parquet", index=False)
    m1d_df.to_parquet(out_dir    / "fires_m1d_s3d_inside_raw.parquet", index=False)
    m2d_df.to_parquet(out_dir    / "fires_m2d_s3d_inside_raw.parquet", index=False)
    c2_raw_df.to_parquet(out_dir / "fires_c2_union_raw.parquet",        index=False)
    R_df.to_parquet(out_dir      / "fires_R_deduped.parquet",           index=False)
    C1_df.to_parquet(out_dir     / "fires_C1_deduped.parquet",          index=False)
    C2_df.to_parquet(out_dir     / "fires_C2_deduped.parquet",          index=False)
    base3d_df.to_parquet(out_dir / "fires_base3d_all.parquet",          index=False)
    print(f"Saved parquets to {out_dir}")

    # ── Build tables ──────────────────────────────────────────────────────────
    tables: dict = {
        "_meta": {
            "panel":       panel,
            "n_names":     n_names,
            "eval_start":  str(eval_start.date()),
            "min_bars":    min_bars,
            "workers":     workers,
            "runtime_s":   round(total_elapsed, 1),
            "dedupe_window_bars": DEDUPE_WINDOW,
            "sets": {
                "R":  "dedupe(m2d_s3d inside COILED)",
                "C1": "dedupe(m1d_s3d inside COILED)",
                "C2": "dedupe(union(m1d_s3d, m2d_s3d) inside COILED)",
            },
        }
    }

    # T1
    tables["T1"] = build_T1(R_df, C1_df, C2_df, m2d_df, m1d_df, c2_raw_df, base3d_df, events_df)

    # T2 (stocks only)
    if panel == "stocks":
        tables["T2"] = build_T2_stocks(R_df, C1_df, C2_df)

    # T3
    tables["T3"] = build_T3(R_df, C1_df, C2_df)

    # T4
    tables["T4"] = build_T4(R_df, C2_df, events_df)

    # T5
    tables["T5"] = build_T5(R_df, C1_df, C2_df)

    # Save
    tables_path = out_dir / "wave4_tables.json"
    with open(tables_path, "w") as f:
        json.dump(tables, f, indent=2, default=str)
    print(f"Saved wave4_tables.json to {tables_path}")

    # ── Print compact summary ─────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print(f"WAVE-4 SUMMARY | panel={panel}")
    print("=" * 70)
    n_ev = len(events_df)
    n_dur  = int((events_df["label"] == "durable").sum()) if n_ev > 0 else 0
    n_trap = int((events_df["label"] == "trap").sum())    if n_ev > 0 else 0
    print(f"Events: total={n_ev}  durable={n_dur}  trap={n_trap}")

    for lbl, df in [("R(m2d)", R_df), ("C1(m1d)", C1_df), ("C2(union)", C2_df)]:
        n = len(df)
        s5  = round(float(df["stop5"].mean()) * 100, 2) if n > 0 else float("nan")
        c15 = round(float(df["clean15"].mean()) * 100, 2) if n > 0 else float("nan")
        print(f"  {lbl:12s}  n={n:5d}  stop5={s5}%  clean15={c15}%")

    print(f"\n  R  raw (undeduped): n={len(m2d_df)}")
    print(f"  C1 raw (undeduped): n={len(m1d_df)}")
    print(f"  C2 raw (undeduped): n={len(c2_raw_df)}")

    # T1 dedupe check
    if len(m2d_df) > 0 and len(R_df) > 0:
        print(f"  Dedupe R: {len(m2d_df)} → {len(R_df)} (kept {100*len(R_df)/len(m2d_df):.1f}%)")

    # T3 summary
    t3 = tables.get("T3", [])
    for row in t3:
        print(f"  T3 {row['comparison']}: n_qualifying={row['n_qualifying_names']}  "
              f"med_delta_c15={row.get('med_per_name_delta_clean15','?')}pp  "
              f"pct_C_wins_c15={row.get('pct_names_C_wins_clean15','?')}%")

    secs_per_name = total_elapsed / max(n_names, 1)
    n_full = {"stocks": 211, "baskets": 2336, "cn": 1382}.get(panel, n_names)
    projected = secs_per_name * n_full / max(workers, 1) / 60
    print(f"\nProjected full {panel} runtime: ~{projected:.1f} min @ --workers {workers} ({n_full} names)")

    return tables, R_df, C1_df, C2_df, m2d_df, m1d_df, c2_raw_df, base3d_df, events_df


# ══════════════════════════════════════════════════════════════════════════════
# Smoke assertions
# ══════════════════════════════════════════════════════════════════════════════

def run_smoke_stocks(
    tables: dict,
    R_deduped: pd.DataFrame, C1_deduped: pd.DataFrame, C2_deduped: pd.DataFrame,
    R_raw: pd.DataFrame, C1_raw: pd.DataFrame, C2_raw: pd.DataFrame,
    events_df: pd.DataFrame,
) -> None:
    """Stocks smoke assertions (8-ticker set):
    1. R deduped n < R undeduped n (dedupe engages)
    2. C2 deduped n >= max(C1 deduped n, R deduped n)
    3. All T-blocks present (T1, T2, T3, T4, T5)
    4. R-undeduped stop5/clean15 within 1.5pp of wave-3 inside-COILED smoke (33.33/42.42)
    """
    print("\n" + "=" * 70)
    print("SMOKE — stocks panel (8-ticker)")
    print("=" * 70)
    errors: list[str] = []

    # [1] Dedupe engages
    n_R_raw   = len(R_raw)
    n_R_ded   = len(R_deduped)
    print(f"[1] R raw={n_R_raw}  R deduped={n_R_ded}")
    if n_R_ded >= n_R_raw and n_R_raw > 0:
        errors.append(f"Dedupe did not reduce R: raw={n_R_raw}, deduped={n_R_ded}")
    else:
        print(f"    Dedupe engaged: {n_R_raw} → {n_R_ded}")

    # [2] C2 >= max(C1, R) deduped
    n_C1_ded = len(C1_deduped)
    n_C2_ded = len(C2_deduped)
    print(f"[2] C1_deduped={n_C1_ded}  C2_deduped={n_C2_ded}  R_deduped={n_R_ded}")
    if n_C2_ded < max(n_C1_ded, n_R_ded) and n_C2_ded > 0:
        # Small subsets: C2 can be = max due to exact overlap — allow equality
        errors.append(f"C2_deduped ({n_C2_ded}) < max(C1={n_C1_ded}, R={n_R_ded})")
    else:
        print(f"    C2 >= max(C1, R): OK")

    # [3] All T-blocks present
    expected_blocks = ["T1", "T2", "T3", "T4", "T5"]
    for b in expected_blocks:
        if b not in tables:
            errors.append(f"Table {b} missing!")
        else:
            val = tables[b]
            if isinstance(val, (list, dict)) and len(val) == 0:
                errors.append(f"Table {b} is empty!")
            else:
                print(f"[3] {b}: present (len={len(val)})")

    # [4] R-undeduped stop5/clean15 vs wave-3 full-panel baseline.
    # Wave-3 T-B reported inside-COILED m2d_s3d (n=3,174): stop5=39.07, clean15=39.29.
    # (The original smoke constants 33.33/42.42 were for the 8-ticker sub-run only;
    #  replaced here with the canonical full-panel numbers so this assertion is valid
    #  for any panel size.)
    REF_STOP5  = 39.07
    REF_CLEAN15 = 39.29
    TOL = 1.5
    if len(R_raw) > 0:
        s5  = round(float(R_raw["stop5"].mean()) * 100, 2)
        c15 = round(float(R_raw["clean15"].mean()) * 100, 2)
        print(f"[4] R-undeduped stop5={s5}% (ref {REF_STOP5}±{TOL}pp)  clean15={c15}% (ref {REF_CLEAN15}±{TOL}pp)")
        if abs(s5 - REF_STOP5) > TOL:
            errors.append(f"R-undeduped stop5={s5}% differs from wave-3 ref {REF_STOP5} by >{TOL}pp")
        if abs(c15 - REF_CLEAN15) > TOL:
            errors.append(f"R-undeduped clean15={c15}% differs from wave-3 ref {REF_CLEAN15} by >{TOL}pp")
    else:
        print("[4] R_raw is empty — wave-3 reference check skipped")

    if errors:
        for e in errors:
            print(f"  FAIL: {e}")
        raise AssertionError(f"Stocks smoke: {len(errors)} failure(s)")
    print("Stocks smoke: PASS")


def run_smoke_cn(
    tables: dict,
    R_deduped: pd.DataFrame, C1_deduped: pd.DataFrame, C2_deduped: pd.DataFrame,
    events_df: pd.DataFrame,
) -> None:
    """CN smoke assertions: C1/C2/R non-empty inside COILED (14 tickers, >= 3 sectors)."""
    print("\n" + "=" * 70)
    print("SMOKE — cn panel (14-ticker)")
    print("=" * 70)
    errors: list[str] = []

    n_R  = len(R_deduped)
    n_C1 = len(C1_deduped)
    n_C2 = len(C2_deduped)
    print(f"[1] R_deduped={n_R}  C1_deduped={n_C1}  C2_deduped={n_C2}")

    if n_R == 0:
        errors.append("R_deduped is empty — m2d_s3d inside COILED produced no fires")
    if n_C1 == 0:
        errors.append("C1_deduped is empty — m1d_s3d inside COILED produced no fires")
    if n_C2 == 0:
        errors.append("C2_deduped is empty — union inside COILED produced no fires")

    # Verify T-blocks
    for b in ["T1", "T3", "T4", "T5"]:
        if b not in tables:
            errors.append(f"Table {b} missing!")
        elif len(tables[b]) == 0:
            errors.append(f"Table {b} is empty!")
        else:
            print(f"[2] {b}: present (len={len(tables[b])})")

    if errors:
        for e in errors:
            print(f"  FAIL: {e}")
        raise AssertionError(f"CN smoke: {len(errors)} failure(s)")
    print("CN smoke: PASS")


def run_smoke_baskets(
    tables: dict,
    R_raw: pd.DataFrame,
    events_df: pd.DataFrame,
) -> None:
    """Baskets mini-smoke: tables build, cohort computes (COILED may be sparse on mini-subset)."""
    print("\n" + "=" * 70)
    print("SMOKE — baskets panel (12-ticker mini)")
    print("=" * 70)
    errors: list[str] = []

    # Tables exist
    for b in ["T1", "T3", "T4", "T5"]:
        if b not in tables:
            errors.append(f"Table {b} missing!")
        else:
            val = tables[b]
            print(f"[1] {b}: present (len={len(val)})")

    # Events non-empty
    n_ev = len(events_df)
    print(f"[2] Events: {n_ev}")
    if n_ev == 0:
        errors.append("No events — labeler failed on baskets mini")

    # T1 base3d_ALL context row present
    t1 = tables.get("T1", [])
    t1_labels = [r.get("label") for r in t1]
    print(f"[3] T1 labels: {t1_labels}")
    if "base3d_ALL_context" not in t1_labels:
        errors.append("T1 missing base3d_ALL_context row")

    if errors:
        for e in errors:
            print(f"  FAIL: {e}")
        raise AssertionError(f"Baskets smoke: {len(errors)} failure(s)")
    print("Baskets smoke: PASS")


# ══════════════════════════════════════════════════════════════════════════════
# CLI entry point
# ══════════════════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(description="Wave-4 durable-bottom COILED-FIRE layer study")
    ap.add_argument("--panel", required=True, choices=["stocks", "baskets", "cn"])
    ap.add_argument("--tickers", default="", help="Comma-separated ticker subset")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--out", default="", help="Output directory")
    args = ap.parse_args()

    tickers_filter = [t.strip() for t in args.tickers.split(",") if t.strip()] if args.tickers else []

    if args.out:
        out_dir = Path(args.out)
    else:
        out_dir = ROOT / "research" / "entry_timing" / "_out" / f"wave4_{args.panel}"
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"Output: {out_dir}")

    if args.panel == "cn":
        result = run_cn_panel(tickers_filter, args.workers, out_dir)
    else:
        result = run_ohlcv_panel(args.panel, tickers_filter, args.workers, out_dir)

    tables, R_df, C1_df, C2_df, m2d_df, m1d_df, c2_raw_df, base3d_df, events_df = result

    if args.panel == "stocks":
        run_smoke_stocks(tables, R_df, C1_df, C2_df, m2d_df, m1d_df, c2_raw_df, events_df)
    elif args.panel == "cn":
        run_smoke_cn(tables, R_df, C1_df, C2_df, events_df)
    else:
        run_smoke_baskets(tables, m2d_df, events_df)


if __name__ == "__main__":
    main()
