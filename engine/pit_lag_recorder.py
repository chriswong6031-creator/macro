"""Learned release-lag recorder — masterplan W1a ("learned lags going forward").

The static release-lag priors in engine.pit are defensible but coarse. This module
accrues a FIRST-PARTY release calendar for free: every collect run, for each stored
series, it appends one row `{series, fetch_ts, last_obs_date}` to an append-only jsonl.
The gap `fetch_ts − last_obs_date` at the moment the collector first SEES a new period is
that period's realised publication lag — so after a few months the log yields empirical,
per-series release lags that refine (and eventually replace) the static priors.

HARD CONSTRAINT: this can NEVER break the collect pipeline. Every public entry point is
wrapped so it swallows all exceptions and returns quietly. It writes to a data file the
live engine does not read.

Log: data/pit_release_log/observations.jsonl  (append-only; one row per series per run)
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from lib import config

log = logging.getLogger(__name__)

_LOG_DIR = "pit_release_log"
_LOG_FILE = "observations.jsonl"


def _path():
    p = config.data_dir() / _LOG_DIR
    p.mkdir(parents=True, exist_ok=True)
    return p / _LOG_FILE


def record(series: str, last_obs_date, group: str | None = None,
           fetch_ts: datetime | None = None) -> None:
    """Append one observation row. Never raises."""
    try:
        ts = (fetch_ts or datetime.now(timezone.utc)).isoformat()
        lod = str(last_obs_date) if last_obs_date is not None else None
        row = {"series": str(series), "group": group,
               "fetch_ts": ts, "last_obs_date": lod}
        with open(_path(), "a") as fh:
            fh.write(json.dumps(row) + "\n")
    except Exception as e:  # noqa: BLE001 — recorder must never break collection
        log.debug("pit_lag_recorder.record failed (ignored): %s", e)


def record_fetch_result(result, group: str | None = None) -> None:
    """Hook for the collector runner: record from a FetchResult (has .source and
    .last_date). Only records reachable outcomes with a real last_date. Never raises."""
    try:
        status = getattr(result, "status", None)
        if status not in ("ok", "stale"):
            return
        last = getattr(result, "last_date", None)
        if not last:
            return
        record(getattr(result, "source", "unknown"), last,
               group=group or getattr(result, "source", None))
    except Exception as e:  # noqa: BLE001
        log.debug("pit_lag_recorder.record_fetch_result failed (ignored): %s", e)


def record_fred_series(frames: dict, group: str = "fred") -> None:
    """Record per-SERIES last-obs dates for a multi-series adapter (FRED), where the
    per-series granularity is what a release calendar actually needs. `frames` maps
    series-id -> DataFrame. Never raises."""
    try:
        for sid, df in (frames or {}).items():
            try:
                if df is None or getattr(df, "empty", True):
                    continue
                last = df.index.max()
                record(sid, getattr(last, "date", lambda: last)(), group=group)
            except Exception:  # noqa: BLE001 — skip one bad series, keep going
                continue
    except Exception as e:  # noqa: BLE001
        log.debug("pit_lag_recorder.record_fred_series failed (ignored): %s", e)


def learned_lags(min_obs: int = 3) -> dict:
    """Reduce the accrued log to per-series empirical release lags. For each series,
    the lag of a period = the earliest fetch_ts at which that last_obs_date appeared,
    minus the last_obs_date. Returns {series: {median_lag_days, n_periods, ...}}.

    Returns {} if the log is missing/empty. Never raises."""
    try:
        import pandas as pd
        p = _path()
        if not p.exists():
            return {}
        rows = []
        with open(p) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:  # noqa: BLE001
                    continue
        if not rows:
            return {}
        df = pd.DataFrame(rows).dropna(subset=["last_obs_date", "fetch_ts"])
        df["fetch_ts"] = pd.to_datetime(df["fetch_ts"], utc=True, errors="coerce")
        df["last_obs_date"] = pd.to_datetime(df["last_obs_date"], errors="coerce")
        df = df.dropna(subset=["fetch_ts", "last_obs_date"])
        out = {}
        for series, g in df.groupby("series"):
            # first time each distinct last_obs_date was seen = its discovery moment
            first_seen = g.groupby("last_obs_date")["fetch_ts"].min()
            lags = (first_seen.index.tz_localize("UTC") if first_seen.index.tz is None
                    else first_seen.index)
            lag_days = (first_seen.values - first_seen.index.tz_localize(None).values)
            lag_days = pd.Series(lag_days).dt.days.dropna()
            lag_days = lag_days[lag_days >= 0]
            if len(lag_days) < min_obs:
                continue
            out[str(series)] = {
                "median_lag_days": round(float(lag_days.median()), 1),
                "p90_lag_days": round(float(lag_days.quantile(0.9)), 1),
                "n_periods": int(len(lag_days)),
            }
        return out
    except Exception as e:  # noqa: BLE001
        log.debug("pit_lag_recorder.learned_lags failed (ignored): %s", e)
        return {}
