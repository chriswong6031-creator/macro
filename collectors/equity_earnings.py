"""Per-stock earnings calendar + surprise history (Phase 2 of
research/STOCK_FUNDAMENTALS_PLAN.md).

Nasdaq's public JSON is the one free source that gives, for the whole US universe:
  next earnings DATE   api.nasdaq.com/api/calendar/earnings?date=YYYY-MM-DD
                       (date-keyed → a ~6-week sweep of weekdays covers everyone in
                        ~30 calls; the earliest hit per ticker is its next report)
  SURPRISE history     api.nasdaq.com/api/company/{sym}/earnings-surprise
                       (last 4 quarters: actual EPS vs consensus + surprise %)

It is UNOFFICIAL and Akamai bot-walled, so: a browser User-Agent, and a CI CANARY —
if the first calendar call is blocked (403/empty), we log and return the existing
cache untouched rather than spend the run hammering a wall. Best-effort, resumable
(surprise history dripped + capped), never fatal to the build.

Writes data/earnings/earnings.parquet (ticker-indexed: next_date, next_time,
eps_forecast, surprises_json, as_of). engine/stock_fundamentals reads it for the
Earnings panel (countdown + beat/miss table). Honest caveat (on the page): dates are
estimated and can move; data is community/Nasdaq-sourced, not official guidance.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta, timezone

import pandas as pd

from lib import config

log = logging.getLogger(__name__)

CALENDAR = "https://api.nasdaq.com/api/calendar/earnings?date={}"
SURPRISE = "https://api.nasdaq.com/api/company/{}/earnings-surprise"
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*", "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.nasdaq.com", "Referer": "https://www.nasdaq.com/",
}
SWEEP_DAYS = 66           # weekdays (~a full quarter) so every name's next report lands
REFRESH_DAYS = 7


def _cache_path():
    p = config.data_dir() / "earnings" / "earnings.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _num(x) -> float | None:
    try:
        v = float(str(x).replace("$", "").replace(",", "").replace("%", "").strip())
    except (TypeError, ValueError):
        return None
    return v if v == v else None


def _get_json(session, url: str, retries: int = 2):
    for attempt in range(retries):
        try:
            r = session.get(url, timeout=20)
            if r.status_code == 403:
                return "blocked"
            r.raise_for_status()
            if "json" not in r.headers.get("content-type", ""):
                return None
            return r.json()
        except Exception as e:  # noqa: BLE001
            if attempt == retries - 1:
                log.debug("nasdaq GET failed %s: %s", url[-40:], e)
                return None
            time.sleep(1.0 * (attempt + 1))
    return None


def _universe() -> set[str]:
    out: set[str] = set()
    for grp in ("breadth", "smallcap_breadth", "midcap_breadth"):
        p = config.data_dir() / grp / "constituents.parquet"
        if p.exists():
            out.update(str(t) for t in pd.read_parquet(p).index)
    return out


def _calendar_sweep(session, universe: set[str]) -> tuple[dict, bool]:
    """{ticker: {next_date, next_time, eps_forecast}} from the upcoming weekday
    calendars. Returns ({}, blocked=True) if the first call is bot-walled."""
    out: dict[str, dict] = {}
    d = datetime.now(timezone.utc).date()
    checked = 0
    first = True
    while checked < SWEEP_DAYS:
        if d.weekday() < 5:                       # weekdays only
            data = _get_json(session, CALENDAR.format(d.isoformat()))
            if first:
                first = False
                if data == "blocked":
                    return {}, True               # CI canary: bot-walled → bail
            rows = ((data or {}).get("data") or {}).get("rows") or [] if data != "blocked" else []
            for r in rows:
                sym = (r.get("symbol") or "").upper()
                if sym and sym in universe and sym not in out:
                    out[sym] = {"next_date": d.isoformat(), "next_time": r.get("time"),
                                "eps_forecast": _num(r.get("epsForecast"))}
            checked += 1
            time.sleep(0.25)
        d += timedelta(days=1)
    return out, False


def _surprises(session, sym: str) -> list[dict]:
    data = _get_json(session, SURPRISE.format(sym))
    if not data or data == "blocked":
        return []
    rows = ((data.get("data") or {}).get("earningsSurpriseTable") or {}).get("rows") or []
    out = []
    for r in rows:
        out.append({"qtr": r.get("fiscalQtrEnd"), "reported": r.get("dateReported"),
                    "eps": _num(r.get("eps")), "consensus": _num(r.get("consensusForecast")),
                    "surprise_pct": _num(r.get("percentageSurprise"))})
    return out


def fetch_earnings(force: bool = False, max_new: int = 120,
                   tickers: list[str] | None = None) -> pd.DataFrame:
    """Sweep the calendar (cheap, whole universe) + drip surprise history (capped).
    Best-effort + bot-wall-aware: returns the existing cache untouched if blocked."""
    import requests
    cache = _cache_path()
    existing = pd.read_parquet(cache) if cache.exists() else pd.DataFrame()
    universe = set(tickers) if tickers else _universe()
    if not universe:
        return existing

    session = requests.Session()
    session.headers.update(HEADERS)

    cal, blocked = _calendar_sweep(session, universe)
    if blocked:
        log.warning("equity_earnings: Nasdaq calendar bot-walled (likely CI IP) — keeping cache")
        return existing
    log.info("equity_earnings: calendar sweep found next dates for %d names", len(cal))

    # surprise history: refresh stale/uncached names, capped
    def stale(t: str) -> bool:
        if force or existing.empty or t not in existing.index:
            return True
        ts = existing.loc[t].get("as_of")
        try:
            return (datetime.now(timezone.utc) - pd.to_datetime(ts)).days > REFRESH_DAYS
        except Exception:  # noqa: BLE001
            return True

    todo = [t for t in (tickers or sorted(cal) or list(universe)) if stale(t)][:max_new]
    now = datetime.now(timezone.utc).isoformat()
    rows = []
    for t in todo:
        surp = _surprises(session, t)
        time.sleep(0.25)
        cc = cal.get(t, {})
        rows.append({"ticker": t, "next_date": cc.get("next_date"),
                     "next_time": cc.get("next_time"), "eps_forecast": cc.get("eps_forecast"),
                     "surprises_json": json.dumps(surp), "as_of": now})

    fresh = pd.DataFrame(rows).set_index("ticker") if rows else pd.DataFrame()
    # also refresh next_date for cached names found in this sweep (cheap, no extra call)
    if not existing.empty:
        existing = existing.copy()
        for t, cc in cal.items():
            if t in existing.index and (fresh.empty or t not in fresh.index):
                existing.loc[t, "next_date"] = cc.get("next_date")
                existing.loc[t, "next_time"] = cc.get("next_time")
                existing.loc[t, "eps_forecast"] = cc.get("eps_forecast")
    if not existing.empty and not fresh.empty:
        out = pd.concat([existing[~existing.index.isin(fresh.index)], fresh])
    else:
        out = fresh if not fresh.empty else existing
    if not out.empty:
        out.to_parquet(cache)
    log.info("equity_earnings: cache now %d tickers (%d with a next date)",
             len(out), int(out["next_date"].notna().sum()) if "next_date" in out else 0)
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    import sys
    ts = sys.argv[1:] or ["AAPL", "NVDA", "JPM"]
    df = fetch_earnings(force=True, max_new=len(ts), tickers=ts)
    for t in ts:
        if t in df.index:
            r = df.loc[t]
            surp = json.loads(r.get("surprises_json") or "[]")
            print(f"\n{t}: next={r.get('next_date')} ({r.get('next_time')}) est={r.get('eps_forecast')}")
            for s in surp:
                print(f"   {s['qtr']}: actual {s['eps']} vs est {s['consensus']} → {s['surprise_pct']}%")
