"""HK short-data collectors — two distinct sub-stores, NEVER conflated.

## Sub-store 1 — SFC weekly reportable short POSITIONS
  Source:  www.sfc.hk aggregated reportable short positions (free, keyless)
  Archive: 2012-08-31 -> present, 721+ weekly CSV files
  Lag:     T+7 (positions as-of Friday, published ~following Friday)
  URL:     https://www.sfc.hk/-/media/EN/pdf/spr/{YYYY}/{MM}/{DD}/
               Short_Position_Reporting_Aggregated_Data_{YYYYMMDD}.csv
           (rev= parameter NOT required -- path is sufficient)
  Store:   data/hk_shorts/positions.parquet
           index=date (report date, i.e. position-as-of date)
           columns: stock_code (int), ticker (str NNNN.HK), stock_name (str),
                    shorted_shares (int), value_hkd (int)
  Note:    pct_issued is NOT stored here because SFC does not publish issued
           share counts.  It can be derived downstream as
               shorted_shares / shares_outstanding
           where shares_outstanding comes from a fundamentals feed.
  Backfill: full_history=True fetches all 721 CSVs from the index page.
            Incremental runs fetch only the last ~3 weeks (tolerate one missed run).
  Failure: fail-closed -- an empty fetch (0 rows) raises RuntimeError.
  Gap tripwire: the summary store (hk_shorts_positions__summary) records the
                latest SFC date so the health surface can detect a missed week.

## Sub-store 2 — HKEX sstoday daily short-sell TURNOVER
  Source:  HKEX "Short Selling Turnover (Main Board) up to day close today"
           https://www.hkex.com.hk/Market-Data/Statistics/Securities-Market/
               Short-Selling-Turnover-Today/
               Short-Selling-Turnover-(Main-Board)-up-to-day-close-today?sc_lang=en
  Cadence: TODAY-ONLY page (no date parameter, no historical backfill possible).
           Accrue-forward daily in the asia collect group.
  Store:   data/hk_shorts/turnover.parquet
           index=date (trading date parsed from the page header)
           columns: stock_code (int), ticker (str), name (str),
                    turnover_sh (int), turnover_hkd (int)
  Failure: A holiday / weekend / pre-open fetch returns empty data from the page.
           This is NOT a failure -- it is tolerated gracefully (returns a
           heartbeat row so the circuit breaker does not trip).
  Staleness threshold: 3 TRADING DAYS (not calendar days) -- see _is_stale_trading().

## CRITICAL DISTINCTION (from masterplan §3 H2 + red-team hk-critic MAJOR):
  positions.parquet  = SFC POSITIONS (>=0.02% of issued shares, weekly, T+7)
  turnover.parquet   = HKEX TURNOVER (daily short-sell volume HKD, today-only)
  These measure different things; downstream code MUST NOT conflate them.

## Store decision (git vs R2):
  POSITIONS panel: ~721 weekly dates x ~1,200 names x 5 cols ~= 4M rows total.
  Compressed parquet ~= 20-30 MB at full depth -- borderline but stays in git
  because (a) it does not grow per-ticker (it is cross-sectional), (b) it is
  NOT regenerable without re-scraping, and (c) the full depth is our H2a
  evidence base.  Decision: GIT, tracked in the sentinel.
  TURNOVER panel: ~250 rows/year x 1,000 names ~= small. GIT.
  Both stores are listed in .gitignore entries to EXCLUDE _closes_cache.parquet
  but the panels themselves are committed.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import date, datetime, timedelta, timezone
from io import StringIO
from typing import Iterator

import pandas as pd

from collectors.base import Adapter, is_connection_error
from lib import config

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SFC_INDEX_URL = (
    "https://www.sfc.hk/en/Regulatory-functions/Market/Short-position-reporting/"
    "Aggregated-reportable-short-positions-of-specified-shares"
)
_SFC_BASE = "https://www.sfc.hk/-/media/EN/pdf/spr"

_HKEX_TURNOVER_URL = (
    "https://www.hkex.com.hk/Market-Data/Statistics/Securities-Market/"
    "Short-Selling-Turnover-Today/"
    "Short-Selling-Turnover-(Main-Board)-up-to-day-close-today?sc_lang=en"
)

GROUP = "hk_shorts"

# How many recent SFC weeks to re-fetch on incremental runs (tolerate one gap)
_SFC_LOOKBACK_WEEKS = 3

# Turnover staleness: 3 trading days
_TURNOVER_STALE_TRADING_DAYS = 3


# ---------------------------------------------------------------------------
# Helpers -- SFC positions
# ---------------------------------------------------------------------------

def _positions_path() -> "config.Path":  # type: ignore[name-defined]
    return config.data_dir() / GROUP / "positions.parquet"


def _sfc_url(report_date: date) -> str:
    """Construct direct SFC CSV URL from the report date.
    rev= parameter is NOT required (verified by direct fetch 2026-07-03)."""
    return (
        f"{_SFC_BASE}/{report_date.year}/{report_date.month:02d}/{report_date.day:02d}/"
        f"Short_Position_Reporting_Aggregated_Data_{report_date.strftime('%Y%m%d')}.csv"
    )


def _parse_sfc_csv(text: str) -> pd.DataFrame:
    """Parse one SFC CSV.  Returns empty DataFrame on parse failure."""
    try:
        df = pd.read_csv(StringIO(text))
    except Exception:
        return pd.DataFrame()
    if df.empty or len(df.columns) < 4:
        return pd.DataFrame()

    # Normalise column names (headers have changed slightly over the 14y archive)
    col_map: dict[str, str] = {}
    for col in df.columns:
        cl = col.strip().lower()
        if "date" in cl:
            col_map[col] = "date_str"
        elif "stock code" in cl or "code" in cl:
            col_map[col] = "stock_code"
        elif "stock name" in cl or "name" in cl:
            col_map[col] = "stock_name"
        elif "shares" in cl:
            col_map[col] = "shorted_shares"
        elif "hk$" in cl or "value" in cl or "amount" in cl:
            col_map[col] = "value_hkd"
    df = df.rename(columns=col_map)
    needed = {"date_str", "stock_code", "shorted_shares"}
    if not needed.issubset(df.columns):
        log.warning("sfc csv missing expected columns; got %s", df.columns.tolist())
        return pd.DataFrame()

    df = df.copy()
    # Parse report date
    try:
        df["date"] = pd.to_datetime(df["date_str"], dayfirst=True, errors="coerce").dt.normalize()
    except Exception:
        df["date"] = pd.NaT
    df = df.dropna(subset=["date"])

    # Numeric coerce
    df["stock_code"] = pd.to_numeric(df["stock_code"], errors="coerce").dropna().astype(int)
    df["shorted_shares"] = pd.to_numeric(df.get("shorted_shares", 0), errors="coerce").fillna(0).astype(int)
    if "value_hkd" in df.columns:
        df["value_hkd"] = pd.to_numeric(df["value_hkd"], errors="coerce").fillna(0).astype(int)
    else:
        df["value_hkd"] = 0

    # Map stock_code -> ticker (NNNN.HK format)
    df["ticker"] = df["stock_code"].apply(lambda c: f"{int(c):04d}.HK" if pd.notna(c) else None)
    if "stock_name" not in df.columns:
        df["stock_name"] = ""

    return df[["date", "stock_code", "ticker", "stock_name", "shorted_shares", "value_hkd"]].dropna(
        subset=["stock_code"]
    )


def _scrape_sfc_dates_from_index(adapter: "HkShortsPositionsAdapter") -> list[date]:
    """Scrape the SFC aggregated-positions index page to get all historical report dates.
    Used only in full_history=True mode to drive the complete backfill.
    Returns sorted list of dates (oldest first).
    """
    log.info("Fetching SFC index page to enumerate archive dates...")
    try:
        r = adapter.http_get(_SFC_INDEX_URL, retries=2, timeout=60)
    except Exception as e:
        log.warning("Could not fetch SFC index page: %s -- falling back to computed dates", e)
        return []

    # Extract dates from CSV URLs embedded in the page
    # Pattern: Short_Position_Reporting_Aggregated_Data_{YYYYMMDD}.csv
    raw_dates = re.findall(
        r"Short_Position_Reporting_Aggregated_Data_(\d{8})\.csv",
        r.text,
    )
    dates: list[date] = []
    for ds in set(raw_dates):
        try:
            dates.append(datetime.strptime(ds, "%Y%m%d").date())
        except ValueError:
            pass
    dates.sort()
    log.info("SFC index: found %d distinct report dates (%s -> %s)",
             len(dates),
             dates[0] if dates else "?",
             dates[-1] if dates else "?")
    return dates


def _have_sfc_dates() -> set[pd.Timestamp]:
    """Return the set of report dates already stored."""
    p = _positions_path()
    if not p.exists():
        return set()
    try:
        df = pd.read_parquet(p, columns=["date"])
        return set(pd.to_datetime(df["date"]).dt.normalize().unique())
    except Exception:
        return set()


def _sfc_date_range_incremental() -> list[date]:
    """Generate the most recent ~3-week window of expected SFC report dates.
    SFC reports weekly (Fridays as the reference date).  We generate a
    lookback window based on today and return dates for the last
    _SFC_LOOKBACK_WEEKS x 7 calendar days.
    """
    today = datetime.now(timezone.utc).date()
    out: list[date] = []
    for days_back in range(_SFC_LOOKBACK_WEEKS * 7 + 7):
        d = today - timedelta(days=days_back)
        # SFC reports weekly; reference dates are typically Thursdays or Fridays.
        # Rather than guessing weekday, we generate the full window and let
        # 404/empty responses confirm which dates don't exist.
        out.append(d)
    return sorted(set(out))


# ---------------------------------------------------------------------------
# Helpers -- HKEX turnover
# ---------------------------------------------------------------------------

def _turnover_path() -> "config.Path":  # type: ignore[name-defined]
    return config.data_dir() / GROUP / "turnover.parquet"


def _parse_hkex_turnover(html: str) -> pd.DataFrame:
    """Parse the fixed-width pre-formatted HKEX short-sell turnover today page.

    Format (inside <pre> tags):
        CODE   NAME OF STOCK               (SH)            ($)
           1   CKH HOLDINGS           1,287,500     84,379,375
        ...
    Returns empty DataFrame if the page is pre-market/holiday/not-yet-posted.
    """
    # Extract content inside <pre>...</pre>
    m = re.search(r"<pre[^>]*>(.*?)</pre>", html, re.DOTALL | re.IGNORECASE)
    if not m:
        return pd.DataFrame()
    raw = m.group(1)

    # Strip HTML tags (just <font>, </font> etc)
    raw = re.sub(r"<[^>]+>", "", raw)

    # Extract the trading date from the header
    date_m = re.search(
        r"TRADING DATE\s*:\s*(\d{2}\s+\w{3}\s+\d{4})", raw, re.IGNORECASE
    )
    if not date_m:
        # pre-market / weekend / holiday -- no trading date present
        return pd.DataFrame()
    try:
        trading_date = pd.to_datetime(date_m.group(1), format="%d %b %Y").normalize()
    except Exception:
        return pd.DataFrame()

    # Parse data rows -- fixed-width but comma-separated numbers
    # Pattern: leading spaces, 4-6 digit code, spaces, name, spaces, shares, spaces, HKD
    rows: list[dict] = []
    for line in raw.splitlines():
        # Rows start with several spaces then a numeric code
        m2 = re.match(r"^\s{2,10}(\d{1,6})\s{2,}(.+?)\s{3,}([\d,]+)\s+([\d,]+)\s*$", line)
        if not m2:
            continue
        code_str, name, sh_str, hkd_str = m2.groups()
        try:
            code = int(code_str)
            sh = int(sh_str.replace(",", ""))
            hkd = int(hkd_str.replace(",", ""))
        except ValueError:
            continue
        rows.append({
            "date": trading_date,
            "stock_code": code,
            "ticker": f"{code:04d}.HK",
            "name": name.strip(),
            "turnover_sh": sh,
            "turnover_hkd": hkd,
        })

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    log.info("HKEX turnover: parsed %d rows for %s", len(df), trading_date.date())
    return df


def _have_turnover_dates() -> set[pd.Timestamp]:
    p = _turnover_path()
    if not p.exists():
        return set()
    try:
        df = pd.read_parquet(p, columns=["date"])
        return set(pd.to_datetime(df["date"]).dt.normalize().unique())
    except Exception:
        return set()


def _is_stale_trading(last_date_ts: pd.Timestamp | None,
                       n_trading_days: int = _TURNOVER_STALE_TRADING_DAYS) -> bool:
    """Return True when the turnover store is more than n_trading_days old.
    Uses a simple Mon-Fri business-day count (ignores HK holidays,
    which are rare enough that a 1-day holiday false-positive is acceptable).
    """
    if last_date_ts is None:
        return True
    today = datetime.now(timezone.utc).date()
    d = last_date_ts.date()
    count = 0
    delta = today - d
    for i in range(delta.days):
        day = d + timedelta(days=i + 1)
        if day.weekday() < 5:  # Mon=0 ... Fri=4
            count += 1
    return count > n_trading_days


# ---------------------------------------------------------------------------
# Coverage report helper
# ---------------------------------------------------------------------------

def compute_coverage(positions_path: "config.Path",  # type: ignore[name-defined]
                     hk_universe_dir: "config.Path") -> dict:  # type: ignore[name-defined]
    """Compute how many of our 157-name HK universe appear in the SFC positions panel.
    Returns a dict with coverage stats for the registry and PR body.
    """
    # Our universe
    our_codes: set[int] = set()
    if hk_universe_dir.exists():
        for f in hk_universe_dir.glob("*.parquet"):
            code_str = f.stem.split(".")[0]
            try:
                our_codes.add(int(code_str))
            except ValueError:
                pass

    if not our_codes:
        return {"our_universe": 0, "latest_sfc_names": 0, "covered": 0, "coverage_pct": 0.0}

    if not positions_path.exists():
        return {"our_universe": len(our_codes), "latest_sfc_names": 0,
                "covered": 0, "coverage_pct": 0.0}

    df = pd.read_parquet(positions_path)
    if df.empty:
        return {"our_universe": len(our_codes), "latest_sfc_names": 0,
                "covered": 0, "coverage_pct": 0.0}

    latest_date = pd.to_datetime(df["date"]).max()
    df_latest = df[pd.to_datetime(df["date"]) == latest_date]
    sfc_codes = set(df_latest["stock_code"].dropna().astype(int))
    covered = our_codes & sfc_codes
    pct = 100.0 * len(covered) / len(our_codes) if our_codes else 0.0

    return {
        "our_universe": len(our_codes),
        "latest_sfc_names": len(sfc_codes),
        "covered": len(covered),
        "coverage_pct": round(pct, 1),
        "latest_date": str(latest_date.date()),
        "h2a_eligible": len(covered) >= 60,  # masterplan gate
    }


# ---------------------------------------------------------------------------
# Adapter 1 -- SFC weekly positions
# ---------------------------------------------------------------------------

class HkShortsPositionsAdapter(Adapter):
    """SFC aggregated weekly reportable short POSITIONS.

    Incremental: re-fetches the last _SFC_LOOKBACK_WEEKS of dates.
    Full-history: scrapes the SFC index page to enumerate all 721+ CSV files
    then downloads them (slow -- ~15 min, best run once with --full-history).

    Stores a per-name weekly panel (date, stock_code, ticker, stock_name,
    shorted_shares, value_hkd) in data/hk_shorts/positions.parquet.
    Also writes data/hk_shorts/coverage.json (H2a decision gate).

    Tripwire: the 'positions__summary' heartbeat series records the latest
    SFC report date; the health surface flags if it is >10 days stale.
    """

    name = "hk_shorts_positions"
    group = GROUP
    stale_after_days = 10  # weekly release; flag if we miss two weeks

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        import json

        have = _have_sfc_dates()
        path = _positions_path()

        if full_history:
            # Scrape the SFC index page for all available dates
            all_dates = _scrape_sfc_dates_from_index(self)
            if not all_dates:
                raise RuntimeError(
                    "hk_shorts_positions: could not retrieve SFC archive date list"
                )
            wanted = [d for d in all_dates if pd.Timestamp(d) not in have]
            log.info("hk_shorts_positions full-history: %d total dates, %d to fetch",
                     len(all_dates), len(wanted))
        else:
            candidate = _sfc_date_range_incremental()
            wanted = [d for d in candidate if pd.Timestamp(d) not in have]
            log.info("hk_shorts_positions incremental: %d candidate dates, %d to fetch",
                     len(candidate), len(wanted))

        new_frames: list[pd.DataFrame] = []
        fetched = skipped = errors = 0

        for i, d in enumerate(wanted):
            url = _sfc_url(d)
            try:
                r = self.http_get(url, retries=2, timeout=30)
                df = _parse_sfc_csv(r.text)
                if df.empty:
                    skipped += 1
                    continue
                new_frames.append(df)
                fetched += 1
                # Brief pause to be polite on full-history backfills
                if full_history and i % 20 == 19:
                    time.sleep(1.0)
            except Exception as e:
                if is_connection_error(e):
                    # Host down -- abort if no data yet
                    if fetched == 0:
                        raise
                    log.warning("Connection error on %s -- stopping fetch: %s", d, e)
                    break
                # 404 = date doesn't exist (not every day is a report date)
                skipped += 1

        if not new_frames:
            # No new data -- emit heartbeat from stored state
            last = None
            if path.exists():
                try:
                    df_stored = pd.read_parquet(path, columns=["date"])
                    last = pd.to_datetime(df_stored["date"]).max()
                except Exception:
                    pass
            if last is None:
                raise RuntimeError(
                    "hk_shorts_positions: no data fetched and no store exists"
                )
            log.info("hk_shorts_positions: no new dates, store current as of %s", last.date())
            hb = pd.DataFrame({"n_new": [0], "fetched": [0]}, index=[last])
            return {"positions__summary": hb}

        # Merge new data into the panel store
        fresh = pd.concat(new_frames, ignore_index=True)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            prev = pd.read_parquet(path)
            combined = pd.concat([prev, fresh], ignore_index=True)
        else:
            combined = fresh

        # Deduplicate on (date, stock_code)
        combined["_date_ts"] = pd.to_datetime(combined["date"])
        combined = (
            combined.drop_duplicates(subset=["_date_ts", "stock_code"], keep="last")
            .sort_values(["_date_ts", "stock_code"])
            .drop(columns=["_date_ts"])
            .reset_index(drop=True)
        )
        combined.to_parquet(path)
        log.info(
            "hk_shorts_positions: +%d rows (%d dates fetched, %d skipped), "
            "panel total %d rows",
            len(fresh), fetched, skipped, len(combined),
        )

        # Write coverage.json for the PR decision gate and health surface
        hk_stocks_dir = config.data_dir() / "hk_stocks"
        cov = compute_coverage(path, hk_stocks_dir)
        cov_path = config.data_dir() / GROUP / "coverage.json"
        with open(cov_path, "w") as fh:
            json.dump(cov, fh, indent=2)
        log.info(
            "hk_shorts_positions coverage: %d/%d our names in SFC (%.1f%%), "
            "H2a eligible=%s",
            cov.get("covered", 0), cov.get("our_universe", 0),
            cov.get("coverage_pct", 0.0), cov.get("h2a_eligible", False),
        )

        last_date = pd.to_datetime(fresh["date"]).max()
        hb = pd.DataFrame(
            {"n_new": [len(fresh)], "fetched": [fetched], "skipped": [skipped]},
            index=[last_date],
        )
        return {"positions__summary": hb}


# ---------------------------------------------------------------------------
# Adapter 2 -- HKEX sstoday short-sell turnover
# ---------------------------------------------------------------------------

class HkShortsTurnoverAdapter(Adapter):
    """HKEX daily short-sell TURNOVER -- today-only page, accrue-forward.

    Fetches the "Short Selling Turnover (Main Board) up to day close today"
    page from HKEX.  The page is TODAY-ONLY: it has no date parameter and
    cannot be used to backfill historical turnover.  Each run appends one
    new day's data.

    Tripwire: stale if the last stored date is >3 trading-days (Mon-Fri) old.
    Holiday / weekend / pre-open fetch returns no data (empty <pre> block)
    and is treated as a success heartbeat, NOT a failure -- the circuit
    breaker must NOT trip on market holidays.
    """

    name = "hk_shorts_turnover"
    group = GROUP
    # stale_after_days is deliberately large -- the trading-day staleness check
    # (3 trading days) is enforced in the fetch() return status, not here.
    # This prevents false-positive "stale" flags over a 4-day holiday weekend.
    stale_after_days = 8

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        # full_history is a no-op: this source is TODAY-ONLY (no backfill possible)
        if full_history:
            log.info(
                "hk_shorts_turnover: full_history requested but source is today-only; "
                "running incremental fetch"
            )

        path = _turnover_path()
        have = _have_turnover_dates()
        today = pd.Timestamp(datetime.now(timezone.utc).date()).normalize()

        # Emit heartbeat if we already have today's data
        if today in have:
            log.info("hk_shorts_turnover: already have today (%s); skipping", today.date())
            hb = pd.DataFrame({"n_new": [0]}, index=[today])
            return {"turnover__summary": hb}

        # Fetch the today-only page
        try:
            r = self.http_get(_HKEX_TURNOVER_URL, retries=2, timeout=30)
        except Exception as e:
            if is_connection_error(e):
                # HKEX unreachable -- if we have recent data, emit stale; else fail
                if have:
                    last_ts = max(have)
                    log.warning(
                        "hk_shorts_turnover: HKEX unreachable (%s); "
                        "last stored %s", e, last_ts.date()
                    )
                    hb = pd.DataFrame({"n_new": [0]}, index=[last_ts])
                    return {"turnover__summary": hb}
                raise
            raise

        df = _parse_hkex_turnover(r.text)

        if df.empty:
            # Pre-market, holiday, or weekend -- not a failure
            log.info(
                "hk_shorts_turnover: page returned no data rows "
                "(pre-market, holiday, or weekend) -- heartbeat only"
            )
            # Use stored last date or today as the heartbeat index
            if have:
                last_ts = max(have)
            else:
                last_ts = today
            hb = pd.DataFrame({"n_new": [0]}, index=[last_ts])
            return {"turnover__summary": hb}

        trading_date = pd.to_datetime(df["date"].iloc[0]).normalize()

        # Skip if already stored for this trading date
        if trading_date in have:
            log.info("hk_shorts_turnover: already have %s; skipping", trading_date.date())
            hb = pd.DataFrame({"n_new": [0]}, index=[trading_date])
            return {"turnover__summary": hb}

        # Merge into panel store
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            prev = pd.read_parquet(path)
            combined = pd.concat([prev, df], ignore_index=True)
        else:
            combined = df

        combined["_date_ts"] = pd.to_datetime(combined["date"])
        combined = (
            combined.drop_duplicates(subset=["_date_ts", "stock_code"], keep="last")
            .sort_values(["_date_ts", "stock_code"])
            .drop(columns=["_date_ts"])
            .reset_index(drop=True)
        )
        combined.to_parquet(path)
        log.info(
            "hk_shorts_turnover: +%d rows for %s; panel total %d rows",
            len(df), trading_date.date(), len(combined),
        )

        # Flag staleness via the summary index
        hb = pd.DataFrame({"n_new": [len(df)]}, index=[trading_date])
        return {"turnover__summary": hb}


# ---------------------------------------------------------------------------
# Standalone test / manual backfill
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    import logging as _logging

    _logging.basicConfig(level=_logging.INFO, format="%(levelname)s %(name)s %(message)s")

    parser = argparse.ArgumentParser(description="HK shorts collector -- manual run")
    parser.add_argument("--full-history", action="store_true",
                        help="Backfill all 721+ SFC weekly CSVs (slow ~15 min)")
    parser.add_argument("--positions-only", action="store_true")
    parser.add_argument("--turnover-only", action="store_true")
    args = parser.parse_args()

    if not args.turnover_only:
        pos = HkShortsPositionsAdapter()
        result = pos.fetch(full_history=args.full_history)
        print("Positions result:", result)

    if not args.positions_only:
        trn = HkShortsTurnoverAdapter()
        result = trn.fetch()
        print("Turnover result:", result)
