"""tests/test_marketing_recall.py — kill-switch recall of booked-but-unsent posts.

THE HOLE UNDER TEST. publish.max_forward_book_min (#3913) lets one sweep book
several posts as Buffer customScheduled sends up to an hour out. Those live in
Buffer's queue, so MARKETING_PUBLISH_ENABLED=0 — which only stops the runner
creating NEW posts — does not stop them. On 2026-07-28 a 16:25:46Z sweep booked
five posts through 17:27Z, the operator disarmed 61 seconds later, and all five
still fired.

Mirrors tests/test_marketing_social_publisher.py: tmp_path for all file I/O,
injected now= for determinism, engine modules imported INSIDE each test, and
ZERO live network — every HTTP path goes through the publisher's single
_transport() seam or a fake publisher.

The three gates this suite exists to hold:
  1. a booked-but-unsent post can be cancelled and lands in a status that does
     NOT let it re-send (`recalled` is terminal in outbox.TRANSITIONS);
  2. an ALREADY-SENT post is never double-counted or resurrected — it is not a
     candidate, it stays `posted`, and it keeps consuming its daily-cap slot;
  3. the dry-run path makes ZERO network calls.
Plus the precondition all of it rests on: the publisher persists the Buffer post
id in the `posting → posted` receipt. Without that, recall is impossible.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


_FIXED_NOW = datetime(2026, 7, 28, 16, 26, 47, tzinfo=timezone.utc)   # the disarm
_AS_OF = "2026-07-28"
_TS_FMT = "%Y-%m-%dT%H:%M:%SZ"


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures / helpers
# ─────────────────────────────────────────────────────────────────────────────

def _seed_posted_item(
    tmp_path: Path,
    *,
    text: str = "$PLTR reclaimed the 50-day. Watching the soldiers now.",
    account: str = "flagship",
    as_of: str = _AS_OF,
    external_id: str | None = "buf-post-1",
    booked_at: datetime | None = None,
    receipt_overrides: dict | None = None,
) -> str:
    """Enqueue one item and drive it queued→approved→posting→posted.

    The `posted` transition carries the SAME receipt shape the live publisher
    writes (scripts/marketing_publisher.py), because that receipt is the only
    place the Buffer post id and the booked send time survive.
    """
    from engine.marketing.outbox import make_item, enqueue, transition
    item = make_item(
        account=account, kind="signal", text=text, as_of=as_of,
        scheduled_at="immediate", provenance="content_studio", now=_FIXED_NOW,
    )
    enqueue(item, root=tmp_path, max_per_account_day=99)
    iid = item["id"]
    transition(iid, "approved", actor="test", root=tmp_path, now=_FIXED_NOW)
    transition(iid, "posting", actor="test", root=tmp_path, now=_FIXED_NOW)

    receipt: dict = {
        "backend": "buffer",
        "external_id": external_id,
        "external_url": None,
        "at": _FIXED_NOW.strftime(_TS_FMT),
        "booked_at": (booked_at or (_FIXED_NOW + timedelta(minutes=5))).strftime(_TS_FMT),
    }
    if receipt_overrides is not None:
        receipt.update(receipt_overrides)
    transition(iid, "posted", actor="test", root=tmp_path, now=_FIXED_NOW,
               note="published", receipt=receipt)
    return iid


class _FakePublisher:
    """Stand-in backend that records delete calls and never touches the network."""

    backend = "buffer"

    def __init__(self, *, ok: bool = True, error: str | None = None) -> None:
        self._ok = ok
        self._error = error
        self.deleted: list[str] = []

    def delete_post(self, post_id: str, *, now=None):
        from engine.marketing.social_publisher import DeleteResult
        self.deleted.append(post_id)
        at = (now or _FIXED_NOW).strftime(_TS_FMT)
        if self._ok:
            return DeleteResult(True, post_id, None, self.backend, at)
        return DeleteResult(False, None, self._error or "buffer_error: nope",
                            self.backend, at)


class _ExplodingPublisher:
    """Any use at all is a test failure — proves a path made no backend call."""

    backend = "buffer"

    def delete_post(self, post_id: str, *, now=None):  # pragma: no cover
        raise AssertionError(
            f"delete_post({post_id!r}) called on a path that must not touch the backend")


def _run_recall(monkeypatch, tmp_path: Path, argv: list[str], *,
                fake_publisher=None, token: str = "test-token",
                now: datetime = _FIXED_NOW) -> int:
    """Invoke the recall runner main() in-process with a controlled environment."""
    import scripts.marketing_recall as rc

    if token:
        monkeypatch.setenv("BUFFER_TOKEN", token)
    else:
        monkeypatch.delenv("BUFFER_TOKEN", raising=False)
    if fake_publisher is not None:
        monkeypatch.setattr(rc, "_make_publisher",
                            lambda backend, *, token, cfg: fake_publisher)
    return rc.main(list(argv) + ["--root", str(tmp_path),
                                 "--now", now.strftime(_TS_FMT)])


def _status_of(tmp_path: Path, iid: str) -> str:
    from engine.marketing.outbox import fold_state
    return fold_state(tmp_path)["status"][iid]


# ─────────────────────────────────────────────────────────────────────────────
# 1. The precondition: the publisher persists the Buffer post id
# ─────────────────────────────────────────────────────────────────────────────

def test_publisher_posted_receipt_persists_the_buffer_post_id():
    """scripts/marketing_publisher.py must write receipt.external_id on posted.

    If the id is not persisted, recall is structurally impossible — there is
    nothing to hand deletePost. This reads the committed source rather than
    re-running the publisher so it stays a standing guard on the one field the
    whole recall path depends on, independent of any fixture.
    """
    src = (Path(__file__).resolve().parent.parent
           / "scripts" / "marketing_publisher.py").read_text(encoding="utf-8")
    # The posted transition and its receipt block.
    idx = src.find('iid, "posted", actor="publisher"')
    assert idx > 0, "the posting→posted transition moved — re-point this guard"
    block = src[idx:idx + 900]
    assert '"external_id": receipt.external_id' in block, (
        "the posted receipt no longer persists the Buffer post id — recall "
        "becomes impossible without it")
    assert '"booked_at"' in block, (
        "the posted receipt no longer persists booked_at — recall needs it to "
        "tell a booked post from one that already sent")


def test_recall_receipt_shape_matches_what_the_publisher_writes(tmp_path):
    """The fixture's receipt keys are the publisher's keys (drift tripwire)."""
    from engine.marketing.outbox import fold_state
    iid = _seed_posted_item(tmp_path)
    rec = fold_state(tmp_path)["last"][iid]["receipt"]
    assert set(rec) >= {"backend", "external_id", "at", "booked_at"}


# ─────────────────────────────────────────────────────────────────────────────
# 2. GATE 1 — a booked-but-unsent post is cancelled and cannot re-send
# ─────────────────────────────────────────────────────────────────────────────

def test_booked_but_unsent_post_is_cancelled_and_recalled(tmp_path, monkeypatch):
    iid = _seed_posted_item(tmp_path, external_id="buf-post-42",
                            booked_at=_FIXED_NOW + timedelta(minutes=5))
    fake = _FakePublisher()

    rc = _run_recall(monkeypatch, tmp_path, ["--recall-pending", "--live"],
                     fake_publisher=fake)

    assert rc == 0
    assert fake.deleted == ["buf-post-42"], "the Buffer post id must be cancelled"
    assert _status_of(tmp_path, iid) == "recalled"


def test_recalled_is_terminal_and_cannot_re_send(tmp_path, monkeypatch):
    """A recalled item may not walk back to approved/queued/posting/posted.

    This is the "lands in a status that does not let it re-send" gate. It is
    asserted twice over — through the public transition() API AND against the
    status machine itself — because a future edit could loosen either one.
    """
    from engine.marketing.outbox import TRANSITIONS, transition, read_ledger

    iid = _seed_posted_item(tmp_path)
    _run_recall(monkeypatch, tmp_path, ["--recall-pending", "--live"],
                fake_publisher=_FakePublisher())
    assert _status_of(tmp_path, iid) == "recalled"

    assert TRANSITIONS["recalled"] == frozenset(), "recalled must stay TERMINAL"

    before = len(read_ledger(root=tmp_path))
    for target in ("approved", "queued", "posting", "posted", "quarantined", "failed"):
        assert transition(iid, target, actor="test", root=tmp_path) is False, (
            f"recalled → {target} must be refused")
    assert len(read_ledger(root=tmp_path)) == before, (
        "a refused transition must not append to the ledger")
    assert _status_of(tmp_path, iid) == "recalled"


def test_recalled_item_is_not_selected_by_the_publisher(tmp_path):
    """End of the line: the publisher's own selector must never pick it up."""
    from engine.marketing.outbox import fold_state
    from scripts.marketing_publisher import _select_approved_due

    iid = _seed_posted_item(tmp_path)
    from engine.marketing.outbox import transition
    transition(iid, "recalled", actor="test", root=tmp_path, now=_FIXED_NOW)

    state = fold_state(tmp_path)
    due = _select_approved_due(state, state["status"], state["items"],
                               None, _FIXED_NOW + timedelta(hours=2))
    assert [i["id"] for i in due] == []


def test_recall_writes_a_retraction_row_to_publications(tmp_path, monkeypatch):
    """The Channels page must stop claiming a post that never went out."""
    from engine.marketing.ledgers import read_jsonl

    iid = _seed_posted_item(tmp_path, external_id="buf-post-7")
    _run_recall(monkeypatch, tmp_path, ["--recall-pending", "--live"],
                fake_publisher=_FakePublisher())

    rows = read_jsonl(tmp_path / "data" / "marketing" / "publications.jsonl")
    assert len(rows) == 1
    row = rows[0]
    assert row["correction_state"] == "retracted"
    assert row["asset_id"] == iid
    assert row["remote_id"] == "buf-post-7"


def test_publications_summary_folds_a_retraction_over_its_original(tmp_path):
    """A retraction SUPERSEDES its original row — it is not a second publication.

    publications.jsonl is append-only, so the correction arrives as a new row
    with the same publication_id. engine.marketing.state must fold last-row-wins
    or a recalled post inflates total_publications while also counting as a
    correction — the ledger reporting one post as both published and retracted.
    """
    from engine.marketing.ledgers import append_jsonl
    from engine.marketing import state as _state

    pubs = tmp_path / "data" / "marketing" / "publications.jsonl"
    append_jsonl(pubs, {"publication_id": "pub-a", "asset_id": "a", "channel": "x",
                        "account": "flagship", "published_at": "2026-07-28T16:31:00Z",
                        "campaign_id": "c", "correction_state": "clean"})
    append_jsonl(pubs, {"publication_id": "pub-a", "asset_id": "a", "channel": "x",
                        "account": "flagship", "published_at": "2026-07-28T16:31:00Z",
                        "campaign_id": "c", "correction_state": "retracted"})

    summary = _state.build_state(root=tmp_path)
    pub_block = ((summary.get("pipeline") or {}).get("publications")) or {}
    assert pub_block.get("total") == 1, "a retraction must not count as a 2nd publication"
    assert pub_block.get("receipts") == 1
    assert pub_block.get("corrections") == 1
    assert [p["status"] for p in pub_block["newest"]] == ["retracted"], (
        "the surviving row must be the correction, not the row it corrects")


# ─────────────────────────────────────────────────────────────────────────────
# 3. GATE 2 — an already-sent post is never resurrected or double-counted
# ─────────────────────────────────────────────────────────────────────────────

def test_already_sent_post_is_never_recalled(tmp_path, monkeypatch):
    """booked_at in the PAST = it went out. Untouchable, and no backend call.

    _ExplodingPublisher makes the assertion structural: if the candidate rule
    ever admits a sent post, the delete attempt itself fails the test rather
    than the status assertion catching it after the fact.
    """
    iid = _seed_posted_item(tmp_path, external_id="buf-post-sent",
                            booked_at=_FIXED_NOW - timedelta(minutes=1))

    rc = _run_recall(monkeypatch, tmp_path, ["--recall-pending", "--live"],
                     fake_publisher=_ExplodingPublisher())

    assert rc == 0
    assert _status_of(tmp_path, iid) == "posted", "a sent post must stay posted"


def test_already_sent_post_keeps_consuming_its_daily_cap_slot(tmp_path, monkeypatch):
    """No double-counting: the sent post still counts, the recalled one does not.

    posted_today_by_account is the Sentinel's post-time cap counter. A sent post
    must keep its slot (or the account silently over-posts); a recalled post must
    release its slot (or the recall shrinks the day's real volume by exactly the
    number of posts the operator pulled — the opposite of the point).
    """
    from engine.marketing.outbox import fold_state, posted_today_by_account

    sent = _seed_posted_item(tmp_path, text="Already went out — the tape agreed.",
                             external_id="buf-sent",
                             booked_at=_FIXED_NOW - timedelta(minutes=1))
    booked = _seed_posted_item(tmp_path, text="Booked for 16:31 and never seen.",
                               external_id="buf-booked",
                               booked_at=_FIXED_NOW + timedelta(minutes=5))
    today = _FIXED_NOW.strftime("%Y-%m-%d")

    before = posted_today_by_account(fold_state(tmp_path), today)
    assert before["flagship"] == 2

    _run_recall(monkeypatch, tmp_path, ["--recall-pending", "--live"],
                fake_publisher=_FakePublisher())

    after = posted_today_by_account(fold_state(tmp_path), today)
    assert _status_of(tmp_path, sent) == "posted"
    assert _status_of(tmp_path, booked) == "recalled"
    assert after["flagship"] == 1, (
        "the sent post must still count; only the recalled one releases its slot")


def test_a_failed_delete_leaves_the_item_posted_and_goes_red(tmp_path, monkeypatch):
    """Fail CLOSED. No confirmed delete → no status change, and a red exit.

    A post we could not cancel is still scheduled to fire. Marking it recalled
    would be the exact resurrection-in-reverse this design forbids, and exiting
    0 would hide from the operator that the recall did not work.
    """
    iid = _seed_posted_item(tmp_path, external_id="buf-post-stubborn")
    fake = _FakePublisher(ok=False, error="buffer_error: post already published")

    rc = _run_recall(monkeypatch, tmp_path, ["--recall-pending", "--live"],
                     fake_publisher=fake)

    assert rc == 1, "a failed recall must be RED — those posts are still going out"
    assert fake.deleted == ["buf-post-stubborn"]
    assert _status_of(tmp_path, iid) == "posted"


def test_unreadable_send_time_is_not_recalled(tmp_path, monkeypatch):
    """Fail closed on a send time we cannot parse — never guess and delete."""
    iid = _seed_posted_item(
        tmp_path, external_id="buf-post-x",
        receipt_overrides={"booked_at": "not-a-timestamp", "at": "also-not-one"})
    # The ledger row's own `at` is the last fallback; blank it so nothing parses.
    ledger = tmp_path / "data" / "marketing" / "outbox" / "status_ledger.jsonl"
    rows = [json.loads(ln) for ln in ledger.read_text().splitlines() if ln.strip()]
    for r in rows:
        if r.get("to") == "posted":
            r["at"] = ""
    ledger.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")

    rc = _run_recall(monkeypatch, tmp_path, ["--recall-pending", "--live"],
                     fake_publisher=_ExplodingPublisher())
    assert rc == 0
    assert _status_of(tmp_path, iid) == "posted"


def test_posted_item_without_an_external_id_is_not_recalled(tmp_path, monkeypatch):
    """No stored Buffer id → nothing to cancel. Report, never guess."""
    iid = _seed_posted_item(tmp_path, external_id=None)
    rc = _run_recall(monkeypatch, tmp_path, ["--recall-pending", "--live"],
                     fake_publisher=_ExplodingPublisher())
    assert rc == 0
    assert _status_of(tmp_path, iid) == "posted"


# ─────────────────────────────────────────────────────────────────────────────
# 4. GATE 3 — the dry-run path makes ZERO network calls
# ─────────────────────────────────────────────────────────────────────────────

def test_dry_run_makes_no_network_calls_and_no_ledger_writes(tmp_path, monkeypatch):
    from engine.marketing.outbox import read_ledger

    iid = _seed_posted_item(tmp_path, external_id="buf-post-9")
    before = len(read_ledger(root=tmp_path))

    rc = _run_recall(monkeypatch, tmp_path, ["--recall-pending"],
                     fake_publisher=_ExplodingPublisher())

    assert rc == 0
    assert _status_of(tmp_path, iid) == "posted"
    assert len(read_ledger(root=tmp_path)) == before
    assert not (tmp_path / "data" / "marketing" / "publications.jsonl").exists()


def test_dry_run_never_builds_a_publisher_at_all(tmp_path, monkeypatch):
    """Not even instantiation — the dry-run must not need a token or a backend.

    Stronger than "no HTTP": it proves the dry-run path never reaches the code
    that could open a socket, so it stays safe to run on a machine with a live
    BUFFER_TOKEN in the environment.
    """
    import scripts.marketing_recall as rc_mod

    _seed_posted_item(tmp_path, external_id="buf-post-10")

    def _boom(*a, **k):  # pragma: no cover
        raise AssertionError("_make_publisher must not be called in a dry-run")

    monkeypatch.setattr(rc_mod, "_make_publisher", _boom)
    monkeypatch.setenv("BUFFER_TOKEN", "a-real-looking-token")
    assert rc_mod.main(["--recall-pending", "--root", str(tmp_path),
                        "--now", _FIXED_NOW.strftime(_TS_FMT)]) == 0


def test_live_without_a_token_is_red_and_touches_nothing(tmp_path, monkeypatch):
    """--live with no BUFFER_TOKEN cannot cancel anything — say so, in red."""
    iid = _seed_posted_item(tmp_path, external_id="buf-post-11")
    rc = _run_recall(monkeypatch, tmp_path, ["--recall-pending", "--live"],
                     fake_publisher=_ExplodingPublisher(), token="")
    assert rc == 1
    assert _status_of(tmp_path, iid) == "posted"


# ─────────────────────────────────────────────────────────────────────────────
# 5. Selection: ids, filters, and the refusal to sweep unscoped
# ─────────────────────────────────────────────────────────────────────────────

def test_ids_selection_recalls_only_the_named_item(tmp_path, monkeypatch):
    keep = _seed_posted_item(tmp_path, text="Leave this one alone entirely.",
                             external_id="buf-keep")
    target = _seed_posted_item(tmp_path, text="Pull this one back right now.",
                               external_id="buf-target")
    fake = _FakePublisher()

    rc = _run_recall(monkeypatch, tmp_path, ["--ids", target, "--live"],
                     fake_publisher=fake)

    assert rc == 0
    assert fake.deleted == ["buf-target"]
    assert _status_of(tmp_path, target) == "recalled"
    assert _status_of(tmp_path, keep) == "posted"


def test_account_filter_scopes_a_sweep(tmp_path, monkeypatch):
    a = _seed_posted_item(tmp_path, account="flagship", text="Flagship desk read.",
                          external_id="buf-a")
    b = _seed_posted_item(tmp_path, account="macro", text="Macro desk read here.",
                          external_id="buf-b")
    fake = _FakePublisher()

    _run_recall(monkeypatch, tmp_path,
                ["--recall-pending", "--account", "macro", "--live"],
                fake_publisher=fake)

    assert fake.deleted == ["buf-b"]
    assert _status_of(tmp_path, a) == "posted"
    assert _status_of(tmp_path, b) == "recalled"


def test_unscoped_run_refuses_rather_than_sweeping(tmp_path, monkeypatch):
    """Neither --ids nor --recall-pending → refuse. Filters narrow, not authorise."""
    iid = _seed_posted_item(tmp_path, external_id="buf-post-12")
    rc = _run_recall(monkeypatch, tmp_path, ["--account", "flagship", "--live"],
                     fake_publisher=_ExplodingPublisher())
    assert rc == 2
    assert _status_of(tmp_path, iid) == "posted"


def test_select_candidates_is_pure_and_reports_named_skips(tmp_path):
    """A named id that cannot be recalled comes back with a REASON, not silence."""
    from engine.marketing.outbox import fold_state
    from scripts.marketing_recall import (
        select_candidates, SKIP_ALREADY_SENT, SKIP_NO_RECEIPT,
    )

    sent = _seed_posted_item(tmp_path, text="This one already went out today.",
                             external_id="buf-sent",
                             booked_at=_FIXED_NOW - timedelta(minutes=1))
    no_id = _seed_posted_item(tmp_path, text="This one lost its receipt id.",
                              external_id=None)
    live_one = _seed_posted_item(tmp_path, text="This one is still pending.",
                                 external_id="buf-live")

    recallable, skipped = select_candidates(
        fold_state(tmp_path), now=_FIXED_NOW,
        ids=frozenset({sent, no_id, live_one}))

    assert [c["id"] for c in recallable] == [live_one]
    reasons = {s["id"]: s["reason"] for s in skipped}
    assert reasons[sent] == SKIP_ALREADY_SENT
    assert reasons[no_id] == SKIP_NO_RECEIPT


def test_a_named_id_that_does_not_exist_still_gets_an_answer(tmp_path):
    """A typo'd id must come back as unknown, not vanish into silence."""
    from engine.marketing.outbox import fold_state
    from scripts.marketing_recall import select_candidates, SKIP_UNKNOWN_ID

    live_one = _seed_posted_item(tmp_path, external_id="buf-live")
    recallable, skipped = select_candidates(
        fold_state(tmp_path), now=_FIXED_NOW,
        ids=frozenset({live_one, "ob-does-not-exist"}))

    assert [c["id"] for c in recallable] == [live_one]
    assert {s["id"]: s["reason"] for s in skipped} == {
        "ob-does-not-exist": SKIP_UNKNOWN_ID}


# ─────────────────────────────────────────────────────────────────────────────
# 6. The Buffer deletePost adapter (transport mocked — zero live traffic)
# ─────────────────────────────────────────────────────────────────────────────

def test_buffer_delete_post_success(monkeypatch):
    from engine.marketing.social_publisher import BufferPublisher

    pub = BufferPublisher(token="tok")
    seen: dict = {}

    def fake_transport(payload):
        seen.update(payload)
        return {"data": {"deletePost": {"__typename": "DeletePostSuccess",
                                        "id": "buf-post-1"}}}

    monkeypatch.setattr(pub, "_transport", fake_transport)
    res = pub.delete_post("buf-post-1", now=_FIXED_NOW)

    assert res.ok is True
    assert res.external_id == "buf-post-1"
    assert res.error is None
    # The documented mutation shape (developers.buffer.com, confirmed 2026-07-28).
    assert "deletePost" in seen["query"]
    assert "DeletePostInput!" in seen["query"]
    assert "... on MutationError" in seen["query"], (
        "the MutationError catch-all is the documented way to receive a message "
        "from an error member the query does not name (e.g. VoidMutationError)")
    assert seen["variables"] == {"input": {"id": "buf-post-1"}}


def test_buffer_delete_post_mutation_error_union(monkeypatch):
    from engine.marketing.social_publisher import BufferPublisher

    pub = BufferPublisher(token="tok")
    monkeypatch.setattr(pub, "_transport", lambda payload: {
        "data": {"deletePost": {"__typename": "VoidMutationError",
                                "message": "post not found"}}})
    res = pub.delete_post("gone", now=_FIXED_NOW)
    assert res.ok is False
    assert "post not found" in res.error


def test_buffer_delete_post_graphql_error(monkeypatch):
    from engine.marketing.social_publisher import BufferPublisher

    pub = BufferPublisher(token="tok")
    monkeypatch.setattr(pub, "_transport",
                        lambda payload: {"errors": [{"message": "unauthorized"}]})
    res = pub.delete_post("buf-1", now=_FIXED_NOW)
    assert res.ok is False
    assert "unauthorized" in res.error


def test_buffer_delete_post_no_id_in_payload_is_not_a_success(monkeypatch):
    """An ambiguous payload must NOT be read as a confirmed delete."""
    from engine.marketing.social_publisher import BufferPublisher

    pub = BufferPublisher(token="tok")
    monkeypatch.setattr(pub, "_transport",
                        lambda payload: {"data": {"deletePost": {}}})
    res = pub.delete_post("buf-1", now=_FIXED_NOW)
    assert res.ok is False


def test_buffer_delete_post_network_error_no_raise(monkeypatch):
    from engine.marketing.social_publisher import BufferPublisher

    pub = BufferPublisher(token="tok")

    def boom(payload):
        raise OSError("connection reset")

    monkeypatch.setattr(pub, "_transport", boom)
    res = pub.delete_post("buf-1", now=_FIXED_NOW)
    assert res.ok is False
    assert res.external_id is None


def test_buffer_delete_post_empty_id_fails_soft(monkeypatch):
    from engine.marketing.social_publisher import BufferPublisher

    pub = BufferPublisher(token="tok")
    monkeypatch.setattr(pub, "_transport", lambda payload: (_ for _ in ()).throw(
        AssertionError("must not reach the transport for an empty id")))
    res = pub.delete_post("  ", now=_FIXED_NOW)
    assert res.ok is False
    assert res.error == "empty_post_id"


def test_buffer_delete_post_empty_token_fails_soft(monkeypatch):
    """No token → _transport raises; delete_post must convert, never raise."""
    from engine.marketing.social_publisher import BufferPublisher

    monkeypatch.delenv("BUFFER_TOKEN", raising=False)
    res = BufferPublisher(token="").delete_post("buf-1", now=_FIXED_NOW)
    assert res.ok is False


# ─────────────────────────────────────────────────────────────────────────────
# 7. Downstream readers stop treating a recalled post as a real one
# ─────────────────────────────────────────────────────────────────────────────

def test_recalled_text_does_not_block_its_own_replacement(tmp_path, monkeypatch):
    """The operator recalls in order to REPLACE the copy.

    A recalled item left in the near-dup corpus would veto its own rewrite as a
    near-duplicate of a post nobody ever saw — turning the recall into a lockout.
    """
    from engine.marketing.outbox import make_item, enqueue

    text = "$PLTR reclaimed the 50-day. Watching the soldiers now."
    _seed_posted_item(tmp_path, text=text, external_id="buf-dup")
    _run_recall(monkeypatch, tmp_path, ["--recall-pending", "--live"],
                fake_publisher=_FakePublisher())

    replacement = make_item(
        account="flagship", kind="signal", text=text, as_of="2026-07-29",
        scheduled_at="immediate", provenance="content_studio", now=_FIXED_NOW)
    assert enqueue(replacement, root=tmp_path, max_per_account_day=99) == "queued"


def test_metrics_poller_skips_a_retracted_post(tmp_path, monkeypatch):
    """A post that never went out has no analytics to poll."""
    from scripts.marketing_metrics_poll import gather_targets

    _seed_posted_item(tmp_path, external_id="buf-gone")
    _run_recall(monkeypatch, tmp_path, ["--recall-pending", "--live"],
                fake_publisher=_FakePublisher())

    targets = gather_targets(tmp_path, now=_FIXED_NOW + timedelta(hours=1),
                             max_age_days=7)
    assert [t["remote_id"] for t in targets] == []


def test_admin_outbox_panel_counts_recalled(tmp_path, monkeypatch):
    from admin import marketing as _am

    _seed_posted_item(tmp_path, external_id="buf-panel")
    _run_recall(monkeypatch, tmp_path, ["--recall-pending", "--live"],
                fake_publisher=_FakePublisher())

    panel = _am.outbox(root=str(tmp_path))
    assert panel["ok"] is True
    assert panel["summary"]["recalled"] == 1
    assert panel["summary"]["posted"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# 8. The admin DISARM toggle dispatches the recall
# ─────────────────────────────────────────────────────────────────────────────

def test_disarm_dispatches_a_recall(monkeypatch):
    """DISARM must mean STOP — including posts already handed to Buffer."""
    from admin import marketing as _am
    from admin import github_api as _gh

    calls: list[dict] = []
    monkeypatch.setattr(_gh, "token", lambda: "gh-token")
    monkeypatch.setattr(_gh, "set_repo_variable", lambda name, value: True)
    monkeypatch.setattr(_gh, "dispatch",
                        lambda **kw: (calls.append(kw), {"ok": True})[1])

    res = _am.arm_publisher(False)

    assert res["ok"] is True
    assert res["enabled"] is False
    assert res["recall"]["ok"] is True
    assert calls and calls[0]["inputs"] == {"recall_pending": "true"}
    assert calls[0]["workflow"] == "marketing-publish.yml"


def test_arming_does_not_dispatch_a_recall(monkeypatch):
    from admin import marketing as _am
    from admin import github_api as _gh

    calls: list[dict] = []
    monkeypatch.setattr(_gh, "token", lambda: "gh-token")
    monkeypatch.setattr(_gh, "set_repo_variable", lambda name, value: True)
    monkeypatch.setattr(_gh, "dispatch",
                        lambda **kw: (calls.append(kw), {"ok": True})[1])

    res = _am.arm_publisher(True)

    assert res["ok"] is True
    assert "recall" not in res
    assert calls == []


def test_a_failed_recall_dispatch_does_not_fail_the_disarm(monkeypatch):
    """The disarm already succeeded. Report the recall honestly, don't undo it."""
    from admin import marketing as _am
    from admin import github_api as _gh

    monkeypatch.setattr(_gh, "token", lambda: "gh-token")
    monkeypatch.setattr(_gh, "set_repo_variable", lambda name, value: True)
    monkeypatch.setattr(_gh, "dispatch",
                        lambda **kw: {"ok": False, "error": "HTTP 403 — no Actions scope"})

    res = _am.arm_publisher(False)

    assert res["ok"] is True, "the variable write succeeded — do not report failure"
    assert res["enabled"] is False
    assert res["recall"]["ok"] is False
    assert "WILL still send" in res["note"], (
        "an operator whose recall did not dispatch must be told the booked posts "
        "are still going out")


# ─────────────────────────────────────────────────────────────────────────────
# 9. The workflow wiring — or it ships dark
# ─────────────────────────────────────────────────────────────────────────────

def _publish_workflow() -> dict:
    yaml = pytest.importorskip("yaml")
    path = (Path(__file__).resolve().parent.parent
            / ".github" / "workflows" / "marketing-publish.yml")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_workflow_exposes_the_recall_input_and_step():
    wf = _publish_workflow()
    # `on:` parses as the boolean True in YAML 1.1.
    inputs = wf[True]["workflow_dispatch"]["inputs"]
    assert "recall_pending" in inputs

    steps = wf["jobs"]["publish"]["steps"]
    recall = [s for s in steps if "marketing_recall" in str(s.get("run") or "")]
    assert len(recall) == 1, "the recall step must exist exactly once"
    assert "--recall-pending" in recall[0]["run"]
    assert "--live" in recall[0]["run"]
    assert "inputs.recall_pending" in recall[0]["if"]


def test_workflow_skips_the_publisher_on_a_recall_run():
    steps = _publish_workflow()["jobs"]["publish"]["steps"]
    publisher = [s for s in steps
                 if "scripts.marketing_publisher" in str(s.get("run") or "")]
    assert len(publisher) == 1
    assert "inputs.recall_pending" in publisher[0]["if"], (
        "a recall run must not also publish")


def test_workflow_commits_the_ledger_on_a_recall_run():
    """The recall's own ledger writes must survive.

    The operator sets MARKETING_PUBLISH_ENABLED=0 and the recall runs moments
    later, so the commit step's `== '1'` armed test is false by construction.
    Without the recall clause every recall would cancel the posts at Buffer and
    then throw away the record — main would still read `posted`.
    """
    steps = _publish_workflow()["jobs"]["publish"]["steps"]
    commit = [s for s in steps if "commit changed outbox ledgers" in str(s.get("name") or "")]
    assert len(commit) == 1
    cond = str(commit[0]["if"])
    assert "MARKETING_PUBLISH_ENABLED == '1'" in cond
    assert "inputs.recall_pending" in cond


def test_workflow_skips_the_jitter_sleep_on_a_recall_run():
    """A recall races posts due in minutes — it must not sleep first."""
    steps = _publish_workflow()["jobs"]["publish"]["steps"]
    jitter = [s for s in steps if "humanizing jitter" in str(s.get("name") or "")]
    assert len(jitter) == 1
    assert "inputs.recall_pending" in str(jitter[0]["if"])


def test_recall_suite_is_wired_into_ci():
    """An unrun suite guards nothing (the test-whitelist-rot failure mode)."""
    root = Path(__file__).resolve().parent.parent
    jobs = (root / ".github" / "ci" / "legacy-jobs.yml").read_text(encoding="utf-8")
    assert "tests/test_marketing_recall.py" in jobs, (
        "wire the suite into the marketing-engine lane or it ships dark")
    ci = (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "tests/test_marketing_recall.py" in ci, (
        "add the suite to ci.yml's trigger paths or edits to it run nothing")
    assert "scripts/marketing_recall.py" in ci, (
        "add the runner to ci.yml's trigger paths or edits to it run nothing")
