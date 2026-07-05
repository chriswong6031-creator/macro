"""Hermetic unit tests for the single-regime path amendment (Amendment 1).

Spec frozen 2026-07-05 in research/ORACLE_REVERSION_GATE_PREREG.md.

Test inventory:
(A) single_regime_detection_triggers_at_minority_lt_30 — minority_n < 30 takes
    single-regime path; minority_n >= 30 (both sides) takes standard path.
(B) regime_matched_pool_contains_only_operating_regime_dates — the per-node
    placebo pool from _gauntlet_placebo_regime_matched is restricted to dates
    in the operating regime only (no cross-regime contamination).
(C) is_risk_off_date_logic — _is_risk_off_date mirrors _regime_at exactly for
    spy_above_200d and vix_pctile boundary conditions.

All fixtures are SYNTHETIC — no real data files, no network.
"""
from __future__ import annotations

import sys
import os

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.oracle_reversion_screen import (
    _is_risk_off_date,
    _gauntlet_placebo_regime_matched,
    run_gauntlet,
    _agg_stats,
)


# ---------------------------------------------------------------------------
# Synthetic data helpers
# ---------------------------------------------------------------------------

def _make_entries_df(
    n_on: int,
    n_off: int,
    node: str = "XLK",
    ret_exit_on: float = 0.03,
    ret_exit_off: float = 0.03,
    seed: int = 42,
) -> pd.DataFrame:
    """Build a synthetic entries_df with n_on risk_on and n_off risk_off rows."""
    rng = np.random.default_rng(seed)
    total = n_on + n_off
    if total == 0:
        return pd.DataFrame(columns=[
            "node", "trigger_date", "exec_date", "MFE", "MAE",
            "ret_exit", "regime", "hold_sessions",
        ])
    dates = pd.date_range("2010-01-01", periods=total, freq="B")
    regimes = (["risk_on"] * n_on) + (["risk_off"] * n_off)
    idx = rng.permutation(total)
    regimes = [regimes[i] for i in idx]
    ret_exit = [
        ret_exit_on + rng.normal(0, 0.005)
        if r == "risk_on" else ret_exit_off + rng.normal(0, 0.005)
        for r in regimes
    ]
    return pd.DataFrame({
        "node": node,
        "trigger_date": dates,
        "exec_date": dates + pd.Timedelta(days=1),
        "MFE": rng.uniform(0.01, 0.08, total),
        "MAE": rng.uniform(-0.05, -0.005, total),
        "ret_exit": ret_exit,
        "regime": regimes,
        "hold_sessions": [21] * total,
    })


def _make_panel_for_nodes(
    nodes: list,
    n_days: int = 600,
    start: str = "2010-01-01",
    seed: int = 42,
) -> pd.DataFrame:
    """Build a minimal multi-index panel with ret, spy_above_200d, vix_pctile."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(start, periods=n_days)
    rows = []
    for node in nodes:
        ret = rng.normal(0, 0.01, n_days)
        # First half: risk_off (spy_above=0, vix=0.80), second half: risk_on
        spy_above = [0.0 if i < n_days // 2 else 1.0 for i in range(n_days)]
        vix_pctile = [0.80 if i < n_days // 2 else 0.30 for i in range(n_days)]
        for i, dt in enumerate(dates):
            rows.append({
                "node": node,
                "date": dt,
                "ret": float(ret[i]),
                "spy_above_200d": spy_above[i],
                "vix_pctile": vix_pctile[i],
            })
    df = pd.DataFrame(rows).set_index(["node", "date"])
    return df


# ---------------------------------------------------------------------------
# (A) Single-regime detection
# ---------------------------------------------------------------------------

class TestSingleRegimeDetection:
    """Test the minority_n < 30 trigger logic inside run_gauntlet."""

    def _run_and_capture_path(self, n_on, n_off, capsys):
        entries = _make_entries_df(n_on=n_on, n_off=n_off)
        panel = _make_panel_for_nodes(["XLK"])
        compound = {"id": "test", "universe": {"tier": "s"}, "entry_rule": {}}
        run_gauntlet(compound, entries, panel, window=25, exit_sessions=21, exit_mode="time")
        return capsys.readouterr().out

    def test_minority_lt_30_takes_single_regime_path(self, capsys):
        output = self._run_and_capture_path(n_on=200, n_off=5, capsys=capsys)
        assert "SINGLE-REGIME" in output, f"Expected SINGLE-REGIME:\n{output}"

    def test_minority_exactly_29_takes_single_regime_path(self, capsys):
        output = self._run_and_capture_path(n_on=200, n_off=29, capsys=capsys)
        assert "SINGLE-REGIME" in output, f"Expected SINGLE-REGIME for n_off=29:\n{output}"

    def test_minority_exactly_30_takes_standard_path(self, capsys):
        output = self._run_and_capture_path(n_on=200, n_off=30, capsys=capsys)
        assert "STANDARD" in output, f"Expected STANDARD for n_off=30:\n{output}"

    def test_both_ge_30_takes_standard_path(self, capsys):
        output = self._run_and_capture_path(n_on=150, n_off=120, capsys=capsys)
        assert "STANDARD" in output, f"Expected STANDARD for both>=30:\n{output}"

    def test_zero_on_takes_single_regime_with_risk_off_operating(self, capsys):
        output = self._run_and_capture_path(n_on=0, n_off=200, capsys=capsys)
        assert "SINGLE-REGIME" in output
        assert "risk_off" in output

    def test_single_regime_prints_operating_regime(self, capsys):
        # n_off=5 -> risk_off is minority -> risk_on is operating
        output = self._run_and_capture_path(n_on=200, n_off=5, capsys=capsys)
        assert "risk_on" in output, f"Expected 'risk_on' as operating regime:\n{output}"

    def test_single_regime_prints_n_operating(self, capsys):
        output = self._run_and_capture_path(n_on=200, n_off=5, capsys=capsys)
        assert "n_operating=200" in output, f"Expected n_operating=200:\n{output}"

    def test_single_regime_leg4_prime_in_output(self, capsys):
        output = self._run_and_capture_path(n_on=200, n_off=5, capsys=capsys)
        assert "Leg 4'" in output, f"Expected Leg 4' in single-regime output:\n{output}"

    def test_standard_leg4_has_both_regimes(self, capsys):
        output = self._run_and_capture_path(n_on=200, n_off=120, capsys=capsys)
        assert "AND on=" in output and "AND off=" in output, (
            f"Expected standard Leg 4 format:\n{output}"
        )

    def test_single_regime_leg6_prime_regime_matched_label(self, capsys):
        output = self._run_and_capture_path(n_on=200, n_off=5, capsys=capsys)
        assert "Regime-matched placebo" in output, (
            f"Expected 'Regime-matched placebo' label:\n{output}"
        )

    def test_standard_leg6_timing_placebo_label(self, capsys):
        output = self._run_and_capture_path(n_on=200, n_off=120, capsys=capsys)
        assert "Leg 6  Timing placebo" in output, (
            f"Expected standard 'Timing placebo' label:\n{output}"
        )


# ---------------------------------------------------------------------------
# (B) Regime-matched pool contains only operating-regime dates
# ---------------------------------------------------------------------------

class TestRegimeMatchedPool:
    """_gauntlet_placebo_regime_matched restricts pool to operating regime only."""

    def _split_panel(self, node="XLK", n_days=400, split_at=200):
        """Panel: first split_at dates risk_off, rest risk_on."""
        dates = pd.bdate_range("2010-01-01", periods=n_days)
        rng = np.random.default_rng(7)
        rows = []
        for i, dt in enumerate(dates):
            rows.append({
                "node": node,
                "date": dt,
                "ret": float(rng.normal(0.0002, 0.01)),
                "spy_above_200d": 0.0 if i < split_at else 1.0,
                "vix_pctile": 0.80 if i < split_at else 0.30,
            })
        return pd.DataFrame(rows).set_index(["node", "date"])

    def test_risk_off_pool_yields_finite_pctile95(self):
        """risk_off pool: pctile95 must be finite when panel has risk_off dates."""
        panel = self._split_panel(n_days=400, split_at=200)
        entries = _make_entries_df(n_on=0, n_off=50, node="XLK")
        _, pctile95 = _gauntlet_placebo_regime_matched(
            entries, panel, 25, 21, "time", "risk_off", n_draws=50, rng_seed=42,
        )
        assert not np.isnan(pctile95), "Expected finite pctile95 for risk_off"

    def test_risk_on_pool_yields_finite_pctile95(self):
        """risk_on pool: pctile95 must be finite when panel has risk_on dates."""
        panel = self._split_panel(n_days=400, split_at=200)
        entries = _make_entries_df(n_on=50, n_off=0, node="XLK")
        _, pctile95 = _gauntlet_placebo_regime_matched(
            entries, panel, 25, 21, "time", "risk_on", n_draws=50, rng_seed=42,
        )
        assert not np.isnan(pctile95), "Expected finite pctile95 for risk_on"

    def test_no_operating_regime_dates_in_panel_yields_nan(self):
        """If panel has zero dates in operating regime, pool is empty -> pctile95=NaN."""
        # All-risk_on panel
        n_days = 200
        dates = pd.bdate_range("2010-01-01", periods=n_days)
        rng = np.random.default_rng(99)
        rows = [
            {"node": "XLK", "date": dt,
             "ret": float(rng.normal(0.0, 0.01)),
             "spy_above_200d": 1.0, "vix_pctile": 0.30}
            for dt in dates
        ]
        panel = pd.DataFrame(rows).set_index(["node", "date"])
        entries = _make_entries_df(n_on=50, n_off=0, node="XLK")
        _, pctile95 = _gauntlet_placebo_regime_matched(
            entries, panel, 25, 21, "time", "risk_off",  # risk_off operating but none in panel
            n_draws=50, rng_seed=42,
        )
        assert np.isnan(pctile95), (
            f"Expected NaN pctile95 (no risk_off dates in panel), got {pctile95}"
        )

    def test_real_mean_matches_entries_mean(self):
        """real_mean returned must equal entries_df['ret_exit'].mean()."""
        panel = self._split_panel()
        entries = _make_entries_df(n_on=0, n_off=50, node="XLK")
        expected_mean = float(entries["ret_exit"].mean())
        real_mean, _ = _gauntlet_placebo_regime_matched(
            entries, panel, 25, 21, "time", "risk_off", n_draws=50, rng_seed=42,
        )
        assert abs(real_mean - expected_mean) < 1e-10, (
            f"real_mean {real_mean} != entries mean {expected_mean}"
        )

    def test_identical_seed_produces_identical_result(self):
        """Same seed produces identical (real_mean, pctile95)."""
        panel = self._split_panel()
        entries = _make_entries_df(n_on=0, n_off=50, node="XLK")
        r1, p1 = _gauntlet_placebo_regime_matched(
            entries, panel, 25, 21, "time", "risk_off", n_draws=100, rng_seed=77,
        )
        r2, p2 = _gauntlet_placebo_regime_matched(
            entries, panel, 25, 21, "time", "risk_off", n_draws=100, rng_seed=77,
        )
        assert r1 == r2
        assert p1 == p2


# ---------------------------------------------------------------------------
# (C) _is_risk_off_date boundary conditions
# ---------------------------------------------------------------------------

class TestIsRiskOffDate:
    """_is_risk_off_date mirrors _regime_at logic exactly."""

    def _row(self, spy_above, vix_pctile):
        return pd.Series({"spy_above_200d": spy_above, "vix_pctile": vix_pctile})

    def test_spy_above_0_is_risk_off(self):
        assert _is_risk_off_date(self._row(0.0, 0.30)) is True

    def test_spy_above_1_vix_below_70_is_risk_on(self):
        assert _is_risk_off_date(self._row(1.0, 0.30)) is False

    def test_vix_ge_070_is_risk_off(self):
        assert _is_risk_off_date(self._row(1.0, 0.70)) is True

    def test_vix_069_is_risk_on(self):
        assert _is_risk_off_date(self._row(1.0, 0.69)) is False

    def test_vix_exactly_070_is_risk_off(self):
        assert _is_risk_off_date(self._row(1.0, 0.70)) is True

    def test_both_conditions_true_is_risk_off(self):
        assert _is_risk_off_date(self._row(0.0, 0.80)) is True

    def test_nan_spy_above_vix_below_is_risk_on(self):
        row = pd.Series({"spy_above_200d": float("nan"), "vix_pctile": 0.30})
        assert _is_risk_off_date(row) is False

    def test_nan_vix_spy_above_0_is_risk_off(self):
        row = pd.Series({"spy_above_200d": 0.0, "vix_pctile": float("nan")})
        assert _is_risk_off_date(row) is True

    def test_vix_above_70_spy_nan_is_risk_off(self):
        row = pd.Series({"spy_above_200d": float("nan"), "vix_pctile": 0.80})
        assert _is_risk_off_date(row) is True

    def test_missing_columns_defaults_to_risk_on(self):
        row = pd.Series({"other_col": 1.0})
        assert _is_risk_off_date(row) is False
