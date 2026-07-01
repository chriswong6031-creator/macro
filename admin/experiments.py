"""Experiments & Data Collection panel.

Reads the committed experiments registry (site/marketdata/experiments.json, emitted by
the macro build's engine.experiments_registry) and derives LIVE come-back timing + a
"results ready" count, so the console can tell the owner exactly when to return for the
next step of each running experiment / data-collection accrual.

Same shape as the other panels (brief.py): read a committed JSON from the local repo clone
(the VPS pulls main within minutes), compute derived fields, return a dict. Degrades to a
graceful "no registry yet" payload if the file is absent.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone

from .paths import SITE

_REGISTRY = SITE / "marketdata" / "experiments.json"
_PRIO = {"high": 0, "medium": 1, "low": 2}
# statuses that are already concluded (don't re-flag their come-back date as "newly ready")
_DONE = {"validated", "proven"}
# kinds that never auto-mature a result on their come-back date (a re-check prompt, not a result)
_NO_AUTO_READY = {"parked_research"}


def _read_json(p):
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return None


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _days_until(d) -> int | None:
    if not d:
        return None
    try:
        return (date.fromisoformat(str(d)[:10]) - _today()).days
    except Exception:  # noqa: BLE001
        return None


def _decorate(e: dict) -> dict:
    """Add live days_until + a 'ready' flag (come-back date reached, or the registry already
    computed results are in) so the timing stays current even if the JSON is a few days old."""
    du = _days_until(e.get("come_back_on"))
    ready = bool(e.get("ready")) or (
        du is not None and du <= 0
        and (e.get("status") or "") not in _DONE
        and (e.get("kind") or "") not in _NO_AUTO_READY)
    return {**e, "days_until": du, "ready": ready}


def panel() -> dict:
    """The full Experiments registry with live timing, sorted ready-first then soonest."""
    reg = _read_json(_REGISTRY)
    if not reg or not reg.get("experiments"):
        return {
            "ok": False, "experiments": [], "ready_count": 0, "n": 0,
            "reason": ("No experiments registry yet — the macro build emits "
                       "site/marketdata/experiments.json (engine.experiments_registry). "
                       "Run a build (or wait for the nightly) to populate it."),
        }
    exps = [_decorate(e) for e in reg.get("experiments") or []]
    exps.sort(key=lambda e: (not e["ready"],
                             e["days_until"] if e["days_until"] is not None else 9999,
                             _PRIO.get(e.get("priority"), 1)))
    ready = [e for e in exps if e["ready"]]
    # group counts by status for the header/overview
    by_status: dict[str, int] = {}
    for e in exps:
        by_status[e.get("status") or "?"] = by_status.get(e.get("status") or "?", 0) + 1
    return {
        "ok": True, "as_of": reg.get("as_of"), "generated_at": reg.get("generated_at"),
        "today": _today().isoformat(), "n": len(exps), "ready_count": len(ready),
        "by_status": by_status, "experiments": exps, "note": reg.get("note"),
    }


def alert_summary() -> dict:
    """Compact digest for /api/summary → the header badge + overview: how many experiments
    have results ready to review, and the single soonest one still accruing."""
    p = panel()
    if not p.get("ok"):
        return {"available": False, "ready_count": 0, "n": 0}
    upcoming = [e for e in p["experiments"] if not e["ready"] and e.get("days_until") is not None]
    soonest = min(upcoming, key=lambda e: e["days_until"]) if upcoming else None
    return {
        "available": True, "ready_count": p["ready_count"], "n": p["n"],
        "ready": [{"id": e["id"], "name": e["name"], "next_step": e.get("next_step"),
                   "phase_hint": e.get("phase_hint")} for e in p["experiments"] if e["ready"]][:6],
        "soonest": ({"id": soonest["id"], "name": soonest["name"],
                     "days_until": soonest["days_until"],
                     "come_back_on": soonest.get("come_back_on")} if soonest else None),
    }
