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


def _cache_age_days(p) -> float | None:
    """Age of the short-interest cache in days, from its embedded `asof`
    (fetch-date) column — NEVER file mtime. On CI runners a checkout rewrites
    files with mtime = checkout time, so a committed months-old cache always
    looks brand-new by mtime and the refresh short-circuits forever (the
    polygon-universe frozen-cache class, #2690; this cache froze at its
    2026-06-13 fill the same way). Unreadable or asof-less caches return
    None — the caller treats that as stale and refetches."""
    try:
        asof = pd.read_parquet(p, columns=["asof"])["asof"].dropna()
        if asof.empty:
            return None
        newest = max(date.fromisoformat(str(v)) for v in asof.unique())
        return float((date.today() - newest).days)
    except Exception as e:  # noqa: BLE001
        log.warning("finra: cannot read asof from %s (%s) — treating as stale", p, e)
        return None


def fetch_short_interest(force: bool = False, max_age_days: int = 4) -> pd.DataFrame | None:
    cache = config.data_dir() / "finra" / "short_interest.parquet"
    cache.parent.mkdir(parents=True, exist_ok=True)
    if not force and cache.exists():
        age = _cache_age_days(cache)
        if age is not None and age < max_age_days:
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
    # embedded fetch-date stamp — the freshness gate reads THIS, never mtime (#2690 class)
    snap["asof"] = date.today().isoformat()
    snap.to_parquet(cache)
    log.info("finra short interest: %d universe names, settlement %s", len(snap), settlement)

    # "Latest-known-per-settlement" convenience store — NOT a PIT-safe backtest source.
    #
    # Dedup key is (settlement_date, ticker) with keep="last".  This means that if
    # the same settlement is captured on two different calendar days (e.g. because
    # FINRA restated/corrected a figure), the LATER capture wins and the earlier
    # vintage is overwritten.  capture_date is stored as a column but cannot be used
    # to reconstruct point-in-time state because prior rows are deleted on restatement.
    #
    # This design is intentional for the current consumer (engine/equity_factors.py),
    # which only needs the most-recent best estimate of short interest.  Any future
    # consumer that requires PIT correctness — e.g. a backtest that must join on what
    # was knowable on a given date — MUST NOT use short_interest_history.parquet as-is
    # and must instead build a true vintage matrix keyed on (settlement_date, ticker,
    # capture_date) where all captures are retained.
    #
    # Contrast: collectors/finra_short_volume.py uses (date, ticker) safely because
    # daily short-volume data is never revised by FINRA.
    hist_p = cache.parent / "short_interest_history.parquet"
    hist_snap = snap.drop(columns=["asof"]).copy()   # history keeps its own capture_date; no asof stamp
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
