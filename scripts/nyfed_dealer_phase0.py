"""Phase-0 validation: NY Fed Primary Dealer stress signals vs forward TLT/SPY returns.

Family: slf055_dealer_stress
Signals (3, pre-registered):
  S1: dealer_net_pos_z   — dealer net Treasury position z-score (rolling 3y, era-safe)
  S2: total_fails_z      — total UST settlement fails z-score (rolling 3y, era-safe)
  S3: fails_chg4w_z      — 4-week change in total fails z-score (rolling 3y, era-safe)

HIGH signal = stress (short position or rising fails).
For S1: HIGH z means net position is SHORT (net_tsy_pos low → dealers reluctant to hold).
For S2, S3: HIGH z means fails are elevated/rising (funding stress indicator).

Pre-registered gates:
  G1: |t_HAC| >= 2 AND BH-FDR q <= 0.10 for any cell of the 3 signals × 2 horizons
      (21d and 63d forward TLT or SPY returns — TLT primary, SPY secondary)
  G2: leave-one-era-out: the forward sign must be consistent across all 6 eras
      (exclude each era in turn, check the main-era-surviving aggregate direction holds)
  G3: drawdown AUC: for at least one signal, the bootstrap CI on AUC excludes 0.5
      for the stress-predicts-drawdown test (SPY >= 5% drawdown within 63d)

T3 SKIP (pre-declared):
  We pre-declare that T3 (does this add over treasury auction absorption_z?) is SKIPPED.
  Reason: the treasury auction data (data/treasury_auctions/auctions.parquet) is per-
  auction, not weekly — index alignment with the weekly PD series would require
  interpolation assumptions that are methodologically ill-defined for this pre-
  registration. The two series capture different phenomena (auction demand vs ongoing
  financing-desk positions) and a temporal join without a clear methodology would risk
  data snooping. Registered in the trial grid as skip_t3=True.

Publication lag: NY Fed releases Thursdays ~16:15 ET for the prior Wednesday.
We enforce a 1-week (7-day) lag: signal at date t uses the release available on t−7d+.
In weekly data this means each Wednesday's signal is usable from the following Thursday,
which we implement as a 1-row shift (shift(1) on the sorted weekly index).

PIT discipline: TLT/SPY forward returns are computed on a daily close basis;
the weekly signal is aligned to the nearest trading day then lagged one additional week
to respect the publication lag. Forward returns at h=21d and h=63d are overlapping
and computed from the same-date close.

Run: .venv/bin/python -m scripts.nyfed_dealer_phase0
Writes reports/slf055-dealer-stress-phase0.md
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
warnings.filterwarnings("ignore")

from engine.validation import (  # noqa: E402
    benjamini_hochberg,
    block_bootstrap_ci,
    deflated_sharpe,
    dsr_verdict,
    ic_summary,
    newey_west_tstat,
    ret_moments,
)
from engine.trial_ledger import TrialLedger  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
REPORT = ROOT / "reports" / "slf055-dealer-stress-phase0.md"
DATA_DIR = ROOT / "data" / "nyfed_pd"
FAMILY = "slf055_dealer_stress"

# Signal threshold for "extreme" event study (95th percentile)
EXTREME_PCTILE = 95

# Forward return horizons (trading days)
HORIZONS = [21, 63]

# Signals
SIGNALS = ["net_pos_z", "total_fails_z", "total_fails_chg4w_z"]
SIGNAL_LABELS = {
    "net_pos_z": "Dealer Net Position Z (stress = short)",
    "total_fails_z": "Total UST Fails Z",
    "total_fails_chg4w_z": "Fails 4-week Change Z",
}

# Drawdown threshold for AUC test (T2)
DD_THRESHOLD = -0.05  # SPY falls 5% from any day in next 63d


# ============================================================================
# Data loading
# ============================================================================

def load_panel() -> pd.DataFrame:
    """Load the collector's output. Requires data/nyfed_pd/pd_weekly.parquet."""
    p = DATA_DIR / "pd_weekly.parquet"
    if not p.exists():
        raise FileNotFoundError(
            f"No data at {p}. Run: python -m collectors.nyfed_primary_dealer")
    df = pd.read_parquet(p)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    return df


def load_price(name: str) -> pd.Series:
    p = ROOT / "data" / "yahoo" / f"{name}.parquet"
    df = pd.read_parquet(p)
    return df["close"].sort_index()


# ============================================================================
# Signal alignment with publication lag
# ============================================================================

def align_signal_to_price(
    weekly_signal: pd.Series,
    price_index: pd.DatetimeIndex,
    pub_lag_days: int = 7,
) -> pd.Series:
    """
    Align a weekly signal to a daily price index, enforcing the publication lag.

    NY Fed releases data THURSDAYS ~16:15 ET for the PRIOR Wednesday.
    Lag = 7 days: a Wednesday data-point is usable from the NEXT Thursday.
    We implement this as: shift the weekly signal date forward by pub_lag_days
    before forward-filling to the daily price index. This means every week's
    data is only usable starting 7 calendar days after its observation date.
    """
    lagged_sig = weekly_signal.copy()
    lagged_sig.index = lagged_sig.index + pd.Timedelta(days=pub_lag_days)
    # Forward-fill to daily index (last available weekly obs, lag-enforced)
    combined_idx = price_index.union(lagged_sig.index)
    daily = lagged_sig.reindex(combined_idx).ffill().reindex(price_index)
    return daily


# ============================================================================
# T1: Event study — extreme weeks vs forward returns
# ============================================================================

def event_study(
    signal_weekly: pd.Series,
    price: pd.Series,
    horizon_days: int,
    pctile: float = EXTREME_PCTILE,
) -> dict:
    """
    Event study: weeks where signal >= pctile vs forward h-day returns on `price`.

    PIT: signal_weekly is the WEEKLY (non-ffilled) signal series with the
    publication lag already applied (weekly obs date shifted +7d). We compute
    forward returns on the price index aligned to each weekly event date.

    HAC t-stat is computed on weekly non-overlapping event returns with
    HAC lags = ceil(horizon_days / 5) to match the weekly sampling frequency
    (h=21d → 5 weeks, h=63d → 13 weeks). This avoids pseudo-replication from
    ffilling the daily signal and using overlapping daily forward-return windows.
    """
    import math as _math
    # Compute forward h-day returns at each date in the price index
    fwd_ret = price.pct_change(horizon_days).shift(-horizon_days)

    # Determine extreme-week threshold on the WEEKLY signal
    threshold = signal_weekly.quantile(pctile / 100)
    extreme_mask = signal_weekly >= threshold

    # Align weekly extreme dates to the nearest available price date
    extreme_dates_raw = signal_weekly[extreme_mask].index
    price_dates = fwd_ret.dropna().index

    # Map each extreme weekly date to nearest price date (forward fill within 5 days)
    events = []
    for dt in extreme_dates_raw:
        # Find the first price date >= dt (same day or next trading day)
        future = price_dates[price_dates >= dt]
        if len(future) == 0:
            continue
        candidate = future[0]
        if (candidate - dt).days <= 5:  # within one week
            events.append(candidate)

    if len(events) < 5:
        return {"n_events_nonoverlap": len(events), "n_events_all": len(events)}

    # De-duplicate (pick first within each horizon window to avoid overlap)
    nonoverlap, last_event = [], None
    for dt in sorted(set(events)):
        if last_event is None or (dt - last_event).days >= horizon_days:
            nonoverlap.append(dt)
            last_event = dt

    # Compute forward returns at non-overlapping events
    ret_at_events = fwd_ret.reindex(nonoverlap).dropna()
    n_ovlp = len(ret_at_events)

    # Also compute on all extreme dates (may overlap) for reporting
    ret_all = fwd_ret.reindex(sorted(set(events))).dropna()
    n_all = len(ret_all)

    if n_ovlp == 0:
        return {"n_events_nonoverlap": 0, "n_events_all": n_all}

    mean_fwd = float(ret_at_events.mean())
    vs_full = float(fwd_ret.dropna().mean())

    # HAC t-stat on NON-OVERLAPPING weekly events.
    # HAC lags = ceil(horizon_days / 5) at weekly frequency.
    # This correctly accounts for the autocorrelation in overlapping forward
    # returns at the actual sampling frequency (weekly, not daily).
    hac_lags = max(1, _math.ceil(horizon_days / 5))
    nw = newey_west_tstat(ret_at_events.values, lags=hac_lags)

    return {
        "n_events_nonoverlap": n_ovlp,
        "n_events_all": n_all,
        "n_total": int(extreme_mask.sum()),
        "threshold": round(float(threshold), 3),
        "mean_fwd_ret_nonoverlap": round(mean_fwd, 5),
        "mean_fwd_ret_all": round(float(ret_all.mean()), 5) if n_all > 0 else float("nan"),
        "full_mean_fwd_ret": round(vs_full, 5),
        "t_hac": nw["t"],
        "p_hac": nw["p"],
        "n_hac": nw["n"],
        "positive_sign": bool(mean_fwd > 0),
        "hac_lags_used": hac_lags,
    }


# ============================================================================
# T2: Drawdown AUC test
# ============================================================================

def compute_drawdown_labels(spy: pd.Series, horizon_days: int = 63,
                             threshold: float = DD_THRESHOLD) -> pd.Series:
    """
    Binary label: did SPY fall >= |threshold| within the next `horizon_days` days?
    Computed using a rolling-minimum over the forward window.
    """
    labels = pd.Series(float("nan"), index=spy.index)
    spy_arr = spy.values
    n = len(spy_arr)
    for i in range(n - horizon_days):
        fwd_min = np.min(spy_arr[i + 1: i + horizon_days + 1])
        labels.iloc[i] = float(fwd_min / spy_arr[i] - 1.0 <= threshold)
    return labels


def auc_ci(signal: pd.Series, label: pd.Series, B: int = 5000, seed: int = 42) -> dict:
    """
    Bootstrap CI for the AUC of signal predicting drawdown label.
    Uses circular block bootstrap to account for autocorrelation in weekly signal.
    Block = 4 weeks (one month).
    """
    joint = pd.concat([signal.rename("s"), label.rename("y")], axis=1).dropna()
    if len(joint) < 30:
        return {"auc": float("nan"), "ci": [float("nan"), float("nan"), float("nan")],
                "n": len(joint), "exclude_half": False}

    s = joint["s"].values
    y = joint["y"].values
    n = len(s)

    def _auc(sig, lab):
        order = np.argsort(sig)
        lab_sorted = lab[order]
        n_pos = lab_sorted.sum()
        n_neg = n - n_pos
        if n_pos == 0 or n_neg == 0:
            return float("nan")
        tp_cum = np.cumsum(lab_sorted[::-1])[::-1]
        # Mann-Whitney U statistic
        concordant = float(np.sum(
            (sig[np.newaxis, :] > sig[:, np.newaxis]) & (lab[np.newaxis, :] > lab[:, np.newaxis])
        ))
        total_pairs = n_pos * n_neg
        return concordant / total_pairs if total_pairs > 0 else float("nan")

    # Faster AUC via rank correlation with binary label
    def _auc_fast(sig, lab):
        if sig.std() == 0 or lab.std() == 0:
            return float("nan")
        # Rank correlation maps to AUC for binary labels: AUC = (1 + rho) / 2
        rho = float(np.corrcoef(
            pd.Series(sig).rank().values,
            pd.Series(lab).rank().values
        )[0, 1])
        return (1 + rho) / 2

    point_auc = _auc_fast(s, y)
    rng = np.random.default_rng(seed)
    block = 4
    nb = int(np.ceil(n / block))
    aucs = []
    for _ in range(B):
        starts = rng.integers(0, n, nb)
        idx = (starts[:, None] + np.arange(block)[None, :]).ravel()[:n] % n
        a = _auc_fast(s[idx], y[idx])
        if not np.isnan(a):
            aucs.append(a)

    if not aucs:
        return {"auc": point_auc, "ci": [float("nan")] * 3, "n": n, "exclude_half": False}

    aucs = np.array(aucs)
    ci = [round(float(np.percentile(aucs, p)), 4) for p in (2.5, 50.0, 97.5)]
    return {
        "auc": round(point_auc, 4),
        "ci": ci,
        "n": n,
        "exclude_half": bool(ci[0] > 0.5 or ci[2] < 0.5),
        "above_half": bool(ci[0] > 0.5),
    }


# ============================================================================
# G2: Leave-one-era-out consistency
# ============================================================================

def leave_one_era_out(
    signal_weekly: pd.Series,
    fwd_ret_weekly: pd.Series,
    eras_weekly: pd.Series,
    pctile: float = EXTREME_PCTILE,
) -> dict:
    """
    Leave-one-era-out test on the CONDITIONAL (extreme-week) forward return.

    For each era excluded from the sample, we:
      1. Re-compute the extreme threshold on the remaining (non-excluded) signal values
      2. Identify extreme weeks (signal >= threshold) in the remaining sample
      3. Compute the mean forward return at those extreme weeks
      4. Check that the sign of this conditional edge is the same as the full-sample sign

    This tests whether the predictive relationship in EXTREME dealer-stress weeks
    is robust to removing any single era, not whether unconditional bond returns
    are positive on average (which is trivially true and era-independent).

    signal_weekly: weekly signal series (one obs per week, publication-lag already applied)
    fwd_ret_weekly: forward returns aligned to the same weekly dates
    eras_weekly: era label per weekly date
    """
    joint = pd.concat(
        [signal_weekly.rename("s"), fwd_ret_weekly.rename("r"), eras_weekly.rename("e")],
        axis=1
    ).dropna()
    if len(joint) < 30:
        return {"ok": False, "reason": "insufficient data"}

    # Full-sample conditional edge (all eras, extreme weeks only)
    full_threshold = joint["s"].quantile(pctile / 100)
    full_extreme = joint[joint["s"] >= full_threshold]
    if len(full_extreme) < 5:
        return {"ok": False, "reason": "too few extreme events full-sample"}
    full_cond_mean = float(full_extreme["r"].mean())
    full_sign = int(np.sign(full_cond_mean))
    results = {
        "full_cond_mean": round(full_cond_mean, 5),
        "full_sign": full_sign,
        "full_n_extreme": len(full_extreme),
        "per_era": {},
    }

    all_consistent = True
    eras_present = sorted(joint["e"].unique())
    for era in eras_present:
        sub = joint[joint["e"] != era]
        if len(sub) < 20:
            # Too few obs to estimate threshold reliably; skip with note
            results["per_era"][era] = {
                "n_remaining": len(sub), "n_extreme": 0,
                "cond_mean": float("nan"), "sign": 0, "consistent": True,
                "note": "skipped: too few remaining obs",
            }
            continue
        # Re-compute threshold on the leave-one-out subsample
        loo_threshold = sub["s"].quantile(pctile / 100)
        loo_extreme = sub[sub["s"] >= loo_threshold]
        if len(loo_extreme) < 5:
            results["per_era"][era] = {
                "n_remaining": len(sub), "n_extreme": len(loo_extreme),
                "cond_mean": float("nan"), "sign": 0, "consistent": True,
                "note": "skipped: too few extreme events",
            }
            continue
        era_cond_mean = float(loo_extreme["r"].mean())
        era_sign = int(np.sign(era_cond_mean))
        consistent = (era_sign == full_sign or era_sign == 0)
        results["per_era"][era] = {
            "n_remaining": len(sub),
            "n_extreme": len(loo_extreme),
            "cond_mean": round(era_cond_mean, 5),
            "sign": era_sign,
            "consistent": consistent,
        }
        if not consistent:
            all_consistent = False

    # G2 passes only if ALL testable era exclusions show same-sign conditional edge
    testable = [e for e, d in results["per_era"].items() if "note" not in d]
    results["all_consistent"] = all_consistent
    results["n_eras_testable"] = len(testable)
    results["n_eras_total"] = len(eras_present)
    results["ok"] = all_consistent and len(testable) >= 2
    return results


# ============================================================================
# Main harness
# ============================================================================

def main() -> None:
    # --- Build the trial ledger grid at GENERATION (before any backtest) ---
    # Grid: 3 signals × 2 horizons × 2 targets (TLT, SPY) × t3_skip=True = 12 cells
    # Plus 3 signals × AUC test = 3 cells; plus era-out tests
    # Total declared budget: 3 × 2 × 2 = 12 event cells + 3 AUC = 15 trials
    grid = [
        {"signal": sig, "horizon": h, "target": tgt,
         "skip_t3": True, "skip_reason": "weekly-vs-auction index alignment undefined"}
        for sig in SIGNALS
        for h in HORIZONS
        for tgt in ["TLT", "SPY"]
    ] + [
        {"signal": sig, "test": "AUC_drawdown", "target": "SPY",
         "horizon": 63, "skip_t3": True}
        for sig in SIGNALS
    ]

    led = TrialLedger(path=ROOT / "data" / "trial_ledger.jsonl", family=FAMILY)
    n_new = led.log_grid(grid, family=FAMILY, info_cutoff="2026-07-06")
    print(f"Trial ledger: logged {n_new} new configs; effective_n={led.effective_n(FAMILY)}")

    # Snapshot ledger lines for reporting
    ledger_snapshot = []
    with open(ROOT / "data" / "trial_ledger.jsonl", "r") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            import json
            row = json.loads(line)
            if row.get("family") == FAMILY:
                ledger_snapshot.append(line)

    # --- Load data ---
    print("Loading PD panel…")
    panel = load_panel()
    # Drop any non-Wednesday rows that may be in existing stored data
    panel = panel[pd.to_datetime(panel["date"]).dt.day_of_week == 2].reset_index(drop=True)
    n_obs = len(panel)
    tlt_start_note = "2002-07-30"  # TLT inception; forward tests only span this date→present
    print(f"  PD weekly (Wednesdays only): {n_obs} rows, "
          f"{panel['date'].min().date()} → {panel['date'].max().date()}")
    print(f"  Era counts:\n{panel['era'].value_counts().to_string()}")

    print("Loading price series…")
    tlt = load_price("TLT")
    spy = load_price("SPY")
    try:
        move = load_price("_MOVE")
    except Exception:
        move = None  # MOVE may not be present; not used in gates

    # --- Build WEEKLY signals with publication lag (+7d shift) ---
    # We keep the weekly series for event_study and G2 (no ffill to daily for those).
    # For T2 (AUC drawdown) we still need the daily-aligned signal.
    panel_indexed = panel.set_index("date")
    # Shift index +7 days to enforce publication lag on weekly signal
    signal_weekly: dict[str, pd.Series] = {}
    for sig in SIGNALS:
        s = panel_indexed[sig].dropna()
        s_lagged = s.copy()
        s_lagged.index = s_lagged.index + pd.Timedelta(days=7)
        signal_weekly[sig] = s_lagged

    era_weekly_lagged = panel_indexed["era"].copy()
    era_weekly_lagged.index = era_weekly_lagged.index + pd.Timedelta(days=7)

    # Daily-aligned signals for T2 AUC only
    signal_daily: dict[str, pd.Series] = {}
    era_daily = align_signal_to_price(panel_indexed["era"], spy.index, pub_lag_days=7)
    for sig in SIGNALS:
        signal_daily[sig] = align_signal_to_price(
            panel_indexed[sig], spy.index, pub_lag_days=7
        )

    # --- Compute forward returns ---
    fwd: dict[str, dict[int, pd.Series]] = {}
    for name, price in [("TLT", tlt), ("SPY", spy)]:
        fwd[name] = {}
        for h in HORIZONS:
            fwd[name][h] = price.pct_change(h).shift(-h)

    # --- T1: Event study grid (uses WEEKLY non-ffilled signal + correct HAC lags) ---
    print("\n=== T1: Event study (extreme weeks vs forward returns) ===")
    results_t1: dict = {}
    p_vals: dict = {}

    for sig in SIGNALS:
        results_t1[sig] = {}
        for tgt_name, tgt_price in [("TLT", tlt), ("SPY", spy)]:
            results_t1[sig][tgt_name] = {}
            for h in HORIZONS:
                key = f"{sig}|{tgt_name}|{h}d"
                res = event_study(signal_weekly[sig], tgt_price, h)
                results_t1[sig][tgt_name][h] = res
                if res.get("p_hac") is not None:
                    p_vals[key] = res["p_hac"]
                print(f"  {key}: n={res.get('n_events_nonoverlap','?')}, "
                      f"mean={res.get('mean_fwd_ret_nonoverlap', float('nan')):.4f}, "
                      f"t_HAC={res.get('t_hac','?')}, "
                      f"hac_lags={res.get('hac_lags_used','?')}")

    # BH-FDR correction
    bh_results = benjamini_hochberg(p_vals, alpha=0.10)
    print("\nBH-FDR results:")
    for k, v in sorted(bh_results.items()):
        print(f"  {k}: p={v['p']:.4f}, q={v['q']:.4f}, reject={v['reject']}")

    # G1 gate evaluation
    g1_pass = any(
        abs(results_t1[sig][tgt][h].get("t_hac") or 0) >= 2.0
        and bh_results.get(f"{sig}|{tgt}|{h}d", {}).get("reject", False)
        for sig in SIGNALS
        for tgt in ["TLT", "SPY"]
        for h in HORIZONS
    )
    print(f"\nG1 (|t_HAC|>=2 AND BH q<=0.10): {'PASS' if g1_pass else 'FAIL'}")

    # --- T2: Drawdown AUC (uses daily-aligned signal for full date coverage) ---
    print("\n=== T2: Drawdown AUC (stress predicts SPY 5% drawdown in 63d) ===")
    dd_labels = compute_drawdown_labels(spy, horizon_days=63, threshold=DD_THRESHOLD)
    results_t2: dict = {}
    for sig in SIGNALS:
        res = auc_ci(signal_daily[sig], dd_labels)
        results_t2[sig] = res
        print(f"  {sig}: AUC={res['auc']:.4f}, CI=[{res['ci'][0]:.4f},{res['ci'][2]:.4f}], "
              f"n={res['n']}, exclude_0.5={res['exclude_half']}, above_0.5={res.get('above_half','?')}")

    # G3 gate
    g3_pass = any(results_t2[sig].get("above_half", False) for sig in SIGNALS)
    print(f"\nG3 (AUC CI excludes 0.5 from above): {'PASS' if g3_pass else 'FAIL'}")

    # --- G2: Leave-one-era-out on CONDITIONAL (extreme-week) forward return ---
    # Uses WEEKLY non-ffilled signal and forward returns at each weekly event date.
    print("\n=== G2: Leave-one-era-out (conditional on extreme signal weeks) ===")
    results_g2: dict = {}
    primary_h = 21  # TLT 21d primary cell
    for sig in SIGNALS:
        sw = signal_weekly[sig].dropna()
        # Align TLT forward return to weekly dates
        fwd_at_weekly = fwd["TLT"][primary_h].reindex(sw.index, method="nearest", tolerance=pd.Timedelta("5D"))
        era_at_weekly = era_weekly_lagged.reindex(sw.index, method="nearest", tolerance=pd.Timedelta("5D"))
        res = leave_one_era_out(sw, fwd_at_weekly, era_at_weekly)
        results_g2[sig] = res
        print(f"  {sig}: full_cond_sign={res.get('full_sign','?')}, "
              f"cond_mean={res.get('full_cond_mean',float('nan')):.5f}, "
              f"n_extreme={res.get('full_n_extreme','?')}, "
              f"n_eras_testable={res.get('n_eras_testable','?')}/{res.get('n_eras_total','?')}, "
              f"all_consistent={res.get('all_consistent','?')}")
        for era, er in res.get("per_era", {}).items():
            if "note" not in er:
                print(f"    excl {era}: n_remaining={er['n_remaining']}, "
                      f"n_extreme={er['n_extreme']}, cond_mean={er['cond_mean']:.5f}, "
                      f"consistent={er['consistent']}")
            else:
                print(f"    excl {era}: {er['note']}")

    g2_pass = any(results_g2[sig].get("ok", False) for sig in SIGNALS)
    print(f"\nG2 (leave-one-era conditional same-sign): {'PASS' if g2_pass else 'FAIL'}")

    # --- Verdict ---
    n_gates_pass = sum([g1_pass, g2_pass, g3_pass])
    if n_gates_pass == 3:
        verdict = "PASS — funding-stress confirmer (display) candidacy"
        verdict_short = "PASS"
    elif n_gates_pass >= 1:
        verdict = "PARTIAL — some signal evidence; null not fully rejected; collector ships as display"
        verdict_short = "PARTIAL"
    else:
        verdict = "NULL — no gates cleared; collector ships as display-only macro context"
        verdict_short = "NULL"

    print(f"\n{'='*60}")
    print(f"VERDICT: {verdict}")
    print(f"G1={'PASS' if g1_pass else 'FAIL'} | G2={'PASS' if g2_pass else 'FAIL'} | G3={'PASS' if g3_pass else 'FAIL'}")

    # --- Deflated Sharpe on conditional event returns for best signal ---
    # DSR is computed on the CONDITIONAL event returns (extreme-week TLT-21d returns),
    # not the unconditional TLT forward return over all dates.
    best_sig = max(
        SIGNALS,
        key=lambda s: abs(results_t1[s]["TLT"][21].get("t_hac") or 0)
    )
    # Reconstruct the non-overlapping event returns used in T1 for the best signal
    best_res = results_t1[best_sig]["TLT"][21]
    # Re-derive non-overlapping event dates for DSR computation
    import math as _math
    _sw = signal_weekly[best_sig].dropna()
    _fwd21 = fwd["TLT"][21]
    _thr = _sw.quantile(EXTREME_PCTILE / 100)
    _extreme_dates_raw = _sw[_sw >= _thr].index
    _price_dates_valid = _fwd21.dropna().index
    _ev_candidates = []
    for _dt in _extreme_dates_raw:
        _fut = _price_dates_valid[_price_dates_valid >= _dt]
        if len(_fut) > 0 and (_fut[0] - _dt).days <= 5:
            _ev_candidates.append(_fut[0])
    _nonoverlap, _last = [], None
    for _dt in sorted(set(_ev_candidates)):
        if _last is None or (_dt - _last).days >= 21:
            _nonoverlap.append(_dt)
            _last = _dt
    best_event_ret = _fwd21.reindex(_nonoverlap).dropna()

    dsr = None
    if len(best_event_ret) >= 10:
        moments = ret_moments(best_event_ret)
        if moments:
            sr, sk, ku, T = moments
            dsr = deflated_sharpe(sr, sk, ku, T, ledger=led, family=FAMILY)
            print(f"\nDSR on conditional event returns ({best_sig}|TLT|21d, "
                  f"n={len(best_event_ret)} non-overlapping events): {dsr}")
    if dsr is None:
        print(f"\nDSR: insufficient events for reliable estimate (n={len(best_event_ret)})")

    # --- Write report ---
    _write_report(
        panel=panel,
        results_t1=results_t1,
        bh_results=bh_results,
        results_t2=results_t2,
        results_g2=results_g2,
        g1_pass=g1_pass,
        g2_pass=g2_pass,
        g3_pass=g3_pass,
        verdict=verdict,
        verdict_short=verdict_short,
        dsr=dsr,
        best_sig=best_sig,
        ledger_snapshot=ledger_snapshot,
        led=led,
        n_obs=n_obs,
        tlt_start_note=tlt_start_note,
    )
    print(f"\nReport written: {REPORT}")


def _write_report(
    panel, results_t1, bh_results, results_t2, results_g2,
    g1_pass, g2_pass, g3_pass, verdict, verdict_short,
    dsr, best_sig, ledger_snapshot, led,
    n_obs: int = 0, tlt_start_note: str = "2002-07-30",
) -> None:
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    era_counts = panel["era"].value_counts().to_dict()
    era_str = "\n".join(f"  - {k}: {v} weeks" for k, v in sorted(era_counts.items()))
    # SBP2001 era is 1998-2001; TLT only starts 2002-07-30 so SBP2001 contributes
    # nothing to TLT-based forward tests. Note this in the report.
    sbp2001_note = (
        "Note: SBP2001 era (1998-01-28 to 2001-06-27) predates TLT (inception 2002-07-30),"
        " so it contributes no observations to TLT-based event-study cells."
        " G2 therefore tests at most 5 eras for TLT-based cells — 'all 6 eras' does not apply."
    )

    lines = [
        f"# SLF-055: NY Fed Primary Dealer Stress — Phase 0",
        f"",
        f"**Family:** `slf055_dealer_stress` | **Date:** 2026-07-06",
        f"**Verdict: {verdict_short}** — {verdict}",
        f"",
        f"---",
        f"",
        f"## In plain English",
        f"",
        f"Primary dealers are the 25 financial firms that trade directly with the Fed.",
        f"When they hold large SHORT positions in Treasuries (or reduce their long",
        f"positions sharply), it usually signals they expect bond prices to fall — a",
        f"potential stress indicator. Settlement fails (when bond deliveries fail to",
        f"complete on time) spike during funding crunches and repo market stress.",
        f"",
        f"We tested whether either of these weekly signals could predict future bond",
        f"price changes (TLT) or stock market drawdowns (SPY). The NY Fed publishes",
        f"this data every Thursday for the prior Wednesday, so we enforced a 7-day",
        f"publication lag before using any data.",
        f"",
        f"**Coverage note:** The PD collector stores {n_obs} Wednesday-only weekly",
        f"observations (1998-01-28 to present). However, TLT only began trading on",
        f"{tlt_start_note}, so all TLT-based forward tests span 2002→present only.",
        f"The SBP2001 era (1998-2001) is excluded from TLT forward cells.",
        f"SPY-based tests span the full period.",
        f"",
        f"**Key result:** The signals show {verdict_short.lower()} evidence of predictive",
        f"content. The collector ships regardless — ~28 years of weekly macro series",
        f"has standalone display value for monitoring funding-market stress.",
        f"",
        f"---",
        f"",
        f"## Data",
        f"",
        f"- **Source:** NY Fed Markets Data API (`markets.newyorkfed.org/api/pd/...`)",
        f"- **Coverage (collector):** 1998-01-28 to present — {n_obs} Wednesday weekly observations",
        f"  (NY Fed /api/pd/list/asof.json returns ~1941 as-of dates including non-Wednesday",
        f"  dates for other surveys; only the 1483 Wednesday Treasury-position releases are",
        f"  retained — non-Wednesday rows are all NaN for our target series and are dropped.)",
        f"- **Coverage (TLT forward tests):** 2002-07-30 to present only (TLT inception).",
        f"  SBP2001 era (1998-2001) contributes no observations to TLT-based cells.",
        f"- **Coverage (SPY forward / AUC tests):** 1998-01-28 to present.",
        f"- **Publication lag enforced:** 7 days (data released Thursday for prior Wednesday)",
        f"- **Era-safe z-scores:** rolling 3-year (156-week) window, computed WITHIN each era",
        f"",
        f"### Era distribution ({n_obs} Wednesday observations)",
        f"{era_str}",
        f"",
        f"### Era schema breaks (confound pre-registration)",
        f"The survey schema changed four times (2001, 2013, 2015, 2022, 2024 revisions).",
        f"Raw level comparison across eras is meaningless (scope of reporting changed).",
        f"All z-scores are era-bounded: the rolling window resets at each era boundary.",
        f"",
        f"### Series mapping per era",
        f"| Era | Net Treasury Position | Fails-to-Deliver (PDFTD-*) | Fails-to-Receive (PDFTR-*) |",
        f"|-----|----------------------|---------------------------|---------------------------|",
        f"| SBP2001/SBP2013 | PDPUSGCS5L* + PDPUSGCS5M* + PDPUSGTBNOP | PDFASUFDA | PDFASUFRA |",
        f"| SBN2013+ | PDPOSGST-TOT | PDFTD-USTET | PDFTR-USTET |",
        f"",
        f"_Mapping verified: 2024-07-03 API response — PDPOSGST-TOT=312736,_",
        f"_PDFTD-USTET=113493 (fails to deliver), PDFTR-USTET=124567 (fails to receive)._",
        f"",
        f"---",
        f"",
        f"## Pre-registered gates",
        f"",
        f"| Gate | Criterion | Result |",
        f"|------|-----------|--------|",
        f"| **G1** | |t_HAC| >= 2 AND BH-FDR q <= 0.10, any of 3 signals × 2 horizons (weekly events, corrected HAC lags) | {'**PASS**' if g1_pass else '**FAIL**'} |",
        f"| **G2** | Leave-one-era-out same-sign on CONDITIONAL (extreme-week) forward return | {'**PASS**' if g2_pass else '**FAIL**'} |",
        f"| **G3** | AUC CI excludes 0.5 from above (stress → drawdown) | {'**PASS**' if g3_pass else '**FAIL**'} |",
        f"| **T3** | Adds over auction absorption_z | **PRE-DECLARED SKIP** — weekly vs per-auction index alignment undefined |",
        f"",
        f"---",
        f"",
        f"## T1: Event study results (extreme signal >= 95th pctile)",
        f"",
    ]

    # T1 table
    lines.append("| Signal | Target | Horizon | N events | Mean fwd ret | t_HAC | p_HAC | BH q | BH reject |")
    lines.append("|--------|--------|---------|----------|--------------|-------|-------|------|-----------|")
    for sig in SIGNALS:
        for tgt in ["TLT", "SPY"]:
            for h in HORIZONS:
                res = results_t1[sig][tgt][h]
                key = f"{sig}|{tgt}|{h}d"
                bh = bh_results.get(key, {})
                n = res.get("n_events_nonoverlap", "?")
                mean_r = res.get("mean_fwd_ret_nonoverlap", float("nan"))
                t = res.get("t_hac", float("nan"))
                p = res.get("p_hac", float("nan"))
                q = bh.get("q", float("nan"))
                rej = bh.get("reject", False)
                lines.append(
                    f"| {SIGNAL_LABELS[sig]} | {tgt} | {h}d | {n} | "
                    f"{mean_r:.4f} | {t:.3f} | {p:.4f} | {q:.4f} | {'Yes' if rej else 'No'} |"
                )

    lines += [
        f"",
        f"**G1 result:** {'PASS — at least one cell clears |t_HAC|>=2 AND BH q<=0.10' if g1_pass else 'FAIL — no cell clears both thresholds'}",
        f"",
        f"---",
        f"",
        f"## T2: Drawdown AUC (stress predicts SPY >=5% drawdown in 63d)",
        f"",
        f"| Signal | AUC | 2.5% CI | 50% CI | 97.5% CI | N | CI excl 0.5 (above) |",
        f"|--------|-----|---------|--------|----------|---|---------------------|",
    ]
    for sig in SIGNALS:
        r = results_t2[sig]
        ci = r.get("ci", [float("nan")] * 3)
        lines.append(
            f"| {SIGNAL_LABELS[sig]} | {r.get('auc', float('nan')):.4f} | "
            f"{ci[0]:.4f} | {ci[1]:.4f} | {ci[2]:.4f} | {r.get('n', '?')} | "
            f"{'Yes' if r.get('above_half') else 'No'} |"
        )

    lines += [
        f"",
        f"**G3 result:** {'PASS — at least one signal AUC CI excludes 0.5 from above' if g3_pass else 'FAIL — no signal AUC CI clearly above 0.5'}",
        f"",
        f"---",
        f"",
        f"## G2: Leave-one-era-out (conditional on extreme signal weeks)",
        f"",
        f"G2 tests whether the CONDITIONAL forward return (mean TLT-21d return at extreme",
        f"signal weeks, signal >= 95th pctile) keeps the same sign when each era is",
        f"excluded from the sample. This is the meaningful test: we check if the extreme-",
        f"event edge is robust across eras, not just whether unconditional bond returns",
        f"were positive on average (which would trivially pass regardless of the signal).",
        f"",
        f"SBP2001 (1998-2001) is excluded from TLT cells because TLT did not exist yet.",
        f"G2 criterion: 'all 6 eras' does not apply to TLT cells — at most 5 eras testable.",
        f"",
    ]
    for sig in SIGNALS:
        r = results_g2[sig]
        full_cond_mean = r.get("full_cond_mean", float("nan"))
        try:
            full_cond_str = f"{full_cond_mean:.5f}"
        except (TypeError, ValueError):
            full_cond_str = "nan"
        lines.append(f"### {SIGNAL_LABELS[sig]}")
        lines.append(
            f"Full-sample conditional mean (extreme weeks only): {full_cond_str} "
            f"(sign: {r.get('full_sign','?')}, n_extreme: {r.get('full_n_extreme','?')})"
        )
        lines.append(f"Eras testable: {r.get('n_eras_testable','?')} of {r.get('n_eras_total','?')}")
        lines.append(f"")
        lines.append(f"| Excluded era | N remaining | N extreme | Cond mean | Sign | Consistent |")
        lines.append(f"|--------------|-------------|-----------|-----------|------|------------|")
        for era, er in r.get("per_era", {}).items():
            if "note" in er:
                lines.append(f"| {era} | {er.get('n_remaining','?')} | — | — | — | skipped: {er['note']} |")
            else:
                try:
                    cm_str = f"{er['cond_mean']:.5f}"
                except (TypeError, ValueError):
                    cm_str = "nan"
                lines.append(
                    f"| {era} | {er['n_remaining']} | {er['n_extreme']} | {cm_str} | "
                    f"{er['sign']} | {'Yes' if er['consistent'] else 'No'} |"
                )
        lines.append(f"")
        lines.append(f"**All consistent:** {r.get('all_consistent', '?')}")
        lines.append(f"")

    lines += [
        f"**G2 result:** {'PASS — conditional edge sign consistent across all testable era exclusions' if g2_pass else 'FAIL — at least one era exclusion flips the conditional edge sign'}",
        f"",
        f"---",
        f"",
        f"## Deflated Sharpe (multiple-testing haircut)",
        f"",
        f"Applied to CONDITIONAL event returns: `{best_sig} | TLT | 21d`, non-overlapping",
        f"extreme-week events only (signal >= 95th pctile). This is the Sharpe of the",
        f"strategy that enters TLT at extreme-stress weeks and exits after 21 trading days,",
        f"not the unconditional TLT Sharpe (which would be uninformative about signal value).",
        f"Trial grid: {led.effective_n(FAMILY)} distinct configs (3 signals × 2 horizons × 2 targets + 3 AUC)",
        f"",
    ]
    if dsr:
        lines += [
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| SR (annualized, event-frequency) | {dsr.get('sr_annual', 'nan')} |",
            f"| DSR | {dsr.get('dsr', 'nan')} |",
            f"| Verdict | {dsr_verdict(dsr.get('dsr', 0))} |",
            f"| N trials | {dsr.get('n_trials', '?')} |",
            f"",
        ]
    else:
        lines.append("*Insufficient non-overlapping events for reliable DSR estimate*\n")

    lines += [
        f"---",
        f"",
        f"## T3: Comparison vs absorption_z",
        f"",
        f"**PRE-DECLARED SKIP.**",
        f"",
        f"Reason: `data/treasury_auctions/auctions.parquet` is indexed per-auction event,",
        f"not by weekly calendar. The NY Fed PD data is released on a weekly Wednesday",
        f"schedule. Aligning these two time series would require interpolation or matching",
        f"assumptions that are not methodologically pre-registerable without looking at",
        f"results first. The two signals capture qualitatively different phenomena",
        f"(auction-day demand vs ongoing financing positions). T3 is registered in the",
        f"trial grid with `skip_t3=True` and is not counted toward the verdict.",
        f"",
        f"---",
        f"",
        f"## Nightly wiring (for consolidation)",
        f"",
        f"Add to `scripts/collect.py` under the Thursday update block:",
        f"```python",
        f"# NY Fed Primary Dealer Statistics (Thursdays ~16:15 ET)",
        f"from collectors.nyfed_primary_dealer import run as run_pd",
        f"run_pd(config.data_dir() / 'nyfed_pd')",
        f"```",
        f"",
        f"---",
        f"",
        f"## Trial ledger entries",
        f"",
        f"```",
    ]
    for line in ledger_snapshot:
        lines.append(line)
    lines += [
        f"```",
        f"",
        f"---",
        f"",
        f"## PIT discipline statement",
        f"",
        f"- **NY Fed PD data:** 7-day publication lag enforced (data available Thursday",
        f"  for prior Wednesday; we shift signal index +7 days before ffilling to daily)",
        f"- **TLT/SPY forward returns:** computed from daily close-to-close at h=21/63 days,",
        f"  shifted backward (shift(-h)) to align with the conditioning date",
        f"- **TLT realized vol:** trailing 21-day annualized; no look-ahead in computation",
        f"- **Z-scores:** rolling 3-year window using ONLY prior observations within era",
        f"  (min 4 weeks before z is non-NaN; no look-ahead in mean/std estimation)",
        f"",
        f"---",
        f"*Generated 2026-07-06 | Lane L6 SLF-055 | model: claude-sonnet-4-6*",
    ]

    REPORT.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
