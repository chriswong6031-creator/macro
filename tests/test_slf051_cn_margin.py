"""Minimal pytest for SLF-051 margin impulse pure-function logic.

Tests only importable, pure-function helpers (no network, no large data).
Fixtures are tiny synthetic series to keep the suite sub-second.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------#
# import the module under test (path-safe)
# ---------------------------------------------------------------------------#
import importlib.util as _ilu

_spec = _ilu.spec_from_file_location(
    "slf051", ROOT / "scripts" / "slf051_cn_margin_phase0.py"
)
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)


# ---------------------------------------------------------------------------#
# helpers
# ---------------------------------------------------------------------------#
def _idx(n: int, start: str = "2015-01-01") -> pd.DatetimeIndex:
    return pd.date_range(start, periods=n, freq="B")  # business days


def _prices(n: int = 300, seed: int = 42) -> pd.Series:
    rng = np.random.default_rng(seed)
    log_ret = rng.normal(0.0003, 0.012, n)
    prices = 100.0 * np.exp(np.cumsum(log_ret))
    return pd.Series(prices, index=_idx(n))


# ---------------------------------------------------------------------------#
# forward_returns
# ---------------------------------------------------------------------------#
class TestForwardReturns:
    def test_basic_shape(self):
        px = _prices(200)
        fwds = _mod.forward_returns(px, [21, 63])
        assert "fwd_21d" in fwds.columns
        assert "fwd_63d" in fwds.columns
        assert len(fwds) == len(px)

    def test_no_lookahead_last_horizon_rows(self):
        """Last h rows should be NaN because we can't look 21d forward."""
        px = _prices(200)
        fwds = _mod.forward_returns(px, [21])
        assert fwds["fwd_21d"].iloc[-21:].isna().all()

    def test_fwd_return_sign(self):
        """Known monotone price: every fwd 5d return must be positive."""
        px = pd.Series(
            [100.0 + i * 0.5 for i in range(100)], index=_idx(100)
        )
        fwds = _mod.forward_returns(px, [5])
        # First 95 entries should be positive (last 5 are NaN)
        valid = fwds["fwd_5d"].iloc[:95]
        assert (valid > 0).all(), "monotone up price => all fwd returns positive"


# ---------------------------------------------------------------------------#
# forward_maxdrawdown
# ---------------------------------------------------------------------------#
class TestForwardMaxDrawdown:
    def test_no_lookahead_last_rows(self):
        """Last `horizon` rows should be NaN (no future window)."""
        horizon = 21
        px = _prices(100)
        dd = _mod.forward_maxdrawdown(px, horizon)
        # rows beyond len(px)-horizon should not appear
        assert len(dd) == len(px) - horizon

    def test_monotone_up_no_drawdown(self):
        """Monotone rising prices: max drawdown = 0 at every step."""
        px = pd.Series(
            [100.0 + i for i in range(100)], index=_idx(100)
        )
        dd = _mod.forward_maxdrawdown(px, 10)
        assert (dd.dropna() >= 0).all(), "rising prices => no drawdown (dd >= 0)"

    def test_monotone_down_negative_drawdown(self):
        """Monotone falling prices: max drawdown should be negative at every step."""
        px = pd.Series(
            [100.0 - i * 0.5 for i in range(100)], index=_idx(100)
        )
        dd = _mod.forward_maxdrawdown(px, 5)
        valid = dd.dropna()
        assert (valid < 0).all(), "falling prices => all drawdowns negative"

    def test_known_value(self):
        """Price drops 10% and recovers: max drawdown should be exactly -10%."""
        # 3 prices: 100, 90, 100
        px = pd.Series([100.0, 90.0, 100.0], index=pd.date_range("2020-01-01", periods=3))
        dd = _mod.forward_maxdrawdown(px, 2)
        # Only date 0 has a full 2-day window: future = [90, 100]
        # min(90/100 - 1, 100/100 - 1) = min(-0.10, 0.00) = -0.10
        assert abs(dd.iloc[0] - (-0.10)) < 1e-9


# ---------------------------------------------------------------------------#
# build_signals (smoke test on synthetic data)
# ---------------------------------------------------------------------------#
class TestBuildSignals:
    def _make_data(self, n: int = 600):
        """Create synthetic bal and dt DataFrames on a business-day index."""
        idx = _idx(n, "2014-01-01")
        rng = np.random.default_rng(7)
        # Slowly trending margin total (in billions)
        margin_total = pd.Series(
            1000.0 + np.cumsum(rng.normal(1.0, 3.0, n)), index=idx, name="margin_total"
        )
        bal = pd.DataFrame({"margin_total": margin_total}, index=idx)

        trade_amt_ratio = pd.Series(
            9.0 + rng.normal(0, 0.5, n), index=idx, name="trade_amt_ratio"
        )
        dt = pd.DataFrame({
            "margin_balance": margin_total * 0.99,
            "trade_amt_ratio": trade_amt_ratio,
            "margin_trade_amt": margin_total * 0.99 * trade_amt_ratio / 100,
        }, index=idx)
        dt.index.name = "STATISTICS_DATE"
        bal.index.name = "DIM_DATE"
        return bal, dt

    def test_signal_columns_exist(self):
        bal, dt = self._make_data()
        sigs = _mod.build_signals(bal, dt)
        for col in ["sig_roc20", "sig_roc60", "sig_turnrat_z", "sig_washout"]:
            assert col in sigs.columns, f"missing column {col}"

    def test_washout_binary(self):
        """sig_washout must be 0 or 1 (no other values)."""
        bal, dt = self._make_data()
        sigs = _mod.build_signals(bal, dt)
        unique = set(sigs["sig_washout"].dropna().unique())
        assert unique <= {0.0, 1.0}, f"sig_washout has non-binary values: {unique}"

    def test_roc20_lag(self):
        """roc20 at row 0..18 should be NaN (no 20-bar history)."""
        bal, dt = self._make_data(300)
        sigs = _mod.build_signals(bal, dt)
        # first 20 rows: should be NaN
        assert sigs["sig_roc20"].iloc[:20].isna().all()

    def test_turnrat_z_delayed_start(self):
        """turnrat_z requires 252d rolling; first ~63 rows should be NaN (min_periods=63)."""
        bal, dt = self._make_data(400)
        sigs = _mod.build_signals(bal, dt)
        # First 62 rows must be NaN due to min_periods=63
        assert sigs["sig_turnrat_z"].iloc[:62].isna().all()


# ---------------------------------------------------------------------------#
# washout_event_study
# ---------------------------------------------------------------------------#
class TestWashoutEventStudy:
    def test_fire_count(self):
        """Returns n_fire_dates equal to count of signal==1 dates."""
        n = 300
        idx = _idx(n)
        signal = pd.Series(0.0, index=idx)
        signal.iloc[50] = 1.0
        signal.iloc[100] = 1.0
        signal.iloc[200] = 1.0
        fwd21 = pd.Series(np.random.default_rng(1).normal(0.01, 0.05, n), index=idx)
        fwd63 = pd.Series(np.random.default_rng(2).normal(0.02, 0.08, n), index=idx)

        res = _mod.washout_event_study(signal, fwd21, fwd63)
        assert res["n_fire_dates"] == 3

    def test_known_direction(self):
        """If all fire-date fwd returns are positive, direction_ok_21 = True."""
        n = 300
        idx = _idx(n)
        signal = pd.Series(0.0, index=idx)
        fire_positions = [50, 100, 150, 200, 250]
        for pos in fire_positions:
            signal.iloc[pos] = 1.0
        fwd21 = pd.Series(-0.01, index=idx)  # mostly negative
        for pos in fire_positions:
            fwd21.iloc[pos] = 0.05  # fire dates are positive

        fwd63 = fwd21.copy()
        res = _mod.washout_event_study(signal, fwd21, fwd63)
        assert res["direction_ok_21"] is True

    def test_no_fires(self):
        """Zero fire dates: means should be NaN."""
        n = 200
        idx = _idx(n)
        signal = pd.Series(0.0, index=idx)
        fwd21 = pd.Series(0.01, index=idx)
        fwd63 = pd.Series(0.02, index=idx)
        res = _mod.washout_event_study(signal, fwd21, fwd63)
        assert res["n_fire_dates"] == 0
        assert math.isnan(res["mean_fwd21"])


# ---------------------------------------------------------------------------#
# baseline_200dma
# ---------------------------------------------------------------------------#
class TestBaseline200dma:
    def test_all_above_200dma(self):
        """If prices are always above 200dma, n_below should be 0."""
        n = 400
        idx = _idx(n)
        # Monotone rising: always above its own SMA after warmup
        prices = pd.Series([100.0 + i * 0.1 for i in range(n)], index=idx)
        fwd21 = pd.Series(0.01, index=idx)
        fwd63 = pd.Series(0.02, index=idx)
        res = _mod.baseline_200dma(prices, fwd21, fwd63)
        assert res["n_below"] == 0

    def test_returns_dict_keys(self):
        """Result dict must contain expected keys."""
        n = 400
        idx = _idx(n)
        prices = pd.Series([100.0 + np.sin(i / 20) * 10 for i in range(n)], index=idx)
        fwd21 = pd.Series(np.random.default_rng(3).normal(0.005, 0.04, n), index=idx)
        fwd63 = pd.Series(np.random.default_rng(4).normal(0.01, 0.06, n), index=idx)
        res = _mod.baseline_200dma(prices, fwd21, fwd63)
        for key in ["n_below", "mean_fwd21_below_200dma", "mean_fwd63_below_200dma",
                    "direction_ok_21", "direction_ok_63"]:
            assert key in res, f"missing key: {key}"


# ---------------------------------------------------------------------------#
# split_half
# ---------------------------------------------------------------------------#
class TestSplitHalf:
    def test_structure(self):
        n = 300
        idx = _idx(n)
        signal = pd.Series(np.random.default_rng(5).normal(0, 1, n), index=idx)
        fwd = pd.Series(np.random.default_rng(6).normal(0.005, 0.04, n), index=idx)
        res = _mod.split_half(signal, fwd, +1)
        assert "first_half" in res
        assert "second_half" in res
        assert "g4_pass" in res

    def test_consistent_positive_direction(self):
        """If top decile always positive in both halves, g4_pass should be True."""
        n = 500
        idx = _idx(n)
        # Signal: high values -> high future returns
        signal = pd.Series(np.linspace(0, 10, n), index=idx)
        # Forward return proportional to signal rank
        fwd = signal * 0.001 + 0.002
        res = _mod.split_half(signal, fwd, +1)
        assert res["g4_pass"] is True


# ---------------------------------------------------------------------------#
# drawdown_auc
# ---------------------------------------------------------------------------#
class TestDrawdownAuc:
    def test_direction_ok_when_top_worse(self):
        """When top-decile has lower (more negative) drawdown than rest, direction_ok=True."""
        n = 400
        idx = _idx(n)
        # top_mask: True for first 40 obs (10%), False for rest
        top_mask = pd.Series([1.0] * 40 + [0.0] * 360, index=idx)
        # top has worse dd
        dd = pd.Series([-0.20] * 40 + [-0.05] * 360, index=idx)
        res = _mod.drawdown_auc(top_mask, dd)
        assert res["direction_ok"] is True

    def test_direction_ok_false_when_top_better(self):
        """When top-decile has higher (less negative) drawdown than rest, direction_ok=False."""
        n = 400
        idx = _idx(n)
        top_mask = pd.Series([1.0] * 40 + [0.0] * 360, index=idx)
        dd = pd.Series([-0.01] * 40 + [-0.15] * 360, index=idx)
        res = _mod.drawdown_auc(top_mask, dd)
        assert res["direction_ok"] is False
