"""Focused contracts for the deterministic CN continuation Wave-1 packet."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scripts.research.cn_limit_continuation_w1 import (
    BOUNDARY_PURGE_SESSIONS,
    C_AUCTION_SELECTION_FIELDS,
    CHINEXT_REGISTRATION_IPO_FIRST5_DATE,
    DEFAULT_CALENDAR_PATH,
    DEFAULT_RAW_DIR,
    DEFAULT_ZT_PATH,
    EXPECTED_CALENDAR_SESSIONS,
    EXIT_IDS,
    LIMIT_TOLERANCE,
    MAIN_REGISTRATION_IPO_FIRST5_DATE,
    STAR_FIRST_LISTING_DATE,
    MarketCalendar,
    _book_summary,
    _build_ecology,
    _fixed_exit,
    _capital_accounted_split,
    _no_duplicate_exit_rows,
    _no_duplicate_portfolio_book,
    _seal_state_exit,
    _vendor_descriptive_stratum,
    _zt_inventory,
    apply_boundary_purge,
    board_era,
    canonical_ticker,
    extract_ticker_events,
    gap_bucket,
    limit_width,
    load_market_calendar,
    ipo_no_limit_rule,
    render_markdown,
    run_measurement,
    tolerant_at_upper,
)


def _frame(
    closes: list[float],
    *,
    opens: list[float] | None = None,
    highs: list[float] | None = None,
    lows: list[float] | None = None,
    volumes: list[float] | None = None,
    dates: pd.DatetimeIndex | None = None,
) -> pd.DataFrame:
    n = len(closes)
    dates = dates if dates is not None else pd.bdate_range("2022-01-03", periods=n)
    opens = list(closes) if opens is None else opens
    highs = [max(o, c) for o, c in zip(opens, closes)] if highs is None else highs
    lows = [min(o, c) for o, c in zip(opens, closes)] if lows is None else lows
    volumes = list(np.linspace(1_000_000, 2_000_000, n)) if volumes is None else volumes
    return pd.DataFrame(
        {
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volumes,
        },
        index=dates,
    )


def _event_frame_for_measurement(periods: int = 180) -> pd.DataFrame:
    """A synthetic main-board path with separated board events and legal exits."""
    dates = pd.bdate_range("2023-01-02", periods=periods)
    closes = [10.0] * periods
    opens = [10.0] * periods
    highs = [10.1] * periods
    lows = [9.9] * periods
    for i in (70, 95, 125, 150):
        prior = closes[i - 1]
        closes[i] = round(prior * 1.10, 2)
        opens[i] = prior * 1.02
        highs[i] = closes[i]
        lows[i] = opens[i]
        # Next official open is below its new upper limit, so the candidate fills.
        opens[i + 1] = closes[i] * 1.01
        closes[i + 1] = opens[i + 1] * 0.995
        highs[i + 1] = opens[i + 1] * 1.01
        lows[i + 1] = opens[i + 1] * 0.99
        opens[i + 2] = closes[i + 1] * 1.01
        closes[i + 2] = opens[i + 2] * 1.01
        highs[i + 2] = closes[i + 2] * 1.005
        lows[i + 2] = opens[i + 2] * 0.995
    return _frame(closes, opens=opens, highs=highs, lows=lows, dates=dates)


def test_limit_width_and_era_are_explicit_and_chinext_is_separate():
    assert limit_width("main", pd.Timestamp("2026-07-06")) == 0.10
    assert limit_width("chinext", pd.Timestamp("2020-08-21")) == 0.10
    assert limit_width("chinext", pd.Timestamp("2020-08-24")) == 0.20
    assert board_era("chinext", pd.Timestamp("2020-08-21")) != board_era(
        "chinext", pd.Timestamp("2020-08-24")
    )


def test_tolerant_definition_accepts_float_noise_but_not_a_real_miss():
    upper = 11.0
    assert LIMIT_TOLERANCE == 0.002
    assert tolerant_at_upper(10.999, upper)
    assert tolerant_at_upper(upper * (1 - LIMIT_TOLERANCE), upper)
    assert not tolerant_at_upper(upper * (1 - LIMIT_TOLERANCE) - 0.001, upper)


def test_wave0_calendar_has_3786_sessions_and_dec25_successor():
    clock = load_market_calendar(DEFAULT_CALENDAR_PATH)
    sessions = clock.sessions[
        (clock.sessions >= pd.Timestamp("2011-01-01"))
        & (clock.sessions <= pd.Timestamp("2026-08-07"))
    ]
    assert len(sessions) == EXPECTED_CALENDAR_SESSIONS
    assert clock.successor[pd.Timestamp("2014-12-24")] == pd.Timestamp("2014-12-25")


def test_000408_dec24_to_dec25_is_adjacent_and_preserves_streak():
    dates = pd.to_datetime(
        ["2014-12-23", "2014-12-24", "2014-12-25", "2014-12-26"]
    )
    frame = _frame(
        [10.0, 11.0, 12.1, 12.0],
        opens=[10.0, 10.1, 11.2, 12.0],
        highs=[10.0, 11.0, 12.1, 12.0],
        lows=[10.0, 10.1, 11.2, 11.9],
        dates=pd.DatetimeIndex(dates),
    )
    rows, _, _ = extract_ticker_events(
        "000408.SZ",
        frame,
        start_date=dates.min(),
        end_date=dates.max(),
        min_prior_sessions=1,
        market_calendar=MarketCalendar.from_dates(dates),
    )
    dec24 = next(row for row in rows if row["signal_date"] == "2014-12-24")
    dec25 = next(row for row in rows if row["signal_date"] == "2014-12-25")
    assert dec24["next_session_date"] == "2014-12-25"
    assert dec24["next_board"] is True
    assert dec25["board_count"] == 2


def test_c0_uses_true_next_common_market_session_across_weekend():
    dates = pd.to_datetime(["2022-01-06", "2022-01-07", "2022-01-10", "2022-01-11"])
    frame = _frame(
        [10.0, 11.0, 12.1, 12.0],
        opens=[10.0, 10.1, 11.2, 12.0],
        highs=[10.0, 11.0, 12.1, 12.0],
        lows=[10.0, 10.1, 11.2, 11.9],
        dates=pd.DatetimeIndex(dates),
    )
    rows, _, _ = extract_ticker_events(
        "000001.SZ",
        frame,
        start_date=pd.Timestamp("2022-01-01"),
        end_date=pd.Timestamp("2022-12-31"),
        min_prior_sessions=1,
        market_calendar=MarketCalendar.from_dates(dates),
    )
    friday = next(row for row in rows if row["signal_date"] == "2022-01-07")
    assert friday["next_session_date"] == "2022-01-10"
    assert friday["calendar_gap_days"] == 3
    assert friday["next_board"] is True


def test_missing_true_next_session_stays_in_denominator_and_resets_ladder():
    market_dates = pd.to_datetime(
        ["2022-01-06", "2022-01-07", "2022-01-10", "2022-01-11", "2022-01-12"]
    )
    # The ticker is halted/missing on Monday and resumes with a board on Tuesday.
    ticker_dates = pd.to_datetime(["2022-01-06", "2022-01-07", "2022-01-11", "2022-01-12"])
    frame = _frame(
        [10.0, 11.0, 12.1, 12.0],
        opens=[10.0, 10.1, 11.2, 12.0],
        highs=[10.0, 11.0, 12.1, 12.0],
        lows=[10.0, 10.1, 11.2, 11.9],
        dates=pd.DatetimeIndex(ticker_dates),
    )
    rows, _, _ = extract_ticker_events(
        "000001.SZ",
        frame,
        start_date=pd.Timestamp("2022-01-01"),
        end_date=pd.Timestamp("2022-12-31"),
        min_prior_sessions=1,
        market_calendar=MarketCalendar.from_dates(market_dates),
    )
    friday = next(row for row in rows if row["signal_date"] == "2022-01-07")
    resumed = next(row for row in rows if row["signal_date"] == "2022-01-11")
    assert friday["next_session_date"] == "2022-01-10"
    assert friday["next_session_state"] == "no_bar_halt_or_data_missing"
    assert friday["next_board"] is False
    assert friday["next_board_observed_bar_sensitivity"] is None
    assert friday["next_observed_ticker_date_sensitivity"] == "2022-01-11"
    assert friday["entry_fill_state"] == "no_bar_halt_or_data_missing_no_fill"
    assert resumed["board_count"] == 1
    assert resumed["ticker_session_board_count_sensitivity"] == 2


def test_open_at_upper_limit_is_queue_no_fill_and_gap_is_not_a_selection_field():
    dates = pd.bdate_range("2022-01-03", periods=5)
    frame = _frame(
        [10.0, 11.0, 12.1, 12.0, 12.0],
        opens=[10.0, 10.2, 12.1, 12.0, 12.0],
        highs=[10.0, 11.0, 12.1, 12.0, 12.0],
        lows=[10.0, 10.2, 12.1, 11.9, 11.9],
        dates=dates,
    )
    rows, _, _ = extract_ticker_events(
        "000001.SZ",
        frame,
        start_date=dates.min(),
        end_date=dates.max(),
        min_prior_sessions=1,
    )
    first = next(row for row in rows if row["signal_date"] == str(dates[1].date()))
    assert first["entry_fill_state"] == "open_at_upper_limit_queue_no_fill"
    assert first["entry_price"] is None
    assert first["exits"] == {}
    assert first["postgap_bucket"] == "upper_limit_queue"
    assert "entry_gap_norm" not in C_AUCTION_SELECTION_FIELDS


def test_official_open_entry_cannot_exit_until_following_session():
    dates = pd.bdate_range("2022-01-03", periods=6)
    frame = _frame(
        [10.0, 11.0, 11.4, 11.5, 11.6, 11.7],
        opens=[10.0, 10.2, 11.2, 11.45, 11.55, 11.65],
        highs=[10.0, 11.0, 11.5, 11.6, 11.7, 11.8],
        lows=[10.0, 10.2, 11.1, 11.4, 11.5, 11.6],
        dates=dates,
    )
    rows, _, _ = extract_ticker_events(
        "000001.SZ",
        frame,
        start_date=dates.min(),
        end_date=dates.max(),
        min_prior_sessions=1,
    )
    event = next(row for row in rows if row["signal_date"] == str(dates[1].date()))
    assert event["entry_fill_state"] == "official_open_candidate_fill"
    assert event["next_session_date"] == str(dates[2].date())
    assert event["exits"]["tplus1_legal_open"]["exit_date"] == str(dates[3].date())
    assert event["exits"]["tplus1_legal_close"]["exit_date"] == str(dates[3].date())


def test_seal_state_exit_holds_and_lower_limit_open_carries():
    dates = pd.bdate_range("2022-01-03", periods=6)
    opens = np.array([10.0, 11.0, 10.89, 10.89, 10.95, 11.1])
    lowers = np.array([9.0, 9.9, 10.89, 10.89, 10.8, 10.9])
    volumes = np.ones(6)
    sealed = np.array([False, True, True, False, False, False])
    clock = MarketCalendar.from_dates(dates)
    date_to_index = {date: i for i, date in enumerate(dates)}
    obs, held = _seal_state_exit(
        opens=opens,
        lowers=lowers,
        volumes=volumes,
        sealed_up=sealed,
        dates=dates,
        entry_date=dates[1],
        market_calendar=clock,
        date_to_index=date_to_index,
    )
    assert held == 2
    # First unsealed close is index 3; index 4 is sellable.
    assert obs.date == str(dates[4].date())

    carried = _fixed_exit(
        opens=opens,
        closes=np.array([10.0, 11.0, 12.1, 10.89, 10.95, 11.1]),
        lowers=lowers,
        volumes=volumes,
        dates=dates,
        target_date=dates[2],
        price_field="open",
        market_calendar=clock,
        date_to_index=date_to_index,
    )
    # Index 2 and 3 are at their lower-limit cushions; index 4 is the first sellable open.
    assert carried.date == str(dates[4].date())
    assert carried.locked_down_deferrals == 2


def test_halt_on_exact_exit_session_is_unresolved_not_future_resumption():
    market_dates = pd.to_datetime(
        ["2022-01-06", "2022-01-07", "2022-01-10", "2022-01-11", "2022-01-12", "2022-01-13"]
    )
    ticker_dates = pd.to_datetime(
        ["2022-01-06", "2022-01-07", "2022-01-10", "2022-01-12", "2022-01-13"]
    )
    frame = _frame(
        [10.0, 11.0, 11.2, 11.3, 11.4],
        opens=[10.0, 10.2, 11.1, 11.25, 11.35],
        highs=[10.0, 11.0, 11.3, 11.4, 11.5],
        lows=[10.0, 10.2, 11.0, 11.2, 11.3],
        dates=pd.DatetimeIndex(ticker_dates),
    )
    rows, _, _ = extract_ticker_events(
        "000001.SZ",
        frame,
        start_date=pd.Timestamp("2022-01-01"),
        end_date=pd.Timestamp("2022-12-31"),
        min_prior_sessions=1,
        market_calendar=MarketCalendar.from_dates(market_dates),
    )
    event = next(row for row in rows if row["signal_date"] == "2022-01-07")
    assert event["entry_fill_state"] == "official_open_candidate_fill"
    assert event["exits"]["tplus1_legal_open"]["exit_date"] == "2022-01-11"
    assert event["exits"]["tplus1_legal_open"]["gross_return"] is None
    assert event["exits"]["tplus1_legal_open"]["exit_reason"] == "missing_bar_halt_or_data_missing"
    assert event["exits"]["seal_state_next_open"]["gross_return"] is None
    assert event["exits"]["seal_state_next_open"]["exit_reason"] == "missing_bar_halt_or_data_missing"


def test_zero_volume_board_and_next_session_are_non_tradable():
    dates = pd.bdate_range("2022-02-07", periods=5)
    zero_signal = _frame(
        [10.0, 11.0, 11.1, 11.2, 11.3],
        opens=[10.0, 10.1, 11.0, 11.1, 11.2],
        highs=[10.0, 11.0, 11.2, 11.3, 11.4],
        lows=[10.0, 10.1, 10.9, 11.0, 11.1],
        volumes=[1_000.0, 0.0, 1_000.0, 1_000.0, 1_000.0],
        dates=dates,
    )
    rows, _, diag = extract_ticker_events(
        "000001.SZ",
        zero_signal,
        start_date=dates.min(),
        end_date=dates.max(),
        min_prior_sessions=1,
        market_calendar=MarketCalendar.from_dates(dates),
    )
    assert not rows
    assert diag["zero_volume_tolerant_board_price_rows_reclassified"] == 1

    zero_next = _frame(
        [10.0, 11.0, 12.1, 12.0, 12.0],
        opens=[10.0, 10.1, 11.2, 12.0, 12.0],
        highs=[10.0, 11.0, 12.1, 12.0, 12.0],
        lows=[10.0, 10.1, 11.2, 11.9, 11.9],
        volumes=[1_000.0, 1_000.0, 0.0, 1_000.0, 1_000.0],
        dates=dates,
    )
    rows, _, _ = extract_ticker_events(
        "000001.SZ",
        zero_next,
        start_date=dates.min(),
        end_date=dates.max(),
        min_prior_sessions=1,
        market_calendar=MarketCalendar.from_dates(dates),
    )
    event = next(row for row in rows if row["signal_date"] == str(dates[1].date()))
    assert event["next_session_bar_observed"] is True
    assert event["next_session_available"] is False
    assert event["next_session_state"] == "zero_volume_halt_or_no_trade"
    assert event["next_board"] is False
    assert event["entry_fill_state"] == "zero_volume_halt_or_no_trade_no_fill"


def test_zero_volume_exit_and_lower_limit_carry_abort_without_jump():
    dates = pd.bdate_range("2022-03-01", periods=6)
    frame = _frame(
        [10.0, 11.0, 11.2, 11.3, 11.4, 11.5],
        opens=[10.0, 10.2, 11.1, 11.25, 11.35, 11.45],
        highs=[10.0, 11.0, 11.3, 11.4, 11.5, 11.6],
        lows=[10.0, 10.2, 11.0, 11.2, 11.3, 11.4],
        volumes=[1_000.0, 1_000.0, 1_000.0, 0.0, 1_000.0, 1_000.0],
        dates=dates,
    )
    rows, _, _ = extract_ticker_events(
        "000001.SZ",
        frame,
        start_date=dates.min(),
        end_date=dates.max(),
        min_prior_sessions=1,
        market_calendar=MarketCalendar.from_dates(dates),
    )
    event = next(row for row in rows if row["signal_date"] == str(dates[1].date()))
    assert event["exits"]["tplus1_legal_open"]["gross_return"] is None
    assert event["exits"]["tplus1_legal_open"]["exit_reason"] == "zero_volume_halt_or_no_trade"
    assert event["exits"]["seal_state_next_open"]["exit_reason"] == "zero_volume_halt_or_no_trade"

    clock = MarketCalendar.from_dates(
        pd.to_datetime([*dates[:2], "2026-07-01", *dates[2:]])
    )
    carried = _fixed_exit(
        opens=np.array([10.0, 11.0, 10.0, 10.1, 10.2, 10.3]),
        closes=np.array([10.0, 11.0, 9.9, 10.1, 10.2, 10.3]),
        lowers=np.array([9.0, 9.9, 9.9, 9.9, 9.9, 9.9]),
        volumes=np.array([1.0, 1.0, 1.0, 0.0, 1.0, 1.0]),
        dates=dates,
        target_date=dates[2],
        price_field="close",
        market_calendar=clock,
        date_to_index={date: i for i, date in enumerate(dates)},
    )
    assert carried.price is None
    assert carried.date == str(dates[3].date())
    assert carried.reason == "zero_volume_halt_or_no_trade"


def test_main_registration_ipo_first_five_sessions_are_quarantined():
    assert MAIN_REGISTRATION_IPO_FIRST5_DATE == pd.Timestamp("2023-04-10")
    dates = pd.bdate_range("2023-04-10", periods=7)
    closes = [10.0, 11.0, 12.1, 13.31, 14.64, 16.10, 16.0]
    opens = [10.0] + [closes[i - 1] * 1.02 for i in range(1, len(closes))]
    frame = _frame(
        closes,
        opens=opens,
        highs=[max(o, c) for o, c in zip(opens, closes)],
        lows=[min(o, c) for o, c in zip(opens, closes)],
        dates=dates,
    )
    rows, _, diag = extract_ticker_events(
        "001001.SZ",
        frame,
        start_date=dates.min(),
        end_date=dates.max(),
        min_prior_sessions=0,
        market_calendar=MarketCalendar.from_dates(dates),
    )
    assert diag["ipo_no_limit_sessions_applied"] == 5
    assert [row["signal_date"] for row in rows] == [str(dates[5].date())]

    old_dates = pd.bdate_range("2023-03-01", periods=3)
    old_frame = _frame(
        [10.0, 11.0, 11.1],
        opens=[10.0, 10.1, 11.0],
        highs=[10.0, 11.0, 11.2],
        lows=[10.0, 10.1, 10.9],
        dates=old_dates,
    )
    old_rows, _, old_diag = extract_ticker_events(
        "001001.SZ",
        old_frame,
        start_date=old_dates.min(),
        end_date=old_dates.max(),
        min_prior_sessions=0,
        market_calendar=MarketCalendar.from_dates(old_dates),
    )
    assert old_diag["ipo_no_limit_sessions_applied"] == 1
    assert old_rows[0]["signal_date"] == str(old_dates[1].date())


@pytest.mark.parametrize("ticker", ["001248.SZ", "001232.SZ"])
def test_zero_volume_issue_rows_do_not_advance_main_ipo_clock_or_filtered_context(
    ticker: str,
):
    dates = pd.to_datetime(
        [
            "2026-06-29",
            "2026-06-30",
            "2026-07-02",
            "2026-07-03",
            "2026-07-06",
            "2026-07-07",
            "2026-07-08",
            "2026-07-09",
            "2026-07-10",
        ]
    )
    closes = [10.0, 10.0, 10.0, 11.0, 12.1, 13.31, 14.64, 16.10, 16.0]
    opens = [10.0, 10.0, 10.0] + [
        closes[i - 1] * 1.02 for i in range(3, len(closes))
    ]
    frame = _frame(
        closes,
        opens=opens,
        highs=[max(o, c) for o, c in zip(opens, closes)],
        lows=[min(o, c) for o, c in zip(opens, closes)],
        volumes=[0.0, 0.0, 1_000.0, 1_000.0, 1_000.0, 1_000.0, 1_000.0, 1_000.0, 1_000.0],
        dates=pd.DatetimeIndex(dates),
    )
    clock = MarketCalendar.from_dates(
        pd.to_datetime([*dates[:2], "2026-07-01", *dates[2:]])
    )
    full_rows, _, full_diag = extract_ticker_events(
        ticker,
        frame,
        start_date=dates.min(),
        end_date=dates.max(),
        min_prior_sessions=0,
        market_calendar=clock,
    )
    filtered_rows, _, filtered_diag = extract_ticker_events(
        ticker,
        frame,
        start_date=pd.Timestamp("2026-07-09"),
        end_date=dates.max(),
        min_prior_sessions=0,
        market_calendar=clock,
    )
    expected_no_limit = ["2026-07-02", "2026-07-03", "2026-07-06", "2026-07-07", "2026-07-08"]
    assert full_diag["raw_first_row_date"] == "2026-06-29"
    assert full_diag["listing_date"] == "2026-07-02"
    assert full_diag["raw_rows_before_first_positive_volume_session"] == 2
    assert full_diag["ipo_no_limit_regime"] == "main_registration_first_five"
    assert full_diag["ipo_no_limit_positive_volume_dates"] == expected_no_limit
    assert filtered_diag["ipo_no_limit_positive_volume_dates"] == expected_no_limit
    assert [row["signal_date"] for row in full_rows] == ["2026-07-09"]
    assert filtered_rows == full_rows


def test_actual_issue_price_placeholders_do_not_start_listing_clock():
    clock = load_market_calendar(DEFAULT_CALENDAR_PATH)
    expected = {
        "001248.SZ": {
            "raw_first": "2026-06-29",
            "listing": "2026-07-02",
            "prelisting_rows": 2,
            "no_limit": [
                "2026-07-02",
                "2026-07-03",
                "2026-07-06",
                "2026-07-07",
                "2026-07-08",
            ],
        },
        "001232.SZ": {
            "raw_first": "2026-08-03",
            "listing": "2026-08-04",
            "prelisting_rows": 1,
            "no_limit": [
                "2026-08-04",
                "2026-08-05",
                "2026-08-06",
                "2026-08-07",
            ],
        },
    }
    for ticker, anchors in expected.items():
        frame = pd.read_parquet(DEFAULT_RAW_DIR / f"{ticker}.parquet")
        _, _, diag = extract_ticker_events(
            ticker,
            frame,
            start_date=pd.Timestamp("2011-01-04"),
            end_date=pd.Timestamp("2026-08-07"),
            min_prior_sessions=0,
            market_calendar=clock,
        )
        assert diag["raw_first_row_date"] == anchors["raw_first"]
        assert diag["listing_date"] == anchors["listing"]
        assert diag["raw_rows_before_first_positive_volume_session"] == anchors["prelisting_rows"]
        assert diag["ipo_no_limit_positive_volume_dates"] == anchors["no_limit"]


def test_ipo_regime_boundaries_and_pre_reform_chinext_day_two():
    assert MAIN_REGISTRATION_IPO_FIRST5_DATE == pd.Timestamp("2023-04-10")
    assert CHINEXT_REGISTRATION_IPO_FIRST5_DATE == pd.Timestamp("2020-08-24")
    assert STAR_FIRST_LISTING_DATE == pd.Timestamp("2019-07-22")
    assert ipo_no_limit_rule("main", pd.Timestamp("2023-04-07")) == (
        "main_historical_listing_day_only",
        1,
    )
    assert ipo_no_limit_rule("main", pd.Timestamp("2023-04-10")) == (
        "main_registration_first_five",
        5,
    )
    assert ipo_no_limit_rule("chinext", pd.Timestamp("2020-08-21")) == (
        "chinext_pre_reform_listing_day_only",
        1,
    )
    assert ipo_no_limit_rule("chinext", pd.Timestamp("2020-08-24")) == (
        "chinext_registration_first_five",
        5,
    )
    assert ipo_no_limit_rule("star", STAR_FIRST_LISTING_DATE) == (
        "star_from_inception_first_five",
        5,
    )

    dates = pd.bdate_range("2016-03-01", periods=3)
    frame = _frame(
        [10.0, 11.0, 11.1],
        opens=[10.0, 10.2, 11.0],
        highs=[10.0, 11.0, 11.2],
        lows=[10.0, 10.2, 10.9],
        dates=dates,
    )
    rows, _, diag = extract_ticker_events(
        "300503.SZ",
        frame,
        start_date=dates.min(),
        end_date=dates.max(),
        min_prior_sessions=0,
        market_calendar=MarketCalendar.from_dates(dates),
    )
    assert diag["ipo_no_limit_regime"] == "chinext_pre_reform_listing_day_only"
    assert diag["ipo_no_limit_positive_volume_dates"] == [str(dates[0].date())]
    assert [row["signal_date"] for row in rows] == [str(dates[1].date())]


def test_post_reform_chinext_and_star_exclude_first_five_traded_sessions():
    for ticker, start, width, regime in (
        ("300857.SZ", "2020-08-24", 0.20, "chinext_registration_first_five"),
        ("688001.SS", "2019-07-22", 0.20, "star_from_inception_first_five"),
    ):
        dates = pd.bdate_range(start, periods=7)
        closes = [10.0]
        for _ in range(5):
            closes.append(round(closes[-1] * (1.0 + width), 2))
        closes.append(closes[-1])
        opens = [closes[0]] + [value * 1.02 for value in closes[:-1]]
        frame = _frame(
            closes,
            opens=opens,
            highs=[max(o, c) for o, c in zip(opens, closes)],
            lows=[min(o, c) for o, c in zip(opens, closes)],
            dates=dates,
        )
        rows, _, diag = extract_ticker_events(
            ticker,
            frame,
            start_date=dates.min(),
            end_date=dates.max(),
            min_prior_sessions=0,
            market_calendar=MarketCalendar.from_dates(dates),
        )
        assert diag["ipo_no_limit_regime"] == regime
        assert diag["ipo_no_limit_positive_volume_dates"] == [
            str(date.date()) for date in dates[:5]
        ]
        assert [row["signal_date"] for row in rows] == [str(dates[5].date())]


def test_joint_candidate_book_holds_nonfills_as_cash_and_states_identity():
    events = pd.DataFrame(
        [
            {
                "entry_fill_state": "official_open_candidate_fill",
                "exits": {"seal_state_next_open": {"gross_return": 0.10}},
                "date_cluster": "2025-01-02",
                "run_cluster": "a",
            },
            {
                "entry_fill_state": "open_at_upper_limit_queue_no_fill",
                "exits": {},
                "date_cluster": "2025-01-03",
                "run_cluster": "b",
            },
        ]
    )
    summary = _book_summary(events, "seal_state_next_open", 0)
    assert summary["p_fill_of_mature_book"] == pytest.approx(0.5)
    assert summary["filled_conditional_metric"]["mean"] == pytest.approx(0.10)
    assert summary["joint_cash_book_metric"]["mean"] == pytest.approx(0.05)
    assert summary["p_fill_times_conditional_mean"] == pytest.approx(0.05)
    assert summary["arms"]["not_filled_cash_zero"] == 1


def _portfolio_event(
    ticker: str,
    signal_date: str,
    entry_date: str,
    exit_date: str | None,
    gross_return: float | None,
) -> dict[str, object]:
    payload = {
        exit_id: {
            "exit_date": exit_date,
            "exit_reason": "official_open" if exit_date else "unresolved",
            "gross_return": gross_return,
        }
        for exit_id in EXIT_IDS
    }
    return {
        "ticker": ticker,
        "signal_date": signal_date,
        "next_session_date": entry_date,
        "entry_fill_state": "official_open_candidate_fill",
        "exits": payload,
        "run_cluster": f"{ticker}:{signal_date}",
        "split": "train_2011_2019",
        "board_count_bucket": "1",
        "market_scope": "main_primary",
    }


def test_no_duplicate_ticker_rejects_overlap_and_date_equal_differs_from_rows():
    events = pd.DataFrame(
        [
            _portfolio_event("A", "2015-01-02", "2015-01-05", "2015-01-07", -0.10),
            _portfolio_event("B", "2015-01-02", "2015-01-05", "2015-01-07", -0.10),
            _portfolio_event("A", "2015-01-05", "2015-01-06", "2015-01-08", 0.50),
            _portfolio_event("C", "2015-01-07", "2015-01-08", "2015-01-09", 0.10),
        ]
    )
    rows = _no_duplicate_exit_rows(events, "seal_state_next_open")
    overlap = rows[rows["signal_date"].eq("2015-01-05")].iloc[0]
    assert overlap["portfolio_state"] == "same_ticker_overlap_rejected_cash_zero"
    assert overlap["gross_book_return"] == 0.0

    book = _no_duplicate_portfolio_book(events)
    metric = next(
        row
        for row in book["metrics"]
        if row["split"] == "train_2011_2019"
        and row["exit_id"] == "seal_state_next_open"
        and row["cost_bps"] == 0
    )
    assert metric["overlap_rejected_cash_zero"] == 1
    assert metric["row_weighted_event_metric"]["mean"] == pytest.approx(-0.025)
    # Entry-date cohorts: (-10%, -10%) => -10%; overlap cash => 0%; C => +10%.
    assert metric["date_equal_daily_book_metric"]["mean"] == pytest.approx(0.0)
    assert "NOT_IMPLEMENTABLE_PORTFOLIO_RETURN" in book["portfolio_scope_warning"]


def test_self_financing_book_reserves_cash_until_exit():
    dates = pd.to_datetime(
        ["2015-01-05", "2015-01-06", "2015-01-07", "2015-01-08", "2015-01-09"]
    )
    events = pd.DataFrame(
        [
            _portfolio_event("A", "2015-01-02", "2015-01-05", "2015-01-07", 0.10),
            _portfolio_event("B", "2015-01-05", "2015-01-06", "2015-01-08", 0.20),
            _portfolio_event("C", "2015-01-07", "2015-01-08", "2015-01-09", 0.0),
        ]
    )
    result = _capital_accounted_split(
        events,
        MarketCalendar.from_dates(dates),
        split="train_2011_2019",
        exit_id="seal_state_next_open",
        cost_bps=0,
    )
    assert result["funnel"]["accepted_positions"] == 2
    assert result["funnel"]["capital_unavailable_rejected_cash_zero"] == 1
    assert result["final_nav_cost_basis"] == pytest.approx(1.10)
    assert result["daily_realised_return_metric"]["n"] == len(dates)


def test_vendor_stratum_excludes_clones_and_stamps_retrospective_rows(tmp_path: Path):
    clock = MarketCalendar.from_dates(pd.to_datetime(["2026-07-03", "2026-07-06"]))
    vendor_path = tmp_path / "zt.parquet"
    pd.DataFrame(
        {
            "ticker": ["600001.SH", "600001.SH", "600001.SH"],
            "date": ["2026-07-03", "2026-07-04", "2026-07-06"],
            "asof": ["2026-07-06", "2026-07-04", "2026-07-06"],
            "seal_fund_yi": [1.0, 99.0, 2.0],
            "failed_seals": [1, 9, 0],
            "turnover_pct": [10.0, 99.0, 5.0],
        }
    ).to_parquet(vendor_path, index=False)
    events = pd.DataFrame(
        [
            {
                "ticker": "600001.SS",
                "signal_date": "2026-07-03",
                "market_scope": "main_primary",
                "split": "vendor_tail_audit",
                "next_board": True,
                "date_cluster": "2026-07-03",
                "run_cluster": "r1",
            },
            {
                "ticker": "600001.SS",
                "signal_date": "2026-07-06",
                "market_scope": "main_primary",
                "split": "vendor_tail_audit",
                "next_board": False,
                "date_cluster": "2026-07-06",
                "run_cluster": "r2",
            },
        ]
    )
    result = _vendor_descriptive_stratum(vendor_path, events, clock)
    assert result["excluded_clone_dates"] == ["2026-07-04"]
    assert result["excluded_clone_rows"] == 1
    assert result["valid_observed_session_rows"] == 2
    assert result["retrospectively_fetched_rows"] == 1
    assert result["joined_curated_event_rows"] == 2
    assert result["literal_joined_curated_event_rows_sensitivity"] == 0
    assert result["alias_recovered_join_rows"] == 2
    assert result["sh_alias_rows_normalized"] == 2
    assert result["return_metrics"] == []


def test_vendor_pool_identity_canonicalization_matches_procurement_census():
    assert canonical_ticker("600000.SH") == "600000.SS"
    assert canonical_ticker("000001.sz") == "000001.SZ"
    raw_tickers = {path.stem for path in DEFAULT_RAW_DIR.glob("*.parquet")}
    inventory = _zt_inventory(
        DEFAULT_ZT_PATH,
        raw_tickers,
        load_market_calendar(DEFAULT_CALENDAR_PATH),
    )
    # Wave 0 physically removes the 818 weekend-clone rows; the continuation
    # inventory must bind to that repaired 3,102-row artifact, not merely
    # filter the stale pre-repair file at measurement time.
    assert inventory["rows"] == 3102
    assert inventory["literal_unique_tickers"] == 1770
    assert inventory["unique_tickers"] == 1607
    assert inventory["literal_raw_overlap_tickers"] == 514
    assert inventory["raw_overlap_tickers"] == 580
    assert inventory["raw_overlap_pct"] == pytest.approx(580 / 1607 * 100.0)
    assert inventory["vendor_tickers_without_raw_ohlcv"] == 1027
    assert inventory["valid_observed_session_rows"] == 3102
    assert inventory["valid_observed_rows_with_raw_ohlcv"] == 1187
    assert inventory["canonical_duplicate_ticker_date_rows"] == 0


def test_ecology_is_causal_with_respect_to_future_dates():
    dates = pd.bdate_range("2025-01-02", periods=80)
    counters = {
        "universe_n": Counter({d: 100 for d in dates}),
        "sealed_up": Counter({d: 5 for d in dates}),
        "first_board": Counter({d: 3 for d in dates}),
        "failed_up": Counter({d: 1 for d in dates}),
        "sealed_down": Counter({d: 0 for d in dates}),
    }
    event_rows = []
    for i, d in enumerate(dates[:-1]):
        event_rows.append(
            {
                "next_session_date": str(dates[i + 1].date()),
                "next_board": i % 3 == 0,
            }
        )
    events = pd.DataFrame(event_rows)
    base = _build_ecology(counters, events)

    changed = {key: Counter(value) for key, value in counters.items()}
    changed["sealed_up"][dates[-1]] = 99
    changed_result = _build_ecology(changed, events)
    compare_date = dates[-2]
    base_row = base[base["date"].eq(compare_date)].iloc[0]
    changed_row = changed_result[changed_result["date"].eq(compare_date)].iloc[0]
    assert base_row["ecology_soft_score"] == pytest.approx(changed_row["ecology_soft_score"])


def test_boundary_purge_removes_only_final_ten_sessions_of_prior_blocks():
    calendar = pd.bdate_range("2019-11-01", "2024-02-01")
    rows = pd.DataFrame(
        {
            "signal_date": calendar.strftime("%Y-%m-%d"),
            "split": [
                "train_2011_2019"
                if d.year == 2019
                else (
                    "calibration_2020_2023"
                    if d.year <= 2023
                    else "historical_replay_after_common_prior"
                )
                for d in calendar
            ],
        }
    )
    purged, audit = apply_boundary_purge(rows, calendar)
    assert audit["sessions_per_boundary"] == BOUNDARY_PURGE_SESSIONS
    assert audit["event_rows_removed"]["train_2011_2019"] == BOUNDARY_PURGE_SESSIONS
    assert audit["event_rows_removed"]["calibration_2020_2023"] == BOUNDARY_PURGE_SESSIONS
    assert (purged["split"] == "calibration_2020_2023").sum() == (
        (rows["split"] == "calibration_2020_2023").sum() - BOUNDARY_PURGE_SESSIONS
    )


def test_full_small_fixture_is_deterministic_and_postgap_has_no_returns(tmp_path: Path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    _event_frame_for_measurement().to_parquet(raw_dir / "000001.SZ.parquet")
    calendar_path = tmp_path / "calendar.parquet"
    pd.DataFrame(
        {"close": 1.0}, index=_event_frame_for_measurement().index
    ).to_parquet(calendar_path)
    zt_path = tmp_path / "zt.parquet"
    pd.DataFrame(
        {
            "ticker": ["000001.SZ", "999999.SZ"],
            "date": ["2026-06-15", "2026-06-15"],
            "asof": ["2026-07-06", "2026-07-06"],
            "seal_fund_yi": [1.0, 2.0],
            "failed_seals": [0, 1],
            "turnover_pct": [5.0, 10.0],
        }
    ).to_parquet(zt_path, index=False)

    first = run_measurement(
        raw_dir=raw_dir,
        calendar_path=calendar_path,
        st_path=tmp_path / "missing_st.parquet",
        zt_path=zt_path,
    )
    second = run_measurement(
        raw_dir=raw_dir,
        calendar_path=calendar_path,
        st_path=tmp_path / "missing_st.parquet",
        zt_path=zt_path,
    )
    assert first == second
    postgap = first["results"]["C_POSTGAP"]
    assert postgap["return_metrics"] == []
    assert postgap["return_metrics_status"].startswith("PROHIBITED")
    assert first["authority"] == "none_research_display_only"
    assert first["data_inventory"]["zt_pool"]["vendor_tickers_without_raw_ohlcv"] == 1
    assert first["results"]["C_AUCTION"]["primary_n1_n2_event_level_metrics"]
    assert first["results"]["C_AUCTION"]["event_level_expectancy_label"].endswith(
        "NOT_A_PORTFOLIO_RETURN"
    )
    assert first["results"]["C_AUCTION"]["strict_sealed_close_event_level_sensitivity"]
    assert first["results"]["C0_TRUE_NEXT_SESSION"]["strict_sealed_close_sensitivity"]
    assert first["results"]["C_AUCTION_PRIMARY_N1_N2_PORTFOLIO"][
        "self_financing_paper_book"
    ]["metrics"]
    portfolio_metrics = first["results"]["C_AUCTION_PRIMARY_N1_N2_PORTFOLIO"][
        "self_financing_paper_book"
    ]["metrics"]
    assert {row["cost_bps"] for row in portfolio_metrics} == {0, 30, 60, 100}
    assert {row["exit_id"] for row in portfolio_metrics} == set(EXIT_IDS)
    assert first["results"]["C_AUCTION"]["primary_n1_n2_fill_funnel"]
    assert first["ore_coverage_ledger"]["n3plus"]["status"].startswith("EXPLORATORY")
    fingerprint = first["data_inventory"]["input_provenance"]
    assert fingerprint["combined_sha256"]
    assert "snapshot still contains 2 off-calendar clone rows" in fingerprint[
        "zt_pool_snapshot_disclosure"
    ]
    assert set(fingerprint["components"]) == {
        "raw_ohlcv_content_sha256",
        "calendar_content_sha256",
        "st_snapshot_content_sha256",
        "zt_pool_content_sha256",
        "runner_content_sha256",
        "definition_config_sha256",
    }
    assert first["results"]["FROZEN_CROWD_CLOCK"]["table"]
    for construction_id in (
        "C_AUCTION_N",
        "C_AUCTION_ONE_PRICE_D_CLOSE",
        "C_AUCTION_INTRADAY_RANGE_D_CLOSE",
        "C_AUCTION_ECOLOGY_D_CLOSE",
    ):
        construction = first["results"][construction_id]
        assert construction["combination_search"] == "PROHIBITED_NOT_RUN"
        assert {row["cost_bps"] for row in construction["joint_candidate_book_metrics"]} == {
            0,
            30,
            60,
            100,
        }
        assert {row["exit_id"] for row in construction["joint_candidate_book_metrics"]} == {
            "tplus1_legal_open",
            "tplus1_legal_close",
            "tplus2_close",
            "tplus4_close",
            "seal_state_next_open",
        }
    assert all("UNTESTED VARIANTS" in row["ore_ledger"] for row in first["construction_verdicts"])

    markdown = render_markdown(first)
    assert "realised D+1 gap is not a selection filter" in markdown
    assert "## UNTESTED VARIANTS" in markdown
    assert "## Frozen crowd clock" in markdown
    assert "## Predeclared 2015 standalone stress era" in markdown
    assert "## ORE coverage ledger" in markdown
    assert "It is not a portfolio return" in markdown
    assert "strategy-level return" not in markdown
    assert markdown.rstrip().endswith(first["UNTESTED VARIANTS"][-1])


@pytest.mark.parametrize(
    ("value", "queue", "expected"),
    [
        (-0.3, False, "le_neg_0_25_band"),
        (0.1, False, "zero_to_0_25_band"),
        (0.9, False, "gt_0_80_band_below_queue"),
        (0.9, True, "upper_limit_queue"),
    ],
)
def test_postgap_buckets_are_fixed(value: float, queue: bool, expected: str):
    assert gap_bucket(value, queue) == expected
