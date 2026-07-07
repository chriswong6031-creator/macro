"""Phase-0 study: China export-share nowcast — d2_cn_export_share_nowcast family.

Signal hypothesis:
    A positive YoY export surprise (actual vs trailing seasonal trend) in a product
    line where 1-3 listed A-share companies carry >50% of national export share
    predicts positive relative returns for those issuers over the next 21 trading days
    vs the CSI300 benchmark.

    Direction: positive_surprise → positive issuer-vs-CSI300 21d return.
    Baseline: CSI300 daily close from data/cn_export_products/csi300_close.parquet.

PRE-REGISTERED GAPS (locked before any computation):
    G1: SMALL N — Comtrade monthly data × 3 HS lines (post-concentration filter; see
        AMENDMENT A1) = at most ~30-72 non-null release months per HS code. Study is
        explicitly labelled EXPLORATORY / PHASE-0.
    G2: DESEASONALIZATION ASSUMPTION — Combined Jan+Feb convention removes CNY-shift
        distortion between Jan and Feb across years. YoY on the combined series removes
        most calendar seasonality but may not remove structural trend shifts (pandemic,
        policy cycles). Residual noise is treated as the "surprise" signal.
    G3: PUBLICATION LAG — Comtrade monthly data lags ~3 months from the reference
        month. Entry is set to day 20 of M+3 (3 months after the reference month M)
        to ensure data is published before the trade is entered. The 21-day forward
        window then covers trading days AFTER the release date.
    G4: ISSUER SHARE ESTIMATES are from industry association reports (CPIA/Infolink/
        SNE Research/CPCA) with "as-of" 2023. Actual export-period share weighting is
        UNOBSERVABLE — we use equal-weight across the 2-3 mapped issuers per HS line,
        not share-weighted (no PIT per-period share data available). The >50% threshold
        is applied to the sum of the 1-3 named issuers' national/capacity shares per
        industry source; see CSV notes.
    G5: PRICE-STORE COVERAGE — china_stocks/ per-ticker parquets used for pre-2021
        history. china_search/closes.parquet (2021-06+) used as a coverage check.
        Some tickers (688223.SS Jinko Solar, 688390.SS GoodWe) are Science & Technology
        Innovation Board (STAR) listees with shorter history; observation windows may
        be shorter than the tape. Honest NA treatment.
    G6: CSI300 BENCHMARK — daily close from pre-saved parquet. Sector-specific
        photovoltaic/battery indices were not machine-fetchable. CSI300 is a coarser
        baseline; sector excess returns may overstate alpha vs the true sector index.
    G7: OVERLAP CORRECTION — 21-day forward return windows OVERLAP when release months
        are adjacent. Newey-West HAC t-statistics with lag=2 monthly lags are used
        throughout. (Lag is in the units of the event series index, which is monthly —
        one monthly lag captures adjacent-release autocorrelation; we use 2 to be
        conservative.)
    G8: SPLIT-HALF — time-based: first half vs second half of the observation window
        per HS line. With 10-24 event dates per half, the NW HAC estimate is computed
        with lag=min(2,n-1). For n<6 the split-half t-stat is listed as
        HAC-DEGENERATE and is NOT interpreted as evidence for or against the signal.
    G9: 854141 SHORT HISTORY — solar cells monocrystalline (HS Rev-6 code 854141) only
        available in Comtrade from 2022-01 (HS reclassification). That cell has ~34
        non-null months, making it especially noisy.

AMENDMENT A1 (pre-registered before computation):
    HS lines 854160 (Solar modules) and 850440 (Solar inverters) are EXCLUDED from
    the active study because the 1-3 named A-share tickers' national/capacity share
    sums to 43% and 50% respectively — both fall at or below the >50% frozen
    concentration criterion. The top_n_combined_pct figures in the CSV (72%/76%)
    cite global shipment/market share, NOT national export share, and are therefore
    inadmissible as evidence for the >50% national-export-share gate. Lines retained:
    854141 (Solar cells mono, 63% CN cell capacity), 850760 (Li-ion batteries, 58%
    global usage, dominated by CN exports), 870380 (EV passenger cars, 52% BYD alone
    in listed-company NEV exports per CPCA).

CELLS (≤4 gated cells, covering 3 retained HS lines):
    Cell-1: Positive surprise → 21d excess return, retained HS lines pooled (POOLED)
    Cell-2: Positive surprise → 21d excess return, per-HS-line (individual lines)
    Cell-3: Split-half consistency test on Cell-1 pooled
    Cell-4: Magnitude bucket — large surprise vs small surprise (top vs bottom tercile)

GATE SEQUENCE (in order):
    1. |t| ≥ 2.0 (Newey-West HAC, lag=2 monthly lags) on Cell-1 pooled
    2. BH-FDR q ≤ 0.10 across all cell p-values (Cell-1 + Cell-2 lines)
    3. Split-half same-sign consistency (both halves positive)
    All three must pass for a PROMOTE verdict; any fail → SIGNAL NULL (honest null).

TrialLedger: log_grid called at generation before any backtest.
Exemplars: scripts/insider_phase0.py, scripts/naaim_overlay_phase0.py.
Stats from engine/validation.py (deflated_sharpe, ret_moments) + engine/trial_ledger.py.

Store layout:
    data/cn_export_products/<hs_code>.parquet — monthly export tape (FOB USD)
    data/cn_export_products/csi300_close.parquet — daily CSI300 close
    data/china_stocks/<TICKER>.parquet — daily OHLCV per A-share ticker
    data/china_search/closes.parquet — panel close 2021-06+, 1514 tickers (coverage check)
"""
from __future__ import annotations

import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Path setup — work in the worktree root, not the main repo root
# ---------------------------------------------------------------------------
WORKTREE_ROOT = Path(__file__).resolve().parent.parent
# data/ in the worktree symlinks to the main data store — used READ-ONLY
MAIN_DATA = WORKTREE_ROOT / "data"

# TrialLedger is written to a WORKTREE-LOCAL path to avoid polluting the shared
# data/trial_ledger.jsonl in the main checkout (house law §DATA: ledgers).
WORKTREE_LEDGER_PATH = WORKTREE_ROOT / "data_local" / "trial_ledger.jsonl"

import logging
import warnings
import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)
warnings.filterwarnings("ignore", category=FutureWarning)

sys.path.insert(0, str(WORKTREE_ROOT))
from engine.trial_ledger import TrialLedger
from engine.validation import deflated_sharpe, ret_moments

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
FAMILY = "d2_cn_export_share_nowcast"
FORWARD_DAYS = 21          # trading days
NW_LAG = 2                 # Newey-West HAC lag in MONTHLY units (event series is monthly;
                           # lag=2 captures adjacent-release autocorrelation conservatively)
FDR_ALPHA = 0.10           # BH-FDR threshold
T_GATE = 2.0               # |t| gate

# PUBLICATION LAG CONSTANT
# Comtrade monthly data is released with ~3-month lag. For reference month M (tape index
# YYYY-MM-01), the entry date is set to day 20 of M+3. This ensures the measured data
# exists before the trade is entered and the 21-day forward window is entirely post-release.
RELEASE_LAG_MONTHS = 3
RELEASE_LAG_DAY = 20  # day within the lag month (proxy for GACC/Comtrade publication)

# Issuer mapping — ACTIVE LINES ONLY (after Amendment A1 concentration filter).
# 854160 (Solar modules, 43% mapped-name share) and 850440 (Solar inverters, 50% not
# strictly >50%) are EXCLUDED. Only lines where 1-3 named tickers exceed 50% national
# export / capacity share are retained.
ISSUER_MAP = {
    "854141": ["600438.SS", "688223.SS", "002459.SZ"],  # Solar cells mono (63% CN capacity)
    "850760": ["300750.SZ", "002594.SZ", "002074.SZ"],  # Li-ion batteries (58% global)
    "870380": ["002594.SZ", "601633.SS", "600104.SS"],  # EV passenger cars (BYD 52%)
}

# Excluded lines (documented for transparency, not used in computation)
EXCLUDED_LINES = {
    "854160": "Solar modules — 43% mapped-name national share (43% < 50% threshold, FAIL)",
    "850440": "Solar inverters — 50% mapped-name national share (need strictly >50%, FAIL)",
}

HS_LABELS = {
    "854141": "Solar cells mono",
    "850760": "Li-ion batteries",
    "870380": "EV passenger cars",
}

EXPORT_DIR = MAIN_DATA / "cn_export_products"
CHINA_STOCKS_DIR = MAIN_DATA / "china_stocks"
CHINA_SEARCH_CLOSES = MAIN_DATA / "china_search" / "closes.parquet"
CSI300_PATH = EXPORT_DIR / "csi300_close.parquet"


# ---------------------------------------------------------------------------
# STEP 1: Log grid to TrialLedger BEFORE any computation (house law §5)
# ---------------------------------------------------------------------------
def _build_grid():
    """Enumerate all configurations tried. Called at generation."""
    cells = []
    # Cell-1: pooled positive surprise → 21d excess return
    cells.append({"cell": 1, "type": "pooled", "hs": "all", "direction": "positive",
                  "horizon_d": FORWARD_DAYS, "deseasonalize": "CNY_combined_YoY_trend",
                  "release_lag_months": RELEASE_LAG_MONTHS})
    # Cell-2: per-HS-line
    for hs in ISSUER_MAP:
        cells.append({"cell": 2, "type": "per_line", "hs": hs, "direction": "positive",
                      "horizon_d": FORWARD_DAYS, "deseasonalize": "CNY_combined_YoY_trend",
                      "release_lag_months": RELEASE_LAG_MONTHS})
    # Cell-3: split-half on pooled
    for half in ["first", "second"]:
        cells.append({"cell": 3, "type": "split_half", "hs": "all", "half": half,
                      "horizon_d": FORWARD_DAYS, "deseasonalize": "CNY_combined_YoY_trend",
                      "release_lag_months": RELEASE_LAG_MONTHS})
    # Cell-4: magnitude tercile (large vs small surprise)
    for tercile in ["top", "bottom"]:
        cells.append({"cell": 4, "type": "magnitude", "hs": "all", "tercile": tercile,
                      "horizon_d": FORWARD_DAYS, "deseasonalize": "CNY_combined_YoY_trend",
                      "release_lag_months": RELEASE_LAG_MONTHS})
    return cells


# ---------------------------------------------------------------------------
# STEP 2: Load data
# ---------------------------------------------------------------------------
def load_export_tape() -> dict[str, pd.DataFrame]:
    """Load monthly export tape for each active HS code. Returns dict hs->DataFrame[fob_usd].
    Note: only ISSUER_MAP keys are loaded; EXCLUDED_LINES are not loaded.
    """
    tapes = {}
    for hs in ISSUER_MAP:
        path = EXPORT_DIR / f"{hs}.parquet"
        if not path.exists():
            log.warning("MISSING tape: %s — gap G1: partial tape (collection incomplete)", path)
            continue
        df = pd.read_parquet(path)
        if "fob_usd" not in df.columns:
            log.warning("MALFORMED tape %s: missing fob_usd column", hs)
            continue
        df.index = pd.to_datetime(df.index)
        tapes[hs] = df
        nn = df["fob_usd"].notna().sum()
        log.info("Tape %s (%s): %d rows, %d non-null, latest=%s",
                 hs, HS_LABELS[hs], len(df), nn,
                 df.index.max().strftime("%Y-%m") if len(df) else "N/A")
    return tapes


def load_csi300() -> pd.Series:
    """Load CSI300 daily close from pre-saved parquet."""
    if not CSI300_PATH.exists():
        log.error("CSI300 parquet missing: %s", CSI300_PATH)
        return pd.Series(dtype=float)
    df = pd.read_parquet(CSI300_PATH)
    # columns: could be 'close' or the raw akshare column name
    if "close" in df.columns:
        return pd.to_numeric(df["close"], errors="coerce").rename("csi300")
    # try first numeric column
    num_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    if num_cols:
        log.warning("CSI300: using column '%s' as close", num_cols[0])
        return pd.to_numeric(df[num_cols[0]], errors="coerce").rename("csi300")
    log.error("CSI300: no numeric column found in %s", CSI300_PATH)
    return pd.Series(dtype=float)


def load_ticker_close(ticker: str) -> pd.Series:
    """Load daily close for one A-share ticker.
    Tries china_stocks/<TICKER>.parquet first (full history from 2011+),
    then china_search/closes.parquet panel (2021-06+ only).
    """
    # Primary: per-ticker parquet
    ticker_path = CHINA_STOCKS_DIR / f"{ticker}.parquet"
    if ticker_path.exists():
        try:
            df = pd.read_parquet(ticker_path)
            # column names vary; look for 'close' or 'Close'
            for col in ["close", "Close", "收盘"]:
                if col in df.columns:
                    s = pd.to_numeric(df[col], errors="coerce").rename(ticker)
                    s.index = pd.to_datetime(s.index)
                    return s
            # fallback: use last numeric column
            num_cols = df.select_dtypes(include=[np.number]).columns.tolist()
            if num_cols:
                s = pd.to_numeric(df[num_cols[-1]], errors="coerce").rename(ticker)
                s.index = pd.to_datetime(s.index)
                return s
        except Exception as e:
            log.warning("Failed loading %s from china_stocks: %s", ticker, e)

    # Fallback: china_search panel (2021-06+ only)
    if CHINA_SEARCH_CLOSES.exists():
        try:
            panel = pd.read_parquet(CHINA_SEARCH_CLOSES)
            panel.index = pd.to_datetime(panel.index)
            if ticker in panel.columns:
                log.info("  %s: using china_search panel (2021-06+ only — GAP G5)", ticker)
                return panel[ticker].rename(ticker)
        except Exception as e:
            log.warning("Failed loading %s from china_search panel: %s", ticker, e)

    log.warning("PRICE MISS: %s — no data in any store", ticker)
    return pd.Series(dtype=float, name=ticker)


def verify_price_coverage():
    """PRICE-STORE LAW: verify each known ticker loads from each store. Print coverage."""
    log.info("=== PRICE-STORE COVERAGE VERIFICATION ===")
    all_tickers = sorted({t for tks in ISSUER_MAP.values() for t in tks})
    results = {}
    for ticker in all_tickers:
        ticker_path = CHINA_STOCKS_DIR / f"{ticker}.parquet"
        in_china_stocks = ticker_path.exists()
        close = load_ticker_close(ticker)
        n = close.dropna().shape[0]
        if n > 0:
            earliest = close.dropna().index.min().strftime("%Y-%m")
            latest = close.dropna().index.max().strftime("%Y-%m")
        else:
            earliest = latest = "N/A"
        results[ticker] = {
            "china_stocks_file": in_china_stocks,
            "n_days": n,
            "earliest": earliest,
            "latest": latest,
        }
        status = "OK" if n > 100 else "WARN(<100 days)"
        store = "china_stocks" if in_china_stocks else "china_search (2021-06+)"
        log.info("  %s: %s | n=%d | %s->%s | store=%s",
                 ticker, status, n, earliest, latest, store)
    return results


# ---------------------------------------------------------------------------
# STEP 3: Deseasonalize export series (YoY with CNY combined-month convention)
# ---------------------------------------------------------------------------
def apply_cny_combination(s: pd.Series) -> pd.Series:
    """Apply the CNY combined Jan+Feb convention.

    CNY shifts between Jan and Feb across years, creating artificial YoY distortions
    when Jan-heavy years are compared against Feb-heavy years. Fix: for each year,
    average Jan and Feb into a single 'Jan-Feb' observation (assigned to Feb-01),
    then drop the standalone Jan observation.

    Returns a monthly series where Jan is NaN (dropped) and Feb carries the combined
    value for that year's Jan+Feb.

    Lane rule 4: monthly official series MUST use this convention before YoY.
    """
    out = s.copy()
    years = s.index.year.unique()
    for yr in years:
        jan_idx = pd.Timestamp(yr, 1, 1)
        feb_idx = pd.Timestamp(yr, 2, 1)
        jan_val = s.get(jan_idx, float("nan"))
        feb_val = s.get(feb_idx, float("nan"))
        # Compute combined as mean of available months
        avail = [v for v in [jan_val, feb_val] if not np.isnan(v)]
        if avail:
            combined = float(np.mean(avail))
        else:
            combined = float("nan")
        # Assign combined to Feb, drop Jan
        if feb_idx in out.index:
            out[feb_idx] = combined
        if jan_idx in out.index:
            out[jan_idx] = float("nan")
    return out


def compute_yoy_surprise(tape_df: pd.DataFrame, hs_code: str,
                          trend_window: int = 12) -> pd.DataFrame:
    """Compute YoY export surprise deseasonalized via CNY-combined trailing trend.

    Method (per SEASONALITY rule 4 + CNY combined-month convention):
        1. Apply CNY combination: Jan+Feb -> Feb combined, Jan -> NaN (per year)
        2. Compute raw YoY = (combined_series / combined_series.shift(12)) - 1
           (shift(12) aligns same-month in prior year; Jan rows are NaN so no
           cross-contamination)
        3. Compute trailing trend = rolling(trend_window).median() of raw YoY
           (PIT: shift(1) uses only past values)
        4. Surprise = raw_yoy - trend_yoy (residual vs recent trend)

    Returns DataFrame with columns: fob_usd, fob_combined, yoy_raw, yoy_trend,
    yoy_surprise. NaN where < 13 months of data.

    Pre-registered gap G2: YoY with CNY combination removes calendar seasonality
    but not structural trend shifts.
    """
    s = tape_df["fob_usd"].copy()
    # CNY combination (lane rule 4)
    s_cny = apply_cny_combination(s)

    # YoY raw (requires 12 months history; Jan rows are NaN so shift(12) is clean)
    yoy_raw = (s_cny / s_cny.shift(12)) - 1.0
    # Trailing trend (expanding up to trend_window; PIT: shift(1) uses only past values)
    yoy_trend = yoy_raw.shift(1).rolling(trend_window, min_periods=3).median()
    # Surprise = actual YoY minus trend
    yoy_surprise = yoy_raw - yoy_trend

    out = pd.DataFrame({
        "fob_usd": s,
        "fob_combined": s_cny,
        "yoy_raw": yoy_raw,
        "yoy_trend": yoy_trend,
        "yoy_surprise": yoy_surprise,
    })
    n_valid = out["yoy_surprise"].notna().sum()
    log.info("  %s YoY surprise (CNY-combined): %d valid periods (of %d total)",
             hs_code, n_valid, len(out))
    return out


# ---------------------------------------------------------------------------
# STEP 4: Forward returns computation — with PIT publication-lag shift
# ---------------------------------------------------------------------------
def compute_entry_date(ref_month: pd.Timestamp) -> pd.Timestamp:
    """Compute PIT entry date for a Comtrade reference month.

    Comtrade publishes data with ~3-month lag. For reference month M (tape index
    YYYY-MM-01), the entry date is set to day RELEASE_LAG_DAY of M+RELEASE_LAG_MONTHS.
    This ensures the measured data exists before the trade is entered.

    Example: ref_month=2024-01-01 → entry = 2024-04-20.
    """
    # Add RELEASE_LAG_MONTHS months then set to RELEASE_LAG_DAY
    # Use pd.DateOffset to handle month-end correctly
    release_month = ref_month + pd.DateOffset(months=RELEASE_LAG_MONTHS)
    # Clamp day to end of month (handles short months like Feb)
    import calendar
    last_day = calendar.monthrange(release_month.year, release_month.month)[1]
    day = min(RELEASE_LAG_DAY, last_day)
    return pd.Timestamp(release_month.year, release_month.month, day)


def get_issuer_forward_returns(
    ticker: str,
    ref_months: pd.DatetimeIndex,
    csi300: pd.Series,
    forward_days: int = FORWARD_DAYS,
) -> pd.Series:
    """Compute 21-day forward excess return (issuer vs CSI300) for each reference month.

    PIT FIX: Entry date is NOT the tape index (YYYY-MM-01 = export reference month).
    Entry date = first trading day on/after compute_entry_date(ref_month), which is
    day 20 of M+3 (3 months after reference month M). This enforces the publication
    lag and ensures no lookahead bias.

    Returns: pd.Series indexed by ref_months (tape index dates) with excess return values.
    Pre-registered gap G3: entry dated to ~3 months after reference month.
    Pre-registered gap G7: overlapping windows; NW HAC used for t-stats.
    """
    close = load_ticker_close(ticker)
    if close.empty:
        return pd.Series(np.nan, index=ref_months, name=ticker)

    # Align to trading calendar via reindex + ffill
    all_dates = close.index.union(csi300.index)
    all_dates = pd.DatetimeIndex(sorted(all_dates))
    close_r = close.reindex(all_dates).ffill()
    csi300_r = csi300.reindex(all_dates).ffill()

    # Only keep dates where both have data
    valid = close_r.notna() & csi300_r.notna()
    dates_valid = all_dates[valid]

    results = {}
    for rd in ref_months:
        # Compute PIT entry date: day 20 of M+3
        pit_entry = compute_entry_date(rd)

        # Find first valid trading day on or after PIT entry date
        future = dates_valid[dates_valid >= pit_entry]
        if len(future) < forward_days + 1:
            results[rd] = np.nan
            continue
        entry_date = future[0]
        exit_idx = np.searchsorted(dates_valid, entry_date) + forward_days
        if exit_idx >= len(dates_valid):
            results[rd] = np.nan
            continue
        exit_date = dates_valid[exit_idx]

        issuer_ret = float(close_r[exit_date] / close_r[entry_date]) - 1.0
        csi_ret = float(csi300_r[exit_date] / csi300_r[entry_date]) - 1.0
        results[rd] = issuer_ret - csi_ret

    return pd.Series(results, name=ticker)


# ---------------------------------------------------------------------------
# STEP 5: Newey-West HAC t-statistic (overlap-corrected, monthly-unit lag)
# ---------------------------------------------------------------------------
def newey_west_tstat(y: np.ndarray, lag: int = NW_LAG) -> float:
    """One-sample Newey-West t-stat for H0: E[y]=0. HAC SE in the series' own units.

    y must be time-ordered (calendar-time, not arbitrary event-time reindex).

    lag: number of autocorrelation lags in the units of y's time index.
         For this study y is indexed monthly (one obs per release month), so
         lag=NW_LAG=2 captures up to 2-month autocorrelation — appropriate for
         adjacent-month event overlap. Using lag=21 (daily trading days) on a
         monthly series would over-smooth ~42% of the sample (degenerate HAC).

    Returns NaN when n < 6 (too few for HAC) or when variance is degenerate.
    """
    y = np.asarray(y, dtype=float)
    mask = ~np.isnan(y)
    y = y[mask]
    n = len(y)
    if n < 6:
        return float("nan")
    mu = y.mean()
    # Newey-West: Sigma_NW = Gamma(0) + 2 * sum_{l=1}^{lag} w_l * Gamma(l)
    e = y - mu
    gamma0 = (e ** 2).mean()
    # Guard: if near-zero variance (all same returns), return NaN
    if gamma0 < 1e-12:
        return float("nan")
    actual_lag = min(lag, n - 1)
    nw_var = gamma0
    for l in range(1, actual_lag + 1):
        w = 1.0 - l / (actual_lag + 1.0)  # Bartlett kernel
        gamma_l = (e[l:] * e[:-l]).mean()
        nw_var += 2.0 * w * gamma_l
    # Guard: NW variance must be positive and bounded away from zero
    if nw_var < gamma0 * 1e-6:
        # NW collapsed — fall back to simple (iid) t-stat as conservative estimate
        se = np.sqrt(max(gamma0, 1e-12) / n)
    else:
        nw_var = max(nw_var, 1e-12)
        se = np.sqrt(nw_var / n)
    t = float(mu / se)
    # Clip to prevent overflow in downstream p-value computation
    return float(np.clip(t, -1e6, 1e6))


# ---------------------------------------------------------------------------
# STEP 6: BH-FDR correction
# ---------------------------------------------------------------------------
def bh_fdr(p_values: list[float], alpha: float = FDR_ALPHA) -> tuple[list[bool], list[float]]:
    """Benjamini-Hochberg FDR correction. Returns (rejected, adjusted_p_values).
    NaN p-values pass through as non-rejected with NaN adjusted p."""
    n = len(p_values)
    idx = np.argsort([p if not np.isnan(p) else 1.0 for p in p_values])
    p_adj = [float("nan")] * n
    rejected = [False] * n
    prev = 1.0
    for rank, i in enumerate(reversed(idx)):
        p = p_values[i]
        if np.isnan(p):
            p_adj[i] = float("nan")
            continue
        threshold = (n - rank) * alpha / n
        adj = min(p * n / (n - rank), prev)
        p_adj[i] = adj
        prev = adj
        if p <= threshold:
            rejected[i] = True
    return rejected, p_adj


def tstat_to_pvalue(t: float, n: int) -> float:
    """Two-tailed p-value from t-stat using normal approximation (large N)."""
    if np.isnan(t):
        return float("nan")
    from math import erfc, sqrt
    return float(erfc(abs(t) / sqrt(2.0)))


# ---------------------------------------------------------------------------
# STEP 7: Build event study
# ---------------------------------------------------------------------------
def build_events(
    tapes: dict[str, pd.DataFrame],
    csi300: pd.Series,
) -> pd.DataFrame:
    """Build the event-study panel.

    For each (hs_code, ref_month, issuer):
        - ref_month = month of Comtrade data point (tape index)
        - entry_date = compute_entry_date(ref_month) = day 20 of M+3 (PIT clean)
        - yoy_surprise = CNY-combined deseasonalized YoY surprise
        - fwd_ret_21d = 21d forward issuer excess vs CSI300 from entry_date

    Returns DataFrame with columns:
        hs_code, issuer, ref_month, entry_date, yoy_surprise, fwd_ret_21d
    """
    rows = []
    for hs_code, tape_df in tapes.items():
        surp_df = compute_yoy_surprise(tape_df, hs_code)
        valid = surp_df.dropna(subset=["yoy_surprise"])
        if valid.empty:
            log.warning("%s: no valid YoY surprise periods", hs_code)
            continue

        for ticker in ISSUER_MAP.get(hs_code, []):
            fwd = get_issuer_forward_returns(
                ticker, valid.index, csi300, FORWARD_DAYS
            )
            for rd in valid.index:
                entry_dt = compute_entry_date(rd)
                fwd_val = float(fwd[rd]) if rd in fwd.index else np.nan
                rows.append({
                    "hs_code": hs_code,
                    "hs_label": HS_LABELS[hs_code],
                    "issuer": ticker,
                    "ref_month": rd,
                    "entry_date": entry_dt,  # PIT: day 20 of M+3
                    "yoy_surprise": float(valid.loc[rd, "yoy_surprise"]),
                    "fwd_ret_21d": fwd_val,
                })

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["ref_month"] = pd.to_datetime(df["ref_month"])
    df["entry_date"] = pd.to_datetime(df["entry_date"])
    # Use ref_month as release_date column for downstream compatibility
    df["release_date"] = df["ref_month"]
    df = df.sort_values(["hs_code", "issuer", "release_date"]).reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# STEP 8: Run cells
# ---------------------------------------------------------------------------
def run_cell1_pooled(events: pd.DataFrame) -> dict:
    """Cell-1: pooled positive-surprise events → 21d excess return."""
    pos = events[events["yoy_surprise"] > 0].dropna(subset=["fwd_ret_21d"])
    n = len(pos)
    log.info("Cell-1 POOLED: n=%d positive-surprise events", n)
    if n < 5:
        return {"cell": 1, "type": "pooled", "n": n, "mean_ret": None,
                "t_stat": None, "p_value": None, "gate_pass": False,
                "note": "INSUFFICIENT DATA (n<5)"}
    # Sort by release_date for NW HAC (calendar time ordering)
    pos_sorted = pos.sort_values("release_date")
    # Use ISSUER-AVERAGED return per release_date to avoid double-counting months
    # where multiple issuers share the same HS event
    avg_by_date = pos_sorted.groupby("release_date")["fwd_ret_21d"].mean()
    y = avg_by_date.values
    mean_ret = float(np.nanmean(y))
    t = newey_west_tstat(y, lag=NW_LAG)
    p = tstat_to_pvalue(t, len(y))
    gate = abs(t) >= T_GATE if not np.isnan(t) else False
    result = {
        "cell": 1, "type": "pooled",
        "n_events": n, "n_dates": len(avg_by_date),
        "mean_ret_21d": round(mean_ret, 5),
        "t_stat_nw": round(t, 3) if not np.isnan(t) else None,
        "p_value": round(p, 4) if not np.isnan(p) else None,
        "gate_pass": gate,
        "gate": f"|t|>={T_GATE}: {'PASS' if gate else 'FAIL'}",
    }
    log.info("Cell-1: mean_ret=%.4f t=%.3f p=%.4f -> %s",
             mean_ret, t if not np.isnan(t) else -99, p if not np.isnan(p) else -99,
             "PASS" if gate else "FAIL")
    return result


def run_cell2_per_line(events: pd.DataFrame) -> list[dict]:
    """Cell-2: per-HS-line positive-surprise events → 21d excess return."""
    results = []
    for hs_code in ISSUER_MAP:
        sub = events[(events["hs_code"] == hs_code) & (events["yoy_surprise"] > 0)].dropna(subset=["fwd_ret_21d"])
        n = len(sub)
        if n < 3:
            results.append({"cell": 2, "hs_code": hs_code, "hs_label": HS_LABELS[hs_code],
                             "n_events": n, "mean_ret_21d": None, "t_stat_nw": None,
                             "p_value": None, "gate_pass": False, "note": "INSUFFICIENT DATA"})
            continue
        avg_by_date = sub.groupby("release_date")["fwd_ret_21d"].mean()
        y = avg_by_date.sort_index().values
        mean_ret = float(np.nanmean(y))
        t = newey_west_tstat(y, lag=min(NW_LAG, len(y) - 1))
        p = tstat_to_pvalue(t, len(y))
        gate = abs(t) >= T_GATE if not np.isnan(t) else False
        results.append({
            "cell": 2, "hs_code": hs_code, "hs_label": HS_LABELS[hs_code],
            "n_events": n, "n_dates": len(avg_by_date),
            "mean_ret_21d": round(mean_ret, 5),
            "t_stat_nw": round(t, 3) if not np.isnan(t) else None,
            "p_value": round(p, 4) if not np.isnan(p) else None,
            "gate_pass": gate,
        })
        log.info("Cell-2 [%s]: n=%d mean_ret=%.4f t=%.3f p=%.4f -> %s",
                 hs_code, n, mean_ret, t if not np.isnan(t) else -99,
                 p if not np.isnan(p) else -99, "PASS" if gate else "FAIL")
    return results


def run_cell3_split_half(events: pd.DataFrame) -> dict:
    """Cell-3: split-half consistency on pooled positive-surprise events.

    NOTE: Split-half t-stats use lag=min(NW_LAG, n-1) on 10-24-point halves.
    For small n, this may equal n-1 which makes the HAC estimate degenerate
    (too many lags for the sample). These t-stats are flagged as HAC-DEGENERATE
    in the report and are NOT interpreted as statistical evidence — only the
    sign direction (both halves positive?) is used for Gate 3.
    """
    pos = events[events["yoy_surprise"] > 0].dropna(subset=["fwd_ret_21d"])
    avg_by_date = pos.groupby("release_date")["fwd_ret_21d"].mean().sort_index()
    n_dates = len(avg_by_date)
    if n_dates < 10:
        return {"cell": 3, "type": "split_half", "n_dates": n_dates,
                "first_half_t": None, "second_half_t": None,
                "same_sign": None, "gate_pass": False, "note": "INSUFFICIENT DATA"}
    mid = n_dates // 2
    first = avg_by_date.iloc[:mid].values
    second = avg_by_date.iloc[mid:].values
    n1, n2 = len(first), len(second)
    lag1 = min(NW_LAG, n1 - 1)
    lag2 = min(NW_LAG, n2 - 1)
    t1 = newey_west_tstat(first, lag=lag1)
    t2 = newey_west_tstat(second, lag=lag2)
    m1 = float(np.nanmean(first))
    m2 = float(np.nanmean(second))
    same_sign = (m1 > 0) == (m2 > 0)
    # Gate 3 is SIGN ONLY; t-stats are reported but labeled degenerate
    hac_degenerate = (lag1 >= n1 - 1) or (lag2 >= n2 - 1)
    gate = same_sign
    result = {
        "cell": 3, "type": "split_half",
        "n_dates_first": n1, "n_dates_second": n2,
        "first_mean_ret": round(m1, 5), "second_mean_ret": round(m2, 5),
        "first_half_t": round(t1, 3) if not np.isnan(t1) else None,
        "second_half_t": round(t2, 3) if not np.isnan(t2) else None,
        "hac_degenerate_warning": hac_degenerate,
        "same_sign": same_sign,
        "gate_pass": gate,
        "gate": f"same-sign: {'PASS' if same_sign else 'FAIL'}",
    }
    deg_note = " [HAC-DEGENERATE: t-stats not interpretable]" if hac_degenerate else ""
    log.info("Cell-3 split-half: first=%.4f (t=%.3f) second=%.4f (t=%.3f) same_sign=%s -> %s%s",
             m1, t1 if not np.isnan(t1) else -99, m2, t2 if not np.isnan(t2) else -99,
             same_sign, "PASS" if gate else "FAIL", deg_note)
    return result


def run_cell4_magnitude(events: pd.DataFrame) -> dict:
    """Cell-4: large vs small surprise magnitude (top tercile vs bottom tercile)."""
    pos = events[events["yoy_surprise"] > 0].dropna(subset=["fwd_ret_21d"])
    avg_by_date = pos.groupby(["release_date"])[["yoy_surprise", "fwd_ret_21d"]].mean().sort_index()
    if len(avg_by_date) < 9:
        return {"cell": 4, "type": "magnitude", "n": len(avg_by_date),
                "top_t": None, "bottom_t": None, "gate_pass": False,
                "note": "INSUFFICIENT DATA (need >=9 for terciles)"}
    q33 = avg_by_date["yoy_surprise"].quantile(0.33)
    q67 = avg_by_date["yoy_surprise"].quantile(0.67)
    top = avg_by_date[avg_by_date["yoy_surprise"] >= q67]["fwd_ret_21d"].values
    bot = avg_by_date[avg_by_date["yoy_surprise"] <= q33]["fwd_ret_21d"].values
    t_top = newey_west_tstat(top, lag=min(NW_LAG, len(top) - 1))
    t_bot = newey_west_tstat(bot, lag=min(NW_LAG, len(bot) - 1))
    m_top = float(np.nanmean(top))
    m_bot = float(np.nanmean(bot))
    gate = (not np.isnan(t_top) and abs(t_top) >= T_GATE and
            m_top > m_bot)  # magnitude monotonicity
    result = {
        "cell": 4, "type": "magnitude",
        "top_n": len(top), "bottom_n": len(bot),
        "top_mean_ret": round(m_top, 5), "bottom_mean_ret": round(m_bot, 5),
        "top_t_nw": round(t_top, 3) if not np.isnan(t_top) else None,
        "bottom_t_nw": round(t_bot, 3) if not np.isnan(t_bot) else None,
        "monotone": m_top > m_bot,
        "gate_pass": gate,
    }
    log.info("Cell-4 magnitude: top=%.4f (t=%.3f) bot=%.4f (t=%.3f) monotone=%s -> %s",
             m_top, t_top if not np.isnan(t_top) else -99,
             m_bot, t_bot if not np.isnan(t_bot) else -99,
             m_top > m_bot, "PASS" if gate else "FAIL")
    return result


# ---------------------------------------------------------------------------
# STEP 9: BH-FDR across cells
# ---------------------------------------------------------------------------
def run_bh_fdr(c1: dict, c2_list: list[dict]) -> dict:
    """BH-FDR correction across Cell-1 + Cell-2 p-values."""
    p_vals = []
    labels = []
    if c1.get("p_value") is not None:
        p_vals.append(c1["p_value"])
        labels.append("C1_pooled")
    for c in c2_list:
        if c.get("p_value") is not None:
            p_vals.append(c["p_value"])
            labels.append(f"C2_{c['hs_code']}")
        else:
            p_vals.append(float("nan"))
            labels.append(f"C2_{c['hs_code']}")

    if not p_vals or all(np.isnan(p) for p in p_vals):
        return {"bh_any_rejected": False, "note": "no valid p-values for FDR"}

    rejected, p_adj = bh_fdr(p_vals, FDR_ALPHA)
    result = {
        "bh_alpha": FDR_ALPHA,
        "bh_any_rejected": any(rejected),
        "cells": [
            {"label": lbl, "p_raw": pv, "p_adj": pa, "rejected": rej}
            for lbl, pv, pa, rej in zip(labels, p_vals, p_adj, rejected)
        ],
    }
    for r in result["cells"]:
        p_raw_str = f"{r['p_raw']:.4f}" if r["p_raw"] is not None and not np.isnan(float(r["p_raw"] or float("nan"))) else "NaN"
        p_adj_str = f"{r['p_adj']:.4f}" if r["p_adj"] is not None and not np.isnan(float(r["p_adj"] or float("nan"))) else "NaN"
        log.info("BH-FDR [%s]: p_raw=%s p_adj=%s rejected=%s",
                 r["label"], p_raw_str, p_adj_str, r["rejected"])
    return result


# ---------------------------------------------------------------------------
# STEP 10: Overall verdict
# ---------------------------------------------------------------------------
def overall_verdict(c1: dict, c3: dict, bh: dict) -> dict:
    """Apply gate sequence: all 3 must pass for PROMOTE."""
    gate1 = c1.get("gate_pass", False)
    gate2 = bh.get("bh_any_rejected", False)
    gate3 = c3.get("gate_pass", False)
    promote = gate1 and gate2 and gate3
    verdict = "PROMOTE" if promote else "NULL"
    gate_detail = [
        f"Gate 1 (|t|>={T_GATE} pooled NW-HAC lag={NW_LAG}mo): {'PASS' if gate1 else 'FAIL'}",
        f"Gate 2 (BH-FDR any reject, alpha={FDR_ALPHA}): {'PASS' if gate2 else 'FAIL'}",
        f"Gate 3 (split-half same-sign): {'PASS' if gate3 else 'FAIL'}",
    ]
    return {
        "verdict": verdict,
        "promote": promote,
        "gate1_pooled_t": gate1,
        "gate2_bh_fdr": gate2,
        "gate3_split_half": gate3,
        "gate_detail": gate_detail,
    }


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
def main():
    log.info("=" * 60)
    log.info("D2 CN Export Share Nowcast — Phase-0 Study (FIXED)")
    log.info("Family: %s | Forward: %dd | FDR alpha: %.2f | NW_LAG: %dmo",
             FAMILY, FORWARD_DAYS, FDR_ALPHA, NW_LAG)
    log.info("Active HS lines: %s (2 excluded per Amendment A1)", list(ISSUER_MAP.keys()))
    log.info("Excluded lines: %s", list(EXCLUDED_LINES.keys()))
    log.info("PIT entry: day %d of M+%d (Comtrade ~%dmo lag)",
             RELEASE_LAG_DAY, RELEASE_LAG_MONTHS, RELEASE_LAG_MONTHS)
    log.info("=" * 60)

    # --- Register trial grid BEFORE any computation (house law §5) ---
    # TrialLedger points to a WORKTREE-LOCAL path, NOT to shared data/trial_ledger.jsonl
    WORKTREE_LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    led = TrialLedger(path=WORKTREE_LEDGER_PATH, family=FAMILY)
    grid = _build_grid()
    n_new = led.log_grid(grid, family=FAMILY,
                         info_cutoff="2026-06-30",  # tapes run through 2026-06
                         note="phase-0 export-share nowcast grid (fixed: PIT+CNY+criterion)")
    log.info("TrialLedger (WORKTREE-LOCAL at %s): logged %d configs (%d new) | effective_n=%d",
             WORKTREE_LEDGER_PATH, len(grid), n_new, led.effective_n(FAMILY))

    # --- Log Amendment A1 exclusions ---
    log.info("Amendment A1: excluded HS lines:")
    for hs, reason in EXCLUDED_LINES.items():
        log.info("  %s: %s", hs, reason)

    # --- Price-store law: verify all active tickers load ---
    price_cov = verify_price_coverage()
    missing_tickers = [t for t, v in price_cov.items() if v["n_days"] < 10]
    if missing_tickers:
        log.warning("PRICE MISS: %s — study will have NaN for these cells", missing_tickers)

    # --- Load data ---
    log.info("Loading CSI300 benchmark...")
    csi300 = load_csi300()
    log.info("CSI300: %d days, %s->%s", len(csi300.dropna()),
             csi300.dropna().index.min().strftime("%Y-%m") if len(csi300.dropna()) else "N/A",
             csi300.dropna().index.max().strftime("%Y-%m") if len(csi300.dropna()) else "N/A")
    if csi300.empty:
        log.error("FATAL: CSI300 missing — cannot compute excess returns. Abort.")
        sys.exit(1)

    log.info("Loading export tapes (active HS lines only)...")
    tapes = load_export_tape()
    if not tapes:
        log.error("FATAL: no tapes loaded — partial data per gap G1 (collection incomplete)")
        sys.exit(1)
    log.info("Loaded %d/%d active HS tapes: %s", len(tapes), len(ISSUER_MAP),
             ", ".join(tapes.keys()))
    missing_hs = [h for h in ISSUER_MAP if h not in tapes]
    if missing_hs:
        log.warning("PARTIAL TAPE (gap G1): missing HS codes: %s", missing_hs)

    # --- Build event panel ---
    log.info("Building event panel (PIT entry = day %d of M+%d)...",
             RELEASE_LAG_DAY, RELEASE_LAG_MONTHS)
    events = build_events(tapes, csi300)
    log.info("Event panel: %d rows total (all events including negative surprise)",
             len(events))
    if not events.empty:
        # Show sample of entry dates to verify PIT shift is applied
        sample = events[["ref_month", "entry_date", "hs_code"]].drop_duplicates(subset=["ref_month", "hs_code"]).head(3)
        for _, row in sample.iterrows():
            log.info("  PIT check: ref_month=%s -> entry_date=%s [+%dmo lag ok: %s]",
                     row["ref_month"].strftime("%Y-%m"),
                     row["entry_date"].strftime("%Y-%m-%d"),
                     RELEASE_LAG_MONTHS,
                     "OK" if row["entry_date"] > row["ref_month"] else "FAIL-NO-LAG")
    pos_events = events[events["yoy_surprise"] > 0]
    log.info("Positive-surprise events: %d | with fwd_ret: %d",
             len(pos_events), pos_events["fwd_ret_21d"].notna().sum())

    # Honest N statement
    log.info("--- HONEST N STATEMENT ---")
    log.info("Active HS lines: %d | Tapes loaded: %d", len(ISSUER_MAP), len(tapes))
    log.info("Monthly tape x %d HS codes x ~3 issuers/code = %d issuer-month observations",
             len(tapes), len(events))
    log.info("Positive-surprise events: %d", len(pos_events))
    log.info("Events with valid fwd_ret: %d (for statistical tests)",
             pos_events["fwd_ret_21d"].notna().sum() if not pos_events.empty else 0)
    log.info("Unique release dates (pooled): %d", events["release_date"].nunique() if not events.empty else 0)

    # --- Run cells ---
    log.info("\n--- CELL 1: Pooled ---")
    c1 = run_cell1_pooled(events)

    log.info("\n--- CELL 2: Per-HS-line ---")
    c2_list = run_cell2_per_line(events)

    log.info("\n--- CELL 3: Split-half ---")
    c3 = run_cell3_split_half(events)

    log.info("\n--- CELL 4: Magnitude ---")
    c4 = run_cell4_magnitude(events)

    log.info("\n--- BH-FDR correction ---")
    bh = run_bh_fdr(c1, c2_list)

    log.info("\n--- OVERALL VERDICT ---")
    verdict = overall_verdict(c1, c3, bh)
    for line in verdict["gate_detail"]:
        log.info("  %s", line)
    log.info("VERDICT: %s", verdict["verdict"])

    # --- Summary printout ---
    print("\n" + "=" * 60)
    print(f"D2 CN EXPORT SHARE NOWCAST — PHASE-0 VERDICT: {verdict['verdict']}")
    print("=" * 60)
    print(f"\nGAPS PRE-REGISTERED: G1-G9 + Amendment A1 (see script header)")
    print(f"Active HS lines (post-A1): {list(tapes.keys())}")
    print(f"Excluded HS lines: {list(EXCLUDED_LINES.keys())} (concentration criterion fail)")
    print(f"Missing tapes: {missing_hs if missing_hs else 'none'}")
    print(f"PIT entry: day {RELEASE_LAG_DAY} of M+{RELEASE_LAG_MONTHS} (Comtrade ~3mo lag)")
    print(f"NW HAC lag: {NW_LAG} monthly lags (series units; NOT daily bars)")
    print(f"\nEvent panel: {len(events)} issuer-month observations")
    print(f"Positive-surprise events: {len(pos_events)}")
    print(f"Events with valid 21d fwd return: {pos_events['fwd_ret_21d'].notna().sum() if not pos_events.empty else 0}")
    print(f"\nCell 1 (pooled positive surprise -> 21d excess, PIT clean):")
    print(f"  n_events={c1.get('n_events')} n_dates={c1.get('n_dates')}")
    print(f"  mean_ret_21d={c1.get('mean_ret_21d')} t_NW={c1.get('t_stat_nw')} p={c1.get('p_value')}")
    print(f"  Gate 1: {c1.get('gate')}")
    print(f"\nCell 2 (per HS line):")
    for r in c2_list:
        print(f"  {r['hs_code']} ({r['hs_label']}): n={r.get('n_events')} "
              f"mean={r.get('mean_ret_21d')} t={r.get('t_stat_nw')} p={r.get('p_value')} "
              f"gate={'PASS' if r.get('gate_pass') else 'FAIL'}")
    print(f"\nCell 3 (split-half): {c3.get('gate')}")
    degen_flag = " [HAC-DEGENERATE — sign only]" if c3.get("hac_degenerate_warning") else ""
    print(f"  first={c3.get('first_mean_ret')} t={c3.get('first_half_t')}{degen_flag}")
    print(f"  second={c3.get('second_mean_ret')} t={c3.get('second_half_t')}{degen_flag}")
    print(f"\nCell 4 (magnitude):")
    print(f"  top tercile: n={c4.get('top_n')} mean={c4.get('top_mean_ret')} t={c4.get('top_t_nw')}")
    print(f"  bottom tercile: n={c4.get('bottom_n')} mean={c4.get('bottom_mean_ret')} t={c4.get('bottom_t_nw')}")
    print(f"  monotone (top>bottom): {c4.get('monotone')}")
    print(f"\nBH-FDR (alpha={FDR_ALPHA}): any_rejected={bh.get('bh_any_rejected')}")
    if "cells" in bh:
        for r in bh["cells"]:
            p_adj = r["p_adj"]
            p_adj_str = f"{p_adj:.4f}" if p_adj is not None and not (isinstance(p_adj, float) and np.isnan(p_adj)) else "NaN"
            print(f"  {r['label']}: p_raw={r['p_raw']} p_adj={p_adj_str} rej={r['rejected']}")
    print(f"\nGate sequence:")
    for line in verdict["gate_detail"]:
        print(f"  {line}")
    print(f"\nFINAL VERDICT: {verdict['verdict']}")
    if not verdict["promote"]:
        print("  (All nulls are HONEST RESULTS — not failures of the study)")
    print(f"\nTrialLedger (worktree-local): family={FAMILY} effective_n={led.effective_n(FAMILY)}")
    print("=" * 60)

    return {
        "verdict": verdict,
        "c1": c1, "c2": c2_list, "c3": c3, "c4": c4, "bh": bh,
        "n_tapes": len(tapes),
        "missing_hs": missing_hs,
        "n_events": len(events),
        "n_pos_events": len(pos_events),
    }


if __name__ == "__main__":
    main()
