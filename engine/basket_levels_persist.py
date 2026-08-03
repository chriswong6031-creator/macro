"""Persist the per-basket EW level SERIES (HK / Canada).

Masterplan §5.2 / §5.0 precise gap: the HK/CA thematic-basket LEVEL SERIES are recomputed
and DISCARDED on every render. engine.basket_freeze already persists a PIT last-value tape
(one float/basket/day). This module persists the *full computed level series* the render
throws away, so downstream ignition grading / structure math can read a level series
without re-deriving it.

  data/basket_levels/<market>_levels.parquet   (market ∈ {hk, ca})
    index   : date (datetime64[ns])          — one row per session in the payload's chart
    columns : <bid>__level     float64        — EW level (chart.baskets[bid], TR basis)
              __bench           float64        — benchmark level (chart.bench)

  (A `<bid>__rel20` as-of-stamp column shipped with the module was retired 2026-08:
  no reader ever existed, the last-row-only stamp could never accrue history — prior
  stamps were overwritten under the old fresh-wins merge and fall behind the front
  under the window trim — and within the surviving window rel20 is derivable from
  `<bid>__level` / `__bench`. persist() drops the legacy columns from a prior store
  so they cannot ride the carried-columns path.)

VALIDITY CONTRACT (window-trimmed; small, git-tracked):
  The EW levels are recomputed each render over a rolling price window and rebased at the
  window's own start (engine.baskets._ew_level), so two renders' series sit on DIFFERENT
  bases wherever the window front has advanced. A store that kept rows after they fell out
  of the window (the pre-fix append-merge) would accrete a continuum of vintages, and any
  cross-date ratio straddling a vintage boundary would embed the returns of the days dropped
  from the window front — not a return (the moving-base defect measured on the frozen-store
  sibling and chain-linked out of engine.basket_freeze in PR #4373).

  Each write therefore keeps ONLY the freshly recomputed window: every surviving row shares
  tonight's single base, so any cross-date ratio obtainable from this store is a true return
  by construction. Rows behind the advancing front are dropped (logged) — deep history is
  discarded deliberately rather than kept behind a validity marker every future reader would
  have to know to honor; nothing can validly ratio those rows anyway. Columns for baskets
  absent from tonight's payload are carried at tonight's dates only: they were last written
  whole by a single render, so they stay single-vintage and ratio-valid within their
  surviving span, and age out as the window advances past it.

  Idempotent; levels are recomputed deterministically each render from the same closes;
  there is no PIT-immutability claim here — that is basket_freeze's job. Never raises.
"""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from lib import config

log = logging.getLogger(__name__)

DOMAIN_DIR = "basket_levels"


def _path(market: str) -> Path:
    p = config.data_dir() / DOMAIN_DIR / f"{market}_levels.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _frame_from_payload(data: dict) -> pd.DataFrame | None:
    """Build the wide [date × (<bid>__level, __bench)] frame from a baskets payload.

    `data` must still carry `chart` (call BEFORE the builder pops it).
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
    return pd.DataFrame(cols, index=idx)


def persist(data: dict, market: str) -> dict:
    """Persist the level series for one market's baskets payload. Idempotent. Never raises.

    Returns {market, path, n_baskets, n_dates, n_trimmed, wrote} (wrote False on skip/failure)."""
    result = {"market": market, "path": None, "n_baskets": 0, "n_dates": 0, "wrote": False}
    try:
        new_df = _frame_from_payload(data)
        if new_df is None or new_df.empty:
            log.warning("basket_levels_persist[%s]: no chart level series in payload — skipping", market)
            return result
        p = _path(market)
        combined = new_df.sort_index()
        n_trimmed = 0
        if p.exists():
            try:
                old = pd.read_parquet(p)
                old.index = pd.DatetimeIndex(old.index)
                # schema-retired (module docstring): legacy __rel20 columns must not ride
                # the carried-columns path below
                legacy = [c for c in old.columns if c.endswith("__rel20")]
                if legacy:
                    old = old.drop(columns=legacy)
                    log.info("basket_levels_persist[%s]: dropped %d retired __rel20 column(s)",
                             market, len(legacy))
                # VALIDITY (module docstring): only tonight's window survives — fresh cells
                # replace everything on shared dates, and old rows outside tonight's window
                # are trimmed, never merged. Columns for baskets absent tonight are carried
                # at tonight's dates only (single-vintage: last written whole by one render).
                carried_cols = [c for c in old.columns if c not in combined.columns]
                if carried_cols:
                    carried = old.loc[old.index.isin(combined.index), carried_cols]
                    carried = carried[~carried.index.duplicated(keep="last")]
                    combined = combined.join(carried)
                n_trimmed = int(len(old.index.difference(combined.index)))
                if n_trimmed:
                    log.warning("basket_levels_persist[%s]: trimmed %d stale-base row(s) behind "
                                "the advancing chart window — cross-vintage ratios are not "
                                "returns, so they must not survive in the store", market, n_trimmed)
            except Exception as e:  # noqa: BLE001
                log.warning("basket_levels_persist[%s]: prior store unreadable (%s) — overwriting", market, e)
                combined = new_df.sort_index()
        combined.to_parquet(p)
        result.update({
            "path": str(p),
            "n_baskets": len([c for c in new_df.columns if c.endswith("__level")]),
            "n_dates": int(len(combined)),
            "n_trimmed": n_trimmed,
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
    """The persisted EW level Series for one basket (for ignition grading / structure reads).

    Single-vintage by the module's validity contract: any cross-date ratio within the
    returned series is a true consistent-base return."""
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
