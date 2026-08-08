"""tests/test_marketing_receipt_supply.py — a receipt slot must draw a RESOLVED plan.

THE DEFECT (found 2026-08-08). `kind=receipt` had shipped ZERO posts in the whole
570-row history of data/marketing/outbox/items.jsonl, and every registry the house
law cares about was already correct: the kind is in `outbox.KINDS`, in
`PLANNED_KINDS`, in `_ANGLE_BY_KIND`, in the approval-desk decider list, and it
carries a non-zero tilt weight on all thirteen desks. `graded_receipts()` was
returning real rows (6 tickers inside the 30-day window that day).

The break was a POOL MISMATCH, and it was structural rather than intermittent:

  * a receipt slot took its ticker from `watch_pool`, i.e. from
    `postable_signals(plans)`, which admits only `_LIVE_PHASES`
    (triggered_pre_t1 / triggered / active / pre_trigger / running);
  * a graded receipt requires `receipt_source._is_resolved` — phase
    `invalidated`, or a DONE profit-plan level.

One plan cannot be pre-resolution and resolved at once, so the two sets were
disjoint BY CONSTRUCTION, every night. The downstream join
(`_receipts_by_ticker.get(ticker)`) therefore always missed and every receipt item
was reallocated to `watchlist` before the writer ever ran.

WHAT THIS SUITE PINS. Not "receipts exist" — a fixture can always be made to
produce one. It pins the RELATION that failed: the pool a receipt slot draws from
must be the resolved set, and it must NOT be the live set. The two directions are
asserted separately, because the bug passed a test of the first kind (the item was
typed `receipt`) while failing the second (its ticker could never join).

It also pins the monitor. `_alarm_on_starved_receipts` returned early on
`if n_receipts: return` — a claim about the SOURCE used to certify the OUTCOME —
so the one alarm built to catch receipt starvation was guaranteed to stay silent
through it.

CONVENTIONS. Synthetic plans only; no repo data, no wall clock, no writes.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from engine.marketing import content_studio as cs


TODAY = "2026-08-09"


#: `plan_account` calls `postable_signals(plans)` with no `today`, so the
#: freshness gate reads the WALL CLOCK. A hardcoded `_signal_date` would therefore
#: be a scheduled failure — fresh the day this was written, stale a fortnight
#: later — so the fixture dates are derived from today instead.
_FRESH = (datetime.now(timezone.utc).date() - timedelta(days=2)).isoformat()


def _live_plan(ticker: str) -> dict:
    """A plan `postable_signals` admits and `_is_resolved` refuses.

    TWO FIXTURE TRAPS, both of which made the first draft of this suite fail for
    reasons that had nothing to do with receipts: the gate reads
    `management_confidence`, NOT `confidence`, and the scale is 0-100 against
    `_MIN_CONFIDENCE = 50.0`, so a plausible-looking 0.9 is a REJECT.
    """
    return {
        "asset": ticker,
        "direction": "BULL",
        "phase": "active",
        "management_confidence": 90.0,
        "_signal_date": _FRESH,
        "horizon_days": 21,
    }


def _resolved_plan(ticker: str) -> dict:
    """A plan `_is_resolved` admits and `postable_signals` refuses."""
    return {
        "asset": ticker,
        "direction": "BULL",
        "phase": "invalidated",
        "management_confidence": 90.0,
        "_signal_date": _FRESH,
        "horizon_days": 21,
    }


@pytest.fixture(scope="module")
def _fixture_is_disjoint():
    """Vacuous-green guard, and the defect restated as an assertion.

    If `postable_signals` ever started admitting a resolved plan, every assertion
    below would still pass while testing nothing — so prove the two pools really
    are disjoint on these fixtures before relying on them.
    """
    from engine.marketing.receipt_source import _is_resolved

    live, resolved = _live_plan("LIVE"), _resolved_plan("DONE")
    postable = {str(p.get("asset")) for p in cs.postable_signals([live, resolved])}
    assert postable == {"LIVE"}, (
        f"postable_signals admitted {postable}; this suite assumes it admits only "
        f"live-phase plans"
    )
    assert _is_resolved(resolved) and not _is_resolved(live)
    return True


def _plan(account_id: str, plans: list[dict], **kw):
    return cs.plan_account(
        account={"id": account_id, "tilt": {"receipt": 1.0}},
        plans=plans,
        n_days=1,
        per_day=6,
        seed=0,
        **kw,
    )


def test_a_receipt_slot_draws_the_resolved_plan_not_the_live_one(_fixture_is_disjoint):
    """The fix, in one assertion. Both plans are on the board; a receipt slot must
    land on the resolved one, which is the only one a graded receipt can cover."""
    plans = [_live_plan("LIVE"), _resolved_plan("DONE")]
    items = _plan("flagship", plans, receipt_plans=[_resolved_plan("DONE")])
    receipts = [i for i in items if i.type == "receipt"]
    assert receipts, "the tilt asked for receipts and none were allocated"
    tickers = {i.ticker for i in receipts if i.ticker}
    assert tickers == {"DONE"}, (
        f"receipt slots drew {tickers}; a receipt may only ever name a RESOLVED "
        f"plan, and LIVE is the pre-resolution pool that can never join one"
    )


def test_without_the_resolved_pool_the_rung_degrades_and_is_not_deleted(
        _fixture_is_disjoint):
    """`receipt_plans=None` is the un-updated caller, and it must be a NO-OP.

    THE TIDIER VERSION OF THIS FIX WAS A VOLUME REGRESSION, and this test is the
    one that caught it. Routing an unfillable receipt rung to the pool-empty
    `continue` reads better — a receipt is only ever a resolved plan, so no
    resolved plan means no rung — and it DELETES a post that used to ship: the
    rung previously drew a coverage ticker and became a `watchlist` post one layer
    down. It also breaks the every-family-gets-a-rung guarantee
    (tests/test_marketing_content.py::test_all_types_present_in_every_account).

    So the contract is: a receipt is an UPGRADE on a coverage rung when the data
    exists, never a condition of having one.
    """
    plans = [_live_plan("LIVE"), _resolved_plan("DONE")]
    items = _plan("flagship", plans, receipt_plans=None)
    receipts = [i for i in items if i.type == "receipt"]
    assert receipts, "the receipt rung was deleted instead of degrading"
    assert all(i.ticker == "LIVE" for i in receipts), (
        f"expected the unchanged coverage draw; got "
        f"{[i.ticker for i in receipts]}"
    )


def test_the_cooldown_still_binds_the_resolved_pool(_fixture_is_disjoint):
    """The cooldown still binds. Widening receipt supply must not become a way
    around the cross-day cooldown that stops a desk re-posting one name.

    No live plan on the board here, so the coverage fallback has nothing either
    and the rung genuinely has no ticker — which isolates the cooldown from the
    fallback tested below.
    """
    items = _plan("flagship", [_resolved_plan("DONE")],
                  receipt_plans=[_resolved_plan("DONE")],
                  cooled_watch=frozenset({"DONE"}))
    receipts = [i for i in items if i.type == "receipt"]
    assert all(i.ticker != "DONE" for i in receipts), (
        "a cooled ticker reached a receipt slot"
    )


def test_a_cooled_receipt_falls_back_to_coverage_rather_than_vanishing(
        _fixture_is_disjoint):
    """The pair of the two tests above, and the case that actually happens most
    nights: a graded receipt EXISTS but this desk has already used the name.

    `receipt_pool` empties after cooling, the branch does not fire, and the rung
    degrades to coverage. Asserted because "cooled" and "nothing graded" reach the
    fallback by different routes and only one of them was ever exercised.
    """
    report: dict = {}
    items = _plan("flagship", [_live_plan("LIVE"), _resolved_plan("DONE")],
                  receipt_plans=[_resolved_plan("DONE")],
                  cooled_watch=frozenset({"DONE"}), report=report)
    receipts = [i for i in items if i.type == "receipt"]
    assert receipts, "the receipt rung vanished when its only name was cooled"
    assert all(i.ticker != "DONE" for i in receipts), "a cooled name was posted"


def test_the_starved_receipt_alarm_can_see_a_graded_but_unattached_night(capsys):
    """The monitor's own blind spot.

    `n_receipts > 0` and `receipt_items == 0` is the exact state that held for the
    outbox's whole history, and the old early return made it unreportable. The
    annotation must start the line, or GitHub drops it.
    """
    cs._alarm_on_starved_receipts([], 6, 30, TODAY, receipt_items=0)
    out = capsys.readouterr().out
    assert out.strip(), "graded>0 with zero attachable receipts printed nothing"
    line = out.strip().splitlines()[0]
    assert line.startswith("::warning title=marketing-receipts-unattached::"), line


def test_the_alarm_stays_quiet_when_receipts_actually_attached(capsys):
    """The other direction, so the new branch cannot become a nightly warning."""
    cs._alarm_on_starved_receipts([], 6, 30, TODAY, receipt_items=2)
    assert capsys.readouterr().out.strip() == ""


def test_an_unmeasured_caller_is_not_upgraded_into_the_new_alarm(capsys):
    """`receipt_items=None` means the caller did not measure it. Such a caller must
    keep the ORIGINAL verdict rather than being handed an alarm it cannot answer."""
    cs._alarm_on_starved_receipts([], 6, 30, TODAY)
    assert capsys.readouterr().out.strip() == ""
