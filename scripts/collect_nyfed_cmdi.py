"""Standalone collector: NY Fed Corporate Bond Market Distress Index (CMDI).

Fetches the CMDI Excel file from the NY Fed interactive data endpoint,
parses Market CMDI, IG CMDI, HY CMDI sub-indices, and saves:
  - data/nyfed_cmdi/cmdi_weekly.parquet   (raw weekly, end-of-week Friday)
  - data/nyfed_cmdi/cmdi_monthly.parquet  (month-end last-reading resample)

Idempotent: skips download if the cached file is from today (or force=True
overrides). Safe to run weekly — NY Fed publishes monthly but may re-release.

Nightly wiring (for consolidation into scripts/collect.py):
  from scripts.collect_nyfed_cmdi import collect_nyfed_cmdi
  collect_nyfed_cmdi()

URL verified 2026-07-06:
  https://www.newyorkfed.org/medialibrary/research/interactives/data/cmdi/cmdi_interactive_data.xlsx
  (discovered from the CMDI interactive JS bundle at /medialibrary/Research/Interactives/cmdi/js/main-es2015.js)
"""
from __future__ import annotations

import io
import sys
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
CMDI_DIR = DATA_DIR / "nyfed_cmdi"
CMDI_WEEKLY_PATH = CMDI_DIR / "cmdi_weekly.parquet"
CMDI_MONTHLY_PATH = CMDI_DIR / "cmdi_monthly.parquet"

CMDI_URL = (
    "https://www.newyorkfed.org/medialibrary/research/interactives/data/cmdi/"
    "cmdi_interactive_data.xlsx"
)
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _is_fresh(path: Path, max_age_days: int = 0) -> bool:
    """True if the file exists and was written today (max_age_days=0)."""
    if not path.exists():
        return False
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).date()
    return (date.today() - mtime).days <= max_age_days


def collect_nyfed_cmdi(force: bool = False) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Download and cache CMDI. Returns (weekly_df, monthly_df).

    force=True re-downloads even if today's cache exists.
    """
    CMDI_DIR.mkdir(parents=True, exist_ok=True)

    if not force and _is_fresh(CMDI_WEEKLY_PATH, max_age_days=0):
        weekly = pd.read_parquet(CMDI_WEEKLY_PATH)
        monthly = pd.read_parquet(CMDI_MONTHLY_PATH)
        print(f"[cmdi] cache fresh: {len(weekly)} weekly rows, "
              f"{weekly.index.min().date()} -> {weekly.index.max().date()}")
        return weekly, monthly

    print(f"[cmdi] downloading from NY Fed...")
    req = urllib.request.Request(CMDI_URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
    except Exception as e:
        print(f"[cmdi] ERROR: download failed: {e}")
        if CMDI_WEEKLY_PATH.exists():
            print("[cmdi] falling back to cached file")
            weekly = pd.read_parquet(CMDI_WEEKLY_PATH)
            monthly = pd.read_parquet(CMDI_MONTHLY_PATH)
            return weekly, monthly
        raise

    df = pd.read_excel(io.BytesIO(raw), sheet_name="Sheet1")
    df = df.rename(columns={
        "eow_friday": "date",
        "Market CMDI": "market_cmdi",
        "IG CMDI": "ig_cmdi",
        "HY CMDI": "hy_cmdi",
    })
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()

    # Keep sub-indices and percentile bands (p5..p99 are useful context)
    keep_cols = ["market_cmdi", "ig_cmdi", "hy_cmdi",
                 "p5", "p10", "p25", "p50", "p75", "p90", "p95", "p99"]
    df = df[[c for c in keep_cols if c in df.columns]]

    # Validate coverage
    assert len(df) > 500, f"CMDI unexpectedly short: {len(df)} rows"
    assert "market_cmdi" in df.columns, "market_cmdi column missing"

    df.to_parquet(CMDI_WEEKLY_PATH)
    print(f"[cmdi] saved {len(df)} weekly rows -> {CMDI_WEEKLY_PATH}")

    # Resample to month-end (last available reading in each calendar month)
    monthly = df[["market_cmdi", "ig_cmdi", "hy_cmdi"]].resample("ME").last()
    monthly.to_parquet(CMDI_MONTHLY_PATH)
    print(f"[cmdi] saved {len(monthly)} monthly rows -> {CMDI_MONTHLY_PATH}")

    return df, monthly


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Collect NY Fed CMDI")
    ap.add_argument("--force", action="store_true", help="Force re-download")
    args = ap.parse_args()
    weekly, monthly = collect_nyfed_cmdi(force=args.force)
    print(f"\nWeekly tail:\n{weekly.tail(3)}")
    print(f"\nMonthly tail:\n{monthly.tail(3)}")
