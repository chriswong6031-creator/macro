"""HKEX CBBC / Derivative Warrant daily outstanding collector (H-CBB).

WHY
---
HK's most distinctive microstructure: Callable Bull/Bear Contracts (CBBC) and
Derivative Warrants (DW) create dense issuer-hedge "magnet" zones near spot.
A bull CBBC mandatory call fires when spot touches the call price from above —
the issuer must immediately unwind its hedge (sell the underlying), amplifying
the down move. Dense outstanding CBBC just below spot = forced-sell cascade
risk. This collector feeds the engine/hk_cbbc.py leverage-map organ.

SOURCE — verified 2026-07-08 (no key required, free, EOD)
----------------------------------------------------------
HKEX News (www1.hkexnews.hk) titleSearchServlet — the same endpoint that
powers hk_placements.py. Structured-products tier-1/tier-2 codes:

  t1code=70000  ("Debt and Structured Products")
  t2Gcode=22    CBBC
  t2code=71500  "Daily Trading Report - CBBC"  (XLSX, ~9 issuers/day)
  t2Gcode=20    DW
  t2code=71100  "Daily Trading Report - DW"    (XLSX, ~11 issuers/day)

Each issuer files one XLSX per day by ~18:30 HKT. Schema (verified):
  Row header: Stock Short Name | Stock Code | # Bought | Avg Price Bought |
              # Sold | Avg Price Sold | # Still Out in Market | Total Issue Size |
              Pct of Issue Still Out | Trading Currency | Active Quote (Yes/No)

Bull/Bear (CBBC): short name contains "RC" = Callable Bull, "RP" = Callable Bear.
Call/Put (DW):    short name contains "EC" = Call, "EP" = Put.

Mandatory call price (for CBBC magnet analysis): NOT available in the daily
XLSX. It is in the Supplemental Listing Document (PDF, t2code=73600).
Building a call-level lookup from PDFs is out of scope for W1 — the engine
computes the bull/bear ratio and outstanding skew without it, and degrades
gracefully when call levels are absent. This is documented honestly in the
engine output.

STORE
-----
  data/hk_cbbc/
    raw/YYYYMMDD_cbbc.parquet  — daily CBBC snapshot (appended-only dir)
    raw/YYYYMMDD_dw.parquet    — daily DW snapshot
    cbbc_latest.parquet        — latest composite (overwritten nightly)
    dw_latest.parquet          — latest DW composite
    coverage.json              — freshness stamp

Columns (both CBBC and DW):
  date (date), trade_date (str YYYYMMDD), product_type ('cbbc'|'dw'),
  short_name (str), stock_code (str), bull_bear ('bull'|'bear'|'unknown'),
  outstanding (int), issue_size (int), pct_outstanding (float),
  active_quote (bool), issuer (str), underlying_code (str, best-effort from name)

FAIL-OPEN
---------
  * HTTP or parse failure → logs warning, returns {} (no write, no crash).
  * Missing issuers on a given day → tolerated (market holiday, timing).
  * Never raises into the collect pipeline.

LANE CONTRACT
-------------
  Network I/O: collect lane ONLY (asia-close group "hk_cbbc").
  Render lane reads back via load_latest() — pure parquet/JSON reads, no network.
"""
from __future__ import annotations

import io
import json
import logging
import re
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

from collectors.base import Adapter
from lib import config

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SERVLET = "https://www1.hkexnews.hk/search/titleSearchServlet.do"
_BASE_URL = "https://www1.hkexnews.hk"

# Browser UA (same as hk_placements — same endpoint; verified 2026-07-08)
_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

# HKEX Structured Products category codes (verified from tiertwo_e.json 2026-07-08)
_T1_CODE = "70000"   # Debt and Structured Products
_CBBC_T2G = "22"     # CBBC group
_CBBC_T2  = "71500"  # Daily Trading Report - CBBC (count=249 as of 2026-07-08)
_DW_T2G   = "20"     # DW group
_DW_T2    = "71100"  # Daily Trading Report - DW (count=300 as of 2026-07-08)

# Look-back window for incremental runs (days) — covers a week to self-heal missed runs
_INCR_WINDOW_D = 7

# A FRESH (empty) store bootstraps with this many days so the engine has at least
# a few sessions of data to work with on day one.
_BOOTSTRAP_WINDOW_D = 14

# Staleness: issuers file by ~18:30 HKT. If we haven't seen a day's data
# after 3 trading days, flag stale.
_STALE_DAYS = 3

# Column layout of the HKEX DTS XLSX data rows (0-indexed)
_COL_SHORT_NAME   = 0
_COL_STOCK_CODE   = 1
_COL_OUTSTANDING  = 6
_COL_ISSUE_SIZE   = 7
_COL_PCT_OUT      = 8
_COL_CURRENCY     = 9
_COL_ACTIVE_QUOTE = 10

# Store paths
def _store_dir(data_root: Path | None = None) -> Path:
    if data_root is None:
        data_root = config.data_dir()
    return data_root / "hk_cbbc"

def _raw_dir(data_root: Path | None = None) -> Path:
    return _store_dir(data_root) / "raw"

def _coverage_path(data_root: Path | None = None) -> Path:
    return _store_dir(data_root) / "coverage.json"

# Column definitions for the canonical store frame
_COLUMNS = [
    "date", "trade_date", "product_type", "short_name", "stock_code",
    "bull_bear", "outstanding", "issue_size", "pct_outstanding",
    "active_quote", "issuer", "underlying_code",
]

# ---------------------------------------------------------------------------
# Name-parsing helpers
# ---------------------------------------------------------------------------

def parse_bull_bear_cbbc(short_name: str) -> str:
    """Classify a CBBC by short name convention (RC = bull, RP = bear).

    Naming example: 'CT#HSI  RC2709C' → bull  |  'CT#HSI  RP2802A' → bear
    The RC/RP token may appear anywhere after the '#' separator.
    Returns 'unknown' when the convention is ambiguous.
    """
    n = str(short_name or "").upper()
    if "RC" in n:
        return "bull"
    if "RP" in n:
        return "bear"
    return "unknown"


def parse_call_put_dw(short_name: str) -> str:
    """Classify a DW by short name convention (EC = call, EP = put).

    Naming example: 'MBLININ@EC2702A' → call  |  'MB-KBLH@EP2612A' → put
    Returns 'unknown' for unrecognised patterns.
    """
    n = str(short_name or "").upper()
    if "EC" in n:
        return "call"
    if "EP" in n:
        return "put"
    return "unknown"


def parse_underlying_code(short_name: str, product_type: str) -> str:
    """Best-effort extraction of the underlying code from the short name.

    CBBC: 'CT#HSI  RC2709C' → 'HSI'   |  'CT#HKEX RC2610A' → 'HKEX'
    DW:   'MBLININ@EC2702A' → 'ININ'   |  'MB-AIA @EC2705A' → 'AIA'

    Stripped to 4 chars max; may be wrong for unusual issuers. Returns empty
    string on parse failure — downstream handles via honest null.
    """
    n = str(short_name or "")
    # CBBC convention: ISSUER#UNDERLYING TYPEEXPIRY_SERIES
    if "#" in n:
        after = n.split("#", 1)[1].strip()
        # Take first non-space segment (up to first space / RC / RP)
        code = re.split(r"[\s@RC]+", after)[0]
        return code[:8].strip()
    # DW convention: ISSUER-UNDERLYING@TYPEEXPIRY_SERIES
    if "@" in n:
        before = n.split("@", 1)[0]
        # Remove issuer prefix (2-4 chars) then take the rest
        code = re.sub(r"^MB[-\s]?", "", before, flags=re.I).strip()
        return code[:8].strip()
    # Fallback: strip issuer prefix heuristic
    return ""


# ---------------------------------------------------------------------------
# XLSX parser
# ---------------------------------------------------------------------------

def parse_dts_xlsx(raw_bytes: bytes, issuer_name: str,
                   product_type: str, trade_date: str) -> pd.DataFrame:
    """Parse a HKEX Daily Trading Summary XLSX into the canonical frame.

    Both CBBC and DW DTS files share the same column layout (verified 2026-07-08):
      col 0: Stock Short Name
      col 1: Stock Code
      col 2: # Bought     col 3: Avg Price Bought
      col 4: # Sold       col 5: Avg Price Sold
      col 6: # Still Out in Market
      col 7: Total Issue Size
      col 8: Percent of Issue Still Out
      col 9: Trading Currency
      col 10: Active Quote Criteria (Yes/No)

    The header row is identified by looking for 'Stock Short Name' (case-insensitive).
    All rows above the header + the separator row are skipped.
    Returns empty DataFrame on any parse error (fail-open).
    """
    rows: list[dict] = []
    try:
        df_raw = pd.read_excel(io.BytesIO(raw_bytes), sheet_name=0, header=None,
                               engine="openpyxl")
    except Exception as e:  # noqa: BLE001
        log.warning("hk_cbbc: parse_dts_xlsx: read_excel failed (%s)", e)
        return pd.DataFrame(columns=_COLUMNS)

    # Locate the header row
    header_row_idx: int | None = None
    for i, row in df_raw.iterrows():
        cell = str(row.iloc[0] or "").strip().lower()
        if "stock short name" in cell:
            header_row_idx = int(i)
            break

    if header_row_idx is None:
        log.warning("hk_cbbc: parse_dts_xlsx: no header row found in XLSX from %s", issuer_name)
        return pd.DataFrame(columns=_COLUMNS)

    # Extract trade date from the file if not provided (backup)
    if not trade_date:
        for i, row in df_raw.iterrows():
            cell = str(row.iloc[0] or "").strip().lower()
            if "trade date" in cell and int(i) < header_row_idx:
                val = str(row.iloc[1] or "").strip()
                if re.match(r"^\d{8}$", val):
                    trade_date = val
                    break

    # Parse data rows (skip header + separator)
    session_date: date | None = None
    if re.match(r"^\d{8}$", str(trade_date)):
        try:
            session_date = datetime.strptime(str(trade_date), "%d%m%Y").date()
        except ValueError:
            # Try YYYYMMDD
            try:
                session_date = datetime.strptime(str(trade_date), "%Y%m%d").date()
            except ValueError:
                pass

    for i, row in df_raw.iterrows():
        if int(i) <= header_row_idx + 1:
            continue  # skip header and separator rows
        short_name = str(row.iloc[_COL_SHORT_NAME] or "").strip()
        if not short_name or "---" in short_name or short_name.lower().startswith("total"):
            continue
        try:
            stock_code = str(int(row.iloc[_COL_STOCK_CODE])) if pd.notna(row.iloc[_COL_STOCK_CODE]) else ""
        except (TypeError, ValueError):
            stock_code = str(row.iloc[_COL_STOCK_CODE] or "").strip()

        if not stock_code:
            continue

        try:
            outstanding = int(row.iloc[_COL_OUTSTANDING] or 0)
        except (TypeError, ValueError):
            outstanding = 0
        try:
            issue_size = int(row.iloc[_COL_ISSUE_SIZE] or 0)
        except (TypeError, ValueError):
            issue_size = 0
        try:
            pct_out = float(row.iloc[_COL_PCT_OUT] or 0.0)
        except (TypeError, ValueError):
            pct_out = 0.0

        active_raw = str(row.iloc[_COL_ACTIVE_QUOTE] if len(row) > _COL_ACTIVE_QUOTE else "")
        active_quote = active_raw.strip().lower() == "yes"

        if product_type == "cbbc":
            bull_bear = parse_bull_bear_cbbc(short_name)
        else:
            bull_bear = parse_call_put_dw(short_name)

        underlying_code = parse_underlying_code(short_name, product_type)

        rows.append({
            "date": session_date,
            "trade_date": str(trade_date),
            "product_type": product_type,
            "short_name": short_name,
            "stock_code": stock_code,
            "bull_bear": bull_bear,
            "outstanding": outstanding,
            "issue_size": issue_size,
            "pct_outstanding": pct_out,
            "active_quote": active_quote,
            "issuer": issuer_name[:60],
            "underlying_code": underlying_code,
        })

    return pd.DataFrame(rows, columns=_COLUMNS) if rows else pd.DataFrame(columns=_COLUMNS)


# ---------------------------------------------------------------------------
# Servlet fetch helpers
# ---------------------------------------------------------------------------

def _query_servlet(t2g_code: str, t2_code: str,
                   from_d: date, to_d: date,
                   row_range: int = 100, timeout: int = 30,
                   retries: int = 3) -> list[dict]:
    """Fetch rows from the HKEX News titleSearchServlet. Returns [] on failure."""
    params = {
        "sortDir": "0", "sortByOptions": "DateTime",
        "category": "0", "market": "SEHK", "stockId": "-1",
        "documentType": "-1",
        "fromDate": from_d.strftime("%Y%m%d"),
        "toDate": to_d.strftime("%Y%m%d"),
        "title": "", "searchType": "1",
        "t1code": _T1_CODE, "t2Gcode": t2g_code, "t2code": t2_code,
        "rowRange": str(row_range), "lang": "E",
    }
    last: Exception | None = None
    for attempt in range(retries):
        try:
            r = requests.get(_SERVLET, params=params, timeout=timeout,
                             headers={"User-Agent": _BROWSER_UA})
            r.raise_for_status()
            payload = json.loads(r.text)
            result = payload.get("result")
            if not result or result == "null":
                return []
            rows = json.loads(result)
            return rows if isinstance(rows, list) else []
        except Exception as e:  # noqa: BLE001
            last = e
            if attempt < retries - 1:
                wait = 2.0 * (2 ** attempt)
                log.warning("hk_cbbc: servlet t2=%s attempt %d/%d failed (%s); retry %.0fs",
                            t2_code, attempt + 1, retries, e, wait)
                time.sleep(wait)
    log.warning("hk_cbbc: servlet t2=%s failed after %d attempts: %s", t2_code, retries, last)
    return []


def _download_xlsx(file_link: str, timeout: int = 30) -> bytes | None:
    """Download an XLSX file from HKEX News. Returns None on failure."""
    url = _BASE_URL + file_link
    try:
        r = requests.get(url, timeout=timeout,
                         headers={"User-Agent": _BROWSER_UA,
                                  "Referer": _BASE_URL + "/"})
        r.raise_for_status()
        return r.content
    except Exception as e:  # noqa: BLE001
        log.warning("hk_cbbc: XLSX download failed %s: %s", url, e)
        return None


# ---------------------------------------------------------------------------
# Issuer title → issuer name helper
# ---------------------------------------------------------------------------

def _issuer_from_title(title: str) -> str:
    """Extract a short issuer name from the announcement title.

    E.g. 'J.P. Morgan Structured Products B.V. - Daily Trading Summary...'
    → 'J.P. Morgan Structured Products B.V.'
    """
    cleaned = re.sub(r"&#x[0-9a-fA-F]+;", "/", title)  # unescape HTML entities
    parts = re.split(r"\s*[-–—]\s*", cleaned, maxsplit=1)
    return parts[0].strip()[:60] if parts else title[:60]


# ---------------------------------------------------------------------------
# Core fetch
# ---------------------------------------------------------------------------

def fetch_daily_dts(product_type: str, from_d: date, to_d: date,
                    data_root: Path | None = None) -> list[pd.DataFrame]:
    """Fetch all Daily Trading Summary XLSXs for a product type over [from_d, to_d].

    product_type: 'cbbc' | 'dw'
    Returns a list of parsed DataFrames (one per issuer-day file).
    Empty list on failure or no data. Never raises.
    """
    t2g = _CBBC_T2G if product_type == "cbbc" else _DW_T2G
    t2  = _CBBC_T2  if product_type == "cbbc" else _DW_T2

    rows = _query_servlet(t2g, t2, from_d, to_d, row_range=200)
    if not rows:
        log.info("hk_cbbc: no %s DTS rows returned for %s..%s", product_type, from_d, to_d)
        return []

    frames: list[pd.DataFrame] = []
    for row in rows:
        file_link = row.get("FILE_LINK", "")
        if not file_link or not file_link.endswith(".xlsx"):
            continue
        title = row.get("TITLE", "")
        issuer = _issuer_from_title(title)

        # Extract trade date from the file_link path or DATE_TIME field
        dt_str = row.get("DATE_TIME", "")   # e.g. "08/07/2026 18:15"
        trade_date = ""
        if dt_str:
            try:
                dt = datetime.strptime(dt_str, "%d/%m/%Y %H:%M")
                trade_date = dt.strftime("%d%m%Y")  # matches XLSX internal format
            except ValueError:
                pass

        raw_bytes = _download_xlsx(file_link)
        if raw_bytes is None:
            continue

        df = parse_dts_xlsx(raw_bytes, issuer, product_type, trade_date)
        if not df.empty:
            frames.append(df)

        time.sleep(0.3)  # polite pacing

    return frames


# ---------------------------------------------------------------------------
# Store helpers
# ---------------------------------------------------------------------------

def _save_raw(df: pd.DataFrame, trade_date_str: str, product_type: str,
              data_root: Path | None = None) -> None:
    """Persist a daily snapshot to data/hk_cbbc/raw/YYYYMMDD_{type}.parquet."""
    raw = _raw_dir(data_root)
    raw.mkdir(parents=True, exist_ok=True)
    # Normalise trade date to YYYYMMDD
    td = trade_date_str
    if re.match(r"^\d{8}$", td):
        try:
            # If it's DDMMYYYY convert to YYYYMMDD for filename
            d = datetime.strptime(td, "%d%m%Y")
            td = d.strftime("%Y%m%d")
        except ValueError:
            pass
    path = raw / f"{td}_{product_type}.parquet"
    df.to_parquet(path, index=False)


def _save_latest(df: pd.DataFrame, product_type: str,
                 data_root: Path | None = None) -> None:
    """Overwrite the latest composite parquet."""
    p = _store_dir(data_root) / f"{product_type}_latest.parquet"
    _store_dir(data_root).mkdir(parents=True, exist_ok=True)
    df.to_parquet(p, index=False)


def _write_coverage(cbbc_rows: int, dw_rows: int, latest_date: str,
                    data_root: Path | None = None) -> None:
    p = _coverage_path(data_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "cbbc_rows": cbbc_rows,
        "dw_rows": dw_rows,
        "latest_trade_date": latest_date,
    }, indent=2))


def load_latest(product_type: str = "cbbc",
                data_root: Path | None = None) -> pd.DataFrame:
    """Load latest composite parquet. Returns empty DataFrame if missing."""
    p = _store_dir(data_root) / f"{product_type}_latest.parquet"
    if not p.exists():
        return pd.DataFrame(columns=_COLUMNS)
    try:
        return pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        log.warning("hk_cbbc: load_latest %s failed (%s)", product_type, e)
        return pd.DataFrame(columns=_COLUMNS)


def store_status(data_root: Path | None = None) -> dict:
    """Freshness stamp for render-lane health gating.

    Returns {available, cbbc_rows, dw_rows, latest_trade_date, fetched_at}.
    ``available`` is False when the store is missing/empty.
    """
    p = _coverage_path(data_root)
    if not p.exists():
        return {"available": False, "cbbc_rows": 0, "dw_rows": 0,
                "latest_trade_date": None, "fetched_at": None}
    try:
        d = json.loads(p.read_text())
        d["available"] = bool(d.get("cbbc_rows", 0) or d.get("dw_rows", 0))
        return d
    except Exception:  # noqa: BLE001
        return {"available": False, "cbbc_rows": 0, "dw_rows": 0,
                "latest_trade_date": None, "fetched_at": None}


# ---------------------------------------------------------------------------
# Main fetch entry point
# ---------------------------------------------------------------------------

def fetch_hk_cbbc(full_history: bool = False,
                  data_root: Path | None = None) -> dict:
    """Fetch CBBC + DW daily trading summaries and persist to store.

    Incremental (default): trailing _INCR_WINDOW_D days.
    Full history: trailing _BOOTSTRAP_WINDOW_D days.

    Returns {cbbc_rows, dw_rows, latest_trade_date}.
    Never raises — errors are logged and degrade gracefully.
    """
    today = date.today()
    back = _BOOTSTRAP_WINDOW_D if full_history else _INCR_WINDOW_D
    from_d = today - timedelta(days=back)
    to_d = today

    all_cbbc: list[pd.DataFrame] = []
    all_dw: list[pd.DataFrame] = []

    try:
        cbbc_frames = fetch_daily_dts("cbbc", from_d, to_d, data_root)
        all_cbbc.extend(cbbc_frames)
    except Exception as e:  # noqa: BLE001
        log.warning("hk_cbbc: CBBC fetch failed (%s)", e)

    try:
        dw_frames = fetch_daily_dts("dw", from_d, to_d, data_root)
        all_dw.extend(dw_frames)
    except Exception as e:  # noqa: BLE001
        log.warning("hk_cbbc: DW fetch failed (%s)", e)

    # Combine and save
    cbbc_df = pd.concat(all_cbbc, ignore_index=True) if all_cbbc else pd.DataFrame(columns=_COLUMNS)
    dw_df   = pd.concat(all_dw,   ignore_index=True) if all_dw   else pd.DataFrame(columns=_COLUMNS)

    latest_date = ""

    if not cbbc_df.empty:
        # Dedupe on (trade_date, stock_code, issuer) — keep last (freshest issuer file)
        cbbc_df = cbbc_df.drop_duplicates(
            subset=["trade_date", "stock_code", "issuer"], keep="last")
        # Save per-day raw snapshots
        for td_val, grp in cbbc_df.groupby("trade_date"):
            _save_raw(grp.reset_index(drop=True), str(td_val), "cbbc", data_root)
        # Save latest
        latest_td = cbbc_df["trade_date"].max()
        latest_date = str(latest_td)
        latest_cbbc = cbbc_df[cbbc_df["trade_date"] == latest_td].copy()
        _save_latest(latest_cbbc.reset_index(drop=True), "cbbc", data_root)
        log.info("hk_cbbc: CBBC %d rows, latest %s", len(cbbc_df), latest_td)

    if not dw_df.empty:
        dw_df = dw_df.drop_duplicates(
            subset=["trade_date", "stock_code", "issuer"], keep="last")
        for td_val, grp in dw_df.groupby("trade_date"):
            _save_raw(grp.reset_index(drop=True), str(td_val), "dw", data_root)
        latest_td_dw = dw_df["trade_date"].max()
        if not latest_date or latest_td_dw > latest_date:
            latest_date = str(latest_td_dw)
        latest_dw = dw_df[dw_df["trade_date"] == latest_td_dw].copy()
        _save_latest(latest_dw.reset_index(drop=True), "dw", data_root)
        log.info("hk_cbbc: DW %d rows, latest %s", len(dw_df), latest_td_dw)

    _write_coverage(len(cbbc_df), len(dw_df), latest_date, data_root)

    return {
        "cbbc_rows": len(cbbc_df),
        "dw_rows": len(dw_df),
        "latest_trade_date": latest_date,
    }


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------

class HkCbbcAdapter(Adapter):
    """Plugs the CBBC/DW daily fetch into the scripts/collect.py pipeline.

    Network I/O only in the collect lane. The render lane reads back via
    load_latest() / store_status() — pure parquet/JSON reads, no network.
    """

    name = "hk_cbbc"
    group = "hk_cbbc"
    stale_after_days = _STALE_DAYS

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        result = fetch_hk_cbbc(full_history=full_history)
        cbbc_df = load_latest("cbbc")
        # Return summary frame so run_adapter's staleness check works
        if cbbc_df.empty:
            # Degrade: return a sentinel so the adapter doesn't hard-fail
            log.warning("hk_cbbc: CBBC store empty after fetch (no data yet)")
            today = pd.Timestamp.today().normalize()
            summary = pd.DataFrame(
                {"cbbc_rows": [0], "dw_rows": [0]},
                index=[today])
            return {"cbbc__summary": summary}

        # Use the most recent date as the index so the staleness check works
        latest_date = cbbc_df["date"].dropna().max()
        if pd.isnull(latest_date):
            latest_date = pd.Timestamp.today().normalize()

        summary = pd.DataFrame(
            {"cbbc_rows": [result["cbbc_rows"]],
             "dw_rows": [result["dw_rows"]]},
            index=[pd.Timestamp(latest_date)])
        return {"cbbc__summary": summary}


# ---------------------------------------------------------------------------
# CLI / manual run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    import logging as _logging

    _logging.basicConfig(level=_logging.INFO,
                         format="%(levelname)s %(name)s %(message)s")
    ap = argparse.ArgumentParser(description="HKEX CBBC/DW daily outstanding collector (H-CBB)")
    ap.add_argument("--full-history", action="store_true",
                    help=f"Backfill trailing {_BOOTSTRAP_WINDOW_D} days")
    args = ap.parse_args()
    result = fetch_hk_cbbc(full_history=args.full_history)
    print(f"Done: {result}")
    cov = _coverage_path()
    if cov.exists():
        print(cov.read_text())
