"""tests/test_marketing_lane_rerun.py — a lane re-run must REPLACE, not duplicate.

2026-07-26: two governor runs wrote the same day. enqueue() dedupes on an item
id that make_item() derives from the item's CONTENT, so the moment the copy
improved the second run minted new ids and landed a full second set beside the
first. The operator deleted eight duplicates by hand.

The fix is two halves, and both are needed:
  * supersede_lane()      — retire the previous run's undecided items
  * decided_source_keys() — do not GENERATE a competitor for a settled slot

Miss the second half and an approved post survives (correctly) while its
replacement queues beside it (wrongly), and the ticker posts twice.
"""
from __future__ import annotations

import pytest

from engine.marketing.outbox import (
    decided_source_keys,
    enqueue,
    fold_state,
    make_item,
    record_decision,
    supersede_lane,
)

AS_OF = "2026-07-26"
LANE = "weekend_levels"


@pytest.fixture()
def repo(tmp_path):
    (tmp_path / "data" / "marketing" / "outbox").mkdir(parents=True)
    return tmp_path


def _mk(ticker, text):
    return make_item(account="flagship", kind="watchlist", text=text, as_of=AS_OF,
                     provenance=LANE, source={"ticker": ticker})


def _governor_run(repo, texts):
    """The governor's enqueue path, as wired in marketing_governor."""
    items = [_mk(tk, tx) for tk, tx in texts.items()]
    settled = decided_source_keys(account="flagship", as_of=AS_OF,
                                  provenance=LANE, root=repo)
    items = [i for i in items if i["source"]["ticker"] not in settled]
    queued = {i["id"] for i in items
              if enqueue(i, root=repo, max_per_account_day=-1) == "queued"}
    if queued:
        supersede_lane(account="flagship", as_of=AS_OF, provenance=LANE,
                       keep_ids=queued, root=repo, actor="marketing_governor")
    return settled


def _live(repo):
    st = fold_state(repo)
    return {st["items"][k]["source"]["ticker"]: st["items"][k]["text"].splitlines()[0]
            for k in st["items"] if st["status"][k] != "quarantined"}


OLD = {"TSLA": "$TSLA into the week\n\nA.", "MSFT": "$MSFT into the week\n\nB."}
NEW = {"TSLA": "Eight weeks down, new low. No thanks.\n\nA.",
       "MSFT": "$MSFT keeps leaking\n\nB."}


def test_rerun_replaces_instead_of_duplicating(repo):
    """The actual incident: two runs, eight duplicates."""
    _governor_run(repo, OLD)
    assert len(_live(repo)) == 2

    _governor_run(repo, NEW)
    live = _live(repo)
    assert len(live) == 2, f"a re-run duplicated the set: {live}"
    assert live["TSLA"].startswith("Eight weeks down")
    assert live["MSFT"] == "$MSFT keeps leaking"


def test_rerun_is_idempotent(repo):
    """Same copy twice must not grow the queue."""
    _governor_run(repo, NEW)
    _governor_run(repo, NEW)
    _governor_run(repo, NEW)
    assert len(_live(repo)) == 2


def test_an_approved_post_survives_and_gets_no_competitor(repo):
    """Replacing an approved post takes the operator's yes back; queueing a
    second one for the same ticker posts it twice. Neither is acceptable."""
    _governor_run(repo, OLD)
    st = fold_state(repo)
    tsla = next(k for k, i in st["items"].items() if i["source"]["ticker"] == "TSLA")
    record_decision(tsla, "approve", actor="admin", root=repo)

    skipped = _governor_run(repo, NEW)
    assert skipped == {"TSLA"}

    live = _live(repo)
    assert live["TSLA"] == "$TSLA into the week"      # the approved copy stands
    assert live["MSFT"] == "$MSFT keeps leaking"      # undecided one still improves
    assert len(live) == 2                            # and TSLA is not queued twice
    assert fold_state(repo)["status"][tsla] == "queued"


def test_a_held_post_is_replaced(repo):
    """Held means 'not yet', not 'no' — better copy should supersede it."""
    _governor_run(repo, OLD)
    st = fold_state(repo)
    msft = next(k for k, i in st["items"].items() if i["source"]["ticker"] == "MSFT")
    record_decision(msft, "hold", actor="admin", root=repo)

    assert _governor_run(repo, NEW) == set()
    assert _live(repo)["MSFT"] == "$MSFT keeps leaking"
    assert fold_state(repo)["status"][msft] == "quarantined"


def test_supersede_never_touches_another_lane_or_another_day(repo):
    other_lane = make_item(account="flagship", kind="watchlist", text="other lane\n\nx.",
                           as_of=AS_OF, provenance="content_studio", source={"ticker": "TSLA"})
    other_day = _mk("TSLA", "$TSLA yesterday\n\ny.")
    other_day["as_of"] = "2026-07-25"
    enqueue(other_lane, root=repo, max_per_account_day=-1)
    enqueue(other_day, root=repo, max_per_account_day=-1)

    _governor_run(repo, OLD)
    _governor_run(repo, NEW)

    st = fold_state(repo)
    assert st["status"][other_lane["id"]] == "queued"
    assert st["status"][other_day["id"]] == "queued"


def test_supersede_is_skipped_when_nothing_new_queued(repo):
    """A failed regeneration must not leave the day with no content."""
    _governor_run(repo, OLD)
    before = _live(repo)
    # Nothing queued this time → supersede must not run.
    res = supersede_lane(account="flagship", as_of=AS_OF, provenance=LANE,
                         keep_ids=set(), root=repo)
    # Called with an empty keep set it WOULD retire everything, which is exactly
    # why the governor only calls it when something queued.
    assert res["superseded"] == 2
    assert before  # the guard lives in the caller; documented here on purpose


def test_supersede_is_fail_soft(repo):
    res = supersede_lane(account="flagship", as_of=AS_OF, provenance=LANE,
                         keep_ids=set(), root=repo / "does-not-exist")
    assert res["superseded"] == 0
