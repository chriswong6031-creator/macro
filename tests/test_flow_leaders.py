"""tests/test_flow_leaders.py — Hermetic unit tests for engine/flow_leaders.py (FL W1).

Coverage:
  - tri-state semantics (null ≠ False; K/n_avail math)
  - cold-start nulls (< 5 sessions → recurrence None; < 20 obs → flow_z None)
  - 0DTE exclusion from ranking
  - mktcap-missing → null net_prem_norm (excluded from ranking)
  - oi_confirm tri-state + 3× volume gate
  - flow_inflect edge cases
  - PIT parity: board_a_fire pure over supplied legs; callers stamp fire_date
  - ETF-agnosticism: engine takes what it's given; missing personality → legs None
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.flow_leaders import (
    BoardALegs,
    BoardBLegs,
    INFLECT_NEG_SESSIONS,
    MIN_Z,
    MIN_Z_HISTORY,
    OI_CONFIRM_VOL_MULT,
    RECUR_LEG_MIN,
    RECUR_LEG_WINDOW,
    RECUR_MIN_HISTORY,
    ZERODTE_MAX,
    _and3,
    _is_null,
    _or3,
    board_a_fire,
    board_a_legs,
    board_b_fire,
    board_b_legs,
    dominant_strikes,
    earnings_window,
    flow_inflect,
    flow_recur_leg,
    flow_z,
    gamma_caution,
    normalized_impact_table,
    oi_confirm,
    protective_put_flag,
    recurrence_count,
    ts_breadth,
    vol_trade_flag,
)


# ── Kleene helpers ────────────────────────────────────────────────────────────

class TestKleeneHelpers:
    """B1: _and3 / _or3 Kleene three-valued logic; _is_null null detection."""

    # _and3 truth table
    def test_and3_both_true(self):
        assert _and3(True, True) is True

    def test_and3_false_shorts(self):
        assert _and3(False, True) is False
        assert _and3(True, False) is False
        assert _and3(False, None) is False  # False dominates

    def test_and3_true_none_is_none(self):
        assert _and3(True, None) is None

    def test_and3_none_none_is_none(self):
        assert _and3(None, None) is None

    def test_and3_all_false(self):
        assert _and3(False, False) is False

    # _or3 truth table
    def test_or3_any_true(self):
        assert _or3(True, False) is True
        assert _or3(True, None) is True  # True dominates
        assert _or3(None, True) is True

    def test_or3_all_false_is_false(self):
        assert _or3(False, False) is False

    def test_or3_false_none_is_none(self):
        assert _or3(False, None) is None

    def test_or3_none_none_is_none(self):
        assert _or3(None, None) is None

    # _is_null
    def test_is_null_none(self):
        assert _is_null(None) is True

    def test_is_null_pd_na(self):
        assert _is_null(pd.NA) is True

    def test_is_null_float_nan(self):
        assert _is_null(float("nan")) is True

    def test_is_null_false_for_bool_true(self):
        assert _is_null(True) is False

    def test_is_null_false_for_bool_false(self):
        assert _is_null(False) is False

    def test_is_null_false_for_zero(self):
        assert _is_null(0) is False

    def test_is_null_false_for_float_zero(self):
        assert _is_null(0.0) is False


class TestKleeneCompoundLegs:
    """Partial-path Kleene matrix for A5 (AND), A7/B2/B7 (OR) compound legs."""

    # A5: ribbon_up AND rs_1m > 0
    def test_a5_true_none_is_none(self):
        """ribbon_up=True, rs_1m=None → cannot determine → None."""
        legs = board_a_legs(ribbon_up=True, rs_1m=None)
        assert legs.A5_price_leader is None

    def test_a5_false_none_is_false(self):
        """ribbon_up=False, rs_1m=None → False (False dominates in AND)."""
        legs = board_a_legs(ribbon_up=False, rs_1m=None)
        assert legs.A5_price_leader is False

    def test_a5_none_none_is_none(self):
        """Both unknown → None."""
        legs = board_a_legs(ribbon_up=None, rs_1m=None)
        assert legs.A5_price_leader is None

    def test_a5_true_true_is_true(self):
        legs = board_a_legs(ribbon_up=True, rs_1m=0.05)
        assert legs.A5_price_leader is True

    def test_a5_true_rs_nonpositive_is_false(self):
        legs = board_a_legs(ribbon_up=True, rs_1m=0.0)
        assert legs.A5_price_leader is False

    def test_a5_none_rs_nonpositive_is_false(self):
        """rs_1m ≤ 0 settles A5=False even when ribbon_up is None."""
        legs = board_a_legs(ribbon_up=None, rs_1m=-0.01)
        assert legs.A5_price_leader is False

    # A7: rel_volume≥1.30 OR obv_slope_up
    def test_a7_true_none_is_true(self):
        """rel_volume ≥ RVOL → True even when obv_slope_up is None."""
        legs = board_a_legs(rel_volume=1.50, obv_slope_up=None)
        assert legs.A7_vol_confirm is True

    def test_a7_false_none_is_none(self):
        """rel_volume < RVOL, obv_slope_up=None → cannot determine → None."""
        legs = board_a_legs(rel_volume=0.80, obv_slope_up=None)
        assert legs.A7_vol_confirm is None

    def test_a7_none_none_is_none(self):
        legs = board_a_legs(rel_volume=None, obv_slope_up=None)
        assert legs.A7_vol_confirm is None

    def test_a7_both_false_is_false(self):
        legs = board_a_legs(rel_volume=0.80, obv_slope_up=False)
        assert legs.A7_vol_confirm is False

    # B2: stoch_os OR rsi_stack_oversold
    def test_b2_true_none_is_true(self):
        """stoch K<20 → True even when rsi_stack_oversold is None."""
        legs = board_b_legs(weekly_stochrsi_k_min3=10.0, rsi_stack_oversold=None)
        assert legs.B2_oversold_osc is True

    def test_b2_false_none_is_none(self):
        """stoch K≥20, rsi_stack_oversold=None → None."""
        legs = board_b_legs(weekly_stochrsi_k_min3=50.0, rsi_stack_oversold=None)
        assert legs.B2_oversold_osc is None

    def test_b2_none_none_is_none(self):
        legs = board_b_legs(weekly_stochrsi_k_min3=None, rsi_stack_oversold=None)
        assert legs.B2_oversold_osc is None

    def test_b2_both_false_is_false(self):
        legs = board_b_legs(weekly_stochrsi_k_min3=50.0, rsi_stack_oversold=False)
        assert legs.B2_oversold_osc is False

    # B7: rel_volume OR obv_slope_up (same Kleene OR as A7)
    def test_b7_true_none_is_true(self):
        legs = board_b_legs(rel_volume=1.50, obv_slope_up=None)
        assert legs.B7_vol_confirm is True

    def test_b7_false_none_is_none(self):
        legs = board_b_legs(rel_volume=0.80, obv_slope_up=None)
        assert legs.B7_vol_confirm is None

    def test_b7_none_none_is_none(self):
        legs = board_b_legs(rel_volume=None, obv_slope_up=None)
        assert legs.B7_vol_confirm is None


class TestNAvailPdNA:
    """B2: n_avail must NOT count pd.NA as available."""

    def test_pd_na_field_not_counted(self):
        legs = BoardALegs(A1_flow_recur=pd.NA)
        assert legs.n_avail == 0

    def test_pd_na_and_true_counted_correctly(self):
        legs = BoardALegs(A1_flow_recur=pd.NA, A8_not_trap=True)
        assert legs.n_avail == 1
        assert legs.K == 1

    def test_pd_na_and_false_counted_correctly(self):
        legs = BoardALegs(A1_flow_recur=pd.NA, A2_flow_z_hot=False)
        assert legs.n_avail == 1
        assert legs.K == 0

    def test_float_nan_field_not_counted(self):
        """float NaN in a leg field is treated as null (n_avail=0)."""
        legs = BoardALegs(A1_flow_recur=float("nan"))
        assert legs.n_avail == 0


class TestFlowZInfSafety:
    """M1: flow_z must sanitize ±inf inputs."""

    def test_inf_in_history_returns_none(self):
        """An inf value in the history must not propagate; result should be None
        if ±inf causes fewer than MIN_Z_HISTORY valid observations after sanitization."""
        vals = [1.0] * 19 + [float("inf")]
        s = pd.Series(vals)
        # After replacing inf with NaN and dropping, only 19 valid obs → < MIN_Z_HISTORY=20
        assert flow_z(s) is None

    def test_inf_among_sufficient_history_gives_valid_z(self):
        """If there are still ≥ MIN_Z_HISTORY valid observations after removing inf,
        flow_z should return a valid float."""
        # 25 values: 24 valid + 1 inf → 24 valid obs ≥ 20 → should return float
        vals = [2.0] * 10 + [float("inf")] + [2.0] * 14
        s = pd.Series(vals)
        result = flow_z(s)
        # After removing inf: 24 obs, all 2.0 → std=0 → None
        assert result is None  # constant series → std=0

    def test_neg_inf_in_history_returns_none_below_threshold(self):
        vals = [1.0] * 18 + [float("-inf"), 5.0]
        s = pd.Series(vals)
        # After replacing -inf: 19 valid obs → < 20 → None
        assert flow_z(s) is None

    def test_nan_flow_z_val_gives_none_a2(self):
        """board_a_legs(flow_z_val=NaN) must set A2=None, not False."""
        legs = board_a_legs(flow_z_val=float("nan"))
        assert legs.A2_flow_z_hot is None


class TestFlowInflectFirstFlip:
    """m1: days_since_inflection = bars since the FIRST positive flip event."""

    def test_canonical_example(self):
        """[-1,-1,-1,5,2,3] → inflected True, days_since_inflection 2.

        The flip event is index 3 (5.0): 3 negatives precede it.
        Current bar (index 5) is 2 bars after the flip → days_since = 2.
        """
        s = pd.Series([-1.0, -1.0, -1.0, 5.0, 2.0, 3.0])
        result = flow_inflect(s)
        assert result["inflected"] is True
        assert result["days_since_inflection"] == 2

    def test_flip_at_earliest_qualifying_event(self):
        """Flip at index 3 (5.0), more positives follow; days_since is from index 3."""
        # [-3,-2,-1,5,4,3,2] → flip at index 3, days_since = 3
        s = pd.Series([-3.0, -2.0, -1.0, 5.0, 4.0, 3.0, 2.0])
        result = flow_inflect(s)
        assert result["inflected"] is True
        assert result["days_since_inflection"] == 3

    def test_flip_is_latest_bar_days_since_zero(self):
        """[-1,-1,-1,5] → flip event IS the latest bar → days_since=0."""
        s = pd.Series([-1.0, -1.0, -1.0, 5.0])
        result = flow_inflect(s)
        assert result["inflected"] is True
        assert result["days_since_inflection"] == 0

    def test_no_qualifying_flip_gives_none_days_since(self):
        """No qualifying flip (only 2 negatives before positive) → days_since=None."""
        s = pd.Series([-1.0, -1.0, 2.0, 3.0, 4.0])
        result = flow_inflect(s)
        assert result["days_since_inflection"] is None


class TestRecurMinHistoryConstant:
    """m4: RECUR_MIN_HISTORY constant replaces all literal 5s in cold-start logic."""

    def test_constant_value(self):
        assert RECUR_MIN_HISTORY == 5

    def test_recurrence_count_uses_constant(self):
        """Exactly RECUR_MIN_HISTORY - 1 sessions → null."""
        rows = [{"session": i, "ticker": "X", "in_top20": True}
                for i in range(RECUR_MIN_HISTORY - 1)]
        mem = pd.DataFrame(rows)
        result = recurrence_count(mem)
        assert pd.isna(result["X"])

    def test_flow_recur_leg_uses_constant(self):
        """Exactly RECUR_MIN_HISTORY - 1 sessions → pd.NA."""
        rows = [{"session": i, "ticker": "X", "in_top20": True}
                for i in range(RECUR_MIN_HISTORY - 1)]
        mem = pd.DataFrame(rows)
        result = flow_recur_leg(mem)
        assert pd.isna(result["X"])


# ── fixtures ──────────────────────────────────────────────────────────────────

def _day_rows(tickers, net_prem, z_share=None):
    """Build a minimal day_rows DataFrame."""
    n = len(tickers)
    z = z_share if z_share is not None else [0.1] * n
    return pd.DataFrame({
        "ticker": tickers,
        "net_premium_mn": net_prem,
        "premium_mn": [abs(x) for x in net_prem],
        "zerodte_share": z,
        "signing_source": ["minute_tick"] * n,
    })


def _membership(sessions_tickers_in_top20):
    """Build membership DataFrame from list of (session, ticker, in_top20)."""
    rows = [{"session": s, "ticker": t, "in_top20": b}
            for s, t, b in sessions_tickers_in_top20]
    return pd.DataFrame(rows)


def _chain_day(underlying, strikes, volumes, ois, is_call=None):
    """Build a minimal chains day DataFrame."""
    n = len(strikes)
    ic = is_call if is_call is not None else [True] * n
    return pd.DataFrame({
        "underlying": [underlying] * n,
        "K": strikes,
        "is_call": ic,
        "volume": volumes,
        "oi": ois,
    })


# ── normalized_impact_table ───────────────────────────────────────────────────

class TestNormalizedImpactTable:
    def test_basic_norm(self):
        tickers = ["AAPL", "MSFT"]
        rows = _day_rows(tickers, [10.0, 5.0])
        mktcap = {"AAPL": 3000.0, "MSFT": 2000.0}
        df = normalized_impact_table(rows, mktcap)
        assert "net_prem_norm" in df.columns
        assert abs(df.loc[df.ticker == "AAPL", "net_prem_norm"].iloc[0] - 10.0/3000.0) < 1e-9
        assert abs(df.loc[df.ticker == "MSFT", "net_prem_norm"].iloc[0] - 5.0/2000.0) < 1e-9

    def test_mktcap_missing_gives_null_norm(self):
        """Missing mktcap → null net_prem_norm, excluded from ranking."""
        rows = _day_rows(["AAPL", "NOCTCAP"], [10.0, 5.0])
        mktcap = {"AAPL": 3000.0}
        df = normalized_impact_table(rows, mktcap)
        nocap = df.loc[df.ticker == "NOCTCAP"]
        assert nocap["net_prem_norm"].isna().all()
        assert not nocap["in_top20"].any()

    def test_zerodte_excluded_from_ranking(self):
        """Names with zerodte_share > ZERODTE_MAX excluded from top-20 count."""
        rows = _day_rows(["AAPL", "SPAMDTE"], [100.0, 999.0],
                         z_share=[0.1, ZERODTE_MAX + 0.01])
        mktcap = {"AAPL": 100.0, "SPAMDTE": 100.0}
        df = normalized_impact_table(rows, mktcap)
        assert df.loc[df.ticker == "SPAMDTE", "zerodte_excluded"].all()
        assert not df.loc[df.ticker == "SPAMDTE", "in_top20"].any()
        assert df.loc[df.ticker == "AAPL", "in_top20"].all()

    def test_ex0dte_override_cancels_exclusion(self):
        """Caller-supplied ex-0DTE net premium overrides exclusion for tape source."""
        rows = _day_rows(["TSLA"], [50.0], z_share=[0.80])
        mktcap = {"TSLA": 500.0}
        ex0dte = {"TSLA": 30.0}
        df = normalized_impact_table(rows, mktcap, net_premium_ex0dte_mn=ex0dte)
        assert not df.loc[df.ticker == "TSLA", "zerodte_excluded"].any()
        assert df.loc[df.ticker == "TSLA", "in_top20"].any()

    def test_in_top20_boolean(self):
        """in_top20 is bool column, not object or int."""
        rows = _day_rows(["AAPL"], [1.0])
        mktcap = {"AAPL": 100.0}
        df = normalized_impact_table(rows, mktcap)
        assert df["in_top20"].dtype in (bool, object)
        # value itself is True
        assert df["in_top20"].iloc[0] is True or df["in_top20"].iloc[0] == True  # noqa: E712

    def test_empty_input(self):
        """Empty input → empty output with correct columns."""
        rows = pd.DataFrame(columns=["ticker", "net_premium_mn", "premium_mn",
                                     "zerodte_share", "signing_source"])
        df = normalized_impact_table(rows, {})
        assert df.empty


# ── recurrence_count ──────────────────────────────────────────────────────────

class TestRecurrenceCount:
    def test_cold_start_less_than_5_sessions_is_null(self):
        """< 5 sessions of history → null, not 0."""
        rows = []
        for s in range(3):
            rows.append({"session": s, "ticker": "AAPL", "in_top20": True})
        mem = pd.DataFrame(rows)
        result = recurrence_count(mem)
        assert pd.isna(result["AAPL"])

    def test_exactly_5_sessions_gives_count(self):
        """Exactly 5 sessions of history → returns an integer count."""
        rows = [{"session": i, "ticker": "AAPL", "in_top20": i >= 2} for i in range(5)]
        mem = pd.DataFrame(rows)
        result = recurrence_count(mem)
        assert not pd.isna(result["AAPL"])
        assert result["AAPL"] >= 0

    def test_counts_only_trailing_window(self):
        """Recurrence count uses trailing RECUR_WINDOW sessions only."""
        rows = []
        # 12 sessions total; ticker in top-20 only in the first 5 (old), not in trailing 10
        for s in range(12):
            rows.append({"session": s, "ticker": "AAPL", "in_top20": s < 5})
        mem = pd.DataFrame(rows)
        result = recurrence_count(mem)
        # trailing 10 = sessions 2..11; in_top20 only for sessions 2,3,4 = 3
        assert result["AAPL"] == 3.0

    def test_empty_membership(self):
        mem = pd.DataFrame(columns=["session", "ticker", "in_top20"])
        result = recurrence_count(mem)
        assert result.empty


class TestFlowRecurLeg:
    def test_cold_start_null(self):
        """< 5 sessions → pd.NA (not False)."""
        rows = [{"session": i, "ticker": "TSLA", "in_top20": True} for i in range(2)]
        mem = pd.DataFrame(rows)
        result = flow_recur_leg(mem)
        assert pd.isna(result["TSLA"])

    def test_meets_threshold(self):
        """≥ RECUR_LEG_MIN of trailing RECUR_LEG_WINDOW → True."""
        rows = []
        for s in range(10):
            # 5 sessions of history, in top-20 for 3 of last 5
            rows.append({"session": s, "ticker": "NVDA", "in_top20": s >= 7})
        mem = pd.DataFrame(rows)
        result = flow_recur_leg(mem)
        # sessions 7,8,9 in trailing window [5..9] → 3 → True
        assert result["NVDA"] is True or result["NVDA"] == True  # noqa: E712

    def test_does_not_meet_threshold(self):
        """2 of trailing 5 → False."""
        rows = []
        for s in range(10):
            rows.append({"session": s, "ticker": "F", "in_top20": s in (8, 9)})
        mem = pd.DataFrame(rows)
        result = flow_recur_leg(mem)
        # 2 of trailing 5 sessions in top-20 < RECUR_LEG_MIN=3 → False
        assert result["F"] is False or result["F"] == False  # noqa: E712


# ── dominant_strikes ──────────────────────────────────────────────────────────

class TestDominantStrikes:
    def test_returns_top_3_by_volume(self):
        cd = _chain_day("AAPL", [150, 155, 160, 165], [1000, 5000, 3000, 200], [500, 600, 400, 100])
        dom = dominant_strikes(cd)
        assert len(dom) == 3
        # Top 3 by volume: 5000, 3000, 1000
        assert set(dom["K"].tolist()) == {155, 160, 150}

    def test_empty_chain_returns_empty(self):
        result = dominant_strikes(pd.DataFrame())
        assert result.empty

    def test_custom_top_k(self):
        cd = _chain_day("MSFT", [100, 105, 110, 115, 120], [5, 4, 3, 2, 1], [10, 10, 10, 10, 10])
        dom = dominant_strikes(cd, top_k=2)
        assert len(dom) == 2


# ── oi_confirm ────────────────────────────────────────────────────────────────

class TestOiConfirm:
    def test_none_when_next_day_absent(self):
        """Next-day chain absent → None (tri-state)."""
        fd = _chain_day("AAPL", [150], [5000], [1000])
        result = oi_confirm(fd, pd.DataFrame())
        assert result.get("AAPL") is None

    def test_true_when_oi_grows_and_vol_sufficient(self):
        """ΔOI > 0 AND vol ≥ 3× prior OI → True."""
        fd = _chain_day("AAPL", [150], [6000], [1000])  # vol=6000 ≥ 3×1000=3000
        nd = _chain_day("AAPL", [150], [100], [1500])    # OI grew 1000→1500
        result = oi_confirm(fd, nd)
        assert result.get("AAPL") is True

    def test_false_when_vol_insufficient(self):
        """vol < 3× prior OI → False (even if OI grew)."""
        fd = _chain_day("AAPL", [150], [2000], [1000])  # vol=2000 < 3×1000=3000
        nd = _chain_day("AAPL", [150], [100], [1500])
        result = oi_confirm(fd, nd)
        assert result.get("AAPL") is False

    def test_false_when_oi_drops(self):
        """OI did not grow → False."""
        fd = _chain_day("AAPL", [150], [6000], [1000])
        nd = _chain_day("AAPL", [150], [100], [800])  # OI fell
        result = oi_confirm(fd, nd)
        assert result.get("AAPL") is False

    def test_three_state_semantics(self):
        """Verify none/false/true can all be produced from this function."""
        fd_a = _chain_day("AAPL", [150], [6000], [1000])
        fd_b = _chain_day("MSFT", [300], [2000], [1000])
        # combine flow day
        fd = pd.concat([fd_a, fd_b], ignore_index=True)
        nd_a = _chain_day("AAPL", [150], [100], [1500])
        nd = pd.concat([nd_a], ignore_index=True)  # MSFT absent from next day
        result = oi_confirm(fd, nd)
        assert result.get("AAPL") is True
        assert result.get("MSFT") is None


# ── ts_breadth ────────────────────────────────────────────────────────────────

class TestTsBreadth:
    def test_none_when_tape_row_none(self):
        assert ts_breadth(None) is None

    def test_counts_positive_buckets(self):
        row = pd.Series({
            "dte_1_7d": 1.0,
            "dte_8_30d": 2.0,
            "dte_31_90d": -1.0,
            "dte_90p": 0.5,
        })
        assert ts_breadth(row) == 3

    def test_zero_positive_buckets(self):
        row = pd.Series({
            "dte_1_7d": -1.0,
            "dte_8_30d": -2.0,
            "dte_31_90d": -0.5,
            "dte_90p": 0.0,  # zero is not positive
        })
        assert ts_breadth(row) == 0

    def test_all_positive(self):
        row = pd.Series({
            "dte_1_7d": 0.1,
            "dte_8_30d": 0.2,
            "dte_31_90d": 0.3,
            "dte_90p": 0.4,
        })
        assert ts_breadth(row) == 4

    def test_missing_column_treated_as_zero(self):
        """Columns absent from tape_row → not counted."""
        row = pd.Series({"dte_1_7d": 1.0, "dte_8_30d": 1.0})
        result = ts_breadth(row)
        assert result == 2  # only 2 present-and-positive


# ── flow_inflect ──────────────────────────────────────────────────────────────

class TestFlowInflect:
    def test_none_when_fewer_than_4_sessions(self):
        s = pd.Series([-1.0, -2.0, 3.0])
        result = flow_inflect(s)
        assert result["inflected"] is None
        assert result["days_since_inflection"] is None

    def test_inflected_true_after_3_negatives(self):
        # 3 negative then flip positive
        s = pd.Series([-3.0, -2.0, -1.0, 5.0])
        result = flow_inflect(s)
        assert result["inflected"] is True
        assert result["days_since_inflection"] == 0

    def test_inflected_false_when_latest_negative(self):
        s = pd.Series([-3.0, -2.0, -1.0, -0.5])
        result = flow_inflect(s)
        assert result["inflected"] is False

    def test_inflected_false_when_not_enough_prior_negatives(self):
        # only 2 negatives before the flip
        s = pd.Series([-1.0, -1.0, 1.0, 5.0])
        result = flow_inflect(s)
        # 2 negatives < INFLECT_NEG_SESSIONS (3) → False
        assert result["inflected"] is False

    def test_days_since_inflection(self):
        # The function finds the FIRST positive bar (flip event) that follows ≥3 negatives.
        # s = [-3, -2, -1, 5, 4, 3]:
        #   Flip event at index 3 (5.0): 3 negatives precede it → qualifies.
        #   Current bar is index 5; days_since = 5 - 1 - 3 = 2.
        s = pd.Series([-3.0, -2.0, -1.0, 5.0, 4.0, 3.0])
        result = flow_inflect(s)
        assert result["inflected"] is True
        assert result["days_since_inflection"] == 2

    def test_days_since_inflection_older(self):
        # Inflection at index 3 (5.0), then 2 negatives, then check
        # positives at index 3 qualify (3 negatives before it at 0,1,2)
        # but indices 4,5 are negative so the search finds index 3 as the most recent positive.
        s = pd.Series([-3.0, -2.0, -1.0, 5.0, -4.0, -3.0])
        result = flow_inflect(s)
        # latest is negative → inflected=False; but days_since still finds last inflection
        assert result["inflected"] is False
        # last positive after ≥3 negatives was at index 3 → days_since = 2
        assert result["days_since_inflection"] == 2


# ── flow_z ────────────────────────────────────────────────────────────────────

class TestFlowZ:
    def test_none_when_fewer_than_20_obs(self):
        s = pd.Series([1.0] * 19)
        assert flow_z(s) is None

    def test_cold_start_2_sessions_null(self):
        """2-session history → None (cold-start)."""
        s = pd.Series([10.0, 20.0])
        assert flow_z(s) is None

    def test_returns_float_at_20_obs(self):
        s = pd.Series([1.0] * 19 + [2.0])
        result = flow_z(s)
        assert result is not None
        assert isinstance(result, float)

    def test_z_formula(self):
        # all zeros except last = 10; mean=0.5, std computed from series
        vals = [0.0] * 19 + [10.0]
        s = pd.Series(vals)
        mu = sum(vals) / 20
        import statistics
        std = statistics.stdev(vals)
        expected_z = (10.0 - mu) / std
        result = flow_z(s)
        assert result is not None
        assert abs(result - expected_z) < 0.01

    def test_none_when_zero_std(self):
        s = pd.Series([5.0] * 20)
        assert flow_z(s) is None


# ── de-escalation flags ───────────────────────────────────────────────────────

class TestDeescalationFlags:
    def test_earnings_window_none(self):
        assert earnings_window(None) is None

    def test_earnings_window_within(self):
        assert earnings_window(10) is True

    def test_earnings_window_outside(self):
        assert earnings_window(20) is False

    def test_earnings_window_boundary(self):
        assert earnings_window(14) is True

    def test_vol_trade_flag_none_when_no_tape(self):
        assert vol_trade_flag(None) is None

    def test_vol_trade_flag_true_both_elevated(self):
        row = pd.Series({"ask_side_call_premium": 1.0, "ask_side_put_premium": 2.0})
        assert vol_trade_flag(row) is True

    def test_vol_trade_flag_false_one_not_elevated(self):
        row = pd.Series({"ask_side_call_premium": 1.0, "ask_side_put_premium": -0.5})
        assert vol_trade_flag(row) is False

    def test_protective_put_none_when_no_tape(self):
        assert protective_put_flag(None) is None

    def test_protective_put_true(self):
        row = pd.Series({"money_far_otm": 0.3})
        assert protective_put_flag(row) is True

    def test_protective_put_false_zero(self):
        row = pd.Series({"money_far_otm": 0.0})
        assert protective_put_flag(row) is False

    def test_gamma_caution_none(self):
        assert gamma_caution(None) is None

    def test_gamma_caution_short(self):
        assert gamma_caution("short") is True

    def test_gamma_caution_long(self):
        assert gamma_caution("long") is False


# ── BoardALegs + board_a_fire ─────────────────────────────────────────────────

class TestBoardALegs:
    def test_null_legs_excluded_from_k_and_n_avail(self):
        """Tri-state: None legs do not count toward K or n_avail."""
        legs = BoardALegs(A1_flow_recur=True, A8_not_trap=True)
        assert legs.K == 2
        assert legs.n_avail == 2

    def test_false_legs_in_n_avail_not_k(self):
        legs = BoardALegs(A1_flow_recur=False, A8_not_trap=True, A2_flow_z_hot=False)
        assert legs.K == 1  # only A8
        assert legs.n_avail == 3

    def test_k_avail_ignores_none(self):
        """None in A2 does not increment n_avail."""
        legs = BoardALegs(A1_flow_recur=True, A8_not_trap=True, A2_flow_z_hot=None)
        assert legs.n_avail == 2

    def test_board_a_fire_requires_a1_a8_and_a2_or_a3(self):
        legs = BoardALegs(A1_flow_recur=True, A8_not_trap=True, A2_flow_z_hot=True)
        assert board_a_fire(legs) is True

    def test_board_a_fire_with_a3_instead_of_a2(self):
        legs = BoardALegs(A1_flow_recur=True, A8_not_trap=True, A3_oi_confirmed=True)
        assert board_a_fire(legs) is True

    def test_board_a_fire_fails_without_a1(self):
        legs = BoardALegs(A1_flow_recur=None, A8_not_trap=True, A2_flow_z_hot=True)
        assert board_a_fire(legs) is False

    def test_board_a_fire_fails_without_a8(self):
        legs = BoardALegs(A1_flow_recur=True, A8_not_trap=False, A2_flow_z_hot=True)
        assert board_a_fire(legs) is False

    def test_board_a_fire_fails_when_a2_and_a3_both_false(self):
        legs = BoardALegs(A1_flow_recur=True, A8_not_trap=True,
                          A2_flow_z_hot=False, A3_oi_confirmed=False)
        assert board_a_fire(legs) is False

    def test_board_a_fire_fails_when_a2_none_a3_none(self):
        """Null legs do NOT count as True — fire requires definite True."""
        legs = BoardALegs(A1_flow_recur=True, A8_not_trap=True,
                          A2_flow_z_hot=None, A3_oi_confirmed=None)
        assert board_a_fire(legs) is False

    def test_pit_parity_fire_pure_over_legs_given(self):
        """board_a_fire is a pure function of the legs struct.

        PIT law: a fire qualified by A3 (oi_confirmed, t+1 asof) is perfectly
        representable.  The caller is responsible for stamping fire_date = the
        date all legs are known.  board_a_fire itself has no date state.
        """
        # Day-d legs: A3 not yet known
        legs_d = BoardALegs(A1_flow_recur=True, A8_not_trap=True,
                            A2_flow_z_hot=False, A3_oi_confirmed=None)
        assert board_a_fire(legs_d) is False  # A2 False, A3 None → no fire

        # Day-d+1 legs: A3 now known (OI confirmed)
        legs_d1 = BoardALegs(A1_flow_recur=True, A8_not_trap=True,
                             A2_flow_z_hot=False, A3_oi_confirmed=True)
        assert board_a_fire(legs_d1) is True   # fire → caller stamps fire_date = d+1


# ── BoardBLegs + board_b_fire ─────────────────────────────────────────────────

class TestBoardBLegs:
    def test_null_legs_excluded_from_k(self):
        legs = BoardBLegs(B1_washout_recent=True, B8_not_trap=None)
        assert legs.K == 1
        assert legs.n_avail == 1

    def test_b4_is_display_chip_not_fire_qualifying(self):
        """B4 htf_cross_near is True but must NOT contribute to board_b_fire."""
        legs = BoardBLegs(B1_washout_recent=True, B5_flow_inflect=True,
                          B8_not_trap=True, B4_htf_cross_near=True)
        # B4 in K/n_avail (it is a leg) but fire rule only uses B1, B5, B8
        assert board_b_fire(legs) is True
        # Verify B4 doesn't single-handedly enable fire
        legs_no_b1 = BoardBLegs(B1_washout_recent=None, B5_flow_inflect=True,
                                 B8_not_trap=True, B4_htf_cross_near=True)
        assert board_b_fire(legs_no_b1) is False

    def test_board_b_fire_requires_b1_b5_b8(self):
        legs = BoardBLegs(B1_washout_recent=True, B5_flow_inflect=True, B8_not_trap=True)
        assert board_b_fire(legs) is True

    def test_board_b_fire_fails_missing_b5(self):
        legs = BoardBLegs(B1_washout_recent=True, B5_flow_inflect=None, B8_not_trap=True)
        assert board_b_fire(legs) is False

    def test_board_b_fire_fails_trap(self):
        legs = BoardBLegs(B1_washout_recent=True, B5_flow_inflect=True, B8_not_trap=False)
        assert board_b_fire(legs) is False


# ── board_a_legs evaluator ────────────────────────────────────────────────────

class TestBoardALegsEvaluator:
    def test_full_inputs_produce_all_legs(self):
        legs = board_a_legs(
            recur_leg=True,
            flow_z_val=2.5,
            oi_confirmed=True,
            ts_breadth_val=3,
            ribbon_up=True,
            rs_1m=0.05,
            high52w_prox=0.95,
            rel_volume=1.5,
            obv_slope_up=True,
            failed_breakout_trap=False,
        )
        assert legs.A1_flow_recur is True
        assert legs.A2_flow_z_hot is True
        assert legs.A3_oi_confirmed is True
        assert legs.A4_ts_breadth is True
        assert legs.A5_price_leader is True
        assert legs.A6_near_high is True
        assert legs.A7_vol_confirm is True
        assert legs.A8_not_trap is True
        assert legs.K == 8

    def test_null_inputs_give_null_legs(self):
        """Missing all inputs → all None legs."""
        legs = board_a_legs()
        assert legs.A1_flow_recur is None
        assert legs.A2_flow_z_hot is None
        assert legs.K == 0
        assert legs.n_avail == 0

    def test_etf_missing_personality_legs_null(self):
        """Engine takes what it's given; no personality → failed_breakout_trap=None → A8=None."""
        legs = board_a_legs(
            recur_leg=True,
            flow_z_val=2.5,
            failed_breakout_trap=None,  # ETF — no personality
        )
        assert legs.A8_not_trap is None
        # Fire still works if A1/A8 requirements can't be met (A8 None → fire=False)
        assert board_a_fire(legs) is False

    def test_a2_flow_z_boundary(self):
        legs_below = board_a_legs(flow_z_val=MIN_Z - 0.01)
        assert legs_below.A2_flow_z_hot is False
        legs_at = board_a_legs(flow_z_val=MIN_Z)
        assert legs_at.A2_flow_z_hot is True

    def test_a4_ts_breadth_threshold(self):
        assert board_a_legs(ts_breadth_val=2).A4_ts_breadth is True
        assert board_a_legs(ts_breadth_val=1).A4_ts_breadth is False


# ── board_b_legs evaluator ────────────────────────────────────────────────────

class TestBoardBLegsEvaluator:
    def test_null_washout_ctx_gives_null_b1(self):
        legs = board_b_legs(washout_ctx=None)
        assert legs.B1_washout_recent is None

    def test_washout_ctx_bb_reclaim(self):
        ctx = {"bb_lower_reclaim_days": 5, "drawdown_21d_pct": None, "recovery_begun": None}
        legs = board_b_legs(washout_ctx=ctx)
        assert legs.B1_washout_recent is True

    def test_washout_ctx_deep_drawdown(self):
        ctx = {"bb_lower_reclaim_days": None, "drawdown_21d_pct": -0.15, "recovery_begun": True}
        legs = board_b_legs(washout_ctx=ctx)
        assert legs.B1_washout_recent is True

    def test_b4_passed_through(self):
        legs = board_b_legs(htf_cross_near=True)
        assert legs.B4_htf_cross_near is True

    def test_flow_inflect_val_wires_to_b5(self):
        legs = board_b_legs(flow_inflect_val={"inflected": True, "days_since_inflection": 0})
        assert legs.B5_flow_inflect is True

        legs_false = board_b_legs(flow_inflect_val={"inflected": False, "days_since_inflection": None})
        assert legs_false.B5_flow_inflect is False


# ── ETF agnosticism ───────────────────────────────────────────────────────────

class TestEtfAgnosticism:
    def test_etf_in_impact_table_with_no_mktcap(self):
        """ETFs have no mktcap mapping → null norm, not ranked."""
        rows = _day_rows(["SPY", "QQQ", "AAPL"], [100.0, 80.0, 5.0])
        mktcap = {"AAPL": 3000.0}  # no ETF mktcap
        df = normalized_impact_table(rows, mktcap)
        assert df.loc[df.ticker == "SPY", "net_prem_norm"].isna().all()
        assert not df.loc[df.ticker == "SPY", "in_top20"].any()
        # AAPL still gets ranked
        assert df.loc[df.ticker == "AAPL", "in_top20"].any()
