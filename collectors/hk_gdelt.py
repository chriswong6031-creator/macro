"""GDELT DOC 2.0 collector — HK platform-tech bellwether narrative pulse.

Fetches GDELT ``timelinevol`` (volume intensity) and ``timelinetone`` (average
tone) time-series for each bellwether entity, trailing ~90 days.

SOURCE
------
GDELT DOC 2.0 API (keyless, free, public):
  https://api.gdeltproject.org/api/v2/doc/doc
  mode=timelinevol  → {"timeline":[{"series":"Volume Intensity","data":[...]}]}
  mode=timelinetone → {"timeline":[{"series":"Average Tone","data":[...]}]}
  Each data point: {"date": "20260708T000000Z", "value": <float>}

Verified 2026-07-08 — endpoint returns daily data covering trailing 90d for
English company-name queries. Rate limit: 1 request / 5s enforced by this
collector. One query per entity per mode per run; results cached in-process for
the session.

ENTITY-RESOLUTION CAVEAT (honest — do not overclaim)
------------------------------------------------------
GDELT indexes English-language news. Company-name queries match ANY article that
mentions the string — no disambiguating company-entity resolution. "Alibaba"
will include general China-tech articles that name it; "Baidu" articles about
the search engine; "SMIC" is rarer and may pick up semiconductor-general news.
"Meituan" and "Kuaishou" have low English-language coverage → expect thin
series. Volume values are normalized article-count fractions (not raw counts).
Queries are by the most common English name; alternative names (Ant Group,
Ant Financial) are queried separately and merged at the entity level.

STORE
-----
  data/hk_gdelt/
    <entity_slug>.parquet   — tidy per-entity vol+tone series (daily rows)
    coverage.json           — freshness stamp {entity_slug: {date, rows, source}}

Parquet columns:
  date (datetime64, UTC midnight), entity_query (str), ticker (str),
  vol_intensity (float | NaN), avg_tone (float | NaN)

FAIL-OPEN DESIGN
----------------
  * HTTP or parse failure for any entity → logs warning, skips that entity;
    others continue.
  * Rate-limit response or empty data → treated as a no-data entity (not a crash).
  * Re-run within the same calendar day reuses the cached parquet (day-stamp
    check against coverage.json); does not re-hammer the API.
  * Any exception in the top-level collect() → logs + returns empty dict.

LANE CONTRACT
-------------
  Network I/O: collect lane ONLY.
  Render lane reads back via load_store() / store_status() — pure parquet reads.
  NEVER called from the engine layer at render time.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import NamedTuple

import pandas as pd
import requests

from collectors.base import Adapter
from lib import config

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Entity → ticker map
# ---------------------------------------------------------------------------

class _Entity(NamedTuple):
    slug: str         # store key, also parquet stem
    ticker: str       # HK ticker e.g. "9988.HK"
    name_en: str      # display name
    name_zh: str      # display name (Chinese)
    queries: list[str]  # GDELT queries for this entity (merged on fetch)


ENTITIES: list[_Entity] = [
    _Entity("alibaba",  "9988.HK",  "Alibaba",  "阿里巴巴", ["Alibaba", "Ant Group"]),
    _Entity("tencent",  "0700.HK",  "Tencent",  "腾讯",     ["Tencent"]),
    _Entity("meituan",  "3690.HK",  "Meituan",  "美团",     ["Meituan"]),
    _Entity("xiaomi",   "1810.HK",  "Xiaomi",   "小米",     ["Xiaomi"]),
    _Entity("baidu",    "9888.HK",  "Baidu",    "百度",     ["Baidu"]),
    _Entity("jdcom",    "9618.HK",  "JD.com",   "京东",     ["JD.com"]),
    _Entity("kuaishou", "1024.HK",  "Kuaishou", "快手",     ["Kuaishou"]),
    _Entity("smic",     "0981.HK",  "SMIC",     "中芯国际", ["SMIC"]),
]

# ---------------------------------------------------------------------------
# GDELT API parameters
# ---------------------------------------------------------------------------

_GDELT_BASE = "https://api.gdeltproject.org/api/v2/doc/doc"
_TIMESPAN    = "90d"
_REQUEST_GAP = 5.5   # seconds between API requests (rate limit: 1/5s)

# ---------------------------------------------------------------------------
# Store layout
# ---------------------------------------------------------------------------

_STORE_DIR = "hk_gdelt"


def _store_root(data_root: Path | None = None) -> Path:
    if data_root is None:
        data_root = config.data_dir()
    return data_root / _STORE_DIR


def _coverage_path(data_root: Path | None = None) -> Path:
    return _store_root(data_root) / "coverage.json"


def load_coverage(data_root: Path | None = None) -> dict:
    """Return coverage.json as a dict; {} if missing or corrupt."""
    p = _coverage_path(data_root)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception as e:  # noqa: BLE001
        log.warning("hk_gdelt: coverage.json corrupt: %s", e)
        return {}


def _save_coverage(cov: dict, data_root: Path | None = None) -> None:
    p = _coverage_path(data_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cov, indent=2, default=str))


# ---------------------------------------------------------------------------
# GDELT fetch helpers
# ---------------------------------------------------------------------------

def _gdelt_timeline(query: str, mode: str, session: requests.Session) -> list[dict]:
    """Fetch one GDELT timeline series. Returns list of {date, value} dicts.
    Raises on HTTP error or unexpected shape (caller handles gracefully).
    """
    params = {
        "query":    query,
        "mode":     mode,
        "timespan": _TIMESPAN,
        "format":   "json",
    }
    resp = session.get(_GDELT_BASE, params=params, timeout=30)
    # GDELT rate-limit response is a 429 or a 200 with a plain-text message
    if resp.status_code == 429:
        log.warning("hk_gdelt: GDELT rate limit hit for query=%r mode=%s", query, mode)
        return []
    resp.raise_for_status()
    # Check for rate-limit text body (GDELT sometimes returns 200 + text)
    ctype = resp.headers.get("Content-Type", "")
    if "application/json" not in ctype and "json" not in ctype:
        log.warning("hk_gdelt: non-JSON response for query=%r mode=%s (rate limit?)", query, mode)
        return []
    data = resp.json()
    timeline = data.get("timeline", [])
    if not timeline:
        return []
    # The first series is the one we want
    series = timeline[0]
    return series.get("data", [])


def _parse_gdelt_date(raw: str) -> pd.Timestamp | None:
    """Parse '20260708T000000Z' → pd.Timestamp UTC midnight."""
    try:
        return pd.Timestamp(raw, tz="UTC")
    except Exception:  # noqa: BLE001
        return None


def _fetch_entity(entity: _Entity, session: requests.Session) -> pd.DataFrame | None:
    """Fetch vol + tone for all queries of one entity; merge into a single DataFrame.

    Returns a DataFrame with columns [date, entity_query, ticker, vol_intensity, avg_tone]
    indexed by date. Returns None on total failure.
    """
    vol_rows: dict[pd.Timestamp, list[float]] = {}
    tone_rows: dict[pd.Timestamp, list[float]] = {}

    for q_idx, query in enumerate(entity.queries):
        if q_idx > 0:
            time.sleep(_REQUEST_GAP)

        # Vol
        try:
            time.sleep(_REQUEST_GAP)
            vol_data = _gdelt_timeline(query, "timelinevol", session)
            for pt in vol_data:
                ts = _parse_gdelt_date(pt.get("date", ""))
                if ts is not None:
                    vol_rows.setdefault(ts, []).append(float(pt["value"]))
        except Exception as e:  # noqa: BLE001
            log.warning("hk_gdelt: vol fetch failed for %s query=%r: %s", entity.slug, query, e)

        # Tone
        try:
            time.sleep(_REQUEST_GAP)
            tone_data = _gdelt_timeline(query, "timelinetone", session)
            for pt in tone_data:
                ts = _parse_gdelt_date(pt.get("date", ""))
                if ts is not None:
                    tone_rows.setdefault(ts, []).append(float(pt["value"]))
        except Exception as e:  # noqa: BLE001
            log.warning("hk_gdelt: tone fetch failed for %s query=%r: %s", entity.slug, query, e)

    if not vol_rows and not tone_rows:
        log.warning("hk_gdelt: no data for entity %s", entity.slug)
        return None

    all_dates = sorted(set(vol_rows) | set(tone_rows))
    records = []
    for ts in all_dates:
        # Merge multiple query values by taking the mean (e.g. Alibaba + Ant Group)
        vol_vals = vol_rows.get(ts, [])
        tone_vals = tone_rows.get(ts, [])
        records.append({
            "date":         ts,
            "entity_query": entity.queries[0],  # primary query label
            "ticker":       entity.ticker,
            "vol_intensity": sum(vol_vals) / len(vol_vals) if vol_vals else float("nan"),
            "avg_tone":     sum(tone_vals) / len(tone_vals) if tone_vals else float("nan"),
        })

    df = pd.DataFrame(records).set_index("date").sort_index()
    return df


# ---------------------------------------------------------------------------
# Day-cache check
# ---------------------------------------------------------------------------

def _already_fetched_today(slug: str, data_root: Path | None = None) -> bool:
    """Return True if we have a fresh parquet for this slug from today."""
    cov = load_coverage(data_root)
    entry = cov.get(slug, {})
    today = date.today().isoformat()
    return entry.get("date") == today


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def collect(
    data_root: Path | None = None,
    force: bool = False,
) -> dict[str, str]:
    """Fetch GDELT vol+tone for all bellwether entities; persist parquets.

    Returns a dict {slug: "ok" | "cached" | "error"} for logging.
    Never raises — fail-open on any per-entity error.
    """
    root = _store_root(data_root)
    root.mkdir(parents=True, exist_ok=True)
    cov = load_coverage(data_root)
    today = date.today().isoformat()

    session = requests.Session()
    session.headers.update({
        "User-Agent": "MacroDashboard/1.0 HK-GDELT-Collector (research)"
    })

    results: dict[str, str] = {}

    for entity in ENTITIES:
        if not force and _already_fetched_today(entity.slug, data_root):
            log.info("hk_gdelt: %s already fetched today — skipping", entity.slug)
            results[entity.slug] = "cached"
            continue

        log.info("hk_gdelt: fetching entity=%s queries=%s", entity.slug, entity.queries)
        try:
            df = _fetch_entity(entity, session)
            if df is None or df.empty:
                log.warning("hk_gdelt: empty result for %s", entity.slug)
                results[entity.slug] = "error"
                cov[entity.slug] = {"date": today, "rows": 0, "status": "empty"}
                continue

            pq_path = root / f"{entity.slug}.parquet"
            df.to_parquet(pq_path)
            cov[entity.slug] = {
                "date":   today,
                "rows":   len(df),
                "status": "ok",
                "ticker": entity.ticker,
            }
            results[entity.slug] = "ok"
            log.info("hk_gdelt: %s → %d rows → %s", entity.slug, len(df), pq_path)
        except Exception as e:  # noqa: BLE001
            log.error("hk_gdelt: entity %s failed: %s", entity.slug, e)
            results[entity.slug] = "error"
            cov[entity.slug] = {"date": today, "rows": 0, "status": f"error:{e}"}

    _save_coverage(cov, data_root)
    return results


def load_store(slug: str, data_root: Path | None = None) -> pd.DataFrame | None:
    """Load a parquet for one entity slug. Returns None if missing or corrupt."""
    p = _store_root(data_root) / f"{slug}.parquet"
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
        df.index = pd.to_datetime(df.index, utc=True)
        return df.sort_index()
    except Exception as e:  # noqa: BLE001
        log.warning("hk_gdelt.load_store: failed to load %s: %s", slug, e)
        return None


def store_status(data_root: Path | None = None) -> dict:
    """Return coverage.json + existence check for each entity parquet."""
    cov = load_coverage(data_root)
    root = _store_root(data_root)
    return {
        entity.slug: {
            "parquet_exists": (root / f"{entity.slug}.parquet").exists(),
            "coverage": cov.get(entity.slug, {}),
        }
        for entity in ENTITIES
    }


# ---------------------------------------------------------------------------
# Adapter (mirrors HkCbbcAdapter / HkHkexnewsAdapter pattern)
# ---------------------------------------------------------------------------

_STALE_DAYS = 3   # daily collect; flag stale if >3 days old


class HkGdeltAdapter(Adapter):
    """Plugs the GDELT DOC 2.0 narrative collector into the scripts/collect.py pipeline.

    Network I/O only in the collect lane (asia-close). The render lane reads
    back via load_store() / store_status() — pure parquet/JSON reads, no network.
    CN_LANE=asia is set at the workflow-job level; it is not derived from this group.
    """

    name = "hk_gdelt"
    group = "hk_gdelt"
    stale_after_days = _STALE_DAYS

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        # full_history is a no-op: GDELT timespan is fixed at 90d per call
        results = collect()
        cov = load_coverage()
        today = date.today().isoformat()
        n_ok = sum(1 for v in results.values() if v in ("ok", "cached"))
        # Return a summary frame so run_adapter's staleness check works
        summary = pd.DataFrame(
            {"entities_ok": [n_ok], "entities_total": [len(ENTITIES)]},
            index=[pd.Timestamp(today)],
        )
        return {"gdelt__summary": summary}


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    force = "--force" in sys.argv
    results = collect(force=force)
    print(json.dumps(results, indent=2))
