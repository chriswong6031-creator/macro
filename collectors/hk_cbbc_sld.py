"""HKEXnews Supplemental Listing Document (SLD) PDF call-price collector.

WHY
---
CBBC magnet-cluster analysis requires the mandatory call price per CBBC.
This is NOT available in the daily XLSX outstanding file — it is published
in the Supplemental Listing Document (SLD) at the time of issuance.

Mandatory call price semantics (sign-critical for magnet math):
  Bull CBBC: call price IS BELOW spot at issuance (mandatory-call fires when
             spot FALLS TO call price — issuer must sell the underlying to
             unwind the hedge → forced-sell magnet BELOW spot).
  Bear CBBC: call price IS ABOVE spot at issuance (mandatory-call fires when
             spot RISES TO call price — issuer must buy the underlying → forced-
             buy / short-squeeze magnet ABOVE spot).

Dense outstanding bull-CBBC calls clustered just under spot = forced-sell
cascade risk on breach. Dense bear-CBBC calls just above spot = forced-buy.

SOURCE
------
  HKEX News (www1.hkexnews.hk) titleSearchServlet:
    t1code=70000  Debt and Structured Products
    t2Gcode=22    CBBC
    t2code=73600  Supplemental Listing Document (PDF)

  ~145 PDFs/week. Each SLD covers 1–N CBBC stock codes issued on the same
  date by one issuer. The "Key Terms" table in every SLD contains:
    - CBBCs Stock Code(s) / CBBCs Stock code  — 5-digit HK structured product code
    - Type                                    — Bull | Bear
    - Company / Index                         — underlying name
    - Call Price (HK$) / Call Level           — mandatory call price per CBBC
    - Strike Price (HK$) / Strike Level       — strike price (optional; stored)
    - Entitlement / Number of CBBCs per Entitlement — ratio (optional; stored)

SCHEMA (verified against 4 live PDFs, 2026-07-08):
  • Equity CBBCs (BOCI layout): Key Terms table with columns per CBBC stock code
  • Index CBBCs (Citigroup/UBS layout): same layout, "Call Level" instead of "Call Price"
  • Multi-series PDFs: multiple columns in the Key Terms table (e.g. 5 stock codes)

EXTRACTION METHOD (verified 2026-07-08)
-----------------------------------------
  pdftotext -layout → text with spatial columns preserved.
  The "Key Terms" table is a wide table with one column per CBBC stock code.
  Extraction strategy:
    1. Find the "CBBCs Stock Code(s)" / "CBBCs Stock code" header line → read
       all 5-digit codes from that line.
    2. Positionally match the column positions of each code.
    3. For each of {Call Price (HK$), Call Level, Type, Company, Index,
       Strike Price (HK$), Strike Level}: find the matching row and split
       values at the same column positions.
  Fallback: plain-text regex for the compact single-series layout.

STORE
-----
  data/hk_cbbc/
    call_levels.parquet    — per structured-product stock code call level
                             (join key matches W1 outstanding data)
    sld_cache/             — one file per downloaded PDF (never re-fetched)
    sld_coverage.json      — freshness stamp

  Columns in call_levels.parquet:
    stock_code (str)        — 5-digit HKEX structured-product code
    call_price (float)      — mandatory call price or call level
    strike_price (float)    — strike price or level (may be None)
    bull_bear (str)         — 'bull' | 'bear'
    underlying_name (str)   — company name or index name (raw from PDF)
    issuer (str)            — issuer name (from SLD title)
    issue_date (str)        — YYYYMMDD (date of SLD filing)
    entitlement_ratio (float) — CBBCs per underlying unit (may be None)

FAIL-OPEN
---------
  • PDF download failure → log warning, skip that SLD.
  • pdftotext missing → log error, return empty (test environment graceful).
  • Parse failure on any SLD → log warning, skip (that CBBC absent from output).
  • Never raises into the collect pipeline.
  • Unparseable PDFs are noted in the coverage JSON.

CACHING
-------
  PDFs are persisted to sld_cache/ after first download (content-addressed by
  the last path component of FILE_LINK). Re-runs skip already-cached PDFs.
  Cache is permanent — SLD data does not change after issuance.

LANE CONTRACT
-------------
  Network I/O: collect lane ONLY.
  Render lane reads call_levels.parquet — no network.

RECENT WINDOW
-------------
  Fetches trailing _SLD_WINDOW_D days of SLD filings (default 30 days).
  This covers a full month of newly listed CBBCs. The call_levels store is
  append-only (deduplicated by stock_code, keeping newest).
"""
from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import tempfile
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

_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

_T1_CODE  = "70000"   # Debt and Structured Products
_CBBC_T2G = "22"      # CBBC group
_SLD_T2   = "73600"   # Supplemental Listing Document (PDF)

# Trailing window for SLD fetch (days)
_SLD_WINDOW_D = 30

# Stale threshold for the call_levels store
_STALE_DAYS = 3

# Max SLDs to download per run (rate-limiter; ~145/week so 200 is a month)
_MAX_PDFS_PER_RUN = 200

# Store paths
def _store_dir(data_root: Path | None = None) -> Path:
    if data_root is None:
        data_root = config.data_dir()
    return data_root / "hk_cbbc"

def _sld_cache_dir(data_root: Path | None = None) -> Path:
    return _store_dir(data_root) / "sld_cache"

def _call_levels_path(data_root: Path | None = None) -> Path:
    return _store_dir(data_root) / "call_levels.parquet"

def _sld_coverage_path(data_root: Path | None = None) -> Path:
    return _store_dir(data_root) / "sld_coverage.json"

# Canonical columns for call_levels.parquet
_CL_COLUMNS = [
    "stock_code",       # 5-digit str
    "call_price",       # float (HK$) or index level
    "strike_price",     # float (may be None)
    "bull_bear",        # 'bull' | 'bear'
    "underlying_name",  # company or index name
    "issuer",           # issuer name
    "issue_date",       # YYYYMMDD str
    "entitlement_ratio",# float (may be None)
]

# ---------------------------------------------------------------------------
# pdftotext availability check
# ---------------------------------------------------------------------------

def _pdftotext_available() -> bool:
    """Return True if pdftotext is on PATH."""
    return shutil.which("pdftotext") is not None


# ---------------------------------------------------------------------------
# PDF text extraction
# ---------------------------------------------------------------------------

def extract_pdf_text(pdf_bytes: bytes) -> str | None:
    """Extract text from PDF bytes using pdftotext -layout.

    Returns the text string, or None on failure (pdftotext missing or crash).
    Never raises.
    """
    if not _pdftotext_available():
        log.error("hk_cbbc_sld: pdftotext not found — SLD parsing unavailable")
        return None
    try:
        fd, tmp_path = tempfile.mkstemp(suffix=".pdf")
        try:
            import os
            with os.fdopen(fd, "wb") as fh:
                fh.write(pdf_bytes)
            result = subprocess.run(
                ["pdftotext", "-layout", tmp_path, "-"],
                capture_output=True, timeout=30,
            )
            if result.returncode != 0:
                log.warning("hk_cbbc_sld: pdftotext returned %d: %s",
                            result.returncode, result.stderr[:200])
                return None
            return result.stdout.decode("utf-8", errors="replace")
        finally:
            try:
                import os as _os
                _os.unlink(tmp_path)
            except OSError:
                pass
    except subprocess.TimeoutExpired:
        log.warning("hk_cbbc_sld: pdftotext timed out")
        return None
    except Exception as e:  # noqa: BLE001
        log.warning("hk_cbbc_sld: pdftotext exception: %s", e)
        return None


# ---------------------------------------------------------------------------
# SLD Key Terms table parser
# ---------------------------------------------------------------------------

def _clean_number(s: str) -> float | None:
    """Parse a numeric value from an SLD table cell.

    Handles commas (e.g. "23,500"), stripping currency prefixes (HK$, HKD).
    Returns None on failure.
    """
    s = str(s or "").strip()
    s = re.sub(r"HK\$?|HKD\s*", "", s, flags=re.I)
    s = s.replace(",", "").strip()
    # Handle ranges or expressions — take first number
    m = re.match(r"([\d]+\.?\d*)", s)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass
    return None


def _split_row_values(line: str, col_positions: list[int]) -> list[str]:
    """Split a text row into column values using nearest-column assignment.

    col_positions is a sorted list of x-start positions of each column
    (the positions of the stock code header tokens).

    Strategy: extract all non-whitespace tokens from the line (skipping
    the label portion before the first column), then assign each token to
    its nearest column by start position. This handles the common HKEX SLD
    layout where data values are centered differently from the column header.

    Returns a list of strings, one per column (empty string when a column
    has no data value).
    """
    if not col_positions:
        return [line.strip()]

    n_cols = len(col_positions)
    # Pre-fill with empty strings
    result: list[str] = [""] * n_cols

    # The label for this row lives before the first data column.
    # Skip everything before col_positions[0] - 5 (some slack for label bleed)
    label_end = max(0, col_positions[0] - 2)
    data_portion = line[label_end:]
    # Offset adjustment
    base_offset = label_end

    # Find all tokens (groups of non-whitespace) and their start positions
    for m in re.finditer(r'\S+', data_portion):
        token = m.group()
        abs_pos = base_offset + m.start()

        # Skip if this token is within the label zone
        if abs_pos < col_positions[0] - 2:
            continue

        # Assign to nearest column position
        best_idx = min(range(n_cols),
                       key=lambda i: abs(col_positions[i] - abs_pos))
        # Accumulate (multiple tokens may belong to same column, e.g. "HK$ 448.00")
        if result[best_idx]:
            result[best_idx] += " " + token
        else:
            result[best_idx] = token

    return result


def _find_col_positions(line: str, codes: list[str]) -> list[int] | None:
    """Find the character-column positions of each stock code in the header line.

    Returns a sorted list of x-positions (one per code), or None on failure.
    """
    positions = []
    for code in codes:
        idx = line.find(code)
        if idx < 0:
            return None
        positions.append(idx)
    return sorted(set(positions))  # deduplicate and sort


def parse_sld_text(text: str, issuer_name: str = "", issue_date: str = "") -> list[dict]:
    """Parse the Key Terms table from a pdftotext -layout extracted SLD text.

    Returns a list of dicts, one per CBBC stock code, with keys matching
    _CL_COLUMNS. Returns [] when parsing fails (fail-open).

    Layout is wide: multiple CBBCs per SLD (one column each), or a single
    CBBC. Handles equity CBBCs ("Call Price") and index CBBCs ("Call Level").

    Sign-correctness note:
      Bull CBBC: call_price < spot at issuance (magnet BELOW spot).
      Bear CBBC: call_price > spot at issuance (magnet ABOVE spot).
      We record the raw value from the PDF; sign interpretation is in the
      engine (magnet_below / magnet_above by bull_bear, not by arithmetic).
    """
    if not text:
        return []

    lines = text.splitlines()

    # --- Step 1: Find stock code header line ---
    # Pattern: "CBBCs Stock Code(s)  56106  56110  ..." or
    #          "CBBCs Stock code  55910"
    stock_code_line: str | None = None
    stock_code_line_idx: int = -1
    # Match lines with 5-digit numbers preceded by a stock-code header
    for i, line in enumerate(lines):
        if re.search(r"CBBCs?\s+Stock\s+[Cc]ode", line, re.I):
            codes_in_line = re.findall(r"\b(\d{5})\b", line)
            if codes_in_line:
                stock_code_line = line
                stock_code_line_idx = i
                break

    if stock_code_line is None:
        log.warning("hk_cbbc_sld: no stock code line found in SLD (issuer=%s)", issuer_name)
        return []

    # Extract stock codes (5-digit integers in that line)
    codes = re.findall(r"\b(\d{5})\b", stock_code_line)
    if not codes:
        return []

    # Find column x-positions of each code in the header line
    col_positions = _find_col_positions(stock_code_line, codes)
    if not col_positions:
        log.warning("hk_cbbc_sld: column positions not found for codes %s", codes)
        return []

    # --- Step 2: Scan subsequent lines for key fields ---
    # We only need lines until the next major section (which starts a new paragraph)
    # Limit scan to 80 lines after the header line to avoid runaway
    scan_end = min(stock_code_line_idx + 80, len(lines))
    segment = lines[stock_code_line_idx: scan_end]

    # Row data collectors
    row_data: dict[str, list[str | None]] = {
        "call_price":       [None] * len(codes),
        "strike_price":     [None] * len(codes),
        "bull_bear":        [None] * len(codes),
        "underlying_name":  [None] * len(codes),
        "entitlement_ratio":[None] * len(codes),
    }

    # Row label patterns to match
    _ROW_PATTERNS = [
        # (row_key, regex to match the row label)
        ("call_price",       re.compile(r"Call\s+(Price|Level)\s*[\(\[]?", re.I)),
        ("strike_price",     re.compile(r"Strike\s+(Price|Level)\s*[\(\[]?", re.I)),
        ("bull_bear",        re.compile(r"^\s*Type\b", re.I)),
        ("underlying_name",  re.compile(r"^\s*(Company|Index)\s*$", re.I)),
        ("entitlement_ratio",re.compile(r"Number of CBBCs per Entitlement|Entitlement\s+Ratio", re.I)),
    ]

    for line in segment:
        for row_key, pattern in _ROW_PATTERNS:
            if pattern.search(line):
                values = _split_row_values(line, col_positions)
                # First token is the label — skip it by using col_positions
                # but the label is before col_positions[0], so values align to codes
                # However: the label itself lives in col 0 if col_positions[0] > 0.
                # values already has len(col_positions) elements aligned to codes.
                for j, val in enumerate(values):
                    if j < len(codes) and row_data[row_key][j] is None:
                        row_data[row_key][j] = val.strip()
                break  # matched one pattern per line

    # --- Step 3: Also look for underlying name by fallback patterns ---
    # Sometimes "Company" or "Index" appears on a different line
    for row_key in ["underlying_name", "bull_bear"]:
        # If we still have Nones, scan again with a more permissive match
        if any(v is None for v in row_data[row_key]):
            for line in segment:
                if row_key == "underlying_name":
                    m = re.match(r"^\s*(?:Company|Index)\s{2,}(.+)", line, re.I)
                    if m:
                        raw = m.group(1).strip()
                        names = _split_row_values(raw, col_positions) if col_positions else [raw]
                        for j, val in enumerate(names):
                            if j < len(codes) and row_data["underlying_name"][j] is None:
                                row_data["underlying_name"][j] = val.strip() or raw
                elif row_key == "bull_bear":
                    m = re.match(r"^\s*Type\s{2,}(Bull|Bear)", line, re.I)
                    if m:
                        raw = m.group(0)
                        # Read all Bull/Bear tokens from the line
                        tokens = re.findall(r"\b(Bull|Bear)\b", line, re.I)
                        for j, tok in enumerate(tokens):
                            if j < len(codes) and row_data["bull_bear"][j] is None:
                                row_data["bull_bear"][j] = tok.lower()

    # --- Step 4: Assemble output records ---
    out = []
    for j, code in enumerate(codes):
        call_raw  = row_data["call_price"][j]
        call_val  = _clean_number(call_raw)
        if call_val is None:
            log.warning("hk_cbbc_sld: no call price for stock_code=%s in issuer=%s",
                        code, issuer_name)
            # Fail-open: skip this code rather than fabricate
            continue

        strike_raw = row_data["strike_price"][j]
        strike_val = _clean_number(strike_raw)

        bb_raw = row_data["bull_bear"][j] or ""
        bull_bear = "bull" if re.search(r"\bbull\b", bb_raw, re.I) else (
                    "bear" if re.search(r"\bbear\b", bb_raw, re.I) else "unknown")

        underlying = str(row_data["underlying_name"][j] or "").strip()

        ent_raw = row_data["entitlement_ratio"][j]
        ent_val = _clean_number(ent_raw)

        out.append({
            "stock_code":        code,
            "call_price":        call_val,
            "strike_price":      strike_val,
            "bull_bear":         bull_bear,
            "underlying_name":   underlying,
            "issuer":            issuer_name[:80],
            "issue_date":        issue_date,
            "entitlement_ratio": ent_val,
        })

    return out


# ---------------------------------------------------------------------------
# Servlet helpers
# ---------------------------------------------------------------------------

def _query_sld_servlet(from_d: date, to_d: date,
                       row_range: int = 200, timeout: int = 30,
                       retries: int = 3) -> list[dict]:
    """Fetch SLD rows from the HKEX News titleSearchServlet. Returns [] on failure."""
    params = {
        "sortDir": "0", "sortByOptions": "DateTime",
        "category": "0", "market": "SEHK", "stockId": "-1",
        "documentType": "-1",
        "fromDate": from_d.strftime("%Y%m%d"),
        "toDate": to_d.strftime("%Y%m%d"),
        "title": "", "searchType": "1",
        "t1code": _T1_CODE, "t2Gcode": _CBBC_T2G, "t2code": _SLD_T2,
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
                log.warning("hk_cbbc_sld: servlet attempt %d/%d failed (%s); retry %.0fs",
                            attempt + 1, retries, e, wait)
                time.sleep(wait)
    log.warning("hk_cbbc_sld: servlet failed after %d attempts: %s", retries, last)
    return []


def _download_pdf(file_link: str, timeout: int = 30) -> bytes | None:
    """Download a PDF from HKEX News. Returns None on failure."""
    url = _BASE_URL + file_link
    try:
        r = requests.get(url, timeout=timeout,
                         headers={"User-Agent": _BROWSER_UA,
                                  "Referer": _BASE_URL + "/"})
        r.raise_for_status()
        return r.content
    except Exception as e:  # noqa: BLE001
        log.warning("hk_cbbc_sld: PDF download failed %s: %s", url, e)
        return None


def _issuer_from_title(title: str) -> str:
    """Extract a short issuer name from the SLD announcement title."""
    cleaned = re.sub(r"&#x[0-9a-fA-F]+;", "/", title)
    parts = re.split(r"\s*[-–—]\s*", cleaned, maxsplit=1)
    return parts[0].strip()[:80] if parts else title[:80]


def _cache_key(file_link: str) -> str:
    """Derive a cache filename from the file_link path (last component)."""
    return Path(file_link).name  # e.g. "2026070800848.pdf"


# ---------------------------------------------------------------------------
# Main fetch function
# ---------------------------------------------------------------------------

def fetch_sld_call_levels(data_root: Path | None = None,
                          window_days: int = _SLD_WINDOW_D) -> dict:
    """Fetch SLD PDFs for the trailing window and extract call prices.

    Returns {new_pdfs, parsed_records, stock_codes_parsed, stock_codes_failed}.
    Never raises.
    """
    today = date.today()
    from_d = today - timedelta(days=window_days)
    to_d   = today

    cache_dir = _sld_cache_dir(data_root)
    cache_dir.mkdir(parents=True, exist_ok=True)

    rows = _query_sld_servlet(from_d, to_d, row_range=_MAX_PDFS_PER_RUN)
    if not rows:
        log.info("hk_cbbc_sld: no SLD rows returned for %s..%s", from_d, to_d)
        return _write_empty_results(data_root)

    all_records: list[dict] = []
    new_pdfs = 0
    failed_codes = 0

    for row in rows:
        file_link = row.get("FILE_LINK", "")
        if not file_link or not file_link.lower().endswith(".pdf"):
            continue

        ckey = _cache_key(file_link)
        cached_path = cache_dir / ckey

        # Use cached PDF if available
        if cached_path.exists():
            pdf_bytes = cached_path.read_bytes()
        else:
            pdf_bytes = _download_pdf(file_link)
            if pdf_bytes is None:
                continue
            # Persist to cache
            try:
                cached_path.write_bytes(pdf_bytes)
            except OSError as e:
                log.warning("hk_cbbc_sld: cache write failed for %s: %s", ckey, e)
            new_pdfs += 1
            time.sleep(0.3)  # polite pacing

        title = row.get("TITLE", "")
        issuer = _issuer_from_title(title)

        dt_str = row.get("DATE_TIME", "")  # e.g. "08/07/2026 18:15"
        issue_date = ""
        if dt_str:
            try:
                dt = datetime.strptime(dt_str, "%d/%m/%Y %H:%M")
                issue_date = dt.strftime("%Y%m%d")
            except ValueError:
                pass

        # Extract text from PDF
        text = extract_pdf_text(pdf_bytes)
        if text is None:
            log.warning("hk_cbbc_sld: PDF text extraction failed for %s", ckey)
            failed_codes += 1
            continue

        # Parse Key Terms table
        records = parse_sld_text(text, issuer_name=issuer, issue_date=issue_date)
        if records:
            all_records.extend(records)
            log.debug("hk_cbbc_sld: %s → %d CBBC records", ckey, len(records))
        else:
            log.warning("hk_cbbc_sld: no records parsed from %s (issuer=%s)",
                        ckey, issuer)
            failed_codes += 1

    # Persist call_levels.parquet (append dedup: newest wins per stock_code)
    if all_records:
        new_df = pd.DataFrame(all_records, columns=_CL_COLUMNS)
        existing = _load_call_levels(data_root)
        if not existing.empty:
            # Combine; for duplicate stock_code keep the row from the newest SLD
            combined = pd.concat([existing, new_df], ignore_index=True)
            # Sort by issue_date ascending so the latest row wins on dedup
            combined = combined.sort_values("issue_date", ascending=True)
            combined = combined.drop_duplicates(subset=["stock_code"], keep="last")
        else:
            combined = new_df.drop_duplicates(subset=["stock_code"], keep="last")

        _store_dir(data_root).mkdir(parents=True, exist_ok=True)
        combined.to_parquet(_call_levels_path(data_root), index=False)
        log.info("hk_cbbc_sld: %d total call levels in store (%d new records from %d PDFs)",
                 len(combined), len(all_records), len(rows))
    else:
        log.info("hk_cbbc_sld: no new records parsed (already cached or no data)")
        combined = _load_call_levels(data_root)

    # Write coverage JSON
    _write_sld_coverage(
        n_records=len(combined) if not combined.empty else 0,
        n_new_pdfs=new_pdfs,
        n_failed=failed_codes,
        data_root=data_root,
    )

    return {
        "new_pdfs": new_pdfs,
        "parsed_records": len(all_records),
        "stock_codes_parsed": len(combined) if not combined.empty else 0,
        "stock_codes_failed": failed_codes,
    }


def _write_empty_results(data_root: Path | None) -> dict:
    _write_sld_coverage(0, 0, 0, data_root)
    return {"new_pdfs": 0, "parsed_records": 0,
            "stock_codes_parsed": 0, "stock_codes_failed": 0}


def _write_sld_coverage(n_records: int, n_new_pdfs: int, n_failed: int,
                        data_root: Path | None = None) -> None:
    p = _sld_coverage_path(data_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "call_levels_in_store": n_records,
        "new_pdfs_this_run": n_new_pdfs,
        "failed_pdfs": n_failed,
    }, indent=2))


# ---------------------------------------------------------------------------
# Load helpers (render-lane: no network)
# ---------------------------------------------------------------------------

def _load_call_levels(data_root: Path | None = None) -> pd.DataFrame:
    """Load call_levels.parquet. Returns empty DataFrame if missing/corrupt."""
    p = _call_levels_path(data_root)
    if not p.exists():
        return pd.DataFrame(columns=_CL_COLUMNS)
    try:
        return pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        log.warning("hk_cbbc_sld: call_levels load failed (%s)", e)
        return pd.DataFrame(columns=_CL_COLUMNS)


# Public alias used by engine
load_call_levels = _load_call_levels


def sld_store_status(data_root: Path | None = None) -> dict:
    """Coverage JSON for render-lane freshness gating."""
    p = _sld_coverage_path(data_root)
    if not p.exists():
        return {"available": False, "call_levels_in_store": 0}
    try:
        d = json.loads(p.read_text())
        d["available"] = bool(d.get("call_levels_in_store", 0))
        return d
    except Exception:  # noqa: BLE001
        return {"available": False, "call_levels_in_store": 0}


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------

class HkCbbcSldAdapter(Adapter):
    """Collector adapter for the SLD call-price harvest.

    Group: hk_cbbc (same group as the daily XLSX collector, runs in same lane).
    """

    name = "hk_cbbc_sld"
    group = "hk_cbbc"
    stale_after_days = _STALE_DAYS

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        window = _SLD_WINDOW_D * 3 if full_history else _SLD_WINDOW_D
        result = fetch_sld_call_levels(window_days=window)
        cl_df = _load_call_levels()
        if cl_df.empty:
            log.warning("hk_cbbc_sld: call_levels store empty after fetch")
            today = pd.Timestamp.today().normalize()
            summary = pd.DataFrame(
                {"sld_records": [0], "failed": [result.get("stock_codes_failed", 0)]},
                index=[today])
            return {"cbbc_sld__summary": summary}

        today = pd.Timestamp.today().normalize()
        summary = pd.DataFrame(
            {"sld_records": [len(cl_df)],
             "failed": [result.get("stock_codes_failed", 0)]},
            index=[today])
        return {"cbbc_sld__summary": summary}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    import logging as _logging

    _logging.basicConfig(level=_logging.INFO, format="%(levelname)s %(name)s %(message)s")
    ap = argparse.ArgumentParser(description="HKEXnews SLD call-price collector (CBBC W2)")
    ap.add_argument("--full-history", action="store_true",
                    help=f"Fetch trailing {_SLD_WINDOW_D * 3} days (3x window)")
    args = ap.parse_args()
    result = fetch_sld_call_levels(
        window_days=_SLD_WINDOW_D * 3 if args.full_history else _SLD_WINDOW_D)
    print(f"Done: {result}")
