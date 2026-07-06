"""Nightly grader for the breadth-divergence forward log.

End-of-collect step (PR-A2).  For every row in
data/breadth_divergence/forward_log.parquet whose h21 outcome window has
MATURED (stamp_date + 21 business days <= today), computes the realized
forward 21-day max-drawdown using basket EW-level histories built from
data/baskets/ohlcv/ + data/baskets/membership.json.

Design contracts:
- MATURITY GATE   : only grades rows where np.busday_count(stamp_date,
                    today) >= 21.  Unmatured rows are untouched.
- IDEMPOTENT      : skips rows that already have a non-null fwd_dd value.
- SINGLE-WRITER   : called only from scripts/collect.py end-of-collect
                    block; never raises into the caller.
- NEVER RAISES    : entire body wrapped; non-fatal on any error.

Levels are built from the deep OHLCV store (data/baskets/ohlcv/<ticker>.parquet)
and the PIT membership.json (respects added/removed dates), matching the
engine.baskets._ew_level convention.  Labels history is not available here —
grade_forward_log() is called without labels (lead_vs_guard_days will be None
for all graded rows; that is honest: labels are a display-time enrichment).

Writes back the parquet in-place only when at least one new grade was added.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# h21 = 21-business-day forward window (matching engine/basket_breadth_divergence.py)
H = 21


# ---------------------------------------------------------------------------
# Level builder (mirrors engine.baskets._ew_level from the OHLCV store)
# ---------------------------------------------------------------------------

def _build_level(basket_id: str, members: list[dict], ohlcv_dir: Path) -> pd.Series | None:
    """Build EW-level Series for basket_id from data/baskets/ohlcv/.

    Returns None if fewer than 3 members have price data.
    Mirrors engine.baskets._ew_level: PIT membership dates respected.
    """
    closes: dict[str, pd.Series] = {}
    for m in members:
        t = m["ticker"]
        p = ohlcv_dir / f"{t}.parquet"
        if not p.exists():
            continue
        try:
            df = pd.read_parquet(p, columns=["close"])
            s = df["close"].dropna()
            if len(s) < H + 2:
                continue
            s.index = pd.DatetimeIndex(s.index)
            closes[t] = s
        except Exception:  # noqa: BLE001
            continue

    if len(closes) < 3:
        return None

    all_idx = pd.DatetimeIndex(sorted(set().union(*[s.index for s in closes.values()]))).sort_values()
    rets = pd.DataFrame({t: closes[t].reindex(all_idx) for t in closes}).pct_change(fill_method=None)

    # PIT membership mask
    mask = pd.DataFrame(False, index=all_idx, columns=list(closes.keys()))
    for m in members:
        t = m["ticker"]
        if t not in closes:
            continue
        a = all_idx >= pd.Timestamp(m["added"])
        if m.get("removed"):
            a = a & (all_idx < pd.Timestamp(m["removed"]))
        mask[t] = a

    ew = rets.where(mask).mean(axis=1)
    first = ew.first_valid_index()
    if first is None:
        return None
    lvl = pd.Series(np.nan, index=all_idx, name=basket_id)
    lvl.loc[first:] = (1.0 + ew.loc[first:].fillna(0.0)).cumprod()
    return lvl


def _load_levels(basket_ids: list[str], root: Path) -> dict[str, pd.Series]:
    """Load EW-level histories for the requested basket_ids."""
    try:
        import json
        mem_path = root / "data" / "baskets" / "membership.json"
        if not mem_path.exists():
            return {}
        mem = json.loads(mem_path.read_text())
        bdict = mem.get("baskets", {})
    except Exception:  # noqa: BLE001
        return {}

    ohlcv_dir = root / "data" / "baskets" / "ohlcv"
    levels: dict[str, pd.Series] = {}
    for bid in basket_ids:
        b = bdict.get(bid)
        if b is None:
            continue
        lvl = _build_level(bid, b.get("members", []), ohlcv_dir)
        if lvl is not None and lvl.dropna().shape[0] >= H + 2:
            levels[bid] = lvl
    return levels


# ---------------------------------------------------------------------------
# Core grading pass
# ---------------------------------------------------------------------------

def _log_path(root: Path) -> Path:
    return root / "data" / "breadth_divergence" / "forward_log.parquet"


def grade_matured_rows(root: Path | None = None) -> int:
    """Grade matured, ungraded rows.  Returns count of newly graded rows."""
    if root is None:
        root = Path(__file__).resolve().parent.parent

    p = _log_path(root)
    if not p.exists():
        return 0

    try:
        df = pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        log.warning("grade_breadth_divergence: parquet read failed: %s", e)
        return 0

    if df.empty:
        return 0

    today = date.today()

    # Identify rows eligible for grading:
    # - h21 outcome window matured: busday_count(stamp_date, today) >= H
    # - fwd_dd not yet populated (column may not exist yet)
    if "fwd_dd" not in df.columns:
        df["fwd_dd"] = None

    df["date"] = df["date"].astype(str)
    matured_mask = df["date"].apply(
        lambda d: np.busday_count(d, today.isoformat()) >= H
    )
    ungraded_mask = df["fwd_dd"].isna()
    to_grade = df[matured_mask & ungraded_mask]

    if to_grade.empty:
        log.debug("grade_breadth_divergence: no matured ungraded rows (total=%d)", len(df))
        return 0

    # Load level histories only for the basket_ids we need
    needed_ids = to_grade["basket_id"].unique().tolist()
    levels = _load_levels(needed_ids, root)

    if not levels:
        log.warning(
            "grade_breadth_divergence: no level histories available for %s; "
            "skipping grade pass",
            needed_ids,
        )
        return 0

    from engine.basket_breadth_divergence import grade_forward_log  # noqa: PLC0415

    result = grade_forward_log(to_grade, levels, labels=None, h=H)
    graded_rows: list[dict[str, Any]] = [r for r in result.get("rows", []) if r.get("fwd_dd") is not None]

    if not graded_rows:
        return 0

    # Merge fwd_dd back into df by (date, basket_id, region)
    graded_map = {
        (r["date"], r["basket_id"]): r["fwd_dd"]
        for r in graded_rows
    }

    n_new = 0
    for idx in df.index:
        key = (str(df.at[idx, "date"]), str(df.at[idx, "basket_id"]))
        if key in graded_map and pd.isna(df.at[idx, "fwd_dd"]):
            df.at[idx, "fwd_dd"] = graded_map[key]
            n_new += 1

    if n_new:
        df.to_parquet(p, index=False)
        log.info("grade_breadth_divergence: graded %d rows (total=%d)", n_new, len(df))

    return n_new


# ---------------------------------------------------------------------------
# Collect-step hook
# ---------------------------------------------------------------------------

def run_as_collect_step() -> None:
    """End-of-collect hook — must never raise."""
    try:
        n = grade_matured_rows()
        log.debug("grade_breadth_divergence collect step: %d newly graded", n)
    except Exception as exc:  # noqa: BLE001
        log.error("[grade_breadth_divergence] step crashed (non-fatal): %s", exc)
