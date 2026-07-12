"""Tests for engine/t0_indicator.py — T0 beta turn indicator.

All fixtures are synthetic (hand-built). No repo data dependencies.
"""
from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from engine.t0_indicator import T0_D3K_MAX, build_artifact, write_artifact


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_d1_grid(ticker: str, xup_bars: float | None, k: float | None = 25.0, d: float | None = 22.0) -> pd.DataFrame:
    """Build a minimal d1_grid DataFrame with one ticker row."""
    row = {
        "d1_k": k,
        "d1_d": d,
        "d1_kd_xup_bars": xup_bars,
        "d1_macd": 0.0,
        "d1_sig": 0.0,
        "d1_macd_xup_bars": None,
        "d1_from_os": True,
        "d1_ob": False,
    }
    return pd.DataFrame([row], index=[ticker])


def _make_closes(tickers: list[str], n: int = 300) -> pd.DataFrame:
    """Simple declining close panel with n bars."""
    dates = pd.bdate_range("2023-01-01", periods=n)
    data = {t: np.linspace(100.0, 50.0, n) for t in tickers}
    return pd.DataFrame(data, index=dates)


def _make_d3_map(ticker: str, k: float | None, d: float | None = 25.0) -> dict:
    return {ticker: {"d3_k": k, "d3_d": d, "d3_macd": 0.0, "d3_sig": 0.0}}


# ---------------------------------------------------------------------------
# Unit tests — T0 condition gates
# ---------------------------------------------------------------------------

class TestBuildArtifactGates:
    """Test that T0 filters match/exclude correctly."""

    def test_fires_when_d3k_21_and_xup0(self):
        """d3_k=21 and xup=0 -> match."""
        ticker = "AAPL"
        d1 = _make_d1_grid(ticker, xup_bars=0.0)
        d3 = _make_d3_map(ticker, k=21.0)
        closes = _make_closes([ticker])
        art = build_artifact(d1_grid=d1, d3_map=d3, closes=closes, asof="2024-01-02")
        assert len(art["matches"]) == 1
        assert art["matches"][0]["ticker"] == ticker
        assert art["matches"][0]["d3_k"] == pytest.approx(21.0, abs=0.001)

    def test_excluded_when_d3k_exactly_30_boundary(self):
        """d3_k=30.0 is excluded (strict <, boundary case)."""
        ticker = "MSFT"
        d1 = _make_d1_grid(ticker, xup_bars=0.0)
        d3 = _make_d3_map(ticker, k=T0_D3K_MAX)  # exactly 30.0
        closes = _make_closes([ticker])
        art = build_artifact(d1_grid=d1, d3_map=d3, closes=closes, asof="2024-01-02")
        assert len(art["matches"]) == 0

    def test_included_at_29_99(self):
        """d3_k=29.99 is included (strictly below 30.0)."""
        ticker = "NVDA"
        d1 = _make_d1_grid(ticker, xup_bars=0.0)
        d3 = _make_d3_map(ticker, k=29.99)
        closes = _make_closes([ticker])
        art = build_artifact(d1_grid=d1, d3_map=d3, closes=closes, asof="2024-01-02")
        assert len(art["matches"]) == 1

    def test_excluded_when_xup_is_1(self):
        """xup_bars=1.0 (cross happened one bar ago) -> excluded."""
        ticker = "AMZN"
        d1 = _make_d1_grid(ticker, xup_bars=1.0)
        d3 = _make_d3_map(ticker, k=21.0)
        closes = _make_closes([ticker])
        art = build_artifact(d1_grid=d1, d3_map=d3, closes=closes, asof="2024-01-02")
        assert len(art["matches"]) == 0

    def test_excluded_when_xup_is_none(self):
        """xup_bars=None (no cross within 15 bars) -> excluded."""
        ticker = "GOOGL"
        d1 = _make_d1_grid(ticker, xup_bars=None)
        d3 = _make_d3_map(ticker, k=21.0)
        closes = _make_closes([ticker])
        art = build_artifact(d1_grid=d1, d3_map=d3, closes=closes, asof="2024-01-02")
        assert len(art["matches"]) == 0

    def test_excluded_when_xup_is_nan(self):
        """xup_bars=NaN -> excluded."""
        ticker = "META"
        d1 = _make_d1_grid(ticker, xup_bars=float("nan"))
        d3 = _make_d3_map(ticker, k=21.0)
        closes = _make_closes([ticker])
        art = build_artifact(d1_grid=d1, d3_map=d3, closes=closes, asof="2024-01-02")
        assert len(art["matches"]) == 0

    def test_excluded_when_d3k_is_none(self):
        """d3_k=None -> excluded."""
        ticker = "TSLA"
        d1 = _make_d1_grid(ticker, xup_bars=0.0)
        d3 = _make_d3_map(ticker, k=None)
        closes = _make_closes([ticker])
        art = build_artifact(d1_grid=d1, d3_map=d3, closes=closes, asof="2024-01-02")
        assert len(art["matches"]) == 0

    def test_empty_d1_grid_zero_matches(self):
        """Empty d1_grid -> valid artifact with 0 matches."""
        d1 = pd.DataFrame()  # empty
        d3 = _make_d3_map("XYZ", k=15.0)
        closes = _make_closes(["XYZ"])
        art = build_artifact(d1_grid=d1, d3_map=d3, closes=closes, asof="2024-01-02")
        assert isinstance(art, dict)
        assert art["matches"] == []
        assert art["universe_n"] == 1

    def test_sort_order_dollar_adv_desc_none_last(self):
        """Matches sorted by dollar_adv_20d descending, None last."""
        tickers = ["A", "B", "C", "D"]
        rows = [
            {"d1_k": 25.0, "d1_d": 22.0, "d1_kd_xup_bars": 0.0,
             "d1_macd": 0.0, "d1_sig": 0.0, "d1_macd_xup_bars": None,
             "d1_from_os": True, "d1_ob": False},
        ] * len(tickers)
        d1 = pd.DataFrame(rows, index=tickers)
        d3 = {t: {"d3_k": 20.0, "d3_d": 18.0} for t in tickers}
        closes = _make_closes(tickers)
        liq = {
            "A": {"adv_dollar_20d_median": 1_000_000.0},
            "B": {"adv_dollar_20d_median": 5_000_000.0},
            "C": {"adv_dollar_20d_median": None},
            "D": {"adv_dollar_20d_median": 2_000_000.0},
        }
        art = build_artifact(d1_grid=d1, d3_map=d3, closes=closes, asof="2024-01-02",
                             liq_map=liq)
        result_tickers = [m["ticker"] for m in art["matches"]]
        # B=5M, D=2M, A=1M, C=None
        assert result_tickers == ["B", "D", "A", "C"]


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------

class TestArtifactSchema:
    """Verify all frozen top-level keys are present and authority flags correct."""

    def _sample_artifact(self) -> dict:
        ticker = "SPY"
        d1 = _make_d1_grid(ticker, xup_bars=0.0)
        d3 = _make_d3_map(ticker, k=20.0)
        closes = _make_closes([ticker])
        return build_artifact(d1_grid=d1, d3_map=d3, closes=closes, asof="2024-06-01",
                              sector_map={"SPY": "ETF"},
                              liq_map={"SPY": {"adv_dollar_20d_median": 9e9}})

    def test_all_top_level_keys_present(self):
        art = self._sample_artifact()
        expected = {
            "schema", "as_of", "generated_utc", "params", "universe_n",
            "matches", "authority", "disclosure_en", "disclosure_zh",
        }
        assert expected.issubset(set(art.keys()))

    def test_schema_field(self):
        art = self._sample_artifact()
        assert art["schema"] == "t0_indicator.v1"

    def test_authority_tier_is_display(self):
        art = self._sample_artifact()
        assert art["authority"]["tier"] == "display"

    def test_authority_all_action_flags_false(self):
        art = self._sample_artifact()
        auth = art["authority"]
        for flag in ("may_rank", "may_gate", "may_size", "may_escalate"):
            assert auth[flag] is False, f"authority.{flag} must be False"

    def test_generated_utc_parses_as_iso8601(self):
        art = self._sample_artifact()
        ts = art["generated_utc"]
        # Must parse without error; datetime.fromisoformat handles +00:00 suffix
        parsed = datetime.fromisoformat(ts)
        assert parsed.tzinfo is not None, "generated_utc must be tz-aware"

    def test_params_frozen_keys(self):
        art = self._sample_artifact()
        params = art["params"]
        assert params["d3_k_max"] == T0_D3K_MAX
        assert params["cross_age_bars"] == 0
        assert params["d3_grid"] == "3B"
        assert params["d1_grid"] == "1B"

    def test_match_fields(self):
        art = self._sample_artifact()
        assert len(art["matches"]) == 1
        m = art["matches"][0]
        for field in ("ticker", "d3_k", "d3_d", "d1_k", "d1_d", "close", "sector", "dollar_adv_20d"):
            assert field in m, f"match missing field: {field}"
        assert m["ticker"] == "SPY"
        assert m["sector"] == "ETF"

    def test_as_of_passed_through(self):
        art = self._sample_artifact()
        assert art["as_of"] == "2024-06-01"

    def test_disclosure_en_no_buy_verb(self):
        art = self._sample_artifact()
        text = art["disclosure_en"].lower()
        assert "buy now" not in text
        assert "act now" not in text

    def test_universe_n_matches_closes_columns(self):
        ticker = "QQQ"
        d1 = _make_d1_grid(ticker, xup_bars=0.0)
        d3 = _make_d3_map(ticker, k=15.0)
        closes = _make_closes(["QQQ", "SPY", "IWM"])  # 3 tickers
        art = build_artifact(d1_grid=d1, d3_map=d3, closes=closes, asof="2024-01-01")
        assert art["universe_n"] == 3


# ---------------------------------------------------------------------------
# Integration test — synthetic price series through actual engines
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def integration_synth_data():
    """Build synthetic close, d1_grid, and d3_map.

    Fixture shape (verified to fire the T0 condition):
      - 600 business-day close series starting 2020-01-01.
      - Noisy decline at -0.6%/day avg (seed=999) keeps RSI depressed.
      - Last 4 bars: -1.5%, -1.5%, +2.0%, +1.5% — the two up bars create a
        1D StochRSI K-above-D cross on the final bar (xup_bars=0).
      - The 3B grid (resample('3B').last()) is fully in oversold territory
        (d3_k ≈ 0) because the 3B RSI range denominator sees mostly declining
        prices even after the 2-bar bounce.

    Do NOT change the seed or the last-bar log-returns without re-verifying
    that both conditions still hold (d3_k < 30 AND d1_kd_xup_bars == 0).
    """
    from engine.pick_lab import signals_1d as _s1d
    from engine.signal_quality import signal_frame as _sf

    ticker = "SYNTH"
    np.random.seed(999)
    n = 600
    dates = pd.bdate_range("2020-01-01", periods=n)

    # Noisy declining log-returns; last 4 bars overridden for the T0 cross
    log_rets = np.random.normal(-0.006, 0.010, n)
    log_rets[-4] = -0.015   # down
    log_rets[-3] = -0.015   # down
    log_rets[-2] = 0.020    # up (creates K lift)
    log_rets[-1] = 0.015    # up (K crosses D on this bar)

    prices = 100 * np.exp(np.cumsum(log_rets))
    prices = np.insert(prices, 0, 100.0)[:n]
    close = pd.Series(prices, index=dates, name=ticker)
    close_panel = close.to_frame()

    # Compute 1D grid (signals_1d)
    d1_grid = _s1d.compute_grids(close_panel)

    # Compute 3B signal_frame to extract d3_k
    sf3 = _sf(close)
    d3_map: dict = {}
    if not sf3.empty and len(sf3) >= 2:
        last3 = sf3.iloc[-1]
        k3 = float(last3["k"]) if pd.notna(last3["k"]) else None
        d3 = float(last3["d"]) if pd.notna(last3["d"]) else None
        d3_map[ticker] = {"d3_k": k3, "d3_d": d3}
    else:
        d3_map[ticker] = {"d3_k": None, "d3_d": None}

    return ticker, close_panel, d1_grid, d3_map


class TestIntegrationWithRealEngines:
    """End-to-end: synthetic price -> compute_grids + signal_frame -> build_artifact.

    We construct a daily close series that achieves both T0 conditions:
      - 3B-grid StochRSI K < 30 (oversold).
      - 1D StochRSI K crossed above D on the latest daily bar (xup_bars == 0).

    We assert the ticker appears in matches; if the fixture fails to achieve the
    T0 condition we print diagnostic info and FAIL (we do not weaken the assertion).
    """

    def test_build_artifact_runs_end_to_end(self, integration_synth_data):
        """build_artifact completes without error on synthetic data."""
        ticker, close_panel, d1_grid, d3_map = integration_synth_data
        art = build_artifact(
            d1_grid=d1_grid,
            d3_map=d3_map,
            closes=close_panel,
            asof="2024-06-01",
        )
        assert isinstance(art, dict)
        assert art["schema"] == "t0_indicator.v1"

    def test_fixture_fires_t0_condition(self, integration_synth_data):
        """The synthetic fixture achieves T0 condition and ticker appears in matches.

        Diagnostic info printed if it fails so the fixture can be tuned.
        """
        ticker, close_panel, d1_grid, d3_map = integration_synth_data

        d3_info = d3_map.get(ticker, {})
        d3_k = d3_info.get("d3_k")

        xup_bars = None
        if not d1_grid.empty and ticker in d1_grid.index:
            xup_bars = d1_grid.loc[ticker].get("d1_kd_xup_bars")

        art = build_artifact(
            d1_grid=d1_grid,
            d3_map=d3_map,
            closes=close_panel,
            asof="2024-06-01",
        )

        matched = [m for m in art["matches"] if m["ticker"] == ticker]

        if not matched:
            # Detailed diagnostics to help tune the fixture
            pytest.fail(
                f"T0 fixture did not fire. "
                f"d3_k={d3_k!r} (need < {T0_D3K_MAX}), "
                f"d1_kd_xup_bars={xup_bars!r} (need == 0.0). "
                f"Reshape the fixture: increase decline length/slope or adjust "
                f"final up-bars so K crosses D exactly on the last bar."
            )

        m = matched[0]
        assert m["d3_k"] is not None
        assert m["d3_k"] < T0_D3K_MAX
        # Close should be a positive number
        assert m["close"] is not None and m["close"] > 0

    def test_write_artifact_roundtrip(self, integration_synth_data, tmp_path):
        """write_artifact writes valid JSON that round-trips back to the artifact."""
        import json

        ticker, close_panel, d1_grid, d3_map = integration_synth_data
        art = build_artifact(
            d1_grid=d1_grid,
            d3_map=d3_map,
            closes=close_panel,
            asof="2024-06-01",
        )
        out_path = write_artifact(art, tmp_path)
        assert out_path.exists()
        loaded = json.loads(out_path.read_text())
        assert loaded["schema"] == "t0_indicator.v1"
        assert "matches" in loaded
        assert loaded["universe_n"] == art["universe_n"]
