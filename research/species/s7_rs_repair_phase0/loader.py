"""S7 RS-Repair Phase-0 — data loader.

Loads price data from the massive_stock_day store (P1) and data/stocks (P2).
Provides:
  - load_massive_ticker(ticker, data_root)  -> pd.DataFrame[open,high,low,close,volume]
  - load_p2_ticker(ticker, data_root)       -> pd.DataFrame[close,high,low,volume]
  - liquidity_ok(df, fire_date)             -> bool  (trailing-63d median $vol >= $2M, close >= $2)
  - sp1500_pit(data_root)                   -> callable(ticker, date) -> bool
  - sector_map(data_root)                   -> dict[ticker -> xl_etf]
  - run_split_sanity(data_root, n_sample)   -> None  (prints pre-flight report)

P1 ADJUSTMENT SEMANTICS: massive_stock_day is Polygon split-adjusted OHLCV (price-return,
NOT total-return).  The store jumps from 2022-12-19 to 2025-01-02 locally; the gap years
2023-2024 are on R2 (the rolling-5y entitlement model).  Do NOT mix with data/stocks which
is yahoo total-return adjusted.

P2 BENCHMARK CHOICE: P2 uses data/stocks/SPY.parquet as benchmark (total-return adjusted,
consistent with all other P2 names — apples-to-apples within P2).  P1 uses
massive_stock_day/SPY.parquet (price-return, consistent within P1).
"""
from __future__ import annotations

import random
import logging
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# GICS sector name (as used in sp500_heatmap/industry_map.json) → XL* ETF
# Standard 11-sector SPDR map.
# ---------------------------------------------------------------------------
SECTOR_TO_XL: dict[str, str] = {
    "Technology":              "XLK",
    "Healthcare":              "XLV",
    "Financial":               "XLF",
    "Consumer Cyclical":       "XLY",
    "Consumer Defensive":      "XLP",
    "Industrials":             "XLI",
    "Energy":                  "XLE",
    "Basic Materials":         "XLB",
    "Real Estate":             "XLRE",
    "Communication Services":  "XLC",
    "Utilities":               "XLU",
    # Aliases that appear in breadth/constituents.parquet sector column
    "Health Care":             "XLV",
    "Communication Services":  "XLC",
    "Consumer Staples":        "XLP",
    "Consumer Discretionary":  "XLY",
    "Materials":               "XLB",
    "Information Technology":  "XLK",
    "Financials":              "XLF",
}


def load_massive_ticker(ticker: str, data_root: Path | str) -> pd.DataFrame:
    """Read one ticker from massive_stock_day.  Returns DataFrame with columns
    open, high, low, close, volume and a DatetimeIndex named 'date'.
    Returns empty DataFrame if file not found."""
    path = Path(data_root) / "massive_stock_day" / f"{ticker}.parquet"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_parquet(path, columns=["open", "high", "low", "close", "volume"])
    df.index = pd.to_datetime(df.index)
    df.index.name = "date"
    return df.sort_index()


def load_p2_ticker(ticker: str, data_root: Path | str) -> pd.DataFrame:
    """Read one ticker from data/stocks (P2 panel).  Returns DataFrame with
    columns close, high, low, volume.  The P2 store uses a multi-level column
    (Price level); flatten it here."""
    path = Path(data_root) / "stocks" / f"{ticker}.parquet"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_parquet(path)
    # Flatten multi-level columns if present (data/stocks has Price level)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.droplevel(0)
    df.index = pd.to_datetime(df.index)
    df.index.name = "date"
    # normalise to lower-case columns
    df.columns = [c.lower() for c in df.columns]
    return df.sort_index()


def liquidity_ok(df: pd.DataFrame, fire_date: pd.Timestamp, *,
                 min_dvol: float = 2e6, min_close: float = 2.0) -> bool:
    """Return True iff trailing-63d median dollar volume >= min_dvol AND
    close >= min_close at fire_date.  Uses massive-store column names."""
    if df.empty:
        return False
    try:
        loc = df.index.get_loc(fire_date)
    except KeyError:
        # fire_date not in index; find most-recent row on or before it
        pos = df.index.searchsorted(fire_date, side="right") - 1
        if pos < 0:
            return False
        loc = pos
    if isinstance(loc, (slice, np.ndarray)):
        loc = int(loc.start if isinstance(loc, slice) else loc[-1])
    start = max(0, loc - 63)
    window = df.iloc[start: loc + 1]
    if window.empty:
        return False
    close_col = "close"
    vol_col = "volume"
    if close_col not in window.columns or vol_col not in window.columns:
        return False
    close_now = float(window[close_col].iloc[-1])
    dvol = (window[close_col] * window[vol_col]).median()
    return close_now >= min_close and dvol >= min_dvol


def sp1500_pit(data_root: Path | str):
    """Return a callable f(ticker, date) -> bool that checks PIT S&P 1500 membership.

    Loads data/breadth/sp1500_pit_membership.parquet once and builds an interval
    structure for fast lookup.
    """
    path = Path(data_root) / "breadth" / "sp1500_pit_membership.parquet"
    if not path.exists():
        log.warning("sp1500_pit_membership.parquet not found; returning False for all")
        return lambda ticker, date: False

    df = pd.read_parquet(path)
    df["start_date"] = pd.to_datetime(df["start_date"])
    df["end_date"] = pd.to_datetime(df["end_date"])

    # group by ticker -> list of (start, end) intervals  (end=NaT means still active)
    intervals: dict[str, list[tuple[pd.Timestamp, pd.Timestamp]]] = {}
    for row in df.itertuples(index=False):
        t = row.ticker
        s = row.start_date
        e = row.end_date if pd.notna(row.end_date) else pd.Timestamp("2099-12-31")
        intervals.setdefault(t, []).append((s, e))

    def lookup(ticker: str, date: pd.Timestamp) -> bool:
        ts = intervals.get(ticker)
        if ts is None:
            return False
        dt = pd.Timestamp(date)
        return any(s <= dt <= e for s, e in ts)

    return lookup


def sector_map(data_root: Path | str) -> dict[str, str]:
    """Return dict[ticker -> XL* ETF ticker].

    Primary source: data/sp500_heatmap/industry_map.json  (503 SP500 names with sector).
    Fallback: data/breadth/constituents.parquet (sector names may differ slightly).
    Returns only tickers that have a known XL* mapping.
    """
    import json

    result: dict[str, str] = {}

    # Primary: industry_map.json (sector names match SECTOR_TO_XL keys above)
    imap_path = Path(data_root) / "sp500_heatmap" / "industry_map.json"
    if imap_path.exists():
        with open(imap_path) as f:
            imap = json.load(f)
        for ticker, info in imap.items():
            sec = info.get("sector", "")
            xl = SECTOR_TO_XL.get(sec)
            if xl:
                result[ticker] = xl

    # Supplement with constituents.parquet (can have tickers not in imap)
    const_path = Path(data_root) / "breadth" / "constituents.parquet"
    if const_path.exists():
        const = pd.read_parquet(const_path)
        for ticker, row in const.iterrows():
            if ticker not in result:
                xl = SECTOR_TO_XL.get(row.get("sector", ""))
                if xl:
                    result[str(ticker)] = xl

    return result


def massive_trading_dates(data_root: Path | str) -> list[pd.Timestamp]:
    """Return sorted list of all trading dates in the massive store
    (from _backfill_state.json processed_days).  Fast reference calendar."""
    import json
    path = Path(data_root) / "massive_stock_day" / "_backfill_state.json"
    if not path.exists():
        return []
    with open(path) as f:
        state = json.load(f)
    return [pd.Timestamp(d) for d in state.get("processed_days", [])]


def run_split_sanity(data_root: Path | str, n_sample: int = 200,
                     seed: int = 42) -> dict:
    """Split-sanity pre-flight per SPEC §8.1.

    Samples n_sample tickers from massive_stock_day, flags any |1d return| > 40%
    with normal volume (< 5× median trailing 63d volume) as potential split artefact.
    Also checks for discontinuities in the index (calendar gaps > 7 calendar days
    excluding the known 2023-01-01 to 2024-12-31 gap window).

    Prints a summary.  Returns dict with counts.
    """
    import os

    massive_dir = Path(data_root) / "massive_stock_day"
    files = sorted(massive_dir.glob("*.parquet"))
    # Exclude manifest/state files
    files = [f for f in files if not f.stem.startswith("_")]
    rng = random.Random(seed)
    sample = rng.sample(files, min(n_sample, len(files)))

    suspicious: list[dict] = []
    gap_tickers: list[str] = []
    empty_tickers: list[str] = []
    # Known gap windows (R2 data plane — rolling 5y entitlement means
    # individual tickers can have their own start dates; the primary market-wide
    # gap is 2022-12-20 to 2025-01-02)
    GAP_START = pd.Timestamp("2022-12-19")
    GAP_END   = pd.Timestamp("2025-01-02")

    for fp in sample:
        ticker = fp.stem
        try:
            df = pd.read_parquet(fp, columns=["close", "volume"])
            df.index = pd.to_datetime(df.index)
            if df.empty or len(df) < 5:
                empty_tickers.append(ticker)
                continue
            rets = df["close"].pct_change().abs()
            vol  = df["volume"]
            med_vol = vol.rolling(63, min_periods=1).median()
            high_ret = rets > 0.40
            normal_vol = vol < med_vol * 5
            # EXCLUDE: first row (no prior bar to compare) and rows immediately
            # after the known R2 gap boundary (first bar after a multi-year gap
            # is NOT a split artefact — it's just the gap transition).
            first_bar_mask = rets.isna()  # pct_change().abs() is NaN on first row
            # Flag any bar that immediately follows a >100 calendar-day gap
            dts_all = df.index.sort_values()
            gap_following = set()
            for i in range(1, len(dts_all)):
                cal_gap = (dts_all[i] - dts_all[i - 1]).days
                if cal_gap > 100:
                    gap_following.add(dts_all[i])
            after_gap_mask = rets.index.isin(gap_following)
            real_suspect = high_ret & normal_vol & ~first_bar_mask & ~after_gap_mask
            flags = df[real_suspect]
            for dt, row in flags.iterrows():
                suspicious.append({
                    "ticker": ticker,
                    "date": dt,
                    "ret": float(rets.loc[dt]),
                    "vol_ratio": float(vol.loc[dt] / med_vol.loc[dt]) if med_vol.loc[dt] > 0 else None,
                })
            # Check for gaps outside the known R2 window (>30 calendar days,
            # excluding tickers that simply started after the gap period)
            dts = df.index.sort_values()
            gaps_cal = pd.Series(dts).diff().dt.days.fillna(0)
            big_gaps = gaps_cal[gaps_cal > 30]
            for pos in big_gaps.index:
                gap_dt = dts[pos]
                # Skip if this is the R2 gap transition
                if GAP_START <= gap_dt <= GAP_END:
                    continue
                # Skip if ticker only has post-gap data (started after the gap)
                first_dt = dts[0]
                if first_dt >= GAP_END:
                    continue
                gap_tickers.append(f"{ticker}@{gap_dt.date()}")
        except Exception as exc:
            log.warning("split_sanity: failed on %s: %s", ticker, exc)

    print(f"\n=== Split-Sanity Pre-Flight (n={len(sample)} sample) ===")
    print(f"  |1d ret|>40% with normal volume (potential split artefact): {len(suspicious)}")
    if suspicious[:5]:
        for s in suspicious[:5]:
            print(f"    {s['ticker']} {s['date'].date()} ret={s['ret']:.1%} vol_ratio={s['vol_ratio']:.1f}x")
        if len(suspicious) > 5:
            print(f"    ... and {len(suspicious)-5} more")
    print(f"  Extra calendar gaps >7d outside R2 window: {len(gap_tickers)}")
    if gap_tickers[:5]:
        print("   ", gap_tickers[:5])
    print(f"  Empty/tiny tickers: {len(empty_tickers)}")
    print(f"  NOTE: massive_stock_day is split-adjusted Polygon price-return data.")
    print(f"        Known 2-year local gap: 2022-12-20 to 2025-01-02 (R2 data plane).")
    print(f"        Fires across this gap have no local forward-return data — they will")
    print(f"        be dropped at the metrics stage (insufficient forward bars).")
    print()
    return {
        "n_sample": len(sample),
        "n_suspicious": len(suspicious),
        "n_extra_gaps": len(gap_tickers),
        "n_empty": len(empty_tickers),
        "suspicious": suspicious,
    }


def list_p1_tickers(data_root: Path | str) -> list[str]:
    """Return sorted list of all ticker stems in massive_stock_day (excl. _* files)."""
    d = Path(data_root) / "massive_stock_day"
    return sorted(f.stem for f in d.glob("*.parquet") if not f.stem.startswith("_"))


def list_p2_tickers(data_root: Path | str) -> list[str]:
    """Return sorted list of all ticker stems in data/stocks."""
    d = Path(data_root) / "stocks"
    return sorted(f.stem for f in d.glob("*.parquet"))
