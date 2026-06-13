"""bitcoin-data.com (BGeometrics) collector — free tier, QUOTA-AWARE.

The hard constraints (verified 2026-06-12):
- 10 requests/hour, 15/day PER IP (CI shared-runner IPs may collide with
  strangers' usage — treat quota exhaustion as routine, not exceptional).
- History limited to a rolling ~4-year window -> archive-forever policy:
  every row we ever pull is kept by store.upsert(); the window slides but our
  parquet doesn't forget (same pattern as the FRED OAS cache).

Design:
- One request per metric per run, in config priority order, with
  startday = last stored date (re-fetches last point; upsert dedupes).
- Stop cleanly the moment quota headers (X-RateLimit-Remaining-*) hit zero or
  a 429 lands; return whatever was fetched. Partial success is success —
  metrics skipped today self-heal tomorrow because each call covers a range.
- fetch() raises only if NOTHING could be fetched (so the circuit breaker
  still notices a genuinely dead source).
"""
from __future__ import annotations

import logging
import time
from datetime import date, timedelta

import pandas as pd
import requests

from collectors.base import Adapter
from lib import config, store

log = logging.getLogger(__name__)


class BgeoAdapter(Adapter):
    name = "bgeo"
    group = "bgeo"
    stale_after_days = 4

    def __init__(self) -> None:
        self.cfg = config.load()["bgeo"]
        self.remaining_hour: int | None = None
        self.remaining_day: int | None = None

    # -- quota bookkeeping ----------------------------------------------------
    def _note_quota(self, r: requests.Response) -> None:
        def _h(name: str) -> int | None:
            v = r.headers.get(name)
            return int(v) if v is not None and v.isdigit() else None
        self.remaining_hour = _h("X-RateLimit-Remaining-Hour")
        self.remaining_day = _h("X-RateLimit-Remaining-Day")

    def _quota_left(self) -> bool:
        if self.remaining_hour is not None and self.remaining_hour <= 0:
            return False
        if self.remaining_day is not None and self.remaining_day <= 0:
            return False
        return True

    # -- fetch ------------------------------------------------------------------
    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        metrics: dict[str, str] = self.cfg["metrics"]
        budget = int(self.cfg["daily_request_budget"])
        out: dict[str, pd.DataFrame] = {}
        skipped: list[str] = []
        spent = 0

        for endpoint, col in metrics.items():
            if spent >= budget or not self._quota_left():
                skipped.append(endpoint)
                continue
            last = store.last_date(self.group, col)
            if last and not full_history:
                startday = str(last)  # overlap one point; upsert dedupes
            else:
                startday = self.cfg["window_start"]
            try:
                spent += 1
                df = self._fetch_metric(endpoint, col, startday)
                if df is not None and not df.empty:
                    out[col] = df
            except QuotaExhausted:
                skipped.append(endpoint)
                log.warning("bgeo quota exhausted after %d requests; skipping rest", spent)
                # mark quota dead so the loop drains without further requests
                self.remaining_hour = 0
            except Exception as e:  # noqa: BLE001 — one metric must not kill the rest
                log.warning("bgeo metric %s failed: %s", endpoint, e)

        if skipped:
            log.info("bgeo skipped (quota/budget): %s — will self-heal next run",
                     ",".join(skipped))
        if not out:
            raise ValueError(f"bgeo fetched nothing (spent={spent}, skipped={skipped})")
        return out

    def _fetch_metric(self, endpoint: str, col: str, startday: str) -> pd.DataFrame | None:
        url = f"{self.cfg['base_url']}/v1/{endpoint}"
        params = {"startday": startday, "size": str(self.cfg["page_size"])}
        r = requests.get(url, params=params, timeout=60,
                         headers={"User-Agent": config.load()["sponsors"]["user_agent"]})
        self._note_quota(r)
        if r.status_code == 429:
            raise QuotaExhausted(r.headers.get("X-RateLimit-Reset-Hour", "?"))
        r.raise_for_status()
        rows = r.json()
        if not isinstance(rows, list) or not rows:
            return None
        df = pd.DataFrame(rows)
        if "d" not in df.columns:
            raise ValueError(f"{endpoint}: unexpected schema {list(df.columns)[:6]}")
        # generic shape: {"d": date, "unixTs": ..., "<value>": number, ...}
        value_cols = [c for c in df.columns if c not in ("d", "unixTs")]
        if not value_cols:
            raise ValueError(f"{endpoint}: no value column")
        idx = pd.to_datetime(df["d"].str.slice(0, 10))
        if len(value_cols) == 1:
            out = pd.DataFrame({col: pd.to_numeric(df[value_cols[0]], errors="coerce").values},
                               index=idx)
        else:  # multi-column endpoints keep their own names, prefixed
            out = pd.DataFrame(index=idx)
            for c in value_cols:
                out[f"{col}_{c}"] = pd.to_numeric(df[c], errors="coerce").values
        out = out.dropna(how="all")
        time.sleep(1.0)  # gentle pacing between quota-counted calls
        return out


class QuotaExhausted(Exception):
    pass
