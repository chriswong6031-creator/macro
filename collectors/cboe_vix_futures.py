"""CBOE VIX-futures settlement collector — the front-month VX print that powers the
dislocation engine's thin-quote SANITIZER, plus the FULL M1..M6 VX term-structure curve.

On 5-Aug-2024 spot VIX printed ~65 intraday on thin early-session SPX option quotes
while the front VIX FUTURE stayed below ~35 (SEC DERA). A naive "VIX>30/40 =
capitulation" rule fires on that partly-fictitious number. Storing the front VX
settlement lets engine/dislocation.py cross-check spot VIX against it and flag the
spot print UNRELIABLE rather than treat it as a real panic trigger.

Two series are persisted from the SAME daily CSV (so the curve costs no extra requests):

  • vix_futures (front_settle, days_to_expiry) — the nearest non-expired VX contract
    (weekly OR monthly), the comparison the sanitizer already relies on. UNCHANGED.
  • vix_curve (m1..m6 settle + dte) — the full STANDARD MONTHLY VX ladder. The settlement
    CSV mixes weekly VX (week-number-prefixed symbols, e.g. VX25/M6) with the standard
    monthly contracts (bare VX/{Mon}{Yr}); the curve keeps only the monthlies, sorted by
    expiry, so slope/carry (M1/M2 contango, roll yield) become a clean, single time series.
    This is the futures analog of the VIX/VIX3M spot term structure engine/vol_regime
    already scores — but on the actual tradeable curve, with a real roll yield.

ACCRUAL CLOCK: there is NO bulk historical settlement file (each date is one request via
the www endpoint; the cdn.* path 403s bots). So vix_curve accrues FORWARD only — it seeds
to the same modest depth as the front-month backfill (the same ~45 CSVs, for free) but has
no deep history. Curve slope/carry therefore becomes validatable in ~12 months of forward
accrual, not now. See research/VOL_REGIME_DATA_ACCRUAL.md. Degrades to "no data" on
holidays/weekends and never raises into the run unless nothing at all is fetched.
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
MONTH_CURVE_N = 6     # M1..M6 monthly VX ladder persisted for the term-structure/carry clock


class CboeVixFuturesAdapter(Adapter):
    name = "cboe_vix_futures"
    group = "cboe"
    stale_after_days = 5

    def __init__(self) -> None:
        self.cfg = config.load().get("cboe", {})

    def _vx_rows(self, d: date) -> pd.DataFrame | None:
        """Cleaned VX settlement rows for one date (cols: exp, px, monthly), or None when
        that day has no data (holiday/weekend/blocked). Fetched ONCE; both the front-month
        and the full curve derive from it."""
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
        # STANDARD MONTHLY = the symbol's pre-"/" token is exactly "VX"; weeklies carry a
        # week-number prefix (VX25/M6, VX30/N6). Absent/odd Symbol column -> not monthly
        # (curve just doesn't accrue that day; the front-month read is unaffected).
        sym = (vx["Symbol"].astype(str) if "Symbol" in vx.columns
               else pd.Series("", index=vx.index))
        vx["monthly"] = sym.str.split("/").str[0].str.upper().eq("VX")
        return vx.dropna(subset=["exp", "px"])

    @staticmethod
    def _front(rows: pd.DataFrame, d: date) -> dict | None:
        """Nearest non-expired VX contract (weekly or monthly) = the front the sanitizer
        compares spot VIX against. Behaviour is unchanged from the single-series collector."""
        future = rows[rows["exp"] > pd.Timestamp(d)]
        if future.empty:
            return None
        front = future.loc[future["exp"].idxmin()]
        return {"front_settle": round(float(front["px"]), 4),
                "days_to_expiry": int((front["exp"].date() - d).days)}

    @staticmethod
    def _curve(rows: pd.DataFrame, d: date) -> dict | None:
        """M1..M6 STANDARD-MONTHLY VX settlements + days-to-expiry for one date, or None
        when no monthly contracts are present. Ragged tails (a day listing only 5 monthlies)
        simply omit m6 — store.upsert aligns columns and never drops prior history."""
        mon = rows[rows["monthly"] & (rows["exp"] > pd.Timestamp(d))].sort_values("exp")
        if mon.empty:
            return None
        row: dict[str, float | int] = {}
        for i, (_, c) in enumerate(mon.head(MONTH_CURVE_N).iterrows(), start=1):
            row[f"m{i}_settle"] = round(float(c["px"]), 4)
            row[f"m{i}_dte"] = int((c["exp"].date() - d).days)
        return row

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        ndays = int(self.cfg.get("vix_backfill_days", 45) if full_history
                    else self.cfg.get("vix_recent_days", 6))
        pace = float(self.cfg.get("vix_request_pace_s", 0.4))
        fronts: dict[pd.Timestamp, dict] = {}
        curves: dict[pd.Timestamp, dict] = {}
        d, got, misses = date.today(), 0, 0
        while got < ndays and misses < 10:
            if d.weekday() < 5:                        # Mon-Fri only
                rows = self._vx_rows(d)
                if rows is not None and not rows.empty:
                    front = self._front(rows, d)
                    curve = self._curve(rows, d)
                    if front is not None:
                        fronts[pd.Timestamp(d)] = front
                    if curve is not None:
                        curves[pd.Timestamp(d)] = curve
                    if front is not None or curve is not None:
                        got += 1
                        misses = 0
                    else:
                        misses += 1
                else:
                    misses += 1
                time.sleep(pace)
            d -= timedelta(days=1)
        out: dict[str, pd.DataFrame] = {}
        if fronts:
            out["vix_futures"] = pd.DataFrame.from_dict(fronts, orient="index").sort_index()
        if curves:
            out["vix_curve"] = pd.DataFrame.from_dict(curves, orient="index").sort_index()
        if not out:
            raise ValueError("no VIX-future settlements fetched (endpoint may have moved)")
        return out
