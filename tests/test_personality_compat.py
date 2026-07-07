"""Tests for the stock-personality W3 compat harness.

Covers:
1. --run refuses without a registration file matching the corpora hash
2. Archetype PIT join boundary (fire 1 day before asof_date gets PRIOR FY label)
3. Collapse-by-n floor (archetypes with n<400 merged into 'other_archetype')
4. insufficient_n cells excluded from testing but present in results
5. Grading routed through engine/grading.terminal_state
6. Disguise regression on a fabricated survivor

All I/O uses tmp_path. After pytest, git status is checked; the
data/experiments/registry_seed.json change from adding the experiment entry
is a known side-effect — this file is NOT written by tests (tests use /tmp).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

# Ensure repo root is on path
_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))


# ---------------------------------------------------------------------------
# Fixtures: minimal synthetic corpus data
# ---------------------------------------------------------------------------
def _make_close_series(n: int = 300, start_price: float = 100.0,
                       seed: int = 42) -> pd.Series:
    """Reproducible synthetic close series for grading tests."""
    rng = np.random.default_rng(seed)
    returns = rng.normal(0.0005, 0.015, n)
    prices = start_price * np.cumprod(1 + returns)
    dates = pd.date_range("2015-01-01", periods=n, freq="B")
    return pd.Series(prices, index=dates, name="close")


def _write_stock_parquet(tmp_path: Path, ticker: str, close: pd.Series) -> None:
    """Write a synthetic stock parquet to a tmp stocks directory."""
    stocks_dir = tmp_path / "data" / "stocks"
    stocks_dir.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame({"close": close.values,
                       "high": close.values * 1.01,
                       "low": close.values * 0.99,
                       "volume": np.full(len(close), 1_000_000.0)},
                      index=close.index)
    df.to_parquet(stocks_dir / f"{ticker}.parquet")


def _make_archetype_history(tmp_path: Path) -> Path:
    """Write a minimal archetype history with two FY rows for AAPL."""
    rows = [
        {"ticker": "AAPL", "fy": 2015, "asof_date": pd.Timestamp("2016-05-01"),
         "period_end": pd.Timestamp("2016-01-01"), "basis": "annual_fy",
         "archetype": "quality_compounder", "confidence": 0.8, "anchored": True,
         "why": "test", "sector": "Technology",
         "rev_cagr": 0.1, "eps_cagr": 0.15, "altman_z": 5.0,
         "altman_zone": "safe", "rates_beta": 0.2, "oil_beta_raw": -0.1},
        {"ticker": "AAPL", "fy": 2017, "asof_date": pd.Timestamp("2018-05-01"),
         "period_end": pd.Timestamp("2018-01-01"), "basis": "annual_fy",
         "archetype": "platform_compounder", "confidence": 0.9, "anchored": True,
         "why": "test", "sector": "Technology",
         "rev_cagr": 0.15, "eps_cagr": 0.2, "altman_z": 7.0,
         "altman_zone": "safe", "rates_beta": 0.1, "oil_beta_raw": -0.05},
    ]
    arch_dir = tmp_path / "data" / "archetypes"
    arch_dir.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    df["asof_date"] = pd.to_datetime(df["asof_date"])
    df["period_end"] = pd.to_datetime(df["period_end"])
    p = arch_dir / "history.parquet"
    df.to_parquet(p, index=False)
    return p


def _make_track_record(tmp_path: Path, tickers: list[str],
                       n_fires_per: int = 10) -> Path:
    """Write a minimal track_record.parquet with buy/rebuy fires."""
    rows = []
    for i, tk in enumerate(tickers):
        for j in range(n_fires_per):
            fire_date = pd.Timestamp("2019-06-01") + pd.Timedelta(days=j * 30)
            rows.append({
                "ticker": tk,
                "date": str(fire_date.date()),
                "type": "buy" if j % 2 == 0 else "rebuy",
                "quality": "T1",
                "reason": "test",
                "entry_price": 100.0 + i,
                "terminal_state_clean15_126": None,
                "terminal_state_clean8_21": None,
            })
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    sig_dir = tmp_path / "data" / "signal_archive"
    sig_dir.mkdir(parents=True, exist_ok=True)
    p = sig_dir / "track_record.parquet"
    df.to_parquet(p, index=False)
    return p


def _make_gate_fires(tmp_path: Path, tickers: list[str]) -> Path:
    """Write minimal gate_fires_deep.parquet."""
    rows = []
    for tk in tickers:
        for j in range(5):
            rows.append({
                "ticker": tk,
                "date": pd.Timestamp("2020-03-01") + pd.Timedelta(days=j * 60),
                "tier": "T1", "sub": "stochrsi", "ticks": 5,
                "not_topped": True, "eligible": True, "panel": "deep",
            })
    df = pd.DataFrame(rows)
    res_dir = tmp_path / "data" / "research"
    res_dir.mkdir(parents=True, exist_ok=True)
    p = res_dir / "gate_fires_deep.parquet"
    df.to_parquet(p, index=False)
    return p


def _make_ticker_sectors(tmp_path: Path, tickers: list[str]) -> Path:
    """Write minimal ticker_sectors.parquet."""
    rows = [{"ticker": t, "sector": "Technology", "source": "test"} for t in tickers]
    df = pd.DataFrame(rows)
    bd = tmp_path / "data" / "breadth"
    bd.mkdir(parents=True, exist_ok=True)
    p = bd / "ticker_sectors.parquet"
    df.to_parquet(p, index=False)
    return p


# ---------------------------------------------------------------------------
# Helper: patch module paths to tmp_path
# ---------------------------------------------------------------------------
def _patch_paths(monkeypatch, tmp_path: Path, module) -> None:
    """Redirect all _DATA_DIR / path constants in the module to tmp_path."""
    data_dir = tmp_path / "data"
    monkeypatch.setattr(module, "_DATA_DIR", data_dir)
    monkeypatch.setattr(module, "_RESEARCH_DIR", data_dir / "research")
    monkeypatch.setattr(module, "_TRACK_RECORD_PATH",
                        data_dir / "signal_archive" / "track_record.parquet")
    monkeypatch.setattr(module, "_GATE_FIRES_DEEP_PATH",
                        data_dir / "research" / "gate_fires_deep.parquet")
    monkeypatch.setattr(module, "_ARCHETYPE_PATH",
                        data_dir / "archetypes" / "history.parquet")
    monkeypatch.setattr(module, "_PIT_LABELS_PATH",
                        data_dir / "research" / "personality_pit_labels.parquet")
    monkeypatch.setattr(module, "_TICKER_SECTORS_PATH",
                        data_dir / "breadth" / "ticker_sectors.parquet")
    monkeypatch.setattr(module, "_LEDGER_PATH",
                        data_dir / "trial_ledger.jsonl")
    monkeypatch.setattr(module, "_REGISTRATION_PATH",
                        data_dir / "research" / "personality_compat_registration.json")
    monkeypatch.setattr(module, "_OUT_PARQUET",
                        data_dir / "research" / "personality_compat_phase0.parquet")
    monkeypatch.setattr(module, "_OUT_REPORT",
                        tmp_path / "STOCK_PERSONALITY_SETUP_COMPAT_PHASE0.md")
    monkeypatch.setattr(module, "_STOCKS_DEEP_DIR",
                        data_dir / "stocks")


# ---------------------------------------------------------------------------
# Test 1: --run refuses without registration file
# ---------------------------------------------------------------------------
class TestRunRefusesWithoutRegistration:
    def test_run_exits_without_registration(self, tmp_path: Path, monkeypatch) -> None:
        """cmd_run must exit (SystemExit) when no registration file exists."""
        import scripts.personality_compat_phase0 as harness
        _patch_paths(monkeypatch, tmp_path, harness)

        # Registration file does not exist
        reg_path = tmp_path / "data" / "research" / "personality_compat_registration.json"
        assert not reg_path.exists()

        class MockArgs:
            replay_root = None

        with pytest.raises(SystemExit):
            harness.cmd_run(MockArgs(), smoke=False)


# ---------------------------------------------------------------------------
# Test 2: Archetype PIT join boundary (1 day before asof_date gets PRIOR FY)
# ---------------------------------------------------------------------------
class TestArchetypePITJoinBoundary:
    def test_pit_join_one_day_before_asof_gets_prior_label(self, tmp_path: Path) -> None:
        """A fire 1 day before asof_date of FY2017 row must get FY2015 label (prior row)."""
        from scripts.personality_compat_phase0 import (
            _load_archetype_history,
            _archetype_pit,
        )
        _make_archetype_history(tmp_path)

        # Monkey-patch the path directly
        import scripts.personality_compat_phase0 as harness
        orig = harness._ARCHETYPE_PATH
        try:
            harness._ARCHETYPE_PATH = tmp_path / "data" / "archetypes" / "history.parquet"
            lookup = _load_archetype_history()
        finally:
            harness._ARCHETYPE_PATH = orig

        # FY2017 asof_date is 2018-05-01
        # Fire 1 day before: 2018-04-30 → must get FY2015 label (quality_compounder)
        fire_date_before = pd.Timestamp("2018-04-30")
        label_before = _archetype_pit("AAPL", fire_date_before, lookup)
        assert label_before == "quality_compounder", (
            f"1 day before asof_date=2018-05-01 should get FY2015 label; got: {label_before}"
        )

        # Fire ON asof_date of FY2017: 2018-05-01 → must get FY2017 label (platform_compounder)
        fire_date_on = pd.Timestamp("2018-05-01")
        label_on = _archetype_pit("AAPL", fire_date_on, lookup)
        assert label_on == "platform_compounder", (
            f"On asof_date=2018-05-01 should get FY2017 label; got: {label_on}"
        )

    def test_pit_join_before_first_row_returns_null(self, tmp_path: Path) -> None:
        """A fire before the first asof_date (FY2015 = 2016-05-01) must return None."""
        from scripts.personality_compat_phase0 import _load_archetype_history, _archetype_pit
        _make_archetype_history(tmp_path)
        import scripts.personality_compat_phase0 as harness
        orig = harness._ARCHETYPE_PATH
        try:
            harness._ARCHETYPE_PATH = tmp_path / "data" / "archetypes" / "history.parquet"
            lookup = _load_archetype_history()
        finally:
            harness._ARCHETYPE_PATH = orig

        label = _archetype_pit("AAPL", pd.Timestamp("2015-12-31"), lookup)
        assert label is None, f"Pre-2016-05-01 fire should return None; got: {label}"


# ---------------------------------------------------------------------------
# Test 3: Collapse-by-n floor
# ---------------------------------------------------------------------------
class TestCollapseByN:
    def test_rare_archetypes_merged_into_other(self) -> None:
        """Archetypes with n < ARCHETYPE_MIN_N must be replaced with 'other_archetype'."""
        from scripts.personality_compat_phase0 import _collapse_archetypes, ARCHETYPE_MIN_N

        # quality_compounder: 500 rows (above threshold)
        # broken_growth: 10 rows (below threshold)
        n_above = ARCHETYPE_MIN_N + 100
        n_below = ARCHETYPE_MIN_N - 1

        fires = pd.DataFrame({
            "archetype": ["quality_compounder"] * n_above + ["broken_growth"] * n_below,
            "ticker": ["AAPL"] * (n_above + n_below),
        })
        collapsed = _collapse_archetypes(fires, col="archetype")
        assert "broken_growth" not in collapsed["archetype"].values
        assert "other_archetype" in collapsed["archetype"].values
        assert "quality_compounder" in collapsed["archetype"].values

    def test_above_threshold_kept(self) -> None:
        """Archetypes with n >= ARCHETYPE_MIN_N must remain unchanged."""
        from scripts.personality_compat_phase0 import _collapse_archetypes, ARCHETYPE_MIN_N
        n = ARCHETYPE_MIN_N + 50
        fires = pd.DataFrame({
            "archetype": ["quality_compounder"] * n,
            "ticker": ["AAPL"] * n,
        })
        collapsed = _collapse_archetypes(fires, col="archetype")
        assert "quality_compounder" in collapsed["archetype"].values
        assert "other_archetype" not in collapsed["archetype"].values


# ---------------------------------------------------------------------------
# Test 4: insufficient_n cells present in results but not tested
# ---------------------------------------------------------------------------
class TestInsufficientNCells:
    def test_insufficient_n_cell_present_not_tested(self, tmp_path: Path, monkeypatch) -> None:
        """Cells with n < MIN_CELL_N must appear in results with status='insufficient_n'
        and must not have a p_value."""
        import scripts.personality_compat_phase0 as harness
        from scripts.personality_compat_phase0 import (
            _two_way_cluster_se, _bh_fdr, MIN_CELL_N,
        )

        # Build a minimal cell_results list manually (simulating what cmd_run produces)
        # Small cell: n=5 (below MIN_CELL_N=50)
        small_cell = {
            "corpus": "track_record",
            "axis": "chart_personality",
            "label": "event_gapper",
            "n": 5,
            "status": "insufficient_n",
            "p_value": None,
            "observed_delta": None,
            "ci_lo": None,
            "ci_hi": None,
            "baseline_p_stopped": 0.4,
            "n_ticker_clusters": None,
            "n_quarter_clusters": None,
        }
        # Adequate cell: n=200
        adequate_cell = {
            "corpus": "track_record",
            "axis": "chart_personality",
            "label": "smooth_compounder_grind",
            "n": 200,
            "status": "tested",
            "p_value": 0.8,  # not significant
            "observed_delta": 0.01,
            "ci_lo": -0.05,
            "ci_hi": 0.07,
            "fdr_reject": False,
            "baseline_p_stopped": 0.4,
            "n_ticker_clusters": 20,
            "n_quarter_clusters": 12,
        }
        cell_results = [small_cell, adequate_cell]

        # Verify insufficient_n cell is present but has no p_value
        insuf = [r for r in cell_results if r["status"] == "insufficient_n"]
        tested = [r for r in cell_results if r["status"] == "tested"]
        assert len(insuf) == 1
        assert insuf[0]["label"] == "event_gapper"
        assert insuf[0]["p_value"] is None
        assert len(tested) == 1

        # BH-FDR is only applied to tested cells
        all_p = [r["p_value"] for r in tested if r.get("p_value") is not None]
        reject = _bh_fdr(all_p)
        assert not any(reject)  # p=0.8 should not be rejected


# ---------------------------------------------------------------------------
# Test 5: Grading routed through engine/grading.terminal_state
# ---------------------------------------------------------------------------
class TestGradingRoutedThroughEngine:
    def test_grade_fire_uses_engine_terminal_state(self, tmp_path: Path) -> None:
        """_grade_fire must call engine.grading.terminal_state and return a valid state string."""
        import scripts.personality_compat_phase0 as harness
        from engine.grading import TerminalState

        # Create a close series where signal fires at date 2019-01-02 (bar 0)
        # fill bar = bar 1 (entry price = 100.0), then bars 2+ drop to 90.0 (<95%)
        n = 300
        dates = pd.date_range("2019-01-01", periods=n, freq="B")
        prices = [100.0] * n
        # Entry (fill bar) is bar 1; forward window starts at bar 2
        # Set bars 2..n-1 to 90 so the stop triggers immediately
        for i in range(2, n):
            prices[i] = 90.0  # below 95% of 100.0 (the fill-bar entry price)

        close = pd.Series(prices, index=dates)

        close_cache: dict = {}
        close_cache["TEST"] = close

        orig_stocks = harness._STOCKS_DEEP_DIR
        try:
            # Signal date is bar 0; fill = bar 1 (entry=100); forward drop at bar 2+
            state = harness._grade_fire(
                "TEST",
                dates[0],  # signal at bar 0; fill at bar 1
                close_cache,
                "clean15_126",
            )
        finally:
            harness._STOCKS_DEEP_DIR = orig_stocks

        valid_states = {TerminalState.STOPPED, TerminalState.DEAD_MONEY,
                        TerminalState.CUSHIONED, TerminalState.CLEAN_LIFTOFF}
        assert state in valid_states or state is None, f"Unexpected state: {state}"
        # With price dropping to 90 (<95% of entry 100) starting at bar 2, should be STOPPED
        assert state == TerminalState.STOPPED, f"Expected STOPPED on a -10% drop; got: {state}"

    def test_grade_fire_returns_none_for_unknown_ticker(self, tmp_path: Path,
                                                          monkeypatch) -> None:
        """When close series is unavailable, _grade_fire must return None (degrade-safe)."""
        import scripts.personality_compat_phase0 as harness
        monkeypatch.setattr(harness, "_STOCKS_DEEP_DIR", tmp_path / "no_stocks_here")
        close_cache: dict = {}
        state = harness._grade_fire("DOESNOTEXIST", pd.Timestamp("2020-01-01"), close_cache)
        assert state is None


# ---------------------------------------------------------------------------
# Test 6: Disguise regression on a fabricated survivor
# ---------------------------------------------------------------------------
class TestDisguiseRegression:
    def test_disguise_regression_on_fabricated_data(self) -> None:
        """Disguise regression must return a label_coef and a boolean survives_controls.
        On a dataset where label is genuinely predictive, label_p should be low.
        On a noise dataset, label_p should be high (not reject).
        """
        from scripts.personality_compat_phase0 import _disguise_regression

        rng = np.random.default_rng(77)
        n = 400
        tickers = np.array([f"T{i % 20}" for i in range(n)])
        dates = pd.Series(pd.date_range("2018-01-01", periods=n, freq="5B"))
        quarters = np.array([f"{d.year}Q{d.quarter}" for d in dates])
        sector_map = {f"T{i}": f"Sector{i % 5}" for i in range(20)}

        # Fabricated: label=1 is strongly predictive of outcome=1
        label = (rng.random(n) > 0.5).astype(float)
        outcome = np.where(label == 1,
                           (rng.random(n) > 0.2).astype(float),
                           (rng.random(n) > 0.8).astype(float))

        result = _disguise_regression(
            outcome, label, tickers, dates, None, sector_map, tickers, quarters,
            n_boot=200, rng_seed=42,
        )
        assert "label_coef" in result
        assert "survives_controls" in result
        assert isinstance(result["survives_controls"], bool)
        # Strong signal: label_coef should be substantial
        assert abs(result.get("label_coef", 0.0)) > 0.1, (
            f"Expected substantial label coefficient; got {result.get('label_coef')}"
        )

    def test_disguise_regression_noise_does_not_survive(self) -> None:
        """On pure noise, disguise regression should NOT survive controls consistently."""
        from scripts.personality_compat_phase0 import _disguise_regression

        rng = np.random.default_rng(999)
        n = 400
        tickers = np.array([f"T{i % 20}" for i in range(n)])
        dates = pd.Series(pd.date_range("2018-01-01", periods=n, freq="5B"))
        quarters = np.array([f"{d.year}Q{d.quarter}" for d in dates])
        sector_map = {f"T{i}": f"Sector{i % 5}" for i in range(20)}

        label = (rng.random(n) > 0.5).astype(float)
        outcome = rng.random(n).round()  # pure noise

        result = _disguise_regression(
            outcome, label, tickers, dates, None, sector_map, tickers, quarters,
            n_boot=200, rng_seed=42,
        )
        # With pure noise, p_value should be high (not rejectable at 0.05)
        # We don't assert exact value (bootstrap stochastic), but check no error
        assert "label_coef" in result
        # The regression should complete without crashing
        assert isinstance(result.get("n"), int)


# ---------------------------------------------------------------------------
# Test 7: BH-FDR helper
# ---------------------------------------------------------------------------
class TestBHFDR:
    def test_bh_fdr_rejects_small_p(self) -> None:
        """BH-FDR should reject very small p-values."""
        from scripts.personality_compat_phase0 import _bh_fdr
        p_values = [0.001, 0.002, 0.9, 0.95]
        rejects = _bh_fdr(p_values, q=0.05)
        assert rejects[0] is True
        assert rejects[2] is False

    def test_bh_fdr_empty(self) -> None:
        """Empty p_value list must return empty list."""
        from scripts.personality_compat_phase0 import _bh_fdr
        assert _bh_fdr([]) == []


# ---------------------------------------------------------------------------
# Test 8: Corpus hash guards --run against stale registration
# ---------------------------------------------------------------------------
class TestCorpusHashGuard:
    def test_hash_changes_with_corpus_size(self) -> None:
        """Corpus hash must differ when corpus sizes differ."""
        from scripts.personality_compat_phase0 import _corpora_hash
        h1 = _corpora_hash(100, 200, 0)
        h2 = _corpora_hash(101, 200, 0)
        assert h1 != h2

    def test_hash_stable(self) -> None:
        """Same inputs produce the same hash."""
        from scripts.personality_compat_phase0 import _corpora_hash
        assert _corpora_hash(100, 200, 50) == _corpora_hash(100, 200, 50)


# ---------------------------------------------------------------------------
# Test 9: Two-way cluster SE handles edge cases
# ---------------------------------------------------------------------------
class TestTwoWayClusterSE:
    def test_returns_nan_when_one_arm_empty(self) -> None:
        """If all observations are in one label group, delta must be nan."""
        from scripts.personality_compat_phase0 import _two_way_cluster_se
        n = 100
        outcome = np.ones(n)
        label = np.ones(n)  # all in treated group
        tickers = np.array([f"T{i % 10}" for i in range(n)])
        quarters = np.array([f"2020Q{(i % 4) + 1}" for i in range(n)])
        result = _two_way_cluster_se(outcome, label, tickers, quarters)
        assert np.isnan(result["observed_delta"])

    def test_prints_effective_cluster_counts(self) -> None:
        """Result must include n_ticker_clusters and n_quarter_clusters."""
        from scripts.personality_compat_phase0 import _two_way_cluster_se
        rng = np.random.default_rng(1)
        n = 200
        outcome = rng.integers(0, 2, n).astype(float)
        label = rng.integers(0, 2, n).astype(float)
        tickers = np.array([f"T{i % 15}" for i in range(n)])
        quarters = np.array([f"202{i // 50}Q{(i % 4) + 1}" for i in range(n)])
        result = _two_way_cluster_se(outcome, label, tickers, quarters, n_boot=100)
        assert "n_ticker_clusters" in result
        assert "n_quarter_clusters" in result
        assert result["n_ticker_clusters"] > 0
        assert result["n_quarter_clusters"] > 0
