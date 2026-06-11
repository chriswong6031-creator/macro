"""Adapter layer. Every external source implements Adapter; the runner wraps
fetch() with retry/backoff and a circuit breaker so one broken scraper can
never kill the run — it logs the gap, marks the source stale, and moves on.
"""
from __future__ import annotations

import logging
import time
import traceback
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

import pandas as pd
import requests

from lib import config, store

log = logging.getLogger(__name__)

CIRCUIT_BREAKER_FAILS = 3  # consecutive run failures -> mark dead, skip


@dataclass
class FetchResult:
    source: str
    status: str            # ok | stale | failed | dead | skipped
    rows: int = 0
    last_date: str | None = None
    error: str | None = None
    notes: list[str] = field(default_factory=list)


class Adapter:
    """Subclass per source. fetch() returns the canonical DataFrame(s) and is
    allowed to raise — the runner handles failure."""

    name: str = "base"
    group: str = "misc"

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        """Return {series_name: DataFrame indexed by date}. Raise on failure."""
        raise NotImplementedError

    def validate(self, name: str, df: pd.DataFrame) -> pd.DataFrame:
        """Basic sanity: datetime index, numeric columns, no all-NaN."""
        if df is None or df.empty:
            raise ValueError(f"{self.name}/{name}: empty frame")
        df = df.copy()
        df.index = pd.to_datetime(df.index).normalize()
        df = df[~df.index.duplicated(keep="last")].sort_index()
        df = df.dropna(how="all")
        if df.empty:
            raise ValueError(f"{self.name}/{name}: all-NaN after cleaning")
        return df

    def last_good_date(self) -> date | None:
        dates = [d for d in (store.last_date(self.group, n) for n in self.stored_series()) if d]
        return max(dates) if dates else None

    def stored_series(self) -> list[str]:
        d = config.data_dir() / self.group
        if not d.exists():
            return []
        return [p.stem for p in d.glob("*.parquet")]

    # -- shared HTTP helpers ---------------------------------------------------
    def http_get(self, url: str, retries: int = 3, backoff_base: float = 3.0,
                 timeout: int = 60, **kwargs) -> requests.Response:
        headers = kwargs.pop("headers", {})
        headers.setdefault("User-Agent",
                           config.load()["sponsors"]["user_agent"])
        last_exc: Exception | None = None
        for attempt in range(retries):
            try:
                r = requests.get(url, timeout=timeout, headers=headers, **kwargs)
                if r.status_code in (429, 500, 502, 503, 504):
                    raise requests.HTTPError(f"HTTP {r.status_code}", response=r)
                r.raise_for_status()
                return r
            except Exception as e:  # noqa: BLE001 — retried, then surfaced by runner
                last_exc = e
                wait = backoff_base * (2 ** attempt)
                log.warning("%s GET %s attempt %d/%d failed (%s); retry in %.0fs",
                            self.name, url.split("?")[0], attempt + 1, retries, e, wait)
                if attempt < retries - 1:
                    time.sleep(wait)
        raise last_exc  # type: ignore[misc]


def _breaker_state() -> dict:
    return store.read_status().get("circuit_breaker", {})


def run_adapter(adapter: Adapter, full_history: bool = False,
                stale_after_days: int = 5) -> FetchResult:
    """Execute one adapter with circuit breaker + graceful degradation."""
    breaker = _breaker_state()
    fails = breaker.get(adapter.name, 0)
    if fails >= CIRCUIT_BREAKER_FAILS and not full_history:
        return FetchResult(adapter.name, "dead", error=f"circuit open ({fails} consecutive failures)")

    try:
        frames = adapter.fetch(full_history=full_history)
        rows, last = 0, None
        for series_name, df in frames.items():
            df = adapter.validate(series_name, df)
            merged = store.upsert(adapter.group, series_name, df,
                                  outlier_col=df.columns[0] if len(df.columns) == 1 else None)
            rows += len(df)
            last = max(filter(None, [last, merged.index.max()]))
        status = "ok"
        if last is not None:
            age = (datetime.now(timezone.utc).date() - last.date()).days
            if age > stale_after_days:
                status = "stale"
        return FetchResult(adapter.name, status, rows=rows,
                           last_date=str(last.date()) if last is not None else None)
    except Exception as e:  # noqa: BLE001 — degrade, never crash the run
        log.error("adapter %s failed: %s\n%s", adapter.name, e, traceback.format_exc(limit=3))
        return FetchResult(adapter.name, "failed", error=f"{type(e).__name__}: {e}")


def update_breaker(results: list[FetchResult]) -> dict:
    breaker = _breaker_state()
    for r in results:
        if r.status == "failed":
            breaker[r.source] = breaker.get(r.source, 0) + 1
        elif r.status in ("ok", "stale"):
            breaker[r.source] = 0
    return breaker
