"""The probation queue — proposals waiting on a curated ratification act (W3A §4).

NOTHING IN HERE IS PRODUCTION VOCABULARY. A proposal is a machine saying "these two
things look related" or "this key may have been renamed"; the graph build ignores every
row whose ``status`` is not ``ratified``, and W3A ratifies nothing. That is the whole
point: G0.13 forbids promoting a string or overlap statistic into an edge, so the
statistic lands here with its evidence and a human decides later — or never.

The file is APPEND-ONLY JSONL and rows are keep-FIRST on ``proposal_id``, which is a
deterministic hash of the proposal's SUBJECT. Re-running a proposer therefore re-proposes
nothing: the same finding on the same subject is the same row, and a curator's decision
on it is never overwritten by a later run that happened to see the same overlap again.

Ratification is a CURATED act. This module deliberately ships no ``ratify()``: the way a
row becomes ratified is a human editing it (or a delegated curation session doing so
under its own receipt), and a helper that flipped the field would be the exact
auto-promotion path the queue exists to prevent.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

#: What a proposal can ask for. ``identity_continuity`` (a suspected ticker rename) and
#: ``key_rename`` (a suspected source-key rename) come from the refresh path; the rest
#: from the coverage-gap and overlap diagnostics.
PROPOSAL_KINDS: frozenset[str] = frozenset({
    "new_theme", "merge", "split", "mapping", "key_rename", "identity_continuity",
})

PROPOSED_BY: frozenset[str] = frozenset({
    "coverage_gap", "overlap_stats", "refresh_identity", "llm_proposed",
})

STATUSES: frozenset[str] = frozenset({"proposed", "ratified", "rejected"})

ROW_FIELDS: tuple[str, ...] = (
    "proposal_id", "kind", "subject", "evidence", "evidence_refs", "proposed_by",
    "created", "status", "ratified_by", "note",
)


def utc_now_stamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z")


def proposal_id(kind: str, subject: dict) -> str:
    """Deterministic id from (kind, subject). The same finding is the same row."""
    payload = json.dumps({"kind": str(kind), "subject": subject},
                         ensure_ascii=False, sort_keys=True, default=str)
    return "prop:" + hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def make_proposal(*, kind: str, subject: dict, evidence: dict | None = None,
                  evidence_refs: list[str] | None = None, proposed_by: str,
                  created: str | None = None, note: str | None = None) -> dict:
    """A well-formed, UNRATIFIED proposal row. Refuses an unknown kind or proposer."""
    if kind not in PROPOSAL_KINDS:
        raise ValueError(f"unknown proposal kind {kind!r}; known: {sorted(PROPOSAL_KINDS)}")
    if proposed_by not in PROPOSED_BY:
        raise ValueError(
            f"unknown proposer {proposed_by!r}; known: {sorted(PROPOSED_BY)} — a "
            f"proposal whose origin is not named cannot be audited later")
    return {
        "proposal_id": proposal_id(kind, subject),
        "kind": kind,
        "subject": dict(subject),
        "evidence": dict(evidence or {}),
        "evidence_refs": list(evidence_refs or []),
        "proposed_by": proposed_by,
        "created": created or utc_now_stamp(),
        # Written as PROPOSED, always. A proposer cannot mint a ratified row.
        "status": "proposed",
        "ratified_by": None,
        "note": note,
    }


def validate(row: dict) -> list[str]:
    """Structural problems with one row, empty when it is well-formed."""
    out: list[str] = []
    for f in ("proposal_id", "kind", "proposed_by", "created", "status"):
        if not str(row.get(f) or "").strip():
            out.append(f"missing {f}")
    if row.get("kind") and row["kind"] not in PROPOSAL_KINDS:
        out.append(f"kind {row['kind']!r} outside {sorted(PROPOSAL_KINDS)}")
    if row.get("proposed_by") and row["proposed_by"] not in PROPOSED_BY:
        out.append(f"proposed_by {row['proposed_by']!r} outside {sorted(PROPOSED_BY)}")
    if row.get("status") and row["status"] not in STATUSES:
        out.append(f"status {row['status']!r} outside {sorted(STATUSES)}")
    if row.get("status") == "ratified" and not str(row.get("ratified_by") or "").strip():
        out.append("status=ratified with no ratified_by — ratification names its author")
    if row.get("status") != "ratified" and str(row.get("ratified_by") or "").strip():
        out.append("ratified_by set on a row that is not ratified")
    return out


def read_proposals(path: Path) -> list[dict]:
    """Every row on disk, oldest first. Unparseable lines are reported, never fatal."""
    if not path.exists():
        return []
    out: list[dict] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except Exception:  # noqa: BLE001
            log.warning("theme_graph.probation: %s line %d unparseable — skipped",
                        path.name, lineno)
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def ratified(rows: list[dict]) -> list[dict]:
    """The rows a build may act on. Everything else is a suggestion, not a fact."""
    return [r for r in rows if str(r.get("status")) == "ratified"
            and str(r.get("ratified_by") or "").strip()]


def append_proposals(rows: list[dict], path: Path) -> tuple[int, int]:
    """Append new rows keep-FIRST on ``proposal_id``. Returns ``(appended, skipped)``.

    Never rewrites the file: existing bytes stay exactly as they are, so a curator's
    edits to earlier rows survive every later proposer run.
    """
    bad = [(r.get("proposal_id"), errs) for r in rows if (errs := validate(r))]
    if bad:
        raise ValueError(f"refusing to append malformed proposals: {bad[:3]}")
    known = {str(r.get("proposal_id")) for r in read_proposals(path)}
    fresh = [r for r in rows if str(r.get("proposal_id")) not in known]
    skipped = len(rows) - len(fresh)
    if not fresh:
        return 0, skipped
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for row in fresh:
            fh.write(json.dumps({k: row.get(k) for k in ROW_FIELDS},
                                ensure_ascii=False, sort_keys=True) + "\n")
    return len(fresh), skipped
