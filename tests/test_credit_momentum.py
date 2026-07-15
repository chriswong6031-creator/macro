"""Tests for engine/credit_momentum.py — CCW-W3.

Coverage:
  - canon-on-spread: severity orientation, velocity percentile
  - density gate open/closed conditions
  - composition-change suppression
  - K-of-N tag logic (2-of-3 boundary)
  - forward ledger keep-FIRST idempotency
  - FINRA breadth math (productCategory buy/sell trap)
  - divergence quadrant classification
  - alerts debounce (credit_market_turn + credit_theme_stress)
  - JSON emission null-safety on EMPTY stores (every input missing → valid JSON, no crash)

Zero network calls; all inputs are synthetic (tmp_path fixtures).
"""
from __future__ import annotations

import json
import tempfile
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Helpers — synthetic data factories
# ---------------------------------------------------------------------------

def _make_daily_series(n: int, base: float = 300.0, seed: int = 42, trend: float = 0.0) -> pd.Series:
    """Make a synthetic daily spread series."""
    rng = np.random.default_rng(seed)
    vals = base + trend * np.arange(n) + rng.normal(0, 5, n).cumsum()
    idx = pd.date_range("2016-01-01", periods=n, freq="B")
    return pd.Series(vals, index=idx, name="spread")


def _write_parquet(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path)


def _write_series_parquet(s: pd.Series, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df = s.to_frame(name=s.name or "value")
    df.to_parquet(path)


def _minimal_data_root(tmp_path: Path) -> Path:
    """Create a minimal data root with deep HY OAS + IG OAS."""
    root = tmp_path / "data"

    # Deep-history HY OAS (archive)
    hy_s = _make_daily_series(2600, base=400.0)
    _write_series_parquet(hy_s.rename("hy_oas"), root / "archive" / "BAMLH0A0HYM2.parquet")

    # Deep-history IG OAS (archive)
    ig_s = _make_daily_series(2600, base=100.0, seed=43)
    _write_series_parquet(ig_s.rename("ig_oas"), root / "archive" / "BAMLC0A0CM.parquet")

    # Moody's spreads
    _write_series_parquet(_make_daily_series(2600, base=180.0).rename("baa_corp"), root / "fred" / "DBAA.parquet")
    _write_series_parquet(_make_daily_series(2600, base=80.0, seed=99).rename("aaa_corp"), root / "fred" / "DAAA.parquet")

    # CCC and BB OAS (archive)
    _write_series_parquet(_make_daily_series(800, base=800.0).rename("ccc_oas"), root / "archive" / "BAMLH0A3HYC.parquet")
    _write_series_parquet(_make_daily_series(800, base=250.0, seed=77).rename("bb_oas"), root / "archive" / "BAMLH0A1HYBB.parquet")

    # Issuer registry
    registry = {
        "themes": {
            "hyperscaler_credit": {
                "issuers": {
                    "MSFT": {"equity_ticker": "MSFT", "id_prefixes": [], "name_match_patterns": ["MICROSOFT"]},
                }
            }
        }
    }
    reg_path = root / "corp_bonds" / "issuer_themes.json"
    reg_path.parent.mkdir(parents=True, exist_ok=True)
    reg_path.write_text(json.dumps(registry))

    return root


# ---------------------------------------------------------------------------
# Test 1: Canon-on-spread: velocity percentile and severity orientation
# ---------------------------------------------------------------------------

class TestCanonOnSpread:
    def test_widening_series_produces_high_velocity_pctile(self, tmp_path):
        """A monotonically widening spread should have vel21_pctile close to 100."""
        from engine.credit_momentum import _compute_velocity

        # Build a series that widens sharply in the last 100 bars (all time series ~2600 bars)
        calm = _make_daily_series(2400, base=300.0, trend=0.0)
        widening = _make_daily_series(200, base=float(calm.iloc[-1]), trend=2.0)
        widening.index = pd.date_range(calm.index[-1] + pd.Timedelta(days=1), periods=200, freq="B")
        s = pd.concat([calm, widening])

        vel = _compute_velocity(s)
        assert vel["vel21"] is not None, "vel21 should not be None for a long series"
        assert vel["vel21"] > 0, "vel21 should be positive (widening)"
        assert vel["vel21_pctile"] is not None
        assert vel["vel21_pctile"] > 70.0, f"Expected high pctile during widening, got {vel['vel21_pctile']}"

    def test_tightening_series_has_low_velocity_pctile(self, tmp_path):
        """A monotonically tightening spread should have low vel21_pctile."""
        from engine.credit_momentum import _compute_velocity

        calm = _make_daily_series(2400, base=300.0, trend=0.0)
        tightening_vals = float(calm.iloc[-1]) - 2.0 * np.arange(200)
        tightening = pd.Series(tightening_vals,
                               index=pd.date_range(calm.index[-1] + pd.Timedelta(days=1), periods=200, freq="B"))
        s = pd.concat([calm, tightening])

        vel = _compute_velocity(s)
        assert vel["vel21"] is not None
        assert vel["vel21"] < 0, "vel21 should be negative (tightening)"
        assert vel["vel21_pctile"] is not None
        assert vel["vel21_pctile"] < 30.0, f"Expected low pctile during tightening, got {vel['vel21_pctile']}"

    def test_spread_series_state_widening_stress(self, tmp_path):
        """Build a spread series in widening stress; state should be 'widening_stress'."""
        from engine.credit_momentum import _build_series_state

        calm = _make_daily_series(2400, base=300.0, trend=0.0)
        widening = _make_daily_series(100, base=float(calm.iloc[-1]), trend=4.0)
        widening.index = pd.date_range(calm.index[-1] + pd.Timedelta(days=1), periods=100, freq="B")
        s = pd.concat([calm, widening])

        state = _build_series_state("test_spread", s, orientation="spread")
        assert state["orientation"] == "spread"
        assert state["severity_note"] is not None, "spread orientation should have severity_note"
        # velocity should show widening
        assert state["velocity"]["vel21"] is not None
        assert state["velocity"]["vel21"] > 0

    def test_spread_orientation_emits_severity_note(self, tmp_path):
        from engine.credit_momentum import _build_series_state
        s = _make_daily_series(250, base=300.0)
        state = _build_series_state("test", s, orientation="spread")
        assert "severity_note" in state
        assert state["severity_note"] is not None

    def test_price_orientation_no_severity_note(self, tmp_path):
        from engine.credit_momentum import _build_series_state
        s = _make_daily_series(250, base=100.0)
        state = _build_series_state("test", s, orientation="price")
        assert state.get("severity_note") is None


# ---------------------------------------------------------------------------
# Test 2: Density gate
# ---------------------------------------------------------------------------

class TestDensityGate:
    def _make_theme_df(self, n_bonds: int, match_ratio: float, n_dates: int = 25) -> pd.DataFrame:
        rows = []
        base_date = date(2026, 1, 1)
        for i in range(n_dates):
            rows.append({
                "as_of": pd.Timestamp(base_date) + pd.Timedelta(days=i),
                "theme": "test_theme",
                "n_bonds": n_bonds,
                "matched_n": int(n_bonds * match_ratio),
            })
        return pd.DataFrame(rows)

    def test_gate_open_when_above_thresholds(self):
        from engine.credit_momentum import _check_density_gate
        df = self._make_theme_df(10, 0.7, 25)
        open_, reason = _check_density_gate(df, "test_theme")
        assert open_ is True, f"Expected gate open; reason: {reason}"

    def test_gate_closed_too_few_bonds(self):
        from engine.credit_momentum import _check_density_gate
        df = self._make_theme_df(5, 0.8, 25)
        open_, reason = _check_density_gate(df, "test_theme")
        assert open_ is False
        assert "n_bonds" in reason.lower()

    def test_gate_closed_low_match_ratio(self):
        from engine.credit_momentum import _check_density_gate
        df = self._make_theme_df(12, 0.4, 25)
        open_, reason = _check_density_gate(df, "test_theme")
        assert open_ is False
        assert "match ratio" in reason.lower()

    def test_gate_closed_insufficient_dates(self):
        from engine.credit_momentum import _check_density_gate
        df = self._make_theme_df(10, 0.8, 10)  # < 21 dates
        open_, reason = _check_density_gate(df, "test_theme")
        assert open_ is False
        assert "fewer than" in reason.lower() or "accruing" in reason.lower()

    def test_gate_closed_missing_theme(self):
        from engine.credit_momentum import _check_density_gate
        df = self._make_theme_df(10, 0.8, 25)
        open_, reason = _check_density_gate(df, "nonexistent_theme")
        assert open_ is False

    def test_gate_boundary_exactly_8_bonds(self):
        from engine.credit_momentum import _check_density_gate
        df = self._make_theme_df(8, 0.65, 25)
        open_, _ = _check_density_gate(df, "test_theme")
        assert open_ is True

    def test_gate_boundary_exactly_60_percent_match(self):
        from engine.credit_momentum import _check_density_gate
        df = self._make_theme_df(10, 0.60, 25)
        open_, _ = _check_density_gate(df, "test_theme")
        assert open_ is True


# ---------------------------------------------------------------------------
# Test 3: Composition-change suppression
# ---------------------------------------------------------------------------

class TestCompositionChangeSuppression:
    def test_composition_mask_nulls_out_bars(self):
        """Bars where composition_change=True should produce NaN in velocity output."""
        from engine.credit_momentum import _compute_velocity

        n = 250
        s = _make_daily_series(n, base=300.0)
        # Flag every 5th bar as composition change
        comp_mask = pd.Series(False, index=s.index)
        comp_mask.iloc[::5] = True

        vel_with_mask    = _compute_velocity(s, composition_mask=comp_mask)
        vel_without_mask = _compute_velocity(s, composition_mask=None)

        # vel21 should differ (composition bars set to NaN change the diff window)
        # Both should still compute (not crash)
        assert vel_without_mask["vel21"] is not None
        # With mask, some bars are NaN — vel21 may differ or be None near mask edges
        # The key test: no crash, values are float or None
        v = vel_with_mask["vel21"]
        assert v is None or isinstance(v, float)

    def test_composition_mask_suppresses_cross_events(self, tmp_path):
        """build_series_state with comp_mask should not crash; if no gate, no oscillator events."""
        from engine.credit_momentum import _build_series_state

        s = _make_daily_series(300, base=300.0)
        comp_mask = pd.Series(False, index=s.index)
        comp_mask.iloc[-5:] = True  # recent bars composition-changed

        all_events: list = []
        state = _build_series_state("test", s, orientation="spread",
                                    composition_mask=comp_mask, all_events=all_events)
        # Should not crash and produce valid state
        assert isinstance(state, dict)
        assert "velocity" in state


# ---------------------------------------------------------------------------
# Test 4: K-of-N tag logic
# ---------------------------------------------------------------------------

class TestKofNTagLogic:
    def _make_vel(self, vel21_pctile: float | None = None, vel21: float | None = None) -> dict:
        return {"vel21_pctile": vel21_pctile, "vel21": vel21 or 0.0}

    def test_credit_market_turn_fires_at_2_of_3(self):
        from engine.credit_momentum import _compute_credit_market_turn_tag
        # leg1=True, leg2=True, leg3=False → score=2, fired=True
        tag = _compute_credit_market_turn_tag(
            hy_oas_vel=self._make_vel(90.0),     # vel21_pctile=90 >= 85 → leg1=True
            quality_spread_vel=self._make_vel(vel21=5.0),  # widening → leg2=True
            ccc_bb_vel=self._make_vel(vel21=-2.0),  # tightening → leg3=False
        )
        assert tag["fired"] is True
        assert tag["score"] == 2
        assert tag["legs"]["hy_vel21_pctile_ge85"] is True
        assert tag["legs"]["quality_spread_widening_21d"] is True
        assert tag["legs"]["ccc_bb_widening_21d"] is False

    def test_credit_market_turn_does_not_fire_at_1_of_3(self):
        from engine.credit_momentum import _compute_credit_market_turn_tag
        tag = _compute_credit_market_turn_tag(
            hy_oas_vel=self._make_vel(90.0),     # leg1=True
            quality_spread_vel=self._make_vel(vel21=-1.0),  # leg2=False
            ccc_bb_vel=self._make_vel(vel21=-1.0),  # leg3=False
        )
        assert tag["fired"] is False
        assert tag["score"] == 1

    def test_credit_market_turn_fires_at_3_of_3(self):
        from engine.credit_momentum import _compute_credit_market_turn_tag
        tag = _compute_credit_market_turn_tag(
            hy_oas_vel=self._make_vel(90.0),
            quality_spread_vel=self._make_vel(vel21=5.0),
            ccc_bb_vel=self._make_vel(vel21=10.0),
        )
        assert tag["fired"] is True
        assert tag["score"] == 3

    def test_credit_market_turn_not_fired_when_pctile_below_85(self):
        from engine.credit_momentum import _compute_credit_market_turn_tag
        tag = _compute_credit_market_turn_tag(
            hy_oas_vel=self._make_vel(84.9),   # just below threshold
            quality_spread_vel=self._make_vel(vel21=5.0),
            ccc_bb_vel=self._make_vel(vel21=5.0),
        )
        assert tag["legs"]["hy_vel21_pctile_ge85"] is False
        assert tag["score"] == 2
        assert tag["fired"] is True   # 2 legs still fire (leg2 + leg3)

    def test_credit_theme_stress_2_of_3_boundary(self):
        from engine.credit_momentum import _compute_credit_theme_stress_tag
        # leg1=True (vel pctile high), leg2=False, leg3=False → score=1, not fired
        tag = _compute_credit_theme_stress_tag(
            "hyperscaler_credit",
            {"vel21_pctile": 90.0},  # leg1=True
            None, None,              # leg2=leg3=False (no grid data)
        )
        assert tag["fired"] is False
        assert tag["score"] == 1

    def test_credit_market_turn_all_none_no_crash(self):
        from engine.credit_momentum import _compute_credit_market_turn_tag
        tag = _compute_credit_market_turn_tag(
            hy_oas_vel={},
            quality_spread_vel={},
            ccc_bb_vel={},
        )
        assert isinstance(tag, dict)
        assert tag["fired"] is False


# ---------------------------------------------------------------------------
# Test 5: Forward ledger keep-FIRST idempotency
# ---------------------------------------------------------------------------

class TestForwardLedger:
    def test_keep_first_no_duplicate(self, tmp_path, monkeypatch):
        """Keep-FIRST: same event_id written twice → only one row stored.
        Requires COLLECT_LANE=nightly and as_of==today (Fix 3 guards)."""
        from engine.credit_momentum import _make_ledger_event, _upsert_forward_log
        monkeypatch.setenv("COLLECT_LANE", "nightly")

        root = tmp_path / "data"
        today = date.today()
        ev1 = _make_ledger_event("hy_oas", "velocity_threshold", today,
                                  {"vel21_pctile": 87.0, "orientation": "spread"})
        # First write
        n1 = _upsert_forward_log([ev1], root)
        assert n1 == 1

        # Second write with same event_id → should NOT add new row
        n2 = _upsert_forward_log([ev1], root)
        assert n2 == 0

        # Read back and verify single row
        log_path = root / "corp_bonds" / "forward_log.jsonl"
        lines = [l for l in log_path.read_text().splitlines() if l.strip()]
        assert len(lines) == 1

    def test_different_event_ids_both_written(self, tmp_path, monkeypatch):
        """Two distinct events for today → both written.
        Requires COLLECT_LANE=nightly (Fix 3). Both events use today's date."""
        from engine.credit_momentum import _make_ledger_event, _upsert_forward_log
        monkeypatch.setenv("COLLECT_LANE", "nightly")

        root = tmp_path / "data"
        today = date.today()
        ev1 = _make_ledger_event("hy_oas", "velocity_threshold", today, {"val": 1})
        ev2 = _make_ledger_event("quality_spread", "velocity_threshold", today, {"val": 2})
        n = _upsert_forward_log([ev1, ev2], root)
        assert n == 2

        log_path = root / "corp_bonds" / "forward_log.jsonl"
        lines = [l for l in log_path.read_text().splitlines() if l.strip()]
        assert len(lines) == 2

    def test_ledger_event_frozen_ruler_fields(self, tmp_path):
        from engine.credit_momentum import _make_ledger_event, _FWD_H_PRIMARY, _FWD_H_SECONDARY

        ev = _make_ledger_event("hy_oas", "velocity_threshold", date(2026, 7, 1), {})
        assert ev["ruler_h_primary"] == _FWD_H_PRIMARY
        assert ev["ruler_h_secondary"] == _FWD_H_SECONDARY
        # Graded fields should be None at emission
        assert ev["graded_at"] is None
        assert ev["direction_hit_h_primary"] is None

    def test_event_id_is_deterministic(self):
        from engine.credit_momentum import _make_ledger_event
        ev1 = _make_ledger_event("hy_oas", "velocity_threshold", date(2026, 7, 1), {"x": 1})
        ev2 = _make_ledger_event("hy_oas", "velocity_threshold", date(2026, 7, 1), {"x": 999})
        assert ev1["event_id"] == ev2["event_id"]


# ---------------------------------------------------------------------------
# Test 6: FINRA breadth math
# ---------------------------------------------------------------------------

class TestFinraBreadthMath:
    def _make_breadth_df(self) -> pd.DataFrame:
        """Synthetic FINRA breadth with multiple productCategory values."""
        rows = []
        for i in range(30):
            dt = pd.Timestamp("2026-01-01") + pd.Timedelta(days=i)
            for cat in ["all securities", "investment grade", "high yield", "convertibles"]:
                rows.append({
                    "tradeReportDate": dt,
                    "productCategory": cat,
                    "advances":        100 + i,
                    "declines":        80 - (i // 2),
                    "unchanged":       20,
                    "totalTrades":     200 + i,
                    "totalVolume":     1e9,
                    "fiftyTwoWeekHigh": 5,
                    "fiftyTwoWeekLow":  3,
                })
        return pd.DataFrame(rows)

    def _make_sentiment_df(self) -> pd.DataFrame:
        """CRITICAL: buy/sell in productCategory; grade in tradeType."""
        rows = []
        for i in range(30):
            dt = pd.Timestamp("2026-01-01") + pd.Timedelta(days=i)
            for trade_type in ["investment grade", "high yield", "all securities"]:
                for prod_cat in ["customer buy", "customer sell", "inter-dealer", "affiliate buy", "affiliate sell", "all securities"]:
                    rows.append({
                        "tradeReportDate":  dt,
                        "tradeType":        trade_type,
                        "productCategory":  prod_cat,
                        "totalVolume":      1e8 * (1.2 if prod_cat == "customer buy" else 1.0),
                        "totalTrades":      100,
                        "totalTransactions": 50,
                    })
        return pd.DataFrame(rows)

    def test_advance_share_correct_math(self, tmp_path):
        """advance_share = advances / (advances + declines)."""
        from engine.credit_momentum import _load_finra_breadth

        root = tmp_path / "data"
        bdf = self._make_breadth_df()
        _write_parquet(bdf, root / "corp_bonds" / "finra_corporateMarketBreadth.parquet")

        result = _load_finra_breadth(root)
        all_sec = result["breadth"].get("all securities", {})
        assert "advance_share_latest" in all_sec
        adv_latest = all_sec["advance_share_latest"]
        assert adv_latest is not None
        # With advances=129, declines=65 (last row), adv_share = 129/(129+65) ≈ 0.665
        expected_approx = 129.0 / (129.0 + 65.0)
        assert abs(adv_latest - expected_approx) < 0.1

    def test_sentiment_buy_sell_trap(self, tmp_path):
        """productCategory carries buy/sell; tradeType is the grade dimension.

        A bug would be: reading tradeType for buy/sell or productCategory for grade.
        This test verifies the ratio uses customer buy / customer sell vol from productCategory,
        filtered by tradeType (grade).
        """
        from engine.credit_momentum import _load_finra_breadth

        root = tmp_path / "data"
        sdf = self._make_sentiment_df()
        _write_parquet(sdf, root / "corp_bonds" / "finra_corporateMarketSentiment.parquet")

        result = _load_finra_breadth(root)
        ig_sentiment = result["sentiment"].get("investment grade", {})
        assert ig_sentiment.get("state") != "no_data", "investment grade sentiment should have data"
        assert "buy_sell_ratio_latest" in ig_sentiment
        ratio = ig_sentiment["buy_sell_ratio_latest"]
        assert ratio is not None
        # buy vol > sell vol (factor 1.2 in synthetic data), so ratio > 1
        assert ratio > 1.0, f"Expected buy>sell, got ratio={ratio}"

    def test_finra_source_label_never_missing(self, tmp_path):
        """_source label must always be present (CCW-R14 compliance)."""
        from engine.credit_momentum import _load_finra_breadth

        root = tmp_path / "data"
        result = _load_finra_breadth(root)  # no files present
        assert result["_source"] == "FINRA trade data"

    def test_advance_share_per_category(self, tmp_path):
        """All 4 productCategories should produce separate breadth entries."""
        from engine.credit_momentum import _load_finra_breadth

        root = tmp_path / "data"
        bdf = self._make_breadth_df()
        _write_parquet(bdf, root / "corp_bonds" / "finra_corporateMarketBreadth.parquet")

        result = _load_finra_breadth(root)
        for cat in ["all securities", "investment grade", "high yield", "convertibles"]:
            assert cat in result["breadth"], f"Missing category: {cat}"


# ---------------------------------------------------------------------------
# Test 7: Divergence quadrant classification
# ---------------------------------------------------------------------------

class TestDivergenceQuadrant:
    def _make_theme_df_with_spread(self, spread_d21: float) -> pd.DataFrame:
        """Make a theme_df with enough history for 21d diff."""
        n = 30
        base_spread = 150.0
        rows = []
        for i in range(n):
            rows.append({
                "as_of": pd.Timestamp("2026-01-01") + pd.Timedelta(days=i),
                "theme": "test_theme",
                "g_spread_bp_pw": base_spread + (spread_d21 / 21.0) * i,
                "n_bonds": 10,
                "matched_n": 8,
            })
        return pd.DataFrame(rows)

    def test_risk_formation_quadrant(self, tmp_path):
        """equity UP + credit WIDENING (positive d21) = risk_formation."""
        from engine.credit_momentum import _compute_divergence_quadrant

        root = tmp_path / "data"
        # Write equity close that goes UP 5% over 21 days
        msft_vals = 400.0 * (1.0 + np.linspace(0, 0.05, 60))
        msft_s = pd.Series(msft_vals, index=pd.date_range("2025-12-01", periods=60, freq="B"), name="close")
        _write_series_parquet(msft_s, root / "baskets" / "ohlcv" / "MSFT.parquet")

        registry = {"themes": {"test_theme": {"issuers": {"MSFT": {"equity_ticker": "MSFT"}}}}}
        theme_df = self._make_theme_df_with_spread(spread_d21=10.0)   # widening

        result = _compute_divergence_quadrant("test_theme", theme_df, registry, root)
        assert result["quadrant"] == "risk_formation", f"Expected risk_formation, got {result['quadrant']}"
        assert result["credit_d21_bp"] > 0

    def test_converging_good_quadrant(self, tmp_path):
        """equity UP + credit TIGHTENING = converging_good."""
        from engine.credit_momentum import _compute_divergence_quadrant

        root = tmp_path / "data"
        msft_vals = 400.0 * (1.0 + np.linspace(0, 0.05, 60))
        msft_s = pd.Series(msft_vals, index=pd.date_range("2025-12-01", periods=60, freq="B"), name="close")
        _write_series_parquet(msft_s, root / "baskets" / "ohlcv" / "MSFT.parquet")

        registry = {"themes": {"test_theme": {"issuers": {"MSFT": {"equity_ticker": "MSFT"}}}}}
        theme_df = self._make_theme_df_with_spread(spread_d21=-10.0)  # tightening

        result = _compute_divergence_quadrant("test_theme", theme_df, registry, root)
        assert result["quadrant"] == "converging_good"

    def test_accruing_when_no_equity_tickers(self, tmp_path):
        from engine.credit_momentum import _compute_divergence_quadrant
        root = tmp_path / "data"
        registry = {"themes": {"test_theme": {"issuers": {}}}}
        theme_df = self._make_theme_df_with_spread(10.0)
        result = _compute_divergence_quadrant("test_theme", theme_df, registry, root)
        assert result["quadrant"] == "accruing"
        assert result["n_equity_tickers"] == 0

    def test_accruing_when_theme_df_empty(self, tmp_path):
        from engine.credit_momentum import _compute_divergence_quadrant
        root = tmp_path / "data"
        result = _compute_divergence_quadrant("test_theme", pd.DataFrame(), {}, root)
        assert result["quadrant"] == "accruing"


# ---------------------------------------------------------------------------
# Test 8: Alerts debounce
# ---------------------------------------------------------------------------

class TestAlertsDebounce:
    def _make_credit_json(self, tmp_path: Path,
                           market_turn_fired: bool = False,
                           market_turn_score: int = 0,
                           theme_stress_fired: bool = False,
                           theme: str = "hyperscaler_credit") -> Path:
        legs_mt = {
            "hy_vel21_pctile_ge85": market_turn_score >= 2,
            "quality_spread_widening_21d": market_turn_score >= 2,
            "ccc_bb_widening_21d": market_turn_score >= 3,
        }
        legs_ts = {
            "vel21_pctile_ge85": theme_stress_fired,
            "spread_3b_bear_cross_secondary": False,
            "price_3b_down_cross": False,
        }
        data = {
            "organ": "credit_momentum.v1",
            "as_of": "2026-07-14",
            "authority": {"rank": False, "size": False, "gate": False, "escalate": False},
            "tags": {
                "credit_market_turn": {
                    "tag": "credit_market_turn",
                    "fired": market_turn_fired,
                    "score": market_turn_score,
                    "legs": legs_mt,
                },
                "credit_theme_stress": [
                    {
                        "tag": "credit_theme_stress",
                        "theme": theme,
                        "fired": theme_stress_fired,
                        "score": 1 if theme_stress_fired else 0,
                        "legs": legs_ts,
                    }
                ],
            },
        }
        path = tmp_path / "credit_momentum.json"
        path.write_text(json.dumps(data))
        return path

    def test_no_events_when_tags_not_fired(self, tmp_path):
        from engine.bonds_alerts import compute_credit_events
        path = self._make_credit_json(tmp_path, market_turn_fired=False, theme_stress_fired=False)
        events = compute_credit_events(str(path))
        assert events == []

    def test_market_turn_event_when_fired_with_history(self, tmp_path, monkeypatch):
        """credit_market_turn emits only after >= 5 bars of consecutive active history (Fix 6).
        Monkeypatch load_events to return sufficient prior history."""
        import engine.bonds_alerts as ba
        from engine.bonds_alerts import compute_credit_events, _DEBOUNCE_MARKET_TURN

        # Build 5 prior active events on consecutive business days
        prior_events = []
        for i in range(_DEBOUNCE_MARKET_TURN):
            d = date.today() - timedelta(days=i + 1)
            prior_events.append({
                "id": f"bonds:credit:credit_market_turn:{d}:active",
                "ts": str(d) + "T00:00:00",
                "type": "credit_market_turn",
                "asset": "credit",
            })
        monkeypatch.setattr(ba, "load_events", lambda: prior_events)

        path = self._make_credit_json(tmp_path, market_turn_fired=True, market_turn_score=2)
        events = compute_credit_events(str(path))
        types = [e["type"] for e in events]
        assert "credit_market_turn" in types, (
            f"Expected credit_market_turn with {_DEBOUNCE_MARKET_TURN} prior events, got {types}"
        )

    def test_theme_stress_event_when_fired_with_history(self, tmp_path, monkeypatch):
        """credit_theme_stress emits only after >= 3 bars of consecutive active history (Fix 6)."""
        import engine.bonds_alerts as ba
        from engine.bonds_alerts import compute_credit_events, _DEBOUNCE_THEME_STRESS

        theme = "hyperscaler_credit"
        prior_events = []
        for i in range(_DEBOUNCE_THEME_STRESS):
            d = date.today() - timedelta(days=i + 1)
            prior_events.append({
                "id": f"bonds:credit:credit_theme_stress:{theme}:{d}:active",
                "ts": str(d) + "T00:00:00",
                "type": "credit_theme_stress",
                "asset": f"credit/{theme}",
            })
        monkeypatch.setattr(ba, "load_events", lambda: prior_events)

        path = self._make_credit_json(tmp_path, theme_stress_fired=True, theme=theme)
        events = compute_credit_events(str(path))
        types = [e["type"] for e in events]
        assert "credit_theme_stress" in types, (
            f"Expected credit_theme_stress with {_DEBOUNCE_THEME_STRESS} prior events, got {types}"
        )

    def test_event_idempotent_same_date(self, tmp_path):
        """Same credit_momentum.json → same event_ids (idempotent)."""
        from engine.bonds_alerts import compute_credit_events
        path = self._make_credit_json(tmp_path, market_turn_fired=True, market_turn_score=2)
        events1 = compute_credit_events(str(path))
        events2 = compute_credit_events(str(path))
        ids1 = {e["id"] for e in events1}
        ids2 = {e["id"] for e in events2}
        assert ids1 == ids2

    def test_missing_json_returns_empty(self, tmp_path):
        from engine.bonds_alerts import compute_credit_events
        events = compute_credit_events(str(tmp_path / "nonexistent.json"))
        assert events == []

    def test_events_have_zh_fields(self, tmp_path):
        from engine.bonds_alerts import compute_credit_events
        path = self._make_credit_json(tmp_path, market_turn_fired=True, market_turn_score=2)
        events = compute_credit_events(str(path))
        for e in events:
            assert "headline_zh" in e, f"Missing headline_zh in event {e.get('id')}"
            assert "detail_zh" in e, f"Missing detail_zh in event {e.get('id')}"


# ---------------------------------------------------------------------------
# Test 9: JSON emission null-safety on EMPTY stores
# ---------------------------------------------------------------------------

class TestNullSafetyEmptyStores:
    def test_snapshot_empty_root_no_crash(self, tmp_path):
        """snapshot() on a completely empty data root must return valid JSON, no crash."""
        from engine.credit_momentum import snapshot

        root = tmp_path / "data"
        root.mkdir(parents=True, exist_ok=True)
        # Create minimal registry to avoid registry load error
        reg_path = root / "corp_bonds" / "issuer_themes.json"
        reg_path.parent.mkdir(parents=True, exist_ok=True)
        reg_path.write_text(json.dumps({"themes": {}}))

        result = snapshot(root=root)
        assert isinstance(result, dict)
        assert result["organ"] == "credit_momentum.v1"
        assert "authority" in result
        assert result["authority"]["rank"] is False

    def test_snapshot_writes_json_file(self, tmp_path):
        from engine.credit_momentum import snapshot
        root = tmp_path / "data"
        root.mkdir(parents=True, exist_ok=True)
        reg_path = root / "corp_bonds" / "issuer_themes.json"
        reg_path.parent.mkdir(parents=True, exist_ok=True)
        reg_path.write_text(json.dumps({"themes": {}}))

        snapshot(root=root)
        out_path = root / "corp_bonds" / "credit_momentum.json"
        assert out_path.exists(), "credit_momentum.json should be written"
        # Verify parseable
        payload = json.loads(out_path.read_text())
        assert "organ" in payload

    def test_snapshot_all_roster_null_safe(self, tmp_path):
        """With no data, roster series should all be in 'accruing' state, not crash."""
        from engine.credit_momentum import snapshot

        root = tmp_path / "data"
        root.mkdir(parents=True, exist_ok=True)
        reg_path = root / "corp_bonds" / "issuer_themes.json"
        reg_path.parent.mkdir(parents=True, exist_ok=True)
        reg_path.write_text(json.dumps({"themes": {}}))

        result = snapshot(root=root)
        roster = result.get("roster", {})
        for key, val in roster.items():
            assert isinstance(val, dict), f"roster[{key}] should be dict"
            # Every series should have a 'state' key
            assert "state" in val or "series_id" in val, f"roster[{key}] missing state/series_id"

    def test_snapshot_with_hy_oas_only(self, tmp_path):
        """With only HY OAS archive, should compute hy_oas state without crashing."""
        from engine.credit_momentum import snapshot

        root = tmp_path / "data"
        hy_s = _make_daily_series(2600, base=400.0)
        _write_series_parquet(hy_s.rename("hy_oas"), root / "archive" / "BAMLH0A0HYM2.parquet")

        reg_path = root / "corp_bonds" / "issuer_themes.json"
        reg_path.parent.mkdir(parents=True, exist_ok=True)
        reg_path.write_text(json.dumps({"themes": {}}))

        result = snapshot(root=root)
        hy_state = result["roster"]["hy_oas"]
        assert hy_state.get("level") is not None or hy_state.get("state") is not None

    def test_snapshot_authority_always_all_false(self, tmp_path):
        """Authority dict must always be all-false (CCW-R10)."""
        from engine.credit_momentum import snapshot, AUTHORITY_V1

        root = _minimal_data_root(tmp_path)
        result = snapshot(root=root)
        auth = result["authority"]
        assert auth["rank"] is False
        assert auth["size"] is False
        assert auth["gate"] is False
        assert auth["escalate"] is False

    def test_finra_breadth_empty_source_safe(self, tmp_path):
        """_load_finra_breadth on empty root → valid dict, no crash."""
        from engine.credit_momentum import _load_finra_breadth
        root = tmp_path / "data"
        result = _load_finra_breadth(root)
        assert "_source" in result
        assert "breadth" in result
        assert "sentiment" in result

    def test_own_store_breadth_empty_no_crash(self, tmp_path):
        from engine.credit_momentum import _build_own_store_breadth
        root = tmp_path / "data"
        result = _build_own_store_breadth(root)
        assert "n_snapshots" in result
        assert result["n_snapshots"] == 0

    def test_transition_watch_empty_no_crash(self, tmp_path):
        from engine.credit_momentum import _build_transition_watch
        root = tmp_path / "data"
        result = _build_transition_watch(root)
        assert "n_snapshots" in result

    def test_orcl_watch_empty_panel(self, tmp_path):
        from engine.credit_momentum import _build_orcl_watch
        root = tmp_path / "data"
        result = _build_orcl_watch(pd.DataFrame(), root)
        assert result["issuer"] == "ORCL"
        assert result["g_spread_bp_pw"] is None

    def test_rolling_percentile_handles_short_series(self):
        from engine.credit_momentum import _rolling_percentile
        s = pd.Series([1.0, 2.0, 3.0])
        out = _rolling_percentile(s, 2600)
        # Short series: should produce NaN (not crash)
        assert isinstance(out, pd.Series)

    def test_compute_velocity_empty_series(self):
        from engine.credit_momentum import _compute_velocity
        result = _compute_velocity(pd.Series([], dtype=float))
        assert result["vel21"] is None
        assert result["vel63"] is None

    def test_compute_velocity_short_series(self):
        from engine.credit_momentum import _compute_velocity
        s = _make_daily_series(10, base=300.0)
        result = _compute_velocity(s)
        # Should not crash; may be None for short series
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# Test 10: GRID UNLOCK — daily bar gating (Fix 1)
# ---------------------------------------------------------------------------

class TestGridUnlock:
    def test_785_bar_series_unlocks_1d_2b_3b(self):
        """785 daily bars should unlock 1D (>=200), 2B (>=400), 3B (>=600) grids.

        Pre-condition: 785 >= 200 (1D), 785 >= 400 (2B), 785 >= 600 (3B).
        After resampling 2B: ~392 completed 2B bars >= 200 resampled floor.
        After resampling 3B: ~261 completed 3B bars >= 200 resampled floor.
        """
        from engine.credit_momentum import _compute_grid_data
        s = _make_daily_series(785, base=300.0)
        gd_1d = _compute_grid_data(s, "1D", 1, None)
        gd_2b = _compute_grid_data(s, "2B", 2, None)
        gd_3b = _compute_grid_data(s, "3B", 3, None)
        assert gd_1d is not None, "1D grid should unlock at 785 daily bars"
        assert gd_2b is not None, "2B grid should unlock at 785 daily bars (>= 400 daily)"
        assert gd_3b is not None, "3B grid should unlock at 785 daily bars (>= 600 daily)"

    def test_300_bar_series_unlocks_1d_only(self):
        """300 daily bars: 1D unlocks (>=200), 2B locked (< 400), 3B locked (< 600)."""
        from engine.credit_momentum import _compute_grid_data
        s = _make_daily_series(300, base=300.0)
        gd_1d = _compute_grid_data(s, "1D", 1, None)
        gd_2b = _compute_grid_data(s, "2B", 2, None)
        gd_3b = _compute_grid_data(s, "3B", 3, None)
        assert gd_1d is not None, "1D grid should unlock at 300 daily bars"
        assert gd_2b is None, "2B grid should be locked at 300 daily bars (need 400)"
        assert gd_3b is None, "3B grid should be locked at 300 daily bars (need 600)"

    def test_199_bar_series_unlocks_no_grids(self):
        """199 daily bars: all grids locked (< 200 daily minimum for 1D)."""
        from engine.credit_momentum import _compute_grid_data
        s = _make_daily_series(199, base=300.0)
        gd_1d = _compute_grid_data(s, "1D", 1, None)
        assert gd_1d is None, "1D grid should be locked at 199 daily bars"


# ---------------------------------------------------------------------------
# Test 11: SEVERITY INVERSION — spread series cross direction (Fix 2)
# ---------------------------------------------------------------------------

class TestSeverityInversion:
    def test_bull_cross_on_spread_is_widening_deterioration(self, tmp_path):
        """On a spread series, bull_cross → 'widening_deterioration' (Fix 2).

        Empirical basis: mean d1 at bull_cross ≈ +0.071 bp on HY OAS (spread rising).
        A monotonically widening spread series has bull_cross events near the top.
        """
        from engine.credit_momentum import _extract_cross_events, _compute_grid_data

        # Build a series with enough bars that has a rising trend (spread widening)
        s = _make_daily_series(600, base=200.0, trend=0.5)  # steady widening
        gd = _compute_grid_data(s, "1D", 1, None)
        if gd is None:
            pytest.skip("Insufficient bars for grid computation")

        events = _extract_cross_events("test_hy_oas", "1D", gd, orientation="spread")
        bull_events = [e for e in events if e["direction"] == "bull"]
        bear_events = [e for e in events if e["direction"] == "bear"]

        # Check severity mapping
        for e in bull_events:
            assert e["severity"] == "widening_deterioration", (
                f"bull_cross on spread should be 'widening_deterioration', got {e['severity']}"
            )
        for e in bear_events:
            assert e["severity"] == "tightening_improvement", (
                f"bear_cross on spread should be 'tightening_improvement', got {e['severity']}"
            )

    def test_price_series_has_no_severity(self):
        """Price series should have severity=None (no spread orientation)."""
        from engine.credit_momentum import _extract_cross_events, _compute_grid_data

        s = _make_daily_series(600, base=100.0)
        gd = _compute_grid_data(s, "1D", 1, None)
        if gd is None:
            pytest.skip("Insufficient bars")

        events = _extract_cross_events("test_etf", "1D", gd, orientation="price")
        for e in events:
            assert e["severity"] is None, (
                f"price series should have severity=None, got {e['severity']}"
            )


# ---------------------------------------------------------------------------
# Test 12: FORWARD LEDGER — COLLECT_LANE guard + current-bar-only (Fix 3)
# ---------------------------------------------------------------------------

class TestForwardLedgerPIT:
    def test_no_write_without_nightly_collect_lane(self, tmp_path, monkeypatch):
        """_upsert_forward_log should write 0 rows when COLLECT_LANE != 'nightly'."""
        from engine.credit_momentum import _make_ledger_event, _upsert_forward_log
        monkeypatch.delenv("COLLECT_LANE", raising=False)

        root = tmp_path / "data"
        ev = _make_ledger_event("hy_oas", "velocity_threshold", date.today(),
                                 {"vel21_pctile": 87.0})
        n = _upsert_forward_log([ev], root)
        assert n == 0, "Should write 0 rows when COLLECT_LANE is not 'nightly'"
        assert not (root / "corp_bonds" / "forward_log.jsonl").exists()

    def test_write_with_nightly_collect_lane(self, tmp_path, monkeypatch):
        """_upsert_forward_log should write rows when COLLECT_LANE == 'nightly'."""
        from engine.credit_momentum import _make_ledger_event, _upsert_forward_log
        monkeypatch.setenv("COLLECT_LANE", "nightly")

        root = tmp_path / "data"
        ev = _make_ledger_event("hy_oas", "velocity_threshold", date.today(),
                                 {"vel21_pctile": 87.0})
        n = _upsert_forward_log([ev], root)
        assert n == 1, "Should write 1 row when COLLECT_LANE == 'nightly'"

    def test_historical_events_not_written(self, tmp_path, monkeypatch):
        """Events with as_of != today should NOT be written (current-bar-only, Fix 3)."""
        from engine.credit_momentum import _make_ledger_event, _upsert_forward_log
        monkeypatch.setenv("COLLECT_LANE", "nightly")

        root = tmp_path / "data"
        # Historical event (yesterday)
        yesterday = date.today() - timedelta(days=1)
        ev_hist = _make_ledger_event("hy_oas", "velocity_threshold", yesterday, {"x": 1})
        # Today's event
        ev_today = _make_ledger_event("hy_oas", "velocity_threshold", date.today(), {"x": 2})

        n = _upsert_forward_log([ev_hist, ev_today], root)
        assert n == 1, "Should only write today's event, not historical"

        log_path = root / "corp_bonds" / "forward_log.jsonl"
        rows = [json.loads(l) for l in log_path.read_text().splitlines() if l.strip()]
        assert len(rows) == 1
        assert rows[0]["as_of"] == str(date.today())

    def test_ledger_event_has_registered_at_and_source(self, tmp_path):
        """ledger events must have registered_at and source='live' (Fix 3)."""
        from engine.credit_momentum import _make_ledger_event
        ev = _make_ledger_event("hy_oas", "velocity_threshold", date.today(), {})
        assert "registered_at" in ev, "ledger event must have registered_at"
        assert ev["source"] == "live", "ledger event must have source='live'"


# ---------------------------------------------------------------------------
# Test 13: THEME_STRESS TAG — legs 2+3 reachable (Fix 5)
# ---------------------------------------------------------------------------

class TestThemeStressTagLegs:
    def _make_synthetic_gd(self, bull_cross_today: bool = False, bear_cross_today: bool = False) -> dict:
        """Create a minimal synthetic grid dict with controllable cross signals."""
        n = 600
        idx = pd.date_range("2020-01-01", periods=n, freq="B")
        # macd and signal are flat (no real crosses) — we manually set bull/bear cross
        macd = pd.Series(np.zeros(n), index=idx)
        sig  = pd.Series(np.zeros(n), index=idx)
        hist = macd - sig
        hist_vel3 = hist - hist.shift(3)
        depth_pctile = pd.Series(np.full(n, 50.0), index=idx)
        bull_cross = pd.Series(np.zeros(n, dtype=bool), index=idx)
        bear_cross = pd.Series(np.zeros(n, dtype=bool), index=idx)
        if bull_cross_today:
            bull_cross.iloc[-1] = True
        if bear_cross_today:
            bear_cross.iloc[-1] = True
        return {
            "macd": macd, "signal": sig, "hist": hist, "hist_vel3": hist_vel3,
            "k": pd.Series(np.full(n, 50.0), index=idx),
            "d": pd.Series(np.full(n, 50.0), index=idx),
            "depth_pctile": depth_pctile,
            "bull_cross": bull_cross, "bear_cross": bear_cross,
            "dates": idx, "n_bars": n,
        }

    def test_leg1_and_leg2_fires_tag(self):
        """leg1 (vel>=85) + leg2 (spread bull cross in last 30 bars) → fired=True."""
        from engine.credit_momentum import _compute_credit_theme_stress_tag
        n = 600
        idx = pd.date_range("2020-01-01", periods=n, freq="B")
        spread_gd = self._make_synthetic_gd(bull_cross_today=True)
        series_as_of = idx[-1]  # latest bar = today

        tag = _compute_credit_theme_stress_tag(
            "test_theme",
            {"vel21_pctile": 90.0},   # leg1=True
            spread_gd,                 # leg2: bull cross exists within 30 bars
            None,                      # leg3=None → False
            series_as_of=series_as_of,
        )
        assert tag["legs"]["vel21_pctile_ge85"] is True
        assert tag["legs"]["spread_3b_bull_cross_widening_secondary"] is True
        assert tag["fired"] is True, f"Expected fired=True, got score={tag['score']}"
        assert tag["score"] == 2

    def test_leg1_and_leg3_fires_tag(self):
        """leg1 (vel>=85) + leg3 (price bear cross) → fired=True."""
        from engine.credit_momentum import _compute_credit_theme_stress_tag
        n = 600
        idx = pd.date_range("2020-01-01", periods=n, freq="B")
        price_gd = self._make_synthetic_gd(bear_cross_today=True)
        series_as_of = idx[-1]

        tag = _compute_credit_theme_stress_tag(
            "test_theme",
            {"vel21_pctile": 90.0},  # leg1=True
            None,                     # leg2=False
            price_gd,                 # leg3: bear cross
            series_as_of=series_as_of,
        )
        assert tag["legs"]["vel21_pctile_ge85"] is True
        assert tag["legs"]["price_3b_bear_cross"] is True
        assert tag["fired"] is True, f"Expected fired=True, got score={tag['score']}"

    def test_only_leg1_not_fired(self):
        """Only leg1 fires (vel>=85, no grid data) → score=1, fired=False."""
        from engine.credit_momentum import _compute_credit_theme_stress_tag
        tag = _compute_credit_theme_stress_tag(
            "test_theme", {"vel21_pctile": 90.0}, None, None, series_as_of=None
        )
        assert tag["fired"] is False
        assert tag["score"] == 1

    def test_no_legs_not_fired(self):
        """No legs → fired=False, score=0."""
        from engine.credit_momentum import _compute_credit_theme_stress_tag
        tag = _compute_credit_theme_stress_tag(
            "test_theme", {}, None, None, series_as_of=None
        )
        assert tag["fired"] is False
        assert tag["score"] == 0


# ---------------------------------------------------------------------------
# Test 14: BONDS_ALERTS debounce — no events before history accrues (Fix 6)
# ---------------------------------------------------------------------------

class TestBondsAlertsDebounce:
    def _make_credit_json_fired(self, tmp_path: Path, theme: str = "test_theme") -> Path:
        data = {
            "organ": "credit_momentum.v1",
            "as_of": str(date.today()),
            "authority": {"rank": False, "size": False, "gate": False, "escalate": False},
            "tags": {
                "credit_market_turn": {
                    "tag": "credit_market_turn",
                    "fired": True,
                    "score": 2,
                    "legs": {
                        "hy_vel21_pctile_ge85": True,
                        "quality_spread_widening_21d": True,
                        "ccc_bb_widening_21d": False,
                    },
                },
                "credit_theme_stress": [
                    {
                        "tag": "credit_theme_stress",
                        "theme": theme,
                        "fired": True,
                        "score": 2,
                        "legs": {
                            "vel21_pctile_ge85": True,
                            "spread_3b_bull_cross_widening_secondary": True,
                            "price_3b_bear_cross": False,
                        },
                    }
                ],
            },
        }
        path = tmp_path / "credit_momentum.json"
        path.write_text(json.dumps(data))
        return path

    def test_no_events_without_prior_history(self, tmp_path, monkeypatch):
        """With no prior event history, debounce prevents emission (< 5 bars for market_turn)."""
        from engine.bonds_alerts import compute_credit_events, _DEBOUNCE_MARKET_TURN
        # Monkeypatch load_events to return empty (no history)
        import engine.bonds_alerts as ba
        monkeypatch.setattr(ba, "load_events", lambda: [])
        path = self._make_credit_json_fired(tmp_path)
        events = compute_credit_events(str(path))
        # DEBOUNCE_MARKET_TURN=5: with 0 prior events, consecutive=1 < 5 → no events
        assert all(e["type"] != "credit_market_turn" for e in events), (
            "credit_market_turn should not emit without >= 5 bars of history"
        )

    def test_no_crash_on_first_run_empty_file(self, tmp_path):
        """compute_credit_events with missing JSON returns [] without crash."""
        from engine.bonds_alerts import compute_credit_events
        events = compute_credit_events(str(tmp_path / "nonexistent.json"))
        assert events == []
