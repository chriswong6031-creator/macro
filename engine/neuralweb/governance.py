"""engine.neuralweb.governance — Neural Web governance event ledger.

Appends consequential authority-state transitions to
data/neuralweb/governance.jsonl (schema neuralweb.governance.v1).
The ledger is the permanent record of what the constitution authorised,
revoked, or lapsed — not the underlying evidence accumulation (that lives
in qledger, spine, and tune-logs).

WRITE DISCIPLINE
----------------
All nightly writers run serially inside the engine lane; manual / quarterly
events are appended by CLI at non-overlapping times.  No intraday writer
exists.  This mirrors the single-writer contract in engine/neuralweb/reflexes.py:
enforced by documented contract and workflow commit-step coverage, NOT a
global lock.

NEVER-RAISE CONTRACT
--------------------
append_event() catches all exceptions, logs a warning via the module logger,
and returns False — it NEVER propagates the exception to the caller.
A governance-logging failure must never abort the lane that generated it.

EVENT-TYPE VOCABULARY
---------------------
    authority_grant      — an engine earns a new authority level
    authority_lapse      — evidence goes stale or CI drops below zero
    tier_promotion       — artifact moves from lower to higher qual_ladder tier
    tier_demotion        — artifact drops a rung on the ladder
    a6_auto_apply        — lane-(i) deterministic bounded calibration write
    a6_llm_proposed      — lane-(ii) LLM-proposed parameter change
    config_arm           — dormant engine flips enabled:True
    config_disarm        — engine flips enabled:False
    operator_override    — human overrides an engine decision with evidence
    article3_review      — Article-3 review of a grandfathered authority grant
    research_factory_gate      — Research Factory human-gate decision
                                 (paper/deferred/rejected/scoped_build), article:null
    research_factory_challenge — Research Factory challenge packet written
                                 (advisory-only, RF-7), article:null
    metabolism_adjudication    — Metabolism A5 orchestrator grant/deny + the
                                 two-key resolution row (R-AUT-6), article:null
    metabolism_adversary_review — Metabolism A5 adversary veto/non-veto row
                                 (R-AUT-9), article:null

SCHEMA (neuralweb.governance.v1)
---------------------------------
Required on all rows:
    schema          "neuralweb.governance.v1"
    event_id        SHA-256[:16] of (event_type + target + ts)
    event_type      one of the vocabulary above
    target          the engine / artifact / flag being governed
    ts              ISO-8601 UTC, timespec="seconds"
    article         int (1, 2, 3, 6) or null
    authored_by     the writer identity

Optional on all rows:
    before          dict — state before the transition
    after           dict — state after the transition
    evidence        dict — evidence package at decision time
    root            str  — project root used by the writer (for test isolation)
    note            str  — free-form annotation
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_SCHEMA = "neuralweb.governance.v1"

_VALID_EVENT_TYPES = frozenset({
    "authority_grant",
    "authority_lapse",
    "tier_promotion",
    "tier_demotion",
    "a6_auto_apply",
    "a6_llm_proposed",
    "config_arm",
    "config_disarm",
    "operator_override",
    "article3_review",
    # W5 (RF-12): human-gate decisions recorded by research_factory_decide.py
    "research_factory_gate",
    # W4 (RF-12): challenge packets written by research_factory_challenge_pack.py
    "research_factory_challenge",
    # Metabolism A5 (R-AUT-6): ADJUDICATE row-pairs. metabolism_adjudication
    # carries both the orchestrator grant/deny and the two-key resolution;
    # metabolism_adversary_review carries the adversary veto/non-veto.  All are
    # display-tier (article:null) — the metabolism authors code, not signals.
    "metabolism_adjudication",
    "metabolism_adversary_review",
})


def _ledger_path(root: str | Path | None = None) -> Path:
    if root is None:
        try:
            from lib import config  # type: ignore[import]
            base = Path(config.data_dir())
        except Exception:  # noqa: BLE001
            base = Path("data")
    else:
        base = Path(root) / "data"
    p = base / "neuralweb" / "governance.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _event_id(event_type: str, target: str, ts: str) -> str:
    """SHA-256[:16] of (event_type + target + ts) — deterministic, matches reflex pattern."""
    raw = f"{event_type}|{target}|{ts}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def append_event(
    event_type: str,
    target: str,
    *,
    article: int | None = None,
    authored_by: str,
    evidence: dict[str, Any] | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    root: str | Path | None = None,
    note: str | None = None,
) -> bool:
    """Append one governance event to data/neuralweb/governance.jsonl.

    Parameters
    ----------
    event_type : str
        One of the event-type vocabulary above.
    target : str
        The engine, artifact path, or flag being governed
        (e.g. "engine/risk_radar_intl_audit.can_force:CN").
    article : int | None
        Constitutional article implicated (1, 2, 3, 6) or None.
    authored_by : str
        The writer identity (e.g. "risk_radar_intl_audit", "market_state_tune").
    evidence : dict | None
        Evidence package at decision time.
    before : dict | None
        State before the transition.
    after : dict | None
        State after the transition.
    root : str | Path | None
        Project root for path resolution (None = production paths).
    note : str | None
        Free-form human annotation.

    Returns
    -------
    bool
        True if the event was appended successfully; False on any error.
        NEVER raises.
    """
    try:
        if event_type not in _VALID_EVENT_TYPES:
            log.warning("governance: unknown event_type %r — allowed: %s",
                        event_type, sorted(_VALID_EVENT_TYPES))
            # Still write it; schema drift is diagnosed by the quarterly auditor

        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        eid = _event_id(event_type, target, ts)

        row: dict[str, Any] = {
            "schema": _SCHEMA,
            "event_id": eid,
            "event_type": event_type,
            "target": target,
            "ts": ts,
            "article": article,
            "authored_by": authored_by,
        }
        if evidence is not None:
            row["evidence"] = evidence
        if before is not None:
            row["before"] = before
        if after is not None:
            row["after"] = after
        if note is not None:
            row["note"] = note

        p = _ledger_path(root)
        line = json.dumps(row, separators=(",", ":"), default=str)
        with p.open("a") as fh:
            fh.write(line + "\n")
        return True

    except Exception as exc:  # noqa: BLE001
        log.warning("governance.append_event failed for %s/%s: %s", event_type, target, exc)
        return False


def load_events(
    root: str | Path | None = None,
    event_type: str | None = None,
    target: str | None = None,
) -> list[dict[str, Any]]:
    """Load and optionally filter governance events from the ledger.

    Parameters
    ----------
    root : str | Path | None
        Project root for path resolution (None = production paths).
    event_type : str | None
        If given, only return events of this type.
    target : str | None
        If given, only return events whose target starts with this prefix.

    Returns
    -------
    list[dict]
        Parsed rows matching the filters.  Empty on missing file or parse errors.
    """
    try:
        p = _ledger_path(root)
        if not p.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in p.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            if event_type is not None and row.get("event_type") != event_type:
                continue
            if target is not None and not str(row.get("target", "")).startswith(target):
                continue
            rows.append(row)
        return rows
    except Exception as exc:  # noqa: BLE001
        log.warning("governance.load_events failed: %s", exc)
        return []
