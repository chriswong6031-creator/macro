"""Unit tests for engine/event_landmine.py — Codex B5 event-windows display composition.

Tests cover (per task spec):
  1. Earnings leg: None-safe (missing row, past date, future date, tdays calculation).
  2. FOMC leg: None-safe (empty list, past dates, next-date selection, tdays).
  3. Debt leg: None-safe (None df, empty df, missing ticker, present ticker with data,
     ticker with all-NaN debt/cash fields).
  4. compose(): all-None legs returns None; partial legs return correct subset.
  5. Window math: tdays is calendar days (consistent with test assertion).
  6. No-recommendation-string firewall: no advice verbs in block values.
  7. Schema: _display_only key is True when block is returned.

No live I/O — all tests use synthetic DataFrames or injected FOMC lists.
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import engine.event_landmine as el  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_quarterly_df(rows: list[dict]) -> pd.DataFrame:
    """Build a minimal statements_quarterly DataFrame for testing."""
    if not rows:
        return pd.DataFrame(columns=["ticker", "period_end", "filed",
                                     "long_term_debt", "current_debt", "cash", "net_debt"])
    return pd.DataFrame(rows)


def _earnings_row(next_date: str | None, next_time: str | None = None) -> dict:
    """Build a minimal earnings row dict."""
    return {"next_date": next_date, "next_time": next_time}


# ---------------------------------------------------------------------------
# _compose_earnings_leg tests
# ---------------------------------------------------------------------------

class TestComposeEarningsLeg:
    def test_none_row_returns_none(self):
        assert el._compose_earnings_leg(None, date(2026, 7, 6)) is None

    def test_empty_dict_returns_none(self):
        assert el._compose_earnings_leg({}, date(2026, 7, 6)) is None

    def test_missing_next_date_returns_none(self):
        assert el._compose_earnings_leg({"next_date": None}, date(2026, 7, 6)) is None

    def test_empty_string_next_date_returns_none(self):
        assert el._compose_earnings_leg({"next_date": ""}, date(2026, 7, 6)) is None

    def test_past_date_returns_none(self):
        # Past date must be suppressed (same law as earnings_blackout)
        row = _earnings_row("2026-07-01")
        result = el._compose_earnings_leg(row, date(2026, 7, 6))
        assert result is None

    def test_same_day_returns_tdays_zero(self):
        today = date(2026, 7, 6)
        row = _earnings_row("2026-07-06")
        result = el._compose_earnings_leg(row, today)
        assert result is not None
        assert result["tdays"] == 0
        assert result["date"] == "2026-07-06"

    def test_future_date_correct_tdays(self):
        today = date(2026, 7, 6)
        row = _earnings_row("2026-07-20")
        result = el._compose_earnings_leg(row, today)
        assert result is not None
        assert result["tdays"] == 14
        assert result["date"] == "2026-07-20"

    def test_weekend_counts_in_tdays(self):
        # Calendar days — weekends included (unlike trading days)
        today = date(2026, 7, 10)  # Friday
        row = _earnings_row("2026-07-13")  # Monday (3 calendar days away)
        result = el._compose_earnings_leg(row, today)
        assert result is not None
        assert result["tdays"] == 3  # calendar, not trading days

    def test_time_field_pre_market(self):
        today = date(2026, 7, 6)
        row = _earnings_row("2026-07-20", "time-pre-market")
        result = el._compose_earnings_leg(row, today)
        assert result is not None
        assert result["time"] == "pre-market"

    def test_time_field_after_hours(self):
        today = date(2026, 7, 6)
        row = _earnings_row("2026-07-20", "time-after-hours")
        result = el._compose_earnings_leg(row, today)
        assert result is not None
        assert result["time"] == "after-hours"

    def test_unknown_time_returns_none(self):
        today = date(2026, 7, 6)
        row = _earnings_row("2026-07-20", "time-during-market")
        result = el._compose_earnings_leg(row, today)
        assert result is not None
        assert result["time"] is None

    def test_nan_next_date_returns_none(self):
        row = {"next_date": "nan"}
        assert el._compose_earnings_leg(row, date(2026, 7, 6)) is None

    def test_unparseable_date_returns_none(self):
        row = {"next_date": "not-a-date"}
        assert el._compose_earnings_leg(row, date(2026, 7, 6)) is None


# ---------------------------------------------------------------------------
# _compose_fomc_leg tests
# ---------------------------------------------------------------------------

class TestComposeFomcLeg:
    def test_empty_list_returns_none(self):
        assert el._compose_fomc_leg(date(2026, 7, 6), fomc_dates=[]) is None

    def test_all_past_dates_returns_none(self):
        dates = [date(2026, 1, 28), date(2026, 3, 18)]
        assert el._compose_fomc_leg(date(2026, 7, 6), fomc_dates=dates) is None

    def test_selects_next_future_date(self):
        today = date(2026, 7, 6)
        dates = [date(2026, 1, 28), date(2026, 7, 29), date(2026, 9, 16)]
        result = el._compose_fomc_leg(today, fomc_dates=dates)
        assert result is not None
        assert result["date"] == "2026-07-29"
        assert result["tdays"] == 23

    def test_same_day_fomc_tdays_zero(self):
        today = date(2026, 7, 29)
        dates = [date(2026, 7, 29), date(2026, 9, 16)]
        result = el._compose_fomc_leg(today, fomc_dates=dates)
        assert result is not None
        assert result["tdays"] == 0
        assert result["date"] == "2026-07-29"

    def test_tdays_is_calendar_days(self):
        today = date(2026, 7, 10)  # Friday
        # 3 calendar days to Monday (includes weekend)
        dates = [date(2026, 7, 13)]
        result = el._compose_fomc_leg(today, fomc_dates=dates)
        assert result is not None
        assert result["tdays"] == 3

    def test_unsorted_dates_selects_nearest(self):
        today = date(2026, 7, 6)
        # Deliberately unsorted
        dates = [date(2026, 9, 16), date(2026, 7, 29), date(2026, 10, 28)]
        result = el._compose_fomc_leg(today, fomc_dates=dates)
        assert result["date"] == "2026-07-29"


# ---------------------------------------------------------------------------
# _compose_debt_leg tests
# ---------------------------------------------------------------------------

class TestComposeDebtLeg:
    def test_none_df_returns_none(self):
        assert el._compose_debt_leg(None, "AAPL") is None

    def test_empty_df_returns_none(self):
        df = _make_quarterly_df([])
        assert el._compose_debt_leg(df, "AAPL") is None

    def test_missing_ticker_returns_none(self):
        df = _make_quarterly_df([{
            "ticker": "MSFT", "period_end": "2026-03-31", "filed": "2026-04-29",
            "long_term_debt": 3e10, "current_debt": 5e9, "cash": 2e10, "net_debt": 1.5e10,
        }])
        assert el._compose_debt_leg(df, "AAPL") is None

    def test_ticker_case_insensitive(self):
        df = _make_quarterly_df([{
            "ticker": "AAPL", "period_end": "2026-03-28", "filed": "2026-05-01",
            "long_term_debt": 7.4e10, "current_debt": 8.3e9, "cash": 4.5e10, "net_debt": 3.7e10,
        }])
        result = el._compose_debt_leg(df, "aapl")  # lowercase
        assert result is not None
        assert result["long_term_debt"] == round(7.4e10, 0)

    def test_all_nan_debt_cash_returns_none(self):
        import math
        df = _make_quarterly_df([{
            "ticker": "ZZZ", "period_end": "2026-03-31", "filed": "2026-04-29",
            "long_term_debt": float("nan"), "current_debt": float("nan"),
            "cash": float("nan"), "net_debt": float("nan"),
        }])
        assert el._compose_debt_leg(df, "ZZZ") is None

    def test_cash_only_present_returns_leg(self):
        """Cash-only names (no debt) should still show the cash field."""
        df = _make_quarterly_df([{
            "ticker": "GOOG", "period_end": "2026-03-31", "filed": "2026-04-29",
            "long_term_debt": float("nan"), "current_debt": float("nan"),
            "cash": 9.8e10, "net_debt": float("nan"),
        }])
        result = el._compose_debt_leg(df, "GOOG")
        assert result is not None
        assert result["cash"] == round(9.8e10, 0)
        assert result["long_term_debt"] is None
        assert result["current_debt"] is None

    def test_selects_latest_period_end(self):
        """Multiple rows — most recent period_end is selected."""
        df = _make_quarterly_df([
            {"ticker": "TEST", "period_end": "2025-09-30", "filed": "2025-10-28",
             "long_term_debt": 1e9, "current_debt": 2e8, "cash": 5e8, "net_debt": 7e8},
            {"ticker": "TEST", "period_end": "2026-03-31", "filed": "2026-04-28",
             "long_term_debt": 1.1e9, "current_debt": 2.2e8, "cash": 6e8, "net_debt": 7.2e8},
        ])
        result = el._compose_debt_leg(df, "TEST")
        assert result is not None
        assert result["period_end"] == "2026-03-31"
        assert result["long_term_debt"] == round(1.1e9, 0)

    def test_returns_period_end_and_filed(self):
        df = _make_quarterly_df([{
            "ticker": "XYZ", "period_end": "2026-03-31", "filed": "2026-04-29",
            "long_term_debt": 1e9, "current_debt": 2e8, "cash": 5e8, "net_debt": 7e8,
        }])
        result = el._compose_debt_leg(df, "XYZ")
        assert result is not None
        assert result["period_end"] == "2026-03-31"
        assert result["filed"] == "2026-04-29"

    def test_net_debt_none_when_nan(self):
        df = _make_quarterly_df([{
            "ticker": "PARTIAL", "period_end": "2026-03-31", "filed": "2026-04-29",
            "long_term_debt": 1e9, "current_debt": float("nan"),
            "cash": 5e8, "net_debt": float("nan"),
        }])
        result = el._compose_debt_leg(df, "PARTIAL")
        assert result is not None
        assert result["net_debt"] is None
        assert result["current_debt"] is None
        assert result["long_term_debt"] == round(1e9, 0)


# ---------------------------------------------------------------------------
# compose() integration tests
# ---------------------------------------------------------------------------

class TestCompose:
    def test_all_none_inputs_returns_none(self):
        # Only FOMC will populate if the live list has future dates; pass empty list to isolate
        result = el.compose("AAPL", None, None, today=date(2099, 1, 1), fomc_dates=[])
        assert result is None

    def test_returns_display_only_marker(self):
        today = date(2026, 7, 6)
        fomc = [date(2026, 7, 29)]
        result = el.compose("AAPL", None, None, today=today, fomc_dates=fomc)
        assert result is not None
        assert result["_display_only"] is True

    def test_earnings_leg_populated(self):
        today = date(2026, 7, 6)
        row = _earnings_row("2026-07-20")
        result = el.compose("AAPL", row, None, today=today, fomc_dates=[])
        assert result is not None
        assert result["earnings"] is not None
        assert result["earnings"]["date"] == "2026-07-20"
        assert result["earnings"]["tdays"] == 14

    def test_fomc_leg_populated(self):
        today = date(2026, 7, 6)
        fomc = [date(2026, 7, 29)]
        result = el.compose("AAPL", None, None, today=today, fomc_dates=fomc)
        assert result is not None
        assert result["fomc_within"] is not None
        assert result["fomc_within"]["date"] == "2026-07-29"

    def test_debt_leg_populated(self):
        today = date(2026, 7, 6)
        df = _make_quarterly_df([{
            "ticker": "AAPL", "period_end": "2026-03-28", "filed": "2026-05-01",
            "long_term_debt": 7.4e10, "current_debt": 8.3e9, "cash": 4.5e10, "net_debt": 3.7e10,
        }])
        result = el.compose("AAPL", None, df, today=today, fomc_dates=[])
        assert result is not None
        assert result["debt"] is not None
        assert result["debt"]["current_debt"] == round(8.3e9, 0)

    def test_partial_legs_schema(self):
        """When only FOMC fires, earnings and debt are None but key is present."""
        today = date(2026, 7, 6)
        fomc = [date(2026, 7, 29)]
        result = el.compose("AAPL", None, None, today=today, fomc_dates=fomc)
        assert result is not None
        assert "earnings" in result
        assert "fomc_within" in result
        assert "debt" in result
        assert result["earnings"] is None
        assert result["debt"] is None

    def test_past_earnings_not_surfaced(self):
        today = date(2026, 7, 6)
        row = _earnings_row("2026-07-01")  # past
        result = el.compose("AAPL", row, None, today=today, fomc_dates=[])
        # All legs None -> compose returns None (FOMC list empty, debt None)
        assert result is None

    def test_today_default_used_when_none(self):
        """today=None should not raise; uses date.today() internally."""
        result = el.compose("AAPL", None, None, today=None, fomc_dates=[date(2099, 1, 1)])
        # FOMC date 2099-01-01 is always future; block should be returned
        assert result is not None
        assert result["fomc_within"] is not None


# ---------------------------------------------------------------------------
# No-recommendation-string firewall
# ---------------------------------------------------------------------------

ADVICE_VERBS = {
    "buy", "sell", "wait", "avoid", "hold", "enter", "exit",
    "add", "reduce", "short", "size", "overweight", "underweight",
    "increase", "decrease",
}

def _collect_string_values(obj, acc: list) -> None:
    """Recursively collect all string values from a nested dict/list."""
    if isinstance(obj, dict):
        for v in obj.values():
            _collect_string_values(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            _collect_string_values(v, acc)
    elif isinstance(obj, str):
        acc.append(obj)


class TestNoRecommendationStrings:
    def _get_sample_block(self):
        today = date(2026, 7, 6)
        df = _make_quarterly_df([{
            "ticker": "SAMPLE", "period_end": "2026-03-28", "filed": "2026-05-01",
            "long_term_debt": 1e9, "current_debt": 2e8, "cash": 5e8, "net_debt": 7e8,
        }])
        return el.compose(
            "SAMPLE",
            _earnings_row("2026-07-20"),
            df,
            today=today,
            fomc_dates=[date(2026, 7, 29)],
        )

    def test_no_advice_verbs_in_string_values(self):
        block = self._get_sample_block()
        assert block is not None
        strings: list[str] = []
        _collect_string_values(block, strings)
        for s in strings:
            words = {w.lower().strip(".,;:!?") for w in s.split()}
            bad = words & ADVICE_VERBS
            assert not bad, (
                f"Advice verb found in event_windows block value: {bad!r} in {s!r}"
            )

    def test_display_only_true(self):
        block = self._get_sample_block()
        assert block is not None
        assert block["_display_only"] is True
