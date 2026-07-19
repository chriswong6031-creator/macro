"""admin.allies_store — Operator status ledger for Allies targets (MKT-D11 W1).

Append-only JSONL ledger of operator status transitions on ally candidates
(finance creators / newsletters / communities / fund managers). Gitignored
server-local: data/operator/allies_status.jsonl.

**MKT-D11 law:** every external contact is a human operator acting *outside*
this system. This ledger records that a decision was made; it NEVER contacts
anyone. A status transition past ``candidate`` is an operator-only action.

Single writer: the admin server POST /api/marketing/allies/transition endpoint.
The nightly MUST NOT stage this file (same .gitignore path-a rule as the action
ledger — data/operator/ is fully ignored).

Schema per row
--------------
  ts           str  ISO-8601 UTC, server-stamped (never caller-supplied)
  actor        str  always "operator"
  target_id    str  the allies_target id this decision is about
  from_status  str  status the target was in when the decision was recorded
  to_status    str  status the operator moved it to
  note         str  free text, capped at NOTE_MAX_CHARS

Transition law
--------------
The status machine is deliberately narrow. Legal steps:

    candidate         -> operator_approved
    operator_approved -> contacted
    contacted         -> active
    <any status>      -> retired      (an operator can always shelve a target)

Anything else is rejected. ``append_transition`` sanitises inputs and NEVER
raises to the caller (IO errors are logged-and-dropped, exactly like
admin.actions.append_action). ``fold_status`` replays the ledger over the seed
targets to derive each target's current status + history; malformed or illegal
transitions, and transitions that reference an unknown target, are skipped with
a logged warning rather than corrupting the fold.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# The seed status every target starts in (from allies_targets.jsonl).
SEED_STATUS = "candidate"

# Every status a target can be in.
VALID_STATUSES = ("candidate", "operator_approved", "contacted", "active", "retired")

# Legal forward steps. "retired" is reachable from ANY status (see is_legal).
_FORWARD = {
    "candidate": "operator_approved",
    "operator_approved": "contacted",
    "contacted": "active",
}

NOTE_MAX_CHARS = 280


# ---------------------------------------------------------------------------
# Paths / time (kept lazy + patchable, mirroring admin.actions)
# ---------------------------------------------------------------------------

def _ledger_path() -> Path:
    from .paths import DATA
    return DATA / "operator" / "allies_status.jsonl"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Transition rules
# ---------------------------------------------------------------------------

def is_legal(from_status: str, to_status: str) -> bool:
    """True iff moving from_status -> to_status is a sanctioned step.

    Retiring is always allowed (from any valid current status). Otherwise only
    the single next forward step is legal. Same-status and backward moves are
    rejected.
    """
    if to_status not in VALID_STATUSES:
        return False
    if from_status not in VALID_STATUSES:
        return False
    if to_status == "retired":
        # An operator can shelve a target from any live status, but retiring an
        # already-retired target is a no-op we still reject (nothing to record).
        return from_status != "retired"
    return _FORWARD.get(from_status) == to_status


def legal_next(from_status: str) -> list[str]:
    """The status values a target in from_status may legally move to.

    Returns the single forward step (if any) plus "retired" — in the order the
    operator control should offer them. A retired target has no legal moves.
    """
    if from_status == "retired" or from_status not in VALID_STATUSES:
        return []
    nxt = _FORWARD.get(from_status)
    out = [nxt] if nxt else []
    out.append("retired")
    return out


# ---------------------------------------------------------------------------
# Writer (never raises)
# ---------------------------------------------------------------------------

def append_transition(
    target_id: str,
    from_status: str,
    to_status: str,
    note: str = "",
) -> dict:
    """Append one operator status-transition row to the ledger.

    Parameters
    ----------
    target_id   : the allies_target id being moved
    from_status : the status the target was in (folded current status)
    to_status   : the status the operator moved it to
    note        : free text, silently capped at NOTE_MAX_CHARS

    Returns
    -------
    The row dict that was (attempted to be) written — returned even on IO error
    so the caller can echo it in the HTTP response. Validation of the transition
    is the *caller's* job (the server checks is_legal before calling); this
    writer records verbatim, exactly like admin.actions.append_action.
    """
    row = {
        "ts": _now_iso(),
        "actor": "operator",
        "target_id": str(target_id or ""),
        "from_status": str(from_status or ""),
        "to_status": str(to_status or ""),
        "note": str(note or "")[:NOTE_MAX_CHARS],
    }

    try:
        p = _ledger_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
    except Exception as exc:  # noqa: BLE001
        logger.error("allies_status write failed (dropped): %s", exc)

    return row


# ---------------------------------------------------------------------------
# Reader / fold
# ---------------------------------------------------------------------------

def read_transitions() -> list[dict]:
    """Read all operator transition rows. Fail-soft: [] if the file is absent
    or unreadable (day-0 accruing state)."""
    try:
        p = _ledger_path()
        if not p.exists():
            return []
        rows: list[dict] = []
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:  # noqa: BLE001 — one bad line never kills the fold
                logger.warning("allies_status: skipping malformed ledger line")
                continue
            if isinstance(obj, dict):
                rows.append(obj)
        return rows
    except Exception as exc:  # noqa: BLE001
        logger.warning("allies_status read failed: %s", exc)
        return []


def fold_status(targets: list[dict], transitions: list[dict] | None = None) -> dict:
    """Replay the operator ledger over the seed targets.

    Every target starts at SEED_STATUS ("candidate"). Transitions are applied in
    ledger order; a transition is applied only if it is legal *from the target's
    current folded status* and references a known target. Illegal transitions,
    transitions on unknown targets, and rows missing target_id/to_status are
    ignored with a logged warning (they never corrupt the fold or raise).

    Note: the ledger row's own ``from_status`` is advisory — the fold trusts its
    own running current status, so a stale client (two operators, one behind)
    can't apply an out-of-order step. Last *valid* transition wins.

    Returns
    -------
    { target_id: {"status": <current>, "history": [row, ...]} }
    where history is the list of transitions that were actually applied, oldest
    first. Targets with no transitions get {"status": SEED_STATUS, "history": []}.
    """
    if transitions is None:
        transitions = read_transitions()

    known = {str(t.get("target_id")) for t in (targets or []) if t.get("target_id") is not None}
    fold: dict[str, dict] = {
        tid: {"status": SEED_STATUS, "history": []} for tid in known
    }

    for row in transitions:
        if not isinstance(row, dict):
            continue
        tid = row.get("target_id")
        to_status = row.get("to_status")
        if tid is None or to_status is None:
            logger.warning("allies_status: transition missing target_id/to_status — ignored")
            continue
        tid = str(tid)
        if tid not in fold:
            logger.warning("allies_status: transition references unknown target %r — ignored", tid)
            continue
        current = fold[tid]["status"]
        if not is_legal(current, str(to_status)):
            logger.warning(
                "allies_status: illegal transition %s: %s -> %s (ignored)",
                tid, current, to_status,
            )
            continue
        fold[tid]["status"] = str(to_status)
        fold[tid]["history"].append(row)

    return fold
