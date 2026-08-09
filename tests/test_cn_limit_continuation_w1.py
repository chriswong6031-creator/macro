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
    LIMIT_TOLERANCE,
    MarketCalendar,
    _book_summary,
    _build_ecology,
    _fixed_exit,
    _seal_state_exit,
    _vendor_descriptive_stratum,
    apply_boundary_purge,
    board_era,
    extract_ticker_events,
    gap_bucket,
    limit_width,
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
    dates: pd.DatetimeIndex | None = None,
) -> pd.DataFrame:
    n = len(closes)
    dates = dates if dates is not None else pd.bdate_range("2025-01-02", periods=n)
    opens = list(closes) if opens is None else opens
    highs = [max(o, c) for o, c in zip(opens, closes)] if highs is None else highs
    lows = [min(o, c) for o, c in zip(opens, closes)] if lows is None else lows
    return pd.DataFrame(
        {
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": np.linspace(1_000_000, 2_000_000, n),
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


def test_c0_uses_true_next_common_market_session_across_weekend():
    dates = pd.to_datetime(["2025-01-02", "2025-01-03", "2025-01-06", "2025-01-07"])
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
        start_date=pd.Timestamp("2025-01-01"),
        end_date=pd.Timestamp("2025-12-31"),
        min_prior_sessions=1,
        market_calendar=MarketCalendar.from_dates(dates),
    )
    friday = next(row for row in rows if row["signal_date"] == "2025-01-03")
    assert friday["next_session_date"] == "2025-01-06"
    assert friday["calendar_gap_days"] == 3
    assert friday["next_board"] is True


def test_missing_true_next_session_stays_in_denominator_and_resets_ladder():
    market_dates = pd.to_datetime(
        ["2025-01-02", "2025-01-03", "2025-01-06", "2025-01-07", "2025-01-08"]
    )
    # The ticker is halted/missing on Monday and resumes with a board on Tuesday.
    ticker_dates = pd.to_datetime(["2025-01-02", "2025-01-03", "2025-01-07", "2025-01-08"])
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
        start_date=pd.Timestamp("2025-01-01"),
        end_date=pd.Timestamp("2025-12-31"),
        min_prior_sessions=1,
        market_calendar=MarketCalendar.from_dates(market_dates),
    )
    friday = next(row for row in rows if row["signal_date"] == "2025-01-03")
    resumed = next(row for row in rows if row["signal_date"] == "2025-01-07")
    assert friday["next_session_date"] == "2025-01-06"
    assert friday["next_session_state"] == "no_bar_halt_or_data_missing"
    assert friday["next_board"] is False
    assert friday["next_board_observed_bar_sensitivity"] is None
    assert friday["next_observed_ticker_date_sensitivity"] == "2025-01-07"
    assert friday["entry_fill_state"] == "no_bar_halt_or_data_missing_no_fill"
    assert resumed["board_count"] == 1
    assert resumed["ticker_session_board_count_sensitivity"] == 2


def test_open_at_upper_limit_is_queue_no_fill_and_gap_is_not_a_selection_field():
    dates = pd.bdate_range("2025-01-02", periods=5)
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
    dates = pd.bdate_range("2025-01-02", periods=6)
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
    dates = pd.bdate_range("2025-01-02", periods=6)
    opens = np.array([10.0, 11.0, 10.89, 10.89, 10.95, 11.1])
    lowers = np.array([9.0, 9.9, 10.89, 10.89, 10.8, 10.9])
    sealed = np.array([False, True, True, False, False, False])
    clock = MarketCalendar.from_dates(dates)
    date_to_index = {date: i for i, date in enumerate(dates)}
    obs, held = _seal_state_exit(
        opens=opens,
        lowers=lowers,
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
        ["2025-01-02", "2025-01-03", "2025-01-06", "2025-01-07", "2025-01-08", "2025-01-09"]
    )
    ticker_dates = pd.to_datetime(
        ["2025-01-02", "2025-01-03", "2025-01-06", "2025-01-08", "2025-01-09"]
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
        start_date=pd.Timestamp("2025-01-01"),
        end_date=pd.Timestamp("2025-12-31"),
        min_prior_sessions=1,
        market_calendar=MarketCalendar.from_dates(market_dates),
    )
    event = next(row for row in rows if row["signal_date"] == "2025-01-03")
    assert event["entry_fill_state"] == "official_open_candidate_fill"
    assert event["exits"]["tplus1_legal_open"]["exit_date"] == "2025-01-07"
    assert event["exits"]["tplus1_legal_open"]["gross_return"] is None
    assert event["exits"]["tplus1_legal_open"]["exit_reason"] == "missing_bar_halt_or_data_missing"
    assert event["exits"]["seal_state_next_open"]["gross_return"] is None
    assert event["exits"]["seal_state_next_open"]["exit_reason"] == "missing_bar_halt_or_data_missing"


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


def test_vendor_stratum_excludes_clones_and_stamps_retrospective_rows(tmp_path: Path):
    clock = MarketCalendar.from_dates(pd.to_datetime(["2026-07-03", "2026-07-06"]))
    vendor_path = tmp_path / "zt.parquet"
    pd.DataFrame(
        {
            "ticker": ["000001.SZ", "000001.SZ", "000001.SZ"],
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
                "ticker": "000001.SZ",
                "signal_date": "2026-07-03",
                "market_scope": "main_primary",
                "split": "vendor_tail_audit",
                "next_board": True,
                "date_cluster": "2026-07-03",
                "run_cluster": "r1",
            },
            {
                "ticker": "000001.SZ",
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
    assert result["return_metrics"] == []


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
    assert first["results"]["C_AUCTION"]["joint_candidate_book_metrics"]
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
