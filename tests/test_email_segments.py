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
            assert "coalesce(e.tier,'free')" in s.sql, s.key
        if "e.status" in s.sql:
            assert "coalesce(e.status,'none')" in s.sql, s.key


def test_normalize_coerces_empty_strings_not_just_none():
    """PostgREST hands back '' for a nulled text column in some shapes; `or` catches both,
    a plain `is None` check would not."""
    row = seg.normalize({"tier": "", "status": ""})
    assert row["tier"] == "free" and row["status"] == "none"


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
