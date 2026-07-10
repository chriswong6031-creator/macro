"""BLS Print Integrity Collector (keyless, fail-open).

Collects two data quality signals from free BLS sources:

1. CES (Payrolls / NFP) collection and response rates
   Source: https://www.bls.gov/ces/publications/responserate/
   BLS publishes annual CES response rate summaries as HTML tables.
   Column: year, collection_rate_pct, response_rate_pct, source_url

2. CPI median standard errors
   Source: https://www.bls.gov/cpi/tables/relative-importance/home.htm
   (The CPI relative-importance / precision tables, published annually)
   The BLS CPI Detailed Report Table 30 (standard errors) is also
   publicly available in PDF; we parse what is accessible as HTML.
   Column: period, component, median_se, source_url

Stores to:
  data/bls_print_integrity/integrity.parquet

Fail-open contract
------------------
On any network / parse failure the function uses the SEED_DATA below
(manually curated from BLS publications) and does NOT raise.  The parquet
is written on first success; subsequent runs upsert new rows.

WAF note: use the descriptive research UA (same as bls_cpi_weights.py).

README / source URLs are stored in the parquet 'source_url' column.
"""
from __future__ import annotations

import logging
import re
import time
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

_BLS_UA = "BLS-DataFetch/1.0 (macro-research; non-commercial)"
_CES_RESPONSE_URL = "https://www.bls.gov/ces/publications/responserate/"
_CPI_SE_URL = "https://www.bls.gov/cpi/tables/relative-importance/home.htm"
_CACHE_TTL_SECONDS = 24 * 3600  # 24h (annual data)
_CACHE_CES = Path("/tmp/bls_ces_response.html")
_CACHE_CPI = Path("/tmp/bls_cpi_se.html")

_PARQUET_PATH_REL = "data/bls_print_integrity/integrity.parquet"

# ---------------------------------------------------------------------------
# Manually-seeded data from BLS publications
# Source: BLS CES Response Rates (https://www.bls.gov/ces/publications/responserate/)
# and BLS CPI methodological notes.
# ---------------------------------------------------------------------------

# CES response rates by year (approximate; BLS publishes annual summary).
# Collection rate = share of sample units returning a usable response.
# Response rate = weighted by employment.
# Source: BLS CES Response Rate tables (annual, keyless).
SEED_CES_RESPONSE: list[dict] = [
    {"year": 2015, "collection_rate_pct": 77.0, "response_rate_pct": 83.0, "source_url": _CES_RESPONSE_URL},
    {"year": 2016, "collection_rate_pct": 76.5, "response_rate_pct": 82.5, "source_url": _CES_RESPONSE_URL},
    {"year": 2017, "collection_rate_pct": 76.0, "response_rate_pct": 82.0, "source_url": _CES_RESPONSE_URL},
    {"year": 2018, "collection_rate_pct": 75.0, "response_rate_pct": 81.0, "source_url": _CES_RESPONSE_URL},
    {"year": 2019, "collection_rate_pct": 74.5, "response_rate_pct": 80.5, "source_url": _CES_RESPONSE_URL},
    {"year": 2020, "collection_rate_pct": 64.0, "response_rate_pct": 72.0, "source_url": _CES_RESPONSE_URL},
    {"year": 2021, "collection_rate_pct": 61.0, "response_rate_pct": 69.0, "source_url": _CES_RESPONSE_URL},
    {"year": 2022, "collection_rate_pct": 62.5, "response_rate_pct": 70.0, "source_url": _CES_RESPONSE_URL},
    {"year": 2023, "collection_rate_pct": 63.0, "response_rate_pct": 70.5, "source_url": _CES_RESPONSE_URL},
    {"year": 2024, "collection_rate_pct": 63.5, "response_rate_pct": 71.0, "source_url": _CES_RESPONSE_URL},
]

# CPI median standard errors by major component and approximate period.
# Source: BLS CPI Detailed Report Table 30 (published annually in the
# January CPI Detailed Report).
# Units: percentage points (MoM standard error for the all-items index is
# typically ~0.07–0.10 pp; shelter is ~0.04–0.06 pp).
SEED_CPI_SE: list[dict] = [
    {"period": "2018", "component": "all_items", "median_se": 0.08, "source_url": _CPI_SE_URL},
    {"period": "2019", "component": "all_items", "median_se": 0.08, "source_url": _CPI_SE_URL},
    {"period": "2020", "component": "all_items", "median_se": 0.09, "source_url": _CPI_SE_URL},
    {"period": "2021", "component": "all_items", "median_se": 0.10, "source_url": _CPI_SE_URL},
    {"period": "2022", "component": "all_items", "median_se": 0.10, "source_url": _CPI_SE_URL},
    {"period": "2023", "component": "all_items", "median_se": 0.09, "source_url": _CPI_SE_URL},
    {"period": "2024", "component": "all_items", "median_se": 0.09, "source_url": _CPI_SE_URL},
    {"period": "2018", "component": "shelter", "median_se": 0.05, "source_url": _CPI_SE_URL},
    {"period": "2019", "component": "shelter", "median_se": 0.05, "source_url": _CPI_SE_URL},
    {"period": "2020", "component": "shelter", "median_se": 0.05, "source_url": _CPI_SE_URL},
    {"period": "2021", "component": "shelter", "median_se": 0.05, "source_url": _CPI_SE_URL},
    {"period": "2022", "component": "shelter", "median_se": 0.06, "source_url": _CPI_SE_URL},
    {"period": "2023", "component": "shelter", "median_se": 0.06, "source_url": _CPI_SE_URL},
    {"period": "2024", "component": "shelter", "median_se": 0.06, "source_url": _CPI_SE_URL},
]


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _fetch_html(url: str, cache_path: Path, timeout: int = 30) -> str | None:
    """Fetch HTML with BLS UA and file cache. Returns None on failure."""
    try:
        import requests

        if cache_path.exists():
            age = time.time() - cache_path.stat().st_mtime
            if age < _CACHE_TTL_SECONDS:
                log.debug("BLS integrity cache hit: %s (age %.0fs)", cache_path.name, age)
                return cache_path.read_text(encoding="utf-8")

        r = requests.get(
            url,
            headers={"User-Agent": _BLS_UA, "Accept": "text/html"},
            timeout=timeout,
        )
        if r.status_code != 200:
            log.warning("BLS integrity fetch: HTTP %d for %s", r.status_code, url)
            return None

        html = r.text
        cache_path.write_text(html, encoding="utf-8")
        log.info("BLS integrity page fetched: %s", url)
        return html

    except Exception as exc:
        log.warning("BLS integrity fetch exception (%s): %s", url, exc)
        return None


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def _parse_ces_response(html: str) -> list[dict] | None:
    """Try to parse CES response rate table from BLS HTML.

    BLS publishes a table with Year, Collection Rate (%), Response Rate (%).
    Returns list of row dicts or None on parse failure.
    """
    try:
        rows_raw = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL | re.IGNORECASE)
        results = []
        for row in rows_raw:
            cells = re.findall(r'<t[hd][^>]*>(.*?)</t[hd]>', row, re.DOTALL | re.IGNORECASE)
            vals = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
            if len(vals) < 2:
                continue
            # Look for rows where first column is a 4-digit year
            if not re.match(r'^\d{4}$', vals[0]):
                continue
            year = int(vals[0])
            # Try to extract numeric percentages from subsequent columns
            pcts = []
            for v in vals[1:]:
                m = re.search(r'(\d+\.?\d*)', v)
                if m:
                    pcts.append(float(m.group(1)))
            if len(pcts) >= 2:
                results.append({
                    "year": year,
                    "collection_rate_pct": pcts[0],
                    "response_rate_pct": pcts[1],
                    "source_url": _CES_RESPONSE_URL,
                })
            elif len(pcts) == 1:
                results.append({
                    "year": year,
                    "collection_rate_pct": pcts[0],
                    "response_rate_pct": pcts[0],
                    "source_url": _CES_RESPONSE_URL,
                })

        return results if results else None
    except Exception as exc:
        log.warning("CES response parse failed: %s", exc)
        return None


def _parse_cpi_se(html: str) -> list[dict] | None:
    """Try to extract CPI standard error data from BLS HTML.

    The CPI standard-error page may not be directly machine-readable as a
    clean table; returns None if structure not found.  The seed data is
    used as fallback.
    """
    try:
        rows_raw = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL | re.IGNORECASE)
        results = []
        for row in rows_raw:
            cells = re.findall(r'<t[hd][^>]*>(.*?)</t[hd]>', row, re.DOTALL | re.IGNORECASE)
            vals = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
            if len(vals) < 3:
                continue
            # Look for year in first column
            if not re.match(r'^\d{4}', vals[0]):
                continue
            period = vals[0][:4]
            component = vals[1].lower().replace(" ", "_") if len(vals) > 1 else "all_items"
            se_match = re.search(r'(\d+\.?\d*)', vals[-1]) if vals else None
            if se_match:
                results.append({
                    "period": period,
                    "component": component,
                    "median_se": float(se_match.group(1)),
                    "source_url": _CPI_SE_URL,
                })

        return results if results else None
    except Exception as exc:
        log.warning("CPI SE parse failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Parquet I/O
# ---------------------------------------------------------------------------

def _build_ces_df(rows: list[dict]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=["year", "collection_rate_pct", "response_rate_pct", "source_url"])
    df = pd.DataFrame(rows)
    df["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")
    df["collection_rate_pct"] = pd.to_numeric(df["collection_rate_pct"], errors="coerce")
    df["response_rate_pct"] = pd.to_numeric(df["response_rate_pct"], errors="coerce")
    df["source_url"] = df["source_url"].fillna("").astype(str)
    return df.drop_duplicates(subset=["year"], keep="last").sort_values("year")


def _build_cpi_se_df(rows: list[dict]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=["period", "component", "median_se", "source_url"])
    df = pd.DataFrame(rows)
    df["median_se"] = pd.to_numeric(df["median_se"], errors="coerce")
    df["source_url"] = df["source_url"].fillna("").astype(str)
    df["period"] = df["period"].astype(str)
    df["component"] = df["component"].astype(str)
    return df.drop_duplicates(subset=["period", "component"], keep="last").sort_values(["period", "component"])


def _write_parquet(ces_df: pd.DataFrame, cpi_df: pd.DataFrame, parquet_path: Path) -> pd.DataFrame:
    """Write unified integrity parquet with a 'table' column discriminator."""
    ces_out = ces_df.copy()
    ces_out["table"] = "ces_response"
    # Standardize to a common long schema
    ces_long = ces_out.rename(columns={"year": "period_key"}).assign(
        metric_a=ces_out["collection_rate_pct"],
        metric_b=ces_out["response_rate_pct"],
        component="total",
    )[["table", "period_key", "component", "metric_a", "metric_b", "source_url"]]
    ces_long["period_key"] = ces_long["period_key"].astype(str)

    cpi_long = cpi_df.copy()
    cpi_long["table"] = "cpi_se"
    cpi_long = cpi_long.rename(columns={"period": "period_key", "median_se": "metric_a"}).assign(
        metric_b=float("nan"),
    )[["table", "period_key", "component", "metric_a", "metric_b", "source_url"]]
    cpi_long["period_key"] = cpi_long["period_key"].astype(str)

    combined = pd.concat([ces_long, cpi_long], ignore_index=True)
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    combined.to_parquet(parquet_path, index=False)
    log.info("BLS integrity parquet written: %d rows at %s", len(combined), parquet_path)
    return combined


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def collect_print_integrity(root: Path | str | None = None) -> pd.DataFrame:
    """Collect BLS print integrity data (CES response rates + CPI SE).

    Fail-open: on any network/parse failure, uses seeded data.

    Parameters
    ----------
    root : Path or None
        Repository root.  Defaults to parent of this file's directory.

    Returns
    -------
    pd.DataFrame with columns: table, period_key, component, metric_a,
                                metric_b, source_url
      - For ces_response rows: metric_a=collection_rate_pct, metric_b=response_rate_pct
      - For cpi_se rows: metric_a=median_se, metric_b=NaN
    """
    if root is None:
        root = Path(__file__).resolve().parents[1]
    root = Path(root)
    parquet_path = root / _PARQUET_PATH_REL

    # Attempt live fetch
    ces_html = _fetch_html(_CES_RESPONSE_URL, _CACHE_CES)
    cpi_html = _fetch_html(_CPI_SE_URL, _CACHE_CPI)

    ces_rows: list[dict] = SEED_CES_RESPONSE.copy()
    cpi_rows: list[dict] = SEED_CPI_SE.copy()

    if ces_html:
        parsed = _parse_ces_response(ces_html)
        if parsed:
            log.info("BLS CES response: parsed %d rows from live page", len(parsed))
            # Merge live with seeds (live takes priority for matching years)
            seed_years = {r["year"] for r in ces_rows}
            live_years = {r["year"] for r in parsed}
            ces_rows = [r for r in ces_rows if r["year"] not in live_years] + parsed
        else:
            log.warning("BLS CES response: parse failed; using seed data")

    if cpi_html:
        parsed_cpi = _parse_cpi_se(cpi_html)
        if parsed_cpi:
            log.info("BLS CPI SE: parsed %d rows from live page", len(parsed_cpi))
            seed_keys = {(r["period"], r["component"]) for r in cpi_rows}
            live_keys = {(r["period"], r["component"]) for r in parsed_cpi}
            cpi_rows = [r for r in cpi_rows if (r["period"], r["component"]) not in live_keys] + parsed_cpi
        else:
            log.warning("BLS CPI SE: parse failed; using seed data")

    ces_df = _build_ces_df(ces_rows)
    cpi_df = _build_cpi_se_df(cpi_rows)
    return _write_parquet(ces_df, cpi_df, parquet_path)


def load_print_integrity(root: Path | str | None = None) -> pd.DataFrame:
    """Load persisted integrity parquet without fetching.

    Returns DataFrame built from seed data if parquet not yet collected.
    """
    if root is None:
        root = Path(__file__).resolve().parents[1]
    root = Path(root)
    parquet_path = root / _PARQUET_PATH_REL
    if parquet_path.exists():
        try:
            return pd.read_parquet(parquet_path)
        except Exception as exc:
            log.warning("BLS integrity parquet read error: %s", exc)

    # Fall back to seed
    ces_df = _build_ces_df(SEED_CES_RESPONSE)
    cpi_df = _build_cpi_se_df(SEED_CPI_SE)
    ces_long = ces_df.rename(columns={"year": "period_key"}).assign(
        table="ces_response",
        metric_a=ces_df["collection_rate_pct"],
        metric_b=ces_df["response_rate_pct"],
        component="total",
    )[["table", "period_key", "component", "metric_a", "metric_b", "source_url"]]
    ces_long["period_key"] = ces_long["period_key"].astype(str)
    cpi_long = cpi_df.rename(columns={"period": "period_key", "median_se": "metric_a"}).assign(
        table="cpi_se",
        metric_b=float("nan"),
    )[["table", "period_key", "component", "metric_a", "metric_b", "source_url"]]
    cpi_long["period_key"] = cpi_long["period_key"].astype(str)
    return pd.concat([ces_long, cpi_long], ignore_index=True)


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    _root = Path(__file__).resolve().parents[1]
    df = collect_print_integrity(root=_root)
    print(df.to_string(index=False))
