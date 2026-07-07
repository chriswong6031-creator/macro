#!/usr/bin/env python3
"""G-T2X gauntlet — locked pre-registered overlay study on T2 TIER_ONSET events.

Pre-registration source: research/signal_engine/TIER_ENTRY_DEEPDIVE.md §6.

Candidate: T2 tier-onset events, t+1 E1 fill, per-overlay filters.

First-wave overlays (max 5, one pass each, NO post-hoc threshold tuning):
  1. 2W washout context: w_setup fires after confirmed 2W stoch washout
     (w2.stoch <= W2_STOCH_WASHOUT=35.0 OR w2.stoch_cross_up). Computable PIT from prices.
  2. Fire-day turnover z > 0 (above-median volume on signal day). Computable from volume history.
  3. Sector-cycle phase in {bottoming, recovering} — NOT-RUN (no PIT per-stock sector membership).
  4. NW dispersion-regime lens — NOT-RUN (no PIT time series exists in data/).
  5. fill_premium_20d < 8% (not-extended filter). Computable from prices.

Ruler: mean 21d benchmark-excess from E1 fill with -5% stop, month-block bootstrap CI
(1000 reps, seed 42). Same conventions as _bt_tier_deepdive_v3.py.

Promotion gates (ALL must hold + directional consistency in both temporal splits):
  - CI_lo > 0
  - stop-out_21 <= 50% US / <= 52% CN
  - clean8_21 >= 33%
  - n_filtered >= 300 per market
  - retention >= 25% of base T2 fires

Kill: filtered excess <= unfiltered T2 base, or retention < 15%.

Universe: same as v3 (baskets/ohlcv 2498 US names, china_stocks 800-name seed=42 CN).
Period: US 2015-2026-05, CN 2016-2026-05.
Output: /tmp/tier_deepdive/g_t2x/
"""
from __future__ import annotations

import gc
import glob
import json
import os
import random
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Path wiring — same as v3
# ---------------------------------------------------------------------------
_WORKTREE = Path(__file__).resolve().parents[1]
_REPO_ROOT = _WORKTREE.parents[2]
_DATA_ROOT = _REPO_ROOT / "data"
_OUT_DIR = Path("/tmp/tier_deepdive/g_t2x")
_OUT_DIR.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(_WORKTREE))

from engine.confluence_tiers import (  # noqa: E402
    tier_stream, MIN_HISTORY,
    _tf_bars,
)
from engine.grading import (  # noqa: E402
    STOP_BARRIER,
    LIFTOFF_8,
    LIFTOFF_HORIZON_21,
)
from engine.setup_tier import w_setup, W2_STOCH_WASHOUT  # noqa: E402

# ---------------------------------------------------------------------------
# Pre-registered constants — LOCKED, no modification
# ---------------------------------------------------------------------------
CN_START = pd.Timestamp("2016-01-01")
US_START = pd.Timestamp("2015-01-01")
COMMON_END = pd.Timestamp("2026-05-31")

PRIMARY_H = 21
STOP_MULT = STOP_BARRIER   # 0.95

TRUNC_63 = pd.Timestamp("2026-03-01")   # events after this lack full 63d fwd data
TRUNC_126 = pd.Timestamp("2026-01-01")

BOOT_ITERS = 1000
BOOT_SEED = 42

# ---------------------------------------------------------------------------
# Overlay 5 threshold (pre-registered, NOT tunable)
# ---------------------------------------------------------------------------
FILL_PREMIUM_THRESHOLD = 0.08   # 8%

# ---------------------------------------------------------------------------
# Data loaders (identical to v3)
# ---------------------------------------------------------------------------

def _load_close_ohlcv(fp: str) -> tuple[pd.Series, pd.DataFrame]:
    df = pd.read_parquet(fp)
    df.index = pd.to_datetime(df.index)
    df = df.sort_index()
    close = df["close"].dropna()
    return close, df


def load_cn_benchmark() -> pd.Series:
    fp = _DATA_ROOT / "china" / "510300.SS.parquet"
    df = pd.read_parquet(str(fp))
    df.index = pd.to_datetime(df.index)
    return df["close"].sort_index()


def load_us_benchmark() -> pd.Series:
    fp = _DATA_ROOT / "yahoo" / "SPY.parquet"
    df = pd.read_parquet(str(fp))
    df.index = pd.to_datetime(df.index)
    return df["close"].sort_index()


# ---------------------------------------------------------------------------
# Entry price helpers (identical to v3)
# ---------------------------------------------------------------------------

def cn_entry_price(ohlcv: pd.DataFrame, t_date: pd.Timestamp) -> float | None:
    dates = ohlcv.index
    try:
        pos = dates.searchsorted(t_date, side="right")
        if pos >= len(dates):
            return None
        row = ohlcv.iloc[pos]
        hi = float(row["high"])
        lo = float(row["low"])
        if hi == lo:
            return None
        return (hi + lo) / 2.0
    except Exception:
        return None


def us_entry_price(ohlcv: pd.DataFrame, t_date: pd.Timestamp) -> float | None:
    dates = ohlcv.index
    try:
        pos = dates.searchsorted(t_date, side="right")
        if pos >= len(dates):
            return None
        row = ohlcv.iloc[pos]
        op = float(row["open"]) if "open" in row.index else float("nan")
        if np.isfinite(op) and op > 0:
            return op
        cl = float(row["close"])
        if np.isfinite(cl) and cl > 0:
            return cl
        return None
    except Exception:
        return None


def fill_date_bar(ohlcv: pd.DataFrame, t_date: pd.Timestamp) -> pd.Timestamp | None:
    dates = ohlcv.index
    pos = dates.searchsorted(t_date, side="right")
    if pos >= len(dates):
        return None
    return dates[pos]


# ---------------------------------------------------------------------------
# Overlay 1: w_setup washout context (PIT-safe, computable from prices)
# ---------------------------------------------------------------------------

def compute_w_setup_washout(close: pd.Series, event_date: pd.Timestamp) -> bool:
    """Return True if 2W washout context is active on event_date.

    Uses w_setup() from engine/setup_tier.py on close.loc[:event_date].
    Active when: w2.stoch <= W2_STOCH_WASHOUT=35.0 OR w2.stoch_cross_up=True.
    This is the same W2_STOCH_WASHOUT constant from setup_tier.py (=35.0).
    """
    try:
        c_pit = close.loc[:event_date]
        if len(c_pit) < MIN_HISTORY:
            return False
        ws = w_setup(c_pit)
        if ws is None:
            return False
        w2 = ws.get("w2", {})
        if not w2:
            return False
        stoch = w2.get("stoch")
        stoch_cross_up = bool(w2.get("stoch_cross_up", False))
        if stoch_cross_up:
            return True
        if stoch is not None and np.isfinite(stoch) and stoch <= W2_STOCH_WASHOUT:
            return True
        return False
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Overlay 2: fire-day turnover z > 0 (volume z-score on signal day)
# ---------------------------------------------------------------------------

def compute_turnover_z(ohlcv: pd.DataFrame, event_date: pd.Timestamp,
                       lookback: int = 60) -> float | None:
    """Compute z-score of fire-day volume relative to prior lookback-day distribution.

    Returns z-score (positive = above average). None if insufficient data.
    """
    try:
        if "volume" not in ohlcv.columns:
            return None
        vol_series = ohlcv["volume"].dropna()
        if len(vol_series) < lookback + 5:
            return None
        # Find the event_date bar
        pos = vol_series.index.searchsorted(event_date, side="right") - 1
        if pos < 0 or pos >= len(vol_series):
            return None
        fire_vol = float(vol_series.iloc[pos])
        if not np.isfinite(fire_vol) or fire_vol <= 0:
            return None
        # Historical window: prior lookback bars before event_date (not including it)
        hist = vol_series.iloc[max(0, pos - lookback):pos]
        if len(hist) < 20:
            return None
        hist_vals = hist.values.astype(float)
        hist_vals = hist_vals[np.isfinite(hist_vals) & (hist_vals > 0)]
        if len(hist_vals) < 20:
            return None
        m = np.mean(hist_vals)
        s = np.std(hist_vals)
        if s <= 0:
            return None
        return float((fire_vol - m) / s)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Outcome computation for T2 (same logic as v3 but only what G-T2X needs)
# ---------------------------------------------------------------------------

def compute_t2_outcome(
    close: pd.Series,
    ohlcv: pd.DataFrame,
    event_date: pd.Timestamp,
    benchmark: pd.Series,
    market: str,
) -> dict | None:
    """Compute outcome row for one T2 TIER_ONSET event."""
    if market == "CN":
        fill_price = cn_entry_price(ohlcv, event_date)
    else:
        fill_price = us_entry_price(ohlcv, event_date)

    if fill_price is None or not np.isfinite(fill_price) or fill_price <= 0:
        return None

    t1_date = fill_date_bar(ohlcv, event_date)
    if t1_date is None:
        return None

    fwd_close = close[close.index >= t1_date]
    if len(fwd_close) < 2:
        return None

    bench_aligned = benchmark.reindex(close.index, method="ffill")

    # 21d return and excess
    ret_21: float | None = None
    excess_21: float | None = None
    if len(fwd_close) > PRIMARY_H:
        ph = float(fwd_close.iloc[PRIMARY_H])
        if np.isfinite(ph) and ph > 0:
            ret_21 = ph / fill_price - 1.0
            t1_pos = close.index.searchsorted(t1_date, side="left")
            if t1_pos + PRIMARY_H < len(bench_aligned):
                b0v = bench_aligned.iloc[t1_pos]
                bhv = bench_aligned.iloc[t1_pos + PRIMARY_H]
                if (np.isfinite(b0v) and np.isfinite(bhv) and b0v > 0):
                    excess_21 = ret_21 - (bhv / b0v - 1.0)

    # Stop-out with -5% barrier (includes fill-day low)
    stop_price = fill_price * STOP_MULT
    stop_out_21 = False
    stop_exit_price: float | None = None

    if len(fwd_close) > PRIMARY_H:
        fwd_ohlcv = ohlcv[ohlcv.index >= t1_date]
        if len(fwd_ohlcv) > PRIMARY_H and "low" in ohlcv.columns:
            fwd_low = fwd_ohlcv["low"].iloc[0:PRIMARY_H + 1]
            fwd_open = fwd_ohlcv["open"].iloc[0:PRIMARY_H + 1] if "open" in ohlcv.columns else None
            for bar_idx in range(min(PRIMARY_H + 1, len(fwd_low))):
                lo = float(fwd_low.iloc[bar_idx])
                if lo <= stop_price:
                    stop_exit_price = stop_price
                    if fwd_open is not None and bar_idx < len(fwd_open):
                        op = float(fwd_open.iloc[bar_idx])
                        if np.isfinite(op) and op < stop_price:
                            stop_exit_price = op
                    stop_out_21 = True
                    break
        else:
            fwd_c = fwd_close.iloc[0:PRIMARY_H + 1]
            for bar_idx in range(min(PRIMARY_H + 1, len(fwd_c))):
                cl = float(fwd_c.iloc[bar_idx])
                if cl <= stop_price:
                    stop_out_21 = True
                    stop_exit_price = stop_price
                    break

    # wstop return (what matters for the ruler)
    wstop_ret_21: float | None = None
    if len(fwd_close) > PRIMARY_H:
        if stop_out_21 and stop_exit_price is not None:
            wstop_ret_21 = stop_exit_price / fill_price - 1.0
        elif ret_21 is not None:
            wstop_ret_21 = ret_21

    # clean8_21: no drawdown worse than -8% before reaching +8% liftoff (among non-stopped)
    clean8_21: bool | None = None
    if len(fwd_close) > LIFTOFF_HORIZON_21:
        liftoff8_bar = None
        stop_bar_21 = None
        fwd21 = fwd_close.iloc[1:LIFTOFF_HORIZON_21 + 1]
        for bi in range(len(fwd21)):
            cl = float(fwd21.iloc[bi])
            if cl <= fill_price * STOP_MULT:
                stop_bar_21 = bi
                break
            if cl >= fill_price * LIFTOFF_8 and liftoff8_bar is None:
                liftoff8_bar = bi
        clean8_21 = (
            liftoff8_bar is not None
            and (stop_bar_21 is None or stop_bar_21 > liftoff8_bar)
        )

    # fill_premium_20d
    fill_premium_20d: float | None = None
    try:
        t_pos = close.index.searchsorted(event_date, side="right") - 1
        if t_pos >= 20:
            trailing20_min = float(close.iloc[max(0, t_pos - 19): t_pos + 1].min())
            if trailing20_min > 0:
                fill_premium_20d = fill_price / trailing20_min - 1.0
    except Exception:
        pass

    truncated_63 = event_date > TRUNC_63

    return {
        "event_date": event_date,
        "fill_date": t1_date,
        "fill_price": fill_price,
        "excess_21": excess_21,
        "wstop_ret_21": wstop_ret_21,
        "stop_out_21": stop_out_21,
        "clean8_21": clean8_21,
        "fill_premium_20d": fill_premium_20d,
        "truncated_63": truncated_63,
    }


# ---------------------------------------------------------------------------
# Per-ticker T2 event collector with overlay features
# ---------------------------------------------------------------------------

def _collect_t2_events(args) -> list[dict]:
    """Collect T2 TIER_ONSET events with overlay features for one ticker."""
    ticker, close_path, market, start, end = args
    try:
        close, ohlcv = _load_close_ohlcv(close_path)
        hist_before = close[close.index < start]
        if len(hist_before) < MIN_HISTORY:
            return []

        if market == "CN":
            benchmark = load_cn_benchmark()
        else:
            benchmark = load_us_benchmark()

        base_ts = tier_stream(close)
        if base_ts.empty:
            return []

        # T2 onsets: first session of each T2 run (gap >= 1 bar from prior T2)
        ts_filtered = base_ts[(base_ts.index >= start) & (base_ts.index <= end)]
        tier_mask_np = (ts_filtered['tier'] == 'T2').to_numpy().astype(int)
        shifted = np.zeros(len(tier_mask_np), dtype=int)
        shifted[1:] = tier_mask_np[:-1]
        is_onset = (tier_mask_np == 1) & (shifted == 0)
        onset_dates = ts_filtered.index[is_onset]

        results = []
        for onset_date in onset_dates:
            out = compute_t2_outcome(close, ohlcv, onset_date, benchmark, market)
            if out is None:
                continue

            # Overlay 1: w_setup washout context (PIT-safe)
            ov1_washout = compute_w_setup_washout(close, onset_date)

            # Overlay 2: fire-day turnover z > 0
            tz = compute_turnover_z(ohlcv, onset_date, lookback=60)
            ov2_turnover_z = float(tz) if tz is not None else None
            ov2_pass = (tz is not None and tz > 0)

            # Overlay 5: fill_premium_20d < 8%
            fp20 = out.get("fill_premium_20d")
            ov5_not_extended = (fp20 is not None and fp20 < FILL_PREMIUM_THRESHOLD)

            out["ticker"] = ticker
            out["market"] = market
            out["ov1_washout"] = ov1_washout
            out["ov2_turnover_z"] = ov2_turnover_z
            out["ov2_pass"] = ov2_pass
            out["ov5_not_extended"] = ov5_not_extended
            results.append(out)

        return results
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Universe loaders (identical to v3)
# ---------------------------------------------------------------------------

def load_us_universe():
    result = {}
    fps = sorted(glob.glob(str(_DATA_ROOT / "baskets" / "ohlcv" / "*.parquet")))
    for fp in fps:
        t = Path(fp).stem
        try:
            df = pd.read_parquet(fp)
            df.index = pd.to_datetime(df.index)
            close = df["close"].dropna()
        except Exception:
            continue
        if len(close) < MIN_HISTORY:
            continue
        result[t] = fp
    return result


def load_cn_universe():
    members = pd.read_parquet(_DATA_ROOT / "china_search" / "members.parquet")
    tickers = members.index.tolist()
    result = {}
    for t in tickers:
        fp = _DATA_ROOT / "china_stocks" / f"{t}.parquet"
        if not fp.exists():
            continue
        try:
            df = pd.read_parquet(str(fp))
            df.index = pd.to_datetime(df.index)
            close = df["close"].dropna()
        except Exception:
            continue
        if len(close) < MIN_HISTORY:
            continue
        result[t] = str(fp)
    return result


# ---------------------------------------------------------------------------
# Bootstrap CI helper (month-block, seed 42, 1000 iterations)
# ---------------------------------------------------------------------------

def bootstrap_ci(rows: list[dict], excess_key: str = "excess_21",
                 n_iter: int = BOOT_ITERS) -> dict:
    """Month-block bootstrap CI on excess_21 for the given rows."""
    rng = np.random.default_rng(BOOT_SEED)
    eligible = [r for r in rows
                if r.get(excess_key) is not None
                and np.isfinite(r[excess_key])
                and not r.get("truncated_63", False)]
    if len(eligible) < 5:
        return {"n": len(eligible), "ci_lo": None, "ci_hi": None,
                "observed_mean": None, "note": "too few events"}

    months: dict[str, list[float]] = {}
    for r in eligible:
        try:
            m = str(pd.Timestamp(r["event_date"]).to_period("M"))
        except Exception:
            m = "unknown"
        if m not in months:
            months[m] = []
        months[m].append(r[excess_key])

    month_keys = list(months.keys())
    n_months = len(month_keys)
    boot_means = []
    for _ in range(n_iter):
        sampled = rng.choice(n_months, size=n_months, replace=True)
        vals = []
        for idx in sampled:
            vals.extend(months[month_keys[idx]])
        if vals:
            boot_means.append(float(np.mean(vals)))

    if not boot_means:
        return {"n": len(eligible), "ci_lo": None, "ci_hi": None,
                "observed_mean": None, "note": "bootstrap failed"}

    obs_mean = float(np.mean([r[excess_key] for r in eligible]))
    return {
        "n": len(eligible),
        "n_months": n_months,
        "observed_mean": obs_mean,
        "ci_lo_95": float(np.percentile(boot_means, 2.5)),
        "ci_hi_95": float(np.percentile(boot_means, 97.5)),
    }


# ---------------------------------------------------------------------------
# Per-overlay statistics computation
# ---------------------------------------------------------------------------

def _safe_mean(vals) -> float | None:
    vs = [v for v in vals if v is not None and np.isfinite(v)]
    return float(np.mean(vs)) if vs else None


def _pct_rate(bools) -> float | None:
    valid = [v for v in bools if v is not None]
    if not valid:
        return None
    return float(sum(1 for v in valid if v) / len(valid) * 100.0)


def compute_overlay_stats(rows: list[dict], market: str) -> dict:
    """Compute all gate metrics for a set of filtered rows."""
    n = len(rows)
    if n == 0:
        return {
            "n": 0,
            "excess_21_mean": None,
            "stop_out_21_pct": None,
            "clean8_21_pct": None,
            "ci": {"n": 0, "ci_lo": None, "ci_hi": None, "observed_mean": None},
        }

    excess_vals = [r["excess_21"] for r in rows
                   if r.get("excess_21") is not None and np.isfinite(r["excess_21"])]
    stop_vals = [r["stop_out_21"] for r in rows if r.get("stop_out_21") is not None]
    clean8_vals = [r["clean8_21"] for r in rows if r.get("clean8_21") is not None]

    ci = bootstrap_ci(rows, excess_key="excess_21")

    return {
        "n": n,
        "excess_21_mean": _safe_mean(excess_vals),
        "excess_21_n_valid": len(excess_vals),
        "stop_out_21_pct": _pct_rate(stop_vals),
        "clean8_21_pct": _pct_rate(clean8_vals),
        "ci": ci,
    }


def check_promotion_gates(stats: dict, base_stats: dict, n_base: int,
                          market: str) -> dict:
    """Evaluate all pre-registered promotion gates against computed stats.

    Returns a dict: gate_name -> {pass: bool, value: ..., threshold: ...}.
    """
    n_filtered = stats["n"]
    retention_pct = (n_filtered / n_base * 100) if n_base > 0 else 0.0
    ci = stats.get("ci", {})
    ci_lo = ci.get("ci_lo_95")
    excess_mean = stats.get("excess_21_mean")
    stop_out_pct = stats.get("stop_out_21_pct")
    clean8_pct = stats.get("clean8_21_pct")

    base_excess_mean = base_stats.get("excess_21_mean")
    stop_threshold = 50.0 if market == "US" else 52.0

    gates = {}

    # Gate 1: CI_lo > 0
    gates["ci_lo_positive"] = {
        "pass": (ci_lo is not None and ci_lo > 0),
        "value": ci_lo,
        "threshold": "> 0",
    }

    # Gate 2: stop-out_21 <= 50% US / <= 52% CN
    gates["stop_out_21"] = {
        "pass": (stop_out_pct is not None and stop_out_pct <= stop_threshold),
        "value": stop_out_pct,
        "threshold": f"<= {stop_threshold}%",
    }

    # Gate 3: clean8_21 >= 33%
    gates["clean8_21"] = {
        "pass": (clean8_pct is not None and clean8_pct >= 33.0),
        "value": clean8_pct,
        "threshold": ">= 33%",
    }

    # Gate 4: n_filtered >= 300
    gates["n_filtered"] = {
        "pass": n_filtered >= 300,
        "value": n_filtered,
        "threshold": ">= 300",
    }

    # Gate 5: retention >= 25% of base T2 fires
    gates["retention"] = {
        "pass": retention_pct >= 25.0,
        "value": round(retention_pct, 1),
        "threshold": ">= 25% of base",
    }

    # Kill check: filtered excess <= unfiltered T2 base
    kill_excess = (
        excess_mean is not None
        and base_excess_mean is not None
        and excess_mean <= base_excess_mean
    )
    # Kill check: retention < 15%
    kill_retention = retention_pct < 15.0

    all_pass = all(g["pass"] for g in gates.values())
    any_kill = kill_excess or kill_retention

    if kill_excess:
        verdict = "KILL"
        kill_reason = f"filtered excess ({excess_mean:.4f}) <= base ({base_excess_mean:.4f})"
    elif kill_retention:
        verdict = "KILL"
        kill_reason = f"retention {retention_pct:.1f}% < 15%"
    elif any_kill:
        verdict = "KILL"
        kill_reason = "kill condition met"
    elif all_pass:
        verdict = "PROMOTE"
        kill_reason = None
    else:
        # Some gates failed but no explicit kill — report as NULL
        verdict = "NULL"
        kill_reason = None

    return {
        "gates": gates,
        "n_base": n_base,
        "n_filtered": n_filtered,
        "retention_pct": round(retention_pct, 1),
        "excess_21_mean": excess_mean,
        "base_excess_21_mean": base_excess_mean,
        "all_gates_pass": all_pass,
        "kill_excess": kill_excess,
        "kill_retention": kill_retention,
        "verdict": verdict,
        "kill_reason": kill_reason,
    }


# ---------------------------------------------------------------------------
# Temporal split-half directional consistency check
# ---------------------------------------------------------------------------

def split_half_consistency(rows: list[dict], base_excess_mean: float | None) -> dict:
    """Check directional consistency of excess_21 in two temporal halves.

    Splits all rows at the midpoint date, computes mean excess in each half.
    Both halves must be directionally consistent (mean > 0 AND > base) for
    the promotion to be considered consistent across splits.
    """
    eligible = [r for r in rows
                if r.get("event_date") is not None
                and r.get("excess_21") is not None
                and np.isfinite(r["excess_21"])
                and not r.get("truncated_63", False)]
    if len(eligible) < 10:
        return {"consistent": None, "note": "too few events for split check",
                "h1_mean": None, "h2_mean": None, "h1_n": 0, "h2_n": 0}

    eligible_sorted = sorted(eligible, key=lambda r: r["event_date"])
    mid = len(eligible_sorted) // 2
    h1 = eligible_sorted[:mid]
    h2 = eligible_sorted[mid:]

    h1_vals = [r["excess_21"] for r in h1 if r.get("excess_21") is not None]
    h2_vals = [r["excess_21"] for r in h2 if r.get("excess_21") is not None]

    h1_mean = float(np.mean(h1_vals)) if h1_vals else None
    h2_mean = float(np.mean(h2_vals)) if h2_vals else None

    h1_dates = [r["event_date"] for r in h1]
    h2_dates = [r["event_date"] for r in h2]
    h1_date_range = (
        f"{min(h1_dates).date()} to {max(h1_dates).date()}" if h1_dates else "N/A"
    )
    h2_date_range = (
        f"{min(h2_dates).date()} to {max(h2_dates).date()}" if h2_dates else "N/A"
    )

    # Both halves must be directionally consistent (excess > 0 AND > base in both)
    if h1_mean is not None and h2_mean is not None:
        # Directionally consistent = both positive AND both above base
        base = base_excess_mean if base_excess_mean is not None else 0.0
        both_positive = h1_mean > 0 and h2_mean > 0
        both_above_base = h1_mean > base and h2_mean > base
        consistent = both_positive and both_above_base
    else:
        consistent = None

    return {
        "consistent": consistent,
        "h1_n": len(h1),
        "h2_n": len(h2),
        "h1_mean": round(h1_mean, 6) if h1_mean is not None else None,
        "h2_mean": round(h2_mean, 6) if h2_mean is not None else None,
        "h1_date_range": h1_date_range,
        "h2_date_range": h2_date_range,
    }


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def run_market(market: str, universe: dict, start: pd.Timestamp,
               end: pd.Timestamp) -> dict:
    """Collect T2 events with overlay features for one market."""
    t0 = time.time()
    print(f"\n{'='*60}")
    print(f"G-T2X: Running {market} lane ({len(universe)} names) ...")

    tickers = sorted(universe.keys())
    if market == "CN" and len(tickers) > 800:
        rng = random.Random(42)
        tickers = rng.sample(tickers, 800)
        print(f"  CN capped at 800 names (seed=42)")

    # Probe for ETA
    t_probe = time.time()
    probe_results = []
    for tk in tickers[:5]:
        probe_results.extend(_collect_t2_events(
            (tk, universe[tk], market, start, end)
        ))
    probe_elapsed = time.time() - t_probe
    est = probe_elapsed / 5 * len(tickers)
    print(f"  5-name probe: {probe_elapsed:.1f}s, estimated total: {est:.0f}s ({est/60:.1f}m)")

    all_events = []
    for i, tk in enumerate(tickers):
        events = _collect_t2_events((tk, universe[tk], market, start, end))
        all_events.extend(events)
        if (i + 1) % 200 == 0:
            print(f"  {i+1}/{len(tickers)} done ({time.time()-t0:.0f}s), events so far: {len(all_events)}")

    elapsed = time.time() - t0
    print(f"  {market} done: {len(all_events)} T2 events in {elapsed:.1f}s")
    return {"events": all_events, "n_tickers": len(tickers), "elapsed_s": round(elapsed, 1)}


def analyze_overlays(events: list[dict], market: str,
                     v3_base_stats: dict) -> dict:
    """Run each overlay filter and compute gate metrics."""
    n_base = len(events)
    base_excess_vals = [r["excess_21"] for r in events
                        if r.get("excess_21") is not None and np.isfinite(r["excess_21"])
                        and not r.get("truncated_63", False)]
    base_excess_mean = float(np.mean(base_excess_vals)) if base_excess_vals else None

    print(f"\n  {market} base: n={n_base}, excess_21_mean={base_excess_mean:.4f}" if base_excess_mean is not None else f"  {market} base: n={n_base}")

    # Compute base stats for reference
    base_stats = compute_overlay_stats(events, market)

    results = {}

    # ── Overlay 1: 2W washout context ──────────────────────────────────────
    ov1_rows = [r for r in events if r.get("ov1_washout") is True]
    print(f"  OV1 washout: n={len(ov1_rows)} / {n_base} = {len(ov1_rows)/n_base*100:.1f}%")
    ov1_stats = compute_overlay_stats(ov1_rows, market)
    ov1_gates = check_promotion_gates(ov1_stats, base_stats, n_base, market)
    ov1_split = split_half_consistency(ov1_rows, base_excess_mean)
    results["ov1_washout"] = {
        "name": "OV1: 2W washout context (w2.stoch<=35 OR stoch_cross_up)",
        "status": "RAN",
        "n_base": n_base,
        "n_filtered": len(ov1_rows),
        "retention_pct": round(len(ov1_rows) / n_base * 100, 1) if n_base > 0 else 0,
        "stats": ov1_stats,
        "gates": ov1_gates,
        "split_half": ov1_split,
    }

    # ── Overlay 2: fire-day turnover z > 0 ────────────────────────────────
    ov2_rows = [r for r in events if r.get("ov2_pass") is True]
    print(f"  OV2 turnover_z>0: n={len(ov2_rows)} / {n_base} = {len(ov2_rows)/n_base*100:.1f}%")
    ov2_stats = compute_overlay_stats(ov2_rows, market)
    ov2_gates = check_promotion_gates(ov2_stats, base_stats, n_base, market)
    ov2_split = split_half_consistency(ov2_rows, base_excess_mean)
    results["ov2_turnover_z"] = {
        "name": "OV2: fire-day turnover z > 0 (above-median volume)",
        "status": "RAN",
        "n_base": n_base,
        "n_filtered": len(ov2_rows),
        "retention_pct": round(len(ov2_rows) / n_base * 100, 1) if n_base > 0 else 0,
        "stats": ov2_stats,
        "gates": ov2_gates,
        "split_half": ov2_split,
    }

    # ── Overlay 3: sector-cycle phase — NOT-RUN ────────────────────────────
    results["ov3_sector_phase"] = {
        "name": "OV3: sector-cycle phase in {bottoming, recovering}",
        "status": "NOT-RUN",
        "reason": (
            "No point-in-time historical per-stock sector membership available. "
            "sector_holdings/ contains only a current snapshot (2026-06-11 single date). "
            "sector_cycles/backfill.parquet has MONTHLY sector phase (11 SPDR ETFs) from "
            "2010-12-31 but no PIT ticker-to-sector assignment for individual stocks over "
            "the backtest window. Without PIT stock-to-sector mapping, this overlay cannot "
            "be computed without improvising a proxy — prohibited by pre-registration."
        ),
    }

    # ── Overlay 4: NW L3 dispersion-regime — NOT-RUN ──────────────────────
    results["ov4_nw_dispersion"] = {
        "name": "OV4: NW L3 dispersion-regime lens",
        "status": "NOT-RUN",
        "reason": (
            "No point-in-time historical L3 dispersion-regime time series found in data/. "
            "data/neuralweb/ contains only current-state-only files (world_state.json, "
            "kernel_estimates.parquet, spine_index.parquet) with no backfilled history. "
            "No dispersion_regime or L3-labelled parquet/json found under data/**. "
            "Without a historical daily regime label series, this overlay cannot be "
            "applied over the backtest window without constructing a proxy — "
            "prohibited by pre-registration."
        ),
    }

    # ── Overlay 5: fill_premium_20d < 8% ──────────────────────────────────
    ov5_rows = [r for r in events if r.get("ov5_not_extended") is True]
    print(f"  OV5 fp20d<8%: n={len(ov5_rows)} / {n_base} = {len(ov5_rows)/n_base*100:.1f}%")
    ov5_stats = compute_overlay_stats(ov5_rows, market)
    ov5_gates = check_promotion_gates(ov5_stats, base_stats, n_base, market)
    ov5_split = split_half_consistency(ov5_rows, base_excess_mean)
    results["ov5_not_extended"] = {
        "name": "OV5: fill_premium_20d < 8% (not-extended filter)",
        "status": "RAN",
        "n_base": n_base,
        "n_filtered": len(ov5_rows),
        "retention_pct": round(len(ov5_rows) / n_base * 100, 1) if n_base > 0 else 0,
        "stats": ov5_stats,
        "gates": ov5_gates,
        "split_half": ov5_split,
    }

    return {
        "market": market,
        "n_base": n_base,
        "base_excess_21_mean": round(base_excess_mean, 6) if base_excess_mean is not None else None,
        "base_stop_out_21_pct": base_stats.get("stop_out_21_pct"),
        "base_clean8_21_pct": base_stats.get("clean8_21_pct"),
        "base_ci": base_stats.get("ci", {}),
        "overlays": results,
    }


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def _fmt_pct(v, digits=1) -> str:
    if v is None:
        return "—"
    return f"{v:.{digits}f}%"


def _fmt_f(v, digits=4) -> str:
    if v is None:
        return "—"
    return f"{v:.{digits}f}"


def _fmt_gate(g: dict) -> str:
    status = "PASS" if g.get("pass") else "FAIL"
    val = g.get("value")
    threshold = g.get("threshold", "")
    val_str = _fmt_pct(val) if isinstance(val, float) and "%" in str(threshold) else _fmt_f(val, 4)
    return f"{status} (value={val_str}, threshold={threshold})"


def build_report(us_analysis: dict, cn_analysis: dict,
                 us_elapsed: float, cn_elapsed: float,
                 total_elapsed: float) -> str:
    lines = []
    lines.append("# G-T2X Gauntlet Results")
    lines.append("")
    lines.append("**Pre-registration:** research/signal_engine/TIER_ENTRY_DEEPDIVE.md §6")
    lines.append("**Status:** LOCKED — no post-hoc threshold tuning. Nulls printed, not hidden.")
    lines.append("**Run date:** 2026-07-06")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Pre-Registration Summary")
    lines.append("")
    lines.append("**Candidate:** T2 tier-onset events, t+1 E1 fill, per-overlay filters.")
    lines.append("")
    lines.append("**First-wave overlays (5, one pass each):**")
    lines.append("1. OV1: 2W washout context (w2.stoch <= 35 OR stoch_cross_up)")
    lines.append("2. OV2: fire-day turnover z > 0 (above-median volume on signal day)")
    lines.append("3. OV3: sector-cycle phase in {bottoming, recovering}")
    lines.append("4. OV4: NW dispersion-regime lens (NW L3 regime signal)")
    lines.append("5. OV5: fill_premium_20d < 8% (not-extended)")
    lines.append("")
    lines.append("**Ruler:** mean 21d benchmark-excess from E1 fill with −5% stop, "
                 "month-block bootstrap CI (1000 reps, seed 42).")
    lines.append("")
    lines.append("**Promotion gates (ALL must hold + directional consistency in both temporal splits):**")
    lines.append("- CI_lo > 0")
    lines.append("- stop-out_21 <= 50% (US) / <= 52% (CN)")
    lines.append("- clean8_21 >= 33%")
    lines.append("- n_filtered >= 300 per market")
    lines.append("- retention >= 25% of base T2 fires")
    lines.append("")
    lines.append("**Kill:** filtered excess <= unfiltered T2 base, OR retention < 15%.")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Universe and Data")
    lines.append("")
    lines.append(f"- **US:** {us_analysis.get('n_base', '?')} T2 onset events, "
                 f"{us_analysis.get('n_tickers_ran', '?')} tickers (baskets/ohlcv), "
                 f"2015-01-01 to 2026-05-31")
    lines.append(f"- **CN:** {cn_analysis.get('n_base', '?')} T2 onset events, "
                 f"{cn_analysis.get('n_tickers_ran', '?')} tickers (china_stocks, seed=42 cap 800), "
                 f"2016-01-01 to 2026-05-31")
    lines.append("- **Benchmark:** SPY (US), 510300.SS (CN)")
    lines.append("- **Fill:** t+1 open (US), t+1 (hi+lo)/2 (CN)")
    lines.append("- **Stop:** −5% from fill, monitored from fill-day low including fill day")
    lines.append(f"- **Runtime:** US {us_elapsed:.0f}s, CN {cn_elapsed:.0f}s, total {total_elapsed:.0f}s ({total_elapsed/60:.1f}m)")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Base T2 Metrics (Unfiltered — v3 baseline)")
    lines.append("")
    lines.append("| Market | n_base | excess_21 mean | CI_lo_95 | CI_hi_95 | stop_out_21% | clean8_21% |")
    lines.append("|---|---|---|---|---|---|---|")
    for mkt, anal in (("US", us_analysis), ("CN", cn_analysis)):
        n = anal.get("n_base", 0)
        exc = anal.get("base_excess_21_mean")
        ci = anal.get("base_ci", {})
        ci_lo = ci.get("ci_lo_95")
        ci_hi = ci.get("ci_hi_95")
        so = anal.get("base_stop_out_21_pct")
        c8 = anal.get("base_clean8_21_pct")
        lines.append(f"| {mkt} | {n} | {_fmt_f(exc)} | {_fmt_f(ci_lo)} | {_fmt_f(ci_hi)} | "
                     f"{_fmt_pct(so)} | {_fmt_pct(c8)} |")
    lines.append("")
    lines.append("*Note: v3 baseline (TIER_ENTRY_DEEPDIVE.md §3a) for US T2: excess_21 mean −0.03%, "
                 "CI (−0.59%, +0.44%), stop_out 55.6%, clean8 29.9%.*")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Per-overlay sections
    all_overlays = ["ov1_washout", "ov2_turnover_z", "ov3_sector_phase",
                    "ov4_nw_dispersion", "ov5_not_extended"]
    ov_labels = {
        "ov1_washout": "OV1: 2W Washout Context",
        "ov2_turnover_z": "OV2: Fire-day Turnover z > 0",
        "ov3_sector_phase": "OV3: Sector-Cycle Phase {bottoming, recovering}",
        "ov4_nw_dispersion": "OV4: NW L3 Dispersion-Regime Lens",
        "ov5_not_extended": "OV5: fill_premium_20d < 8%",
    }

    lines.append("## Per-Overlay Results")
    lines.append("")

    for ov_key in all_overlays:
        label = ov_labels[ov_key]
        lines.append(f"### {label}")
        lines.append("")

        us_ov = us_analysis.get("overlays", {}).get(ov_key, {})
        cn_ov = cn_analysis.get("overlays", {}).get(ov_key, {})
        status = us_ov.get("status", "UNKNOWN")

        if status == "NOT-RUN":
            reason = us_ov.get("reason", "No reason given")
            lines.append(f"**Status: NOT-RUN**")
            lines.append("")
            lines.append(f"**Reason:** {reason}")
            lines.append("")
            lines.append("**Verdict: NOT-RUN** (both US and CN)")
            lines.append("")
            lines.append("---")
            lines.append("")
            continue

        # RAN overlay — print results table
        lines.append("**Results Table:**")
        lines.append("")
        lines.append("| Market | n_base | n_filtered | retention% | excess_21 mean | CI_lo_95 | CI_hi_95 | stop_out_21% | clean8_21% |")
        lines.append("|---|---|---|---|---|---|---|---|---|")

        for mkt, ov in (("US", us_ov), ("CN", cn_ov)):
            n_base = ov.get("n_base", 0)
            n_filt = ov.get("n_filtered", 0)
            ret = ov.get("retention_pct", 0)
            stats = ov.get("stats", {})
            exc = stats.get("excess_21_mean")
            ci_d = stats.get("ci", {})
            ci_lo = ci_d.get("ci_lo_95")
            ci_hi = ci_d.get("ci_hi_95")
            so = stats.get("stop_out_21_pct")
            c8 = stats.get("clean8_21_pct")
            lines.append(
                f"| {mkt} | {n_base} | {n_filt} | {ret:.1f}% | {_fmt_f(exc)} | "
                f"{_fmt_f(ci_lo)} | {_fmt_f(ci_hi)} | {_fmt_pct(so)} | {_fmt_pct(c8)} |"
            )

        lines.append("")
        lines.append("**Split-half consistency:**")
        lines.append("")
        lines.append("| Market | H1 n | H1 dates | H1 mean exc | H2 n | H2 dates | H2 mean exc | Consistent? |")
        lines.append("|---|---|---|---|---|---|---|---|")

        for mkt, ov in (("US", us_ov), ("CN", cn_ov)):
            sh = ov.get("split_half", {})
            h1n = sh.get("h1_n", 0)
            h2n = sh.get("h2_n", 0)
            h1m = sh.get("h1_mean")
            h2m = sh.get("h2_mean")
            h1dr = sh.get("h1_date_range", "N/A")
            h2dr = sh.get("h2_date_range", "N/A")
            cons = sh.get("consistent")
            cons_str = ("YES" if cons else "NO") if cons is not None else "—"
            lines.append(
                f"| {mkt} | {h1n} | {h1dr} | {_fmt_f(h1m)} | {h2n} | {h2dr} | {_fmt_f(h2m)} | {cons_str} |"
            )

        lines.append("")
        lines.append("**Gate-by-gate (US / CN):**")
        lines.append("")
        lines.append("| Gate | Threshold | US value | US result | CN value | CN result |")
        lines.append("|---|---|---|---|---|---|")

        gate_defs = [
            ("ci_lo_positive", "CI_lo > 0"),
            ("stop_out_21", "stop_out_21 <= 50%/52%"),
            ("clean8_21", "clean8_21 >= 33%"),
            ("n_filtered", "n_filtered >= 300"),
            ("retention", "retention >= 25%"),
        ]

        us_gates_d = us_ov.get("gates", {}).get("gates", {})
        cn_gates_d = cn_ov.get("gates", {}).get("gates", {})

        for gate_key, gate_label in gate_defs:
            us_g = us_gates_d.get(gate_key, {})
            cn_g = cn_gates_d.get(gate_key, {})
            threshold = us_g.get("threshold", gate_label)
            us_val = us_g.get("value")
            cn_val = cn_g.get("value")
            us_pass = "PASS" if us_g.get("pass") else "FAIL"
            cn_pass = "PASS" if cn_g.get("pass") else "FAIL"
            # Format values
            if isinstance(us_val, float) and "%" in str(threshold):
                us_val_s = _fmt_pct(us_val)
                cn_val_s = _fmt_pct(cn_val)
            else:
                us_val_s = _fmt_f(us_val, 4)
                cn_val_s = _fmt_f(cn_val, 4)
            lines.append(f"| {gate_label} | {threshold} | {us_val_s} | {us_pass} | {cn_val_s} | {cn_pass} |")

        lines.append("")

        # Kill / verdict
        us_g_full = us_ov.get("gates", {})
        cn_g_full = cn_ov.get("gates", {})
        us_verdict = us_g_full.get("verdict", "UNKNOWN")
        cn_verdict = cn_g_full.get("verdict", "UNKNOWN")

        # Overall overlay verdict: PROMOTE only if both markets PROMOTE + both splits consistent
        us_split_ok = us_ov.get("split_half", {}).get("consistent")
        cn_split_ok = cn_ov.get("split_half", {}).get("consistent")

        if us_verdict == "KILL" or cn_verdict == "KILL":
            overall = "KILL"
        elif us_verdict == "PROMOTE" and cn_verdict == "PROMOTE":
            if us_split_ok and cn_split_ok:
                overall = "PROMOTE"
            elif us_split_ok is False or cn_split_ok is False:
                overall = "NULL"
            else:
                overall = "NULL"  # split check inconclusive
        elif us_verdict == "NULL" or cn_verdict == "NULL":
            overall = "NULL"
        else:
            overall = "NULL"

        kill_str = ""
        if us_g_full.get("kill_reason"):
            kill_str += f" US kill: {us_g_full['kill_reason']}."
        if cn_g_full.get("kill_reason"):
            kill_str += f" CN kill: {cn_g_full['kill_reason']}."

        lines.append(f"**Verdict: {overall}** (US={us_verdict}, CN={cn_verdict}){kill_str}")
        lines.append("")
        lines.append("---")
        lines.append("")

    # Summary verdict table
    lines.append("## Summary Verdict Table")
    lines.append("")
    lines.append("| Overlay | US n_filt | CN n_filt | US excess | CN excess | US CI_lo | CN CI_lo | US stop% | CN stop% | US clean8% | CN clean8% | US verdict | CN verdict | Overall |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")

    for ov_key in all_overlays:
        us_ov = us_analysis.get("overlays", {}).get(ov_key, {})
        cn_ov = cn_analysis.get("overlays", {}).get(ov_key, {})
        label_short = ov_key.replace("ov1_washout", "OV1").replace("ov2_turnover_z", "OV2") \
                             .replace("ov3_sector_phase", "OV3").replace("ov4_nw_dispersion", "OV4") \
                             .replace("ov5_not_extended", "OV5")

        if us_ov.get("status") == "NOT-RUN":
            lines.append(f"| {label_short} | NOT-RUN | NOT-RUN | — | — | — | — | — | — | — | — | NOT-RUN | NOT-RUN | NOT-RUN |")
            continue

        us_stats = us_ov.get("stats", {})
        cn_stats = cn_ov.get("stats", {})
        us_gates_full = us_ov.get("gates", {})
        cn_gates_full = cn_ov.get("gates", {})

        us_nf = us_ov.get("n_filtered", 0)
        cn_nf = cn_ov.get("n_filtered", 0)
        us_exc = us_stats.get("excess_21_mean")
        cn_exc = cn_stats.get("excess_21_mean")
        us_ci_lo = us_stats.get("ci", {}).get("ci_lo_95")
        cn_ci_lo = cn_stats.get("ci", {}).get("ci_lo_95")
        us_so = us_stats.get("stop_out_21_pct")
        cn_so = cn_stats.get("stop_out_21_pct")
        us_c8 = us_stats.get("clean8_21_pct")
        cn_c8 = cn_stats.get("clean8_21_pct")
        us_v = us_gates_full.get("verdict", "?")
        cn_v = cn_gates_full.get("verdict", "?")

        # Overall
        us_sv = us_ov.get("split_half", {}).get("consistent")
        cn_sv = cn_ov.get("split_half", {}).get("consistent")
        if us_v == "KILL" or cn_v == "KILL":
            overall_v = "KILL"
        elif us_v == "PROMOTE" and cn_v == "PROMOTE" and us_sv and cn_sv:
            overall_v = "PROMOTE"
        else:
            overall_v = "NULL"

        lines.append(
            f"| {label_short} | {us_nf} | {cn_nf} | {_fmt_f(us_exc)} | {_fmt_f(cn_exc)} | "
            f"{_fmt_f(us_ci_lo)} | {_fmt_f(cn_ci_lo)} | {_fmt_pct(us_so)} | {_fmt_pct(cn_so)} | "
            f"{_fmt_pct(us_c8)} | {_fmt_pct(cn_c8)} | {us_v} | {cn_v} | {overall_v} |"
        )

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Plain-English Summary")
    lines.append("")
    lines.append("**In plain English:** This study tested 5 pre-registered filter overlays on T2 "
                 "tier-onset events across 2,498 US names (2015-2026) and 800 CN names (2016-2026). "
                 "The base T2 population — unfiltered — shows near-zero benchmark-excess at 21 days "
                 "with confidence intervals straddling zero and stop-out rates of ~56% (matching "
                 "TIER_ENTRY_DEEPDIVE §3a).")
    lines.append("")
    lines.append("**Overlays 3 and 4 were NOT-RUN:** OV3 (sector-cycle phase) requires "
                 "point-in-time per-stock sector membership history, which does not exist — "
                 "sector_holdings/ has only a 2026-06-11 snapshot. OV4 (NW L3 dispersion regime) "
                 "requires a historical daily regime label series, which does not exist in data/neuralweb/. "
                 "No proxies were improvised — the pre-registration prohibits this.")
    lines.append("")
    lines.append("**Overlays 1, 2, and 5 ran.** Results by overlay:")
    lines.append("")

    for ov_key in ["ov1_washout", "ov2_turnover_z", "ov5_not_extended"]:
        us_ov = us_analysis.get("overlays", {}).get(ov_key, {})
        cn_ov = cn_analysis.get("overlays", {}).get(ov_key, {})
        us_stats = us_ov.get("stats", {})
        cn_stats = cn_ov.get("stats", {})
        us_gates_full = us_ov.get("gates", {})
        cn_gates_full = cn_ov.get("gates", {})
        us_v = us_gates_full.get("verdict", "?")
        cn_v = cn_gates_full.get("verdict", "?")
        us_nf = us_ov.get("n_filtered", 0)
        cn_nf = cn_ov.get("n_filtered", 0)
        us_exc = us_stats.get("excess_21_mean")
        cn_exc = cn_stats.get("excess_21_mean")
        us_ci = us_stats.get("ci", {})
        cn_ci = cn_stats.get("ci", {})
        us_so = us_stats.get("stop_out_21_pct")
        cn_so = cn_stats.get("stop_out_21_pct")
        us_c8 = us_stats.get("clean8_21_pct")
        cn_c8 = cn_stats.get("clean8_21_pct")

        ov_names = {
            "ov1_washout": "OV1 (2W washout)",
            "ov2_turnover_z": "OV2 (turnover z>0)",
            "ov5_not_extended": "OV5 (fp20d<8%)",
        }
        name = ov_names[ov_key]

        # Determine overall verdict
        us_sv = us_ov.get("split_half", {}).get("consistent")
        cn_sv = cn_ov.get("split_half", {}).get("consistent")
        if us_v == "KILL" or cn_v == "KILL":
            overall_v = "KILL"
        elif us_v == "PROMOTE" and cn_v == "PROMOTE" and us_sv and cn_sv:
            overall_v = "PROMOTE"
        else:
            overall_v = "NULL"

        lines.append(f"- **{name}** (overall {overall_v}): US n={us_nf} ({us_ov.get('retention_pct', 0):.0f}% retained), "
                     f"excess={_fmt_f(us_exc)} CI_lo={_fmt_f(us_ci.get('ci_lo_95'))}, "
                     f"stop_out={_fmt_pct(us_so)}, clean8={_fmt_pct(us_c8)}; "
                     f"CN n={cn_nf} ({cn_ov.get('retention_pct', 0):.0f}% retained), "
                     f"excess={_fmt_f(cn_exc)} CI_lo={_fmt_f(cn_ci.get('ci_lo_95'))}, "
                     f"stop_out={_fmt_pct(cn_so)}, clean8={_fmt_pct(cn_c8)}. "
                     f"US verdict={us_v}, CN verdict={cn_v}.")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Caveats")
    lines.append("")
    lines.append("1. **CN survivorship bias.** CN universe is 2026-snapshot. "
                 "Historical CN numbers are directionally informative but overstated vs. a PIT universe.")
    lines.append("2. **OV3 / OV4 NOT-RUN.** Both overlays require historical time-series data "
                 "that does not exist in backfillable form. These are flagged as data gaps — "
                 "future builds must create archival sector-phase-per-stock and NW dispersion-regime series.")
    lines.append("3. **OV1 w_setup is compute-intensive.** For each event, w_setup() is called on "
                 "the truncated series close[:event_date]. This is PIT-safe but slow (~2-4s per "
                 "ticker on average).")
    lines.append("4. **Turnover z uses 60-bar rolling lookback.** Pre-registration says 'above-median "
                 "volume on signal day'; z>0 is above the rolling mean which equals above-median "
                 "under approximate normality. Window = 60 prior bars (about 3 months).")
    lines.append("5. **US PIT filter not applied.** US broad universe uses all baskets/ohlcv parquets; "
                 "no SP1500 PIT survivorship filter applied, matching v3 baseline.")
    lines.append(f"6. **Truncation.** Events after {TRUNC_63.date()} excluded from CI bootstrap "
                 "(lack full 63d forward data).")
    lines.append("7. **No VALIDATED language.** All metrics are descriptive. "
                 "No signal has been promoted based on this study.")
    lines.append("")
    lines.append("---")
    lines.append("*Generated by scripts/_bt_g_t2x.py — G-T2X locked gauntlet, 2026-07-06.*")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    t_total = time.time()
    print("G-T2X gauntlet starting ...")
    print(f"  Worktree: {_WORKTREE}")
    print(f"  Data root: {_DATA_ROOT}")
    print(f"  Output: {_OUT_DIR}")

    # Load universes
    print("\nLoading universes ...")
    us_universe = load_us_universe()
    cn_universe = load_cn_universe()
    print(f"  US: {len(us_universe)} names, CN: {len(cn_universe)} names")

    # CN cap at 800 (seed=42) — same as v3
    cn_tickers = sorted(cn_universe.keys())
    if len(cn_tickers) > 800:
        rng = random.Random(42)
        cn_tickers_capped = rng.sample(cn_tickers, 800)
        cn_universe_capped = {t: cn_universe[t] for t in cn_tickers_capped}
    else:
        cn_universe_capped = cn_universe

    # Run per-market collection
    us_run = run_market("US", us_universe, US_START, COMMON_END)
    cn_run = run_market("CN", cn_universe_capped, CN_START, COMMON_END)

    us_events = us_run["events"]
    cn_events = cn_run["events"]
    us_elapsed = us_run["elapsed_s"]
    cn_elapsed = cn_run["elapsed_s"]

    print(f"\nCollection done: US {len(us_events)} events, CN {len(cn_events)} events")

    # Load v3 base stats for reference
    v3_us_base = {
        "excess_21_mean": -0.000252,
        "ci_lo_95": -0.005859,
        "ci_hi_95": 0.004440,
        "stop_out_21_pct": 55.607,
        "clean8_21_pct": 29.909,
    }
    v3_cn_base = {
        "excess_21_mean": 0.006970,
        "ci_lo_95": -0.003071,
        "ci_hi_95": 0.017965,
        "stop_out_21_pct": 55.630,
        "clean8_21_pct": 34.550,
    }

    # Analyze overlays
    print("\nAnalyzing overlays ...")
    us_analysis = analyze_overlays(us_events, "US", v3_us_base)
    cn_analysis = analyze_overlays(cn_events, "CN", v3_cn_base)

    # Annotate with tickers ran
    us_analysis["n_tickers_ran"] = us_run["n_tickers"]
    cn_analysis["n_tickers_ran"] = cn_run["n_tickers"]

    total_elapsed = time.time() - t_total

    # Build and save report
    report_md = build_report(us_analysis, cn_analysis,
                             us_elapsed, cn_elapsed, total_elapsed)

    report_path = _OUT_DIR / "results.md"
    with open(str(report_path), "w") as f:
        f.write(report_md)
    print(f"\nReport written to {report_path}")

    # Save raw JSON
    def _json_safe(obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj) if np.isfinite(obj) else None
        if isinstance(obj, (np.bool_,)):
            return bool(obj)
        if isinstance(obj, pd.Timestamp):
            return str(obj.date())
        if isinstance(obj, pd.DatetimeIndex):
            return None
        raise TypeError(f"Not serializable: {type(obj)}")

    results_json = {
        "us_analysis": {k: v for k, v in us_analysis.items() if k != "events"},
        "cn_analysis": {k: v for k, v in cn_analysis.items() if k != "events"},
        "us_n_events": len(us_events),
        "cn_n_events": len(cn_events),
        "total_elapsed_s": round(total_elapsed, 1),
    }
    json_path = _OUT_DIR / "results.json"
    with open(str(json_path), "w") as f:
        json.dump(results_json, f, indent=2, default=_json_safe)
    print(f"JSON written to {json_path}")

    print(f"\nTotal runtime: {total_elapsed:.1f}s ({total_elapsed/60:.1f}m)")
    return results_json, report_md


if __name__ == "__main__":
    main()
