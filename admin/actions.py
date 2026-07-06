"""admin.actions — Operator action ledger (L4 instrumentation, NW Rails PR-8).

Append-only JSONL ledger of operator decisions on alerts/experiments/boards.
Gitignored server-local: data/operator/action_ledger.jsonl.

Single writer: the admin server POST /api/actions endpoint. The nightly MUST NOT
stage this file (RUL-P10 path a — explicit .gitignore entry).

Schema per row
--------------
  ts           str  ISO-8601 UTC, server-stamped (never caller-supplied)
  actor        str  always "operator"
  surface      str  alert id / experiment id / board name (from caller)
  action       str  one of VALID_ACTIONS
  direction_note str  free text, capped at NOTE_MAX_CHARS
  latency_s    float|null  server-computed from alert_emit_ts when provided

Design law
----------
append_action() NEVER raises to the caller: any IO error is logged-and-dropped.
The ledger accumulates in calendar time; grading harness is a post-Fable wave
(same Wilson floor n>=25 as the cortex A2 gate).
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

VALID_ACTIONS = frozenset({"acted", "dismissed", "overrode", "snoozed"})
NOTE_MAX_CHARS = 280

# Resolved at module load; admin/paths.py ROOT is repo-root.
# Keep import lazy to avoid circular deps (paths → dotenv → no deps).
def _ledger_path() -> Path:
    from .paths import DATA
    return DATA / "operator" / "action_ledger.jsonl"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def append_action(
    surface: str,
    action: str,
    direction_note: str,
    alert_emit_ts: str | None = None,
) -> dict:
    """Append one operator action row to the ledger.

    Parameters
    ----------
    surface        : alert id, experiment id, or board name
    action         : one of VALID_ACTIONS
    direction_note : free text, silently capped at NOTE_MAX_CHARS
    alert_emit_ts  : ISO-8601 UTC string of when the alert was emitted;
                     when provided latency_s is computed server-side

    Returns
    -------
    The row dict that was (attempted to be) written.  Returned even on IO
    error so the caller can include it in the HTTP response.
    """
    ts_now = _now_iso()

    # Sanitise inputs
    note = str(direction_note or "")[:NOTE_MAX_CHARS]

    latency_s: float | None = None
    if alert_emit_ts:
        try:
            emit_dt = datetime.fromisoformat(str(alert_emit_ts).replace("Z", "+00:00"))
            now_dt = datetime.now(timezone.utc)
            latency_s = round((now_dt - emit_dt).total_seconds(), 1)
        except Exception:  # noqa: BLE001
            latency_s = None

    row = {
        "ts": ts_now,
        "actor": "operator",
        "surface": str(surface or ""),
        "action": str(action),
        "direction_note": note,
        "latency_s": latency_s,
    }

    try:
        p = _ledger_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
    except Exception as exc:  # noqa: BLE001
        logger.error("action_ledger write failed (dropped): %s", exc)

    return row
