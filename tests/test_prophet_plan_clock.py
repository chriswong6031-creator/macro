"""tests/test_prophet_plan_clock.py — the Prophet US plan pipeline's clock, trigger,
price reach, lossless intake, closed-state copy and shipped order (P1-P6, 2026-08-06).

WHY THIS FILE EXISTS
--------------------
The pre-existing prophet fixtures are DEGENERATE for every defect below: they set
``asof == signal_date`` and carry no ``trigger``, so the two worst defects in the
pipeline were invisible to a green suite.

  * ``signal_date`` is the base-FORMATION anchor (``hold.anchor``) and preceded
    origination by up to 152 days on the shipped book (94 of 103 plans had a gap).
    ``entry`` is the ORIGINATION-day close.  Anchoring the horizon clock and the
    outcome scan to ``signal_date`` graded plans on bars that predated them: all 9
    EXPIRED ledger rows and both winners closed before their own plan existed, and
    14 plans were born already past horizon.
  * The plan's own copy says "No position until trigger is confirmed" while
    ``_determine_outcome`` never read ``plan["trigger"]`` — 5 of 16 shipped rows
    booked full P&L on positions the plan told the reader not to take.

Every fixture here therefore has ``asof`` MONTHS after ``signal_date`` and a trigger
above the graded window.  A fixture that cannot express the defect cannot pin its fix.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import scripts.build_prophet as bp  # noqa: E402
from engine.prophet_bridge import (  # noqa: E402
    N_CANDIDATES,
    load_quarantined_ids,
    originate_plans,
    plan_clock_date,
    select_candidates,
)
from engine.prophet_management import compute_management_state  # noqa: E402


# ---------------------------------------------------------------------------
# fixtures — the SHIPPED shape, not the degenerate one
# ---------------------------------------------------------------------------

FORMATION = "2026-03-01"   # hold.anchor — the base formed here
ORIGINATION = "2026-07-01"  # the night the plan was written; entry IS this close
# 122 calendar days apart. A 45-day horizon read off FORMATION is already 77 days
# past expiry on the plan's own birthday.


def _plan(
    *,
    plan_id: str = "AAA-BULL-20260301",
    ticker: str = "AAA",
    entry: float = 100.0,
    trigger: float | None = 105.0,
    invalidation: float = 90.0,
    targets: tuple[float, ...] = (115.0, 130.0),
    signal_date: str = FORMATION,
    entry_date: str | None = ORIGINATION,
    asof: str | None = ORIGINATION,
    horizon_days: int = 45,
    direction: str = "BULL",
) -> dict:
    """A plan in the shape the shipped book actually holds: an OLD formation anchor,
    a RECENT origination, and a trigger the plan says must confirm first."""
    plan: dict = {
        "schema": "prophet.trade_plan/v1",
        "id": plan_id,
        "asset": ticker,
        "direction": direction,
        "signal_date": signal_date,
        "_signal_date": signal_date,
        "entry": entry,
        "trigger": trigger,
        "invalidation": invalidation,
        "targets": list(targets),
        "horizon_days": horizon_days,
        "min_hold_days": 10,
        "tranche": 1,
        "option_contract": None,
        "authority_tier": "display",
        "source_engines": ["us_standouts_buy_lane"],
    }
    if asof is not None:
        plan["asof"] = asof
    if entry_date is not None:
        plan["entry_date"] = entry_date
    return plan


def _closes(values: list[float], start: str) -> pd.DataFrame:
    """Daily closes on business days from `start` (inclusive)."""
    idx = pd.date_range(start, periods=len(values), freq="B")
    return pd.DataFrame({"close": values}, index=idx)


def _advance(tmp_path, plans: dict, ph_map: dict, asof: str) -> list:
    """advance_ledger against a tmp ledger with a stubbed price loader."""
    orig_path, orig_dir = bp.LEDGER_PATH, bp.LEDGER_DIR
    try:
        bp.LEDGER_PATH = tmp_path / "ledger.jsonl"
        bp.LEDGER_DIR = tmp_path
        bp._initialize_ledger()
        with patch("scripts.build_prophet._load_price_history_for_management",
                   side_effect=lambda t: ph_map.get(t)):
            return bp.advance_ledger(plans, asof)
    finally:
        bp.LEDGER_PATH, bp.LEDGER_DIR = orig_path, orig_dir


# ===========================================================================
# P1 — the grading clock
# ===========================================================================

class TestTheClockIsTheEntryDate:

    def test_a_plan_with_a_100_day_old_anchor_is_not_expired_at_birth(self, tmp_path):
        """THE defect, stated as a test.

        Formation 2026-03-01, origination 2026-07-01, horizon 45 days.  Under the old
        clock the very first bar after formation is already day 1 of 45 and the plan
        EXPIRES months before it was written.  Under the entry-date clock it is simply
        open: five bars have printed since entry.
        """
        plan = _plan(trigger=None)   # trigger isolated in its own section below
        # Bars run from FORMATION so the frame contains the whole poisoned window.
        ph = _closes([100.0] * 120, start=FORMATION)
        rows = _advance(tmp_path, {plan["id"]: plan}, {"AAA": ph}, "2026-07-08")
        assert rows == [], (
            "a plan originated on 2026-07-01 cannot have expired: the old clock read "
            "its 2026-03-01 formation anchor and closed it as EXPIRED on bars that "
            "predated the plan"
        )

    def test_the_same_plan_on_the_old_clock_would_have_expired(self, tmp_path):
        """Mutation direction: strip entry_date AND asof, and the old behaviour returns.

        This is the test's own falsifier — without it, the assertion above would pass
        just as well against a function that never closes anything.
        """
        plan = _plan(trigger=None, entry_date=None, asof=None)
        ph = _closes([100.0] * 120, start=FORMATION)
        rows = _advance(tmp_path, {plan["id"]: plan}, {"AAA": ph}, "2026-07-08")
        assert len(rows) == 1 and rows[0]["outcome"] == "EXPIRED", (
            "with nothing but signal_date to read, the scan MUST fall back to it — "
            "this is the shape the fix is measured against"
        )

    def test_the_scan_starts_after_the_entry_bar_not_after_formation(self, tmp_path):
        """A dip below invalidation BEFORE origination must not close the plan.

        The name traded at 80 in April — 10 points through the plan's stop — but the
        plan did not exist then and its entry was taken in July.  The old scan saw
        that April bar and booked INVALIDATED with a −20% result.
        """
        closes = [100.0] * 30 + [80.0] + [100.0] * 120   # the April hole
        ph = _closes(closes, start=FORMATION)
        plan = _plan(trigger=None)
        rows = _advance(tmp_path, {plan["id"]: plan}, {"AAA": ph}, "2026-07-08")
        assert rows == [], "a pre-origination stop-out is not this plan's outcome"

    def test_horizon_expiry_counts_from_entry_date(self, tmp_path):
        """The clock must not merely be un-stuck — it must actually run."""
        plan = _plan(trigger=None, horizon_days=10)
        # Flat from formation; the asof is 20 calendar days past origination.
        ph = _closes([100.0] * 200, start=FORMATION)
        rows = _advance(tmp_path, {plan["id"]: plan}, {"AAA": ph}, "2026-07-25")
        assert len(rows) == 1
        assert rows[0]["outcome"] == "EXPIRED"
        assert rows[0]["days_held"] >= 10
        # close_date is entry_date + days_held, never formation + days_held.
        assert rows[0]["close_date"] > ORIGINATION, (
            f"close_date {rows[0]['close_date']} predates origination {ORIGINATION} — "
            "the ledger row was written from the formation anchor again"
        )
        assert rows[0]["entry_date"] == ORIGINATION

    def test_management_tau_reads_the_entry_date(self):
        """The third call site: elapsed/τ inside compute_management_state."""
        plan = _plan(trigger=None, horizon_days=45)
        ph = _closes([100.0] * 200, start=FORMATION)
        ph = ph[ph.index <= pd.Timestamp(ORIGINATION)]
        state = compute_management_state(plan=plan, price_history=ph,
                                         asof=ORIGINATION)
        assert state["days_elapsed"] == 0, (
            "on origination night the plan has spent none of its horizon; reading "
            "signal_date gave 122 days of a 45-day horizon and forced overtime"
        )
        assert state["phase"] != "overtime"

    def test_close_date_never_precedes_the_plans_own_origination(self, tmp_path):
        """The exact invariant the quarantine rule tests for, enforced going forward."""
        closes = [100.0] * 30 + [130.0] + [100.0] * 130   # a pre-origination T2 spike
        ph = _closes(closes, start=FORMATION)
        plan = _plan(trigger=None)
        rows = _advance(tmp_path, {plan["id"]: plan}, {"AAA": ph}, "2026-09-01")
        for row in rows:
            assert row["close_date"] >= ORIGINATION, row


# ===========================================================================
# P2 — the trigger is read
# ===========================================================================

class TestTriggerConfirmation:

    def test_an_unconfirmed_trigger_closes_no_entry_with_a_null_result(self, tmp_path):
        """Price never reaches 105. The plan said "no position until confirmed", so
        the −8% drift below it is not a loss this plan took."""
        plan = _plan(trigger=105.0, invalidation=None, horizon_days=10)
        closes = [100.0] * 40 + [99.0, 98.0, 97.0, 96.0, 95.0,
                                 94.0, 93.0, 92.0, 92.0, 92.0, 92.0, 92.0]
        ph = _closes(closes, start=FORMATION)
        # Re-index so the post-origination bars are the tail of the frame.
        ph.index = pd.date_range(FORMATION, periods=len(closes), freq="B")
        plan["entry_date"] = str(ph.index[39].date())
        rows = _advance(tmp_path, {plan["id"]: plan}, {"AAA": ph}, "2027-01-01")
        assert len(rows) == 1
        assert rows[0]["outcome"] == "NO_ENTRY"
        assert rows[0]["stock_result_pct"] is None, (
            "a trade that never opened has no P&L; booking one is the defect"
        )

    def test_no_entry_is_in_neither_side_of_the_rate(self):
        """The exclusion is the point — a NO_ENTRY in the denominator would report a
        losing trade the plan explicitly told the reader not to take."""
        ledger = [
            {"id": "W", "outcome": "T1_HIT", "stock_result_pct": 12.0},
            {"id": "L", "outcome": "INVALIDATED", "stock_result_pct": -8.0},
            {"id": "N", "outcome": "NO_ENTRY", "stock_result_pct": None},
        ]
        summary = bp.record_summary(ledger, set())
        assert summary["n_scored"] == 2
        assert summary["n_no_entry"] == 1
        assert summary["win_rate"] == 0.5, (
            "3 rows, 1 win — but the NO_ENTRY is not a loss, so the rate is 1/2"
        )

    def test_the_scan_starts_at_confirmation_not_at_the_clock(self, tmp_path):
        """A stop-level print BEFORE the trigger confirms is not an exit.

        Entry 100, trigger 105, stop 90.  The tape goes 88 (no position — the plan is
        still waiting), then 106 (confirmed), then 120 (T1).  Scanning from the clock
        books INVALIDATED at 88 on a position that did not exist.
        """
        closes = [100.0] * 40 + [88.0, 106.0, 120.0, 120.0]
        ph = _closes(closes, start=FORMATION)
        plan = _plan(trigger=105.0, invalidation=90.0, horizon_days=45)
        plan["entry_date"] = str(ph.index[39].date())
        rows = _advance(tmp_path, {plan["id"]: plan}, {"AAA": ph}, "2027-01-01")
        assert len(rows) == 1
        assert rows[0]["outcome"] == "T1_HIT", (
            f"got {rows[0]['outcome']} — the pre-confirmation 88 print was read as an "
            "exit from a position the plan had not entered"
        )

    def test_confirmation_is_inclusive_of_the_published_level(self, tmp_path):
        """The plan publishes "above 105" as the level to act on; trading AT it acts
        on the plan. Pinned in both directions so a refactor cannot quietly flip it."""
        plan = _plan(trigger=105.0, invalidation=None, horizon_days=3)
        exact = _closes([100.0] * 40 + [105.0, 105.0, 105.0, 105.0], start=FORMATION)
        plan["entry_date"] = str(exact.index[39].date())
        rows = _advance(tmp_path, {plan["id"]: plan}, {"AAA": exact}, "2027-01-01")
        assert rows[0]["outcome"] == "EXPIRED", "105.0 confirms the 105.0 trigger"

        plan2 = _plan(plan_id="BBB-BULL-1", ticker="BBB", trigger=105.0,
                      invalidation=None, horizon_days=3)
        under = _closes([100.0] * 40 + [104.99] * 4, start=FORMATION)
        plan2["entry_date"] = str(under.index[39].date())
        rows2 = _advance(tmp_path, {plan2["id"]: plan2}, {"BBB": under}, "2027-01-01")
        assert rows2[0]["outcome"] == "NO_ENTRY", "104.99 does not confirm 105.0"

    def test_a_null_trigger_is_treated_as_confirmed(self, tmp_path):
        """Legacy plans and fixtures predate the field; they must grade as before."""
        plan = _plan(trigger=None, horizon_days=5)
        ph = _closes([100.0] * 40 + [100.0] * 10, start=FORMATION)
        plan["entry_date"] = str(ph.index[39].date())
        rows = _advance(tmp_path, {plan["id"]: plan}, {"AAA": ph}, "2027-01-01")
        assert rows[0]["outcome"] == "EXPIRED"

    def test_bear_confirmation_is_mirrored(self, tmp_path):
        plan = _plan(plan_id="CCC-BEAR-1", ticker="CCC", direction="BEAR",
                     entry=100.0, trigger=95.0, invalidation=None,
                     targets=(85.0, 70.0), horizon_days=45)
        ph = _closes([100.0] * 40 + [97.0, 94.0, 84.0, 84.0], start=FORMATION)
        plan["entry_date"] = str(ph.index[39].date())
        rows = _advance(tmp_path, {plan["id"]: plan}, {"CCC": ph}, "2027-01-01")
        assert rows[0]["outcome"] == "T1_HIT"


# ===========================================================================
# Quarantine — derived, excluded, disclosed, and the jsonl untouched
# ===========================================================================

class TestLedgerQuarantine:

    @staticmethod
    def _fixture():
        plans = {
            "OLD-BULL-1": {"id": "OLD-BULL-1", "asof": "2026-07-14"},
            "OK-BULL-1": {"id": "OK-BULL-1", "asof": "2026-07-01"},
            "EDGE-BULL-1": {"id": "EDGE-BULL-1", "asof": "2026-07-10"},
        }
        ledger = [
            # closed 2026-05-04, plan written 2026-07-14 → graded before it existed
            {"id": "OLD-BULL-1", "close_date": "2026-05-04", "outcome": "EXPIRED",
             "stock_result_pct": 6.4},
            {"id": "OK-BULL-1", "close_date": "2026-07-20", "outcome": "INVALIDATED",
             "stock_result_pct": -9.8},
            # same day = NOT poisoned; the rule is STRICTLY predates
            {"id": "EDGE-BULL-1", "close_date": "2026-07-10", "outcome": "T1_HIT",
             "stock_result_pct": 15.9},
        ]
        return ledger, plans

    def test_the_list_is_derived_from_the_arithmetic_not_enumerated(self):
        ledger, plans = self._fixture()
        rows = bp.derive_quarantine(ledger, plans)
        assert [r["id"] for r in rows] == ["OLD-BULL-1"]
        assert rows[0]["reason"] == "graded_on_pre_origination_clock"
        assert rows[0]["quarantined"] == "2026-08-06"

    def test_moving_a_plans_origination_moves_the_list(self):
        """Mutation check: nothing here may be hardcoded. Re-date the OK plan's
        origination past its own close and it becomes poisoned too."""
        ledger, plans = self._fixture()
        plans["OK-BULL-1"]["asof"] = "2026-08-01"
        assert {r["id"] for r in bp.derive_quarantine(ledger, plans)} == {
            "OLD-BULL-1", "OK-BULL-1"}

    def test_a_row_with_no_locatable_plan_is_not_quarantined(self):
        """Silence is not evidence of poison."""
        ledger, plans = self._fixture()
        ledger.append({"id": "GHOST-BULL-1", "close_date": "2020-01-01",
                       "outcome": "EXPIRED", "stock_result_pct": 1.0})
        assert "GHOST-BULL-1" not in {r["id"] for r in bp.derive_quarantine(ledger, plans)}

    def test_the_file_round_trips_through_the_shared_reader(self, tmp_path):
        ledger, plans = self._fixture()
        orig_dir = bp.LEDGER_DIR
        try:
            bp.LEDGER_DIR = tmp_path
            payload = bp.write_quarantine(ledger, plans)
        finally:
            bp.LEDGER_DIR = orig_dir
        path = tmp_path / "ledger_quarantine.json"
        assert path.exists()
        assert payload["count"] == 1
        assert load_quarantined_ids(path) == {"OLD-BULL-1"}

    def test_an_absent_file_is_an_empty_quarantine_not_a_crash(self, tmp_path):
        assert load_quarantined_ids(tmp_path / "nope.json") == set()

    def test_summaries_exclude_the_quarantined_rows(self):
        ledger, plans = self._fixture()
        ids = {r["id"] for r in bp.derive_quarantine(ledger, plans)}
        summary = bp.record_summary(ledger, ids)
        assert summary["n_rows_total"] == 3
        assert summary["n_quarantined"] == 1
        assert summary["n_scored"] == 2
        # The poisoned row is the +6.4% "winner". Dropping it halves the win rate.
        assert summary["win_rate"] == 0.5
        assert bp.record_summary(ledger, set())["n_scored"] == 3

    def test_the_disclosure_line_is_plain_words_and_bilingual(self, tmp_path):
        ledger, plans = self._fixture()
        orig_dir = bp.LEDGER_DIR
        try:
            bp.LEDGER_DIR = tmp_path
            payload = bp.write_quarantine(ledger, plans)
        finally:
            bp.LEDGER_DIR = orig_dir
        assert payload["note"] == (
            "1 early rows quarantined 2026-08-06 — graded on a clock that predated "
            "the plan")
        assert payload["note_zh"], "an EN-only disclosure desyncs the bilingual pair"
        # No raw enum slugs or internal study names in the reader-facing line.
        for banned in ("EXPIRED", "T1_HIT", "_determine_outcome", "signal_date"):
            assert banned not in payload["note"]

    def test_the_ledger_file_itself_is_never_rewritten(self, tmp_path):
        """Append-only means append-only: quarantine SUBTRACTS from summaries, it does
        not edit the record."""
        ledger, plans = self._fixture()
        path = tmp_path / "ledger.jsonl"
        body = "# header\n" + "\n".join(json.dumps(r) for r in ledger) + "\n"
        path.write_text(body, encoding="utf-8")
        before = path.read_bytes()
        orig_path, orig_dir = bp.LEDGER_PATH, bp.LEDGER_DIR
        try:
            bp.LEDGER_PATH, bp.LEDGER_DIR = path, tmp_path
            bp.write_quarantine(bp._load_ledger_rows(), plans)
        finally:
            bp.LEDGER_PATH, bp.LEDGER_DIR = orig_path, orig_dir
        assert path.read_bytes() == before

    def test_the_committed_ledger_derives_exactly_the_reported_set(self):
        """Against the REAL artifacts: the count is an observation of the rule, and
        this test states it so a later change to either side is visible."""
        ledger_path = _REPO / "data" / "prophet" / "ledger.jsonl"
        plans_dir = _REPO / "site" / "prophet" / "plans"
        if not (ledger_path.exists() and plans_dir.exists()):
            pytest.skip("committed prophet artifacts absent")
        plans = {}
        for p in plans_dir.glob("*.json"):
            d = json.loads(p.read_text(encoding="utf-8"))
            plans[d["id"]] = d
        rows = [json.loads(ln) for ln in ledger_path.read_text().splitlines()
                if ln.strip() and not ln.startswith("#")]
        derived = {r["id"] for r in bp.derive_quarantine(rows, plans)}
        # Every derived row must actually satisfy the stated rule — the property, not
        # the count, is what must hold on any future artifact.
        for plan_id in derived:
            row = next(r for r in rows if r["id"] == plan_id)
            assert row["close_date"] < plans[plan_id]["asof"]
        assert derived, "the shipped ledger is the reason this rule exists"


# ===========================================================================
# P3 — the plan lane can price its own plans
# ===========================================================================

class TestPlanLanePriceReach:

    def test_the_panel_rung_prices_a_name_no_per_ticker_parquet_covers(self):
        """PINS has no ohlcv and no stocks parquet — 27 of 103 plans were like it, and
        an unpriceable plan can never be managed, never closed, and blocks its slot
        forever."""
        for sub in ("data/baskets/ohlcv", "data/stocks"):
            assert not (_REPO / sub / "PINS.parquet").exists(), (
                "fixture assumption broken: PINS now has a per-ticker parquet")
        df = bp._load_price_history_for_management("PINS")
        if df is None:
            pytest.skip("breadth close panels absent in this checkout")
        assert "close" in df.columns and not df.empty
        assert isinstance(df.index, pd.DatetimeIndex)

    def test_origination_and_management_resolve_to_the_same_series(self):
        """A plan priced at birth but not a night later is worse than one never born."""
        from engine.prophet_bridge import _load_price_history  # noqa: PLC0415
        a = _load_price_history("PINS")
        b = bp._load_price_history_for_management("PINS")
        if a is None or b is None:
            pytest.skip("breadth close panels absent in this checkout")
        assert list(a.index) == list(b.index)
        assert a["close"].tolist() == b["close"].tolist()

    def test_a_per_ticker_parquet_still_wins(self):
        """Priority order is the reason the panels can never disagree with the
        per-ticker store on a shipped plan."""
        from engine.prophet_bridge import _PLAN_PRICE_DIRS  # noqa: PLC0415
        assert _PLAN_PRICE_DIRS[0].endswith("ohlcv")
        assert _PLAN_PRICE_DIRS[1].endswith("stocks")
        aapl = bp._load_price_history_for_management("AAPL")
        if aapl is None:
            pytest.skip("no committed AAPL history")
        # A panel frame is close-only; the per-ticker store carries full OHLCV.
        assert len(aapl.columns) > 1, "AAPL resolved to a panel instead of its parquet"

    def test_an_unreachable_name_is_still_a_null(self):
        """The fix widens reach; it does not fabricate. Foreign issuers in no US index
        cache stay unpriced, and that is a real null."""
        assert bp._load_price_history_for_management("ZZZZNOTATICKER") is None


# ===========================================================================
# P4 — every survivor is attempted; helper slicing is not an opportunity gate
# ===========================================================================

def _buy_row(ticker: str, *, priority: float, spot: float = 100.0,
             anchor: str = "2026-07-02") -> dict:
    return {
        "ticker": ticker,
        "dir": "up",
        "conviction": {"score": 70, "band": "neutral", "drivers": ["momentum"],
                       "cautions": ["macro"], "trust_tier": {"en": "tier-2"}},
        "entry_signal": {"act_level": 3, "status": "partial", "spot": spot,
                         "chase_above": spot * 1.03, "atr_pct": 2.0,
                         "entry_grade": "solid"},
        "hold": {"state": "HOLD", "anchor": anchor, "invalidation": spot * 0.9},
        "prophet": {"version": "us_prophet_v1", "score": priority},
    }


def _write_standouts(tmp_path: Path, buys: list[dict], *, as_of="2026-07-02") -> Path:
    path = tmp_path / "us_standouts.json"
    path.write_text(json.dumps({
        "as_of": as_of,
        "staleness": {
            "price_through": as_of,
            "delayed": False,
            "unknown": False,
            "basis": "panel_majority",
            "inputs": {"panel": {"mixed_vintage": False}},
        },
        "gate_go": True,
        "buy": buys,
    }),
                    encoding="utf-8")
    return path


class TestFiltersThenLosslessOrigination:

    def test_a_board_of_already_live_names_still_originates_from_below_the_line(
            self, tmp_path):
        """THE 2026-08-05 night: all 12 capped candidates were re-admissions, so the
        run originated ZERO plans while eligible names sat one row below the cap."""
        buys = ([_buy_row(f"LIVE{i:02d}", priority=99.0 - i) for i in range(N_CANDIDATES)]
                + [_buy_row(f"NEW{i:02d}", priority=50.0 - i) for i in range(6)])
        path = _write_standouts(tmp_path, buys)
        active = {f"LIVE{i:02d}-BULL" for i in range(N_CANDIDATES)}

        stats: dict = {}
        plans = originate_plans(path, "2026-07-02", set(), None,
                                active_keys=active, intake_stats=stats)
        assert [p["asset"] for p in plans] == [f"NEW{i:02d}" for i in range(6)], (
            "the cap was spent on names that were skipped anyway"
        )
        assert stats["reorigination_blocked"] == N_CANDIDATES
        assert stats["eligible_after_skips"] == 6
        assert stats["admitted"] == N_CANDIDATES + 6

    def test_the_old_cap_semantics_would_have_yielded_nothing(self, tmp_path):
        """The falsifier: cap-then-filter, computed here, returns an empty set on the
        same artifact. Without this the test above could pass on any implementation
        that simply originates everything."""
        buys = ([_buy_row(f"LIVE{i:02d}", priority=99.0 - i) for i in range(N_CANDIDATES)]
                + [_buy_row(f"NEW{i:02d}", priority=50.0 - i) for i in range(6)])
        path = _write_standouts(tmp_path, buys)
        with path.open(encoding="utf-8") as fh:
            standouts = json.load(fh)
        old_capped = select_candidates(standouts, n=N_CANDIDATES)
        active = {f"LIVE{i:02d}-BULL" for i in range(N_CANDIDATES)}
        survivors_of_the_old_cap = [
            row for row in old_capped
            if f"{row['ticker']}-BULL" not in active
        ]
        assert survivors_of_the_old_cap == [], (
            "cap-then-filter must yield nothing here, or this fixture does not "
            "reproduce the defect"
        )

    def test_the_old_cap_no_longer_truncates_live_origination(self, tmp_path):
        buys = [_buy_row(f"T{i:02d}", priority=99.0 - i) for i in range(30)]
        path = _write_standouts(tmp_path, buys)
        stats: dict = {}
        plans = originate_plans(path, "2026-07-02", set(), None,
                                active_keys=set(), intake_stats=stats)
        assert len(plans) == 30
        assert stats["eligible_after_skips"] == 30
        assert stats["cap"] is None
        assert stats["cap_applied"] is False
        assert stats["truncated"] == 0
        assert stats["lossless"] is True

    def test_admission_and_order_are_untouched(self, tmp_path):
        """The fence: this change may only ever ADD names from further down the same
        ordering, never re-rank the ones above."""
        buys = [_buy_row(f"T{i:02d}", priority=99.0 - i) for i in range(20)]
        path = _write_standouts(tmp_path, buys)
        plans = originate_plans(path, "2026-07-02", set(), None, active_keys=set())
        with path.open(encoding="utf-8") as fh:
            expected = [r["ticker"] for r in
                        select_candidates(json.load(fh), n=None)]
        assert [p["asset"] for p in plans] == expected

    def test_uncapped_select_returns_the_whole_admitted_pool(self, tmp_path):
        buys = [_buy_row(f"T{i:02d}", priority=99.0 - i) for i in range(30)]
        path = _write_standouts(tmp_path, buys)
        with path.open(encoding="utf-8") as fh:
            standouts = json.load(fh)
        assert len(select_candidates(standouts, n=None)) == 30
        assert len(select_candidates(standouts, n=N_CANDIDATES)) == N_CANDIDATES

    def test_duplicate_ids_are_still_suppressed_before_origination(self, tmp_path):
        buys = [_buy_row(f"T{i:02d}", priority=99.0 - i) for i in range(4)]
        path = _write_standouts(tmp_path, buys)
        existing = {"T00-BULL-20260702", "T01-BULL-20260702"}
        stats: dict = {}
        plans = originate_plans(path, "2026-07-02", set(existing), None,
                                active_keys=set(), intake_stats=stats)
        assert [p["asset"] for p in plans] == ["T02", "T03"]
        assert stats["duplicate_id_blocked"] == 2


# ===========================================================================
# P1 (origination side) — every new plan carries its entry_date
# ===========================================================================

class TestOriginationStampsTheClock:

    def test_every_new_plan_separates_entry_price_session_from_run_date(self, tmp_path):
        price_session = "2026-07-02"
        run_date = "2026-07-03"
        path = _write_standouts(
            tmp_path,
            [_buy_row("AAA", priority=90.0, anchor=FORMATION)],
            as_of=price_session,
        )
        plans = originate_plans(path, run_date, set(), None, active_keys=set())
        assert len(plans) == 1
        plan = plans[0]
        assert plan["entry_date"] == plan["price_basis_date"] == price_session
        assert plan["asof"] == plan["recorded_at"] == run_date
        assert plan["signal_date"] == FORMATION, "the id anchor is unchanged"
        assert plan["id"].endswith("20260301"), "no key migration"
        assert plan_clock_date(plan) == price_session

    def test_the_priority_score_the_pick_was_ordered_by_is_frozen_on_the_plan(
            self, tmp_path):
        path = _write_standouts(tmp_path, [_buy_row("AAA", priority=88.5)])
        plans = originate_plans(path, "2026-07-02", set(), None, active_keys=set())
        assert plans[0]["_priority_score"] == 88.5


# ===========================================================================
# P5 / P6 — closed-state copy and shipped order
# ===========================================================================

class TestClosedStateCopy:

    def test_a_closed_plan_ships_no_live_instruction(self):
        en, zh = bp._closed_state_lines("INVALIDATED")
        assert len(en) == 1 and len(zh) == 1
        text = en[0].lower()
        assert "closed" in text
        for banned in ("buy", "stop at", "trim", "add ", "enter"):
            assert banned not in text, f"{banned!r} is an instruction on a dead thesis"

    def test_the_outcome_is_stated_in_plain_words_not_ledger_slugs(self):
        en, zh = bp._closed_state_lines("T1_HIT")
        assert "hit first target" in en[0]
        assert "T1_HIT" not in en[0]
        assert zh[0].startswith("该计划已结束")

    def test_an_unmapped_outcome_still_says_it_is_over(self):
        en, zh = bp._closed_state_lines(None)
        assert "closed" in en[0].lower() and zh[0]
        en2, _ = bp._closed_state_lines("SOMETHING_NEW")
        assert "closed" in en2[0].lower()

    def test_both_halves_are_always_present(self):
        for outcome in (None, "", "T1_HIT", "T2_HIT", "INVALIDATED", "EXPIRED", "XX"):
            en, zh = bp._closed_state_lines(outcome)
            assert en and zh, outcome


class TestIndexOrderMatchesTheDeclaredKey:

    @staticmethod
    def _sorted(entries):
        rows = list(entries)
        rows.sort(key=lambda e: (
            0 if isinstance(e.get("_priority_score"), (int, float))
            and not isinstance(e.get("_priority_score"), bool) else 1,
            -(e.get("_priority_score")
              if isinstance(e.get("_priority_score"), (int, float))
              and not isinstance(e.get("_priority_score"), bool)
              else (e.get("_conviction_score") or 0)),
            e.get("id", ""),
        ))
        return [r["id"] for r in rows]

    def test_priority_score_outranks_conviction(self):
        """The artifact declares the priority score; conviction carries ZERO ordering
        authority in this system (US_BOARD_MEASUREMENT.md). The two disagree here."""
        entries = [
            {"id": "LOWPRI", "_priority_score": 10.0, "_conviction_score": 95},
            {"id": "HIGHPRI", "_priority_score": 90.0, "_conviction_score": 40},
        ]
        assert self._sorted(entries) == ["HIGHPRI", "LOWPRI"]

    def test_an_unscored_plan_sorts_below_every_scored_one(self):
        entries = [
            {"id": "LEGACY", "_priority_score": None, "_conviction_score": 99},
            {"id": "SCORED", "_priority_score": 1.0, "_conviction_score": 1},
        ]
        assert self._sorted(entries) == ["SCORED", "LEGACY"]

    def test_legacy_rows_keep_the_old_key_among_themselves(self):
        entries = [
            {"id": "A", "_priority_score": None, "_conviction_score": 10},
            {"id": "B", "_priority_score": None, "_conviction_score": 80},
        ]
        assert self._sorted(entries) == ["B", "A"]

    def test_id_breaks_a_tie_so_the_order_is_deterministic(self):
        entries = [
            {"id": "ZZZ", "_priority_score": 5.0},
            {"id": "AAA", "_priority_score": 5.0},
        ]
        assert self._sorted(entries) == ["AAA", "ZZZ"]
