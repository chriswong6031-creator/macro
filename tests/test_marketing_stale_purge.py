"""tests/test_marketing_stale_purge.py — the one-off broom for an outage backlog.

Mirrors tests/test_marketing_outbox.py: tmp_path for all file I/O, injected now=
for determinism, engine module imported INSIDE each test, zero network.

WHAT IS BEING PINNED. The Buffer plan locked around 2026-08-05 and the
publisher's rate-limit branch requeued every refused item back to `approved` on
every 30-minute sweep, so by 08-08 the queue held a pile of undeliverable posts
about sessions that had closed. `scripts/marketing_stale_purge.py` retires that
pile before the plan renews. The properties that matter are all "what it must NOT
touch": anything terminal, anything fresh, and anything whose birth stamp cannot
be read.

Run: TZ=UTC python3 -m pytest tests/test_marketing_stale_purge.py -q
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest


_CUTOFF = datetime(2026, 8, 8, 0, 0, 0, tzinfo=timezone.utc)
_OLD = datetime(2026, 8, 6, 9, 30, 0, tzinfo=timezone.utc)     # before the cutoff
_NEW = datetime(2026, 8, 8, 9, 30, 0, tzinfo=timezone.utc)     # after it
_PURGE_NOW = datetime(2026, 8, 8, 12, 0, 0, tzinfo=timezone.utc)


def _seed(tmp_path, *, text: str, created: datetime, account: str = "flagship",
          kind: str = "signal", to: str | None = None) -> str:
    """One enqueued item, optionally driven to a further status. Returns its id."""
    from engine.marketing.outbox import make_item, enqueue, transition
    item = make_item(account=account, kind=kind, text=text,
                     as_of=created.strftime("%Y-%m-%d"), scheduled_at="immediate",
                     provenance="content_studio", now=created)
    enqueue(item, root=tmp_path, max_per_account_day=99)
    for step in (to or "").split(">"):
        step = step.strip()
        if step:
            assert transition(item["id"], step, actor="test", root=tmp_path,
                              now=created), f"could not reach {step}"
    return item["id"]


@pytest.fixture()
def seeded(tmp_path):
    """A queue with every shape the purge has to tell apart."""
    ids = {
        "old_queued": _seed(
            tmp_path, text="Old queued post about Monday's close.", created=_OLD),
        "old_approved": _seed(
            tmp_path, text="Old approved post, armed and undeliverable.",
            created=_OLD, to="approved"),
        "old_approved_other_desk": _seed(
            tmp_path, text="Another desk, same outage, different words.",
            created=_OLD, account="kelly", kind="macro", to="approved"),
        "fresh_queued": _seed(
            tmp_path, text="Written this morning about this morning.",
            created=_NEW),
        "old_posted": _seed(
            tmp_path, text="This one actually went out before the lock.",
            created=_OLD, to="approved>posting>posted"),
        "old_quarantined": _seed(
            tmp_path, text="Already retired by an earlier sweep.",
            created=_OLD, to="quarantined"),
        "old_failed": _seed(
            tmp_path, text="Failed for a reason of its very own.",
            created=_OLD, to="approved>failed"),
    }
    return tmp_path, ids


def _purge(tmp_path, *, live: bool, now=_PURGE_NOW):
    from scripts.marketing_stale_purge import purge
    return purge(tmp_path, _CUTOFF, live=live, now=now)


# ─────────────────────────────────────────────────────────────────────────────
# Selection
# ─────────────────────────────────────────────────────────────────────────────

def test_it_takes_the_stale_live_items_and_nothing_else(seeded):
    tmp_path, ids = seeded
    from engine.marketing.outbox import current_statuses

    out = _purge(tmp_path, live=True)
    assert out["purged"] == 3, out
    assert not out["refused"]

    statuses = current_statuses(tmp_path)
    for key in ("old_queued", "old_approved", "old_approved_other_desk"):
        assert statuses[ids[key]] == "quarantined", key
    # Fresh copy is the whole point of a cutoff — it must survive untouched.
    assert statuses[ids["fresh_queued"]] == "queued"
    # Terminal states are somebody else's record, not the broom's.
    assert statuses[ids["old_posted"]] == "posted"
    assert statuses[ids["old_quarantined"]] == "quarantined"
    # `failed` is re-armable but deliberately out of scope: an item is there for
    # a reason of its own, and burying it under "the backlog was stale" erases it.
    assert statuses[ids["old_failed"]] == "failed"


def test_the_note_travels_with_every_row(seeded):
    tmp_path, ids = seeded
    from engine.marketing.ledgers import read_jsonl
    from scripts.marketing_stale_purge import DEFAULT_NOTE

    _purge(tmp_path, live=True)
    rows = [r for r in read_jsonl(
        tmp_path / "data" / "marketing" / "outbox" / "status_ledger.jsonl")
        if r.get("actor") == "stale_purge"]
    assert len(rows) == 3
    assert {r["note"] for r in rows} == {DEFAULT_NOTE}
    assert {r["to"] for r in rows} == {"quarantined"}
    # Plain words for the human reading the quarantine view, and a greppable key.
    assert "stale_purge_2026-08-08" in DEFAULT_NOTE
    assert "no longer fresh" in DEFAULT_NOTE


def test_the_summary_counts_by_account_and_kind(seeded):
    tmp_path, _ = seeded
    out = _purge(tmp_path, live=False)
    assert out["selected"] == 3
    assert out["by_account_kind"] == {"flagship/signal": 2, "kelly/macro": 1}


# ─────────────────────────────────────────────────────────────────────────────
# The two properties an operator actually relies on
# ─────────────────────────────────────────────────────────────────────────────

def test_a_dry_run_writes_nothing(seeded):
    tmp_path, ids = seeded
    from engine.marketing.outbox import current_statuses

    before = dict(current_statuses(tmp_path))
    out = _purge(tmp_path, live=False)

    assert out["selected"] == 3
    assert out["purged"] == 0
    assert current_statuses(tmp_path) == before, (
        "the dry run mutated the ledger — quarantine is TERMINAL and a "
        "projection must not destroy the queue it is projecting")


def test_it_is_idempotent(seeded):
    """Second run = zero changes. Not by a marker file: a purged item's folded
    status is `quarantined`, which is not selectable, so the selection itself is
    what makes the re-run empty."""
    tmp_path, _ = seeded
    from engine.marketing.ledgers import read_jsonl

    first = _purge(tmp_path, live=True)
    ledger = tmp_path / "data" / "marketing" / "outbox" / "status_ledger.jsonl"
    rows_after_first = len(list(read_jsonl(ledger)))

    second = _purge(tmp_path, live=True)

    assert first["purged"] == 3
    assert second["selected"] == 0
    assert second["purged"] == 0
    assert len(list(read_jsonl(ledger))) == rows_after_first, (
        "the re-run appended ledger rows — a broom that keeps sweeping the same "
        "floor writes a growing ledger about nothing")


# ─────────────────────────────────────────────────────────────────────────────
# Birth stamps
# ─────────────────────────────────────────────────────────────────────────────

def test_an_unreadable_created_stamp_is_never_purged(tmp_path):
    """UNKNOWN is not OLD. A malformed field must never be why a post dies."""
    from engine.marketing.outbox import current_statuses, fold_state
    from scripts.marketing_stale_purge import select_stale

    iid = _seed(tmp_path, text="Perfectly good post, broken stamp.", created=_OLD)
    state = fold_state(tmp_path)
    state["items"][iid]["created_at"] = "not-a-timestamp"
    state["items"][iid]["as_of"] = ""

    assert select_stale(state, _CUTOFF) == []
    assert current_statuses(tmp_path)[iid] == "queued"


def test_as_of_is_the_fallback_when_created_at_is_missing(tmp_path):
    """Pre-stamp rows have no created_at; a date-only floor still dates them."""
    from engine.marketing.outbox import fold_state
    from scripts.marketing_stale_purge import select_stale

    iid = _seed(tmp_path, text="An older row with no birth stamp.", created=_OLD)
    state = fold_state(tmp_path)
    state["items"][iid].pop("created_at", None)
    state["items"][iid]["as_of"] = "2026-08-05"

    assert [i["id"] for i in select_stale(state, _CUTOFF)] == [iid]


def test_an_item_created_exactly_at_the_cutoff_survives(tmp_path):
    """The cutoff is exclusive — "created BEFORE this" means before it."""
    from engine.marketing.outbox import fold_state
    from scripts.marketing_stale_purge import select_stale

    _seed(tmp_path, text="Born on the stroke of the cutoff.", created=_CUTOFF)
    assert select_stale(fold_state(tmp_path), _CUTOFF) == []


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def test_cli_defaults_to_a_dry_run(seeded, capsys):
    tmp_path, _ = seeded
    from engine.marketing.outbox import current_statuses
    from scripts.marketing_stale_purge import main

    before = dict(current_statuses(tmp_path))
    rc = main(["--cutoff", "2026-08-08T00:00:00Z", "--root", str(tmp_path)])
    assert rc == 0
    assert current_statuses(tmp_path) == before


def test_cli_rejects_an_unparseable_cutoff(tmp_path):
    from scripts.marketing_stale_purge import main
    assert main(["--cutoff", "last tuesday", "--root", str(tmp_path)]) == 2


def test_cli_live_writes_the_ledger(seeded):
    tmp_path, ids = seeded
    from engine.marketing.outbox import current_statuses
    from scripts.marketing_stale_purge import main

    assert main(["--cutoff", "2026-08-08T00:00:00Z", "--root", str(tmp_path),
                 "--live"]) == 0
    assert current_statuses(tmp_path)[ids["old_approved"]] == "quarantined"
