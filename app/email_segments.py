"""app/email_segments.py — the ONE definition of who is in an email segment (SEE W4).

Two planes need the same answer to "who is in segment X", and they speak different
languages:

  * ``admin/email_center.py`` runs Supabase **Management-API SQL** (the operator PAT) to
    build the roster, the per-segment counts and the CSV export;
  * ``app/marketing_emails.py`` runs inside macro-api with a **service-role** key and no
    PAT, so it assembles the same roster from the GoTrue admin list + PostgREST and
    filters it in Python.

Two hand-written copies of one predicate is how a compliance gate rots: the export would
say 412 people and the send would reach 419, and nobody would notice until seven of the
extra were the seven who had unsubscribed. So every segment is declared ONCE here as a
PAIR — a SQL ``WHERE`` fragment and a Python predicate over the same normalised row — and
``tests/test_email_segments.py`` asserts the pair agrees on a full grid of rows.

G3/G4 — ``marketing_eligible`` excludes by CONSTRUCTION
-------------------------------------------------------
Its membership rule is not "list everyone, then remember to filter the suppressed out".
The exclusion *is* the rule, in both renderings: an address carried by
``email_suppression``, or a user whose ``email_prefs.marketing_opt_out`` is true, is never
a member of the set, so no caller can forget to apply it and no new caller can
accidentally opt out of applying it.

That is the plan. The DECISION still happens at send time: ``mailer.send(cls='marketing')``
re-reads suppression and the opt-out for every single recipient and is fail-closed on the
lookup itself. A segment computed at 09:00 and drained at 09:40 cannot mail someone who
unsubscribed at 09:20, because the segment never gets the last word.

The base
--------
:data:`BASE_SQL` / :func:`base_match` gate EVERY segment, including ``all``: an account
that is soft-deleted, banned, anonymous, or has no address on file is not a person we can
or may mail. This mirrors ``admin/users.py::_ACTIVE`` (the Users page's own definition of
a real account) and adds the mailability clause; ``tests/test_email_segments.py`` asserts
the mirror still holds, so a change to one is not silently a divergence from the other.

The SQL fragments are static text — no value from an operator, a query string or a
database row is ever interpolated into them. A caller resolves a segment by KEY, and an
unknown key raises rather than reaching SQL (:func:`get`).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

# --------------------------------------------------------------------------- #
# Suppression vocabulary — shared by BOTH writers, for the same reason the segments are
# --------------------------------------------------------------------------- #
#: Reasons that record what the ADDRESS did, not what its owner chose. A hard bounce means
#: the address rejected us; a complaint means someone pressed "spam". Neither is a
#: preference anybody may overwrite with a weaker one, and neither is liftable from a link
#: or from the console — see ``admin/email_center.py::suppress`` (SQL writer) and
#: ``app/unsubscribe.py::_suppress`` (PostgREST writer), which BOTH consult this tuple.
#:
#: It lives here rather than in either writer because two hand-written copies of one
#: compliance rule is exactly the rot this module exists to prevent: the console proved
#: that by documenting "a complaint is not removable" three times while allowing a
#: re-suppression as ``manual`` to overwrite the reason and unlock the removal.
HARD_REASONS = ("bounce", "complaint")

#: The reasons a person (or an operator) MAY lift: everything that is not a hard reason.
SOFT_REASONS = ("unsubscribe", "manual")

REASONS = SOFT_REASONS + HARD_REASONS

#: The hard reasons as a SQL literal list, for an ``on conflict do update … where`` guard.
HARD_REASONS_SQL = "(" + ", ".join(f"'{r}'" for r in HARD_REASONS) + ")"

# --------------------------------------------------------------------------- #
# The canonical join. Both planes read the same four relations under the same four
# aliases, so a fragment written here means the same thing everywhere it is used.
#
# The suppression join is on lower(email) on BOTH sides: `email_suppression` is keyed by
# address, addresses arrive from unsubscribe links, bounce webhooks and operator typing,
# and "Ada@Example.com" unsubscribing has to suppress "ada@example.com". app/mailer.py
# lowercases before its own lookup for the same reason.
# --------------------------------------------------------------------------- #
JOIN_SQL = (
    "from auth.users u "
    "left join public.user_entitlements e on e.user_id = u.id "
    "left join public.email_prefs p on p.user_id = u.id "
    "left join public.email_suppression s on lower(s.email) = lower(u.email)"
)

# `deleted_at is null and not anonymous and not banned` is admin/users.py::_ACTIVE
# verbatim (modulo the `u.` alias) — the Users page's own definition of a real account, so
# the two pages' totals foot instead of quietly disagreeing.
ACTIVE_SQL = (
    "u.deleted_at is null "
    "and coalesce(u.is_anonymous, false) = false "
    "and (u.banned_until is null or u.banned_until < now())"
)

# This module's addition: a row with no address is not a recipient. Anonymous sessions
# never have one, and neither do a handful of provider-linked rows.
MAILABLE_SQL = "u.email is not null and u.email <> ''"

# Every segment sits on top of this, `all` included. Kept as the composition of the two
# above so the Email Center can report WHICH clause excluded someone rather than a bare
# "some accounts are not listed".
BASE_SQL = f"{ACTIVE_SQL} and {MAILABLE_SQL}"

TIERS = ("free", "insider", "pro")
STATUSES = ("active", "trialing", "past_due", "canceled", "none")

# The tier/status defaulting expression, authored ONCE so the fragments below, the roster
# projection and the CSV export cannot drift from each other or from :func:`normalize`.
#
# `nullif(…, '')` is not decoration. Python resolves an EMPTY tier to 'free' (`row.get(…)
# or 'free'`), and a bare `coalesce(e.tier,'free')` does not — coalesce only replaces
# NULL. A row carrying '' would then be a `free` member on the sweeper's plane and a
# member of NO tier segment on the console's, which is the two-copies divergence this
# module exists to prevent. PostgREST hands back '' for a nulled text column in some
# shapes, so this is reachable, not hypothetical.
TIER_SQL = "coalesce(nullif(e.tier,''),'free')"
STATUS_SQL = "coalesce(nullif(e.status,''),'none')"


def normalize(row: dict) -> dict:
    """A raw roster row from either plane, in the shape the predicates expect.

    Absent tier/status resolve the way :data:`TIER_SQL` does in SQL: a user who never
    touched billing IS a free member (the registration lockdown made that true), not a
    user with an unknown plan. An EMPTY string resolves the same way on both planes — see
    the note on :data:`TIER_SQL`.
    """
    return {
        "tier": (row.get("tier") or "free") or "free",
        "status": (row.get("status") or "none") or "none",
        "suppressed": bool(row.get("suppressed")),
        "opt_out": bool(row.get("opt_out")),
    }


def _parse_ts(value) -> datetime | None:
    """An ISO8601 timestamp from the GoTrue admin JSON as an aware UTC datetime, else None."""
    s = str(value or "").strip()
    if not s:
        return None
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)


def base_match(row: dict, *, now: datetime | None = None) -> bool:
    """The Python half of :data:`BASE_SQL`, for a roster row from the auth admin API.

    Kept separate from the segment predicates because the two planes learn these four
    facts differently: SQL reads the columns, the GoTrue admin list reads the JSON fields.

    The ban clause is the one that has to be READ rather than merely truthy-tested.
    ``ACTIVE_SQL`` says ``u.banned_until is null or u.banned_until < now()`` — an EXPIRED
    ban is an active account — while ``not row.get("banned_until")`` called every ban
    permanent. A user banned for a day last March was therefore mailable on the console
    and invisible to the sweeper, which is the divergence this module exists to prevent.
    An unparseable value fails CLOSED (not mailable): SQL cannot produce one from a
    timestamp column, so it can only be junk, and junk must not open a gate.
    """
    if not str(row.get("email") or "").strip():
        return False
    if row.get("deleted_at"):
        return False
    if row.get("is_anonymous"):
        return False
    banned = row.get("banned_until")
    if not banned:
        return True
    until = _parse_ts(banned)
    if until is None:
        return False
    return until < (now or datetime.now(timezone.utc))


# --------------------------------------------------------------------------- #
# The segments
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Segment:
    key: str
    label_en: str
    label_zh: str
    #: static SQL WHERE fragment over the JOIN_SQL aliases — never interpolated into
    sql: str
    #: the same predicate over a :func:`normalize`d row
    match: Callable[[dict], bool]
    #: one plain line saying who this is, for the operator picking a segment
    note_en: str
    note_zh: str


SEGMENTS: tuple[Segment, ...] = (
    Segment(
        "all", "Everyone", "全部",
        "true",
        lambda r: True,
        "Every account we can reach.", "所有能收到邮件的账户。",
    ),
    Segment(
        "free", "Free", "免费",
        f"{TIER_SQL} = 'free'",
        lambda r: r["tier"] == "free",
        "Never paid or trialed.", "从未付费或试用。",
    ),
    Segment(
        "trialing", "On trial", "试用中",
        f"{STATUS_SQL} = 'trialing'",
        lambda r: r["status"] == "trialing",
        "In a trial right now.", "正在试用期内。",
    ),
    # ---- the paid tiers ---------------------------------------------------- #
    # 'essential' is the rename migration's alias of the 'insider' wire value (lib/tiers.py).
    # Phase 1 emits only 'insider', so today these two clauses are the same population; the
    # alias is named here so a stored row that flips during Phase 2 does not silently drop
    # a paying customer OUT of the paid segment (and into no tier segment at all).
    #
    # The segment KEY stays `insider`: a saved campaign's targeting is stored BY key, and
    # renaming it would orphan every campaign already aimed at this audience. Only the
    # DISPLAY name moves.
    Segment(
        "paid", "Paying", "付费",
        f"{TIER_SQL} in ('insider','essential','pro')",
        lambda r: r["tier"] in ("insider", "essential", "pro"),
        "Essential and Pro together.", "Essential 与 Pro 合计。",
    ),
    Segment(
        "insider", "Essential", "Essential",
        f"{TIER_SQL} in ('insider','essential')",
        lambda r: r["tier"] in ("insider", "essential"),
        "On the Essential plan.", "使用 Essential 方案。",
    ),
    Segment(
        "pro", "Pro", "Pro",
        f"{TIER_SQL} = 'pro'",
        lambda r: r["tier"] == "pro",
        "On the Pro plan.", "使用 Pro 方案。",
    ),
    Segment(
        "canceled", "Cancelled", "已取消",
        f"{STATUS_SQL} = 'canceled'",
        lambda r: r["status"] == "canceled",
        "Paid once, cancelled since.", "曾经付费，之后取消。",
    ),
    # ---- the compliance segment (G3/G4) ------------------------------------ #
    # Both exclusions are IN the membership rule. `s.email is null` is an antijoin
    # against email_suppression: a row exists there only for an address that
    # unsubscribed, hard-bounced, complained, or was killed by hand, and the LEFT JOIN
    # leaves s.email NULL for everyone else. `coalesce(p.marketing_opt_out,false) =
    # false` is the per-user preference, with coalesce because most users have no
    # email_prefs row at all and no row means "has not opted out".
    Segment(
        "marketing_eligible", "Can receive marketing", "可接收营销邮件",
        "s.email is null and coalesce(p.marketing_opt_out, false) = false",
        lambda r: not r["suppressed"] and not r["opt_out"],
        "Everyone who has not unsubscribed.", "所有未退订的人。",
    ),
)

BY_KEY: dict[str, Segment] = {s.key: s for s in SEGMENTS}
KEYS: tuple[str, ...] = tuple(s.key for s in SEGMENTS)
DEFAULT_KEY = "all"

#: The one segment whose definition is a compliance promise, named so callers and tests
#: can refer to it without spelling the string again.
MARKETING_KEY = "marketing_eligible"


def get(key: str | None) -> Segment:
    """The segment for ``key``. Unknown keys raise — they never reach SQL.

    An allow-list lookup rather than a validated interpolation: the caller's string is
    used to FIND a fragment authored in this file, never to build one, so there is no
    path by which an operator-typed segment name becomes SQL.
    """
    seg = BY_KEY.get(str(key or "").strip())
    if seg is None:
        raise KeyError(f"unknown segment {key!r}; expected one of {list(KEYS)}")
    return seg


def where_sql(key: str | None, *, extra: str | None = None) -> str:
    """The complete WHERE body for a segment: base ∧ segment ∧ optional extra.

    ``extra`` is for a caller's own already-escaped fragment (the roster search box, which
    goes through ``_lit``). It is appended, never merged, so it can only ever NARROW the
    set — a caller cannot widen a segment past its own definition, and in particular
    cannot widen ``marketing_eligible`` back over someone who unsubscribed.
    """
    seg = get(key)
    parts = [BASE_SQL, f"({seg.sql})"]
    if extra:
        parts.append(f"({extra})")
    return " and ".join(parts)


def matches(key: str | None, row: dict) -> bool:
    """Python-side membership for an already-:func:`normalize`d row."""
    return get(key).match(row)


def needs_entitlements(key: str | None) -> bool:
    """Does this segment's membership depend on the billing join?

    Derived from the fragment rather than hand-listed, so a new tier segment cannot forget
    to declare itself: a rule that references the ``e.`` alias needs ``user_entitlements``,
    and one that does not cannot be changed by that table.

    The sweeper uses this to decide whether a failed entitlements read must ABORT the drain
    (#4: a transient PostgREST blip made every user normalise to ``tier='free'``, which
    turned a free-users-only campaign into a broadcast that reached paying subscribers) or
    is simply irrelevant — ``all`` and ``marketing_eligible`` are decided without it.
    """
    return "e." in get(key).sql


def options() -> list[dict]:
    """The segment picker, in display order — labels for the operator, keys for the API."""
    return [
        {"key": s.key, "label_en": s.label_en, "label_zh": s.label_zh,
         "note_en": s.note_en, "note_zh": s.note_zh}
        for s in SEGMENTS
    ]
