"""engine.marketing.ad_review — the human gate every ad passes before it can run.

Operator ruling 2026-07-27: **an ad is reviewed by a person before it is eligible
for split testing.** Autonomous testing is earned later, once the system has been
taught enough taste to hold quality on its own — it is not the starting state.

This module is the enforcement, not the convention. `ad_arena` cannot construct a
live arena without the approved set this produces, so "I forgot to get it
reviewed" is a raise rather than a silent live ad. That failure already happened
once: a hero test went live on un-reviewed copy because nothing structural
stopped it.

**The rejection note is the point, not the paperwork.** A `no` with a reason is
the only training signal the system gets about taste, and the ladder the operator
described — hand-gated now, autonomous later — runs on that corpus. So a
rejection without a reason is refused: it teaches nothing and cannot be argued
with later.

Reviews are a forward-only ledger, separate from the creatives themselves. The
creative row stays immutable and the decision is its own fact, so the history
reads "who approved what, when, and why" rather than a mutated status field with
no author.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .ledgers import append_jsonl, read_jsonl

log = logging.getLogger(__name__)

REVIEWS_FILE = "reviews.jsonl"
SCHEMA = "marketing.ad_review/v1"

APPROVED = "approved"
REJECTED = "rejected"
PENDING = "pending"
VERDICTS: tuple[str, ...] = (APPROVED, REJECTED)


class UnapprovedCreative(PermissionError):
    """Raised when an ad would run without a human having approved it."""


class MissingRejectionReason(ValueError):
    """Raised on a rejection with no reason — a `no` that teaches nothing."""


# ─────────────────────────────────────────────────────────────────────────────
# Ledger
# ─────────────────────────────────────────────────────────────────────────────

def _dir(root: Path | str | None = None) -> Path:
    from .ad_arena import DEFAULT_LEDGER_DIR  # noqa: PLC0415 — avoids a cycle
    return (Path(root) if root is not None else Path(".")) / DEFAULT_LEDGER_DIR


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class Review:
    creative_id: str
    verdict: str                    # approved | rejected
    reviewer: str
    note: str = ""
    at: str = ""

    def as_dict(self) -> dict:
        return {
            "schema": SCHEMA,
            "creative_id": self.creative_id,
            "verdict": self.verdict,
            "reviewer": self.reviewer,
            "note": self.note,
            "at": self.at or _now(),
        }


def record(
    creative_id: str, verdict: str, *, reviewer: str, note: str = "",
    root: Path | str | None = None, at: str | None = None,
) -> Review:
    """Append one review decision.  Raises on a rejection with no reason.

    A later decision supersedes an earlier one — an operator may approve
    something they first rejected, and the ledger keeps both so the change of
    mind is visible rather than overwritten.
    """
    v = str(verdict).strip().lower()
    if v not in VERDICTS:
        raise ValueError(f"verdict must be one of {VERDICTS}, got {verdict!r}")
    if not str(reviewer).strip():
        raise ValueError("a review needs a reviewer — an anonymous approval is not a gate")
    note = str(note or "").strip()
    if v == REJECTED and not note:
        raise MissingRejectionReason(
            f"rejecting {creative_id} needs a reason. The reason IS the training "
            f"signal — a bare 'no' teaches the system nothing and cannot be "
            f"argued with when the same ad comes back."
        )
    r = Review(creative_id=str(creative_id), verdict=v, reviewer=str(reviewer).strip(),
               note=note, at=at or _now())
    append_jsonl(_dir(root) / REVIEWS_FILE, r.as_dict())
    return r


def load_reviews(*, root: Path | str | None = None) -> list[dict]:
    """Every decision, oldest first — the full audit trail."""
    return read_jsonl(_dir(root) / REVIEWS_FILE)


def latest_by_creative(*, root: Path | str | None = None) -> dict[str, dict]:
    """The decision that currently stands for each creative."""
    out: dict[str, dict] = {}
    for row in load_reviews(root=root):
        cid = row.get("creative_id")
        if cid:
            out[str(cid)] = row
    return out


def state(creative_id: str, *, root: Path | str | None = None) -> str:
    """`approved`, `rejected`, or `pending` for one creative."""
    row = latest_by_creative(root=root).get(str(creative_id))
    return str(row.get("verdict")) if row else PENDING


def approved_ids(*, root: Path | str | None = None) -> set[str]:
    """The set `ad_arena` requires before it will build anything live."""
    return {cid for cid, row in latest_by_creative(root=root).items()
            if row.get("verdict") == APPROVED}


# ─────────────────────────────────────────────────────────────────────────────
# The gate
# ─────────────────────────────────────────────────────────────────────────────

def assert_approved(creative_ids: Iterable[str], approvals: Iterable[str] | None) -> None:
    """Raise unless EVERY creative has been approved by a person.

    `approvals=None` is not "skip the check" — it is the absence of a review pass,
    and it raises. There is deliberately no bypass argument: the way to run an ad
    is to have it approved.
    """
    wanted = [str(c) for c in creative_ids]
    have = set(approvals or ())
    missing = [c for c in wanted if c not in have]
    if missing:
        raise UnapprovedCreative(
            f"{len(missing)} of {len(wanted)} ads have not been approved by a person: "
            f"{missing}. Operator ruling 2026-07-27 — an ad is reviewed before it is "
            f"eligible for split testing. Record a decision with "
            f"engine.marketing.ad_review.record(...)."
        )


# ─────────────────────────────────────────────────────────────────────────────
# Queue + taste corpus
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Queue:
    pending: list[dict] = field(default_factory=list)
    approved: list[dict] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"pending": list(self.pending), "approved": list(self.approved),
                "rejected": list(self.rejected),
                "counts": {"pending": len(self.pending), "approved": len(self.approved),
                           "rejected": len(self.rejected)}}


def queue(creatives: dict[str, dict], *, root: Path | str | None = None) -> Queue:
    """Split creatives into what still needs a human, and what has had one."""
    decisions = latest_by_creative(root=root)
    q = Queue()
    for cid, c in sorted(creatives.items()):
        row = decisions.get(cid)
        entry = dict(c)
        entry["review"] = row
        if row is None:
            q.pending.append(entry)
        elif row.get("verdict") == APPROVED:
            q.approved.append(entry)
        else:
            q.rejected.append(entry)
    return q


def taste_notes(*, root: Path | str | None = None) -> list[dict[str, Any]]:
    """Every rejection reason, newest first — what the operator has taught so far.

    This is the corpus the autonomy ladder runs on. Read it before generating the
    next batch: a system that keeps proposing what has already been rejected has
    not learned anything, it has only been outvoted repeatedly.
    """
    notes = [r for r in load_reviews(root=root)
             if r.get("verdict") == REJECTED and r.get("note")]
    return list(reversed(notes))
