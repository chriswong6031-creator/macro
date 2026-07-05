"""FINRA consolidated short interest collector (Phase 3 factor input).

FINRA's keyless Query API publishes bi-monthly exchange-listed short interest:
shares short, average daily volume and days-to-cover per symbol. High days-to-
cover negatively predicts the cross-section (Hong-Li-Rajan-Sherman 2015), so it
feeds a `short_interest` factor in engine/equity_factors.py.

`settlementDate` is a partition key — the API forbids sorting by it unless an
EQUAL filter is given — so we probe recent candidate settlement dates (the ~15th
and month-end, newest-first), take the latest that has data, then page its full
snapshot. Written ticker-indexed to data/finra/short_interest.parquet, cached a
few days (the report is bi-monthly).
"""
from __future__ import annotations

import calendar
import json
import logging
from datetime import date, datetime, timedelta, timezone

import pandas as pd

from lib import config

log = logging.getLogger(__name__)


def _cfg() -> dict:
    return config.load()["finra"]


def _headers() -> dict:
    return {"User-Agent": _cfg()["user_agent"], "Content-Type": "application/json",
            "Accept": "application/json"}


def _post(body: dict) -> list | None:
    import requests
    try:
        r = requests.post(_cfg()["url"], data=json.dumps(body), headers=_headers(), timeout=40)
        if r.status_code != 200:
            return None
        return r.json()
    except Exception as e:  # noqa: BLE001
        log.debug("finra post failed: %s", e)
        return None


def _last_business_day(d: date) -> date:
    while d.weekday() >= 5:           # Sat/Sun -> step back to Friday
        d -= timedelta(days=1)
    return d


def _candidate_dates(n: int) -> list[str]:
    """Recent FINRA settlement dates, newest-first: the last business day on/before
    the 15th, and the last business day of each month."""
    today = datetime.now(timezone.utc).date()
    out: list[date] = []
    y, m = today.year, today.month
    for _ in range(n // 2 + 2):
        mid = _last_business_day(date(y, m, 15))
        eom = _last_business_day(date(y, m, calendar.monthrange(y, m)[1]))
        out += [eom, mid]
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    out = sorted({d for d in out if d <= today}, reverse=True)
    return [d.isoformat() for d in out[:n]]


def _latest_settlement() -> str | None:
    for d in _candidate_dates(_cfg()["lookback_dates"]):
        rows = _post({"limit": 2, "compareFilters": [
            {"compareType": "EQUAL", "fieldName": "settlementDate", "fieldValue": d}]})
        if rows:
            return d
    return None


def _snapshot(settlement: str) -> pd.DataFrame:
    cfg = _cfg()
    rows: list[dict] = []
    for page in range(cfg["max_pages"]):
        batch = _post({"limit": cfg["page_size"], "offset": page * cfg["page_size"],
                       "compareFilters": [{"compareType": "EQUAL",
                                           "fieldName": "settlementDate", "fieldValue": settlement}]})
        if not batch:
            break
        rows.extend(batch)
        if len(batch) < cfg["page_size"]:
            break
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df = df.rename(columns={"symbolCode": "ticker",
                            "currentShortPositionQuantity": "short_shares",
                            "previousShortPositionQuantity": "prev_short_shares",
                            "averageDailyVolumeQuantity": "avg_daily_vol",
                            "daysToCoverQuantity": "days_to_cover",
                            "changePercent": "si_change_pct"})
    keep = ["ticker", "short_shares", "prev_short_shares", "avg_daily_vol",
            "days_to_cover", "si_change_pct"]
    df = df[[c for c in keep if c in df.columns]].copy()
    for c in df.columns:
        if c != "ticker":
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["days_to_cover"]).drop_duplicates("ticker", keep="last")
    df["settlement_date"] = settlement
    return df.set_index("ticker")


def _universe_tickers() -> set[str]:
    out: set[str] = set()
    for grp in ("breadth", "smallcap_breadth", "midcap_breadth"):
        p = config.data_dir() / grp / "_closes_cache.parquet"
        if p.exists():
            out.update(pd.read_parquet(p).columns)
    return out


def fetch_short_interest(force: bool = False, max_age_days: int = 4) -> pd.DataFrame | None:
    cache = config.data_dir() / "finra" / "short_interest.parquet"
    cache.parent.mkdir(parents=True, exist_ok=True)
    if not force and cache.exists():
        age = (datetime.now(timezone.utc).timestamp() - cache.stat().st_mtime) / 86400.0
        if age < max_age_days:
            log.info("finra short-interest cache fresh (%.1fd)", age)
            return pd.read_parquet(cache)

    settlement = _latest_settlement()
    if not settlement:
        log.warning("finra: no recent settlement date returned data")
        return pd.read_parquet(cache) if cache.exists() else None
    snap = _snapshot(settlement)
    if snap.empty:
        return pd.read_parquet(cache) if cache.exists() else None
    universe = _universe_tickers()
    if universe:
        snap = snap[snap.index.isin(universe)]
    snap.to_parquet(cache)
    log.info("finra short interest: %d universe names, settlement %s", len(snap), settlement)

    # PIT history accrual — append-only, keyed on (settlement_date, ticker).
    # settlement_date is already in the snapshot (set above in _snapshot()).
    # capture_date records the UTC calendar day this snapshot was fetched.
    # Dedup key is (settlement_date, ticker); keep="last" so a same-day re-run
    # overwrites without duplicating (idempotent within a calendar day).
    hist_p = cache.parent / "short_interest_history.parquet"
    hist_snap = snap.copy()
    capture_date = pd.Timestamp.now("UTC").normalize().tz_localize(None)
    hist_snap["capture_date"] = capture_date
    hist_snap = hist_snap.reset_index()   # ticker becomes a column
    if hist_p.exists():
        hist_snap = pd.concat([pd.read_parquet(hist_p), hist_snap], ignore_index=True)
        hist_snap = hist_snap.drop_duplicates(
            subset=["settlement_date", "ticker"], keep="last"
        )
    hist_snap.to_parquet(hist_p)
    log.info(
        "finra short interest history: %d rows (capture %s)", len(hist_snap), capture_date.date()
    )

    return snap
