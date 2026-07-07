"""Minimal pure-logic tests for options_tape_signed_pilot.

No network calls, no file I/O, no ThetaTerminal dependency.
Tests: quote-rule signing, delta proxy bucketing, aggregation, state machine.
"""
from __future__ import annotations

import json
import tempfile
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Allow import from repo root without install
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.options_tape_signed_pilot import (
    _sign_trades,
    _aggregate_day,
    _moneyness_delta_proxy,
    BackfillStateMachine,
)


# ---------------------------------------------------------------------------
# 1. Quote-rule signing logic
# ---------------------------------------------------------------------------

class TestSigningRule:
    """Verify the simple quote rule (NOT Lee-Ready)."""

    def _make_df(self, rows: list[dict]) -> pd.DataFrame:
        base = {"right": "CALL", "strike": 100.0, "size": 10.0}
        records = [{**base, **r} for r in rows]
        return pd.DataFrame(records)

    def test_at_ask_is_buy(self):
        df = self._make_df([{"price": 5.0, "bid": 4.0, "ask": 5.0}])
        out = _sign_trades(df, spot=100.0)
        assert out["side"].iloc[0] == "BUY", "price == ask must be BUY"

    def test_above_ask_is_buy(self):
        df = self._make_df([{"price": 5.5, "bid": 4.0, "ask": 5.0}])
        out = _sign_trades(df, spot=100.0)
        assert out["side"].iloc[0] == "BUY", "price > ask must be BUY"

    def test_at_bid_is_sell(self):
        df = self._make_df([{"price": 4.0, "bid": 4.0, "ask": 5.0}])
        out = _sign_trades(df, spot=100.0)
        assert out["side"].iloc[0] == "SELL", "price == bid must be SELL"

    def test_below_bid_is_sell(self):
        df = self._make_df([{"price": 3.5, "bid": 4.0, "ask": 5.0}])
        out = _sign_trades(df, spot=100.0)
        assert out["side"].iloc[0] == "SELL", "price < bid must be SELL"

    def test_midpoint_is_excluded(self):
        df = self._make_df([{"price": 4.5, "bid": 4.0, "ask": 5.0}])
        out = _sign_trades(df, spot=100.0)
        assert out["side"].iloc[0] is None or pd.isna(out["side"].iloc[0]), \
            "midpoint trade must be excluded (None)"

    def test_crossed_market_excluded(self):
        """bid > ask = crossed market → excluded."""
        df = self._make_df([{"price": 5.0, "bid": 6.0, "ask": 5.0}])
        out = _sign_trades(df, spot=100.0)
        assert out["side"].iloc[0] is None or pd.isna(out["side"].iloc[0]), \
            "crossed market must be excluded"

    def test_nan_bid_excluded(self):
        df = self._make_df([{"price": 5.0, "bid": float("nan"), "ask": 5.0}])
        out = _sign_trades(df, spot=100.0)
        assert out["side"].iloc[0] is None or pd.isna(out["side"].iloc[0])

    def test_nan_ask_excluded(self):
        df = self._make_df([{"price": 4.0, "bid": 4.0, "ask": float("nan")}])
        out = _sign_trades(df, spot=100.0)
        assert out["side"].iloc[0] is None or pd.isna(out["side"].iloc[0])

    def test_empty_dataframe(self):
        df = pd.DataFrame(columns=["price", "bid", "ask", "strike", "right", "size"])
        out = _sign_trades(df, spot=100.0)
        assert len(out) == 0

    def test_mixed_batch(self):
        """Buy, sell, mid in same batch → correct classification."""
        df = self._make_df([
            {"price": 5.0, "bid": 4.0, "ask": 5.0},   # BUY
            {"price": 4.0, "bid": 4.0, "ask": 5.0},   # SELL
            {"price": 4.5, "bid": 4.0, "ask": 5.0},   # EXCLUDED (mid)
        ])
        out = _sign_trades(df, spot=100.0)
        assert out["side"].iloc[0] == "BUY"
        assert out["side"].iloc[1] == "SELL"
        assert out["side"].iloc[2] is None or pd.isna(out["side"].iloc[2])


# ---------------------------------------------------------------------------
# 2. Delta proxy bucketing
# ---------------------------------------------------------------------------

class TestDeltaProxy:
    """Verify moneyness-bucket proxy delta assignment."""

    def _proxy(self, strike, is_call, spot) -> float:
        s = pd.Series([float(strike)])
        c = pd.Series([bool(is_call)])
        return float(_moneyness_delta_proxy(s, c, spot).iloc[0])

    def test_atm_call(self):
        # moneyness = (100-100)/100 = 0 → |m|<=0.10 → 0.50
        assert self._proxy(100, True, 100) == pytest.approx(0.50)

    def test_deep_itm_call(self):
        # spot=100, strike=70 → m=(100-70)/100=0.30 > 0.20 → 0.90
        assert self._proxy(70, True, 100) == pytest.approx(0.90)

    def test_itm_call(self):
        # spot=100, strike=85 → m=0.15 → 0.10<|m|<=0.20 → 0.70
        assert self._proxy(85, True, 100) == pytest.approx(0.70)

    def test_otm_call(self):
        # spot=100, strike=115 → m=(100-115)/100=-0.15 → OTM, |m|=0.15 → 0.30
        assert self._proxy(115, True, 100) == pytest.approx(0.30)

    def test_deep_otm_call(self):
        # spot=100, strike=130 → m=(100-130)/100=-0.30 → OTM, |m|=0.30>0.20 → 0.10
        assert self._proxy(130, True, 100) == pytest.approx(0.10)

    def test_atm_put(self):
        # put moneyness = (strike-spot)/spot = 0 → 0.50
        assert self._proxy(100, False, 100) == pytest.approx(0.50)

    def test_deep_itm_put(self):
        # put: strike=130, spot=100 → m=(130-100)/100=0.30>0.20 → 0.90
        assert self._proxy(130, False, 100) == pytest.approx(0.90)

    def test_deep_otm_put(self):
        # put: strike=70, spot=100 → m=(70-100)/100=-0.30 → OTM, 0.10
        assert self._proxy(70, False, 100) == pytest.approx(0.10)

    def test_vectorized(self):
        """Vectorized call works correctly for mixed call/put series."""
        strikes = pd.Series([70.0, 100.0, 130.0])  # deep ITM call, ATM call, deep OTM call
        is_call = pd.Series([True, True, True])
        result = _moneyness_delta_proxy(strikes, is_call, 100.0)
        assert list(result) == pytest.approx([0.90, 0.50, 0.10])


# ---------------------------------------------------------------------------
# 3. Aggregation
# ---------------------------------------------------------------------------

class TestAggregation:
    """Verify _aggregate_day produces correct signed metrics."""

    def _make_signed(self, rows: list[dict]) -> pd.DataFrame:
        """Build a pre-signed DataFrame."""
        return pd.DataFrame(rows)

    def test_empty_returns_zeros(self):
        agg = _aggregate_day(pd.DataFrame())
        assert agg["buy_count"] == 0
        assert agg["sell_count"] == 0
        assert agg["net_premium"] == 0.0

    def test_buy_premium_correct(self):
        df = pd.DataFrame([
            {"side": "BUY",  "price": 5.0, "size": 10.0, "delta_proxy": 0.50,
             "bid": 4.0, "ask": 5.0},
        ])
        agg = _aggregate_day(df)
        # 5.0 * 10 * 100 = 5000
        assert agg["buy_premium"] == pytest.approx(5000.0)
        assert agg["sell_premium"] == pytest.approx(0.0)
        assert agg["net_premium"] == pytest.approx(5000.0)

    def test_sell_premium_correct(self):
        df = pd.DataFrame([
            {"side": "SELL", "price": 4.0, "size": 5.0, "delta_proxy": 0.50,
             "bid": 4.0, "ask": 5.0},
        ])
        agg = _aggregate_day(df)
        assert agg["sell_premium"] == pytest.approx(2000.0)
        assert agg["net_premium"] == pytest.approx(-2000.0)

    def test_net_delta_signed_correctly(self):
        df = pd.DataFrame([
            {"side": "BUY",  "price": 5.0, "size": 10.0, "delta_proxy": 0.70,
             "bid": 4.0, "ask": 5.0},
            {"side": "SELL", "price": 4.0, "size": 20.0, "delta_proxy": 0.30,
             "bid": 4.0, "ask": 5.0},
        ])
        agg = _aggregate_day(df)
        assert agg["buy_delta_proxy"] == pytest.approx(7.0)   # 0.70 * 10
        assert agg["sell_delta_proxy"] == pytest.approx(6.0)  # 0.30 * 20
        assert agg["net_delta_proxy"]  == pytest.approx(1.0)  # 7 - 6

    def test_exclusion_rate(self):
        df = pd.DataFrame([
            {"side": "BUY",  "price": 5.0, "size": 10.0, "delta_proxy": 0.5,
             "bid": 4.0, "ask": 5.0},
            {"side": None,   "price": 4.5, "size": 5.0,  "delta_proxy": 0.5,
             "bid": 4.0, "ask": 5.0},  # excluded
        ])
        agg = _aggregate_day(df)
        assert agg["total_count"] == 2
        assert agg["excluded_count"] == 1
        assert agg["exclusion_rate"] == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# 4. State machine
# ---------------------------------------------------------------------------

class TestBackfillStateMachine:
    """Verify BackfillStateMachine: init, mark_done, is_done, resume."""

    def test_new_state_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            sm = BackfillStateMachine(path)
            assert not sm.is_done("SPY", date(2026, 7, 1))

    def test_mark_and_check_done(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            sm = BackfillStateMachine(path)
            d = date(2026, 7, 1)
            sm.mark_done("SPY", d)
            assert sm.is_done("SPY", d)
            assert not sm.is_done("SPY", date(2026, 7, 2))
            assert not sm.is_done("QQQ", d)

    def test_save_and_reload(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            sm = BackfillStateMachine(path)
            sm.mark_done("SPY", date(2026, 7, 1))
            sm.save()

            sm2 = BackfillStateMachine(path)
            assert sm2.is_done("SPY", date(2026, 7, 1))
            assert not sm2.is_done("SPY", date(2026, 7, 2))

    def test_mark_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            sm = BackfillStateMachine(path)
            sm.mark_error("AAPL", date(2026, 7, 2), "timeout")
            sm.save()

            sm2 = BackfillStateMachine(path)
            errors = sm2._state["underlyings"]["AAPL"]["errors"]
            assert "2026-07-02" in errors
            assert errors["2026-07-02"] == "timeout"

    def test_idempotent_mark_done(self):
        """Marking the same date twice should not duplicate the entry."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            sm = BackfillStateMachine(path)
            d = date(2026, 7, 1)
            sm.mark_done("SPY", d)
            sm.mark_done("SPY", d)
            assert sm._state["underlyings"]["SPY"]["completed_dates"].count("2026-07-01") == 1

    def test_coverage_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            sm = BackfillStateMachine(path)
            sm.mark_done("SPY", date(2026, 7, 1))
            sm.mark_done("SPY", date(2026, 7, 2))
            sm.mark_done("AAPL", date(2026, 7, 1))
            cov = sm.coverage_summary()
            assert cov["SPY"] == 2
            assert cov["AAPL"] == 1

    def test_corrupt_state_resets(self):
        """Corrupt JSON should reset to empty state, not crash."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            path.write_text("{corrupt json {{")
            sm = BackfillStateMachine(path)
            assert sm._state == {"version": 1, "underlyings": {}}


# ---------------------------------------------------------------------------
# 5. PILOT_UNDERLYINGS contract
# ---------------------------------------------------------------------------

def test_pilot_underlyings_count():
    """Lane spec requires exactly 20 underlyings."""
    from scripts.options_tape_signed_pilot import PILOT_UNDERLYINGS
    assert len(PILOT_UNDERLYINGS) == 20

def test_pilot_underlyings_contains_required():
    """The 10 required names from the lane spec must all be present."""
    from scripts.options_tape_signed_pilot import PILOT_UNDERLYINGS
    required = {"SPY", "QQQ", "AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "META", "GOOGL", "AMD"}
    missing = required - set(PILOT_UNDERLYINGS)
    assert not missing, f"Missing required underlyings: {missing}"
