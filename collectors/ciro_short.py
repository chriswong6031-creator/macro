"""CIRO Consolidated Short Position Report (CSPR) — twice-monthly TSX short-position panel.

C5 phase-0 substrate (HK/Canada masterplan §4 C5, Slice G, 2026-07-03).

WHAT
----
The Canadian Investment Regulatory Organization (CIRO, formerly IIROC) publishes a
Consolidated Short Position Report (CSPR) twice per month: on the 15th and on the
last calendar day of each month.  Each report is an XLS file listing aggregate
short positions (shares) for every TSX (and TSXV/CSE) listed security.

DEPTH (VERIFIED 2026-07-03)
----------------------------
The masterplan assumed a 2012→ or 2017→ CSPR archive. Wayback Machine CDX query
on 2026-07-03 returned the FIRST archived URL at 2021-10-15. The live ciro.ca site
returns a Cloudflare challenge page to all non-browser requests. Wayback is the only
programmatic path. TRUE archive depth: 2021-10-15 → present (~114 semi-monthly
cross-sections at programme launch).  C5 phase-0 is rescoped from ~330 to ~114.

STORE (GIT-TRACKED, NOT R2)
----------------------------
  data/ciro_short/positions.parquet
    index: report_date (pd.Timestamp, twice-monthly)
    columns: symbol (str, no .TO suffix), exchange, name, short_shares (int64),
             net_change (int64)
  data/ciro_short/coverage.json
    {fetched_at, n_report_dates, earliest_date, latest_date,
     n_tsx_rows_total, n_new_dates, n_failed_dates}

Store decision: ~114 report-dates × ~2,500 TSX rows ≈ 285,000 rows total.
At ~50B/row that's <15MB, well inside the 20MB git-track threshold.  Not R2.

SYMBOL NORMALISATION
--------------------
TSX tickers in the CSPR use no .TO suffix.  Dual-class shares use a dash
(e.g. TECK-B), while our CA panel may use a dot (TECK.B).  `to_cspr()` strips
".TO" and converts remaining dots to dashes, giving ~91.3% panel coverage.

CADENCE / FRESHNESS
-------------------
Twice-monthly (15th + last day of month).  Publication lag ≈ T+2.
STALE_DAYS = 18 covers the longest gap between reports + publication lag.
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Iterator

import pandas as pd
import requests

from collectors.base import Adapter
from lib import config

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

# Wayback Machine CDX API — enumerate archived URLs matching a pattern
_WB_CDX_URL = "https://web.archive.org/cdx/search/cdx"
# Wayback replay endpoint — fetch a specific archived snapshot
_WB_REPLAY = "https://web.archive.org/web/{timestamp}/{original}"

# True archive depth confirmed by CDX query 2026-07-03
_EARLIEST_VERIFIED = date(2021, 10, 15)

# Stores
_STORE = Path(config.data_dir()) / "ciro_short" / "positions.parquet"
_COVERAGE = Path(config.data_dir()) / "ciro_short" / "coverage.json"

# Staleness threshold (18d covers longest gap + T+2 lag)
_STALE_DAYS = 18

# Only keep TSX exchange rows (exclude TSXV, CSE)
_KEEP_EXCHANGES = {"TSX"}


# ---------------------------------------------------------------------------
# Symbol normalisation helpers
# ---------------------------------------------------------------------------

def to_cspr(ticker: str) -> str:
    """Convert a panel ticker (e.g. 'TECK-B.TO', 'SU.TO') to a CSPR-format symbol.

    Rules: strip .TO suffix → convert remaining dots to dashes (dual-class).
    """
    s = ticker.upper()
    if s.endswith(".TO"):
        s = s[:-3]
    s = s.replace(".", "-")
    return s


def from_cspr(symbol: str) -> str:
    """Inverse normalisation for a CSPR symbol back to .TO ticker form (best-effort)."""
    return symbol.replace("-", ".") + ".TO"


# ---------------------------------------------------------------------------
# XLS parsing
# ---------------------------------------------------------------------------

def _parse_xls_bytes(raw: bytes, report_date: date) -> pd.DataFrame:
    """Parse a CIRO CSPR XLS file from raw bytes.

    Returns a DataFrame with columns:
      symbol, exchange, name, short_shares (int64), net_change (int64)

    Only TSX rows are retained (see _KEEP_EXCHANGES). Raises ValueError if the
    file cannot be parsed or no TSX rows found.
    """
    try:
        import xlrd
    except ImportError as e:
        raise RuntimeError("xlrd is required for CIRO XLS parsing: pip install xlrd") from e

    wb = xlrd.open_workbook(file_contents=raw)
    sheet = wb.sheet_by_index(0)

    # Scan header row — CSPR files have a variable number of header rows before
    # the data starts. The header usually contains "Security Symbol" or "Symbol".
    header_row = None
    col_symbol = col_exchange = col_name = col_shares = col_change = None

    for row_idx in range(min(20, sheet.nrows)):
        row = [str(sheet.cell_value(row_idx, c)).strip().lower()
               for c in range(sheet.ncols)]
        # Detect header by presence of 'symbol' or 'ticker' in a cell
        if any("symbol" in cell or "ticker" in cell for cell in row):
            header_row = row_idx
            for c_idx, cell in enumerate(row):
                if "symbol" in cell or "ticker" in cell:
                    col_symbol = col_symbol or c_idx
                if "exchange" in cell or "market" in cell:
                    col_exchange = col_exchange or c_idx
                if "name" in cell:
                    col_name = col_name or c_idx
                if "short" in cell and "position" in cell:
                    col_shares = col_shares or c_idx
                elif "position" in cell and col_shares is None:
                    col_shares = c_idx
                if "change" in cell or "net" in cell:
                    col_change = col_change or c_idx
            break

    if header_row is None:
        raise ValueError(f"CSPR XLS for {report_date}: no header row found")
    if col_symbol is None:
        raise ValueError(f"CSPR XLS for {report_date}: no symbol column found")

    rows: list[dict] = []
    for row_idx in range(header_row + 1, sheet.nrows):
        sym = str(sheet.cell_value(row_idx, col_symbol)).strip()
        if not sym or sym.lower() in ("", "security symbol", "symbol"):
            continue

        exc = ""
        if col_exchange is not None:
            exc = str(sheet.cell_value(row_idx, col_exchange)).strip().upper()

        # Only keep target exchanges
        if _KEEP_EXCHANGES and exc not in _KEEP_EXCHANGES:
            continue

        name = ""
        if col_name is not None:
            name = str(sheet.cell_value(row_idx, col_name)).strip()

        # Parse share count
        def _int_cell(c_idx: int | None) -> int:
            if c_idx is None:
                return 0
            v = sheet.cell_value(row_idx, c_idx)
            try:
                return int(float(v))
            except (TypeError, ValueError):
                return 0

        short_shares = _int_cell(col_shares)
        net_change = _int_cell(col_change)

        rows.append({
            "symbol": sym,
            "exchange": exc,
            "name": name,
            "short_shares": short_shares,
            "net_change": net_change,
        })

    if not rows:
        raise ValueError(f"CSPR XLS for {report_date}: no TSX rows found")

    df = pd.DataFrame(rows)
    df["short_shares"] = df["short_shares"].astype("int64")
    df["net_change"] = df["net_change"].astype("int64")
    df["report_date"] = pd.Timestamp(report_date)
    return df


# ---------------------------------------------------------------------------
# Report date generation
# ---------------------------------------------------------------------------

def _cspr_report_dates(start: date, end: date) -> Iterator[date]:
    """Yield twice-monthly CSPR report dates between start and end (inclusive).

    Dates: 15th and last calendar day of each month.
    """
    d = date(start.year, start.month, 1)
    while d <= end:
        # 15th
        d15 = date(d.year, d.month, 15)
        if start <= d15 <= end:
            yield d15
        # Last day of month
        if d.month == 12:
            last = date(d.year, 12, 31)
        else:
            last = date(d.year, d.month + 1, 1) - timedelta(days=1)
        if start <= last <= end:
            yield last
        # Advance to next month
        if d.month == 12:
            d = date(d.year + 1, 1, 1)
        else:
            d = date(d.year, d.month + 1, 1)


# ---------------------------------------------------------------------------
# Wayback Machine CDX discovery
# ---------------------------------------------------------------------------

def _wb_cdx_archived_dates(timeout: int = 30) -> list[tuple[str, str]]:
    """Query Wayback CDX API for all archived CSPR XLS files.

    Returns list of (timestamp, original_url) tuples, sorted by timestamp.
    Checks both the old iiroc.ca domain and the new ciro.ca domain.
    """
    results: list[tuple[str, str]] = []
    patterns = [
        "iiroc.ca/*CSPR*.xls",
        "ciro.ca/*CSPR*.xls",
        "ciro.ca/sites/default/files/epubs/CSPR/*.xls",
    ]
    seen_ts: set[str] = set()
    for pattern in patterns:
        try:
            r = requests.get(
                _WB_CDX_URL,
                params={
                    "url": pattern,
                    "output": "json",
                    "fl": "timestamp,original",
                    "filter": "statuscode:200",
                    "collapse": "timestamp:8",  # dedupe by date (YYYYMMDD)
                    "limit": "2000",
                },
                headers={"User-Agent": _BROWSER_UA},
                timeout=timeout,
            )
            r.raise_for_status()
            data = r.json()
            if not data or len(data) < 2:
                continue
            # data[0] is the header row ["timestamp", "original"]
            for row in data[1:]:
                ts, orig = str(row[0]), str(row[1])
                if ts not in seen_ts:
                    seen_ts.add(ts)
                    results.append((ts, orig))
            time.sleep(0.5)
        except Exception as e:  # noqa: BLE001
            log.warning("CDX query failed for pattern %s: %s", pattern, e)

    results.sort(key=lambda x: x[0])
    log.info("CDX found %d archived CSPR snapshots", len(results))
    return results


def _wb_replay_download(timestamp: str, original: str,
                         timeout: int = 30) -> bytes:
    """Download a file from the Wayback Machine replay endpoint."""
    url = _WB_REPLAY.format(timestamp=timestamp, original=original)
    r = requests.get(
        url,
        headers={"User-Agent": _BROWSER_UA},
        timeout=timeout,
        allow_redirects=True,
    )
    r.raise_for_status()
    return r.content


# ---------------------------------------------------------------------------
# Store helpers
# ---------------------------------------------------------------------------

def _load_store() -> pd.DataFrame:
    """Load existing positions store, or return an empty DataFrame."""
    if _STORE.exists():
        try:
            return pd.read_parquet(_STORE)
        except Exception as e:  # noqa: BLE001
            log.warning("ciro_short: store read failed (%s), starting fresh", e)
    return pd.DataFrame(columns=["report_date", "symbol", "exchange", "name",
                                  "short_shares", "net_change"])


def _save_store(df: pd.DataFrame) -> None:
    """Save the combined positions store."""
    _STORE.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(_STORE, index=False)


def _stored_report_dates(df: pd.DataFrame) -> set[date]:
    """Return the set of report dates already in the store."""
    if df.empty or "report_date" not in df.columns:
        return set()
    return set(pd.to_datetime(df["report_date"]).dt.date.unique())


def _write_coverage(
    n_report_dates: int,
    earliest_date: str,
    latest_date: str,
    n_tsx_rows_total: int,
    n_new_dates: int,
    n_failed_dates: int,
) -> None:
    _COVERAGE.parent.mkdir(parents=True, exist_ok=True)
    _COVERAGE.write_text(json.dumps({
        "fetched_at": pd.Timestamp.now().isoformat(),
        "n_report_dates": n_report_dates,
        "earliest_date": earliest_date,
        "latest_date": latest_date,
        "n_tsx_rows_total": n_tsx_rows_total,
        "n_new_dates": n_new_dates,
        "n_failed_dates": n_failed_dates,
    }, indent=2))


# ---------------------------------------------------------------------------
# Main fetch function
# ---------------------------------------------------------------------------

def fetch_ciro_short(full_history: bool = False) -> int:
    """Download and parse CIRO CSPR XLS files via the Wayback Machine.

    Args:
        full_history: If True, fetch all archived dates back to _EARLIEST_VERIFIED.
                      If False, only fetch dates not already in the store and within
                      the last 60 days (incremental top-up).

    Returns:
        Number of new report dates successfully parsed and stored.

    Raises:
        RuntimeError: If no new dates could be fetched AND the store is empty
                      (fail-closed: at least one report date must succeed on first run).
    """
    existing = _load_store()
    already_have = _stored_report_dates(existing)

    # Discover archived CSPR files via Wayback CDX
    cdx_entries = _wb_cdx_archived_dates()
    if not cdx_entries:
        if not already_have:
            raise RuntimeError("ciro_short: CDX returned no results and store is empty")
        log.warning("ciro_short: CDX returned no results; using existing store")
        return 0

    # Determine which report dates to attempt
    today = date.today()
    if full_history:
        cutoff = _EARLIEST_VERIFIED
    else:
        cutoff = today - timedelta(days=60)

    new_chunks: list[pd.DataFrame] = []
    n_new = 0
    n_failed = 0

    for ts, orig in cdx_entries:
        # Parse the date from the CDX timestamp (YYYYMMDD...)
        try:
            snap_date = date(int(ts[:4]), int(ts[4:6]), int(ts[6:8]))
        except (ValueError, IndexError):
            continue

        if snap_date < cutoff:
            continue

        # Infer report_date from the filename or snapshot date
        # CSPR filename is like 20231015_CSPR_Report.xls
        m = re.search(r'(\d{8})_CSPR', orig, re.IGNORECASE)
        if m:
            try:
                ds = m.group(1)
                report_date = date(int(ds[:4]), int(ds[4:6]), int(ds[6:8]))
            except ValueError:
                report_date = snap_date
        else:
            report_date = snap_date

        if report_date in already_have:
            continue

        try:
            raw = _wb_replay_download(ts, orig, timeout=30)
            df_chunk = _parse_xls_bytes(raw, report_date)
            new_chunks.append(df_chunk)
            already_have.add(report_date)
            n_new += 1
            log.info("ciro_short: fetched %s (%d TSX rows)", report_date, len(df_chunk))
            time.sleep(0.3)  # polite pacing for Wayback
        except Exception as e:  # noqa: BLE001
            n_failed += 1
            log.warning("ciro_short: failed %s (%s): %s", report_date, ts, e)

    if n_new == 0 and not already_have:
        raise RuntimeError(
            f"ciro_short: 0 new dates fetched and store is empty "
            f"({n_failed} failures). Check CDX results and Wayback access."
        )

    if new_chunks:
        combined = pd.concat([existing] + new_chunks, ignore_index=True)
        # Dedup on (report_date, symbol) — keep latest
        combined["_sort_key"] = pd.to_datetime(combined["report_date"])
        combined = (
            combined.sort_values("_sort_key")
            .drop_duplicates(subset=["report_date", "symbol"], keep="last")
            .drop(columns=["_sort_key"])
            .reset_index(drop=True)
        )
        _save_store(combined)
        log.info("ciro_short: stored %d new report dates; panel total %d rows",
                 n_new, len(combined))

        # Update coverage.json
        dates_in_store = sorted(
            pd.to_datetime(combined["report_date"]).dt.date.unique()
        )
        _write_coverage(
            n_report_dates=len(dates_in_store),
            earliest_date=str(dates_in_store[0]) if dates_in_store else "",
            latest_date=str(dates_in_store[-1]) if dates_in_store else "",
            n_tsx_rows_total=len(combined),
            n_new_dates=n_new,
            n_failed_dates=n_failed,
        )
    elif already_have:
        log.info("ciro_short: no new dates to fetch (store already current)")

    return n_new


# ---------------------------------------------------------------------------
# Read-only API for display/engine layer
# ---------------------------------------------------------------------------

def short_panel_for_symbol(symbol: str) -> pd.DataFrame:
    """Return the time-series of short positions for a single TSX symbol.

    Args:
        symbol: Either CSPR-format (no .TO suffix) or panel-format (with .TO).

    Returns:
        DataFrame indexed by report_date with columns [short_shares, net_change].
        Empty DataFrame if symbol not found or store absent.
    """
    cspr_sym = to_cspr(symbol)
    df = _load_store()
    if df.empty:
        return pd.DataFrame()
    mask = df["symbol"].str.upper() == cspr_sym.upper()
    sub = df[mask].copy()
    if sub.empty:
        return pd.DataFrame()
    sub["report_date"] = pd.to_datetime(sub["report_date"])
    return sub.set_index("report_date")[["short_shares", "net_change"]].sort_index()


def short_map(ca_panel_tickers: list[str]) -> dict[str, dict]:
    """Return a dict of {ticker: {latest_short_shares, net_change_latest, pct_change_4w}}
    for the given CA panel tickers, keyed by the panel ticker format (with .TO).

    This is the read-only display API for engine/canada_stocks.py or similar callers.
    Returns an empty dict if the store is absent.
    """
    df = _load_store()
    if df.empty:
        return {}

    df["report_date"] = pd.to_datetime(df["report_date"])
    # Build a reverse lookup: cspr_symbol → panel_ticker
    sym_to_ticker: dict[str, str] = {}
    cspr_to_symbol: dict[str, str] = {}
    for t in ca_panel_tickers:
        cspr = to_cspr(t)
        sym_to_ticker[cspr.upper()] = t
        cspr_to_symbol[cspr.upper()] = cspr

    out: dict[str, dict] = {}
    for cspr_sym, grp in df.groupby(df["symbol"].str.upper()):
        panel_ticker = sym_to_ticker.get(str(cspr_sym))
        if panel_ticker is None:
            continue
        grp_sorted = grp.sort_values("report_date")
        latest = grp_sorted.iloc[-1]
        prev_4w = grp_sorted[
            grp_sorted["report_date"] <= latest["report_date"] - pd.Timedelta(days=28)
        ]
        prev_row = prev_4w.iloc[-1] if not prev_4w.empty else None
        pct_change_4w = None
        if prev_row is not None and prev_row["short_shares"] > 0:
            pct_change_4w = round(
                (latest["short_shares"] - prev_row["short_shares"])
                / prev_row["short_shares"] * 100, 2
            )
        out[panel_ticker] = {
            "short_shares": int(latest["short_shares"]),
            "net_change": int(latest["net_change"]),
            "report_date": str(latest["report_date"].date()),
            "pct_change_4w": pct_change_4w,
        }
    return out


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------

class CiroShortAdapter(Adapter):
    """Plugs CIRO CSPR fetch into the collect.py pipeline.

    The adapter manages its own parquet store (data/ciro_short/) directly,
    similar to HkShortsPositionsAdapter.  It returns a summary DataFrame so
    run_adapter's staleness / status machinery still works.
    """

    name = "ciro_short"
    group = "canada_short"
    stale_after_days = _STALE_DAYS

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        n_new = fetch_ciro_short(full_history=full_history)

        # Load store to report latest date and row count
        df = _load_store()
        if df.empty:
            # Should not happen (fetch raises if store is empty after a failed run)
            return {"positions__summary": pd.DataFrame(
                {"n_new": [0]}, index=[pd.Timestamp.now().normalize()]
            )}

        df["report_date"] = pd.to_datetime(df["report_date"])
        latest_ts = df["report_date"].max()

        summary = pd.DataFrame(
            {"n_new_dates": [n_new], "n_rows_total": [len(df)]},
            index=[latest_ts],
        )
        return {"positions__summary": summary}


# ---------------------------------------------------------------------------
# CLI / manual run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    import logging as _logging

    _logging.basicConfig(level=_logging.INFO, format="%(levelname)s %(name)s %(message)s")

    parser = argparse.ArgumentParser(description="CIRO CSPR short-position collector")
    parser.add_argument("--full-history", action="store_true",
                        help=f"Backfill from {_EARLIEST_VERIFIED} (Wayback CDX verified depth)")
    parser.add_argument("--dry-cdx", action="store_true",
                        help="Just list Wayback CDX results, don't download")
    args = parser.parse_args()

    if args.dry_cdx:
        entries = _wb_cdx_archived_dates()
        for ts, orig in entries:
            print(ts, orig)
        print(f"\nTotal: {len(entries)} archived CSPR snapshots")
    else:
        n = fetch_ciro_short(full_history=args.full_history)
        print(f"Done: {n} new report dates fetched")
        if _COVERAGE.exists():
            cov = json.loads(_COVERAGE.read_text())
            print(f"Coverage: {cov.get('n_report_dates')} report dates, "
                  f"earliest={cov.get('earliest_date')}, "
                  f"latest={cov.get('latest_date')}, "
                  f"n_tsx_rows={cov.get('n_tsx_rows_total')}")
