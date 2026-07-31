"""tests/test_marketing_rewrite.py — a rewrite SUPERSEDES, it never appends.

THE DEFECT (X Growth audit, 2026-07-25..31). The `claude_rewrite` lane appended
its rewritten items at the original's slot instead of replacing it: cici's
2026-07-28 17:00 slot held THREE near-identical $FDS posts (one content_studio
original plus two rewrites, all carrying the same `source.plan_item_id`), and the
week ran 46 same-account-same-minute collisions.

THE SECOND, QUIETER DEFECT. `scripts/marketing_requeue_stale_copy` had the right
intent and the wrong ORDER: it enqueued the replacement first and quarantined the
original second. `outbox.enqueue` rejects near-duplicates against a same-account
7-day corpus at token-Jaccard >= 0.7, and a rewrite of a post is by construction
a near-duplicate of that post — so every light rewrite it attempted was refused
as "duplicate" and the stale copy stayed queued. `_enqueue_ctx` excludes DEAD ids
from that corpus, which is why retiring the original FIRST is what makes the
replacement admissible at all.

Covers: supersede (original leaves the queue when the rewrite lands), the
ordering that makes it possible, idempotence on a second run, and the refusal
paths that must never leave two live versions of one post.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest


_FIXED_NOW = datetime(2026, 7, 28, 15, 46, 0, tzinfo=timezone.utc)
_AS_OF = "2026-07-28"

# The live collision, close enough that the near-dup guard sees them as one post
# (token Jaccard well above 0.7) — which is exactly the point.
_ORIGINAL_TEXT = (
    "$FDS is 2.4% off its high\n\n"
    "FDS at 247.10 against a 52-week high of 272.40. That's close enough that "
    "the high itself is the level that matters: clear it and there's no "
    "overhead supply left, fail it again and this is the second rejection from "
    "the same place."
)
_REWRITE_TEXT = (
    "$FDS is 2.4% off its high\n\n"
    "FDS at 247.10 against a 52-week high of 272.40. That's close enough that "
    "the high itself is the level that matters: clear it and there's no "
    "overhead supply left, fail it and the range keeps its ceiling."
)


def _item(text: str, *, account: str = "cici", slot: str = "D1-S13") -> dict:
    from engine.marketing.outbox import make_item
    return make_item(
        account=account, kind="watchlist", text=text, as_of=_AS_OF,
        scheduled_at="2026-07-28T17:00:00Z", slot=slot, provenance="claude_rewrite",
        source={"plan_item_id": "post-cici-013", "ticker": "FDS"},
        now=_FIXED_NOW,
    )


def _live_texts(root: Path) -> list[str]:
    from engine.marketing.outbox import fold_state
    from engine.marketing.rewrite import TERMINAL_STATUSES
    state = fold_state(root)
    return [
        it["text"] for iid, it in state["items"].items()
        if str(state["status"].get(iid) or "queued") not in TERMINAL_STATUSES
    ]


def _queue_original(root: Path) -> dict:
    from engine.marketing.outbox import enqueue
    original = _item(_ORIGINAL_TEXT)
    assert enqueue(original, root=root) == "queued"
    return original


class TestRewriteSupersedes:
    def test_the_original_leaves_the_queue_when_the_rewrite_lands(self, tmp_path):
        from engine.marketing.rewrite import apply_rewrite
        original = _queue_original(tmp_path)
        new = _item(_REWRITE_TEXT)

        res = apply_rewrite(original["id"], new, root=tmp_path, actor="test")

        assert res["ok"] and res["outcome"] == "superseded", res
        live = _live_texts(tmp_path)
        assert live == [_REWRITE_TEXT], (
            f"the queue holds {len(live)} live version(s) of one post: {live}"
        )

    def test_the_enqueue_is_not_refused_as_a_near_duplicate_of_its_own_original(
            self, tmp_path):
        """The ordering defect, pinned directly: enqueue-then-quarantine cannot
        work because the original vetoes its own replacement."""
        from engine.marketing.outbox import enqueue
        from engine.marketing.rewrite import apply_rewrite
        original = _queue_original(tmp_path)

        # Enqueue-first (the old order) is REFUSED — proving the fix is the
        # ordering, not a cosmetic refactor.
        assert enqueue(_item(_REWRITE_TEXT), root=tmp_path) == "duplicate"

        # Quarantine-first (apply_rewrite) admits the very same copy.
        res = apply_rewrite(original["id"], _item(_REWRITE_TEXT), root=tmp_path,
                            actor="test")
        assert res["ok"], res
        assert res["enqueue"] == "queued", res

    def test_the_replacement_names_what_it_replaced(self, tmp_path):
        from engine.marketing.outbox import read_items
        from engine.marketing.rewrite import apply_rewrite
        original = _queue_original(tmp_path)
        new = _item(_REWRITE_TEXT)
        apply_rewrite(original["id"], new, root=tmp_path, actor="test")
        queued = [i for i in read_items(tmp_path) if i["id"] == new["id"]]
        assert queued and queued[0]["source"]["supersedes"] == original["id"], queued

    def test_a_second_run_adds_nothing(self, tmp_path):
        """Idempotence falls out of the same rule: the original is terminal, so
        the repeat is a no-op instead of a third copy."""
        from engine.marketing.outbox import read_items
        from engine.marketing.rewrite import apply_rewrite
        original = _queue_original(tmp_path)
        apply_rewrite(original["id"], _item(_REWRITE_TEXT), root=tmp_path, actor="t")
        n_after_first = len(read_items(tmp_path))

        res = apply_rewrite(original["id"], _item(_REWRITE_TEXT), root=tmp_path,
                            actor="t")
        assert not res["ok"] and res["outcome"] == "original_not_live", res
        assert len(read_items(tmp_path)) == n_after_first
        assert len(_live_texts(tmp_path)) == 1

    def test_identical_copy_is_a_no_op_not_a_churn(self, tmp_path):
        from engine.marketing.outbox import read_items
        from engine.marketing.rewrite import apply_rewrite
        original = _queue_original(tmp_path)
        res = apply_rewrite(original["id"], _item(_ORIGINAL_TEXT), root=tmp_path,
                            actor="test")
        assert res["outcome"] == "unchanged", res
        assert len(read_items(tmp_path)) == 1
        assert _live_texts(tmp_path) == [_ORIGINAL_TEXT]

    def test_an_invalid_replacement_never_costs_the_day_its_original(self, tmp_path):
        from engine.marketing.rewrite import apply_rewrite
        original = _queue_original(tmp_path)
        broken = _item(_REWRITE_TEXT)
        broken["kind"] = "not_a_kind"
        res = apply_rewrite(original["id"], broken, root=tmp_path, actor="test")
        assert not res["ok"] and res["outcome"].startswith("invalid:"), res
        assert _live_texts(tmp_path) == [_ORIGINAL_TEXT]

    def test_a_terminal_original_is_left_alone(self, tmp_path):
        from engine.marketing.outbox import transition
        from engine.marketing.rewrite import apply_rewrite
        original = _queue_original(tmp_path)
        transition(original["id"], "quarantined", actor="operator", root=tmp_path)
        res = apply_rewrite(original["id"], _item(_REWRITE_TEXT), root=tmp_path,
                            actor="test")
        assert res["outcome"] == "original_not_live", res
        assert _live_texts(tmp_path) == []

    def test_an_unknown_original_queues_nothing(self, tmp_path):
        from engine.marketing.outbox import read_items
        from engine.marketing.rewrite import apply_rewrite
        res = apply_rewrite("ob-does-not-exist", _item(_REWRITE_TEXT),
                            root=tmp_path, actor="test")
        assert res["outcome"] == "original_unknown", res
        assert read_items(tmp_path) == []

    def test_a_lost_slot_is_loud(self, tmp_path, capsys):
        """If the replacement is refused AFTER the original is retired, the slot
        is empty and terminal — that has to reach the Actions summary."""
        from engine.marketing import rewrite as _rw
        original = _queue_original(tmp_path)

        def _refuse(*_a, **_k):
            return "cap_exceeded"

        import engine.marketing.outbox as _ob
        real = _ob.enqueue
        _ob.enqueue = _refuse
        try:
            res = _rw.apply_rewrite(original["id"], _item(_REWRITE_TEXT),
                                    root=tmp_path, actor="test")
        finally:
            _ob.enqueue = real
        assert res["outcome"] == "enqueue_failed:cap_exceeded", res
        out = capsys.readouterr().out
        assert any(line.startswith("::warning") for line in out.splitlines()), out
        assert "marketing_rewrite_slot_lost" in out


class TestLiveItemsFor:
    def test_it_counts_only_live_items_of_that_lane_and_day(self, tmp_path):
        from engine.marketing.outbox import enqueue, transition
        from engine.marketing.rewrite import live_items_for
        keep = _item(_ORIGINAL_TEXT)
        assert enqueue(keep, root=tmp_path) == "queued"
        other_day = _item("A totally different watchlist note on $NVDA levels.")
        other_day["as_of"] = "2026-07-29"
        other_day["id"] = keep["id"] + "-x"
        assert enqueue(other_day, root=tmp_path) == "queued"

        found = live_items_for(root=tmp_path, account="cici", as_of=_AS_OF,
                               provenance="claude_rewrite")
        assert [i["id"] for i in found] == [keep["id"]], found

        transition(keep["id"], "quarantined", actor="op", root=tmp_path)
        assert live_items_for(root=tmp_path, account="cici", as_of=_AS_OF,
                              provenance="claude_rewrite") == []
