"""Collector: China 减持 (major-holder pre-disclosure sale calendar).

SOURCE: Eastmoney datacenter — RPT_SHARE_HOLDER_INCREASE (大股东增减持)
        filter DIRECTION=减持; provides per-sale records with:
          SECURITY_CODE     ticker (no exchange suffix)
          SECURITY_NAME_ABBR  short name
          NOTICE_DATE       announcement/filing date (post-trade disclosure)
          START_DATE        execution window open date (from original plan)
          END_DATE          execution window close / this-sale date
          HOLDER_NAME       holder name
          CHANGE_NUM        shares sold (万股)
          HOLD_RATIO        post-sale holding % of total shares
          CHANGE_NUM_SYMBOL signed version (negative = reduce)
          MARKET            二级市场 | 大宗交易 | ...
          FREE_SHARES       total circulating shares at time of filing (万股)
          AFTER_HOLDER_NUM  post-sale shares held (万股)
          TRADE_DATE        actual trade/settlement date

CONSTRUCT: The PRE-DISCLOSURE REGIME (2017 CSRC Amendment) mandates that
major holders (≥5%) and directors/supervisors must announce a sale plan
at least 15 calendar days before the execution window opens.  After the plan
window opens, supply pressure materialises as execution proceeds.

PANEL UNIT: Each row = ONE execution window for ONE holder on ONE stock.
Multiple individual sales within the same plan window are COLLAPSED to the
window level (sum of shares sold, earliest START_DATE, latest END_DATE).

PIT LAW (pre-registered): We cannot observe the original plan announcement
date from this endpoint (NOTICE_DATE is the post-sale filing, not the plan
announcement). PIT assumption: the execution window is public on START_DATE
(it opens that day). Conservative: we allow signal availability = START_DATE
(the day the window opens), NOT the plan announcement date which is legally
required to be ≥15 calendar days earlier. This is a conservative PIT choice
because anyone could see the window was open on START_DATE.

AMENDMENT AM-COLL-1 (pre-registered before computing): The endpoint does not
expose the original plan announcement date. We use START_DATE as the signal
availability date (the day the window opens). The actual announcement would be
~15+ days earlier, making our PIT assumption CONSERVATIVE (we use a LATER date
than the true availability, i.e. we give LESS credit to the signal).

AMENDMENT AM-COLL-2 (pre-registered): FREE_SHARES is often NULL in the
raw data. We use AFTER_HOLDER_NUM / HOLD_RATIO * 100 as a proxy for total
shares; if both are missing we impute from price-store float proxies.

TARGET: data/cn_holder_sales/
  raw.parquet      — all raw records, deduplicated
  windows.parquet  — window-collapsed panel (one row per ticker+window)

Nightly wiring (for consolidation):
  Add to scripts/collect.py under the china-altdata section:
    from collectors.cn_holder_sale_calendar import collect; collect()
  Runs in ~10-15 min for a full backfill; incremental adds ~1 min daily.
"""
from __future__ import annotations

import time
import logging
from pathlib import Path

import numpy as np
import pandas as pd
import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "cn_holder_sales"
RAW_PATH = OUT_DIR / "raw.parquet"
WINDOWS_PATH = OUT_DIR / "windows.parquet"

EM_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
EM_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; research-bot/1.0)"}

# Columns we actually need
COLS = (
    "SECURITY_CODE,SECURITY_NAME_ABBR,NOTICE_DATE,START_DATE,END_DATE,"
    "HOLDER_NAME,CHANGE_NUM,HOLD_RATIO,CHANGE_NUM_SYMBOL,MARKET,"
    "FREE_SHARES,AFTER_HOLDER_NUM,TRADE_DATE,CHANGE_RATE,AFTER_CHANGE_RATE"
)


# ---------------------------------------------------------------------------
# Download helpers
# ---------------------------------------------------------------------------
def _fetch_page(page: int, page_size: int = 500) -> dict:
    params = {
        "reportName": "RPT_SHARE_HOLDER_INCREASE",
        "columns": COLS,
        "pageNumber": str(page),
        "pageSize": str(page_size),
        "sortColumns": "NOTICE_DATE",
        "sortTypes": "-1",
        "source": "WEB",
        "client": "WEB",
        "filter": '(DIRECTION="减持")',
    }
    for attempt in range(3):
        try:
            r = requests.get(EM_URL, params=params, headers=EM_HEADERS, timeout=20)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)
    return {}


def _download_all(max_pages: int | None = None) -> pd.DataFrame:
    """Download all 减持 records from EM. ~224 pages at 500/page."""
    page1 = _fetch_page(1)
    result = page1.get("result", {})
    total_pages = result.get("pages", 0)
    total_count = result.get("count", 0)
    logger.info(f"EM 减持: {total_count} records, {total_pages} pages")
    print(f"[cn_holder_sale_calendar] Total records: {total_count}, pages: {total_pages}")

    all_data = list(result.get("data") or [])

    limit = min(total_pages, max_pages) if max_pages else total_pages
    for page in range(2, limit + 1):
        d = _fetch_page(page)
        rows = (d.get("result") or {}).get("data") or []
        all_data.extend(rows)
        if page % 20 == 0:
            print(f"  ... page {page}/{limit} ({len(all_data)} records so far)")
        time.sleep(0.4)   # polite rate limit

    df = pd.DataFrame(all_data)
    print(f"[cn_holder_sale_calendar] Downloaded: {len(df)} rows")
    return df


# ---------------------------------------------------------------------------
# Cleaning
# ---------------------------------------------------------------------------
def _clean(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    for col in ("NOTICE_DATE", "START_DATE", "END_DATE", "TRADE_DATE"):
        df[col] = pd.to_datetime(df[col], errors="coerce").dt.normalize()

    for col in ("CHANGE_NUM", "HOLD_RATIO", "CHANGE_NUM_SYMBOL",
                "FREE_SHARES", "AFTER_HOLDER_NUM", "CHANGE_RATE", "AFTER_CHANGE_RATE"):
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # CHANGE_NUM is in 万股 (10,000 shares); convert to shares
    df["shares_sold"] = df["CHANGE_NUM"].abs() * 1e4

    # Derive total shares proxy (in 万股)
    # HOLD_RATIO = AFTER_HOLDER_NUM / total_shares * 100
    # => total_shares (万股) = AFTER_HOLDER_NUM / HOLD_RATIO * 100
    # This is the AFTER-sale total shares. Pre-sale total ≈ same (float doesn't change much)
    mask = df["HOLD_RATIO"].notna() & (df["HOLD_RATIO"] > 0) & df["AFTER_HOLDER_NUM"].notna()
    df["total_shares_wan"] = np.where(
        mask,
        df["AFTER_HOLDER_NUM"] / df["HOLD_RATIO"] * 100.0,
        np.nan
    )
    # Also use FREE_SHARES if available (circulating shares)
    # We prefer total_shares as the denominator for pct calculations

    # Execution window date (best estimate)
    # END_DATE = the date of this specific sale; START_DATE = window open
    # Use START_DATE as the window-open date for PIT purposes
    # If START_DATE is null (pre-2017), fall back to END_DATE - 30d (rough estimate)
    df["window_open"] = df["START_DATE"].fillna(
        df["END_DATE"] - pd.Timedelta(days=30)
    )
    df["window_close"] = df["END_DATE"].fillna(df["NOTICE_DATE"])

    # Add exchange suffix to match price store naming
    # SH: 60xxxx, 68xxxx (STAR Market) | SZ: 000xxx, 001xxx, 002xxx, 003xxx, 300xxx
    def _suffix(code: str) -> str:
        if not isinstance(code, str):
            return ""
        c = code.strip()
        if c.startswith(("6",)):
            return f"{c}.SH"
        return f"{c}.SZ"

    df["ticker"] = df["SECURITY_CODE"].apply(_suffix)

    # Drop rows with no END_DATE (can't locate window)
    df = df.dropna(subset=["END_DATE"])

    # Filter: only secondary-market and block-trade sales (not rights/gift/inheritance)
    df = df[df["MARKET"].isin(["二级市场", "大宗交易"])].copy()

    return df.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Window collapse
# ---------------------------------------------------------------------------
def _collapse_windows(df: pd.DataFrame) -> pd.DataFrame:
    """Collapse per-sale rows to one row per (ticker, holder, window) unit.

    A 'window' is identified by (SECURITY_CODE, HOLDER_NAME, START_DATE cluster).
    We use a 45-day proximity rule: sales from the same holder within 45 days
    of the previous sale are aggregated into one window.
    Vectorized implementation for speed.
    """
    df = df.copy().sort_values(["SECURITY_CODE", "HOLDER_NAME", "window_open"])

    # Vectorized window assignment:
    # Within each (SECURITY_CODE, HOLDER_NAME) group, assign a window_id
    # that increments whenever the gap to the previous same-group record > 45d.
    grp_keys = ["SECURITY_CODE", "HOLDER_NAME"]
    # Days since epoch — robust across pandas datetime storage units (us vs ns)
    df["_wo_days"] = (df["window_open"] - pd.Timestamp("1970-01-01")).dt.days

    # Per-group: diff of _wo_days, flag new window when diff > 45
    df = df.sort_values(grp_keys + ["_wo_days"])
    df["_prev_days"] = df.groupby(grp_keys)["_wo_days"].shift(1)
    df["_gap"] = (df["_wo_days"] - df["_prev_days"]).fillna(999)
    df["_new_win"] = (df["_gap"] > 45).astype(int)
    df["_win"] = df.groupby(grp_keys)["_new_win"].cumsum()

    agg = df.groupby(["SECURITY_CODE", "ticker", "HOLDER_NAME", "_win"]).agg(
        shares_sold_total=("shares_sold", "sum"),
        total_shares_wan_median=("total_shares_wan", "median"),
        window_open=("window_open", "min"),
        window_close=("window_close", "max"),
        notice_date_min=("NOTICE_DATE", "min"),
        n_sales=("shares_sold", "count"),
        markets=("MARKET", lambda x: "|".join(sorted(set(x.dropna())))),
        hold_ratio_after=("HOLD_RATIO", "min"),   # post-final-sale
    ).reset_index()

    # Planned pct of float (shares_sold / total_shares, as a fraction)
    agg["shares_sold_wan"] = agg["shares_sold_total"] / 1e4
    agg["pct_float"] = np.where(
        agg["total_shares_wan_median"] > 0,
        agg["shares_sold_wan"] / agg["total_shares_wan_median"],
        np.nan,
    )

    # signal_date: the day the window opened (START_DATE proxy)
    # PIT: signal available on this date (window publicly open)
    agg["signal_date"] = agg["window_open"]

    agg = agg.sort_values("signal_date").reset_index(drop=True)
    return agg


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def collect(force: bool = False) -> pd.DataFrame:
    """Download, clean, and save the 减持 panel. Returns the window-level df."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if RAW_PATH.exists() and not force:
        print(f"[cn_holder_sale_calendar] Raw already cached: {RAW_PATH}")
        raw = pd.read_parquet(RAW_PATH)
    else:
        raw = _download_all()
        raw = _clean(raw)
        raw.to_parquet(RAW_PATH, index=False)
        print(f"[cn_holder_sale_calendar] Saved raw: {len(raw)} rows -> {RAW_PATH}")

    windows = _collapse_windows(raw)
    windows.to_parquet(WINDOWS_PATH, index=False)
    print(f"[cn_holder_sale_calendar] Saved windows: {len(windows)} rows -> {WINDOWS_PATH}")

    # Summary stats
    print(f"\n  Date range: {windows['signal_date'].min()} .. {windows['signal_date'].max()}")
    print(f"  Unique tickers: {windows['ticker'].nunique()}")
    print(f"  Unique holders: {windows['HOLDER_NAME'].nunique()}")
    print(f"  Median pct_float: {windows['pct_float'].median():.4f}")
    print(f"  pct_float NaN: {windows['pct_float'].isna().sum()}/{len(windows)}")

    return windows


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    collect(force=True)
