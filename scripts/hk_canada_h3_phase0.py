"""
H3 — A/H Discount Tilt — Phase-0 backtest
Pre-registration: research/HK_CANADA_H3_PREREG.md
Trial family: hk_canada_h3  (program budget n_trials=30)
HK/Canada program W3 — H3

Gate pre-registration (verbatim from prereg §8):
  GO:     IC>0 both horizons; HAC-t ≥ 2.0 (3m IC & excess); L/S same sign; DSR≥0.90;
          split-half sign stability; survivorship robustness on ≥8-pair panel
  ACCRUE: IC>0 both horizons AND (HAC-t ≥ 1.5 at 3m) BUT (DSR<0.90 OR half-flip OR HAC-t<2.0)
  NO-GO:  IC ≤ 0 either horizon, OR sign disagreement 1m/3m, OR L/S sign negative vs positive long
  KILL:   IC < 0 with HAC-t ≥ 2.0 at 3m (backwards)

PIT discipline:
  - premium panel: daily closes (A and H close same day, no lag needed; monthend forms signal)
  - entry: NEXT trading day's close after month-end t (open proxy, look-ahead-free)
  - closes_deep last date: 2026-06-18 (15bd stale, does not touch graded cross-sections)
  - HSI: _HSI.parquet price index; H legs are dividend-adjusted TR (drift noted in prereg §2)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.trial_ledger import TrialLedger
from engine.validation import (
    benjamini_hochberg,
    block_bootstrap_ci,
    bootstrap_effective_t,
    cross_sectional_resid,
    deflated_sharpe,
    dsr_verdict,
    ic_summary,
    newey_west_tstat,
    rank_ic,
)

# ── Config grid (declare before any backtest) ──────────────────────────────
FAMILY = "hk_canada_h3"
N_TRIALS_PROGRAM = 30  # programme-level DSR budget (masterplan §6)

# Two decision trials × two horizons = 4 decision p-values
# Robustness variants R1-R4: NOT decision, NOT FDR-counted
GRID = [
    {"signal": "pctile", "horizon": "1m", "kind": "decision"},
    {"signal": "pctile", "horizon": "3m", "kind": "decision"},
    {"signal": "d1y",    "horizon": "1m", "kind": "decision"},
    {"signal": "d1y",    "horizon": "3m", "kind": "decision"},
    # R1 portfolio width variants
    {"signal": "pctile", "horizon": "3m", "kind": "robustness", "variant": "R1_top3"},
    {"signal": "pctile", "horizon": "3m", "kind": "robustness", "variant": "R1_top7"},
    # R2 window length variant
    {"signal": "pctile_756d", "horizon": "3m", "kind": "robustness", "variant": "R2_756d"},
    # R3 size-residualized IC (reported, not decision)
    {"signal": "pctile_resid", "horizon": "3m", "kind": "robustness", "variant": "R3_size_resid"},
    # R4 split-half (pre/post 2021) — two sub-periods
    {"signal": "pctile", "horizon": "3m", "kind": "robustness", "variant": "R4_pre2021"},
    {"signal": "pctile", "horizon": "3m", "kind": "robustness", "variant": "R4_post2021"},
]

# ── Data paths ─────────────────────────────────────────────────────────────
DATA = ROOT / "data"
PANEL_DIR = DATA / "hk_ah_panel"
HK_DIR = DATA / "hk"
HK_SEARCH = DATA / "hk_search"


def load_data():
    """Load premium panel, pairs map, H-leg closes, HSI."""
    prem = pd.read_parquet(PANEL_DIR / "premium.parquet")
    prem.index = pd.to_datetime(prem.index)

    with open(PANEL_DIR / "pairs.json") as f:
        pairs = json.load(f)

    closes = pd.read_parquet(HK_SEARCH / "closes_deep.parquet")
    closes.index = pd.to_datetime(closes.index)

    hsi = pd.read_parquet(HK_DIR / "_HSI.parquet")[["close"]]
    hsi.index = pd.to_datetime(hsi.index)
    hsi.columns = ["hsi"]

    return prem, pairs, closes, hsi


def build_own_history_pctile(prem: pd.DataFrame, window: int = 504,
                              min_obs: int = 252) -> pd.DataFrame:
    """
    For each pair j and date t: percentile rank of prem[j,t] within its trailing
    `window`-day own history, requiring >= min_obs non-NaN observations.
    High pctile = H unusually cheap vs own norm = long candidate.
    """
    result = pd.DataFrame(index=prem.index, columns=prem.columns, dtype=float)
    arr = prem.values
    cols = prem.columns.tolist()

    for ci, col in enumerate(cols):
        s = arr[:, ci]
        for ti in range(len(prem)):
            lo = max(0, ti - window + 1)
            window_vals = s[lo:ti + 1]
            valid = window_vals[~np.isnan(window_vals)]
            if len(valid) < min_obs:
                result.iloc[ti, ci] = np.nan
            else:
                v = s[ti]
                if np.isnan(v):
                    result.iloc[ti, ci] = np.nan
                else:
                    # percentile rank of current value within window
                    rank = (valid < v).sum() + 0.5 * (valid == v).sum()
                    result.iloc[ti, ci] = rank / len(valid)
    return result


def build_d1y(prem: pd.DataFrame) -> pd.DataFrame:
    """1y premium change: P[t] - P[t-252]. Positive = premium widened = H got cheaper."""
    return prem - prem.shift(252)


def get_month_ends(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Return all month-end dates in the index."""
    # Resample to business month end, keep only actual traded dates
    # Use last traded date per calendar month
    df = pd.DataFrame({"d": 1}, index=index)
    me = df.resample("BME").last()
    # Filter to dates actually in the original index
    return me.index.intersection(index)


def next_valid_print(closes_col: pd.Series, after_date, max_lag: int = 5) -> float | None:
    """Return price of first valid close strictly after `after_date`, within max_lag sessions."""
    idx = closes_col.index
    future = idx[idx > after_date]
    for d in future[:max_lag]:
        v = closes_col.loc[d]
        if pd.notna(v):
            return v, d
    return None, None


def build_forward_returns(
    closes: pd.DataFrame,
    hsi: pd.Series,
    month_ends: pd.DatetimeIndex,
    pairs: list[dict],
    h_cols: list[str],
    horizon_bd: int,
):
    """
    For each month-end t in month_ends:
      - entry = next valid H close strictly after t (within 5 sessions)
      - exit = H close h trading-bars after entry (real close, no forward-fill across halts)
      - excess_j = (H exit/entry - 1) - (HSI exit/entry - 1)
    Returns DataFrame (month_ends x h_cols) of excess returns.
    Benchmark HSI uses actual traded HSI closes only (no forward fill).
    """
    hsi_aligned = hsi.reindex(closes.index)  # no fill — use actual traded HSI closes only

    records = []
    for t in month_ends:
        row = {"date": t}
        # Get HSI entry
        hsi_vals = hsi.loc[hsi.index > t]
        if len(hsi_vals) == 0:
            continue
        hsi_entry_date = hsi_vals.index[0]
        hsi_entry = hsi_vals.iloc[0]

        # Get HSI exit = hsi_entry_date + horizon_bd (use actual closes, not forward fill)
        hsi_future = hsi.loc[hsi.index > hsi_entry_date]
        if len(hsi_future) < horizon_bd:
            continue
        hsi_exit = hsi_future.iloc[horizon_bd - 1]
        hsi_ret = hsi_exit / hsi_entry - 1

        for col in h_cols:
            h_close = closes[col]
            # Entry: next valid close strictly after t, within 5 sessions
            entry_val, entry_date = next_valid_print(h_close, t, max_lag=5)
            if entry_val is None or entry_date is None:
                row[col] = np.nan
                continue

            # Exit: h_close horizon_bd sessions after entry_date (strictly, no ffill)
            h_future = h_close.loc[h_close.index > entry_date]
            h_future_valid = h_future.dropna()
            if len(h_future_valid) < horizon_bd:
                row[col] = np.nan
                continue
            exit_val = h_future_valid.iloc[horizon_bd - 1]

            h_ret = exit_val / entry_val - 1
            row[col] = h_ret - hsi_ret

        records.append(row)

    if not records:
        return pd.DataFrame(columns=["date"] + h_cols).set_index("date")

    df = pd.DataFrame(records).set_index("date")
    return df


def top5_rank_weighted_excess(signal_row: pd.Series, fwd_row: pd.Series, k: int = 5) -> float:
    """
    Rank-weighted long top-k H legs by signal (highest signal = deepest discount).
    Weights ∝ rank within top-k, normalized to sum 1.
    Returns the weighted excess return (or NaN if fewer than 2 valid pairs).
    """
    valid = signal_row.dropna().index.intersection(fwd_row.dropna().index)
    if len(valid) < 2:
        return np.nan

    sig = signal_row[valid].sort_values(ascending=False)
    topk = sig.head(k).index
    if len(topk) < 2:
        return np.nan

    ranks = np.arange(len(topk), 0, -1, dtype=float)  # highest signal = highest rank
    weights = ranks / ranks.sum()

    excess_vals = fwd_row[topk].values
    if np.any(np.isnan(excess_vals)):
        # Drop NaN, re-weight
        valid_mask = ~np.isnan(excess_vals)
        if valid_mask.sum() < 2:
            return np.nan
        ranks_valid = ranks[valid_mask]
        weights = ranks_valid / ranks_valid.sum()
        excess_vals = excess_vals[valid_mask]

    return float(np.dot(weights, excess_vals))


def tercile_ls_excess(signal_row: pd.Series, fwd_row: pd.Series) -> float:
    """
    Top-tercile minus bottom-tercile equal-weight H legs (dividend-neutral L/S).
    Both legs are H-leg TR, so dividend drift cancels.
    """
    valid = signal_row.dropna().index.intersection(fwd_row.dropna().index)
    if len(valid) < 3:
        return np.nan

    sig = signal_row[valid].sort_values(ascending=False)
    n = len(sig)
    t = max(1, n // 3)

    top_names = sig.head(t).index
    bot_names = sig.tail(t).index

    top_ret = fwd_row[top_names].mean()
    bot_ret = fwd_row[bot_names].mean()

    if pd.isna(top_ret) or pd.isna(bot_ret):
        return np.nan
    return float(top_ret - bot_ret)


def run_trial(
    sig_panel: pd.DataFrame,
    fwd_panel: pd.DataFrame,
    month_ends: pd.DatetimeIndex,
    signal_name: str,
    horizon_label: str,
    top_k: int = 5,
) -> dict:
    """
    For a given signal panel and forward return panel, compute all decision stats.
    Returns dict of results.
    """
    # Align signal to rebalance dates (use signal at month-end t)
    # Signal formed at t, entry is t+1, so signal[t] drives the rebalance
    common_dates = month_ends.intersection(sig_panel.index).intersection(fwd_panel.index)

    ics = []
    top5_series = []
    ls_series = []
    pair_counts = []

    for t in common_dates:
        sig_row = sig_panel.loc[t]
        fwd_row = fwd_panel.loc[t]

        valid = sig_row.dropna().index.intersection(fwd_row.dropna().index)
        pair_counts.append(len(valid))
        if len(valid) < 3:
            ics.append(np.nan)
            top5_series.append(np.nan)
            ls_series.append(np.nan)
            continue

        ic = rank_ic(sig_row[valid], fwd_row[valid])
        ics.append(ic)
        top5_series.append(top5_rank_weighted_excess(sig_row, fwd_row, k=top_k))
        ls_series.append(tercile_ls_excess(sig_row, fwd_row))

    ics = np.array(ics, dtype=float)
    top5_arr = np.array(top5_series, dtype=float)
    ls_arr = np.array(ls_series, dtype=float)
    dates_arr = np.array(common_dates)

    # --- IC summary ---
    ics_clean = ics[~np.isnan(ics)]
    ic_mean = float(np.mean(ics_clean)) if len(ics_clean) > 0 else np.nan
    ic_std = float(np.std(ics_clean, ddof=1)) if len(ics_clean) > 1 else np.nan
    ic_ir = ic_mean / ic_std if ic_std and ic_std > 0 else np.nan
    ic_hitrate = float(np.mean(ics_clean > 0)) if len(ics_clean) > 0 else np.nan

    # NW HAC-t on IC series (lags: 2 for 3m, 1 for 1m, following prereg §4)
    nw_lags = 2 if "3m" in horizon_label else 1
    ic_nw = newey_west_tstat(pd.Series(ics_clean).dropna().values, lags=nw_lags)
    ic_hac_t = ic_nw.get("t", np.nan)  # key is "t", not "t_stat"
    if ic_hac_t is None:
        ic_hac_t = np.nan

    # --- Top-5 excess series ---
    top5_clean = top5_arr[~np.isnan(top5_arr)]
    top5_mean = float(np.mean(top5_clean)) if len(top5_clean) > 0 else np.nan
    top5_nw = newey_west_tstat(top5_clean, lags=nw_lags)
    top5_hac_t = top5_nw.get("t", np.nan)  # key is "t", not "t_stat"
    if top5_hac_t is None:
        top5_hac_t = np.nan

    # block-bootstrap effective-t (block=3 for 3m overlap, 1 for 1m)
    block = 3 if "3m" in horizon_label else 1
    bt_result = bootstrap_effective_t(pd.Series(top5_clean), block=block)
    t_eff = bt_result.get("t_eff", np.nan)  # key is t_eff (int), n_eff not returned
    n_eff = bt_result.get("t_raw", len(top5_clean))  # fallback to raw n

    # --- L/S tercile (dividend-neutral sign check) ---
    ls_clean = ls_arr[~np.isnan(ls_arr)]
    ls_mean = float(np.mean(ls_clean)) if len(ls_clean) > 0 else np.nan

    # --- DSR (only on primary 3m, using programme ledger for n_trials) ---
    # NOTE: dsr_val is set by caller after getting led; we return top5_clean for that.
    # For now, store raw series for external DSR call.
    dsr_val = np.nan
    dsr_verd = "N/A"

    return {
        "signal": signal_name,
        "horizon": horizon_label,
        "n_rebalances": len(common_dates),
        "n_ic_obs": len(ics_clean),
        "median_pair_count": float(np.median(pair_counts)),
        # IC stats
        "ic_mean": ic_mean,
        "ic_std": ic_std,
        "ic_ir": ic_ir,
        "ic_hitrate": ic_hitrate,
        "ic_hac_t": ic_hac_t,
        "ic_nw_lags": nw_lags,
        # Top-5 excess stats
        "top5_excess_mean": top5_mean,
        "top5_excess_ann_pct": top5_mean * 12 * 100 if not np.isnan(top5_mean) else np.nan,
        "top5_hac_t": top5_hac_t,
        "t_eff": t_eff,
        "n_eff": n_eff,
        # L/S
        "ls_tercile_mean": ls_mean,
        # DSR
        "dsr": dsr_val,
        "dsr_verdict": dsr_verd,
        # Raw series for split-half
        "_ics": ics,
        "_top5": top5_arr,
        "_ls": ls_arr,
        "_dates": dates_arr,
    }


def split_half_sign(series: np.ndarray, dates: np.ndarray, split_date=None) -> dict:
    """Check sign stability across median-date split and pre/post split_date split."""
    valid_mask = ~np.isnan(series)
    s = series[valid_mask]
    d = np.array(dates[valid_mask], dtype="datetime64[D]")

    if len(s) < 4:
        return {"h1_mean": np.nan, "h2_mean": np.nan,
                "pre_mean": np.nan, "post_mean": np.nan,
                "h1h2_same_sign": False, "presplit_same_sign": False}

    # Median-date split: use the sorted-position midpoint, not arithmetic median
    sorted_d = np.sort(d)
    mid = sorted_d[len(sorted_d) // 2]  # sorted middle date
    h1 = s[d <= mid]
    h2 = s[d > mid]

    result = {
        "h1_mean": float(np.mean(h1)) if len(h1) > 0 else np.nan,
        "h2_mean": float(np.mean(h2)) if len(h2) > 0 else np.nan,
        "h1h2_same_sign": bool(np.sign(np.mean(h1)) == np.sign(np.mean(h2)))
        if len(h1) > 0 and len(h2) > 0 else False,
    }

    if split_date is not None:
        sd = np.datetime64(pd.Timestamp(split_date), "D")
        pre = s[d < sd]
        post = s[d >= sd]
        result["pre_mean"] = float(np.mean(pre)) if len(pre) > 0 else np.nan
        result["post_mean"] = float(np.mean(post)) if len(post) > 0 else np.nan
        result["presplit_same_sign"] = bool(
            np.sign(np.mean(pre)) == np.sign(np.mean(post))
        ) if len(pre) > 0 and len(post) > 0 else False
    else:
        result["pre_mean"] = np.nan
        result["post_mean"] = np.nan
        result["presplit_same_sign"] = False

    return result


def main():
    print("=" * 70)
    print("H3 — A/H Discount Tilt — Phase-0")
    print("PRE-REGISTRATION: research/HK_CANADA_H3_PREREG.md")
    print("Family:", FAMILY, "| n_trials (program):", N_TRIALS_PROGRAM)
    print("=" * 70)

    # ── Step 1: Log full trial grid BEFORE any backtest ──────────────────
    led = TrialLedger(family=FAMILY)
    n_logged = led.log_grid(GRID, family=FAMILY, info_cutoff="2026-07-03")
    # Log the declared programme budget (floor for DSR haircut, per masterplan §6)
    led.log_declared_budget(
        N_TRIALS_PROGRAM, family=FAMILY,
        reason="HK/Canada masterplan §6 programme budget (all configs across both markets)"
    )
    eff_n = led.effective_n(FAMILY)
    print(f"\nTrialLedger: logged {n_logged} new configs to data/trial_ledger.jsonl")
    print(f"TrialLedger: declared budget={N_TRIALS_PROGRAM}, effective_n={eff_n}")

    # ── Step 2: Load data ─────────────────────────────────────────────────
    print("\nLoading data...")
    prem, pairs, closes, hsi_df = load_data()
    hsi = hsi_df["hsi"]

    h_cols = [p["h"] for p in pairs]
    pair_joint_starts = {p["h"]: pd.Timestamp(p["joint_start"]) for p in pairs}

    print(f"  Premium panel: {prem.shape[0]} rows × {prem.shape[1]} pairs")
    print(f"  Premium range: {prem.index[0].date()} → {prem.index[-1].date()}")
    print(f"  H closes: {closes.shape[0]} rows × {closes.shape[1]} names")
    print(f"  HSI: {hsi_df.shape[0]} rows, {hsi.index[0].date()} → {hsi.index[-1].date()}")

    # Apply inception-honest masking: each pair enters only from joint_start
    prem_pit = prem.copy()
    for col in h_cols:
        js = pair_joint_starts.get(col)
        if js is not None:
            prem_pit.loc[prem_pit.index < js, col] = np.nan

    # ── Step 3: Build signal panels ───────────────────────────────────────
    print("\nBuilding own-history percentile signal (504d window, ≥252 obs required)...")
    print("  (This may take ~60 seconds for 25 pairs × 5711 dates)")
    pctile_504 = build_own_history_pctile(prem_pit, window=504, min_obs=252)

    print("Building 756d window variant (R2)...")
    pctile_756 = build_own_history_pctile(prem_pit, window=756, min_obs=252)

    print("Building 1y premium change (d1y) signal...")
    d1y = build_d1y(prem_pit)

    # Get all month-ends with ≥5 pairs available
    month_ends_all = get_month_ends(prem.index)
    n_pairs_per_me = pctile_504.loc[month_ends_all].notna().sum(axis=1)
    # Graded window: first month with ≥8 pairs
    me_ge8 = month_ends_all[n_pairs_per_me >= 8]
    me_ge5 = month_ends_all[n_pairs_per_me >= 5]
    print(f"\nMonth-ends total: {len(month_ends_all)}")
    print(f"Month-ends ≥5 pairs: {len(me_ge5)} (first: {me_ge5[0].date() if len(me_ge5) else 'N/A'})")
    print(f"Month-ends ≥8 pairs: {len(me_ge8)} (first: {me_ge8[0].date() if len(me_ge8) else 'N/A'})")

    # ── Step 4: Build forward return panels ──────────────────────────────
    print("\nBuilding 1m (21bd) forward H-excess returns...")
    fwd_1m = build_forward_returns(closes, hsi, me_ge8, pairs, h_cols, horizon_bd=21)
    print(f"  1m fwd panel: {fwd_1m.shape}")

    print("Building 3m (63bd) forward H-excess returns...")
    fwd_3m = build_forward_returns(closes, hsi, me_ge8, pairs, h_cols, horizon_bd=63)
    print(f"  3m fwd panel: {fwd_3m.shape}")

    # ── Step 5: Signal vs forward aligned at month-ends ──────────────────
    pctile_me = pctile_504.reindex(me_ge8)
    pctile_756_me = pctile_756.reindex(me_ge8)
    d1y_me = d1y.reindex(me_ge8)

    # ── Step 6: Run decision trials ───────────────────────────────────────
    print("\n" + "=" * 70)
    print("DECISION TRIALS")
    print("=" * 70)

    res_pa_1m = run_trial(pctile_me, fwd_1m, me_ge8, "pctile", "1m")
    res_pa_3m = run_trial(pctile_me, fwd_3m, me_ge8, "pctile", "3m")
    res_pb_1m = run_trial(d1y_me, fwd_1m, me_ge8, "d1y", "1m")
    res_pb_3m = run_trial(d1y_me, fwd_3m, me_ge8, "d1y", "3m")

    # Compute DSR on 3m top-5 excess series using ledger (honest n_trials path)
    from scipy.stats import skew as sp_skew, kurtosis as sp_kurt
    for res in [res_pa_3m, res_pb_3m]:
        top5_clean = res["_top5"][~np.isnan(res["_top5"])]
        if len(top5_clean) > 5:
            try:
                monthly_mean = float(np.mean(top5_clean))
                monthly_std = float(np.std(top5_clean, ddof=1))
                if monthly_std > 0:
                    monthly_sr = monthly_mean / monthly_std
                    ann_sr = monthly_sr * np.sqrt(12)
                    sk = float(sp_skew(top5_clean))
                    ku = float(sp_kurt(top5_clean))  # excess kurtosis
                    T_monthly = len(top5_clean)
                    t_eff_val = res.get("t_eff", np.nan)
                    t_eff_int = int(t_eff_val) if not np.isnan(t_eff_val) else None
                    dsr_dict = deflated_sharpe(
                        sr_daily=ann_sr / np.sqrt(252),
                        skew=sk,
                        kurt=ku,
                        T=T_monthly * 21,
                        ledger=led,
                        family=FAMILY,
                        t_eff=t_eff_int,
                    )
                    if dsr_dict is not None:
                        res["dsr"] = dsr_dict.get("dsr", np.nan)
                        res["dsr_verdict"] = dsr_verdict(res["dsr"]) if not np.isnan(res["dsr"]) else "N/A"
            except Exception as e:
                print(f"  DSR computation error for {res['signal']} {res['horizon']}: {e}")

    def print_result(r, label):
        print(f"\n{label}")
        print(f"  n_rebalances: {r['n_rebalances']}, n_ic_obs: {r['n_ic_obs']}, "
              f"median_pair_count: {r['median_pair_count']:.1f}")
        print(f"  IC mean: {r['ic_mean']:.4f}, IC-IR: {r['ic_ir']:.3f}, "
              f"IC hitrate: {r['ic_hitrate']:.3f}, HAC-t(IC): {r['ic_hac_t']:.3f}")
        print(f"  Top-5 excess mean: {r['top5_excess_mean']:.4f} "
              f"({r['top5_excess_ann_pct']:.2f}% ann), HAC-t: {r['top5_hac_t']:.3f}")
        print(f"  L/S tercile mean: {r['ls_tercile_mean']:.4f}")
        print(f"  n_eff: {r['n_eff']:.1f}, t_eff: {r['t_eff']:.3f}")
        print(f"  DSR: {r['dsr']:.4f} ({r['dsr_verdict']}) " if not np.isnan(r['dsr'])
              else f"  DSR: N/A ({r['dsr_verdict']})")

    print_result(res_pa_1m, "TRIAL (a) PRIMARY — own-history pctile @ 1m")
    print_result(res_pa_3m, "TRIAL (a) PRIMARY — own-history pctile @ 3m")
    print_result(res_pb_1m, "TRIAL (b) SECONDARY — 1y premium change (d1y) @ 1m")
    print_result(res_pb_3m, "TRIAL (b) SECONDARY — 1y premium change (d1y) @ 3m")

    # ── Step 7: BH-FDR across 4 decision p-values ─────────────────────────
    print("\n" + "=" * 70)
    print("BH-FDR (α=0.10, 4 p-values: trials a+b × 1m+3m)")
    print("=" * 70)
    from scipy.stats import t as tdist

    def nw_pval(t_stat, n_obs, lags):
        if t_stat is None or np.isnan(t_stat) or n_obs < 3:
            return 1.0
        df = max(1, n_obs - lags - 1)
        return float(2 * tdist.sf(abs(t_stat), df=df))

    pval_pa_1m = nw_pval(res_pa_1m["ic_hac_t"], res_pa_1m["n_ic_obs"], 1)
    pval_pa_3m = nw_pval(res_pa_3m["ic_hac_t"], res_pa_3m["n_ic_obs"], 2)
    pval_pb_1m = nw_pval(res_pb_1m["ic_hac_t"], res_pb_1m["n_ic_obs"], 1)
    pval_pb_3m = nw_pval(res_pb_3m["ic_hac_t"], res_pb_3m["n_ic_obs"], 2)

    bh_input = {
        "pctile_1m": pval_pa_1m,
        "pctile_3m": pval_pa_3m,
        "d1y_1m": pval_pb_1m,
        "d1y_3m": pval_pb_3m,
    }
    bh_result = benjamini_hochberg(bh_input, alpha=0.10)

    print("  p-values (NW HAC two-sided on IC):")
    for k, v in bh_input.items():
        _v = bh_result.get(k, {})
        sig = "*" if (isinstance(_v, dict) and _v.get("reject", False)) else ""
        print(f"    {k}: p={v:.4f} {sig}")
    print("  (* = BH-significant at α=0.10)")

    # ── Step 8: Split-half sign stability ────────────────────────────────
    print("\n" + "=" * 70)
    print("SPLIT-HALF SIGN STABILITY (PRIMARY 3m)")
    print("=" * 70)

    sh_ic = split_half_sign(
        res_pa_3m["_ics"], res_pa_3m["_dates"], split_date="2021-01-01"
    )
    sh_top5 = split_half_sign(
        res_pa_3m["_top5"], res_pa_3m["_dates"], split_date="2021-01-01"
    )

    print(f"  IC split (median-date): H1 mean={sh_ic['h1_mean']:.4f}, "
          f"H2 mean={sh_ic['h2_mean']:.4f}, same_sign={sh_ic['h1h2_same_sign']}")
    print(f"  IC split (pre/post 2021): pre={sh_ic['pre_mean']:.4f}, "
          f"post={sh_ic['post_mean']:.4f}, same_sign={sh_ic['presplit_same_sign']}")
    print(f"  Top-5 split (median-date): H1={sh_top5['h1_mean']:.4f}, "
          f"H2={sh_top5['h2_mean']:.4f}, same_sign={sh_top5['h1h2_same_sign']}")
    print(f"  Top-5 split (pre/post 2021): pre={sh_top5['pre_mean']:.4f}, "
          f"post={sh_top5['post_mean']:.4f}, same_sign={sh_top5['presplit_same_sign']}")

    # ── Step 9: Robustness variants ───────────────────────────────────────
    print("\n" + "=" * 70)
    print("ROBUSTNESS VARIANTS (reported, NOT decision, NOT FDR-counted)")
    print("=" * 70)

    # R1: top-3 and top-7
    r1_top3 = run_trial(pctile_me, fwd_3m, me_ge8, "pctile", "3m", top_k=3)
    r1_top7 = run_trial(pctile_me, fwd_3m, me_ge8, "pctile", "3m", top_k=7)
    print(f"\nR1 top-3: excess={r1_top3['top5_excess_mean']:.4f}, "
          f"IC={r1_top3['ic_mean']:.4f}, HAC-t(IC)={r1_top3['ic_hac_t']:.3f}")
    print(f"R1 top-7: excess={r1_top7['top5_excess_mean']:.4f}, "
          f"IC={r1_top7['ic_mean']:.4f}, HAC-t(IC)={r1_top7['ic_hac_t']:.3f}")

    # R2: 756d window
    pctile_756_me_aligned = pctile_756_me.reindex(me_ge8)
    r2 = run_trial(pctile_756_me_aligned, fwd_3m, me_ge8, "pctile_756d", "3m")
    print(f"\nR2 (756d window): IC={r2['ic_mean']:.4f}, HAC-t={r2['ic_hac_t']:.3f}, "
          f"excess={r2['top5_excess_mean']:.4f}")

    # R3: size-residualized IC (log-price proxy)
    print("\nR3: Size-residualized IC (log-price proxy)...")
    resid_ics = []
    for t in me_ge8:
        if t not in pctile_me.index or t not in fwd_3m.index:
            resid_ics.append(np.nan)
            continue
        sig_row = pctile_me.loc[t]
        fwd_row = fwd_3m.loc[t]
        valid = sig_row.dropna().index.intersection(fwd_row.dropna().index)
        valid = valid.intersection(closes.columns)  # tickers present in closes
        if len(valid) < 3:
            resid_ics.append(np.nan)
            continue
        # Log-price size proxy at t (last available close on or before t)
        close_t = closes.loc[:t, valid].iloc[-1] if t in closes.index else \
            closes.loc[closes.index <= t, valid].iloc[-1]
        log_price = np.log(close_t.replace(0, np.nan)).dropna()
        valid2 = valid.intersection(log_price.index)
        if len(valid2) < 3:
            resid_ics.append(np.nan)
            continue
        sig_v = sig_row[valid2]
        # cross-sectional residualize
        sig_resid = cross_sectional_resid(sig_v, log_price[valid2])
        if sig_resid is None or sig_resid.isna().all():
            resid_ics.append(np.nan)
            continue
        ic_r = rank_ic(sig_resid.dropna(), fwd_row[sig_resid.dropna().index])
        resid_ics.append(ic_r)

    resid_ics_arr = np.array(resid_ics, dtype=float)
    resid_ics_clean = resid_ics_arr[~np.isnan(resid_ics_arr)]
    r3_ic_mean = float(np.mean(resid_ics_clean)) if len(resid_ics_clean) > 0 else np.nan
    r3_nw = newey_west_tstat(resid_ics_clean, lags=2) if len(resid_ics_clean) > 5 else {}
    r3_hac_t = r3_nw.get("t", np.nan)
    if r3_hac_t is None:
        r3_hac_t = np.nan
    print(f"R3 size-residualized IC: mean={r3_ic_mean:.4f}, "
          f"HAC-t={r3_hac_t:.3f} (n={len(resid_ics_clean)})")

    # R4: pre-2021 vs 2021+ split subsamples
    split_date = pd.Timestamp("2021-01-01")
    me_pre2021 = me_ge8[me_ge8 < split_date]
    me_post2021 = me_ge8[me_ge8 >= split_date]

    print(f"\nR4 pre-2021 subsample: {len(me_pre2021)} month-ends")
    print(f"R4 post-2021 subsample: {len(me_post2021)} month-ends")

    if len(me_pre2021) >= 6:
        fwd_3m_pre = build_forward_returns(closes, hsi, me_pre2021, pairs, h_cols, horizon_bd=63)
        r4_pre = run_trial(pctile_me.reindex(me_pre2021), fwd_3m_pre,
                           me_pre2021, "pctile", "3m_pre2021")
        print(f"R4 pre-2021: IC={r4_pre['ic_mean']:.4f}, HAC-t={r4_pre['ic_hac_t']:.3f}, "
              f"top5={r4_pre['top5_excess_mean']:.4f}")
    else:
        print("R4 pre-2021: insufficient observations")
        r4_pre = {"ic_mean": np.nan, "ic_hac_t": np.nan, "top5_excess_mean": np.nan}

    if len(me_post2021) >= 6:
        fwd_3m_post = build_forward_returns(closes, hsi, me_post2021, pairs, h_cols, horizon_bd=63)
        r4_post = run_trial(pctile_me.reindex(me_post2021), fwd_3m_post,
                            me_post2021, "pctile", "3m_post2021")
        print(f"R4 post-2021: IC={r4_post['ic_mean']:.4f}, HAC-t={r4_post['ic_hac_t']:.3f}, "
              f"top5={r4_post['top5_excess_mean']:.4f}")
    else:
        print("R4 post-2021: insufficient observations")
        r4_post = {"ic_mean": np.nan, "ic_hac_t": np.nan, "top5_excess_mean": np.nan}

    # ── Step 10: Survivorship bound (worst-5-haircut) ─────────────────────
    print("\n" + "=" * 70)
    print("SURVIVORSHIP BOUND (prereg §7)")
    print("=" * 70)

    # Pairs sorted by joint history length (n_days)
    pairs_sorted = sorted(pairs, key=lambda p: p["n_days"])
    shortest5 = [p["h"] for p in pairs_sorted[:5]]
    longest15y_threshold = 252 * 15  # trading days (n_days counts trading days, not calendar days)
    long_pairs = [p["h"] for p in pairs if p["n_days"] >= longest15y_threshold]

    print(f"Shortest 5 pairs (haircut): {shortest5}")
    print(f"Pairs ≥15y history: {long_pairs} (n={len(long_pairs)})")

    # Haircut: exclude shortest-5
    haircut_cols = [c for c in h_cols if c not in shortest5]
    pctile_hc_me = pctile_me[haircut_cols]
    fwd_3m_hc = fwd_3m[haircut_cols] if all(c in fwd_3m.columns for c in haircut_cols) \
        else fwd_3m[[c for c in haircut_cols if c in fwd_3m.columns]]

    r_haircut = run_trial(pctile_hc_me, fwd_3m_hc, me_ge8, "pctile_haircut5", "3m")
    print(f"\nHaircut (excl. shortest-5): IC={r_haircut['ic_mean']:.4f}, "
          f"HAC-t={r_haircut['ic_hac_t']:.3f}, top5={r_haircut['top5_excess_mean']:.4f}")

    # Long survivors only (≥15y)
    if len(long_pairs) >= 3:
        pctile_lp_me = pctile_me[[c for c in long_pairs if c in pctile_me.columns]]
        fwd_3m_lp = fwd_3m[[c for c in long_pairs if c in fwd_3m.columns]]
        r_long = run_trial(pctile_lp_me, fwd_3m_lp, me_ge8, "pctile_long15y", "3m")
        print(f"Long survivors (≥15y) only: IC={r_long['ic_mean']:.4f}, "
              f"HAC-t={r_long['ic_hac_t']:.3f}, top5={r_long['top5_excess_mean']:.4f}")
    else:
        print(f"Long survivors: only {len(long_pairs)} pairs, skipping (too thin)")
        r_long = {"ic_mean": np.nan, "ic_hac_t": np.nan, "top5_excess_mean": np.nan}

    # ── Step 11: Pre-registered gate evaluation ───────────────────────────
    print("\n" + "=" * 70)
    print("PRE-REGISTERED GATE EVALUATION (prereg §8)")
    print("=" * 70)

    ic_pos_1m = not np.isnan(res_pa_1m["ic_mean"]) and res_pa_1m["ic_mean"] > 0
    ic_pos_3m = not np.isnan(res_pa_3m["ic_mean"]) and res_pa_3m["ic_mean"] > 0
    hac_t_ic_3m = res_pa_3m["ic_hac_t"]
    hac_t_top5_3m = res_pa_3m["top5_hac_t"]
    ls_same_sign = (not np.isnan(res_pa_3m["ls_tercile_mean"])
                    and not np.isnan(res_pa_3m["top5_excess_mean"])
                    and np.sign(res_pa_3m["ls_tercile_mean"]) == np.sign(res_pa_3m["top5_excess_mean"]))
    dsr_val_3m = res_pa_3m["dsr"]
    dsr_ge_090 = not np.isnan(dsr_val_3m) and dsr_val_3m >= 0.90
    split_stable = (sh_top5["h1h2_same_sign"] and sh_top5["presplit_same_sign"])
    survival_ok = (not np.isnan(r_haircut["ic_mean"]) and r_haircut["ic_mean"] > 0)
    _bh_pa3m = bh_result.get("pctile_3m", {})
    bh_pctile_3m = _bh_pa3m.get("reject", False) if isinstance(_bh_pa3m, dict) else False

    print(f"  (1) IC>0 at 1m: {ic_pos_1m} ({res_pa_1m['ic_mean']:.4f})")
    print(f"  (1) IC>0 at 3m: {ic_pos_3m} ({res_pa_3m['ic_mean']:.4f})")
    print(f"  (2) HAC-t ≥ 2.0 (3m IC): {hac_t_ic_3m:.3f} >= 2.0 → {hac_t_ic_3m >= 2.0}")
    print(f"  (2) HAC-t ≥ 2.0 (3m top-5 excess): {hac_t_top5_3m:.3f} >= 2.0 → {hac_t_top5_3m >= 2.0}")
    print(f"  (3) L/S same sign as top-5 excess at 3m: {ls_same_sign}")
    dsr_str = f"{dsr_val_3m:.4f}" if not np.isnan(dsr_val_3m) else "N/A"
    print(f"  (4) DSR ≥ 0.90: {dsr_str} → {dsr_ge_090}")
    print(f"  (5) Split-half stable (H1/H2 and pre/post-2021): {split_stable}")
    print(f"       H1/H2 same sign: {sh_top5['h1h2_same_sign']}, "
          f"pre/post-2021 same sign: {sh_top5['presplit_same_sign']}")
    print(f"  (6) Survivorship haircut (excl. shortest-5): IC>0 → {survival_ok}")
    print(f"  BH-significant (pctile 3m): {bh_pctile_3m}")

    # Determine verdict
    ic_ok_both = ic_pos_1m and ic_pos_3m
    hac_ge_2 = (not np.isnan(hac_t_ic_3m) and hac_t_ic_3m >= 2.0 and
                not np.isnan(hac_t_top5_3m) and hac_t_top5_3m >= 2.0)
    hac_ge_15 = (not np.isnan(hac_t_ic_3m) and hac_t_ic_3m >= 1.5 or
                 not np.isnan(hac_t_top5_3m) and hac_t_top5_3m >= 1.5)

    go_conditions = (ic_ok_both and hac_ge_2 and ls_same_sign and
                     dsr_ge_090 and split_stable and survival_ok and bh_pctile_3m)
    no_go_conditions = (not ic_ok_both or
                        (not np.isnan(res_pa_3m["ls_tercile_mean"]) and
                         not np.isnan(res_pa_3m["top5_excess_mean"]) and
                         res_pa_3m["ls_tercile_mean"] < 0 and res_pa_3m["top5_excess_mean"] > 0))
    kill_conditions = (not np.isnan(res_pa_3m["ic_mean"]) and res_pa_3m["ic_mean"] < 0 and
                       not np.isnan(hac_t_ic_3m) and hac_t_ic_3m >= 2.0)
    accrue_conditions = (ic_ok_both and hac_ge_15 and
                         not (dsr_ge_090 and split_stable and hac_ge_2 and bh_pctile_3m))

    if kill_conditions:
        verdict = "KILL"
    elif no_go_conditions:
        verdict = "NO-GO"
    elif go_conditions:
        verdict = "GO"
    elif accrue_conditions:
        verdict = "ACCRUE"
    else:
        verdict = "NO-GO"

    print(f"\n{'=' * 70}")
    print(f"VERDICT: {verdict}")
    print(f"{'=' * 70}")

    # ── Step 12: Summary dict for report ─────────────────────────────────
    return {
        "verdict": verdict,
        "res_pa_1m": res_pa_1m,
        "res_pa_3m": res_pa_3m,
        "res_pb_1m": res_pb_1m,
        "res_pb_3m": res_pb_3m,
        "bh_result": bh_result,
        "bh_input": bh_input,
        "sh_ic": sh_ic,
        "sh_top5": sh_top5,
        "r1_top3": r1_top3,
        "r1_top7": r1_top7,
        "r2": r2,
        "r3_ic_mean": r3_ic_mean,
        "r3_ic_hac_t": r3_nw.get("t", np.nan),
        "r4_pre": r4_pre,
        "r4_post": r4_post,
        "r_haircut": r_haircut,
        "r_long": r_long,
        "me_ge8_count": len(me_ge8),
        "gate_checks": {
            "ic_pos_1m": ic_pos_1m,
            "ic_pos_3m": ic_pos_3m,
            "hac_ge_2": hac_ge_2,
            "hac_ge_15": hac_ge_15,
            "ls_same_sign": ls_same_sign,
            "dsr_ge_090": dsr_ge_090,
            "split_stable": split_stable,
            "survival_ok": survival_ok,
            "bh_pctile_3m": bh_pctile_3m,
        },
        "go_conditions": go_conditions,
        "no_go_conditions": no_go_conditions,
        "kill_conditions": kill_conditions,
        "pair_joint_starts": {k: str(v) for k, v in pair_joint_starts.items()},
        "pairs_sorted_by_history": [p["h"] for p in pairs_sorted],
        "shortest5": shortest5,
        "long_pairs": long_pairs,
    }


if __name__ == "__main__":
    results = main()
    print(f"\nDone. Verdict: {results['verdict']}")
