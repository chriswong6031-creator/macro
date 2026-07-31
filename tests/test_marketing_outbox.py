"""tests/test_marketing_outbox.py — Outbox contract tests (D02 W0).

Covers:
1. Schema round-trip: make_item → validate_item == [] → enqueue "queued" → read_items
2. make_item raises ValueError on bad kind / empty text / empty account
3. Deterministic id: same inputs → same id; differing text → different id
4. Dedupe: enqueue same item twice → "duplicate"; items.jsonl has 1 line
5. Caps: 8 items queued; 9th → "cap_exceeded"; effective_cap config bounds
6. Status transitions: legal chain works; illegal jumps return False + no append
7. Decisions: approve leads to transition; hold leaves queued; unknown/invalid → False
8. emit_from_content_plan: counts, media, gate, day prefix, re-run dedupe
9. Actuator dry-run: subprocess + dryrun_report.json
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _worktree_root() -> Path:
    p = Path(__file__).resolve()
    for candidate in [p.parent, p.parent.parent, p.parent.parent.parent]:
        if (candidate / "engine").is_dir():
            return candidate
    raise RuntimeError(f"Could not locate repo root from {p}")


ROOT = _worktree_root()

_FIXED_NOW = datetime(2026, 7, 19, 12, 0, 0, tzinfo=timezone.utc)
_AS_OF = "2026-07-19"

# Emit fixtures carry 3 clean D1 items per account; the Sentinel default cap is
# 2/day (weeks_1_2 floor), so tests that want all 3 through raise the sentinel
# cap EXPLICITLY — the authority stays with the sentinel: block, never outbox.
_EMIT_CFG = {"sentinel": {"max_posts_per_account_per_day": 8}}

# Nine DEEPLY distinct post texts (max pairwise token Jaccard ~0.09, well under
# the 0.7 near-dup bar) so cap-gate tests exercise the CAP, not the enqueue-time
# near-dup guard (2026-07-27 dedup upgrade). A trivially-indexed "post number {i}"
# fixture would now collide as a near-duplicate.
_DISTINCT_TEXTS = [
    "Nvidia broke out above its fifty day average on record volume today.",
    "Gold futures slid two percent as the dollar index reclaimed key resistance.",
    "Small caps quietly outperformed while mega tech chopped sideways all session.",
    "Crude oil printed a fresh weekly low ahead of the inventory report Wednesday.",
    "Regional bank shares stabilized after last week's deposit flight scare eased.",
    "Bitcoin coiled inside a tight range as options expiry loomed over the weekend.",
    "Semiconductor equipment names caught a bid on upbeat foundry capex guidance.",
    "Treasury yields cooled sharply after a soft services survey landed midmorning.",
    "Homebuilders rallied hard when mortgage rates dipped below the seven handle.",
]


def _make_minimal_item(
    tmp_path: Path,
    *,
    account: str = "flagship",
    kind: str = "signal",
    text: str = "Test post about $PLTR hitting breakout.",
    as_of: str = _AS_OF,
    provenance: str = "content_studio",
) -> dict:
    """Build a minimal valid item for tests."""
    from engine.marketing.outbox import make_item
    return make_item(
        account=account,
        kind=kind,
        text=text,
        as_of=as_of,
        provenance=provenance,
        now=_FIXED_NOW,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1. Schema round-trip
# ─────────────────────────────────────────────────────────────────────────────

def test_schema_roundtrip(tmp_path):
    from engine.marketing.outbox import make_item, validate_item, enqueue, read_items, SCHEMA_ID

    item = make_item(
        account="flagship",
        kind="signal",
        text="$PLTR breakout at the 200-day.",
        as_of=_AS_OF,
        provenance="content_studio",
        now=_FIXED_NOW,
    )

    # validate_item returns no errors
    errors = validate_item(item)
    assert errors == [], f"Expected no errors, got: {errors}"

    # enqueue returns "queued"
    result = enqueue(item, root=tmp_path)
    assert result == "queued", f"Expected 'queued', got: {result!r}"

    # read_items returns exactly the item we enqueued
    items = read_items(root=tmp_path)
    assert len(items) == 1
    assert items[0]["id"] == item["id"]
    assert items[0]["schema"] == SCHEMA_ID
    assert items[0]["account"] == "flagship"
    assert items[0]["kind"] == "signal"
    assert items[0]["status"] == "queued"
    assert items[0]["text"] == "$PLTR breakout at the 200-day."


# ─────────────────────────────────────────────────────────────────────────────
# 2. make_item raises ValueError on invalid inputs
# ─────────────────────────────────────────────────────────────────────────────

def test_make_item_raises_on_bad_kind():
    from engine.marketing.outbox import make_item
    with pytest.raises(ValueError, match="kind"):
        make_item(
            account="flagship",
            kind="nonsense_kind",
            text="Some text.",
            as_of=_AS_OF,
            provenance="content_studio",
        )


def test_make_item_raises_on_empty_text():
    from engine.marketing.outbox import make_item
    with pytest.raises(ValueError, match="text"):
        make_item(
            account="flagship",
            kind="signal",
            text="",
            as_of=_AS_OF,
            provenance="content_studio",
        )


def test_make_item_raises_on_whitespace_text():
    from engine.marketing.outbox import make_item
    with pytest.raises(ValueError, match="text"):
        make_item(
            account="flagship",
            kind="signal",
            text="   ",
            as_of=_AS_OF,
            provenance="content_studio",
        )


def test_make_item_raises_on_empty_account():
    from engine.marketing.outbox import make_item
    with pytest.raises(ValueError, match="account"):
        make_item(
            account="",
            kind="signal",
            text="Some text.",
            as_of=_AS_OF,
            provenance="content_studio",
        )


# ─────────────────────────────────────────────────────────────────────────────
# 3. Deterministic id
# ─────────────────────────────────────────────────────────────────────────────

def test_deterministic_id_same_inputs():
    from engine.marketing.outbox import make_item

    item1 = make_item(
        account="flagship", kind="signal",
        text="Price level break.", as_of=_AS_OF,
        provenance="content_studio", now=_FIXED_NOW,
    )
    item2 = make_item(
        account="flagship", kind="signal",
        text="Price level break.", as_of=_AS_OF,
        provenance="test_harness",  # provenance does NOT affect id
        now=datetime(2020, 1, 1, tzinfo=timezone.utc),  # nor does now
    )
    assert item1["id"] == item2["id"]


def test_deterministic_id_differing_text():
    from engine.marketing.outbox import make_item

    item1 = make_item(
        account="flagship", kind="signal",
        text="Text A.", as_of=_AS_OF,
        provenance="content_studio",
    )
    item2 = make_item(
        account="flagship", kind="signal",
        text="Text B.", as_of=_AS_OF,
        provenance="content_studio",
    )
    assert item1["id"] != item2["id"]


def test_deterministic_id_whitespace_normalized():
    """Whitespace normalization: same text with different internal spacing → same id."""
    from engine.marketing.outbox import make_item

    item1 = make_item(
        account="flagship", kind="signal",
        text="The  market  broke out.", as_of=_AS_OF,
        provenance="content_studio",
    )
    item2 = make_item(
        account="flagship", kind="signal",
        text="The market broke out.", as_of=_AS_OF,
        provenance="content_studio",
    )
    assert item1["id"] == item2["id"]


# ─────────────────────────────────────────────────────────────────────────────
# 4. Dedupe
# ─────────────────────────────────────────────────────────────────────────────

def test_dedupe_second_enqueue_returns_duplicate(tmp_path):
    from engine.marketing.outbox import make_item, enqueue

    item = make_item(
        account="flagship", kind="signal",
        text="Dedup test post.", as_of=_AS_OF,
        provenance="content_studio", now=_FIXED_NOW,
    )
    r1 = enqueue(item, root=tmp_path)
    r2 = enqueue(item, root=tmp_path)
    assert r1 == "queued"
    assert r2 == "duplicate"


def test_dedupe_items_jsonl_has_one_line(tmp_path):
    from engine.marketing.outbox import make_item, enqueue

    item = make_item(
        account="flagship", kind="signal",
        text="Dedup test post line count.", as_of=_AS_OF,
        provenance="content_studio", now=_FIXED_NOW,
    )
    enqueue(item, root=tmp_path)
    enqueue(item, root=tmp_path)

    items_file = tmp_path / "data" / "marketing" / "outbox" / "items.jsonl"
    lines = [l for l in items_file.read_text().splitlines() if l.strip()]
    assert len(lines) == 1


# ─────────────────────────────────────────────────────────────────────────────
# 4b. Cross-night near-duplicate guard
#    _item_id folds as_of into the hash, so identical copy re-emitted on a later
#    day gets a fresh id and id-dedupe misses it — the 2026-07-26/07-27 verbatim
#    "My read on today's move" event repeat. The text guard closes that hole
#    WITHOUT touching copy that legitimately updates its numbers day to day.
# ─────────────────────────────────────────────────────────────────────────────

def test_cross_night_identical_text_is_deduped(tmp_path):
    from engine.marketing.outbox import make_item, enqueue, read_items

    text = "My read on today's move\n\nWhat's driving today: hawkish repricing, front-end up."
    d26 = make_item(account="flagship", kind="event", text=text, as_of="2026-07-26",
                    provenance="content_studio", now=_FIXED_NOW)
    d27 = make_item(account="flagship", kind="event", text=text, as_of="2026-07-27",
                    provenance="content_studio", now=_FIXED_NOW)
    # Different ids — id-dedupe alone would let both through (the actual bug).
    assert d26["id"] != d27["id"]
    assert enqueue(d26, root=tmp_path) == "queued"
    assert enqueue(d27, root=tmp_path) == "duplicate"
    assert len(read_items(root=tmp_path)) == 1


def test_cross_night_different_text_both_queue(tmp_path):
    """A signal that updates its numbers day to day must NOT be caught — the
    guard fires only on byte-identical (whitespace-normalized) copy."""
    from engine.marketing.outbox import make_item, enqueue, read_items

    a = make_item(account="flagship", kind="signal", text="$ROST held 219.90 for 14 sessions.",
                  as_of="2026-07-26", provenance="content_studio", now=_FIXED_NOW)
    b = make_item(account="flagship", kind="signal", text="$ROST held 220.10 for 15 sessions.",
                  as_of="2026-07-27", provenance="content_studio", now=_FIXED_NOW)
    assert enqueue(a, root=tmp_path) == "queued"
    assert enqueue(b, root=tmp_path) == "queued"
    assert len(read_items(root=tmp_path)) == 2


def test_identical_text_outside_window_both_queue(tmp_path):
    """Beyond the dedup window (>7 days) the same evergreen line may recur."""
    from engine.marketing.outbox import make_item, enqueue, read_items

    text = "Evergreen note: size the position so the stop doesn't scare you out."
    a = make_item(account="flagship", kind="education", text=text, as_of="2026-07-01",
                  provenance="content_studio", now=_FIXED_NOW)
    b = make_item(account="flagship", kind="education", text=text, as_of="2026-07-27",
                  provenance="content_studio", now=_FIXED_NOW)
    assert enqueue(a, root=tmp_path) == "queued"
    assert enqueue(b, root=tmp_path) == "queued"
    assert len(read_items(root=tmp_path)) == 2


# ─────────────────────────────────────────────────────────────────────────────
# 4c. Enqueue-time NEAR-duplicate guard ("deeply reworded" law, 2026-07-27)
#    Exact-text dedup only catches whitespace diffs; a lightly-reworded repeat
#    (token Jaccard ≥ 0.7 vs a same-account 7-day text) is now blocked too. A
#    DEEPLY reworded post (< 0.7) passes. Strictly per-account.
# ─────────────────────────────────────────────────────────────────────────────

def test_near_duplicate_helper_thresholds():
    from engine.marketing.outbox import near_duplicate, token_jaccard, _NEAR_DUP_JACCARD
    assert _NEAR_DUP_JACCARD == 0.7
    # Two empty strings are NOT near-duplicates.
    assert near_duplicate("", "") is False
    assert token_jaccard("", "") == 0.0
    # Identical → jaccard 1.0 → near-dup.
    assert near_duplicate("SPY is holding 640 today", "SPY is holding 640 today") is True
    # A changed number lowers similarity (numbers kept in the token set).
    assert near_duplicate("SPY holding 640", "SPY holding 655") is False


def test_enqueue_near_dup_lightly_reworded_is_blocked(tmp_path):
    """Same account, ≥0.7 Jaccard (only filler words added) → 'duplicate'."""
    from engine.marketing.outbox import make_item, enqueue, read_items, token_jaccard
    a_text = "SPY reclaimed the fifty day moving average on strong breadth today"
    b_text = "SPY reclaimed the fifty day moving average on strong breadth again today"
    assert token_jaccard(a_text, b_text) >= 0.7
    a = make_item(account="flagship", kind="signal", text=a_text, as_of="2026-07-26",
                  provenance="content_studio", now=_FIXED_NOW)
    b = make_item(account="flagship", kind="signal", text=b_text, as_of="2026-07-27",
                  provenance="content_studio", now=_FIXED_NOW)
    assert a["id"] != b["id"]
    assert enqueue(a, root=tmp_path) == "queued"
    assert enqueue(b, root=tmp_path) == "duplicate"
    assert len(read_items(root=tmp_path)) == 1


def test_enqueue_deeply_reworded_passes(tmp_path):
    """Same account but < 0.7 Jaccard (genuinely different copy) → both queue."""
    from engine.marketing.outbox import make_item, enqueue, read_items, token_jaccard
    a_text = "SPY reclaimed the fifty day moving average on strong breadth today"
    b_text = "Breadth thrust fired as the equal weight index cleared its downtrend line"
    assert token_jaccard(a_text, b_text) < 0.7
    a = make_item(account="flagship", kind="signal", text=a_text, as_of="2026-07-26",
                  provenance="content_studio", now=_FIXED_NOW)
    b = make_item(account="flagship", kind="signal", text=b_text, as_of="2026-07-27",
                  provenance="content_studio", now=_FIXED_NOW)
    assert enqueue(a, root=tmp_path) == "queued"
    assert enqueue(b, root=tmp_path) == "queued"
    assert len(read_items(root=tmp_path)) == 2


def test_enqueue_near_dup_blocks_cross_account_too(tmp_path):
    """XG-W2 INVERTED this contract, deliberately.

    The old law here was "cross-account near-dup is the sentinel's plan-time
    job, not this guard". That was defensible with one live account and became a
    hole at seven: sentinel's cross-account pass only sees items inside ONE
    nightly content plan, so it never sees the queue across nights and never
    sees the fast lanes (press/earnings), which do not enter a plan at all. Two
    of OUR accounts posting near-identical text is the text-similarity
    clustering signal, not a style problem — so the outbox now carries the bar
    too, at the STRICTER sentinel.near_dup_jaccard threshold.
    """
    from engine.marketing.outbox import (
        cross_account_threshold, enqueue, make_item, read_items, token_jaccard,
    )
    a_text = "SPY reclaimed the fifty day moving average on strong breadth today"
    b_text = "SPY reclaimed the fifty day moving average on strong breadth again today"
    assert token_jaccard(a_text, b_text) >= cross_account_threshold(None)
    a = make_item(account="deskA", kind="signal", text=a_text, as_of="2026-07-26",
                  provenance="content_studio", now=_FIXED_NOW)
    b = make_item(account="deskB", kind="signal", text=b_text, as_of="2026-07-27",
                  provenance="content_studio", now=_FIXED_NOW)
    assert enqueue(a, root=tmp_path) == "queued"
    assert enqueue(b, root=tmp_path) == "cross_account_duplicate"
    assert len(read_items(root=tmp_path)) == 1


def test_cross_account_distinct_text_still_queues(tmp_path):
    """The cross-account bar is SIMILARITY, not account identity.

    Two desks covering the same day in genuinely different words both queue —
    otherwise the guard would be a one-post-per-network rule. This is the
    companion to the test above: it proves the bar can be cleared.
    """
    from engine.marketing.outbox import (
        cross_account_threshold, enqueue, make_item, read_items, token_jaccard,
    )

    a_text = "Breadth improved into the close; new highs outnumbered new lows."
    b_text = "Credit spreads tightened while the dollar gave back yesterday's bid."
    assert token_jaccard(a_text, b_text) < cross_account_threshold(None)
    a = make_item(account="flagship", kind="event", text=a_text, as_of="2026-07-27",
                  provenance="content_studio", now=_FIXED_NOW)
    b = make_item(account="specialist", kind="event", text=b_text, as_of="2026-07-27",
                  provenance="content_studio", now=_FIXED_NOW)
    assert enqueue(a, root=tmp_path) == "queued"
    assert enqueue(b, root=tmp_path) == "queued"
    assert len(read_items(root=tmp_path)) == 2


def test_cross_account_identical_text_is_refused(tmp_path):
    """Byte-identical copy on two desks is the most obvious fleet tell of all."""
    from engine.marketing.outbox import make_item, enqueue, read_items

    text = "Same wording, different desks — no longer allowed (XG-W2)."
    a = make_item(account="flagship", kind="event", text=text, as_of="2026-07-27",
                  provenance="content_studio", now=_FIXED_NOW)
    b = make_item(account="specialist", kind="event", text=text, as_of="2026-07-27",
                  provenance="content_studio", now=_FIXED_NOW)
    assert enqueue(a, root=tmp_path) == "queued"
    assert enqueue(b, root=tmp_path) == "cross_account_duplicate"
    assert len(read_items(root=tmp_path)) == 1


# ─────────────────────────────────────────────────────────────────────────────
# 5. Caps
# ─────────────────────────────────────────────────────────────────────────────

def test_cap_8_items_ok_9th_rejected(tmp_path):
    from engine.marketing.outbox import make_item, enqueue

    # Deeply distinct texts (well under the 0.7 near-dup bar) so this test
    # isolates the CAP gate, not the enqueue-time dedup gate.
    results = []
    for i in range(9):
        item = make_item(
            account="flagship", kind="signal",
            text=_DISTINCT_TEXTS[i],
            as_of=_AS_OF,
            provenance="content_studio", now=_FIXED_NOW,
        )
        results.append(enqueue(item, root=tmp_path, max_per_account_day=8))

    queued = [r for r in results if r == "queued"]
    cap_exceeded = [r for r in results if r == "cap_exceeded"]
    assert len(queued) == 8, f"Expected 8 queued, got {len(queued)}: {results}"
    assert len(cap_exceeded) == 1, f"Expected 1 cap_exceeded, got {len(cap_exceeded)}: {results}"
    assert results[8] == "cap_exceeded", "9th item must be cap_exceeded"


def test_effective_cap_outbox_can_lower_below_sentinel(tmp_path):
    from engine.marketing.outbox import effective_cap
    assert effective_cap({"sentinel": {"max_posts_per_account_per_day": 4},
                          "outbox": {"max_posts_per_account_per_day": 3}}) == 3


def test_effective_cap_outbox_cannot_raise_above_sentinel_default(tmp_path):
    """With no sentinel config, the Sentinel in-code floor (weeks_1_2 = 2) rules."""
    from engine.marketing.outbox import effective_cap
    assert effective_cap({"outbox": {"max_posts_per_account_per_day": 20}}) == 2


def test_effective_cap_default_is_sentinel_floor():
    """No config at all → Sentinel's weeks_1_2 in-code default (2), NOT an
    outbox-owned constant (config/marketing.yml sentinel: LAW)."""
    from engine.marketing.outbox import effective_cap
    assert effective_cap({}) == 2


def test_effective_cap_follows_sentinel_ramp():
    """When Sentinel raises the cap (week-5+ ramp), the outbox follows — there
    is no independent outbox ceiling."""
    from engine.marketing.outbox import effective_cap
    assert effective_cap({"sentinel": {"max_posts_per_account_per_day": 12}}) == 12


def test_cap_9th_item_not_written_to_file(tmp_path):
    from engine.marketing.outbox import make_item, enqueue

    for i in range(9):
        item = make_item(
            account="flagship", kind="signal",
            text=_DISTINCT_TEXTS[i],
            as_of=_AS_OF,
            provenance="content_studio", now=_FIXED_NOW,
        )
        enqueue(item, root=tmp_path, max_per_account_day=8)

    items_file = tmp_path / "data" / "marketing" / "outbox" / "items.jsonl"
    lines = [l for l in items_file.read_text().splitlines() if l.strip()]
    assert len(lines) == 8, f"Expected 8 lines (cap), got {len(lines)}"


# ─────────────────────────────────────────────────────────────────────────────
# 6. Status transitions
# ─────────────────────────────────────────────────────────────────────────────

def test_legal_transition_chain(tmp_path):
    """queued → approved → posted is a legal chain."""
    from engine.marketing.outbox import make_item, enqueue, transition, current_statuses

    item = make_item(
        account="flagship", kind="macro",
        text="Legal chain test post.", as_of=_AS_OF,
        provenance="content_studio", now=_FIXED_NOW,
    )
    enqueue(item, root=tmp_path)
    item_id = item["id"]

    # queued → approved
    ok1 = transition(item_id, "approved", actor="test", root=tmp_path)
    assert ok1 is True

    # approved → posted
    ok2 = transition(item_id, "posted", actor="test", root=tmp_path)
    assert ok2 is True

    # Fold gives posted
    statuses = current_statuses(root=tmp_path)
    assert statuses[item_id] == "posted"


def test_illegal_jump_queued_to_posted(tmp_path):
    """queued → posted is not a legal transition; must return False and not append."""
    from engine.marketing.outbox import make_item, enqueue, transition, read_ledger

    item = make_item(
        account="flagship", kind="signal",
        text="Illegal jump test post.", as_of=_AS_OF,
        provenance="content_studio", now=_FIXED_NOW,
    )
    enqueue(item, root=tmp_path)
    item_id = item["id"]

    before_count = len(read_ledger(root=tmp_path))
    ok = transition(item_id, "posted", actor="test", root=tmp_path)
    after_count = len(read_ledger(root=tmp_path))

    assert ok is False
    assert after_count == before_count, "Illegal transition must not append to ledger"


def test_illegal_jump_posted_to_anything(tmp_path):
    """posted is a terminal state; no further transitions allowed."""
    from engine.marketing.outbox import make_item, enqueue, transition, read_ledger

    item = make_item(
        account="flagship", kind="signal",
        text="Terminal posted state test.", as_of=_AS_OF,
        provenance="content_studio", now=_FIXED_NOW,
    )
    enqueue(item, root=tmp_path)
    item_id = item["id"]

    # Advance to posted
    transition(item_id, "approved", actor="test", root=tmp_path)
    transition(item_id, "posted", actor="test", root=tmp_path)

    before_count = len(read_ledger(root=tmp_path))
    ok = transition(item_id, "approved", actor="test", root=tmp_path)
    after_count = len(read_ledger(root=tmp_path))

    assert ok is False
    assert after_count == before_count


def test_illegal_jump_approved_to_queued(tmp_path):
    """approved → queued is not a valid transition."""
    from engine.marketing.outbox import make_item, enqueue, transition, read_ledger

    item = make_item(
        account="flagship", kind="signal",
        text="Approved back to queued test.", as_of=_AS_OF,
        provenance="content_studio", now=_FIXED_NOW,
    )
    enqueue(item, root=tmp_path)
    item_id = item["id"]

    transition(item_id, "approved", actor="test", root=tmp_path)
    before_count = len(read_ledger(root=tmp_path))
    ok = transition(item_id, "queued", actor="test", root=tmp_path)
    after_count = len(read_ledger(root=tmp_path))

    assert ok is False
    assert after_count == before_count


def test_ledger_only_grows(tmp_path):
    """Append-only assertion: ledger line count only ever increases."""
    from engine.marketing.outbox import make_item, enqueue, transition, read_ledger

    item = make_item(
        account="flagship", kind="event",
        text="Append-only ledger test post.", as_of=_AS_OF,
        provenance="content_studio", now=_FIXED_NOW,
    )
    enqueue(item, root=tmp_path)
    item_id = item["id"]

    counts: list[int] = []
    counts.append(len(read_ledger(root=tmp_path)))  # 0 before any transition

    transition(item_id, "approved", actor="test", root=tmp_path)
    counts.append(len(read_ledger(root=tmp_path)))

    transition(item_id, "posted", actor="test", root=tmp_path)
    counts.append(len(read_ledger(root=tmp_path)))

    # Illegal transitions (terminal state)
    transition(item_id, "queued", actor="test", root=tmp_path)
    counts.append(len(read_ledger(root=tmp_path)))

    # Verify monotonically non-decreasing
    for i in range(1, len(counts)):
        assert counts[i] >= counts[i - 1], (
            f"Ledger shrank at step {i}: {counts[i - 1]} → {counts[i]}"
        )


def test_transition_now_param_stamps_ledger_at(tmp_path):
    """transition(now=...) stamps the row's `at` from the injected clock."""
    from engine.marketing.outbox import make_item, enqueue, transition, read_ledger

    item = _make_minimal_item(tmp_path)
    enqueue(item, root=tmp_path)
    assert transition(item["id"], "approved", actor="test", root=tmp_path,
                      now=_FIXED_NOW)
    row = read_ledger(root=tmp_path)[-1]
    assert row["at"] == "2026-07-19T12:00:00Z"


def test_posted_today_by_account_counts_ledger_date_not_as_of(tmp_path):
    """The daily-cap counter keys on the LAST ledger row's date, not as_of.

    A nightly item (as_of = generation day, yesterday) posted today COUNTS;
    an item posted yesterday does NOT (whatever its as_of); posting (in-flight)
    holds a slot; queued/approved never count.
    """
    from datetime import datetime, timezone as _tz
    from engine.marketing.outbox import (
        make_item, enqueue, transition, fold_state, posted_today_by_account
    )
    today = _AS_OF                                             # 2026-07-19
    yesterday_now = datetime(2026, 7, 18, 22, 0, 0, tzinfo=_tz.utc)

    def _seed(text: str, *, as_of: str, to: list[str], at: datetime) -> str:
        it = make_item(account="flagship", kind="signal", text=text,
                       as_of=as_of, provenance="content_studio", now=_FIXED_NOW)
        enqueue(it, root=tmp_path, max_per_account_day=99)
        for status in to:
            assert transition(it["id"], status, actor="t", root=tmp_path, now=at)
        return it["id"]

    # Nightly item posted TODAY → counts (the undercount bug this pins).
    _seed("Nightly, posted today.", as_of="2026-07-18",
          to=["approved", "posted"], at=_FIXED_NOW)
    # Posted YESTERDAY (as_of today!) → does not count.
    _seed("Posted yesterday.", as_of=today,
          to=["approved", "posted"], at=yesterday_now)
    # In-flight TODAY → holds a slot.
    _seed("In flight today.", as_of=today,
          to=["approved", "posting"], at=_FIXED_NOW)
    # Approved today, never posted → no slot.
    _seed("Approved only.", as_of=today, to=["approved"], at=_FIXED_NOW)

    counts = posted_today_by_account(fold_state(tmp_path), today)
    assert counts == {"flagship": 2}


# ─────────────────────────────────────────────────────────────────────────────
# 7. Decisions
# ─────────────────────────────────────────────────────────────────────────────

def test_approve_decision_then_transition(tmp_path):
    """record_decision('approve') → actuator can transition to approved."""
    from engine.marketing.outbox import (
        make_item, enqueue, record_decision, latest_decisions, transition, current_statuses
    )

    item = make_item(
        account="flagship", kind="signal",
        text="Operator approve test post.", as_of=_AS_OF,
        provenance="content_studio", now=_FIXED_NOW,
    )
    enqueue(item, root=tmp_path)
    item_id = item["id"]

    ok = record_decision(item_id, "approve", actor="operator", root=tmp_path)
    assert ok is True

    # Actuator reads decision and applies it
    dec = latest_decisions(root=tmp_path)
    assert dec[item_id]["decision"] == "approve"

    # Actuator transitions to approved
    ok2 = transition(item_id, "approved", actor="actuator", root=tmp_path)
    assert ok2 is True

    statuses = current_statuses(root=tmp_path)
    assert statuses[item_id] == "approved"


def test_hold_decision_leaves_queued(tmp_path):
    """record_decision('hold') must leave status as queued."""
    from engine.marketing.outbox import (
        make_item, enqueue, record_decision, current_statuses
    )

    item = make_item(
        account="flagship", kind="signal",
        text="Operator hold test post.", as_of=_AS_OF,
        provenance="content_studio", now=_FIXED_NOW,
    )
    enqueue(item, root=tmp_path)
    item_id = item["id"]

    record_decision(item_id, "hold", actor="operator", root=tmp_path)
    # No transition called — status remains queued
    statuses = current_statuses(root=tmp_path)
    assert statuses[item_id] == "queued"


def test_record_decision_unknown_id_returns_false(tmp_path):
    from engine.marketing.outbox import record_decision

    ok = record_decision("ob-2026-07-19-nonexistent", "approve", actor="operator", root=tmp_path)
    assert ok is False


def test_record_decision_invalid_decision_returns_false(tmp_path):
    from engine.marketing.outbox import make_item, enqueue, record_decision

    item = make_item(
        account="flagship", kind="signal",
        text="Invalid decision string test.", as_of=_AS_OF,
        provenance="content_studio", now=_FIXED_NOW,
    )
    enqueue(item, root=tmp_path)
    item_id = item["id"]

    ok = record_decision(item_id, "publish", actor="operator", root=tmp_path)
    assert ok is False


# ─────────────────────────────────────────────────────────────────────────────
# 8. emit_from_content_plan
# ─────────────────────────────────────────────────────────────────────────────

def _make_plan_fixture(as_of: str = _AS_OF) -> dict:
    """Build a minimal content plan fixture.

    D1 items:
      - item 1: clean, D1-AM, no chart → should be emitted
      - item 2: clean, D1-PM, no chart → should be emitted
      - item 3: clean, D1-EOD, chart_id "chart-001" matching a featured chart → should be emitted
    Gate item:
      - item 4: D1-AM, has _live_gate_fail → skipped_gate
    D2 item:
      - item 5: D2-AM → not in D1 prefix, not emitted
    """
    tiny_svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><circle cx="50" cy="50" r="40"/></svg>'

    return {
        "as_of": as_of,
        "accounts": [
            {
                "id": "flagship",
                "queue": [
                    {
                        "id": "post-flagship-001",
                        "type": "signal",
                        "account": "flagship",
                        "cashtag": "$PLTR",
                        "ticker": "PLTR",
                        "headline": "PLTR reclaimed the 50-day.",
                        "body": "First session above the 50-day since April.",
                        "provenance": "neural_web",
                        "chart_id": None,
                        "slot": "D1-AM",
                        "status": "drafted",
                    },
                    {
                        "id": "post-flagship-002",
                        "type": "macro",
                        "account": "flagship",
                        "cashtag": "",
                        "ticker": "",
                        "headline": "Rate path update.",
                        "body": "Fed futures pricing 2 cuts by December.",
                        "provenance": "neural_web",
                        "chart_id": None,
                        "slot": "D1-PM",
                        "status": "drafted",
                    },
                    {
                        "id": "post-flagship-003",
                        "type": "chart",
                        "account": "flagship",
                        "cashtag": "$NVDA",
                        "ticker": "NVDA",
                        "headline": "NVDA weekly setup.",
                        "body": "Chart shows compression at the highs.",
                        "provenance": "neural_web",
                        "chart_id": "chart-001",
                        "slot": "D1-EOD",
                        "status": "drafted",
                    },
                    {
                        "id": "post-flagship-004",
                        "type": "signal",
                        "account": "flagship",
                        "cashtag": "$SBUX",
                        "ticker": "SBUX",
                        "headline": "SBUX stale signal.",
                        "body": "Signal is 17 days old.",
                        "provenance": "neural_web",
                        "chart_id": None,
                        "slot": "D1-AM",
                        "status": "drafted",
                        "_live_gate_fail": "signal is 17d old (max 10d)",
                    },
                    {
                        "id": "post-flagship-005",
                        "type": "education",
                        "account": "flagship",
                        "cashtag": "",
                        "ticker": "",
                        "headline": "D2 explainer post.",
                        "body": "This is scheduled for tomorrow.",
                        "provenance": "neural_web",
                        "chart_id": None,
                        "slot": "D2-AM",
                        "status": "drafted",
                    },
                ],
            }
        ],
        "featured_charts": [
            {
                "id": "chart-001",
                "ticker": "NVDA",
                "account": "flagship",
                "cashtag": "$NVDA",
                "marker_source": "signal",
                "marker_date": as_of,
                "marker_price": 950.0,
                "svg": tiny_svg,
                "headline": "NVDA Setup",
                "body": "Compression at highs.",
                "source": "prophet",
                "combo_id": None,
            }
        ],
    }


def test_emit_counts(tmp_path):
    """3 clean D1 items emitted; 1 skipped_gate; D2 item not emitted."""
    from engine.marketing.outbox import emit_from_content_plan

    plan = _make_plan_fixture()
    result = emit_from_content_plan(plan, root=tmp_path, cfg=_EMIT_CFG, day_prefix="D1")

    assert result["emitted"] == 3, f"Expected 3 emitted, got: {result}"
    assert result["skipped_gate"] == 1, f"Expected 1 skipped_gate, got: {result}"
    assert result["skipped_dupe"] == 0
    assert result["skipped_invalid"] == 0
    # D2 item is not counted anywhere (not in D1 prefix)
    total_accounted = (
        result["emitted"] + result["skipped_gate"] +
        result["skipped_dupe"] + result["skipped_cap"] + result["skipped_invalid"]
    )
    # D1 items: 3 clean + 1 gate = 4 processed; 1 D2 = skipped silently
    assert total_accounted == 4


def test_emit_media_written(tmp_path):
    """Chart item produces an SVG media file at the expected path."""
    from engine.marketing.outbox import emit_from_content_plan

    plan = _make_plan_fixture()
    result = emit_from_content_plan(plan, root=tmp_path, cfg=_EMIT_CFG, day_prefix="D1")

    assert result["media_written"] == 1

    svg_path = tmp_path / "data" / "marketing" / "outbox" / "media" / _AS_OF / "chart-001.svg"
    assert svg_path.exists(), f"SVG file not written at {svg_path}"

    content = svg_path.read_text(encoding="utf-8")
    tiny_svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><circle cx="50" cy="50" r="40"/></svg>'
    assert content == tiny_svg


def test_emit_media_path_repo_relative(tmp_path):
    """Media entry path in the queued item is repo-relative."""
    from engine.marketing.outbox import emit_from_content_plan, read_items

    plan = _make_plan_fixture()
    emit_from_content_plan(plan, root=tmp_path, cfg=_EMIT_CFG, day_prefix="D1")

    items = read_items(root=tmp_path)
    chart_items = [i for i in items if i.get("source", {}).get("chart_id") == "chart-001"]
    assert chart_items, "No item with chart_id=chart-001 found"

    media_list = chart_items[0].get("media") or []
    assert media_list, "Chart item has no media"
    path = media_list[0]["path"]
    # Must be repo-relative (not absolute)
    assert not path.startswith("/"), f"path must be repo-relative; got: {path}"
    assert "outbox/media" in path


def test_emit_rerun_gives_skipped_dupe(tmp_path):
    """Second emit call: all previously emitted items are duplicates."""
    from engine.marketing.outbox import emit_from_content_plan

    plan = _make_plan_fixture()
    r1 = emit_from_content_plan(plan, root=tmp_path, cfg=_EMIT_CFG, day_prefix="D1")
    r2 = emit_from_content_plan(plan, root=tmp_path, cfg=_EMIT_CFG, day_prefix="D1")

    assert r1["emitted"] == 3
    assert r2["emitted"] == 0
    assert r2["skipped_dupe"] == 3, f"Expected 3 skipped_dupe on re-run, got: {r2}"


def test_emit_by_account(tmp_path):
    """by_account tracks emitted count per account."""
    from engine.marketing.outbox import emit_from_content_plan

    plan = _make_plan_fixture()
    result = emit_from_content_plan(plan, root=tmp_path, cfg=_EMIT_CFG, day_prefix="D1")

    assert "flagship" in result["by_account"]
    assert result["by_account"]["flagship"] == 3


def test_emit_media_not_rewritten_if_exists(tmp_path):
    """If SVG file already exists, emit does not rewrite it (idempotent)."""
    from engine.marketing.outbox import emit_from_content_plan

    plan = _make_plan_fixture()
    emit_from_content_plan(plan, root=tmp_path, cfg=_EMIT_CFG, day_prefix="D1")

    # Overwrite with known content
    svg_path = tmp_path / "data" / "marketing" / "outbox" / "media" / _AS_OF / "chart-001.svg"
    svg_path.write_text("EXISTING_CONTENT", encoding="utf-8")

    # Second run with different plan (but same chart id) — gate bypassed via different items
    plan2 = dict(plan)
    plan2["accounts"] = [{"id": "flagship", "queue": [
        {
            "id": "post-flagship-new-001",
            "type": "chart",
            "account": "flagship",
            "cashtag": "$NVDA",
            "ticker": "NVDA",
            "headline": "New post with same chart.",
            "body": "Different post, same chart.",
            "provenance": "neural_web",
            "chart_id": "chart-001",
            "slot": "D1-AM",
            "status": "drafted",
        }
    ]}]
    emit_from_content_plan(plan2, root=tmp_path, cfg=_EMIT_CFG, day_prefix="D1")

    # File must retain the overwritten content (not rewritten)
    assert svg_path.read_text(encoding="utf-8") == "EXISTING_CONTENT"


# ─────────────────────────────────────────────────────────────────────────────
# 9. Actuator dry-run (subprocess)
# ─────────────────────────────────────────────────────────────────────────────

def test_actuator_no_dry_run_flag_exits_2(tmp_path):
    """Without --dry-run: actuator must exit with code 2."""
    result = subprocess.run(
        [sys.executable, "scripts/marketing_actuator.py", "--root", str(tmp_path)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2, (
        f"Expected exit 2, got {result.returncode}. stderr={result.stderr!r}"
    )
    assert "dry-run" in result.stderr.lower() or "refusing" in result.stderr.lower()


def test_actuator_dry_run_exits_0_and_writes_report(tmp_path):
    """--dry-run exits 0 and produces dryrun_report.json."""
    # Seed the outbox with a few items
    from engine.marketing.outbox import emit_from_content_plan, record_decision, read_items

    plan = _make_plan_fixture()
    emit_from_content_plan(plan, root=tmp_path, cfg=_EMIT_CFG, day_prefix="D1")

    items = read_items(root=tmp_path)
    assert items, "No items seeded"

    # Approve the first item, hold the second
    first_id = items[0]["id"]
    second_id = items[1]["id"]
    record_decision(first_id, "approve", actor="operator", root=tmp_path)
    record_decision(second_id, "hold", actor="operator", root=tmp_path)

    result = subprocess.run(
        [
            sys.executable, "scripts/marketing_actuator.py",
            "--dry-run", "--root", str(tmp_path),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"Expected exit 0, got {result.returncode}. stdout={result.stdout!r} stderr={result.stderr!r}"
    )

    report_path = tmp_path / "data" / "marketing" / "outbox" / "dryrun_report.json"
    assert report_path.exists(), "dryrun_report.json not written"

    report = json.loads(report_path.read_text())
    assert report["schema"] == "marketing.outbox.dryrun/v2"
    assert report["dry_run"] is True
    assert "kill_switch" in report
    assert "MARKETING_PUBLISH_ENABLED" in report["kill_switch"]

    # would_post contains the approved item
    would_post_ids = {e["id"] for e in report["would_post"]}
    assert first_id in would_post_ids, (
        f"Approved item {first_id} not in would_post: {would_post_ids}"
    )

    # would_post entries have expected text
    first_entry = next(e for e in report["would_post"] if e["id"] == first_id)
    assert first_entry["chars"] > 0
    assert "text" in first_entry

    # held list contains the held item
    assert second_id in report["held"], (
        f"Held item {second_id} not in report['held']: {report['held']}"
    )

    # Counts are consistent
    counts = report["counts"]
    assert counts["items_total"] == len(items)
    assert counts["approved"] >= 1
    assert counts["held"] >= 1


def test_actuator_dry_run_counts_consistent(tmp_path):
    """Counts in dryrun_report.json are internally consistent."""
    from engine.marketing.outbox import emit_from_content_plan

    plan = _make_plan_fixture()
    emit_from_content_plan(plan, root=tmp_path, cfg=_EMIT_CFG, day_prefix="D1")

    subprocess.run(
        [sys.executable, "scripts/marketing_actuator.py", "--dry-run", "--root", str(tmp_path)],
        cwd=str(ROOT),
        capture_output=True,
    )

    report_path = tmp_path / "data" / "marketing" / "outbox" / "dryrun_report.json"
    report = json.loads(report_path.read_text())
    counts = report["counts"]

    assert counts["items_total"] == 3  # 3 D1 items emitted
    accounted = (
        counts["queued"] + counts["held"] + counts["approved"] +
        counts["posted"] + counts["failed"] + counts["quarantined"]
    )
    assert accounted == counts["items_total"], (
        f"Status counts don't add up to items_total: {counts}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 10. D08 Sentinel seam — quarantine skip + cap authority
# ─────────────────────────────────────────────────────────────────────────────

def test_emit_skips_sentinel_quarantined_and_unverified(tmp_path):
    """Sentinel-quarantined and crash-path-unverified items never reach the outbox."""
    from engine.marketing.outbox import emit_from_content_plan

    plan = _make_plan_fixture()
    q = plan["accounts"][0]["queue"]
    q[0]["status"] = "quarantined"                       # sentinel quarantine
    q[0]["sentinel_reasons"] = ["advice_lexicon:guaranteed"]
    q[1]["sentinel_ok"] = False                          # crash path stamp
    q[2]["sentinel_ok"] = True                           # explicit pass

    result = emit_from_content_plan(plan, root=tmp_path, cfg=_EMIT_CFG, day_prefix="D1")
    assert result["skipped_sentinel"] == 2, f"got: {result}"
    assert result["emitted"] == 1


def test_emit_missing_sentinel_field_passes_through(tmp_path):
    """Pre-D08 plans carry no sentinel_ok — emission behavior unchanged."""
    from engine.marketing.outbox import emit_from_content_plan

    result = emit_from_content_plan(_make_plan_fixture(), root=tmp_path, cfg=_EMIT_CFG, day_prefix="D1")
    assert result["emitted"] == 3
    assert result["skipped_sentinel"] == 0


def test_effective_cap_sentinel_config_is_authoritative():
    """D08 law: the actuator reads its cap from sentinel config; outbox may only lower it."""
    from engine.marketing.outbox import effective_cap

    assert effective_cap({"sentinel": {"max_posts_per_account_per_day": 2}}) == 2
    assert effective_cap({"sentinel": {"max_posts_per_account_per_day": 2},
                          "outbox": {"max_posts_per_account_per_day": 1}}) == 1
    assert effective_cap({"sentinel": {"max_posts_per_account_per_day": 2},
                          "outbox": {"max_posts_per_account_per_day": 10}}) == 2
    # Unlimited (-1): the autonomous-cadence policy. effective_cap returns -1 to
    # signal "no daily cap"; consumers treat a negative cap as unbounded.
    assert effective_cap({"sentinel": {"max_posts_per_account_per_day": -1}}) == -1
    # Outbox may still LOWER an unlimited Sentinel cap to a real number.
    assert effective_cap({"sentinel": {"max_posts_per_account_per_day": -1},
                          "outbox": {"max_posts_per_account_per_day": 5}}) == 5
    # Both unlimited → unlimited.
    assert effective_cap({"sentinel": {"max_posts_per_account_per_day": -1},
                          "outbox": {"max_posts_per_account_per_day": -1}}) == -1


def test_effective_cap_repo_config_is_unlimited():
    """The shipped config lifts the daily cap to unlimited (autonomous cadence,
    operator 2026-07-24) — effective_cap returns -1 (no bound). Was 2/day."""
    import yaml
    from engine.marketing.outbox import effective_cap

    cfg_path = Path(__file__).resolve().parent.parent / "config" / "marketing.yml"
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    assert effective_cap(cfg) == -1


# ─────────────────────────────────────────────────────────────────────────────
# 11. fold_state — single-pass rich fold
# ─────────────────────────────────────────────────────────────────────────────

def test_fold_state_basic(tmp_path):
    from engine.marketing.outbox import (
        enqueue, fold_state, record_decision, transition,
    )

    a = _make_minimal_item(tmp_path, text="Fold test post A.")
    b = _make_minimal_item(tmp_path, text="Fold test post B.")
    enqueue(a, root=tmp_path)
    enqueue(b, root=tmp_path)
    record_decision(a["id"], "hold", actor="op", root=tmp_path)
    transition(b["id"], "approved", actor="actuator", root=tmp_path)

    st = fold_state(tmp_path)
    assert st["order"] == [a["id"], b["id"]]
    assert st["status"][a["id"]] == "queued"
    assert st["status"][b["id"]] == "approved"
    assert st["held"] == {a["id"]}
    assert st["decisions"][a["id"]]["decision"] == "hold"
    assert st["last"][b["id"]]["to"] == "approved"
    assert st["attempts"] == {}


def test_fold_state_attempts_counts_failures(tmp_path):
    from engine.marketing.outbox import enqueue, fold_state, transition

    item = _make_minimal_item(tmp_path, text="Attempts counting post.")
    enqueue(item, root=tmp_path)
    transition(item["id"], "approved", actor="t", root=tmp_path)
    transition(item["id"], "failed", actor="t", root=tmp_path)
    transition(item["id"], "approved", actor="t", root=tmp_path)
    transition(item["id"], "failed", actor="t", root=tmp_path)

    st = fold_state(tmp_path)
    assert st["attempts"][item["id"]] == 2
    assert st["status"][item["id"]] == "failed"


# ─────────────────────────────────────────────────────────────────────────────
# 12. apply_decisions — batch approval application + governed retry
# ─────────────────────────────────────────────────────────────────────────────

def test_apply_decisions_approves_queued(tmp_path):
    from engine.marketing.outbox import (
        apply_decisions, current_statuses, enqueue, record_decision,
    )

    a = _make_minimal_item(tmp_path, text="Apply approve post.")
    b = _make_minimal_item(tmp_path, text="Apply hold post.")
    enqueue(a, root=tmp_path)
    enqueue(b, root=tmp_path)
    record_decision(a["id"], "approve", actor="op", root=tmp_path)
    record_decision(b["id"], "hold", actor="op", root=tmp_path)

    out = apply_decisions(tmp_path)
    assert out["approved"] == [a["id"]]
    assert out["rearmed"] == [] and out["quarantined"] == []
    st = current_statuses(tmp_path)
    assert st[a["id"]] == "approved"
    assert st[b["id"]] == "queued"  # hold never transitions


def test_apply_decisions_idempotent(tmp_path):
    from engine.marketing.outbox import apply_decisions, enqueue, record_decision, read_ledger

    item = _make_minimal_item(tmp_path, text="Idempotent apply post.")
    enqueue(item, root=tmp_path)
    record_decision(item["id"], "approve", actor="op", root=tmp_path)
    apply_decisions(tmp_path)
    n_rows = len(read_ledger(tmp_path))
    out2 = apply_decisions(tmp_path)
    assert out2 == {"approved": [], "rearmed": [], "quarantined": []}
    assert len(read_ledger(tmp_path)) == n_rows  # no duplicate rows


def test_apply_decisions_stale_approve_never_rearms_failed(tmp_path):
    """An approve recorded BEFORE the failure must not re-arm the item —
    a failure always needs a fresh human look (no silent retry-spam)."""
    from engine.marketing.outbox import (
        apply_decisions, current_statuses, enqueue, record_decision, transition,
    )

    item = _make_minimal_item(tmp_path, text="Stale approval post.")
    enqueue(item, root=tmp_path)
    record_decision(item["id"], "approve", actor="op", root=tmp_path)
    apply_decisions(tmp_path)                                   # queued → approved
    transition(item["id"], "failed", actor="t", root=tmp_path)  # post attempt failed

    out = apply_decisions(tmp_path)  # decision predates the failure
    assert out["rearmed"] == [] and out["quarantined"] == []
    assert current_statuses(tmp_path)[item["id"]] == "failed"


def test_apply_decisions_fresh_approve_rearms_failed(tmp_path):
    import time as _time
    from engine.marketing.outbox import (
        apply_decisions, current_statuses, enqueue, record_decision, transition,
    )

    item = _make_minimal_item(tmp_path, text="Fresh re-arm post.")
    enqueue(item, root=tmp_path)
    record_decision(item["id"], "approve", actor="op", root=tmp_path)
    apply_decisions(tmp_path)
    transition(item["id"], "failed", actor="t", root=tmp_path)
    _time.sleep(1.1)  # decision timestamps are second-granular ISO strings
    record_decision(item["id"], "approve", actor="op", root=tmp_path)

    out = apply_decisions(tmp_path)
    assert out["rearmed"] == [item["id"]]
    assert current_statuses(tmp_path)[item["id"]] == "approved"


def test_apply_decisions_quarantines_at_max_attempts(tmp_path):
    """Docket W1 §7: after MAX_POST_ATTEMPTS failures a fresh approval
    quarantines instead of re-arming — never retry-spam."""
    import time as _time
    from engine.marketing.outbox import (
        MAX_POST_ATTEMPTS, apply_decisions, current_statuses, enqueue,
        record_decision, transition,
    )

    item = _make_minimal_item(tmp_path, text="Max attempts post.")
    enqueue(item, root=tmp_path)
    record_decision(item["id"], "approve", actor="op", root=tmp_path)
    apply_decisions(tmp_path)
    for _ in range(MAX_POST_ATTEMPTS - 1):
        transition(item["id"], "failed", actor="t", root=tmp_path)
        transition(item["id"], "approved", actor="t", root=tmp_path)
    transition(item["id"], "failed", actor="t", root=tmp_path)  # attempt #MAX fails

    _time.sleep(1.1)
    record_decision(item["id"], "approve", actor="op", root=tmp_path)
    out = apply_decisions(tmp_path)
    assert out["quarantined"] == [item["id"]]
    assert current_statuses(tmp_path)[item["id"]] == "quarantined"


# ─────────────────────────────────────────────────────────────────────────────
# 13. Activity log + sentinel contract
# ─────────────────────────────────────────────────────────────────────────────

def test_emit_appends_activity_row(tmp_path):
    from engine.marketing.outbox import emit_from_content_plan, read_activity

    emit_from_content_plan(_make_plan_fixture(), root=tmp_path, cfg=_EMIT_CFG,
                           day_prefix="D1")
    rows = read_activity(tmp_path)
    assert len(rows) == 1
    row = rows[0]
    assert row["lane"] == "emit"
    assert row["emitted"] == 3
    assert row["skipped_gate"] == 1
    assert row["by_account"] == {"flagship": 3}


def test_actuator_appends_activity_row(tmp_path):
    from engine.marketing.outbox import emit_from_content_plan, read_activity

    emit_from_content_plan(_make_plan_fixture(), root=tmp_path, cfg=_EMIT_CFG,
                           day_prefix="D1")
    subprocess.run(
        [sys.executable, "scripts/marketing_actuator.py", "--dry-run", "--root", str(tmp_path)],
        cwd=str(ROOT), capture_output=True,
    )
    lanes = [r["lane"] for r in read_activity(tmp_path)]
    assert lanes == ["emit", "actuator_dry_run"]


def test_emit_default_cap_is_sentinel_floor(tmp_path):
    """With no cfg, emit enforces the Sentinel weeks_1_2 floor (2/day/account)
    at enqueue time — defense-in-depth even when the plan was never gated."""
    from engine.marketing.outbox import emit_from_content_plan

    result = emit_from_content_plan(_make_plan_fixture(), root=tmp_path,
                                    day_prefix="D1")
    assert result["emitted"] == 2
    assert result["skipped_cap"] == 1


def test_sentinel_contract_resolves_config_and_defaults():
    from engine.marketing.outbox import sentinel_contract

    c = sentinel_contract({})
    assert c["source"] == "sentinel_defaults"
    assert c["effective_cap"] == 2
    assert c["min_minutes_between_posts"] == 45  # 45-min ladder re-spec (2026-07-27)
    assert c["links_allowed"] is False

    c2 = sentinel_contract({"sentinel": {"max_posts_per_account_per_day": 4,
                                         "links_allowed": True}})
    assert c2["source"] == "config"
    assert c2["effective_cap"] == 4
    assert c2["links_allowed"] is True
    assert c2["min_minutes_between_posts"] == 45  # default fills the gap (45-min ladder)


def test_actuator_report_carries_sentinel_contract(tmp_path):
    from engine.marketing.outbox import emit_from_content_plan

    emit_from_content_plan(_make_plan_fixture(), root=tmp_path, cfg=_EMIT_CFG,
                           day_prefix="D1")
    subprocess.run(
        [sys.executable, "scripts/marketing_actuator.py", "--dry-run", "--root", str(tmp_path)],
        cwd=str(ROOT), capture_output=True,
    )
    report = json.loads(
        (tmp_path / "data" / "marketing" / "outbox" / "dryrun_report.json").read_text())
    assert "sentinel" in report
    assert report["sentinel"]["min_minutes_between_posts"] == 45  # 45-min ladder re-spec
    assert "applied_decisions" in report
    assert report["kill_switch"]["publish_enabled"] is False


def test_sentinel_contract_string_false_stays_false():
    """A quoted "false" in YAML must not silently enable links (D08 R2) —
    string bools parse strictly, mirroring sentinel.publish_enabled."""
    from engine.marketing.outbox import sentinel_contract

    c = sentinel_contract({"sentinel": {"links_allowed": "false"}})
    assert c["links_allowed"] is False
    c2 = sentinel_contract({"sentinel": {"links_allowed": "true"}})
    assert c2["links_allowed"] is True


def test_emit_stamps_tape_claim_source(tmp_path):
    """The publisher's live tape gate needs structured claim data on each item:
    ticker, thesis direction/entry/invalidation from the attached _plan, and a
    baseline_pct for same-day move claims. emit stamps them into item.source."""
    from engine.marketing.outbox import emit_from_content_plan, read_items

    plan = _make_plan_fixture()
    sig = plan["accounts"][0]["queue"][0]
    assert sig["type"] == "signal"
    sig["_plan"] = {"id": "prophet-NVDA-1", "direction": "BULL",
                    "entry": 950.0, "invalidation": 899.0}
    # A mover-shaped D1 item with baseline data.
    plan["accounts"][0]["queue"].append({
        "id": "post-flagship-006",
        "type": "mover",
        "account": "flagship",
        "cashtag": "$ISRG",
        "ticker": "ISRG",
        "headline": "$ISRG -14.2% today",
        "body": "Biggest drop in the index. Watching, not chasing.",
        "provenance": "movers_desk",
        "chart_id": None,
        "slot": "D1-EOD",
        "status": "drafted",
        "_mover_data": {"ticker": "ISRG", "pct": -14.2},
    })

    emit_from_content_plan(plan, root=tmp_path, cfg=_EMIT_CFG, day_prefix="D1")
    items = {i["source"].get("plan_item_id"): i for i in read_items(tmp_path)
             if i.get("source")}

    sig_item = items.get(sig["id"])
    assert sig_item is not None
    src = sig_item["source"]
    assert src["ticker"] == sig["ticker"]
    assert src["direction"] == "BULL"
    assert src["entry"] == 950.0
    assert src["invalidation"] == 899.0
    assert src["signal_id"] == "prophet-NVDA-1"

    mover_item = items.get("post-flagship-006")
    assert mover_item is not None
    assert mover_item["source"]["ticker"] == "ISRG"
    assert mover_item["source"]["baseline_pct"] == -14.2


# ─────────────────────────────────────────────────────────────────────────────
# F6: slot_datetime — real per-day advisory times (D2..D7 no longer read day-1)
# ─────────────────────────────────────────────────────────────────────────────

class TestSlotDatetime:
    def test_d1_is_as_of_day(self):
        from engine.marketing.outbox import slot_datetime
        assert slot_datetime("2026-07-20", "D1-AM") == "2026-07-20T14:00:00Z"
        assert slot_datetime("2026-07-20", "D1-PM") == "2026-07-20T17:30:00Z"
        assert slot_datetime("2026-07-20", "D1-EOD") == "2026-07-20T20:15:00Z"

    def test_later_days_offset_by_n_minus_one(self):
        from engine.marketing.outbox import slot_datetime
        # THE BUG: D3-AM used to map to as_of T14:00 (day-1). Now +2 days.
        assert slot_datetime("2026-07-20", "D3-AM") == "2026-07-22T14:00:00Z"
        assert slot_datetime("2026-07-20", "D7-EOD") == "2026-07-26T20:15:00Z"

    def test_ladder_pacific_slots_summer_pdt(self):
        """Gate 5: the 30-min ladder (S1..S28) resolves to Pacific-clock UTC.
        July = PDT (UTC-7): S1 4:00 AM→11:00, S5 6:00 AM→13:00, S8 7:30 AM→14:30,
        S28 5:30 PM→00:30 next-day.

        Re-pinned 2026-07-28 when the ladder went 45-min/19-slot → 30-min/28-slot
        so flagship could hold a 30-minute cadence. The WINDOW is deliberately
        unchanged (4:00 AM–5:30 PM local) — only the step tightened, so the first
        and last rungs still land where they always did and no post moved into
        low-engagement hours."""
        from engine.marketing.outbox import slot_datetime
        assert slot_datetime("2026-07-15", "D1-S1") == "2026-07-15T11:00:00Z"   # 4:00 AM
        assert slot_datetime("2026-07-15", "D1-S5") == "2026-07-15T13:00:00Z"   # 6:00 AM
        assert slot_datetime("2026-07-15", "D1-S8") == "2026-07-15T14:30:00Z"   # 7:30 AM
        assert slot_datetime("2026-07-15", "D1-S28") == "2026-07-16T00:30:00Z"  # 5:30 PM

    def test_ladder_step_is_thirty_minutes_end_to_end(self):
        """The step is the contract flagship's cadence rests on, so pin it
        directly rather than inferring it from two sampled rungs: every adjacent
        pair is exactly 30 minutes apart and the span is 28 rungs."""
        from datetime import datetime, timezone

        from engine.marketing.outbox import _LADDER_PT_TIMES, slot_datetime

        assert len(_LADDER_PT_TIMES) == 28
        stamps = [slot_datetime("2026-07-15", f"D1-S{i}") for i in range(1, 29)]
        assert all(s is not None for s in stamps), "a ladder rung resolves to no time"
        parsed = [datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                  for s in stamps]
        gaps = {int((b - a).total_seconds() // 60) for a, b in zip(parsed, parsed[1:])}
        assert gaps == {30}, f"ladder step is not a uniform 30 min: {sorted(gaps)}"

    def test_ladder_pacific_slots_winter_pst(self):
        """Gate 5: the SAME local slots shift +1h in UTC under PST (winter) —
        DST handled by zoneinfo, never a hardcoded offset."""
        from engine.marketing.outbox import slot_datetime
        assert slot_datetime("2026-01-15", "D1-S1") == "2026-01-15T12:00:00Z"   # 4:00 AM PST
        assert slot_datetime("2026-01-15", "D1-S28") == "2026-01-16T01:30:00Z"  # 5:30 PM PST

    def test_ladder_day_offset(self):
        """D<n> offsets by n-1 days, then resolves the Pacific slot on THAT date."""
        from engine.marketing.outbox import slot_datetime
        assert slot_datetime("2026-07-15", "D2-S1") == "2026-07-16T11:00:00Z"

    def test_immediate_and_unparseable_return_none(self):
        from engine.marketing.outbox import slot_datetime
        assert slot_datetime("2026-07-20", "MOVER-01") is None
        assert slot_datetime("2026-07-20", "THEME-02") is None
        assert slot_datetime("2026-07-20", "CONF-01") is None
        assert slot_datetime("2026-07-20", "immediate") is None
        assert slot_datetime("2026-07-20", "D1-XX") is None   # unknown time suffix
        assert slot_datetime("not-a-date", "D1-AM") is None   # bad as_of

    def test_scheduled_at_wrapper_preserves_immediate_contract(self):
        from engine.marketing.outbox import _scheduled_at_for_slot
        assert _scheduled_at_for_slot("D2-PM", "2026-07-20") == "2026-07-21T17:30:00Z"
        assert _scheduled_at_for_slot("MOVER-01", "2026-07-20") == "immediate"


# ─────────────────────────────────────────────────────────────────────────────
# Slot-prefix refusals are COUNTED, and the unemittable ones are ANNOUNCED
# (X Growth wave 1, 2026-07-31)
#
# The skip on a non-D1 slot is the oldest gate in emit_from_content_plan and it
# incremented nothing: the 2026-07-31 activity row read every counter zero while
# six live movers/theme_list items were discarded, which reads identically to
# "the plan was empty". These pin the counter, the family split, and the two
# opposite annotation behaviours (forward ladder = silence, non-day label =
# ::warning at line start).
# ─────────────────────────────────────────────────────────────────────────────

def _slot_plan(as_of: str, slots: list[str]) -> dict:
    """A plan whose queue is one distinct item per slot label."""
    return {
        "as_of": as_of,
        "accounts": [
            {
                "id": "flagship",
                "queue": [
                    {
                        "id": f"post-slot-{n:03d}",
                        "type": "macro",
                        "account": "flagship",
                        "cashtag": "",
                        "ticker": "",
                        "headline": f"Slot probe {n}.",
                        "body": _DISTINCT_TEXTS[n % len(_DISTINCT_TEXTS)],
                        "provenance": "neural_web",
                        "chart_id": None,
                        "slot": slot,
                        "status": "drafted",
                    }
                    for n, slot in enumerate(slots)
                ],
            }
        ],
        "featured_charts": [],
    }


class TestSkippedSlotMismatch:
    def test_non_d1_slot_is_counted_not_silent(self, tmp_path):
        """THE DEFECT: a MOVER-/THEME- slot vanished through a bare `continue`.

        Pins the counter itself — pre-fix this key did not exist, so the emit
        summary could not distinguish "nothing to say" from "six posts thrown
        away".
        """
        from engine.marketing.outbox import emit_from_content_plan

        plan = _slot_plan(_AS_OF, ["MOVER-01", "THEME-02", "D1-AM"])
        result = emit_from_content_plan(plan, root=tmp_path, cfg=_EMIT_CFG,
                                        day_prefix="D1")

        assert result["emitted"] == 1
        assert result["skipped_slot_mismatch"] == 2, result

    def test_family_breakdown_separates_ladder_from_unemittable(self, tmp_path):
        """D2..D7 and MOVER-/THEME-/CONF- are both skipped and are NOT the same
        event: the forward ladder is regenerated nightly by design, a non-day
        label is a lane that can never publish. The breakdown is what lets an
        operator tell them apart in the activity row."""
        from engine.marketing.outbox import emit_from_content_plan

        plan = _slot_plan(_AS_OF, ["D2-AM", "D7-PM", "MOVER-01", "CONF-01",
                                   "THEME-03", "D1-AM"])
        result = emit_from_content_plan(plan, root=tmp_path, cfg=_EMIT_CFG,
                                        day_prefix="D1")

        assert result["skipped_slot_mismatch"] == 5, result
        assert result["skipped_slot_by_family"] == {
            "D2": 1, "D7": 1, "MOVER": 1, "CONF": 1, "THEME": 1,
        }, result

    def test_counter_reaches_the_activity_row(self, tmp_path):
        """The activity row is the surface an operator actually reads; a counter
        that only lives in the return value would have left the same silence."""
        from engine.marketing.outbox import emit_from_content_plan

        emit_from_content_plan(_slot_plan(_AS_OF, ["MOVER-01", "D1-AM"]),
                               root=tmp_path, cfg=_EMIT_CFG, day_prefix="D1")

        rows = [
            json.loads(line)
            for line in (tmp_path / "data" / "marketing" / "outbox" /
                         "activity.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        emit_rows = [r for r in rows if r.get("lane") == "emit"]
        assert emit_rows, rows
        assert emit_rows[-1]["skipped_slot_mismatch"] == 1
        assert emit_rows[-1]["skipped_slot_by_family"] == {"MOVER": 1}

    def test_unemittable_family_warns_at_line_start(self, tmp_path, capsys):
        """A non-day label gets a GitHub annotation, and it must START the line —
        this module's logger prefixes its records, so a logged annotation is
        silently dropped by Actions (tests/test_gh_annotation_line_start.py)."""
        from engine.marketing.outbox import emit_from_content_plan

        emit_from_content_plan(_slot_plan(_AS_OF, ["MOVER-01", "THEME-02", "D1-AM"]),
                               root=tmp_path, cfg=_EMIT_CFG, day_prefix="D1")

        out = capsys.readouterr().out
        hits = [ln for ln in out.splitlines()
                if "marketing_unemittable_slots" in ln]
        assert hits, out
        assert hits[0].startswith("::warning title=marketing_unemittable_slots::"), hits
        assert "MOVER=1" in hits[0] and "THEME=1" in hits[0]

    def test_forward_ladder_alone_raises_no_alarm(self, tmp_path, capsys):
        """~800 D2..D7 items are skipped every night BY DESIGN. Warning on them
        would fire nightly and train the operator to ignore the annotation that
        matters."""
        from engine.marketing.outbox import emit_from_content_plan

        result = emit_from_content_plan(_slot_plan(_AS_OF, ["D2-AM", "D3-PM", "D1-AM"]),
                                        root=tmp_path, cfg=_EMIT_CFG, day_prefix="D1")

        assert result["skipped_slot_mismatch"] == 2
        assert "marketing_unemittable_slots" not in capsys.readouterr().out


# ─────────────────────────────────────────────────────────────────────────────
# The movers desk actually REACHES the outbox (X Growth wave 1, 2026-07-31)
# ─────────────────────────────────────────────────────────────────────────────

def _write_heatmaps(root: Path) -> None:
    """Minimal sp500 + themes heatmap fixtures — enough supply for 2 movers and
    2 theme lists (movers_source needs |pct| >= 3.0 and >= 4 theme members)."""
    md = root / "site" / "marketdata"
    md.mkdir(parents=True, exist_ok=True)
    (md / "sp500_heatmap.json").write_text(json.dumps({
        "asof": _AS_OF,
        "tiles": [
            {"t": "AAPL", "name": "Apple", "sector": "Technology",
             "perf": {"1D": 7.5}},
            {"t": "NVDA", "name": "NVIDIA", "sector": "Technology",
             "perf": {"1D": -9.1}},
            {"t": "AMD", "name": "AMD", "sector": "Technology",
             "perf": {"1D": -6.2}},
        ],
    }), encoding="utf-8")
    (md / "themes_heatmap.json").write_text(json.dumps({
        "tiles": [
            {"t": "aicompute", "name": "Compute",
             "sector": "Artificial Intelligence", "perf": {"1D": -3.0},
             "members": [{"t": "NVDA", "perf": {"1D": -4.5}},
                         {"t": "AMD", "perf": {"1D": -6.2}},
                         {"t": "SMCI", "perf": {"1D": -5.1}},
                         {"t": "AVGO", "perf": {"1D": -3.8}},
                         {"t": "MRVL", "perf": {"1D": -2.5}}]},
            {"t": "biotech", "name": "Biotech Core",
             "sector": "Healthcare & Biotech", "perf": {"1D": 2.5},
             "members": [{"t": "AMGN", "perf": {"1D": 4.2}},
                         {"t": "BIIB", "perf": {"1D": 3.1}},
                         {"t": "REGN", "perf": {"1D": 2.8}},
                         {"t": "GILD", "perf": {"1D": 1.9}},
                         {"t": "VRTX", "perf": {"1D": 2.2}}]},
        ],
    }), encoding="utf-8")


def test_movers_desk_items_reach_the_outbox(tmp_path):
    """END TO END, and it is the whole defect: content_plan mints mover /
    theme_list posts and emit_from_content_plan must QUEUE them.

    Pre-fix the movers desk stamped MOVER-NN / THEME-NN, emit dropped every slot
    that is not "D1-", and the desk published nothing from 2026-07-19 onward
    while every plan carried its items. The assertion is on outbox KINDS, so it
    fails on the pre-fix engine no matter how the plan is shaped.
    """
    from engine.marketing.content_studio import content_plan
    from engine.marketing.outbox import emit_from_content_plan, read_items
    from tests.test_marketing_content import _SAMPLE_ACCOUNTS, _SAMPLE_PLANS

    _write_heatmaps(tmp_path)
    cfg = {"desk_network": {"stage": "A", "accounts": _SAMPLE_ACCOUNTS},
           "sentinel": {"max_posts_per_account_per_day": 8}}
    plan = content_plan(cfg, _SAMPLE_PLANS, closes_loader=None, root=tmp_path)

    reach = [it for acct in plan["accounts"] for it in acct["queue"]
             if it.get("provenance") == "movers_desk"]
    assert reach, "fixture produced no movers-desk items"
    assert all(str(it["slot"]).startswith("D1-") for it in reach), (
        f"reach items still carry an unemittable slot: "
        f"{[it['slot'] for it in reach]}")

    emit_from_content_plan(plan, root=tmp_path, cfg=cfg, day_prefix="D1")
    kinds = {i["kind"] for i in read_items(tmp_path)}
    assert {"mover", "theme_list"} & kinds, (
        f"movers desk reached no outbox item; kinds={sorted(kinds)}")


# ─────────────────────────────────────────────────────────────────────────────
# X Growth W1g — a post may not be scheduled before it existed.
#
# THE DEFECT (2026-07-25..31 audit): 41 items shipped with `scheduled_at`
# EARLIER than their own `created_at` — a D1 slot ladder resolved against the
# CONTENT date while the run itself happened hours later, so an item written at
# 15:46Z was booked for 13:00Z the same day. The publisher reads "due in the
# past" as due NOW, so the whole ladder collapsed into one undifferentiated
# backlog and posted back-to-back, and every "was this late?" measurement
# downstream was poisoned at birth.
# ─────────────────────────────────────────────────────────────────────────────

class TestScheduleFloorAtEnqueue:
    def _backdated(self, *, text="Backdated slot test about $PLTR levels."):
        from engine.marketing.outbox import make_item
        return make_item(
            account="flagship", kind="signal", text=text, as_of=_AS_OF,
            provenance="content_studio", slot="D1-S1",
            # created 12:00Z (_FIXED_NOW), booked for 09:00Z the same day
            scheduled_at="2026-07-19T09:00:00Z", now=_FIXED_NOW,
        )

    def test_a_slot_before_creation_is_clamped_forward(self, tmp_path):
        from engine.marketing.outbox import enqueue, read_items
        item = self._backdated()
        assert enqueue(item, root=tmp_path) == "queued"
        row = read_items(root=tmp_path)[0]
        assert row["scheduled_at"] >= row["created_at"], (
            f"queued a post scheduled {row['scheduled_at']} before it was "
            f"created {row['created_at']}"
        )
        assert row["scheduled_at"] == "2026-07-19T12:00:00Z", row["scheduled_at"]

    def test_the_original_slot_is_preserved_for_diagnosis(self, tmp_path):
        """Silently tidying a lane's bad slots hides the lane that emits them."""
        from engine.marketing.outbox import enqueue, read_items
        assert enqueue(self._backdated(), root=tmp_path) == "queued"
        row = read_items(root=tmp_path)[0]
        assert (row.get("source") or {}).get("scheduled_at_original") == \
            "2026-07-19T09:00:00Z", row.get("source")

    def test_a_future_slot_is_left_exactly_alone(self, tmp_path):
        from engine.marketing.outbox import make_item, enqueue, read_items
        item = make_item(
            account="flagship", kind="signal",
            text="Future slot test about $NVDA and the tape.", as_of=_AS_OF,
            provenance="content_studio", slot="D1-S6",
            scheduled_at="2026-07-19T22:00:00Z", now=_FIXED_NOW,
        )
        assert enqueue(item, root=tmp_path) == "queued"
        assert read_items(root=tmp_path)[0]["scheduled_at"] == "2026-07-19T22:00:00Z"

    def test_immediate_is_not_a_time_and_is_never_rewritten(self, tmp_path):
        from engine.marketing.outbox import make_item, enqueue, read_items
        item = make_item(
            account="flagship", kind="signal",
            text="Immediate post about $AMD and the chip tape.", as_of=_AS_OF,
            provenance="content_studio", scheduled_at="immediate", now=_FIXED_NOW,
        )
        assert enqueue(item, root=tmp_path) == "queued"
        assert read_items(root=tmp_path)[0]["scheduled_at"] == "immediate"

    def test_the_clamp_does_not_change_the_item_id(self, tmp_path):
        """The id hashes (account, kind, text, as_of) — if the clamp fed into it,
        dedupe would break for every clamped item."""
        from engine.marketing.outbox import enqueue, read_items
        item = self._backdated()
        wanted = item["id"]
        assert enqueue(item, root=tmp_path) == "queued"
        assert read_items(root=tmp_path)[0]["id"] == wanted

    def test_the_caller_sees_the_same_schedule_the_ledger_does(self, tmp_path):
        """The clamp mutates in place on purpose: the governor lanes log and
        index off the dict they handed in."""
        from engine.marketing.outbox import enqueue
        item = self._backdated()
        assert enqueue(item, root=tmp_path) == "queued"
        assert item["scheduled_at"] == "2026-07-19T12:00:00Z", item["scheduled_at"]
