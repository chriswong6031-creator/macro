"""US IPO calendar — the keyless deal-reference feed behind the IPO Radar.

Nasdaq's public JSON is the one free source that lists, by month, the whole US
new-issue pipeline with offer terms:

  api.nasdaq.com/api/ipo/calendar?date=YYYY-MM
      data.priced     -> ticker, company, exchange, offer PRICE, shares, $ size, pricedDate
      data.upcoming   -> ticker, company, exchange, price RANGE, shares, expectedPriceDate
      data.filed      -> ticker, company, filedDate, $ size  (S-1 on file, not yet priced)
      data.withdrawn  -> pulled deals

Like collectors/equity_earnings.py this is UNOFFICIAL and Akamai bot-walled, so it
uses a browser User-Agent and a CI CANARY: if the first month's call is blocked
(403/empty), we log and return the existing cache untouched rather than hammer a
wall. It is therefore *seeded locally and committed* (data/ipo/calendar.parquet is
git-tracked, like data/earnings/earnings.parquet) so the live page has deals even
when CI's IP is walled; a successful CI run refreshes it.

This is DEAL REFERENCE DATA, not a time series — keyed by Nasdaq dealID and merged
across runs (newer status wins, e.g. filed -> priced), so the priced-deal history
keeps growing even after old months age out of the queryable window. Run/refresh
is driven by scripts/build_ipo.py (the build step), NOT scripts/collect.py — the
same pattern equity_earnings uses, because the circuit-breaker runner's validate()
assumes a datetime/numeric series and this is a string record table.

Honest caveat (surfaced on the page): community/Nasdaq-sourced, not official; the
predictive demand signals (oversubscription, book demand, allocation) are NOT here
— they live in paid feeds (Dealogic/Bloomberg). This gives the calendar + offer
terms only.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone

import pandas as pd

from lib import config

log = logging.getLogger(__name__)

CALENDAR = "https://api.nasdaq.com/api/ipo/calendar?date={}"   # YYYY-MM
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*", "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.nasdaq.com", "Referer": "https://www.nasdaq.com/",
}
LOOKBACK_MONTHS = 18   # keep ~1.5y of priced deals so "recent listings" stays populated
AHEAD_MONTHS = 2       # upcoming / expected-to-price window

# SPACs/blank-checks distort IPO base rates (they price at $10, "pop" rarely) so we
# FLAG (never drop) them; the page can separate operating-company IPOs from SPACs.
_SPAC_RE = re.compile(r"acquisition corp|acquisition compan|blank check|"
                      r"acquisition holding|capital acquisition", re.I)


def _cache_path():
    p = config.data_dir() / "ipo" / "calendar.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _num(x) -> float | None:
    try:
        v = float(str(x).replace("$", "").replace(",", "").replace("%", "").strip())
    except (TypeError, ValueError):
        return None
    return v if v == v else None


def _date_iso(x) -> str | None:
    if not x:
        return None
    d = pd.to_datetime(str(x), errors="coerce")
    return None if pd.isna(d) else d.strftime("%Y-%m-%d")


def _price_range(x) -> tuple[float | None, float | None, float | None]:
    """'14.00-16.00' -> (14.0, 16.0, 15.0); '18.00' -> (18.0, 18.0, 18.0)."""
    if not x:
        return None, None, None
    parts = [p for p in re.split(r"[-–]", str(x)) if p.strip()]
    nums = [_num(p) for p in parts]
    nums = [n for n in nums if n is not None]
    if not nums:
        return None, None, None
    lo, hi = min(nums), max(nums)
    return lo, hi, round((lo + hi) / 2, 4)


def _is_spac(name: str | None, ticker: str | None, offer: float | None) -> bool:
    if name and _SPAC_RE.search(name):
        return True
    # $10 unit ticker (…U) is the classic SPAC tell
    t = (ticker or "").upper().replace("'", "").replace(".", "")
    return bool(t.endswith("U") and len(t) >= 4 and offer is not None and abs(offer - 10.0) < 0.01)


def _months(lookback: int, ahead: int) -> list[str]:
    now = datetime.now(timezone.utc)
    base = now.year * 12 + (now.month - 1)
    out = []
    for k in range(-lookback, ahead + 1):
        m = base + k
        out.append(f"{m // 12:04d}-{(m % 12) + 1:02d}")
    return out


def _get_json(session, url: str, retries: int = 2):
    for attempt in range(retries):
        try:
            r = session.get(url, timeout=25)
            if r.status_code == 403:
                return "blocked"
            r.raise_for_status()
            if "json" not in r.headers.get("content-type", ""):
                return None
            return r.json()
        except Exception as e:  # noqa: BLE001
            if attempt == retries - 1:
                log.debug("nasdaq ipo GET failed %s: %s", url[-18:], e)
                return None
            time.sleep(1.0 * (attempt + 1))
    return None


def _rows_from_month(data: dict) -> list[dict]:
    d = (data or {}).get("data") or {}
    out: list[dict] = []

    def base(r: dict, status: str) -> dict:
        tk = (r.get("proposedTickerSymbol") or "").upper().strip() or None
        nm = (r.get("companyName") or "").strip() or None
        offer = _num(r.get("proposedSharePrice"))
        lo, hi, mid = _price_range(r.get("proposedSharePrice"))
        return {
            "deal_id": r.get("dealID"), "ticker": tk, "company": nm,
            "exchange": (r.get("proposedExchange") or "").strip() or None,
            "status": status,
            "offer_price": offer if (offer and lo == hi) else None,  # single price = final
            "range_low": lo, "range_high": hi, "range_mid": mid,
            "shares": _num(r.get("sharesOffered")),
            "offer_value_usd": _num(r.get("dollarValueOfSharesOffered")),
            "priced_date": _date_iso(r.get("pricedDate")),
            "expected_date": _date_iso(r.get("expectedPriceDate")),
            "filed_date": _date_iso(r.get("filedDate")),
            "withdraw_date": _date_iso(r.get("withdrawDate")),
            "is_spac": _is_spac(nm, tk, offer if (offer and lo == hi) else mid),
        }

    for r in ((d.get("priced") or {}).get("rows") or []):
        out.append(base(r, "priced"))
    for r in (((d.get("upcoming") or {}).get("upcomingTable") or {}).get("rows") or []):
        out.append(base(r, "upcoming"))
    for r in ((d.get("filed") or {}).get("rows") or []):
        out.append(base(r, "filed"))
    for r in ((d.get("withdrawn") or {}).get("rows") or []):
        out.append(base(r, "withdrawn"))
    return [r for r in out if r.get("deal_id")]


# status precedence so a later run can promote a deal but never demote it on a
# transient empty section (priced is terminal-good; withdrawn is terminal-bad)
_RANK = {"filed": 0, "upcoming": 1, "priced": 3, "withdrawn": 3}


def fetch_ipo_calendar(lookback: int = LOOKBACK_MONTHS, ahead: int = AHEAD_MONTHS,
                       force: bool = False) -> pd.DataFrame:
    """Sweep the rolling month window, parse, and merge into the cache by deal_id.
    Best-effort + bot-wall-aware: returns the existing cache if the first call is
    blocked. Never raises (the build must survive a walled IP)."""
    import requests
    cache = _cache_path()
    existing = pd.read_parquet(cache) if cache.exists() else pd.DataFrame()

    session = requests.Session()
    session.headers.update(HEADERS)

    fresh: dict[str, dict] = {}
    first = True
    for ym in _months(lookback, ahead):
        data = _get_json(session, CALENDAR.format(ym))
        if first:
            first = False
            if data == "blocked":
                log.warning("ipo_calendar: Nasdaq bot-walled (likely CI IP) — keeping cache")
                return existing
        if data and data != "blocked":
            for row in _rows_from_month(data):
                did = row["deal_id"]
                prev = fresh.get(did)
                if prev is None or _RANK.get(row["status"], 0) >= _RANK.get(prev["status"], 0):
                    fresh[did] = row
        time.sleep(0.25)

    if not fresh:
        return existing

    now = datetime.now(timezone.utc).isoformat()
    new_df = pd.DataFrame(list(fresh.values()))
    new_df["as_of"] = now
    new_df = new_df.set_index("deal_id")

    if not existing.empty:
        existing = existing.copy()
        if "deal_id" in existing.columns:           # legacy frame stored deal_id as a column
            existing = existing.set_index("deal_id")
        # newer status wins; deals that aged out of the window are preserved as-is
        keep = existing[~existing.index.isin(new_df.index)]
        out = pd.concat([keep, new_df])
    else:
        out = new_df

    out = out.sort_values(["priced_date", "expected_date", "filed_date"],
                          na_position="first")
    out.to_parquet(cache)
    n_priced = int((out["status"] == "priced").sum())
    log.info("ipo_calendar: cache now %d deals (%d priced, %d SPAC-flagged)",
             len(out), n_priced, int(out["is_spac"].sum()))
    return out


def load_calendar() -> pd.DataFrame:
    """Read the cached calendar (deal_id index). Empty frame if never collected."""
    p = _cache_path()
    if not p.exists():
        return pd.DataFrame()
    df = pd.read_parquet(p)
    if "deal_id" in df.columns:
        df = df.set_index("deal_id")
    return df


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    df = fetch_ipo_calendar(force=True)
    if df.empty:
        print("no data (blocked or empty)")
    else:
        print(f"{len(df)} deals; by status:\n{df['status'].value_counts()}")
        rec = df[df["status"] == "priced"].sort_values("priced_date").tail(8)
        for did, r in rec.iterrows():
            tag = " [SPAC]" if r.get("is_spac") else ""
            print(f"  {r['priced_date']}  {r['ticker'] or '?':6}  ${r.get('offer_price')}"
                  f"  {r['company']}{tag}")
