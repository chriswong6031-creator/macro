"""SEC Fails-to-Deliver (FTD) collector — production daily/incremental runner.

Source: SEC FTD data files at
  https://www.sec.gov/data-research/sec-markets-data/fails-deliver-data
Semi-monthly zips, pipe-delimited:
  SETTLEMENT DATE | CUSIP | SYMBOL | QUANTITY (FAILS) | DESCRIPTION | PRICE

PIT LAW (pre-registered):
  First-half-month file (settlement dates 1..15) is published ~30 days after
  period end.  Second-half file (16..EOM) is published ~15 days after period
  end.  We conservatively apply the SAME uniform 30-calendar-day lag to ALL
  rows regardless of half-month parity.  This means:
    availability_date = period_end + 30 calendar days
  where period_end = last settlement date in the file.
  A signal built on this store must not use any row where the observation date
  is before that row's availability_date.

Store: data/sec_ftd/panel.parquet
  Columns: date (Timestamp), symbol (str), cusip (str),
           ftd_shares (float), price (float), availability_date (Timestamp)

Nightly wiring (for consolidation):
  Add to nightly collect step:
    python -m collectors.sec_ftd --incremental
  This fetches only files whose availability_date has passed since the last
  known panel date and appends to data/sec_ftd/panel.parquet.
"""
from __future__ import annotations

import io
import logging
import re
import time
import zipfile
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

from lib import config

log = logging.getLogger(__name__)

# SEC FTD index page — we discover per-file URLs from here
SEC_INDEX_URL = "https://www.sec.gov/data-research/sec-markets-data/fails-deliver-data"

# File naming: cnsfails{YYYYMM}{a|b}.zip
# a = first half of month (settlement dates 1-15)
# b = second half of month (settlement dates 16-EOM)
# Multiple URL path prefixes are used by SEC (older files use a FOIA path):
#   /files/data/fails-deliver-data/             (2017+)
#   /files/data/frequently-requested-foia-document-fails-deliver-data/  (pre-2017)
# We discover the correct URL per file from the index page.

# Uniform PIT lag: 30 calendar days from period_end (conservative)
PIT_LAG_DAYS = 30

# Rate limit: <= 8 req/s per SEC fair-use policy
SLEEP_BETWEEN = 0.15  # 1/SLEEP_BETWEEN ≈ 6.7 req/s

GROUP = "sec_ftd"

# SEC requires a contact UA per their data-research fair-access policy
SEC_UA = "macro-dashboard research bot / educational use (contact: longr2512@gmail.com)"

# Cache the URL map across calls in one process
_URL_MAP_CACHE: dict[str, str] | None = None


def _panel_path() -> Path:
    return config.data_dir() / GROUP / "panel.parquet"


def _fetch_url_map(sess: requests.Session) -> dict[str, str]:
    """Discover the correct download URL for each FTD file from the SEC index page.

    The SEC uses multiple path prefixes (the older FOIA path for pre-2017 files)
    so we cannot hard-code a single URL template.  We scrape the index page once
    per process and cache the result.
    """
    global _URL_MAP_CACHE
    if _URL_MAP_CACHE is not None:
        return _URL_MAP_CACHE

    import re as _re
    r = sess.get(SEC_INDEX_URL, timeout=30)
    r.raise_for_status()
    hrefs = _re.findall(
        r'href="(/files/data/[^"]*cnsfails(\d{6})([ab])\.zip)"',
        r.text, _re.IGNORECASE)
    url_map = {}
    for path, ym, half in hrefs:
        key = ym + half.lower()
        url = "https://www.sec.gov" + path
        # If a key appears multiple times, keep the first (top of page = newest)
        url_map.setdefault(key, url)
    log.info("FTD index: discovered %d file URLs", len(url_map))
    _URL_MAP_CACHE = url_map
    return url_map


def _have_files() -> set[str]:
    """File keys (YYYYMM + a/b) already ingested into the panel."""
    p = _panel_path()
    if not p.exists():
        return set()
    try:
        meta = pd.read_parquet(p, columns=["_file_key"])
        return set(meta["_file_key"].dropna().unique())
    except Exception:
        return set()


def _file_key(yr: int, mo: int, half: str) -> str:
    """Canonical file key — e.g. '202606a'."""
    return f"{yr:04d}{mo:02d}{half}"


def _period_end(yr: int, mo: int, half: str) -> date:
    """Last settlement date in a file — approximate.
    For 'a' (first half): day 15 of the month.
    For 'b' (second half): last day of the month.
    """
    if half == "a":
        return date(yr, mo, 15)
    # last day of month
    if mo == 12:
        return date(yr + 1, 1, 1) - timedelta(days=1)
    return date(yr, mo + 1, 1) - timedelta(days=1)


def _availability_date(yr: int, mo: int, half: str) -> date:
    """First date this file's data is considered PIT-safe to use (period_end + 30d)."""
    return _period_end(yr, mo, half) + timedelta(days=PIT_LAG_DAYS)


def _all_file_specs(start_year: int = 2009, end_date: date | None = None) -> list[dict]:
    """All (year, month, half, key, avail_date) specs from start_year to today.

    Data begins 2009-07 on the SEC page (earlier files return 404).
    We do not generate specs whose availability_date is in the future (not yet published).
    """
    today = date.today()
    end_date = end_date or today
    specs = []
    for yr in range(start_year, end_date.year + 1):
        for mo in range(1, 13):
            for half in ("a", "b"):
                avail = _availability_date(yr, mo, half)
                if avail > today:
                    continue  # not yet published
                pe = _period_end(yr, mo, half)
                if pe > end_date:
                    continue
                # skip before actual data begins
                if yr == 2009 and mo < 7:
                    continue
                specs.append({
                    "yr": yr, "mo": mo, "half": half,
                    "key": _file_key(yr, mo, half),
                    "period_end": pe,
                    "avail_date": avail,
                })
    return specs


def _parse_zip(content: bytes, key: str, avail_date: date) -> pd.DataFrame:
    """Parse one FTD zip → DataFrame with columns:
    date, symbol, cusip, ftd_shares, price, availability_date, _file_key.
    """
    try:
        z = zipfile.ZipFile(io.BytesIO(content))
        txt_name = z.namelist()[0]
        txt = z.read(txt_name).decode("latin-1", errors="replace")
    except Exception as exc:
        log.warning("zip parse error for %s: %s", key, exc)
        return pd.DataFrame()

    rows = []
    for line in txt.splitlines():
        parts = line.split("|")
        if len(parts) < 6 or not parts[0].isdigit():
            continue
        try:
            rows.append({
                "date": pd.Timestamp(parts[0]),
                "cusip": parts[1].strip(),
                "symbol": parts[2].strip().upper(),
                "ftd_shares": float(parts[3]),
                "description": parts[4].strip(),
                "price": float(parts[5]) if parts[5].strip() else float("nan"),
            })
        except (ValueError, IndexError):
            continue

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["availability_date"] = pd.Timestamp(avail_date)
    df["_file_key"] = key
    # Drop the description column (not needed for the panel)
    df = df.drop(columns=["description"], errors="ignore")
    return df[["date", "symbol", "cusip", "ftd_shares", "price",
               "availability_date", "_file_key"]]


def _flush(path: Path, frames: list[pd.DataFrame]) -> None:
    """Append-dedup-sort existing panel with new frames."""
    if not frames:
        return
    fresh = pd.concat(frames, ignore_index=True)
    if path.exists():
        prev = pd.read_parquet(path)
        combined = pd.concat([prev, fresh], ignore_index=True)
    else:
        combined = fresh
    combined = (combined
                .drop_duplicates(subset=["date", "symbol", "cusip"], keep="last")
                .sort_values(["date", "symbol"])
                .reset_index(drop=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    combined.to_parquet(path, index=False)


def backfill(start_year: int = 2009, end_date: date | None = None,
             dry_run: bool = False, log_every: int = 50) -> dict:
    """Fetch all missing FTD files from start_year to end_date.

    Resumable: already-fetched file keys are skipped.
    Returns summary dict {fetched, skipped, errors, total_wanted}.
    """
    specs = _all_file_specs(start_year=start_year, end_date=end_date)
    have = _have_files()
    wanted = [s for s in specs if s["key"] not in have]

    log.info("FTD backfill: %d total specs, %d already fetched, %d to fetch",
             len(specs), len(specs) - len(wanted), len(wanted))

    if dry_run:
        log.info("DRY RUN — would fetch %d files", len(wanted))
        return {"fetched": 0, "skipped": 0, "errors": 0, "total_wanted": len(wanted)}

    sess = requests.Session()
    sess.headers["User-Agent"] = SEC_UA
    url_map = _fetch_url_map(sess)

    path = _panel_path()
    fetched = skipped = errors = 0
    new_frames: list[pd.DataFrame] = []

    for i, spec in enumerate(wanted):
        url = url_map.get(spec["key"])
        if not url:
            skipped += 1
            log.debug("no URL for %s — not listed on SEC index page", spec["key"])
            if i % log_every == 0 and i > 0:
                log.info("progress %d/%d: fetched=%d skipped=%d errors=%d",
                         i, len(wanted), fetched, skipped, errors)
            continue

        try:
            r = sess.get(url, timeout=40)
            if r.status_code == 404:
                skipped += 1
                time.sleep(SLEEP_BETWEEN)
                if i % log_every == 0:
                    log.info("progress %d/%d: fetched=%d skipped=%d errors=%d",
                             i, len(wanted), fetched, skipped, errors)
                continue
            r.raise_for_status()
        except Exception as exc:
            errors += 1
            log.warning("fetch %s failed: %s", spec["key"], exc)
            time.sleep(SLEEP_BETWEEN * 4)
            continue

        df = _parse_zip(r.content, spec["key"], spec["avail_date"])
        if df.empty:
            skipped += 1
        else:
            new_frames.append(df)
            fetched += 1

        # Checkpoint every 100 fetches
        if fetched > 0 and fetched % 100 == 0:
            _flush(path, new_frames)
            new_frames = []
            log.info("checkpoint: %d/%d fetched, %d skipped, %d errors",
                     fetched, len(wanted), skipped, errors)

        time.sleep(SLEEP_BETWEEN)
        if i % log_every == 0 and i > 0:
            log.info("progress %d/%d: fetched=%d skipped=%d errors=%d",
                     i, len(wanted), fetched, skipped, errors)

    # Final flush
    if new_frames:
        _flush(path, new_frames)

    log.info("backfill complete: fetched=%d skipped=%d errors=%d", fetched, skipped, errors)
    if path.exists():
        panel = pd.read_parquet(path, columns=["date", "symbol"])
        log.info("panel: %d rows, %d dates, %d symbols",
                 len(panel), panel["date"].nunique(), panel["symbol"].nunique())

    return {"fetched": fetched, "skipped": skipped, "errors": errors,
            "total_wanted": len(wanted)}


def incremental(lookback_files: int = 4) -> dict:
    """Fetch the most recent `lookback_files` file specs that are newly available
    (past their availability_date) but not yet in the panel.  Used for nightly
    collection — does not re-fetch the whole history.
    """
    specs = _all_file_specs()
    have = _have_files()
    # Most recent missing files
    missing = [s for s in specs if s["key"] not in have]
    to_fetch = missing[-lookback_files:] if missing else []

    if not to_fetch:
        log.info("incremental: nothing to fetch")
        return {"fetched": 0, "skipped": 0, "errors": 0}

    log.info("incremental: fetching %d missing files", len(to_fetch))
    sess = requests.Session()
    sess.headers["User-Agent"] = SEC_UA
    url_map = _fetch_url_map(sess)

    path = _panel_path()
    fetched = skipped = errors = 0
    new_frames: list[pd.DataFrame] = []

    for spec in to_fetch:
        url = url_map.get(spec["key"])
        if not url:
            skipped += 1
            log.debug("incremental: no URL for %s", spec["key"])
            continue

        try:
            r = sess.get(url, timeout=40)
            if r.status_code == 404:
                skipped += 1
                time.sleep(SLEEP_BETWEEN)
                continue
            r.raise_for_status()
        except Exception as exc:
            errors += 1
            log.warning("incremental fetch %s failed: %s", spec["key"], exc)
            time.sleep(SLEEP_BETWEEN * 4)
            continue

        df = _parse_zip(r.content, spec["key"], spec["avail_date"])
        if df.empty:
            skipped += 1
        else:
            new_frames.append(df)
            fetched += 1
        time.sleep(SLEEP_BETWEEN)

    if new_frames:
        _flush(path, new_frames)

    log.info("incremental complete: fetched=%d skipped=%d errors=%d",
             fetched, skipped, errors)
    return {"fetched": fetched, "skipped": skipped, "errors": errors}


def load_panel(data_dir: Path | None = None) -> pd.DataFrame:
    """Load the full FTD panel, returning an empty DataFrame if not yet built."""
    p = (_panel_path() if data_dir is None
         else data_dir / GROUP / "panel.parquet")
    if not p.exists():
        return pd.DataFrame()
    return pd.read_parquet(p)


def load_panel_pit(as_of: date, data_dir: Path | None = None) -> pd.DataFrame:
    """Load FTD panel restricted to rows whose availability_date <= as_of.

    This is the PIT-safe interface: the signal harness calls this so no
    future-published data leaks into the backtest.
    """
    panel = load_panel(data_dir=data_dir)
    if panel.empty:
        return panel
    avail = pd.to_datetime(panel["availability_date"]).dt.date
    return panel[avail <= as_of].copy()
