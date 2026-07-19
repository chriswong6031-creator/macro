"""engine.marketing.receipt_source — REAL receipts from graded Prophet plan outcomes.

Produces concrete receipt dicts from Prophet plans that have graded outcomes
(T1/T2 DONE hits, invalidations, or both on the same plan = "mixed").

Public API:
    graded_receipts(plans, *, closes_loader=None, today=None) -> list[dict]

Each returned dict:
    {
        "ticker": str,
        "kind": "win" | "loss" | "mixed",
        "signal_date": str,          # YYYY-MM-DD
        # win fields (present on "win" and "mixed"):
        "entry": float,
        "target": float,
        "gain_pct": float,           # e.g. 9.6 for +9.6%
        "gain_pct_str": str,         # e.g. "+9.6%"
        "target_label": str,         # e.g. "T1"
        # loss fields (present on "loss" and "mixed"):
        "entry": float,
        "stop": float,               # the invalidation level
        "loss_pct": float,           # e.g. -6.4 (negative)
        "loss_pct_str": str,         # e.g. "-6.4%"
    }

Freshness: signal_date must be within *max_age_days* of today (default 14).
Priority: mixed > win > loss when deduplicating per ticker.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Callable


_MAX_AGE_DAYS = 14
_KIND_PRIORITY = {"mixed": 3, "win": 2, "loss": 1}


def _parse_date(s: object) -> date | None:
    try:
        parts = str(s)[:10].split("-")
        return date(int(parts[0]), int(parts[1]), int(parts[2]))
    except Exception:
        return None


def _age_days(signal_date: object, today: str | None = None) -> int | None:
    sd = _parse_date(signal_date)
    if sd is None:
        return None
    if today:
        nd = _parse_date(today)
    else:
        nd = datetime.now(timezone.utc).date()
    if nd is None:
        return None
    return (nd - sd).days


def _fmt_pct(v: float) -> str:
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.1f}%"


def graded_receipts(
    plans: list[dict],
    *,
    closes_loader: Callable[[str], tuple[list[str], list[float]] | None] | None = None,
    today: str | None = None,
    max_age_days: int = _MAX_AGE_DAYS,
) -> list[dict]:
    """Extract real graded receipts from Prophet plans.

    A "receipt" is a plan where something concrete happened:
    - At least one profit_plan level has status=="DONE"  → WIN
    - phase=="invalidated"                               → LOSS (entry→invalidation)
    - Both above on the same plan                        → MIXED (the richest receipt)

    Freshness: signal_date must be within max_age_days of today.
    Deduplication: one receipt per ticker; richest kind wins (mixed > win > loss).
    """
    if not plans:
        return []

    raw: list[dict] = []

    for plan in plans:
        if not isinstance(plan, dict):
            continue
        ticker = plan.get("asset", "")
        if not ticker:
            continue

        signal_date_raw = plan.get("_signal_date")
        age = _age_days(signal_date_raw, today=today)
        if age is None or age < 0 or age > max_age_days:
            continue

        signal_date = str(signal_date_raw)[:10] if signal_date_raw else ""
        entry = float(plan.get("entry") or 0)
        invalidation = float(plan.get("invalidation") or 0)
        phase = str(plan.get("phase", "")).lower()
        profit_plan = plan.get("profit_plan") or []

        # Check for DONE targets
        done_levels: list[dict] = []
        if isinstance(profit_plan, list):
            for lvl in profit_plan:
                if isinstance(lvl, dict) and str(lvl.get("status", "")).upper() == "DONE":
                    done_levels.append(lvl)

        is_invalidated = phase == "invalidated"
        is_win = bool(done_levels) and entry > 0

        if not is_win and not is_invalidated:
            continue

        receipt: dict = {
            "ticker": ticker,
            "signal_date": signal_date,
            "entry": entry,
        }

        if is_win and is_invalidated:
            receipt["kind"] = "mixed"
            # Best DONE level (last one = highest label e.g. T1 before T2)
            best = done_levels[-1]
            target = float(best.get("level") or 0)
            gain_pct = (target - entry) / entry * 100 if entry > 0 else 0.0
            receipt["target"] = target
            receipt["gain_pct"] = round(gain_pct, 1)
            receipt["gain_pct_str"] = _fmt_pct(gain_pct)
            receipt["target_label"] = best.get("label", "T1")
            stop = invalidation
            loss_pct = (stop - entry) / entry * 100 if entry > 0 else 0.0
            receipt["stop"] = stop
            receipt["loss_pct"] = round(loss_pct, 1)
            receipt["loss_pct_str"] = _fmt_pct(loss_pct)

        elif is_win:
            receipt["kind"] = "win"
            best = done_levels[-1]
            target = float(best.get("level") or 0)
            gain_pct = (target - entry) / entry * 100 if entry > 0 else 0.0
            receipt["target"] = target
            receipt["gain_pct"] = round(gain_pct, 1)
            receipt["gain_pct_str"] = _fmt_pct(gain_pct)
            receipt["target_label"] = best.get("label", "T1")

        else:  # loss only
            receipt["kind"] = "loss"
            stop = invalidation
            loss_pct = (stop - entry) / entry * 100 if entry > 0 else 0.0
            receipt["stop"] = stop
            receipt["loss_pct"] = round(loss_pct, 1)
            receipt["loss_pct_str"] = _fmt_pct(loss_pct)

        raw.append(receipt)

    # Deduplicate: one per ticker, prefer richest kind (mixed > win > loss)
    best_by_ticker: dict[str, dict] = {}
    for r in raw:
        t = r["ticker"]
        if t not in best_by_ticker:
            best_by_ticker[t] = r
        else:
            existing_priority = _KIND_PRIORITY.get(best_by_ticker[t]["kind"], 0)
            new_priority = _KIND_PRIORITY.get(r["kind"], 0)
            if new_priority > existing_priority:
                best_by_ticker[t] = r

    # Return sorted by ticker for determinism
    return sorted(best_by_ticker.values(), key=lambda r: r["ticker"])
