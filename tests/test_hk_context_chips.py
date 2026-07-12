"""Tests for engine/hk_context_chips.py (HKRV-W4).

Covers:
  1. Each chip is fail-open on a missing store (returns None or absent key).
  2. rate_path state mapping thresholds.
  3. vhsi_pctile sanity on a synthetic series.
  4. compute_all() returns a dict; missing chips are absent, not None entries.
  5. All returned chips carry display_only=True (AUTHORITY FENCE HKRV-R5).
"""
from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

# Ensure repo root on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import hk_context_chips as cc


# ---------------------------------------------------------------------------
# helpers — synthetic time-series builders
# ---------------------------------------------------------------------------

def _date_range(n: int, freq: str = "B") -> pd.DatetimeIndex:
    return pd.date_range("2024-01-01", periods=n, freq=freq)


def _series(n: int = 300, base: float = 100.0, noise: float = 1.0) -> pd.Series:
    rng = np.random.default_rng(42)
    vals = base + np.cumsum(rng.normal(0, noise, n))
    return pd.Series(vals, index=_date_range(n))


def _df(col: str, n: int = 300, **kwargs) -> pd.DataFrame:
    return _series(n, **kwargs).rename(col).to_frame()


# ---------------------------------------------------------------------------
# 1. Fail-open: each chip returns None when the store is absent
# ---------------------------------------------------------------------------

class TestFailOpen:
    """Each chip must degrade gracefully (return None) when store.read returns None."""

    def _patch_store_none(self):
        """Context-manager: make lib.store.read always return None."""
        return patch("engine.hk_context_chips._read_store", return_value=None)

    def test_hstech_rs_absent_store(self):
        with self._patch_store_none():
            assert cc.hstech_rs() is None

    def test_ah_compression_absent_store(self):
        with self._patch_store_none():
            assert cc.ah_compression() is None

    def test_southbound_agg_absent_store(self):
        with self._patch_store_none():
            assert cc.southbound_agg() is None

    def test_peg_funding_absent_store(self):
        with self._patch_store_none():
            assert cc.peg_funding() is None

    def test_rate_path_absent_store(self):
        with self._patch_store_none():
            assert cc.rate_path() is None

    def test_cnh_basis_absent_store(self):
        with self._patch_store_none():
            assert cc.cnh_basis() is None

    def test_em_dm_rs_absent_store(self):
        with self._patch_store_none():
            assert cc.em_dm_rs() is None

    def test_ashr_fxi_absent_store(self):
        with self._patch_store_none():
            assert cc.ashr_fxi() is None

    def test_vhsi_pctile_absent_store(self):
        with self._patch_store_none():
            assert cc.vhsi_pctile() is None

    def test_compute_all_all_absent(self):
        """compute_all() returns {} when every store is absent."""
        with self._patch_store_none():
            result = cc.compute_all()
        assert isinstance(result, dict)
        # None chips are dropped — no None values in the dict
        assert all(v is not None for v in result.values())


# ---------------------------------------------------------------------------
# 2. rate_path state mapping
# ---------------------------------------------------------------------------

class TestRatePathStateMapping:
    """Verify the three-state logic for rate_path."""

    def _make_stores(self, m12_rate: float, dff_rate: float) -> dict:
        """Return a mock _read_store that returns synthetic ZQ and DFF data."""
        zq_df = pd.DataFrame(
            {"m12": [m12_rate] * 5},
            index=_date_range(5),
        )
        dff_df = pd.DataFrame(
            {"fed_funds": [dff_rate] * 5},
            index=_date_range(5),
        )

        def _mock_read(group: str, name: str) -> pd.DataFrame | None:
            if group == "rate_futures" and name == "zq_path":
                return zq_df
            if group == "fred" and name == "DFF":
                return dff_df
            return None

        return _mock_read

    def test_hikes_priced(self):
        """m12 > DFF by more than 12.5bp → hikes_priced."""
        mock = self._make_stores(m12_rate=4.50, dff_rate=4.30)  # +20bp → hikes
        with patch("engine.hk_context_chips._read_store", side_effect=mock):
            chip = cc.rate_path()
        assert chip is not None
        assert chip["state"] == "hikes_priced", f"expected hikes_priced, got {chip['state']}"

    def test_on_hold(self):
        """m12 ≈ DFF (within 12.5bp) → on_hold."""
        mock = self._make_stores(m12_rate=4.30, dff_rate=4.25)  # +5bp → on_hold
        with patch("engine.hk_context_chips._read_store", side_effect=mock):
            chip = cc.rate_path()
        assert chip is not None
        assert chip["state"] == "on_hold", f"expected on_hold, got {chip['state']}"

    def test_cuts_priced(self):
        """m12 < DFF by more than 12.5bp → cuts_priced."""
        mock = self._make_stores(m12_rate=3.75, dff_rate=4.30)  # -55bp → cuts
        with patch("engine.hk_context_chips._read_store", side_effect=mock):
            chip = cc.rate_path()
        assert chip is not None
        assert chip["state"] == "cuts_priced", f"expected cuts_priced, got {chip['state']}"

    def test_display_only_flag(self):
        """rate_path chip must carry display_only=True (AUTHORITY FENCE HKRV-R5)."""
        mock = self._make_stores(m12_rate=3.75, dff_rate=4.30)
        with patch("engine.hk_context_chips._read_store", side_effect=mock):
            chip = cc.rate_path()
        assert chip is not None
        assert chip.get("display_only") is True

    def test_implied_bp_sign(self):
        """implied_bp_12m is (m12 − dff)*100; negative when cuts priced."""
        mock = self._make_stores(m12_rate=3.75, dff_rate=4.30)
        with patch("engine.hk_context_chips._read_store", side_effect=mock):
            chip = cc.rate_path()
        assert chip is not None
        # (3.75 - 4.30) * 100 = -55bp → negative = cuts priced
        assert chip["value"] < 0

    def test_hikes_priced_positive_bp(self):
        """implied_bp_12m is positive when hikes priced (m12 > DFF)."""
        mock = self._make_stores(m12_rate=4.50, dff_rate=4.30)
        with patch("engine.hk_context_chips._read_store", side_effect=mock):
            chip = cc.rate_path()
        assert chip is not None
        assert chip["value"] > 0


# ---------------------------------------------------------------------------
# 3. vhsi_pctile sanity on synthetic series
# ---------------------------------------------------------------------------

class TestVhsiPctile:
    """Verify rolling-percentile logic in vhsi_pctile."""

    def _make_hk_store(self, close_series: pd.Series) -> "callable":
        df = close_series.rename("close").to_frame()

        def _mock_read(group: str, name: str) -> pd.DataFrame | None:
            if group == "hk" and name == "^HSIL":
                return df
            return None

        return _mock_read

    def test_high_percentile_state(self):
        """When the latest value is the max of a 300-bar series → ≥80th pctile state."""
        rng = np.random.default_rng(0)
        base = pd.Series(15.0 + rng.uniform(0, 5, 299), index=_date_range(299))
        # append a spike that is definitely the maximum
        spike = pd.Series([100.0], index=_date_range(1, freq="B")[-1:])
        s = pd.concat([base, spike])
        mock = self._make_hk_store(s)
        with patch("engine.hk_context_chips._read_store", side_effect=mock):
            chip = cc.vhsi_pctile()
        assert chip is not None
        assert "elevated" in chip["state_en"], f"expected elevated, got {chip['state_en']}"
        assert chip.get("pctile_252d") is not None
        assert chip["pctile_252d"] >= 0.8

    def test_low_percentile_state(self):
        """When the latest value is the min → ≤20th pctile state."""
        rng = np.random.default_rng(1)
        base = pd.Series(20.0 + rng.uniform(0, 10, 299), index=_date_range(299))
        low = pd.Series([1.0], index=_date_range(1, freq="B")[-1:])
        s = pd.concat([base, low])
        mock = self._make_hk_store(s)
        with patch("engine.hk_context_chips._read_store", side_effect=mock):
            chip = cc.vhsi_pctile()
        assert chip is not None
        assert "depressed" in chip["state_en"], f"expected depressed, got {chip['state_en']}"
        assert chip["pctile_252d"] <= 0.2

    def test_mid_range_state(self):
        """When the latest value is at ~50th percentile → mid-range state."""
        # Build a series where the last value is the median of the 252d tail.
        rng = np.random.default_rng(7)
        vals = rng.uniform(10, 30, 300)
        # Replace the last value with the median of the last 252 values so it
        # lands firmly in the mid-range (pctile ~0.5).
        vals[-1] = float(np.median(vals[-252:]))
        s = pd.Series(vals, index=_date_range(300))
        mock = self._make_hk_store(s)
        with patch("engine.hk_context_chips._read_store", side_effect=mock):
            chip = cc.vhsi_pctile()
        assert chip is not None
        # pctile_252d should be in (0.2, 0.8)
        p = chip.get("pctile_252d")
        assert p is not None
        assert 0.2 < p < 0.8, f"expected mid-range pctile, got {p}"

    def test_too_short_series_returns_none(self):
        """Fewer than 30 bars → chip returns None."""
        s = pd.Series([20.0] * 20, index=_date_range(20))
        mock = self._make_hk_store(s)
        with patch("engine.hk_context_chips._read_store", side_effect=mock):
            chip = cc.vhsi_pctile()
        assert chip is None

    def test_display_only_flag(self):
        """vhsi_pctile chip must carry display_only=True."""
        s = pd.Series(np.linspace(10, 30, 300), index=_date_range(300))
        mock = self._make_hk_store(s)
        with patch("engine.hk_context_chips._read_store", side_effect=mock):
            chip = cc.vhsi_pctile()
        assert chip is not None
        assert chip.get("display_only") is True


# ---------------------------------------------------------------------------
# 4. compute_all: no None values in returned dict
# ---------------------------------------------------------------------------

class TestComputeAll:
    """compute_all() guarantees no None chip values in the returned dict."""

    def test_no_none_values_when_all_absent(self):
        with patch("engine.hk_context_chips._read_store", return_value=None):
            result = cc.compute_all()
        assert isinstance(result, dict)
        for k, v in result.items():
            assert v is not None, f"chip '{k}' returned None value in compute_all"

    def test_keys_match_chip_key_field(self):
        """When chips succeed, their dict key matches the 'key' field inside."""
        rng = np.random.default_rng(42)

        def _mock_read(group, name):
            # Return minimal DataFrames for the chips that need them
            n = 300
            idx = _date_range(n)
            if group == "hk" and name == "^HSIL":
                return pd.DataFrame({"close": rng.uniform(15, 30, n)}, index=idx)
            if group == "rate_futures" and name == "zq_path":
                return pd.DataFrame({"m12": np.full(n, 3.75)}, index=idx)
            if group == "fred" and name == "DFF":
                return pd.DataFrame({"fed_funds": np.full(n, 4.30)}, index=idx)
            return None

        with patch("engine.hk_context_chips._read_store", side_effect=_mock_read):
            result = cc.compute_all()

        for k, chip in result.items():
            assert chip["key"] == k, f"chip dict key '{k}' != chip['key'] '{chip['key']}'"


# ---------------------------------------------------------------------------
# 5. authority fence: all chips must carry display_only=True
# ---------------------------------------------------------------------------

class TestAuthorityFence:
    """Every chip that successfully returns a result must have display_only=True."""

    def _mock_read_all(self, group: str, name: str) -> pd.DataFrame | None:
        """Return a minimal DataFrame for any known store request."""
        rng = np.random.default_rng(99)
        n = 300
        idx = _date_range(n)
        # Build appropriate structures per store
        if group == "hk" and name in ("^HSI", "3033.HK", "^HSIL"):
            return pd.DataFrame({"close": 100 + rng.uniform(-5, 5, n)}, index=idx)
        if group == "hk_ah_official" and name == "ah_spot":
            return pd.DataFrame({"hsahp": 90 + rng.uniform(-10, 10, n)}, index=idx)
        if group == "hk_connect" and name in ("southbound_sh", "southbound_sz"):
            return pd.DataFrame({"net": rng.uniform(-5000, 5000, n)}, index=idx)
        if group == "hkma" and name == "interbank_liquidity":
            return pd.DataFrame({"hibor_1m": np.full(n, 2.7)}, index=idx)
        if group == "fred" and name == "SOFR":
            return pd.DataFrame({"sofr": np.full(n, 3.6)}, index=idx)
        if group == "fred" and name == "DFF":
            return pd.DataFrame({"fed_funds": np.full(n, 4.30)}, index=idx)
        if group == "rate_futures" and name == "zq_path":
            return pd.DataFrame({"m12": np.full(n, 3.75)}, index=idx)
        if group == "yahoo" and name in ("CNH=F", "CNH=X"):
            return pd.DataFrame({"close": 7.2 + rng.uniform(-0.05, 0.05, n)}, index=idx)
        if group == "yahoo" and name in ("EEM", "SPY", "ASHR", "FXI"):
            return pd.DataFrame({"close": 50 + rng.uniform(-5, 5, n)}, index=idx)
        return None

    def test_all_returned_chips_have_display_only_true(self):
        with patch("engine.hk_context_chips._read_store", side_effect=self._mock_read_all):
            result = cc.compute_all()
        # There should be at least a few chips succeeding with the mock data
        assert result, "compute_all returned empty dict with full mock data"
        for k, chip in result.items():
            assert chip.get("display_only") is True, (
                f"chip '{k}' missing display_only=True (AUTHORITY FENCE HKRV-R5 violation)"
            )
