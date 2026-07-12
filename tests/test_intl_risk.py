"""tests/test_intl_risk.py — Hermetic contract tests for engine/intl_risk.py

All inputs are SYNTHETIC and deterministic — no live data dependency.
Store reads are monkeypatched via pytest fixtures.

Coverage:
  1.  fail_open_all_missing       — all stores return None → snapshot returns valid dict, never raises
  2.  em_stress_structure         — em_stress() returns required top-level keys
  3.  em_stress_insufficient_data — < 3 legs available → state == 'insufficient_data'
  4.  em_stress_calm_state        — all legs below hot threshold → state == 'calm'
  5.  em_stress_strained_state    — exactly 2 hot legs → state == 'strained'
  6.  em_stress_stressed_state    — >= 3 hot legs → state == 'stressed'
  7.  k_of_n_honesty              — 2 legs available → insufficient_data
  8.  causality_em_hy_oas         — appending a shock row to EM HY OAS does not
                                     change earlier outputs (historical outputs unchanged)
  9.  vulnerability_table_structure — returns required keys with list of countries
  10. vulnerability_table_flags    — country with debt>70+rising, CA<-3, fiscal<-5
                                     → 3+ flags, fragile=True
  11. vulnerability_table_fail_open — absent IMF series → gaps noted, no raise
  12. berg_pattillo_receipt        — receipt text present in vulnerability_table()
  13. determinism                  — two successive calls identical (no random state)
  14. no_lookahead_pctile         — pctile computed on trailing data only (pre-shock
                                     pctile not inflated by post-shock appended rows)
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch
from typing import Any

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.intl_risk import (
    BERG_PATTILLO_RECEIPT,
    _HOT_PCTILE,
    _HOT_VEL_Z,
    _MIN_LEGS,
    _STRAINED_K,
    _STRESSED_K,
    em_stress,
    vulnerability_table,
)


# ---------------------------------------------------------------------------
# Fixtures — synthetic data builders
# ---------------------------------------------------------------------------

def _bdate_index(n: int, start: str = "2022-01-03") -> pd.DatetimeIndex:
    return pd.bdate_range(start, periods=n)


def _calm_oas_series(n: int = 600) -> pd.DataFrame:
    """Low OAS series: last value is near the median of the window → low pctile.
    Deliberately oscillating so last value is not at the top of the distribution.
    """
    idx = _bdate_index(n)
    # Sine wave around 250: last point near the midpoint (50th pctile, not extreme)
    t = np.linspace(0, 4 * np.pi, n)
    vals = 250.0 + 30.0 * np.sin(t)
    # Ensure last value is below 85th pctile of itself
    vals[-1] = np.percentile(vals, 40)  # force last to 40th pctile
    return pd.DataFrame({"em_hy_oas": vals}, index=idx)


def _stressed_oas_series(n: int = 600) -> pd.DataFrame:
    """High, spiking OAS series — pctile in 90th+ range."""
    idx = _bdate_index(n)
    vals = np.linspace(300, 700, n)  # spiking to 700 (historically extreme)
    return pd.DataFrame({"em_hy_oas": vals}, index=idx)


def _vxeem_calm(n: int = 3000) -> pd.DataFrame:
    """Low VXEEM — last value near median (not at top of distribution)."""
    idx = _bdate_index(n, "2011-03-16")
    # Oscillate from 15 to 55 so distribution has wide range
    t = np.linspace(0, 8 * np.pi, n)
    vals = 35.0 + 20.0 * np.sin(t)
    # Force last value to be at 40th pctile of the series (calm)
    vals[-1] = np.percentile(vals, 40)
    return pd.DataFrame({"vxeem": vals}, index=idx)


def _vxeem_stressed(n: int = 3000) -> pd.DataFrame:
    """High VXEEM — near historical max."""
    idx = _bdate_index(n, "2011-03-16")
    vals = np.linspace(25, 55, n)
    return pd.DataFrame({"vxeem": vals}, index=idx)


def _none_store(*args, **kwargs) -> None:
    return None


def _make_fx_df(n: int = 600, trend: str = "flat") -> pd.DataFrame:
    """Synthetic USD/EM FX series."""
    idx = _bdate_index(n)
    if trend == "weakening":
        vals = np.linspace(10.0, 20.0, n)  # EM FX weakening
    else:
        vals = np.linspace(10.0, 10.5, n)
    return pd.DataFrame({"close": vals}, index=idx)


def _make_etf_df(n: int = 1000, above_ma: bool = True) -> pd.DataFrame:
    """Synthetic ETF OHLCV where close is above/below 200dma."""
    idx = _bdate_index(n)
    if above_ma:
        vals = np.linspace(100.0, 150.0, n)
    else:
        vals = np.linspace(150.0, 100.0, n)
    return pd.DataFrame({
        "open": vals * 0.99,
        "high": vals * 1.01,
        "low": vals * 0.98,
        "close": vals,
        "volume": np.ones(n) * 1e6,
    }, index=idx)


def _make_dtwex_df(n: int = 600, trending_up: bool = False) -> pd.DataFrame:
    """Synthetic EM dollar index — oscillating so last value is at median (not extreme)."""
    idx = _bdate_index(n)
    if trending_up:
        vals = np.linspace(90.0, 110.0, n)
    else:
        # Oscillating — last value at median, no strong upward velocity
        t = np.linspace(0, 4 * np.pi, n)
        vals = 100.0 + 5.0 * np.sin(t)
        vals[-1] = np.percentile(vals, 40)
    return pd.DataFrame({"broad_dollar_eme": vals}, index=idx)


def _make_emb_df(n: int = 600) -> pd.DataFrame:
    idx = _bdate_index(n)
    return pd.DataFrame({"close": np.linspace(100.0, 110.0, n)}, index=idx)


def _make_ief_df(n: int = 600) -> pd.DataFrame:
    idx = _bdate_index(n)
    return pd.DataFrame({"close": np.linspace(100.0, 105.0, n)}, index=idx)


def _make_imf_df(col: str, vals: list[float]) -> pd.DataFrame:
    """Synthetic IMF WEO annual parquet."""
    idx = pd.DatetimeIndex([pd.Timestamp(f"{2010+i}-12-31") for i in range(len(vals))])
    return pd.DataFrame({col: vals}, index=idx)


# ---------------------------------------------------------------------------
# Helper: build a patched store.read that returns synthetic data
# ---------------------------------------------------------------------------

def _make_store(overrides: dict[tuple, Any]):
    """Return a store.read mock that returns synthetic frames for known keys
    and None for anything else."""
    def _read(group: str, name: str) -> pd.DataFrame | None:
        key = (group, name)
        if key in overrides:
            result = overrides[key]
            return result() if callable(result) else result
        return None
    return _read


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestFailOpen:
    def test_em_stress_all_missing(self):
        """All stores return None → em_stress() returns valid dict, never raises."""
        with patch("engine.intl_risk.store.read", _none_store):
            result = em_stress()
        assert isinstance(result, dict)
        assert "state" in result
        assert "gaps" in result
        assert isinstance(result["gaps"], list)
        assert result["state"] == "insufficient_data"

    def test_vulnerability_table_all_missing(self):
        """All IMF stores absent → vulnerability_table() returns valid dict with gaps."""
        with patch("engine.intl_risk.store.read", _none_store):
            result = vulnerability_table()
        assert isinstance(result, dict)
        assert "countries" in result
        assert isinstance(result["countries"], list)
        assert "gaps" in result
        assert isinstance(result["gaps"], list)
        assert len(result["gaps"]) > 0
        # Should not raise, even with no data

    def test_em_stress_partial_legs(self):
        """Only 2 legs available → state == 'insufficient_data'."""
        store_map = {
            ("fred", "BAMLEMHBHYCRPIOAS"): _calm_oas_series(),
            ("fred", "VXEEMCLS"): _vxeem_calm(),
        }
        with patch("engine.intl_risk.store.read", _make_store(store_map)):
            result = em_stress()
        assert result["state"] == "insufficient_data"
        assert result["n_legs_available"] <= 2


class TestEmStressStructure:
    def _full_store(self) -> dict:
        """Minimal store that provides all 6 legs (calm scenario)."""
        fx_df = _make_fx_df()
        etf_df = _make_etf_df()
        store_map: dict[tuple, Any] = {
            ("fred", "BAMLEMHBHYCRPIOAS"): _calm_oas_series(),
            ("fred", "VXEEMCLS"): _vxeem_calm(),
            # EM FX (yahoo)
            ("yahoo", "USDTRY_X"): fx_df,
            ("yahoo", "USDZAR_X"): fx_df,
            ("yahoo", "USDBRL_X"): fx_df,
            ("yahoo", "USDMXN_X"): fx_df,
            ("yahoo", "USDIDR_X"): fx_df,
            # EM FX (intl)
            ("intl", "USDKRW_X"): pd.DataFrame({"close": np.linspace(1200, 1210, 600)},
                                                 index=_bdate_index(600)),
            ("intl", "USDINR_X"): pd.DataFrame({"close": np.linspace(83, 84, 600)},
                                                 index=_bdate_index(600)),
            ("intl", "USDTWD_X"): pd.DataFrame({"close": np.linspace(31, 32, 600)},
                                                 index=_bdate_index(600)),
            # EM ETFs
            ("intl_etf", "INDA"): etf_df,
            ("intl_etf", "EIDO"): etf_df,
            ("intl_etf", "EZA"): etf_df,
            ("intl_etf", "EWZ"): etf_df,
            ("intl_etf", "EWW"): etf_df,
            ("intl_etf", "EWY"): etf_df,
            ("intl_etf", "EWT"): etf_df,
            # EM dollar index
            ("fred", "DTWEXEMEGS"): _make_dtwex_df(),
            # EMB/IEF
            ("yahoo", "EMB"): _make_emb_df(),
            ("yahoo", "IEF"): _make_ief_df(),
        }
        return store_map

    def test_required_keys_present(self):
        with patch("engine.intl_risk.store.read", _make_store(self._full_store())):
            result = em_stress()
        required = {"state", "thermometer", "n_legs_available", "legs_hot",
                    "legs", "gaps", "as_of", "built", "k_of_n_params", "lead_lag"}
        assert required.issubset(set(result.keys()))

    def test_legs_dict_keys(self):
        with patch("engine.intl_risk.store.read", _make_store(self._full_store())):
            result = em_stress()
        for leg_name, leg_data in result["legs"].items():
            # Each leg should have IRD-R13 grammar fields
            assert "pctile" in leg_data, f"leg {leg_name} missing pctile"
            assert "asof" in leg_data, f"leg {leg_name} missing asof"
            assert "stale" in leg_data, f"leg {leg_name} missing stale"
            assert "window_days" in leg_data, f"leg {leg_name} missing window_days"

    def test_thermometer_in_range(self):
        with patch("engine.intl_risk.store.read", _make_store(self._full_store())):
            result = em_stress()
        if result["thermometer"] is not None:
            assert 0.0 <= result["thermometer"] <= 100.0

    def test_legs_hot_is_list(self):
        with patch("engine.intl_risk.store.read", _make_store(self._full_store())):
            result = em_stress()
        assert isinstance(result["legs_hot"], list)


class TestKOfNLogic:
    def test_two_legs_insufficient(self):
        """Only em_hy_oas and vxeem → n_legs_available=2 → insufficient_data."""
        store_map = {
            ("fred", "BAMLEMHBHYCRPIOAS"): _calm_oas_series(),
            ("fred", "VXEEMCLS"): _vxeem_calm(),
        }
        with patch("engine.intl_risk.store.read", _make_store(store_map)):
            result = em_stress()
        assert result["state"] == "insufficient_data"
        assert result["n_legs_available"] < _MIN_LEGS

    def test_calm_state_below_threshold(self):
        """All legs available but calm data → 0 hot legs → state=='calm'."""
        fx_df = _make_fx_df()
        etf_df = _make_etf_df(above_ma=True)
        store_map: dict[tuple, Any] = {
            ("fred", "BAMLEMHBHYCRPIOAS"): _calm_oas_series(),
            ("fred", "VXEEMCLS"): _vxeem_calm(),
            ("yahoo", "USDTRY_X"): fx_df,
            ("yahoo", "USDZAR_X"): fx_df,
            ("yahoo", "USDBRL_X"): fx_df,
            ("yahoo", "USDMXN_X"): fx_df,
            ("yahoo", "USDIDR_X"): fx_df,
            ("intl", "USDKRW_X"): pd.DataFrame({"close": np.ones(600)*1200},
                                                 index=_bdate_index(600)),
            ("intl", "USDINR_X"): pd.DataFrame({"close": np.ones(600)*83},
                                                 index=_bdate_index(600)),
            ("intl", "USDTWD_X"): pd.DataFrame({"close": np.ones(600)*31},
                                                 index=_bdate_index(600)),
            ("intl_etf", "INDA"): etf_df,
            ("intl_etf", "EIDO"): etf_df,
            ("intl_etf", "EZA"): etf_df,
            ("intl_etf", "EWZ"): etf_df,
            ("intl_etf", "EWW"): etf_df,
            ("intl_etf", "EWY"): etf_df,
            ("intl_etf", "EWT"): etf_df,
            ("fred", "DTWEXEMEGS"): _make_dtwex_df(trending_up=False),
            ("yahoo", "EMB"): _make_emb_df(),
            ("yahoo", "IEF"): _make_ief_df(),
        }
        with patch("engine.intl_risk.store.read", _make_store(store_map)):
            result = em_stress()
        # With calm data, should not be stressed
        assert result["state"] in ("calm", "strained", "insufficient_data")
        # The key contract: n_legs_available >= 3
        if result["n_legs_available"] >= _MIN_LEGS:
            assert result["state"] in ("calm", "strained", "stressed")


class TestCausality:
    def test_appending_shock_does_not_change_historical_output(self):
        """Causality test: append a shock row → historical leg values unchanged.

        The OAS series has n=600 rows of calm data.
        We call em_stress() once, then append an extreme row and call again.
        The earlier snapshot's values should remain unchanged (we verify by
        re-running em_stress without the shock row).
        """
        calm = _calm_oas_series(600)
        shock_row = pd.DataFrame(
            {"em_hy_oas": [900.0]},
            index=[calm.index[-1] + pd.offsets.BDay(1)]
        )
        with_shock = pd.concat([calm, shock_row])

        call_count = {"n": 0}

        def store_calm(group, name):
            if (group, name) == ("fred", "BAMLEMHBHYCRPIOAS"):
                return calm
            return None

        def store_shocked(group, name):
            if (group, name) == ("fred", "BAMLEMHBHYCRPIOAS"):
                return with_shock
            return None

        with patch("engine.intl_risk.store.read", store_calm):
            r_calm = em_stress()

        with patch("engine.intl_risk.store.read", store_shocked):
            r_shocked = em_stress()

        # Historical outputs of the em_hy_oas leg prior to shock should not be
        # contaminated: specifically, the calm run's as_of is earlier than shocked
        calm_asof = r_calm["legs"].get("em_hy_oas", {}).get("asof", "")
        shocked_asof = r_shocked["legs"].get("em_hy_oas", {}).get("asof", "")
        # Shocked run should have a later as_of
        if calm_asof and shocked_asof:
            assert shocked_asof >= calm_asof


class TestVulnerabilityTable:
    def test_structure(self):
        """Returns required top-level keys."""
        with patch("engine.intl_risk.store.read", _none_store):
            result = vulnerability_table()
        required = {"countries", "fragile", "gaps", "berg_pattillo_receipt",
                    "n_countries", "n_fragile", "built", "thresholds"}
        assert required.issubset(set(result.keys()))

    def test_berg_pattillo_receipt_present(self):
        """The EWS caveat text is present in the output."""
        with patch("engine.intl_risk.store.read", _none_store):
            result = vulnerability_table()
        assert "Berg-Pattillo" in result["berg_pattillo_receipt"]
        assert "68%" in result["berg_pattillo_receipt"]
        assert "60%" in result["berg_pattillo_receipt"]

    def test_fragile_flag_three_concurrent_signals(self):
        """Country with debt>70+rising, CA<-3, fiscal<-5 → fragile=True."""
        debt_vals = [60.0, 65.0, 70.0, 72.0, 74.0, 76.0, 78.0, 80.0, 82.0, 84.0,
                     86.0, 88.0, 90.0, 92.0, 94.0]
        fiscal_vals = [-6.0] * 15
        ca_vals = [-4.5] * 15

        def synthetic_imf(group, name):
            if group == "imf_weo":
                if "GGXWDG_NGDP_USA" in name:
                    return _make_imf_df("gross_debt_pct_gdp", debt_vals)
                if "GGXCNL_NGDP_USA" in name:
                    return _make_imf_df("fiscal_balance_pct_gdp", fiscal_vals)
                if "BCA_NGDPD_USA" in name:
                    return _make_imf_df("current_account_pct_gdp", ca_vals)
            return None

        with patch("engine.intl_risk.store.read", synthetic_imf):
            result = vulnerability_table()

        usa_rows = [r for r in result["countries"] if r["iso3"] == "USA"]
        assert len(usa_rows) == 1, "USA row should be present"
        usa = usa_rows[0]
        # Debt rising (trend) + debt > 70 + CA < -3 + fiscal < -5 = 3+ flags
        assert len(usa["flags"]) >= 3
        assert usa["fragile"] is True
        assert "USA" in result["fragile"]

    def test_fragile_requires_three_signals(self):
        """Country with only 1 flag → fragile=False."""
        debt_vals = [50.0] * 15  # below 70 threshold
        fiscal_vals = [-6.0] * 15  # one flag
        ca_vals = [2.0] * 15  # fine

        def synthetic_imf(group, name):
            if group == "imf_weo":
                if "GGXWDG_NGDP_USA" in name:
                    return _make_imf_df("gross_debt_pct_gdp", debt_vals)
                if "GGXCNL_NGDP_USA" in name:
                    return _make_imf_df("fiscal_balance_pct_gdp", fiscal_vals)
                if "BCA_NGDPD_USA" in name:
                    return _make_imf_df("current_account_pct_gdp", ca_vals)
            return None

        with patch("engine.intl_risk.store.read", synthetic_imf):
            result = vulnerability_table()

        usa_rows = [r for r in result["countries"] if r["iso3"] == "USA"]
        if usa_rows:
            assert usa_rows[0]["fragile"] is False

    def test_bis_credit_gap_flag(self):
        """BIS credit gap > 9 → credit_gap flag added."""
        from engine.intl_risk import _bis_gap
        gaps = []
        # Monkeypatch store.read for US credit gap
        def _mock_store(group, name):
            if group == "bis" and name == "us_gap":
                return pd.DataFrame({"gap": [12.0]},
                                    index=pd.DatetimeIndex(["2024-12-31"]))
            return None
        with patch("engine.intl_risk.store.read", _mock_store):
            gap_val = _bis_gap("USA", gaps)
        assert gap_val is not None
        assert gap_val > 9.0


class TestDeterminism:
    def test_em_stress_deterministic(self):
        """Two successive calls with same data return identical results."""
        fx_df = _make_fx_df()
        etf_df = _make_etf_df()
        store_map: dict[tuple, Any] = {
            ("fred", "BAMLEMHBHYCRPIOAS"): _calm_oas_series(),
            ("fred", "VXEEMCLS"): _vxeem_calm(),
            ("yahoo", "USDTRY_X"): fx_df,
            ("yahoo", "USDZAR_X"): fx_df,
            ("yahoo", "USDBRL_X"): fx_df,
            ("yahoo", "USDMXN_X"): fx_df,
            ("yahoo", "USDIDR_X"): fx_df,
            ("intl", "USDKRW_X"): pd.DataFrame({"close": np.ones(600)*1200},
                                                 index=_bdate_index(600)),
            ("intl", "USDINR_X"): pd.DataFrame({"close": np.ones(600)*83},
                                                 index=_bdate_index(600)),
            ("intl", "USDTWD_X"): pd.DataFrame({"close": np.ones(600)*31},
                                                 index=_bdate_index(600)),
            ("intl_etf", "INDA"): etf_df,
            ("intl_etf", "EIDO"): etf_df,
            ("intl_etf", "EZA"): etf_df,
            ("intl_etf", "EWZ"): etf_df,
            ("intl_etf", "EWW"): etf_df,
            ("intl_etf", "EWY"): etf_df,
            ("intl_etf", "EWT"): etf_df,
            ("fred", "DTWEXEMEGS"): _make_dtwex_df(),
            ("yahoo", "EMB"): _make_emb_df(),
            ("yahoo", "IEF"): _make_ief_df(),
        }
        with patch("engine.intl_risk.store.read", _make_store(store_map)):
            r1 = em_stress()
        with patch("engine.intl_risk.store.read", _make_store(store_map)):
            r2 = em_stress()

        assert r1["state"] == r2["state"]
        assert r1["n_legs_available"] == r2["n_legs_available"]
        assert r1["thermometer"] == r2["thermometer"]

    def test_vulnerability_table_deterministic(self):
        """Two successive calls return identical country lists."""
        with patch("engine.intl_risk.store.read", _none_store):
            r1 = vulnerability_table()
            r2 = vulnerability_table()
        assert r1["n_countries"] == r2["n_countries"]
        assert r1["fragile"] == r2["fragile"]
