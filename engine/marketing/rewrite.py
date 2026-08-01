"""engine.marketing.rewrite — replace a queued post with rewritten copy, atomically.

WHY THIS EXISTS
A rewrite is not a new post. It is the SAME post said better, and the queue may
never hold both versions. The X Growth audit of 2026-07-25..31 found the opposite
in production: the `claude_rewrite` lane APPENDED its rewritten items at the
original's slot instead of superseding it, so cici's 2026-07-28 17:00 slot held
THREE near-identical $FDS posts (one `content_studio` original plus two rewrites,
all three carrying the same `source.plan_item_id`), and the week ran 46
same-account-same-minute collisions. A reader following that account would have
seen the same paragraph three times inside one minute.

TWO STRUCTURAL RULES, BOTH ENFORCED HERE

1. QUARANTINE FIRST, ENQUEUE SECOND. This is not stylistic ordering, it is the
   only order that WORKS. `outbox.enqueue` rejects near-duplicates against a
   7-day same-account corpus at token-Jaccard >= 0.7 — and a rewrite of a post is
   by construction a near-duplicate of that post. `scripts/marketing_requeue_stale_copy`
   enqueued first and its own log line admitted the outcome ("enqueue returned
   %r — original left queued"), which means every light rewrite it attempted was
   silently refused and the stale copy stayed queued. `_enqueue_ctx` excludes
   DEAD ids (quarantined/failed/recalled) from that corpus, so retiring the
   original is precisely what frees its own replacement to land. It is also why
   an ad-hoc lane that "just appends the row" bypasses every guard in the file:
   the guards were never the problem, the ordering was.

2. NEVER LEAVE BOTH LIVE. If the enqueue fails after the original is retired,
   the slot is empty and the failure is LOUD (return code + ::warning), because
   `quarantined` is terminal in `outbox.TRANSITIONS` and there is no rollback.
   That trade is deliberate: an empty slot is a missing post, while two live
   versions of one post is a visible, permanent embarrassment on the account,
   and the nightly re-emits the slot anyway.

IDEMPOTENCE FALLS OUT OF THE SAME RULE. Re-running a rewrite finds the original
already terminal and refuses ("original_not_live"), so a lane that fires twice
adds zero items the second time instead of a second copy.
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

#: Statuses a rewrite may not touch. The post is gone, in flight, or was killed
#: on purpose. `recalled` is terminal by the outbox's own law: the operator
#: pulled that copy, and its replacement is a NEW item under a new plan slot,
#: not a second attempt at a dead one.
TERMINAL_STATUSES: frozenset[str] = frozenset(
    {"posted", "posting", "quarantined", "failed", "recalled"}
)


def apply_rewrite(
    original_id: str,
    new_item: dict,
    *,
    root: Path | str | None = None,
    actor: str = "rewrite",
    note: str | None = None,
    max_per_account_day: int | None = None,
    cfg: dict | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Supersede *original_id* with *new_item* as ONE operation.

    Returns ``{"ok": bool, "outcome": str, "original_id": str,
    "new_id": str|None, "enqueue": str|None}`` and never raises. ``outcome`` is
    one of:

      ``superseded``        — original quarantined, replacement queued (ok)
      ``unchanged``         — the rewrite is byte-identical copy; nothing done
      ``original_unknown``  — no such item
      ``original_not_live`` — already terminal (also the second-run no-op)
      ``invalid:<msg>``     — the replacement is not a valid outbox item
      ``quarantine_failed`` — the ledger refused the transition; nothing queued
      ``enqueue_failed:<code>`` — original retired, replacement refused: THE
                                  SLOT IS NOW EMPTY and the caller must know

    The replacement records ``source.supersedes`` so the queue carries its own
    lineage — an item whose predecessor is unnamed is one nobody can audit.
    """
    from engine.marketing.outbox import (  # noqa: PLC0415 — lazy: heavy module
        effective_cap, enqueue, fold_state, transition, validate_item,
    )

    out: dict[str, Any] = {
        "ok": False, "outcome": "", "original_id": str(original_id),
        "new_id": (new_item or {}).get("id"), "enqueue": None,
    }
    try:
        state = fold_state(root)
        original = (state.get("items") or {}).get(original_id)
        if original is None:
            out["outcome"] = "original_unknown"
            log.warning("rewrite: unknown original %r — nothing done", original_id)
            return out

        status = str((state.get("status") or {}).get(original_id) or "queued")
        if status in TERMINAL_STATUSES:
            # Also the idempotence path: a second run of the same rewrite lands
            # here and adds nothing.
            out["outcome"] = "original_not_live"
            log.info("rewrite: %s is %s — leaving it alone", original_id, status)
            return out

        if str(new_item.get("text") or "") == str(original.get("text") or ""):
            # Nothing to say differently. Retiring a good post to re-queue the
            # same words would spend a slot and a ledger row for no change.
            out["ok"] = True
            out["outcome"] = "unchanged"
            return out

        errors = validate_item(new_item)
        if errors:
            # Checked BEFORE the quarantine so an unusable replacement cannot
            # cost the day its original.
            out["outcome"] = f"invalid:{errors[0]}"
            log.warning("rewrite: replacement for %s is invalid (%s) — original "
                        "left queued", original_id, errors[0])
            return out

        src = new_item.get("source")
        if not isinstance(src, dict):
            src = {}
            new_item["source"] = src
        src["supersedes"] = str(original_id)

        reason = note or f"superseded by {new_item.get('id')} (rewritten copy)"
        if not transition(original_id, "quarantined", actor=actor, root=root,
                          note=reason, now=now, _state=state):
            out["outcome"] = "quarantine_failed"
            log.warning("rewrite: could not quarantine %s — replacement NOT "
                        "queued (never leave both live)", original_id)
            return out

        cap = (max_per_account_day if max_per_account_day is not None
               else effective_cap(cfg or {}))
        code = enqueue(new_item, root=root, max_per_account_day=cap, cfg=cfg)
        out["enqueue"] = code
        if code != "queued":
            out["outcome"] = f"enqueue_failed:{code}"
            # Bare print at line start with flush — a "::warning" behind this
            # module's log formatter is not a line start and GitHub drops it
            # silently (tests/test_gh_annotation_line_start.py).
            print(f"::warning title=marketing_rewrite_slot_lost::Rewrite of "
                  f"{original_id} retired the original but the replacement was "
                  f"refused ({code}); that slot is now EMPTY. The original is "
                  f"terminal and cannot be re-armed — re-emit the slot.",
                  flush=True)
            return out

        out["ok"] = True
        out["outcome"] = "superseded"
        log.info("rewrite: %s superseded by %s", original_id, new_item.get("id"))
        return out
    except Exception as exc:  # noqa: BLE001 — a rewrite must never take a lane down
        log.warning("rewrite: unexpected error on %s: %s", original_id, exc)
        out["outcome"] = f"error:{exc}"
        return out


def live_items_for(
    *,
    root: Path | str | None = None,
    account: str,
    as_of: str,
    provenance: str,
) -> list[dict]:
    """Every still-live (non-terminal) item a lane already has for one day.

    The read half of the idempotence contract: a lane asks "did I already build
    this day?" before it builds it again. Shared here rather than in each lane so
    "live" means the same thing everywhere — folded ledger status, not the
    `status` field frozen on the row at creation time.
    """
    from engine.marketing.outbox import fold_state  # noqa: PLC0415

    try:
        state = fold_state(root)
        status = state.get("status") or {}
        return [
            it for iid, it in (state.get("items") or {}).items()
            if str(it.get("account") or "") == account
            and str(it.get("as_of") or "") == as_of
            and str(it.get("provenance") or "") == provenance
            and str(status.get(iid) or "queued") not in TERMINAL_STATUSES
        ]
    except Exception as exc:  # noqa: BLE001
        log.warning("rewrite.live_items_for failed: %s", exc)
        return []
