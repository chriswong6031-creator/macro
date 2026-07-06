"""NY Fed Primary Dealer Statistics collector — weekly, 1998-01-28 to present.

Pulls net outright Treasury positions, Treasury settlement fails (to-deliver +
to-receive) via the NY Fed Markets Data API (markets.newyorkfed.org/api/pd/...).

SCHEMA ERAS — the survey structure changed four times; each era's keyids differ.
We store era tags alongside the values and build z-scores WITHIN each era (rolling
3y / 156-week windows) to avoid cross-era level splices.

Era map (from /api/pd/list/asof.json):
  SBP2001 : 1998-01-28 → 2001-06-27  (original structure, 79 series)
  SBP2013 : 2001-07-04 → 2013-03-27  (expanded, 140 series)
  SBN2013 : 2013-04-03 → 2014-12-31  (2013 revision, ~350 series)
  SBN2015 : 2015-01-07 → 2021-12-31  (2015 revision, ~650 series)
  SBN2022 : 2022-01-05 → 2024-06-28  (2022 revision)
  SBN2024 : 2024-07-03 → present     (2024 revision, 1099 series)

Series pulled per era (all in $millions unless noted):

Net Treasury coupon position (outright long − short):
  SBP2001/SBP2013 : PDPUSGCS5L* + PDPUSGCS5M* = coupon net (<=5y + 5y+)
  SBN2013+       : PDPOSGST-TOT = total US Treasury securities net position

Treasury settlement fails (financing book):
  SBP2001/SBP2013 : PDFASUFDA (fails to deliver), PDFASUFRA (fails to receive)
  SBN2013+       : PDFTD-USTET (fails to deliver), PDFTR-USTET (fails to receive)

Output: data/nyfed_pd/pd_weekly.parquet
  Columns: date, era, net_tsy_pos, fails_to_deliver, fails_to_receive, total_fails
  Plus: net_pos_z, total_fails_z  (rolling 3y / 156w z-scores, era-safe)
  Plus: total_fails_chg4w          (4-week change in total_fails, raw)
  Plus: total_fails_chg4w_z        (z-score of that 4-week change, era-safe)

Publication lag: NY Fed releases data THURSDAYS ~16:15 ET for the PRIOR Wednesday.
Signal users must apply a 1-week lag before using in any forward study.

Run:
  .venv/bin/python -m collectors.nyfed_primary_dealer [--backfill] [--start YYYY-MM-DD]
Writes data/nyfed_pd/pd_weekly.parquet.
"""
from __future__ import annotations

import argparse
import json
import logging
import time
import urllib.request
from pathlib import Path

import pandas as pd
import numpy as np

log = logging.getLogger(__name__)

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) macro-dashboard/research"
BASE_URL = "https://markets.newyorkfed.org/api/pd"

# Era definitions: (seriesbreak_tag, start_date, end_date)
ERAS = [
    ("SBP2001", "1998-01-28", "2001-06-27"),
    ("SBP2013", "2001-07-04", "2013-03-27"),
    ("SBN2013", "2013-04-03", "2014-12-31"),
    ("SBN2015", "2015-01-07", "2021-12-31"),
    ("SBN2022", "2022-01-05", "2024-06-28"),
    ("SBN2024", "2024-07-03", "2099-12-31"),
]

# Rolling window for intra-era z-scores (weeks)
Z_WINDOW = 156  # ~3 years

# -------------------------------- extraction helpers --------------------------

def _http_get(url: str, retries: int = 4, timeout: int = 40) -> bytes:
    last: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as exc:
            last = exc
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"HTTP fetch failed after {retries} tries for {url}: {last}")


def fetch_asof_dates() -> list[dict]:
    """Return all available (asof, seriesbreak) date records from the NY Fed API."""
    data = json.loads(_http_get(f"{BASE_URL}/list/asof.json"))
    return data["pd"]["asofdates"]


def fetch_one_date(asof: str) -> dict:
    """Fetch all timeseries for a single as-of date. Returns {keyid: value_or_nan}."""
    url = f"{BASE_URL}/get/asof/{asof}.json"
    data = json.loads(_http_get(url))
    out = {}
    for ts in data.get("pd", {}).get("timeseries", []):
        kid = ts.get("keyid", "")
        val = ts.get("value", "")
        try:
            out[kid] = float(val)
        except (ValueError, TypeError):
            out[kid] = float("nan")
    return out


# -------------------------------- series selection per era --------------------

def _era_tag(seriesbreak: str) -> str:
    """Map seriesbreak → simplified era label."""
    era_map = {
        "SBP2001": "SBP2001",
        "SBP2013": "SBP2013",
        "SBN2013": "SBN2013",
        "SBN2015": "SBN2015",
        "SBN2022": "SBN2022",
        "SBN2024": "SBN2024",
    }
    return era_map.get(seriesbreak, seriesbreak)


def _extract_row(asof: str, seriesbreak: str, series_data: dict) -> dict:
    """
    Extract the three target measurements from a single-date data blob.

    Era-routing logic (see module docstring for the series mapping):
      - SBP2001 / SBP2013: pre-2013 structure uses PDPUSG* and PDFASUF* keyids
      - SBN2013+: modern structure uses PDPOSGST-TOT and PDFTD/PDFTR-USTET

    The net position is (long outright positions) − (short outright positions).
    In the early eras these are split by maturity bucket; we sum across buckets.

    'N/A', missing, and '*' values all become NaN.
    """
    era = _era_tag(seriesbreak)
    row: dict = {"date": pd.Timestamp(asof), "era": era}

    def v(key: str) -> float:
        return series_data.get(key, float("nan"))

    if era in ("SBP2001", "SBP2013"):
        # Net coupon position = sum of (net-outright = net-open) for coupon buckets
        # NOP = net outright positions across maturity buckets
        # Keys: PDPUSGCS5LNOP (<=5yr), PDPUSGCS5MNOP (>5yr)
        # Also: PDPUSGCS36NOP (3-6yr), PDPUSGCS3LNOP (>3yr) in SBP2013 era
        # Use the most reliable total: sum all NOP keys we find
        nop_keys_v1 = ["PDPUSGCS5LNOP", "PDPUSGCS5MNOP"]
        nop_keys_v2 = ["PDPUSGCS36NOP", "PDPUSGCS3LNOP"]
        parts_v1 = [v(k) for k in nop_keys_v1]
        parts_v2 = [v(k) for k in nop_keys_v2]
        # Prefer v1 keys (present in both sub-eras), fall back to v2
        parts = parts_v1 if not all(np.isnan(parts_v1)) else parts_v2
        valid = [p for p in parts if not np.isnan(p)]
        net_pos = float(np.sum(valid)) if valid else float("nan")

        # Bills: PDPUSGTBNOP
        bills = v("PDPUSGTBNOP")
        if not np.isnan(bills) and not np.isnan(net_pos):
            net_pos += bills
        elif np.isnan(net_pos) and not np.isnan(bills):
            net_pos = bills

        # Fails: PDFASUFDA (UST fail-to-deliver), PDFASUFRA (UST fail-to-receive)
        ftd = v("PDFASUFDA")
        ftr = v("PDFASUFRA")

    else:
        # Modern eras (SBN2013+): use aggregated series
        # PDPOSGST-TOT = total UST (excl TIPS) dealer net position
        net_pos = v("PDPOSGST-TOT")
        # PDFTD-USTET = UST fails to deliver; PDFTR-USTET = UST fails to receive
        ftd = v("PDFTD-USTET")
        ftr = v("PDFTR-USTET")

    row["net_tsy_pos"] = net_pos
    row["fails_to_deliver"] = ftd
    row["fails_to_receive"] = ftr
    row["total_fails"] = (
        float(np.nansum([ftd, ftr]))
        if not (np.isnan(ftd) and np.isnan(ftr))
        else float("nan")
    )
    return row


# -------------------------------- z-score computation ------------------------

def _era_zscore(s: pd.Series, era: pd.Series, window: int = Z_WINDOW) -> pd.Series:
    """
    Rolling z-score computed WITHIN each era only.

    For each row, the rolling mean/std uses only the rows up to that point
    within the SAME era. This prevents cross-era level splices from contaminating
    the z (e.g., the 2013 schema revision changed the position reporting scope).

    Minimum 4 weeks of data required within the era window before z is non-NaN.
    """
    out = pd.Series(float("nan"), index=s.index)
    for era_tag in era.unique():
        mask = era == era_tag
        sub = s[mask].sort_index()
        roll_mean = sub.rolling(window, min_periods=4).mean()
        roll_std = sub.rolling(window, min_periods=4).std(ddof=1)
        z = (sub - roll_mean) / roll_std.replace(0, float("nan"))
        out[mask] = z.values
    return out


# -------------------------------- main backfill/update -----------------------

def load_existing(path: Path) -> pd.DataFrame:
    if path.exists():
        df = pd.read_parquet(path)
        df["date"] = pd.to_datetime(df["date"])
        return df
    return pd.DataFrame()


def save(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    log.info("Saved %d rows → %s", len(df), path)


def build_zscores(df: pd.DataFrame) -> pd.DataFrame:
    """Add era-safe rolling z-scores and 4-week change z to the panel."""
    df = df.sort_values("date").copy()
    df["net_pos_z"] = _era_zscore(df["net_tsy_pos"], df["era"])
    df["total_fails_z"] = _era_zscore(df["total_fails"], df["era"])
    # 4-week change in total_fails, then z within era
    df["total_fails_chg4w"] = df.groupby("era")["total_fails"].transform(
        lambda s: s.sort_index().diff(4)
    )
    df["total_fails_chg4w_z"] = _era_zscore(df["total_fails_chg4w"], df["era"])
    return df


def run(data_dir: Path, start: str | None = None, throttle_s: float = 0.3) -> pd.DataFrame:
    """Full backfill (or incremental update) → returns the final panel DataFrame."""
    out_path = data_dir / "pd_weekly.parquet"
    existing = load_existing(out_path)
    existing_dates: set[str] = set()
    if not existing.empty:
        existing_dates = set(existing["date"].dt.strftime("%Y-%m-%d"))
        log.info("Existing rows: %d (last: %s)", len(existing), existing["date"].max())

    # Get all available as-of dates from NY Fed
    log.info("Fetching as-of date list from NY Fed…")
    all_asof = fetch_asof_dates()
    log.info("NY Fed reports %d total as-of dates (1998→present)", len(all_asof))

    # Filter to Wednesday-only Treasury position/fails releases.
    # The /api/pd/list/asof.json returns 1941 as-of dates but only 1483 are the
    # Wednesday Treasury-position/fails release (PDPOSGST-TOT, PDFTD-USTET, etc.).
    # The other ~458 are Thursday/Monday/Tuesday/Friday dates for DIFFERENT surveys
    # (PDCBFHLMC-* agency/mortgage series and others) — they contain none of our
    # target series and produce empty rows that corrupt the z-score rolling windows.
    wed_asof = [a for a in all_asof
                if pd.Timestamp(a["asof"]).day_of_week == 2]  # 2 = Wednesday
    log.info("Wednesday-only Treasury releases: %d", len(wed_asof))

    # Filter to requested start and exclude already-stored dates
    if start:
        wed_asof = [a for a in wed_asof if a["asof"] >= start]
    to_fetch = [a for a in wed_asof if a["asof"] not in existing_dates]
    log.info("Dates to fetch: %d", len(to_fetch))

    new_rows = []
    for i, rec in enumerate(to_fetch):
        asof = rec["asof"]
        sb = rec["seriesbreak"]
        try:
            series_data = fetch_one_date(asof)
            row = _extract_row(asof, sb, series_data)
            new_rows.append(row)
        except Exception as exc:
            log.warning("SKIP %s (%s): %s", asof, sb, exc)
        if (i + 1) % 50 == 0:
            log.info("  fetched %d / %d dates…", i + 1, len(to_fetch))
        time.sleep(throttle_s)

    if new_rows:
        new_df = pd.DataFrame(new_rows)
        combined = pd.concat([existing, new_df], ignore_index=True)
    else:
        combined = existing.copy()

    if combined.empty:
        log.warning("No data collected — returning empty frame")
        return combined

    combined = combined.drop_duplicates(subset=["date"]).sort_values("date").reset_index(drop=True)
    # Drop any non-Wednesday rows that may exist in previously-stored data
    # (the /api/pd/list/asof.json includes non-Wednesday dates for other surveys)
    combined = combined[pd.to_datetime(combined["date"]).dt.day_of_week == 2].reset_index(drop=True)
    combined = build_zscores(combined)
    save(combined, out_path)
    return combined


# -------------------------------- CLI ----------------------------------------

def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    p = argparse.ArgumentParser(description="NY Fed Primary Dealer Statistics collector")
    p.add_argument("--backfill", action="store_true",
                   help="Re-fetch all dates even if already stored")
    p.add_argument("--start", default=None,
                   help="Earliest date to fetch (YYYY-MM-DD), default=1998-01-28")
    p.add_argument("--data-dir", default=None,
                   help="Override data directory (default: repo data/nyfed_pd)")
    args = p.parse_args()

    root = Path(__file__).resolve().parent.parent
    data_dir = Path(args.data_dir) if args.data_dir else root / "data" / "nyfed_pd"

    if args.backfill and (data_dir / "pd_weekly.parquet").exists():
        (data_dir / "pd_weekly.parquet").unlink()
        log.info("Cleared existing store (--backfill)")

    df = run(data_dir, start=args.start)
    print(f"\nDone. {len(df)} weekly rows, {df['date'].min().date()} → {df['date'].max().date()}")
    print(df[["date", "era", "net_tsy_pos", "total_fails", "net_pos_z",
              "total_fails_z"]].tail(5).to_string(index=False))


if __name__ == "__main__":
    main()
