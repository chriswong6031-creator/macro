#!/usr/bin/env python3
"""scripts/marketing_stale_purge.py — retire an outbox backlog built by an outage.

WHY THIS EXISTS
The Buffer subscription lapsed around 2026-08-05. From 2026-08-06T00:42Z every
publish attempt came back 429 with a sixteen-day ``Retry-After``, and the
publisher's rate-limit branch — which is right about a five-minute quota blip and
wrong about a fortnight — walked each refused item straight back to ``approved``
and picked it up again on the next 30-minute sweep. Two days later the queue held
~49 undeliverable posts, most of them written on 08-05..08-07, all of them still
armed. The last post that actually shipped was 2026-08-05T20:46:42Z.

Nothing in that pile is publishable. A market post is a claim about a tape, and
these describe sessions that have closed. When the plan renews they must not fire
as a two-day burst of history dressed as news, so they are retired BEFORE the
switch flips rather than trusted to a gate that might not catch them.

The standing reapers (``outbox.expire_stale_planned`` at 36h,
``outbox.expire_stale_wire`` at 3h/12h by kind) cover this shape going forward.
This script is the one-off broom for the backlog that accumulated while neither
of them was reached, and it is written to be re-runnable rather than clever:
running it twice changes nothing the second time.

WHAT IT DOES
Folds the outbox through the outbox module's own reader, selects items whose
EFFECTIVE status is ``queued`` or ``approved`` and whose creation stamp predates
``--cutoff``, and transitions each to ``quarantined`` through
``outbox.transition``. Never hand-writes a ledger row: the fold is the only thing
that knows an item's real status, and a hand-appended row that disagrees with it
is skipped on the next read with a warning nobody sees.

``quarantined`` is terminal and already reachable from both live statuses, which
is exactly why the standing reapers use it too — see the note above
``expire_stale_planned``: TRANSITIONS is a safety contract, and widening it for
housekeeping costs more than it buys. The note travels with the row, so the
admin's quarantine view says why in words.

    # what it would retire, touching nothing
    python3 -m scripts.marketing_stale_purge --cutoff 2026-08-08T00:00:00Z

    # write the ledger
    python3 -m scripts.marketing_stale_purge --cutoff 2026-08-08T00:00:00Z --live

The ledger rows this writes must be COMMITTED for the publisher to see them.
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

log = logging.getLogger("marketing_stale_purge")

#: The statuses a purge may touch. Everything else is either already terminal
#: (posted/quarantined/recalled/failed) or in flight (posting), and a broom that
#: reaches into either is not a broom.
#:
#: `failed` is deliberately absent even though it is re-armable: an item sits
#: there because something went wrong with THAT post, and a bulk sweep that
#: buries it under "the backlog was stale" erases the only record of the reason.
PURGEABLE: frozenset[str] = frozenset({"queued", "approved"})

#: The note every row this script writes carries. One literal so a re-run, a
#: grep, and the admin panel all agree on what happened. Plain words on purpose —
#: this string is read by a person in the quarantine view.
DEFAULT_NOTE = ("stale_purge_2026-08-08: Buffer-outage backlog; event no longer "
                "fresh")


def _parse_iso(raw: str | None) -> datetime | None:
    """An iso8601 stamp as an aware UTC datetime, or None when nothing parses.

    None means UNKNOWN, never "old": an item whose creation stamp cannot be read
    is left exactly where it is. A malformed field must not be the reason a post
    is destroyed — the same rule ``outbox._wire_item_born_at`` states.
    """
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _created_at(item: dict) -> datetime | None:
    """When this item was written. ``created_at``, else ``as_of`` at 00:00Z.

    NOT ``scheduled_at``: the fast lanes all enqueue the literal string
    "immediate", which is exactly why ``expire_stale_planned`` — whose age comes
    from ``scheduled_at`` — could never retire one of them.
    """
    born = _parse_iso(item.get("created_at"))
    if born is not None:
        return born
    as_of = str(item.get("as_of") or "").strip()
    if as_of:
        return _parse_iso(f"{as_of[:10]}T00:00:00Z")
    return None


def select_stale(state: dict, cutoff: datetime) -> list[dict]:
    """The items a purge at ``cutoff`` would retire, in ledger order.

    Pure: reads a folded snapshot, writes nothing. Split out so the dry run and
    the live run cannot disagree about the selection — they call this, once each.
    """
    items = state.get("items") or {}
    statuses = state.get("status") or {}
    out: list[dict] = []
    for iid in state.get("order") or list(items):
        item = items.get(iid)
        if not isinstance(item, dict):
            continue
        if str(statuses.get(iid) or "") not in PURGEABLE:
            continue
        born = _created_at(item)
        if born is None or born >= cutoff:
            continue
        out.append(item)
    return out


def _summarize(selected: list[dict]) -> dict[tuple[str, str], int]:
    """Counts by (account, kind) — what an operator actually wants to read."""
    counts: dict[tuple[str, str], int] = {}
    for item in selected:
        key = (str(item.get("account") or "?"), str(item.get("kind") or "?"))
        counts[key] = counts.get(key, 0) + 1
    return counts


def purge(root: Path | str | None, cutoff: datetime, *, live: bool,
          note: str = DEFAULT_NOTE, actor: str = "stale_purge",
          now: datetime | None = None) -> dict:
    """Retire everything ``select_stale`` picks. Returns a summary dict.

    IDEMPOTENT BY CONSTRUCTION, not by a marker file: a purged item's effective
    status is ``quarantined``, which is not in :data:`PURGEABLE`, so the second
    run selects nothing. That is also why the selection reads the FOLD rather
    than the raw items file — ``items.jsonl`` still says "queued" forever.
    """
    from engine.marketing import outbox as _outbox  # noqa: PLC0415

    state = _outbox.fold_state(root)
    selected = select_stale(state, cutoff)
    counts = _summarize(selected)
    out: dict = {
        "selected": len(selected),
        "purged": 0,
        "refused": [],
        "by_account_kind": {f"{a}/{k}": n for (a, k), n in sorted(counts.items())},
        "live": bool(live),
    }
    if not live:
        return out

    for item in selected:
        iid = str(item.get("id") or "")
        # One fold, sequential writes through the canonical writer: `_state`
        # keeps the snapshot current so N transitions fold once, not N times.
        if _outbox.transition(iid, "quarantined", actor=actor, root=root,
                              note=note, now=now, _state=state):
            out["purged"] += 1
        else:
            out["refused"].append(iid)
    return out


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cutoff", required=True,
                    help="iso8601 UTC; items created BEFORE this are retired "
                         "(e.g. 2026-08-08T00:00:00Z)")
    ap.add_argument("--root", default=None,
                    help="repo root holding data/marketing/outbox "
                         "(default: this repo)")
    ap.add_argument("--note", default=DEFAULT_NOTE,
                    help="ledger note written on every retired row")
    ap.add_argument("--live", action="store_true",
                    help="write the ledger (default: dry run, no writes)")
    args = ap.parse_args(argv)

    cutoff = _parse_iso(args.cutoff)
    if cutoff is None:
        log.error("--cutoff %r is not an iso8601 stamp", args.cutoff)
        return 2

    root = Path(args.root).resolve() if args.root else ROOT
    result = purge(root, cutoff, live=bool(args.live), note=args.note)

    verb = "RETIRED" if args.live else "WOULD RETIRE"
    log.info("%s %d item(s) created before %s", verb, result["selected"],
             cutoff.strftime("%Y-%m-%dT%H:%M:%SZ"))
    for key, n in sorted(result["by_account_kind"].items()):
        log.info("  %-28s %d", key, n)
    if result["refused"]:
        log.warning("%d item(s) refused the transition (illegal or unknown): %s",
                    len(result["refused"]), ", ".join(result["refused"][:10]))
    if not args.live:
        log.info("dry run — pass --live to write the ledger")
    else:
        log.info("purged %d/%d. COMMIT data/marketing/outbox/ for the publisher "
                 "to see this.", result["purged"], result["selected"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
