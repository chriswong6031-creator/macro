"""Live dating for the policy layer — turn the static check-by / as-of dates into live
status: intel staleness, task-force deadline countdowns, and overdue-prediction flags.

Pure + defensive (date arithmetic only); never raises. Display-only — it just makes the
dated artifacts self-announce when they need re-verification (stale intel) or resolution
(a prediction whose check-by has passed while still 'open')."""
from __future__ import annotations

from datetime import date

_STALE_DAYS = 14          # intel older than this prompts a re-verify banner


def _days_to(iso: str | None, today: date) -> int | None:
    """Signed days from today to `iso` (negative = in the past). None if unparseable."""
    try:
        return (date.fromisoformat(iso) - today).days
    except Exception:  # noqa: BLE001
        return None


def annotate(intel: dict | None, today: date | None = None) -> dict:
    """Compute live date status for the intel substrate. Returns staleness + per-id
    task-force / prediction status maps + overdue counts. Defensive on missing fields."""
    intel = intel or {}
    today = today or date.today()

    asof_age = _days_to(intel.get("as_of"), today)
    age_days = (-asof_age) if asof_age is not None else None
    staleness = {"as_of": intel.get("as_of"), "age_days": age_days,
                 "stale": age_days is not None and age_days > _STALE_DAYS}

    tf = {}
    for t in (intel.get("fed", {}).get("task_forces") or []):
        dd = _days_to(t.get("check_by"), today)
        tf[t.get("id")] = {"days_to": dd,
                           "overdue": dd is not None and dd < 0 and t.get("status") == "pending"}

    pr = {}
    for p in (intel.get("predictions") or []):
        dd = _days_to(p.get("check_by"), today)
        pr[p.get("id")] = {"days_to": dd,
                           "overdue": dd is not None and dd < 0 and p.get("status") == "open"}

    return {
        "today": today.isoformat(),
        "staleness": staleness,
        "task_forces": tf,
        "predictions": pr,
        "overdue_task_forces": sum(1 for x in tf.values() if x["overdue"]),
        "overdue_predictions": sum(1 for x in pr.values() if x["overdue"]),
    }
