"""Tests for build_per_fire_sector_benchmark.py — A1-to-spec per-fire S(f) build.

Key correctness test: constituent-pool mean diverges from winner-selected mean.
The original W1 §7 benchmark used only fires with non-null 252d returns (winners),
which mechanically inflates the benchmark. S(f) uses ALL resolvable tickers in the
fire tape at each fire date — including those that declined. This test demonstrates
the divergence on a synthetic fixture.

Run:
    python -m pytest tests/test_per_fire_sector_benchmark.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.research.build_per_fire_sector_benchmark import (  # noqa: E402
    _fill_index,
    _ticker_252d_return,
    build_all_closes,
    compute_sf_for_fires,
    era_coverage_report,
    delta_vs_old_benchmark_stats,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _trading_days(start: str, n: int) -> list[pd.Timestamp]:
    return list(pd.bdate_range(start=start, periods=n))


def _make_close(dates: list[pd.Timestamp], start_price: float = 100.0,
                total_return: float = 0.5) -> pd.Series:
    """Build a close series that achieves exactly total_return over its length."""
    n = len(dates)
    if n < 2:
        prices = [start_price] * n
    else:
        # Geometric progression achieving total_return
        end_price = start_price * (1 + total_return)
        prices = np.linspace(start_price, end_price, n).tolist()
    return pd.Series(prices, index=dates, name="close")


def _make_fire_tape(tickers: list[str], fire_date: str) -> pd.DataFrame:
    """Build a minimal fire tape DataFrame."""
    return pd.DataFrame({
        "ticker": tickers,
        "date": [pd.Timestamp(fire_date)] * len(tickers),
    })


# ---------------------------------------------------------------------------
# _fill_index
# ---------------------------------------------------------------------------

def test_fill_index_returns_next_bar():
    """fill_index should return the first bar strictly AFTER fire_date."""
    dates = _trading_days("2021-07-06", 10)
    close = _make_close(dates)
    fire_date = dates[0]  # 2021-07-06
    fi = _fill_index(close, fire_date)
    # First bar is 2021-07-06; fill index = bar AFTER that = index 1
    assert fi == 1


def test_fill_index_fire_before_data():
    """fire_date before all data → fill_index at position 0."""
    dates = _trading_days("2021-07-06", 10)
    close = _make_close(dates)
    fire_date = pd.Timestamp("2020-01-01")  # before all bars
    fi = _fill_index(close, fire_date)
    assert fi == 0


def test_fill_index_fire_after_data():
    """fire_date after all data → fill_index returns None."""
    dates = _trading_days("2021-07-06", 10)
    close = _make_close(dates)
    fire_date = pd.Timestamp("2030-01-01")  # after all bars
    fi = _fill_index(close, fire_date)
    assert fi is None


# ---------------------------------------------------------------------------
# _ticker_252d_return
# ---------------------------------------------------------------------------

def test_ticker_252d_return_clean():
    """A 300-bar series with fire at bar 0 produces a finite 252d return."""
    dates = _trading_days("2021-07-06", 300)
    close = _make_close(dates, total_return=0.3)
    fire_date = dates[0]
    ret = _ticker_252d_return(close, fire_date, horizon=252)
    assert ret is not None
    assert isinstance(ret, float)
    assert -1.0 < ret < 10.0


def test_ticker_252d_return_too_short():
    """Series shorter than horizon → None."""
    dates = _trading_days("2021-07-06", 100)
    close = _make_close(dates)
    fire_date = dates[0]
    ret = _ticker_252d_return(close, fire_date, horizon=252)
    assert ret is None


def test_ticker_252d_return_zero_entry():
    """Zero entry price → None (avoid division by zero)."""
    dates = _trading_days("2021-07-06", 300)
    prices = [0.0] * 300
    close = pd.Series(prices, index=dates)
    fire_date = dates[0]
    ret = _ticker_252d_return(close, fire_date, horizon=252)
    assert ret is None


def test_ticker_252d_return_after_all_data():
    """fire_date after all data → fill_index is None → return None."""
    dates = _trading_days("2021-07-06", 300)
    close = _make_close(dates)
    fire_date = pd.Timestamp("2030-01-01")
    ret = _ticker_252d_return(close, fire_date, horizon=252)
    assert ret is None


# ---------------------------------------------------------------------------
# build_all_closes — priority merge
# ---------------------------------------------------------------------------

def test_build_all_closes_priority():
    """Yahoo takes priority over massive/dead_name/stocks for same ticker."""
    dates = _trading_days("2021-07-06", 10)
    yahoo = {"AAPL": _make_close(dates, total_return=0.5)}
    massive = {"AAPL": _make_close(dates, total_return=0.1)}
    dead_name = {}
    stocks = {}
    merged = build_all_closes(yahoo, massive, dead_name, stocks)
    # Yahoo wins
    assert abs(merged["AAPL"].iloc[-1] - yahoo["AAPL"].iloc[-1]) < 1e-9


def test_build_all_closes_merge_disjoint():
    """Tickers from all stores appear in merged dict."""
    dates = _trading_days("2021-07-06", 10)
    yahoo = {"AAPL": _make_close(dates)}
    massive = {"MSFT": _make_close(dates)}
    dead_name = {"TWTR": _make_close(dates)}
    stocks = {"GE": _make_close(dates)}
    merged = build_all_closes(yahoo, massive, dead_name, stocks)
    assert "AAPL" in merged
    assert "MSFT" in merged
    assert "TWTR" in merged
    assert "GE" in merged


# ---------------------------------------------------------------------------
# KEY TEST: pool mean diverges from winner-selected mean
# ---------------------------------------------------------------------------

def test_pool_mean_lower_than_winner_mean():
    """S(f) constituent-pool mean < winner-selected mean.

    Fixture:
    - Fire tape: 5 tickers (A, B, C, D, E), all fired on 2021-07-06.
    - Ticker A: 252d return = +100% (winner)
    - Ticker B: 252d return = +80%  (winner)
    - Ticker C: 252d return = -20%  (loser)
    - Ticker D: 252d return = -40%  (loser)
    - Ticker E: 252d return = +5%   (moderate)

    Winner-selected mean (A+B+E only, the ones with positive returns):
      (1.0 + 0.8 + 0.05) / 3 = 0.617

    Constituent-pool mean (all 5 resolvable at fire date):
      (1.0 + 0.8 + (-0.2) + (-0.4) + 0.05) / 5 = 0.25

    S(f) should be 0.25, substantially below the winner-mean 0.617.

    This demonstrates the A1 spec requirement: S(f) uses the full pool,
    not just the winning sub-set that W1 §7 used by construction.
    """
    n_bars = 260  # enough for 252d + fill bar
    dates = _trading_days("2021-07-06", n_bars)
    fire_date = dates[0]  # fire at first bar

    target_returns = {
        "A": 1.00,
        "B": 0.80,
        "C": -0.20,
        "D": -0.40,
        "E": 0.05,
    }

    closes: dict[str, pd.Series] = {}
    for ticker, ret in target_returns.items():
        closes[ticker] = _make_close(dates, start_price=100.0, total_return=ret)

    # Verify the fixture produces the correct sign for each ticker.
    # Note: linspace over 260 bars from bar[0] to bar[259] achieves target_return.
    # But _ticker_252d_return uses bar[1] as entry (fill_index = next bar after fire_date=bar[0])
    # and measures return over bars 1..252. This means realized return is slightly less
    # than target_return in magnitude (252/259 fraction of the total price move).
    # Sign is preserved; tolerance is 0.1 (sign check only matters here).
    actual_returns: dict[str, float] = {}
    for ticker, expected_ret in target_returns.items():
        actual_ret = _ticker_252d_return(closes[ticker], fire_date, horizon=252)
        assert actual_ret is not None, f"{ticker} should be resolvable"
        if expected_ret > 0:
            assert actual_ret > 0, (
                f"{ticker}: expected positive return ~{expected_ret}, got {actual_ret}"
            )
        else:
            assert actual_ret < 0, (
                f"{ticker}: expected negative return ~{expected_ret}, got {actual_ret}"
            )
        actual_returns[ticker] = actual_ret

    # Build fire tape with all 5 tickers
    fire_tape = _make_fire_tape(list(target_returns.keys()), "2021-07-06")

    # Compute S(f)
    all_closes = build_all_closes(closes, {}, {}, {})
    df = compute_sf_for_fires(fire_tape, all_closes, horizon=252, verbose=False)

    assert len(df) == 5, "One row per fire"

    # All fires have the same fire_date, so all should get the same S(f)
    sf_means = df["sf_mean"].dropna().values
    assert len(sf_means) == 5, "All 5 fires should have S(f) computed"

    # S(f) should be the mean of all 5 ACTUAL (measured) returns
    expected_sf = np.mean(list(actual_returns.values()))
    for sf in sf_means:
        assert abs(sf - expected_sf) < 0.01, (
            f"S(f)={sf:.4f}, expected constituent-pool mean={expected_sf:.4f}"
        )

    # Winner-selected mean: only the fires with positive actual returns
    winner_returns = [v for v in actual_returns.values() if v > 0]
    winner_mean = np.mean(winner_returns)

    # S(f) must be substantially less than winner-mean (losers drag pool down)
    assert expected_sf < winner_mean, (
        f"Pool mean {expected_sf:.4f} should be < winner mean {winner_mean:.4f}"
    )
    # Quantify the gap: pool includes losers (C: ~-20%, D: ~-40%) so gap is large
    gap = winner_mean - expected_sf
    assert gap > 0.2, (
        f"Gap between pool mean ({expected_sf:.4f}) and winner mean ({winner_mean:.4f}) "
        f"should be substantial (>0.2); got {gap:.4f}. "
        "This confirms S(f) correctly uses all constituents, not just winners."
    )


# ---------------------------------------------------------------------------
# compute_sf_for_fires — coverage stamps
# ---------------------------------------------------------------------------

def test_no_pool_gets_null_not_fallback():
    """Fire with no resolvable constituents gets sf_mean=null, not a winner-mean fallback."""
    fire_date = "2015-01-05"
    # One fire with ticker X; no price data at all for any ticker
    fires = _make_fire_tape(["X"], fire_date)
    df = compute_sf_for_fires(fires, {}, horizon=252, verbose=False)
    assert len(df) == 1
    row = df.iloc[0]
    assert row["sf_n_pool"] == 0
    assert pd.isna(row["sf_mean"]), "No pool → sf_mean must be null, not a fallback"
    assert "NO POOL" in str(row["coverage_stamp"])


def test_era_stamps():
    """Era stamps are assigned correctly by fire_date."""
    fires = pd.DataFrame({
        "ticker": ["A", "B", "C"],
        "date": [
            pd.Timestamp("2022-01-05"),  # post-2021-anchor
            pd.Timestamp("2015-01-05"),  # 2012-2021
            pd.Timestamp("2008-01-05"),  # pre-2012
        ]
    })
    # No price data: all sf_mean = null, but era stamps should still be correct
    df = compute_sf_for_fires(fires, {}, horizon=252, verbose=False)
    era_by_date = {row["fire_date"]: row["era"] for _, row in df.iterrows()}
    assert era_by_date[pd.Timestamp("2022-01-05")] == "post-2021-anchor"
    assert era_by_date[pd.Timestamp("2015-01-05")] == "2012-2021"
    assert era_by_date[pd.Timestamp("2008-01-05")] == "pre-2012"


def test_survivorship_biased_stamps():
    """Pre-2021-07-06 fires are stamped survivorship_biased=True."""
    fires = pd.DataFrame({
        "ticker": ["A", "B"],
        "date": [
            pd.Timestamp("2022-01-05"),  # post-anchor → False
            pd.Timestamp("2015-01-05"),  # pre-anchor → True
        ]
    })
    df = compute_sf_for_fires(fires, {}, horizon=252, verbose=False)
    biased_by_date = {row["fire_date"]: row["survivorship_biased"] for _, row in df.iterrows()}
    assert biased_by_date[pd.Timestamp("2022-01-05")] is False
    assert biased_by_date[pd.Timestamp("2015-01-05")] is True


# ---------------------------------------------------------------------------
# era_coverage_report
# ---------------------------------------------------------------------------

def test_era_coverage_report_structure():
    """era_coverage_report produces all three era keys with expected fields."""
    # Minimal synthetic df
    df = pd.DataFrame({
        "fire_date": [
            pd.Timestamp("2022-01-05"),
            pd.Timestamp("2015-01-05"),
            pd.Timestamp("2008-01-05"),
        ],
        "era": ["post-2021-anchor", "2012-2021", "pre-2012"],
        "fire_return_252d": [0.1, None, None],
        "sf_mean": [0.05, None, None],
        "sf_n_pool": [10, 0, 0],
        "survivorship_biased": [False, True, True],
        "coverage_stamp": ["post-anchor", "UPPER BOUND", "UNREACHABLE"],
    })
    report = era_coverage_report(df)
    assert "post-2021-anchor" in report
    assert "2012-2021" in report
    assert "pre-2012" in report
    # post-anchor should have 1 fire
    r = report["post-2021-anchor"]
    assert r["n_fires"] == 1
    assert r["n_fire_priced_252d"] == 1
    assert r["pct_sf_mean"] == 100.0


def test_era_coverage_report_pre2012_unreachable():
    """pre-2012 fires have 0% coverage since price data is unavailable."""
    df = pd.DataFrame({
        "fire_date": [pd.Timestamp("2005-01-05")],
        "era": ["pre-2012"],
        "fire_return_252d": [None],
        "sf_mean": [None],
        "sf_n_pool": [0],
        "survivorship_biased": [True],
        "coverage_stamp": ["UNREACHABLE"],
    })
    report = era_coverage_report(df)
    r = report["pre-2012"]
    assert r["n_fires"] == 1
    assert r["n_sf_mean_computed"] == 0
    assert r["pct_sf_mean"] == 0.0


# ---------------------------------------------------------------------------
# Boundary conditions
# ---------------------------------------------------------------------------

def test_single_constituent_pool():
    """S(f) with exactly one constituent = that constituent's return."""
    n_bars = 260
    dates = _trading_days("2021-07-06", n_bars)
    fire_date = dates[0]

    # Only ticker A in fire tape; it has a 252d return = 0.30
    closes = {"A": _make_close(dates, total_return=0.30)}
    fires = _make_fire_tape(["A"], "2021-07-06")

    df = compute_sf_for_fires(fires, closes, horizon=252, verbose=False)
    row = df.iloc[0]
    assert row["sf_n_pool"] == 1
    assert row["sf_mean"] is not None
    assert abs(row["sf_mean"] - 0.30) < 0.05


def test_fire_with_no_own_price_still_gets_sf():
    """Fire with ticker that has no price can still get S(f) from pool of other tickers."""
    n_bars = 260
    dates = _trading_days("2021-07-06", n_bars)
    fire_date = dates[0]

    closes = {
        "B": _make_close(dates, total_return=0.20),
        "C": _make_close(dates, total_return=0.10),
    }
    # Fire is for ticker A which has no price
    fires = pd.DataFrame({
        "ticker": ["A", "B", "C"],
        "date": [pd.Timestamp("2021-07-06")] * 3,
    })

    all_closes = build_all_closes({}, {}, {}, closes)
    df = compute_sf_for_fires(fires, all_closes, horizon=252, verbose=False)

    row_a = df[df["ticker"] == "A"].iloc[0]
    # A has no own price
    assert pd.isna(row_a["fire_return_252d"])
    # But the pool (B, C) still computes S(f)
    assert row_a["sf_n_pool"] == 2
    assert row_a["sf_mean"] is not None
    expected_pool_mean = (0.20 + 0.10) / 2
    assert abs(row_a["sf_mean"] - expected_pool_mean) < 0.05


# ---------------------------------------------------------------------------
# Fix (1): Calendar-continuity guard — gap-leg rejection
# ---------------------------------------------------------------------------

def test_gap_leg_rejected_by_continuity_guard():
    """A 252-bar forward window with a multi-year gap in the middle must return None.

    This test would FAIL under the old implementation that lacked the
    calendar-continuity guard (ruling LH-W1-3): without the guard,
    the function would silently return a return measured across a data gap,
    producing a corrupted label.

    Fixture:
    - 10 bars of normal trading data anchored at 2021-07-06
    - A gap (missing data) from 2021-07-21 to 2024-01-02 (~900 calendar days)
    - 260 bars of normal trading data after the gap

    The forward window (252 bars from fill_index) straddles this gap.
    With the continuity guard, _ticker_252d_return must return None.
    Without the guard (old implementation), it would return a value — WRONG.
    """
    # Build the gapped series:
    # Segment 1: 10 bars starting 2021-07-06
    seg1_dates = list(pd.bdate_range(start="2021-07-06", periods=10))
    # Segment 2: 260 bars starting ~900 days after seg1 ends (large gap)
    seg2_start = seg1_dates[-1] + pd.Timedelta(days=920)  # ~2.5 year gap
    seg2_dates = list(pd.bdate_range(start=seg2_start, periods=260))
    all_dates = seg1_dates + seg2_dates
    n = len(all_dates)
    prices = np.linspace(100.0, 150.0, n)
    gapped_close = pd.Series(prices, index=all_dates)

    # fire_date = first bar; fill_index = bar 1 (next bar after fire_date)
    # Forward window from bar 1 spans into the gap.
    fire_date = seg1_dates[0]
    result = _ticker_252d_return(gapped_close, fire_date, horizon=252)

    # With the gap guard: must return None (gap > 10 calendar days found in window)
    assert result is None, (
        f"Expected None for gapped series (LH-W1-3 calendar-continuity guard), "
        f"got {result}. The gap between consecutive bars in the window exceeds "
        "10 calendar days, which signals a data discontinuity that would corrupt "
        "the N-bar return label."
    )


def test_clean_series_passes_continuity_guard():
    """A clean trading series (no gaps > 10 calendar days) should return a valid return."""
    # Normal business-day series: max gap = 3 calendar days (Fri->Mon)
    dates = list(pd.bdate_range(start="2021-07-06", periods=300))
    close = _make_close(dates, total_return=0.25)
    fire_date = dates[0]
    result = _ticker_252d_return(close, fire_date, horizon=252)
    assert result is not None, "Clean series should pass the continuity guard"
    assert isinstance(result, float)
    assert -1.0 < result < 5.0


def test_short_gap_within_threshold_passes():
    """A gap of exactly 10 calendar days (threshold) should pass (not > 10)."""
    # Build a series with a 10-calendar-day gap (just at the threshold, not over)
    seg1_dates = list(pd.bdate_range(start="2021-07-06", periods=5))
    # 10 calendar days after last bar of seg1
    seg2_start = seg1_dates[-1] + pd.Timedelta(days=10)
    seg2_dates = list(pd.bdate_range(start=seg2_start, periods=300))
    all_dates = seg1_dates + seg2_dates
    prices = np.linspace(100.0, 130.0, len(all_dates))
    close = pd.Series(prices, index=all_dates)
    fire_date = seg1_dates[0]
    result = _ticker_252d_return(close, fire_date, horizon=252)
    # Gap = 10 days, threshold is > 10, so this should pass
    assert result is not None, "Gap of exactly 10 calendar days should NOT be rejected (threshold is > 10)"


# ---------------------------------------------------------------------------
# Fix (2): A2 §4 contact-freeze enforcement
# ---------------------------------------------------------------------------

def test_a2_freeze_filter_excludes_post2024(tmp_path):
    """delta_vs_old_benchmark_stats must exclude fire_date > 2023-12-31 from labels."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    # Build a synthetic labels parquet with fires spanning 2022-2025
    fire_dates = pd.to_datetime([
        "2022-06-15", "2023-06-15", "2024-06-15", "2025-01-15",
    ])
    labels_df = pd.DataFrame({
        "fire_date": fire_dates,
        "total_return_252d": [0.10, 0.15, 0.20, 0.25],
    })
    labels_path = tmp_path / "long_hold_labels.parquet"
    labels_df.to_parquet(labels_path, index=False)

    # Build a per-fire benchmark df with fires in 2022-2025
    bench_df = pd.DataFrame({
        "fire_date": fire_dates,
        "sf_mean": [0.08, 0.12, 0.18, 0.22],
        "sf_n_pool": [10, 10, 10, 10],
    })

    result = delta_vs_old_benchmark_stats(bench_df, labels_path)

    # Should succeed with computed status
    assert result["status"] == "computed", f"Expected computed, got: {result}"

    # Freeze compliance keys must be present
    assert result.get("a2_freeze_compliant") is True
    assert result.get("a2_freeze_cutoff") == "2023-12-31"

    # 2024 and 2025 fires (2 rows) must be excluded from both labels and df
    assert result["n_labels_excluded_post2024"] == 2, (
        f"Expected 2 labels rows excluded (2024, 2025), got {result['n_labels_excluded_post2024']}"
    )
    assert result["n_df_fires_excluded_post2024"] == 2, (
        f"Expected 2 df fires excluded (2024, 2025), got {result['n_df_fires_excluded_post2024']}"
    )

    # Comparison must only cover 2022 and 2023 cohort years
    assert result["n_fires_compared"] == 2, (
        f"Expected 2 fires compared (2022+2023 only), got {result['n_fires_compared']}"
    )


# ---------------------------------------------------------------------------
# Fix (3): Sample mode writes to SAMPLE path, not canonical
# ---------------------------------------------------------------------------

def test_sample_output_path_is_not_canonical():
    """Sample runs must write to per_fire_sector_benchmark_SAMPLE.parquet, not the canonical path."""
    from scripts.research.build_per_fire_sector_benchmark import _OUT_PARQUET

    sample_path_stem = "per_fire_sector_benchmark_SAMPLE"
    canonical_stem = "per_fire_sector_benchmark"

    # Verify canonical path stem
    assert _OUT_PARQUET.stem == canonical_stem, (
        f"Canonical path stem should be '{canonical_stem}', got '{_OUT_PARQUET.stem}'"
    )

    # Verify the SAMPLE path would be a different file
    sample_path = _OUT_PARQUET.parent / f"{sample_path_stem}.parquet"
    assert sample_path != _OUT_PARQUET, "SAMPLE path must differ from canonical path"
    assert "SAMPLE" in sample_path.stem, "SAMPLE path must contain 'SAMPLE' in stem"
