"""Persist the per-basket EW level SERIES + 20d rel returns (HK / Canada).

Masterplan §5.2 / §5.0 precise gap: the HK/CA thematic-basket LEVEL SERIES are recomputed
and DISCARDED on every render. engine.basket_freeze already persists a PIT last-value tape
(one float/basket/day). This module persists the *full computed level series* the render
throws away, plus each basket's 20d relative-vs-benchmark return, so downstream ignition
grading / structure math can read a level series without re-deriving it.

  data/basket_levels/<market>_levels.parquet   (market ∈ {hk, ca})
    index   : date (datetime64[ns])          — one row per session in the payload's chart
    columns : <bid>__level     float64        — EW level (chart.baskets[bid], TR basis)
              __bench           float64        — benchmark level (chart.bench)
              <bid>__rel20      float64        — this basket's 20d rel-vs-bench return (as-of row only)

IDEMPOTENT / APPEND-MERGE (small, git-tracked):
  We overwrite level cells with the freshly computed series (levels are recomputed
  deterministically each render from the same closes; there is no PIT-immutability claim here —
  that is basket_freeze's job). The store simply carries the latest full series so a reader
  never has to recompute it. Dates are unioned; new baskets add columns. Never raises.
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from lib import config

log = logging.getLogger(__name__)

DOMAIN_DIR = "basket_levels"


def _path(market: str) -> Path:
    p = config.data_dir() / DOMAIN_DIR / f"{market}_levels.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _frame_from_payload(data: dict) -> pd.DataFrame | None:
    """Build the wide [date × (<bid>__level, __bench, <bid>__rel20)] frame from a baskets payload.

    `data` must still carry `chart` (call BEFORE the builder pops it) and `baskets`.
    """
    chart = (data or {}).get("chart") or {}
    dates = chart.get("dates")
    if not dates:
        return None
    idx = pd.DatetimeIndex(pd.to_datetime(dates))
    cols: dict[str, list] = {"__bench": chart.get("bench") or [None] * len(idx)}
    for bid, lv in (chart.get("baskets") or {}).items():
        if len(lv) == len(idx):
            cols[f"{bid}__level"] = lv
    if len(cols) <= 1:                      # only bench, no basket levels
        return None
    df = pd.DataFrame(cols, index=idx)
    # attach each basket's 20d rel (as-of row only; NaN elsewhere) from the payload perf block
    rel20 = {b["id"]: ((b.get("perf") or {}).get("20d") or {}).get("rel") for b in (data.get("baskets") or [])}
    for bid, rel in rel20.items():
        s = pd.Series(np.nan, index=idx, dtype="float64")
        if rel is not None and len(idx):
            s.iloc[-1] = float(rel)
        df[f"{bid}__rel20"] = s
    return df


def persist(data: dict, market: str) -> dict:
    """Persist the level series for one market's baskets payload. Idempotent. Never raises.

    Returns {market, path, n_baskets, n_dates, wrote} (wrote False on skip/failure)."""
    result = {"market": market, "path": None, "n_baskets": 0, "n_dates": 0, "wrote": False}
    try:
        new_df = _frame_from_payload(data)
        if new_df is None or new_df.empty:
            log.warning("basket_levels_persist[%s]: no chart level series in payload — skipping", market)
            return result
        p = _path(market)
        if p.exists():
            try:
                old = pd.read_parquet(p)
                old.index = pd.DatetimeIndex(old.index)
                # union dates, prefer the freshly computed series where they overlap
                combined = new_df.combine_first(old)
                # ensure freshly computed cells win over stale ones on shared (date,col)
                combined.loc[new_df.index, new_df.columns] = new_df
                combined = combined.sort_index()
            except Exception as e:  # noqa: BLE001
                log.warning("basket_levels_persist[%s]: prior store unreadable (%s) — overwriting", market, e)
                combined = new_df.sort_index()
        else:
            combined = new_df.sort_index()
        combined.to_parquet(p)
        result.update({
            "path": str(p),
            "n_baskets": len([c for c in new_df.columns if c.endswith("__level")]),
            "n_dates": int(len(combined)),
            "wrote": True,
        })
        log.info("basket_levels_persist[%s]: wrote %d baskets × %d dates -> %s",
                 market, result["n_baskets"], result["n_dates"], p.name)
        return result
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("basket_levels_persist[%s]: failed: %s", market, e)
        return result


def read_levels(market: str) -> pd.DataFrame | None:
    p = _path(market)
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
        df.index = pd.DatetimeIndex(df.index)
        return df.sort_index()
    except Exception as e:  # noqa: BLE001
        log.warning("basket_levels_persist[%s]: read failed: %s", market, e)
        return None


def level_series(market: str, bid: str) -> pd.Series | None:
    """The persisted EW level Series for one basket (for ignition grading / structure reads)."""
    df = read_levels(market)
    if df is None:
        return None
    col = f"{bid}__level"
    if col not in df.columns:
        return None
    return df[col].dropna()


def bench_series(market: str) -> pd.Series | None:
    df = read_levels(market)
    if df is None or "__bench" not in df.columns:
        return None
    return df["__bench"].dropna()
