"""scripts/metabolism_journal.py — Per-cycle journal for the Metabolism loop (A1).

STATELESS-CATTLE LAW (R-AUT-3): all loop state lives in git artifacts.
This module is the sole canonical writer/reader of
data/metabolism/journal/<cycle_id>.json.

Schema (metabolism.journal.v1):
  {
    "schema":     "metabolism.journal.v1",
    "cycle_id":   str,           # e.g. "cycle-2026-07-09-0001"
    "stage":      str,           # last-written stage name
    "status":     str,           # "pending" | "running" | "done" | "failed" | "noop_paused"
    "auth_ok":    bool | None,   # result of A2 preflight (None = not yet run)
    "artifacts":  list[str],     # paths of artifacts produced so far
    "next_stage": str | None,    # stage to run next (null when done/failed)
    "ts":         str,           # ISO-8601 UTC of last update
    "stages":     dict,          # per-stage completion records
  }

RESUME SEMANTICS:
  - start_stage()  → sets stage="<name>", status="running", ts=now; idempotent if
    already "done" for that stage (returns existing record without overwriting).
  - finish_stage() → records status for a stage in journal["stages"][name]; if the
    stage was the last → sets top-level status to "done".
  - is_stage_done() → True when journal["stages"][name]["status"] == "done".
  - The caller loop: if is_stage_done("sense"): skip sense.  Only run pending stages.

NEVER-RAISE CONTRACT (mirrors governance.py):
  All public functions catch ALL exceptions, log a warning, and return a safe
  fallback.  A journal failure must never abort the stage that invoked it.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_SCHEMA = "metabolism.journal.v1"
_JOURNAL_SUBDIR = Path("data") / "metabolism" / "journal"

_VALID_STATUSES = frozenset({"pending", "running", "done", "failed", "noop_paused"})


# ── Path helpers ─────────────────────────────────────────────────────────────

def _repo_root() -> Path:
    """Auto-detect repo root from this file's location (scripts/metabolism_journal.py)."""
    return Path(__file__).resolve().parent.parent


def journal_path(cycle_id: str, root: Path | None = None) -> Path:
    """Return the path for a given cycle_id's journal file."""
    base = root if root is not None else _repo_root()
    return base / _JOURNAL_SUBDIR / f"{cycle_id}.json"


# ── Internal read/write ──────────────────────────────────────────────────────

def _read_journal(cycle_id: str, root: Path | None = None) -> dict[str, Any]:
    """Read the journal for cycle_id; returns an empty-ish default if absent or corrupt."""
    p = journal_path(cycle_id, root)
    if not p.exists():
        return _default_journal(cycle_id)
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_journal: corrupt journal %s: %s — returning default", p, exc)
        return _default_journal(cycle_id)


def _write_journal(cycle_id: str, data: dict[str, Any], root: Path | None = None) -> bool:
    """Atomically write the journal for cycle_id. Returns True on success."""
    try:
        p = journal_path(cycle_id, root)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        tmp.replace(p)
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_journal: write failed for %s: %s", cycle_id, exc)
        return False


def _default_journal(cycle_id: str) -> dict[str, Any]:
    """Return the default (empty) journal for a new cycle."""
    return {
        "schema": _SCHEMA,
        "cycle_id": cycle_id,
        "stage": "",
        "status": "pending",
        "auth_ok": None,
        "artifacts": [],
        "next_stage": None,
        "ts": _now_iso(),
        "stages": {},
    }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ── Public API ───────────────────────────────────────────────────────────────

def load_journal(cycle_id: str, root: Path | None = None) -> dict[str, Any]:
    """Return the current journal for cycle_id (reads from disk).

    Returns
    -------
    dict — journal data (never raises).
    """
    try:
        return _read_journal(cycle_id, root)
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_journal.load_journal: %s", exc)
        return _default_journal(cycle_id)


def start_stage(
    cycle_id: str,
    stage: str,
    root: Path | None = None,
) -> dict[str, Any]:
    """Record that a stage has started running.

    If the stage is already "done" in the journal, returns the existing journal
    unchanged (idempotency: re-running a done stage is a no-op).

    Parameters
    ----------
    cycle_id : str
    stage    : str — stage name (e.g. "sense", "preflight", "propose")
    root     : Path | None — repo root for test isolation

    Returns
    -------
    dict — updated journal (never raises).
    """
    try:
        j = _read_journal(cycle_id, root)

        # Idempotency: if this stage is already done, skip
        existing = j.get("stages", {}).get(stage, {})
        if existing.get("status") == "done":
            log.debug("metabolism_journal.start_stage: %s/%s already done — skipping", cycle_id, stage)
            return j

        ts = _now_iso()
        j["stage"] = stage
        j["status"] = "running"
        j["ts"] = ts

        # Record per-stage entry
        if "stages" not in j:
            j["stages"] = {}
        j["stages"][stage] = {
            "status": "running",
            "started_at": ts,
        }
        _write_journal(cycle_id, j, root)
        return j
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_journal.start_stage(%s, %s): %s", cycle_id, stage, exc)
        return _default_journal(cycle_id)


def finish_stage(
    cycle_id: str,
    stage: str,
    status: str,
    *,
    artifacts: list[str] | None = None,
    next_stage: str | None = None,
    auth_ok: bool | None = None,
    note: str | None = None,
    root: Path | None = None,
) -> dict[str, Any]:
    """Record that a stage has finished with the given status.

    Parameters
    ----------
    cycle_id  : str
    stage     : str — stage name
    status    : str — one of "done" | "failed" | "noop_paused"
    artifacts : list[str] | None — paths produced by this stage (appended)
    next_stage: str | None — stage to run next
    auth_ok   : bool | None — if provided, sets journal["auth_ok"]
    note      : str | None — human-readable annotation
    root      : Path | None

    Returns
    -------
    dict — updated journal (never raises).
    """
    try:
        if status not in _VALID_STATUSES:
            log.warning("metabolism_journal.finish_stage: unknown status %r", status)

        j = _read_journal(cycle_id, root)
        ts = _now_iso()

        # Update per-stage record
        if "stages" not in j:
            j["stages"] = {}
        stage_rec = j["stages"].get(stage, {})
        stage_rec["status"] = status
        stage_rec["finished_at"] = ts
        if note:
            stage_rec["note"] = note
        j["stages"][stage] = stage_rec

        # Update top-level fields
        j["stage"] = stage
        j["status"] = status
        j["ts"] = ts

        if artifacts:
            existing = j.get("artifacts") or []
            j["artifacts"] = list(dict.fromkeys(existing + artifacts))  # dedup, order-stable

        if next_stage is not None:
            j["next_stage"] = next_stage

        if auth_ok is not None:
            j["auth_ok"] = auth_ok

        _write_journal(cycle_id, j, root)
        return j
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_journal.finish_stage(%s, %s): %s", cycle_id, stage, exc)
        return _default_journal(cycle_id)


def is_stage_done(cycle_id: str, stage: str, root: Path | None = None) -> bool:
    """Return True if stage is recorded as "done" in the journal.

    Used by loop orchestrators to skip already-completed stages (resume semantics).

    Returns
    -------
    bool — True iff the stage status == "done"; never raises.
    """
    try:
        j = _read_journal(cycle_id, root)
        return j.get("stages", {}).get(stage, {}).get("status") == "done"
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_journal.is_stage_done(%s, %s): %s", cycle_id, stage, exc)
        return False


def new_cycle_id(prefix: str = "cycle") -> str:
    """Generate a fresh, collision-resistant cycle ID.

    Format: ``<prefix>-<date>-<sha4>``
    e.g.  ``cycle-2026-07-09-a3f2``

    The SHA-4 suffix uses the UTC timestamp at microsecond resolution to
    distinguish rapid successive calls.  Not cryptographically random — just
    collision-resistant for nightly scheduling.
    """
    ts_str = datetime.now(timezone.utc).isoformat()
    sha4 = hashlib.sha256(ts_str.encode()).hexdigest()[:4]
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"{prefix}-{date_str}-{sha4}"


def list_cycles(root: Path | None = None) -> list[str]:
    """Return sorted list of known cycle_ids (from journal directory).

    Returns
    -------
    list[str] — sorted cycle IDs; empty on error (never raises).
    """
    try:
        base = root if root is not None else _repo_root()
        d = base / _JOURNAL_SUBDIR
        if not d.exists():
            return []
        return sorted(p.stem for p in d.glob("*.json"))
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_journal.list_cycles: %s", exc)
        return []
