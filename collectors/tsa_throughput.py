"""TSA Throughput Collector — Lane A9 (wave-2, data product only).

Scrapes daily national checkpoint passenger counts from tsa.gov.
Source: https://www.tsa.gov/travel/passenger-volumes (current year)
        https://www.tsa.gov/travel/passenger-volumes/{year} (archives 2019-2024)

Free, no API key required, public government data published daily.
History available 2019-01-01 onward.

Store written: data/tsa/throughput.parquet
  columns: passengers (int64), avg7d (float64), yoy_pct (float64), vs2019_pct (float64)
  index:    date (DatetimeIndex, daily)

PIT assumptions:
  - TSA publishes the prior calendar day's count each morning ET.
  - 7d average and YoY/2019 comparisons are computed in-process from the
    same parquet; no look-ahead (they reference only rows <= current row date).
  - 2019-baseline % uses same weekday nearest match within ±3 days to reduce
    day-of-week noise (holiday bunching in either year still distorts; noted).
  - YoY % uses same calendar date ±0 days; if missing, ±1 day fallback.

Nightly wiring (for consolidation):
  Add to scripts/collect.py import block:
      from collectors.tsa_throughput import TsaThroughputAdapter
  Add to the adapter registry list:
      TsaThroughputAdapter(),
  The adapter self-gates on last stored date; incremental runs fetch only
  the current-year page (< 1 second). Full-history flag fetches all year pages.
  No config keys required; no credentials; no rate-limit headers observed.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime
from html.parser import HTMLParser

import pandas as pd
import requests

from collectors.base import Adapter
from lib import store

log = logging.getLogger(__name__)

BASE_URL = "https://www.tsa.gov/travel/passenger-volumes"
HISTORY_START_YEAR = 2019
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; MacroDashboard/1.0; "
        "+https://mastermind-x.com)"
    )
}
GROUP = "tsa"
SERIES = "throughput"


# ---------------------------------------------------------------------------
# HTML parser
# ---------------------------------------------------------------------------

class _TableParser(HTMLParser):
    """Extract the first <table> from TSA passenger-volumes pages."""

    def __init__(self) -> None:
        super().__init__()
        self._in_table = False
        self._in_cell = False
        self._rows: list[list[str]] = []
        self._cur: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag == "table":
            self._in_table = True
        if self._in_table and tag in ("td", "th"):
            self._in_cell = True
        if self._in_table and tag == "tr":
            self._cur = []

    def handle_endtag(self, tag: str) -> None:
        if tag in ("td", "th"):
            self._in_cell = False
        if tag == "tr" and self._in_table and self._cur:
            self._rows.append(self._cur[:])
            self._cur = []
        if tag == "table":
            self._in_table = False

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._cur.append(data.strip())

    @property
    def rows(self) -> list[list[str]]:
        return self._rows


def parse_tsa_html(html: str) -> pd.DataFrame:
    """Parse TSA passenger-volumes HTML page into a date-indexed DataFrame.

    Returns DataFrame with columns [passengers] indexed by date.
    Raises ValueError if no parseable data rows found.

    Pre-registered amendment A1: rows where the 'Numbers' cell contains only
    non-numeric characters (e.g. blank or placeholder) are silently dropped
    rather than coercing to NaN — blank rows appear on TSA pages for dates
    not yet published.
    """
    parser = _TableParser()
    parser.feed(html)
    rows = parser.rows

    records: list[dict] = []
    for row in rows:
        if len(row) < 2:
            continue
        date_str, num_str = row[0], row[1]
        # Skip header row
        if date_str.lower() in ("date", ""):
            continue
        # Strip commas and parse integer (amendment A1: skip non-numeric)
        clean = re.sub(r"[,\s]", "", num_str)
        if not clean.isdigit():
            continue
        try:
            dt = datetime.strptime(date_str.strip(), "%m/%d/%Y").date()
        except ValueError:
            log.debug("Skipping unparseable date: %r", date_str)
            continue
        records.append({"date": dt, "passengers": int(clean)})

    if not records:
        raise ValueError("No parseable rows found in TSA HTML")

    df = pd.DataFrame(records)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    df = df[~df.index.duplicated(keep="last")]
    return df


# ---------------------------------------------------------------------------
# Derived display fields
# ---------------------------------------------------------------------------

def compute_display_fields(df: pd.DataFrame) -> pd.DataFrame:
    """Add 7d avg, same-weekday YoY %, and 2019-baseline % columns.

    All computations are PIT: each row only references rows <= its own date.
    This function is safe to call on the full historical parquet (no future
    look-ahead) because pandas rolling and shift operate on sorted index.
    """
    df = df.copy().sort_index()

    # 7-day rolling average (trailing, min 1 day)
    df["avg7d"] = df["passengers"].rolling(7, min_periods=1).mean()

    # YoY: same calendar date one year prior; fallback to ±1 day
    df["yoy_pct"] = _yoy_pct(df["passengers"])

    # 2019 baseline: same weekday ±3 days in 2019
    df["vs2019_pct"] = _vs2019_pct(df["passengers"])

    return df


def _yoy_pct(s: pd.Series) -> pd.Series:
    """Year-over-year % change vs same calendar date prior year."""
    result = pd.Series(index=s.index, dtype=float)
    idx_set = set(s.index)
    for dt in s.index:
        prior_year = dt - pd.DateOffset(years=1)
        # Try exact date first, then ±1 day
        ref = None
        for delta in (0, 1, -1):
            candidate = prior_year + pd.Timedelta(days=delta)
            if candidate in idx_set:
                ref = candidate
                break
        if ref is not None and s[ref] > 0:
            result[dt] = (s[dt] / s[ref] - 1) * 100
    return result


def _vs2019_pct(s: pd.Series) -> pd.Series:
    """% vs nearest same-weekday 2019 date (within ±3 days)."""
    baseline = s[s.index.year == 2019]
    result = pd.Series(index=s.index, dtype=float)
    if baseline.empty:
        return result
    for dt in s.index:
        if dt.year == 2019:
            continue
        target_weekday = dt.dayofweek
        # approximate same position in 2019; leap-day (Feb 29) maps to Feb 28
        try:
            approx_2019 = dt.replace(year=2019)
        except ValueError:
            approx_2019 = dt.replace(year=2019, day=28)
        # search ±3 days for matching weekday
        best = None
        best_delta = 999
        for delta in range(-3, 4):
            candidate = approx_2019 + pd.Timedelta(days=delta)
            if candidate in baseline.index and candidate.dayofweek == target_weekday:
                if abs(delta) < best_delta:
                    best_delta = abs(delta)
                    best = candidate
        if best is None:
            # No weekday match; fall back to nearest date in 2019 regardless of weekday
            diffs = abs((baseline.index - approx_2019).days)
            nearest_idx = diffs.argmin()
            if diffs[nearest_idx] <= 7:
                best = baseline.index[nearest_idx]
        if best is not None and baseline[best] > 0:
            result[dt] = (s[dt] / baseline[best] - 1) * 100
    return result


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------

class TsaThroughputAdapter(Adapter):
    """TSA daily checkpoint passenger throughput, 2019-present.

    Incremental by default: fetches only the current-year page unless
    full_history=True, which fetches all archive pages (2019..current year).
    """

    name = "tsa_throughput"
    group = GROUP
    stale_after_days = 2  # TSA publishes daily; 2-day tolerance for weekends

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        current_year = date.today().year
        last = store.last_date(self.group, SERIES)

        if full_history or last is None:
            years = list(range(HISTORY_START_YEAR, current_year + 1))
            log.info("tsa_throughput: full history backfill, years=%s", years)
        else:
            # Incremental: only need current year page
            years = [current_year]
            log.info("tsa_throughput: incremental, last=%s", last)

        frames: list[pd.DataFrame] = []
        for year in years:
            url = BASE_URL if year == current_year else f"{BASE_URL}/{year}"
            try:
                r = requests.get(url, headers=HEADERS, timeout=30)
                r.raise_for_status()
                df = parse_tsa_html(r.text)
                log.info("tsa_throughput: fetched year=%d rows=%d", year, len(df))
                frames.append(df)
            except Exception as exc:
                log.warning("tsa_throughput: year=%d failed: %s", year, exc)
                if not frames and year == years[-1]:
                    raise

        if not frames:
            raise RuntimeError("tsa_throughput: no data fetched from any year")

        raw = pd.concat(frames).sort_index()
        raw = raw[~raw.index.duplicated(keep="last")]

        # Upsert raw passengers first, then recompute display fields over full history
        store.upsert(self.group, SERIES, raw[["passengers"]])
        full = store.read(self.group, SERIES)
        if full is None or full.empty:
            full = raw[["passengers"]]

        enhanced = compute_display_fields(full)
        store.upsert(self.group, SERIES, enhanced)

        log.info(
            "tsa_throughput: stored rows=%d, date range %s to %s",
            len(enhanced),
            enhanced.index.min().date(),
            enhanced.index.max().date(),
        )
        return {SERIES: enhanced}
