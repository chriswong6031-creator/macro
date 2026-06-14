"""CBOE VIX-futures settlement collector — the front-month VX print that powers the
dislocation engine's thin-quote SANITIZER.

On 5-Aug-2024 spot VIX printed ~65 intraday on thin early-session SPX option quotes
while the front VIX FUTURE stayed below ~35 (SEC DERA). A naive "VIX>30/40 =
capitulation" rule fires on that partly-fictitious number. Storing the front VX
settlement lets engine/dislocation.py cross-check spot VIX against it and flag the
spot print UNRELIABLE rather than treat it as a real panic trigger.

Source: CBOE's keyless daily settlement CSV — ONE request per date (there is no bulk
file; the cdn.* path 403s bots, but the www endpoint serves clean CSV). Columns:
Product, Symbol, Expiration Date, Price. We keep the VX rows and take the nearest
NON-expired contract as the front month. The sanitizer only needs the current front,
so history accrues going forward; a modest backfill seeds it. Degrades to "no data"
on holidays/weekends and never raises into the run unless nothing at all is fetched.
"""
from __future__ import annotations

import io
import logging
import time
from datetime import date, timedelta

import pandas as pd

from collectors.base import Adapter
from lib import config

log = logging.getLogger(__name__)

# keyless. The cdn.cboe.com settlement path 403s for bots; the www endpoint works.
SETTLE_URL = "https://www.cboe.com/us/futures/market_statistics/settlement/csv/?dt={date}"
UA = "Mozilla/5.0 (macro-dashboard research)"


class CboeVixFuturesAdapter(Adapter):
    name = "cboe_vix_futures"
    group = "cboe"
    stale_after_days = 5

    def __init__(self) -> None:
        self.cfg = config.load().get("cboe", {})

    def _front(self, d: date) -> dict | None:
        """Front-month VX settlement for one date, or None if that day has no data."""
        url = self.cfg.get("vix_settlement_url", SETTLE_URL).format(date=d.isoformat())
        try:
            r = self.http_get(url, retries=2, timeout=30, headers={"User-Agent": UA})
        except Exception:  # noqa: BLE001 — a missing day (holiday/weekend) is normal
            return None
        if "csv" not in r.headers.get("Content-Type", "").lower() or not r.text.strip():
            return None
        try:
            df = pd.read_csv(io.StringIO(r.text))
        except Exception:  # noqa: BLE001
            return None
        if "Product" not in df.columns or "Expiration Date" not in df.columns:
            return None
        vx = df[df["Product"].astype(str).str.upper() == "VX"].copy()
        if vx.empty:
            return None
        vx["exp"] = pd.to_datetime(vx["Expiration Date"], errors="coerce")
        vx["px"] = pd.to_numeric(vx["Price"], errors="coerce")
        vx = vx.dropna(subset=["exp", "px"])
        future = vx[vx["exp"] > pd.Timestamp(d)]      # nearest non-expired contract = front
        if future.empty:
            return None
        front = future.loc[future["exp"].idxmin()]
        return {"front_settle": round(float(front["px"]), 4),
                "days_to_expiry": int((front["exp"].date() - d).days)}

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        ndays = int(self.cfg.get("vix_backfill_days", 45) if full_history
                    else self.cfg.get("vix_recent_days", 6))
        pace = float(self.cfg.get("vix_request_pace_s", 0.4))
        rows: dict[pd.Timestamp, dict] = {}
        d, got, misses = date.today(), 0, 0
        while got < ndays and misses < 10:
            if d.weekday() < 5:                        # Mon-Fri only
                front = self._front(d)
                if front is not None:
                    rows[pd.Timestamp(d)] = front
                    got += 1
                    misses = 0
                else:
                    misses += 1
                time.sleep(pace)
            d -= timedelta(days=1)
        if not rows:
            raise ValueError("no VIX-future settlements fetched (endpoint may have moved)")
        return {"vix_futures": pd.DataFrame.from_dict(rows, orient="index").sort_index()}
