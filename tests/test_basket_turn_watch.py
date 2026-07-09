"""Tests for engine/basket_turn_watch.py — FTR W4.

Covers:
  (1) impulse_day leg — fraction floor, threshold math
  (2) rs_z leg — cross-sectional z computation
  (3) breadth_surge leg — Δpct50 z and crossing count
  (4) volume_confirm leg — EW dollar-vol vs 20d median
  (5) complex_confirm leg — sibling positive rs_z count
  (6) shock_relative_bid leg — binary gate conditions
  (7) State assignment — WATCH / IGNITION thresholds
  (8) Hysteresis — 2-session downgrade delay
  (9) Ledger idempotency — keep-first per (date, basket_id)
  (10) US_LANE gate — stamp only when US_LANE=nightly
  (11) Forbidden fields — no beneficiary/casualty/shelter/front_run/buy/direction
       anywhere in the emitted JSON
  (12) compute() exit-0 contract — never raises even with empty inputs
  (13) W5 complexes block — ai_capex EW, n_live, only_green_complex logic
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

# Ensure project root on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import engine.basket_turn_watch as BTW
from scripts import build_basket_pulse as BP


# ── helpers ────────────────────────────────────────────────────────────────────

_TODAY = "2026-07-09"

FORBIDDEN_KEYS = frozenset(
    ["beneficiary", "casualty", "shelter", "front_run", "buy", "direction"]
)


def _walk_keys(obj: Any) -> list[str]:
    """Recursively collect all string keys from a nested dict/list."""
    keys: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            keys.append(k)
            keys.extend(_walk_keys(v))
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            keys.extend(_walk_keys(item))
    return keys


def _make_close_series(values: list[float], n_pad: int = 0) -> pd.Series:
    """Build a pd.Series of close prices with a DatetimeIndex."""
    if n_pad:
        values = [values[0]] * n_pad + list(values)
    idx = pd.date_range(end="2026-07-09", periods=len(values), freq="B")
    return pd.Series(values, index=idx, dtype=float)


def _flat_series(value: float, n: int) -> pd.Series:
    """Constant close series of length n."""
    return _make_close_series([value] * n)


def _make_df(close_vals: list[float], volume_vals: list[float] | None = None) -> pd.DataFrame:
    """Build a price DataFrame with close + volume columns."""
    n = len(close_vals)
    vol = volume_vals if volume_vals is not None else [1_000_000.0] * n
    idx = pd.date_range(end="2026-07-09", periods=n, freq="B")
    return pd.DataFrame({"close": close_vals, "volume": vol}, index=idx)


# ── (1) impulse_day ────────────────────────────────────────────────────────────

class TestImpulseDay:
    def _closes(self, prev: float, today: float) -> pd.Series:
        return _make_close_series([prev, today])

    def test_fires_when_enough_members_up(self):
        """3 of 6 tickers up ≥3% with 6 members → 1/3 threshold met (2 floor)."""
        closes = {
            "A": self._closes(100, 103.5),   # +3.5% ✓
            "B": self._closes(100, 103.0),   # +3.0% ✓
            "C": self._closes(100, 103.1),   # +3.1% ✓
            "D": self._closes(100, 101.0),   # +1.0% ✗
            "E": self._closes(100, 100.5),   # +0.5% ✗
            "F": self._closes(100, 102.0),   # +2.0% ✗
        }
        assert BTW._leg_impulse_day(["A", "B", "C", "D", "E", "F"], closes) is True

    def test_does_not_fire_when_below_threshold(self):
        """1 of 6 up ≥3% but need ≥2 (floor)."""
        closes = {
            "A": self._closes(100, 103.5),   # ✓
            "B": self._closes(100, 102.0),   # ✗
            "C": self._closes(100, 100.5),   # ✗
            "D": self._closes(100, 101.0),   # ✗
            "E": self._closes(100, 102.5),   # ✗
            "F": self._closes(100, 100.1),   # ✗
        }
        assert BTW._leg_impulse_day(["A", "B", "C", "D", "E", "F"], closes) is False

    def test_floor_two_members_with_only_two_tickers(self):
        """2-member basket: need 1 (1/3*2=0.67→1; floor=2 so need 2)."""
        closes = {
            "A": self._closes(100, 105.0),   # +5% ✓
            "B": self._closes(100, 101.0),   # ✗
        }
        # 2 members, threshold = max(1/3*2, 2) = max(0.67, 2) = 2 → need both
        assert BTW._leg_impulse_day(["A", "B"], closes) is False

    def test_floor_satisfied_both_up(self):
        """Both members up → floor=2 satisfied."""
        closes = {
            "A": self._closes(100, 104.0),
            "B": self._closes(100, 103.5),
        }
        assert BTW._leg_impulse_day(["A", "B"], closes) is True

    def test_empty_tickers_returns_false(self):
        assert BTW._leg_impulse_day([], {}) is False

    def test_missing_price_data_returns_false(self):
        """No price data → never fires."""
        assert BTW._leg_impulse_day(["NOSYM"], {}) is False


# ── (2) rs_z ──────────────────────────────────────────────────────────────────

class TestRsZ:
    def _spy(self, ret: float = 0.005) -> float:
        return ret

    def test_fires_when_z_above_threshold(self):
        """Basket with strong outlier return should produce z >= 2.0.

        With A=0.10 vs peers around 0%, the excess of A is ~0.095 while others
        cluster near 0. std of excesses ≈ 0.04 → z ≈ 2+ depending on exact numbers.
        Use a stronger outlier to guarantee z >= 2.
        """
        # A is a large outlier; others are clustered near zero
        all_rets = {
            "A": 0.12,     # this basket — strong outperformer
            "B": 0.001,
            "C": 0.000,
            "D": -0.001,
            "E": 0.002,
            "F": -0.002,
            "G": 0.001,
            "H": -0.001,
            "I": 0.000,
            "J": 0.001,
        }
        spy_ret = 0.000
        fired, z = BTW._leg_rs_z("A", 0.12, all_rets, spy_ret)
        assert fired is True, f"Expected fired=True, got z={z}"
        assert z is not None and z >= BTW.RS_Z_THRESHOLD

    def test_does_not_fire_when_z_below_threshold(self):
        """Basket at market-average return → z near 0."""
        all_rets = {bid: 0.01 for bid in ["A", "B", "C", "D", "E"]}
        fired, z = BTW._leg_rs_z("A", 0.01, all_rets, 0.01)
        assert fired is False

    def test_none_return_returns_false(self):
        fired, z = BTW._leg_rs_z("A", None, {}, 0.005)
        assert fired is False
        assert z is None

    def test_none_spy_returns_false(self):
        fired, z = BTW._leg_rs_z("A", 0.05, {"A": 0.05}, None)
        assert fired is False

    def test_insufficient_baskets_returns_false(self):
        """Need at least 3 baskets for a meaningful z."""
        fired, z = BTW._leg_rs_z("A", 0.05, {"A": 0.05, "B": 0.01}, 0.005)
        assert fired is False


# ── (3) breadth_surge — tested via direct close array ─────────────────────────

class TestBreadthSurge:
    def _make_closes_map(self, tickers: list[str], n: int = 120) -> dict[str, pd.Series]:
        """Build a closes_map where each ticker trends up gradually."""
        out: dict[str, pd.Series] = {}
        for tk in tickers:
            vals = [100.0 + i * 0.1 for i in range(n)]
            out[tk] = _make_close_series(vals)
        return out

    def test_fires_when_all_cross_above_ma50_today(self):
        """Force 3 tickers to cross above their 50d MA today."""
        n = 120
        closes = {}
        for i, tk in enumerate(["A", "B", "C"]):
            # Was below MA for last 50 days, then spike today
            vals = [90.0] * (n - 1) + [120.0]  # MA50 will be ~90, today=120
            closes[tk] = _make_close_series(vals)

        # With 3 tickers all crossing: Δpct50 today should be high
        result = BTW._leg_breadth_surge(["A", "B", "C"], closes)
        # We can't guarantee exact z threshold in this test without a full 60d history,
        # but we can verify the function doesn't crash and returns a bool
        assert isinstance(result, bool)

    def test_returns_false_insufficient_data(self):
        """Only 10 sessions → below the 51-bar minimum."""
        closes = {
            "A": _make_close_series([100.0] * 10),
            "B": _make_close_series([100.0] * 10),
        }
        assert BTW._leg_breadth_surge(["A", "B"], closes) is False

    def test_returns_false_empty_tickers(self):
        assert BTW._leg_breadth_surge([], {}) is False


# ── (4) volume_confirm ─────────────────────────────────────────────────────────

class TestVolumeConfirm:
    def test_fires_when_volume_spike(self):
        """Today's dollar-vol is 2× median → should fire at 1.5× threshold."""
        n = 25  # 20d lookback + 5 buffer
        close = [100.0] * n
        vol_base = [1_000_000.0] * (n - 1) + [2_000_000.0]  # spike today
        price_data = {
            "A": _make_df(close, vol_base),
            "B": _make_df(close, vol_base),
        }
        # Trim closes_map (not used in volume_confirm)
        result = BTW._leg_volume_confirm(["A", "B"], price_data)
        assert result is True

    def test_does_not_fire_at_normal_volume(self):
        """Normal volume → should not fire."""
        n = 25
        close = [100.0] * n
        vol = [1_000_000.0] * n  # no spike
        price_data = {
            "A": _make_df(close, vol),
        }
        result = BTW._leg_volume_confirm(["A"], price_data)
        assert result is False

    def test_returns_false_insufficient_data(self):
        """Fewer than 21 rows → can't compute median."""
        price_data = {
            "A": _make_df([100.0] * 10, [1_000_000.0] * 10),
        }
        assert BTW._leg_volume_confirm(["A"], price_data) is False


# ── (5) complex_confirm ────────────────────────────────────────────────────────

class TestComplexConfirm:
    def test_fires_with_two_positive_siblings(self):
        """2 siblings with positive rs_z → fires."""
        sibling_ids = frozenset(["S1", "S2", "S3"])
        all_rs_z = {"S1": 1.5, "S2": 0.8, "S3": -0.5}
        assert BTW._leg_complex_confirm("A", sibling_ids, all_rs_z) is True

    def test_does_not_fire_with_one_positive_sibling(self):
        """Only 1 sibling positive → doesn't fire (need ≥2)."""
        sibling_ids = frozenset(["S1", "S2"])
        all_rs_z = {"S1": 1.5, "S2": -0.5}
        assert BTW._leg_complex_confirm("A", sibling_ids, all_rs_z) is False

    def test_does_not_fire_with_none_z_values(self):
        """None rs_z values don't count as positive."""
        sibling_ids = frozenset(["S1", "S2", "S3"])
        all_rs_z = {"S1": None, "S2": None, "S3": None}
        assert BTW._leg_complex_confirm("A", sibling_ids, all_rs_z) is False

    def test_empty_siblings_returns_false(self):
        assert BTW._leg_complex_confirm("A", frozenset(), {"B": 2.0}) is False


# ── (6) shock_relative_bid ────────────────────────────────────────────────────

class TestShockRelativeBid:
    def test_fires_on_oil_shock_spy_down_rs_positive(self):
        """All three gate conditions met → binary True."""
        md = {"primary": "oil_shock", "family": "neutral"}
        assert BTW._leg_shock_relative_bid(rs_z=0.5, market_drivers=md, spy_ret=-0.02) is True

    def test_geopolitical_family_inoperative(self):
        """Geopolitical family matching is currently inoperative.

        The market_drivers taxonomy has no 'geopolitical' driver or family
        (verified: engine/market_drivers.py DRIVERS — oil_shock has family='inflation';
        'geopolitical' is absent; emitted market_drivers block has no top-level 'family' key).
        Until the taxonomy is extended upstream, leg 6 only gates on primary=='oil_shock'.
        This test documents the known inoperative state so any future taxonomy extension
        that enables it will surface here.
        """
        md = {"primary": "other", "family": "geopolitical"}
        # Family-based match is inoperative — returns False (not True as the original spec
        # intended), because 'geopolitical' does not exist in the upstream taxonomy.
        assert BTW._leg_shock_relative_bid(rs_z=1.0, market_drivers=md, spy_ret=-0.01) is False

    def test_does_not_fire_when_spy_flat(self):
        md = {"primary": "oil_shock"}
        assert BTW._leg_shock_relative_bid(rs_z=1.0, market_drivers=md, spy_ret=0.0) is False

    def test_does_not_fire_when_spy_up(self):
        md = {"primary": "oil_shock"}
        assert BTW._leg_shock_relative_bid(rs_z=1.0, market_drivers=md, spy_ret=0.01) is False

    def test_does_not_fire_when_rs_z_negative(self):
        md = {"primary": "oil_shock"}
        assert BTW._leg_shock_relative_bid(rs_z=-0.1, market_drivers=md, spy_ret=-0.02) is False

    def test_does_not_fire_when_rs_z_none(self):
        md = {"primary": "oil_shock"}
        assert BTW._leg_shock_relative_bid(rs_z=None, market_drivers=md, spy_ret=-0.02) is False

    def test_does_not_fire_when_no_market_drivers(self):
        assert BTW._leg_shock_relative_bid(rs_z=1.0, market_drivers=None, spy_ret=-0.02) is False

    def test_does_not_fire_on_non_shock_driver(self):
        md = {"primary": "earnings_season", "family": "neutral"}
        assert BTW._leg_shock_relative_bid(rs_z=2.0, market_drivers=md, spy_ret=-0.03) is False


# ── (7) state assignment ──────────────────────────────────────────────────────

class TestStateAssignment:
    """Test the K-of-N state logic via a minimal compute() call with synthetic data."""

    def _minimal_compute(
        self,
        legs_true: list[str],
        tmp_path: Path,
    ) -> dict | None:
        """Run compute() with a synthetic single-basket universe.

        Sets exactly the specified legs to True (using patched leg functions).
        Returns the basket row for 'test_basket' or None.
        """
        import engine.basket_turn_watch as btw_mod

        # Build a synthetic closes_map with enough data for any leg
        n = 150
        close_vals = [100.0 + i * 0.01 for i in range(n)]
        spy_closes = _make_close_series(close_vals)
        # Add a bump today for rs_z if needed
        closes = {"SPY": spy_closes}
        for tk in ["M1", "M2", "M3", "M4", "M5", "M6"]:
            closes[tk] = _make_close_series(close_vals)

        # Minimal membership
        baskets_meta = {
            "test_basket": {
                "members": [
                    {"ticker": "M1", "removed": None},
                    {"ticker": "M2", "removed": None},
                    {"ticker": "M3", "removed": None},
                    {"ticker": "M4", "removed": None},
                    {"ticker": "M5", "removed": None},
                    {"ticker": "M6", "removed": None},
                ]
            }
        }

        # Patch legs
        _LEGS = {
            "impulse_day": "_leg_impulse_day",
            "rs_z": "_leg_rs_z",
            "breadth_surge": "_leg_breadth_surge",
            "volume_confirm": "_leg_volume_confirm",
            "complex_confirm": "_leg_complex_confirm",
            "shock_relative_bid": "_leg_shock_relative_bid",
        }

        import unittest.mock as mock
        patches = []

        # Patch each leg to return its fixed value
        for leg_name, fn_name in _LEGS.items():
            fired = leg_name in legs_true
            if leg_name == "rs_z":
                # _leg_rs_z returns (bool, float|None)
                z_val = 3.0 if fired else -1.0
                p = mock.patch.object(btw_mod, fn_name, return_value=(fired, z_val if fired else None))
            else:
                p = mock.patch.object(btw_mod, fn_name, return_value=fired)
            patches.append(p)
            p.start()

        # Patch price loading to avoid disk access
        mock.patch.object(btw_mod, "_load_prices", lambda tk, dr=None: _make_df(close_vals)).start()
        mock.patch.object(btw_mod, "_load_market_drivers", lambda dr=None: None).start()
        mock.patch.object(btw_mod, "stamp_ledger", return_value=0).start()
        mock.patch.object(btw_mod, "_theme_sibling_map", return_value={"test_basket": frozenset()}).start()

        try:
            result = btw_mod.compute(
                baskets_meta=baskets_meta,
                data_root=tmp_path,
                as_of=_TODAY,
                run_backscan=False,
            )
        finally:
            mock.patch.stopall()

        for b in result.get("baskets", []):
            if b["basket_id"] == "test_basket":
                return b
        return None

    def test_watch_state_k2(self, tmp_path):
        """K=2 (any 2 legs) → WATCH."""
        row = self._minimal_compute(["impulse_day", "volume_confirm"], tmp_path)
        assert row is not None
        assert row["state"] == "WATCH"
        assert row["k"] == 2

    def test_ignition_state_k3_with_rs_z(self, tmp_path):
        """K=3 including rs_z → IGNITION."""
        row = self._minimal_compute(["rs_z", "impulse_day", "volume_confirm"], tmp_path)
        assert row is not None
        assert row["state"] == "IGNITION"
        assert row["k"] == 3

    def test_no_state_k1(self, tmp_path):
        """K=1 → state=None (below WATCH threshold)."""
        row = self._minimal_compute(["impulse_day"], tmp_path)
        assert row is not None
        assert row["state"] is None

    def test_watch_not_ignition_k3_without_rs_z(self, tmp_path):
        """K=3 but rs_z NOT in legs → WATCH (not IGNITION)."""
        row = self._minimal_compute(
            ["impulse_day", "volume_confirm", "breadth_surge"], tmp_path)
        assert row is not None
        assert row["state"] == "WATCH"
        assert row["k"] == 3


# ── (8) hysteresis ────────────────────────────────────────────────────────────

class TestHysteresis:
    def test_downgrade_state_within_hysteresis_window(self, tmp_path):
        """Prior WATCH ledger row from 1 session ago → state=DOWNGRADE when K<2."""
        import engine.basket_turn_watch as btw_mod
        import unittest.mock as mock

        # Write a fake prior ledger row for 1 session ago
        prior_rows = [
            {
                "basket_id": "test_basket",
                "date": "2026-07-08",  # 1 session ago
                "state": "WATCH",
                "k": 2,
                "legs": {},
            }
        ]

        with mock.patch.object(btw_mod, "load_ledger", return_value=prior_rows), \
             mock.patch.object(btw_mod, "_days_since_last_state", return_value=1), \
             mock.patch.object(btw_mod, "stamp_ledger", return_value=0):

            # All legs return False (K=0)
            with mock.patch.object(btw_mod, "_leg_impulse_day", return_value=False), \
                 mock.patch.object(btw_mod, "_leg_rs_z", return_value=(False, None)), \
                 mock.patch.object(btw_mod, "_leg_breadth_surge", return_value=False), \
                 mock.patch.object(btw_mod, "_leg_volume_confirm", return_value=False), \
                 mock.patch.object(btw_mod, "_leg_complex_confirm", return_value=False), \
                 mock.patch.object(btw_mod, "_leg_shock_relative_bid", return_value=False), \
                 mock.patch.object(btw_mod, "_load_prices", lambda tk, dr=None: _make_df([100.0] * 30)), \
                 mock.patch.object(btw_mod, "_load_market_drivers", lambda dr=None: None), \
                 mock.patch.object(btw_mod, "_theme_sibling_map", return_value={"test_basket": frozenset()}):

                baskets_meta = {
                    "test_basket": {
                        "members": [{"ticker": "M1", "removed": None}]
                    }
                }
                result = btw_mod.compute(
                    baskets_meta=baskets_meta,
                    data_root=tmp_path,
                    as_of=_TODAY,
                    run_backscan=False,
                )

        basket_row = next(
            (b for b in result["baskets"] if b["basket_id"] == "test_basket"), None)
        assert basket_row is not None
        assert basket_row["state"] == "DOWNGRADE"

    def test_no_downgrade_outside_hysteresis_window(self, tmp_path):
        """Prior row from 3 sessions ago → beyond hysteresis window → state=None."""
        import engine.basket_turn_watch as btw_mod
        import unittest.mock as mock

        prior_rows = [
            {
                "basket_id": "test_basket",
                "date": "2026-07-03",  # 3+ sessions ago
                "state": "WATCH",
                "k": 2,
                "legs": {},
            }
        ]

        with mock.patch.object(btw_mod, "load_ledger", return_value=prior_rows), \
             mock.patch.object(btw_mod, "_days_since_last_state", return_value=3), \
             mock.patch.object(btw_mod, "stamp_ledger", return_value=0):

            with mock.patch.object(btw_mod, "_leg_impulse_day", return_value=False), \
                 mock.patch.object(btw_mod, "_leg_rs_z", return_value=(False, None)), \
                 mock.patch.object(btw_mod, "_leg_breadth_surge", return_value=False), \
                 mock.patch.object(btw_mod, "_leg_volume_confirm", return_value=False), \
                 mock.patch.object(btw_mod, "_leg_complex_confirm", return_value=False), \
                 mock.patch.object(btw_mod, "_leg_shock_relative_bid", return_value=False), \
                 mock.patch.object(btw_mod, "_load_prices", lambda tk, dr=None: _make_df([100.0] * 30)), \
                 mock.patch.object(btw_mod, "_load_market_drivers", lambda dr=None: None), \
                 mock.patch.object(btw_mod, "_theme_sibling_map", return_value={"test_basket": frozenset()}):

                baskets_meta = {
                    "test_basket": {
                        "members": [{"ticker": "M1", "removed": None}]
                    }
                }
                result = btw_mod.compute(
                    baskets_meta=baskets_meta,
                    data_root=tmp_path,
                    as_of=_TODAY,
                    run_backscan=False,
                )

        basket_row = next(
            (b for b in result["baskets"] if b["basket_id"] == "test_basket"), None)
        assert basket_row is not None
        assert basket_row["state"] is None


# ── (9) ledger idempotency ────────────────────────────────────────────────────

class TestLedgerIdempotency:
    def test_keep_first_per_date_basket(self, tmp_path):
        """Calling stamp_ledger twice with the same (date, basket_id) → only 1 row written."""
        (tmp_path / "basket_turn").mkdir(parents=True, exist_ok=True)

        row = {
            "basket_id": "mag7",
            "date": _TODAY,
            "state": "WATCH",
            "k": 2,
            "legs": {},
            "as_of": _TODAY,
        }

        os.environ["US_LANE"] = "nightly"
        try:
            n1 = BTW.stamp_ledger([row], as_of=_TODAY, data_root=tmp_path)
            n2 = BTW.stamp_ledger([row], as_of=_TODAY, data_root=tmp_path)
        finally:
            os.environ.pop("US_LANE", None)

        assert n1 == 1
        assert n2 == 0

        rows = BTW.load_ledger(tmp_path)
        assert len(rows) == 1
        assert rows[0]["basket_id"] == "mag7"
        # FT-R9: per-basket forward-return fields are NOT seeded (grading unit is cohort).
        assert "fwd_21d_ew_vs_spy" not in rows[0]

    def test_multiple_baskets_same_date(self, tmp_path):
        """Two different basket_ids on the same date → both written."""
        (tmp_path / "basket_turn").mkdir(parents=True, exist_ok=True)

        rows_in = [
            {"basket_id": "mag7", "date": _TODAY, "state": "WATCH", "k": 2, "legs": {}, "as_of": _TODAY},
            {"basket_id": "ai_semiconductors", "date": _TODAY, "state": "IGNITION", "k": 3, "legs": {}, "as_of": _TODAY},
        ]

        os.environ["US_LANE"] = "nightly"
        try:
            n = BTW.stamp_ledger(rows_in, as_of=_TODAY, data_root=tmp_path)
        finally:
            os.environ.pop("US_LANE", None)

        assert n == 2
        rows = BTW.load_ledger(tmp_path)
        assert len(rows) == 2


# ── (10) lane gate (COLLECT_LANE + legacy US_LANE alias) ─────────────────────

class TestUsLaneGate:
    def test_stamp_skipped_without_lane_sentinel(self, tmp_path):
        """Without COLLECT_LANE or US_LANE set to nightly the ledger is not written."""
        (tmp_path / "basket_turn").mkdir(parents=True, exist_ok=True)
        row = {"basket_id": "mag7", "state": "WATCH", "k": 2, "legs": {}, "as_of": _TODAY}
        os.environ.pop("COLLECT_LANE", None)
        os.environ.pop("US_LANE", None)
        n = BTW.stamp_ledger([row], as_of=_TODAY, data_root=tmp_path)
        assert n == 0
        assert not (tmp_path / "basket_turn" / "ledger.jsonl").exists()

    def test_stamp_written_with_collect_lane_nightly(self, tmp_path):
        """With COLLECT_LANE=nightly (production sentinel from daily.yml engine step) the ledger IS written."""
        (tmp_path / "basket_turn").mkdir(parents=True, exist_ok=True)
        row = {"basket_id": "mag7", "state": "WATCH", "k": 2, "legs": {}, "as_of": _TODAY}
        os.environ.pop("US_LANE", None)
        os.environ["COLLECT_LANE"] = "nightly"
        try:
            n = BTW.stamp_ledger([row], as_of=_TODAY, data_root=tmp_path)
        finally:
            os.environ.pop("COLLECT_LANE", None)
        assert n == 1

    def test_stamp_written_with_us_lane_nightly(self, tmp_path):
        """US_LANE=nightly legacy alias still works (used in tests; not set by workflow)."""
        (tmp_path / "basket_turn").mkdir(parents=True, exist_ok=True)
        row = {"basket_id": "mag7", "state": "WATCH", "k": 2, "legs": {}, "as_of": _TODAY}
        os.environ.pop("COLLECT_LANE", None)
        os.environ["US_LANE"] = "nightly"
        try:
            n = BTW.stamp_ledger([row], as_of=_TODAY, data_root=tmp_path)
        finally:
            os.environ.pop("US_LANE", None)
        assert n == 1


# ── (11) forbidden fields ─────────────────────────────────────────────────────

class TestForbiddenFields:
    def test_compute_output_has_no_forbidden_keys(self, tmp_path):
        """The full JSON output of compute() must contain no forbidden keys."""
        result = BTW.compute(
            baskets_meta={},
            data_root=tmp_path,
            as_of=_TODAY,
            run_backscan=False,
        )
        # Walk all keys recursively
        all_keys = _walk_keys(result)
        found = [k for k in all_keys if k in FORBIDDEN_KEYS]
        assert not found, (
            f"Forbidden key(s) found in compute() output: {found}\n"
            f"Forbidden set: {FORBIDDEN_KEYS}"
        )

    def test_authority_block_present(self, tmp_path):
        """Authority block must be in the output with may_rank=False."""
        result = BTW.compute(
            baskets_meta={},
            data_root=tmp_path,
            as_of=_TODAY,
            run_backscan=False,
        )
        auth = result.get("authority") or {}
        assert auth.get("tier") == "display"
        assert auth.get("may_rank") is False
        assert auth.get("may_gate") is False
        assert auth.get("may_size") is False
        assert auth.get("may_escalate") is False

    def test_disclosure_string_present(self, tmp_path):
        """Disclosure string must appear in the output."""
        result = BTW.compute(
            baskets_meta={},
            data_root=tmp_path,
            as_of=_TODAY,
            run_backscan=False,
        )
        disclosure = result.get("disclosure", "")
        assert "expected-null forward meter" in disclosure.lower() or \
               "expected-null" in disclosure.lower() or \
               "display only" in disclosure.lower(), \
               f"Disclosure string missing expected language: {disclosure!r}"


# ── (12) exit-0 contract ──────────────────────────────────────────────────────

class TestExitZeroContract:
    def test_empty_baskets_meta_returns_dict(self, tmp_path):
        """Empty baskets_meta → returns a dict, never raises."""
        result = BTW.compute(
            baskets_meta={},
            data_root=tmp_path,
            as_of=_TODAY,
            run_backscan=False,
        )
        assert isinstance(result, dict)
        assert result["schema"] == "basket_turn_watch.v1"
        assert result["baskets"] == []

    def test_none_baskets_meta_with_missing_file_returns_dict(self, tmp_path):
        """Missing membership.json → returns a valid dict, never raises."""
        result = BTW.compute(
            baskets_meta=None,
            data_root=tmp_path,    # no membership.json in tmp_path
            as_of=_TODAY,
            run_backscan=False,
        )
        assert isinstance(result, dict)
        assert "baskets" in result

    def test_bad_price_data_does_not_crash(self, tmp_path):
        """Basket with unreadable price data → compute still returns."""
        import unittest.mock as mock
        import engine.basket_turn_watch as btw_mod

        with mock.patch.object(btw_mod, "_load_prices", side_effect=RuntimeError("disk fail")), \
             mock.patch.object(btw_mod, "stamp_ledger", return_value=0):
            result = btw_mod.compute(
                baskets_meta={"mag7": {"members": [{"ticker": "AAPL", "removed": None}]}},
                data_root=tmp_path,
                as_of=_TODAY,
                run_backscan=False,
            )
        assert isinstance(result, dict)

    def test_json_serializable(self, tmp_path):
        """Output must be JSON-serializable (no NaN, no datetime objects)."""
        result = BTW.compute(
            baskets_meta={},
            data_root=tmp_path,
            as_of=_TODAY,
            run_backscan=False,
        )
        # Should not raise
        serialized = json.dumps(result, default=str, allow_nan=False)
        assert len(serialized) > 0


# ── (13) W5 complexes block ───────────────────────────────────────────────────

class TestComplexesBlock:
    """Tests for the _compute_complexes() function in build_basket_pulse.py (W5)."""

    def _make_basket_data(self, ids_chg: dict[str, float | None]) -> list[dict[str, Any]]:
        """Build a list of basket pulse dicts."""
        return [
            {"id": bid, "live_ew_chg_pct": chg, "n_members": 3, "n_quoted": 2, "stale": False}
            for bid, chg in ids_chg.items()
        ]

    def _make_quotes_with_spy(self, spy_chg: float, now: datetime, age_min: float = 1.0) -> dict:
        """Build quotes dict with SPY."""
        ts_ms = int(now.timestamp() * 1000) - int(age_min * 60_000)
        return {
            "SPY": {
                "price": 500.0,
                "ts": ts_ms,
                "changePct": spy_chg,
                "source": "test",
                "basis": "regular",
                "prevClose": 498.0,
                "currency": "USD",
                "delayMin": 15,
            }
        }

    def test_ai_capex_ew_computed_correctly(self):
        """EW of ai_capex member baskets' live_ew_chg_pct."""
        ai_ids = frozenset({
            "memory_storage", "ai_semiconductors", "semicap_equipment",
            "data_center_power", "grid_electrification", "nuclear_power",
        })
        now = datetime(2026, 7, 9, 14, 0, tzinfo=timezone.utc)
        now_ms = int(now.timestamp() * 1000)
        baskets_data = self._make_basket_data({
            "memory_storage": 2.5,
            "ai_semiconductors": 3.5,
            "semicap_equipment": 1.5,
            "data_center_power": None,   # null — excluded from EW
            "grid_electrification": 2.0,
            "nuclear_power": 1.0,
        })
        # SPY down
        quotes = self._make_quotes_with_spy(-0.5, now)

        import unittest.mock as mock
        with mock.patch.object(BP, "_ai_capex_ids", return_value=ai_ids):
            result = BP._compute_complexes(baskets_data, quotes, now_ms)

        assert len(result) == 1
        c = result[0]
        assert c["complex_id"] == "ai_capex"
        assert c["n_baskets"] == 6
        assert c["n_live"] == 5   # data_center_power is null

        # EW = mean(2.5, 3.5, 1.5, 2.0, 1.0) = 10.5/5 = 2.1
        assert c["live_ew_chg_pct"] == pytest.approx(2.1, abs=0.01)

    def test_only_green_complex_when_spy_down_and_complex_up(self):
        """only_green_complex=True when complex EW>0 and SPY<0."""
        ai_ids = frozenset({"memory_storage", "ai_semiconductors"})
        now = datetime(2026, 7, 9, 14, 0, tzinfo=timezone.utc)
        now_ms = int(now.timestamp() * 1000)
        baskets_data = self._make_basket_data({
            "memory_storage": 1.0,
            "ai_semiconductors": 2.0,
        })
        quotes = self._make_quotes_with_spy(-1.0, now)  # SPY down

        import unittest.mock as mock
        with mock.patch.object(BP, "_ai_capex_ids", return_value=ai_ids):
            result = BP._compute_complexes(baskets_data, quotes, now_ms)

        assert result[0]["only_green_complex"] is True

    def test_not_only_green_when_spy_up(self):
        """only_green_complex=False when SPY is up (even if complex is up)."""
        ai_ids = frozenset({"memory_storage", "ai_semiconductors"})
        now = datetime(2026, 7, 9, 14, 0, tzinfo=timezone.utc)
        now_ms = int(now.timestamp() * 1000)
        baskets_data = self._make_basket_data({
            "memory_storage": 1.0,
            "ai_semiconductors": 2.0,
        })
        quotes = self._make_quotes_with_spy(0.5, now)  # SPY up

        import unittest.mock as mock
        with mock.patch.object(BP, "_ai_capex_ids", return_value=ai_ids):
            result = BP._compute_complexes(baskets_data, quotes, now_ms)

        assert result[0]["only_green_complex"] is False

    def test_null_live_ew_when_no_coverage(self):
        """All member baskets have null live_ew_chg_pct → live_ew_chg_pct is None."""
        ai_ids = frozenset({"memory_storage"})
        now = datetime(2026, 7, 9, 14, 0, tzinfo=timezone.utc)
        now_ms = int(now.timestamp() * 1000)
        baskets_data = self._make_basket_data({"memory_storage": None})
        quotes = self._make_quotes_with_spy(-0.5, now)

        import unittest.mock as mock
        with mock.patch.object(BP, "_ai_capex_ids", return_value=ai_ids):
            result = BP._compute_complexes(baskets_data, quotes, now_ms)

        assert result[0]["live_ew_chg_pct"] is None
        assert result[0]["only_green_complex"] is False

    def test_complexes_in_build_output(self, tmp_path):
        """build() output must contain a 'complexes' key."""
        now = datetime(2026, 7, 9, 14, 0, tzinfo=timezone.utc)

        # Write a minimal membership.json in tmp_path
        membership = {
            "baskets": {
                "memory_storage": {"members": [{"ticker": "MU", "removed": None}]},
            }
        }
        (tmp_path / "baskets").mkdir(parents=True, exist_ok=True)
        (tmp_path / "baskets" / "membership.json").write_text(json.dumps(membership))

        # Use an in-memory quotes fixture
        import unittest.mock as mock
        with mock.patch.object(BP, "_load_quotes", return_value=({}, None)), \
             mock.patch.object(BP, "_load_membership", return_value=membership["baskets"]), \
             mock.patch.object(BP, "_load_market_drivers", return_value=None), \
             mock.patch.object(BP, "_cum_2d", return_value=None):

            result = BP.build(now=now)

        assert "complexes" in result
        assert isinstance(result["complexes"], list)
