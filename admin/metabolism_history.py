"""admin/metabolism_history.py — Unified reverse-chronological change-history for
the Metabolism + Neural Web loops.

Aggregates every ledger the autonomous loops write when they change things:
PRs opened, audit verdicts, revert actions, immune heals, governance events,
charter proposals, revamp adjudications, lifecycle docket entries, cycle
journals, dispatch freezes, verify outcomes, lessons learned, parked
constructions, heartbeat probes, and shadow rehearsals.

FAIL-SOFT CONTRACT
------------------
Every source reader is wrapped in try/except.  A missing directory, corrupt
file, or unreadable JSON line is silently skipped — never fatal.  The top-level
history() function never raises.  A missing or nonexistent root path returns a
valid but empty response dict with all sources at count=0.

PUBLIC API
----------
history(limit=100, root=None) -> dict

  Returns:
    {
      "events": [...],        sorted newest-first, capped at `limit`
      "sources": {...},       one entry per source lane
      "phase0": bool,         True when no events outside {"heartbeat","shadow"}
      "generated_at": str     ISO-8601
    }

  `limit` is clamped to [1, 500].
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import github_api
from .paths import ROOT

_PHASE0_EXCLUDE = {"heartbeat", "shadow"}

_ALL_SOURCES = (
    "pr", "audit", "revert", "immune", "governance",
    "genesis", "revamp", "lifecycle", "journal", "freeze",
    "verify", "lesson", "parked", "heartbeat", "shadow",
)


# ---------------------------------------------------------------------------
# Timestamp helpers
# ---------------------------------------------------------------------------

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _parse_ts(ts_str: Any) -> datetime:
    """Parse an ISO-8601 timestamp string.  Returns _EPOCH on any failure.

    Always returns an AWARE datetime (naive inputs are assumed UTC): the
    ledgers mix "…Z" and "…+00:00" suffixes, and a naive/aware mix would make
    the feed-wide sort raise TypeError.
    """
    try:
        s = str(ts_str or "").strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:  # noqa: BLE001
        return _EPOCH


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _tail_lines(p: Path, n: int) -> list[str]:
    """Last n lines of a text file — bounds jsonl lanes so the request path
    stays flat as append-only ledgers accrue years of rows."""
    lines = p.read_text(encoding="utf-8").splitlines()
    return lines[-n:] if len(lines) > n else lines


# ---------------------------------------------------------------------------
# Source readers — each returns (events: list[dict], note: str | None)
# ---------------------------------------------------------------------------

def _read_pr(base: Path) -> tuple[list[dict], str | None]:  # noqa: ARG001
    """Source: github PR lane.

    Filter PRs whose head_ref starts with 'metabolism/' or 'claude/loop-'.
    """
    try:
        if not github_api.token():
            return [], "no GitHub token — PR lane unavailable"
        result = github_api.list_prs(per_page=100)
        if not result.get("ok"):
            err = result.get("error", "list_prs failed")
            return [], f"PR lane unavailable: {err}"
        events: list[dict] = []
        for p in result.get("prs") or []:
            head_ref = p.get("head_ref") or ""
            if not (head_ref.startswith("metabolism/") or head_ref.startswith("claude/loop-")):
                continue
            merged_at = p.get("merged_at")
            draft = p.get("draft", False)
            state = p.get("state") or "unknown"
            if merged_at:
                kind = "merged"
                status = "ok"
                ts = merged_at
            elif draft:
                kind = "draft"
                status = "info"
                ts = p.get("created_at") or ""
            else:
                kind = state
                status = "info" if state == "open" else "warn"
                ts = p.get("created_at") or ""
            events.append({
                "ts": ts,
                "source": "pr",
                "kind": kind,
                "title": p.get("title") or f"PR #{p.get('number')}",
                "detail": head_ref,
                "ref": f"#{p.get('number')}",
                "url": p.get("html_url"),
                "status": status,
            })
        return events, None
    except Exception as exc:  # noqa: BLE001
        return [], f"pr reader error: {exc}"


def _read_audit(base: Path) -> tuple[list[dict], str | None]:
    """Source: data/metabolism/audit/<pr>.json (metabolism.audit.v1)."""
    try:
        audit_dir = base / "data" / "metabolism" / "audit"
        if not audit_dir.exists():
            return [], None
        events: list[dict] = []
        for f in audit_dir.glob("*.json"):
            try:
                raw = json.loads(f.read_text(encoding="utf-8"))
                verdict = raw.get("verdict", "")
                pr_number = raw.get("pr_number")
                # verdict: approve → ok, reject → bad
                status = "ok" if verdict == "approve" else "bad"
                rationale = str(raw.get("rationale") or "")
                events.append({
                    "ts": raw.get("ts") or "",
                    "source": "audit",
                    "kind": verdict,
                    "title": f"PR audit: {verdict} — PR #{pr_number}",
                    "detail": rationale[:160],
                    "ref": f"#{pr_number}" if pr_number is not None else None,
                    "url": None,
                    "status": status,
                })
            except Exception:  # noqa: BLE001
                continue
        return events, None
    except Exception as exc:  # noqa: BLE001
        return [], f"audit reader error: {exc}"


def _read_revert(base: Path) -> tuple[list[dict], str | None]:
    """Source: data/metabolism/revert/<proposal_id>.json (metabolism.revert_actioned.v1).

    Fields: ts, proposal_id, status (revert_pr_opened|revert_conflict|revert_pr_open_failed),
    pr_number, branch, pr_url (via extra dict merge).
    """
    try:
        revert_dir = base / "data" / "metabolism" / "revert"
        if not revert_dir.exists():
            return [], None
        events: list[dict] = []
        for f in revert_dir.glob("*.json"):
            try:
                raw = json.loads(f.read_text(encoding="utf-8"))
                status_val = raw.get("status") or ""
                if status_val == "revert_pr_opened":
                    status = "warn"
                else:
                    status = "bad"
                pr_url = raw.get("pr_url")
                if not (isinstance(pr_url, str) and pr_url.startswith(("https://", "http://"))):
                    pr_url = None
                pr_number = raw.get("pr_number")
                proposal_id = raw.get("proposal_id") or f.stem
                events.append({
                    "ts": raw.get("ts") or "",
                    "source": "revert",
                    "kind": status_val,
                    "title": f"Revert actioned: {proposal_id} — {status_val}",
                    "detail": f"PR #{pr_number}" if pr_number else status_val,
                    "ref": f"#{pr_number}" if pr_number is not None else None,
                    "url": pr_url,
                    "status": status,
                })
            except Exception:  # noqa: BLE001
                continue
        return events, None
    except Exception as exc:  # noqa: BLE001
        return [], f"revert reader error: {exc}"


def _read_immune(base: Path) -> tuple[list[dict], str | None]:
    """Source: data/metabolism/immune_claims.jsonl rows.

    Fields per row: red_class, check_name, main_sha, pr_number, ts.
    Title MUST say 'draft' and must NOT say 'merged/applied' (R-V8-3).
    """
    try:
        p = base / "data" / "metabolism" / "immune_claims.jsonl"
        if not p.exists():
            return [], None
        events: list[dict] = []
        for line in _tail_lines(p, 1000):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                red_class = row.get("red_class") or row.get("check_name") or "unknown"
                pr_number = row.get("pr_number")
                events.append({
                    "ts": row.get("ts") or "",
                    "source": "immune",
                    "kind": "immune_heal",
                    # Title must say "draft"; must not say "merged" or "applied"
                    "title": f"Immune heal PR opened (draft) — {red_class}",
                    "detail": f"check: {row.get('check_name') or red_class}",
                    "ref": f"#{pr_number}" if pr_number is not None else None,
                    "url": None,
                    "status": "warn",
                })
            except Exception:  # noqa: BLE001
                continue
        return events, None
    except Exception as exc:  # noqa: BLE001
        return [], f"immune reader error: {exc}"


def _parse_article3_reason(reason: str) -> tuple[int | None, int | None]:
    """Extract n and min_n from a reason string like 'insufficient-n: n=9 < min_n=25'.

    Returns (n, min_n) as ints, or (None, None) if the pattern is absent/malformed.
    """
    try:
        import re  # noqa: PLC0415
        m = re.search(r"\bn=(\d+)", reason)
        m2 = re.search(r"\bmin_n=(\d+)", reason)
        n_val = int(m.group(1)) if m else None
        min_n_val = int(m2.group(1)) if m2 else None
        return n_val, min_n_val
    except Exception:  # noqa: BLE001
        return None, None


def _governance_title(event_type: str, target: str, row: dict,
                      payload: "dict | None" = None) -> str:
    """Build a human-readable title for a governance row.

    article3_review  → "Authority earn-in: {target} — {n} of {min_n} graded observations
                         (granted / still in shadow)"
    authority_lapse  → "Authority lapsed: {target} — evidence fell below the earn-in floor"
    everything else  → "{event_type}: {target}"

    FIX 4: Real writers (engine/altdata_brain.py:585-593) nest granted/reason under the
    'evidence' key.  Read from the already-flattened payload dict first; fall back to
    row top level for legacy tolerance.
    """
    if event_type == "article3_review":
        # Primary: payload (flattened from evidence/before/after by caller).
        # Fallback: row top level (legacy / test fixtures that put fields at top level).
        _src: dict = payload if isinstance(payload, dict) else {}
        granted = _src.get("granted") if "granted" in _src else row.get("granted")
        reason_val = _src.get("reason") if "reason" in _src else row.get("reason")
        reason = str(reason_val or "")
        n_val, min_n_val = _parse_article3_reason(reason)
        if n_val is not None and min_n_val is not None:
            status_word = "granted" if granted else "still in shadow"
            return (
                f"Authority earn-in: {target} — {n_val} of {min_n_val} "
                f"graded observations ({status_word})"
            )
        # Fallback: reason string may be empty or differently formatted
        status_word = "granted" if granted else "still in shadow"
        fallback_reason = reason if reason else "checking earn-in requirements"
        return f"Authority earn-in: {target} — {fallback_reason} ({status_word})"
    if event_type == "authority_lapse":
        return f"Authority lapsed: {target} — evidence fell below the earn-in floor"
    return f"{event_type}: {target}"


def _read_governance(base: Path) -> tuple[list[dict], str | None]:
    """Source: data/neuralweb/governance.jsonl (neuralweb.governance.v1).

    Fields: ts, event_type, target, authored_by, evidence, note, ...payload.
    article3_review rows get plain-word title translation.
    authority_lapse rows get plain-word title translation.
    """
    try:
        p = base / "data" / "neuralweb" / "governance.jsonl"
        if not p.exists():
            return [], None
        events: list[dict] = []
        for line in _tail_lines(p, 1000):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                event_type = row.get("event_type") or ""
                target = row.get("target") or ""
                # Compact summary of up to 3 payload scalars from evidence/before/after
                payload = {}
                for key in ("evidence", "before", "after"):
                    val = row.get(key)
                    if isinstance(val, dict):
                        payload.update(val)
                        break
                scalar_items = [
                    f"{k}={v}" for k, v in list(payload.items())[:3]
                    if isinstance(v, (str, int, float, bool)) or v is None
                ]
                detail = "; ".join(scalar_items) if scalar_items else (row.get("note") or "")
                events.append({
                    "ts": row.get("ts") or "",
                    "source": "governance",
                    "kind": event_type,
                    "title": _governance_title(event_type, target, row, payload),
                    "detail": str(detail)[:200],
                    "ref": None,
                    "url": None,
                    "status": "info",
                })
            except Exception:  # noqa: BLE001
                continue
        return events, None
    except Exception as exc:  # noqa: BLE001
        return [], f"governance reader error: {exc}"


def _read_genesis(base: Path) -> tuple[list[dict], str | None]:
    """Source: data/metabolism/charter_proposals/*.json (metabolism.charter_proposal.v1).

    Fields: ts, domain_id, label, cycle_id, ...
    """
    try:
        proposal_dir = base / "data" / "metabolism" / "charter_proposals"
        if not proposal_dir.exists():
            return [], None
        events: list[dict] = []
        for f in proposal_dir.glob("*.json"):
            try:
                raw = json.loads(f.read_text(encoding="utf-8"))
                domain_id = raw.get("domain_id") or f.stem
                label = raw.get("label") or domain_id
                events.append({
                    "ts": raw.get("ts") or "",
                    "source": "genesis",
                    "kind": "charter_proposal",
                    "title": f"New lobe proposed: {label}",
                    "detail": str(raw.get("rationale") or "")[:160],
                    "ref": None,
                    "url": None,
                    "status": "info",
                })
            except Exception:  # noqa: BLE001
                continue
        return events, None
    except Exception as exc:  # noqa: BLE001
        return [], f"genesis reader error: {exc}"


def _read_revamp(base: Path) -> tuple[list[dict], str | None]:
    """Source: data/metabolism/revamp_adjudications/*.json (metabolism.revamp_adjudication.v1).

    Fields: ts, lobe_id, recommendation (in_place_fix|revamp_new_charter|hold_operator|accruing).
    """
    try:
        revamp_dir = base / "data" / "metabolism" / "revamp_adjudications"
        if not revamp_dir.exists():
            return [], None
        events: list[dict] = []
        for f in revamp_dir.glob("*.json"):
            try:
                raw = json.loads(f.read_text(encoding="utf-8"))
                lobe = raw.get("lobe_id") or f.stem
                rec = raw.get("recommendation") or ""
                status = "warn" if rec == "hold_operator" else "info"
                events.append({
                    "ts": raw.get("ts") or "",
                    "source": "revamp",
                    "kind": rec,
                    "title": f"Charter revamp: {lobe} — {rec}",
                    "detail": str(raw.get("rationale") or "")[:160],
                    "ref": None,
                    "url": None,
                    "status": status,
                })
            except Exception:  # noqa: BLE001
                continue
        return events, None
    except Exception as exc:  # noqa: BLE001
        return [], f"revamp reader error: {exc}"


def _read_lifecycle(base: Path) -> tuple[list[dict], str | None]:
    """Source: data/metabolism/lifecycle_docket/*.json (metabolism.lifecycle_docket.v1).

    Fields: ts, lobe_id, from_state, to_state.
    """
    try:
        lc_dir = base / "data" / "metabolism" / "lifecycle_docket"
        if not lc_dir.exists():
            return [], None
        events: list[dict] = []
        for f in lc_dir.glob("*.json"):
            try:
                raw = json.loads(f.read_text(encoding="utf-8"))
                lobe = raw.get("lobe_id") or f.stem
                from_state = raw.get("from_state") or "?"
                to_state = raw.get("to_state") or "?"
                events.append({
                    "ts": raw.get("ts") or "",
                    "source": "lifecycle",
                    "kind": "state_transition",
                    "title": f"Lobe {lobe}: {from_state} → {to_state} proposed",
                    "detail": f"{from_state} → {to_state}",
                    "ref": None,
                    "url": None,
                    "status": "info",
                })
            except Exception:  # noqa: BLE001
                continue
        return events, None
    except Exception as exc:  # noqa: BLE001
        return [], f"lifecycle reader error: {exc}"


def _read_journal(base: Path) -> tuple[list[dict], str | None]:
    """Source: data/metabolism/journal/cycle-*.json (metabolism.journal.v1).

    Fields: cycle_id, stage, status (pending|running|done|failed|noop_paused), ts, stages{}.
    """
    try:
        journal_dir = base / "data" / "metabolism" / "journal"
        if not journal_dir.exists():
            return [], None
        events: list[dict] = []
        for f in journal_dir.glob("cycle-*.json"):
            try:
                raw = json.loads(f.read_text(encoding="utf-8"))
                cycle_id = raw.get("cycle_id") or f.stem
                status_val = raw.get("status") or "unknown"
                stage = raw.get("stage") or ""
                stages = raw.get("stages") or {}
                if status_val == "done":
                    status = "ok"
                elif status_val == "failed":
                    status = "bad"
                else:
                    status = "info"
                events.append({
                    "ts": raw.get("ts") or "",
                    "source": "journal",
                    "kind": status_val,
                    "title": f"Cycle {cycle_id} — {status_val}",
                    "detail": f"last stage: {stage}; {len(stages)} stages",
                    "ref": None,
                    "url": None,
                    "status": status,
                })
            except Exception:  # noqa: BLE001
                continue
        return events, None
    except Exception as exc:  # noqa: BLE001
        return [], f"journal reader error: {exc}"


def _read_freeze(base: Path) -> tuple[list[dict], str | None]:
    """Source: data/metabolism/journal/freeze_*.json (metabolism.dispatch_freeze.v1).

    Fields: ts, event, stage, earliest_reset, key_reset_hints.
    """
    try:
        journal_dir = base / "data" / "metabolism" / "journal"
        if not journal_dir.exists():
            return [], None
        events: list[dict] = []
        for f in journal_dir.glob("freeze_*.json"):
            try:
                raw = json.loads(f.read_text(encoding="utf-8"))
                earliest_reset = raw.get("earliest_reset") or ""
                events.append({
                    "ts": raw.get("ts") or "",
                    "source": "freeze",
                    "kind": raw.get("event") or "dispatch_freeze",
                    "title": "Dispatch freeze — all keys cooling",
                    "detail": str(earliest_reset),
                    "ref": None,
                    "url": None,
                    "status": "warn",
                })
            except Exception:  # noqa: BLE001
                continue
        return events, None
    except Exception as exc:  # noqa: BLE001
        return [], f"freeze reader error: {exc}"


def _read_verify(base: Path) -> tuple[list[dict], str | None]:
    """Source: data/metabolism/verify/*.json (metabolism.verify.v1).

    Fields: cycle_id, proposal_id, contract, realized, triage{action, classification}.
    """
    try:
        verify_dir = base / "data" / "metabolism" / "verify"
        if not verify_dir.exists():
            return [], None
        events: list[dict] = []
        for f in verify_dir.glob("*.json"):
            try:
                raw = json.loads(f.read_text(encoding="utf-8"))
                cycle_id = raw.get("cycle_id") or f.stem
                triage = raw.get("triage") or {}
                action = triage.get("action") or ""
                classification = triage.get("classification") or ""
                label = action or classification or "unknown"
                # action containing revert/park → warn, else info
                if "revert" in action or "park" in action:
                    status = "warn"
                else:
                    status = "info"
                events.append({
                    "ts": raw.get("ts") or "",
                    "source": "verify",
                    "kind": label,
                    "title": f"Verify {cycle_id}: {label}",
                    "detail": classification,
                    "ref": None,
                    "url": None,
                    "status": status,
                })
            except Exception:  # noqa: BLE001
                continue
        return events, None
    except Exception as exc:  # noqa: BLE001
        return [], f"verify reader error: {exc}"


def _read_lesson(base: Path) -> tuple[list[dict], str | None]:
    """Source: data/metabolism/lessons.jsonl (metabolism.lessons.v1).

    Fields: ts, cycle_id, proposal_id, lobe, verdict, what_worked, what_failed,
    construction.  Title = lesson text ~160 chars (what_failed is the primary
    text since lessons encode what went wrong and what to avoid repeating).
    """
    try:
        p = base / "data" / "metabolism" / "lessons.jsonl"
        if not p.exists():
            return [], None
        events: list[dict] = []
        for line in _tail_lines(p, 1000):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                # Build lesson text from the primary descriptive fields
                parts = []
                for field in ("what_failed", "what_worked", "construction"):
                    val = row.get(field) or ""
                    if val:
                        parts.append(val)
                text = " | ".join(parts) if parts else row.get("verdict") or "lesson"
                events.append({
                    "ts": row.get("ts") or "",
                    "source": "lesson",
                    "kind": row.get("verdict") or "lesson",
                    "title": text[:160],
                    "detail": f"lobe={row.get('lobe') or ''} verdict={row.get('verdict') or ''}",
                    "ref": None,
                    "url": None,
                    "status": "info",
                })
            except Exception:  # noqa: BLE001
                continue
        return events, None
    except Exception as exc:  # noqa: BLE001
        return [], f"lesson reader error: {exc}"


def _read_parked(base: Path) -> tuple[list[dict], str | None]:
    """Source: data/metabolism/claims.jsonl rows WHERE schema == 'metabolism.parked_construction.v1'.

    Fields: ts, proposal_id, parked_construction{lobe, kind, sensors}.
    Other schemas in claims.jsonl are ignored.
    """
    try:
        p = base / "data" / "metabolism" / "claims.jsonl"
        if not p.exists():
            return [], None
        events: list[dict] = []
        for line in _tail_lines(p, 1000):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                # Filter: only parked_construction schema rows
                if row.get("schema") != "metabolism.parked_construction.v1":
                    continue
                pc = row.get("parked_construction") or {}
                lobe = pc.get("lobe") or "unknown"
                kind = pc.get("kind") or "unknown"
                events.append({
                    "ts": row.get("ts") or "",
                    "source": "parked",
                    "kind": "parked_construction",
                    "title": f"Construction parked: {lobe}/{kind}",
                    "detail": f"proposal_id={row.get('proposal_id') or ''}",
                    "ref": None,
                    "url": None,
                    "status": "warn",
                })
            except Exception:  # noqa: BLE001
                continue
        return events, None
    except Exception as exc:  # noqa: BLE001
        return [], f"parked reader error: {exc}"


def _read_heartbeat(base: Path) -> tuple[list[dict], str | None]:
    """Source: data/metabolism/heartbeat.jsonl (metabolism.heartbeat.v1).

    Fields: ts, run_id, workflow, sha, phase, note.
    Read only the last 200 lines.
    """
    try:
        p = base / "data" / "metabolism" / "heartbeat.jsonl"
        if not p.exists():
            return [], None
        events: list[dict] = []
        for line in _tail_lines(p, 200):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                phase = row.get("phase") or "unknown"
                note = row.get("note") or "heartbeat"
                events.append({
                    "ts": row.get("ts") or "",
                    "source": "heartbeat",
                    "kind": phase,
                    "title": note,
                    "detail": f"run_id={row.get('run_id') or ''} workflow={row.get('workflow') or ''}",
                    "ref": None,
                    "url": None,
                    "status": "info",
                })
            except Exception:  # noqa: BLE001
                continue
        return events, None
    except Exception as exc:  # noqa: BLE001
        return [], f"heartbeat reader error: {exc}"


def _read_shadow(base: Path) -> tuple[list[dict], str | None]:
    """Source: data/metabolism/shadow/*/summary.json (metabolism.shadow_cycle.v1).

    Fields: cycle_id, ts, stages (dict), wall_seconds.
    """
    try:
        shadow_dir = base / "data" / "metabolism" / "shadow"
        if not shadow_dir.exists():
            return [], None
        events: list[dict] = []
        for summary_f in shadow_dir.glob("*/summary.json"):
            try:
                raw = json.loads(summary_f.read_text(encoding="utf-8"))
                cycle_id = raw.get("cycle_id") or summary_f.parent.name
                stages = raw.get("stages") or {}
                n_stages = len(stages) if isinstance(stages, dict) else 0
                events.append({
                    "ts": raw.get("ts") or "",
                    "source": "shadow",
                    "kind": "shadow_rehearsal",
                    "title": f"Shadow cycle {cycle_id} rehearsed — {n_stages} stages",
                    "detail": f"wall_seconds={raw.get('wall_seconds')}",
                    "ref": None,
                    "url": None,
                    "status": "info",
                })
            except Exception:  # noqa: BLE001
                continue
        return events, None
    except Exception as exc:  # noqa: BLE001
        return [], f"shadow reader error: {exc}"


# Map source name → reader function
_READERS: dict[str, Any] = {
    "pr": _read_pr,
    "audit": _read_audit,
    "revert": _read_revert,
    "immune": _read_immune,
    "governance": _read_governance,
    "genesis": _read_genesis,
    "revamp": _read_revamp,
    "lifecycle": _read_lifecycle,
    "journal": _read_journal,
    "freeze": _read_freeze,
    "verify": _read_verify,
    "lesson": _read_lesson,
    "parked": _read_parked,
    "heartbeat": _read_heartbeat,
    "shadow": _read_shadow,
}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def history(limit: int = 100, root: Path | None = None) -> dict:
    """Return the metabolism change-history dict.

    Parameters
    ----------
    limit : int
        Max events to return.  Clamped to [1, 500].
    root : Path | None
        Repo root for file I/O.  Uses ROOT from .paths when None, so all
        internal helpers receive the explicit base Path for test isolation.

    Returns
    -------
    dict with keys: events, sources, phase0, generated_at.
    Never raises.
    """
    try:
        limit = max(1, min(500, int(limit)))
        base: Path = Path(root) if root is not None else ROOT

        all_events: list[dict] = []
        sources: dict[str, dict] = {}

        for source_name in _ALL_SOURCES:
            reader = _READERS[source_name]
            try:
                evts, note = reader(base)
            except Exception as exc:  # noqa: BLE001
                evts, note = [], f"reader raised: {exc}"

            sources[source_name] = {
                "count": len(evts),
                "note": note,
            }
            all_events.extend(evts)

        # Sort newest-first; parse-failures sort last (they resolve to _EPOCH)
        def _sort_key(e: dict) -> datetime:
            return _parse_ts(e.get("ts"))

        all_events.sort(key=_sort_key, reverse=True)

        # phase0: True when no events come from sources outside {"heartbeat","shadow"}
        non_phase0_count = sum(
            1 for e in all_events
            if e.get("source") not in _PHASE0_EXCLUDE
        )
        phase0 = non_phase0_count == 0

        return {
            "events": all_events[:limit],
            "sources": sources,
            "phase0": phase0,
            "heartbeat_default_excluded": True,
            "generated_at": _now_iso(),
        }
    except Exception as exc:  # noqa: BLE001
        # Last-resort: always return the contract shape
        return {
            "events": [],
            "sources": {s: {"count": 0, "note": f"history() error: {exc}"} for s in _ALL_SOURCES},
            "phase0": True,
            "heartbeat_default_excluded": True,
            "generated_at": _now_iso(),
        }
