"""scripts/fetch_finviz_screener.py — pull per-ticker Finviz industry classification.

Finviz's GICS-style sector→industry taxonomy is the source of the user's "subsectors". The
themes collector (scripts/fetch_finviz_themes.py) only pulls the narrative-theme treemap; this
one pulls the *screener* (the Overview view, v=111) for a given universe filter and parses the
per-row ``data-boxover-*`` tooltip attributes, which carry ticker / company / industry / country /
market-cap for every row. Sector is mapped from industry via the static FINVIZ_IND_TO_SECTOR table
(Finviz's taxonomy is stable; any unmapped industry falls back to "Other").

Usage:
    python -m scripts.fetch_finviz_screener --index ndx     # Nasdaq-100  (f=idx_ndx)
    python -m scripts.fetch_finviz_screener --index rut     # Russell-2000 (f=idx_rut)
    python -m scripts.fetch_finviz_screener --filter idx_sp500   # any raw f= filter

Writes data/finviz_screener/<filter>.json:
    {"filter": "idx_ndx", "as_of": "...", "n": 101,
     "rows": [{"ticker","company","industry","sector","country","market_cap_b"}...]}

Browser User-Agent passes Cloudflare (the python-requests UA is 403'd). EOD/static — politely
paced. Best-effort, never fatal: a failed page is retried then skipped with a logged gap.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from lib import config

log = logging.getLogger(__name__)

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
BASE = "https://finviz.com/screener.ashx?v=111&f={flt}&r={r}"
PER_PAGE = 20
OUT_DIR = "finviz_screener"

# Named-universe shortcuts → Finviz filter token.
INDEX_FILTER = {"ndx": "idx_ndx", "nasdaq": "idx_ndx", "rut": "idx_rut",
                "russell": "idx_rut", "sp500": "idx_sp500", "spx": "idx_sp500"}

# Finviz industry → Finviz sector. Covers the full Finviz industry taxonomy (~145 industries
# across the 11 Finviz sectors). Unmapped industries fall back to "Other" (logged).
FINVIZ_IND_TO_SECTOR: dict[str, str] = {
    # --- Technology ---
    "Semiconductors": "Technology", "Semiconductor Equipment & Materials": "Technology",
    "Software - Infrastructure": "Technology", "Software - Application": "Technology",
    "Information Technology Services": "Technology", "Communication Equipment": "Technology",
    "Computer Hardware": "Technology", "Consumer Electronics": "Technology",
    "Electronic Components": "Technology", "Scientific & Technical Instruments": "Technology",
    "Electronics & Computer Distribution": "Technology", "Solar": "Technology",
    # --- Communication Services ---
    "Internet Content & Information": "Communication Services",
    "Telecom Services": "Communication Services", "Entertainment": "Communication Services",
    "Electronic Gaming & Multimedia": "Communication Services",
    "Advertising Agencies": "Communication Services",
    "Broadcasting": "Communication Services", "Publishing": "Communication Services",
    # --- Consumer Cyclical ---
    "Internet Retail": "Consumer Cyclical", "Auto Manufacturers": "Consumer Cyclical",
    "Auto Parts": "Consumer Cyclical", "Auto & Truck Dealerships": "Consumer Cyclical",
    "Specialty Retail": "Consumer Cyclical", "Apparel Retail": "Consumer Cyclical",
    "Apparel Manufacturing": "Consumer Cyclical", "Footwear & Accessories": "Consumer Cyclical",
    "Home Improvement Retail": "Consumer Cyclical", "Restaurants": "Consumer Cyclical",
    "Lodging": "Consumer Cyclical", "Resorts & Casinos": "Consumer Cyclical",
    "Travel Services": "Consumer Cyclical", "Leisure": "Consumer Cyclical",
    "Gambling": "Consumer Cyclical", "Furnishings, Fixtures & Appliances": "Consumer Cyclical",
    "Residential Construction": "Consumer Cyclical", "Packaging & Containers": "Consumer Cyclical",
    "Personal Services": "Consumer Cyclical", "Recreational Vehicles": "Consumer Cyclical",
    "Textile Manufacturing": "Consumer Cyclical", "Department Stores": "Consumer Cyclical",
    "Luxury Goods": "Consumer Cyclical",
    # --- Consumer Defensive ---
    "Discount Stores": "Consumer Defensive", "Grocery Stores": "Consumer Defensive",
    "Beverages - Non-Alcoholic": "Consumer Defensive", "Beverages - Wineries & Distilleries": "Consumer Defensive",
    "Beverages - Brewers": "Consumer Defensive", "Confectioners": "Consumer Defensive",
    "Packaged Foods": "Consumer Defensive", "Farm Products": "Consumer Defensive",
    "Household & Personal Products": "Consumer Defensive", "Tobacco": "Consumer Defensive",
    "Food Distribution": "Consumer Defensive", "Education & Training Services": "Consumer Defensive",
    # --- Healthcare ---
    "Drug Manufacturers - General": "Healthcare", "Drug Manufacturers - Specialty & Generic": "Healthcare",
    "Biotechnology": "Healthcare", "Diagnostics & Research": "Healthcare",
    "Medical Devices": "Healthcare", "Medical Instruments & Supplies": "Healthcare",
    "Medical Care Facilities": "Healthcare", "Medical Distribution": "Healthcare",
    "Health Information Services": "Healthcare", "Healthcare Plans": "Healthcare",
    "Pharmaceutical Retailers": "Healthcare",
    # --- Financial ---
    "Banks - Diversified": "Financial", "Banks - Regional": "Financial",
    "Asset Management": "Financial", "Insurance - Life": "Financial",
    "Insurance - Property & Casualty": "Financial", "Insurance - Diversified": "Financial",
    "Insurance - Specialty": "Financial", "Insurance - Reinsurance": "Financial",
    "Insurance Brokers": "Financial", "Capital Markets": "Financial",
    "Financial Data & Stock Exchanges": "Financial", "Credit Services": "Financial",
    "Mortgage Finance": "Financial", "Financial Conglomerates": "Financial",
    "Shell Companies": "Financial",
    # --- Industrials ---
    "Aerospace & Defense": "Industrials", "Specialty Industrial Machinery": "Industrials",
    "Farm & Heavy Construction Machinery": "Industrials", "Industrial Distribution": "Industrials",
    "Building Products & Equipment": "Industrials", "Engineering & Construction": "Industrials",
    "Infrastructure Operations": "Industrials", "Specialty Business Services": "Industrials",
    "Consulting Services": "Industrials", "Staffing & Employment Services": "Industrials",
    "Security & Protection Services": "Industrials", "Conglomerates": "Industrials",
    "Electrical Equipment & Parts": "Industrials", "Tools & Accessories": "Industrials",
    "Railroads": "Industrials", "Trucking": "Industrials", "Integrated Freight & Logistics": "Industrials",
    "Airlines": "Industrials", "Airports & Air Services": "Industrials", "Marine Shipping": "Industrials",
    "Metal Fabrication": "Industrials", "Pollution & Treatment Controls": "Industrials",
    "Waste Management": "Industrials", "Rental & Leasing Services": "Industrials",
    "Business Equipment & Supplies": "Industrials",
    # --- Basic Materials ---
    "Specialty Chemicals": "Basic Materials", "Chemicals": "Basic Materials",
    "Agricultural Inputs": "Basic Materials", "Building Materials": "Basic Materials",
    "Steel": "Basic Materials", "Aluminum": "Basic Materials", "Copper": "Basic Materials",
    "Other Industrial Metals & Mining": "Basic Materials", "Gold": "Basic Materials",
    "Silver": "Basic Materials", "Other Precious Metals & Mining": "Basic Materials",
    "Coking Coal": "Basic Materials", "Lumber & Wood Production": "Basic Materials",
    "Paper & Paper Products": "Basic Materials",
    # --- Energy ---
    "Oil & Gas E&P": "Energy", "Oil & Gas Integrated": "Energy", "Oil & Gas Midstream": "Energy",
    "Oil & Gas Refining & Marketing": "Energy", "Oil & Gas Equipment & Services": "Energy",
    "Oil & Gas Drilling": "Energy", "Thermal Coal": "Energy", "Uranium": "Energy",
    # --- Utilities ---
    "Utilities - Regulated Electric": "Utilities", "Utilities - Regulated Gas": "Utilities",
    "Utilities - Regulated Water": "Utilities", "Utilities - Diversified": "Utilities",
    "Utilities - Independent Power Producers": "Utilities", "Utilities - Renewable": "Utilities",
    # --- Real Estate ---
    "REIT - Specialty": "Real Estate", "REIT - Industrial": "Real Estate",
    "REIT - Retail": "Real Estate", "REIT - Office": "Real Estate",
    "REIT - Residential": "Real Estate", "REIT - Healthcare Facilities": "Real Estate",
    "REIT - Hotel & Motel": "Real Estate", "REIT - Diversified": "Real Estate",
    "REIT - Mortgage": "Real Estate", "Real Estate Services": "Real Estate",
    "Real Estate - Development": "Real Estate", "Real Estate - Diversified": "Real Estate",
}

# data-boxover attrs on the ticker <td>: ticker / company / industry / country / value (mkt cap).
_ROW = re.compile(
    r'data-boxover-ticker="(?P<ticker>[^"]*)"\s*'
    r'data-boxover-company="(?P<company>[^"]*)"\s*'
    r'data-boxover-industry="(?P<industry>[^"]*)"\s*'
    r'data-boxover-country="(?P<country>[^"]*)"\s*'
    r'data-boxover-value="(?P<value>[^"]*)"')
_TOTAL = re.compile(r'#\d+\s*/\s*(\d+)\s*Total')


def _get(url: str, retries: int = 4, pause: float = 1.2) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    last = None
    for i in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                html = r.read().decode("utf-8", "replace")
            if "Just a moment" in html[:600] or "<title>Finviz Elite</title>" in html[:400]:
                raise RuntimeError("blocked/elite-wall")
            return html
        except Exception as e:  # noqa: BLE001 — network is best-effort
            last = e
            time.sleep(pause * (i + 1))
    raise RuntimeError(f"GET failed after {retries}: {url} ({last})")


def _unescape(s: str) -> str:
    return (s.replace("&amp;", "&").replace("&#39;", "'").replace("&quot;", '"')
             .replace("&lt;", "<").replace("&gt;", ">").strip())


def _mktcap_b(value: str) -> float | None:
    """Finviz market-cap string ('190.83B', '1.20T', '845.00M', '-') → billions float."""
    v = (value or "").strip().replace(",", "")
    if not v or v == "-":
        return None
    mult = {"T": 1000.0, "B": 1.0, "M": 0.001, "K": 1e-6}.get(v[-1].upper())
    try:
        return round(float(v[:-1]) * mult, 4) if mult else round(float(v), 4)
    except ValueError:
        return None


def fetch(flt: str, *, max_pages: int = 200, pause: float = 0.9) -> dict:
    """Walk the screener for filter ``flt`` and return the parsed classification payload."""
    rows: dict[str, dict] = {}
    total = None
    r = 1
    page = 0
    while page < max_pages:
        html = _get(BASE.format(flt=flt, r=r))
        if total is None:
            m = _TOTAL.search(html)
            total = int(m.group(1)) if m else None
            log.info("finviz screener %s: %s total", flt, total)
        n_before = len(rows)
        for m in _ROW.finditer(html):
            tk = _unescape(m.group("ticker")).upper()
            if not tk:
                continue
            ind = _unescape(m.group("industry"))
            rows[tk] = {
                "ticker": tk,
                "company": _unescape(m.group("company")),
                "industry": ind,
                "sector": FINVIZ_IND_TO_SECTOR.get(ind, "Other"),
                "country": _unescape(m.group("country")),
                "market_cap_b": _mktcap_b(m.group("value")),
            }
        got = len(rows) - n_before
        page += 1
        log.info("  page %d (r=%d): +%d rows (%d/%s)", page, r, got, len(rows), total)
        if got == 0:
            break
        if total is not None and len(rows) >= total:
            break
        r += PER_PAGE
        time.sleep(pause)

    unmapped = sorted({v["industry"] for v in rows.values()
                       if v["sector"] == "Other" and v["industry"]})
    if unmapped:
        log.warning("finviz screener %s: %d industries unmapped to sector: %s",
                    flt, len(unmapped), unmapped)
    return {
        "filter": flt,
        "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "n": len(rows),
        "total_reported": total,
        "unmapped_industries": unmapped,
        "rows": sorted(rows.values(), key=lambda x: (-(x["market_cap_b"] or 0), x["ticker"])),
    }


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(description="Fetch Finviz screener industry classification")
    ap.add_argument("--index", choices=sorted(INDEX_FILTER), help="named universe shortcut")
    ap.add_argument("--filter", dest="flt", help="raw Finviz f= filter token (e.g. idx_ndx)")
    ap.add_argument("--pause", type=float, default=0.9, help="seconds between pages")
    args = ap.parse_args()

    flt = args.flt or (INDEX_FILTER[args.index] if args.index else None)
    if not flt:
        ap.error("pass --index {ndx,rut,...} or --filter <token>")

    payload = fetch(flt, pause=args.pause)
    out = config.data_dir() / OUT_DIR / f"{flt}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=0, separators=(",", ":")))
    log.info("wrote %s — %d rows (%d reported)", out, payload["n"], payload["total_reported"] or -1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
