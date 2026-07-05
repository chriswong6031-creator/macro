"""engine.neuralweb.metabolism — Machine registration for cortex-proposed hypotheses.

ANTI-MINING LAW (masterplan §5 W7b + §7)
-----------------------------------------
* registered_at is ALWAYS server-side (set here, never accepted from the cortex).
* Every grade is computed ONLY on data strictly after registered_at.
* Proposal budget: max 3 registrations per calendar week.  Beyond that →
  retire-one-to-file-one (an explicit retire() call required first).
* fdr_family is hard-wired to 'cortex' — the cortex cannot override it.
* All cortex hypotheses share one FDR family so their volume never raises
  the discovery bar for human programs.

REGISTRATION SCHEMA (neuralweb.machine_registry.v1)
-----------------------------------------------------
Required:
  id            str   "cortex-<YYYY-MM-DD>-<slug>"
  kind          str   "cortex_hypothesis"
  registered_at str   ISO-8601 UTC (server-side — this module)
  registered_by str   "cortex" or "cortex:<run_id>"
  fdr_family    str   "cortex" (hard-wired)
  claim_shape   str   one of CLAIM_SHAPES
  hypothesis    str   natural-language claim
  spine_query   dict  machine-readable claim spec
  pre_committed_gate dict {metric, threshold, min_n, horizon_d}
  horizon_d     int   trading-day evaluation horizon
  come_back     str   ISO-8601 date (registered_at + horizon_d + 7 buffer)

Optional:
  status        str   registered | budget-rejected | invalid | passed | failed |
                      insufficient-n | retired
  notes         str

BUDGET ENFORCEMENT (server-side)
---------------------------------
_count_week_registrations() counts rows with kind='cortex_hypothesis' AND
registered_at within the current calendar week (Mon-Sun).  BUDGET_PER_WEEK=3.
When exhausted, register_hypothesis() returns a budget-rejected row WITHOUT
writing to the registry.  retire() is required first.

TRIAL LEDGER WIRING
-------------------
On each accepted registration: log_declared_budget(1, family='cortex') is called
on the shared TrialLedger so the overfit_guard DSR haircut stays honest as
cortex volume grows.

GOVERNANCE EVENTS
-----------------
Every accepted registration appends an a6_llm_proposed event to governance.jsonl
(per the A6 Lane-(ii) doctrine in constitution.py).
Every retire() appends a tier_demotion event.
These are the only governance writes; evaluation results are written by the
evaluator, not here.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_SCHEMA = "neuralweb.machine_registry.v1"
_REGISTRY_FILE = Path("data") / "neuralweb" / "machine_registry.jsonl"
_BUDGET_PER_WEEK = 3

CLAIM_SHAPES = frozenset({
    "lead_lag",
    "conditional_regime",
    "entry_quality",
    "sector_conditional",
})

_WRITE_LOCK = threading.Lock()


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _registry_path(root: Path | str | None = None) -> Path:
    if root is not None:
        return Path(root) / "data" / "neuralweb" / "machine_registry.jsonl"
    try:
        from lib import config as _cfg  # type: ignore[import]
        return Path(_cfg.data_dir()) / "neuralweb" / "machine_registry.jsonl"
    except Exception:  # noqa: BLE001
        return _REGISTRY_FILE


def _ledger_path(root: Path | str | None = None) -> Path:
    if root is not None:
        return Path(root) / "data" / "trial_ledger.jsonl"
    try:
        from engine.trial_ledger import DEFAULT_PATH  # type: ignore[import]
        return DEFAULT_PATH
    except Exception:  # noqa: BLE001
        return Path("data") / "trial_ledger.jsonl"


# ---------------------------------------------------------------------------
# Registry I/O
# ---------------------------------------------------------------------------

def _load_registry(root: Path | str | None) -> list[dict]:
    p = _registry_path(root)
    if not p.exists():
        return []
    rows = []
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:  # noqa: BLE001
                pass
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism: could not load registry (%s)", exc)
    return rows


def _append_registry(row: dict, root: Path | str | None) -> bool:
    p = _registry_path(root)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with _WRITE_LOCK:
            with p.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, default=str) + "\n")
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism: append_registry failed (%s)", exc)
        return False


def _update_row_status(row_id: str, new_status: str, root: Path | str | None) -> bool:
    """Rewrite the registry file with updated status for row_id.  Returns True on success."""
    p = _registry_path(root)
    try:
        rows = _load_registry(root)
        updated = False
        new_lines = []
        for row in rows:
            if row.get("id") == row_id:
                row = dict(row)
                row["status"] = new_status
                updated = True
            new_lines.append(json.dumps(row, default=str))
        if not updated:
            return False
        with _WRITE_LOCK:
            p.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism: update_row_status failed (%s)", exc)
        return False


# ---------------------------------------------------------------------------
# Budget enforcement (server-side)
# ---------------------------------------------------------------------------

def _iso_week_key(dt: datetime) -> str:
    """Return 'YYYY-WNN' ISO week key for dt."""
    year, week, _ = dt.isocalendar()
    return f"{year}-W{week:02d}"


def _count_week_registrations(root: Path | str | None, now: datetime) -> int:
    """Count accepted registrations in the current calendar week."""
    week_key = _iso_week_key(now)
    rows = _load_registry(root)
    count = 0
    for row in rows:
        if row.get("kind") != "cortex_hypothesis":
            continue
        if row.get("status") in ("budget-rejected", "invalid", "retired"):
            continue
        rat = row.get("registered_at")
        if not rat:
            continue
        try:
            dt = datetime.fromisoformat(str(rat))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if _iso_week_key(dt) == week_key:
                count += 1
        except Exception:  # noqa: BLE001
            pass
    return count


def _count_open_hypotheses(root: Path | str | None) -> int:
    """Count hypotheses that are registered and not retired/failed/passed."""
    rows = _load_registry(root)
    open_statuses = {"registered", "accruing", "insufficient-n"}
    return sum(
        1 for r in rows
        if r.get("kind") == "cortex_hypothesis"
        and r.get("status") in open_statuses
    )


# ---------------------------------------------------------------------------
# ID / slug helpers
# ---------------------------------------------------------------------------

def _make_id(hypothesis: str, now: datetime) -> str:
    """Generate a stable cortex-<date>-<slug> id."""
    today = now.strftime("%Y-%m-%d")
    slug = re.sub(r"[^a-z0-9]+", "-", hypothesis.lower()[:40]).strip("-")
    h = hashlib.sha256(f"{today}:{hypothesis}".encode()).hexdigest()[:6]
    return f"cortex-{today}-{slug}-{h}"


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------

_REQUIRED_GATE_KEYS = {"metric", "threshold", "min_n", "horizon_d"}


def _validate_hypothesis(h: dict) -> list[str]:
    """Return list of validation errors (empty = valid)."""
    errors: list[str] = []

    if not h.get("hypothesis"):
        errors.append("hypothesis: missing or empty")

    cs = h.get("claim_shape")
    if cs not in CLAIM_SHAPES:
        errors.append(f"claim_shape: must be one of {sorted(CLAIM_SHAPES)}, got {cs!r}")

    gate = h.get("pre_committed_gate")
    if not gate or not isinstance(gate, dict):
        errors.append("pre_committed_gate: missing or not a dict")
    else:
        missing = _REQUIRED_GATE_KEYS - set(gate.keys())
        if missing:
            errors.append(f"pre_committed_gate: missing required keys {sorted(missing)}")
        try:
            int(gate.get("min_n", 0))
        except (TypeError, ValueError):
            errors.append("pre_committed_gate.min_n: must be an integer")
        try:
            int(gate.get("horizon_d", 0))
        except (TypeError, ValueError):
            errors.append("pre_committed_gate.horizon_d: must be an integer")

    sq = h.get("spine_query")
    if not sq or not isinstance(sq, dict):
        errors.append("spine_query: missing or not a dict")

    hd = h.get("horizon_d")
    try:
        if hd is None or int(hd) <= 0:
            errors.append("horizon_d: must be a positive integer")
    except (TypeError, ValueError):
        errors.append("horizon_d: must be an integer")

    return errors


# ---------------------------------------------------------------------------
# Trial ledger wiring
# ---------------------------------------------------------------------------

def _log_to_trial_ledger(row_id: str, root: Path | str | None) -> None:
    """Log one declared trial to the trial ledger for the 'cortex' family."""
    try:
        from engine.trial_ledger import TrialLedger  # type: ignore[import]
        led = TrialLedger(path=_ledger_path(root))
        led.log_declared_budget(1, family="cortex",
                                reason=f"cortex hypothesis registration: {row_id}")
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism: trial ledger update failed for %s (%s)", row_id, exc)


# ---------------------------------------------------------------------------
# Governance event wiring
# ---------------------------------------------------------------------------

def _emit_governance(
    event_type: str,
    row_id: str,
    note: str,
    root: Path | str | None,
    evidence: dict | None = None,
) -> None:
    """Append a governance event.  Fail-open."""
    try:
        from engine.neuralweb.governance import append_event  # type: ignore[import]
        append_event(
            event_type,
            target=f"cortex_hypothesis:{row_id}",
            article=6,
            authored_by="metabolism",
            note=note,
            evidence=evidence,
            root=root,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism: governance event failed for %s (%s)", row_id, exc)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def register_hypothesis(
    h: dict[str, Any],
    root: Path | str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Consume an inbox row and register it in the machine registry.

    Parameters
    ----------
    h : dict
        Must carry: hypothesis (str), claim_shape, spine_query, pre_committed_gate,
        horizon_d, and optionally registered_by.
        Must NOT carry registered_at — this is set server-side here.

    Returns
    -------
    dict with keys: id, status, registered_at (or budget_state), reason.
    Status values:
      "registered"       — accepted and written
      "budget-rejected"  — weekly budget exhausted (retire first)
      "invalid"          — schema validation failed
    """
    if now is None:
        now = datetime.now(timezone.utc)

    # Step 1: schema validation
    errors = _validate_hypothesis(h)
    if errors:
        row_id = _make_id(h.get("hypothesis", "unknown"), now)
        log.warning("metabolism: register_hypothesis invalid (%s): %s", row_id, errors)
        invalid_row: dict[str, Any] = {
            "schema": _SCHEMA,
            "id": row_id,
            "kind": "cortex_hypothesis",
            "status": "invalid",
            "registered_at": None,
            "registered_by": h.get("registered_by", "cortex"),
            "fdr_family": "cortex",
            "claim_shape": h.get("claim_shape"),
            "hypothesis": h.get("hypothesis", ""),
            "spine_query": h.get("spine_query"),
            "pre_committed_gate": h.get("pre_committed_gate"),
            "horizon_d": h.get("horizon_d"),
            "come_back": None,
            "reason": "; ".join(errors),
        }
        _append_registry(invalid_row, root)
        return {"id": row_id, "status": "invalid", "reason": "; ".join(errors)}

    row_id = _make_id(h["hypothesis"], now)

    # Step 2: budget enforcement (server-side)
    week_count = _count_week_registrations(root, now)
    if week_count >= _BUDGET_PER_WEEK:
        log.warning(
            "metabolism: BUDGET EXHAUSTED for week %s (%d/%d) — retire first",
            _iso_week_key(now), week_count, _BUDGET_PER_WEEK,
        )
        budget_row: dict[str, Any] = {
            "schema": _SCHEMA,
            "id": row_id,
            "kind": "cortex_hypothesis",
            "status": "budget-rejected",
            "registered_at": None,
            "registered_by": h.get("registered_by", "cortex"),
            "fdr_family": "cortex",
            "claim_shape": h.get("claim_shape"),
            "hypothesis": h.get("hypothesis", ""),
            "spine_query": h.get("spine_query"),
            "pre_committed_gate": h.get("pre_committed_gate"),
            "horizon_d": h.get("horizon_d"),
            "come_back": None,
            "reason": (
                f"budget-rejected: week {_iso_week_key(now)} already has "
                f"{week_count}/{_BUDGET_PER_WEEK} registrations. "
                "Call retire() on an existing hypothesis first."
            ),
            "budget_state": {
                "week": _iso_week_key(now),
                "used": week_count,
                "limit": _BUDGET_PER_WEEK,
            },
        }
        _append_registry(budget_row, root)
        return {
            "id": row_id,
            "status": "budget-rejected",
            "reason": budget_row["reason"],
            "budget_state": budget_row["budget_state"],
        }

    # Step 3: build the registration row
    registered_at = now.isoformat(timespec="seconds")
    horizon_d = int(h["horizon_d"])
    come_back_dt = now.date() + timedelta(days=horizon_d + 7)

    reg_row: dict[str, Any] = {
        "schema": _SCHEMA,
        "id": row_id,
        "kind": "cortex_hypothesis",
        "status": "registered",
        "registered_at": registered_at,      # SERVER-SIDE: never accepted from cortex
        "registered_by": h.get("registered_by", "cortex"),
        "fdr_family": "cortex",              # HARD-WIRED
        "claim_shape": h["claim_shape"],
        "hypothesis": h["hypothesis"],
        "spine_query": h["spine_query"],
        "pre_committed_gate": h["pre_committed_gate"],
        "horizon_d": horizon_d,
        "come_back": come_back_dt.isoformat(),
        "is_context_only": True,
    }

    # Step 4: write to registry
    written = _append_registry(reg_row, root)
    if not written:
        return {
            "id": row_id,
            "status": "invalid",
            "reason": "registry write failed",
        }

    # Step 5: declare in trial ledger
    _log_to_trial_ledger(row_id, root)

    # Step 6: governance event (A6 lane-ii — LLM-proposed).
    # Record the pre-committed gate, spine_query, claim_shape, and horizon_d
    # as evidence so that any post-hoc edit to machine_registry.jsonl is
    # detectable against this ledger entry.  Exploitation still requires
    # filesystem write access to machine_registry.jsonl (which is git-tracked),
    # but this closes the "visible in the ledger" gap named in the spec.
    _emit_governance(
        "a6_llm_proposed",
        row_id,
        f"cortex hypothesis registered: {h['hypothesis'][:120]}",
        root,
        evidence={
            "pre_committed_gate": h["pre_committed_gate"],
            "spine_query": h["spine_query"],
            "claim_shape": h["claim_shape"],
            "horizon_d": horizon_d,
        },
    )

    log.info(
        "metabolism: registered %s (shape=%s, horizon=%dd, come_back=%s)",
        row_id, h["claim_shape"], horizon_d, come_back_dt,
    )
    return {
        "id": row_id,
        "status": "registered",
        "registered_at": registered_at,
        "come_back": come_back_dt.isoformat(),
    }


def retire(
    hypothesis_id: str,
    reason: str,
    root: Path | str | None = None,
) -> bool:
    """Retire an existing hypothesis (required for retire-one-to-file-one).

    Updates status to 'retired' in the registry and appends a governance event.
    Returns True on success, False if not found.
    """
    ok = _update_row_status(hypothesis_id, "retired", root)
    if ok:
        _emit_governance(
            "tier_demotion",
            hypothesis_id,
            f"retired: {reason[:200]}",
            root,
        )
        log.info("metabolism: retired %s (%s)", hypothesis_id, reason[:80])
    else:
        log.warning("metabolism: retire — id %r not found in registry", hypothesis_id)
    return ok


def load_due(
    root: Path | str | None = None,
    today: date | None = None,
) -> list[dict]:
    """Return registered hypotheses whose come_back date <= today and status='registered'."""
    if today is None:
        today = datetime.now(timezone.utc).date()
    rows = _load_registry(root)
    due = []
    for row in rows:
        if row.get("kind") != "cortex_hypothesis":
            continue
        if row.get("status") != "registered":
            continue
        cb = row.get("come_back")
        if not cb:
            continue
        try:
            cb_date = date.fromisoformat(str(cb)[:10])
            if cb_date <= today:
                due.append(row)
        except Exception:  # noqa: BLE001
            pass
    return due


def load_by_id(
    hypothesis_id: str,
    root: Path | str | None = None,
) -> dict | None:
    """Return the most recent registry row for hypothesis_id, or None."""
    rows = _load_registry(root)
    # Return last match (most recent status)
    found = None
    for row in rows:
        if row.get("id") == hypothesis_id:
            found = row
    return found


def inbox_to_registered(
    inbox_path: Path,
    root: Path | str | None = None,
    now: datetime | None = None,
) -> list[dict]:
    """Read hypothesis_inbox.jsonl and register all inbox-not-registered rows.

    Updates inbox rows with status transitions inline (status field).
    Returns list of registration results.
    """
    if not inbox_path.exists():
        return []

    results = []
    raw_lines = inbox_path.read_text(encoding="utf-8").splitlines()
    updated_lines = []

    for line in raw_lines:
        line_stripped = line.strip()
        if not line_stripped:
            updated_lines.append(line)
            continue
        try:
            row = json.loads(line_stripped)
        except Exception:  # noqa: BLE001
            updated_lines.append(line)
            continue

        if row.get("status") != "inbox-not-registered":
            updated_lines.append(line)
            continue

        # Attempt registration
        result = register_hypothesis(row, root=root, now=now)
        new_status = result.get("status", "invalid")
        row["status"] = new_status
        row["registration_result"] = result
        updated_lines.append(json.dumps(row, default=str))
        results.append(result)

    # Rewrite inbox with status updates (audit trail)
    try:
        inbox_path.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism: could not rewrite inbox (%s)", exc)

    return results
