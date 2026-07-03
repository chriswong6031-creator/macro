"""CIRO Consolidated Short Position Report (CSPR) — twice-monthly TSX short-position panel.

C5 phase-0 substrate (HK/Canada masterplan §4 C5, Slice G, 2026-07-03).

WHAT
----
The Canadian Investment Regulatory Organization (CIRO, formerly IIROC) publishes a
Consolidated Short Position Report (CSPR) twice per month: on the 15th and on the
last calendar day of each month.  Each report is an XLS file listing aggregate
short positions (shares) for every TSX (and TSXV/CSE) listed security.

DEPTH (RE-VERIFIED 2026-07-03, W3 — the earlier ~114/2021-10 figure was WRONG)
------------------------------------------------------------------------------
The masterplan assumed a 2012→ or 2017→ CSPR archive; the Slice-G collector docstring
then claimed "2021-10-15 → present, ~114 cross-sections". BOTH are falsified by direct
Wayback probe on 2026-07-03 (W3):

  * The .xls report files are NOT independently indexed in the Wayback CDX API
    (they have opaque GUID filenames, e.g. `ab44fc63-..._en.xls`, with the report
    date carried only in the PAGE's anchor TEXT `YYYYMMDD_CSPR_Report`, never in the
    URL).  The old `*CSPR*.xls` CDX globs therefore returned zero rows — the collector
    was silently finding nothing.  Verified: `iiroc.ca/Documents/2021/*_en.xls`,
    `.../2020/*_en.xls`, and three specific report GUIDs all return `[]` from CDX.
  * The WORKING route is a PAGE-snapshot walk: CDX-enumerate snapshots of the CSPR
    *page* (`iiroc.ca/.../consolidated-short-position-report.aspx`), fetch each
    snapshot's HTML, extract the `(report_date, guid_href)` pairs from the anchor
    list (each snapshot lists ~4-10 recent semi-monthly reports), dedupe by date,
    then replay-fetch each file via the FULL replay host
    `web.archive.org/web/<page_ts>/<href>` (Wayback redirects to the nearest actual
    capture; the `id_` raw variant 404s because it demands an exact-timestamp capture
    the file doesn't have).  One such fetch verified: 437 KB, `application/vnd.ms-excel`,
    OLE2/BIFF magic `\\xd0\\xcf\\x11\\xe0` — a genuine .xls.
  * TRUE achievable depth: the iiroc CSPR page was archived 2019-01 → 2021-05 (it 404s
    after the 2021-05 site migration to ciro.ca).  The listed reports span
    ~2018-11-30 → 2021-02-15.  The ciro.ca successor page is NOT in Wayback under any
    CSPR slug and its files live at opaque `/media/<id>/download` URLs also uncaptured;
    the live ciro.ca site returns 403 Cloudflare to browser UAs.  So the reachable
    window is ONLY ~2018-11 → 2021-02 → roughly 40-50 semi-monthly cross-sections,
    NOT 114 and NOT to present.  C5 phase-0 (which needs >=60 cross-sections) therefore
    does NOT clear the power bar → verdict ACCRUE-DATA (see reports/c5-phase0.md).

STORE (GIT-TRACKED, NOT R2)
----------------------------
  data/ciro_short/positions.parquet
    index: report_date (pd.Timestamp, twice-monthly)
    columns: symbol (str, no .TO suffix), exchange, name, short_shares (int64),
             net_change (int64)
  data/ciro_short/coverage.json
    {fetched_at, n_report_dates, earliest_date, latest_date,
     n_tsx_rows_total, n_new_dates, n_failed_dates, n_page_snapshots, n_page_failed}

Store decision: ~45 report-dates × ~2,000-2,500 TSX rows ≈ 100k rows total.
Well inside the 20MB git-track threshold.  Not R2.

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
# Wayback replay host prefix — fetch an archived resource; Wayback redirects a
# "/web/<page_ts>/<original_or_archived_href>" request to the nearest actual capture.
_WB_HOST = "https://web.archive.org"
_WB_REPLAY = "https://web.archive.org/web/{timestamp}/{original}"

# The CSPR *page* URLs whose Wayback snapshots list the semi-monthly report files.
# The iiroc.ca page was archived 2019-01 → 2021-05 (404s after the ciro.ca migration);
# the ciro.ca variants are listed for forward-completeness but were not archived under
# any CSPR slug as of 2026-07-03 (they resolve to zero snapshots — harmless).
_CSPR_PAGES = [
    "iiroc.ca/industry/marketmonitoringanalysis/Pages/consolidated-short-position-report.aspx",
    "ciro.ca/office-investor/market-data-and-statistics/consolidated-short-position-report",
    "ciro.ca/newsroom/publications/consolidated-short-position-report",
]

# Anchor-text pattern carrying the report date: "20210430_CSPR_Report".
_REPORT_ANCHOR_RE = re.compile(
    r'<a[^>]+href="(/web/[^"]*Documents/\d{4}/[0-9a-f-]+_en\.xls)"[^>]*>\s*(\d{8})_CSPR',
    re.IGNORECASE,
)

# True achievable archive depth re-verified by page-snapshot walk 2026-07-03 (W3).
# The reachable window is ~2018-11 → 2021-02 (iiroc page archived through 2021-05).
_EARLIEST_VERIFIED = date(2018, 11, 1)

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
        # Detect header by presence of 'symbol' or 'ticker' in a cell.
        if any("symbol" in cell or "ticker" in cell for cell in row):
            header_row = row_idx
            # The canonical CSPR header (verified 2019→2021) is:
            #   Security Issue Name | Security Symbol | Exchange Code | No.Shares | Net Change
            # Detect columns by keyword, matching Net Change FIRST so the "No.Shares"
            # / "position" (short-shares) column can never be shadowed by "Net Change".
            for c_idx, cell in enumerate(row):
                if "symbol" in cell or "ticker" in cell:
                    if col_symbol is None:
                        col_symbol = c_idx
                if "exchange" in cell or "market" in cell:
                    if col_exchange is None:
                        col_exchange = c_idx
                if "name" in cell:
                    if col_name is None:
                        col_name = c_idx
                # Net change first (so it wins col 4, not the shares detector).
                if ("net" in cell and "change" in cell) or cell.strip() == "net change":
                    if col_change is None:
                        col_change = c_idx
                    continue
                # Short-position share count: "No.Shares" / "shares" / "short position".
                if ("share" in cell) or ("short" in cell and "position" in cell):
                    if col_shares is None:
                        col_shares = c_idx
            # Fallback: bare "change" if the explicit "net change" match missed.
            if col_change is None:
                for c_idx, cell in enumerate(row):
                    if "change" in cell:
                        col_change = c_idx
                        break
            break

    if header_row is None:
        raise ValueError(f"CSPR XLS for {report_date}: no header row found")
    if col_symbol is None:
        raise ValueError(f"CSPR XLS for {report_date}: no symbol column found")
    if col_shares is None:
        # Fail loud rather than emit a cross-section of all-zero short positions.
        raise ValueError(
            f"CSPR XLS for {report_date}: no short-shares column found "
            f"(header row {header_row}: "
            f"{[str(sheet.cell_value(header_row, c)) for c in range(sheet.ncols)]})"
        )

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
# Wayback HTTP helper (polite, backoff on 503 / connection resets)
# ---------------------------------------------------------------------------

def _wb_get(url: str, *, timeout: int = 90, max_attempts: int = 5,
            params: dict | None = None) -> requests.Response:
    """GET a Wayback URL with exponential backoff.

    Wayback returns 503 under load and periodically refuses connections; both are
    transient. Backs off (3s, 6s, 12s, ...) and retries. Raises the last error if
    all attempts fail.
    """
    last: Exception | None = None
    for att in range(max_attempts):
        try:
            r = requests.get(
                url,
                params=params,
                headers={"User-Agent": _BROWSER_UA},
                timeout=timeout,
                allow_redirects=True,
            )
            # 404 = the resource was never captured by Wayback — permanent, do not
            # retry (retrying only wastes the backoff budget on a dead file).
            if r.status_code == 404:
                r.raise_for_status()
            if r.status_code == 503:
                raise requests.HTTPError("503 Wayback busy", response=r)
            r.raise_for_status()
            return r
        except requests.HTTPError as e:
            resp = getattr(e, "response", None)
            if resp is not None and resp.status_code == 404:
                raise  # permanent — surface immediately, no backoff
            last = e
            if att < max_attempts - 1:
                time.sleep(3 * (2 ** att))
        except Exception as e:  # noqa: BLE001  (connection resets etc. — transient)
            last = e
            if att < max_attempts - 1:
                time.sleep(3 * (2 ** att))
    assert last is not None
    raise last


# ---------------------------------------------------------------------------
# Wayback page-snapshot discovery (the WORKING route — see module docstring)
# ---------------------------------------------------------------------------

def _wb_page_snapshots(timeout: int = 60) -> list[tuple[str, str]]:
    """Enumerate Wayback snapshots of the CSPR *page(s)* (statuscode 200).

    Returns sorted, de-duplicated (timestamp, page_original_url) pairs. The .xls
    report files themselves are NOT independently indexed in CDX (GUID filenames);
    we must read each page snapshot's HTML to discover them. Each snapshot is later
    replayed at ITS OWN page URL (the iiroc.ca vs ciro.ca host differs).
    """
    seen: dict[str, str] = {}  # timestamp -> page_original_url
    for page in _CSPR_PAGES:
        try:
            r = _wb_get(
                _WB_CDX_URL, timeout=timeout,
                params={
                    "url": page,
                    "output": "json",
                    "fl": "timestamp,original,statuscode",
                    "filter": "statuscode:200",
                    "limit": "500",
                },
            )
            data = r.json()
            if data and len(data) > 1:
                for row in data[1:]:
                    ts, orig = str(row[0]), str(row[1])
                    seen.setdefault(ts, orig)
        except Exception as e:  # noqa: BLE001
            log.warning("ciro_short: CDX page enumeration failed for %s: %s", page, e)
        time.sleep(0.5)
    snaps = sorted(seen.items())
    log.info("ciro_short: %d CSPR page snapshots found", len(snaps))
    return snaps


def _wb_discover_reports() -> tuple[dict[date, tuple[str, str]], int, int]:
    """Walk CSPR page snapshots and discover semi-monthly report files.

    For each page snapshot, fetch the archived HTML and extract every
    (report_date, archived_href) pair from the `YYYYMMDD_CSPR_Report` anchors.
    A single snapshot typically lists ~4-10 recent reports, so many snapshots over
    years dedupe (by report_date, keeping the first/earliest page_ts) into a dense
    semi-monthly series.

    Returns:
        (date2ref, n_page_snapshots, n_page_failed) where date2ref maps
        report_date -> (page_timestamp, archived_href).
    """
    snaps = _wb_page_snapshots()
    date2ref: dict[date, tuple[str, str]] = {}
    n_page_failed = 0

    for ts, page_orig in snaps:
        # Replay each snapshot at its OWN archived page URL.
        page_url = f"{_WB_HOST}/web/{ts}/{page_orig}"
        try:
            html = _wb_get(page_url, timeout=90).text
        except Exception as e:  # noqa: BLE001
            n_page_failed += 1
            log.warning("ciro_short: page snapshot %s fetch failed: %s", ts, e)
            continue

        for m in _REPORT_ANCHOR_RE.finditer(html):
            href, ds = m.group(1), m.group(2)
            try:
                rd = date(int(ds[:4]), int(ds[4:6]), int(ds[6:8]))
            except ValueError:
                continue
            # keep the first-seen href for a given report date (earliest page_ts)
            date2ref.setdefault(rd, (ts, href))
        time.sleep(0.5)  # polite pacing

    log.info(
        "ciro_short: discovered %d distinct report dates (%d page snapshots, "
        "%d page fetch failures)",
        len(date2ref), len(snaps), n_page_failed,
    )
    return date2ref, len(snaps), n_page_failed


def _wb_replay_download(page_ts: str, archived_href: str,
                        timeout: int = 90) -> bytes:
    """Download a report file via the Wayback replay host.

    `archived_href` is the `/web/<ts>/https://www.iiroc.ca/Documents/.../GUID_en.xls`
    href extracted from the page HTML. Wayback redirects to the nearest actual
    capture of the file. Validates the OLE2/BIFF magic so an HTML error page never
    reaches the xlrd parser.
    """
    if archived_href.startswith("/web/"):
        url = _WB_HOST + archived_href
    else:
        url = _WB_REPLAY.format(timestamp=page_ts, original=archived_href)
    r = _wb_get(url, timeout=timeout)
    content = r.content
    # OLE2/BIFF (legacy .xls) magic; guards against Wayback 404 HTML pages.
    if content[:8] != b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        raise ValueError(
            f"replay for {archived_href[-40:]} returned non-XLS content "
            f"({content[:16]!r}, {len(content)} bytes)"
        )
    return content


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
    n_page_snapshots: int = 0,
    n_page_failed: int = 0,
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
        "n_page_snapshots": n_page_snapshots,
        "n_page_failed": n_page_failed,
    }, indent=2))


# ---------------------------------------------------------------------------
# Main fetch function
# ---------------------------------------------------------------------------

def fetch_ciro_short(full_history: bool = False,
                     checkpoint_every: int = 5) -> int:
    """Download and parse CIRO CSPR XLS files via the Wayback page-snapshot walk.

    Route (see module docstring): CDX-enumerate CSPR *page* snapshots → parse each
    snapshot's HTML for `(report_date, archived_href)` anchors → dedupe by date →
    replay-fetch each file via the Wayback host → parse via xlrd. Polite pacing +
    exponential backoff on Wayback 503s; the parquet is checkpoint-saved every
    `checkpoint_every` new dates so an interrupted run resumes (already-stored dates
    are skipped on the next run).

    Args:
        full_history: If True, fetch all discoverable report dates. If False, only
                      dates newer than the last 60 days that are not already stored
                      (incremental top-up — mostly a no-op now that the archive is
                      frozen at 2021-02, but kept for forward compatibility).
        checkpoint_every: Save the parquet after this many newly-parsed dates.

    Returns:
        Number of new report dates successfully parsed and stored.

    Raises:
        RuntimeError: If no new dates could be fetched AND the store is empty
                      (fail-closed: at least one report date must land on first run).
    """
    existing = _load_store()
    already_have = _stored_report_dates(existing)

    # Discover report files by walking the CSPR page snapshots.
    date2ref, n_page_snaps, n_page_failed = _wb_discover_reports()
    if not date2ref:
        if not already_have:
            raise RuntimeError(
                "ciro_short: page-walk discovered no CSPR reports and store is empty "
                f"({n_page_snaps} page snapshots, {n_page_failed} page failures)"
            )
        log.warning("ciro_short: page-walk found no reports; using existing store")
        _write_coverage(
            n_report_dates=len(already_have),
            earliest_date=str(min(already_have)) if already_have else "",
            latest_date=str(max(already_have)) if already_have else "",
            n_tsx_rows_total=len(existing),
            n_new_dates=0, n_failed_dates=0,
            n_page_snapshots=n_page_snaps, n_page_failed=n_page_failed,
        )
        return 0

    # Determine which report dates to attempt.
    if full_history:
        cutoff = _EARLIEST_VERIFIED
    else:
        cutoff = date.today() - timedelta(days=60)

    targets = sorted(rd for rd in date2ref
                     if rd >= cutoff and rd not in already_have)

    new_chunks: list[pd.DataFrame] = []
    n_new = 0
    n_failed = 0

    def _flush() -> pd.DataFrame:
        """Merge new chunks into the store and persist (checkpoint)."""
        nonlocal existing, new_chunks
        if not new_chunks:
            return existing
        combined = pd.concat([existing] + new_chunks, ignore_index=True)
        combined["_sort_key"] = pd.to_datetime(combined["report_date"])
        combined = (
            combined.sort_values("_sort_key")
            .drop_duplicates(subset=["report_date", "symbol"], keep="last")
            .drop(columns=["_sort_key"])
            .reset_index(drop=True)
        )
        _save_store(combined)
        existing = combined
        new_chunks = []
        return combined

    for rd in targets:
        page_ts, href = date2ref[rd]
        try:
            raw = _wb_replay_download(page_ts, href, timeout=90)
            df_chunk = _parse_xls_bytes(raw, rd)
            new_chunks.append(df_chunk)
            already_have.add(rd)
            n_new += 1
            log.info("ciro_short: fetched %s (%d TSX rows)", rd, len(df_chunk))
            if n_new % checkpoint_every == 0:
                _flush()  # checkpoint so an interrupted run resumes
            time.sleep(0.4)  # polite pacing for Wayback
        except Exception as e:  # noqa: BLE001
            n_failed += 1
            log.warning("ciro_short: failed %s (%s): %s", rd, page_ts, e)

    combined = _flush()

    if n_new == 0 and not already_have:
        raise RuntimeError(
            f"ciro_short: 0 new dates parsed and store is empty "
            f"({n_failed} file failures over {len(targets)} targets). "
            "Check Wayback replay access."
        )

    dates_in_store = sorted(
        pd.to_datetime(combined["report_date"]).dt.date.unique()
    ) if not combined.empty else []
    _write_coverage(
        n_report_dates=len(dates_in_store),
        earliest_date=str(dates_in_store[0]) if dates_in_store else "",
        latest_date=str(dates_in_store[-1]) if dates_in_store else "",
        n_tsx_rows_total=len(combined),
        n_new_dates=n_new,
        n_failed_dates=n_failed,
        n_page_snapshots=n_page_snaps,
        n_page_failed=n_page_failed,
    )
    log.info("ciro_short: %d new dates; panel %d rows over %d report dates",
             n_new, len(combined), len(dates_in_store))
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
                        help=f"Backfill from {_EARLIEST_VERIFIED} (page-walk verified depth)")
    parser.add_argument("--dry-discover", action="store_true",
                        help="Just walk CSPR page snapshots and list discoverable report dates")
    args = parser.parse_args()

    if args.dry_discover:
        d2r, n_snaps, n_pf = _wb_discover_reports()
        for rd in sorted(d2r):
            ts, href = d2r[rd]
            print(rd, ts, href[-46:])
        print(f"\nTotal: {len(d2r)} distinct report dates "
              f"({n_snaps} page snapshots, {n_pf} page failures)")
    else:
        n = fetch_ciro_short(full_history=args.full_history)
        print(f"Done: {n} new report dates fetched")
        if _COVERAGE.exists():
            cov = json.loads(_COVERAGE.read_text())
            print(f"Coverage: {cov.get('n_report_dates')} report dates, "
                  f"earliest={cov.get('earliest_date')}, "
                  f"latest={cov.get('latest_date')}, "
                  f"n_tsx_rows={cov.get('n_tsx_rows_total')}")
