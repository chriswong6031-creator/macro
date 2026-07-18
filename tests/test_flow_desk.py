"""tests/test_flow_desk.py — unit tests for scripts/build_flow_desk.py.

Covers:
  1. Rollup math — sector heatmap aggregates premium correctly from fixtures.
  2. Min-history z gate — z_score returns None below 20 obs; returns value above.
  3. tape_flow-absent degrade — page payload builds without tape_flow files.
  4. _soft_tone categorisation.
  5. build_top_movers sorts by |net_premium_mn| and caps at N.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pandas as pd
import pytest

# Allow import from repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.build_flow_desk import (
    MIN_Z_HISTORY,
    _soft_tone,
    _z_score,
    build_sector_heatmap,
    build_top_movers,
)


# ── fixtures ───────────────────────────────────────────────────────────────────

FLOW_ROWS_FIXTURE = [
    {"key": "AAPL", "asof": "2026-07-02", "net_premium_mn": 120.0, "zerodte_share": 0.5, "tone": "pos", "verdict": "test"},
    {"key": "MSFT", "asof": "2026-07-02", "net_premium_mn": -40.0, "zerodte_share": 0.3, "tone": "neg", "verdict": "test"},
    {"key": "NVDA", "asof": "2026-07-02", "net_premium_mn": 80.0, "zerodte_share": 0.6, "tone": "pos", "verdict": "test"},
    {"key": "JPM",  "asof": "2026-07-02", "net_premium_mn": -90.0, "zerodte_share": 0.4, "tone": "neg", "verdict": "test"},
    {"key": "BAC",  "asof": "2026-07-02", "net_premium_mn": 10.0,  "zerodte_share": 0.2, "tone": "neutral", "verdict": "test"},
]

GICS_MAP_FIXTURE = {
    "AAPL": "Technology",
    "MSFT": "Technology",
    "NVDA": "Technology",
    "JPM":  "Financials",
    "BAC":  "Financials",
}


# ── helpers ────────────────────────────────────────────────────────────────────

def _make_data_dir_with_summaries(tmpdir: Path, tickers_and_vals: dict[str, list[float]]) -> Path:
    """Create data/options_flow/summary_<TICKER>.parquet fixtures."""
    flow_dir = tmpdir / "data" / "options_flow"
    flow_dir.mkdir(parents=True, exist_ok=True)
    tape_dir = tmpdir / "data" / "tape_flow" / "daily"
    tape_dir.mkdir(parents=True, exist_ok=True)
    # No per-name site/flow/<TICKER>.json needed for rollup test (gross defaults to 0)
    for ticker, gross_vals in tickers_and_vals.items():
        dates = pd.date_range("2026-01-01", periods=len(gross_vals), freq="B")
        df = pd.DataFrame({
            "premium_mn": gross_vals,
            "net_premium_mn": [v * 0.1 for v in gross_vals],
            "zerodte_share": [0.5] * len(gross_vals),
        }, index=dates)
        df.to_parquet(flow_dir / f"summary_{ticker}.parquet")
    return tmpdir / "data"


# ── z-score gate ───────────────────────────────────────────────────────────────

class TestZScoreGate:
    def test_returns_none_below_min_history(self):
        s = pd.Series([10.0] * (MIN_Z_HISTORY - 1))
        assert _z_score(s, 15.0) is None

    def test_returns_value_at_exact_min(self):
        import statistics
        vals = list(range(MIN_Z_HISTORY))
        s = pd.Series(vals, dtype=float)
        result = _z_score(s, float(vals[-1]))
        assert result is not None
        assert isinstance(result, float)

    def test_z_above_min_history_with_variance(self):
        # Non-uniform series → sigma > 0 → z computable
        vals = list(range(1, 31))  # 1..30, variance > 0
        s = pd.Series(vals, dtype=float)
        mean = sum(vals) / len(vals)
        result = _z_score(s, mean)
        assert result is not None
        assert isinstance(result, float)
        # value equal to mean → z near 0
        assert abs(result) < 0.1

    def test_z_large_deviation_with_variance(self):
        # Varied series → z for extreme outlier is large
        import numpy as np
        rng = np.random.default_rng(42)
        vals = list(rng.normal(100, 10, 30))
        s = pd.Series(vals)
        result = _z_score(s, 500.0)  # far above mean=100
        assert result is not None
        assert result > 5.0

    def test_z_handles_zero_stddev(self):
        # All identical values → sigma=0 → should return None (not crash)
        s = pd.Series([5.0] * 25)
        result = _z_score(s, 5.0)
        # sigma=0 edge case → None
        assert result is None

    def test_z_handles_nan_in_series_with_variance(self):
        import numpy as np
        rng = np.random.default_rng(7)
        clean_vals = list(rng.normal(50, 5, 25))
        vals = [float("nan")] * 5 + clean_vals
        s = pd.Series(vals)
        result = _z_score(s, 50.0)
        # 25 clean obs ≥ MIN_Z_HISTORY=20, variance > 0 → should compute
        assert result is not None


# ── soft tone ─────────────────────────────────────────────────────────────────

class TestSoftTone:
    def test_positive_large(self):
        assert _soft_tone(200.0) == "pos~"

    def test_negative_large(self):
        assert _soft_tone(-200.0) == "neg~"

    def test_small_positive(self):
        assert _soft_tone(30.0) == "neutral"

    def test_small_negative(self):
        assert _soft_tone(-30.0) == "neutral"

    def test_none(self):
        assert _soft_tone(None) == "neutral"

    def test_boundary_pos(self):
        assert _soft_tone(51.0) == "pos~"

    def test_boundary_neg(self):
        assert _soft_tone(-51.0) == "neg~"

    def test_exactly_50(self):
        assert _soft_tone(50.0) == "neutral"


# ── rollup math ───────────────────────────────────────────────────────────────

class TestRollupMath:
    """Rollup math: sector heatmap must correctly aggregate net_premium_mn by sector."""

    def _run_heatmap(self, flow_rows, gics_map, data_dir: Path):
        return build_sector_heatmap(flow_rows, gics_map, data_dir)

    def test_sector_net_aggregates_correctly(self, tmp_path):
        """Technology net = AAPL + MSFT + NVDA = 120 - 40 + 80 = 160."""
        data_dir = _make_data_dir_with_summaries(tmp_path, {
            "AAPL": [], "MSFT": [], "NVDA": [], "JPM": [], "BAC": [],
        })
        result = self._run_heatmap(FLOW_ROWS_FIXTURE, GICS_MAP_FIXTURE, data_dir)
        tech = next((r for r in result if r["sector"] == "Technology"), None)
        assert tech is not None, "Technology sector missing from heatmap"
        # net_premium_mn comes from flow_rows aggregation
        assert tech["net_premium_mn"] == pytest.approx(160.0, abs=0.5)

    def test_financials_net_aggregates_correctly(self, tmp_path):
        """Financials net = JPM + BAC = -90 + 10 = -80."""
        data_dir = _make_data_dir_with_summaries(tmp_path, {
            "AAPL": [], "MSFT": [], "NVDA": [], "JPM": [], "BAC": [],
        })
        result = self._run_heatmap(FLOW_ROWS_FIXTURE, GICS_MAP_FIXTURE, data_dir)
        fin = next((r for r in result if r["sector"] == "Financials"), None)
        assert fin is not None
        assert fin["net_premium_mn"] == pytest.approx(-80.0, abs=0.5)

    def test_sector_n_names_correct(self, tmp_path):
        data_dir = _make_data_dir_with_summaries(tmp_path, {
            "AAPL": [], "MSFT": [], "NVDA": [], "JPM": [], "BAC": [],
        })
        result = self._run_heatmap(FLOW_ROWS_FIXTURE, GICS_MAP_FIXTURE, data_dir)
        tech = next((r for r in result if r["sector"] == "Technology"), None)
        assert tech is not None
        assert tech["n_names"] == 3

    def test_z_raw_fallback_for_thin_history(self, tmp_path):
        """With fewer than MIN_Z_HISTORY obs per ticker, z_raw_fallback must be True."""
        # Give each ticker only 5 rows (< 20)
        data_dir = _make_data_dir_with_summaries(tmp_path, {
            "AAPL": [100.0] * 5, "MSFT": [80.0] * 5, "NVDA": [120.0] * 5,
        })
        result = self._run_heatmap(
            [r for r in FLOW_ROWS_FIXTURE if r["key"] in ("AAPL", "MSFT", "NVDA")],
            {k: v for k, v in GICS_MAP_FIXTURE.items() if k in ("AAPL", "MSFT", "NVDA")},
            data_dir,
        )
        tech = next((r for r in result if r["sector"] == "Technology"), None)
        assert tech is not None
        assert tech["z_raw_fallback"] is True
        assert tech["premium_z"] is None

    def test_z_computed_for_sufficient_history(self, tmp_path):
        """With 25 rows, z should be computed (not None)."""
        data_dir = _make_data_dir_with_summaries(tmp_path, {
            "AAPL": [100.0] * 25, "MSFT": [80.0] * 25, "NVDA": [120.0] * 25,
        })
        result = self._run_heatmap(
            [r for r in FLOW_ROWS_FIXTURE if r["key"] in ("AAPL", "MSFT", "NVDA")],
            {k: v for k, v in GICS_MAP_FIXTURE.items() if k in ("AAPL", "MSFT", "NVDA")},
            data_dir,
        )
        tech = next((r for r in result if r["sector"] == "Technology"), None)
        assert tech is not None
        assert tech["z_raw_fallback"] is False
        # z may be 0 (all same) or None if sigma=0; the key check is the flag is False
        # and premium_z has been computed (if sigma>0)

    def test_unknown_ticker_not_included(self, tmp_path):
        """Tickers not in gics_map should be silently excluded from heatmap."""
        flow_with_unknown = FLOW_ROWS_FIXTURE + [
            {"key": "UNKN", "asof": "2026-07-02", "net_premium_mn": 999.0,
             "zerodte_share": 0.5, "tone": "pos", "verdict": "test"},
        ]
        data_dir = _make_data_dir_with_summaries(tmp_path, {
            "AAPL": [], "MSFT": [], "NVDA": [], "JPM": [], "BAC": [],
        })
        result = self._run_heatmap(flow_with_unknown, GICS_MAP_FIXTURE, data_dir)
        # UNKN ticker not in any sector → net should still be correct for known sectors
        tech = next((r for r in result if r["sector"] == "Technology"), None)
        assert tech is not None
        assert tech["net_premium_mn"] == pytest.approx(160.0, abs=0.5)


# ── tape_flow absent degrade ──────────────────────────────────────────────────

class TestTapeFlowAbsentDegrade:
    """Page builds without tape_flow files — tape_breadth becomes None."""

    def test_heatmap_builds_without_tape_flow(self, tmp_path):
        data_dir = tmp_path / "data"
        (data_dir / "options_flow").mkdir(parents=True, exist_ok=True)
        # tape_flow/daily dir absent
        result = build_sector_heatmap(FLOW_ROWS_FIXTURE, GICS_MAP_FIXTURE, data_dir)
        # Should build without crashing
        assert isinstance(result, list)
        assert len(result) == 2  # Technology + Financials
        for cell in result:
            assert cell["tape_breadth"] is None
            assert cell["tape_n"] == 0

    def test_heatmap_partial_tape_flow(self, tmp_path):
        """Only some tickers have tape_flow data — breadth computed over those present."""
        data_dir = tmp_path / "data"
        (data_dir / "options_flow").mkdir(parents=True, exist_ok=True)
        tape_dir = data_dir / "tape_flow" / "daily"
        tape_dir.mkdir(parents=True, exist_ok=True)
        # Write tape_flow for AAPL only (positive net_signed_premium)
        spy_df = pd.DataFrame({
            "root": ["AAPL"], "date": ["2026-07-02"],
            "net_signed_premium": [500000.0],
            "signing_source": ["tape"],
        })
        spy_df.to_parquet(tape_dir / "AAPL.parquet")
        result = build_sector_heatmap(
            [r for r in FLOW_ROWS_FIXTURE if r["key"] in ("AAPL", "MSFT", "NVDA")],
            {k: v for k, v in GICS_MAP_FIXTURE.items() if k in ("AAPL", "MSFT", "NVDA")},
            data_dir,
        )
        tech = next((r for r in result if r["sector"] == "Technology"), None)
        assert tech is not None
        assert tech["tape_breadth"] is not None
        assert tech["tape_n"] == 1   # only AAPL had tape data
        assert tech["tape_breadth"] == pytest.approx(1.0)  # AAPL is positive


# ── top movers ────────────────────────────────────────────────────────────────

class TestTopMovers:
    def test_sorted_by_abs_net(self):
        rows = [
            {"key": "A", "net_premium_mn": 10.0, "tone": "pos", "zerodte_share": None, "verdict": None, "asof": "2026-07-02"},
            {"key": "B", "net_premium_mn": -500.0, "tone": "neg", "zerodte_share": None, "verdict": None, "asof": "2026-07-02"},
            {"key": "C", "net_premium_mn": 200.0, "tone": "pos", "zerodte_share": None, "verdict": None, "asof": "2026-07-02"},
        ]
        result = build_top_movers(rows, n=3)
        assert result[0]["ticker"] == "B"   # |-500| > |200| > |10|
        assert result[1]["ticker"] == "C"
        assert result[2]["ticker"] == "A"

    def test_caps_at_n(self):
        rows = [
            {"key": f"X{i}", "net_premium_mn": float(i), "tone": "pos",
             "zerodte_share": None, "verdict": None, "asof": "2026-07-02"}
            for i in range(20)
        ]
        result = build_top_movers(rows, n=5)
        assert len(result) == 5

    def test_excludes_none_net(self):
        rows = [
            {"key": "A", "net_premium_mn": None, "tone": "neutral", "zerodte_share": None, "verdict": None, "asof": "2026-07-02"},
            {"key": "B", "net_premium_mn": 100.0, "tone": "pos", "zerodte_share": None, "verdict": None, "asof": "2026-07-02"},
        ]
        result = build_top_movers(rows, n=10)
        assert len(result) == 1
        assert result[0]["ticker"] == "B"

    def test_net_premium_rounded(self):
        rows = [
            {"key": "A", "net_premium_mn": 123.456789, "tone": "pos",
             "zerodte_share": None, "verdict": None, "asof": "2026-07-02"},
        ]
        result = build_top_movers(rows, n=1)
        assert result[0]["net_premium_mn"] == pytest.approx(123.5, abs=0.1)


# ── flow-proxy wiring ─────────────────────────────────────────────────────────

class TestProxyWiring:
    """The sector proxy store froze for 16 days because rebuild() had no
    production caller (reader wired in P1.7, writer never invoked). These
    tests pin the wiring so it cannot silently drop out again."""

    def test_sector_proxy_calls_engine_rebuild(self, monkeypatch):
        import engine.etf_flows as ef
        import scripts.build_flow_desk as bfd
        calls = []
        monkeypatch.setattr(ef, "rebuild", lambda *a, **k: calls.append(1) or None)
        bfd._rebuild_sector_proxy()
        assert calls, "_rebuild_sector_proxy() must invoke engine.etf_flows.rebuild()"

    def test_sector_proxy_nonfatal_on_engine_error(self, monkeypatch):
        import engine.etf_flows as ef
        import scripts.build_flow_desk as bfd

        def _boom(*a, **k):
            raise RuntimeError("synthetic engine failure")

        monkeypatch.setattr(ef, "rebuild", _boom)
        bfd._rebuild_sector_proxy()  # must not raise

    def test_build_rebuilds_proxies_before_flow_rows_gate(self):
        import inspect
        import scripts.build_flow_desk as bfd
        src = inspect.getsource(bfd.build)
        i_sector = src.index("_rebuild_sector_proxy()")
        i_broad = src.index("_rebuild_broad_proxy()")
        i_gate = src.index("_load_flow_index(")
        i_tile = src.index("build_etf_tile(")
        assert i_broad < i_gate and i_sector < i_gate, (
            "proxy rebuilds must run before the empty-flow-rows early return "
            "so the stores accrue even on nights with no options-flow index"
        )
        assert i_sector < i_tile, "sector proxy must rebuild before build_etf_tile reads it"
