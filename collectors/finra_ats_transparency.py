"""FINRA OTC Transparency — weekly per-ATS venue volume collector (T2e).

FINRA's OTC Transparency programme publishes, with a 2–4 week publication lag,
the aggregate shares and trades each registered ATS executed in every NMS security
for the prior week.  The dataset is accessible keyless via:

    https://api.finra.org/data/group/OTCMarket/name/weeklySummary

No API key, OAuth token, or registration is required — it is part of FINRA's
public transparency mandate.

DATASET SHAPE (2026-07 repair — the 2.5-year silent stall):
  The dataset is PARTITIONED on (weekStartDate, tierIdentifier) and holds
  2021-12-06 → present. Three traps, all verified live 2026-07-11:
    1. An UNFILTERED query returns the OLDEST partition (week 2023-11-06), not the
       latest published week as this collector originally assumed — that is exactly
       why the store froze at 2023-11-06 while every nightly run logged "all weeks
       already stored".
    2. GET query params (compareFilters/dateRangeFilters/fields) are silently
       IGNORED — filters only apply on POST with a JSON body.
    3. weekStartDate is a date field: filter it with dateRangeFilters
       (start==end), not a compareFilters EQUAL (silently ignored).
  Week discovery goes through the partitions metadata endpoint:
       GET https://api.finra.org/partitions/group/OTCMarket/name/weeklySummary
  Tiers publish staggered: T1 ~2wk after the week ends, T2/OTCE ~4wk. A week is
  ingested only once BOTH T1 and T2 partitions exist (write-once per week; a
  T1-only snapshot would permanently under-count the small-cap venues).

SEMANTICS (binding — roadmap R5):
  - Grain: weekly, per ATS venue per symbol.
  - Lag: data appears ~2–4 weeks after the reporting week ends.  Every record
    is labeled with its `week_start` date; the UI must display the lag chip.
  - Label: "ATS venue volume" or "weekly ATS share volume" — NEVER "dark pool
    prints" and NEVER "live".
  - Store: data/finra_ats/<week_start>.parquet (one file per week, content-
    addressed by weekStartDate so reruns are idempotent). A week is written
    COMPLETE or not at all — page-level failures skip the whole week rather
    than persisting a truncated file.
  - Budget: discovery window = newest 8 complete weeks, at most 2 fetched per
    run (~192k rows / ~39 pages each) — steady state is ≤1 new week per week;
    the cap only paces the initial catch-up. --full-history widens the window
    to every available partition for manual off-render backfills. Weeks older
    than the window (incl. the 2023-11-06 pre-repair remnant, which is itself
    truncated to the old 20k-row page cap) are intentionally not re-fetched;
    the darkpool desk reads the latest week only.

Graceful-degrade contract (same as collectors/finra_short_volume.py):
  - If the API is unreachable and we already have stored data, return a heartbeat
    so the runner marks the source 'ok/stale' rather than 'failed'.

TWO ADAPTERS, ONE ENDPOINT (2026-08-05):
  FinraAtsTransparencyAdapter → summaryTypeCode ATS_W_SMBL_FIRM → data/finra_ats/
      registered ATS venues — "true" dark pools.
  FinraOtcNonAtsAdapter       → summaryTypeCode OTC_W_SMBL_FIRM → data/finra_otc_nonats/
      non-ATS OTC — wholesaler/broker internalization, predominantly retail
      marketable flow. Off-exchange volume is ATS + non-ATS, and non-ATS is the
      BIGGER half: measured week 2026-06-22, ATS was only 16-31% of each name's
      off-exchange total (AAPL 31.4%, NVDA 23.5%, TSLA 26.0%, GME 24.5%, F 16.5%).
      Holding both is what lets a consumer separate institutional block flow from
      retail order flow instead of calling the whole blob "dark pool".

Schema written to parquet:
    week_start  : pd.Timestamp     (Monday of the reporting week)
    ticker      : str               (issueSymbolIdentifier)
    mpid        : str               (market-participant ID: ATS venue or OTC firm)
    venue_name  : str               (marketParticipantName)
    shares      : float             (totalWeeklyShareQuantity)
    trades      : int               (totalWeeklyTradeCount)
    notional    : float             (totalNotionalSum, USD — added 2026-08-05;
                                     ABSENT in weeks stored before that date, so
                                     readers must fillna rather than assume it)
    tier        : str               (T1 / T2 / OTCE; "NMS" in pre-2024 rows)
"""
from __future__ import annotations

import logging
import time
from datetime import date
from pathlib import Path

import pandas as pd
import requests

from collectors.base import Adapter, is_connection_error
from lib import config

log = logging.getLogger(__name__)

API_BASE = "https://api.finra.org/data/group/OTCMarket/name/weeklySummary"
API_PARTITIONS = "https://api.finra.org/partitions/group/OTCMarket/name/weeklySummary"
# summaryTypeCode for per-symbol per-firm rows (as opposed to aggregate stats).
# ATS_W_SMBL_FIRM = registered ATS ("true" dark pools).
# OTC_W_SMBL_FIRM = non-ATS OTC — wholesaler/broker INTERNALIZATION, which is
#   predominantly retail marketable order flow. This is the LARGER half of
#   off-exchange volume (measured week 2026-06-22: ATS was only 16-31% of the
#   off-exchange total per name — AAPL 31.4%, NVDA 23.5%, TSLA 26.0%, F 16.5%),
#   and it is what separates institutional block flow from retail order flow.
SUMMARY_TYPE = "ATS_W_SMBL_FIRM"
SUMMARY_TYPE_NONATS = "OTC_W_SMBL_FIRM"
GROUP = "finra_ats"
GROUP_NONATS = "finra_otc_nonats"
PAGE_SIZE = 5000         # API max per page (record-max-limit header)
SLEEP_PAGE = 0.3         # seconds between pages
MAX_PAGES = 60           # safety cap: 60 × 5000 = 300k rows/week (weeks run ~192k)
PAGE_RETRIES = 3         # per-page retries on 429/5xx/timeouts (API is CDN-flaky)
RECENT_WINDOW_WEEKS = 8  # only look this far back for missing weeks (normal runs)
MAX_WEEKS_PER_RUN = 2    # fetch at most this many missing weeks per nightly run


def _store_dir(group: str = GROUP) -> Path:
    return config.data_dir() / group


def _week_path(week_start: date, group: str = GROUP) -> Path:
    return _store_dir(group) / f"{week_start.strftime('%Y%m%d')}.parquet"


def _have_weeks(group: str = GROUP) -> set[date]:
    d = _store_dir(group)
    if not d.exists():
        return set()
    out: set[date] = set()
    for p in d.glob("*.parquet"):
        try:
            out.add(date.fromisoformat(p.stem[:4] + "-" + p.stem[4:6] + "-" + p.stem[6:8]))
        except ValueError:
            continue
    return out


def _http(session: requests.Session, method: str, url: str, *,
          json_body: dict | None = None, timeout: int = 60) -> requests.Response:
    """One API request with bounded retries on transient CDN/gateway errors
    (FINRA's CloudFront edge throws sporadic 504s even in healthy weeks)."""
    last_exc: Exception | None = None
    for attempt in range(PAGE_RETRIES):
        try:
            r = session.request(method, url, json=json_body, timeout=timeout,
                                headers={"Accept": "application/json"})
            if r.status_code in (429, 500, 502, 503, 504):
                raise requests.HTTPError(f"HTTP {r.status_code}", response=r)
            r.raise_for_status()
            return r
        except Exception as e:  # noqa: BLE001 — retried, then surfaced to caller
            last_exc = e
            if attempt < PAGE_RETRIES - 1:
                wait = 5 * (2 ** attempt)
                log.warning("finra_ats: %s %s failed (%s); retry in %ds",
                            method, url.rsplit("/", 1)[-1], e, wait)
                time.sleep(wait)
    raise last_exc  # type: ignore[misc]


def _degradable(e: Exception) -> bool:
    """True when the failure means FINRA is unreachable/melting (network error or
    retried-out transient HTTP status) — i.e. safe to fall back to stored data."""
    if is_connection_error(e):
        return True
    return (isinstance(e, requests.HTTPError) and e.response is not None
            and e.response.status_code in (429, 500, 502, 503, 504))


def _fetch_partitions(session: requests.Session) -> dict[date, set[str]]:
    """Available (weekStartDate → {tierIdentifier}) partitions, via the metadata
    endpoint. Raises on failure (caller degrades to heartbeat when possible)."""
    payload = _http(session, "GET", API_PARTITIONS, timeout=40).json()
    out: dict[date, set[str]] = {}
    for entry in payload.get("availablePartitions", []):
        parts = entry.get("partitions") or []
        if len(parts) < 2:
            continue
        try:
            wk = date.fromisoformat(str(parts[0]))
        except ValueError:
            continue
        out.setdefault(wk, set()).add(str(parts[1]))
    return out


def _complete_weeks(partitions: dict[date, set[str]]) -> list[date]:
    """Weeks whose T1 AND T2 partitions are both published, newest first.
    (OTCE/NA co-publish with T2; requiring T1+T2 avoids ingesting the T1-only
    early snapshot into a write-once weekly file.)"""
    return sorted((w for w, tiers in partitions.items() if {"T1", "T2"} <= tiers),
                  reverse=True)


def _fetch_week(session: requests.Session, week: date,
                summary_type: str = SUMMARY_TYPE) -> list[dict]:
    """Fetch ALL <summary_type> records for one reporting week (all tiers).

    Raises on failure — the caller must then SKIP the week entirely so a
    truncated file is never written. Returns the raw list of row dicts.
    """
    rows: list[dict] = []
    total_expected: int | None = None
    offset = 0
    for _ in range(MAX_PAGES):
        body = {
            "limit": PAGE_SIZE,
            "offset": offset,
            "compareFilters": [{"fieldName": "summaryTypeCode",
                                "fieldValue": summary_type,
                                "compareType": "EQUAL"}],
            "dateRangeFilters": [{"fieldName": "weekStartDate",
                                  "startDate": week.isoformat(),
                                  "endDate": week.isoformat()}],
        }
        r = _http(session, "POST", API_BASE, json_body=body, timeout=60)
        if total_expected is None:
            try:
                total_expected = int(r.headers.get("Record-Total", ""))
            except ValueError:
                total_expected = None
        page = r.json()
        if not isinstance(page, list) or not page:
            break
        rows.extend(page)
        if len(page) < PAGE_SIZE:
            break   # last page
        offset += PAGE_SIZE
        time.sleep(SLEEP_PAGE)
    if total_expected is not None and len(rows) < total_expected:
        # MAX_PAGES cap hit — refuse the truncated week rather than storing it
        raise RuntimeError(
            f"finra otc-transparency [{summary_type}]: week {week} truncated at "
            f"{len(rows)}/{total_expected} rows (MAX_PAGES={MAX_PAGES} cap) — raise the cap")
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
        # totalNotionalSum (USD) — was dropped before 2026-08-05. Dollar weighting is
        # how desks actually rank off-exchange participation (a $3 name and a $300 name
        # are not the same trade), and notional/shares gives an average print PRICE that
        # cross-checks the venue mix. Older stored weeks lack it → readers must fillna.
        try:
            notional = float(r.get("totalNotionalSum") or 0)
        except (ValueError, TypeError):
            notional = 0.0
        tier_raw = r.get("tierIdentifier") or r.get("tierDescription") or ""
        records.append({
            "week_start": week_start,
            "ticker": str(ticker).strip().upper(),
            "mpid": mpid,
            "venue_name": venue_name,
            "shares": shares,
            "trades": trades,
            "notional": notional,
            "tier": str(tier_raw).strip(),
        })
    if not records:
        return pd.DataFrame()
    return pd.DataFrame(records)


def _heartbeat(latest: date, key: str = "finra_ats__ingest") -> dict[str, pd.DataFrame]:
    hb = pd.DataFrame({"new_rows": [0]}, index=[pd.Timestamp(latest)])
    return {key: hb}


class FinraAtsTransparencyAdapter(Adapter):
    """Weekly per-ATS venue volume — FINRA OTC Transparency (keyless, T2e)."""

    name = "finra_ats_transparency"
    group = GROUP
    summary_type = SUMMARY_TYPE
    store_group = GROUP
    ingest_key = "finra_ats__ingest"
    # Staleness anchor math: the heartbeat is indexed at the newest COMPLETE
    # (T1+T2) week's START date. T2 publishes ~4wk after the week ENDS, so the
    # newest complete week_start is ~28-35d old in healthy steady state (observed
    # 40d across the 2026-07-04 holiday). 50 keeps holiday slack while flagging a
    # genuinely stalled feed within ~2 missed weeks. (The old 10 could never pass.)
    stale_after_days = 50

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        have = _have_weeks(self.store_group)
        store_dir = _store_dir(self.store_group)
        store_dir.mkdir(parents=True, exist_ok=True)

        session = requests.Session()
        session.headers["User-Agent"] = (
            "macro-dashboard research (keyless FINRA OTC Transparency API)"
        )

        try:
            partitions = _fetch_partitions(session)
        except Exception as e:  # noqa: BLE001
            if _degradable(e) and have:
                latest = max(have)
                log.warning("%s: partitions unreachable (%s); "
                            "using stored data, latest %s", self.name, e, latest)
                return _heartbeat(latest, self.ingest_key)
            raise

        complete = _complete_weeks(partitions)
        if not complete:
            if have:
                return _heartbeat(max(have), self.ingest_key)
            raise RuntimeError(f"{self.name}: no complete weeks published and no stored history")

        window = complete if full_history else complete[:RECENT_WINDOW_WEEKS]
        cap = len(window) if full_history else MAX_WEEKS_PER_RUN
        missing = [w for w in window if w not in have][:cap]
        skipped = sum(1 for w in window if w not in have) - len(missing)
        if skipped:
            log.info("%s: %d missing week(s) beyond this run's cap of %d — "
                     "will catch up on later runs", self.name, skipped, cap)

        if not missing:
            latest = max(have)
            log.info("%s: all recent complete weeks stored; latest %s", self.name, latest)
            return _heartbeat(latest, self.ingest_key)

        total_rows = 0
        written: list[date] = []
        for w in missing:
            try:
                rows = _fetch_week(session, w, self.summary_type)
            except Exception as e:  # noqa: BLE001
                # Never write a partial week. If nothing succeeded this run and
                # nothing is stored, surface the failure; otherwise degrade.
                log.warning("%s: week %s fetch failed (%s); skipping", self.name, w, e)
                if not written and not have:
                    raise
                break
            week_df = _parse_rows(rows)
            week_df = week_df[week_df["week_start"].dt.date == w]
            if week_df.empty:
                log.warning("%s: week %s returned no per-symbol rows; skipping", self.name, w)
                continue
            week_df.to_parquet(_week_path(w, self.store_group), index=False)
            total_rows += len(week_df)
            written.append(w)
            log.info("%s: stored week %s → %d rows, %d firms",
                     self.name, w, len(week_df), week_df["mpid"].nunique())

        latest = max(set(written) | have) if (written or have) else None
        if latest is None:
            raise RuntimeError(f"{self.name}: no rows returned and no stored history")
        log.info("%s: %d new week(s), %d rows total, latest %s",
                 self.name, len(written), total_rows, latest)
        hb = pd.DataFrame({"new_rows": [total_rows]}, index=[pd.Timestamp(latest)])
        return {self.ingest_key: hb}


class FinraOtcNonAtsAdapter(FinraAtsTransparencyAdapter):
    """Weekly per-symbol NON-ATS OTC volume — wholesaler/broker internalization.

    Same endpoint, same partitions, same write-once weekly contract as the ATS
    sibling; only the summaryTypeCode and the store differ. Kept as a separate
    store (data/finra_otc_nonats/) so the ATS files keep a stable schema and so
    "which venue" (ATS) never silently blends with "which wholesaler" (non-ATS).

    WHY THIS EXISTS: off-exchange volume is ATS + non-ATS, and the non-ATS half is
    the BIGGER one (ATS was 16-31% of the off-exchange total per name in week
    2026-06-22). The dark-pool desk previously attributed 100% of off-exchange
    volume to "dark pool" while showing only the ATS venue table — so its venue
    table could never account for its own headline number. Holding both halves is
    what lets the desk separate institutional block flow from retail order flow.

    Volume is far smaller than the ATS feed (~38k rows/week vs ~191k), so no
    universe filter is needed to stay size-lawful.
    """

    name = "finra_otc_nonats"
    group = GROUP_NONATS
    summary_type = SUMMARY_TYPE_NONATS
    store_group = GROUP_NONATS
    ingest_key = "finra_otc_nonats__ingest"


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    FinraAtsTransparencyAdapter().fetch()
    FinraOtcNonAtsAdapter().fetch()
