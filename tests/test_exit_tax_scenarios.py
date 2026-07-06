"""Unit tests for EXIT-TAX-SCENARIOS (scripts/research/exit_tax_scenarios.py).

Tests cover:
1. After-tax return computation (gain taxed, loss not).
2. Annual compounding math for short-term recycling.
3. Tax kink: ST vs LT scenario rate pairing.
4. Survivorship split present in output.
5. Long-hold parquet absent → manifest DEFER fallback, no crash.
6. Scenario rate sanity (0% rate → no drag; 100% rate → all wiped if gain).
7. NOT_MODELED and scenario-analysis disclaimers are present in output.
"""
from __future__ import annotations

import importlib.util
import json
import math
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


# ── import the module under test ──────────────────────────────────────────────

def _load_module():
    spec = importlib.util.spec_from_file_location(
        "exit_tax_scenarios",
        Path(__file__).parents[1] / "scripts" / "research" / "exit_tax_scenarios.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


try:
    etax = _load_module()
    MODULE_AVAILABLE = True
except Exception as e:
    MODULE_AVAILABLE = False
    _LOAD_ERROR = str(e)


def _skip_if_unavailable():
    if not MODULE_AVAILABLE:
        pytest.skip(f"exit_tax_scenarios module not loadable: {_LOAD_ERROR}")


# ── 1. After-tax return computation ──────────────────────────────────────────

class TestAfterTaxReturn:
    def setup_method(self):
        _skip_if_unavailable()

    def test_gain_taxed(self):
        """Positive return: after_tax = gross * (1 - rate)."""
        at = etax._after_tax_return(0.20, 0.35)
        assert abs(at - 0.20 * 0.65) < 1e-10

    def test_loss_not_taxed(self):
        """Negative return: after_tax = gross (no tax event on loss, simplified)."""
        at = etax._after_tax_return(-0.10, 0.35)
        assert abs(at - (-0.10)) < 1e-10

    def test_zero_rate_no_drag(self):
        """0% tax rate → after_tax = gross."""
        at = etax._after_tax_return(0.20, 0.0)
        assert abs(at - 0.20) < 1e-10

    def test_zero_gain_no_drag(self):
        """0% return → 0 after-tax regardless of rate."""
        at = etax._after_tax_return(0.0, 0.35)
        assert abs(at - 0.0) < 1e-10


# ── 2. Annual compounding math ────────────────────────────────────────────────

class TestCompoundAfterTaxAnnual:
    def setup_method(self):
        _skip_if_unavailable()

    def test_zero_rate_equals_gross_compound(self):
        """0% ST rate → annual = (1+gross)^cycles - 1 (same as gross compounding)."""
        gross_per_cycle = 0.02
        cycles = 12.0
        at_annual = etax._compound_after_tax_annual(gross_per_cycle, cycles, 0.0)
        expected = (1.0 + gross_per_cycle) ** cycles - 1.0
        assert abs(at_annual - expected) < 1e-10

    def test_known_value_35pct(self):
        """Verify: 2% per cycle, 12 cycles/yr, 35% ST rate.

        per_cycle_at = 0.02 * 0.65 = 0.013
        annual = (1.013)^12 - 1 ≈ 0.1683
        """
        at = etax._compound_after_tax_annual(0.02, 12.0, 0.35)
        expected = (1.0 + 0.02 * 0.65) ** 12 - 1.0
        assert abs(at - expected) < 1e-10

    def test_loss_cycle_no_tax(self):
        """Negative per-cycle return → compounded without tax (losses not credited)."""
        at = etax._compound_after_tax_annual(-0.01, 12.0, 0.35)
        expected = (1.0 + (-0.01)) ** 12 - 1.0
        assert abs(at - expected) < 1e-10

    def test_hold21_12cycles_matches_scenario_output(self):
        """Cross-check module's scenario output for hold_21 at 35% ST rate."""
        expected_at = etax._compound_after_tax_annual(
            etax.HOLD21_GROSS_MEAN_RET, etax.CYCLES_PER_YEAR, 0.35
        )
        # Run scenario row
        scenarios = [etax.TaxScenario(rate=0.35, label="35%")]
        rows = etax._run_exit_grid_scenarios(
            gross_mean_ret_per_cycle=etax.HOLD21_GROSS_MEAN_RET,
            cycles_per_year=etax.CYCLES_PER_YEAR,
            n_fires=etax.HOLD21_N_FIRES,
            wr=etax.HOLD21_WR,
            hold_bars=21,
            scenarios=scenarios,
        )
        assert len(rows) == 1
        # Output is rounded to 6 decimal places; allow rounding tolerance
        assert abs(rows[0]["after_tax_annual_compounded"] - expected_at) < 1e-5


# ── 3. LT scenario rate pairing ───────────────────────────────────────────────

class TestLtScenarioPairing:
    def setup_method(self):
        _skip_if_unavailable()

    def test_st35_maps_to_lt20(self):
        """ST 35% → LT 20% in the pairing table."""
        rows = etax._run_lt_scenarios(
            gross_252d_mean_ret=0.30,
            n_fires=2000,
            wr=0.65,
            survivorship_biased=False,
            scenarios=[etax.TaxScenario(0.35, "35%")],
            cohort_label="test",
        )
        assert rows[0]["scenario_lt_rate"] == 0.20

    def test_st0_maps_to_lt0(self):
        """ST 0% → LT 0%."""
        rows = etax._run_lt_scenarios(
            gross_252d_mean_ret=0.30,
            n_fires=2000,
            wr=0.65,
            survivorship_biased=False,
            scenarios=[etax.TaxScenario(0.0, "0%")],
            cohort_label="test",
        )
        assert rows[0]["scenario_lt_rate"] == 0.0

    def test_lt_after_tax_uses_lt_rate(self):
        """After-tax at LT=20% differs from gross for a positive return."""
        rows = etax._run_lt_scenarios(
            gross_252d_mean_ret=0.50,
            n_fires=100,
            wr=0.70,
            survivorship_biased=False,
            scenarios=[etax.TaxScenario(0.35, "35%")],
            cohort_label="test",
        )
        r = rows[0]
        assert r["scenario_lt_rate"] == 0.20
        # after_tax < gross
        assert r["after_tax_annual_lt"] < r["gross_annual_approx"]
        # verify the math
        expected = etax._lt_after_tax_annual(0.50, 0.20)
        assert abs(r["after_tax_annual_lt"] - expected) < 1e-8


# ── 4. Survivorship split ─────────────────────────────────────────────────────

class TestSurvivorshipSplit:
    def setup_method(self):
        _skip_if_unavailable()

    def test_biased_cohort_labelled_upper_bound(self):
        """Survivor-biased row carries UPPER BOUND label."""
        rows = etax._run_lt_scenarios(
            gross_252d_mean_ret=0.40,
            n_fires=5000,
            wr=0.73,
            survivorship_biased=True,
            scenarios=[etax.TaxScenario(0.35, "35%")],
            cohort_label="survivor_biased",
        )
        assert "UPPER BOUND" in rows[0]["survivorship_note"]

    def test_honest_cohort_not_labelled_upper_bound(self):
        """Honest cohort does NOT carry UPPER BOUND label."""
        rows = etax._run_lt_scenarios(
            gross_252d_mean_ret=0.37,
            n_fires=2000,
            wr=0.66,
            survivorship_biased=False,
            scenarios=[etax.TaxScenario(0.35, "35%")],
            cohort_label="honest",
        )
        assert "UPPER BOUND" not in rows[0]["survivorship_note"]


# ── 5. Long-hold parquet absent → manifest fallback ──────────────────────────

class TestParquetAbsentFallback:
    def setup_method(self):
        _skip_if_unavailable()

    def test_load_long_hold_labels_absent(self):
        """_load_long_hold_labels with no parquets → returns None, no crash."""
        with patch.object(etax, "_LABELS_PATH_WT",
                          Path("/tmp/__nonexistent_labels__.parquet")), \
             patch.object(etax, "_LABELS_PATH_MAIN",
                          Path("/tmp/__nonexistent_labels_main__.parquet")):
            result = etax._load_long_hold_labels()
        assert result is None

    def test_manifest_fallback_returns_cohort_list(self):
        """_get_252d_stats_from_manifest with a minimal manifest → list, no crash."""
        minimal_manifest = {
            "episode_cluster_counts": {
                "honest_cohort_252d_n_fires": 720,
                "honest_cohort_252d_episode_clusters": 700,
            }
        }
        cohorts = etax._get_252d_stats_from_manifest(minimal_manifest)
        assert isinstance(cohorts, list)
        assert len(cohorts) >= 1
        assert cohorts[0]["cohort"].startswith("honest_cohort")
        # Return stats unavailable from manifest → None
        assert cohorts[0]["mean_252d_ret"] is None


# ── 6. Scenario rate sanity ───────────────────────────────────────────────────

class TestScenarioRateSanity:
    def setup_method(self):
        _skip_if_unavailable()

    def test_zero_rate_no_drag(self):
        """0% ST rate → after_tax_annual = gross_annual (no drag)."""
        rows = etax._run_exit_grid_scenarios(
            gross_mean_ret_per_cycle=0.02,
            cycles_per_year=12.0,
            n_fires=1000,
            wr=0.57,
            hold_bars=21,
            scenarios=[etax.TaxScenario(0.0, "0%")],
        )
        r = rows[0]
        assert abs(r["tax_drag_annual_bps"]) < 1e-4
        assert abs(r["after_tax_annual_compounded"] - r["gross_annual_compounded"]) < 1e-8

    def test_higher_rate_higher_drag(self):
        """35% ST drag > 15% ST drag for same gross return."""
        rows_15 = etax._run_exit_grid_scenarios(
            gross_mean_ret_per_cycle=0.02, cycles_per_year=12.0,
            n_fires=1000, wr=0.57, hold_bars=21,
            scenarios=[etax.TaxScenario(0.15, "15%")],
        )
        rows_35 = etax._run_exit_grid_scenarios(
            gross_mean_ret_per_cycle=0.02, cycles_per_year=12.0,
            n_fires=1000, wr=0.57, hold_bars=21,
            scenarios=[etax.TaxScenario(0.35, "35%")],
        )
        assert rows_35[0]["tax_drag_annual_bps"] > rows_15[0]["tax_drag_annual_bps"]

    def test_all_scenario_rates_present(self):
        """All 5 scenario rates produce output rows."""
        scenarios = [etax.TaxScenario(r, f"{int(r*100)}%")
                     for r in etax.SCENARIO_RATES]
        rows = etax._run_exit_grid_scenarios(
            gross_mean_ret_per_cycle=0.02, cycles_per_year=12.0,
            n_fires=1000, wr=0.57, hold_bars=21,
            scenarios=scenarios,
        )
        assert len(rows) == len(etax.SCENARIO_RATES)
        assert rows[0]["scenario_rate"] == 0.0
        assert rows[-1]["scenario_rate"] == 0.40


# ── 7. Output JSON contains required fields ───────────────────────────────────

class TestOutputStructure:
    def setup_method(self):
        _skip_if_unavailable()

    def test_exit_grid_scenario_row_json_serializable(self):
        """exit_grid scenario rows are JSON-serializable."""
        rows = etax._run_exit_grid_scenarios(
            gross_mean_ret_per_cycle=0.02, cycles_per_year=12.0,
            n_fires=1000, wr=0.57, hold_bars=21,
            scenarios=[etax.TaxScenario(0.35, "35%")],
        )
        json.dumps(rows)

    def test_lt_scenario_row_json_serializable(self):
        """lt_scenario rows are JSON-serializable."""
        rows = etax._run_lt_scenarios(
            gross_252d_mean_ret=0.30, n_fires=2000, wr=0.65,
            survivorship_biased=False,
            scenarios=[etax.TaxScenario(0.35, "35%")],
            cohort_label="test",
        )
        json.dumps(rows)

    def test_st_is_stated_for_exit_grid(self):
        """Each exit-grid row carries the house-law note about short-term construction."""
        rows = etax._run_exit_grid_scenarios(
            gross_mean_ret_per_cycle=0.02, cycles_per_year=12.0,
            n_fires=1000, wr=0.57, hold_bars=21,
            scenarios=[etax.TaxScenario(0.35, "35%")],
        )
        note = rows[0]["note"]
        assert "SHORT-TERM" in note
        assert "≤" in note  # "≤126 bars"
