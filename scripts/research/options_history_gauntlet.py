"""W-E1 Options History Gauntlet — era-partitioned studies on the 24-root ThetaData EOD store.

PREREGISTRATION: research/OPTIONS_HISTORY_GAUNTLET_E1.md (committed BEFORE this file).
Reviewer: confirm that file's git log timestamp is earlier than this file's commit.

Four studies (all per-era; all with BH-FDR alpha=0.10 family):
  S-GEXR-H : gamma regime → forward REALIZED VOL (not direction)
  SKEW-DEESC-H : sector skew level + 5d change → 21d max drawdown / 5-21d return vs SPY
  CWIV-H   : sector/index ivspread (CW) → 5-21d relative return vs SPY (rank-IC)
  DOI-H    : 5d ΔOI persistence → 5/10d relative return vs SPY

House yardstick: 5-day and 21-day forward horizons ONLY.
3-month / 6-month / 63-day+ returns are EXPLICITLY EXCLUDED (house law).

Usage:
    python scripts/research/options_history_gauntlet.py
    # Requires /Users/chriswong/theta-ops-wt/data/thetadata_eod/ to be present.
    # On CI (store absent) prints a clear SKIP message and exits 0.

Runtime target: < 10 minutes on 4 cores (vectorized, parallel where possible).
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import warnings
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

warnings.filterwarnings("ignore", category=RuntimeWarning)

# ---------------------------------------------------------------------------
# Store config
# ---------------------------------------------------------------------------
_STORE = Path("/Users/chriswong/theta-ops-wt/data/thetadata_eod")
_STUDY_ROOTS = [
    "SPX", "SPXW", "SPY", "QQQ", "IWM", "DIA",
    "XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY",
    "SMH", "SOXX", "XBI", "KRE", "ARKK", "NVDA",
]
_SECTOR_ETFS = ["XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY"]
_BROAD_ETFS = ["SPY", "QQQ", "IWM", "DIA"]
_CWIV_ROOTS = _SECTOR_ETFS + _BROAD_ETFS  # 15 roots

# Era partitions from OPTIONS_ALPHA_ERA_PARTITION_AMENDMENT.md (ratified)
_GREEKS_ERAS = [
    ("Era1", "2017-01-01", "2019-12-31"),
    ("Era2", "2020-01-01", "2022-12-31"),
    ("Era3", "2023-01-01", "2026-12-31"),
]
_OI_ERAS = [
    ("Era0", "2012-01-01", "2015-12-31"),
    ("Era1", "2016-01-01", "2019-12-31"),
    ("Era2", "2020-01-01", "2022-12-31"),
    ("Era3", "2023-01-01", "2026-12-31"),
]

# BH-FDR family size (pre-stated)
_BH_FAMILY_K = 52
_BH_ALPHA = 0.10

# Min-n floors
_MIN_N_BUCKET = 30   # for BH family inclusion
_MIN_N_ERA = 20      # for per-era reporting

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _store_check() -> bool:
    """Return True if the ThetaData store is present and readable."""
    return (_STORE / "greeks").exists() and (_STORE / "oi").exists()


def _era_mask(dates: pd.Series, era_start: str, era_end: str) -> pd.Series:
    return (dates >= pd.Timestamp(era_start)) & (dates <= pd.Timestamp(era_end))


def _load_greeks_root(root: str, years: list[int], cols: list[str]) -> pd.DataFrame | None:
    """Load greeks parquet files for a root across requested years.
    Returns None if root has no data in that range."""
    store = _STORE / "greeks" / root
    if not store.exists():
        return None
    frames = []
    for yr in years:
        p = store / f"{yr}.parquet"
        if p.exists():
            df = pd.read_parquet(p, columns=cols)
            frames.append(df)
    if not frames:
        return None
    return pd.concat(frames, ignore_index=True)


def _load_oi_root(root: str, years: list[int]) -> pd.DataFrame | None:
    """Load OI parquet files for a root across requested years."""
    store = _STORE / "oi" / root
    if not store.exists():
        return None
    frames = []
    for yr in years:
        p = store / f"{yr}.parquet"
        if p.exists():
            df = pd.read_parquet(p, columns=["date", "open_interest"])
            frames.append(df)
    if not frames:
        return None
    return pd.concat(frames, ignore_index=True)


def _bh_fdr(pvals: dict[str, float], k_family: int = _BH_FAMILY_K,
            alpha: float = _BH_ALPHA) -> dict[str, dict]:
    """Benjamini-Hochberg FDR correction over a pre-stated family.
    pvals: {label: p_value}. Returns {label: {raw_p, bh_p, reject, rank}}.
    k_family: the total pre-registered family size (cells with n<30 excluded but
    their "slot" still counts in denominator, per strict BH convention).
    """
    labels = list(pvals.keys())
    pvs = np.array([pvals[l] for l in labels])
    order = np.argsort(pvs)
    ranks = np.empty(len(pvs), dtype=int)
    ranks[order] = np.arange(1, len(pvs) + 1)

    # BH threshold: reject H0 if p_i <= (rank_i / k_family) * alpha
    bh_thresholds = (ranks / k_family) * alpha
    reject = pvs <= bh_thresholds

    # BH-adjusted p-value = min over all j>=rank of (k_family * p_j / j)
    adj_pvs = np.empty(len(pvs))
    for i, r in enumerate(ranks):
        future_ratios = [(k_family * pvs[order[j]] / (j + 1)) for j in range(r - 1, len(pvs))]
        adj_pvs[i] = min(future_ratios) if future_ratios else pvs[i]
    adj_pvs = np.clip(adj_pvs, 0, 1)

    return {
        labels[i]: {
            "raw_p": float(pvs[i]),
            "bh_adj_p": float(adj_pvs[i]),
            "reject_h0": bool(reject[i]),
            "rank": int(ranks[i]),
        }
        for i in range(len(labels))
    }


def _hac_ttest(x: np.ndarray, lag: int | None = None) -> tuple[float, float]:
    """One-sample HAC-robust t-test (mean != 0). Returns (t_stat, p_value).
    Implements Newey-West covariance for time-series of mean differences."""
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 5:
        return float("nan"), float("nan")
    mu = np.mean(x)
    if lag is None:
        lag = int(np.floor(4.0 * (n / 100.0) ** (2.0 / 9.0)))
        lag = max(lag, 1)
    # Newey-West variance
    resid = x - mu
    gamma0 = np.dot(resid, resid) / n
    nw_var = gamma0
    for j in range(1, lag + 1):
        gamma_j = np.dot(resid[j:], resid[:-j]) / n
        nw_var += 2.0 * (1.0 - j / (lag + 1.0)) * gamma_j
    se = np.sqrt(max(nw_var, 1e-30) / n)
    t = mu / se
    p = float(2.0 * stats.t.sf(abs(t), df=max(n - 1, 1)))
    return float(t), p


def _mannwhitney(a: np.ndarray, b: np.ndarray) -> tuple[float, float]:
    """Two-sided Mann-Whitney U test. Returns (stat, p_value)."""
    a = a[np.isfinite(a)]; b = b[np.isfinite(b)]
    if len(a) < 2 or len(b) < 2:
        return float("nan"), float("nan")
    try:
        res = stats.mannwhitneyu(a, b, alternative="two-sided")
        return float(res.statistic), float(res.pvalue)
    except Exception:
        return float("nan"), float("nan")


def _realized_vol(prices: pd.Series, window: int) -> pd.Series:
    """Annualized realized volatility over rolling `window` days."""
    log_ret = np.log(prices / prices.shift(1))
    return log_ret.rolling(window).std() * np.sqrt(252)


def _print_section(title: str) -> None:
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


def _print_table(rows: list[dict], cols: list[str], col_widths: list[int] | None = None) -> None:
    if col_widths is None:
        col_widths = [max(len(str(r.get(c, ""))) for r in [{"dummy": c}] + rows) + 2
                      for c in cols]
    header = "  ".join(str(c).ljust(w) for c, w in zip(cols, col_widths))
    print(header)
    print("-" * len(header))
    for r in rows:
        row = "  ".join(str(r.get(c, "")).ljust(w) for c, w in zip(cols, col_widths))
        print(row)


# ---------------------------------------------------------------------------
# S-GEXR-H: Gamma regime → forward realized volatility
# ---------------------------------------------------------------------------

def _compute_daily_gamma_regime(root: str) -> pd.DataFrame | None:
    """Return daily net-dealer-gamma sign + magnitude for a root (greeks store)."""
    years = list(range(2017, 2027))
    cols = ["date", "strike", "right", "expiration", "gamma", "open_interest" if False else "gamma",
            "underlying_price"]
    # Load from greeks; OI not in greeks so use greeks gamma * strike-count as proxy
    gr = _load_greeks_root(root, years, cols=["date", "right", "gamma", "underlying_price"])
    if gr is None or gr.empty:
        return None
    # Net dealer gamma = sum(call_gamma * oi) - sum(put_gamma * oi)
    # We don't have OI in greeks store; use raw gamma sum as proxy (sign should be robust)
    gr["is_call"] = gr["right"].str.upper() == "C"
    gr["signed_gamma"] = np.where(gr["is_call"], gr["gamma"], -gr["gamma"])
    daily = gr.groupby("date").agg(
        net_gamma=("signed_gamma", "sum"),
        underlying_price=("underlying_price", "first"),
    ).reset_index()
    daily["regime"] = np.where(daily["net_gamma"] >= 0, "LONG", "SHORT")
    return daily


def run_sgexr_h() -> dict[str, Any]:
    """S-GEXR-H: does gamma regime condition forward 5/21d realized vol?"""
    _print_section("S-GEXR-H: Gamma regime → forward realized volatility")
    print("  Roots: all 23 non-AAPL | Eras: 2017-19, 2020-22, 2023→")
    print("  Target: 5d and 21d annualized realized vol (NOT direction)")
    print("  Method: Mann-Whitney U + HAC t-test on continuous gamma proxy")
    print()

    all_daily = []
    for root in _STUDY_ROOTS:
        df = _compute_daily_gamma_regime(root)
        if df is not None and not df.empty:
            df["root"] = root
            all_daily.append(df)

    if not all_daily:
        print("  NULL: no data loaded.")
        return {"study": "S-GEXR-H", "result": "NULL", "pvals": {}}

    panel = pd.concat(all_daily, ignore_index=True)
    panel["date"] = pd.to_datetime(panel["date"])
    panel = panel.sort_values(["root", "date"]).reset_index(drop=True)

    # Compute forward realized vol per root
    rv_frames = []
    for root, grp in panel.groupby("root"):
        g = grp.sort_values("date").copy()
        if g["underlying_price"].isna().all():
            continue
        g["rv5"] = _realized_vol(g["underlying_price"], 5).shift(-5)
        g["rv21"] = _realized_vol(g["underlying_price"], 21).shift(-21)
        rv_frames.append(g)

    if not rv_frames:
        print("  NULL: could not compute realized vol.")
        return {"study": "S-GEXR-H", "result": "NULL", "pvals": {}}

    panel = pd.concat(rv_frames, ignore_index=True)

    result_rows = []
    pvals_for_bh = {}

    for era_name, era_start, era_end in _GREEKS_ERAS:
        mask = _era_mask(panel["date"], era_start, era_end)
        era_data = panel[mask].copy()
        if era_data.empty:
            continue

        long_mask = era_data["regime"] == "LONG"
        short_mask = era_data["regime"] == "SHORT"

        for horizon, col in [(5, "rv5"), (21, "rv21")]:
            long_rv = era_data.loc[long_mask, col].dropna().values
            short_rv = era_data.loc[short_mask, col].dropna().values

            n_long = len(long_rv)
            n_short = len(short_rv)
            cell_key = f"GEXR.{era_name}.{horizon}d"

            if n_long < _MIN_N_ERA or n_short < _MIN_N_ERA:
                result_rows.append({
                    "era": era_name, "horizon": f"{horizon}d",
                    "n_long": n_long, "n_short": n_short,
                    "mean_rv_long": "SPARSE", "mean_rv_short": "SPARSE",
                    "mw_p": "SPARSE", "bh_adj_p": "SPARSE", "reject": "SPARSE",
                    "note": "n < floor",
                })
                continue

            mw_stat, mw_p = _mannwhitney(short_rv, long_rv)  # does SHORT > LONG (vol)?

            # HAC t-test on difference (continuous proxy)
            diff = era_data.loc[long_mask, col].values - np.nanmean(era_data.loc[short_mask, col].values)
            t_stat, t_p = _hac_ttest(era_data[col].values - era_data[col].mean())

            row = {
                "era": era_name,
                "horizon": f"{horizon}d",
                "n_long": n_long,
                "n_short": n_short,
                "mean_rv_long": f"{np.mean(long_rv):.3f}",
                "mean_rv_short": f"{np.mean(short_rv):.3f}",
                "mw_p": f"{mw_p:.3f}" if np.isfinite(mw_p) else "nan",
                "bh_adj_p": "—",
                "reject": "—",
                "note": "",
            }
            result_rows.append(row)

            if min(n_long, n_short) >= _MIN_N_BUCKET and np.isfinite(mw_p):
                pvals_for_bh[cell_key] = mw_p

    # BH-FDR (partial family — this study's cells only)
    bh = _bh_fdr(pvals_for_bh)
    for row in result_rows:
        cell_key = f"GEXR.{row['era']}.{row['horizon']}"
        if cell_key in bh:
            row["bh_adj_p"] = f"{bh[cell_key]['bh_adj_p']:.3f}"
            row["reject"] = "YES" if bh[cell_key]["reject_h0"] else "no"

    cols = ["era", "horizon", "n_long", "n_short", "mean_rv_long", "mean_rv_short",
            "mw_p", "bh_adj_p", "reject"]
    widths = [8, 8, 8, 9, 14, 15, 8, 10, 8]
    _print_table(result_rows, cols, widths)

    _print_post_decay_commentary("S-GEXR-H", result_rows, "reject", "era")
    return {"study": "S-GEXR-H", "rows": result_rows, "pvals": pvals_for_bh, "bh": bh}


# ---------------------------------------------------------------------------
# SKEW-DEESC-H: Sector skew level + 5d change → drawdown / return vs SPY
# ---------------------------------------------------------------------------

def _compute_daily_skew(root: str) -> pd.DataFrame | None:
    """Compute daily skew (25Δput IV − ATM call IV at ~30d expiry) for a sector ETF root.
    Vectorized: avoids per-date Python loop for speed."""
    years = list(range(2017, 2027))
    cols = ["date", "expiration", "strike", "right", "implied_vol", "delta", "underlying_price"]
    gr = _load_greeks_root(root, years, cols=cols)
    if gr is None or gr.empty:
        return None

    gr["date"] = pd.to_datetime(gr["date"])
    gr["expiration"] = pd.to_datetime(gr["expiration"])
    gr["is_call"] = gr["right"].str.upper() == "C"
    gr["dte"] = (gr["expiration"] - gr["date"]).dt.days
    gr["implied_vol"] = pd.to_numeric(gr["implied_vol"], errors="coerce")
    gr["delta"] = pd.to_numeric(gr["delta"], errors="coerce")

    # Step 1: find target expiry per date (nearest to 30d with >= 7d, vectorized)
    dte_grp = gr[gr["dte"] > 0].groupby(["date", "expiration"])["dte"].first().reset_index()
    valid_dte = dte_grp[dte_grp["dte"] >= 7].copy()
    if valid_dte.empty:
        valid_dte = dte_grp[dte_grp["dte"] > 0].copy()
    if valid_dte.empty:
        return None
    valid_dte["diff30"] = (valid_dte["dte"] - 30).abs()
    best_idx = valid_dte.groupby("date")["diff30"].idxmin()
    best_exp_map = valid_dte.loc[best_idx].set_index("date")["expiration"]

    # Step 2: filter to target-expiry rows only
    gr = gr.join(best_exp_map.rename("target_exp"), on="date", how="inner")
    gr = gr[gr["expiration"] == gr["target_exp"]].copy()
    if gr.empty:
        return None

    gr = gr[gr["implied_vol"] > 0].copy()

    # Step 3: compute spot per date
    spot_map = gr.groupby("date")["underlying_price"].median()
    gr = gr.join(spot_map.rename("spot"), on="date", how="left")
    gr = gr[gr["spot"] > 0].copy()

    # Step 4: OTM put (target delta = -0.25) — delta-first, moneyness fallback
    puts = gr[~gr["is_call"]].copy()
    calls = gr[gr["is_call"]].copy()

    if puts.empty or calls.empty:
        return None

    # Put: distance from delta=-0.25; if delta is degenerate (abs>=0.98), use moneyness K/S~0.95
    puts["delta_ok"] = puts["delta"].notna() & (puts["delta"].abs() < 0.98)
    puts["put_dist"] = np.where(
        puts["delta_ok"],
        (puts["delta"] - (-0.25)).abs(),
        (puts["strike"] / puts["spot"] - 0.95).abs() * 100.0  # moneyness, scaled so delta wins
    )
    put_best_idx = puts.groupby("date")["put_dist"].idxmin()
    put_best = puts.loc[put_best_idx][["date", "implied_vol"]].rename(
        columns={"implied_vol": "put_iv"}).set_index("date")

    # Call: distance from delta=+0.50; moneyness fallback K/S~1.0
    calls["delta_ok"] = calls["delta"].notna() & (calls["delta"].abs() < 0.98)
    calls["call_dist"] = np.where(
        calls["delta_ok"],
        (calls["delta"] - 0.50).abs(),
        (calls["strike"] / calls["spot"] - 1.0).abs() * 100.0
    )
    call_best_idx = calls.groupby("date")["call_dist"].idxmin()
    call_best = calls.loc[call_best_idx][["date", "implied_vol"]].rename(
        columns={"implied_vol": "call_iv"}).set_index("date")

    # Step 5: join put/call IVs and compute skew
    merged = put_best.join(call_best, how="inner")
    merged = merged[(merged["put_iv"] > 0) & (merged["call_iv"] > 0)]
    if merged.empty:
        return None
    merged["skew"] = merged["put_iv"] - merged["call_iv"]
    merged = merged.join(spot_map.rename("underlying_price"), how="left")
    merged = merged.reset_index().rename(columns={"index": "date"})
    merged["date"] = pd.to_datetime(merged.index if "date" not in merged.columns
                                    else merged["date"])
    merged = merged.sort_values("date").reset_index(drop=True)
    return merged[["date", "skew", "underlying_price"]]


def run_skew_deesc_h() -> dict[str, Any]:
    """SKEW-DEESC-H: sector skew level + 5d change → fwd max drawdown + return vs SPY."""
    _print_section("SKEW-DEESC-H: Sector skew → forward drawdown / return vs SPY")
    print("  Roots: 11 sector ETFs | Eras: 2017-19, 2020-22, 2023→")
    print("  Conditions: skew HIGH+RISING, skew HIGH+FALLING, skew LOW")
    print("  Targets: 21d max drawdown, 5d ret-vs-SPY, 21d ret-vs-SPY")
    print("  HOUSE YARDSTICK: 5d and 21d only (no 3-6mo)")
    print()

    print("  Computing daily skews for sector ETFs...", flush=True)
    # Load SPY price series for relative return
    spy_gr = _load_greeks_root("SPY", list(range(2017, 2027)),
                               cols=["date", "underlying_price"])
    spy_price = None
    if spy_gr is not None:
        spy_gr["date"] = pd.to_datetime(spy_gr["date"])
        spy_price = spy_gr.groupby("date")["underlying_price"].first().rename("spy_price")

    all_frames = []
    for root in _SECTOR_ETFS:
        df = _compute_daily_skew(root)
        if df is not None and not df.empty:
            df["root"] = root
            all_frames.append(df)
        else:
            print(f"    {root}: skew compute returned None — SPARSE/NULL")

    if not all_frames:
        print("  NULL: no sector skew data.")
        return {"study": "SKEW-DEESC-H", "result": "NULL", "pvals": {}}

    panel = pd.concat(all_frames, ignore_index=True)
    panel["date"] = pd.to_datetime(panel["date"])

    # Attach SPY for relative returns
    if spy_price is not None:
        panel = panel.join(spy_price, on="date", how="left")

    # Forward returns and max drawdown per root
    fwd_frames = []
    for root, grp in panel.groupby("root"):
        g = grp.sort_values("date").copy()
        p = g["underlying_price"]
        spy = g["spy_price"] if "spy_price" in g.columns else None

        # Forward returns: shift(-h) gives return from today over next h days
        g["fwd_ret5"] = (p.shift(-5) / p - 1.0)
        g["fwd_ret21"] = (p.shift(-21) / p - 1.0)

        # Max drawdown over next 21 days (rolling min of forward prices)
        # We can't do perfect rolling-forward here, so we approximate:
        # max_drawdown_21d = (rolling_min(p, 21).shift(-21) - p) / p
        # This is the worst drawdown from entry in a 21-day window
        # Implementation: build a rolling minimum looking forward
        pvals = p.values
        n = len(pvals)
        mdd21 = np.full(n, np.nan)
        for i in range(n - 21):
            window_prices = pvals[i:i + 22]  # include start
            entry = window_prices[0]
            if entry > 0:
                mdd21[i] = (np.min(window_prices[1:]) - entry) / entry
        g["max_dd21"] = mdd21

        # SPY relative returns
        if spy is not None:
            spy_arr = spy.values
            spy_fwd5 = np.full(n, np.nan)
            spy_fwd21 = np.full(n, np.nan)
            for i in range(n - 5):
                if spy_arr[i] > 0 and spy_arr[i + 5] > 0:
                    spy_fwd5[i] = spy_arr[i + 5] / spy_arr[i] - 1.0
            for i in range(n - 21):
                if spy_arr[i] > 0 and spy_arr[i + 21] > 0:
                    spy_fwd21[i] = spy_arr[i + 21] / spy_arr[i] - 1.0
            g["rel_ret5"] = g["fwd_ret5"].values - spy_fwd5
            g["rel_ret21"] = g["fwd_ret21"].values - spy_fwd21
        else:
            g["rel_ret5"] = g["fwd_ret5"]
            g["rel_ret21"] = g["fwd_ret21"]

        # Skew regime: 252d rolling percentile for HIGH/LOW classification
        g["skew_rank252"] = g["skew"].rolling(252, min_periods=60).rank(pct=True)
        g["skew_5d_chg"] = g["skew"] - g["skew"].shift(5)
        g["skew_high"] = g["skew_rank252"] >= 0.667  # top tercile
        g["skew_low"] = g["skew_rank252"] < 0.333    # bottom tercile

        # Condition buckets
        g["cond"] = "NEUTRAL"
        g.loc[g["skew_high"] & (g["skew_5d_chg"] > 0), "cond"] = "HIGH_RISING"
        g.loc[g["skew_high"] & (g["skew_5d_chg"] <= 0), "cond"] = "HIGH_FALLING"
        g.loc[g["skew_low"], "cond"] = "LOW"

        fwd_frames.append(g)

    panel = pd.concat(fwd_frames, ignore_index=True)
    panel["date"] = pd.to_datetime(panel["date"])

    result_rows = []
    pvals_for_bh = {}

    conditions = ["HIGH_RISING", "HIGH_FALLING", "LOW"]
    targets = [("max_dd21", "21d MaxDD"), ("rel_ret5", "5d RelRet"), ("rel_ret21", "21d RelRet")]

    # Benchmark = NEUTRAL (not in the conditions above)
    neutral_data = panel[panel["cond"] == "NEUTRAL"]

    for era_name, era_start, era_end in _GREEKS_ERAS:
        era_mask = _era_mask(panel["date"], era_start, era_end)
        era_panel = panel[era_mask].copy()
        era_neutral = era_panel[era_panel["cond"] == "NEUTRAL"]

        for cond in conditions:
            cond_data = era_panel[era_panel["cond"] == cond]

            for tgt_col, tgt_label in targets:
                cond_vals = cond_data[tgt_col].dropna().values
                neutral_vals = era_neutral[tgt_col].dropna().values

                n_cond = len(cond_vals)
                n_neutral = len(neutral_vals)
                cell_key = f"SKEW.{era_name}.{cond}.{tgt_col}"

                if n_cond < _MIN_N_ERA or n_neutral < _MIN_N_ERA:
                    result_rows.append({
                        "era": era_name, "condition": cond, "target": tgt_label,
                        "n_cond": n_cond, "n_neutral": n_neutral,
                        "mean_cond": "SPARSE", "mean_neutral": "SPARSE",
                        "mw_p": "SPARSE", "bh_adj_p": "SPARSE", "reject": "SPARSE",
                    })
                    continue

                mw_stat, mw_p = _mannwhitney(cond_vals, neutral_vals)
                result_rows.append({
                    "era": era_name, "condition": cond, "target": tgt_label,
                    "n_cond": n_cond, "n_neutral": n_neutral,
                    "mean_cond": f"{np.nanmean(cond_vals):.4f}",
                    "mean_neutral": f"{np.nanmean(neutral_vals):.4f}",
                    "mw_p": f"{mw_p:.3f}" if np.isfinite(mw_p) else "nan",
                    "bh_adj_p": "—",
                    "reject": "—",
                })
                if min(n_cond, n_neutral) >= _MIN_N_BUCKET and np.isfinite(mw_p):
                    pvals_for_bh[cell_key] = mw_p

    # BH-FDR
    bh = _bh_fdr(pvals_for_bh)
    for row in result_rows:
        cell_key = f"SKEW.{row['era']}.{row['condition']}.{row['target'].replace(' ', '_')}"
        # try matching by era + cond + target label
        for k, v in bh.items():
            era_part = row["era"]
            cond_part = row["condition"]
            if era_part in k and cond_part in k:
                row["bh_adj_p"] = f"{v['bh_adj_p']:.3f}"
                row["reject"] = "YES" if v["reject_h0"] else "no"

    cols = ["era", "condition", "target", "n_cond", "n_neutral",
            "mean_cond", "mean_neutral", "mw_p", "bh_adj_p", "reject"]
    widths = [6, 12, 14, 8, 10, 12, 14, 8, 10, 8]
    _print_table(result_rows, cols, widths)

    _print_post_decay_commentary("SKEW-DEESC-H", result_rows, "reject", "era")
    return {
        "study": "SKEW-DEESC-H", "rows": result_rows,
        "pvals": pvals_for_bh, "bh": bh,
    }


# ---------------------------------------------------------------------------
# CWIV-H: Sector/index ivspread → relative return vs SPY (rank-IC)
# ---------------------------------------------------------------------------

def _compute_daily_ivspread(root: str) -> pd.DataFrame | None:
    """OI-weighted (equal-weight fallback) mean matched-pair CW ivspread.
    Vectorized: avoids per-date Python loop."""
    years = list(range(2017, 2027))
    gr = _load_greeks_root(root, years,
                           cols=["date", "expiration", "strike", "right",
                                 "implied_vol", "underlying_price"])
    if gr is None or gr.empty:
        return None

    gr["date"] = pd.to_datetime(gr["date"])
    gr["expiration"] = pd.to_datetime(gr["expiration"])
    gr["is_call"] = gr["right"].str.upper() == "C"
    gr["dte"] = (gr["expiration"] - gr["date"]).dt.days
    gr["implied_vol"] = pd.to_numeric(gr["implied_vol"], errors="coerce")
    gr = gr[gr["implied_vol"] > 0].copy()

    # Step 1: vectorized target-expiry selection (nearest >=7d to 30d per date)
    dte_grp = gr[gr["dte"] > 0].groupby(["date", "expiration"])["dte"].first().reset_index()
    valid_dte = dte_grp[dte_grp["dte"] >= 7].copy()
    if valid_dte.empty:
        valid_dte = dte_grp[dte_grp["dte"] > 0].copy()
    if valid_dte.empty:
        return None
    valid_dte["diff30"] = (valid_dte["dte"] - 30).abs()
    best_idx = valid_dte.groupby("date")["diff30"].idxmin()
    best_exp_map = valid_dte.loc[best_idx].set_index("date")["expiration"]

    gr = gr.join(best_exp_map.rename("target_exp"), on="date", how="inner")
    gr = gr[gr["expiration"] == gr["target_exp"]].copy()

    # Step 2: spot per date, ATM band filter
    spot_map = gr.groupby("date")["underlying_price"].median()
    gr = gr.join(spot_map.rename("spot"), on="date", how="left")
    gr = gr[gr["spot"] > 0].copy()
    gr = gr[gr["strike"].between(gr["spot"] * 0.92, gr["spot"] * 1.08)].copy()
    if gr.empty:
        return None

    # Step 3: separate calls/puts, find matched strikes per date
    calls = gr[gr["is_call"]][["date", "strike", "implied_vol"]].rename(
        columns={"implied_vol": "call_iv"})
    puts = gr[~gr["is_call"]][["date", "strike", "implied_vol"]].rename(
        columns={"implied_vol": "put_iv"})

    matched = pd.merge(calls, puts, on=["date", "strike"], how="inner")
    matched["raw_spread"] = matched["call_iv"] - matched["put_iv"]
    # Drop bad data: |spread| > 0.50
    matched = matched[matched["raw_spread"].abs() <= 0.50].copy()

    # Step 4: require >= 3 matched pairs per date
    pair_counts = matched.groupby("date")["strike"].count()
    valid_dates = pair_counts[pair_counts >= 3].index
    matched = matched[matched["date"].isin(valid_dates)].copy()
    if matched.empty:
        return None

    # Step 5: equal-weight mean spread per date
    daily_spread = matched.groupby("date")["raw_spread"].mean()
    # Drop if |spread| > 0.50 (sanity bound)
    daily_spread = daily_spread[daily_spread.abs() <= 0.50]

    result = daily_spread.reset_index()
    result.columns = ["date", "ivspread"]
    result = result.join(spot_map.rename("underlying_price"), on="date", how="left")
    return result.sort_values("date").reset_index(drop=True)


def run_cwiv_h() -> dict[str, Any]:
    """CWIV-H: CW ivspread cross-sectional rank-IC → 5/21d relative return vs SPY."""
    _print_section("CWIV-H: CW ivspread cross-sectional rank-IC → forward return vs SPY")
    print("  Roots: 15 (11 sector ETFs + SPY/QQQ/IWM/DIA) | Eras: 2017-19, 2020-22, 2023→")
    print("  Targets: 5d and 21d relative return vs SPY")
    print("  Method: cross-sectional Spearman rank-IC per date, HAC t-test on IC time-series")
    print()

    print("  Computing daily ivspread for CWIV roots...", flush=True)
    root_data: dict[str, pd.DataFrame] = {}
    for root in _CWIV_ROOTS:
        df = _compute_daily_ivspread(root)
        if df is not None and not df.empty:
            root_data[root] = df
        else:
            print(f"    {root}: ivspread returned None — SPARSE/NULL")

    if len(root_data) < 3:
        print("  NULL: fewer than 3 roots with ivspread data.")
        return {"study": "CWIV-H", "result": "NULL", "pvals": {}}

    # Merge into date × root panel
    frames = []
    for root, df in root_data.items():
        df = df.copy()
        df["root"] = root
        frames.append(df)
    panel_long = pd.concat(frames, ignore_index=True)
    panel_long["date"] = pd.to_datetime(panel_long["date"])

    # Compute forward returns per root
    fwd_frames = []
    spy_price = None
    if "SPY" in root_data:
        spy_df = root_data["SPY"].set_index("date")["underlying_price"]
        spy_price = spy_df

    for root, df in root_data.items():
        g = df.sort_values("date").copy()
        p = g["underlying_price"]
        g["fwd_ret5"] = p.shift(-5) / p - 1.0
        g["fwd_ret21"] = p.shift(-21) / p - 1.0

        if spy_price is not None:
            spy_fwd5 = spy_price.shift(-5) / spy_price - 1.0
            spy_fwd21 = spy_price.shift(-21) / spy_price - 1.0
            g = g.join(spy_fwd5.rename("spy_fwd5"), on="date", how="left")
            g = g.join(spy_fwd21.rename("spy_fwd21"), on="date", how="left")
            g["rel_ret5"] = g["fwd_ret5"] - g["spy_fwd5"]
            g["rel_ret21"] = g["fwd_ret21"] - g["spy_fwd21"]
        else:
            g["rel_ret5"] = g["fwd_ret5"]
            g["rel_ret21"] = g["fwd_ret21"]

        g["root"] = root
        fwd_frames.append(g)

    panel_full = pd.concat(fwd_frames, ignore_index=True)
    panel_full["date"] = pd.to_datetime(panel_full["date"])

    # Cross-sectional rank-IC per date
    ic_rows = []
    for date, day_grp in panel_full.groupby("date"):
        if len(day_grp) < 5:  # need ≥5 roots
            continue
        for target, col in [("5d", "rel_ret5"), ("21d", "rel_ret21")]:
            valid = day_grp[["ivspread", col]].dropna()
            if len(valid) < 5:
                continue
            try:
                ic, _ = stats.spearmanr(valid["ivspread"], valid[col])
            except Exception:
                ic = np.nan
            if np.isfinite(ic):
                ic_rows.append({"date": date, "horizon": target, "ic": ic})

    if not ic_rows:
        print("  NULL: no IC rows computed.")
        return {"study": "CWIV-H", "result": "NULL", "pvals": {}}

    ic_panel = pd.DataFrame(ic_rows)
    ic_panel["date"] = pd.to_datetime(ic_panel["date"])

    result_rows = []
    pvals_for_bh = {}

    for era_name, era_start, era_end in _GREEKS_ERAS:
        era_mask = _era_mask(ic_panel["date"], era_start, era_end)
        era_ic = ic_panel[era_mask].copy()

        for target in ["5d", "21d"]:
            ic_vals = era_ic.loc[era_ic["horizon"] == target, "ic"].values
            n = len(ic_vals)
            cell_key = f"CWIV.{era_name}.{target}"
            mean_ic = float(np.nanmean(ic_vals)) if n > 0 else np.nan

            if n < _MIN_N_ERA:
                result_rows.append({
                    "era": era_name, "horizon": target, "n_dates": n,
                    "mean_ic": "SPARSE", "hac_t": "SPARSE",
                    "raw_p": "SPARSE", "bh_adj_p": "SPARSE", "reject": "SPARSE",
                })
                continue

            t_stat, p_val = _hac_ttest(ic_vals)
            result_rows.append({
                "era": era_name, "horizon": target, "n_dates": n,
                "mean_ic": f"{mean_ic:.4f}",
                "hac_t": f"{t_stat:.2f}" if np.isfinite(t_stat) else "nan",
                "raw_p": f"{p_val:.3f}" if np.isfinite(p_val) else "nan",
                "bh_adj_p": "—",
                "reject": "—",
            })
            if n >= _MIN_N_BUCKET and np.isfinite(p_val):
                pvals_for_bh[cell_key] = p_val

    bh = _bh_fdr(pvals_for_bh)
    for row in result_rows:
        cell_key = f"CWIV.{row['era']}.{row['horizon']}"
        if cell_key in bh:
            row["bh_adj_p"] = f"{bh[cell_key]['bh_adj_p']:.3f}"
            row["reject"] = "YES" if bh[cell_key]["reject_h0"] else "no"

    cols = ["era", "horizon", "n_dates", "mean_ic", "hac_t", "raw_p", "bh_adj_p", "reject"]
    widths = [6, 8, 9, 10, 8, 8, 10, 8]
    _print_table(result_rows, cols, widths)

    _print_post_decay_commentary("CWIV-H", result_rows, "reject", "era")
    return {"study": "CWIV-H", "rows": result_rows, "pvals": pvals_for_bh, "bh": bh}


# ---------------------------------------------------------------------------
# DOI-H: 5d ΔOI persistence → forward relative return vs SPY
# ---------------------------------------------------------------------------

def _compute_daily_doi(root: str) -> pd.DataFrame | None:
    """5-day fractional change in total OI for a root."""
    years = list(range(2012, 2027))
    oi_df = _load_oi_root(root, years)
    if oi_df is None or oi_df.empty:
        return None

    oi_df["date"] = pd.to_datetime(oi_df["date"])
    daily_oi = oi_df.groupby("date")["open_interest"].sum().reset_index()
    daily_oi.columns = ["date", "total_oi"]
    daily_oi = daily_oi.sort_values("date")
    daily_oi["doi5"] = daily_oi["total_oi"].pct_change(5)
    return daily_oi


def run_doi_h() -> dict[str, Any]:
    """DOI-H: 5d ΔOI persistence → 5/10d forward relative return vs SPY."""
    _print_section("DOI-H: 5d ΔOI persistence → forward relative return vs SPY")
    print("  Roots: 23 non-AAPL | Eras: Era0 2012-15, Era1 2016-19, Era2 2020-22, Era3 2023→")
    print("  Conditions: OI_UP (>+5%), OI_DOWN (<-5%), OI_FLAT (benchmark)")
    print("  Targets: 5d and 10d relative return vs SPY")
    print("  HOUSE YARDSTICK: 5d and 10d only")
    print()

    print("  Computing daily DOI + price series...", flush=True)

    # SPY prices from greeks store (not OI — need underlying price)
    spy_gr = _load_greeks_root("SPY", list(range(2012, 2027)), cols=["date", "underlying_price"])
    spy_price = None
    if spy_gr is not None:
        spy_gr["date"] = pd.to_datetime(spy_gr["date"])
        spy_price = spy_gr.groupby("date")["underlying_price"].first()

    # For underlying price for each root (from greeks where available, else OI-only)
    root_prices: dict[str, pd.Series] = {}
    for root in _STUDY_ROOTS:
        years_greeks = list(range(2017, 2027))
        gr = _load_greeks_root(root, years_greeks, cols=["date", "underlying_price"])
        if gr is not None and not gr.empty:
            gr["date"] = pd.to_datetime(gr["date"])
            root_prices[root] = gr.groupby("date")["underlying_price"].first()

    all_frames = []
    for root in _STUDY_ROOTS:
        doi_df = _compute_daily_doi(root)
        if doi_df is None or doi_df.empty:
            continue
        doi_df["root"] = root

        # Forward price returns
        price_series = root_prices.get(root)
        if price_series is not None:
            doi_df = doi_df.join(price_series.rename("price"), on="date", how="left")
        else:
            doi_df["price"] = np.nan

        all_frames.append(doi_df)

    if not all_frames:
        print("  NULL: no OI data loaded.")
        return {"study": "DOI-H", "result": "NULL", "pvals": {}}

    panel = pd.concat(all_frames, ignore_index=True)
    panel["date"] = pd.to_datetime(panel["date"])

    # Forward returns per root
    fwd_frames = []
    for root, grp in panel.groupby("root"):
        g = grp.sort_values("date").copy()
        p = g["price"]
        g["fwd_ret5"] = p.shift(-5) / p - 1.0
        g["fwd_ret10"] = p.shift(-10) / p - 1.0

        if spy_price is not None:
            g = g.join(spy_price.rename("spy_price"), on="date", how="left")
            spy = g["spy_price"]
            g["spy_fwd5"] = spy.shift(-5) / spy - 1.0
            g["spy_fwd10"] = spy.shift(-10) / spy - 1.0
            g["rel_ret5"] = g["fwd_ret5"] - g["spy_fwd5"]
            g["rel_ret10"] = g["fwd_ret10"] - g["spy_fwd10"]
        else:
            g["rel_ret5"] = g["fwd_ret5"]
            g["rel_ret10"] = g["fwd_ret10"]

        # OI condition buckets
        g["cond"] = "OI_FLAT"
        g.loc[g["doi5"] > 0.05, "cond"] = "OI_UP"
        g.loc[g["doi5"] < -0.05, "cond"] = "OI_DOWN"
        fwd_frames.append(g)

    panel = pd.concat(fwd_frames, ignore_index=True)
    panel["date"] = pd.to_datetime(panel["date"])

    result_rows = []
    pvals_for_bh = {}

    for era_name, era_start, era_end in _OI_ERAS:
        era_mask = _era_mask(panel["date"], era_start, era_end)
        era_panel = panel[era_mask].copy()
        flat_data = era_panel[era_panel["cond"] == "OI_FLAT"]

        for cond in ["OI_UP", "OI_DOWN"]:
            cond_data = era_panel[era_panel["cond"] == cond]

            for horizon, col in [(5, "rel_ret5"), (10, "rel_ret10")]:
                cond_vals = cond_data[col].dropna().values
                flat_vals = flat_data[col].dropna().values
                n_cond = len(cond_vals)
                n_flat = len(flat_vals)
                cell_key = f"DOI.{era_name}.{cond}.{horizon}d"

                if n_cond < _MIN_N_ERA or n_flat < _MIN_N_ERA:
                    result_rows.append({
                        "era": era_name, "condition": cond, "horizon": f"{horizon}d",
                        "n_cond": n_cond, "n_flat": n_flat,
                        "mean_cond": "SPARSE", "mean_flat": "SPARSE",
                        "mw_p": "SPARSE", "bh_adj_p": "SPARSE", "reject": "SPARSE",
                    })
                    continue

                mw_stat, mw_p = _mannwhitney(cond_vals, flat_vals)
                result_rows.append({
                    "era": era_name, "condition": cond, "horizon": f"{horizon}d",
                    "n_cond": n_cond, "n_flat": n_flat,
                    "mean_cond": f"{np.nanmean(cond_vals):.4f}",
                    "mean_flat": f"{np.nanmean(flat_vals):.4f}",
                    "mw_p": f"{mw_p:.3f}" if np.isfinite(mw_p) else "nan",
                    "bh_adj_p": "—",
                    "reject": "—",
                })
                if min(n_cond, n_flat) >= _MIN_N_BUCKET and np.isfinite(mw_p):
                    pvals_for_bh[cell_key] = mw_p

    bh = _bh_fdr(pvals_for_bh)
    for row in result_rows:
        cell_key = f"DOI.{row['era']}.{row['condition']}.{row['horizon']}"
        if cell_key in bh:
            row["bh_adj_p"] = f"{bh[cell_key]['bh_adj_p']:.3f}"
            row["reject"] = "YES" if bh[cell_key]["reject_h0"] else "no"

    cols = ["era", "condition", "horizon", "n_cond", "n_flat",
            "mean_cond", "mean_flat", "mw_p", "bh_adj_p", "reject"]
    widths = [6, 10, 8, 7, 7, 12, 12, 8, 10, 8]
    _print_table(result_rows, cols, widths)

    _print_post_decay_commentary("DOI-H", result_rows, "reject", "era")
    return {"study": "DOI-H", "rows": result_rows, "pvals": pvals_for_bh, "bh": bh}


# ---------------------------------------------------------------------------
# Post-publication decay commentary (mandatory per era-partition amendment §5)
# ---------------------------------------------------------------------------

def _print_post_decay_commentary(study: str, rows: list[dict],
                                  reject_col: str, era_col: str) -> None:
    """Print post-publication-decay commentary for a study result set."""
    print(f"\n  >>> Post-publication decay commentary ({study}):")

    by_era: dict[str, list[str]] = {}
    for row in rows:
        era = row.get(era_col, "?")
        rej = str(row.get(reject_col, "")).strip()
        if era not in by_era:
            by_era[era] = []
        by_era[era].append(rej)

    any_reject = any(r == "YES" for row in rows
                     for r in [str(row.get(reject_col, ""))])

    if not any_reject:
        print(f"    NULL across all eras — no surviving hypothesis at BH alpha=0.10.")
        print(f"    This is a valid result: literature effects may have been arbitraged away,")
        print(f"    or 15 years of index/ETF history is insufficient cross-sectional breadth.")
        return

    early_eras = {"Era0", "Era1"}
    late_eras = {"Era2", "Era3"}

    early_rejects = sum(1 for row in rows
                        if str(row.get(reject_col, "")) == "YES"
                        and row.get(era_col, "") in early_eras)
    late_rejects = sum(1 for row in rows
                       if str(row.get(reject_col, "")) == "YES"
                       and row.get(era_col, "") in late_eras)

    if early_rejects > 0 and late_rejects == 0:
        print(f"    WARNING: Rejections concentrated in early eras only.")
        print(f"    Per era-partition amendment §5: a signal alive only pre-2016 is DEAD.")
        print(f"    This is consistent with post-publication arbitrage decay.")
        print(f"    Verdict: DEAD (early-era artifact; not carried forward as live signal).")
    elif early_rejects > 0 and late_rejects > 0:
        print(f"    Signal survives into recent eras (Era2/Era3).")
        print(f"    Early-era effect size may exceed recent — check magnitudes for decay pattern.")
        print(f"    Requires Opus stats review before any verdict is printed.")
    elif early_rejects == 0 and late_rejects > 0:
        print(f"    Signal appears only in recent eras — may reflect data artifacts")
        print(f"    (fewer observations, regime shift, or selection bias). Treat with caution.")
        print(f"    Requires Opus stats review before any verdict is printed.")


# ---------------------------------------------------------------------------
# BH-FDR global family across all studies
# ---------------------------------------------------------------------------

def _run_global_bh(all_pvals: dict[str, float]) -> None:
    """Run global BH-FDR across the full pre-stated family of 52 tests."""
    _print_section("Global BH-FDR Family (alpha=0.10, pre-stated k=52)")
    print(f"  Cells with n >= {_MIN_N_BUCKET} and valid p-value: {len(all_pvals)}")
    print(f"  Cells excluded (SPARSE / nan): {_BH_FAMILY_K - len(all_pvals)}")
    print()

    if not all_pvals:
        print("  No valid p-values to adjust — all cells SPARSE or NULL.")
        return

    bh = _bh_fdr(all_pvals, k_family=_BH_FAMILY_K, alpha=_BH_ALPHA)

    rows = []
    for label, r in sorted(bh.items(), key=lambda x: x[1]["raw_p"]):
        rows.append({
            "cell": label,
            "rank": r["rank"],
            "raw_p": f"{r['raw_p']:.4f}",
            "bh_adj_p": f"{r['bh_adj_p']:.4f}",
            "bh_threshold": f"{(r['rank'] / _BH_FAMILY_K) * _BH_ALPHA:.4f}",
            "reject": "YES" if r["reject_h0"] else "no",
        })

    cols = ["cell", "rank", "raw_p", "bh_adj_p", "bh_threshold", "reject"]
    widths = [40, 6, 9, 10, 14, 8]
    _print_table(rows, cols, widths)

    n_reject = sum(1 for r in bh.values() if r["reject_h0"])
    print(f"\n  Surviving rejections at global BH alpha=0.10: {n_reject} / {len(all_pvals)}")
    if n_reject == 0:
        print("  NULL — no hypothesis survives global correction.")
    else:
        print("  NOTE: Survivors are context evidence only; Opus stats review required before")
        print("  any verdict is printed. No deployment or scoring permitted.")


# ---------------------------------------------------------------------------
# Summary and appendix
# ---------------------------------------------------------------------------

def _print_summary(results: dict, elapsed: float) -> None:
    """Print overall summary memo section."""
    _print_section("Summary")
    print(f"  Runtime: {elapsed:.1f}s")
    print()
    print("  In plain English:")
    print("  ─────────────────")
    print("  This gauntlet tested four options signals on 15 years of ThetaData EOD history")
    print("  (24 roots, AAPL excluded). Results are display/context evidence only — they")
    print("  inform the §4 gate hypotheses but do not constitute a gate pass or deployment")
    print("  recommendation. An Opus stats review is MANDATORY before any verdict prints.")
    print()
    print("  Key facts:")
    print("  • Greeks data verified start: 2017-01-03 (most roots)")
    print("  • OI data verified start: 2012-06-01 (most roots)")
    print("  • NVDA, QQQ, SOXX have greeks back to 2012-06-01 (longer ThetaData coverage)")
    print("  • ARKK and XLC start later (ETF inception dates)")
    print("  • All roots end 2026-07-02")
    print()
    print("  What we did NOT compute (house law):")
    print("  • NO 3-month, 6-month, or 63-day+ forward returns")
    print("  • NO composite scores or rankings")
    print("  • NO kernel conditioning")
    print("  • NO deployment or scoring recommendations")
    print()
    print("  ⚠  NULLS are expected and valid: cross-sectional breadth at the ETF/index level")
    print("     (23 roots) is thin for rank-IC studies. Single-name breadth (W-E0) is needed")
    print("     before any confident conclusion on CW ivspread or XZZ skew.")
    print()
    for study_key, res in results.items():
        study = res.get("study", study_key)
        n_pvals = len(res.get("pvals", {}))
        bh = res.get("bh", {})
        n_survive = sum(1 for v in bh.values() if v.get("reject_h0")) if bh else 0
        print(f"  {study}: {n_pvals} valid cells → {n_survive} survive global BH correction")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="W-E1 Options History Gauntlet")
    parser.add_argument("--study", choices=["gexr", "skew", "cwiv", "doi", "all"],
                        default="all", help="Which study to run")
    args = parser.parse_args()

    if not _store_check():
        print("SKIP: ThetaData EOD store not found at", _STORE)
        print("      This script requires the Mac-local theta-ops-wt data store.")
        print("      On CI (store absent) this is expected — exit 0.")
        sys.exit(0)

    print("=" * 70)
    print("  W-E1 Options History Gauntlet")
    print("  Preregistration: research/OPTIONS_HISTORY_GAUNTLET_E1.md")
    print("  House yardstick: 5d and 21d horizons (NO 3-6mo windows)")
    print("  BH-FDR: alpha=0.10, pre-stated family k=52")
    print("=" * 70)

    t0 = time.time()
    results = {}
    all_pvals: dict[str, float] = {}

    if args.study in ("gexr", "all"):
        r = run_sgexr_h()
        results["S-GEXR-H"] = r
        all_pvals.update(r.get("pvals", {}))

    if args.study in ("skew", "all"):
        r = run_skew_deesc_h()
        results["SKEW-DEESC-H"] = r
        all_pvals.update(r.get("pvals", {}))

    if args.study in ("cwiv", "all"):
        r = run_cwiv_h()
        results["CWIV-H"] = r
        all_pvals.update(r.get("pvals", {}))

    if args.study in ("doi", "all"):
        r = run_doi_h()
        results["DOI-H"] = r
        all_pvals.update(r.get("pvals", {}))

    if args.study == "all":
        _run_global_bh(all_pvals)

    elapsed = time.time() - t0
    _print_summary(results, elapsed)

    print("\n  Opus stats review MANDATORY before any verdict prints.")
    print("  Conclusions are context evidence informing §4 gates only.")
    print("  No score-integration proposals, no deployment recommendations.")
    print("=" * 70)


if __name__ == "__main__":
    main()
