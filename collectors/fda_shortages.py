"""FDA Drug Shortage collector — first orphan-rescue feed (Wave 5b / §3.4).

Probes the openFDA drug/shortages endpoint (https://api.fda.gov/drug/shortages.json)
to capture active and resolved drug shortages. Keyless, bounded, non-fatal on failure.

Schema observed at build-time (2026-07-02) via empirical probe:
  generic_name     str   — INN + dosage form
  status           str   — "Current" | "Resolved" | "To Be Discontinued" | absent
  availability     str   — "Available" | "Limited Availability" | "Unavailable" | absent
  initial_posting_date  str  — MM/DD/YYYY
  discontinued_date     str  — MM/DD/YYYY | absent
  update_date           str  — MM/DD/YYYY | absent

The endpoint serves 1,637 records as of 2026-07-02 at keyless rate (no API key required
for low-volume access). Paginated with skip+limit. We fetch all records and cache them
to data/fda/shortages.parquet (append-only, deduped on package_ndc+initial_posting_date).

Display-only; degrades to None / empty on any network failure; never raises into the build.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import pandas as pd
import requests

from collectors.base import is_connection_error
from lib import config

log = logging.getLogger(__name__)

SHORTAGES_URL = "https://api.fda.gov/drug/shortages.json"
PAGE_SIZE = 100       # openFDA max per request
MAX_PAGES = 25        # cap: 2500 records; avoids runaway loop
PACE_S = 0.4          # polite pacing between pages


def _shortages_path():
    p = config.data_dir() / "fda" / "shortages.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _fetch_page(skip: int, limit: int = PAGE_SIZE) -> dict:
    """Fetch one page from the openFDA shortages endpoint. Returns the raw JSON dict."""
    params = {"limit": limit, "skip": skip}
    headers = {"User-Agent": "python-requests/2.32 (macro-dashboard; contact@macro-dashboard.dev)"}
    r = requests.get(SHORTAGES_URL, params=params, headers=headers, timeout=40)
    if r.status_code in (429, 500, 502, 503, 504):
        raise requests.HTTPError(f"HTTP {r.status_code}", response=r)
    r.raise_for_status()
    return r.json()


def _parse_record(rec: dict) -> dict:
    """Flatten one openFDA shortages record into a flat row."""
    openfda = rec.get("openfda") or {}
    brands = openfda.get("brand_name") or []
    substances = openfda.get("substance_name") or []
    return {
        "package_ndc": rec.get("package_ndc") or "",
        "generic_name": rec.get("generic_name") or "",
        "brand_name": brands[0] if brands else None,
        "substance_name": substances[0] if substances else None,
        "status": rec.get("status") or "",
        "availability": rec.get("availability") or "",
        "initial_posting_date": rec.get("initial_posting_date") or "",
        "update_date": rec.get("update_date") or "",
        "discontinued_date": rec.get("discontinued_date") or None,
        "therapeutic_category": (rec.get("therapeutic_category") or [None])[0],
        "company_name": rec.get("company_name") or None,
        "related_info": rec.get("related_info") or None,
        "fetched_utc": datetime.now(timezone.utc).isoformat(),
    }


def fetch_shortages(full_refresh: bool = False) -> pd.DataFrame | None:
    """Fetch all current FDA drug shortage records and cache to parquet.

    Args:
        full_refresh: if True, re-fetch all pages even if cache is warm.
                      if False, always fetches (no incremental mode — the endpoint
                      does not support date-filtered queries for shortage records).

    Returns:
        DataFrame of shortage records, or None on network failure.
    """
    path = _shortages_path()
    rows = []
    try:
        # Page through all records
        skip = 0
        total = None
        for page_idx in range(MAX_PAGES):
            try:
                data = _fetch_page(skip=skip)
            except requests.HTTPError as e:
                log.warning("fda_shortages: HTTP error on page %d: %s", page_idx, e)
                break
            except Exception as e:  # noqa: BLE001
                if is_connection_error(e):
                    log.warning("fda_shortages: connection error: %s", e)
                    return None
                log.warning("fda_shortages: error on page %d: %s", page_idx, e)
                break

            meta = data.get("meta", {}).get("results", {})
            if total is None:
                total = meta.get("total", 0)
            page_results = data.get("results") or []
            if not page_results:
                break
            rows.extend(_parse_record(r) for r in page_results)
            skip += len(page_results)
            if skip >= (total or 0):
                break
            time.sleep(PACE_S)

        if not rows:
            log.info("fda_shortages: no records fetched (endpoint returned empty)")
            if path.exists():
                return pd.read_parquet(path)
            return pd.DataFrame()

        new_df = pd.DataFrame(rows)
        # Append-only / dedupe: merge with existing cache on package_ndc + initial_posting_date
        if path.exists():
            try:
                existing = pd.read_parquet(path)
                combined = pd.concat([existing, new_df], ignore_index=True)
                combined = combined.drop_duplicates(
                    subset=["package_ndc", "initial_posting_date"], keep="last"
                ).reset_index(drop=True)
            except Exception as e:  # noqa: BLE001
                log.warning("fda_shortages: cache merge failed (%s), replacing", e)
                combined = new_df
        else:
            combined = new_df

        combined.to_parquet(path)
        log.info("fda_shortages: fetched %d records (%d total in cache, from %d pages)",
                 len(rows), len(combined), page_idx + 1)
        return combined

    except Exception as e:  # noqa: BLE001
        log.warning("fda_shortages: fetch failed (non-fatal): %s", e)
        if path.exists():
            try:
                return pd.read_parquet(path)
            except Exception:  # noqa: BLE001
                pass
        return None


def load_shortages_cache() -> pd.DataFrame | None:
    """Read the cached shortage records without network fetch. Returns None if no cache."""
    path = _shortages_path()
    if not path.exists():
        return None
    try:
        return pd.read_parquet(path)
    except Exception as e:  # noqa: BLE001
        log.warning("fda_shortages: cache read failed: %s", e)
        return None


if __name__ == "__main__":
    import logging as _logging
    _logging.basicConfig(level=_logging.INFO, format="%(levelname)s %(message)s")
    df = fetch_shortages()
    if df is not None:
        print(f"Fetched {len(df)} records")
        print(df[["generic_name", "status", "availability"]].head(10))
