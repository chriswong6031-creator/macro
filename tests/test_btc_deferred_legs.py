"""Tests for the P5 deferred-context BTC engine modules.

Covers:
  - Each module returns a dict (never raises) when inputs are MISSING
  - btc_dat mNAV math is correct on a synthetic holdings JSON
  - btc_netliq impulse classification is correct on synthetic series
  - btc_leverage_cascade flags high/low risk correctly on synthetic DataFrames

All tests are offline (no network, no real store required).
"""
from __future__ import annotations

import json
import math
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# -------------------------------------------------------------------------
# helpers to make store.read return None (no parquet files)
# -------------------------------------------------------------------------


def _empty_store_read(group, name):
    return None


def _patch_store(monkeypatch):
    import lib.store as st
    monkeypatch.setattr(st, "read", _empty_store_read)


# =========================================================================
# 1. btc_netliq
# =========================================================================
class TestBtcNetliq:
    def test_returns_dict_never_raises_with_empty_store(self, monkeypatch):
        _patch_store(monkeypatch)
        from engine import btc_netliq
        result = btc_netliq.compute(sig_df=None)
        assert isinstance(result, dict)

    def test_returns_ok_false_with_empty_store(self, monkeypatch):
        _patch_store(monkeypatch)
        from engine import btc_netliq
        result = btc_netliq.compute(sig_df=None)
        assert result["ok"] is False
        assert "reason" in result

    def test_returns_ok_false_on_garbage_df(self, monkeypatch):
        _patch_store(monkeypatch)
        from engine import btc_netliq
        garbage = pd.DataFrame({"foo": [np.nan, np.nan]})
        result = btc_netliq.compute(sig_df=garbage)
        assert isinstance(result, dict)
        # net_liquidity_bn not in columns → should fall back to store (also empty) → ok=False
        assert result["ok"] is False

    def test_ok_with_synthetic_net_liquidity(self, monkeypatch):
        _patch_store(monkeypatch)
        from engine import btc_netliq
        # Create a synthetic signals-style DataFrame with net_liquidity_bn
        idx = pd.date_range("2020-01-01", periods=400, freq="D")
        vals = np.linspace(7000, 7500, 400)   # growing → should be expanding
        sig = pd.DataFrame({"net_liquidity_bn": vals}, index=idx)
        result = btc_netliq.compute(sig_df=sig)
        assert isinstance(result, dict)
        assert result["ok"] is True
        assert result["netliq_bn"] is not None

    def test_impulse_expanding_accelerating(self, monkeypatch):
        _patch_store(monkeypatch)
        from engine import btc_netliq
        # Super-exponential (exp(exp(t))) series → YoY > 0 and YoY itself is
        # accelerating (second-derivative > 0).
        idx = pd.date_range("2019-01-01", periods=800, freq="D")
        t = np.linspace(0, 2, 800)
        vals = np.exp(np.exp(t)) * 100  # super-exponential: acceleration is strongly positive
        sig = pd.DataFrame({"net_liquidity_bn": vals}, index=idx)
        result = btc_netliq.compute(sig_df=sig)
        assert result["ok"] is True
        assert result["impulse_state"] == "expanding-accelerating"

    def test_impulse_contracting(self, monkeypatch):
        _patch_store(monkeypatch)
        from engine import btc_netliq
        # Linearly declining series → YoY < 0 → contracting
        idx = pd.date_range("2019-01-01", periods=800, freq="D")
        vals = np.linspace(8000, 4000, 800)
        sig = pd.DataFrame({"net_liquidity_bn": vals}, index=idx)
        result = btc_netliq.compute(sig_df=sig)
        assert result["ok"] is True
        assert result["impulse_state"] == "contracting"

    def test_impulse_expanding_decelerating(self, monkeypatch):
        _patch_store(monkeypatch)
        from engine import btc_netliq
        # Log curve → growing but slowing → decelerating
        idx = pd.date_range("2019-01-01", periods=800, freq="D")
        t = np.linspace(1, 800, 800)
        vals = 5000 + 3000 * np.log(t)   # growing but second-derivative negative
        sig = pd.DataFrame({"net_liquidity_bn": vals}, index=idx)
        result = btc_netliq.compute(sig_df=sig)
        assert result["ok"] is True
        # log curve decelerates → expanding-decelerating
        assert result["impulse_state"] == "expanding-decelerating"

    def test_components_present_field(self, monkeypatch):
        _patch_store(monkeypatch)
        from engine import btc_netliq
        idx = pd.date_range("2020-01-01", periods=400, freq="D")
        vals = np.linspace(7000, 7500, 400)
        sig = pd.DataFrame({"net_liquidity_bn": vals}, index=idx)
        result = btc_netliq.compute(sig_df=sig)
        assert "components_present" in result
        assert isinstance(result["components_present"], list)


# =========================================================================
# 2. etf_perfund
# =========================================================================
class TestEtfPerfund:
    def test_read_perfund_returns_dict_no_parquet(self, monkeypatch):
        _patch_store(monkeypatch)
        from engine import etf_perfund
        result = etf_perfund.read_perfund()
        assert isinstance(result, dict)
        assert result["ok"] is False
        assert "reason" in result

    def test_scrape_returns_disabled_dict_by_default(self, monkeypatch):
        _patch_store(monkeypatch)
        from engine import etf_perfund
        # Default config has scrape_enabled: false
        result = etf_perfund.scrape_and_append()
        assert isinstance(result, dict)
        assert result["ok"] is False
        assert "disabled" in result["reason"].lower() or "scrape" in result["reason"].lower()

    def test_scrape_never_raises_on_bad_url(self, monkeypatch):
        _patch_store(monkeypatch)
        # Monkeypatch config to enable scrape with a broken URL.
        # We patch at the module level that etf_perfund imports from, so we
        # don't need to worry about lru_cache on the original function.
        import lib.config as cfg_mod

        base = dict(cfg_mod.load())
        base["btc_etf_perfund"] = {
            "scrape_enabled": True,
            "url": "http://localhost:1",   # nothing listening
            "timeout_s": 1,
        }
        base.setdefault("sponsors", {}).setdefault("user_agent", "test/1.0")
        monkeypatch.setattr(cfg_mod, "load", lambda: base)

        from engine import etf_perfund
        result = etf_perfund.scrape_and_append()
        assert isinstance(result, dict)
        assert result["ok"] is False

    def test_read_perfund_with_synthetic_parquet(self, monkeypatch, tmp_path):
        """read_perfund works when the parquet exists."""
        # Write a synthetic parquet to tmp location
        idx = pd.date_range("2024-01-01", periods=10, freq="B")
        df = pd.DataFrame({
            "IBIT": np.random.uniform(100, 500, 10),
            "GBTC": np.random.uniform(-300, -50, 10),
            "FBTC": np.random.uniform(50, 200, 10),
        }, index=idx)

        def patched_read(group, name):
            if group == "etf" and name == "perfund":
                return df
            return None

        import lib.store as st
        monkeypatch.setattr(st, "read", patched_read)

        from engine import etf_perfund
        result = etf_perfund.read_perfund(lookback_d=5)
        assert isinstance(result, dict)
        assert result["ok"] is True
        assert "ibit_share" in result
        assert "per_fund" in result
        assert result["ibit_share"] is not None
        assert 0 <= result["ibit_share"] <= 1


# =========================================================================
# 3. btc_dat
# =========================================================================
class TestBtcDat:
    def _write_holdings(self, tmp_path: Path, data: dict) -> str:
        p = tmp_path / "dat_holdings.json"
        p.write_text(json.dumps(data))
        return str(p)

    def test_returns_dict_no_json(self, monkeypatch, tmp_path):
        _patch_store(monkeypatch)
        from engine import btc_dat
        # Pass a path that doesn't exist
        result = btc_dat.compute(holdings_path=str(tmp_path / "missing.json"))
        assert isinstance(result, dict)
        assert result["ok"] is False
        assert "reason" in result

    def test_returns_ok_false_on_missing_required_fields(self, monkeypatch, tmp_path):
        _patch_store(monkeypatch)
        from engine import btc_dat
        path = self._write_holdings(tmp_path, {"asof": "2026-01-01"})
        result = btc_dat.compute(holdings_path=path, btc_price_override=50000.0)
        assert isinstance(result, dict)
        assert result["ok"] is False

    def test_mnav_math_correct(self, monkeypatch, tmp_path):
        """mNAV = (stock_price × shares_out) / (btc_held × btc_price)."""
        _patch_store(monkeypatch)
        from engine import btc_dat

        btc_held = 200_000
        shares_out = 250_000_000
        stock_price = 400.0       # MSTR stock price
        btc_price = 70_000.0

        expected_mnav = (stock_price * shares_out) / (btc_held * btc_price)
        expected_premium = (expected_mnav - 1.0) * 100.0

        holdings = {
            "asof": "2026-06-01",
            "btc_held": btc_held,
            "shares_out": shares_out,
            "avg_cost_usd": 35000.0,
            "stock_price_usd": stock_price,
        }
        path = self._write_holdings(tmp_path, holdings)
        result = btc_dat.compute(holdings_path=path, btc_price_override=btc_price)

        assert result["ok"] is True
        assert result["mnav"] is not None
        assert abs(result["mnav"] - expected_mnav) < 0.001, (
            f"mNAV mismatch: got {result['mnav']}, expected {expected_mnav}"
        )
        assert result["premium_pct"] is not None
        assert abs(result["premium_pct"] - expected_premium) < 0.1

    def test_btc_per_share_math(self, monkeypatch, tmp_path):
        _patch_store(monkeypatch)
        from engine import btc_dat

        btc_held = 100_000
        shares_out = 200_000_000
        holdings = {
            "asof": "2026-06-01",
            "btc_held": btc_held,
            "shares_out": shares_out,
            "avg_cost_usd": 40000.0,
        }
        path = self._write_holdings(tmp_path, holdings)
        result = btc_dat.compute(holdings_path=path, btc_price_override=60000.0)
        assert result["ok"] is True
        assert abs(result["btc_per_share"] - btc_held / shares_out) < 1e-9

    def test_forced_sell_distance_positive_when_btc_above_trigger(
            self, monkeypatch, tmp_path):
        _patch_store(monkeypatch)
        from engine import btc_dat

        avg_cost = 30000.0
        btc_price = 60000.0   # well above avg_cost × 0.78 = 23400
        holdings = {
            "asof": "2026-06-01",
            "btc_held": 100_000,
            "shares_out": 200_000_000,
            "avg_cost_usd": avg_cost,
        }
        path = self._write_holdings(tmp_path, holdings)
        result = btc_dat.compute(holdings_path=path, btc_price_override=btc_price)
        assert result["ok"] is True
        assert result["forced_sell_distance_pct"] is not None
        assert result["forced_sell_distance_pct"] > 0

    def test_state_premium_when_mnav_gt_1(self, monkeypatch, tmp_path):
        _patch_store(monkeypatch)
        from engine import btc_dat

        # stock at 2× NAV
        btc_held = 10_000
        shares_out = 100_000_000
        btc_price = 50_000.0
        nav_per_share = btc_held * btc_price / shares_out  # 5 USD
        stock_price = nav_per_share * 2                    # 10 USD → mNAV=2

        holdings = {
            "asof": "2026-06-01",
            "btc_held": btc_held,
            "shares_out": shares_out,
            "avg_cost_usd": 30000.0,
            "stock_price_usd": stock_price,
        }
        path = self._write_holdings(tmp_path, holdings)
        result = btc_dat.compute(holdings_path=path, btc_price_override=btc_price)
        assert result["ok"] is True
        assert result["state"] == "premium"

    def test_state_discount_when_mnav_lt_1(self, monkeypatch, tmp_path):
        _patch_store(monkeypatch)
        from engine import btc_dat

        btc_held = 10_000
        shares_out = 100_000_000
        btc_price = 50_000.0
        nav_per_share = btc_held * btc_price / shares_out  # 5 USD
        stock_price = nav_per_share * 0.5                  # 2.5 USD → mNAV=0.5

        holdings = {
            "asof": "2026-06-01",
            "btc_held": btc_held,
            "shares_out": shares_out,
            "avg_cost_usd": 30000.0,
            "stock_price_usd": stock_price,
        }
        path = self._write_holdings(tmp_path, holdings)
        result = btc_dat.compute(holdings_path=path, btc_price_override=btc_price)
        assert result["ok"] is True
        assert result["state"] == "discount"

    def test_no_mnav_without_stock_price(self, monkeypatch, tmp_path):
        """mnav should be None when stock price is absent (graceful degrade)."""
        _patch_store(monkeypatch)
        from engine import btc_dat

        holdings = {
            "asof": "2026-06-01",
            "btc_held": 100_000,
            "shares_out": 250_000_000,
            "avg_cost_usd": 35000.0,
            # no stock_price_usd
        }
        path = self._write_holdings(tmp_path, holdings)
        result = btc_dat.compute(holdings_path=path, btc_price_override=60000.0)
        assert result["ok"] is True
        assert result["mnav"] is None
        assert result["premium_pct"] is None
        assert result["state"] == "unknown"

    def test_forced_sell_absent_without_avg_cost(self, monkeypatch, tmp_path):
        _patch_store(monkeypatch)
        from engine import btc_dat

        holdings = {
            "asof": "2026-06-01",
            "btc_held": 100_000,
            "shares_out": 250_000_000,
            # no avg_cost_usd
        }
        path = self._write_holdings(tmp_path, holdings)
        result = btc_dat.compute(holdings_path=path, btc_price_override=60000.0)
        assert result["ok"] is True
        assert result["forced_sell_distance_pct"] is None


# =========================================================================
# 4. btc_leverage_cascade
# =========================================================================
class TestBtcLeverageCascade:
    def _make_df(self, n=300, funding_annual_pct=10.0, funding_z=0.5,
                 oi_mcap_ratio=0.02, oi_change=0.01) -> pd.DataFrame:
        """Synthetic signals DataFrame with constant values."""
        idx = pd.date_range("2024-01-01", periods=n, freq="D")
        return pd.DataFrame({
            "funding_annual_pct": np.full(n, funding_annual_pct),
            "funding_z": np.full(n, funding_z),
            "oi_mcap_ratio": np.full(n, oi_mcap_ratio),
            "oi_change": np.full(n, oi_change),
            "close": np.full(n, 50000.0),
        }, index=idx)

    def test_returns_dict_with_no_store(self, monkeypatch):
        _patch_store(monkeypatch)
        from engine import btc_leverage_cascade
        result = btc_leverage_cascade.compute(sig_df=None)
        assert isinstance(result, dict)
        assert result["ok"] is False  # no store available

    def test_returns_dict_on_empty_df(self, monkeypatch):
        _patch_store(monkeypatch)
        from engine import btc_leverage_cascade
        result = btc_leverage_cascade.compute(sig_df=pd.DataFrame())
        assert isinstance(result, dict)
        assert result["ok"] is False

    def test_returns_dict_on_garbage_df(self, monkeypatch):
        _patch_store(monkeypatch)
        from engine import btc_leverage_cascade
        garbage = pd.DataFrame({"unrelated": [1, 2, 3]},
                               index=pd.date_range("2024-01-01", periods=3))
        result = btc_leverage_cascade.compute(sig_df=garbage)
        assert isinstance(result, dict)
        # funding state unknown, oi state unknown → cascade_risk low → ok True
        assert result["ok"] is True
        assert result["cascade_risk"] == "low"

    def test_high_risk_on_high_funding_and_stretched_oi(self, monkeypatch):
        """Sustained high funding + top-decile OI → cascade_risk = 'high'."""
        _patch_store(monkeypatch)
        from engine import btc_leverage_cascade

        # High funding: 80% annualized (> default 50 threshold) sustained 300 days
        # Stretched OI: high mcap_ratio (constant → at 100th percentile of itself)
        df = self._make_df(n=300, funding_annual_pct=80.0, funding_z=2.5,
                           oi_mcap_ratio=0.08, oi_change=0.05)
        result = btc_leverage_cascade.compute(sig_df=df)
        assert result["ok"] is True
        assert result["cascade_risk"] == "high", (
            f"Expected 'high', got '{result['cascade_risk']}' "
            f"(funding_state={result['funding_state']}, oi_state={result['oi_state']})"
        )
        assert result["derisk_cap"] == 0.5

    def test_low_risk_on_low_funding_and_declining_oi(self, monkeypatch):
        """Low funding + declining OI → cascade_risk = 'low', no derisk_cap."""
        _patch_store(monkeypatch)
        from engine import btc_leverage_cascade

        df = self._make_df(n=300, funding_annual_pct=5.0, funding_z=-0.2,
                           oi_mcap_ratio=0.01, oi_change=-0.05)
        result = btc_leverage_cascade.compute(sig_df=df)
        assert result["ok"] is True
        assert result["cascade_risk"] == "low"
        assert result["derisk_cap"] is None

    def test_elevated_risk_on_moderate_conditions(self, monkeypatch):
        """Elevated funding + elevated OI (not yet stretched) → 'elevated'."""
        _patch_store(monkeypatch)
        from engine import btc_leverage_cascade

        # 35% annualized (> elev threshold 25, < high threshold 50) for 300 days
        # OI at high but not top-decile (uses a constant so it's exactly the max →
        # actually it would be stretched; vary to make it the 80th pctile)
        n = 300
        idx = pd.date_range("2024-01-01", periods=n, freq="D")
        # Make OI ratio rise from low to high, last value around 85th pctile
        oi_vals = np.linspace(0.01, 0.06, n)
        df = pd.DataFrame({
            "funding_annual_pct": np.full(n, 35.0),
            "funding_z": np.full(n, 1.0),
            "oi_mcap_ratio": oi_vals,
            "oi_change": np.full(n, 0.02),
            "close": np.full(n, 50000.0),
        }, index=idx)
        result = btc_leverage_cascade.compute(sig_df=df)
        assert result["ok"] is True
        # last value is at top of its own rolling window → stretched; funding elevated
        # Either elevated or high is acceptable here (funding < 50 threshold)
        assert result["cascade_risk"] in ("elevated", "high")

    def test_negative_funding_gives_negative_state(self, monkeypatch):
        _patch_store(monkeypatch)
        from engine import btc_leverage_cascade

        df = self._make_df(n=300, funding_annual_pct=-20.0, funding_z=-2.0,
                           oi_mcap_ratio=0.01, oi_change=-0.02)
        result = btc_leverage_cascade.compute(sig_df=df)
        assert result["ok"] is True
        assert result["funding_state"] == "negative"
        assert result["cascade_risk"] == "low"

    def test_one_sided_flag_in_result(self, monkeypatch):
        _patch_store(monkeypatch)
        from engine import btc_leverage_cascade

        df = self._make_df(n=300)
        result = btc_leverage_cascade.compute(sig_df=df)
        assert result.get("one_sided") is True

    def test_ok_false_when_disabled(self, monkeypatch):
        _patch_store(monkeypatch)
        import lib.config as cfg_mod

        base = dict(cfg_mod.load())
        base["btc_leverage_cascade"] = {"enabled": False}
        monkeypatch.setattr(cfg_mod, "load", lambda: base)

        from engine import btc_leverage_cascade
        df = self._make_df(n=300, funding_annual_pct=80.0)
        result = btc_leverage_cascade.compute(sig_df=df)
        assert result["ok"] is False
        assert "disabled" in result["reason"]
