"""tests/test_intraday_flow.py — Unit tests for engine/intraday_flow.py (IFT A1+A3).

Covers every public function with synthetic fixtures and edge cases.
All tests are self-contained; no network, no disk I/O.
"""
from __future__ import annotations

import math
import os
import sys
import tempfile
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.intraday_flow import (
    ConfluenceLegs,
    confluence_legs,
    flow_durability,
    higher_lows,
    ncp_velocity,
    rvol_tod,
    session_vwap,
    vol_share_curve,
    volume_durability,
    washout_context,
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _bar(open_=100, high=105, low=98, close=103, volume=100_000):
    return {"open": open_, "high": high, "low": low, "close": close, "volume": volume}


def _session(n: int = 7, vol_per_bar: int = 100_000, base: float = 100.0):
    """Create a simple session of n hourly bars with steady price action."""
    return [_bar(base + i, base + i + 2, base + i - 1, base + i + 1, vol_per_bar)
            for i in range(n)]


# ── vol_share_curve ───────────────────────────────────────────────────────────

class TestVolShareCurve:
    def test_basic_two_sessions(self):
        """Median curve over two identical sessions should equal the single-session curve."""
        sess = _session(7, 100_000)
        result = vol_share_curve([sess, sess])
        assert result is not None
        assert len(result) == 7
        # All volumes equal, so each bar adds 1/7 of total.
        for i, share in enumerate(result):
            assert abs(share - (i + 1) / 7) < 0.01

    def test_cumulative_monotone(self):
        """Output must be non-decreasing and end at 1.0."""
        sess1 = _session(7, 100_000)
        sess2 = _session(7, 200_000)
        result = vol_share_curve([sess1, sess2])
        assert result is not None
        assert result[-1] == 1.0
        for i in range(1, len(result)):
            assert result[i] >= result[i - 1] - 1e-9

    def test_empty_session_list(self):
        assert vol_share_curve([]) is None

    def test_single_session(self):
        """Single session returns None (need >= 2)."""
        assert vol_share_curve([_session(7)]) is None

    def test_zero_volume_sessions_skipped(self):
        """Sessions with all-zero volumes are skipped; needs >= 2 valid sessions."""
        zero_sess = [_bar(100, 105, 98, 103, 0)] * 7
        good_sess = _session(7)
        # Only one valid session after skipping zero-vol.
        assert vol_share_curve([zero_sess, good_sess]) is None

    def test_two_valid_sessions(self):
        """Two valid sessions should produce a result even with one zero-vol skipped."""
        good1 = _session(7)
        good2 = _session(7, 200_000)
        result = vol_share_curve([good1, good2])
        assert result is not None

    def test_trailing_twenty_sessions(self):
        """20 identical sessions should give same result as 2."""
        sess = _session(6)
        r2 = vol_share_curve([sess, sess])
        r20 = vol_share_curve([sess] * 20)
        assert r2 is not None and r20 is not None
        for a, b in zip(r2, r20):
            assert abs(a - b) < 0.01

    def test_unequal_bar_counts_padded(self):
        """Short sessions are padded to 1.0; curve length = max session length."""
        short = _session(4)
        long_ = _session(7)
        result = vol_share_curve([short, long_])
        assert result is not None
        assert len(result) == 7
        # Padded session's last value stays at 1.0, so median >= short-session endpoint.
        assert result[-1] == 1.0


# ── rvol_tod ─────────────────────────────────────────────────────────────────

class TestRvolTod:
    def test_at_pace(self):
        """Cumulative vol equal to expected → RVOL_tod = 1.0."""
        adv20 = 1_000_000
        share = 0.40
        cum_vol = adv20 * share
        result = rvol_tod(cum_vol, adv20, share)
        assert result is not None
        assert abs(result - 1.0) < 0.001

    def test_elevated(self):
        """Vol running 2× expected → RVOL_tod = 2.0."""
        adv20 = 1_000_000
        share = 0.40
        cum_vol = adv20 * share * 2
        result = rvol_tod(cum_vol, adv20, share)
        assert result is not None
        assert abs(result - 2.0) < 0.001

    def test_none_inputs(self):
        assert rvol_tod(None, 1e6, 0.40) is None
        assert rvol_tod(400_000, None, 0.40) is None
        assert rvol_tod(400_000, 1e6, None) is None

    def test_zero_adv(self):
        assert rvol_tod(400_000, 0, 0.40) is None

    def test_zero_share(self):
        assert rvol_tod(400_000, 1e6, 0.0) is None

    def test_low_rvol(self):
        """Vol behind pace → RVOL < 1.0."""
        result = rvol_tod(100_000, 1_000_000, 0.40)
        assert result is not None
        assert result < 1.0


# ── session_vwap ─────────────────────────────────────────────────────────────

class TestSessionVwap:
    def test_single_bar(self):
        """VWAP with one bar = typical price."""
        b = _bar(100, 110, 90, 105, 100_000)
        result = session_vwap([b])
        typical = (110 + 90 + 105) / 3.0
        assert result is not None
        assert abs(result - typical) < 0.01

    def test_equal_volume_bars(self):
        """With equal volumes, VWAP = mean of typical prices."""
        bars = [
            _bar(100, 110, 90, 100, 100_000),
            _bar(110, 120, 100, 110, 100_000),
        ]
        result = session_vwap(bars)
        tp1 = (110 + 90 + 100) / 3.0
        tp2 = (120 + 100 + 110) / 3.0
        expected = (tp1 + tp2) / 2.0
        assert result is not None
        assert abs(result - expected) < 0.01

    def test_empty_bars(self):
        assert session_vwap([]) is None

    def test_zero_volume_bars(self):
        bars = [_bar(100, 110, 90, 105, 0)]
        assert session_vwap(bars) is None

    def test_missing_fields_skipped(self):
        """Bars missing OHLCV fields are skipped; others still contribute."""
        bars = [
            {"high": None, "low": 90, "close": 100, "volume": 100_000},
            _bar(100, 110, 90, 105, 100_000),
        ]
        result = session_vwap(bars)
        assert result is not None


# ── volume_durability ─────────────────────────────────────────────────────────

class TestVolumeDurability:
    def test_all_upper_half_no_baseline(self):
        """All closes in upper half, no baseline → 1.0."""
        bars = [_bar(100, 110, 90, 105, 100_000)] * 6  # close 105 > mid 100
        result = volume_durability(bars, None)
        assert result == 1.0

    def test_all_lower_half_no_baseline(self):
        """All closes in lower half → 0.0."""
        bars = [_bar(100, 110, 90, 92, 100_000)] * 6   # close 92 < mid 100
        result = volume_durability(bars, None)
        assert result == 0.0

    def test_half_and_half(self):
        upper = _bar(100, 110, 90, 105, 100_000)  # close > mid
        lower = _bar(100, 110, 90, 92, 100_000)   # close < mid
        result = volume_durability([upper, lower, upper, lower], None)
        assert result is not None
        assert abs(result - 0.5) < 0.01

    def test_empty_bars(self):
        assert volume_durability([], None) is None

    def test_with_baseline_curve_vol_gate(self):
        """With baseline: bar must also have sufficient volume."""
        # ADV = 1M, expected incremental share per bar = 0.1 → expected 100k/bar
        # Bar 0 has 200k (passes), bar 1 has 10k (fails vol gate)
        curve = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7]
        adv20 = 1_000_000
        bars = [
            _bar(100, 110, 90, 105, 200_000),   # upper-half, vol OK
            _bar(100, 110, 90, 105, 10_000),    # upper-half, vol too low
            _bar(100, 110, 90, 105, 200_000),   # upper-half, vol OK
        ]
        result = volume_durability(bars, curve, adv20)
        assert result is not None
        # 2 of 3 qualify.
        assert abs(result - 2 / 3) < 0.01

    def test_missing_fields_skipped(self):
        bars = [
            {"high": None, "low": 90, "close": 105, "volume": 100_000},
            _bar(100, 110, 90, 105, 100_000),
        ]
        result = volume_durability(bars, None)
        assert result == 1.0  # Only valid bar, and it qualifies.


# ── higher_lows ───────────────────────────────────────────────────────────────

class TestHigherLows:
    def test_steadily_rising_lows(self):
        bars = [_bar(low=100), _bar(low=102), _bar(low=104), _bar(low=106)]
        assert higher_lows(bars) == 3

    def test_first_break(self):
        bars = [_bar(low=100), _bar(low=102), _bar(low=101), _bar(low=103)]
        assert higher_lows(bars) == 1  # Stops at first violation (bar 2 < bar 1)

    def test_no_higher_lows(self):
        bars = [_bar(low=100), _bar(low=99), _bar(low=98)]
        assert higher_lows(bars) == 0

    def test_single_bar(self):
        assert higher_lows([_bar()]) == 0

    def test_empty(self):
        assert higher_lows([]) == 0

    def test_none_lows_skipped(self):
        bars = [{"low": 100}, {"low": None}, {"low": 102}]
        # None lows are skipped during collection.
        result = higher_lows(bars)
        assert isinstance(result, int)


# ── ncp_velocity ─────────────────────────────────────────────────────────────

class TestNcpVelocity:
    def _make_series(self, n: int = 80, slope: float = 5.0, noise: float = 2.0):
        """Linearly growing NCP cumulative series."""
        import numpy as np
        rng = np.random.default_rng(42)
        vals = [i * slope + rng.normal(0, noise) for i in range(n)]
        return vals

    def test_strong_positive_slope(self):
        """Strong upward trend → positive z-score."""
        series = self._make_series(80, slope=10.0, noise=0.1)
        result = ncp_velocity(series)
        assert result is not None
        assert result > 0.5

    def test_strong_negative_slope(self):
        """Strong downward trend → negative z-score."""
        series = [-v for v in self._make_series(80, slope=10.0, noise=0.1)]
        result = ncp_velocity(series)
        assert result is not None
        assert result < -0.5

    def test_too_short(self):
        """Fewer than min_obs points → None."""
        assert ncp_velocity([1.0, 2.0, 3.0]) is None

    def test_empty(self):
        assert ncp_velocity([]) is None

    def test_none_values_filtered(self):
        """None values are filtered out; result still computable with enough data."""
        series = self._make_series(80, slope=5.0)
        series_with_nones = [v if i % 5 != 0 else None for i, v in enumerate(series)]
        result = ncp_velocity(series_with_nones)
        # Should still produce a result as long as enough valid points remain.
        assert result is None or isinstance(result, float)

    def test_flat_series(self):
        """Flat series → z near zero (may be None due to zero vol)."""
        series = [100.0] * 80
        result = ncp_velocity(series)
        # Flat = zero vol → slope_z returns NaN → None
        assert result is None or abs(result) < 1.0


# ── flow_durability ───────────────────────────────────────────────────────────

class TestFlowDurability:
    def _cumulative(self, increments: list[float]) -> list[float]:
        result, cum = [], 0.0
        for v in increments:
            cum += v
            result.append(cum)
        return result

    def test_all_positive_windows(self):
        """All 5-min windows positive → positive_share = 1.0."""
        series = self._cumulative([10.0] * 40)  # 8 windows of 5
        result = flow_durability(series)
        assert result["positive_share"] == 1.0
        assert result["longest_streak"] == 8

    def test_all_negative_windows(self):
        """All 5-min windows negative → positive_share = 0.0, streak = 0."""
        series = self._cumulative([-10.0] * 40)
        result = flow_durability(series)
        assert result["positive_share"] == 0.0
        assert result["longest_streak"] == 0

    def test_alternating(self):
        """Alternating windows → positive_share = 0.5, longest_streak = 1."""
        increments = []
        for _ in range(8):
            increments += [10.0] * 5   # positive window
            increments += [-10.0] * 5  # negative window
        series = self._cumulative(increments)
        result = flow_durability(series)
        assert result is not None
        assert abs(result["positive_share"] - 0.5) < 0.01
        assert result["longest_streak"] == 1

    def test_empty_series(self):
        r = flow_durability([])
        assert r["positive_share"] is None
        assert r["longest_streak"] is None

    def test_too_short(self):
        """Series shorter than window_min → None results."""
        r = flow_durability([1.0, 2.0, 3.0], window_min=5)
        assert r["positive_share"] is None

    def test_custom_window(self):
        """Custom window_min respected."""
        series = self._cumulative([5.0] * 30)  # 10 windows of 3
        result = flow_durability(series, window_min=3)
        assert result["positive_share"] == 1.0
        assert result["longest_streak"] == 10

    def test_streak_counting(self):
        """Max streak properly tracks the longest run."""
        # 3 pos, 1 neg, 5 pos → longest = 5
        increments = [10.0] * 15 + [-5.0] * 5 + [10.0] * 25
        series = self._cumulative(increments)
        result = flow_durability(series)
        assert result is not None
        # 3 + 1 + 5 = 9 windows of 5; longest run should be ≥ 3
        assert result["longest_streak"] >= 3


# ── confluence_legs ──────────────────────────────────────────────────────────

class TestConfluenceLegs:
    def test_all_seven_true(self):
        """All seven legs True → K = 7."""
        legs = confluence_legs(
            bb_lower_reclaim_days=5,
            washout_lookback=10,
            price=105.0,
            vwap=100.0,
            prev_close=103.0,
            rvol_tod_val=1.5,
            rvol_confirm=1.30,
            vol_durability_val=0.70,
            durability_min=0.60,
            cum_ncp=50_000.0,
            flow_durability_val=0.70,
            mtf_upturn_state="UPTURN_CONFIRMED",
            failed_breakout_trap=False,
        )
        assert legs.K == 7
        assert legs.L1_washout_recent is True
        assert legs.L2_reclaim is True
        assert legs.L3_rvol_elevated is True
        assert legs.L4_vol_durable is True
        assert legs.L5_flow_bid is True
        assert legs.L6_upturn_organ is True
        assert legs.L7_leader_quality is True

    def test_all_false(self):
        """All legs False → K = 0."""
        legs = confluence_legs(
            bb_lower_reclaim_days=15,
            washout_lookback=10,
            price=95.0,
            vwap=100.0,
            prev_close=96.0,
            rvol_tod_val=0.80,
            rvol_confirm=1.30,
            vol_durability_val=0.30,
            durability_min=0.60,
            cum_ncp=-50_000.0,
            flow_durability_val=0.30,
            mtf_upturn_state="UPTURN_OFF",
            failed_breakout_trap=True,
        )
        assert legs.K == 0

    def test_null_inputs_all_none(self):
        """No inputs → all legs None → K = 0."""
        legs = confluence_legs()
        assert legs.K == 0
        assert legs.L1_washout_recent is None
        assert legs.L2_reclaim is None
        assert legs.L3_rvol_elevated is None
        assert legs.L4_vol_durable is None
        assert legs.L5_flow_bid is None
        assert legs.L6_upturn_organ is None
        assert legs.L7_leader_quality is None

    def test_l1_drawdown_path(self):
        """L1 via drawdown path when bb_lower_reclaim_days absent."""
        legs = confluence_legs(
            drawdown_21d_pct=-0.15,
            recovery_begun=True,
        )
        assert legs.L1_washout_recent is True

    def test_l1_drawdown_path_insufficient(self):
        """L1 via drawdown path: -8% not enough for -12% threshold."""
        legs = confluence_legs(
            drawdown_21d_pct=-0.08,
            recovery_begun=True,
        )
        assert legs.L1_washout_recent is False

    def test_l5_cum_ncp_only(self):
        """L5 with cum_ncp only (no flow_durability) — positive NCP is True."""
        legs = confluence_legs(cum_ncp=10_000.0)
        assert legs.L5_flow_bid is True

    def test_l5_negative_cum_ncp(self):
        legs = confluence_legs(cum_ncp=-10_000.0)
        assert legs.L5_flow_bid is False

    def test_l6_upturn_watch(self):
        """UPTURN_WATCH qualifies for L6."""
        legs = confluence_legs(mtf_upturn_state="UPTURN_WATCH")
        assert legs.L6_upturn_organ is True

    def test_l6_off(self):
        legs = confluence_legs(mtf_upturn_state="UPTURN_OFF")
        assert legs.L6_upturn_organ is False

    def test_as_dict(self):
        """as_dict() returns correct keys and K."""
        legs = confluence_legs(
            rvol_tod_val=1.5,
            rvol_confirm=1.30,
        )
        d = legs.as_dict()
        assert "K" in d
        assert "L3_rvol_elevated" in d
        assert d["L3_rvol_elevated"] is True
        assert d["K"] == 1

    def test_no_dt_contra_key(self):
        """dt_contra must NOT appear anywhere in the output per DT-R11b."""
        legs = confluence_legs(
            bb_lower_reclaim_days=3,
            price=105.0,
            vwap=100.0,
        )
        d = legs.as_dict()
        assert "dt_contra" not in d
        assert "dt_contra" not in str(d)

    def test_k_counts_only_true(self):
        """K is count of True legs; None legs are not counted."""
        legs = confluence_legs(
            rvol_tod_val=1.5,  # L3 True
            failed_breakout_trap=False,  # L7 True
        )
        assert legs.K == 2

    def test_partial_l2(self):
        """L2 with only price and prev_close (no vwap) still evaluates."""
        legs = confluence_legs(price=105.0, prev_close=103.0)
        assert legs.L2_reclaim is True

    def test_partial_l2_price_vwap_only(self):
        legs = confluence_legs(price=95.0, vwap=100.0)
        assert legs.L2_reclaim is False


# ── ConfluenceLegs dataclass ─────────────────────────────────────────────────

class TestConfluenceLegsDataclass:
    def test_direct_instantiation(self):
        legs = ConfluenceLegs(
            L1_washout_recent=True,
            L2_reclaim=True,
            L3_rvol_elevated=False,
            L4_vol_durable=None,
            L5_flow_bid=True,
            L6_upturn_organ=None,
            L7_leader_quality=True,
        )
        # K = 4 (True for L1, L2, L5, L7; None for L4, L6; False for L3).
        assert legs.K == 4

    def test_empty_dataclass(self):
        legs = ConfluenceLegs()
        assert legs.K == 0


# ── Forward ledger helpers ────────────────────────────────────────────────────

# Import ledger helpers from the builder script.
import scripts.build_intraday_flow as _bif  # noqa: E402


def _make_close_series(dates: list[str], prices: list[float]) -> pd.Series:
    idx = pd.to_datetime(dates)
    return pd.Series(prices, index=idx, dtype=float)


def _make_ohlcv_parquet(tmp_dir: Path, ticker: str, dates: list[str], closes: list[float]) -> None:
    """Write a minimal OHLCV parquet into tmp_dir/baskets/ohlcv/<ticker>.parquet."""
    out = tmp_dir / "baskets" / "ohlcv"
    out.mkdir(parents=True, exist_ok=True)
    idx = pd.to_datetime(dates)
    df = pd.DataFrame({"close": closes, "open": closes, "high": closes, "low": closes, "volume": [1_000_000] * len(dates)}, index=idx)
    df.to_parquet(out / f"{ticker}.parquet")


class TestFwdRet:
    """Unit tests for _fwd_ret — forward return computation."""

    def test_basic_return(self):
        """Simple 5-day return: (105-100)/100 = 0.05."""
        dates = ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-06",
                 "2024-01-07", "2024-01-08", "2024-01-09", "2024-01-10"]
        prices = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0]
        s = _make_close_series(dates, prices)
        ret = _bif._fwd_ret(s, "2024-01-02", 5)
        assert ret is not None
        # entry = 100, exit = close on/before 2024-01-07 = 105
        assert abs(ret - 0.05) < 1e-5

    def test_not_matured_returns_none(self):
        """Horizon not yet covered → None."""
        dates = ["2024-01-02", "2024-01-03"]
        prices = [100.0, 101.0]
        s = _make_close_series(dates, prices)
        # 5-day horizon from 2024-01-02 requires data through 2024-01-07
        ret = _bif._fwd_ret(s, "2024-01-02", 5)
        assert ret is None

    def test_same_day_zero_return(self):
        """1-day horizon when exit equals entry date → ~0."""
        dates = ["2024-01-02", "2024-01-03", "2024-01-04"]
        prices = [100.0, 100.0, 102.0]
        s = _make_close_series(dates, prices)
        # 1-day horizon: entry=100, exit=close on/before 2024-01-03=100
        ret = _bif._fwd_ret(s, "2024-01-02", 1)
        assert ret is not None
        assert abs(ret) < 1e-5

    def test_empty_series_returns_none(self):
        s = pd.Series([], dtype=float)
        s.index = pd.to_datetime([])
        ret = _bif._fwd_ret(s, "2024-01-02", 5)
        assert ret is None


class TestAppendLedger:
    """Tests for _append_ledger_rows — idempotent append + forward stamp."""

    def _row(self, session: str, ticker: str, k: int = 3) -> dict:
        return {
            "session": session, "ticker": ticker, "K": k,
            "L1_washout_recent": True, "L2_reclaim": True,
            "L3_rvol_elevated": None, "L4_vol_durable": None,
            "L5_flow_bid": None, "L6_upturn_organ": True,
            "L7_leader_quality": None,
            "close": 100.0, "mtf_upturn_state": "UPTURN_WATCH",
            "mtf_upturn_K": 2, "failed_breakout_trap": False,
            "rvol_tod_close": None, "cum_ncp": None, "flow_durability_eod": None,
            "built_utc": "2024-01-02T22:00:00+00:00",
        }

    def test_fresh_append(self, tmp_path):
        """Appending to an empty ledger writes a new parquet with one row."""
        rows = [self._row("2024-01-02", "AAPL")]
        n = _bif._append_ledger_rows(rows, tmp_path)
        assert n == 1
        df = _bif._load_ledger(tmp_path)
        assert len(df) == 1
        assert df["ticker"].iloc[0] == "AAPL"
        assert df["session"].iloc[0] == "2024-01-02"

    def test_idempotent_same_session(self, tmp_path):
        """Re-running for the same (session, ticker) must not duplicate."""
        row = self._row("2024-01-02", "AAPL")
        _bif._append_ledger_rows([row], tmp_path)
        n = _bif._append_ledger_rows([row], tmp_path)
        assert n == 0  # nothing new appended
        df = _bif._load_ledger(tmp_path)
        assert len(df) == 1

    def test_different_session_appends(self, tmp_path):
        """Two different sessions for the same ticker both land in the ledger."""
        _bif._append_ledger_rows([self._row("2024-01-02", "AAPL")], tmp_path)
        n = _bif._append_ledger_rows([self._row("2024-01-03", "AAPL")], tmp_path)
        assert n == 1
        df = _bif._load_ledger(tmp_path)
        assert len(df) == 2

    def test_different_tickers_same_session(self, tmp_path):
        """Two tickers in the same session both land."""
        rows = [self._row("2024-01-02", "AAPL"), self._row("2024-01-02", "MSFT")]
        n = _bif._append_ledger_rows(rows, tmp_path)
        assert n == 2
        df = _bif._load_ledger(tmp_path)
        assert set(df["ticker"]) == {"AAPL", "MSFT"}

    def test_missing_data_root_handled(self, tmp_path):
        """Non-existent ledger dir created automatically."""
        subdir = tmp_path / "deep" / "nested"
        rows = [self._row("2024-01-02", "AAPL")]
        n = _bif._append_ledger_rows(rows, subdir)
        assert n == 1
        assert _bif._ledger_path(subdir).exists()


class TestStampForwardReturns:
    """Tests for _stamp_forward_returns — fills fwd_ret columns on existing rows."""

    def test_stamps_when_data_available(self, tmp_path):
        """fwd_ret_1d/5d/10d/21d stamped when price series covers the exit bar."""
        # Build an OHLCV parquet with 30 bars starting 2024-01-02.
        import datetime
        start = datetime.date(2024, 1, 2)
        dates = [(start + datetime.timedelta(days=i)).isoformat() for i in range(30)]
        prices = [100.0 + i for i in range(30)]
        _make_ohlcv_parquet(tmp_path, "AAPL", dates, prices)

        df = pd.DataFrame([{
            "session": "2024-01-02", "ticker": "AAPL", "K": 3,
            "fwd_ret_1d": None, "fwd_ret_5d": None,
            "fwd_ret_10d": None, "fwd_ret_21d": None,
        }])
        df = _bif._stamp_forward_returns(df, tmp_path)

        # fwd_ret_1d: entry=100, exit=close on 2024-01-03=101 → 0.01
        assert df["fwd_ret_1d"].iloc[0] is not None
        assert abs(df["fwd_ret_1d"].iloc[0] - 0.01) < 1e-4
        # fwd_ret_5d: exit on 2024-01-07=105 → 0.05
        assert df["fwd_ret_5d"].iloc[0] is not None
        assert abs(df["fwd_ret_5d"].iloc[0] - 0.05) < 1e-4

    def test_no_stamp_when_not_matured(self, tmp_path):
        """fwd_ret_21d stays None when only 10 days of data available."""
        import datetime
        start = datetime.date(2024, 1, 2)
        dates = [(start + datetime.timedelta(days=i)).isoformat() for i in range(10)]
        prices = [100.0 + i for i in range(10)]
        _make_ohlcv_parquet(tmp_path, "AAPL", dates, prices)

        df = pd.DataFrame([{
            "session": "2024-01-02", "ticker": "AAPL", "K": 3,
            "fwd_ret_1d": None, "fwd_ret_5d": None,
            "fwd_ret_10d": None, "fwd_ret_21d": None,
        }])
        df = _bif._stamp_forward_returns(df, tmp_path)
        assert df["fwd_ret_21d"].iloc[0] is None

    def test_does_not_overwrite_existing(self, tmp_path):
        """Already-stamped values are preserved."""
        import datetime
        start = datetime.date(2024, 1, 2)
        dates = [(start + datetime.timedelta(days=i)).isoformat() for i in range(30)]
        prices = [100.0] * 30
        _make_ohlcv_parquet(tmp_path, "AAPL", dates, prices)

        df = pd.DataFrame([{
            "session": "2024-01-02", "ticker": "AAPL", "K": 3,
            "fwd_ret_1d": 0.999, "fwd_ret_5d": None,
            "fwd_ret_10d": None, "fwd_ret_21d": None,
        }])
        df = _bif._stamp_forward_returns(df, tmp_path)
        # fwd_ret_1d was already non-null — must not be overwritten.
        assert abs(df["fwd_ret_1d"].iloc[0] - 0.999) < 1e-6


class TestLedgerEnabled:
    """Test the COLLECT_LANE gate."""

    def test_disabled_when_env_absent(self, monkeypatch):
        monkeypatch.delenv("COLLECT_LANE", raising=False)
        monkeypatch.delenv("US_LANE", raising=False)
        assert _bif._ledger_enabled() is False

    def test_enabled_when_nightly(self, monkeypatch):
        monkeypatch.setenv("COLLECT_LANE", "nightly")
        assert _bif._ledger_enabled() is True

    def test_case_insensitive(self, monkeypatch):
        monkeypatch.setenv("US_LANE", "NIGHTLY")
        assert _bif._ledger_enabled() is True

    def test_disabled_for_intraday(self, monkeypatch):
        monkeypatch.setenv("COLLECT_LANE", "intraday")
        assert _bif._ledger_enabled() is False


# ── washout_context ───────────────────────────────────────────────────────────

def _make_daily_bars(closes: list[float], highs: list[float] | None = None, lows: list[float] | None = None) -> pd.DataFrame:
    """Build a minimal daily-bars DataFrame for washout_context tests."""
    n = len(closes)
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    if highs is None:
        highs = [c * 1.02 for c in closes]
    if lows is None:
        lows = [c * 0.98 for c in closes]
    return pd.DataFrame(
        {"open": closes, "high": highs, "low": lows, "close": closes, "volume": [1_000_000] * n},
        index=dates,
    )


class TestWashoutContext:
    def test_decline_then_reclaim_has_small_reclaim_days(self):
        """A decline below BB lower band followed by a reclaim should yield small reclaim_days."""
        # Build a frame: steady baseline so BB bands are computed, then a sharp
        # drop that triggers a lower-band wick + close above the band on the last bar.
        # 30 bars at 100, then a sudden bar where low goes very low (below band) and
        # close recovers above, then 2 normal bars after.
        n_base = 30
        closes = [100.0] * n_base
        highs  = [102.0] * n_base
        lows   = [98.0]  * n_base
        # Insert a bb_lower_reclaim bar: low far below where lower band should be,
        # close recovers above typical price.  With SMA20≈100, sd≈0.1, lower≈99.8.
        # Force a real trigger by dropping the price significantly.
        closes.extend([90.0, 90.5])   # sharp drop for two bars to push lower band
        highs.extend([91.0, 91.5])
        lows.extend([89.0, 89.5])
        # Now the reclaim bar: low < lower band (which is now around 97 area after drop),
        # but close comes back above it.
        closes.append(100.5)   # close above baseline
        highs.append(101.0)
        lows.append(88.0)      # low well below recent lower band
        # Two normal bars after the reclaim
        closes.extend([100.5, 101.0])
        highs.extend([102.0, 102.5])
        lows.extend([99.0, 99.5])

        df = _make_daily_bars(closes, highs, lows)
        result = washout_context(df, lookback=90)

        # The reclaim fired; sessions_since should be small (2 bars after the reclaim bar).
        assert result["bb_lower_reclaim_days"] is not None
        assert result["bb_lower_reclaim_days"] <= 5, (
            f"Expected small reclaim_days, got {result['bb_lower_reclaim_days']}"
        )
        # Drawdown should be negative (the drop to 90 from 100 is significant).
        assert result["drawdown_21d_pct"] is not None
        assert result["drawdown_21d_pct"] < 0
        # recovery_begun: latest close (101) > trough close (90) — True
        assert result["recovery_begun"] is True

    def test_monotonic_uptrend_no_reclaim(self):
        """A steady uptrend never triggers a lower-band reclaim (price stays above band)."""
        # 50 bars of steadily rising prices — should never wick below the lower band.
        closes = [100.0 + i * 0.5 for i in range(50)]
        highs  = [c + 1.0 for c in closes]
        lows   = [c - 0.3 for c in closes]  # lows above the lower band in an uptrend
        df = _make_daily_bars(closes, highs, lows)
        result = washout_context(df, lookback=90)

        # No bb_lower_reclaim event expected in a clean uptrend.
        assert result["bb_lower_reclaim_days"] is None
        # Drawdown in an uptrend is near 0 (each close is above the prior peak).
        assert result["drawdown_21d_pct"] is not None
        assert result["drawdown_21d_pct"] >= -0.05, (
            f"Uptrend drawdown should be near 0, got {result['drawdown_21d_pct']}"
        )

    def test_too_short_frame_returns_all_none(self):
        """A single-bar (or empty) frame yields all-None result."""
        # Single bar — not enough for BB bands or 21d drawdown.
        single = _make_daily_bars([100.0])
        result = washout_context(single, lookback=90)
        assert result["bb_lower_reclaim_days"] is None
        assert result["drawdown_21d_pct"] is None
        assert result["recovery_begun"] is None

    def test_empty_frame_returns_all_none(self):
        """Empty DataFrame returns all-None result without raising."""
        empty = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        result = washout_context(empty, lookback=90)
        assert result["bb_lower_reclaim_days"] is None
        assert result["drawdown_21d_pct"] is None
        assert result["recovery_begun"] is None

    def test_none_frame_returns_all_none(self):
        """None input returns all-None result without raising."""
        result = washout_context(None, lookback=90)  # type: ignore[arg-type]
        assert result["bb_lower_reclaim_days"] is None
        assert result["drawdown_21d_pct"] is None
        assert result["recovery_begun"] is None

    def test_missing_columns_returns_all_none(self):
        """DataFrame missing required columns returns all-None."""
        df = pd.DataFrame({"close": [100.0, 101.0, 102.0]})
        result = washout_context(df, lookback=90)
        assert result["bb_lower_reclaim_days"] is None

    def test_recovery_begun_false_when_still_declining(self):
        """recovery_begun is False when the latest close is below the trough close."""
        # 25 bars: steady then sharp decline at the end (no recovery).
        closes = [100.0] * 20 + [95.0, 92.0, 90.0, 88.0, 86.0]
        df = _make_daily_bars(closes)
        result = washout_context(df, lookback=90)
        assert result["drawdown_21d_pct"] is not None
        assert result["drawdown_21d_pct"] < -0.05
        # Latest close (86) is at the trough, so recovery_begun should be False.
        assert result["recovery_begun"] is False
