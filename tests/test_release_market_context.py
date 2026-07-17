"""Tests for engine/release_market_context.py — MRI PR-I enrichments.

Categories:
  1. compute_surprise_distribution — CDF integration sanity, symmetric quantiles,
     inline-band edges, missing-input handling.
  2. get_market_implied_benchmark — null when absent, parses a synthetic snapshots
     frame, picks highest-prob top outcome.
  3. get_reaction_sensitivity — picks 2021plus cells, prefers regime at n>=8,
     fails open on missing playbook file.

Run:
    python -m pytest tests/test_release_market_context.py -v
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

from engine.release_market_context import (
    _ERA_LABEL,
    _KALSHI_TTL_DAYS,
    _REGIME_MIN_N,
    compute_surprise_distribution,
    get_kalshi_implied,
    get_market_implied_benchmark,
    get_reaction_sensitivity,
)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. compute_surprise_distribution
# ═══════════════════════════════════════════════════════════════════════════════

def _sym_proj(center: float = 0.0, spread: float = 0.4) -> dict:
    """Symmetric normal-ish quantile projection centred on `center`."""
    return {
        "p10": center - 1.28 * spread,
        "p25": center - 0.67 * spread,
        "p50": center,
        "p75": center + 0.67 * spread,
        "p90": center + 1.28 * spread,
    }


class TestSurpriseDistribution:
    def test_symmetric_benchmark_equals_median_hot_cold_approx_equal(self):
        """Symmetric quantiles + benchmark = p50 → p_hot ≈ p_cold."""
        proj = _sym_proj(center=0.3, spread=0.4)
        sigma = 0.4
        bench = 0.3  # same as p50
        result = compute_surprise_distribution(proj, bench, sigma)
        assert result is not None, "should produce a result for symmetric inputs"
        assert abs(result["p_hot"] - result["p_cold"]) <= 0.05, (
            f"symmetric: p_hot={result['p_hot']} should ≈ p_cold={result['p_cold']}"
        )

    def test_sums_to_one(self):
        """p_hot + p_cold + p_inline == 1.0."""
        proj = _sym_proj(center=0.25, spread=0.30)
        result = compute_surprise_distribution(proj, 0.25, 0.30)
        assert result is not None
        total = result["p_hot"] + result["p_cold"] + result["p_inline"]
        assert abs(total - 1.0) <= 0.01, f"sum={total}, expected 1.0 ± 0.01"

    def test_high_benchmark_shifts_cold(self):
        """When benchmark is above p90, almost all mass should be p_cold."""
        proj = _sym_proj(center=0.0, spread=0.4)
        bench = 5.0  # far above p90
        sigma = 0.4
        result = compute_surprise_distribution(proj, bench, sigma)
        assert result is not None
        assert result["p_cold"] > 0.9, (
            f"Expected p_cold > 0.9 when bench={bench} far above distribution; got {result['p_cold']}"
        )

    def test_low_benchmark_shifts_hot(self):
        """When benchmark is far below p10, almost all mass should be p_hot."""
        proj = _sym_proj(center=0.0, spread=0.4)
        bench = -5.0  # far below p10
        sigma = 0.4
        result = compute_surprise_distribution(proj, bench, sigma)
        assert result is not None
        assert result["p_hot"] > 0.9, (
            f"Expected p_hot > 0.9 when bench={bench} far below distribution; got {result['p_hot']}"
        )

    def test_inline_band_edge_at_exact_quantiles(self):
        """Band edges aligned with p10/p90 → p_cold ≈ 0.10, p_hot ≈ 0.10."""
        # p10 = -0.35σ below bench, p90 = +0.35σ above bench → band exactly covers [p10, p90]? No.
        # Instead: set bench so that lo = p10 and hi = p90.
        # lo = bench - 0.35σ = p10  →  bench = p10 + 0.35σ
        # hi = bench + 0.35σ = p90  →  bench = p90 - 0.35σ
        # For both to hold simultaneously: p10 + 0.35σ == p90 - 0.35σ → p90 - p10 = 0.70σ
        sigma = 1.0
        spread = 0.35  # so p10 = bench - 0.35*1.0, p90 = bench + 0.35*1.0
        bench = 0.0
        proj = {
            "p10": bench - spread,  # = -0.35
            "p25": bench - 0.10,
            "p50": bench,
            "p75": bench + 0.10,
            "p90": bench + spread,  # = +0.35
        }
        result = compute_surprise_distribution(proj, bench, sigma)
        assert result is not None
        # The inline band [lo, hi] = [bench - 0.35*sigma, bench + 0.35*sigma]
        # = [p10, p90], so CDF(lo)=0.10 and CDF(hi)=0.90 → p_inline≈0.80
        assert result["p_inline"] >= 0.75, (
            f"Expected p_inline ≈ 0.80 when band = [p10,p90]; got {result}"
        )
        assert result["p_cold"] <= 0.15
        assert result["p_hot"] <= 0.15

    def test_missing_quantile_returns_none(self):
        """Any missing quantile → None."""
        proj = _sym_proj()
        proj.pop("p25")  # remove one quantile
        result = compute_surprise_distribution(proj, 0.0, 0.3)
        assert result is None

    def test_none_sigma_returns_none(self):
        """sigma=None → None."""
        result = compute_surprise_distribution(_sym_proj(), 0.0, None)
        assert result is None

    def test_zero_sigma_returns_none(self):
        """sigma=0 → None (division guard)."""
        result = compute_surprise_distribution(_sym_proj(), 0.0, 0.0)
        assert result is None

    def test_non_monotone_quantiles_returns_none(self):
        """Non-monotone quantiles → None."""
        proj = _sym_proj()
        proj["p25"] = proj["p75"] + 1.0  # deliberately break monotonicity
        result = compute_surprise_distribution(proj, 0.0, 0.4)
        assert result is None

    def test_output_structure(self):
        """Result has exactly the three expected keys."""
        result = compute_surprise_distribution(_sym_proj(), 0.0, 0.4)
        assert result is not None
        assert set(result.keys()) == {"p_hot", "p_cold", "p_inline"}

    def test_each_value_between_0_and_1(self):
        """All output probabilities are in [0, 1]."""
        result = compute_surprise_distribution(_sym_proj(), 0.0, 0.4)
        assert result is not None
        for k, v in result.items():
            assert 0.0 <= v <= 1.0, f"{k}={v} out of [0,1]"

    def test_large_sigma_widens_inline_band(self):
        """Larger sigma → more mass in p_inline."""
        proj = _sym_proj(center=0.3, spread=0.4)
        bench = 0.3
        result_small = compute_surprise_distribution(proj, bench, sigma=0.1)
        result_large = compute_surprise_distribution(proj, bench, sigma=1.0)
        assert result_small is not None and result_large is not None
        assert result_large["p_inline"] > result_small["p_inline"], (
            "Larger sigma should produce wider inline band → more p_inline"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 2. get_market_implied_benchmark
# ═══════════════════════════════════════════════════════════════════════════════

# Content-stamp dates for fixtures: the MRI-R33 gate reads the snapshot_date /
# asof_date COLUMN (never mtime, #2690 class), so fixtures must carry live dates.
_SNAP_FRESH = date.today().isoformat()
_SNAP_OLDER = (date.today() - timedelta(days=2)).isoformat()
_SNAP_STALE = (date.today() - timedelta(days=10)).isoformat()


def _make_snapshots_parquet(tmp_path: Path, rows: list[dict]) -> Path:
    p = tmp_path / "data" / "prediction_markets" / "snapshots.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(p, index=False)
    return p


class TestMarketImpliedBenchmark:
    def test_null_when_no_file(self, tmp_path: Path):
        """Returns None when snapshots.parquet doesn't exist."""
        result = get_market_implied_benchmark(
            "cpi_headline", "2026-08-13",
            tmp_path / "data" / "prediction_markets" / "snapshots.parquet",
        )
        assert result is None

    def test_null_when_event_key_absent(self, tmp_path: Path):
        """Returns None when cpi_print event_key not present."""
        rows = [
            {
                "snapshot_date": _SNAP_FRESH, "source": "polymarket",
                "event_key": "fed_next", "event_title": "Fed Decision",
                "end_date": "2026-07-31", "outcome": "Hold", "prob": 0.85,
                "volume24hr": None, "volume_total": None, "liquidity": None,
                "open_interest": None, "mkt_volume24hr": None,
            }
        ]
        p = _make_snapshots_parquet(tmp_path, rows)
        result = get_market_implied_benchmark("cpi_headline", "2026-08-13", p)
        assert result is None

    def test_null_for_claims_release(self, tmp_path: Path):
        """Claims release type → None (no event key configured)."""
        rows = [
            {
                "snapshot_date": _SNAP_FRESH, "source": "polymarket",
                "event_key": "cpi_print", "event_title": "CPI August",
                "end_date": "2026-08-13", "outcome": ">0.3%", "prob": 0.6,
                "volume24hr": None, "volume_total": None, "liquidity": None,
                "open_interest": None, "mkt_volume24hr": None,
            }
        ]
        p = _make_snapshots_parquet(tmp_path, rows)
        result = get_market_implied_benchmark("claims", "2026-07-10", p)
        assert result is None

    def test_parses_cpi_snapshot(self, tmp_path: Path):
        """Parses a valid cpi_print snapshot and returns top outcome."""
        rows = [
            {
                "snapshot_date": _SNAP_FRESH, "source": "polymarket",
                "event_key": "cpi_print", "event_title": "US CPI August 2026",
                "end_date": "2026-08-13", "outcome": "0.2–0.3%", "prob": 0.55,
                "volume24hr": 1000.0, "volume_total": 50000.0,
                "liquidity": 2000.0, "open_interest": 1500.0, "mkt_volume24hr": 800.0,
            },
            {
                "snapshot_date": _SNAP_FRESH, "source": "polymarket",
                "event_key": "cpi_print", "event_title": "US CPI August 2026",
                "end_date": "2026-08-13", "outcome": ">0.3%", "prob": 0.30,
                "volume24hr": 1000.0, "volume_total": 50000.0,
                "liquidity": 2000.0, "open_interest": 1500.0, "mkt_volume24hr": 200.0,
            },
            {
                "snapshot_date": _SNAP_FRESH, "source": "polymarket",
                "event_key": "cpi_print", "event_title": "US CPI August 2026",
                "end_date": "2026-08-13", "outcome": "<0.2%", "prob": 0.15,
                "volume24hr": 1000.0, "volume_total": 50000.0,
                "liquidity": 2000.0, "open_interest": 1500.0, "mkt_volume24hr": 200.0,
            },
        ]
        p = _make_snapshots_parquet(tmp_path, rows)
        result = get_market_implied_benchmark("cpi_headline", "2026-08-13", p)
        assert result is not None
        assert result["source"] == "polymarket"
        assert result["event_key"] == "cpi_print"
        assert result["implied"] == "0.2–0.3%"  # highest prob outcome
        assert result["prob_top"] == pytest.approx(0.55, abs=1e-4)
        assert result["asof"] == _SNAP_FRESH

    def test_picks_latest_snapshot_date(self, tmp_path: Path):
        """When multiple snapshot_dates present, uses the latest."""
        rows = [
            {
                "snapshot_date": _SNAP_OLDER, "source": "polymarket",
                "event_key": "cpi_print", "event_title": "CPI Old",
                "end_date": "2026-08-13", "outcome": "low", "prob": 0.9,
                "volume24hr": None, "volume_total": None, "liquidity": None,
                "open_interest": None, "mkt_volume24hr": None,
            },
            {
                "snapshot_date": _SNAP_FRESH, "source": "polymarket",
                "event_key": "cpi_print", "event_title": "CPI New",
                "end_date": "2026-08-13", "outcome": "high", "prob": 0.7,
                "volume24hr": None, "volume_total": None, "liquidity": None,
                "open_interest": None, "mkt_volume24hr": None,
            },
        ]
        p = _make_snapshots_parquet(tmp_path, rows)
        result = get_market_implied_benchmark("cpi_headline", "2026-08-13", p)
        assert result is not None
        assert result["asof"] == _SNAP_FRESH
        assert result["event_title"] == "CPI New"

    def test_nfp_event_key_used(self, tmp_path: Path):
        """NFP release type uses nfp_print event_key."""
        rows = [
            {
                "snapshot_date": _SNAP_FRESH, "source": "polymarket",
                "event_key": "nfp_print", "event_title": "US Nonfarm Payrolls August",
                "end_date": "2026-08-01", "outcome": ">200K", "prob": 0.45,
                "volume24hr": None, "volume_total": None, "liquidity": None,
                "open_interest": None, "mkt_volume24hr": None,
            },
        ]
        p = _make_snapshots_parquet(tmp_path, rows)
        result = get_market_implied_benchmark("nfp", "2026-08-01", p)
        assert result is not None
        assert result["event_key"] == "nfp_print"

    def test_structure_keys(self, tmp_path: Path):
        """Result contains all expected keys."""
        rows = [
            {
                "snapshot_date": _SNAP_FRESH, "source": "polymarket",
                "event_key": "cpi_print", "event_title": "CPI",
                "end_date": "2026-08-13", "outcome": "inline", "prob": 0.6,
                "volume24hr": None, "volume_total": None, "liquidity": None,
                "open_interest": None, "mkt_volume24hr": None,
            }
        ]
        p = _make_snapshots_parquet(tmp_path, rows)
        result = get_market_implied_benchmark("cpi_headline", "2026-08-13", p)
        assert result is not None
        assert set(result.keys()) >= {"source", "event_key", "event_title", "implied", "prob_top", "asof"}


# ═══════════════════════════════════════════════════════════════════════════════
# 3. get_reaction_sensitivity
# ═══════════════════════════════════════════════════════════════════════════════

def _make_playbook(tmp_path: Path, cells: list[dict]) -> Path:
    p = tmp_path / "research" / "release_playbook" / "results" / "playbook_v1.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cells))
    return p


def _base_cells() -> list[dict]:
    """Minimal set of 2021plus h1 cells for cpi: hot/cold × dgs10_bp/spy_pct."""
    return [
        {"release": "cpi", "bucket": "hot",  "outcome": "dgs10_bp", "horizon": "h1",
         "era": _ERA_LABEL, "regime": None, "n": 20, "mean": 3.2,  "median": 2.0, "ci_lo": -0.85, "ci_hi": 8.3},
        {"release": "cpi", "bucket": "cold", "outcome": "dgs10_bp", "horizon": "h1",
         "era": _ERA_LABEL, "regime": None, "n": 20, "mean": -4.1, "median": -3.0,"ci_lo": -9.0,  "ci_hi": 0.5},
        {"release": "cpi", "bucket": "hot",  "outcome": "spy_pct",  "horizon": "h1",
         "era": _ERA_LABEL, "regime": None, "n": 21, "mean": -0.40,"median": -0.05,"ci_lo": -1.28, "ci_hi": 0.29},
        {"release": "cpi", "bucket": "cold", "outcome": "spy_pct",  "horizon": "h1",
         "era": _ERA_LABEL, "regime": None, "n": 21, "mean": 0.55, "median": 0.4,  "ci_lo": -0.1,  "ci_hi": 1.4},
    ]


class TestReactionSensitivity:
    def test_null_when_playbook_missing(self, tmp_path: Path):
        """Returns None when playbook file doesn't exist."""
        p = tmp_path / "research" / "release_playbook" / "results" / "playbook_v1.json"
        result = get_reaction_sensitivity("cpi_headline", p, current_regime="Q1")
        assert result is None

    def test_null_for_claims_release(self, tmp_path: Path):
        """Claims release type → None (no playbook family)."""
        cells = _base_cells()
        p = _make_playbook(tmp_path, cells)
        result = get_reaction_sensitivity("claims", p, current_regime="Q1")
        assert result is None

    def test_picks_2021plus_cells(self, tmp_path: Path):
        """Uses 2021plus era cells and returns correct mean values."""
        cells = _base_cells()
        p = _make_playbook(tmp_path, cells)
        result = get_reaction_sensitivity("cpi_headline", p, current_regime=None)
        assert result is not None
        assert result["era_basis"] == _ERA_LABEL
        assert result["dgs10_h1_hot_bp"] == pytest.approx(3.2, abs=1e-4)
        assert result["dgs10_h1_cold_bp"] == pytest.approx(-4.1, abs=1e-4)
        assert result["spy_h1_hot_pct"] == pytest.approx(-0.40, abs=1e-4)
        assert result["spy_h1_cold_pct"] == pytest.approx(0.55, abs=1e-4)

    def test_prefers_regime_cell_when_n_ge_threshold(self, tmp_path: Path):
        """Regime-conditioned cell with n>=8 is preferred over era-level cell."""
        cells = _base_cells() + [
            # Regime-conditioned Q1 cell with n=10 (>= _REGIME_MIN_N)
            {"release": "cpi", "bucket": "hot", "outcome": "dgs10_bp", "horizon": "h1",
             "era": _ERA_LABEL, "regime": "Q1", "n": 10, "mean": 7.77, "median": 6.0,
             "ci_lo": 2.0, "ci_hi": 12.0},
        ]
        p = _make_playbook(tmp_path, cells)
        result = get_reaction_sensitivity("cpi_headline", p, current_regime="Q1")
        assert result is not None
        assert result["regime_cells_used"] is True
        # The Q1-conditioned cell should be used for hot dgs10
        assert result["dgs10_h1_hot_bp"] == pytest.approx(7.77, abs=1e-4)
        # Cold dgs10 falls back to era-level (no Q1 cold cell)
        assert result["dgs10_h1_cold_bp"] == pytest.approx(-4.1, abs=1e-4)

    def test_falls_back_when_regime_n_below_threshold(self, tmp_path: Path):
        """Regime-conditioned cell with n<8 is NOT used; falls back to era-level."""
        cells = _base_cells() + [
            # n=5 < _REGIME_MIN_N — should be ignored
            {"release": "cpi", "bucket": "hot", "outcome": "dgs10_bp", "horizon": "h1",
             "era": _ERA_LABEL, "regime": "Q1", "n": 5, "mean": 99.0, "median": 99.0,
             "ci_lo": 0.0, "ci_hi": 99.0},
        ]
        p = _make_playbook(tmp_path, cells)
        result = get_reaction_sensitivity("cpi_headline", p, current_regime="Q1")
        assert result is not None
        assert result["regime_cells_used"] is False
        assert result["dgs10_h1_hot_bp"] == pytest.approx(3.2, abs=1e-4)  # era-level

    def test_nfp_family_mapped_correctly(self, tmp_path: Path):
        """nfp release type maps to 'nfp' playbook family."""
        cells = [
            {"release": "nfp", "bucket": "hot",  "outcome": "dgs10_bp", "horizon": "h1",
             "era": _ERA_LABEL, "regime": None, "n": 15, "mean": 5.1, "median": 4.0, "ci_lo": 1.0, "ci_hi": 9.0},
            {"release": "nfp", "bucket": "cold", "outcome": "dgs10_bp", "horizon": "h1",
             "era": _ERA_LABEL, "regime": None, "n": 15, "mean": -3.2,"median": -2.0,"ci_lo": -7.0, "ci_hi": 0.5},
            {"release": "nfp", "bucket": "hot",  "outcome": "spy_pct",  "horizon": "h1",
             "era": _ERA_LABEL, "regime": None, "n": 15, "mean": 0.3,  "median": 0.2, "ci_lo": -0.5, "ci_hi": 1.2},
            {"release": "nfp", "bucket": "cold", "outcome": "spy_pct",  "horizon": "h1",
             "era": _ERA_LABEL, "regime": None, "n": 15, "mean": -0.8, "median": -0.7,"ci_lo": -2.0, "ci_hi": 0.3},
        ]
        p = _make_playbook(tmp_path, cells)
        result = get_reaction_sensitivity("nfp", p, current_regime=None)
        assert result is not None
        assert result["dgs10_h1_hot_bp"] == pytest.approx(5.1, abs=1e-4)

    def test_output_structure_complete(self, tmp_path: Path):
        """Result has all required keys."""
        cells = _base_cells()
        p = _make_playbook(tmp_path, cells)
        result = get_reaction_sensitivity("cpi_headline", p)
        assert result is not None
        required = {
            "dgs10_h1_hot_bp", "dgs10_h1_cold_bp",
            "spy_h1_hot_pct", "spy_h1_cold_pct",
            "era_basis", "regime_cells_used", "note",
        }
        assert required.issubset(result.keys())

    def test_regime_cells_used_false_by_default(self, tmp_path: Path):
        """Without regime-conditioned cells, regime_cells_used is False."""
        cells = _base_cells()
        p = _make_playbook(tmp_path, cells)
        result = get_reaction_sensitivity("cpi_headline", p, current_regime="Q2")
        assert result is not None
        assert result["regime_cells_used"] is False

    def test_fail_open_on_bad_json(self, tmp_path: Path):
        """Corrupt JSON → returns None without raising."""
        p = tmp_path / "research" / "release_playbook" / "results" / "playbook_v1.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("NOT VALID JSON {{{")
        result = get_reaction_sensitivity("cpi_headline", p)
        assert result is None


# ---------------------------------------------------------------------------
# Kalshi implied read (masterplan §9.1 — preferred market_implied source)
# ---------------------------------------------------------------------------

import pandas as pd
from engine.release_market_context import get_kalshi_implied


def _kalshi_frame(rows):
    cols = ["asof_date", "release_type", "period", "strike", "p_survival",
            "price_type", "is_summary", "implied_median",
            "p_above_lowest_strike", "monotonicity_corrected", "n_brackets",
            "event_ticker", "close_time"]
    return pd.DataFrame(rows, columns=cols)


def test_kalshi_summary_row_preferred_latest_asof(tmp_path):
    path = tmp_path / "kalshi_releases.parquet"
    _kalshi_frame([
        [_SNAP_OLDER, "cpi", "2026-06", float("nan"), None, "summary", True,
         0.12, 0.61, False, 7, "KXCPI-26JUN", None],
        [_SNAP_FRESH, "cpi", "2026-06", float("nan"), None, "summary", True,
         0.10, 0.58, False, 7, "KXCPI-26JUN", None],
        # non-summary bracket row must be ignored
        [_SNAP_FRESH, "cpi", "2026-06", 0.3, 0.42, "mid", False,
         None, None, None, None, "KXCPI-26JUN", None],
    ]).to_parquet(path, index=False)
    out = get_kalshi_implied("cpi_headline", "2026-06", path)
    assert out is not None
    assert out["source"] == "kalshi"
    assert abs(out["implied_median"] - 0.10) < 1e-9  # latest asof wins
    assert out["asof"] == _SNAP_FRESH
    assert out["n_brackets"] == 7


def test_kalshi_core_cpi_not_mapped(tmp_path):
    path = tmp_path / "kalshi_releases.parquet"
    _kalshi_frame([
        [_SNAP_FRESH, "cpi", "2026-06", float("nan"), None, "summary", True,
         0.10, 0.58, False, 7, "KXCPI-26JUN", None],
    ]).to_parquet(path, index=False)
    # Kalshi tracks headline only; core must not borrow the headline ladder
    assert get_kalshi_implied("cpi_core", "2026-06", path) is None


def test_kalshi_absent_file_and_period_failopen(tmp_path):
    assert get_kalshi_implied("cpi_headline", "2026-06",
                              tmp_path / "missing.parquet") is None
    path = tmp_path / "kalshi_releases.parquet"
    _kalshi_frame([
        [_SNAP_FRESH, "nfp", "2026-07", float("nan"), None, "summary", True,
         110000.0, 0.55, False, 9, "KXPAYROLLS-26JUL", None],
    ]).to_parquet(path, index=False)
    assert get_kalshi_implied("cpi_headline", "2026-06", path) is None
    out = get_kalshi_implied("nfp", "2026-07", path)
    assert out is not None and out["implied_median"] == 110000.0


# ---------------------------------------------------------------------------
# MRI-R33 STALE-ENRICH content-stamp gate (#2690 class): staleness is judged
# from the parquet's stamp COLUMN, never file mtime — a checkout-rewritten
# mtime must not resurrect a dead source.
# ---------------------------------------------------------------------------

import os
import time as _time


def test_kalshi_stale_stamp_nulls_with_reason(tmp_path):
    path = tmp_path / "kalshi_releases.parquet"
    _kalshi_frame([
        [_SNAP_STALE, "cpi", "2026-06", float("nan"), None, "summary", True,
         0.10, 0.58, False, 7, "KXCPI-26JUN", None],
    ]).to_parquet(path, index=False)
    # freshen the file's mtime to NOW — the gate must still read it as stale
    os.utime(path, (_time.time(), _time.time()))
    out = get_kalshi_implied("cpi_headline", "2026-06", path)
    assert out is not None and out["implied_median"] is None
    assert "stale" in out["stale_reason"]


def test_market_implied_stale_stamp_nulls_with_reason(tmp_path: Path):
    rows = [{
        "snapshot_date": _SNAP_STALE, "source": "polymarket",
        "event_key": "cpi_print", "event_title": "CPI",
        "end_date": "2026-08-13", "outcome": "inline", "prob": 0.6,
        "volume24hr": None, "volume_total": None, "liquidity": None,
        "open_interest": None, "mkt_volume24hr": None,
    }]
    p = _make_snapshots_parquet(tmp_path, rows)
    os.utime(p, (_time.time(), _time.time()))
    result = get_market_implied_benchmark("cpi_headline", "2026-08-13", p)
    assert result is not None and result["implied"] is None
    assert "stale" in result["stale_reason"]


def test_missing_stamp_column_reads_stale(tmp_path):
    """A parquet without the stamp column fails SAFE (guard fires)."""
    path = tmp_path / "kalshi_releases.parquet"
    pd.DataFrame({"release_type": ["cpi"], "period": ["2026-06"],
                  "is_summary": [True], "implied_median": [0.1]}
                 ).to_parquet(path, index=False)
    out = get_kalshi_implied("cpi_headline", "2026-06", path)
    assert out is not None and out["implied_median"] is None
    assert "stale" in out["stale_reason"]


# ═══════════════════════════════════════════════════════════════════════════════
# 4. compute_expectation_read (MRI-R22)
# ═══════════════════════════════════════════════════════════════════════════════

from engine.release_market_context import compute_expectation_read


class TestExpectationRead:
    """Tests for compute_expectation_read (MRI-R22)."""

    # ── band edges ────────────────────────────────────────────────────────────

    def test_above_threshold(self):
        """standardized > +0.35 → 'above_expectations'."""
        # delta_pp = 0.5, sigma = 1.0 → std = 0.5 > 0.35
        result = compute_expectation_read(
            point=0.5,
            expectation_values={"cleveland_nowcast": 0.0},
            sigma_scale_pp=1.0,
        )
        assert result is not None
        assert result["tag"] == "above_expectations"
        assert result["standardized"] == pytest.approx(0.5, abs=1e-9)

    def test_below_threshold(self):
        """standardized < -0.35 → 'below_expectations'."""
        result = compute_expectation_read(
            point=-0.5,
            expectation_values={"cleveland_nowcast": 0.0},
            sigma_scale_pp=1.0,
        )
        assert result is not None
        assert result["tag"] == "below_expectations"
        assert result["standardized"] == pytest.approx(-0.5, abs=1e-9)

    def test_aligned_at_exact_upper_band_edge(self):
        """standardized exactly +0.35 → 'aligned' (not above)."""
        result = compute_expectation_read(
            point=0.35,
            expectation_values={"cleveland_nowcast": 0.0},
            sigma_scale_pp=1.0,
        )
        assert result is not None
        assert result["tag"] == "aligned"

    def test_aligned_at_exact_lower_band_edge(self):
        """standardized exactly -0.35 → 'aligned' (not below)."""
        result = compute_expectation_read(
            point=-0.35,
            expectation_values={"cleveland_nowcast": 0.0},
            sigma_scale_pp=1.0,
        )
        assert result is not None
        assert result["tag"] == "aligned"

    def test_just_above_upper_band_edge(self):
        """standardized = 0.351 → 'above_expectations'."""
        result = compute_expectation_read(
            point=0.351,
            expectation_values={"cleveland_nowcast": 0.0},
            sigma_scale_pp=1.0,
        )
        assert result is not None
        assert result["tag"] == "above_expectations"

    def test_just_below_lower_band_edge(self):
        """standardized = -0.351 → 'below_expectations'."""
        result = compute_expectation_read(
            point=-0.351,
            expectation_values={"cleveland_nowcast": 0.0},
            sigma_scale_pp=1.0,
        )
        assert result is not None
        assert result["tag"] == "below_expectations"

    # ── empty set → None ──────────────────────────────────────────────────────

    def test_empty_expectation_set_returns_none(self):
        """Empty dict → None (no expectation sources)."""
        result = compute_expectation_read(0.3, {}, 0.4)
        assert result is None

    def test_all_none_values_returns_none(self):
        """All values None → None."""
        result = compute_expectation_read(0.3, {"cleveland_nowcast": None}, 0.4)
        assert result is None

    def test_trend_benchmarks_excluded(self):
        """naive_prior / trailing_3m / ar_model keys are NOT part of the expectation set."""
        # Only trend keys → empty → None
        result = compute_expectation_read(
            point=0.3,
            expectation_values={
                "naive_prior": 0.2,
                "trailing_3m": 0.25,
                "ar_model": 0.28,
            },
            sigma_scale_pp=0.4,
        )
        assert result is None, (
            "Trend benchmarks must NOT be part of the expectation set; result should be None"
        )

    # ── None inputs → None ────────────────────────────────────────────────────

    def test_none_point_returns_none(self):
        """point=None → None."""
        result = compute_expectation_read(None, {"cleveland_nowcast": 0.1}, 0.4)
        assert result is None

    def test_none_sigma_returns_none(self):
        """sigma_scale_pp=None → None."""
        result = compute_expectation_read(0.3, {"cleveland_nowcast": 0.1}, None)
        assert result is None

    def test_zero_sigma_returns_none(self):
        """sigma_scale_pp=0 → None (division guard)."""
        result = compute_expectation_read(0.3, {"cleveland_nowcast": 0.1}, 0.0)
        assert result is None

    # ── single-source set (cleveland only) ───────────────────────────────────

    def test_single_source_cleveland(self):
        """Single source (cleveland_nowcast) produces valid output."""
        result = compute_expectation_read(
            point=0.4,
            expectation_values={"cleveland_nowcast": -0.06},
            sigma_scale_pp=0.30,
        )
        assert result is not None
        assert result["n_sources"] == 1
        assert result["sources"] == ["cleveland_nowcast"]
        assert result["expectation_median"] == pytest.approx(-0.06, abs=1e-9)
        assert result["delta_pp"] == pytest.approx(0.4 - (-0.06), abs=1e-3)
        assert result["tag"] == "above_expectations"  # (0.4+0.06)/0.30 = 1.53 >> 0.35

    # ── two-source median ─────────────────────────────────────────────────────

    def test_two_source_median_cleveland_kalshi(self):
        """Two sources: median of cleveland + kalshi."""
        result = compute_expectation_read(
            point=0.3,
            expectation_values={"cleveland_nowcast": 0.1, "kalshi": 0.2},
            sigma_scale_pp=1.0,
        )
        assert result is not None
        assert result["n_sources"] == 2
        assert set(result["sources"]) == {"cleveland_nowcast", "kalshi"}
        # median([0.1, 0.2]) = 0.15
        assert result["expectation_median"] == pytest.approx(0.15, abs=1e-6)
        assert result["delta_pp"] == pytest.approx(0.3 - 0.15, abs=1e-4)

    # ── Kalshi preferred over Polymarket ──────────────────────────────────────

    def test_kalshi_preferred_over_polymarket(self):
        """When both kalshi and polymarket are present, both appear but kalshi is listed first."""
        result = compute_expectation_read(
            point=0.3,
            expectation_values={"kalshi": 0.2, "polymarket": 0.5},
            sigma_scale_pp=1.0,
        )
        assert result is not None
        # Both sources present; median of [0.2, 0.5] = 0.35
        assert result["n_sources"] == 2
        # Ordering follows _EXPECTATION_KEYS: kalshi before polymarket
        assert result["sources"].index("kalshi") < result["sources"].index("polymarket")

    def test_output_keys(self):
        """Output has exactly the six required keys."""
        result = compute_expectation_read(
            point=0.3,
            expectation_values={"cleveland_nowcast": 0.1},
            sigma_scale_pp=0.4,
        )
        assert result is not None
        assert set(result.keys()) == {
            "tag", "delta_pp", "standardized", "expectation_median", "sources", "n_sources"
        }

    def test_delta_pp_precision(self):
        """delta_pp is rounded to 4 decimal places."""
        result = compute_expectation_read(0.123456789, {"cleveland_nowcast": 0.0}, 1.0)
        assert result is not None
        assert result["delta_pp"] == round(0.123456789, 4)

    def test_standardized_precision(self):
        """standardized is rounded to 2 decimal places."""
        result = compute_expectation_read(0.5, {"cleveland_nowcast": 0.0}, 0.3)
        assert result is not None
        # 0.5 / 0.3 = 1.6667 → rounds to 1.67
        assert result["standardized"] == pytest.approx(round(0.5 / 0.3, 2), abs=1e-9)


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Live-path integration test (§10 lesson — realistic fixture tree)
# ═══════════════════════════════════════════════════════════════════════════════

_REPO_ROOT = Path(__file__).resolve().parents[1]
_NOWCAST_PATH = _REPO_ROOT / "data" / "cleveland_nowcast" / "nowcast.parquet"

_LIVE_PATH_MARK = pytest.mark.skipif(
    not _NOWCAST_PATH.exists(),
    reason="data/cleveland_nowcast/nowcast.parquet not present; skipping live-path integration test",
)


@_LIVE_PATH_MARK
def test_expectation_read_live_path_end_to_end(tmp_path, monkeypatch):
    """Live-path integration: _enrich_upcoming_block produces expectation_read end-to-end.

    Uses a realistic in-repo fixture tree (real Cleveland nowcast parquet via
    monkeypatched root), confirms expectation_read lands for a CPI entry.
    Per §10 lesson: no synthetic-only shortcuts for this test.
    """
    import shutil
    import sys
    sys.path.insert(0, str(_REPO_ROOT))

    # Build a realistic tmp root: copy just the data files we need
    (tmp_path / "data" / "cleveland_nowcast").mkdir(parents=True)
    (tmp_path / "data" / "prediction_markets").mkdir(parents=True)
    (tmp_path / "data" / "regime").mkdir(parents=True)
    shutil.copy(_NOWCAST_PATH, tmp_path / "data" / "cleveland_nowcast" / "nowcast.parquet")

    from scripts.build_release_forecast import (
        _enrich_upcoming_block,
        _read_cleveland_nowcast,
    )
    from engine.release_market_context import compute_expectation_read as _compute_er

    from datetime import date
    today = date(2026, 7, 7)
    period = "2026-06"

    # Build a minimal upcoming block for cpi_headline
    cleveland_val = _read_cleveland_nowcast(tmp_path, "cpi_headline", period, today)
    assert cleveland_val is not None, "Cleveland value should be readable from real parquet"

    # Craft a realistic upcoming item matching what _build_upcoming_block would produce
    item = {
        "release": "cpi",
        "release_type": "cpi_headline",
        "period": period,
        "release_date": "2026-07-11",
        "projection": {"point": 0.42, "p10": 0.1, "p25": 0.2, "p50": 0.35, "p75": 0.5, "p90": 0.65},
        "surprise_skew": {"sigma_scale_pp": 0.3073, "sigma": -0.1606, "tag": "inline"},
        "benchmark_set": {
            "naive_prior": 0.47,
            "trailing_3m": 0.66,
            "ar_model": 0.86,
            "cleveland_nowcast": cleveland_val,
            "market_implied": None,
        },
        "market_implied": None,
        "regime_axis": "inflation",
        "policy_backdrop": {},
    }

    # Monkeypatch the root so _enrich_upcoming_block reads from our tmp_path
    import scripts.build_release_forecast as producer
    monkeypatch.setattr(producer, "_read_cleveland_nowcast",
                        lambda root, rt, p, t: _read_cleveland_nowcast(tmp_path, rt, p, t))

    _enrich_upcoming_block([item], tmp_path)

    er = item.get("expectation_read")
    assert er is not None, (
        f"expectation_read must be set for cpi_headline with Cleveland={cleveland_val:.4f}; got None. "
        "Check that compute_expectation_read is wired in _enrich_upcoming_block."
    )
    assert "tag" in er, "expectation_read must have a 'tag' field"
    assert er["tag"] in ("above_expectations", "below_expectations", "aligned"), (
        f"expectation_read tag must be one of the three valid values; got {er['tag']!r}"
    )
    assert er["n_sources"] >= 1, "at least one source (cleveland_nowcast) must be used"
    assert "cleveland_nowcast" in er["sources"], "cleveland_nowcast must appear in sources"

    # Validate the specific values: point=0.42, cleveland=-0.061, sigma=0.3073
    # delta_pp = 0.42 - (-0.061) ≈ 0.481, standardized ≈ 1.565 → above_expectations
    assert er["tag"] == "above_expectations", (
        f"Expected above_expectations for CPI point=0.42 vs Cleveland≈-0.061 "
        f"(delta≈0.48pp, std≈1.56); got tag={er['tag']!r}, er={er}"
    )
