"""Parquet time-series store. The repo is the database.

Rules:
- One parquet per logical series/table: data/<group>/<name>.parquet
- upsert() merges on the index and NEVER drops rows that exist only on disk.
  This is what makes the FRED OAS cache permanent: once an observation is
  stored it survives every later fetch, even though FRED itself now serves
  only a rolling 3-year window.
- Outlier guard (Phase 4): |daily change| > N sigma is quarantined to
  data/quarantine/, not silently ingested.
"""
from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

import pandas as pd

from lib import config

log = logging.getLogger(__name__)

OUTLIER_SIGMA = 8
OUTLIER_MIN_OBS = 60


def _path(group: str, name: str) -> Path:
    safe = name.replace("^", "_").replace("=", "_").replace("/", "_").replace(" ", "_")
    p = config.data_dir() / group / f"{safe}.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def read(group: str, name: str) -> pd.DataFrame | None:
    p = _path(group, name)
    if not p.exists():
        return None
    df = pd.read_parquet(p)
    df.index = pd.to_datetime(df.index)
    return df.sort_index()


def last_date(group: str, name: str) -> date | None:
    df = read(group, name)
    if df is None or df.empty:
        return None
    return df.index.max().date()


def _quarantine(group: str, name: str, rows: pd.DataFrame, reason: str) -> None:
    qdir = config.data_dir() / "quarantine"
    qdir.mkdir(parents=True, exist_ok=True)
    qp = qdir / f"{group}_{name}.csv".replace("^", "_").replace("=", "_")
    rows.assign(reason=reason).to_csv(qp, mode="a", header=not qp.exists())
    log.warning("quarantined %d rows of %s/%s: %s", len(rows), group, name, reason)


def upsert(group: str, name: str, new: pd.DataFrame, outlier_col: str | None = None) -> pd.DataFrame:
    """Merge new rows into the stored series. New values win on date collision;
    rows present only on disk are always kept (append-only history guarantee)."""
    if new is None or new.empty:
        raise ValueError(f"upsert called with empty frame for {group}/{name}")
    new = new.copy()
    new.index = pd.to_datetime(new.index).normalize()
    new = new[~new.index.duplicated(keep="last")].sort_index()

    old = read(group, name)
    if old is not None and not old.empty and outlier_col and outlier_col in new.columns:
        new = _guard_outliers(group, name, old, new, outlier_col)

    if old is None or old.empty:
        merged = new
    else:
        merged = new.combine_first(old)  # new wins where both exist; old-only rows kept
        merged = merged.sort_index()

    merged.to_parquet(_path(group, name))
    return merged


def _guard_outliers(group: str, name: str, old: pd.DataFrame, new: pd.DataFrame, col: str) -> pd.DataFrame:
    hist = old[col].dropna()
    if len(hist) < OUTLIER_MIN_OBS:
        return new
    diffs = hist.diff().dropna()
    sigma = diffs.std()
    if not sigma or pd.isna(sigma) or sigma == 0:
        return new
    incoming = new[new.index > hist.index.max()]
    if incoming.empty:
        return new
    last_val = hist.iloc[-1]
    jump = (incoming[col] - last_val).abs()
    bad = incoming[jump > OUTLIER_SIGMA * sigma * max(1, len(incoming)) ** 0.5]
    if not bad.empty:
        _quarantine(group, name, bad, f"|change from {last_val:.4g}| > {OUTLIER_SIGMA} sigma ({sigma:.4g})")
        new = new.drop(index=bad.index)
    return new


def write_status(status: dict) -> None:
    p = Path(config.ROOT) / config.load()["storage"]["run_status_file"]
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w") as f:
        json.dump(status, f, indent=2, default=str)


def read_status() -> dict:
    p = Path(config.ROOT) / config.load()["storage"]["run_status_file"]
    if not p.exists():
        return {}
    with open(p) as f:
        return json.load(f)
