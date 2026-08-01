"""tests/test_email_segments.py — app/email_segments.py (SEE W4, gate G3).

The segment definitions are a PAIR — a SQL fragment for the admin console's
Management-API lane and a Python predicate for the sweeper's PostgREST/GoTrue lane —
because the two planes hold different secrets and cannot run each other's query. Two
hand-maintained copies of one membership rule is how a compliance gate rots: the CSV
export would say 412 and the send would reach 419, and nobody would notice until seven of
the extra were the seven who unsubscribed.

So this suite asserts the pair agrees, and it asserts the one thing G3 actually promises:
``marketing_eligible`` excludes suppressed addresses and opted-out users BY CONSTRUCTION,
in BOTH renderings — not by a filter a caller has to remember to apply.

Fully offline: no database, no network, no admin state. Every assertion is over strings
and pure functions.
"""
from __future__ import annotations

import itertools
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import email_segments as seg  # noqa: E402


# ===========================================================================
# Shape
# ===========================================================================
def test_every_segment_the_brief_names_exists():
    assert set(seg.KEYS) == {
        "all", "free", "trialing", "paid", "insider", "pro", "canceled", "marketing_eligible"}


def test_keys_labels_and_notes_are_all_bilingual():
    for s in seg.SEGMENTS:
        assert s.label_en and s.label_zh, s.key
        assert s.note_en and s.note_zh, s.key


def test_unknown_segment_raises_and_never_reaches_sql():
    """The allow-list is the injection boundary: an operator's string LOOKS UP a fragment
    authored in the module, it never becomes one."""
    for bad in ("", None, "nope", "all; drop table users --", "MARKETING_ELIGIBLE",
                "marketing_eligible'--"):
        with pytest.raises(KeyError):
            seg.get(bad)
        with pytest.raises(KeyError):
            seg.where_sql(bad)


def test_surrounding_whitespace_on_a_key_is_tolerated_not_a_new_key():
    """A segment arriving from a query string can carry a stray space. Stripping it is
    deliberate; it resolves to the SAME allow-listed fragment, never to a new one."""
    assert seg.get(" marketing_eligible ").key == seg.MARKETING_KEY


def test_sql_fragments_are_static_with_no_interpolation():
    """No fragment may carry an f-string hole, a %s, or a quote it did not author."""
    for s in seg.SEGMENTS:
        assert "{" not in s.sql and "}" not in s.sql, s.key
        assert "%s" not in s.sql, s.key
        # every quote in a fragment is part of a literal the module wrote itself
        assert s.sql.count("'") % 2 == 0, s.key


def test_fragments_only_reference_the_canonical_aliases():
    """A fragment that named a table the join does not provide would be a runtime error
    on the operator's console, not a test failure, so it is checked here."""
    allowed = {"u", "e", "p", "s"}
    for s in seg.SEGMENTS:
        for alias in re.findall(r"\b([a-z])\.\w+", s.sql):
            assert alias in allowed, f"{s.key} references unknown alias {alias!r}"


def test_the_join_provides_every_alias_the_fragments_use():
    for alias in ("auth.users u", "public.user_entitlements e",
                  "public.email_prefs p", "public.email_suppression s"):
        assert alias in seg.JOIN_SQL


# ===========================================================================
# G3 — marketing_eligible excludes BY CONSTRUCTION, in both renderings
# ===========================================================================
def test_marketing_eligible_sql_carries_both_exclusions_inline():
    """The SQL half. `s.email is null` is the antijoin against email_suppression (a row
    exists there only for an address that unsubscribed, bounced, complained, or was
    killed by hand); the coalesce covers the per-user preference for the majority of
    users who have no email_prefs row at all.

    This is the executable form of the promise: the exclusion is IN the membership rule,
    so a caller cannot select the segment and forget the filter."""
    sql = seg.BY_KEY[seg.MARKETING_KEY].sql
    assert "s.email is null" in sql
    assert "coalesce(p.marketing_opt_out, false) = false" in sql


def test_marketing_eligible_python_predicate_excludes_both():
    match = seg.BY_KEY[seg.MARKETING_KEY].match
    assert match(seg.normalize({})) is True
    assert match(seg.normalize({"suppressed": True})) is False
    assert match(seg.normalize({"opt_out": True})) is False
    assert match(seg.normalize({"suppressed": True, "opt_out": True})) is False


def test_marketing_eligible_excludes_regardless_of_tier():
    """A paying customer who unsubscribed is still unsubscribed. The compliance rule is
    not means-tested."""
    for tier, status in itertools.product(seg.TIERS, seg.STATUSES):
        row = seg.normalize({"tier": tier, "status": status, "suppressed": True})
        assert seg.matches(seg.MARKETING_KEY, row) is False, (tier, status)


def test_where_sql_extra_can_only_narrow_a_segment():
    """The roster search box appends a fragment. It is ANDed, never merged, so no caller
    can widen `marketing_eligible` back over somebody who unsubscribed."""
    extra = "u.email ilike '%ada%'"
    where = seg.where_sql(seg.MARKETING_KEY, extra=extra)
    # the segment's own rule survives intact, parenthesised, and is ANDed with the extra
    assert where == f"{seg.BASE_SQL} and ({seg.BY_KEY[seg.MARKETING_KEY].sql}) and ({extra})"
    # the extra is bracketed, so an `a or b` needle cannot bind looser than the AND and
    # re-admit rows the segment excluded
    assert where.endswith(f"and ({extra})")


def test_every_segment_is_gated_by_the_base_including_all():
    for key in seg.KEYS:
        assert seg.BASE_SQL in seg.where_sql(key), key


# ===========================================================================
# The pair agrees
# ===========================================================================
#: (tier, status) -> the keys that row belongs to, written out by hand rather than
#: derived, so a change to a predicate has to be defended here rather than absorbed.
_EXPECTED = {
    ("free", "none"):      {"all", "free"},
    ("free", "trialing"):  {"all", "free", "trialing"},
    ("free", "canceled"):  {"all", "free", "canceled"},
    ("insider", "active"): {"all", "paid", "insider"},
    ("insider", "trialing"): {"all", "paid", "insider", "trialing"},
    ("pro", "active"):     {"all", "paid", "pro"},
    ("pro", "canceled"):   {"all", "paid", "pro", "canceled"},
    ("pro", "past_due"):   {"all", "paid", "pro"},
    # The rename migration's alias of the 'insider' wire value (lib/tiers.py). Phase 1
    # emits only 'insider', so today these rows do not exist — they are here so that the
    # day the stored value flips, a paying member does not silently fall OUT of `paid`
    # (and out of every tier segment), which is exactly the "console count vs send
    # audience disagree" divergence this module exists to prevent.
    ("essential", "active"):   {"all", "paid", "insider"},
    ("essential", "trialing"): {"all", "paid", "insider", "trialing"},
}


@pytest.mark.parametrize("pair,expected", sorted(_EXPECTED.items()))
def test_python_membership_matches_the_hand_written_truth_table(pair, expected):
    tier, status = pair
    row = seg.normalize({"tier": tier, "status": status})
    got = {k for k in seg.KEYS if seg.matches(k, row)}
    # a clean row is always marketing-eligible; the table above tracks the tier axis only
    assert got == expected | {"marketing_eligible"}


def test_sql_and_python_use_the_same_coalesce_defaults():
    """`coalesce(e.tier,'free')` in SQL and `row.get('tier') or 'free'` in Python have to
    mean the same thing, or a user who never touched billing lands in `free` on one plane
    and nowhere on the other."""
    empty = seg.normalize({})
    assert empty["tier"] == "free" and empty["status"] == "none"
    assert seg.matches("free", empty) is True
    assert seg.matches("paid", empty) is False
    for s in seg.SEGMENTS:
        if "e.tier" in s.sql:
            assert seg.TIER_SQL in s.sql, s.key
        if "e.status" in s.sql:
            assert seg.STATUS_SQL in s.sql, s.key


def test_normalize_coerces_empty_strings_not_just_none():
    """PostgREST hands back '' for a nulled text column in some shapes; `or` catches both,
    a plain `is None` check would not."""
    row = seg.normalize({"tier": "", "status": ""})
    assert row["tier"] == "free" and row["status"] == "none"


def test_an_empty_tier_defaults_on_BOTH_planes_not_just_in_python():
    """The divergence the pair exists to prevent, in its exact shape.

    Python resolves `tier=''` to `free`. A bare `coalesce(e.tier,'free')` does NOT —
    coalesce replaces NULL, not the empty string — so a row carrying '' was a `free`
    member for the sweeper and a member of no tier segment at all for the console. The
    console's count and the send's audience then disagree by exactly those rows, which is
    the failure mode described in this module's own docstring.
    """
    assert seg.normalize({"tier": "", "status": ""})["tier"] == "free"
    assert seg.matches("free", seg.normalize({"tier": ""})) is True
    for s in seg.SEGMENTS:
        if "e.tier" in s.sql:
            assert "nullif(e.tier,'')" in s.sql, s.key
        if "e.status" in s.sql:
            assert "nullif(e.status,'')" in s.sql, s.key


# ===========================================================================
# The ban clause — the other half of the pair, and the one that was read wrong
# ===========================================================================
def test_an_expired_ban_is_mailable_on_both_planes():
    """`ACTIVE_SQL` says `banned_until is null OR banned_until < now()`, so a ban that has
    EXPIRED is an active account. `not row.get("banned_until")` called every ban
    permanent, so a user banned for a day last March counted on the console and was
    invisible to the sweeper — the pair disagreeing about a real person."""
    from datetime import datetime, timedelta, timezone

    now = datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)
    ok = {"email": "ada@example.com"}
    assert "u.banned_until < now()" in seg.ACTIVE_SQL, "the SQL half of this claim"

    expired = {**ok, "banned_until": (now - timedelta(days=120)).isoformat()}
    assert seg.base_match(expired, now=now) is True, "an expired ban is not a ban"

    live = {**ok, "banned_until": (now + timedelta(days=1)).isoformat()}
    assert seg.base_match(live, now=now) is False


def test_an_unparseable_ban_fails_closed():
    """SQL cannot produce junk from a timestamp column, so junk here is junk — and a value
    we cannot read must not be read as permission."""
    assert seg.base_match({"email": "a@example.com", "banned_until": "soon"}) is False


# ===========================================================================
# Suppression vocabulary — one list, both writers
# ===========================================================================
def test_the_hard_and_soft_reasons_partition_the_vocabulary():
    """Both writers read these. A reason that is in neither list is a reason no guard
    covers, and a reason in both is a contradiction."""
    assert set(seg.HARD_REASONS) == {"bounce", "complaint"}
    assert set(seg.SOFT_REASONS) & set(seg.HARD_REASONS) == set()
    assert set(seg.REASONS) == set(seg.SOFT_REASONS) | set(seg.HARD_REASONS)


def test_the_hard_reason_sql_is_a_static_literal_list():
    """It is interpolated into an `on conflict … where` guard, so it must be authored
    here and carry nothing an operator could have supplied."""
    assert seg.HARD_REASONS_SQL == "('bounce', 'complaint')"
    for r in seg.HARD_REASONS:
        assert f"'{r}'" in seg.HARD_REASONS_SQL


# ===========================================================================
# Which segments actually need the billing join
# ===========================================================================
def test_needs_entitlements_is_derived_from_the_fragment():
    """The sweeper aborts a drain when `user_entitlements` cannot be read — but only for a
    segment whose membership that table could have changed. Derived from the SQL rather
    than hand-listed, so a new tier segment cannot forget to declare itself."""
    assert seg.needs_entitlements("free") is True
    assert seg.needs_entitlements("paid") is True
    assert seg.needs_entitlements("trialing") is True
    assert seg.needs_entitlements("all") is False
    assert seg.needs_entitlements(seg.MARKETING_KEY) is False
    for key in seg.KEYS:
        assert seg.needs_entitlements(key) == ("e." in seg.BY_KEY[key].sql), key


# ===========================================================================
# The base mirrors the Users page, so the two consoles' totals relate
# ===========================================================================
def test_active_clause_is_the_users_page_definition_verbatim():
    """admin/users.py::_ACTIVE is what the Users page counts. If these drift, the Email
    Center's roster silently stops relating to the number the operator checks it against
    — which is exactly the footing this suite exists to keep honest."""
    from admin import users

    mine = " ".join(seg.ACTIVE_SQL.replace("u.", "").split())
    theirs = " ".join(users._ACTIVE.split())
    assert mine == theirs


def test_base_adds_mailability_on_top_of_active():
    assert seg.BASE_SQL == f"{seg.ACTIVE_SQL} and {seg.MAILABLE_SQL}"
    assert "u.email is not null" in seg.MAILABLE_SQL


def test_base_match_is_the_python_half_of_base_sql():
    ok = {"email": "ada@example.com"}
    assert seg.base_match(ok) is True
    assert seg.base_match({"email": ""}) is False
    assert seg.base_match({"email": "  "}) is False
    assert seg.base_match({**ok, "deleted_at": "2026-01-01T00:00:00Z"}) is False
    assert seg.base_match({**ok, "is_anonymous": True}) is False
    assert seg.base_match({**ok, "banned_until": "2030-01-01T00:00:00Z"}) is False


def test_options_is_the_picker_and_carries_every_key():
    opts = seg.options()
    assert [o["key"] for o in opts] == list(seg.KEYS)
    for o in opts:
        assert o["label_en"] and o["label_zh"] and o["note_en"] and o["note_zh"]


def test_the_alias_and_the_wire_value_land_in_the_same_segments():
    """Stated as parity rather than as a second truth table, so it cannot drift from the
    canonical rows above."""
    for status in ("active", "trialing"):
        wire = {k for k in seg.KEYS if seg.matches(k, seg.normalize({"tier": "insider", "status": status}))}
        alias = {k for k in seg.KEYS if seg.matches(k, seg.normalize({"tier": "essential", "status": status}))}
        assert alias == wire, status


def test_the_segment_key_stays_insider_even_though_the_label_moved():
    """Saved campaigns store their audience BY KEY — renaming it would orphan every
    campaign already aimed at this tier. Only the display name is allowed to move."""
    assert "insider" in seg.KEYS and "essential" not in seg.KEYS
    assert seg.get("insider").label_en == "Essential"


def test_the_paid_and_tier_sql_both_name_the_alias():
    """Python-side parity above is only half the pair; the SQL plane must agree or the
    console's count and the sweeper's audience diverge by exactly the aliased rows."""
    for key in ("paid", "insider"):
        assert "'essential'" in seg.where_sql(key), key
