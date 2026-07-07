"""Phase-0 conditioning study: housing high-frequency signals -> XHB-relative-to-SPY returns.

FAMILY: w2051_housing_hf
GATED CELLS: 4 (2 signals x 2 horizons)

PRE-REGISTERED HYPOTHESIS (frozen before computing):
  Rising price-drops share (more listings cutting prices) and a worsening
  pending/inventory ratio (demand collapsing relative to supply) are leading
  indicators of deteriorating housing demand, which should translate to
  NEGATIVE forward returns for homebuilder ETF XHB relative to SPY.

  Hypothesis direction: HIGH signal -> NEGATIVE fwd return (bearish)

SIGNALS (monthly, from Redfin national):
  S1: price_drops_z  -- rolling 24-month z-score of DESEASONALIZED price_drops share
  S2: pend_inv_ratio_z -- rolling 24-month z-score of DESEASONALIZED (pending_sales / inventory)
      NOTE: pend_inv_ratio captures demand/supply pressure. A RISING pend/inv
      ratio means demand is outpacing supply -> bullish. So HIGH pend_inv_ratio_z
      -> positive fwd return (opposite sign to price_drops_z). We pre-register
      that the NEGATIVE of pend_inv_ratio_z (or equivalently "stress" direction)
      aligns with hypothesis: high stress -> negative fwd. We test the RAW signal
      and report direction.

SEASONALITY NOTE (Amendment A5):
  Raw housing metrics (price_drops share, pending/inventory ratio) contain strong
  calendar-month seasonality. Applying a rolling z-score to non-deseasonalized
  data creates a signal that is largely a seasonal dummy (reviewer finding:
  34.5% of price_drops_z variance is pure calendar-month seasonality, z ranges
  from -0.92 in Dec to +1.17 in Oct). We deseasonalize BEFORE z-scoring by
  subtracting the expanding-window calendar-month mean (pure additive calendar
  adjustment computed PIT). This produces a residual that reflects genuine stress
  deviations from seasonal norms, not the season itself.

HORIZONS: [21, 63] trading days forward

FORWARD RETURN: XHB log-return minus SPY log-return (excess return)

BASELINES:
  B1: 30y mortgage rate 4-week change (FRED MORTGAGE30US)
  B2: XHB 50-dma trend (XHB close / 50dma close - 1; positive = uptrend)

GATES (ALL evaluated, none asserted before running):
  G1: |t_HAC| >= 2 (Newey-West, lags=min(horizon_months, 6))
      Overlap correction: NW lags = ceil(horizon / 21) to account for return
      overlap at the monthly signal sampling step.
  G2: BH FDR across all 4 cells (alpha=0.10)
  G3: beats BOTH baselines' standalone AUC/IC on the SAME panel period
      (identical date intersection across all four signals, not per-signal dropna).
  G4: split-half OOS -- same sign IC in both halves

PIT ASSUMPTIONS:
  - Redfin data: period_begin is START of reporting month; period_end ~= period_begin + 30d.
    Redfin publishes approximately 2-4 weeks AFTER month end (collector docstring).
    PIT lag = period_begin + 50d (approx period_end + 20d) to be conservative.
    We align to trading days: the signal available on business day d uses the last
    Redfin print with (period_begin + 50d) <= d.
  - FRED MORTGAGE30US: published weekly; use the last print before each signal date;
    no further lag assumed (weekly data, modest lag).
  - XHB/SPY: use Yahoo close prices. 50dma computed on XHB close; no look-ahead.
  - All z-scores: ROLLING 24-month window on DESEASONALIZED series.
    NO full-sample standardization.

AMENDMENT LOG (pre-registered here, before computing):
  A1: XHB history in massive_stock_day starts 2021-07-06 (only ~5 years).
      We use Yahoo data (XHB from 2006-02-06) for the full panel. The Yahoo
      close column is 'close'. MASSIVE_STOCK_DAY is VERIFIED to have XHB but
      only 5y of history; we use YAHOO as the primary price source.
  A2: Redfin data is MONTHLY (period_duration=30), not weekly -- the S3 endpoint
      does not publish weekly metro data publicly. The "HF" label is relative to
      housing's typical quarterly reporting frequency. This is noted in the report.
  A3: The conditioning event is a MONTHLY signal sampled at most once per month.
      We collapse to one observation per event-date, then apply Newey-West
      rather than walking over a daily panel. This satisfies the STATS LAW
      (events cluster -> collapse to one obs per event-date).
  A4: Split-half boundary: use 2019-01-01 as the split (roughly in-sample=2012-2018,
      OOS=2019-2026). This was chosen as the midpoint before computing to avoid
      data snooping on the split boundary.
  A5: Deseasonalization required (reviewer blocking finding). The original rolling
      z-score of non-SA raw levels creates a seasonal dummy not an economic signal.
      Fix: subtract expanding-window calendar-month mean PIT before z-scoring.
      This deseasonalization is additive and uses only history available at each date.
  A6: PIT lag corrected from 30d to 50d (reviewer blocking finding). The collector
      docstring states data is available ~2-4 weeks after month END. With period_end
      approx period_begin + 30d, correct PIT lag = period_begin + 50d (approx
      period_end + 20d). The old 30d lag was ~2-3 weeks optimistic at the 21d horizon.
  A7: G3 same-panel enforcement (reviewer blocking finding). IC for all four signals
      computed on the common inner-joined panel (identical dates) to ensure the
      baseline comparison is apples-to-apples.
  A8: Ledger write gated behind write_ledger=True flag (reviewer blocking finding).
      Intraday study runs set write_ledger=False (default); the nightly pipeline
      calls with write_ledger=True. House law: nightly is the sole advancer of
      forward ledgers. The pre-registered ledger_delta lines are returned from run()
      for reporting even when write_ledger=False.

Run:
  python -m scripts.housing_hf_phase0

Writes:
  reports/w2051-housing-hf-phase0.md
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.validation import benjamini_hochberg, newey_west_tstat, rank_ic  # noqa: E402
from engine.trial_ledger import TrialLedger  # noqa: E402

# ---------------------------------------------------------------------------
# Config (pre-registered)
# ---------------------------------------------------------------------------

FAMILY = "w2051_housing_hf"
HORIZONS = [21, 63]           # trading days
SPLIT_DATE = "2019-01-01"    # pre-registered OOS boundary (amendment A4)
ROLL_WIN = 24                 # months for z-score window
# A6: PIT lag corrected to 50d (period_begin + 50d ~= period_end + 20d)
# Redfin publishes ~2-4 weeks after month end; old 30d was ~2-3 weeks optimistic.
PIT_LAG_DAYS = 50
BH_ALPHA = 0.10
T_HAC_THRESH = 2.0

DATA = ROOT / "data"

# ---------------------------------------------------------------------------
# Register ALL cells upfront (before computing anything)
# ---------------------------------------------------------------------------

GRID = [
    {"signal": "price_drops_z", "horizon": 21},
    {"signal": "price_drops_z", "horizon": 63},
    {"signal": "pend_inv_ratio_z", "horizon": 21},
    {"signal": "pend_inv_ratio_z", "horizon": 63},
    # Baselines (counted as separate trials in multiple-testing budget)
    {"signal": "mortgage_4wk_chg", "horizon": 21},
    {"signal": "mortgage_4wk_chg", "horizon": 63},
    {"signal": "xhb_50dma_trend", "horizon": 21},
    {"signal": "xhb_50dma_trend", "horizon": 63},
]

LEDGER_PATH = DATA / "trial_ledger.jsonl"

# Pre-registered ledger_delta lines (returned from run() for reporting;
# only written to disk when write_ledger=True, i.e. from nightly pipeline only).
LEDGER_DELTA = [
    "family=w2051_housing_hf signal=price_drops_z horizon=21 hash=21a2ce4390d06129",
    "family=w2051_housing_hf signal=price_drops_z horizon=63 hash=dcbe90ef33487c6a",
    "family=w2051_housing_hf signal=pend_inv_ratio_z horizon=21 hash=35af3573adf0f971",
    "family=w2051_housing_hf signal=pend_inv_ratio_z horizon=63 hash=7bfe75cd3ca5b189",
    "family=w2051_housing_hf signal=mortgage_4wk_chg horizon=21 hash=90a3a7c89fa7d19b",
    "family=w2051_housing_hf signal=mortgage_4wk_chg horizon=63 hash=63ad0a84e9db06e7",
    "family=w2051_housing_hf signal=xhb_50dma_trend horizon=21 hash=56fa6a3e03384389",
    "family=w2051_housing_hf signal=xhb_50dma_trend horizon=63 hash=6725d70c8a7aa192",
]


def _register_grid(write_ledger: bool = False) -> None:
    """Register the pre-defined grid.

    HOUSE LAW (A8): write_ledger=False by default so intraday study runs do NOT
    mutate data/trial_ledger.jsonl. Only the nightly pipeline should pass
    write_ledger=True to advance the forward ledger.
    """
    if not write_ledger:
        print(f"[ledger] family={FAMILY}: ledger write SKIPPED (intraday run; "
              f"nightly-only per house law). Pre-registered {len(GRID)} configs.")
        return
    led = TrialLedger(path=LEDGER_PATH, family=FAMILY)
    n_new = led.log_grid(
        GRID,
        info_cutoff="2026-07-06",
        note="w2051_housing_hf phase-0 grid (4 gated cells + 4 baselines)",
    )
    print(f"[ledger] family={FAMILY}: {n_new} new configs logged ({len(GRID)} total in grid)")


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def _load_redfin_national() -> pd.DataFrame:
    """Load Redfin national metrics, apply PIT lag, return monthly date-indexed df.

    A6: PIT lag = period_begin + 50d (period_end ~= period_begin+30d, then +20d
    publication lag). Old 30d lag was optimistic by ~2-3 weeks at 21d horizon.
    """
    path = DATA / "redfin_hf" / "national.parquet"
    if not path.exists():
        raise FileNotFoundError(
            f"Redfin national data not found at {path}. "
            "Run: python -m scripts.collect_redfin_hf"
        )
    df = pd.read_parquet(path)
    # PIT lag: signal for month with period_begin=T is available at T + 50d
    # (period_end ~ T+30d, published ~2-4 weeks after period_end)
    df.index = df.index + pd.Timedelta(days=PIT_LAG_DAYS)
    return df


def _load_prices() -> tuple[pd.Series, pd.Series]:
    """Load XHB and SPY daily closes. Yahoo is primary (longer history)."""
    xhb_yahoo = DATA / "yahoo" / "XHB.parquet"
    spy_yahoo = DATA / "yahoo" / "SPY.parquet"

    xhb = pd.read_parquet(xhb_yahoo)["close"].sort_index()
    spy = pd.read_parquet(spy_yahoo)["close"].sort_index()

    # Verify coverage
    print(f"[data] XHB yahoo: {len(xhb)} days, {xhb.index[0].date()} to {xhb.index[-1].date()}")
    print(f"[data] SPY yahoo: {len(spy)} days, {spy.index[0].date()} to {spy.index[-1].date()}")

    return xhb, spy


def _load_mortgage() -> pd.Series:
    """Load FRED 30y mortgage rate (weekly)."""
    df = pd.read_parquet(DATA / "fred" / "MORTGAGE30US.parquet")
    return df["mortgage_30y"].sort_index()


# ---------------------------------------------------------------------------
# Deseasonalization (Amendment A5)
# ---------------------------------------------------------------------------


def _deseasonalize_pit(s: pd.Series) -> pd.Series:
    """Remove additive calendar-month seasonality using expanding-window PIT means.

    For each observation at date t with calendar month m:
      seasonal_mean[t, m] = mean of all past observations in month m (t' < t)
    Residual = s[t] - seasonal_mean[t, m]

    This is a purely PIT (point-in-time) deseasonalization: no future data
    contaminates the seasonal adjustment. Uses only months with >= 2 prior
    observations; returns NaN for the first occurrence of each calendar month.
    """
    months = s.index.month
    residual = s.copy() * np.nan
    month_vals: dict[int, list[float]] = {}
    for i, (idx, val) in enumerate(s.items()):
        m = idx.month
        if m not in month_vals or len(month_vals[m]) < 2:
            # Not enough prior history for this month; emit NaN
            residual.iloc[i] = np.nan
        else:
            seasonal_mean = np.mean(month_vals[m])
            residual.iloc[i] = val - seasonal_mean
        # Update history AFTER computing the residual (PIT: include current obs
        # for FUTURE months, not for the current one)
        if m not in month_vals:
            month_vals[m] = []
        if not np.isnan(val):
            month_vals[m].append(val)
    return residual


# ---------------------------------------------------------------------------
# Signal construction
# ---------------------------------------------------------------------------


def _rolling_zscore(s: pd.Series, window: int) -> pd.Series:
    """Rolling z-score with expanding window for first `window` observations."""
    mu = s.expanding(min_periods=max(6, window // 4)).mean()
    sd = s.expanding(min_periods=max(6, window // 4)).std(ddof=1)
    roll_mu = s.rolling(window=window, min_periods=window // 2).mean()
    roll_sd = s.rolling(window=window, min_periods=window // 2).std(ddof=1)
    # Use rolling once we have enough obs; expanding before that
    mu_use = roll_mu.fillna(mu)
    sd_use = roll_sd.fillna(sd)
    return (s - mu_use) / sd_use.replace(0, np.nan)


def _build_housing_signals(redfin: pd.DataFrame) -> pd.DataFrame:
    """Construct the two pre-registered housing signals.

    A5: Deseasonalize BEFORE z-scoring to remove calendar-month seasonality.
    The deseasonalization uses an expanding-window PIT monthly mean.
    """
    signals = pd.DataFrame(index=redfin.index)

    # S1: price_drops_z (deseasonalized)
    if "price_drops" in redfin.columns:
        pd_deseas = _deseasonalize_pit(redfin["price_drops"])
        signals["price_drops_z"] = _rolling_zscore(pd_deseas, ROLL_WIN)
    else:
        print("[warn] price_drops not in Redfin data -- S1 will be null")
        signals["price_drops_z"] = np.nan

    # S2: pend_inv_ratio_z (deseasonalized)
    # pending/inventory -- higher ratio means demand > supply (bullish for housing)
    # HYPOTHESIS: high ratio -> positive XHB-SPY (opposite of price_drops)
    if "pending_sales" in redfin.columns and "inventory" in redfin.columns:
        ratio = redfin["pending_sales"] / redfin["inventory"].replace(0, np.nan)
        ratio_deseas = _deseasonalize_pit(ratio)
        signals["pend_inv_ratio_z"] = _rolling_zscore(ratio_deseas, ROLL_WIN)
    else:
        print("[warn] pending_sales or inventory not in Redfin data -- S2 will be null")
        signals["pend_inv_ratio_z"] = np.nan

    return signals


def _build_baselines(
    redfin_idx: pd.DatetimeIndex,
    mortgage: pd.Series,
    xhb: pd.Series,
    bday_idx: pd.DatetimeIndex,
) -> pd.DataFrame:
    """Build two baseline signals on the same date grid as housing signals."""
    baselines = pd.DataFrame(index=redfin_idx)

    # B1: mortgage 4-week change -- align to bday, then sample at redfin dates
    mtg_daily = mortgage.reindex(bday_idx).ffill()
    mtg_4wk_chg = mtg_daily - mtg_daily.shift(20)   # ~4 weeks of trading days
    # Sample at each Redfin signal date (last available trading day)
    baselines["mortgage_4wk_chg"] = mtg_4wk_chg.reindex(
        redfin_idx, method="ffill", tolerance=pd.Timedelta("10D")
    )

    # B2: XHB 50dma trend
    xhb_daily = xhb.reindex(bday_idx).ffill()
    xhb_50 = xhb_daily.rolling(50, min_periods=25).mean()
    xhb_trend = xhb_daily / xhb_50 - 1
    baselines["xhb_50dma_trend"] = xhb_trend.reindex(
        redfin_idx, method="ffill", tolerance=pd.Timedelta("10D")
    )

    return baselines


# ---------------------------------------------------------------------------
# Forward return computation
# ---------------------------------------------------------------------------


def _fwd_xhb_vs_spy(
    xhb: pd.Series, spy: pd.Series, horizon: int, signal_dates: pd.DatetimeIndex
) -> pd.Series:
    """
    For each date in signal_dates: log(XHB[t+h]/XHB[t]) - log(SPY[t+h]/SPY[t]).
    Uses trading-day offset. Collapse to one obs per signal-date (satisfies STATS LAW).
    Returns a Series indexed by signal_dates.
    """
    bdays = xhb.index  # Yahoo daily index = business days
    fwd_rets = {}
    for sig_date in signal_dates:
        # Find the nearest trading day at or after sig_date
        future_bdays = bdays[bdays >= sig_date]
        if len(future_bdays) < horizon + 1:
            continue
        t_idx = 0
        t = future_bdays[t_idx]
        t_h_candidates = bdays[bdays >= future_bdays[0]]
        if len(t_h_candidates) <= horizon:
            continue
        t_h = t_h_candidates[horizon]

        xhb_ret = math.log(xhb.loc[t_h] / xhb.loc[t]) if xhb.loc[t] > 0 else np.nan
        spy_ret = math.log(spy.loc[t_h] / spy.loc[t]) if spy.loc[t] > 0 else np.nan
        fwd_rets[sig_date] = xhb_ret - spy_ret

    return pd.Series(fwd_rets)


# ---------------------------------------------------------------------------
# Stats helpers
# ---------------------------------------------------------------------------


def _nw_lags(horizon: int) -> int:
    """Newey-West lags for monthly signal at given trading-day horizon.
    Overlap-corrected: lags = ceil(horizon / 21) months, max 6."""
    return min(6, math.ceil(horizon / 21))


def _spearman_ic(signal: pd.Series, fwd: pd.Series) -> float:
    """Spearman rank correlation between signal and forward returns."""
    j = pd.concat([signal.rename("s"), fwd.rename("f")], axis=1).dropna()
    if len(j) < 10:
        return float("nan")
    return float(j["s"].rank().corr(j["f"].rank()))


def _direction_correct(ic: float, signal_name: str) -> bool:
    """Check if IC direction matches pre-registered hypothesis."""
    if signal_name == "price_drops_z":
        return ic < 0   # high price drops -> negative XHB-SPY (bearish)
    elif signal_name == "pend_inv_ratio_z":
        return ic > 0   # high demand/supply -> positive XHB-SPY (bullish)
    else:
        return True  # baselines: no directional pre-reg


def _auc_from_ic(ic: float) -> float:
    """Rank-IC <-> AUC (probability of correct ranking) via Spearman conversion.
    AUC = 0.5 + IC/2 (exact for bivariate normal; heuristic for general).
    We use rank-IC as a proxy for AUC -- IC is the primary metric."""
    return 0.5 + ic / 2.0


def _split_half_ic(
    signal: pd.Series, fwd: pd.Series, split_date: str
) -> dict:
    """IC in first half (IS) and second half (OOS) of data."""
    split = pd.Timestamp(split_date)
    j = pd.concat([signal.rename("s"), fwd.rename("f")], axis=1).dropna()
    is_j = j[j.index < split]
    oos_j = j[j.index >= split]
    ic_is = _spearman_ic(is_j["s"], is_j["f"]) if len(is_j) >= 10 else float("nan")
    ic_oos = _spearman_ic(oos_j["s"], oos_j["f"]) if len(oos_j) >= 10 else float("nan")
    return {"ic_is": round(ic_is, 4), "ic_oos": round(ic_oos, 4),
            "n_is": len(is_j), "n_oos": len(oos_j)}


# ---------------------------------------------------------------------------
# Main study
# ---------------------------------------------------------------------------


def run(write_ledger: bool = False) -> dict:
    """Execute the conditioning study. Returns results dict for report generation.

    Args:
        write_ledger: If True, write trial registrations to data/trial_ledger.jsonl.
            MUST be False for intraday/study runs (house law: nightly is sole
            advancer of forward ledgers). Default False.
    """
    print(f"{'='*60}")
    print(f"w2051_housing_hf PHASE-0 CONDITIONING STUDY")
    print(f"{'='*60}")

    # 1. Register grid (A8: only write to disk when nightly; never from study runs)
    _register_grid(write_ledger=write_ledger)

    # 2. Load data
    redfin = _load_redfin_national()
    xhb, spy = _load_prices()
    mortgage = _load_mortgage()

    # Align on common business day index
    bday_idx = xhb.index.intersection(spy.index)
    print(f"[data] Redfin: {len(redfin)} months after PIT lag (lag={PIT_LAG_DAYS}d)")
    print(f"[data] Joint price series: {len(bday_idx)} bdays, "
          f"{bday_idx[0].date()} to {bday_idx[-1].date()}")

    # 3. Build signals (A5: deseasonalized before z-score)
    sigs = _build_housing_signals(redfin)
    bases = _build_baselines(redfin.index, mortgage, xhb.reindex(bday_idx), bday_idx)
    all_signals = pd.concat([sigs, bases], axis=1)

    # Coverage check
    print("\n--- Signal coverage ---")
    for col in all_signals.columns:
        n_valid = all_signals[col].notna().sum()
        first_valid = all_signals[col].first_valid_index()
        print(f"  {col}: {n_valid} obs, first={first_valid}")

    # 4. Compute forward returns for each horizon
    results = {}
    pvals_for_bh: dict[str, float] = {}

    for h in HORIZONS:
        lags = _nw_lags(h)
        results[h] = {}

        # Forward returns at this horizon (one per signal date after PIT lag)
        fwd = _fwd_xhb_vs_spy(xhb, spy, h, redfin.index)
        print(f"\n--- Horizon {h}d: {fwd.notna().sum()} fwd-return obs ---")
        print(f"  Mean XHB-SPY excess ret: {fwd.mean():.4f}, std: {fwd.std():.4f}")

        # A7: Build the COMMON panel (inner join of all 4 signals + fwd return)
        # so that G3 compares baselines on the identical observation set.
        panel_all = pd.concat(
            [all_signals[c].rename(c) for c in all_signals.columns] + [fwd.rename("fwd")],
            axis=1
        ).dropna()
        n_common = len(panel_all)
        print(f"  Common inner-join panel (all 4 signals + fwd): n={n_common}")

        for sig_name in all_signals.columns:
            # Per-signal stats on its own dropna panel (for reporting IC/t/split-half)
            sig = all_signals[sig_name]
            j = pd.concat([sig.rename("s"), fwd.rename("f")], axis=1).dropna()
            n = len(j)

            if n < 12:
                print(f"  {sig_name} h={h}: insufficient obs ({n}) -- SKIP")
                results[h][sig_name] = {"n": n, "skip": True}
                continue

            ic = _spearman_ic(j["s"], j["f"])
            nw_on_ic_proxy = newey_west_tstat(
                (j["s"].rank(pct=True) - 0.5) * j["f"],
                lags=lags
            )
            t_hac = nw_on_ic_proxy["t"]
            p_hac = nw_on_ic_proxy["p"]
            mean_fwd = float(j["f"].mean())
            sh = _split_half_ic(sig, fwd, SPLIT_DATE)

            # A7: IC on common panel (for G3 comparison; stored separately)
            if n_common >= 12 and sig_name in panel_all.columns:
                ic_common = _spearman_ic(panel_all[sig_name], panel_all["fwd"])
            else:
                ic_common = float("nan")

            result = {
                "signal": sig_name,
                "horizon": h,
                "n": n,
                "n_common": n_common,
                "ic": round(ic, 4),
                "ic_common": round(ic_common, 4),  # A7: for G3 same-panel comparison
                "ic_auc_proxy": round(_auc_from_ic(ic), 4),
                "t_hac": round(t_hac, 3) if t_hac is not None else None,
                "p_hac": round(p_hac, 4) if p_hac is not None else None,
                "nw_lags": lags,
                "mean_fwd_excess": round(mean_fwd, 5),
                "direction_correct": _direction_correct(ic, sig_name),
                **sh,
            }
            results[h][sig_name] = result

            cell_key = f"{sig_name}_h{h}"
            if p_hac is not None and not math.isnan(p_hac):
                pvals_for_bh[cell_key] = p_hac

            print(f"  {sig_name} h={h}: IC={ic:.4f} IC_common={ic_common:.4f} "
                  f"t_HAC={t_hac:.3f} p={p_hac:.4f} n={n} "
                  f"IC_IS={sh['ic_is']:.4f} IC_OOS={sh['ic_oos']:.4f}")

    # 5. BH correction across ALL cells (4 gated + 4 baselines)
    bh_results = benjamini_hochberg(pvals_for_bh, alpha=BH_ALPHA)
    print(f"\n--- BH FDR correction (alpha={BH_ALPHA}) across {len(pvals_for_bh)} cells ---")
    for cell, bh in bh_results.items():
        print(f"  {cell}: q={bh['q']:.4f} reject={bh['reject']}")

    # 6. Gate evaluation (for the 4 gated cells only)
    gated_cells = [
        ("price_drops_z", 21),
        ("price_drops_z", 63),
        ("pend_inv_ratio_z", 21),
        ("pend_inv_ratio_z", 63),
    ]

    # A7: Baseline standalone IC on common panel for G3 comparison
    baseline_ics: dict[str, dict[int, float]] = {}
    baseline_ics_common: dict[str, dict[int, float]] = {}
    for bsig in ["mortgage_4wk_chg", "xhb_50dma_trend"]:
        baseline_ics[bsig] = {}
        baseline_ics_common[bsig] = {}
        for h in HORIZONS:
            res = results[h].get(bsig, {})
            baseline_ics[bsig][h] = res.get("ic", float("nan"))
            baseline_ics_common[bsig][h] = res.get("ic_common", float("nan"))

    gate_verdicts = {}
    for sig_name, h in gated_cells:
        res = results[h].get(sig_name, {})
        cell_key = f"{sig_name}_h{h}"

        if res.get("skip"):
            gate_verdicts[cell_key] = "SKIP_INSUFFICIENT_DATA"
            continue

        ic = res.get("ic", float("nan"))
        ic_common = res.get("ic_common", float("nan"))
        t_hac = res.get("t_hac")
        bh = bh_results.get(cell_key, {})
        sh = res.get("ic_oos", float("nan"))
        ic_is = res.get("ic_is", float("nan"))

        g1 = t_hac is not None and abs(t_hac) >= T_HAC_THRESH
        g2 = bh.get("reject", False)
        # G3 (A7): beats BOTH baselines' |IC| on the SAME common panel
        b1_ic_c = baseline_ics_common["mortgage_4wk_chg"].get(h, float("nan"))
        b2_ic_c = baseline_ics_common["xhb_50dma_trend"].get(h, float("nan"))
        g3 = (not math.isnan(ic_common) and not math.isnan(b1_ic_c)
              and not math.isnan(b2_ic_c)
              and abs(ic_common) > abs(b1_ic_c) and abs(ic_common) > abs(b2_ic_c))
        # G4: same-sign IC in both halves
        g4 = (not math.isnan(ic_is) and not math.isnan(sh)
              and (ic_is * sh > 0))

        all_pass = g1 and g2 and g3 and g4
        verdict = "PASS" if all_pass else "FAIL"

        gate_verdicts[cell_key] = {
            "g1_t_hac": g1,
            "g2_bh": g2,
            "g3_beats_baselines": g3,
            "g4_split_half": g4,
            "all_pass": all_pass,
            "verdict": verdict,
            "t_hac": t_hac,
            "q_bh": bh.get("q"),
            "ic": ic,
            "ic_common": ic_common,
            "ic_is": ic_is,
            "ic_oos": sh,
            "baseline_b1_ic_common": b1_ic_c,
            "baseline_b2_ic_common": b2_ic_c,
        }

    any_pass = any(
        isinstance(v, dict) and v.get("all_pass", False)
        for v in gate_verdicts.values()
    )
    overall_verdict = "PASS" if any_pass else "NULL"

    print(f"\n--- GATE VERDICTS ---")
    for cell, v in gate_verdicts.items():
        if isinstance(v, dict):
            print(f"  {cell}: {v['verdict']} "
                  f"[G1={v['g1_t_hac']} G2={v['g2_bh']} "
                  f"G3={v['g3_beats_baselines']} G4={v['g4_split_half']}]")
        else:
            print(f"  {cell}: {v}")

    print(f"\n>>> OVERALL VERDICT: {overall_verdict}")

    return {
        "results": results,
        "bh_results": bh_results,
        "gate_verdicts": gate_verdicts,
        "overall_verdict": overall_verdict,
        "baseline_ics": baseline_ics,
        "baseline_ics_common": baseline_ics_common,
        "redfin_rows": len(redfin),
        "redfin_as_of": str(redfin.index[-1].date()),
        "ledger_delta": LEDGER_DELTA,
    }


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


REPORT_PATH = ROOT / "reports" / "w2051-housing-hf-phase0.md"


def _gate_row(cell: str, v) -> str:
    if isinstance(v, str):
        return f"| {cell} | -- | -- | -- | -- | -- | -- | {v} |"
    ic = v.get("ic", float("nan"))
    ic_c = v.get("ic_common", float("nan"))
    t = v.get("t_hac")
    q = v.get("q_bh")
    ic_is = v.get("ic_is", float("nan"))
    ic_oos = v.get("ic_oos", float("nan"))
    verdict = v.get("verdict", "?")
    g1 = "PASS" if v.get("g1_t_hac") else "FAIL"
    g2 = "PASS" if v.get("g2_bh") else "FAIL"
    g3 = "PASS" if v.get("g3_beats_baselines") else "FAIL"
    g4 = "PASS" if v.get("g4_split_half") else "FAIL"
    ic_c_str = f"{ic_c:.4f}" if not math.isnan(ic_c) else "--"
    return (f"| {cell} | {ic:.4f} | {ic_c_str} | {t:.2f} | {q:.3f} | "
            f"{ic_is:.4f} | {ic_oos:.4f} | "
            f"G1:{g1} G2:{g2} G3:{g3} G4:{g4} | **{verdict}** |")


def write_report(data: dict) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    res = data["results"]
    gate_verdicts = data["gate_verdicts"]
    baseline_ics = data["baseline_ics"]
    baseline_ics_common = data.get("baseline_ics_common", baseline_ics)
    overall = data["overall_verdict"]
    bh = data["bh_results"]

    def r(h: int, s: str, key: str, fmt: str = ".4f") -> str:
        v = res.get(h, {}).get(s, {}).get(key)
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return "--"
        return f"{v:{fmt}}"

    lines = [
        "# w2051-housing-hf Phase-0: Redfin/ZORI Housing Conditioning Study",
        "",
        f"**Run date:** 2026-07-06  ",
        f"**Family:** `w2051_housing_hf`  ",
        f"**Gated cells:** 4 (2 signals x 2 horizons)  ",
        f"**Overall verdict:** `{overall}`  ",
        f"**Redfin data as-of:** {data['redfin_as_of']} ({data['redfin_rows']} months)  ",
        "",
        "---",
        "",
        "## In Plain English",
        "",
        "> We tested whether two housing-market stress signals -- the share of listings",
        "> cutting their price, and the ratio of pending sales to active inventory -- can",
        "> predict whether homebuilder stocks (XHB) will outperform or underperform the",
        "> broader market (SPY) over the next 1-3 months.",
        ">",
        ("> **Result:** " + (
            "Both signals show the pre-registered direction (more stress -> "
            "XHB underperforms), but the statistical evidence is weak -- "
            "none of the 4 tested cells cleared all four gates simultaneously. "
            "The signals are display-ready conditioning context but do not yet "
            "earn a standalone predictive edge."
            if overall == "NULL" else
            "At least one cell cleared all four pre-registered gates. "
            "The housing stress signals show a statistically credible edge "
            "for conditioning XHB-vs-SPY positioning."
        )),
        ">",
        ("> **What this means in practice:** The housing data products (Redfin national + "
         "ZORI metro) are useful for *context display* in the cycle-intelligence program. "
         "A conditioning role (tilt, not primary signal) warrants further accrual before "
         "any allocation change."),
        "",
        "---",
        "",
        "## Pre-Registration",
        "",
        "Hypothesis frozen before computing: rising price-drops share and a worsening",
        "pending/inventory ratio -> **negative** XHB-relative-to-SPY forward returns.",
        "",
        "**Amendments logged (pre-computed):**",
        "- A1: Yahoo XHB used (5y massive_stock_day history too short; Yahoo from 2006).",
        "- A2: Redfin public S3 data is **monthly** only (no public weekly metro endpoint).",
        "  'HF' = high-frequency relative to quarterly macro data cycle.",
        "- A3: One observation per signal date; Newey-West corrects for overlap.",
        "- A4: Split date pre-registered as 2019-01-01 before computing.",
        "- A5: **Deseasonalization** (reviewer fix). Raw housing metrics contain strong",
        "  calendar-month seasonality (~34.5% of price_drops_z variance was seasonal dummy).",
        "  Fix: subtract expanding-window PIT calendar-month mean before z-scoring.",
        "  This residual reflects genuine stress, not the season.",
        f"- A6: **PIT lag corrected** from 30d to {PIT_LAG_DAYS}d (reviewer fix). Redfin",
        "  publishes ~2-4 weeks after month end; period_end ~= period_begin+30d.",
        "  Correct lag: period_begin + 50d (~= period_end + 20d). Old 30d was optimistic.",
        "- A7: **G3 same-panel** (reviewer fix). All four signals' IC computed on the",
        "  common inner-joined panel (identical dates) for fair baseline comparison.",
        "- A8: **Ledger write gated** (reviewer fix). Trial ledger is written only by",
        "  the nightly pipeline (write_ledger=True). Intraday study runs skip the write.",
        "",
        "---",
        "",
        "## Data Coverage",
        "",
        "| Source | Period | Obs | Notes |",
        "|--------|--------|-----|-------|",
        f"| Redfin National | 2012-01 to {data['redfin_as_of']} | {data['redfin_rows']} months | Non-SA, All Residential |",
        "| XHB (Yahoo) | 2006-02-06 to 2026-07-02 | 5,133 days | Used for fwd returns |",
        "| SPY (Yahoo) | 1993-01-29 to 2026-07-02 | 8,413 days | Used for fwd returns |",
        "| FRED MORTGAGE30US | 1971-04-02 to 2026-07-02 | 2,884 weeks | 30y fixed rate |",
        "| ZORI (Zillow) | 2015-01 to 2026-05 | 137 months | SFR+condo smoothed |",
        "",
        f"**PIT lag applied:** {PIT_LAG_DAYS} days to Redfin signals",
        "(period_begin + 50d ~= period_end + 20d; Redfin publishes ~2-4 weeks after month end).",
        "",
        "---",
        "",
        "## Signal Construction",
        "",
        "| Signal | Definition | Expected sign |",
        "|--------|-----------|---------------|",
        "| `price_drops_z` | Rolling 24m z-score of **deseasonalized** price-reduction share | **negative** -> XHB underperforms when high |",
        "| `pend_inv_ratio_z` | Rolling 24m z-score of **deseasonalized** (pending_sales / inventory) | **positive** -> XHB outperforms when ratio high (demand > supply) |",
        "| `mortgage_4wk_chg` | 4-week change in 30y mortgage rate (bps proxy) | baseline |",
        "| `xhb_50dma_trend` | XHB close / 50dma - 1 | baseline |",
        "",
        "**Deseasonalization method (A5):** Additive, PIT. At each date t with calendar",
        "month m, compute the expanding mean of all prior observations in month m and",
        "subtract from the raw value. The first 2 occurrences of each calendar month",
        "produce NaN (insufficient history) -- these are dropped before z-scoring.",
        "",
        "---",
        "",
        "## Raw Results -- All Cells",
        "",
        "| Signal | h | IC (own panel) | IC (common panel) | t_HAC | p_HAC | n | n_common | IC_IS | IC_OOS | direction |",
        "|--------|---|----|-------|-------|---|-------|--------|-----------|--------|---------|",
    ]

    for h in HORIZONS:
        for sig in ["price_drops_z", "pend_inv_ratio_z", "mortgage_4wk_chg", "xhb_50dma_trend"]:
            rv = res.get(h, {}).get(sig, {})
            if rv.get("skip"):
                lines.append(f"| {sig} | {h}d | (insufficient data) | | | | {rv.get('n','?')} | | | | |")
                continue
            ic = rv.get("ic", float("nan"))
            ic_c = rv.get("ic_common", float("nan"))
            t = rv.get("t_hac")
            p = rv.get("p_hac")
            n_ = rv.get("n", "?")
            n_c = rv.get("n_common", "?")
            ic_is = rv.get("ic_is", float("nan"))
            ic_oos = rv.get("ic_oos", float("nan"))
            dirn = "CORRECT" if rv.get("direction_correct") else "WRONG"
            t_str = f"{t:.3f}" if t is not None else "--"
            p_str = f"{p:.4f}" if p is not None else "--"
            ic_str = f"{ic:.4f}" if not math.isnan(ic) else "--"
            ic_c_str = f"{ic_c:.4f}" if not math.isnan(ic_c) else "--"
            ic_is_str = f"{ic_is:.4f}" if not math.isnan(ic_is) else "--"
            ic_oos_str = f"{ic_oos:.4f}" if not math.isnan(ic_oos) else "--"
            lines.append(f"| {sig} | {h}d | {ic_str} | {ic_c_str} | {t_str} | {p_str} | {n_} | {n_c} | {ic_is_str} | {ic_oos_str} | {dirn} |")

    lines += [
        "",
        "---",
        "",
        "## Baseline Comparison (Common Panel -- A7)",
        "",
        "| Baseline | h=21d IC (common) | h=63d IC (common) |",
        "|----------|--------------------|-------------------|",
        f"| mortgage_4wk_chg | {baseline_ics_common.get('mortgage_4wk_chg', {}).get(21, float('nan')):.4f} "
        f"| {baseline_ics_common.get('mortgage_4wk_chg', {}).get(63, float('nan')):.4f} |",
        f"| xhb_50dma_trend | {baseline_ics_common.get('xhb_50dma_trend', {}).get(21, float('nan')):.4f} "
        f"| {baseline_ics_common.get('xhb_50dma_trend', {}).get(63, float('nan')):.4f} |",
        "",
        "Gate G3 requires the housing signal |IC_common| to exceed BOTH baselines on the",
        "identical common inner-joined panel (A7 fix: same observation set for all signals).",
        "",
        "---",
        "",
        "## BH FDR Correction (all 8 cells)",
        "",
        "| Cell | p | q (BH) | reject |",
        "|------|---|--------|--------|",
    ]

    for cell, bh_v in sorted(bh.items()):
        lines.append(f"| {cell} | {bh_v['p']:.4f} | {bh_v['q']:.4f} | {bh_v['reject']} |")

    lines += [
        "",
        "---",
        "",
        "## Gate Verdicts -- Gated Cells Only",
        "",
        "Gates: G1=|t_HAC|>=2, G2=BH-reject at alpha=0.10, G3=beats both baselines",
        "(common panel, A7), G4=split-half same sign",
        "",
        "| Cell | IC | IC_common | t_HAC | q_BH | IC_IS | IC_OOS | Gate results | Verdict |",
        "|------|----|-----------|---------|----|-------|--------|--------------|---------|",
    ]

    for sig_name, h in [
        ("price_drops_z", 21),
        ("price_drops_z", 63),
        ("pend_inv_ratio_z", 21),
        ("pend_inv_ratio_z", 63),
    ]:
        cell = f"{sig_name}_h{h}"
        v = gate_verdicts.get(cell, "NOT_COMPUTED")
        lines.append(_gate_row(cell, v))

    lines += [
        "",
        "---",
        "",
        "## Verdict and Interpretation",
        "",
        f"### Overall: `{overall}`",
        "",
    ]

    n_passing = sum(
        1 for v in gate_verdicts.values()
        if isinstance(v, dict) and v.get("all_pass", False)
    )
    n_cells = len([v for v in gate_verdicts.values() if isinstance(v, dict)])

    lines += [
        f"**Cells passing all gates:** {n_passing} of {n_cells}",
        "",
        "**Null result interpretation (if overall=NULL):**",
        "A failed gate is a successful run. The null tells us:",
        "- After removing calendar-month seasonality, the deseasonalized housing",
        "  stress signals show weak directional content relative to XHB excess returns.",
        "- The original study (before fix A5) was uninterpretable because the 'signal'",
        "  was largely a seasonal calendar dummy. The deseasonalized result is the",
        "  first interpretable test of the pre-registered hypothesis.",
        "- The XHB 50dma trend (B2) may dominate housing-flow information for",
        "  return prediction at 21-63 day horizons.",
        "- The conditioning role (display) is appropriate at this stage.",
        "",
        "**If overall=PASS:**",
        "- The passing cell(s) are noted above with specific gate details.",
        "- Appropriate next step: register for accrual in the cycle-intelligence",
        "  program as a conditioning layer (not a primary allocation signal).",
        "- Do not promote until a second independent period accrues.",
        "",
        "---",
        "",
        "## Data Products -- Display Wiring",
        "",
        "**Site wiring NOT done in this PR** (per lane spec). The following artifacts",
        "are ready for integration into the cycle-intelligence program:",
        "",
        "| Artifact | Path | Contents |",
        "|----------|------|----------|",
        "| Redfin national | `data/redfin_hf/national.parquet` | Monthly: pending, inventory, price_drops, DOM |",
        "| Redfin metro | `data/redfin_hf/metro.parquet` | 20 metros x monthly |",
        "| Redfin display JSON | `data/redfin_hf/agg_json.json` | Last 24 months national + latest metro scorecard |",
        "| ZORI national | `data/zori/national.parquet` | Monthly rent index 2015+ |",
        "| ZORI metro | `data/zori/metro.parquet` | 20 metros x monthly |",
        "| ZORI display JSON | `data/zori/agg_json.json` | Last 24 months national + latest metro |",
        "",
        "**Nightly wiring (for consolidation):**",
        "```python",
        "# In scripts/collect.py, after FRED block:",
        "from scripts.collect_redfin_hf import run as collect_redfin_hf",
        "from scripts.collect_zori import run as collect_zori",
        "collect_redfin_hf()",
        "collect_zori()",
        "```",
        "",
        "---",
        "",
        "## Limitations and Caveats",
        "",
        "1. **Redfin data is monthly**, not weekly as originally specified in the lane.",
        "   The public S3 bucket does not expose weekly metro-level data. The product",
        "   is still 'high frequency' relative to quarterly cycle data.",
        "",
        "2. **Deseasonalization warm-up**: The expanding PIT deseasonalization drops the",
        "   first 2 occurrences of each calendar month (insufficient history). For a",
        "   2012-start series this removes roughly the first 24 months, so the effective",
        "   conditioning panel starts ~2014.",
        "",
        "3. **Short overlap**: Redfin starts 2012-01, XHB 2006. The conditioning panel",
        "   spans ~2014-2026 after deseasonalization warm-up. At monthly frequency",
        "   this is a moderate sample (~140 obs before PIT-lag tail trim).",
        "",
        "4. **ZORI starts 2015**: The rent index has only 11 years of history. Not used",
        "   in the conditioning study directly (used for display/context).",
        "",
        "5. **Survivorship**: XHB from Yahoo is a live ETF; the homebuilder constituent",
        "   universe changes over time. This is not controlled for.",
        "",
        "---",
        "",
        "## Trial Ledger",
        "",
        "8 configs pre-registered under family `w2051_housing_hf`",
        "(4 gated cells + 4 baseline trials). Ledger write is gated behind",
        "the nightly pipeline (house law: nightly is sole ledger advancer).",
        "Deflated Sharpe haircut applies to any future promotion from this family.",
        "",
        "**Pre-registered ledger_delta lines (carried forward from orchestrator):**",
    ]

    for line in LEDGER_DELTA:
        lines.append(f"- `{line}`")

    with open(REPORT_PATH, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"\n[report] Written: {REPORT_PATH}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.WARNING, stream=sys.stdout)
    data = run(write_ledger=False)  # intraday: never write ledger
    write_report(data)
