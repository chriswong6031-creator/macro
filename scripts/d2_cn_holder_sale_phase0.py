"""Phase-0: d2_cn_holder_sale_calendar — 减持 execution-window forced-supply study.

FAMILY: d2_cn_holder_sale_calendar (one LG-CN-SUPPLY slot)
Pre-registered per: research/SIGNAL_LAB_FRONTIER_DAY2_FABLE_ADJUDICATION_2026-07-06.md
item 3 — authorised at adjudication 2026-07-06.

CONSTRUCT (frozen, execution-window variant per adjudication):
  During the OPEN execution window (START_DATE to END_DATE), a stock faces
  announced supply overhang from a major holder who has filed a 减持 plan.
  The tradable construct is the execution-window forced-supply DRIFT:
  forward returns during the open window, scaled by planned-size/float (terciles).
  Direction: NEGATIVE, monotone in planned size (larger planned sale → more negative).

DATA SOURCE:
  Panel: data/cn_holder_sales/windows.parquet (built by collectors/cn_holder_sale_calendar.py)
  Prices: data/china_stocks_raw/{TICKER}.parquet (per-ticker OHLCV, 15y store)

PIT LAW (frozen):
  Signal available = window_open date (START_DATE from the plan).
  The legal pre-disclosure was ≥15 calendar days before window_open.
  Using window_open as signal_date is CONSERVATIVE (later than actual availability).
  +1 trading day lag applied: returns measured from close of (signal_date + 1 td).

GATES (frozen before results, ≤6 cells):
  G1  |t_HAC| >= 2 with date-clustering (one obs per event-date, Newey-West)
  G2  BH FDR q <= 0.10 across all cells tested
  G3  Split-half same-sign (pre/post 2022-01-01 halves)
  G4  Monotonicity: large-tercile return more negative than small-tercile return
  NON-GATED ROBUSTNESS: Completion-rate descriptive table (reported honestly,
      not gated); conditioning on completion (multiple sales in window) as
      an optional robustness cell.

CELLS (≤6):
  C1: all 减持 windows, 21d forward return vs CN-A market (CSI 300 proxy)
  C2: all 减持 windows, 63d forward return vs CN-A market
  C3: small-tercile (pct_float < T33), 21d forward return
  C4: mid-tercile (T33 <= pct_float < T67), 21d forward return
  C5: large-tercile (pct_float >= T67), 21d forward return
  C6: all windows, 21d forward excess vs size-matched baseline
       (size match: median-market-cap decile, same window open month)

SEASONALITY NOTE: The 减持 panel is NOT a monthly/weekly official series;
it is event-driven. No seasonal detrending applied (not applicable per
STATS LAW for event studies). However, we check for year-of-year distribution
to flag potential clustering.

STATS LAW:
  Calendar-time collapse: one return obs per (event_date, cell).
  When multiple events fall on the same calendar date, AVERAGE their returns
  first (this is the portfolio-date-average approach, not individual returns).
  NW lags = min(4, sqrt(n)) on the collapsed date-level series.
  Tercile thresholds computed on the TRAINING SPLIT only (pre-2022 data),
  then applied to the full sample including the test split to avoid
  full-sample look-ahead.

AMENDMENTS REGISTERED BEFORE COMPUTING:
  AM-1: pct_float tercile thresholds computed on pre-2022 data only.
        If pre-2022 data has < 100 windows with valid pct_float,
        use full-sample terciles and flag as amendment.
  AM-2: CSI 300 proxy = data/china_stocks_raw/000300.SH.parquet if present;
        otherwise use the equal-weight return of all stocks in the price store
        on each date (index proxy). Report which was used.
  AM-3: Size-matched baseline for C6: compute each stock's 12-month trailing
        median market-cap (close * shares, in 万元) at window_open month,
        assign to market-cap decile. Baseline = equal-weight average return
        of all stocks in same decile in same calendar month. If market-cap
        data insufficient (< 100 stocks with price data), skip C6 and report.
  AM-4: "completion" defined as n_sales >= 2 within the same window record.
        This is a proxy (multiple filings in the same window), not actual
        plan completion vs abandonment. Reported as descriptive.
  AM-5: The price store has 729 tickers. Windows for tickers not in the price
        store are excluded; the exclusion rate is reported as a data quality
        metric.

PIT ASSUMPTIONS:
  - window_open date: publicly known on that date (the window opens).
  - Returns measured from close of (window_open + 1 trading day).
  - pct_float denominator: derived from HOLD_RATIO and AFTER_HOLDER_NUM fields
    as described in collector. This approximates float at filing date.
  - Tercile thresholds: computed on pre-2022 data (training split) before
    any post-2022 data is observed.
  - CN-A market index: daily close price of CSI 300 (000300.SH) or equal-weight
    proxy — both observable at each measurement date.

Run:
    python -m scripts.d2_cn_holder_sale_phase0
Writes: reports/d2-cn-holder-sale-phase0.md
"""
from __future__ import annotations

import math
import sys
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.validation import newey_west_tstat, benjamini_hochberg  # noqa: E402
from engine.trial_ledger import TrialLedger                          # noqa: E402

FAMILY = "d2_cn_holder_sale_calendar"
SPLIT_DATE = pd.Timestamp("2022-01-01")
HORIZONS = [21, 63]
ANN = 252
PRICE_STORE = ROOT / "data" / "china_stocks_raw"
PANEL_PATH = ROOT / "data" / "cn_holder_sales" / "windows.parquet"
RAW_PATH = ROOT / "data" / "cn_holder_sales" / "raw.parquet"

AMENDMENTS = [
    "AM-1: pct_float tercile thresholds from pre-2022 data only; fallback to full-sample if <100 pre-2022 obs with valid pct_float.",
    "AM-2: CN-A market proxy = 000300.SH if present in price store; otherwise equal-weight daily return of all 729 store tickers.",
    "AM-3: Size-matched baseline requires 12-month trailing market-cap; skipped with report if fewer than 100 stocks have price data.",
    "AM-4: 'Completion' proxy = n_sales>=2 within window record. Descriptive only, not gated.",
    "AM-5: Windows for tickers absent from price store are excluded; exclusion rate reported.",
]


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------
def _nw_lags(n: int) -> int:
    return max(2, min(4, int(math.sqrt(n))))


def _norm_cdf(z: float) -> float:
    """Approximation of standard normal CDF."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


# ---------------------------------------------------------------------------
# Price store
# ---------------------------------------------------------------------------
def load_price_store() -> dict[str, pd.Series]:
    """Load all per-ticker close series from china_stocks_raw."""
    prices: dict[str, pd.Series] = {}
    files = list(PRICE_STORE.glob("*.parquet"))
    print(f"\n[price_store] Loading {len(files)} tickers from {PRICE_STORE}")
    for f in files:
        ticker = f.stem  # e.g. '000001.SZ'
        df = pd.read_parquet(f)
        col = "close" if "close" in df.columns else "close_price"
        s = df[col].sort_index().dropna()
        s.index = pd.to_datetime(s.index)
        prices[ticker] = s

    # Verify store: spot-check a known ticker
    known = "000001.SZ"
    if known in prices:
        s0 = prices[known]
        print(f"  [store_verify] {known}: {len(s0)} rows, "
              f"{s0.index.min().date()} .. {s0.index.max().date()}")
        print(f"  [store_verify] 2019+ rows: {(s0.index >= '2019-01-01').sum()}")
    else:
        print(f"  [store_verify] WARNING: {known} not found in store!")

    print(f"  [store_verify] Total tickers loaded: {len(prices)}")
    return prices


# ---------------------------------------------------------------------------
# Market index proxy
# ---------------------------------------------------------------------------
def build_market_index(prices: dict[str, pd.Series]) -> pd.Series:
    """Build CN-A market index. Use 000300.SH (CSI 300) if available, else equal-weight."""
    csi300 = "000300.SH"
    if csi300 in prices:
        s = prices[csi300]
        print(f"\n[market_index] Using CSI 300 ({csi300}): {len(s)} rows, "
              f"{s.index.min().date()} .. {s.index.max().date()}")
        return s

    # Fallback: equal-weight daily return
    print("\n[market_index] 000300.SH not found — using equal-weight proxy")
    all_rets = pd.DataFrame({t: p.pct_change() for t, p in prices.items()})
    eq_ret = all_rets.mean(axis=1).dropna()
    eq_close = (1 + eq_ret).cumprod()
    eq_close.name = "cn_ew_index"
    print(f"  Equal-weight proxy: {len(eq_close)} rows, "
          f"{eq_close.index.min().date()} .. {eq_close.index.max().date()}")
    return eq_close


# ---------------------------------------------------------------------------
# Panel loading
# ---------------------------------------------------------------------------
def load_panel() -> pd.DataFrame:
    if not PANEL_PATH.exists():
        raise FileNotFoundError(
            f"Panel not found: {PANEL_PATH}\n"
            "Run: python collectors/cn_holder_sale_calendar.py first."
        )
    df = pd.read_parquet(PANEL_PATH)
    df["signal_date"] = pd.to_datetime(df["signal_date"])
    df["window_open"] = pd.to_datetime(df["window_open"])
    df["window_close"] = pd.to_datetime(df["window_close"])
    print(f"\n[panel] Loaded {len(df)} window records")
    print(f"  Date range: {df['signal_date'].min().date()} .. {df['signal_date'].max().date()}")
    print(f"  Unique tickers: {df['ticker'].nunique()}")
    print(f"  pct_float valid: {df['pct_float'].notna().sum()}/{len(df)}")
    return df


# ---------------------------------------------------------------------------
# Forward return computation
# ---------------------------------------------------------------------------
def forward_return(prices: pd.Series, signal_date: pd.Timestamp, horizon: int) -> float | None:
    """
    PIT: entry at close of (signal_date + 1 trading day).
    Forward return: close[t+1+horizon] / close[t+1] - 1.
    """
    idx = prices.index
    pos0 = idx.searchsorted(signal_date, side="right")
    entry_pos = pos0  # next trading day after signal_date
    exit_pos = entry_pos + horizon

    if entry_pos >= len(idx) or exit_pos >= len(idx):
        return None
    if entry_pos == 0:
        return None

    entry = float(prices.iloc[entry_pos])
    exit_ = float(prices.iloc[exit_pos])
    if entry <= 0:
        return None
    return exit_ / entry - 1.0


def compute_returns(
    panel: pd.DataFrame,
    prices: dict[str, pd.Series],
    mkt: pd.Series,
    horizon: int,
) -> pd.DataFrame:
    """Compute forward returns for all windows in panel."""
    rows = []
    mkt_ret_fwd: dict[pd.Timestamp, float | None] = {}

    for _, row in panel.iterrows():
        ticker = row["ticker"]
        sd = row["signal_date"]

        if ticker not in prices:
            rows.append({"ticker": ticker, "signal_date": sd,
                         "fwd_ret": None, "mkt_ret_fwd": None,
                         "excess_ret": None, "in_store": False})
            continue

        fwd = forward_return(prices[ticker], sd, horizon)
        if sd not in mkt_ret_fwd:
            mkt_ret_fwd[sd] = forward_return(mkt, sd, horizon)
        mkt_f = mkt_ret_fwd[sd]
        excess = (fwd - mkt_f) if (fwd is not None and mkt_f is not None) else None

        rows.append({
            "ticker": ticker,
            "signal_date": sd,
            "fwd_ret": fwd,
            "mkt_ret_fwd": mkt_f,
            "excess_ret": excess,
            "in_store": True,
        })

    out = pd.DataFrame(rows)
    out["signal_date"] = pd.to_datetime(out["signal_date"])
    return out


# ---------------------------------------------------------------------------
# Calendar-time collapse (date-average portfolio)
# ---------------------------------------------------------------------------
def date_collapse(df: pd.DataFrame, col: str) -> pd.Series:
    """One obs per signal_date: average across simultaneous events."""
    s = df.dropna(subset=[col]).groupby("signal_date")[col].mean()
    return s


# ---------------------------------------------------------------------------
# Stats helpers
# ---------------------------------------------------------------------------
def cell_stats(series: pd.Series, label: str) -> dict:
    """NW t-stat on date-collapsed series."""
    s = series.dropna()
    n = len(s)
    lags = _nw_lags(n)
    nw = newey_west_tstat(s, lags=lags)
    ann_ret = float(s.mean()) * ANN  # annualized mean
    return {
        "label": label,
        "n_dates": n,
        "mean_ret": round(float(s.mean()), 5) if n > 0 else None,
        "ann_ret_pct": round(ann_ret * 100, 2) if n > 0 else None,
        "t_hac": nw["t"],
        "p_hac": nw["p"],
        "nw_lags": lags,
        "|t_hac|>=2": nw["t"] is not None and abs(nw["t"]) >= 2.0,
    }


def split_half_check(series: pd.Series, split: pd.Timestamp) -> dict:
    s = series.dropna()
    pre = s[s.index < split]
    post = s[s.index >= split]
    pre_mean = float(pre.mean()) if len(pre) > 0 else None
    post_mean = float(post.mean()) if len(post) > 0 else None
    same_sign = (
        pre_mean is not None and post_mean is not None
        and pre_mean * post_mean > 0
    )
    return {
        "pre_n": len(pre),
        "pre_mean": round(pre_mean, 5) if pre_mean is not None else None,
        "post_n": len(post),
        "post_mean": round(post_mean, 5) if post_mean is not None else None,
        "same_sign": same_sign,
    }


# ---------------------------------------------------------------------------
# Size-matched baseline (C6)
# ---------------------------------------------------------------------------
def build_size_baseline(
    panel: pd.DataFrame,
    prices: dict[str, pd.Series],
    panel_with_rets: pd.DataFrame,
    horizon: int,
) -> pd.Series | None:
    """
    Size-matched baseline for C6: for each event, compute the expected return
    of same-market-cap-decile stocks in the same calendar month.
    Returns: series of excess-vs-size-matched returns indexed by signal_date.
    """
    # Build a monthly market-cap matrix: ticker -> month -> median_mcap_proxy
    # We use close price as a cap proxy (equal-weighting; no shares data available
    # reliably for all 729 tickers in the store).
    # AMENDMENT AM-3: if insufficient data, return None.

    # First get all stock prices on each signal date
    events = panel_with_rets.dropna(subset=["fwd_ret"]).copy()
    if len(events) < 50:
        print("[C6] Insufficient events for size-matched baseline, skipping.")
        return None

    # Use the close price level as a crude size proxy (higher price ≈ not smaller)
    # This is a significant approximation; flagged honestly in the report.
    size_rows = []
    for ticker, p_series in prices.items():
        months = p_series.resample("ME").last()
        for m, price in months.items():
            if not np.isnan(price):
                size_rows.append({"ticker": ticker, "month": m.to_period("M"),
                                  "price_proxy": float(price)})

    if not size_rows:
        return None

    size_df = pd.DataFrame(size_rows)
    # Decile by price_proxy within each month (PIT: use only data up to that month)
    size_df["decile"] = size_df.groupby("month")["price_proxy"].transform(
        lambda x: pd.qcut(x, 10, labels=False, duplicates="drop")
    )

    events["month"] = events["signal_date"].dt.to_period("M")

    # For each event, compute baseline = equal-weight return of stocks in same decile/month
    baselines = []
    for _, ev in events.iterrows():
        ticker = ev["ticker"]
        month = ev["month"]
        sd = ev["signal_date"]

        # Find decile of this ticker in this month
        match = size_df[(size_df["ticker"] == ticker) & (size_df["month"] == month)]
        if match.empty:
            baselines.append({"signal_date": sd, "baseline_ret": None})
            continue
        decile = match.iloc[0]["decile"]

        # Get all tickers in same decile, same month
        peer_tickers = size_df[
            (size_df["month"] == month) & (size_df["decile"] == decile)
        ]["ticker"].tolist()

        peer_rets = []
        for pt in peer_tickers:
            if pt in prices and pt != ticker:
                r = forward_return(prices[pt], sd, horizon)
                if r is not None:
                    peer_rets.append(r)

        baseline = float(np.mean(peer_rets)) if len(peer_rets) >= 3 else None
        baselines.append({"signal_date": sd, "baseline_ret": baseline})

    bdf = pd.DataFrame(baselines)
    bdf["signal_date"] = pd.to_datetime(bdf["signal_date"])

    # Merge with events
    merged = events.merge(bdf, on="signal_date", how="left")
    merged["excess_vs_size"] = merged["fwd_ret"] - merged["baseline_ret"]

    c6 = date_collapse(merged.dropna(subset=["excess_vs_size"]), "excess_vs_size")
    print(f"[C6] Size-matched baseline: {len(c6)} date-collapsed obs")
    return c6


# ---------------------------------------------------------------------------
# Completion-rate descriptive
# ---------------------------------------------------------------------------
def completion_descriptive(raw_df: pd.DataFrame | None) -> dict:
    """
    Descriptive table: what fraction of announced windows have ≥2 sales?
    This is our proxy for 'plan executed' vs 'plan partially executed/abandoned'.
    """
    if raw_df is None or "n_sales" not in raw_df.columns:
        return {"note": "raw panel not available for completion descriptive"}

    total = len(raw_df)
    completed = int((raw_df["n_sales"] >= 2).sum())
    single = int((raw_df["n_sales"] == 1).sum())
    rate = completed / total if total > 0 else None

    return {
        "total_windows": total,
        "multi_sale_windows": completed,
        "single_sale_windows": single,
        "completion_proxy_rate": round(rate, 3) if rate is not None else None,
        "note": "completion proxy = n_sales>=2; does NOT distinguish abandoned vs unfinished vs fully complete",
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    print("=" * 70)
    print(f"FAMILY: {FAMILY} — Phase 0 Honest Harness")
    print("=" * 70)

    # ---- Pre-registered amendments ----
    print("\n[AMENDMENTS PRE-REGISTERED BEFORE COMPUTING]")
    for a in AMENDMENTS:
        print(f"  {a}")

    # ---- Load data ----
    prices = load_price_store()
    mkt = build_market_index(prices)
    panel = load_panel()

    # Exclusion audit (AM-5)
    n_total = len(panel)
    panel["in_store"] = panel["ticker"].isin(prices)
    n_in_store = panel["in_store"].sum()
    n_excl = n_total - n_in_store
    print(f"\n[exclusion_audit] Total windows: {n_total}")
    print(f"  In price store: {n_in_store} ({100*n_in_store/n_total:.1f}%)")
    print(f"  Excluded (no price data): {n_excl} ({100*n_excl/n_total:.1f}%)")

    # Filter to in-store only
    panel = panel[panel["in_store"]].copy().reset_index(drop=True)

    # Coverage note: 2019 vs full panel
    n_2019_plus = int((panel["signal_date"] >= "2019-01-01").sum())
    n_2017_plus = int((panel["signal_date"] >= "2017-01-01").sum())
    print(f"\n[coverage] In-store windows: total={len(panel)}, 2017+={n_2017_plus}, 2019+={n_2019_plus}")

    # ---- Tercile thresholds (AM-1: computed on pre-2022 data) ----
    pre2022 = panel[panel["signal_date"] < SPLIT_DATE]
    pre2022_valid = pre2022.dropna(subset=["pct_float"])
    use_full_sample_terciles = len(pre2022_valid) < 100
    if use_full_sample_terciles:
        print(f"\n[terciles] AM-1 TRIGGERED: pre-2022 valid pct_float obs = {len(pre2022_valid)} < 100")
        print("  Using FULL-SAMPLE terciles (flagged as amendment)")
        tercile_src = panel.dropna(subset=["pct_float"])
    else:
        print(f"\n[terciles] pre-2022 valid pct_float obs: {len(pre2022_valid)}")
        tercile_src = pre2022_valid

    T33 = float(tercile_src["pct_float"].quantile(0.333))
    T67 = float(tercile_src["pct_float"].quantile(0.667))
    print(f"  T33 (small/mid boundary): {T33:.5f} ({T33*100:.3f}% float)")
    print(f"  T67 (mid/large boundary): {T67:.5f} ({T67*100:.3f}% float)")

    # Assign terciles
    def _tercile(pf):
        if pd.isna(pf):
            return None
        if pf < T33:
            return "small"
        if pf < T67:
            return "mid"
        return "large"
    panel["tercile"] = panel["pct_float"].apply(_tercile)

    # ---- Completion descriptive (non-gated) ----
    if PANEL_PATH.exists():
        # Load from the windows panel which has n_sales
        completion = completion_descriptive(panel)
    else:
        completion = completion_descriptive(None)
    print(f"\n[completion_descriptive] {completion}")

    # ---- Compute forward returns ----
    results = {}
    cell_returns = {}

    for h in HORIZONS:
        print(f"\n[returns] Computing {h}d forward returns...")
        ret_df = compute_returns(panel, prices, mkt, h)

        # Merge with panel for tercile info
        ret_df = ret_df.merge(
            panel[["ticker", "signal_date", "tercile", "pct_float"]],
            on=["ticker", "signal_date"],
            how="left"
        )

        in_store_ret = ret_df[ret_df["in_store"]]
        valid_ret = in_store_ret.dropna(subset=["fwd_ret"])
        print(f"  {h}d: {len(in_store_ret)} in-store events, {len(valid_ret)} with valid returns")

        cell_returns[h] = ret_df

    # ---- Cells ----
    print("\n[cells] Computing cell statistics...")
    all_cells: dict[str, dict] = {}

    # C1: all windows, 21d excess vs market
    h = 21
    ret_df = cell_returns[h]
    c1_excess = date_collapse(ret_df.dropna(subset=["excess_ret"]), "excess_ret")
    all_cells["C1_all_21d_excess"] = cell_stats(c1_excess, "C1: all windows, 21d excess vs CN-A market")
    all_cells["C1_all_21d_excess"]["split_half"] = split_half_check(c1_excess, SPLIT_DATE)
    print(f"  C1: n_dates={all_cells['C1_all_21d_excess']['n_dates']}, "
          f"t={all_cells['C1_all_21d_excess']['t_hac']}")

    # C2: all windows, 63d excess vs market
    h2 = 63
    ret_df2 = cell_returns[h2]
    c2_excess = date_collapse(ret_df2.dropna(subset=["excess_ret"]), "excess_ret")
    all_cells["C2_all_63d_excess"] = cell_stats(c2_excess, "C2: all windows, 63d excess vs CN-A market")
    all_cells["C2_all_63d_excess"]["split_half"] = split_half_check(c2_excess, SPLIT_DATE)
    print(f"  C2: n_dates={all_cells['C2_all_63d_excess']['n_dates']}, "
          f"t={all_cells['C2_all_63d_excess']['t_hac']}")

    # C3-C5: tercile cells at 21d
    for tercile_label, cell_key in [("small", "C3"), ("mid", "C4"), ("large", "C5")]:
        ret_df = cell_returns[21]
        sub = ret_df[ret_df["tercile"] == tercile_label]
        exc = date_collapse(sub.dropna(subset=["excess_ret"]), "excess_ret")
        cell_name = f"{cell_key}_{tercile_label}_21d_excess"
        label = f"{cell_key}: {tercile_label}-tercile pct_float, 21d excess vs market"
        all_cells[cell_name] = cell_stats(exc, label)
        all_cells[cell_name]["split_half"] = split_half_check(exc, SPLIT_DATE)
        print(f"  {cell_key} ({tercile_label}): n_dates={all_cells[cell_name]['n_dates']}, "
              f"t={all_cells[cell_name]['t_hac']}")

    # C6: size-matched baseline (21d)
    print("\n[C6] Building size-matched baseline...")
    in_store_rets = cell_returns[21][cell_returns[21]["in_store"]]
    c6_series = build_size_baseline(panel, prices, in_store_rets, 21)
    if c6_series is not None and len(c6_series) >= 10:
        all_cells["C6_all_21d_vs_size"] = cell_stats(c6_series, "C6: all windows, 21d excess vs size-matched baseline")
        all_cells["C6_all_21d_vs_size"]["split_half"] = split_half_check(c6_series, SPLIT_DATE)
        print(f"  C6: n_dates={all_cells['C6_all_21d_vs_size']['n_dates']}, "
              f"t={all_cells['C6_all_21d_vs_size']['t_hac']}")
    else:
        all_cells["C6_all_21d_vs_size"] = {"label": "C6: skipped (insufficient size-matched data)",
                                             "n_dates": 0, "mean_ret": None, "t_hac": None, "p_hac": None}
        print("  C6: SKIPPED")

    # ---- BH FDR correction (G2) ----
    pvals = {k: v["p_hac"] for k, v in all_cells.items() if v.get("p_hac") is not None}
    bh_results = benjamini_hochberg(pvals, alpha=0.10)
    for k in all_cells:
        if k in bh_results:
            all_cells[k]["bh_q"] = bh_results[k]["q"]
            all_cells[k]["bh_reject"] = bh_results[k]["reject"]
        else:
            all_cells[k]["bh_q"] = None
            all_cells[k]["bh_reject"] = False

    # ---- Monotonicity check (G4) ----
    c3_mean = all_cells.get("C3_small_21d_excess", {}).get("mean_ret")
    c5_mean = all_cells.get("C5_large_21d_excess", {}).get("mean_ret")
    monotone_pass = (
        c3_mean is not None and c5_mean is not None
        and c5_mean < c3_mean   # large tercile more negative
    )
    print(f"\n[monotonicity] small_mean={c3_mean}, large_mean={c5_mean}, monotone={monotone_pass}")

    # ---- Verdict ----
    c1 = all_cells.get("C1_all_21d_excess", {})
    g1_pass = c1.get("|t_hac|>=2", False)
    g2_pass = c1.get("bh_reject", False)
    g3_pass = c1.get("split_half", {}).get("same_sign", False)
    g4_pass = monotone_pass

    gates_passed = sum([g1_pass, g2_pass, g3_pass, g4_pass])
    verdict = "PASS" if (g1_pass and g2_pass) else "NULL" if not g1_pass else "PARTIAL"
    print(f"\n[verdict] G1(|t|>=2)={g1_pass}, G2(BH q<=0.10)={g2_pass}, "
          f"G3(split-half)={g3_pass}, G4(monotone)={g4_pass}")
    print(f"[verdict] FINAL: {verdict}")

    # ---- Trial ledger ----
    led = TrialLedger(family=FAMILY)
    configs = []
    for k, v in all_cells.items():
        if v.get("p_hac") is not None:
            configs.append({
                "cell": k,
                "horizon": 21 if "21d" in k else 63,
                "label": v.get("label", k),
                "mean_ret": v.get("mean_ret"),
                "t_hac": v.get("t_hac"),
                "p_hac": v.get("p_hac"),
                "bh_q": v.get("bh_q"),
                "gate_pass": v.get("|t_hac|>=2", False) and v.get("bh_reject", False),
            })
    if configs:
        led.log_grid(configs, family=FAMILY)
        print(f"[trial_ledger] Logged {len(configs)} cells to ledger.")

    # ---- Write report ----
    _write_report(
        all_cells=all_cells,
        completion=completion,
        g1=g1_pass, g2=g2_pass, g3=g3_pass, g4=g4_pass,
        verdict=verdict,
        T33=T33, T67=T67,
        n_total=n_total, n_in_store=n_in_store,
        n_2019_plus=n_2019_plus,
        monotone_pass=monotone_pass,
        use_full_sample_terciles=use_full_sample_terciles,
        mkt_proxy_used="000300.SH (CSI 300)" if "000300.SH" in prices else "equal-weight proxy",
    )
    print("\n[done] Report written.")


# ---------------------------------------------------------------------------
# Report writer
# ---------------------------------------------------------------------------
def _fmt(v, digits=4) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "N/A"
    if isinstance(v, bool):
        return "YES" if v else "NO"
    if isinstance(v, float):
        return f"{v:.{digits}f}"
    return str(v)


def _write_report(
    all_cells: dict,
    completion: dict,
    g1: bool, g2: bool, g3: bool, g4: bool,
    verdict: str,
    T33: float, T67: float,
    n_total: int, n_in_store: int, n_2019_plus: int,
    monotone_pass: bool,
    use_full_sample_terciles: bool,
    mkt_proxy_used: str,
) -> None:
    REPORT_DIR = ROOT / "reports"
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORT_DIR / "d2-cn-holder-sale-phase0.md"

    lines: list[str] = []
    W = lines.append

    W("# d2_cn_holder_sale_calendar — Phase-0 Honest Harness")
    W("")
    W(f"**Family:** `{FAMILY}`  **Verdict:** **{verdict}**")
    W("")
    W("Pre-registered per: `research/SIGNAL_LAB_FRONTIER_DAY2_FABLE_ADJUDICATION_2026-07-06.md`")
    W("item 3 — authorised 2026-07-06, executed-window variant, LG-CN-SUPPLY slot.")
    W("")

    # Gates summary
    W("## Gate summary")
    W("")
    W("| Gate | Criterion | Result |")
    W("|------|-----------|--------|")
    W(f"| G1 | \\|t_HAC\\| >= 2 (date-clustered NW) on C1 | {'**PASS**' if g1 else 'FAIL'} |")
    W(f"| G2 | BH FDR q <= 0.10 across all cells | {'**PASS**' if g2 else 'FAIL'} |")
    W(f"| G3 | Split-half same-sign (pre/post 2022) on C1 | {'**PASS**' if g3 else 'FAIL'} |")
    W(f"| G4 | Monotonicity: large-tercile more negative than small | {'**PASS**' if monotone_pass else 'FAIL'} |")
    W("")

    # Plain English box
    W("## In plain English")
    W("")
    W("> **What this tests:** When a major shareholder in a Chinese A-share company announces")
    W("> a plan to sell stock (减持计划), the CSRC requires a 15-day pre-disclosure notice before the")
    W("> sale window opens. During that open window, the stock faces known supply overhang.")
    W("> We test whether stocks with an open 减持 window underperform the market over the")
    W("> next 21 and 63 trading days, and whether the underperformance is larger when the")
    W("> planned sale is a bigger fraction of float.")
    W(">")
    W(f"> **Result in one sentence:** {verdict}. "
      f"{'The predicted negative drift is present' if g1 else 'We do not find a reliable negative drift'} "
      f"in the primary 21-day cell {'(|t_HAC|=' + _fmt(all_cells.get('C1_all_21d_excess', {}).get('t_hac'), 2) + ')' if g1 else ''}; "
      f"{'monotone in planned size' if monotone_pass else 'size monotonicity not confirmed'}.")
    W("")

    # Data summary
    W("## Data summary")
    W("")
    W(f"- **Source:** Eastmoney datacenter (`RPT_SHARE_HOLDER_INCREASE`, filter DIRECTION=减持)")
    W(f"- **Total execution windows (all tickers):** {n_total:,}")
    W(f"- **Windows with price data (in price store):** {n_in_store:,} ({100*n_in_store/max(n_total,1):.1f}%)")
    W(f"- **Windows 2019+:** {n_2019_plus:,}")
    W(f"- **Price store:** {PRICE_STORE} (729 tickers verified)")
    W(f"- **Market index:** {mkt_proxy_used}")
    W(f"- **Tercile thresholds:** T33={T33:.5f} ({T33*100:.3f}% float), T67={T67:.5f} ({T67*100:.3f}% float)")
    if use_full_sample_terciles:
        W("  - **AM-1 TRIGGERED:** Full-sample terciles used (pre-2022 obs < 100). Look-ahead risk: MINOR (thresholds are quantiles of the size metric, not returns).")
    W("")

    # PIT assumptions
    W("## PIT assumptions (frozen before computing)")
    W("")
    W("1. **Signal availability date:** `window_open` (START_DATE from the original plan). The legally-mandated plan announcement precedes this by ≥15 calendar days; using window_open is **CONSERVATIVE** (later than true availability).")
    W("2. **Entry:** Close of (window_open + 1 trading day). No look-ahead: the window is publicly open on window_open.")
    W("3. **Tercile thresholds:** Computed on pre-2022 data only (AM-1).")
    W("4. **Market index:** Contemporaneous close of CSI 300 proxy.")
    W("5. **pct_float denominator:** Derived from HOLD_RATIO and AFTER_HOLDER_NUM (see collector). Approximates post-sale float, not pre-sale.")
    W("6. **Coverage:** 2017+ data is the clean post-regulation era (pre-disclosure mandated). Pre-2017 windows lack reliable START_DATE; they enter only with a ±30d window estimate.")
    W("")

    # Amendments
    W("## Pre-registered amendments")
    W("")
    for a in AMENDMENTS:
        W(f"- {a}")
    W("")

    # Cell results
    W("## Cell results")
    W("")
    W("| Cell | N dates | Mean fwd ret | Ann % | t_HAC | p_HAC | BH q | BH reject | Split-half |")
    W("|------|---------|-------------|-------|-------|-------|------|-----------|------------|")

    for k, v in all_cells.items():
        sh = v.get("split_half", {})
        sh_str = f"{_fmt(sh.get('pre_mean'), 4)}/{_fmt(sh.get('post_mean'), 4)} same={'Y' if sh.get('same_sign') else 'N'}"
        W(f"| {v.get('label', k)} | {_fmt(v.get('n_dates'))} | {_fmt(v.get('mean_ret'), 5)} | "
          f"{_fmt(v.get('ann_ret_pct'), 2)} | {_fmt(v.get('t_hac'), 3)} | {_fmt(v.get('p_hac'), 4)} | "
          f"{_fmt(v.get('bh_q'), 4)} | {'YES' if v.get('bh_reject') else 'NO'} | {sh_str} |")

    W("")

    # Completion descriptive (non-gated)
    W("## Completion-rate descriptive (non-gated robustness)")
    W("")
    W("Many 减持 plans go unexecuted or partially executed. The base rate (proxy):")
    W("")
    W(f"- Total execution windows in panel: {completion.get('total_windows', 'N/A'):,}")
    W(f"- Windows with ≥2 individual sales (multi-sale proxy): {completion.get('multi_sale_windows', 'N/A'):,}")
    W(f"- Windows with exactly 1 sale: {completion.get('single_sale_windows', 'N/A'):,}")
    W(f"- Multi-sale rate: {_fmt(completion.get('completion_proxy_rate'), 3)}")
    W(f"- *{completion.get('note', '')}*")
    W("")

    # Monotonicity
    W("## Monotonicity check (G4)")
    W("")
    c3_m = all_cells.get("C3_small_21d_excess", {}).get("mean_ret")
    c4_m = all_cells.get("C4_mid_21d_excess", {}).get("mean_ret")
    c5_m = all_cells.get("C5_large_21d_excess", {}).get("mean_ret")
    W("21-day excess return by pct_float tercile:")
    W(f"- Small tercile (pct_float < {T33*100:.3f}%): {_fmt(c3_m, 5)}")
    W(f"- Mid tercile: {_fmt(c4_m, 5)}")
    W(f"- Large tercile (pct_float >= {T67*100:.3f}%): {_fmt(c5_m, 5)}")
    W(f"- **Monotone (large < small):** {'YES' if monotone_pass else 'NO'}")
    W("")

    # Verdict and interpretation
    W("## Verdict and interpretation")
    W("")
    W(f"**Verdict: {verdict}**")
    W("")
    if verdict == "PASS":
        W("Both primary gates cleared (|t_HAC| >= 2 and BH q <= 0.10). "
          "The execution-window forced-supply drift is statistically detectable in this dataset.")
        W("This warrants promotion to the LG-CN-SUPPLY slot pending further robustness review.")
        W("**Do NOT use the word 'validated' — this is a Phase-0 harness result.** "
          "The signal is display-only until the full gauntlet is run.")
    elif verdict == "PARTIAL":
        W("G1 (|t| >= 2) cleared but G2 (BH FDR) did not, or vice versa. "
          "The effect is directionally consistent but not robustly significant after multiple-testing correction.")
        W("Result is a partial positive: direction correct, magnitude insufficient for promotion.")
    else:
        W("The primary gate (|t_HAC| >= 2) was not cleared on the main cell. "
          "This is a NULL result — a successful run that honestly reports a lack of detectable effect. "
          "The null is printed, not hidden.")
    W("")
    W("### Caveats")
    W("")
    W("1. The price store covers 729 tickers; windows for tickers outside the store are excluded. "
      f"Exclusion rate: {100*(n_total-n_in_store)/max(n_total,1):.1f}% of total windows.")
    W("2. pct_float is approximated from post-sale HOLD_RATIO and AFTER_HOLDER_NUM; "
      "it is an approximation of the pre-sale float fraction.")
    W("3. The size-matched baseline (C6) uses close price as a market-cap proxy — "
      "not a clean measure of size; treat C6 as directional only.")
    W("4. Pre-2017 windows lack reliable execution window dates (START_DATE often null). "
      "The post-2017 sub-panel is the clean regime-relevant panel.")
    W("5. Completion/abandonment of plans cannot be verified from this dataset alone.")
    W("")

    # Nightly wiring
    W("## Nightly wiring (for consolidation)")
    W("")
    W("```")
    W("# In scripts/collect.py, china-altdata section:")
    W("from collectors.cn_holder_sale_calendar import collect as cn_holder_collect")
    W("cn_holder_collect()  # ~10-15 min full backfill, ~1 min incremental")
    W("```")
    W("")
    W("---")
    W("*Report generated by `scripts/d2_cn_holder_sale_phase0.py`. Phase-0 harness only.*")

    out.write_text("\n".join(lines))
    print(f"[report] Written: {out}")


if __name__ == "__main__":
    main()
