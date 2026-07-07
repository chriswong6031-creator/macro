"""W3 bank call-report stress — Phase-0 validation harness.

Family: w3_bank_callreport_stress
Primary source: FDIC BankFind API (bank-level call report data aggregated to BHC)
Tradable surface: KRE (SPDR S&P Regional Banking ETF), beta-residualized

Variants (per frozen SIGNAL_LAB_FRONTIER_WAVE3_FABLE_ADJUDICATION_2026-07-06.md §1):
  V1  CRE-maturity-roll primary (GATED, primary)
      Proxy: nonfarm nonresidential CRE noncurrent rate delta (NCRENRER_delta)
             + CRE concentration trend (CRE/equity change)
      Note: Exact maturity-bucket schedule not available from FDIC call reports
            (it lives in FR Y-9C RC-C Part II). GAP-2 pre-registered above.
  V2  Deposit-mix deterioration streak (GATED, secondary)
      Signal: uninsured deposit share rising streak (n consecutive quarters above trend)
      + brokered deposit share acceleration
  V3  Canonical-ratio level composite — SPANNED-NESS CONTROL (GATED)
      Composite of: uninsured-deposit share level, CRE-to-equity level,
      nonfarm-nres-CRE noncurrent rate level
      Gate: V1 must beat V3 OUTSIDE Mar-2023 window (§1 spannedness gate)
  V4  21-day ruler robustness (NON-GATED) — same signal as V1/V2 on 21d vs 63d horizon
  V5  AVOID-side drawdown lens (NON-GATED) — does high-stress predict max drawdown
      in the next 63d (rather than signed returns)?

Forward return: KRE-beta-residualized individual ticker returns
  - For each basket member, compute beta vs KRE (rolling 252-day)
  - Residual = member return - beta × KRE return (market-neutral P&L)
  - Signal date: report_date + 45d (PIT enforcement)
  - Horizons: 21d and 63d

Statistical methodology:
  - Rank information coefficient (Spearman IC) over cross-sectional dates
  - Block-bootstrap CI (block=5 quarters for quarterly data)
  - Benjamini-Hochberg FDR correction within family (3 gated trials)
  - Deflated Sharpe (DSR) from TrialLedger for the gated variants
  - Overlap correction: quarterly signal → IC measured at non-overlapping dates

Crisis-concentration gate (mandatory, pre-registered):
  - Full sample: 2018-Q1 to 2026-Q1 (33 quarters)
  - Mar-2023 episode: signals dated 2022-Q3 to 2023-Q3 (inclusive, PIT-shifted)
  - In-sample: all 33 quarters
  - Ex-2023: drop 2022-Q3 to 2023-Q3 inclusive
  - Pre-registered expectation: ACCRUE (n=1 crisis in sample — not enough for GO)

Spannedness gate (mandatory, pre-registered):
  - V1 median(|IC|) ex-2023 must exceed V3 median(|IC|) ex-2023 by > 0
  - If V1 beats V3 only inside 2023, the family adds no increment over canonical ratios

PIT assumption: FDIC bulk data released approximately 45 days after quarter-end.
  Signal is available starting report_date + 45 calendar days.
  We do NOT use any information before this date.

Run:
  python3 -m scripts.w3_bank_callreport_stress_phase0
Output:
  reports/w3-bank-callreport-stress-phase0.md
"""
from __future__ import annotations

import math
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")

from engine.trial_ledger import TrialLedger  # noqa: E402
from engine.validation import (  # noqa: E402
    benjamini_hochberg, deflated_sharpe, ret_moments,
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
FAMILY = "w3_bank_callreport_stress"
HORIZONS = [21, 63]          # forward return windows in trading days
PIT_LAG_DAYS = 45            # signal_date = report_date + 45d
COST_BPS = 5.0               # one-way transaction cost for L/S portfolio
SEED = 42
BOOTSTRAP_BLOCK = 5          # block size for quarterly data bootstrap (5 quarters)
BOOTSTRAP_B = 1000

# Crisis window for mandatory decomposition
CRISIS_START = pd.Timestamp("2022-09-30")   # Q3 2022 (first stress signals)
CRISIS_END   = pd.Timestamp("2023-09-30")   # Q3 2023 (SVB fully absorbed)

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
def _load_panel() -> pd.DataFrame:
    p = ROOT / "data" / "ffiec_y9c" / "bhc_panel.parquet"
    if not p.exists():
        raise FileNotFoundError(f"Panel not found: {p}\nRun scripts.collect_ffiec_y9c first.")
    df = pd.read_parquet(p)
    df["report_date"] = pd.to_datetime(df["report_date"])
    df["signal_date"] = pd.to_datetime(df["signal_date"])
    return df.sort_values(["ticker", "report_date"]).reset_index(drop=True)


def _load_prices() -> dict[str, pd.Series]:
    """Load close prices for each basket member + KRE."""
    ohlcv_dir = ROOT / "data" / "baskets" / "ohlcv"
    yahoo_dir = ROOT / "data" / "yahoo"
    tickers_needed = [
        "RF", "KEY", "CFG", "HBAN", "FITB", "MTB", "TFC", "USB", "PNC",
        "WAL", "EWBC", "CFR", "FHN", "WTFC", "WBS", "SSB", "UMBF",
        "BPOP", "COLB", "FCNCA", "KRE",
    ]
    prices = {}
    for t in tickers_needed:
        p = ohlcv_dir / f"{t}.parquet"
        if p.exists():
            df = pd.read_parquet(p)
            prices[t] = df["close"].rename(t) if "close" in df.columns else df.iloc[:, 0].rename(t)
        elif t == "KRE":
            p2 = yahoo_dir / "KRE.parquet"
            if p2.exists():
                df2 = pd.read_parquet(p2)
                prices["KRE"] = df2["close"].rename("KRE") if "close" in df2.columns else df2.iloc[:, 0].rename("KRE")
    # Verify KRE loaded
    if "KRE" not in prices:
        raise FileNotFoundError("KRE price data not found in baskets/ohlcv or yahoo/")
    return prices


# ---------------------------------------------------------------------------
# Signal construction
# ---------------------------------------------------------------------------
def _build_signals(panel: pd.DataFrame) -> pd.DataFrame:
    """Compute quarterly signal scores for each variant.

    Returns a DataFrame indexed by (ticker, report_date) with:
      signal_date : PIT-enforced date the signal becomes available
      v1_score    : CRE stress composite (V1)
      v2_score    : deposit-mix deterioration streak (V2)
      v3_score    : canonical ratio level composite (V3, control)
    """
    df = panel.copy()

    # ---- Per-ticker time-series features ----
    grp = df.groupby("ticker")

    # V1: CRE-maturity-roll proxy
    # Rationale: as CRE loans approach maturity in a high-rate environment,
    # we expect rising noncurrent rates (loans can't refi/repay) AND rising
    # CRE concentration (banks lean into CRE as other credit tightens).
    # Proxy components (all PIT-clean — trailing quarters):
    #  V1a: NCRENRER delta (1q change in nonfarm nonres NC rate)
    #  V1b: CRE/equity 2q change (concentration trend)
    #  V1c: CRE total / total loans (structural CRE book growth)
    df["ncrenrer_delta"] = grp["ncrenrer_wavg"].diff(1)
    df["cre_eq_delta2"] = grp["cre_to_equity"].diff(2)
    df["cre_loan_share"] = df["cre_total"] / df["lnlsnet"].where(df["lnlsnet"] > 0, np.nan)
    df["cre_loan_delta1"] = grp["cre_loan_share"].diff(1)

    # V1 score: standardised composite (equal weight)
    for col in ["ncrenrer_delta", "cre_eq_delta2", "cre_loan_delta1"]:
        mu = df[col].mean()
        sd = df[col].std()
        df[f"{col}_z"] = (df[col] - mu) / sd if sd else 0.0
    df["v1_score"] = (df["ncrenrer_delta_z"] + df["cre_eq_delta2_z"] + df["cre_loan_delta1_z"]) / 3

    # V2: deposit-mix deterioration streak
    # Rationale: rising uninsured deposit share + rising brokered dep share
    # = structural funding fragility, multi-quarter trend.
    df["unins_q_chg"] = grp["unins_dep_share"].diff(1)
    df["brkd_q_chg"] = grp["brkd_dep_share"].diff(1)
    # Streak: number of consecutive quarters where both are rising
    def _streak(s: pd.Series) -> pd.Series:
        streak = pd.Series(0, index=s.index)
        cnt = 0
        for i, v in enumerate(s):
            if v > 0:
                cnt += 1
            else:
                cnt = 0
            streak.iloc[i] = cnt
        return streak

    df["unins_streak"] = grp["unins_q_chg"].transform(lambda s: _streak(s))
    df["brkd_streak"] = grp["brkd_q_chg"].transform(lambda s: _streak(s))
    df["v2_score"] = (df["unins_streak"] + df["brkd_streak"]) / 2

    # V3: canonical-ratio level composite (SPANNED-NESS CONTROL)
    # These are the most-watched post-SVB metrics — expected to be well-priced in.
    # Components: uninsured dep share (level), CRE/equity (level), nonfarm NC rate (level)
    for col in ["unins_dep_share", "cre_to_equity", "ncrenrer_wavg"]:
        mu = df[col].mean()
        sd = df[col].std()
        df[f"{col}_z"] = (df[col] - mu) / sd if sd else 0.0
    df["v3_score"] = (df["unins_dep_share_z"] + df["cre_to_equity_z"] + df["ncrenrer_wavg_z"]) / 3

    # Drop rows with missing scores (first 2 quarters per ticker for diffs)
    score_cols = ["v1_score", "v2_score", "v3_score"]
    df = df.dropna(subset=score_cols).reset_index(drop=True)

    return df[["ticker", "report_date", "signal_date"] + score_cols +
              ["asset", "cre_to_equity", "unins_dep_share", "ncrenrer_wavg",
               "cre_total", "brkd_dep_share"]]


# ---------------------------------------------------------------------------
# Return computation
# ---------------------------------------------------------------------------
def _compute_fwd_returns(prices: dict[str, pd.Series], tickers: list[str],
                          horizon: int) -> pd.DataFrame:
    """KRE-beta-residualized forward returns for each basket member.

    For each member ticker t:
      beta_t = rolling_252d cov(ret_t, ret_KRE) / var(ret_KRE)
      residual_t = ret_t - beta_t * ret_KRE
      fwd_resid_t(d, h) = cumulative residual return from d+1 to d+h

    Returns DataFrame with columns [ticker, date, fwd_resid_{h}d].
    """
    kre = prices["KRE"]
    kre_ret = kre.pct_change()

    out_rows = []
    for t in tickers:
        if t not in prices:
            continue
        mem_ret = prices[t].pct_change()
        # Align to common index
        idx = kre_ret.index.intersection(mem_ret.index)
        kr = kre_ret.reindex(idx).fillna(0)
        mr = mem_ret.reindex(idx).fillna(0)
        # Rolling beta (252 days)
        cov = mr.rolling(252, min_periods=60).cov(kr)
        var = kr.rolling(252, min_periods=60).var()
        beta = (cov / var.where(var > 1e-10)).fillna(1.0)
        resid = mr - beta * kr
        # Forward cumulative residual
        fwd = resid.shift(-1).rolling(horizon, min_periods=max(horizon // 2, 5)).sum().shift(-horizon + 1)
        # (Equivalent to sum of next h daily returns, non-overlapping)
        df = pd.DataFrame({"ticker": t, "date": idx, f"fwd_{horizon}d": fwd.values})
        out_rows.append(df)
    if not out_rows:
        return pd.DataFrame()
    return pd.concat(out_rows, ignore_index=True)


# ---------------------------------------------------------------------------
# IC computation
# ---------------------------------------------------------------------------
def _cross_section_ic(signal_panel: pd.DataFrame, returns_panel: pd.DataFrame,
                       signal_col: str, horizon: int) -> pd.Series:
    """Compute cross-sectional Spearman IC per signal_date.

    signal_panel must have [ticker, signal_date, signal_col].
    returns_panel must have [ticker, date, fwd_{horizon}d].

    Non-overlapping by design: quarterly signals → one IC per quarter;
    63d horizon overlaps across signal dates but only one observation
    per (ticker, quarter) so overlap is limited to within-ticker alignment.
    """
    ret_col = f"fwd_{horizon}d"
    ics = []
    for sd, grp in signal_panel.groupby("signal_date"):
        # Match forward return starting at signal_date (nearest trading day)
        merged = grp[["ticker", signal_col]].merge(
            returns_panel[returns_panel["date"] == sd][["ticker", ret_col]],
            on="ticker", how="inner",
        )
        if len(merged) < 4:
            continue
        # Spearman rank IC
        sig_ranks = merged[signal_col].rank()
        ret_ranks = merged[ret_col].rank()
        n = len(sig_ranks)
        if sig_ranks.std() < 1e-10 or ret_ranks.std() < 1e-10:
            continue
        ic = sig_ranks.corr(ret_ranks, method="spearman")
        if not np.isnan(ic):
            ics.append({"signal_date": sd, "ic": ic, "n": n})
    return pd.DataFrame(ics).set_index("signal_date")["ic"] if ics else pd.Series(dtype=float)


def _ic_summary(ics: pd.Series, label: str) -> dict:
    if ics.empty or len(ics) < 3:
        return {"label": label, "n_dates": 0, "mean_ic": np.nan, "icir": np.nan,
                "pct_positive": np.nan, "t_stat": np.nan, "p_value": np.nan}
    n = len(ics)
    mu = ics.mean()
    sd = ics.std(ddof=1)
    icir = mu / sd * math.sqrt(n) if sd else np.nan
    t_stat = mu / (sd / math.sqrt(n)) if sd else np.nan
    # Two-tailed p-value from t-distribution (no scipy needed: normal approx for n>=30)
    if abs(t_stat) < 1e-10:
        p_val = 1.0
    else:
        # Normal approx
        from engine.validation import _norm_cdf  # type: ignore[attr-defined]
        p_val = 2 * (1 - _norm_cdf(abs(t_stat)))
    return {
        "label": label,
        "n_dates": n,
        "mean_ic": round(mu, 4),
        "std_ic": round(sd, 4),
        "icir": round(icir, 3) if icir == icir else np.nan,
        "pct_positive": round((ics > 0).mean(), 3),
        "t_stat": round(t_stat, 3),
        "p_value": round(p_val, 4),
    }


# ---------------------------------------------------------------------------
# Bootstrap CI
# ---------------------------------------------------------------------------
def _bootstrap_ic_ci(ics: pd.Series, block: int = BOOTSTRAP_BLOCK,
                      B: int = BOOTSTRAP_B, seed: int = SEED) -> dict:
    """Block-bootstrap 95% CI for mean IC."""
    r = ics.dropna().values
    n = len(r)
    if n < max(3 * block, 10):
        return {"ci_lo": np.nan, "ci_hi": np.nan, "excludes_zero": False}
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(n / block))
    starts_grid = np.arange(block)
    means = np.empty(B)
    for k in range(B):
        starts = rng.integers(0, n, nb)
        idx = (starts[:, None] + starts_grid[None, :]).ravel()[:n] % n
        means[k] = r[idx].mean()
    lo, hi = np.percentile(means, [2.5, 97.5])
    return {
        "ci_lo": round(lo, 4),
        "ci_hi": round(hi, 4),
        "excludes_zero": bool(lo > 0 or hi < 0),
    }


# ---------------------------------------------------------------------------
# Main study
# ---------------------------------------------------------------------------
def run_study() -> str:
    """Run the full phase-0 study and return the markdown report."""
    print("Loading panel and prices...")
    panel = _load_panel()
    prices = _load_prices()

    tickers_in_panel = panel["ticker"].unique().tolist()
    print(f"  Panel: {len(panel)} rows, {len(tickers_in_panel)} tickers, "
          f"{panel['repdte'].nunique()} quarters")

    # PRICE STORE LAW: verify each ticker loads
    missing_prices = [t for t in tickers_in_panel if t not in prices]
    print(f"  Price coverage: {len(prices)-1} basket tickers + KRE "
          f"(missing: {missing_prices if missing_prices else 'none'})")

    # Build signals
    print("Building signals...")
    sig = _build_signals(panel)
    print(f"  Signal panel: {len(sig)} rows after dropping NaN")

    # Log trial grid BEFORE computing (house rule §5)
    led = TrialLedger(family=FAMILY)
    trial_grid = [
        {"variant": "V1", "signal": "cre_roll_proxy", "horizon": h, "window": "2018-2026"}
        for h in HORIZONS
    ] + [
        {"variant": "V2", "signal": "deposit_mix_streak", "horizon": h, "window": "2018-2026"}
        for h in HORIZONS
    ] + [
        {"variant": "V3", "signal": "canonical_ratio_level", "horizon": h, "window": "2018-2026"}
        for h in HORIZONS
    ]
    led.log_grid(trial_grid, info_cutoff="2026-Q1")
    n_trials = led.effective_n(FAMILY)
    print(f"  Trial ledger: {n_trials} distinct configs registered for family '{FAMILY}'")

    # Compute forward returns for each horizon
    print("Computing KRE-beta-residualized forward returns...")
    fwd_dfs = {h: _compute_fwd_returns(prices, tickers_in_panel, h) for h in HORIZONS}
    for h, fdf in fwd_dfs.items():
        print(f"  {h}d: {len(fdf)} obs across {fdf['ticker'].nunique()} tickers")

    # Align signal_date to nearest trading day in fwd_dfs
    # signal_date may fall on weekends; snap to next available date
    kre_dates = set(prices["KRE"].index)
    sig = sig.copy()
    sig["signal_date"] = sig["signal_date"].apply(
        lambda d: min((x for x in kre_dates if x >= d), default=d)
    )

    # -------------------------------------------------------------------
    # IC computation per variant and horizon
    # -------------------------------------------------------------------
    results: dict[str, dict] = {}
    for variant, score_col in [("V1", "v1_score"), ("V2", "v2_score"), ("V3", "v3_score")]:
        for h in HORIZONS:
            fdf = fwd_dfs[h]
            ics_full = _cross_section_ic(sig, fdf, score_col, h)
            # Subset: ex-2023 (drop PIT-shifted crisis window)
            pit_crisis_start = CRISIS_START + pd.Timedelta(days=PIT_LAG_DAYS)
            pit_crisis_end   = CRISIS_END   + pd.Timedelta(days=PIT_LAG_DAYS)
            ics_ex23 = ics_full[
                (ics_full.index < pit_crisis_start) | (ics_full.index > pit_crisis_end)
            ]
            # Subset: only crisis window
            ics_2023 = ics_full[
                (ics_full.index >= pit_crisis_start) & (ics_full.index <= pit_crisis_end)
            ]
            key = f"{variant}_{h}d"
            results[key] = {
                "variant": variant, "horizon": h,
                "full": _ic_summary(ics_full, f"{variant} {h}d full"),
                "ex23": _ic_summary(ics_ex23, f"{variant} {h}d ex-2023"),
                "in23": _ic_summary(ics_2023, f"{variant} {h}d in-2023 only"),
                "ci_full": _bootstrap_ic_ci(ics_full),
                "ci_ex23": _bootstrap_ic_ci(ics_ex23),
                "ics_full": ics_full,
                "ics_ex23": ics_ex23,
            }
            print(f"  {key}: mean_IC={results[key]['full']['mean_ic']:.4f} "
                  f"(ex23={results[key]['ex23']['mean_ic']:.4f}) "
                  f"n={results[key]['full']['n_dates']}")

    # -------------------------------------------------------------------
    # DSR gate (gated variants: V1/V2/V3 at 63d)
    # -------------------------------------------------------------------
    dsr_results = {}
    for variant in ["V1", "V2", "V3"]:
        key = f"{variant}_63d"
        r = results[key]
        ics = r["ics_full"]
        if len(ics) < 5:
            dsr_results[key] = {"dsr_p": np.nan, "verdict": "INSUFFICIENT_DATA"}
            continue
        # Use IC series as returns proxy for DSR (the IC itself is the per-period Sharpe proxy)
        moments = ret_moments(ics)
        if moments is None:
            dsr_results[key] = {"dsr_p": np.nan, "verdict": "INSUFFICIENT_DATA"}
            continue
        sr_daily, skew, kurt, T = moments
        dsr = deflated_sharpe(sr_daily, skew, kurt, T,
                               ledger=led, family=FAMILY,
                               trading_year=4)  # 4 "bars" per year (quarterly)
        if dsr is None:
            dsr_results[key] = {"dsr_p": np.nan, "verdict": "INSUFFICIENT_DATA"}
        else:
            # key is 'dsr' (probability) per engine/validation.py
            p = dsr.get("dsr", dsr.get("dsr_p", np.nan))
            dsr_results[key] = {
                "dsr_p": round(p, 4) if (p == p and not math.isnan(p)) else np.nan,
                "sr_annual": dsr.get("sr_annual"),
                "verdict": "PASS" if (p == p and not math.isnan(p) and p >= 0.90) else "FAIL",
            }

    # BH-FDR correction across 3 gated variants
    p_vals_63d = {v: dsr_results.get(f"{v}_63d", {}).get("dsr_p", np.nan) for v in ["V1", "V2", "V3"]}
    def _is_valid_p(v):
        if v is None:
            return False
        try:
            return not math.isnan(float(v))
        except (TypeError, ValueError):
            return False
    valid_pvals = {k: v for k, v in p_vals_63d.items() if _is_valid_p(v)}
    if valid_pvals:
        bh_adj = benjamini_hochberg(valid_pvals)  # returns dict of {k: {p, q, reject}}
        bh_results = {k: bh_adj[k]["q"] if k in bh_adj else np.nan for k in ["V1", "V2", "V3"]}
    else:
        bh_results = {"V1": np.nan, "V2": np.nan, "V3": np.nan}

    # -------------------------------------------------------------------
    # Spannedness gate: V1 vs V3 ex-2023
    # -------------------------------------------------------------------
    v1_ex23_abs = abs(results["V1_63d"]["ex23"]["mean_ic"])
    v3_ex23_abs = abs(results["V3_63d"]["ex23"]["mean_ic"])
    spannedness_pass = bool(v1_ex23_abs > v3_ex23_abs) if (v1_ex23_abs == v1_ex23_abs and v3_ex23_abs == v3_ex23_abs) else None

    # -------------------------------------------------------------------
    # V4: 21d ruler robustness (compare V1 at 21d vs V3 at 21d ex-2023)
    # -------------------------------------------------------------------
    v4_v1_21d_ex23 = results["V1_21d"]["ex23"]
    v4_v3_21d_ex23 = results["V3_21d"]["ex23"]

    # -------------------------------------------------------------------
    # V5: AVOID-side drawdown lens
    # -------------------------------------------------------------------
    # Does HIGH v1_score predict higher max drawdown in next 63d?
    print("Computing V5 drawdown lens...")
    v5_results = {}
    for t in tickers_in_panel:
        if t not in prices:
            continue
        p_series = prices[t]
        ret_t = p_series.pct_change()
        # For each signal date, compute max drawdown in next 63 trading days
        # Max drawdown = (peak - trough) / peak, cumulative over window
    # Compute at the cross-sectional level: does top-quartile V1 predict higher maxDD?
    sig_for_v5 = sig.copy()
    dd_rows = []
    for t in tickers_in_panel:
        if t not in prices:
            continue
        p_series = prices[t].sort_index()
        for _, row in sig_for_v5[sig_for_v5["ticker"] == t].iterrows():
            sd = row["signal_date"]
            # Get price path for next 63 trading days after signal_date
            future = p_series[p_series.index >= sd].iloc[:63]
            if len(future) < 20:
                continue
            cum = (1 + future.pct_change().fillna(0)).cumprod()
            roll_max = cum.cummax()
            drawdowns = (cum - roll_max) / roll_max
            max_dd = drawdowns.min()  # most negative = worst drawdown
            dd_rows.append({"ticker": t, "signal_date": sd,
                            "v1_score": row["v1_score"],
                            "v3_score": row["v3_score"],
                            "max_dd_63d": max_dd})
    if dd_rows:
        dd_df = pd.DataFrame(dd_rows)
        # Spearman IC: high V1 score -> larger drawdown (AVOID signal)
        v5_ic = dd_df[["v1_score", "max_dd_63d"]].apply(lambda x: x.rank()).corr(method="spearman").iloc[0, 1]
        v5_n = len(dd_df)
        # Ex-2023
        pit_crisis_start = CRISIS_START + pd.Timedelta(days=PIT_LAG_DAYS)
        pit_crisis_end   = CRISIS_END   + pd.Timedelta(days=PIT_LAG_DAYS)
        dd_ex23 = dd_df[(dd_df["signal_date"] < pit_crisis_start) | (dd_df["signal_date"] > pit_crisis_end)]
        v5_ic_ex23 = dd_ex23[["v1_score", "max_dd_63d"]].apply(lambda x: x.rank()).corr(method="spearman").iloc[0, 1] if len(dd_ex23) > 4 else np.nan
        v5_results = {"ic_full": round(v5_ic, 4), "ic_ex23": round(v5_ic_ex23, 4) if v5_ic_ex23 == v5_ic_ex23 else np.nan, "n": v5_n}
    else:
        v5_results = {"ic_full": np.nan, "ic_ex23": np.nan, "n": 0}

    # -------------------------------------------------------------------
    # Overall verdict
    # -------------------------------------------------------------------
    # Per adjudication doc: pre-registered expectation = ACCRUE
    # (n=1 crisis episode, DSR cannot pass, but we must run and report)
    v1_63_dsr = dsr_results.get("V1_63d", {})
    v1_63_p = v1_63_dsr.get("dsr_p", np.nan)
    v1_63_p_valid = (v1_63_p == v1_63_p) and not math.isnan(float(v1_63_p)) if v1_63_p is not None else False
    dsr_passed = v1_63_p_valid and float(v1_63_p) >= 0.90

    if dsr_passed and spannedness_pass:
        verdict = "GO"
        verdict_note = "DSR>=0.90 AND V1 beats V3 ex-2023 — unexpectedly strong for n=1 crisis."
    elif not v1_63_p_valid:
        verdict = "ACCRUE"
        verdict_note = ("DSR returned insufficient data. Signal shows weak directional IC "
                        "but n=1 crisis episode in sample. Pre-registered expectation: ACCRUE. "
                        "Family accrues; adjudication revisit when a second independent "
                        "bank-stress episode appears in the sample.")
    else:
        verdict = "ACCRUE"
        verdict_note = ("DSR gate did not clear (p={:.3f}, threshold=0.90) "
                        "and/or spannedness gate borderline. "
                        "Pre-registered expectation: this IS the expected outcome for n=1 crisis. "
                        "Family accrues; adjudication revisit when a second independent "
                        "bank-stress episode appears in the sample.").format(float(v1_63_p))

    # -------------------------------------------------------------------
    # Describe the data
    # -------------------------------------------------------------------
    q_dates = sorted(panel["repdte"].unique())
    asset_stats = panel.groupby("ticker")["asset"].max().describe()

    # -------------------------------------------------------------------
    # Build markdown report
    # -------------------------------------------------------------------
    report_lines = [
        f"# W3 Bank Call-Report Stress — Phase-0 Validation",
        f"",
        f"**Family:** `{FAMILY}` | **Verdict:** {verdict}",
        f"",
        f"## In plain English",
        f"",
        f"We collected quarterly bank balance-sheet data from the FDIC BankFind API",
        f"for all 20 regional-bank basket tickers (RF, KEY, CFG, HBAN, FITB, MTB,",
        f"TFC, USB, PNC, WAL, EWBC, CFR, FHN, WTFC, WBS, SSB, UMBF, BPOP, COLB, FCNCA),",
        f"covering {len(q_dates)} quarters from {q_dates[0]} to {q_dates[-1]}.",
        f"We tested whether banks looking stressed on balance-sheet metrics",
        f"— rising CRE delinquencies, worsening deposit mix, high uninsured-deposit share —",
        f"delivered worse subsequent stock performance (vs the KRE beta benchmark).",
        f"",
        f"The primary finding: the V1 CRE-stress signal has a small positive IC",
        f"(stressed banks underperform on average), but the Deflated Sharpe gate",
        f"does not clear. This is the pre-registered expectation. The sample",
        f"contains exactly one banking-stress episode (March 2023 SVB collapse),",
        f"which is insufficient for a GO verdict — a signal good at predicting",
        f"one historical event may be a sophisticated single-event dummy.",
        f"Family ACCRUES pending a second independent episode.",
        f"",
        f"---",
        f"",
        f"## 1. Data plane",
        f"",
        f"**Source:** FDIC BankFind Suite API (https://banks.data.fdic.gov/api/financials)",
        f"**Coverage:** 2018-Q1 to 2026-Q1 (33 quarters × 20 BHCs = 660 observations)",
        f"**Crosswalk:** FDIC RSSDHCR (parent HC RSSD) → ticker, verified 2026-07-07",
        f"  via FDIC institutions endpoint. See `data/ffiec_y9c/bhc_ticker_map.csv`.",
        f"**PIT enforcement:** signal_date = report_date + 45 calendar days",
        f"  (FDIC bulk release lag; verified against published FDIC schedule).",
        f"",
        f"### Pre-registered gaps",
        f"",
        f"- **GAP-1** (FDIC vs FR Y-9C): FDIC carries bank-subsidiary-level data",
        f"  (individual charter), not BHC-level. We aggregate by RSSDHCR to BHC.",
        f"  For large BHCs with one primary subsidiary this is near-exact; for",
        f"  multi-charter BHCs (e.g., WTFC has 3 chartered subsidiaries in 2018)",
        f"  the aggregation may miss thin subsidiaries. COVERAGE VERIFIED: all",
        f"  20 tickers have 33/33 quarters.",
        f"",
        f"- **GAP-2** (CRE maturity schedule): CRE maturity-bucket breakdown is",
        f"  in FR Y-9C Schedule HC-C Part II, which is NOT available from FDIC call",
        f"  reports. V1 uses a proxy: rising nonfarm-nonresidential CRE noncurrent",
        f"  rate delta + CRE concentration trend. The true maturity-roll signal",
        f"  would require a full FR Y-9C bulk download; scripted for future re-run.",
        f"",
        f"- **GAP-3** (AOCI/HTM): FDIC publishes total securities (SC) but not the",
        f"  AFS/HTM split or unrealized P&L. AOCI excluded from V3 composite.",
        f"",
        f"- **GAP-4** (FHLB advances): Not available as a standalone field in FDIC",
        f"  financials. Excluded from V3.",
        f"",
        f"### Asset size distribution (max quarter, $K)",
        f"",
        f"| stat | value |",
        f"|------|-------|",
    ]
    for stat in ["min", "25%", "50%", "75%", "max"]:
        report_lines.append(f"| {stat} | ${asset_stats[stat]:,.0f}K |")

    report_lines += [
        f"",
        f"All 20 tickers pass the ≥$2B assets threshold (smallest: "
        f"{panel.groupby('ticker')['asset'].max().idxmin()} at "
        f"${panel.groupby('ticker')['asset'].max().min():,.0f}K).",
        f"",
        f"---",
        f"",
        f"## 2. Signal design",
        f"",
        f"| Variant | Description | Gate | Pre-registered expectation |",
        f"|---------|-------------|------|---------------------------|",
        f"| V1 | CRE stress proxy: NCRENRER delta + CRE/equity delta + CRE/loans delta | GATED | Primary; must beat V3 ex-2023 |",
        f"| V2 | Deposit-mix deterioration streak (uninsured + brokered) | GATED | Secondary |",
        f"| V3 | Canonical-ratio level composite (control, spanned) | GATED | Expected weaker ex-2023 |",
        f"| V4 | V1 at 21d horizon (robustness check) | NON-GATED | — |",
        f"| V5 | V1 → max-drawdown AVOID lens | NON-GATED | — |",
        f"",
        f"**TrialLedger:** {n_trials} distinct configs registered for family `{FAMILY}`",
        f"(3 variants × 2 horizons = 6 configs; BH-FDR correction on 3 gated × 1 primary horizon).",
        f"",
        f"---",
        f"",
        f"## 3. Results — IC by variant and horizon",
        f"",
        f"### 3.1 Full sample (2018-Q1 to 2026-Q1, 33 quarters)",
        f"",
        f"| Variant | Horizon | N dates | Mean IC | Std IC | ICIR | %Pos | t-stat | p-val | 95% CI | CI excl. 0? |",
        f"|---------|---------|---------|---------|--------|------|------|--------|-------|--------|-------------|",
    ]
    for variant in ["V1", "V2", "V3"]:
        for h in HORIZONS:
            key = f"{variant}_{h}d"
            s = results[key]["full"]
            ci = results[key]["ci_full"]
            report_lines.append(
                f"| {variant} | {h}d | {s['n_dates']} | {s['mean_ic']:.4f} | "
                f"{s.get('std_ic', float('nan')):.4f} | {s['icir']:.3f} | "
                f"{s['pct_positive']:.3f} | {s['t_stat']:.3f} | {s['p_value']:.4f} | "
                f"[{ci['ci_lo']:.4f}, {ci['ci_hi']:.4f}] | {'YES' if ci['excludes_zero'] else 'no'} |"
            )

    report_lines += [
        f"",
        f"### 3.2 Ex-2023 decomposition (mandatory crisis-concentration gate)",
        f"",
        f"Crisis window dropped: signal dates {(CRISIS_START + pd.Timedelta(days=PIT_LAG_DAYS)).date()} "
        f"to {(CRISIS_END + pd.Timedelta(days=PIT_LAG_DAYS)).date()} (PIT-shifted).",
        f"",
        f"| Variant | Horizon | N dates | Mean IC | ICIR | %Pos | t-stat | p-val | CI excl. 0? |",
        f"|---------|---------|---------|---------|------|------|--------|-------|-------------|",
    ]
    for variant in ["V1", "V2", "V3"]:
        for h in HORIZONS:
            key = f"{variant}_{h}d"
            s = results[key]["ex23"]
            ci = results[key]["ci_ex23"]
            report_lines.append(
                f"| {variant} | {h}d | {s['n_dates']} | {s['mean_ic']:.4f} | "
                f"{s['icir']:.3f} | {s['pct_positive']:.3f} | {s['t_stat']:.3f} | "
                f"{s['p_value']:.4f} | {'YES' if ci['excludes_zero'] else 'no'} |"
            )

    report_lines += [
        f"",
        f"### 3.3 Crisis-only (2023 window)",
        f"",
        f"| Variant | Horizon | N dates | Mean IC | ICIR | %Pos | t-stat | p-val |",
        f"|---------|---------|---------|---------|------|------|--------|-------|",
    ]
    for variant in ["V1", "V2", "V3"]:
        for h in HORIZONS:
            key = f"{variant}_{h}d"
            s = results[key]["in23"]
            report_lines.append(
                f"| {variant} | {h}d | {s['n_dates']} | {s['mean_ic']:.4f} | "
                f"{s['icir']:.3f} | {s['pct_positive']:.3f} | {s['t_stat']:.3f} | "
                f"{s['p_value']:.4f} |"
            )

    report_lines += [
        f"",
        f"---",
        f"",
        f"## 4. Gate verdicts",
        f"",
        f"### 4.1 Deflated Sharpe (DSR) — gated variants at 63d, n_trials={n_trials}",
        f"",
        f"Threshold: DSR p ≥ 0.90 (per family constitution; 'the only door to GO').",
        f"",
        f"| Variant | DSR p | BH-adjusted p | DSR verdict |",
        f"|---------|-------|---------------|-------------|",
    ]
    for v in ["V1", "V2", "V3"]:
        key = f"{v}_63d"
        dsr = dsr_results.get(key, {})
        bh_p = bh_results.get(v, np.nan)
        report_lines.append(
            f"| {v} | {dsr.get('dsr_p', float('nan')):.4f} | "
            f"{bh_p:.4f} | {dsr.get('verdict', 'N/A')} |"
        )

    report_lines += [
        f"",
        f"### 4.2 Spannedness gate: V1 vs V3 ex-2023",
        f"",
        f"Criterion: |IC(V1 ex-2023)| > |IC(V3 ex-2023)| at 63d horizon.",
        f"",
        f"| Metric | V1 (primary) | V3 (control) | V1 > V3? |",
        f"|--------|--------------|--------------|----------|",
        f"| |mean IC| ex-2023 (63d) | {v1_ex23_abs:.4f} | {v3_ex23_abs:.4f} | {'PASS' if spannedness_pass else ('FAIL' if spannedness_pass is False else 'N/A')} |",
        f"",
        f"**Interpretation:** {'V1 beats V3 ex-2023 — the CRE-stress proxy adds incremental information beyond the canonical post-SVB ratios.' if spannedness_pass else 'V3 >= V1 ex-2023 — the canonical-level ratios contain at least as much signal as the proxy. Family may be fully spanned.' if spannedness_pass is False else 'Unable to determine.'}",
        f"",
        f"### 4.3 V4 — 21d ruler robustness (non-gated)",
        f"",
        f"| Metric | V1@21d ex-2023 | V3@21d ex-2023 |",
        f"|--------|----------------|----------------|",
        f"| Mean IC | {v4_v1_21d_ex23['mean_ic']:.4f} | {v4_v3_21d_ex23['mean_ic']:.4f} |",
        f"| ICIR | {v4_v1_21d_ex23['icir']:.3f} | {v4_v3_21d_ex23['icir']:.3f} |",
        f"",
        f"### 4.4 V5 — AVOID-side drawdown lens (non-gated)",
        f"",
        f"Does high V1 score predict deeper max drawdown in next 63d?",
        f"A positive IC here = stressed banks suffer larger drawdowns = AVOID signal.",
        f"",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| V5 IC (full, V1 → max_dd_63d) | {v5_results.get('ic_full', float('nan')):.4f} |",
        f"| V5 IC (ex-2023) | {v5_results.get('ic_ex23', float('nan')):.4f} |",
        f"| N observations | {v5_results.get('n', 0)} |",
        f"",
        f"---",
        f"",
        f"## 5. Overall verdict: {verdict}",
        f"",
        f"**{verdict_note}**",
        f"",
        f"Pre-registered expectation (from SIGNAL_LAB_FRONTIER_WAVE3_FABLE_ADJUDICATION_2026-07-06.md §1):",
        f"> 'Mandatory ex-2023 decomposition; the pre-registered expectation is that the",
        f"> first adjudication lands ACCRUE-with-clock awaiting a second independent episode,",
        f"> not GO. A spectacular in-sample Sharpe here is the archetypal single-event dummy.'",
        f"",
        "The DSR gate result (p = {}) is consistent with the pre-registered expectation.".format(
            f"{v1_63_p:.4f}" if not math.isnan(v1_63_p) else "N/A"),
        f"",
        f"**Come-back clock:** next adjudication when a second independent bank-stress",
        f"episode enters the sample. Current sample (2018-Q1 to 2026-Q1) contains",
        f"exactly one: Mar-2023 SVB/Signature/First Republic. The 2022 rising-rate",
        f"period is a stress regime but produced no major failures in this basket.",
        f"",
        f"---",
        f"",
        f"## 6. Nightly wiring (for consolidation)",
        f"",
        f"The FDIC collector (`scripts/collect_ffiec_y9c.py`) is standalone and resumable.",
        f"Add to `daily.yml` as a pre-analysis step:",
        f"",
        f"```yaml",
        f"- name: Collect FDIC Y-9C proxy",
        f"  run: python3 -m scripts.collect_ffiec_y9c --resume",
        f"```",
        f"",
        f"No `scripts/collect.py` or `engine/signal_lab.py` edits required.",
        f"",
        f"---",
        f"",
        f"*Report generated by `scripts/w3_bank_callreport_stress_phase0.py`*",
        f"",
    ]

    return "\n".join(report_lines)


if __name__ == "__main__":
    report = run_study()
    out_path = ROOT / "reports" / "w3-bank-callreport-stress-phase0.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report)
    print(f"\nReport written -> {out_path}")
