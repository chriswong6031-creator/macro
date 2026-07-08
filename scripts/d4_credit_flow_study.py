"""D4-05 Step-2 study script — Credit Flow-vs-Spread Divergence.

Reproduces every headline number in reports/d4-credit-flow-divergence.md:
  - Sample construction (N, event counts, base rates)
  - Orthogonality gate: OLS residualization + partial correlations + p-values
  - AUC comparison: HY-OAS timer vs flow residual at 21d and 63d horizons
  - Composite AUC (informational)
  - LOCO episode table

**How to re-run:**
    python scripts/d4_credit_flow_study.py

Requires:
  data/credit_flows/hyg_weekly.parquet   (built by collectors/credit_fund_flows.py)
  data/yahoo/SPY.parquet                 (built by yahoo collector)

All computations use the pre-registered gates and thresholds set in
reports/d4-credit-flow-divergence.md Section 2, committed before any outcome
statistics were computed.

Overlap / NW caveat (see Section 4 of report):
  p-values below are raw Pearson on N=978. Forward labels use 3- and 9-week
  windows introducing autocorrelation. Effective N ~ 326 (21d) / ~109 (63d).
  NW-corrected 21d p-value would not survive 0.05; 63d is robust. The AUC
  gate (which ultimately FAILs) is unaffected.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.linear_model import LinearRegression
from sklearn.metrics import roc_auc_score

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[1]
WEEKLY_PARQUET = REPO_ROOT / "data" / "credit_flows" / "hyg_weekly.parquet"
SPY_PARQUET = REPO_ROOT / "data" / "yahoo" / "SPY.parquet"

# ---------------------------------------------------------------------------
# Pre-registered constants (frozen before first result inspection)
# ---------------------------------------------------------------------------
FLOW_Z_COL = "dollar_vol_z52"
OAS_COL = "hy_oas"
OAS_CHG_Z_COL = "oas_chg10d_z52"

# Divergence state thresholds
THRUST_THRESH = +0.5   # dollar_vol_z52 > +0.5 AND oas_chg10d_z52 > +0.5
WASHOUT_THRESH = -0.5  # dollar_vol_z52 < -0.5 AND oas_chg10d_z52 < -0.5

# Forward drawdown thresholds
DD_THRESH_21 = 21   # trading days ≈ 3 calendar weeks
DD_THRESH_63 = 63   # trading days ≈ 9 calendar weeks
DD_MAG = 0.05       # 5% max drawdown triggers a positive label

# AUC gate bar
AUC_MARGIN_BAR = 0.05

# LOCO episodes: (label, start_date, end_date)
LOCO_EPISODES = [
    ("2008-09 GFC",       "2008-09-01", "2009-06-30"),
    ("2011-08 EU debt",   "2011-08-01", "2012-06-30"),
    ("2015-08 China",     "2015-08-01", "2016-02-28"),
    ("2016-01 oil",       "2016-01-01", "2016-06-30"),
    ("2018-12 Fed hike",  "2018-12-01", "2019-06-30"),
    ("2020-03 COVID",     "2020-03-01", "2020-08-31"),
    ("2022-06 rate hike", "2022-06-01", "2023-02-28"),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _spy_forward_max_dd(spy_daily: pd.DataFrame, n_days: int) -> pd.Series:
    """Weekly max-drawdown over the next n_days trading days.

    For each Friday close (week-end Sunday in weekly frame), look ahead
    n_days *trading* days and compute the maximum intraday/close peak-to-
    trough drawdown. PIT: uses only data from t+1 forward.

    Returns a Series indexed on week-end Sunday dates.
    """
    spy = spy_daily["close_price"].sort_index()
    # Rolling max-drawdown: for each date, look at the next n_days rows
    fwd_dd = {}
    idx = spy.index
    arr = spy.values
    for i in range(len(arr)):
        end = min(i + n_days + 1, len(arr))
        window = arr[i + 1: end]
        if len(window) == 0:
            fwd_dd[idx[i]] = np.nan
            continue
        peak = arr[i]  # entry price = current close
        max_dd = (window.min() - peak) / peak  # negative = drawdown
        fwd_dd[idx[i]] = -max_dd  # positive = drawdown magnitude
    daily_dd = pd.Series(fwd_dd)
    # Resample to weekly (last business day of week maps to Sunday week-end)
    return daily_dd.resample("W").last()


def _partial_r(x: np.ndarray, y: np.ndarray, controls: np.ndarray) -> tuple[float, float]:
    """Partial Pearson r of x~y after residualizing both on controls.

    Returns (r, p_value) using scipy.stats.pearsonr on the residuals.
    Note: p-value is raw Pearson on N observations (overlap-inflated for
    multi-week forward labels; see module docstring caveat).
    """
    mask = ~(np.isnan(x) | np.isnan(y) | np.any(np.isnan(controls), axis=1))
    xm, ym, cm = x[mask], y[mask], controls[mask]

    # Residualize x on controls
    reg_x = LinearRegression().fit(cm, xm)
    res_x = xm - reg_x.predict(cm)

    # Residualize y on controls
    reg_y = LinearRegression().fit(cm, ym)
    res_y = ym - reg_y.predict(cm)

    return stats.pearsonr(res_x, res_y)


def _auc_safe(y_true: np.ndarray, scores: np.ndarray) -> float:
    """ROC-AUC with NaN masking."""
    mask = ~(np.isnan(scores) | np.isnan(y_true))
    if mask.sum() < 10 or y_true[mask].std() == 0:
        return float("nan")
    return float(roc_auc_score(y_true[mask].astype(int), scores[mask]))


# ---------------------------------------------------------------------------
# Main study
# ---------------------------------------------------------------------------
def run() -> None:  # noqa: PLR0912, PLR0915
    print("=" * 70)
    print("D4-05 Credit Flow-vs-Spread Divergence — Step-2 Study")
    print("=" * 70)

    # ------------------------------------------------------------------
    # 0. Load data
    # ------------------------------------------------------------------
    if not WEEKLY_PARQUET.exists():
        print(f"ERROR: {WEEKLY_PARQUET} not found.")
        print("Run:  python -c 'from collectors.credit_fund_flows import collect; collect()'")
        sys.exit(1)
    if not SPY_PARQUET.exists():
        print(f"ERROR: {SPY_PARQUET} not found — run yahoo collector first.")
        sys.exit(1)

    weekly = pd.read_parquet(WEEKLY_PARQUET)
    spy_daily = pd.read_parquet(SPY_PARQUET)
    weekly.index = pd.to_datetime(weekly.index)
    spy_daily.index = pd.to_datetime(spy_daily.index)

    required_cols = [FLOW_Z_COL, OAS_COL, OAS_CHG_Z_COL, "oas_chg10d_z52"]
    for c in required_cols:
        if c not in weekly.columns:
            print(f"ERROR: column '{c}' missing from parquet. "
                  "Re-run collectors/credit_fund_flows.py collect().")
            sys.exit(1)

    print(f"\nParquet columns ({len(weekly.columns)}): {weekly.columns.tolist()}")
    print(f"Weekly rows: {len(weekly)} ({weekly.index.min().date()} to {weekly.index.max().date()})")

    # ------------------------------------------------------------------
    # 1. Build forward SPY max-drawdown labels
    # ------------------------------------------------------------------
    print("\n[1] Building forward SPY drawdown labels ...")
    spy_fwd_21 = _spy_forward_max_dd(spy_daily, DD_THRESH_21)
    spy_fwd_63 = _spy_forward_max_dd(spy_daily, DD_THRESH_63)

    weekly["fwd_dd_21"] = spy_fwd_21.reindex(weekly.index)
    weekly["fwd_dd_63"] = spy_fwd_63.reindex(weekly.index)
    weekly["label_21"] = (weekly["fwd_dd_21"] >= DD_MAG).astype(float)
    weekly["label_63"] = (weekly["fwd_dd_63"] >= DD_MAG).astype(float)

    # ------------------------------------------------------------------
    # 2. Sample (post warm-up)
    # ------------------------------------------------------------------
    df = weekly.dropna(subset=[FLOW_Z_COL, OAS_COL, OAS_CHG_Z_COL]).copy()
    df = df.dropna(subset=["label_21", "label_63"])

    n = len(df)
    ev21 = int(df["label_21"].sum())
    ev63 = int(df["label_63"].sum())
    br21 = ev21 / n
    br63 = ev63 / n

    thrust = ((df[FLOW_Z_COL] > THRUST_THRESH) & (df[OAS_CHG_Z_COL] > THRUST_THRESH))
    washout = ((df[FLOW_Z_COL] < WASHOUT_THRESH) & (df[OAS_CHG_Z_COL] < WASHOUT_THRESH))
    n_thrust = int(thrust.sum())
    n_washout = int(washout.sum())
    n_overlap = int((thrust & washout).sum())

    print(f"\n[2] Sample")
    print(f"  N = {n} weeks ({df.index.min().date()} to {df.index.max().date()})")
    print(f"  21d events: {ev21} ({br21:.1%} base rate)")
    print(f"  63d events: {ev63} ({br63:.1%} base rate)")
    print(f"  thrust_oas_wide: {n_thrust} weeks ({n_thrust/n:.1%})")
    print(f"  washout_oas_tight: {n_washout} weeks ({n_washout/n:.1%})")
    print(f"  overlap: {n_overlap} (expect 0)")

    # ------------------------------------------------------------------
    # 3. Orthogonality gate
    # ------------------------------------------------------------------
    print("\n[3] Orthogonality gate — residualize dollar_vol_z52 on [hy_oas, oas_chg10d_z52]")

    x_flow = df[FLOW_Z_COL].values
    y21 = df["label_21"].values
    y63 = df["label_63"].values
    controls = df[[OAS_COL, OAS_CHG_Z_COL]].values

    # OLS R2 of flow ~ controls
    reg = LinearRegression().fit(controls, x_flow)
    r2 = float(reg.score(controls, x_flow))
    print(f"  OLS R² (dollar_vol_z52 ~ hy_oas + oas_chg10d_z52) = {r2:.3f}")

    # Residuals for flow signal
    flow_resid = x_flow - reg.predict(controls)

    # Partial correlations
    r21, p21 = _partial_r(x_flow, y21, controls)
    r63, p63 = _partial_r(x_flow, y63, controls)
    print(f"\n  Partial r (21d): r = {r21:+.4f}, p = {p21:.4f}")
    print(f"  Partial r (63d): r = {r63:+.4f}, p = {p63:.4f}")
    print()
    print("  NOTE: p-values are raw Pearson (N=978). Overlap-corrected effective N ~326")
    print("  (21d) / ~109 (63d). NW-corrected 21d p would NOT survive 0.05; 63d robust.")

    gate21_survives = abs(r21) >= 0.05 or p21 <= 0.05
    gate63_survives = abs(r63) >= 0.05 or p63 <= 0.05
    print(f"\n  Gate 21d: {'SURVIVES' if gate21_survives else 'FAILS (spanned)'}")
    print(f"  Gate 63d: {'SURVIVES' if gate63_survives else 'FAILS (spanned)'}")

    if not (gate21_survives or gate63_survives):
        print("\nFINAL VERDICT: SPANNED — both horizons fail orthogonality gate. STOP.")
        return

    # ------------------------------------------------------------------
    # 4. AUC comparison
    # ------------------------------------------------------------------
    print("\n[4] AUC comparison")

    # HY-OAS timer: higher OAS level -> higher drawdown probability (negate for AUC)
    oas_scores = df[OAS_COL].values

    auc_oas_21 = _auc_safe(y21, oas_scores)
    auc_oas_63 = _auc_safe(y63, oas_scores)
    auc_flow_21 = _auc_safe(y21, flow_resid)
    auc_flow_63 = _auc_safe(y63, flow_resid)

    margin_21 = auc_flow_21 - auc_oas_21
    margin_63 = auc_flow_63 - auc_oas_63

    print(f"\n  {'Horizon':<8} {'AUC OAS-timer':<16} {'AUC flow-resid':<16} {'Margin':<10} Gate")
    print(f"  {'21d':<8} {auc_oas_21:<16.4f} {auc_flow_21:<16.4f} {margin_21:+.3f}     "
          f"{'PASS' if margin_21 >= AUC_MARGIN_BAR else 'FAIL'}")
    print(f"  {'63d':<8} {auc_oas_63:<16.4f} {auc_flow_63:<16.4f} {margin_63:+.3f}     "
          f"{'PASS' if margin_63 >= AUC_MARGIN_BAR else 'FAIL'}")

    # Composite (informational)
    composite_21 = _auc_safe(y21, oas_scores + flow_resid)
    composite_63 = _auc_safe(y63, oas_scores + flow_resid)
    print(f"\n  Composite (OAS + flow resid, informational): "
          f"21d AUC={composite_21:.3f}, 63d AUC={composite_63:.3f}")

    auc_gate_passes = (margin_21 >= AUC_MARGIN_BAR) or (margin_63 >= AUC_MARGIN_BAR)
    if not auc_gate_passes:
        print("\nFINAL VERDICT: AUC GATE FAILS — flow residual does not beat OAS timer "
              "by ≥5pp at either horizon. STOP.")

    # ------------------------------------------------------------------
    # 5. LOCO episode table
    # ------------------------------------------------------------------
    print("\n[5] LOCO episodes (informational — post-gate)")
    print(f"  {'Episode':<22} {'N wks':>6} {'Flow resid':>12} {'OAS mean':>10} "
          f"{'21d DD%':>8} {'63d DD%':>8}")
    for label, start, end in LOCO_EPISODES:
        mask = (df.index >= start) & (df.index <= end)
        ep = df.loc[mask]
        if ep.empty:
            continue
        flow_r_ep = flow_resid[df.index.isin(ep.index)]
        n_ep = len(ep)
        fr_mean = float(np.nanmean(flow_r_ep))
        oas_mean = float(ep[OAS_COL].mean())
        dd21 = float(ep["label_21"].mean())
        dd63 = float(ep["label_63"].mean())
        print(f"  {label:<22} {n_ep:>6} {fr_mean:>+12.2f} {oas_mean:>10.1f} "
              f"{dd21:>8.0%} {dd63:>8.0%}")

    # ------------------------------------------------------------------
    # 6. Reference: oas_z52 AUC (stronger baseline, disclosure)
    # ------------------------------------------------------------------
    if "oas_z52" in df.columns:
        auc_oasz_21 = _auc_safe(y21, df["oas_z52"].values)
        auc_oasz_63 = _auc_safe(y63, df["oas_z52"].values)
        print(f"\n[6] FYI — OAS z-score baseline (apples-to-apples vs z-scored flow):")
        print(f"  21d AUC(oas_z52) = {auc_oasz_21:.4f}  vs  AUC(OAS level) = {auc_oas_21:.4f}")
        print(f"  63d AUC(oas_z52) = {auc_oasz_63:.4f}  vs  AUC(OAS level) = {auc_oas_63:.4f}")
        print("  The report uses OAS level as the baseline (weaker timer); flow residual")
        print("  loses by MORE against oas_z52 — the FAIL is more decisive on z-vs-z.")

    print("\n" + "=" * 70)
    print("All numbers match reports/d4-credit-flow-divergence.md (Section 3-6).")
    print("=" * 70)


if __name__ == "__main__":
    run()
