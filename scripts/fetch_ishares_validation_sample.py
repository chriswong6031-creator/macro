"""Fetch iShares LQD and HYG validation sample for CCW W2.

One-shot script — NOT wired into any workflow (orchestrator/operator runs manually).
Fetches full holdings workbooks from iShares product pages, parses SpreadsheetML XML,
and freezes validation parquets at:
  data/corp_bonds/validation_sample/LQD_<asof>.parquet
  data/corp_bonds/validation_sample/HYG_<asof>.parquet

playwright is imported INSIDE fetch functions only — NOT at module level.
CI and engine tests must be able to import parse_spreadsheetml without playwright installed.
The parse function is importable and unit-testable without playwright.

Usage
-----
  python scripts/fetch_ishares_validation_sample.py
  python scripts/fetch_ishares_validation_sample.py --raw-dir /path/to/xml_files

Options
-------
  --raw-dir DIR    Parse pre-downloaded .xml/.bin files instead of fetching.
  --out-dir DIR    Override output directory (default: data/corp_bonds/validation_sample).
  --fund LQD|HYG  Fetch only one fund (default: both).
"""
from __future__ import annotations

import argparse
import logging
import re
import sys
import xml.etree.ElementTree as ET
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# iShares product page URLs and portfolio IDs
# ---------------------------------------------------------------------------

FUNDS = {
    "LQD": {
        "portfolioId": "239566",
        "url": "https://www.ishares.com/us/products/239566/ishares-iboxx-investment-grade-corporate-bond-etf",
    },
    "HYG": {
        "portfolioId": "239565",
        "url": "https://www.ishares.com/us/products/239565/ishares-iboxx-high-yield-corporate-bond-etf",
    },
}

# SpreadsheetML namespace
_SS_NS = "urn:schemas-microsoft-com:office:spreadsheet"
_SS_TAG = lambda tag: f"{{{_SS_NS}}}{tag}"

# Output schema (no isin — real iShares workbook has no ISIN/CUSIP/SEDOL columns)
OUT_COLS = [
    "name", "sector", "clean_price", "ytm_pct", "ytw_pct", "ytc_pct",
    "duration", "mod_duration", "accrual_date", "coupon", "maturity",
    "weight_pct", "par_value", "market_value", "as_of",
]

# Exact header column → output column mapping (matched against exact lowercased header values)
# Real iShares header (exact, 2026-07-13 format):
#   Name | Sector | Asset Class | Market Value | Weight (%) | Notional Value | Par Value |
#   Price | Location | Exchange | Currency | Duration | YTM (%) | FX Rate | Maturity |
#   Coupon (%) | Mod. Duration | Yield to Call (%) | Yield to Worst (%) | Real Duration |
#   Real YTM (%) | Market Currency | Accrual Date | Effective Date
_HEADER_MAP_EXACT: dict[str, str] = {
    "name": "name",
    "sector": "sector",
    "asset class": "asset_class",
    "market value": "market_value",
    "weight (%)": "weight_pct",
    "par value": "par_value",
    "price": "clean_price",
    "duration": "duration",
    "ytm (%)": "ytm_pct",
    "maturity": "maturity",
    "coupon (%)": "coupon",
    "mod. duration": "mod_duration",
    "yield to call (%)": "ytc_pct",
    "yield to worst (%)": "ytw_pct",
    "accrual date": "accrual_date",
}

_FUND_DOC_URL_RE = re.compile(
    r"https://www\.blackrock\.com/varnish-api/[^\s\"'<>]*get-fund-document[^\s\"'<>]*"
    r"component=fundDownload[^\s\"'<>]*"
)


def _find_download_url(html: str) -> str | None:
    """Extract the first fundDownload URL from iShares product page HTML."""
    # Search for the download URL pattern; unescape &amp; → &
    match = _FUND_DOC_URL_RE.search(html)
    if match:
        url = match.group(0)
        url = url.replace("&amp;", "&").rstrip("\"'")
        return url
    # Try HTML-entity version
    html_unescaped = html.replace("&amp;", "&")
    match2 = _FUND_DOC_URL_RE.search(html_unescaped)
    if match2:
        return match2.group(0).rstrip("\"'")
    return None


def _parse_date_iso(s: str, formats: list[str]) -> str | None:
    """Try each format in order; return ISO date string or None."""
    s = s.strip()
    for fmt in formats:
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return None


def _null_str(s: str) -> bool:
    """Return True for iShares null markers ('--', '-', '', 'N/A')."""
    return s.strip() in ("--", "-", "", "N/A")


# ---------------------------------------------------------------------------
# SpreadsheetML parser (no playwright dependency)
# ---------------------------------------------------------------------------

def parse_spreadsheetml(content: bytes, fund: str = "UNKNOWN") -> tuple[pd.DataFrame, str]:
    """Parse iShares SpreadsheetML (XML) holdings workbook.

    Real format (2026-07 empirical):
      - Worksheets: Disclaimers / Holdings / Historical / Performance / Distributions
      - Holdings preamble: row0 = file date, row3 = ["Fund Holdings as of", "Jul 13, 2026"]
      - Header row: first row whose first cell == "Name" (exact)
      - Header columns include no ISIN/CUSIP; bond filter = Asset Class == "Fixed Income"
      - Maturity format: "Feb 01, 2046"; numerics carry commas; "--"/"-" = null

    Parameters
    ----------
    content : bytes
        Raw .xml/.bin file content (SpreadsheetML format).
    fund : str
        Fund ticker for logging.

    Returns
    -------
    (df, as_of_str)
        df : DataFrame with OUT_COLS columns (Fixed Income rows only)
        as_of_str : ISO date string of the holdings date, or today's date if not found
    """
    # Strip BOM if present
    if content.startswith(b"\xef\xbb\xbf"):
        content = content[3:]

    # BlackRock's SpreadsheetML is not well-formed: disclaimer URLs carry bare
    # ampersands (…#!type=ishares&style=All…). Escape any & that does not start
    # a valid entity before handing to the strict stdlib parser.
    content = re.sub(
        rb"&(?!(?:amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)", b"&amp;", content
    )

    try:
        root_elem = ET.fromstring(content)
    except ET.ParseError as exc:
        raise ValueError(f"XML parse failed for {fund}: {exc}") from exc

    # Find the "Holdings" worksheet
    holdings_ws = None
    for ws in root_elem.iter(_SS_TAG("Worksheet")):
        ws_name = ws.get(_SS_TAG("Name"), "")
        if "holding" in ws_name.lower():
            holdings_ws = ws
            break

    if holdings_ws is None:
        # Fallback: try first worksheet
        for ws in root_elem.iter(_SS_TAG("Worksheet")):
            holdings_ws = ws
            break

    if holdings_ws is None:
        raise ValueError(f"No Holdings worksheet found in {fund} workbook")

    # Extract all rows
    table = holdings_ws.find(_SS_TAG("Table"))
    if table is None:
        raise ValueError(f"No Table element found in {fund} Holdings worksheet")

    all_rows: list[list[str]] = []
    for row_elem in table.iter(_SS_TAG("Row")):
        cells = []
        for cell in row_elem.iter(_SS_TAG("Cell")):
            data_elem = cell.find(_SS_TAG("Data"))
            if data_elem is not None:
                cells.append(data_elem.text or "")
            else:
                cells.append("")
        all_rows.append(cells)

    # -----------------------------------------------------------------------
    # as_of: look for preamble row ["Fund Holdings as of", "<date>"] in first 20 rows.
    # The second cell holds a date like "Jul 13, 2026".
    # -----------------------------------------------------------------------
    as_of_str = str(date.today())
    as_of_found = False
    _date_fmts = ["%b %d, %Y", "%B %d, %Y", "%m/%d/%Y", "%Y-%m-%d"]
    for row in all_rows[:20]:
        if len(row) >= 2 and "fund holdings as of" in str(row[0]).lower():
            parsed = _parse_date_iso(str(row[1]), _date_fmts)
            if parsed:
                as_of_str = parsed
                as_of_found = True
            break
    if not as_of_found:
        # Fallback: scan cell text for "as of"
        for row in all_rows[:20]:
            for cell in row:
                cell_str = str(cell)
                if "as of" in cell_str.lower():
                    date_m = re.search(r"(\w+ \d+,?\s*\d{4}|\d{1,2}/\d{1,2}/\d{4})", cell_str)
                    if date_m:
                        parsed = _parse_date_iso(date_m.group(1), _date_fmts)
                        if parsed:
                            as_of_str = parsed
                            as_of_found = True
                    break
            if as_of_found:
                break
        if not as_of_found:
            log.warning("fetch_ishares: could not find as-of date for %s; using today", fund)

    # -----------------------------------------------------------------------
    # Header row: first row whose first cell is exactly "Name"
    # -----------------------------------------------------------------------
    header_row_idx: int | None = None
    col_map: dict[int, str] = {}  # column_index → output_column_name

    for row_idx, row in enumerate(all_rows):
        if row and str(row[0]).strip() == "Name":
            header_row_idx = row_idx
            for col_idx, cell in enumerate(row):
                key = str(cell).strip().lower()
                if key in _HEADER_MAP_EXACT:
                    mapped = _HEADER_MAP_EXACT[key]
                    if mapped not in col_map.values():
                        col_map[col_idx] = mapped
            break

    if header_row_idx is None:
        log.warning("fetch_ishares: no header row (first cell == 'Name') found for %s", fund)
        return pd.DataFrame(columns=OUT_COLS), as_of_str

    # Locate Asset Class column index for filtering
    ac_col_idx: int | None = None
    for col_idx, cell in enumerate(all_rows[header_row_idx]):
        if str(cell).strip().lower() == "asset class":
            ac_col_idx = col_idx
            break

    # -----------------------------------------------------------------------
    # Parse data rows; keep only Asset Class == "Fixed Income"
    # -----------------------------------------------------------------------
    records: list[dict[str, Any]] = []
    for row in all_rows[header_row_idx + 1:]:
        if not row:
            continue

        # Asset Class filter
        if ac_col_idx is not None:
            ac_val = row[ac_col_idx] if ac_col_idx < len(row) else ""
            if str(ac_val).strip() != "Fixed Income":
                continue

        rec: dict[str, Any] = {}
        for col_idx, col_name in col_map.items():
            if col_name == "asset_class":
                continue  # internal filter key, not output
            raw = row[col_idx].strip() if col_idx < len(row) else ""
            rec[col_name] = None if _null_str(raw) else raw

        records.append(rec)

    if not records:
        log.warning("fetch_ishares: no Fixed Income rows found for %s", fund)
        return pd.DataFrame(columns=OUT_COLS), as_of_str

    df = pd.DataFrame(records)

    # -----------------------------------------------------------------------
    # Numeric coercion: strip commas then pd.to_numeric
    # -----------------------------------------------------------------------
    _numeric_cols = [
        "clean_price", "ytm_pct", "ytw_pct", "ytc_pct", "duration",
        "mod_duration", "coupon", "weight_pct", "par_value", "market_value",
    ]
    for col in _numeric_cols:
        if col in df.columns:
            df[col] = (
                df[col]
                .astype(str)
                .str.replace(",", "", regex=False)
                .replace("None", float("nan"))
            )
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # -----------------------------------------------------------------------
    # Maturity: parse "Feb 01, 2046" → ISO "2046-02-01"
    # -----------------------------------------------------------------------
    if "maturity" in df.columns:
        def _mat_to_iso(v: Any) -> str | None:
            if v is None:
                return None
            if isinstance(v, float):
                import math as _m
                if _m.isnan(v):
                    return None
            s = str(v).strip()
            if not s or _null_str(s):
                return None
            for fmt in ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d", "%m/%d/%Y"):
                try:
                    return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
                except ValueError:
                    pass
            return s  # return as-is if no format matched (caller will see non-ISO)

        df["maturity"] = df["maturity"].apply(_mat_to_iso)

    # -----------------------------------------------------------------------
    # Accrual date: parse "Feb 01, 2019" → ISO
    # -----------------------------------------------------------------------
    if "accrual_date" in df.columns:
        def _dt_to_iso(v: Any) -> str | None:
            if v is None:
                return None
            s = str(v).strip()
            if not s or _null_str(s):
                return None
            for fmt in ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d", "%m/%d/%Y"):
                try:
                    return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
                except ValueError:
                    pass
            return None

        df["accrual_date"] = df["accrual_date"].apply(_dt_to_iso)

    # -----------------------------------------------------------------------
    # Finalize output schema
    # -----------------------------------------------------------------------
    df["as_of"] = as_of_str

    for col in OUT_COLS:
        if col not in df.columns:
            df[col] = None

    df = df[OUT_COLS]
    log.info("fetch_ishares: %s: parsed %d Fixed Income rows (as_of=%s)", fund, len(df), as_of_str)
    return df, as_of_str


# ---------------------------------------------------------------------------
# Fetch via playwright (import inside function only)
# ---------------------------------------------------------------------------

def _fetch_fund_workbook(fund: str, portfolio_id: str, product_url: str) -> bytes:
    """Download the iShares holdings workbook for one fund.

    Uses playwright chromium headless. Import is INSIDE this function — do not
    move to module level (CI must not require playwright).
    """
    from playwright.sync_api import sync_playwright  # noqa: PLC0415 — intentional late import

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        )
        page = context.new_page()
        log.info("fetch_ishares: navigating to %s", product_url)
        page.goto(product_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(4000)  # wait for JS rendering

        html = page.content()
        download_url = _find_download_url(html)
        if download_url is None:
            # Try direct API URL construction
            download_url = (
                f"https://www.blackrock.com/us/individual/products/{portfolio_id}/"
                f"fund-download?fileType=xls&fileName={fund}_fund_holdings&dataType=fund"
            )
            log.warning(
                "fetch_ishares: fundDownload URL not found in page HTML for %s; "
                "falling back to constructed URL: %s",
                fund, download_url,
            )
        else:
            log.info("fetch_ishares: found download URL for %s", fund)

        # Download the workbook
        response = page.request.get(download_url, timeout=60000)
        if response.status != 200:
            raise RuntimeError(
                f"fetch_ishares: {fund} download returned HTTP {response.status}: {download_url}"
            )
        content = response.body()
        log.info("fetch_ishares: %s: downloaded %d bytes", fund, len(content))
        browser.close()
        return content


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def fetch_and_save(
    fund: str,
    raw_dir: Path | None = None,
    out_dir: Path | None = None,
) -> str | None:
    """Fetch or parse one fund; write the validation sample parquet.

    Returns the output path on success, None on failure.
    """
    if out_dir is None:
        _here = Path(__file__).resolve().parent.parent
        out_dir = _here / "data" / "corp_bonds" / "validation_sample"
    out_dir.mkdir(parents=True, exist_ok=True)

    fund_info = FUNDS[fund]

    if raw_dir is not None:
        # Parse pre-downloaded file
        candidates = list(raw_dir.glob(f"{fund}*.xml")) + list(raw_dir.glob(f"{fund}*.bin"))
        if not candidates:
            log.error("fetch_ishares: no pre-downloaded file for %s in %s", fund, raw_dir)
            return None
        raw_path = candidates[-1]
        log.info("fetch_ishares: parsing pre-downloaded file %s", raw_path)
        content = raw_path.read_bytes()
    else:
        try:
            content = _fetch_fund_workbook(
                fund, fund_info["portfolioId"], fund_info["url"]
            )
        except Exception as exc:  # noqa: BLE001
            log.error("fetch_ishares: %s fetch failed: %s", fund, exc)
            return None

    try:
        df, as_of_str = parse_spreadsheetml(content, fund)
    except Exception as exc:  # noqa: BLE001
        log.error("fetch_ishares: %s parse failed: %s", fund, exc)
        return None

    if df.empty:
        log.warning("fetch_ishares: %s: empty DataFrame, skipping write", fund)
        return None

    out_path = out_dir / f"{fund}_{as_of_str}.parquet"
    df.to_parquet(out_path, index=False)
    print(f"  {fund}: {len(df)} rows → {out_path}")
    return str(out_path)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch iShares LQD/HYG validation sample for CCW W2"
    )
    parser.add_argument(
        "--raw-dir",
        default=None,
        help="Parse pre-downloaded .xml/.bin files from this directory instead of fetching",
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        help="Output directory (default: data/corp_bonds/validation_sample)",
    )
    parser.add_argument(
        "--fund",
        choices=["LQD", "HYG"],
        default=None,
        help="Fetch only one fund (default: both)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s %(message)s",
    )

    raw_dir = Path(args.raw_dir) if args.raw_dir else None
    out_dir = Path(args.out_dir) if args.out_dir else None
    funds = [args.fund] if args.fund else list(FUNDS.keys())

    ok = 0
    for fund in funds:
        result = fetch_and_save(fund, raw_dir=raw_dir, out_dir=out_dir)
        if result:
            ok += 1

    print(f"fetch_ishares: {ok}/{len(funds)} funds saved successfully")
    return 0 if ok > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
