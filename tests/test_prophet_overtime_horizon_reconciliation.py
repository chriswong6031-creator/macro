"""tests/test_prophet_overtime_horizon_reconciliation.py — the Overtime/horizon ruling
(`research/PROPHET_RULING_J9C_J10_LIFECYCLE_CELLS.md` §13, 2026-08-13).

WHY THIS FILE EXISTS
--------------------
A referral reported "16 open plans past their declared horizon and none produces
``phase=overtime``" and asked whether the producer or the vocabulary was wrong.  Replayed
through the real engines, all 16 turned out to be 1-33 days into a 45-day window: the
"past horizon" reading came from ``age_days``, which anchors on ``signal_date`` — a
formation/event anchor that can precede the plan's own existence by months — while the
horizon, τ, the phase and the EXPIRED/NO_ENTRY close all anchor on ``plan_clock_date``.
Comparing the two is not a weaker test of the same fact; it is a different fact.

The ruling is therefore a VOCABULARY correction, and these tests pin it from both ends:

  * the two clocks stay distinguishable, and the displayed age is the horizon one;
  * ``overtime`` keeps its exact producer (``tau > 1.0 AND not t1_hit``) — the strict
    ``>`` is load-bearing, not an off-by-one;
  * the closure scan retires a plan at ``days >= horizon_days`` on the SAME clock, so on
    a live-priced plan ``overtime`` can only become true AFTER the ledger closed the row.
    A stale price frame is the only path to an OPEN ``overtime`` row;
  * nothing may re-derive Overtime from ``age_days``.

MUTATION DIRECTIONS these pin (each test kills a different one):
  - flipping ``:504`` to ``tau >= 1.0``            → TestTheHorizonBoundary
  - moving the closure gate to ``days > horizon``  → test_closure_is_inclusive_...
  - pointing the pulse back at ``age_days``        → TestTheDisplayedAgeIsTheHorizonClock
  - deriving the cell from ``age_days > horizon``  → TestOvertimeIsNeverDerivedFromAgeDays
  - dropping the ``not t1_hit`` leg                → test_a_plan_that_reached_t1_...
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import scripts.build_prophet as bp  # noqa: E402
from engine.prophet_bridge import plan_clock_date  # noqa: E402
from engine.prophet_management import compute_management_state  # noqa: E402

# ---------------------------------------------------------------------------
# fixture — a plan whose SIGNAL anchor long precedes its own clock, which is the
# shipped shape (94 of 103 plans had that gap) and the only shape that can express
# the defect.  A fixture with signal_date == clock cannot fail these tests.
# ---------------------------------------------------------------------------

SIGNAL = date(2026, 2, 1)      # formation/event anchor
CLOCK = date(2026, 6, 1)       # Monday — the close that IS `entry`
HORIZON = 45                   # the declared window, in CALENDAR days
HORIZON_DAY = CLOCK + timedelta(days=HORIZON)      # 2026-07-16


def _plan(**over) -> dict:
    plan = {
        "id": "AAA-BULL-20260201",
        "asset": "AAA",
        "direction": "BULL",
        "entry": 100.0,
        "invalidation": 90.0,
        "targets": [120.0, 140.0],
        "horizon_days": HORIZON,
        "trigger": 101.0,
        "signal_date": SIGNAL.isoformat(),
        "asof": CLOCK.isoformat(),      # plan_clock_date rung 3
        "confidence": 60.0,
    }
    plan.update(over)
    return plan


def _frame(through: date, *, price: float, start: date = CLOCK) -> pd.DataFrame:
    """Daily closes on weekdays from `start` through `through` (inclusive)."""
    rows, day = [], start
    while day <= through:
        if day.weekday() < 5:
            rows.append((pd.Timestamp(day), price))
        day += timedelta(days=1)
    return pd.DataFrame({"close": [p for _, p in rows]},
                        index=pd.DatetimeIndex([t for t, _ in rows]))


def _at(offset: int, *, price: float = 102.0, frame_through: date | None = None,
        plan: dict | None = None):
    """(state, closure_outcome) for `horizon + offset`, from both real authorities."""
    plan = plan or _plan()
    asof = CLOCK + timedelta(days=HORIZON + offset)
    ph = _frame(frame_through or asof, price=price)
    state = compute_management_state(plan, ph.copy(), asof.isoformat())
    outcome, _, _, _ = bp._determine_outcome(plan, ph.copy(), asof.isoformat())
    return state, outcome


# ===========================================================================
# 1. The two clocks — the whole finding
# ===========================================================================

class TestTheTwoClocks:
    """`age_days` and the horizon clock measure DIFFERENT facts, on the same units."""

    def test_the_horizon_clock_is_the_plan_clock_not_the_signal_date(self):
        plan = _plan()
        assert plan_clock_date(plan) == CLOCK.isoformat()
        state = compute_management_state(
            plan, _frame(HORIZON_DAY, price=102.0), HORIZON_DAY.isoformat())
        assert state["days_elapsed"] == HORIZON, (
            "τ must count from the plan clock; counting from signal_date would make "
            "this plan 165 days old on the day it reaches its 45-day horizon")

    def test_the_signal_age_and_the_clock_age_are_different_numbers(self):
        """The referral's exact shape, reproduced: PINS was 15d into 45 at 167d old.

        If these two ever coincide the fixture is degenerate and every test below lies.
        """
        plan = _plan()
        asof = (CLOCK + timedelta(days=15)).isoformat()      # mid-window, like PINS
        signal_age = bp._age_days(plan["signal_date"], asof)
        clock_age = bp._clock_age_days(plan, asof)
        assert (signal_age, clock_age) == (135, 15)
        assert signal_age > plan["horizon_days"] > clock_age, (
            "the referral's premise — signal age past the horizon while the plan is "
            "barely into its window — must be reproducible or nothing here is pinned")

    def test_both_clocks_count_calendar_days_not_trading_days(self):
        """No trading/calendar conversion exists on this path, in either authority.

        The window spans 6 weekends; a trading-day reading would put the horizon ~19
        sessions later.  Both authorities land on the same calendar day.
        """
        state, outcome = _at(0)
        assert state["days_elapsed"] == HORIZON       # calendar, not ~32 sessions
        assert state["tau"] == 1.0
        assert outcome == "EXPIRED", (
            "closure counts calendar days from the clock too — if either side counted "
            "sessions the two authorities would part company at the boundary")

    def test_the_clock_age_equals_the_engines_own_days_elapsed(self):
        """The published `clock_age_days` is the producer's number, not a second one."""
        for offset in (-30, -1, 0, 1, 12):
            asof = (CLOCK + timedelta(days=HORIZON + offset)).isoformat()
            plan = _plan()
            state = compute_management_state(
                plan, _frame(date.fromisoformat(asof), price=102.0), asof)
            assert bp._clock_age_days(plan, asof) == state["days_elapsed"]


# ===========================================================================
# 2. The boundary — horizon-1 / horizon / horizon+1
# ===========================================================================

class TestTheHorizonBoundary:
    """`tau > 1.0` is exact. horizon-1 and horizon are NOT overtime; horizon+1 is."""

    def test_horizon_minus_one_is_not_overtime(self):
        state, outcome = _at(-1)
        assert state["tau"] < 1.0
        assert state["phase"] == "triggered_pre_t1"
        assert outcome is None, "the plan is still open the day before its horizon"

    def test_at_exactly_the_horizon_the_phase_is_still_not_overtime(self):
        """τ == 1.0 is NOT `> 1.0`.  Kills a `>=` mutation at prophet_management:504."""
        state, _ = _at(0)
        assert state["tau"] == 1.0
        assert state["phase"] != "overtime"
        assert state["phase"] == "triggered_pre_t1"

    def test_horizon_plus_one_is_overtime(self):
        state, _ = _at(1)
        assert state["tau"] > 1.0
        assert state["phase"] == "overtime"

    def test_the_phase_stays_overtime_past_the_boundary(self):
        state, _ = _at(2)
        assert state["phase"] == "overtime"


# ===========================================================================
# 3. THE FINDING — closure precedes the phase by one day, on the same clock
# ===========================================================================

class TestClosurePrecedesOvertime:
    """Why the cell is near-empty, and why that is not an off-by-one to 'fix'."""

    def test_closure_is_inclusive_of_the_horizon_while_overtime_is_exclusive(self):
        """`days >= horizon` closes; `days > horizon` is overtime. One day apart."""
        at_horizon, closed_at_horizon = _at(0)
        past_horizon, closed_past_horizon = _at(1)

        assert closed_at_horizon == "EXPIRED" and at_horizon["phase"] != "overtime"
        assert past_horizon["phase"] == "overtime"
        assert closed_past_horizon == "EXPIRED", (
            "by the time the phase can read overtime the ledger has ALREADY graded the "
            "row — so on a live-priced plan overtime is a post-closure state")

    def test_an_untriggered_plan_closes_no_entry_not_expired_and_not_overtime(self):
        """The other closure arm. A never-triggered plan is NO_ENTRY at the horizon."""
        state, outcome = _at(0, price=100.5)     # below trigger 101
        assert outcome == "NO_ENTRY"
        assert state["phase"] == "pre_trigger"

        past, outcome_past = _at(1, price=100.5)
        assert outcome_past == "NO_ENTRY"
        assert past["phase"] == "overtime", (
            "the phase flips a day after NO_ENTRY too — the untriggered arm has the "
            "same ordering as the triggered one")

    def test_a_stale_price_frame_is_the_only_open_overtime_row(self):
        """A halted/delisted name: no closing bar ever prints, so τ climbs unbounded.

        This is the ONE case the corrected label describes — 'the declared window
        elapsed and no closing print has arrived'.
        """
        stale_through = CLOCK + timedelta(days=HORIZON - 10)
        for offset in (1, 5, 20):
            state, outcome = _at(offset, frame_through=stale_through)
            assert state["phase"] == "overtime"
            assert outcome is None, (
                "no bar at-or-past the horizon ever printed, so the closure scan "
                "cannot grade the row — it stays OPEN while the phase reads overtime")

    def test_at_the_horizon_a_stale_frame_is_not_yet_overtime_either(self):
        """The stale path still respects the boundary — it does not start early."""
        stale_through = CLOCK + timedelta(days=HORIZON - 10)
        state, outcome = _at(0, frame_through=stale_through)
        assert state["tau"] == 1.0
        assert state["phase"] != "overtime"
        assert outcome is None


# ===========================================================================
# 4. The other legs of the transition — T1/T2 state and invalidation
# ===========================================================================

class TestTheOtherLegs:

    def test_a_plan_that_reached_t1_is_never_overtime(self):
        """The `not t1_hit` leg. Kills a mutation that drops it from :504."""
        state, outcome = _at(1, price=125.0)     # above T1 = 120
        assert state["tau"] > 1.0
        assert state["phase"] != "overtime"
        assert state["phase"] == "between_t1_t2"
        assert outcome == "T1_HIT", (
            "in the live pipeline a T1 touch closes the row the same day, so "
            "open ∧ t1_hit is empty — the leg is correct but inert on open plans")

    def test_t1_state_is_sticky_so_a_giveback_past_horizon_is_not_overtime(self):
        """`_first_t1_ts` persists via prev_state: T1 once hit is hit forever."""
        prev = {"_first_t1_ts": "2026-06-20", "_mfe": 25.0, "_mae": 0.0,
                "_max_p1": 1.25, "_first_trigger_ts": "2026-06-02",
                "_first_t2_ts": None}
        asof = CLOCK + timedelta(days=HORIZON + 1)
        state = compute_management_state(
            _plan(), _frame(asof, price=102.0), asof.isoformat(), prev_state=prev)
        assert state["tau"] > 1.0
        assert state["phase"] != "overtime", (
            "price fell back to 102 (p1 ≈ 0.1) but T1 was reached earlier, so the "
            "overtime arm stays shut and the giveback arms own the row")

    def test_invalidation_outranks_overtime(self):
        """Priority 1 beats priority 2 even deep past the horizon."""
        stale_through = CLOCK + timedelta(days=HORIZON - 10)
        state, _ = _at(1, price=85.0, frame_through=stale_through)  # below stop 90
        assert state["tau"] > 1.0
        assert state["phase"] == "invalidated"


# ===========================================================================
# 5. Producer / display agreement — the acceptance criterion
# ===========================================================================

class TestTheDisplayedAgeIsTheHorizonClock:
    """The pulse's age leg must speak the clock the phase and the horizon speak."""

    def test_the_pulse_quotes_the_clock_age_not_the_signal_age(self):
        plan = _plan()
        asof = HORIZON_DAY.isoformat()
        en, _ = bp._plan_pulse(bp._clock_age_days(plan, asof), "pre_trigger", None)
        assert en.startswith(f"{HORIZON}d")
        assert "165d" not in en, (
            "quoting the signal age beside a plan-clock phase is the incoherence that "
            "referred this defect — PINS pulsed '167d' at 33.3% of its window")

    def test_a_degraded_row_carries_both_ages_and_pulses_the_clock_one(self):
        row = bp._degraded_index_entry(
            "AAA-BULL-20260201", _plan(), asof=HORIZON_DAY.isoformat(),
            reason="price unavailable", closed=False, outcome=None)
        assert row["age_days"] == 165          # the SIGNAL's age, still published
        assert row["clock_age_days"] == HORIZON
        assert row["pulse"].startswith(f"{HORIZON}d")

    def test_the_overtime_words_no_longer_claim_the_plan_is_still_running(self):
        """Vocabulary half of the ruling: 'overtime' read as 'in extra time'."""
        en, zh = bp._PHASE_WORD["overtime"]
        assert (en, zh) == ("window elapsed", "窗口已到期")
        assert "overtime" not in en and "超时" not in zh

    def test_the_human_state_ships_a_zh_pair(self):
        """Bilingual law: an unmapped human_state silently drops the leg."""
        from engine.prophet_management import _human_state
        state_en = _human_state("overtime", p1=0.1, trigger_hit=True, tau=1.2)
        assert state_en == "Window Elapsed — Awaiting Close"
        assert state_en in bp._HUMAN_STATE_ZH
        assert bp._HUMAN_STATE_ZH[state_en] == "窗口已到期 — 待收盘确认"

    def test_a_closed_row_still_suppresses_the_phase_leg(self):
        """The suppression is what keeps a post-closure `overtime` off the surface."""
        en, zh = bp._plan_pulse(46, "overtime", "Window Elapsed — Awaiting Close",
                                closed=True, outcome="EXPIRED")
        assert "window elapsed" not in en and "窗口已到期" not in zh
        assert "46d" not in en


# ===========================================================================
# 6. The derivation guard — no second timing engine, ever
# ===========================================================================

class TestOvertimeIsNeverDerivedFromAgeDays:
    """`lifecycle_counts.overtime` must read `phase`, never re-derive 'past horizon'."""

    def test_the_two_derivations_disagree_so_they_cannot_be_swapped(self):
        """A future implementer cannot claim the age test is equivalent."""
        plan = _plan()
        asof = HORIZON_DAY.isoformat()
        state = compute_management_state(
            plan, _frame(HORIZON_DAY, price=102.0), asof)
        by_age = bp._age_days(plan["signal_date"], asof) > plan["horizon_days"]
        by_phase = state["phase"] == "overtime"
        assert by_age is True and by_phase is False, (
            "the age-derived predicate calls this plan overtime on the day it reaches "
            "its horizon at τ=1.0 — the engine does not, and the engine is authority")

    def test_the_live_book_has_no_open_plan_past_its_declared_horizon(self):
        """Population check on the committed payload: max τ, and zero open overtime."""
        index_path = _REPO / "site" / "prophet" / "index.json"
        states_dir = _REPO / "site" / "prophet" / "states"
        if not index_path.exists() or not states_dir.is_dir():
            pytest.skip("committed site/prophet payload absent (sparse checkout)")

        payload = json.loads(index_path.read_text())
        open_rows = [p for p in payload.get("plans", []) if not p.get("closed")]
        if not open_rows:
            pytest.skip("no open plans on the committed payload")

        seen = 0
        for row in open_rows:
            state_path = states_dir / f"{row['id']}.json"
            if not state_path.exists():
                continue
            state = json.loads(state_path.read_text())
            seen += 1
            assert state["tau"] <= 1.0, (
                f"{row['id']} is open at τ={state['tau']} — the closure scan should "
                f"have graded it EXPIRED/NO_ENTRY at τ=1.0 on the same clock")
            assert state["phase"] != "overtime" or state["tau"] > 1.0
        assert seen >= 10, "too few states resolved to call this a population check"

    def test_rows_the_age_predicate_flags_are_correctly_not_overtime(self):
        """The 16 counterexamples, as a standing regression."""
        index_path = _REPO / "site" / "prophet" / "index.json"
        states_dir = _REPO / "site" / "prophet" / "states"
        if not index_path.exists() or not states_dir.is_dir():
            pytest.skip("committed site/prophet payload absent (sparse checkout)")

        payload = json.loads(index_path.read_text())
        flagged = [
            p for p in payload.get("plans", [])
            if not p.get("closed")
            and (p.get("age_days") or 0) > (p.get("horizon_days") or 10 ** 9)
        ]
        if not flagged:
            pytest.skip("no rows where the signal age exceeds the horizon today")

        for row in flagged:
            state_path = states_dir / f"{row['id']}.json"
            if not state_path.exists():
                continue
            state = json.loads(state_path.read_text())
            assert state["phase"] != "overtime"
            assert state["tau"] < 1.0, (
                f"{row['id']}: age_days={row['age_days']} exceeds horizon "
                f"{row['horizon_days']}, but its HORIZON clock reads "
                f"{state['days_elapsed']}d (τ={state['tau']}) — the two ages measure "
                f"different facts and only the second is commensurable")
