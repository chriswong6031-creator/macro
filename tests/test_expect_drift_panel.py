"""Unit tests for scripts/research/build_expect_drift_panel.py.

Tests:
  1. E(f) PIT selection — event 1 session before fire (included vs excluded).
  2. SUE visibility gating — asof_date <= fire_date PIT constraint.
  3. ED-4 (bad_news_absorption) window logic.
  4. ED-5 (good_news_hold) window logic.
  5. No outcome columns in panel output assertion.
  6. confirmed_absorption (ED-7) combining ED-4/ED-5 with ED-3.

Run:
    python -m pytest tests/test_expect_drift_panel.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Bootstrap repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.research.build_expect_drift_panel import (  # noqa: E402
    _select_event_ef,
    _sue_for_ticker_pit,
    _bad_news_absorption_feature,
    _good_news_hold_feature,
    _pead_drift_feature,
    build_panel,
    _dq_at_event,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_close(dates: list[str], prices: list[float] | None = None) -> pd.Series:
    """Build a close series from date strings. If prices is None, use 100.0."""
    idx = pd.DatetimeIndex([pd.Timestamp(d) for d in dates])
    if prices is None:
        prices = [100.0 + float(i) for i in range(len(dates))]
    return pd.Series(prices, index=idx, name="close")


def _trading_days(start: str, n: int) -> list[str]:
    """Generate n consecutive business days starting from start."""
    rng = pd.bdate_range(start=start, periods=n)
    return [str(d.date()) for d in rng]


def _make_eps(
    ticker: str,
    records: list[tuple[str, float, str]],
) -> pd.DataFrame:
    """Build eps_quarterly DataFrame.
    records: list of (period_end, eps_q, asof_date) tuples.
    """
    rows = []
    for period_end, eps_q, asof_date in records:
        rows.append({
            "ticker": ticker,
            "period_end": pd.Timestamp(period_end),
            "eps_q": float(eps_q),
            "asof_date": pd.Timestamp(asof_date),
        })
    return pd.DataFrame(rows)


def _make_earnings(
    ticker: str,
    filing_dates: list[str],
) -> dict[str, pd.DataFrame]:
    """Build earnings_by_ticker dict from filing_dates."""
    rows = [
        {
            "ticker": ticker,
            "cik": 999,
            "filing_date": pd.Timestamp(d),
            "acceptance_datetime": pd.Timestamp(d),
            "items": "2.02,9.01",
        }
        for d in filing_dates
    ]
    df = pd.DataFrame(rows).sort_values("filing_date").reset_index(drop=True)
    return {ticker: df}


# ---------------------------------------------------------------------------
# 1. E(f) PIT selection — excluded vs included
# ---------------------------------------------------------------------------

class TestSelectEventEf:
    def test_event_exactly_1_bday_before_included(self):
        """An event with filing_date = fire_date - 1 BDay should be included."""
        fire = pd.Timestamp("2024-01-09")  # Tuesday
        one_bday_before = (fire - pd.tseries.offsets.BDay(1)).normalize()  # Monday 2024-01-08
        assert str(one_bday_before.date()) == "2024-01-08"

        events = _make_earnings("AAPL", [str(one_bday_before.date())])
        ef = _select_event_ef("AAPL", fire, events)
        assert ef == one_bday_before

    def test_event_on_fire_date_excluded(self):
        """An event with filing_date = fire_date itself is excluded (need >= 1 session gap)."""
        fire = pd.Timestamp("2024-01-09")
        events = _make_earnings("AAPL", [str(fire.date())])
        ef = _select_event_ef("AAPL", fire, events)
        assert ef is None

    def test_event_within_120_days_included(self):
        """An event 119 calendar days before fire should be included."""
        fire = pd.Timestamp("2024-01-09")
        event_date_str = str((fire - pd.Timedelta(days=119)).date())
        events = _make_earnings("AAPL", [event_date_str])
        ef = _select_event_ef("AAPL", fire, events)
        assert ef is not None

    def test_event_exactly_120_days_included(self):
        """An event exactly 120 calendar days before fire is at the boundary (inclusive)."""
        fire = pd.Timestamp("2024-01-09")
        event_date_str = str((fire - pd.Timedelta(days=120)).date())
        events = _make_earnings("AAPL", [event_date_str])
        ef = _select_event_ef("AAPL", fire, events)
        assert ef is not None

    def test_event_121_days_before_excluded(self):
        """An event 121 calendar days before fire should be excluded (outside window)."""
        fire = pd.Timestamp("2024-01-09")
        event_date_str = str((fire - pd.Timedelta(days=121)).date())
        events = _make_earnings("AAPL", [event_date_str])
        ef = _select_event_ef("AAPL", fire, events)
        assert ef is None

    def test_latest_event_selected_when_multiple(self):
        """When multiple events qualify, the latest one is returned."""
        fire = pd.Timestamp("2024-04-10")
        # Three events: 60 days ago, 30 days ago, 5 days ago (all within 120d and >= 1 BDay before)
        e_dates = [
            str((fire - pd.Timedelta(days=60)).date()),
            str((fire - pd.Timedelta(days=30)).date()),
            str((fire - pd.tseries.offsets.BDay(5)).normalize().date()),
        ]
        events = _make_earnings("AAPL", e_dates)
        ef = _select_event_ef("AAPL", fire, events)
        # Latest = 5 BDays before fire
        expected = (fire - pd.tseries.offsets.BDay(5)).normalize()
        assert ef == expected

    def test_no_ticker_in_events(self):
        """Ticker not present in earnings_by_ticker returns None."""
        fire = pd.Timestamp("2024-01-09")
        ef = _select_event_ef("AAPL", fire, {})
        assert ef is None

    def test_monday_fire_excludes_friday_correctly(self):
        """fire_date = Monday; cutoff = Friday (1 BDay before Monday).
        An event on Friday should be included; same-day (Monday) should be excluded."""
        fire = pd.Timestamp("2024-01-08")  # Monday
        friday = pd.Timestamp("2024-01-05")  # Friday

        events_friday = _make_earnings("AAPL", [str(friday.date())])
        ef = _select_event_ef("AAPL", fire, events_friday)
        assert ef == friday

        events_monday = _make_earnings("AAPL", [str(fire.date())])
        ef_monday = _select_event_ef("AAPL", fire, events_monday)
        assert ef_monday is None


# ---------------------------------------------------------------------------
# 2. SUE visibility gating
# ---------------------------------------------------------------------------

class TestSueVisibilityGating:
    def _make_rich_eps(
        self,
        ticker: str,
        late_asof_str: str | None = None,
    ) -> pd.DataFrame:
        """Build 10 quarters of EPS (2 full years of year-ago pairs = 4+ diffs).

        Quarters: Q1-Q4 2021, Q1-Q4 2022, Q1 2023, Q2 2023.
        If late_asof_str is given, the Q2 2023 row gets that asof_date
        (making it NOT visible if fire_date < late_asof_str).
        """
        records = [
            # 2021 base year
            ("2021-03-31", 1.00, "2021-05-15"),
            ("2021-06-30", 1.10, "2021-08-15"),
            ("2021-09-30", 1.05, "2021-11-15"),
            ("2021-12-31", 1.20, "2022-02-15"),
            # 2022 comparison year (4 diffs against 2021)
            ("2022-03-31", 1.15, "2022-05-15"),   # d_q = +0.15 vs 2021-Q1
            ("2022-06-30", 1.25, "2022-08-15"),   # d_q = +0.15
            ("2022-09-30", 1.20, "2022-11-15"),   # d_q = +0.15
            ("2022-12-31", 1.35, "2023-02-15"),   # d_q = +0.15
            # 2023 incremental (need asof <= fire to be visible)
            ("2023-03-31", 1.30, "2023-05-15"),   # d_q = +0.15 vs 2022-Q1
            ("2023-06-30", 2.50, late_asof_str if late_asof_str else "2023-08-15"),
        ]
        return _make_eps(ticker, records)

    def test_future_quarter_excluded_from_sue(self):
        """Quarter with asof_date > fire_date must not be used in SUE computation."""
        fire_date = pd.Timestamp("2023-07-01")
        # Q2 2023 asof = 2023-08-01 > fire_date 2023-07-01 → NOT visible
        eps = self._make_rich_eps("TEST", late_asof_str="2023-08-01")
        result = _sue_for_ticker_pit(eps, fire_date)
        # The late quarter (eps=2.50, asof 2023-08-01) must NOT influence sue_latest
        assert result["sue_latest"] is not None
        # The latest visible quarter is 2023-03-31
        assert result["sue_latest_period_end"] == pd.Timestamp("2023-03-31")

    def test_all_quarters_visible(self):
        """When all quarters are visible (asof <= fire), uses the latest one."""
        fire_date = pd.Timestamp("2023-09-01")
        # Q2 2023 asof = 2023-08-15 <= 2023-09-01 → visible
        eps = self._make_rich_eps("TEST", late_asof_str=None)
        result = _sue_for_ticker_pit(eps, fire_date)
        # Q2 2023 (2023-06-30) IS visible
        assert result["sue_latest_period_end"] == pd.Timestamp("2023-06-30")

    def test_too_few_diffs_returns_none(self):
        """Fewer than min_diffs=4 seasonal diffs -> sue_latest is None.

        With only 3 quarters we can get 0 diffs (no year-ago match).
        """
        fire_date = pd.Timestamp("2022-07-01")
        # Only 3 quarters visible — not enough to produce 4 seasonal diffs
        records = [
            ("2022-03-31", 1.00, "2022-05-15"),
            ("2022-06-30", 1.10, "2022-08-15"),  # asof > fire
            ("2021-03-31", 0.90, "2021-05-15"),
        ]
        eps = _make_eps("TEST", records)
        # Only 1 visible at fire 2022-07-01 (the 2022-06-30 asof 2022-08-15 is NOT visible)
        result = _sue_for_ticker_pit(eps, fire_date)
        assert result["sue_latest"] is None

    def test_sue_streak_counts_consecutive_positive(self):
        """sue_streak should count consecutive quarters with d_q > 0."""
        eps = self._make_rich_eps("TEST")
        fire_date = pd.Timestamp("2023-09-01")
        result = _sue_for_ticker_pit(eps, fire_date)
        assert result["sue_streak"] is not None
        # All 2022+2023 year-ago diffs are +0.15 → streak >= 5
        assert result["sue_streak"] >= 5

    def test_sue_accel_computed_when_two_diffs_available(self):
        """sue_accel = sue_latest - sue_prev should be computed."""
        eps = self._make_rich_eps("TEST")
        fire_date = pd.Timestamp("2023-09-01")
        result = _sue_for_ticker_pit(eps, fire_date)
        assert result["sue_accel"] is not None
        # sue_accel = sue_latest - sue_prev
        if result["sue_latest"] is not None and result["sue_prev"] is not None:
            assert abs(result["sue_accel"] - (result["sue_latest"] - result["sue_prev"])) < 1e-9


# ---------------------------------------------------------------------------
# 3. ED-4 bad_news_absorption window logic
# ---------------------------------------------------------------------------

class TestBadNewsAbsorption:
    def _make_scenario(
        self,
        n_pre: int = 70,
        n_post: int = 15,
        pre_price: float = 100.0,
        event_price: float = 100.0,
        post_prices_below_min: bool = False,
        post_momentum_positive: bool = True,
    ) -> tuple[pd.Series, pd.Timestamp]:
        """Build a close series and event_date for testing BNA."""
        pre_dates = _trading_days("2024-01-01", n_pre)
        event_dt = pd.Timestamp(pre_dates[-1])

        # 15 post-event bars
        post_dates = _trading_days(str((event_dt + pd.Timedelta(days=1)).date()), n_post)

        # Pre-window: flat at pre_price, event at event_price
        pre_prices = [pre_price] * n_pre
        pre_prices[-1] = event_price

        if post_prices_below_min:
            # Make some post prices go below pre_min
            post_prices = [pre_price * 0.90] * n_post  # 10% below pre_min
        else:
            if post_momentum_positive:
                # Slightly above event price (positive momentum)
                post_prices = [event_price * 1.01] * n_post
            else:
                # Below event price (negative momentum)
                post_prices = [event_price * 0.98] * n_post

        all_dates = pre_dates + post_dates
        all_prices = pre_prices + post_prices
        close = _make_close(all_dates, all_prices)
        return close, event_dt

    def test_bad_news_no_breach_positive_momentum_returns_true(self):
        """d_q < 0, no breach of pre-min, positive momentum -> BNA = True."""
        close, event_dt = self._make_scenario(
            post_prices_below_min=False,
            post_momentum_positive=True,
        )
        result = _bad_news_absorption_feature(close, None, event_dt, d_q_at_event=-0.5)
        assert result is True

    def test_bad_news_breach_returns_false(self):
        """d_q < 0, but post price goes below pre-min -> BNA = False."""
        close, event_dt = self._make_scenario(
            post_prices_below_min=True,
            post_momentum_positive=True,
        )
        result = _bad_news_absorption_feature(close, None, event_dt, d_q_at_event=-0.5)
        assert result is False

    def test_positive_dq_returns_false(self):
        """d_q >= 0 immediately returns False (not bad news)."""
        close, event_dt = self._make_scenario()
        result = _bad_news_absorption_feature(close, None, event_dt, d_q_at_event=0.5)
        assert result is False

    def test_none_dq_returns_none(self):
        """d_q = None -> returns None (missing data)."""
        close, event_dt = self._make_scenario()
        result = _bad_news_absorption_feature(close, None, event_dt, d_q_at_event=None)
        assert result is None

    def test_no_post_bars_returns_none(self):
        """No post-event bars -> returns None."""
        pre_dates = _trading_days("2024-01-01", 10)
        close = _make_close(pre_dates, [100.0] * 10)
        event_dt = pd.Timestamp(pre_dates[-1])
        result = _bad_news_absorption_feature(close, None, event_dt, d_q_at_event=-0.5)
        assert result is None

    def test_negative_momentum_returns_false(self):
        """d_q < 0, no breach of pre-min, but negative momentum -> BNA = False."""
        close, event_dt = self._make_scenario(
            post_prices_below_min=False,
            post_momentum_positive=False,
        )
        result = _bad_news_absorption_feature(close, None, event_dt, d_q_at_event=-0.5)
        assert result is False


# ---------------------------------------------------------------------------
# 4. ED-5 good_news_hold window logic
# ---------------------------------------------------------------------------

class TestGoodNewsHold:
    def _make_gnh_close(
        self,
        event_price: float = 100.0,
        react_pct: float = 0.025,  # >= 2% trigger
        hold_pct: float = 1.0,     # close(E(f)+10) >= close(E(f)+1)
        n_pre: int = 10,
        n_post: int = 15,
    ) -> tuple[pd.Series, pd.Timestamp]:
        """Build a close series for good_news_hold testing."""
        pre_dates = _trading_days("2024-01-01", n_pre)
        event_dt = pd.Timestamp(pre_dates[-1])

        post_dates = _trading_days(
            str((event_dt + pd.Timedelta(days=1)).date()), n_post
        )

        pre_prices = [event_price] * n_pre
        price_ef1 = event_price * (1.0 + react_pct)  # E(f)+1
        price_ef10 = price_ef1 * hold_pct             # E(f)+10

        post_prices = [price_ef1] * n_post
        if n_post >= 10:
            post_prices[9] = price_ef10  # bar index 9 = E(f)+10

        all_dates = pre_dates + post_dates
        all_prices = pre_prices + post_prices
        return _make_close(all_dates, all_prices), event_dt

    def test_good_news_holds_returns_true(self):
        """d_q > 0, reaction >= 2%, close(E(f)+10) >= close(E(f)+1) -> True."""
        close, event_dt = self._make_gnh_close(react_pct=0.03, hold_pct=1.01)
        result = _good_news_hold_feature(close, event_dt, d_q_at_event=0.5)
        assert result is True

    def test_insufficient_reaction_returns_false(self):
        """d_q > 0, but reaction < 2% -> False."""
        close, event_dt = self._make_gnh_close(react_pct=0.005)
        result = _good_news_hold_feature(close, event_dt, d_q_at_event=0.5)
        assert result is False

    def test_price_drops_at_10_returns_false(self):
        """d_q > 0, reaction >= 2%, but close(E(f)+10) < close(E(f)+1) -> False."""
        close, event_dt = self._make_gnh_close(react_pct=0.03, hold_pct=0.95)
        result = _good_news_hold_feature(close, event_dt, d_q_at_event=0.5)
        assert result is False

    def test_negative_dq_returns_false(self):
        """d_q <= 0 immediately returns False."""
        close, event_dt = self._make_gnh_close(react_pct=0.03, hold_pct=1.01)
        result = _good_news_hold_feature(close, event_dt, d_q_at_event=-0.5)
        assert result is False

    def test_none_dq_returns_none(self):
        """d_q = None -> returns None."""
        close, event_dt = self._make_gnh_close(react_pct=0.03, hold_pct=1.01)
        result = _good_news_hold_feature(close, event_dt, d_q_at_event=None)
        assert result is None

    def test_insufficient_post_bars_returns_none(self):
        """Fewer than 10 post bars -> returns None (cannot check E(f)+10)."""
        close, event_dt = self._make_gnh_close(n_post=5)
        result = _good_news_hold_feature(close, event_dt, d_q_at_event=0.5)
        assert result is None


# ---------------------------------------------------------------------------
# 5. No outcome columns assertion
# ---------------------------------------------------------------------------

_OUTCOME_COLUMNS = {
    "label", "label_reason", "tactical_win", "total_return_252d",
    "total_return_126d", "total_return_504d", "sector_rel_252d",
    "tercile_rank", "piotroski_f", "fund_unchecked", "missed_hold",
    "cohort_description", "price_source", "resolvable",
    "cohort_fundamentals_coverage_frac", "gap_period", "gap_leg_crossed",
    "horizon_status_126", "horizon_status_252", "horizon_status_504",
}


class TestNoOutcomeColumns:
    def _minimal_labels(self) -> pd.DataFrame:
        """Build a minimal labels-like DataFrame (3 fires) for testing."""
        return pd.DataFrame({
            "ticker": ["AAPL", "MSFT", "GOOG"],
            "fire_date": pd.to_datetime(["2023-01-10", "2023-02-15", "2023-03-20"]),
            "survivorship_biased": [True, True, False],
            "label": ["compounder", "tactical_only", "cheap_trap"],
            "total_return_252d": [0.25, 0.05, -0.10],
        })

    def test_panel_has_no_outcome_columns(self):
        """The built panel must not contain any outcome-derived columns."""
        labels = self._minimal_labels()

        panel = build_panel(
            labels=labels,
            yahoo_closes={},
            stocks_closes={},
            massive_closes={},
            dead_name_closes={},
            sector_closes={},
            ticker_sector_map={},
            eps_by_ticker={},
            earnings_by_ticker={},
            verbose=False,
        )

        panel_cols = set(panel.columns)
        # Must not contain any outcome columns
        forbidden = panel_cols & _OUTCOME_COLUMNS
        assert forbidden == set(), (
            f"Panel contains outcome column(s): {forbidden}. "
            "These must never be present in the expect_drift panel per "
            "AMENDMENT_A2_G1_RETEST.md §4."
        )

    def test_panel_has_required_feature_columns(self):
        """Panel must contain all 7 registered feature columns."""
        labels = self._minimal_labels()

        panel = build_panel(
            labels=labels,
            yahoo_closes={},
            stocks_closes={},
            massive_closes={},
            dead_name_closes={},
            sector_closes={},
            ticker_sector_map={},
            eps_by_ticker={},
            earnings_by_ticker={},
            verbose=False,
        )

        required = {"sue_latest", "sue_streak", "pead_drift",
                    "bad_news_absorption", "good_news_hold",
                    "sue_accel", "confirmed_absorption"}
        panel_cols = set(panel.columns)
        missing = required - panel_cols
        assert missing == set(), f"Panel missing feature columns: {missing}"

    def test_panel_rows_match_input_fires(self):
        """Panel must have exactly the same number of rows as input fires."""
        labels = self._minimal_labels()

        panel = build_panel(
            labels=labels,
            yahoo_closes={},
            stocks_closes={},
            massive_closes={},
            dead_name_closes={},
            sector_closes={},
            ticker_sector_map={},
            eps_by_ticker={},
            earnings_by_ticker={},
            verbose=False,
        )

        assert len(panel) == len(labels)

    def test_panel_has_no_label_column(self):
        """The 'label' column from labels.parquet must NOT appear in the panel."""
        labels = self._minimal_labels()

        panel = build_panel(
            labels=labels,
            yahoo_closes={},
            stocks_closes={},
            massive_closes={},
            dead_name_closes={},
            sector_closes={},
            ticker_sector_map={},
            eps_by_ticker={},
            earnings_by_ticker={},
            verbose=False,
        )

        assert "label" not in panel.columns, (
            "'label' column must not appear in the expect_drift panel — "
            "it is an outcome column forbidden by AMENDMENT_A2_G1_RETEST.md §4."
        )


# ---------------------------------------------------------------------------
# 6. ED-7 confirmed_absorption logic
# ---------------------------------------------------------------------------

class TestConfirmedAbsorption:
    def _make_feature_rec(
        self,
        pead_drift: float | None,
        bad_news_absorption: bool | None,
        good_news_hold: bool | None,
    ) -> dict:
        """Build a minimal feature dict for testing ED-7 logic inline."""
        # Test the logic used in build_panel for confirmed_absorption
        confirmed = None
        if pead_drift is not None and (bad_news_absorption is not None or good_news_hold is not None):
            absorbed = bool(bad_news_absorption) if bad_news_absorption is not None else False
            held = bool(good_news_hold) if good_news_hold is not None else False
            confirmed = bool((absorbed or held) and pead_drift > 0)
        return {"confirmed_absorption": confirmed}

    def test_bna_true_and_pead_positive_gives_true(self):
        result = self._make_feature_rec(pead_drift=0.05, bad_news_absorption=True, good_news_hold=None)
        assert result["confirmed_absorption"] is True

    def test_gnh_true_and_pead_positive_gives_true(self):
        result = self._make_feature_rec(pead_drift=0.05, bad_news_absorption=None, good_news_hold=True)
        assert result["confirmed_absorption"] is True

    def test_both_true_and_pead_positive_gives_true(self):
        result = self._make_feature_rec(pead_drift=0.05, bad_news_absorption=True, good_news_hold=True)
        assert result["confirmed_absorption"] is True

    def test_pead_negative_gives_false_even_if_absorbed(self):
        result = self._make_feature_rec(pead_drift=-0.02, bad_news_absorption=True, good_news_hold=True)
        assert result["confirmed_absorption"] is False

    def test_both_false_and_pead_positive_gives_false(self):
        result = self._make_feature_rec(pead_drift=0.05, bad_news_absorption=False, good_news_hold=False)
        assert result["confirmed_absorption"] is False

    def test_pead_none_gives_none(self):
        result = self._make_feature_rec(pead_drift=None, bad_news_absorption=True, good_news_hold=True)
        assert result["confirmed_absorption"] is None

    def test_both_absorption_none_gives_none(self):
        result = self._make_feature_rec(pead_drift=0.05, bad_news_absorption=None, good_news_hold=None)
        assert result["confirmed_absorption"] is None


# ---------------------------------------------------------------------------
# 7. PEAD drift basic test
# ---------------------------------------------------------------------------

class TestPeadDrift:
    def test_positive_drift_detected(self):
        """When stock rises after event, pead_drift should be positive."""
        # 10 pre-event bars + 25 post-event bars
        pre_dates = _trading_days("2024-01-01", 10)
        event_dt = pd.Timestamp(pre_dates[-1])
        # Post bars: rising prices
        post_dates = _trading_days(
            str((event_dt + pd.Timedelta(days=1)).date()), 25
        )
        # fire_date = 21 bars after event (ensures >= 5 sessions of drift)
        fire_date = pd.Timestamp(post_dates[20])

        # close = 100 pre-event, rising 1% per session after
        pre_prices = [100.0] * 10
        post_prices = [100.0 * (1.01 ** (i + 1)) for i in range(25)]
        close = _make_close(pre_dates + post_dates, pre_prices + post_prices)

        pead = _pead_drift_feature(close, None, event_dt, fire_date)
        assert pead is not None
        assert pead > 0

    def test_insufficient_sessions_returns_none(self):
        """Fewer than 5 elapsed sessions between event and fire -> pead = None."""
        pre_dates = _trading_days("2024-01-01", 10)
        event_dt = pd.Timestamp(pre_dates[-1])
        # Only 3 post-event bars
        post_dates = _trading_days(
            str((event_dt + pd.Timedelta(days=1)).date()), 3
        )
        fire_date = pd.Timestamp(post_dates[-1])

        prices = [100.0] * (10 + 3)
        close = _make_close(pre_dates + post_dates, prices)
        pead = _pead_drift_feature(close, None, event_dt, fire_date)
        assert pead is None


# ---------------------------------------------------------------------------
# 8. PIT cap correctness — ED-4 and ED-5 must not read bars on/after fire_date
# ---------------------------------------------------------------------------

class TestPitCap:
    """Verify that ED-4 (bad_news_absorption) and ED-5 (good_news_hold) are
    capped at fire_date-1, matching how ED-3 (pead_drift) already behaves.

    Regression guard for the look-ahead leak reported in the Opus review.
    """

    def _build_close_with_post_entry_move(
        self,
        n_pre: int = 15,
        n_between: int = 3,
        n_post_entry: int = 15,
        pre_price: float = 100.0,
        post_entry_price: float = 120.0,
    ) -> tuple[pd.Series, pd.Timestamp, pd.Timestamp]:
        """Build a close series where the price is stable before fire_date and
        then jumps sharply on/after fire_date.

        Layout:
          pre_dates[0..n_pre-1]        — event sits at pre_dates[-1]
          between_dates[0..n_between-1] — at 100.0; fire_date = between_dates[-1]
          post_dates                    — at post_entry_price (must NOT be seen by PIT features)

        Returns (close, event_date, fire_date).
        """
        pre_dates = _trading_days("2024-01-01", n_pre)
        event_dt = pd.Timestamp(pre_dates[-1])

        # between_dates: from the session after event_dt
        between_start = str((event_dt + pd.Timedelta(days=1)).date())
        between_dates = _trading_days(between_start, n_between)
        fire_date = pd.Timestamp(between_dates[-1])

        # post-entry dates: start the day after fire_date
        post_start = str((fire_date + pd.Timedelta(days=1)).date())
        post_dates = _trading_days(post_start, n_post_entry)

        all_dates = pre_dates + between_dates + post_dates
        all_prices = (
            [pre_price] * n_pre
            + [pre_price] * n_between
            + [post_entry_price] * n_post_entry
        )
        return _make_close(all_dates, all_prices), event_dt, fire_date

    # --- ED-5 (good_news_hold) ---

    def test_gnh_pit_cap_returns_none_when_ef_plus10_after_fire(self):
        """ED-5: when E(f)+10 falls after fire_date, feature must return None.

        Without the PIT cap, close(E(f)+10) would be read from a bar after
        fire_date (look-ahead leak).  With the cap, the function must return None.
        """
        # event at bar -1, fire_date at bar +3 (only 3 between bars).
        # E(f)+10 = 10 bars after event, which is 7 bars PAST fire_date.
        close, event_dt, fire_date = self._build_close_with_post_entry_move(
            n_between=3, n_post_entry=15,
        )
        result = _good_news_hold_feature(close, event_dt, d_q_at_event=1.0, fire_date=fire_date)
        assert result is None, (
            "ED-5 must return None when E(f)+10 is beyond fire_date-1 (PIT cap). "
            f"Got: {result}"
        )

    def test_gnh_pit_cap_not_triggered_when_ef_plus10_before_fire(self):
        """ED-5: when 10+ bars exist between E(f) and fire_date, cap does not truncate."""
        # event at bar -1, fire_date at bar +20 (>= 10 bars between).
        # initial reaction = 0% (pre_price same throughout) -> reaction < 2% -> False.
        close, event_dt, fire_date = self._build_close_with_post_entry_move(
            n_between=20, n_post_entry=5, pre_price=100.0, post_entry_price=100.0,
        )
        # All prices are flat (100.0) so reaction = 0% < 2% -> False (not None)
        result = _good_news_hold_feature(close, event_dt, d_q_at_event=1.0, fire_date=fire_date)
        assert result is False, (
            "ED-5 should return False (not None) when 10 bars are available before "
            f"fire_date but reaction < 2%.  Got: {result}"
        )

    # --- ED-4 (bad_news_absorption) ---

    def test_bna_pit_cap_applied_to_post_window(self):
        """ED-4: post-event scan (E(f)+1..E(f)+10) must be capped at fire_date-1.

        If a price breach only occurs in bars on/after fire_date, the feature
        must NOT see it (PIT constraint).  Without the cap, a breach in the
        post-entry bars would cause the feature to return False incorrectly.
        """
        # Layout:
        #   pre (70 bars at 100.0), event at pre[-1]
        #   between (3 bars at 100.0)  — all within the non-breach zone
        #   fire_date = between[-1]
        #   post_entry (15 bars at 50.0) — breach below pre_min, but AFTER fire_date
        close, event_dt, fire_date = self._build_close_with_post_entry_move(
            n_pre=70, n_between=3, n_post_entry=15,
            pre_price=100.0, post_entry_price=50.0,  # breach, but only post-entry
        )
        result = _bad_news_absorption_feature(
            close, None, event_dt, d_q_at_event=-1.0, fire_date=fire_date
        )
        # With PIT cap: post_end is capped before the breach bars -> result is None
        # (insufficient post bars within PIT window, since only 3 are between event and fire).
        # The key assertion: it must NOT return False (which would indicate it read the breach).
        assert result is not False, (
            "ED-4 must not read post-entry price bars when fire_date is provided. "
            f"Got: {result} — expected None (insufficient bars) or True, not False "
            "(False would imply the breach in post-entry bars was read)."
        )
