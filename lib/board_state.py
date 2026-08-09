"""W-L1 board-state view model — the surface's ONLY interpreter of the board-state contract.

WHAT THIS IS
------------
Breathing Platform W-L1 (research/BREATHING_PLATFORM_MASTERPLAN_BY_FABLE.md §3-2, §4)
publishes an EVENING board ~17:30 ET, hours ahead of the nightly board of record. The
reader therefore needs one thing the page has never had to say before: *which* board am I
looking at? The whole design of that answer is pinned in
``research/WL1_PROVISIONAL_BOARD_DESIGN_SPEC.md``; this module is the one place the
CONTRACT (§7) is interpreted, so every invariant has exactly one home and one test.

It is a pure function of a dict. It reads nothing off disk, writes nothing to ``data/``,
and cannot reorder, re-rank or re-admit a card — the surface DISPLAYS the delta, it never
computes it (constitution A7: the presentation tier never originates a signal).

THE THREE REFUSALS
------------------
1. ``rel`` is refused OUTRIGHT server-side.
   A nightly render, by construction, holds the board of record or last night's board —
   never the evening board's cards. So a server-rendered ``ahead`` stamp would be a stamp
   describing cards that are not on the page: the one failure mode that would actively lie
   to the reader, and a failure class this house has shipped before (frozen boards reading
   as fresh). The evening and last-confirmed stamps are painted by the live-plane client
   ONLY after it has proved the rendered cards are the ones the payload describes; see the
   W-L1 BOARD STATE block in ``templates/dashboard.html.j2``. Nothing here derives state
   from a clock, and neither does the client.

2. The receipt is refused unless the arithmetic reconciles.
   ``n_confirmed + n_adjusted + n_dropped == n_total``. If the numbers do not add up we
   emit NO receipt rather than a wrong one — and because the per-card ``Adjusted`` mark is
   fenced on the receipt in the template, the marks go with it. Published together or not
   at all.

3. A receipt is impossible after a night with no evening board.
   There was nothing to reconcile against, so ``note='confirmed'`` requires the counts to
   be present; a bare ``note='confirmed'`` with no counts yields no note.

The vocabulary fence (spec §0-7/§0-8) is a copy concern and lives in the template: every
string a reader can see is SSR-baked there in both languages. This module carries no
display copy at all except ``confirmed_label``, which is a DATE the producer pre-formats
in the card partial's own idiom (EN ``Aug 7`` / ZH ``08-07``) — and it must carry both
languages or the ``behind`` state is dropped, because the date is what makes a stale board
impossible to mistake for a fresh one.
"""
from __future__ import annotations

from typing import Any

#: Position vs. the nightly board of record. ``None`` (attribute absent) is the third
#: state and it is load-bearing: the board IS the record, so no stamp is shown at all.
REL_VALUES = ("ahead", "behind")

#: Which note-line content renders. Mutually exclusive — never two at once.
NOTE_VALUES = ("ahead", "confirmed", "behind", "closed")

#: The Tier-2 receipt names the dropped tickers (spec §6.2). A runaway list would turn a
#: popover into a wall, and a board that dropped this many names has a bigger problem than
#: its footnote, so the list is capped and the cap is deliberate rather than incidental.
MAX_DROPPED = 12


def _int(value: Any) -> "int | None":
    """A non-negative int, or ``None``. ``True`` is not 1 here — bools are not counts."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if value >= 0 else None


def _label(value: Any) -> "dict | None":
    """Normalise ``confirmed_label`` to ``{'en': str, 'zh': str}`` or ``None``.

    Accepts the pre-formatted pair, or a bare string when the producer's EN and ZH date
    idioms coincide. Anything else — including a half-filled pair — is dropped, because a
    stamp that reads ``Last confirmed ·`` with nothing after it is worse than no stamp.
    """
    if isinstance(value, str):
        text = value.strip()
        return {"en": text, "zh": text} if text else None
    if isinstance(value, dict):
        en = str(value.get("en") or "").strip()
        zh = str(value.get("zh") or "").strip()
        return {"en": en, "zh": zh} if (en and zh) else None
    return None


def _dropped(value: Any) -> list:
    """Ticker list for the Tier-2 receipt: strings only, order preserved, deduped, capped."""
    if not isinstance(value, (list, tuple)):
        return []
    out: list = []
    seen = set()
    for item in value:
        if not isinstance(item, str):
            continue
        ticker = item.strip()
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)
        out.append(ticker)
        if len(out) >= MAX_DROPPED:
            break
    return out


def board_state_view(raw: Any, *, server_side: bool = True) -> dict:
    """Sanitize the raw board-state contract into the ``_bs`` the template consumes.

    Returns ``{}`` for anything it will not vouch for — absent payload, unknown enum,
    counts that do not reconcile, a ``behind`` state with no date. ``{}`` renders no
    attribute, no stamp, and an empty (but height-reserved) note slot, which is exactly
    the page as it looks today.

    ``server_side=False`` exists for the client-contract tests and for any future
    non-render consumer; it relaxes only refusal #1, never the arithmetic.
    """
    if not isinstance(raw, dict):
        return {}

    view: dict = {}

    rel = raw.get("rel")
    if rel in REL_VALUES and not server_side:
        label = _label(raw.get("confirmed_label"))
        # The date is MANDATORY on `behind` (spec §3 state 3) — it is the whole reason a
        # stale board cannot be mistaken for a fresh one.
        if rel == "ahead" or label:
            view["rel"] = rel
            if label:
                view["confirmed_label"] = label

    note = raw.get("note")
    if note in NOTE_VALUES:
        if note == "confirmed":
            n_total = _int(raw.get("n_total"))
            n_confirmed = _int(raw.get("n_confirmed"))
            n_adjusted = _int(raw.get("n_adjusted"))
            n_dropped = _int(raw.get("n_dropped"))
            counts = (n_total, n_confirmed, n_adjusted, n_dropped)
            reconciles = (
                None not in counts
                and n_total > 0
                and n_confirmed + n_adjusted + n_dropped == n_total
            )
            if reconciles:
                view["note"] = "confirmed"
                view["n_total"] = n_total
                view["n_confirmed"] = n_confirmed
                view["n_adjusted"] = n_adjusted
                view["n_dropped"] = n_dropped
                view["dropped"] = _dropped(raw.get("dropped"))
        elif not server_side:
            # ahead / behind / closed are live-plane states: the nightly render cannot know
            # them and must not guess. Same reason as refusal #1.
            view["note"] = note

    # A label with no `behind` stamp to sit in is dead weight; carry it only when used.
    if view.get("rel") != "behind":
        view.pop("confirmed_label", None)

    return view
