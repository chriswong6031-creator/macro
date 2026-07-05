"""FINRA OTC Transparency — weekly per-ATS venue volume collector (T2e).

FINRA's OTC Transparency programme publishes, with a 2–4 week publication lag,
the aggregate shares and trades each registered ATS executed in every NMS security
for the prior week.  The dataset is accessible keyless via:

    POST/GET https://api.finra.org/data/group/OTCMarket/name/weeklysummary
    (Accept: application/json)

No API key, OAuth token, or registration is required for this endpoint — it is
part of FINRA's public transparency mandate.  The endpoint returns the latest
published reporting week and paginates via `limit`/`offset`.

SEMANTICS (binding — roadmap R5):
  - Grain: weekly, per ATS venue per symbol.
  - Lag: data appears ~2–4 weeks after the reporting week ends.  Every record
    is labeled with its `week_start` date; the UI must display the lag chip.
  - Label: "ATS venue volume" or "weekly ATS share volume" — NEVER "dark pool
    prints" and NEVER "live".
  - Store: data/finra_ats/<week_start>.parquet (one file per week, content-
    addressed by weekStartDate so reruns are idempotent).

Graceful-degrade contract (same as collectors/finra_short_volume.py):
  - If the API is unreachable and we already have stored data, return a heartbeat
    so the runner marks the source 'ok/stale' rather than 'failed'.
  - A 404 or empty response for a specific week is treated as "not yet published"
    and skipped silently.

Schema written to parquet:
    week_start  : pd.Timestamp     (Monday of the reporting week)
    ticker      : str               (issueSymbolIdentifier)
    mpid        : str               (ATS market-participant ID)
    venue_name  : str               (marketParticipantName)
    shares      : float             (totalWeeklyShareQuantity)
    trades      : int               (totalWeeklyTradeCount)
    tier        : str               (T1 / T2 / OTC-E)
"""
from __future__ import annotations

import logging
import time
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import requests

from collectors.base import Adapter, is_connection_error
from lib import config

log = logging.getLogger(__name__)

API_BASE = "https://api.finra.org/data/group/OTCMarket/name/weeklysummary"
# summaryTypeCode for per-symbol per-firm rows (as opposed to aggregate stats)
SUMMARY_TYPE = "ATS_W_SMBL_FIRM"
GROUP = "finra_ats"
PAGE_SIZE = 500          # API max per page
SLEEP_PAGE = 0.3         # seconds between pages
MAX_PAGES = 40           # safety cap: 40 × 500 = 20k rows per week (ample)


def _store_dir() -> Path:
    return config.data_dir() / GROUP


def _week_path(week_start: date) -> Path:
    return _store_dir() / f"{week_start.strftime('%Y%m%d')}.parquet"


def _have_weeks() -> set[date]:
    d = _store_dir()
    if not d.exists():
        return set()
    out: set[date] = set()
    for p in d.glob("*.parquet"):
        try:
            out.add(date.fromisoformat(p.stem[:4] + "-" + p.stem[4:6] + "-" + p.stem[6:8]))
        except ValueError:
            continue
    return out


def _fetch_week(session: requests.Session, fields: list[str]) -> list[dict]:
    """Fetch ALL records for the latest published week via offset pagination.

    Returns the raw list of row dicts. Raises on connection error; returns []
    on empty or unexpected response (treated as 'not yet published').
    """
    rows: list[dict] = []
    offset = 0
    for _ in range(MAX_PAGES):
        params = {
            "limit": PAGE_SIZE,
            "offset": offset,
            "compareFilters": (
                f'[{{"fieldName":"summaryTypeCode",'
                f'"fieldValue":"{SUMMARY_TYPE}",'
                f'"compareType":"EQUAL"}}]'
            ),
        }
        if fields:
            params["fields"] = ",".join(fields)
        try:
            r = session.get(API_BASE, params=params, timeout=40,
                            headers={"Accept": "application/json"})
            if r.status_code == 404:
                break
            r.raise_for_status()
            page: list[dict] = r.json()
            if not isinstance(page, list) or not page:
                break
            rows.extend(page)
            if len(page) < PAGE_SIZE:
                break   # last page
            offset += PAGE_SIZE
            time.sleep(SLEEP_PAGE)
        except requests.exceptions.ConnectionError:
            raise
        except Exception as e:  # noqa: BLE001
            log.warning("finra_ats: fetch page offset=%d failed: %s", offset, e)
            break
    return rows


def _parse_rows(rows: list[dict]) -> pd.DataFrame:
    """Convert raw API rows to the canonical schema DataFrame."""
    records: list[dict] = []
    for r in rows:
        ticker = r.get("issueSymbolIdentifier")
        if not ticker:
            continue  # skip aggregate rows (null symbol)
        week_raw = r.get("weekStartDate") or r.get("summaryStartDate")
        if not week_raw:
            continue
        try:
            week_start = pd.Timestamp(week_raw)
        except Exception:  # noqa: BLE001
            continue
        mpid = (r.get("MPID") or "").strip()
        venue_name = (r.get("marketParticipantName") or "").strip()
        try:
            shares = float(r.get("totalWeeklyShareQuantity") or 0)
            trades = int(r.get("totalWeeklyTradeCount") or 0)
        except (ValueError, TypeError):
            continue
        tier_raw = r.get("tierIdentifier") or r.get("tierDescription") or ""
        records.append({
            "week_start": week_start,
            "ticker": str(ticker).strip().upper(),
            "mpid": mpid,
            "venue_name": venue_name,
            "shares": shares,
            "trades": trades,
            "tier": str(tier_raw).strip(),
        })
    if not records:
        return pd.DataFrame()
    return pd.DataFrame(records)


WANTED_FIELDS = [
    "issueSymbolIdentifier",
    "marketParticipantName",
    "MPID",
    "totalWeeklyShareQuantity",
    "totalWeeklyTradeCount",
    "weekStartDate",
    "summaryStartDate",
    "summaryTypeCode",
    "tierIdentifier",
    "tierDescription",
]


class FinraAtsTransparencyAdapter(Adapter):
    """Weekly per-ATS venue volume — FINRA OTC Transparency (keyless, T2e)."""

    name = "finra_ats_transparency"
    group = GROUP
    stale_after_days = 10    # weekly feed with 2-4wk lag; tolerate 10d before flagging stale

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        have = _have_weeks()
        store_dir = _store_dir()
        store_dir.mkdir(parents=True, exist_ok=True)

        session = requests.Session()
        session.headers["User-Agent"] = (
            "macro-dashboard research (keyless FINRA OTC Transparency API)"
        )

        # Fetch the latest published week from the API
        try:
            rows = _fetch_week(session, WANTED_FIELDS)
        except Exception as e:  # noqa: BLE001
            if is_connection_error(e):
                # CDN/network down — return heartbeat if we have stored data
                if have:
                    latest = max(have)
                    log.warning("finra_ats: connection error (%s); using stored data, latest %s",
                                e, latest)
                    hb = pd.DataFrame({"new_rows": [0]},
                                      index=[pd.Timestamp(latest)])
                    return {"finra_ats__ingest": hb}
            raise

        if not rows:
            if have:
                latest = max(have)
                log.info("finra_ats: no new rows from API (possibly not-yet-published); latest stored %s", latest)
                hb = pd.DataFrame({"new_rows": [0]},
                                  index=[pd.Timestamp(latest)])
                return {"finra_ats__ingest": hb}
            raise RuntimeError("finra_ats: no rows returned and no stored history")

        df = _parse_rows(rows)
        if df.empty:
            if have:
                latest = max(have)
                hb = pd.DataFrame({"new_rows": [0]}, index=[pd.Timestamp(latest)])
                return {"finra_ats__ingest": hb}
            raise RuntimeError("finra_ats: parse produced empty DataFrame")

        # Identify week(s) in this response
        week_dates = df["week_start"].dt.date.unique()
        new_weeks = [w for w in week_dates if w not in have]

        if not new_weeks:
            latest = max(have) if have else max(week_dates)
            log.info("finra_ats: all weeks already stored; latest %s", latest)
            hb = pd.DataFrame({"new_rows": [0]}, index=[pd.Timestamp(latest)])
            return {"finra_ats__ingest": hb}

        # Write one parquet per new week
        total_rows = 0
        latest_week: date | None = None
        for w in new_weeks:
            week_df = df[df["week_start"].dt.date == w].copy()
            path = _week_path(w)
            week_df.to_parquet(path, index=False)
            total_rows += len(week_df)
            latest_week = max(latest_week, w) if latest_week else w
            log.info("finra_ats: stored week %s → %d rows, %d venues, path=%s",
                     w, len(week_df), week_df["mpid"].nunique(), path.name)

        log.info("finra_ats: %d new week(s), %d rows total, latest %s",
                 len(new_weeks), total_rows, latest_week)
        hb = pd.DataFrame({"new_rows": [total_rows]},
                          index=[pd.Timestamp(latest_week)])
        return {"finra_ats__ingest": hb}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    FinraAtsTransparencyAdapter().fetch()
