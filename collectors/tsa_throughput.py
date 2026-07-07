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
  - 2019-baseline % uses same weekday nearest match within ±3 days, EXCLUDING
    US federal holidays from BOTH sides of the comparison. Holidays produce
    anomalously low counts that are not representative of normal travel demand,
    and a weekday-matched holiday-vs-non-holiday comparison produces spurious
    recovery figures (e.g. matching a normal Thursday to Independence Day 2019
    produces a +39% artifact that reads as demand recovery when it is purely
    a day-type mismatch). Both the target date and the 2019 candidate date are
    checked against a self-contained US federal holiday set. Holiday-to-holiday
    matches (e.g. Jul 4 to Jul 4) are also excluded; the result is NaN for
    those dates, which is the honest representation.
  - YoY % uses same calendar date ±0 days; if missing, ±1 day fallback.
    Holiday dates are NOT excluded from YoY (both sides are the same calendar
    date, so the comparison is self-consistent day-type vs day-type).

Pre-registered amendment A3 (holiday exclusion): _vs2019_pct excludes US
  federal holidays from both the target and candidate sets. A3 is not a new
  gate; it is a correction to the display field to prevent materially misleading
  chart-ready numbers on holiday-adjacent dates. The NaN output for holiday
  dates is the correct honest representation for conditions desk display.

Nightly wiring (for consolidation):
  IMPORTANT — self-storing adapter (non-standard pattern):
  TsaThroughputAdapter.fetch() calls store.upsert() internally and returns
  the already-stored frames.  This deviates from the standard Adapter contract
  where fetch() returns raw frames and the runner (fetch_with_breaker) stores
  them.  Do NOT wire this adapter through the standard runner path — doing so
  would double-store and bypass the runner's validate/quarantine/circuit-breaker
  logic.  Instead, call fetch() directly from a dedicated nightly step:

      from collectors.tsa_throughput import TsaThroughputAdapter
      TsaThroughputAdapter().fetch()           # incremental (current year only)
      TsaThroughputAdapter().fetch(full_history=True)  # backfill all years

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

from collectors.base import Adapter
from lib import store

log = logging.getLogger(__name__)

BASE_URL = "https://www.tsa.gov/travel/passenger-volumes"
HISTORY_START_YEAR = 2019
GROUP = "tsa"
SERIES = "throughput"


# ---------------------------------------------------------------------------
# US Federal Holiday helpers (self-contained, no external package)
# ---------------------------------------------------------------------------

def _nth_weekday(year: int, month: int, n: int, weekday: int) -> date:
    """Return the date of the n-th occurrence (1-based) of weekday in year/month.

    weekday follows Python convention: 0=Monday, 6=Sunday.
    """
    d = date(year, month, 1)
    # Advance to first occurrence of weekday in the month
    days_until = (weekday - d.weekday()) % 7
    d = d.replace(day=1 + days_until)
    return d.replace(day=d.day + (n - 1) * 7)


def _last_weekday(year: int, month: int, weekday: int) -> date:
    """Return the last occurrence of weekday in year/month."""
    import calendar
    from datetime import timedelta
    last_day = calendar.monthrange(year, month)[1]
    last = date(year, month, last_day)
    days_back = (last.weekday() - weekday) % 7
    return last - timedelta(days=days_back)


def _observed_holiday(d: date) -> date:
    """Return the observed date for a holiday falling on weekend.

    Saturday -> Friday; Sunday -> Monday.
    Uses timedelta to correctly handle month/year boundaries.
    """
    from datetime import timedelta
    if d.weekday() == 5:  # Saturday -> Friday
        return d - timedelta(days=1)
    if d.weekday() == 6:  # Sunday -> Monday
        return d + timedelta(days=1)
    return d


def us_federal_holidays(year: int) -> frozenset[date]:
    """Return a frozenset of US federal holiday dates for the given year.

    Includes both the actual holiday date and the observed date when a holiday
    falls on a weekend (per OPM rules: Saturday→Friday, Sunday→Monday).

    Covers all 11 federal holidays:
    New Year's Day, MLK Day, Presidents Day, Memorial Day, Juneteenth,
    Independence Day, Labor Day, Columbus Day, Veterans Day,
    Thanksgiving, Christmas Day.
    """
    import calendar as _cal

    holidays: set[date] = set()

    def _add(d: date) -> None:
        holidays.add(d)
        obs = _observed_holiday(d)
        if obs != d:
            holidays.add(obs)

    # Fixed-date holidays
    _add(date(year, 1, 1))   # New Year's Day
    _add(date(year, 6, 19))  # Juneteenth (federal since 2021; include all years for symmetry)
    _add(date(year, 7, 4))   # Independence Day
    _add(date(year, 11, 11)) # Veterans Day
    _add(date(year, 12, 25)) # Christmas Day

    # Floating holidays
    _add(_nth_weekday(year, 1, 3, 0))   # MLK Day: 3rd Monday of January
    _add(_nth_weekday(year, 2, 3, 0))   # Presidents Day: 3rd Monday of February
    _add(_last_weekday(year, 5, 0))     # Memorial Day: last Monday of May
    _add(_nth_weekday(year, 9, 1, 0))   # Labor Day: 1st Monday of September
    _add(_nth_weekday(year, 10, 2, 0))  # Columbus Day: 2nd Monday of October
    _add(_nth_weekday(year, 11, 4, 3))  # Thanksgiving: 4th Thursday of November

    return frozenset(holidays)


# Cache holiday sets for years we query frequently
_HOLIDAY_CACHE: dict[int, frozenset[date]] = {}


def _is_us_federal_holiday(d: "pd.Timestamp | date") -> bool:
    """Return True if d is a US federal holiday or its observed substitute."""
    if isinstance(d, pd.Timestamp):
        d = d.date()
    year = d.year
    if year not in _HOLIDAY_CACHE:
        _HOLIDAY_CACHE[year] = us_federal_holidays(year)
    return d in _HOLIDAY_CACHE[year]


# ---------------------------------------------------------------------------
# HTML parser
# ---------------------------------------------------------------------------

class _TableParser(HTMLParser):
    """Extract the FIRST <table> from TSA passenger-volumes pages.

    Only rows from the first table are captured.  Once the first </table>
    close tag is seen, _done is set and all subsequent tags are ignored.
    This prevents rows from footer/navigation/disclaimer tables on the real
    tsa.gov page from contaminating the data table.  The data table is the
    first (and historically only) table on the passenger-volumes pages; its
    header row contains 'Date' and 'Numbers'.
    """

    def __init__(self) -> None:
        super().__init__()
        self._in_table = False
        self._done = False  # set True after first </table>
        self._in_cell = False
        self._rows: list[list[str]] = []
        self._cur: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if self._done:
            return
        if tag == "table" and not self._in_table:
            self._in_table = True
        if self._in_table and tag in ("td", "th"):
            self._in_cell = True
        if self._in_table and tag == "tr":
            self._cur = []

    def handle_endtag(self, tag: str) -> None:
        if self._done:
            return
        if tag in ("td", "th"):
            self._in_cell = False
        if tag == "tr" and self._in_table and self._cur:
            self._rows.append(self._cur[:])
            self._cur = []
        if tag == "table" and self._in_table:
            self._in_table = False
            self._done = True  # stop processing after first table closes

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
    """% vs nearest same-weekday 2019 date (within ±3 days), holiday-excluded.

    Amendment A3 (pre-registered): US federal holidays are excluded from BOTH
    the target date and the 2019 candidate set. A holiday-vs-non-holiday match
    (or vice versa) produces a spurious recovery figure that is purely a
    day-type artifact (e.g. matching a normal Thursday to Independence Day 2019
    yielded +38.9% vs2019). Holiday dates return NaN — the correct honest
    representation for conditions desk display. Holiday-to-holiday matches
    (e.g. Jul 4 to Jul 4) are also excluded since both sides are anomalously
    low and the ratio is not representative of demand recovery.
    """
    baseline = s[s.index.year == 2019]
    result = pd.Series(index=s.index, dtype=float)
    if baseline.empty:
        return result

    # Build a non-holiday 2019 baseline index for candidate search
    non_holiday_2019 = frozenset(
        ts for ts in baseline.index if not _is_us_federal_holiday(ts)
    )

    for dt in s.index:
        if dt.year == 2019:
            continue
        # Skip target dates that are themselves US federal holidays
        if _is_us_federal_holiday(dt):
            continue
        target_weekday = dt.dayofweek
        # approximate same position in 2019; leap-day (Feb 29) maps to Feb 28
        try:
            approx_2019 = dt.replace(year=2019)
        except ValueError:
            approx_2019 = dt.replace(year=2019, day=28)
        # search ±3 days for matching weekday, excluding 2019 holidays
        best = None
        best_delta = 999
        for delta in range(-3, 4):
            candidate = approx_2019 + pd.Timedelta(days=delta)
            if (
                candidate in baseline.index
                and candidate in non_holiday_2019
                and candidate.dayofweek == target_weekday
            ):
                if abs(delta) < best_delta:
                    best_delta = abs(delta)
                    best = candidate
        if best is None:
            # No weekday match among non-holidays; fall back to nearest
            # non-holiday date in 2019 within ±7 days regardless of weekday
            non_holiday_candidates = [
                ts for ts in baseline.index
                if ts in non_holiday_2019
            ]
            if non_holiday_candidates:
                nh_index = pd.DatetimeIndex(non_holiday_candidates)
                diffs = abs((nh_index - approx_2019).days)
                nearest_idx = diffs.argmin()
                if diffs[nearest_idx] <= 7:
                    best = nh_index[nearest_idx]
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
                # Use self.http_get for retries/backoff and config-sponsored UA
                r = self.http_get(url, timeout=30)
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
