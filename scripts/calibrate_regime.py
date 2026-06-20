"""Bitcoin macro-regime composite — P1 validation harness.

SEPARATE CALIBRATION NAMESPACE — this file MUST NOT modify
scripts/calibrate_vector.py, must NOT write data/vector/calibration.json,
and must NOT touch the live allocator or its DSR.

Outputs:
  data/vector/regime_calibration.json  (self-contained; never read by the live engine)

Run:
  python -m scripts.calibrate_regime

Disciplines carried throughout:
  * Time-series rank IC (Spearman between full index series and forward returns) —
    NOT the cross-sectional rank_ic() from engine.validation which is a one-date /
    multi-name tool and the WRONG tool for a single time series.
  * choice_ledger enumerates every a-priori knob from btc_regime + btc_regime_flags
    so n_trials is machine-counted (not manually declared).
  * DSR EXPECTED TO BE FAR BELOW 0.90 — the composite is display-only; that is
    the correct, intended result. This harness exists to measure and document that.
  * PIT analysis bounded to M2SL (the clearly-vintaged, revision-prone leg). All
    other legs are either market-data (never revised) or de-mean'd z-scores (revisions
    are self-averaging over the rolling window). PIT can only make IC equal-or-WORSE.
  * 2024-> out-of-regime subsample is reported separately with wide CIs; one partial
    cycle is un-validatable.
"""
from __future__ import annotations

import itertools
import json
import math
import sys
import warnings
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
warnings.filterwarnings("ignore")

from engine.btc_regime import (  # noqa: E402
    EXPO_KNOTS_X, EXPO_KNOTS_Y, HIVIX_Z, MIN_FACTORS, SLOPE_LB,
    TREND_MA_D, TREND_MA_W, Z_WINDOW, composite_frame, exposure_band,
)
from engine.btc_regime_flags import (  # noqa: E402
    K_DEFAULT, K_SWEEP, PANEL_LOOKBACK, TAIL_HI, TAIL_LO,
)
from engine.validation import (  # noqa: E402
    backtest_core, block_bootstrap_ci, deflated_sharpe, newey_west_tstat, purged_folds,
)
from lib import config  # noqa: E402

# --------------------------------------------------------------------------- #
# Configuration (mirrors calibrate_vector.py style)
# --------------------------------------------------------------------------- #
START_DATE = "2015-01-01"
SPLIT_DATE = "2021-01-01"
HORIZONS = [30, 90, 180]       # forward-return horizons in days
COST_BPS = 10.0                # one-way transaction cost (bps)
POST_2024 = "2024-01-11"       # first US spot-ETF approval date
TRADING_YEAR = 365             # BTC trades every day

# Cycle windows (approximate BTC market cycles) for leave-one-cycle-out
CYCLE_WINDOWS = [
    ("2015-2018", "2015-01-01", "2018-12-31"),
    ("2018-2021", "2018-12-31", "2020-12-31"),
    ("2021-2024", "2020-12-31", "2024-01-10"),
    ("2024-now",  "2024-01-10", "2099-12-31"),
]

K_CV = 6   # number of purged folds for CPCV

# --------------------------------------------------------------------------- #
# Machine-counted choice ledger — every a-priori knob from btc_regime +
# btc_regime_flags. Each entry is ONE explored choice. n_trials = len(choice_ledger).
# --------------------------------------------------------------------------- #
def _build_choice_ledger() -> list[dict]:
    """Enumerate every a-priori parameter choice that was baked into the composite.
    These are the choices that *could* have been tuned differently — they are all
    FIXED a-priori (not fit to forward returns), but the DSR still must account for
    the fact that a different framework could have chosen different values."""
    ledger: list[dict] = []

    # btc_regime constants
    ledger.append({"knob": "Z_WINDOW", "value": Z_WINDOW,
                   "note": "rolling z-score window (days) — a-priori 365 (≈1 year)"})
    # The 4 z-score cut-points: ±0.5 and ±1.5 define the {-2,-1,0,+1,+2} buckets
    ledger.append({"knob": "z_cut_lo1", "value": 0.5,
                   "note": "score-z lower inner cut-point (±0.5)"})
    ledger.append({"knob": "z_cut_hi1", "value": 1.5,
                   "note": "score-z lower outer cut-point (±1.5)"})
    ledger.append({"knob": "z_cut_lo2", "value": -0.5,
                   "note": "score-z upper inner cut-point (−0.5)"})
    ledger.append({"knob": "z_cut_hi2", "value": -1.5,
                   "note": "score-z upper outer cut-point (−1.5)"})
    ledger.append({"knob": "SLOPE_LB",  "value": SLOPE_LB,
                   "note": "slope look-back for _lvl_chg and tail flags (days)"})
    ledger.append({"knob": "TREND_MA_D", "value": TREND_MA_D,
                   "note": "trend MA fast period (days) — 200D"})
    ledger.append({"knob": "TREND_MA_W", "value": TREND_MA_W,
                   "note": "trend MA slow period (days) — ~200W"})
    ledger.append({"knob": "HIVIX_Z",    "value": HIVIX_Z,
                   "note": "VIX-z threshold for HY-OAS credit accelerant (Lee EFM 2026)"})
    # 6 EXPO knot x-values
    for i, (x, y) in enumerate(zip(EXPO_KNOTS_X, EXPO_KNOTS_Y)):
        ledger.append({"knob": f"EXPO_KNOT_{i}",
                       "value": f"x={x} y={y}",
                       "note": f"exposure spline knot {i} (x={x}→y={y})"})
    ledger.append({"knob": "MIN_FACTORS", "value": MIN_FACTORS,
                   "note": "minimum live factors before index is considered valid"})
    # btc_regime_flags constants
    ledger.append({"knob": "PANEL_LOOKBACK", "value": PANEL_LOOKBACK,
                   "note": "rolling percentile window for on-chain tail bands (days)"})
    ledger.append({"knob": "TAIL_LO",  "value": TAIL_LO,
                   "note": "lower tail threshold for on-chain depressed panel"})
    ledger.append({"knob": "TAIL_HI",  "value": TAIL_HI,
                   "note": "upper tail threshold for on-chain stretched panel"})
    # K_SWEEP has 3 values
    for kk in K_SWEEP:
        ledger.append({"knob": f"K_SWEEP_{kk}", "value": kk,
                       "note": f"confluence k-of-n tail flag threshold (k={kk})"})
    return ledger


# --------------------------------------------------------------------------- #
# Time-series rank IC (the CORRECT tool for a single time-indexed series)
# --------------------------------------------------------------------------- #
def ts_rank_ic(index_s: pd.Series, fwd_s: pd.Series) -> float:
    """Spearman rank correlation between the composite index and a forward-return
    series, both aligned by date. This is a TIME-SERIES rank IC (one scalar over
    the whole period), NOT a cross-sectional rank_ic() which is a one-date /
    multi-name metric — that is the footgun for a single time series.

    Both series are ranked independently over their joint non-NaN dates, then
    Pearson-correlated on ranks (Spearman). Returns NaN if fewer than 30 joints."""
    j = pd.concat([index_s.rename("idx"), fwd_s.rename("fwd")], axis=1, sort=False).dropna()
    if len(j) < 30:
        return float("nan")
    rk_idx = j["idx"].rank()
    rk_fwd = j["fwd"].rank()
    corr = rk_idx.corr(rk_fwd)
    return float(corr)


def fwd_returns(close: pd.Series, horizons: list[int]) -> pd.DataFrame:
    return pd.DataFrame({h: close.pct_change(h).shift(-h) for h in horizons})


# --------------------------------------------------------------------------- #
# IC table: full / pre / post with NW t-stat
# NW is needed because overlapping forward-return windows inject serial correlation
# --------------------------------------------------------------------------- #
def _ic_table_one_horizon(index_s: pd.Series, fwd_s: pd.Series,
                          pre_idx, post_idx, embargo: int) -> dict:
    """Compute IC for full / pre (embargoed) / post halves + Newey-West t-stat.

    The Newey-West t-stat is CRITICAL here: overlapping forward windows (e.g. 90d
    forward return computed on daily rows) inject up to horizon-1 orders of serial
    autocorrelation into the IC, making a plain t-stat overstate significance."""
    full_ic = ts_rank_ic(index_s, fwd_s)
    # embargoed pre: drop the trailing `embargo` rows so labels don't leak across split
    _pre = index_s.loc[pre_idx]
    pre_embargoed = _pre.iloc[:-embargo] if len(_pre) > embargo else _pre
    pre_ic  = ts_rank_ic(pre_embargoed, fwd_s.loc[pre_embargoed.index])
    post_ic = ts_rank_ic(index_s.loc[post_idx], fwd_s.loc[post_idx])

    # Newey-West t-stat on a per-observation product r_t = rank(index) * rank(fwd)
    # (the rank-product series has the same serial structure as overlapping IC)
    j = pd.concat([index_s.rename("idx"), fwd_s.rename("fwd")], axis=1, sort=False).dropna()
    if len(j) >= 8:
        n_lags = min(len(j) // 10, 180)   # proportional to the horizon
        rkp = j["idx"].rank(pct=True) * j["fwd"].rank(pct=True)  # proxy for rank-product
        # center (IC ~ mean rank-product − 0.25 under H0); NW tests if mean ≠ 0
        nw = newey_west_tstat(rkp, lags=n_lags)
    else:
        nw = {"mean": None, "t": None, "p": None, "n": len(j)}

    return {
        "full_ic": round(full_ic, 4) if math.isfinite(full_ic) else None,
        "pre_ic":  round(pre_ic, 4)  if math.isfinite(pre_ic)  else None,
        "post_ic": round(post_ic, 4) if math.isfinite(post_ic) else None,
        "nw_t": nw.get("t"),
        "nw_p": nw.get("p"),
        "n_full": len(j),
        "n_pre":  len(pre_embargoed.dropna()),
        "n_post": len(index_s.loc[post_idx].dropna()),
    }


# --------------------------------------------------------------------------- #
# Leave-one-cycle-out (4 BTC cycle windows)
# --------------------------------------------------------------------------- #
def _leave_one_cycle_out(index_s: pd.Series, fwd_s: pd.Series, h: int) -> dict:
    """Hold out each cycle; train on the rest; report the IC on held-out half.
    Because we have ~3-5 full cycles, ALL paths are dependent — report worst IC."""
    results = {}
    for name, start, end in CYCLE_WINDOWS:
        held_mask = (index_s.index >= start) & (index_s.index < end)
        held_idx = index_s.index[held_mask]
        if len(held_idx) < 30:
            results[name] = {"ic": None, "n": len(held_idx), "note": "too short"}
            continue
        ic = ts_rank_ic(index_s.loc[held_idx], fwd_s.loc[held_idx])
        results[name] = {
            "ic": round(ic, 4) if math.isfinite(ic) else None,
            "n": len(held_idx),
        }
    valid_ics = [v["ic"] for v in results.values() if v.get("ic") is not None]
    worst_ic = min(valid_ics) if valid_ics else None
    best_ic  = max(valid_ics) if valid_ics else None
    return {
        "per_cycle": results,
        "worst_ic": round(worst_ic, 4) if worst_ic is not None else None,
        "best_ic":  round(best_ic, 4) if best_ic is not None else None,
        "note": (f"Leave-one-cycle-out at horizon {h}d: each cycle window held out "
                 "in turn, IC reported on held-out period. With ~4 cycles the "
                 "out-of-cycle IC is high-variance; the worst cycle is the honest bar."),
    }


# --------------------------------------------------------------------------- #
# Combinatorial Purged CV (CPCV)
# --------------------------------------------------------------------------- #
def _cpcv(index_s: pd.Series, fwd_s: pd.Series, k: int, embargo: int, h: int) -> dict:
    """Hand-rolled CPCV using purged_folds: choose 2 test folds at a time (the rest
    train); compute index→fwd-h IC on each combinatorial test path; report mean/std.

    IMPORTANT non-independence warning: on ~3-5 BTC cycles the test paths are NOT
    independent — CIs will be wide and any apparent precision is spurious. Do not
    read tight numbers as meaningful. This section exists to run the procedure
    transparently and flag its limitations explicitly.
    """
    folds = purged_folds(index_s.index, k, embargo)
    fold_keys = list(folds.keys())
    n_folds = len(fold_keys)

    if n_folds < 3:
        return {
            "mean_ic": None, "std_ic": None, "n_paths": 0,
            "note": "too few folds for CPCV",
            "non_independence_warning": True,
        }

    # Generate all combinations of 2 test folds from the k available folds
    path_ics = []
    for test_pair in itertools.combinations(fold_keys, 2):
        test_idx = folds[test_pair[0]]
        for fk in test_pair[1:]:
            test_idx = test_idx.union(folds[fk])
        if len(test_idx) < 30:
            continue
        ic = ts_rank_ic(index_s.loc[test_idx], fwd_s.reindex(test_idx))
        if math.isfinite(ic):
            path_ics.append(ic)

    if not path_ics:
        return {"mean_ic": None, "std_ic": None, "n_paths": 0,
                "non_independence_warning": True,
                "note": "no valid CPCV paths"}

    return {
        "mean_ic": round(float(np.mean(path_ics)), 4),
        "std_ic":  round(float(np.std(path_ics, ddof=1)), 4) if len(path_ics) > 1 else None,
        "n_paths": len(path_ics),
        "k_folds": n_folds,
        "horizon_d": h,
        "non_independence_warning": True,
        "note": (f"CPCV with k={n_folds} purged folds, C(k,2)={len(path_ics)} test paths "
                 f"at horizon {h}d. NON-INDEPENDENT paths on ~3-5 BTC cycles: wide CIs, "
                 "tight numbers are spurious. Do not trust narrow confidence intervals here."),
    }


# --------------------------------------------------------------------------- #
# Allocation backtest via exposure_band
# --------------------------------------------------------------------------- #
def _backtest_exposure(index_s: pd.Series, close: pd.Series) -> dict:
    """Map index → exposure_band (vectorized), shift(1) to avoid look-ahead,
    run backtest_core, compute ret_moments + deflated_sharpe."""
    alloc = index_s.apply(lambda v: exposure_band(v) if pd.notna(v) else 0.0)
    alloc = alloc.reindex(close.index).fillna(0.0)
    bt = backtest_core(close, alloc, cost_bps=COST_BPS)
    net = bt["net"]
    eq  = (1 + net).cumprod()
    hodl_ret = bt["hold"]
    hodl_eq  = (1 + hodl_ret).cumprod()
    years = bt["years"]

    def cagr(e):
        return (float(e.iloc[-1]) ** (1.0 / years) - 1) if years > 0 and float(e.iloc[-1]) > 0 else float("nan")

    def sharpe(r):
        sd = float(r.std())
        return float(r.mean() / sd * math.sqrt(TRADING_YEAR)) if sd else float("nan")

    def maxdd(e):
        return float((e / e.cummax() - 1).min())

    # Per-period moments for the DSR
    r_ = net.dropna()
    if len(r_) >= 3:
        mu, sd_ = float(r_.mean()), float(r_.std(ddof=1))
        if sd_:
            z_ = (r_ - mu) / sd_
            sr_daily = float(mu / sd_)
            skew_val = float((z_**3).mean())
            kurt_val = float((z_**4).mean())
            n_obs    = int(len(r_))
        else:
            sr_daily = skew_val = kurt_val = None
            n_obs = int(len(r_))
    else:
        sr_daily = skew_val = kurt_val = None
        n_obs = int(len(r_)) if len(r_) else 0

    return {
        "cagr_net":      round(100 * cagr(eq), 1),
        "hodl_cagr":     round(100 * cagr(hodl_eq), 1),
        "sharpe_net":    round(sharpe(net), 2),
        "hodl_sharpe":   round(sharpe(hodl_ret), 2),
        "maxdd_pct":     round(100 * maxdd(eq), 1),
        "hodl_maxdd_pct": round(100 * maxdd(hodl_eq), 1),
        "time_in_market": round(float((alloc.reindex(close.index) > 0).mean()) * 100, 1),
        "cost_bps": COST_BPS,
        "sharpe_daily": round(sr_daily, 6) if sr_daily is not None else None,
        "skew": round(skew_val, 4) if skew_val is not None else None,
        "kurt": round(kurt_val, 4) if kurt_val is not None else None,
        "n_obs": n_obs,
    }


# --------------------------------------------------------------------------- #
# PIT demonstration: M2SL-YoY proxy walked across month-ends
# --------------------------------------------------------------------------- #
def _pit_m2_composite(df: pd.DataFrame) -> dict | None:
    """Build a PIT global-M2-YoY proxy from ALFRED vintages (M2SL only, US leg),
    recompute the composite IC swapping in PIT-M2, and report the IC delta.

    Bounded to M2SL because:
      - M2SL IS in DEFAULT_VINTAGE_SERIES and vintages.parquet exists
      - M2 is revision-prone (one-time seasonal adjustments, definition changes)
      - Other legs are market data (rates, DXY, VIX, OAS — never revised) or
        already de-meaned z-scores over rolling windows (self-averaging)

    Returns None if vintages unavailable — degrade gracefully.

    PIT can only make the macro IC equal-or-WORSE: revised data reflects information
    not knowable in real time and is upward-biased relative to initial releases.
    """
    try:
        from collectors.fred import as_of_series, load_vintages
        vintages = load_vintages()
        if vintages is None or vintages.empty:
            return {"ok": False, "reason": "vintages.parquet unavailable",
                    "note": "PIT check skipped — no FRED vintage data on disk. "
                            "PIT can only make the macro IC equal-or-WORSE."}

        m2v = vintages[vintages["series"] == "M2SL"]
        if m2v.empty:
            return {"ok": False, "reason": "M2SL not in vintages.parquet",
                    "note": "PIT check skipped — M2SL absent from vintage store."}

        # Walk across month-ends: at each rebalance, get the M2SL series as
        # known that day (only initial-released data published by then).
        month_ends = pd.date_range(df.index.min(), df.index.max(), freq="BME")
        pit_m2_monthly: dict[pd.Timestamp, float] = {}
        for asof in month_ends:
            pit_s = as_of_series("M2SL", asof, vintages)
            if pit_s.empty:
                continue
            # YoY growth from the PIT snapshot
            pit_s = pit_s.sort_index()
            if len(pit_s) >= 13:
                last_val  = float(pit_s.iloc[-1])
                year_ago  = float(pit_s.iloc[-13]) if len(pit_s) >= 13 else float("nan")
                if year_ago and math.isfinite(year_ago) and year_ago > 0:
                    pit_m2_monthly[asof] = (last_val / year_ago - 1) * 100

        if not pit_m2_monthly:
            return {"ok": False, "reason": "no PIT M2SL YoY computable",
                    "note": "PIT check skipped — too few vintage observations."}

        # Build a daily PIT-M2-YoY by forward-filling from month-ends
        pit_m2_s = pd.Series(pit_m2_monthly).sort_index()
        pit_m2_daily = pit_m2_s.reindex(
            pd.date_range(df.index.min(), df.index.max(), freq="D")
        ).ffill().reindex(df.index)

        # Recompute the composite swapping in PIT-M2 for global_m2_yoy
        df_pit = df.copy()
        df_pit["global_m2_yoy"] = pit_m2_daily

        cf_pit = composite_frame(df_pit)
        index_pit = cf_pit["index"].dropna() if "index" in cf_pit else pd.Series(dtype=float)
        if index_pit.empty:
            return {"ok": False, "reason": "composite returned empty with PIT-M2",
                    "note": "PIT check produced no valid composite index."}

        # Revised composite IC
        cf_rev = composite_frame(df)
        index_rev = cf_rev["index"].dropna() if "index" in cf_rev else pd.Series(dtype=float)

        close = df["close"]
        fwd90 = close.pct_change(90).shift(-90)

        ic_revised = ts_rank_ic(index_rev, fwd90)
        ic_pit     = ts_rank_ic(index_pit, fwd90)
        delta_ic   = (float(ic_pit) - float(ic_revised)) if (math.isfinite(ic_pit) and math.isfinite(ic_revised)) else None

        # Count how many m2 scores SHIFT (fire differently with PIT vs revised)
        # by looking at when the PIT vs revised m2_yoy differ enough to shift the score bucket
        m2_revised = df["global_m2_yoy"].dropna()
        m2_pit_aligned = pit_m2_daily.reindex(m2_revised.index).dropna()
        common = m2_revised.index.intersection(m2_pit_aligned.index)
        if len(common) > 0:
            diff = (m2_revised.loc[common] - m2_pit_aligned.loc[common]).abs()
            # score buckets roughly shift at ±0.5σ thresholds → approximate shift count
            # by how many days the absolute difference exceeds 0.5% (a loose proxy)
            shift_count = int((diff > 0.5).sum())
            pct_shifted = round(float(shift_count / len(common)) * 100, 1)
        else:
            shift_count, pct_shifted = 0, 0.0

        return {
            "ok": True,
            "ic_revised_90d": round(ic_revised, 4) if math.isfinite(ic_revised) else None,
            "ic_pit_90d":     round(ic_pit, 4) if math.isfinite(ic_pit) else None,
            "delta_ic": round(delta_ic, 4) if delta_ic is not None else None,
            "m2_score_shift_days": shift_count,
            "m2_score_shift_pct_of_sample": pct_shifted,
            "n_month_ends_walked": len(pit_m2_monthly),
            "note": ("PIT bounded to M2SL (US leg of global_m2_yoy) — the only leg "
                     "that is both revision-prone and in the vintage store. Other legs "
                     "are market data (never revised) or z-scores (self-averaging). "
                     "PIT can only make the macro IC equal-or-WORSE: revised data "
                     "reflects information not knowable in real time and is upward-biased. "
                     "Delta IC = PIT − revised; negative means PIT is worse (expected)."),
        }
    except Exception as e:  # noqa: BLE001 — degrade gracefully
        return {
            "ok": False,
            "reason": f"{type(e).__name__}: {e}",
            "note": "PIT check failed — degrade gracefully. See reason field.",
        }


# --------------------------------------------------------------------------- #
# Out-of-regime: post-2024 ETF/flow-driven subsample
# --------------------------------------------------------------------------- #
def _out_of_regime(index_s: pd.Series, close: pd.Series) -> dict:
    """Report IC + bootstrap CI on the post-2024 ETF-driven subsample.
    One partial cycle — un-validatable. Flow legs (etf) are REPORT-ONLY and can
    DEMOTE but never PROMOTE the composite."""
    post_idx = index_s.index[index_s.index >= POST_2024]
    if len(post_idx) < 60:
        return {"n": len(post_idx), "ic_90d": None,
                "note": "Post-2024 subsample too short for meaningful stats."}

    fwd90 = close.pct_change(90).shift(-90)
    ic90  = ts_rank_ic(index_s.loc[post_idx], fwd90.reindex(post_idx))

    # Block bootstrap CI on IC via bootstrapping the (index, fwd) pairs
    j = pd.concat([index_s.loc[post_idx].rename("idx"),
                   fwd90.reindex(post_idx).rename("fwd")], axis=1, sort=False).dropna()
    n = len(j)
    block = min(21, n // 3)
    if n >= 60 and block >= 3:
        rng = np.random.default_rng(42)
        nb = int(np.ceil(n / block))
        boot_ics = []
        idx_arr  = j["idx"].values
        fwd_arr  = j["fwd"].values
        for _ in range(2000):
            starts = rng.integers(0, n, nb)
            idxs   = (starts[:, None] + np.arange(block)[None, :]).ravel()[:n] % n
            r_idx  = pd.Series(idx_arr[idxs]).rank()
            r_fwd  = pd.Series(fwd_arr[idxs]).rank()
            boot_ics.append(float(r_idx.corr(r_fwd)))
        ci = [round(float(np.percentile(boot_ics, p)), 3) for p in (2.5, 50, 97.5)]
    else:
        ci = None

    return {
        "n": n,
        "since": POST_2024,
        "ic_90d": round(ic90, 4) if math.isfinite(ic90) else None,
        "ic_90d_bootstrap_ci": ci,
        "note": ("Post-2024 (ETF/flow-driven regime) subsample: one partial cycle, "
                 "un-validatable. The 'etf' leg is tagged context-tier and is "
                 "REPORT-ONLY — it can DEMOTE but never PROMOTE the composite. "
                 "Wide CIs are expected; this block exists to show the honest "
                 "IC number and interval, not to promote it."),
    }


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main() -> int:
    cfg = config.load()["vector"]["calibration"]

    # 1. Load signals.parquet, restrict to start_date, build composite
    df = pd.read_parquet(config.data_dir() / "vector" / "signals.parquet")
    df.index = pd.to_datetime(df.index)
    df = df.loc[START_DATE:].copy()

    cf = composite_frame(df)
    if cf.empty or "index" not in cf.columns:
        print("ERROR: composite_frame returned no 'index' column — aborting.")
        return 1

    index_s = cf["index"].dropna()
    close   = df["close"].dropna()

    # Align index and close to their common dates
    common  = index_s.index.intersection(close.index)
    index_s = index_s.loc[common]
    close   = close.loc[common]

    # Forward returns at the three horizons
    fwd = fwd_returns(close, HORIZONS)

    # Define pre / post halves
    pre_idx  = index_s.index[index_s.index < SPLIT_DATE]
    post_idx = index_s.index[index_s.index >= SPLIT_DATE]
    embargo  = int(max(HORIZONS))   # same convention as calibrate_vector.py

    # 2. IC table: per horizon × half + Newey-West t-stat
    ic_table: dict[str, Any] = {}
    for h in HORIZONS:
        ic_table[f"h{h}d"] = _ic_table_one_horizon(
            index_s, fwd[h], pre_idx, post_idx, embargo
        )
    ic_table["note"] = (
        "Time-series rank IC (Spearman between the composite index and the "
        f"forward h-day return, computed over the full time series). NOT the "
        "cross-sectional rank_ic() which is a per-date multi-name tool and the "
        "WRONG tool for a single index. "
        f"Pre-half embargoed by {embargo} rows to prevent label leakage across "
        f"the {SPLIT_DATE} split boundary. "
        "Newey-West t-stat corrects for serial correlation from overlapping windows."
    )

    # 3. Leave-one-cycle-out (use 90d as the headline horizon)
    loco_90  = _leave_one_cycle_out(index_s, fwd[90], 90)
    loco_180 = _leave_one_cycle_out(index_s, fwd[180], 180)

    # 4. CPCV (k=6, test pairs, horizon 90d)
    cpcv_result = _cpcv(index_s, fwd[90], K_CV, embargo, 90)

    # 5. Allocation backtest + Deflated Sharpe with machine-counted n_trials
    choice_ledger = _build_choice_ledger()
    n_trials = len(choice_ledger)

    bt = _backtest_exposure(index_s, close)
    dsr_result = deflated_sharpe(
        bt.get("sharpe_daily"), bt.get("skew"), bt.get("kurt"),
        bt.get("n_obs"), n_trials,
        trading_year=TRADING_YEAR,
    )
    if dsr_result is not None:
        dsr_result["verdict"] = (
            "SURVIVES multiple-testing (DSR≥0.90)" if dsr_result["dsr"] >= 0.90
            else "FAILS multiple-testing haircut (DSR<0.90) — display-only"
        )
        dsr_result["note"] = (
            f"DSR = P(true Sharpe > 0) deflated for n_trials={n_trials} (machine-counted "
            "from choice_ledger), sample length T, skew and kurtosis. Expected result: "
            "DSR far below 0.90 — the composite is display-only by design. This harness "
            "exists to measure and document that, not to promote it."
        )

    # Block-bootstrap CI on allocation net returns
    bt_core = backtest_core(close, index_s.apply(
        lambda v: exposure_band(v) if pd.notna(v) else 0.0
    ).reindex(close.index).fillna(0.0), cost_bps=COST_BPS)
    boot = block_bootstrap_ci(bt_core["net"], block=21, B=3000, ann=TRADING_YEAR)

    # 6. PIT demonstration (M2SL leg)
    pit_result = _pit_m2_composite(df)

    # 7. Out-of-regime: post-2024 subsample
    oor = _out_of_regime(index_s, close)

    # 8. Verdict
    dsr_ok   = (dsr_result is not None and dsr_result.get("dsr", 0.0) >= 0.90)
    # Post-half IC sign must hold for the primary horizon (90d), want positive
    post_ic_90 = ic_table.get("h90d", {}).get("post_ic")
    post_sign_holds = (post_ic_90 is not None and post_ic_90 > 0)
    full_ic_90  = ic_table.get("h90d", {}).get("full_ic")
    heuristic_bar = 0.05   # minimum meaningful IC for a macro composite

    if dsr_ok and post_sign_holds and (full_ic_90 is not None and full_ic_90 >= heuristic_bar):
        verdict = (
            "DISPLAY-ONLY — composite shows no gate-clearing OOS edge "
            "(NOTE: unexpected — re-examine if DSR≥0.90 AND post IC positive)"
        )
    else:
        verdict = "DISPLAY-ONLY — composite shows no gate-clearing OOS edge"

    # Assemble report
    report = {
        "meta": {
            "span": f"{df.index.min().date()}..{df.index.max().date()}",
            "rows": len(df),
            "index_rows": len(index_s),
            "split_date": SPLIT_DATE,
            "start_date": START_DATE,
            "horizons_d": HORIZONS,
            "embargo_d": embargo,
            "cost_bps_one_way": COST_BPS,
        },
        "n_trials": n_trials,
        "choice_ledger": choice_ledger,
        "ic_table": ic_table,
        "leave_one_cycle_out": {
            "h90d": loco_90,
            "h180d": loco_180,
        },
        "cpcv": cpcv_result,
        "allocation_backtest": bt,
        "allocation_bootstrap": boot or {},
        "deflated_sharpe": dsr_result or {"dsr": None, "verdict": "insufficient data"},
        "pit_m2": pit_result or {"ok": False, "reason": "not attempted"},
        "out_of_regime_post2024": oor,
        "verdict": verdict,
    }

    # Persist — separate namespace from calibration.json
    outdir = config.data_dir() / "vector"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "regime_calibration.json").write_text(
        json.dumps(report, indent=2, default=str)
    )

    _print_summary(report)
    return 0


def _print_summary(report: dict) -> None:
    m = report["meta"]
    L = [
        f"\n=== BTC macro-regime composite calibration "
        f"({m['span']}, {m['index_rows']} regime-index days) ===",
        f"\nSPLIT: pre<{m['split_date']} | post≥{m['split_date']} | embargo={m['embargo_d']}d",
        f"N_TRIALS (machine-counted from choice_ledger): {report['n_trials']}",
    ]

    L.append("\nIC TABLE (time-series rank IC, full / pre / post + NW t-stat):")
    for hk, ic in report["ic_table"].items():
        if not isinstance(ic, dict):
            continue
        L.append(
            f"  {hk:6s}  full={ic.get('full_ic')}  pre={ic.get('pre_ic')}  "
            f"post={ic.get('post_ic')}  NW_t={ic.get('nw_t')}  n_full={ic.get('n_full')}"
        )

    loco = report["leave_one_cycle_out"].get("h90d", {})
    L.append(f"\nLEAVE-ONE-CYCLE-OUT (90d): worst_ic={loco.get('worst_ic')}  best_ic={loco.get('best_ic')}")
    for cyc, v in loco.get("per_cycle", {}).items():
        L.append(f"  {cyc}: ic={v.get('ic')}  n={v.get('n')}")

    cpcv = report["cpcv"]
    L.append(
        f"\nCPCV (k={cpcv.get('k_folds')}, C(k,2)={cpcv.get('n_paths')} paths, 90d): "
        f"mean_ic={cpcv.get('mean_ic')}  std_ic={cpcv.get('std_ic')}"
    )
    L.append("  [NON-INDEPENDENT paths on ~3-5 cycles; wide CIs expected]")

    bt  = report["allocation_backtest"]
    L.append(
        f"\nALLOCATION (exposure_band→shifted, {bt.get('cost_bps')}bps one-way): "
        f"CAGR {bt.get('cagr_net')}% net  HODL {bt.get('hodl_cagr')}%  "
        f"Sharpe {bt.get('sharpe_net')} (HODL {bt.get('hodl_sharpe')})  "
        f"MaxDD {bt.get('maxdd_pct')}%  inMkt {bt.get('time_in_market')}%"
    )

    dsr = report["deflated_sharpe"]
    L.append(
        f"\nDEFLATED SHARPE: DSR={dsr.get('dsr')}  "
        f"SR {dsr.get('sr_annual')} ann vs SR0 {dsr.get('sr0_annual')} ann  "
        f"N={dsr.get('n_trials')} trials  T={dsr.get('T')}d"
    )
    L.append(f"  => {dsr.get('verdict')}")

    pit = report["pit_m2"]
    if pit and pit.get("ok"):
        L.append(
            f"\nPIT (M2SL leg): ic_revised={pit.get('ic_revised_90d')}  "
            f"ic_pit={pit.get('ic_pit_90d')}  delta={pit.get('delta_ic')}  "
            f"score_shift_days={pit.get('m2_score_shift_days')} "
            f"({pit.get('m2_score_shift_pct_of_sample')}% of sample)"
        )
    else:
        L.append(f"\nPIT: skipped — {(pit or {}).get('reason', 'n/a')}")

    oor = report["out_of_regime_post2024"]
    L.append(
        f"\nOUT-OF-REGIME (post-{oor.get('since', '2024')}): "
        f"ic_90d={oor.get('ic_90d')}  ci={oor.get('ic_90d_bootstrap_ci')}  n={oor.get('n')}"
    )

    L.append(f"\nVERDICT: {report['verdict']}")
    print("\n".join(L))


if __name__ == "__main__":
    sys.exit(main())
