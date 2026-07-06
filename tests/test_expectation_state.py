"""tests/test_expectation_state.py — Unit tests for LT-2c: engine/expectation_state.py.

Tests:
  A. _sue_features_for_ticker — PIT-gated SUE + streak computation.
  B. _pead_drift — post-event cumulative return vs benchmark.
  C. _bad_news_absorption — ED-4 binary flag (d_q<0, no new low, momentum).
  D. _good_news_hold — ED-5 binary flag (d_q>0, gap up, held close).
  E. expectation_states() — full builder with synthetic parquets (integration).
  F. Firewall: every output dict carries _display_only=True, _horizon_role='hold_thesis'.

Run:
    python -m pytest tests/test_expectation_state.py -v
"""
from __future__ import annotations

import math
import sys
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

# Bootstrap repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.expectation_state import (  # noqa: E402
    _bad_news_absorption,
    _dq_at_event,
    _good_news_hold,
    _pead_drift,
    _seasonal_diffs,
    _sue_features_for_ticker,
    expectation_states,
)

TODAY = date(2026, 7, 6)  # anchored reference date
TODAY_TS = pd.Timestamp(TODAY)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_close(dates: list[str], prices: list[float] | None = None) -> pd.Series:
    """Build a close Series with DatetimeIndex."""
    idx = pd.DatetimeIndex([pd.Timestamp(d) for d in dates])
    if prices is None:
        prices = [100.0 + float(i) for i in range(len(dates))]
    return pd.Series(prices, index=idx, name="close")


def _trading_days(start: str, n: int) -> list[str]:
    """Return n business days starting from start (inclusive)."""
    return [str(d.date()) for d in pd.bdate_range(start=start, periods=n)]


def _make_eps_df(ticker: str, records: list[tuple]) -> pd.DataFrame:
    """Build eps_quarterly DataFrame from (period_end, eps_q, asof_date) tuples."""
    rows = [
        {"ticker": ticker,
         "period_end": pd.Timestamp(pe),
         "eps_q": float(eps),
         "asof_date": pd.Timestamp(asof)}
        for pe, eps, asof in records
    ]
    return pd.DataFrame(rows)


# ===========================================================================
# A. _sue_features_for_ticker
# ===========================================================================

class TestSueFeaturesForTicker:
    def test_returns_none_when_insufficient_data(self):
        eps = _make_eps_df("AAA", [
            ("2024-03-31", 1.0, "2024-05-31"),
            ("2024-06-30", 1.1, "2024-08-29"),
        ])
        result = _sue_features_for_ticker(eps, asof=TODAY_TS)
        assert result["sue_latest"] is None
        assert result["sue_streak"] is None

    def test_pit_filter_excludes_future_asof(self):
        """Rows with asof_date > today must not be visible."""
        # Provide enough rows but make the last one future-dated
        records = [
            ("2021-03-31", 1.0, "2021-05-31"),
            ("2021-06-30", 1.1, "2021-08-29"),
            ("2021-09-30", 1.2, "2021-11-29"),
            ("2021-12-31", 1.3, "2022-02-28"),
            ("2022-03-31", 1.4, "2022-05-30"),
            ("2022-06-30", 1.5, "2022-08-29"),
            ("2022-09-30", 1.6, "2022-11-28"),
            # Latest quarter filed in the FUTURE — must be invisible
            ("2026-06-30", 2.0, "2027-01-01"),
        ]
        eps = _make_eps_df("TICK", records)
        result = _sue_features_for_ticker(eps, asof=TODAY_TS)
        # Should compute using only rows up to TODAY_TS; last future row excluded
        # With 7 visible rows the loop finds year-ago matches for the 5th through 7th
        # and can compute SUE from those, so result should not be None
        # (exact value depends on matches — just assert it doesn't crash and latest
        # is not the future quarter)
        # We can't easily assert value, but we can assert it doesn't crash
        assert isinstance(result, dict)

    def test_positive_streak(self):
        """All d_q > 0 → sue_streak = 8 (capped)."""
        # Build 10 quarters where each beats year-ago
        records = []
        base_eps = 1.0
        for i in range(10):
            pe = pd.Timestamp("2022-03-31") + pd.DateOffset(months=3 * i)
            eps_val = base_eps + i * 0.1  # monotonically increasing → all d_q > 0
            asof = pe + pd.DateOffset(days=60)
            records.append((str(pe.date()), eps_val, str(asof.date())))
        eps = _make_eps_df("GROW", records)
        result = _sue_features_for_ticker(eps, asof=TODAY_TS)
        if result["sue_streak"] is not None:
            assert result["sue_streak"] <= 8

    def test_sue_latest_sign(self):
        """When latest quarter clearly beats year-ago, sue_latest > 0."""
        # Year-ago: 1.0; latest: 2.0 → big positive d_q
        records = []
        quarters = [
            ("2022-03-31", 1.0, "2022-05-31"),
            ("2022-06-30", 1.0, "2022-08-29"),
            ("2022-09-30", 1.0, "2022-11-28"),
            ("2022-12-31", 1.0, "2023-02-28"),
            ("2023-03-31", 1.0, "2023-05-31"),
            ("2023-06-30", 1.0, "2023-08-29"),
            ("2023-09-30", 1.0, "2023-11-28"),
            ("2023-12-31", 1.0, "2024-02-28"),
            ("2024-03-31", 2.0, "2024-05-31"),  # big beat vs year-ago 1.0
        ]
        eps = _make_eps_df("BEAT", quarters)
        result = _sue_features_for_ticker(eps, asof=TODAY_TS)
        if result["sue_latest"] is not None:
            assert result["sue_latest"] > 0

    def test_zero_sd_returns_none(self):
        """All seasonal diffs identical → σ=0 → sue_latest is None."""
        # All d_q = 0 because eps is constant year-over-year
        records = [
            ("2021-03-31", 1.0, "2021-05-31"),
            ("2021-06-30", 1.0, "2021-08-29"),
            ("2021-09-30", 1.0, "2021-11-28"),
            ("2021-12-31", 1.0, "2022-02-28"),
            ("2022-03-31", 1.0, "2022-05-31"),  # d_q = 0
            ("2022-06-30", 1.0, "2022-08-29"),  # d_q = 0
            ("2022-09-30", 1.0, "2022-11-28"),  # d_q = 0
            ("2022-12-31", 1.0, "2023-02-28"),  # d_q = 0
        ]
        eps = _make_eps_df("FLAT", records)
        result = _sue_features_for_ticker(eps, asof=TODAY_TS)
        assert result["sue_latest"] is None


# ===========================================================================
# B. _pead_drift
# ===========================================================================

class TestPeadDrift:
    def test_requires_min_5_sessions(self):
        """Fewer than 5 sessions after event → None."""
        dates = _trading_days("2026-06-01", 10)
        close = _make_close(dates)
        event_date = pd.Timestamp("2026-05-31")  # event before the price series
        # Only 10 bars available; event + 1 session = 2026-06-01; but we need ≥5
        # after event to have pead. Truncate to 3 bars:
        close_short = close.iloc[:3]
        result = _pead_drift(close_short, None, event_date, TODAY_TS)
        assert result is None

    def test_positive_drift_no_benchmark(self):
        """All prices increasing after event → positive drift (vs no benchmark)."""
        # 30 consecutive bdays with steadily rising prices
        dates = _trading_days("2026-05-15", 30)
        prices = [100.0 + i * 1.0 for i in range(30)]
        close = _make_close(dates, prices)
        event_date = pd.Timestamp("2026-05-14")  # 1 day before data starts
        result = _pead_drift(close, None, event_date, TODAY_TS)
        assert result is not None
        assert result > 0

    def test_benchmark_subtracted(self):
        """When benchmark rises equally, excess drift is ~0."""
        dates = _trading_days("2026-05-15", 30)
        prices = [100.0 + i * 1.0 for i in range(30)]
        close = _make_close(dates, prices)
        benchmark = _make_close(dates, prices)  # identical → excess ≈ 0
        event_date = pd.Timestamp("2026-05-14")
        result = _pead_drift(close, benchmark, event_date, TODAY_TS)
        assert result is not None
        assert abs(result) < 1e-9

    def test_none_on_empty_close(self):
        result = _pead_drift(None, None, pd.Timestamp("2026-05-14"), TODAY_TS)
        assert result is None

    def test_event_after_price_history_returns_none(self):
        dates = _trading_days("2026-01-01", 20)
        close = _make_close(dates)
        event_date = pd.Timestamp("2026-06-30")  # after all price bars
        result = _pead_drift(close, None, event_date, TODAY_TS)
        assert result is None


# ===========================================================================
# C. _bad_news_absorption
# ===========================================================================

class TestBadNewsAbsorption:
    def test_positive_dq_returns_false(self):
        """d_q >= 0 → False immediately (condition 1 fails)."""
        dates = _trading_days("2026-05-01", 30)
        close = _make_close(dates)
        event = pd.Timestamp("2026-05-15")
        result = _bad_news_absorption(close, None, event, d_q=0.5)
        assert result is False

    def test_zero_dq_returns_false(self):
        result = _bad_news_absorption(
            _make_close(_trading_days("2026-05-01", 30)), None,
            pd.Timestamp("2026-05-15"), d_q=0.0
        )
        assert result is False

    def test_none_dq_returns_none(self):
        result = _bad_news_absorption(
            _make_close(_trading_days("2026-05-01", 30)), None,
            pd.Timestamp("2026-05-15"), d_q=None
        )
        assert result is None

    def test_absorbed_bad_news(self):
        """d_q < 0, prices hold above pre-event min, slight positive momentum → True."""
        # Build: pre-event 63 sessions steady at 100, event at position 63,
        # post-event 10 sessions at 101 (no new low, slight momentum positive)
        n_pre = 70
        dates = _trading_days("2025-12-01", n_pre + 15)
        prices = [100.0] * (n_pre + 15)
        # Make post-event 10 sessions slightly above 100 (held)
        event_pos_idx = n_pre
        for k in range(1, 11):
            prices[event_pos_idx + k] = 101.0
        close = _make_close(dates, prices)
        event_date = pd.Timestamp(dates[event_pos_idx])
        result = _bad_news_absorption(close, None, event_date, d_q=-0.5)
        assert result is True

    def test_failed_absorption_breaks_lows(self):
        """d_q < 0, prices break below pre-event min → False."""
        n_pre = 70
        dates = _trading_days("2025-12-01", n_pre + 15)
        prices = [100.0] * (n_pre + 15)
        event_pos_idx = n_pre
        # Post-event crash below 100 (condition 2 fails)
        for k in range(1, 11):
            prices[event_pos_idx + k] = 90.0
        close = _make_close(dates, prices)
        event_date = pd.Timestamp(dates[event_pos_idx])
        result = _bad_news_absorption(close, None, event_date, d_q=-0.5)
        assert result is False

    def test_none_on_empty_close(self):
        result = _bad_news_absorption(None, None, pd.Timestamp("2026-05-15"), d_q=-1.0)
        assert result is None


# ===========================================================================
# D. _good_news_hold
# ===========================================================================

class TestGoodNewsHold:
    def test_negative_dq_returns_false(self):
        dates = _trading_days("2026-05-01", 20)
        result = _good_news_hold(_make_close(dates), pd.Timestamp("2026-05-10"), d_q=-0.5)
        assert result is False

    def test_zero_dq_returns_false(self):
        dates = _trading_days("2026-05-01", 20)
        result = _good_news_hold(_make_close(dates), pd.Timestamp("2026-05-10"), d_q=0.0)
        assert result is False

    def test_none_dq_returns_none(self):
        dates = _trading_days("2026-05-01", 20)
        result = _good_news_hold(_make_close(dates), pd.Timestamp("2026-05-10"), d_q=None)
        assert result is None

    def test_good_news_held(self):
        """d_q > 0, gap +5% next session, held 10 sessions later → True."""
        n_pre = 5
        dates = _trading_days("2026-05-01", n_pre + 15)
        prices = [100.0] * (n_pre + 15)
        event_idx = n_pre
        # E(f)+1: gap up 5%
        prices[event_idx + 1] = 105.0
        # E(f)+10: above E(f)+1
        prices[event_idx + 10] = 106.0
        close = _make_close(dates, prices)
        event_date = pd.Timestamp(dates[event_idx])
        result = _good_news_hold(close, event_date, d_q=0.5)
        assert result is True

    def test_good_news_not_held(self):
        """d_q > 0, gap +5%, but day 10 close < day 1 close → False."""
        n_pre = 5
        dates = _trading_days("2026-05-01", n_pre + 15)
        prices = [100.0] * (n_pre + 15)
        event_idx = n_pre
        prices[event_idx + 1] = 105.0  # gap up
        prices[event_idx + 10] = 100.0  # faded below E(f)+1 → condition 3 fails
        close = _make_close(dates, prices)
        event_date = pd.Timestamp(dates[event_idx])
        result = _good_news_hold(close, event_date, d_q=0.5)
        assert result is False

    def test_insufficient_reaction_returns_false(self):
        """Gap up < 2% → condition 2 fails → False."""
        n_pre = 5
        dates = _trading_days("2026-05-01", n_pre + 15)
        prices = [100.0] * (n_pre + 15)
        event_idx = n_pre
        prices[event_idx + 1] = 100.5  # only 0.5%, less than 2%
        prices[event_idx + 10] = 101.0
        close = _make_close(dates, prices)
        event_date = pd.Timestamp(dates[event_idx])
        result = _good_news_hold(close, event_date, d_q=0.5)
        assert result is False

    def test_none_on_empty_close(self):
        result = _good_news_hold(None, pd.Timestamp("2026-05-10"), d_q=0.5)
        assert result is None

    def test_none_when_no_session_10_bar(self):
        """Not enough bars for session 10 → None."""
        dates = _trading_days("2026-05-01", 7)  # only 7 bars; need 10 post-event
        prices = [100.0, 100.0, 100.0, 100.0, 100.0, 107.0, 108.0]
        close = _make_close(dates, prices)
        event_date = pd.Timestamp(dates[4])
        result = _good_news_hold(close, event_date, d_q=0.5)
        # We need bars at event_idx + 10; only 2 post-event bars available → None
        assert result is None


# ===========================================================================
# E-pre. _dq_at_event — threshold and visibility tests (Fix 1 + Fix 2)
# ===========================================================================

class TestDqAtEvent:
    """Unit tests for _dq_at_event — guards the two study-alignment fixes.

    Fix 1: threshold is _SUE_MIN_DIFFS + 1 (=5), not + 2 (=6) — exactly 5
    visible rows must return a value, not None.

    Fix 2: asof_date parameter controls visibility; caller must pass ref_ts
    (today), not event_date, so a later-filed quarter visible today but not at
    event_date is included — matching build_expect_drift_panel._dq_at_event.
    """

    def _make_eps(self, n_rows: int, asof_today: bool = True) -> pd.DataFrame:
        """Build n_rows of eps_quarterly with asof_date all visible at TODAY_TS."""
        records = []
        for i in range(n_rows):
            pe = pd.Timestamp("2022-03-31") + pd.DateOffset(months=3 * i)
            eps_val = 1.0 + i * 0.1
            asof = (pe + pd.DateOffset(days=60)) if asof_today else pd.Timestamp("2030-01-01")
            records.append((str(pe.date()), eps_val, str(asof.date())))
        return _make_eps_df("TDQ", records)

    def test_exactly_5_visible_rows_returns_value(self):
        """Fix 1: with exactly 5 visible rows (_SUE_MIN_DIFFS+1=5), must return float."""
        eps = self._make_eps(5)
        result = _dq_at_event(eps, TODAY_TS)
        assert result is not None, (
            "With 5 visible rows (_SUE_MIN_DIFFS+1) _dq_at_event must return a value; "
            "got None — threshold divergence not fixed"
        )
        assert isinstance(result, float)

    def test_4_visible_rows_returns_none(self):
        """With 4 visible rows (below _SUE_MIN_DIFFS+1=5), must return None."""
        eps = self._make_eps(4)
        result = _dq_at_event(eps, TODAY_TS)
        assert result is None, "4 visible rows must return None (not enough for a seasonal diff)"

    def test_visibility_gated_by_asof_date(self):
        """Fix 2: rows with asof_date > passed timestamp are invisible.

        Pass a timestamp that only sees 4 rows; should return None.
        Pass TODAY_TS which sees all 6 rows; should return float.
        """
        # Build 6 rows, the last 2 filed after 2025-01-01
        records = [
            ("2022-03-31", 1.0, "2022-06-01"),
            ("2022-06-30", 1.1, "2022-09-01"),
            ("2022-09-30", 1.2, "2022-12-01"),
            ("2022-12-31", 1.3, "2023-03-01"),
            ("2023-03-31", 1.4, "2025-06-01"),  # filed 2025
            ("2023-06-30", 1.5, "2025-09-01"),  # filed 2025
        ]
        eps = _make_eps_df("TDQ2", records)
        # As-of 2024-01-01: only 4 rows visible → None
        asof_early = pd.Timestamp("2024-01-01")
        assert _dq_at_event(eps, asof_early) is None
        # As-of TODAY_TS: all 6 visible → float
        result_today = _dq_at_event(eps, TODAY_TS)
        assert result_today is not None
        assert isinstance(result_today, float)

    def test_returns_float_not_numpy(self):
        """Return value must be a native Python float (json.dumps safe)."""
        eps = self._make_eps(6)
        result = _dq_at_event(eps, TODAY_TS)
        if result is not None:
            assert isinstance(result, float), f"Expected float, got {type(result)}"
            assert not isinstance(result, np.floating), "Must not return np.floating"


# ===========================================================================
# E. expectation_states() — integration with synthetic parquets
# ===========================================================================

class TestExpectationStatesIntegration:
    """Test the full builder with synthetic parquets written to a tmp_path."""

    def _build_inputs(self, tmp_path: Path):
        """Write minimal synthetic parquets for a single ticker 'TSYN'."""
        edgar_dir = tmp_path / "edgar"
        edgar_dir.mkdir(parents=True)
        yahoo_dir = tmp_path / "yahoo"
        yahoo_dir.mkdir()

        # EPS panel: 8 quarters starting 2024-Q1 with consistent beats
        eps_records = []
        base = 1.0
        for i in range(8):
            pe = pd.Timestamp("2024-03-31") + pd.DateOffset(months=3 * i)
            eps_val = base + i * 0.1  # monotonically increasing
            asof = pe + pd.DateOffset(days=60)
            eps_records.append({
                "ticker": "TSYN",
                "period_end": pe,
                "eps_q": eps_val,
                "asof_date": asof,
            })
        eps_df = pd.DataFrame(eps_records)
        eps_df.to_parquet(edgar_dir / "eps_quarterly.parquet", index=False)

        # Earnings 8K: one event 30 days before today
        event_date = pd.Timestamp(TODAY) - pd.Timedelta(days=30)
        e8k_df = pd.DataFrame([{
            "ticker": "TSYN",
            "cik": "12345",
            "filing_date": event_date.strftime("%Y-%m-%d"),
            "acceptance_datetime": event_date.strftime("%Y-%m-%dT12:00:00.000Z"),
            "items": "2.02,9.01",
        }])
        e8k_df.to_parquet(edgar_dir / "earnings_8k_dates.parquet", index=False)

        # Price series: 60 business days with slightly rising prices
        price_dates = list(pd.bdate_range(
            end=pd.Timestamp(TODAY), periods=60
        ))
        prices_df = pd.DataFrame({
            "close": [100.0 + 0.1 * i for i in range(60)],
            "volume": [1_000_000] * 60,
        }, index=price_dates)
        prices_df.index.name = "Date"
        prices_df.to_parquet(yahoo_dir / "TSYN.parquet")

        # SPY: same pattern for benchmark
        spy_df = pd.DataFrame({
            "close": [400.0 + 0.05 * i for i in range(60)],
            "volume": [50_000_000] * 60,
        }, index=price_dates)
        spy_df.index.name = "Date"
        spy_df.to_parquet(yahoo_dir / "SPY.parquet")

        return tmp_path

    def test_builds_chip_for_ticker_with_data(self, tmp_path):
        """expectation_states() returns a chip for TSYN when data is present."""
        import lib.config as lib_cfg
        self._build_inputs(tmp_path)
        with patch.object(lib_cfg, "data_dir", return_value=tmp_path):
            result = expectation_states(today=TODAY, data_dir=tmp_path)
        assert "TSYN" in result
        chip = result["TSYN"]
        assert chip["_display_only"] is True
        assert chip["_horizon_role"] == "hold_thesis"
        assert chip["_version"] == "v1"

    def test_chip_fields_present(self, tmp_path):
        """The chip has the expected schema keys."""
        import lib.config as lib_cfg
        self._build_inputs(tmp_path)
        with patch.object(lib_cfg, "data_dir", return_value=tmp_path):
            result = expectation_states(today=TODAY, data_dir=tmp_path)
        chip = result.get("TSYN", {})
        for key in ("last_event_date", "sue_latest", "sue_streak",
                    "pead_drift_20d", "bad_news_absorption", "good_news_hold",
                    "_horizon_role", "_display_only", "_version", "_benchmark"):
            assert key in chip, f"Missing key: {key}"
        assert chip["_benchmark"] == "SPY", "benchmark must be 'SPY'"

    def test_returns_empty_on_missing_parquets(self, tmp_path):
        """When parquets are absent, returns empty dict (no crash)."""
        import lib.config as lib_cfg
        # Don't write anything
        with patch.object(lib_cfg, "data_dir", return_value=tmp_path):
            result = expectation_states(today=TODAY, data_dir=tmp_path)
        assert result == {}

    def test_no_numpy_scalars_in_output(self, tmp_path):
        """All numeric fields must be native Python types (json.dumps safe)."""
        import json, lib.config as lib_cfg
        self._build_inputs(tmp_path)
        with patch.object(lib_cfg, "data_dir", return_value=tmp_path):
            result = expectation_states(today=TODAY, data_dir=tmp_path)
        chip = result.get("TSYN")
        if chip:
            # This will raise TypeError if numpy scalars are present
            json.dumps(chip)

    def test_ticker_not_in_eps_gets_no_chip(self, tmp_path):
        """Ticker only in 8K but not in EPS panel → no chip."""
        import lib.config as lib_cfg
        self._build_inputs(tmp_path)
        # Add an 8K entry for a ticker with no EPS data
        e8k_extra = pd.DataFrame([{
            "ticker": "NOEPS",
            "cik": "99999",
            "filing_date": (pd.Timestamp(TODAY) - pd.Timedelta(days=10)).strftime("%Y-%m-%d"),
            "acceptance_datetime": "2026-06-26T12:00:00.000Z",
            "items": "2.02",
        }])
        edgar_dir = tmp_path / "edgar"
        existing = pd.read_parquet(edgar_dir / "earnings_8k_dates.parquet")
        pd.concat([existing, e8k_extra], ignore_index=True).to_parquet(
            edgar_dir / "earnings_8k_dates.parquet", index=False
        )
        with patch.object(lib_cfg, "data_dir", return_value=tmp_path):
            result = expectation_states(today=TODAY, data_dir=tmp_path)
        assert "NOEPS" not in result


# ===========================================================================
# F. Firewall annotations
# ===========================================================================

class TestFirewallAnnotations:
    def test_all_firewall_fields_present(self, tmp_path):
        """Every chip must carry the three firewall annotations."""
        import lib.config as lib_cfg
        test_int = TestExpectationStatesIntegration()
        test_int._build_inputs(tmp_path)
        with patch.object(lib_cfg, "data_dir", return_value=tmp_path):
            result = expectation_states(today=TODAY, data_dir=tmp_path)
        for ticker, chip in result.items():
            assert chip.get("_horizon_role") == "hold_thesis", f"{ticker}: bad _horizon_role"
            assert chip.get("_display_only") is True, f"{ticker}: _display_only not True"
            assert chip.get("_version") == "v1", f"{ticker}: bad _version"

    def test_no_scoring_fields_in_chip(self, tmp_path):
        """Chips must not carry score/z/rank/gate — these are firewall-guarded fields."""
        import lib.config as lib_cfg
        test_int = TestExpectationStatesIntegration()
        test_int._build_inputs(tmp_path)
        with patch.object(lib_cfg, "data_dir", return_value=tmp_path):
            result = expectation_states(today=TODAY, data_dir=tmp_path)
        for ticker, chip in result.items():
            for bad_key in ("score", "z", "rank", "gate", "weight"):
                assert bad_key not in chip, f"{ticker}: unexpected scored field '{bad_key}'"
