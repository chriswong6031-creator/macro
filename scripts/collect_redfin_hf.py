"""Redfin Data Center — monthly metro housing-market collector.

Fetches Redfin's publicly available S3 data for:
  - National aggregate (all residential, non-seasonally-adjusted)
  - Top-20 metro breakdown

Metrics collected per geography:
  - pending_sales     : pending home sales count
  - inventory         : active listings count
  - price_drops       : share of listings with price reduction (0-1)
  - median_dom        : median days on market

NOTE: Redfin's public S3 data is MONTHLY granularity (period_duration=30).
The "HF" label refers to housing being monthly vs the quarterly GDP/CPI cycle;
there is no public weekly metro-level file at this URL set. The weekly data
formerly published by Redfin is no longer available via public S3 endpoints.

Writes:
  data/redfin_hf/national.parquet   — date-indexed, one row per month
  data/redfin_hf/metro.parquet      — (date, metro) multi-indexed, top-20 metros
  data/redfin_hf/agg_json.json      — display-ready JSON for cycle-intelligence wiring

Usage (standalone):
  python -m scripts.collect_redfin_hf [--force]

Nightly wiring (for consolidation):
  Add to scripts/collect.py after the FRED block:
      from scripts.collect_redfin_hf import run as collect_redfin_hf
      collect_redfin_hf()
  Suggested cron: daily, tolerates stale data (Redfin updates ~monthly).

PIT assumptions:
  - National: period_begin is the START of the reporting month; data becomes
    available approximately 2-4 weeks after month end. We store period_begin
    as the index date; callers must apply a publication lag of at least 30 days
    before using as a predictive signal.
  - Metro: same lag assumption.
  - No backfilling: each run appends new months (incremental update).
"""
from __future__ import annotations

import argparse
import gzip
import io
import json
import logging
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT_DIR = DATA / "redfin_hf"

LOG = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

NATIONAL_URL = (
    "https://redfin-public-data.s3.us-west-2.amazonaws.com/"
    "redfin_market_tracker/us_national_market_tracker.tsv000.gz"
)
METRO_URL = (
    "https://redfin-public-data.s3.us-west-2.amazonaws.com/"
    "redfin_market_tracker/redfin_metro_market_tracker.tsv000.gz"
)

HEADERS = {"User-Agent": "Mozilla/5.0 redfin-housing-collector/1.0"}

METRIC_COLS = ["pending_sales", "inventory", "price_drops", "median_dom"]
RAW_COLS = {
    "PERIOD_BEGIN": "period_begin",
    "PENDING_SALES": "pending_sales",
    "INVENTORY": "inventory",
    "PRICE_DROPS": "price_drops",
    "MEDIAN_DOM": "median_dom",
}

# Required raw columns — if any are absent, the parse RAISES rather than silently
# degrading to an all-NaN signal (Redfin TSV schema drifts; silent drops are
# invisible until downstream consumers produce garbage outputs).
REQUIRED_RAW_COLS = {
    "PROPERTY_TYPE",
    "IS_SEASONALLY_ADJUSTED",
    "PERIOD_BEGIN",
    "PENDING_SALES",
    "INVENTORY",
    "PRICE_DROPS",
    "MEDIAN_DOM",
    "REGION",
}

# Top-20 US metros by population / Redfin coverage; these are the REGION
# values in the Redfin metro file.
TOP_20_METROS = [
    "New York, NY metro area",
    "Los Angeles, CA metro area",
    "Chicago, IL metro area",
    "Dallas, TX metro area",
    "Houston, TX metro area",
    "Washington, DC metro area",
    "Miami, FL metro area",
    "Philadelphia, PA metro area",
    "Atlanta, GA metro area",
    "Phoenix, AZ metro area",
    "Boston, MA metro area",
    "San Francisco, CA metro area",
    "Riverside, CA metro area",
    "Seattle, WA metro area",
    "Minneapolis, MN metro area",
    "San Diego, CA metro area",
    "Tampa, FL metro area",
    "Denver, CO metro area",
    "Portland, OR metro area",
    "Las Vegas, NV metro area",
]

# ---------------------------------------------------------------------------
# Download helper
# ---------------------------------------------------------------------------


def _fetch_gz(url: str, timeout: int = 120) -> pd.DataFrame:
    """Download a gzip-compressed TSV from `url` and parse into a DataFrame."""
    LOG.info("Fetching %s", url)
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} fetching {url}") from exc
    with gzip.open(io.BytesIO(raw)) as f:
        return pd.read_csv(f, sep="\t", low_memory=False)


# ---------------------------------------------------------------------------
# Parse helpers
# ---------------------------------------------------------------------------


def _validate_schema(df: pd.DataFrame, context: str = "") -> None:
    """Raise ValueError if any required raw column is missing from df.

    Redfin's TSV schema drifts — silent column drops create all-NaN signals
    that only surface when downstream stats produce garbage. Hard failure here
    forces an explicit fix instead of a silent regression.
    """
    missing = REQUIRED_RAW_COLS - set(df.columns)
    if missing:
        raise ValueError(
            f"Redfin TSV schema mismatch {context}: missing columns {sorted(missing)}. "
            "Redfin may have renamed these fields — update RAW_COLS and REQUIRED_RAW_COLS."
        )


def _parse_national(df: pd.DataFrame) -> pd.DataFrame:
    """Extract national All-Residential non-SA monthly time-series."""
    _validate_schema(df, context="(national)")
    sub = df[
        (df["PROPERTY_TYPE"] == "All Residential")
        & (df["IS_SEASONALLY_ADJUSTED"].astype(str).str.lower().isin(["false", "0"]))
    ].copy()
    sub = sub.rename(columns={k: v for k, v in RAW_COLS.items() if k in sub.columns})
    sub["date"] = pd.to_datetime(sub["period_begin"])
    sub = sub.set_index("date").sort_index()
    cols = [c for c in METRIC_COLS if c in sub.columns]
    return sub[cols].dropna(how="all")


def _parse_metro(df: pd.DataFrame, metros: list[str]) -> pd.DataFrame:
    """Extract top-20-metro All-Residential non-SA monthly time-series."""
    _validate_schema(df, context="(metro)")
    sub = df[
        (df["PROPERTY_TYPE"] == "All Residential")
        & (df["IS_SEASONALLY_ADJUSTED"].astype(str).str.lower().isin(["false", "0"]))
    ].copy()

    # Match metros — first try exact REGION, then partial match for fallback
    matched_regions = set()
    for m in metros:
        exact = sub[sub["REGION"] == m]["REGION"].unique()
        if len(exact):
            matched_regions.update(exact)
        else:
            # try without " metro area" suffix
            stem = m.replace(" metro area", "")
            partial = sub[sub["REGION"].str.contains(stem, case=False, regex=False)]["REGION"].unique()
            matched_regions.update(partial)

    sub = sub[sub["REGION"].isin(matched_regions)].copy()
    sub = sub.rename(columns={k: v for k, v in RAW_COLS.items() if k in sub.columns})
    sub["date"] = pd.to_datetime(sub["period_begin"])
    sub = sub[["date", "REGION"] + [c for c in METRIC_COLS if c in sub.columns]]
    sub = sub.rename(columns={"REGION": "metro"})
    sub = sub.set_index(["date", "metro"]).sort_index()
    return sub.dropna(how="all")


# ---------------------------------------------------------------------------
# Display JSON builder
# ---------------------------------------------------------------------------


def _build_agg_json(national: pd.DataFrame, metro: pd.DataFrame) -> dict:
    """Build display-ready aggregates for site wiring.

    Returns a dict with:
      - national: most-recent 24 months of national metrics
      - metro_latest: latest available month per metro (for scorecards)
      - as_of: ISO date of the most recent data point
    """
    nat_recent = national.tail(24).reset_index()
    nat_recent["date"] = nat_recent["date"].dt.strftime("%Y-%m-%d")

    metro_latest_rows = []
    for (date, metro_name), grp in metro.groupby(level=["date", "metro"]):
        metro_latest_rows.append(
            {"date": date.strftime("%Y-%m-%d"), "metro": metro_name, **grp.iloc[0].to_dict()}
        )
    # Keep only the latest date per metro
    metro_df = pd.DataFrame(metro_latest_rows)
    if not metro_df.empty:
        latest_date = metro_df["date"].max()
        metro_latest = metro_df[metro_df["date"] == latest_date].to_dict("records")
    else:
        metro_latest = []

    as_of = national.index.max().strftime("%Y-%m-%d") if not national.empty else "unknown"
    return {
        "as_of": as_of,
        "national_monthly": nat_recent.to_dict("records"),
        "metro_latest": metro_latest,
        "metros_covered": len(metro.index.get_level_values("metro").unique()),
        "source": "Redfin Data Center (public S3)",
        "pit_lag_days": 30,
        "note": (
            "period_begin is the START of the reporting month. "
            "Apply >=30d publication lag before using as predictive signal."
        ),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run(force: bool = False) -> None:
    """Download and persist Redfin housing data. Skips if up-to-date."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    nat_path = OUT_DIR / "national.parquet"
    metro_path = OUT_DIR / "metro.parquet"

    # Check staleness — skip if last run was today (unless force)
    if not force and nat_path.exists():
        mtime = datetime.fromtimestamp(nat_path.stat().st_mtime, tz=timezone.utc)
        age_days = (datetime.now(timezone.utc) - mtime).days
        if age_days < 1:
            LOG.info("redfin_hf data is fresh (age=%dd); skipping", age_days)
            return

    # --- national ---
    nat_raw = _fetch_gz(NATIONAL_URL)
    national = _parse_national(nat_raw)
    LOG.info("National: %d months, %s to %s", len(national),
             national.index[0].date(), national.index[-1].date())
    print(f"[redfin_hf] National: {len(national)} months, "
          f"{national.index[0].date()} to {national.index[-1].date()}")

    # --- metro ---
    metro_raw = _fetch_gz(METRO_URL)
    metro = _parse_metro(metro_raw, TOP_20_METROS)
    n_metros = len(metro.index.get_level_values("metro").unique())
    LOG.info("Metro: %d metros, %d rows", n_metros, len(metro))
    print(f"[redfin_hf] Metro: {n_metros} metros, {len(metro)} rows")

    # --- warn on coverage gaps ---
    found_metros = set(metro.index.get_level_values("metro").unique())
    missing = [m for m in TOP_20_METROS if m not in found_metros]
    if missing:
        LOG.warning("Metros NOT found in Redfin data: %s", missing)
        print(f"[redfin_hf] WARNING: {len(missing)} target metros not matched: {missing}")

    # --- write ---
    national.to_parquet(nat_path)
    metro.to_parquet(metro_path)

    agg = _build_agg_json(national, metro)
    with open(OUT_DIR / "agg_json.json", "w") as fh:
        json.dump(agg, fh, indent=2, default=str)

    print(f"[redfin_hf] Written: {nat_path}, {metro_path}")
    print(f"[redfin_hf] as_of={agg['as_of']}, metros_covered={agg['metros_covered']}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Re-download even if fresh")
    args = parser.parse_args()
    run(force=args.force)
