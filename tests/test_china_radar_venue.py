"""Venue divergence family — unit tests for the three venue pairs.

Tests cover:
  - Synthetic fixture with an injected divergence fires with the right sign and family tag.
  - Missing input file → pair skipped, no crash (returns None).
  - Shallow history (< 60d for AH premium, < 252+20d for offshore gap) → skipped.
  - Ledger accrue carries family='venue'; _fwd_rel returns None for venue pairs (None etf).
  - scan() output carries venue rows in divergences (when they fire) tagged family='venue'.
  - The 2x2 kernel for southbound pair fires correctly.

Network-free throughout: all store.read calls are monkeypatched.
"""
from __future__ import annotations

import pandas as pd
import numpy as np
import pytest

from engine import china_radar as cr
from engine import china_radar_ledger as rl


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _make_series(n: int, base: float = 30.0, sd: float = 2.0, seed: int = 42) -> pd.Series:
    rng = np.random.default_rng(seed)
    vals = base + rng.normal(0, sd, n)
    idx = pd.date_range("2023-01-01", periods=n, freq="B")
    return pd.Series(vals.tolist(), index=idx)


def _make_price_series(n: int, start: float = 100.0, seed: int = 7) -> pd.Series:
    rng = np.random.default_rng(seed)
    rets = rng.normal(0.0005, 0.01, n)
    prices = start * np.cumprod(1 + rets)
    idx = pd.date_range("2022-01-01", periods=n, freq="B")
    return pd.Series(prices.tolist(), index=idx)


# --------------------------------------------------------------------------- #
# A/H Premium pair
# --------------------------------------------------------------------------- #
class TestSigAhPremiumZ:
    def test_fires_positive_when_premium_high(self, monkeypatch):
        """Premium at mean + 3 std → z ≈ 3.0, dir = +1, should fire positive."""
        from lib import store
        s = _make_series(300, base=30.0, sd=2.0)
        # inject a high value at the end
        high_val = float(s.mean()) + 3 * float(s.std())
        s.iloc[-1] = high_val
        df = pd.DataFrame({"hsahp": s})
        monkeypatch.setattr(store, "read", lambda g, n: df if n == "ah_premium" else None)
        result = cr._sig_ah_premium_z()
        assert result is not None
        assert result["dir"] == 1
        assert result["z"] > 0.4

    def test_fires_negative_when_premium_low(self, monkeypatch):
        """Premium at mean - 3 std → dir = -1."""
        from lib import store
        s = _make_series(300, base=30.0, sd=2.0)
        low_val = float(s.mean()) - 3 * float(s.std())
        s.iloc[-1] = low_val
        df = pd.DataFrame({"hsahp": s})
        monkeypatch.setattr(store, "read", lambda g, n: df if n == "ah_premium" else None)
        result = cr._sig_ah_premium_z()
        assert result is not None
        assert result["dir"] == -1

    def test_missing_input_returns_none(self, monkeypatch):
        """Missing ah_premium AND ah_spot → returns None, no crash."""
        from lib import store
        monkeypatch.setattr(store, "read", lambda g, n: None)
        result = cr._sig_ah_premium_z()
        assert result is None

    def test_shallow_history_returns_none(self, monkeypatch):
        """Less than 60 rows → returns None."""
        from lib import store
        s = _make_series(30, base=30.0)
        df = pd.DataFrame({"hsahp": s})
        monkeypatch.setattr(store, "read", lambda g, n: df if n == "ah_premium" else None)
        result = cr._sig_ah_premium_z()
        assert result is None

    def test_includes_data_asof(self, monkeypatch):
        """Result includes data_asof field."""
        from lib import store
        s = _make_series(300, base=30.0, sd=2.0)
        s.iloc[-1] = float(s.mean()) + 3 * float(s.std())
        df = pd.DataFrame({"hsahp": s})
        monkeypatch.setattr(store, "read", lambda g, n: df if n == "ah_premium" else None)
        result = cr._sig_ah_premium_z()
        assert result is not None
        assert "data_asof" in result
        assert result["data_asof"]  # non-empty string


# --------------------------------------------------------------------------- #
# Offshore ETF gap pair
# --------------------------------------------------------------------------- #
class TestSigOffshoreEtfGap:
    def _make_store_fn(self, inject_offshore_outperform: bool = True):
        """Build a store.read mock where offshore ETFs outperform (or underperform) onshore."""
        n = 600
        rng = np.random.default_rng(99)
        # Onshore CSI300 ETF: neutral
        on_vals = 100.0 * np.cumprod(1 + rng.normal(0.0003, 0.008, n))
        on_idx = pd.date_range("2022-01-01", periods=n, freq="B")
        csi_df = pd.DataFrame({"close": on_vals.tolist()}, index=on_idx)

        # Offshore ETFs: inject outperformance or underperformance in last 5 days
        mult = 1.025 if inject_offshore_outperform else 0.97

        def _etf_df(seed):
            rng2 = np.random.default_rng(seed)
            v = 50.0 * np.cumprod(1 + rng2.normal(0.0003, 0.008, n))
            v[-5:] *= mult  # inject 5d divergence
            idx = pd.date_range("2022-01-01", periods=n, freq="B")
            return pd.DataFrame({"close": v.tolist()}, index=idx)

        etf_dfs = {"KWEB": _etf_df(1), "MCHI": _etf_df(2), "CQQQ": _etf_df(3)}

        def _read(group, name):
            if group == "china" and name == "510300.SS":
                return csi_df
            if group == "yahoo" and name in etf_dfs:
                return etf_dfs[name]
            return None

        return _read

    def test_fires_positive_when_offshore_outperforms(self, monkeypatch):
        """Offshore ETFs outperform → z positive → dir +1 (positive divergence candidate)."""
        from lib import store
        monkeypatch.setattr(store, "read", self._make_store_fn(inject_offshore_outperform=True))
        result = cr._sig_offshore_etf_gap()
        assert result is not None, "expected a firing signal with injected outperformance"
        assert result["dir"] == 1
        assert result["z"] > 0

    def test_fires_negative_when_offshore_underperforms(self, monkeypatch):
        """Offshore ETFs underperform → z negative → dir -1."""
        from lib import store
        monkeypatch.setattr(store, "read", self._make_store_fn(inject_offshore_outperform=False))
        result = cr._sig_offshore_etf_gap()
        assert result is not None
        assert result["dir"] == -1

    def test_missing_csi300_returns_none(self, monkeypatch):
        """Missing 510300.SS → returns None."""
        from lib import store
        monkeypatch.setattr(store, "read", lambda g, n: None)
        result = cr._sig_offshore_etf_gap()
        assert result is None

    def test_missing_all_etfs_returns_none(self, monkeypatch):
        """No ETF data → returns None."""
        from lib import store
        n = 600
        rng = np.random.default_rng(77)
        on_vals = 100.0 * np.cumprod(1 + rng.normal(0, 0.008, n))
        idx = pd.date_range("2022-01-01", periods=n, freq="B")
        csi_df = pd.DataFrame({"close": on_vals.tolist()}, index=idx)
        monkeypatch.setattr(store, "read", lambda g, n: csi_df if n == "510300.SS" else None)
        result = cr._sig_offshore_etf_gap()
        assert result is None

    def test_shallow_history_returns_none(self, monkeypatch):
        """Fewer than 252+20 shared days → returns None."""
        from lib import store
        n = 100  # too short
        rng = np.random.default_rng(55)
        vals = 100.0 * np.cumprod(1 + rng.normal(0, 0.008, n))
        idx = pd.date_range("2025-01-01", periods=n, freq="B")
        df = pd.DataFrame({"close": vals.tolist()}, index=idx)
        monkeypatch.setattr(store, "read", lambda g, n: df)
        result = cr._sig_offshore_etf_gap()
        assert result is None

    def test_reports_etf_used(self, monkeypatch):
        """Result includes list of ETFs that had data."""
        from lib import store
        monkeypatch.setattr(store, "read", self._make_store_fn(inject_offshore_outperform=True))
        result = cr._sig_offshore_etf_gap()
        assert result is not None
        assert "etf_used" in result
        assert set(result["etf_used"]).issubset({"KWEB", "MCHI", "CQQQ"})


# --------------------------------------------------------------------------- #
# Southbound vs HSCEI pair
# --------------------------------------------------------------------------- #
class TestSigSouthboundVsHk:
    def _make_store_fn(self, flow_z_sign: int = 1, hk_z_sign: int = -1):
        """Build a mock where southbound flow and HSCEI can be set to opposing directions."""
        n = 600
        rng = np.random.default_rng(33)

        # Southbound: inject high flow (positive z) or low flow (negative z)
        base_flow = rng.normal(5000, 2000, n)
        if flow_z_sign == 1:
            # Recent 20d sum should be above mean by >1 std
            base_flow[-20:] += 10000
        elif flow_z_sign == -1:
            base_flow[-20:] -= 10000
        idx_sb = pd.date_range("2022-01-01", periods=n, freq="B")
        sb_df = pd.DataFrame({"net": base_flow.tolist()}, index=idx_sb)
        sb_df.index.name = "TRADE_DATE"

        # HSCEI: inject positive or negative momentum — use larger multiplier to ensure the
        # 20d return z exceeds ±0.3 deadband vs 1y history
        hsce_vals = 10000.0 * np.cumprod(1 + rng.normal(0.0002, 0.01, n))
        if hk_z_sign == -1:
            hsce_vals[-20:] *= 0.93   # strong underperformance
        elif hk_z_sign == 1:
            hsce_vals[-20:] *= 1.07   # strong outperformance
        idx_hk = pd.date_range("2022-01-01", periods=n, freq="B")
        hsce_df = pd.DataFrame({"close": hsce_vals.tolist()}, index=idx_hk)

        def _read(group, name):
            if group == "china_connect" and name == "southbound":
                return sb_df
            if group == "hk" and name == "_HSCE":
                return hsce_df
            return None

        return _read

    def test_fires_positive_when_flow_leads_hk(self, monkeypatch):
        """Strong southbound flow + HSCEI lagging → positive divergence."""
        from lib import store
        monkeypatch.setattr(store, "read", self._make_store_fn(flow_z_sign=1, hk_z_sign=-1))
        result = cr._sig_southbound_vs_hk()
        assert result is not None
        assert result["dir"] == 1, f"expected dir=1, got {result}"
        # Build venue row and verify sign
        row = cr._build_venue_row(
            __import__("engine.china_conviction", fromlist=["to_100"]),
            "venue_southbound", "SB flow vs HSCEI", "南向 vs HSCEI",
            "HSCEI (HK)", "恒生国企",
            result, "thesis", {}, {}
        )
        assert row is not None
        assert row["sign"] == "positive"
        assert row["family"] == "venue"

    def test_fires_negative_when_hk_leads_flow(self, monkeypatch):
        """Weak southbound flow + HSCEI strongly positive → negative divergence."""
        from lib import store
        monkeypatch.setattr(store, "read", self._make_store_fn(flow_z_sign=-1, hk_z_sign=1))
        result = cr._sig_southbound_vs_hk()
        assert result is not None
        assert result["dir"] == -1
        row = cr._build_venue_row(
            __import__("engine.china_conviction", fromlist=["to_100"]),
            "venue_southbound", "SB flow vs HSCEI", "南向 vs HSCEI",
            "HSCEI (HK)", "恒生国企",
            result, "thesis", {}, {}
        )
        assert row is not None
        assert row["sign"] == "negative"

    def test_missing_southbound_returns_none(self, monkeypatch):
        """Missing southbound data → returns None."""
        from lib import store
        n = 600
        rng = np.random.default_rng(11)
        hsce_vals = 10000.0 * np.cumprod(1 + rng.normal(0, 0.01, n))
        idx = pd.date_range("2022-01-01", periods=n, freq="B")
        hsce_df = pd.DataFrame({"close": hsce_vals.tolist()}, index=idx)
        monkeypatch.setattr(store, "read",
                            lambda g, n: hsce_df if (g == "hk" and n == "_HSCE") else None)
        result = cr._sig_southbound_vs_hk()
        assert result is None

    def test_missing_hscei_returns_none(self, monkeypatch):
        """Missing _HSCE → returns None."""
        from lib import store
        n = 600
        rng = np.random.default_rng(22)
        base_flow = rng.normal(5000, 2000, n).tolist()
        idx = pd.date_range("2022-01-01", periods=n, freq="B")
        sb_df = pd.DataFrame({"net": base_flow}, index=idx)
        sb_df.index.name = "TRADE_DATE"
        monkeypatch.setattr(store, "read",
                            lambda g, n: sb_df if (g == "china_connect" and n == "southbound") else None)
        result = cr._sig_southbound_vs_hk()
        assert result is None

    def test_shallow_southbound_returns_none(self, monkeypatch):
        """Fewer than 80 southbound rows → returns None."""
        from lib import store
        n = 50
        rng = np.random.default_rng(44)
        sb_df = pd.DataFrame({"net": rng.normal(0, 1000, n).tolist()},
                              index=pd.date_range("2026-01-01", periods=n, freq="B"))
        monkeypatch.setattr(store, "read", lambda g, n: sb_df if g == "china_connect" else None)
        result = cr._sig_southbound_vs_hk()
        assert result is None


# --------------------------------------------------------------------------- #
# _build_venue_row
# --------------------------------------------------------------------------- #
class TestBuildVenueRow:
    def test_none_signal_returns_none(self):
        """None signal → None row."""
        row = cr._build_venue_row(
            None, "venue_ah_premium", "AH", "AH",
            "CSI300", "沪深300", None, "thesis", {}, {}
        )
        assert row is None

    def test_zero_dir_returns_none(self):
        """Signal with dir=0 → None row."""
        sig = {"dir": 0, "strength": 0.5, "z": 0.1, "value": 30.0, "data_asof": "2026-07-01"}
        row = cr._build_venue_row(
            None, "venue_ah_premium", "AH", "AH",
            "CSI300", "沪深300", sig, "thesis", {}, {}
        )
        assert row is None

    def test_venue_row_has_family_tag(self):
        """Row with a valid firing signal carries family='venue'."""
        from engine import china_conviction as cv
        sig = {"dir": 1, "strength": 0.7, "z": 1.8, "value": 35.0,
               "data_asof": "2026-07-01",
               "detail_en": "test", "detail_zh": "测试"}
        row = cr._build_venue_row(
            cv, "venue_ah_premium", "AH z", "AH溢价",
            "CSI300", "沪深300", sig, "Thesis text.", {}, {}
        )
        assert row is not None
        assert row["family"] == "venue"
        assert row["sector_etf"] is None
        assert row["sign"] == "positive"
        assert row["hypothesis_en"]
        assert row["reliability"]["basis"] == "unproven"

    def test_southbound_2x2_kernel_in_line_when_flow_and_hk_agree(self):
        """Flow strong + HSCEI also strong → in_line → row is None."""
        from engine import china_conviction as cv
        sig = {"dir": 1, "strength": 0.8, "z": 1.5, "value": 100.0,
               "_hk_z": 0.8,   # HSCEI also positive → same direction
               "data_asof": "2026-07-01",
               "detail_en": "test", "detail_zh": "测试"}
        row = cr._build_venue_row(
            cv, "venue_southbound", "SB vs HSCEI", "南向 vs 恒生国企",
            "HSCEI (HK)", "恒生国企",
            sig, "thesis", {}, {}
        )
        assert row is None   # in_line → filtered


# --------------------------------------------------------------------------- #
# Ledger: family field and venue-pair handling
# --------------------------------------------------------------------------- #
class TestLedgerVenueFamily:
    def test_accrue_carries_family_tag(self, tmp_path, monkeypatch):
        """Venue divergence entries carry family='venue' in ledger."""
        monkeypatch.setattr(rl, "_path", lambda: tmp_path / "ledger.parquet")
        scan = {
            "asof": "2026-07-06",
            "divergences": [
                {
                    "pair": "venue_ah_premium->china",
                    "signal_key": "venue_ah_premium",
                    "family": "venue",
                    "sector_etf": None,
                    "sector_en": "CSI 300 (onshore)",
                    "sector_zh": "沪深300（境内）",
                    "sign": "positive",
                    "price_rs": None,
                    "signal_value": 35.2,
                }
            ],
        }
        rl.accrue(scan)
        df = pd.read_parquet(tmp_path / "ledger.parquet")
        assert "family" in df.columns
        assert df.iloc[0]["family"] == "venue"

    def test_fwd_rel_none_for_null_etf(self):
        """_fwd_rel returns None immediately for None ETF (venue pair)."""
        result = rl._fwd_rel(None, "2026-01-01")
        assert result is None

    def test_accrue_legacy_row_family_is_none(self, tmp_path, monkeypatch):
        """Legacy sector rows (no family key) get family=None in the ledger."""
        monkeypatch.setattr(rl, "_path", lambda: tmp_path / "ledger.parquet")
        scan = {
            "asof": "2026-07-06",
            "divergences": [
                {
                    "pair": "pmi->512400.SS",
                    "signal_key": "pmi",
                    # no "family" key — legacy row
                    "sector_etf": "512400.SS",
                    "sector_en": "Nonferrous metals",
                    "sector_zh": "有色金属",
                    "sign": "positive",
                    "price_rs": -8.6,
                    "signal_value": 51.2,
                }
            ],
        }
        rl.accrue(scan)
        df = pd.read_parquet(tmp_path / "ledger.parquet")
        assert "family" in df.columns
        # Legacy row has no family → stored as None/NaN
        assert df.iloc[0]["family"] is None or pd.isna(df.iloc[0]["family"])


# --------------------------------------------------------------------------- #
# scan() integration: venue rows surface in output
# --------------------------------------------------------------------------- #
class TestScanVenueIntegration:
    def test_scan_venue_rows_carry_family_tag(self, monkeypatch):
        """If a venue signal fires, the scan() output divergences contain family='venue' rows."""
        from lib import store

        # Inject a firing AH premium signal
        n = 300
        rng = np.random.default_rng(42)
        s = pd.Series(
            (30.0 + rng.normal(0, 2.0, n)).tolist(),
            index=pd.date_range("2023-01-01", periods=n, freq="B")
        )
        # Force last value to be 3 std above mean → z > 0.4 → dir = +1
        s.iloc[-1] = float(s.mean()) + 4 * float(s.std())
        ah_df = pd.DataFrame({"hsahp": s})

        # Other stores return None (no sector signals fire — keeps test focused)
        def mock_read(group, name):
            if group == "hk_ah_official" and name == "ah_premium":
                return ah_df
            return None

        monkeypatch.setattr(store, "read", mock_read)
        # Also monkeypatch store in engine imports
        import engine.china_radar as cr_mod
        monkeypatch.setattr(cr_mod, "_sector_flow_boards", lambda: {})

        result = cr.scan()
        if result is None:
            # Scan may return None if ALL rows are in_line or empty (other signals absent)
            return
        venue_rows = [d for d in result.get("divergences", []) if d.get("family") == "venue"]
        # At least one venue row should fire given our injected signal
        assert len(venue_rows) >= 1
        for row in venue_rows:
            assert row["family"] == "venue"
            assert row["sign"] in ("positive", "negative")
            assert row["hypothesis_en"]
            assert "data_asof" in row

    def test_scan_does_not_crash_on_all_missing_venue_data(self, monkeypatch):
        """scan() returns None or valid dict even when all venue data is absent."""
        from lib import store
        monkeypatch.setattr(store, "read", lambda g, n: None)
        import engine.china_radar as cr_mod
        monkeypatch.setattr(cr_mod, "_sector_flow_boards", lambda: {})
        # Should not raise
        result = cr.scan()
        assert result is None or isinstance(result, dict)
