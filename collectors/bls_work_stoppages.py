"""BLS Work Stoppages monthly listing collector (keyless, fail-open).

Source: https://www.bls.gov/wsp/
Parses the BLS "Major Work Stoppages" monthly listing page (free HTML, no key).
Stores monthly data to data/bls_work_stoppages/stoppages.parquet.

Schema
------
  org          str   — labor organization / union name
  employer     str   — company / industry
  states       str   — state(s) affected (comma-separated if multiple)
  workers      int   — number of workers involved (BLS publishes this)
  start_date   date  — stoppage start date
  end_date     date  — stoppage end date (NaT if ongoing)
  naics        str   — NAICS industry code where available (else '')
  source_url   str   — canonical BLS URL for this record

Fail-open contract
------------------
If the BLS page is unreachable or fails to parse, the function returns
the existing parquet (if any) and logs a warning — it does NOT raise.
On first run with no existing parquet and a network failure, the function
writes a manually-seeded initial parquet (see SEED_ROWS below).

WAF note
--------
The BLS WAF blocks python-requests default UA and browser UAs on some
endpoints.  Use the descriptive research UA (same pattern as bls_cpi_weights.py).
"""
from __future__ import annotations

import logging
import re
import time
from datetime import date, datetime
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

_BLS_UA = "BLS-DataFetch/1.0 (macro-research; non-commercial)"
_WSP_URL = "https://www.bls.gov/wsp/"
_CACHE_TTL_SECONDS = 6 * 3600  # 6h (monthly data but check for updates)
_CACHE_PATH = Path("/tmp/bls_wsp_listing.html")

# ---------------------------------------------------------------------------
# Manually-seeded rows for major known stoppages
# These prime the store on first run when the BLS page is unavailable.
# Source: BLS Work Stoppages listing (https://www.bls.gov/wsp/).
# ---------------------------------------------------------------------------

SEED_ROWS: list[dict] = [
    {
        "org": "United Auto Workers (UAW)",
        "employer": "General Motors",
        "states": "MI,OH,TX,KY,MO,NY,TN,WI",
        "workers": 49000,
        "start_date": date(2019, 9, 16),
        "end_date": date(2019, 10, 25),
        "naics": "3361",
        "source_url": "https://www.bls.gov/wsp/",
    },
    {
        "org": "United Auto Workers (UAW)",
        "employer": "Ford Motor Company",
        "states": "MI,OH,MO",
        "workers": 17000,
        "start_date": date(2023, 9, 15),
        "end_date": date(2023, 10, 30),
        "naics": "3361",
        "source_url": "https://www.bls.gov/wsp/",
    },
    {
        "org": "United Auto Workers (UAW)",
        "employer": "Stellantis",
        "states": "MI,OH,IN,IL",
        "workers": 7000,
        "start_date": date(2023, 9, 15),
        "end_date": date(2023, 10, 25),
        "naics": "3361",
        "source_url": "https://www.bls.gov/wsp/",
    },
    {
        "org": "International Association of Machinists (IAM)",
        "employer": "Boeing",
        "states": "WA,OR,CA",
        "workers": 33000,
        "start_date": date(2024, 9, 13),
        "end_date": date(2024, 11, 4),
        "naics": "3364",
        "source_url": "https://www.bls.gov/wsp/",
    },
    {
        "org": "International Longshoremen's Association (ILA)",
        "employer": "US East/Gulf Coast Ports",
        "states": "MA,NJ,NY,VA,SC,GA,FL,TX,LA",
        "workers": 45000,
        "start_date": date(2024, 10, 1),
        "end_date": date(2024, 10, 3),
        "naics": "4831",
        "source_url": "https://www.bls.gov/wsp/",
    },
]


# ---------------------------------------------------------------------------
# HTTP + parsing helpers
# ---------------------------------------------------------------------------

def _fetch_html(timeout: int = 30) -> str | None:
    """Fetch BLS work-stoppages page HTML. Returns None on failure."""
    try:
        import requests

        if _CACHE_PATH.exists():
            age = time.time() - _CACHE_PATH.stat().st_mtime
            if age < _CACHE_TTL_SECONDS:
                log.debug("BLS WSP cache hit (age %.0fs)", age)
                return _CACHE_PATH.read_text(encoding="utf-8")

        r = requests.get(
            _WSP_URL,
            headers={"User-Agent": _BLS_UA, "Accept": "text/html"},
            timeout=timeout,
        )
        if r.status_code != 200:
            log.warning("BLS WSP fetch: HTTP %d (UA: %s)", r.status_code, _BLS_UA)
            return None

        html = r.text
        _CACHE_PATH.write_text(html, encoding="utf-8")
        log.info("BLS WSP page fetched and cached")
        return html

    except Exception as exc:
        log.warning("BLS WSP fetch exception: %s", exc)
        return None


def _parse_date(s: str) -> date | None:
    """Parse BLS date strings: 'Jan. 1, 2024', 'January 1, 2024', '01/01/2024'."""
    s = s.strip().rstrip("*").strip()
    if not s or s.lower() in ("ongoing", "present", "-", "—"):
        return None
    for fmt in ("%B %d, %Y", "%b. %d, %Y", "%b %d, %Y", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    log.debug("Could not parse date: %r", s)
    return None


def _parse_workers(s: str) -> int | None:
    """Parse worker count: '49,000', '49000', '~49,000'."""
    s = re.sub(r"[~,\s]", "", s.strip())
    try:
        return int(s)
    except ValueError:
        return None


def _parse_html_table(html: str) -> list[dict] | None:
    """Parse stoppages from the BLS WSP HTML table.

    BLS renders a table with columns roughly:
      Establishment | Industry | Union | States | Workers | Beginning | Ending

    Column order varies; we attempt to detect by header text.
    Returns list of row dicts, or None if parsing fails.
    """
    try:
        # Find all table rows
        table_match = re.search(
            r'<table[^>]*>(.*?)</table>', html, re.DOTALL | re.IGNORECASE
        )
        if not table_match:
            log.warning("BLS WSP: no <table> found in HTML")
            return None

        table_html = table_match.group(1)
        rows_raw = re.findall(r'<tr[^>]*>(.*?)</tr>', table_html, re.DOTALL | re.IGNORECASE)
        if len(rows_raw) < 2:
            return None

        # Detect header row
        header_cells = re.findall(
            r'<t[hd][^>]*>(.*?)</t[hd]>', rows_raw[0], re.DOTALL | re.IGNORECASE
        )
        headers = [re.sub(r'<[^>]+>', '', c).strip().lower() for c in header_cells]

        # Map column indices
        col_map: dict[str, int] = {}
        for i, h in enumerate(headers):
            if "establishment" in h or "employer" in h or "company" in h:
                col_map.setdefault("employer", i)
            elif "union" in h or "organization" in h or "labor" in h:
                col_map.setdefault("org", i)
            elif "state" in h:
                col_map.setdefault("states", i)
            elif "worker" in h or "employee" in h:
                col_map.setdefault("workers", i)
            elif "begin" in h or "start" in h:
                col_map.setdefault("start_date", i)
            elif "end" in h or "conclud" in h or "settl" in h:
                col_map.setdefault("end_date", i)
            elif "industry" in h or "naics" in h or "sic" in h:
                col_map.setdefault("naics", i)

        if not col_map.get("start_date") and not col_map.get("employer"):
            log.warning("BLS WSP: could not identify required columns; headers=%s", headers)
            return None

        rows_out: list[dict] = []
        for raw_row in rows_raw[1:]:
            cells = re.findall(
                r'<t[hd][^>]*>(.*?)</t[hd]>', raw_row, re.DOTALL | re.IGNORECASE
            )
            cells_clean = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
            if len(cells_clean) < 3:
                continue

            def _get(key: str, default: str = "") -> str:
                idx = col_map.get(key)
                if idx is None or idx >= len(cells_clean):
                    return default
                return cells_clean[idx].strip()

            employer = _get("employer")
            org = _get("org")
            states = _get("states")
            workers_raw = _get("workers")
            start_raw = _get("start_date")
            end_raw = _get("end_date")
            naics = _get("naics")

            if not employer and not org:
                continue

            workers = _parse_workers(workers_raw)
            start_dt = _parse_date(start_raw)
            end_dt = _parse_date(end_raw)

            rows_out.append({
                "org": org,
                "employer": employer,
                "states": states,
                "workers": workers if workers is not None else 0,
                "start_date": start_dt,
                "end_date": end_dt,
                "naics": naics,
                "source_url": _WSP_URL,
            })

        return rows_out if rows_out else None

    except Exception as exc:
        log.warning("BLS WSP parse exception: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Parquet I/O
# ---------------------------------------------------------------------------

_PARQUET_PATH_REL = "data/bls_work_stoppages/stoppages.parquet"

_DTYPE_MAP: dict[str, str] = {
    "org": "str",
    "employer": "str",
    "states": "str",
    "workers": "Int64",
    "naics": "str",
    "source_url": "str",
}


def _build_df(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    if df.empty:
        df = pd.DataFrame(
            columns=["org", "employer", "states", "workers", "start_date", "end_date", "naics", "source_url"]
        )
    df["start_date"] = pd.to_datetime(df.get("start_date", pd.NaT), errors="coerce").dt.date
    df["end_date"] = pd.to_datetime(df.get("end_date", pd.NaT), errors="coerce").dt.date
    df["workers"] = pd.to_numeric(df.get("workers", 0), errors="coerce").fillna(0).astype("Int64")
    for col in ["org", "employer", "states", "naics", "source_url"]:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].fillna("").astype(str)
    return df[["org", "employer", "states", "workers", "start_date", "end_date", "naics", "source_url"]]


def _load_existing(parquet_path: Path) -> pd.DataFrame | None:
    if not parquet_path.exists():
        return None
    try:
        return pd.read_parquet(parquet_path)
    except Exception as exc:
        log.warning("BLS WSP: could not read existing parquet: %s", exc)
        return None


def _merge_and_write(new_rows: list[dict], parquet_path: Path) -> pd.DataFrame:
    """Merge new rows into existing parquet (dedup by org+employer+start_date)."""
    new_df = _build_df(new_rows)
    existing = _load_existing(parquet_path)

    if existing is not None and not existing.empty:
        combined = pd.concat([existing, new_df], ignore_index=True)
        combined = combined.drop_duplicates(
            subset=["org", "employer", "start_date"], keep="last"
        )
    else:
        combined = new_df

    combined = combined.sort_values("start_date", ascending=False, na_position="last")
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    combined.to_parquet(parquet_path, index=False)
    log.info("BLS WSP parquet written: %d rows at %s", len(combined), parquet_path)
    return combined


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def collect_work_stoppages(root: Path | str | None = None) -> pd.DataFrame:
    """Collect BLS work stoppages listing and persist to parquet.

    Fail-open: on any network/parse failure, returns existing parquet data
    (or the manually-seeded SEED_ROWS on first run).

    Parameters
    ----------
    root : Path or None
        Repository root.  Defaults to parent of this file's directory.

    Returns
    -------
    pd.DataFrame with columns: org, employer, states, workers, start_date,
                                end_date, naics, source_url
    """
    if root is None:
        root = Path(__file__).resolve().parents[1]
    root = Path(root)
    parquet_path = root / _PARQUET_PATH_REL

    html = _fetch_html()
    parsed_rows: list[dict] | None = None

    if html is not None:
        parsed_rows = _parse_html_table(html)
        if parsed_rows:
            log.info("BLS WSP: parsed %d rows from live page", len(parsed_rows))
        else:
            log.warning("BLS WSP: HTML fetched but table parse failed; using seed+existing")

    if parsed_rows:
        # Merge live data with seed rows (seed provides manual overrides / history)
        all_rows = SEED_ROWS + parsed_rows
        return _merge_and_write(all_rows, parquet_path)

    # Fall back to existing + seeds
    existing = _load_existing(parquet_path)
    if existing is not None:
        log.info("BLS WSP: using existing parquet (%d rows)", len(existing))
        return existing

    # First run, no network: write seed rows
    log.info("BLS WSP: no existing parquet; writing seed rows (%d)", len(SEED_ROWS))
    return _merge_and_write(SEED_ROWS, parquet_path)


def load_stoppages(root: Path | str | None = None) -> pd.DataFrame:
    """Load the persisted stoppages parquet without fetching.

    Returns empty DataFrame if not yet collected.
    """
    if root is None:
        root = Path(__file__).resolve().parents[1]
    root = Path(root)
    parquet_path = root / _PARQUET_PATH_REL
    existing = _load_existing(parquet_path)
    if existing is not None:
        return existing
    return _build_df(SEED_ROWS)


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    _root = Path(__file__).resolve().parents[1]
    df = collect_work_stoppages(root=_root)
    print(df.to_string(index=False))
