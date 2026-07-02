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

# An open breaker is HALF-OPEN, not permanently dead: after this long it lets ONE
# probe through. A success closes it; a failure re-opens it for another window.
# Without this an open breaker NEVER retries — the daily/weekly collect never pass
# --full-history (the only flag that bypassed it), so a single transient trip
# became a permanent SILENT death (a healthy source stuck "dead" for weeks).
CIRCUIT_HALF_OPEN_AFTER_H = 20.0   # ~one probe per daily run


@dataclass
class FetchResult:
    source: str
    status: str            # ok | stale | failed | dead | skipped | blocked
    rows: int = 0
    last_date: str | None = None
    error: str | None = None
    notes: list[str] = field(default_factory=list)
    probed_at: str | None = None   # set when this run was a half-open breaker probe


class Adapter:
    """Subclass per source. fetch() returns the canonical DataFrame(s) and is
    allowed to raise — the runner handles failure."""

    name: str = "base"
    group: str = "misc"
    stale_after_days: int = 5   # weekly/lagged sources override (COT: 12, H4.1: 10)
    expected_failure: str | None = None  # set to a reason string when a source is
    # known-broken (e.g. bot-blocked); failures then report status 'blocked'
    overwrite_overlap: bool = False  # True for dividend/split-ADJUSTED series (yfinance
    # auto_adjust=True): the fresh pull fully overwrites its own date span so a re-adjusted
    # history leaves no combine_first basis seam. See lib.store.upsert / masterplan §W6-CN.

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


def is_connection_error(exc: Exception) -> bool:
    """True when *exc* means the HOST is unreachable (timeout / refused / DNS), as
    opposed to a data-level problem (404, empty series). Lets a multi-series
    collector fail fast on a dead endpoint instead of retrying EVERY series through
    its full timeout+backoff — a single FRED-frontend outage once turned the
    intl_macro plane into a ~56-minute no-op (34 series x 3 retries x 30s)."""
    if isinstance(exc, (requests.exceptions.ConnectionError,
                        requests.exceptions.Timeout)):   # covers Connect/ReadTimeout
        return True
    s = str(exc).lower()
    return ("timed out" in s or "max retries" in s
            or "failed to establish a new connection" in s
            or "connection aborted" in s or "connection refused" in s)


def _breaker_state() -> dict:
    return store.read_status().get("circuit_breaker", {})


def _probe_state() -> dict:
    return store.read_status().get("circuit_breaker_probe", {})


def _probe_due(last_probe: str | None,
               cooldown_h: float = CIRCUIT_HALF_OPEN_AFTER_H) -> bool:
    """True when an open breaker has waited long enough for its next half-open probe."""
    if not last_probe:
        return True
    try:
        age_h = (datetime.now(timezone.utc)
                 - datetime.fromisoformat(last_probe)).total_seconds() / 3600.0
    except (ValueError, TypeError):
        return True
    return age_h >= cooldown_h


def run_adapter(adapter: Adapter, full_history: bool = False,
                stale_after_days: int | None = None) -> FetchResult:
    """Execute one adapter with circuit breaker + graceful degradation."""
    if stale_after_days is None:
        stale_after_days = adapter.stale_after_days
    breaker = _breaker_state()
    fails = breaker.get(adapter.name, 0)
    half_open = False
    if fails >= CIRCUIT_BREAKER_FAILS and not full_history:
        if not _probe_due(_probe_state().get(adapter.name)):
            return FetchResult(adapter.name, "dead",
                               error=f"circuit open ({fails} consecutive failures)")
        half_open = True   # cooldown elapsed -> let ONE probe through to test recovery
        log.info("adapter %s breaker half-open: probing after %d fails", adapter.name, fails)

    try:
        frames = adapter.fetch(full_history=full_history)
        rows, last = 0, None
        for series_name, df in frames.items():
            df = adapter.validate(series_name, df)
            merged = store.upsert(adapter.group, series_name, df,
                                  outlier_col=df.columns[0] if len(df.columns) == 1 else None,
                                  normalize_index=getattr(adapter, "normalize_index", True),
                                  overwrite_overlap=getattr(adapter, "overwrite_overlap", False))
            rows += len(df)
            last = max(filter(None, [last, merged.index.max()]))
        status = "ok"
        if last is not None:
            age = (datetime.now(timezone.utc).date() - last.date()).days
            if age > stale_after_days:
                status = "stale"
        res = FetchResult(adapter.name, status, rows=rows,
                          last_date=str(last.date()) if last is not None else None)
    except Exception as e:  # noqa: BLE001 — degrade, never crash the run
        if adapter.expected_failure:
            log.info("adapter %s blocked (known): %s", adapter.name, e)
            res = FetchResult(adapter.name, "blocked", error=adapter.expected_failure)
        else:
            log.error("adapter %s failed: %s\n%s", adapter.name, e, traceback.format_exc(limit=3))
            res = FetchResult(adapter.name, "failed", error=f"{type(e).__name__}: {e}")
    if half_open:
        res.probed_at = datetime.now(timezone.utc).isoformat()
    return res


def update_breaker(results: list[FetchResult],
                   probe_state: dict | None = None) -> tuple[dict, dict]:
    """Recompute (circuit_breaker, circuit_breaker_probe) after a collect pass.

    A 'failed' increments the breaker; a reachable, definitive outcome
    ('ok'/'stale'/'blocked') closes it. 'blocked' clears too — it is an
    expected_failure (a known limitation, not a transient outage), so it must not
    leave the source wedged 'dead'. The probe map records when a half-open probe was
    last attempted so an open breaker re-probes at most once per cooldown.
    """
    breaker = _breaker_state()
    probe = dict(_probe_state() if probe_state is None else probe_state)
    for r in results:
        if r.status == "failed":
            breaker[r.source] = breaker.get(r.source, 0) + 1
        elif r.status in ("ok", "stale", "blocked"):
            breaker[r.source] = 0
        # half-open bookkeeping: a recovered/blocked source forgets its probe clock;
        # a still-failing probe stamps the time so it waits a full cooldown again.
        if r.status in ("ok", "stale", "blocked"):
            probe.pop(r.source, None)
        elif r.probed_at:
            probe[r.source] = r.probed_at
    return breaker, probe
