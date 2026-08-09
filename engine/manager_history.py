"""Append-only manager grade/excess history for the Smart Money desk.

The four-quarter memory board is a convenient rolling view, but a rolling JSON
is not a historical ledger.  This module freezes each settled manager-quarter
result into a durable parquet on the nightly lane.  The natural key includes the
method version so a future methodology can coexist with, rather than rewrite,
the record produced by today's public-availability model.

These grades are descriptive cohort ranks.  They never feed Neural Web,
Prophet, allocation, or a trading signal.
"""
from __future__ import annotations

import logging
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from engine.ledger_lane import nightly_advance_enabled
from lib import config

log = logging.getLogger(__name__)

METHOD_VERSION = "fund-memory-public-availability-v2"
_REL_PATH = Path("smart_money") / "manager_history.parquet"
_KEY = ["slug", "period_end", "method_version"]


def _path(root: Path | None = None) -> Path:
    base = Path(root) if root else config.ROOT
    return base / "data" / _REL_PATH


def _load(root: Path | None = None) -> pd.DataFrame:
    path = _path(root)
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_parquet(path)
    except Exception:  # noqa: BLE001 - summary/build must degrade, never break the desk
        log.warning("manager_history: failed to read %s", path, exc_info=True)
        return pd.DataFrame()


def _outcome_grade(rank: Any, n_cohort: Any) -> str | None:
    """Translate an intra-quarter rank into a descriptive cohort band."""
    try:
        r = int(rank)
        n = int(n_cohort)
    except (TypeError, ValueError):
        return None
    if r < 1 or n < 1:
        return None
    percentile = r / n
    if percentile <= 0.15:
        return "A"
    if percentile <= 0.40:
        return "B"
    if percentile <= 0.75:
        return "C"
    return "D"


def _rows_from_memory(memory: dict, recorded_at: str | None = None) -> list[dict]:
    stamp = recorded_at or datetime.now(timezone.utc).isoformat()
    roster_slugs = sorted(str(slug) for slug in (memory.get("funds") or {}))
    roster_hash = hashlib.sha256("\n".join(roster_slugs).encode("utf-8")).hexdigest()
    rows: list[dict] = []
    for slug, fund in (memory.get("funds") or {}).items():
        for quarter in (fund.get("by_quarter") or []):
            if not quarter or quarter.get("dw_excess_60d") is None:
                continue
            rows.append({
                "slug": str(slug),
                "fund_name": fund.get("name") or slug,
                "period_end": str(quarter.get("period_end") or ""),
                "anchor": quarter.get("anchor"),
                "n_priced": int(quarter.get("n_priced") or 0),
                "dw_excess_60d": quarter.get("dw_excess_60d"),
                "new_dw_excess_60d": quarter.get("new_dw_excess_60d"),
                "add_dw_excess_60d": quarter.get("add_dw_excess_60d"),
                "hit_60d": quarter.get("hit_60d"),
                "rank": quarter.get("rank"),
                "n_cohort": int(quarter.get("n_cohort") or 0),
                "beat": quarter.get("beat"),
                "outcome_grade": _outcome_grade(
                    quarter.get("rank"), quarter.get("n_cohort")),
                "tracker_grade_at_record": fund.get("grade"),
                "benchmark": memory.get("benchmark") or "SPY",
                "horizon_days": int(memory.get("horizon_days") or 60),
                "price_as_of": memory.get("as_of"),
                "roster_n": len(roster_slugs),
                "roster_hash": roster_hash,
                "method_version": METHOD_VERSION,
                "recorded_at": stamp,
            })
    return rows


def advance_manager_history(memory: dict, root: Path | None = None) -> int:
    """Freeze newly settled manager-quarter rows on the nightly lane only."""
    if not nightly_advance_enabled():
        log.debug("manager_history: skipped (COLLECT_LANE != nightly)")
        return 0
    rows = _rows_from_memory(memory or {})
    if not rows:
        return 0

    incoming = pd.DataFrame.from_records(rows).drop_duplicates(subset=_KEY, keep="first")
    existing = _load(root)
    if existing.empty:
        combined = incoming
        n_added = len(incoming)
    else:
        key_to_index = {
            key: idx for idx, key in zip(
                existing.index,
                existing[_KEY].itertuples(index=False, name=None),
            )
        }
        metadata_changed = False
        for column in ("roster_n", "roster_hash"):
            if column not in existing.columns:
                existing[column] = pd.NA
        for record in incoming.to_dict(orient="records"):
            idx = key_to_index.get(tuple(record.get(col) for col in _KEY))
            if idx is None:
                continue
            for column in ("roster_n", "roster_hash"):
                if pd.isna(existing.at[idx, column]):
                    existing.at[idx, column] = record[column]
                    metadata_changed = True
        keep = [key not in key_to_index
                for key in incoming[_KEY].itertuples(index=False, name=None)]
        new_rows = incoming[keep]
        if new_rows.empty:
            if metadata_changed:
                path = _path(root)
                path.parent.mkdir(parents=True, exist_ok=True)
                existing.to_parquet(path, index=False)
            return 0
        combined = pd.concat([existing, new_rows], ignore_index=True)
        n_added = len(new_rows)

    path = _path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    combined.to_parquet(path, index=False)
    log.info("manager_history: froze %d settled manager-quarter rows", n_added)
    return int(n_added)


def manager_history_summary(root: Path | None = None) -> dict:
    """Compact audit metadata for the desk payload and operational checks."""
    frame = _load(root)
    if frame.empty:
        return {
            "n_entries": 0, "n_funds": 0, "n_quarters": 0,
            "latest_period": None, "method_version": METHOD_VERSION,
            "latest_grade_counts": {},
        }
    latest = str(frame["period_end"].max())
    latest_rows = frame[frame["period_end"].astype(str) == latest]
    grade_counts = (
        latest_rows["outcome_grade"].dropna().astype(str).value_counts().to_dict()
        if "outcome_grade" in latest_rows.columns else {}
    )
    return {
        "n_entries": int(len(frame)),
        "n_funds": int(frame["slug"].nunique()),
        "n_quarters": int(frame["period_end"].nunique()),
        "latest_period": latest,
        "method_version": METHOD_VERSION,
        "latest_grade_counts": {str(k): int(v) for k, v in grade_counts.items()},
    }
