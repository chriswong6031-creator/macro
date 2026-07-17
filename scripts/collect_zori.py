"""Zillow ZORI — Observed Rent Index monthly metro collector.

Fetches Zillow's ZORI (smoothed, all home types) from the Zillow Research
public data page and persists:
  data/zori/metro.parquet    — (date, metro) multi-indexed monthly rent index
  data/zori/national.parquet — date-indexed national (US) series
  data/zori/agg_json.json    — display-ready JSON for site wiring

ZORI methodology (from Zillow Research):
  - Smoothed, seasonally adjusted rent index for all home types
  - Repeat-rent methodology (controls for composition changes)
  - Published monthly with approximately a 1-month lag
  - Units: USD/month (observed market rent)
  - History: 2015-01 to present

Usage (standalone):
  python -m scripts.collect_zori [--force]

Nightly wiring (for consolidation):
  Add to scripts/collect.py after the Redfin block:
      from scripts.collect_zori import run as collect_zori
      collect_zori()

PIT assumptions:
  - Index date is the last day of the reference month (Zillow convention)
  - Lag: approximately 30-45 days; use prior-month data only in production
  - No look-ahead: callers must shift by 1 observation before using predictively
"""
from __future__ import annotations

import argparse
import io
import json
import logging
import sys
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT_DIR = DATA / "zori"

LOG = logging.getLogger(__name__)

# All-home-types smoothed ZORI (SFR + condo)
ZORI_URL = (
    "https://files.zillowstatic.com/research/public_csvs/zori/"
    "Metro_zori_uc_sfrcondomfr_sm_month.csv"
)

HEADERS = {"User-Agent": "Mozilla/5.0 zori-collector/1.0"}

# Top-20 metros — matched against Zillow's RegionName column
TOP_20_METRO_NAMES = [
    "New York, NY",
    "Los Angeles, CA",
    "Chicago, IL",
    "Dallas, TX",
    "Houston, TX",
    "Washington, DC",
    "Philadelphia, PA",
    "Miami, FL",
    "Atlanta, GA",
    "Phoenix, AZ",
    "Boston, MA",
    "San Francisco, CA",
    "Riverside, CA",
    "Seattle, WA",
    "Minneapolis, MN",
    "San Diego, CA",
    "Tampa, FL",
    "Denver, CO",
    "Portland, OR",
    "Las Vegas, NV",
]


# ---------------------------------------------------------------------------
# Download + parse
# ---------------------------------------------------------------------------


def _fetch_zori(url: str, timeout: int = 60) -> pd.DataFrame:
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} fetching {url}") from exc
    return pd.read_csv(io.BytesIO(raw))


def _wide_to_long(df: pd.DataFrame, metro_filter: list[str] | None = None) -> pd.DataFrame:
    """Melt the wide Zillow CSV (rows=metros, cols=dates) to long format."""
    id_cols = ["RegionID", "SizeRank", "RegionName", "RegionType", "StateName"]
    date_cols = [c for c in df.columns if c not in id_cols]

    if metro_filter:
        df = df[df["RegionName"].isin(metro_filter)].copy()

    melted = df.melt(id_vars=id_cols, value_vars=date_cols,
                     var_name="date_str", value_name="zori")
    melted["date"] = pd.to_datetime(melted["date_str"])
    melted = melted.dropna(subset=["zori"])
    melted = melted.sort_values(["RegionName", "date"])
    return melted[["date", "RegionName", "zori"]].rename(columns={"RegionName": "metro"})


def _extract_national(raw_df: pd.DataFrame) -> pd.DataFrame:
    """Extract the US national row (SizeRank=0 / RegionType='country')."""
    nat = raw_df[raw_df["RegionType"] == "country"].copy()
    if nat.empty:
        nat = raw_df[raw_df["SizeRank"] == 0].copy()
    if nat.empty:
        LOG.warning("No national row found in ZORI data")
        return pd.DataFrame()

    id_cols = ["RegionID", "SizeRank", "RegionName", "RegionType", "StateName"]
    date_cols = [c for c in raw_df.columns if c not in id_cols]
    melted = nat.melt(id_vars=id_cols, value_vars=date_cols,
                      var_name="date_str", value_name="zori")
    melted["date"] = pd.to_datetime(melted["date_str"])
    melted = melted.dropna(subset=["zori"]).sort_values("date")
    return melted.set_index("date")[["zori"]]


def _build_agg_json(national: pd.DataFrame, metro: pd.DataFrame) -> dict:
    nat_recent = national.tail(24).reset_index()
    nat_recent["date"] = nat_recent["date"].dt.strftime("%Y-%m-%d")

    metro_latest_rows = []
    for (date, metro_name), grp in metro.groupby(level=["date", "metro"]):
        metro_latest_rows.append({
            "date": date.strftime("%Y-%m-%d"),
            "metro": metro_name,
            "zori": round(float(grp["zori"].iloc[0]), 2),
        })
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
        "source": "Zillow Research — ZORI (smoothed, all home types)",
        "pit_lag_days": 30,
        "units": "USD/month",
        "note": (
            "Date is end-of-month (Zillow convention). "
            "Shift by 1 observation before using predictively."
        ),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _fetched_age_days(stamp_path: Path) -> int | None:
    """Days since the last fetch, from the sidecar _fetched.json stamp — NEVER
    file mtime (on CI runners a checkout rewrites files with mtime = checkout
    time, so a committed stale cache always looks freshly written and the
    re-download short-circuits; polygon-universe frozen-cache class, #2690).
    Missing/unreadable/stamp-less sidecar returns None (= stale)."""
    try:
        asof = json.loads(stamp_path.read_text()).get("asof")
        return (date.today() - date.fromisoformat(str(asof))).days
    except Exception:  # noqa: BLE001
        return None


def run(force: bool = False) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    nat_path = OUT_DIR / "national.parquet"
    metro_path = OUT_DIR / "metro.parquet"
    stamp_path = OUT_DIR / "_fetched.json"

    if not force and nat_path.exists():
        age_days = _fetched_age_days(stamp_path)
        if age_days is not None and age_days < 1:
            LOG.info("zori data is fresh (age=%dd); skipping", age_days)
            return

    raw_df = _fetch_zori(ZORI_URL)
    LOG.info("ZORI raw: %d rows x %d cols", *raw_df.shape)

    national = _extract_national(raw_df)
    print(f"[zori] National: {len(national)} months, "
          f"{national.index[0].date()} to {national.index[-1].date()}")

    metro_long = _wide_to_long(raw_df, metro_filter=TOP_20_METRO_NAMES)
    metro = metro_long.set_index(["date", "metro"]).sort_index()

    n_metros = len(metro.index.get_level_values("metro").unique())
    found = set(metro.index.get_level_values("metro").unique())
    missing = [m for m in TOP_20_METRO_NAMES if m not in found]
    if missing:
        LOG.warning("ZORI metros NOT found: %s", missing)
        print(f"[zori] WARNING: {len(missing)} metros not matched: {missing}")

    print(f"[zori] Metro: {n_metros} metros, {len(metro)} rows")

    national.to_parquet(nat_path)
    metro.to_parquet(metro_path)

    agg = _build_agg_json(national, metro)
    with open(OUT_DIR / "agg_json.json", "w") as fh:
        json.dump(agg, fh, indent=2, default=str)

    try:
        stamp_path.write_text(json.dumps({"asof": date.today().isoformat()}))
    except Exception as e:  # noqa: BLE001
        LOG.warning("zori: could not write fetch stamp: %s", e)

    print(f"[zori] Written: {nat_path}, {metro_path}")
    print(f"[zori] as_of={agg['as_of']}, metros_covered={n_metros}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    run(force=args.force)
