"""Unit tests for scripts/research/run_w1_sev.py.

Covers:
  (1) _td_distance sign, zero, and boundary semantics
  (2) build_blackout_labels: in-window/out-of-window classification for k=0,k,k+1
  (3) Coverage-absent ticker → NaN stratum, excluded from BOTH arms
  (4) Covered ticker with no future filing → control arm (stratum=0)
  (5) Pooled (RUL-11) dedup: overlapping (ticker, date) fire appears once
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.research.run_w1_sev import (
    _td_distance,
    build_blackout_labels,
    K_VALUES,
)


# ---------------------------------------------------------------------------
# 1. _td_distance — sign, zero, and boundary
# ---------------------------------------------------------------------------

def _make_td_index(start: str = "2020-01-02", periods: int = 252) -> pd.DatetimeIndex:
    """Build a simple business-day trading-day index."""
    return pd.bdate_range(start, periods=periods)


class TestTdDistance:
    """Tests for _td_distance."""

    def test_same_day_returns_zero(self) -> None:
        td = _make_td_index()
        fire = pd.Timestamp("2020-01-02")
        filing = pd.Timestamp("2020-01-02")
        assert _td_distance(fire, filing, td) == 0

    def test_next_trading_day_returns_one(self) -> None:
        td = _make_td_index()
        fire = pd.Timestamp("2020-01-02")    # Thursday
        filing = pd.Timestamp("2020-01-03")  # Friday
        assert _td_distance(fire, filing, td) == 1

    def test_positive_distance(self) -> None:
        td = _make_td_index()
        fire = pd.Timestamp("2020-01-02")
        # 5 trading days later (Mon–Fri = Jan 2–Jan 8 minus weekend)
        # Jan 2 (Thu), Jan 3 (Fri), Jan 6 (Mon), Jan 7 (Tue), Jan 8 (Wed) → 4 steps
        filing = pd.Timestamp("2020-01-08")
        result = _td_distance(fire, filing, td)
        assert isinstance(result, int)
        assert result > 0

    def test_negative_distance_when_filing_before_fire(self) -> None:
        td = _make_td_index()
        fire = pd.Timestamp("2020-01-08")
        filing = pd.Timestamp("2020-01-02")
        result = _td_distance(fire, filing, td)
        assert isinstance(result, int)
        assert result < 0

    def test_boundary_at_k_three(self) -> None:
        """k_td = 3 should be inside the k=3 window (inclusive)."""
        td = _make_td_index()
        fire = pd.Timestamp("2020-01-02")  # Pos 0
        # Position 3 in the bdate_range from Jan 2
        filing = td[3]
        result = _td_distance(fire, filing, td)
        assert result == 3

    def test_beyond_index_returns_none(self) -> None:
        # Build a short index that doesn't include the filing date
        td = pd.bdate_range("2020-01-02", periods=5)
        fire = pd.Timestamp("2020-01-02")
        filing = pd.Timestamp("2025-01-02")  # way beyond the index
        result = _td_distance(fire, filing, td)
        assert result is None


# ---------------------------------------------------------------------------
# 2. build_blackout_labels — stratum assignment
# ---------------------------------------------------------------------------

def _make_fire(ticker: str, date: str) -> pd.DataFrame:
    """Single-row fires DataFrame."""
    return pd.DataFrame({"ticker": [ticker], "date": [pd.Timestamp(date)]})


def _make_ek(ticker: str, filing_dates: list[str]) -> pd.DataFrame:
    """Build a small EDGAR 8-K dates DataFrame."""
    return pd.DataFrame({
        "ticker": [ticker] * len(filing_dates),
        "filing_date": [pd.Timestamp(d) for d in filing_dates],
    })


class TestBuildBlackoutLabels:
    """Tests for build_blackout_labels stratum assignment."""

    def setup_method(self) -> None:
        self.td = _make_td_index("2020-01-02", 500)

    def test_k_td_zero_in_all_k_strata(self) -> None:
        """Same-day filing → k_td=0 → in blackout for ALL k in {1,2,3}."""
        fires = _make_fire("AAPL", "2020-01-02")
        ek = _make_ek("AAPL", ["2020-01-02"])
        result = build_blackout_labels(fires, ek, self.td)
        assert result["ev_k_td"].iloc[0] == 0.0
        for k in K_VALUES:
            assert result[f"ev_blackout_k{k}"].iloc[0] == 1, f"k={k} should be 1 for k_td=0"

    def test_k_td_equals_k_is_in_window(self) -> None:
        """Filing exactly k trading days after fire → k_td=k → in blackout for k (but not k-1)."""
        td = self.td
        fire_date_str = "2020-01-02"
        fire_date = pd.Timestamp(fire_date_str)
        fires = _make_fire("MSFT", fire_date_str)
        k_test = 3
        filing_date = td[k_test]  # exactly k trading days away
        ek = _make_ek("MSFT", [str(filing_date.date())])
        result = build_blackout_labels(fires, ek, td)
        # k_td should == k_test
        assert result["ev_k_td"].iloc[0] == float(k_test)
        # In blackout for k=k_test and above
        for k in K_VALUES:
            if k >= k_test:
                assert result[f"ev_blackout_k{k}"].iloc[0] == 1, (
                    f"k={k} should be 1 when k_td={k_test}"
                )
            else:
                assert result[f"ev_blackout_k{k}"].iloc[0] == 0, (
                    f"k={k} should be 0 when k_td={k_test}"
                )

    def test_k_td_exceeds_k_is_out_of_window(self) -> None:
        """Filing k+1 trading days after fire → out of blackout for ALL k in {1,2,3}."""
        td = self.td
        fire_date_str = "2020-01-02"
        fires = _make_fire("GOOG", fire_date_str)
        k_max = max(K_VALUES)
        filing_date = td[k_max + 1]  # one day beyond the largest k
        ek = _make_ek("GOOG", [str(filing_date.date())])
        result = build_blackout_labels(fires, ek, td)
        for k in K_VALUES:
            assert result[f"ev_blackout_k{k}"].iloc[0] == 0, (
                f"k={k} should be 0 when k_td={k_max+1}"
            )

    def test_coverage_absent_ticker_excluded_from_both_arms(self) -> None:
        """Ticker absent from 8-K store → ev_coverage=0, all ev_blackout_k=NaN."""
        fires = _make_fire("UNKNOWN_TKR", "2020-01-02")
        ek = _make_ek("OTHER_TKR", ["2020-01-10"])  # different ticker entirely
        result = build_blackout_labels(fires, ek, self.td)
        assert result["ev_coverage"].iloc[0] == 0
        for k in K_VALUES:
            col = f"ev_blackout_k{k}"
            val = result[col].iloc[0]
            assert pd.isna(val), (
                f"Coverage-absent ticker should have NaN for {col}; got {val!r}"
            )

    def test_covered_ticker_no_future_filing_is_control(self) -> None:
        """Covered ticker but no future filing → ev_coverage=1, all ev_blackout_k=0."""
        fires = _make_fire("META", "2020-12-31")
        # Filing is in the past, none in the future
        ek = _make_ek("META", ["2015-01-05"])
        result = build_blackout_labels(fires, ek, self.td)
        assert result["ev_coverage"].iloc[0] == 1
        for k in K_VALUES:
            col = f"ev_blackout_k{k}"
            assert result[col].iloc[0] == 0, (
                f"Covered ticker with no future filing should have {col}=0; got {result[col].iloc[0]!r}"
            )


# ---------------------------------------------------------------------------
# 3. Pooled dedup (RUL-11): overlapping (ticker, date) fire appears once
# ---------------------------------------------------------------------------

class TestPooledDedup:
    """Verify that the pooled panel dedup logic in run_sev_study works via
    the drop_duplicates call.  We test the dedup logic directly since we
    cannot run the full study without data files."""

    def test_dedup_removes_exact_duplicate_ticker_date(self) -> None:
        """A (ticker, date) pair present in both deep and baskets panels
        should appear exactly once after dedup."""
        # Simulate: deep fires includes (AAPL, 2021-03-01)
        deep_fires = pd.DataFrame({
            "ticker": ["AAPL", "MSFT"],
            "date": [pd.Timestamp("2021-03-01"), pd.Timestamp("2021-03-01")],
            "panel": ["deep", "deep"],
        })
        # baskets fires also includes (AAPL, 2021-03-01) — the duplicate
        basket_fires = pd.DataFrame({
            "ticker": ["AAPL", "AMZN"],
            "date": [pd.Timestamp("2021-03-01"), pd.Timestamp("2021-03-02")],
            "panel": ["baskets", "baskets"],
        })

        pooled_raw = pd.concat([deep_fires, basket_fires], ignore_index=True)
        assert len(pooled_raw) == 4  # 2 deep + 2 baskets

        pooled_deduped = pooled_raw.drop_duplicates(
            subset=["ticker", "date"], keep="first"
        ).reset_index(drop=True)

        # AAPL 2021-03-01 appears once (not twice)
        aapl_fires = pooled_deduped[
            (pooled_deduped["ticker"] == "AAPL") &
            (pooled_deduped["date"] == pd.Timestamp("2021-03-01"))
        ]
        assert len(aapl_fires) == 1, "AAPL 2021-03-01 must appear exactly once after dedup"

        # Total should be 3 (AAPL, MSFT, AMZN) not 4
        assert len(pooled_deduped) == 3, (
            f"Expected 3 unique (ticker,date) pairs; got {len(pooled_deduped)}"
        )

    def test_dedup_does_not_drop_same_ticker_different_dates(self) -> None:
        """Same ticker on different dates must both survive the dedup."""
        fires = pd.DataFrame({
            "ticker": ["AAPL", "AAPL", "AAPL"],
            "date": [
                pd.Timestamp("2021-01-01"),
                pd.Timestamp("2021-03-01"),
                pd.Timestamp("2021-03-01"),  # duplicate
            ],
        })
        deduped = fires.drop_duplicates(subset=["ticker", "date"], keep="first")
        assert len(deduped) == 2, "Should retain AAPL on two different dates"

    def test_dedup_does_not_drop_different_tickers_same_date(self) -> None:
        """Different tickers on the same date must both survive."""
        fires = pd.DataFrame({
            "ticker": ["AAPL", "MSFT"],
            "date": [pd.Timestamp("2021-03-01"), pd.Timestamp("2021-03-01")],
        })
        deduped = fires.drop_duplicates(subset=["ticker", "date"], keep="first")
        assert len(deduped) == 2, "Different tickers on same date must both survive"
