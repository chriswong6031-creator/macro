"""HY credit flow proxy collector — D4 family (d4_credit_flow_divergence).

Data-availability audit (2026-07-08):
---------------------------------------
Rung (a) ICI weekly estimated flows
    URL: https://www.ici.org/flows_data_<YYYY>.xls  (receipt-verified)
    Coverage: rolling ~2.5-year window per file; oldest free file is
    flows_data_2025.xls whose monthly data begins 2024-01. Files for
    2023 and earlier return HTTP 404.
    VERDICT: NOT ADEQUATE — < 5 years of weekly history unavailable.

Rung (b) HYG / JNK shares-outstanding history
    - yfinance fast_info.shares: point-in-time only (no history).
    - iShares historical NAV/SO CSV endpoint: WAF-blocked (HTML returned
      for authenticated-style CSV URLs, confirmed 2026-07-08).
    VERDICT: NOT ADEQUATE — no historical SO series accessible.

Rung (c) Fallback proxy: HYG weekly dollar-volume z-score
    - HYG price + volume: data/yahoo/HYG.parquet, 2007-04-11 to present
      (4840 daily rows, 19.2 years — well above 5-year bar).
    - HY-OAS: data/fred/BAMLH0A0HYM2.parquet, 1996-12-31 to present
      (7706 daily rows).
    - Overlap when resampled to weekly: 1004 weeks, 2007-04-15 to present.
    - NAV premium-to-discount component: NOT ADDED — iShares NAV history is
      WAF-gated (rung says "if NAV series free"; it is not).
    VERDICT: ADEQUATE — HYG weekly dollar-volume z qualifies as rung-c proxy.

What is stored (data/credit_flows/):
    hyg_weekly.parquet  — weekly HYG close, dollar_volume, dollar_vol_z52,
                          hy_oas, oas_chg10d, oas_z52 (aligned weekly index).
                          dollar_vol_z52 = z-score of dollar_vol vs trailing
                          52-week mean/std (calendar-collapsed, NO look-ahead).

This module only ASSEMBLES from existing stores (data/yahoo/ and data/fred/).
No external network calls are made at collect time, so it can run offline.
"""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from lib import config, store

log = logging.getLogger(__name__)

# Trailing window for z-score (52 weeks).  Must be set BEFORE looking at results.
FLOW_Z_WINDOW = 52
OAS_Z_WINDOW = 52
OAS_CHG_WINDOW = 10  # calendar days for OAS 10d change (spread of the change)


def _load_hyg_daily() -> pd.DataFrame:
    """Read HYG from data/yahoo/ (rung-c source)."""
    df = store.read("yahoo", "HYG")
    if df is None or df.empty:
        raise RuntimeError(
            "data/yahoo/HYG.parquet missing — run yahoo collector first"
        )
    need = {"close_price", "volume"}
    missing = need - set(df.columns)
    if missing:
        raise RuntimeError(f"HYG parquet lacks columns {missing}: have {df.columns.tolist()}")
    return df[["close_price", "volume"]].copy()


def _load_oas_daily() -> pd.DataFrame:
    """Read HY-OAS from data/fred/ (BAMLH0A0HYM2)."""
    df = store.read("fred", "BAMLH0A0HYM2")
    if df is None or df.empty:
        raise RuntimeError(
            "data/fred/BAMLH0A0HYM2.parquet missing — run fred collector first"
        )
    return df[["hy_oas"]].copy()


def _trailing_z(series: pd.Series, window: int) -> pd.Series:
    """Calendar-collapse z-score: z_t = (x_t - mean(x[t-window:t])) / std(x[t-window:t]).
    Excludes t itself from the window (shift(1) convention) to avoid look-ahead.
    Returns NaN for the first `window` observations.
    """
    mu = series.shift(1).rolling(window, min_periods=window // 2).mean()
    sd = series.shift(1).rolling(window, min_periods=window // 2).std(ddof=1)
    return (series - mu) / sd.replace(0, float("nan"))


def build_weekly() -> pd.DataFrame:
    """Assemble and return the weekly credit-flow proxy frame.

    All computations use trailing/lagged windows — no look-ahead.
    Index is end-of-week Sunday (pandas default 'W' resample).
    """
    hyg = _load_hyg_daily()
    oas = _load_oas_daily()

    # Dollar volume = close_price * volume (same-day, not adjusted for splits)
    hyg["dollar_vol"] = hyg["close_price"] * hyg["volume"]

    # Resample to weekly (end-of-week Sunday aggregation)
    hyg_w = hyg.resample("W").agg(
        close_price=("close_price", "last"),
        dollar_vol=("dollar_vol", "sum"),
    ).dropna(subset=["close_price"])

    # OAS: last business day of the week; 10d change computed on daily series
    # then resampled to avoid losing intra-week spread moves
    oas["oas_chg10d"] = oas["hy_oas"].diff(OAS_CHG_WINDOW)
    oas_w = oas.resample("W").agg(
        hy_oas=("hy_oas", "last"),
        oas_chg10d=("oas_chg10d", "last"),
    ).dropna(subset=["hy_oas"])

    # Align on common weekly index
    combined = pd.concat([hyg_w, oas_w], axis=1, sort=True)
    combined = combined.dropna(subset=["close_price", "hy_oas"])
    combined.index.name = "date"

    # Trailing z-scores (no look-ahead: shift inside _trailing_z)
    combined["dollar_vol_z52"] = _trailing_z(combined["dollar_vol"], FLOW_Z_WINDOW)
    combined["oas_z52"] = _trailing_z(combined["hy_oas"], OAS_Z_WINDOW)

    return combined


def collect() -> pd.DataFrame:
    """Build and persist data/credit_flows/hyg_weekly.parquet.

    Returns the assembled frame (useful for callers / tests).
    """
    df = build_weekly()
    out_dir = config.data_dir() / "credit_flows"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "hyg_weekly.parquet"
    df.to_parquet(out_path)
    log.info(
        "credit_fund_flows: wrote %d weekly rows (%s to %s) -> %s",
        len(df),
        df.index.min().date(),
        df.index.max().date(),
        out_path,
    )
    return df


# Canonical path published for downstream consumers
def canonical_path() -> Path:
    return config.data_dir() / "credit_flows" / "hyg_weekly.parquet"
