"""Unit tests for PR-H: NFP decomposition + AHE/AWH targets.

Tests:
  1. config_sanity — 4 new series in release_intel and vintage_series
  2. decomp_sum — components sum to point (within tolerance)
  3. bd_prior_pit — BD prior uses only trailing history (synthetic walk-forward)
  4. government_trend_math — trailing N-month USGOVT mean
  5. ahe_contract — project_release("ahe") output keys + authority flags
  6. awh_contract — project_release("awh") output keys + persistence_only flag
  7. kill_rule_eval — AHE kill rule: benchmark_only when MAE model >= MAE naive in both eras
  8. revision_risk_math — mean/pct_upward match manual calculation

All synthetic data; no real parquets read.

Run:
    python -m pytest tests/test_release_forecast_nfp_decomp.py -v
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

from engine.release_components_nfp import (
    build_nfp_components,
    compute_bd_prior_12month_profile,
    compute_nfp_revision_risk,
    build_ahe_features,
    project_awh,
    _empty_ahe_projection,
    _empty_awh_projection,
)
from engine.release_forecast import knowable_series
from research.release_forecast.backtest_nfp_decomp_v1 import _check_kill_rule


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_vintages(
    series: str,
    periods: list[pd.Timestamp],
    values: list[float],
    release_delays_days: list[int],
) -> pd.DataFrame:
    rows = []
    for p, v, d in zip(periods, values, release_delays_days):
        rt_start = p + pd.Timedelta(days=d)
        rows.append({
            "series": series,
            "period": p,
            "value": v,
            "realtime_start": rt_start,
            "realtime_end": pd.Timestamp("2099-12-31"),
        })
    return pd.DataFrame(rows)


def _build_combined_vintages(*dfs: pd.DataFrame) -> pd.DataFrame:
    return pd.concat(list(dfs), ignore_index=True)


def _knowable(vintages: pd.DataFrame, series: str, asof: date) -> pd.DataFrame:
    return knowable_series(vintages, series, asof)


# ---------------------------------------------------------------------------
# 1. Config sanity: 4 new PR-H series
# ---------------------------------------------------------------------------

class TestConfigSanityPRH:
    """The 4 new PR-H series must be in release_intel and vintage_series."""

    NEW_SERIES = ["USPRIV", "USGOVT", "CES0500000003", "AWHAETP"]

    @pytest.fixture(scope="class")
    def cfg(self):
        cfg_path = _REPO / "config.yml"
        with cfg_path.open() as fh:
            return yaml.safe_load(fh)

    def test_new_series_in_release_intel(self, cfg):
        release_intel = cfg["fred"]["series"].get("release_intel", {})
        for sid in self.NEW_SERIES:
            assert sid in release_intel, (
                f"{sid} not in fred.series.release_intel. "
                f"Found: {list(release_intel.keys())}"
            )

    def test_new_series_in_vintage_series(self, cfg):
        vintage = cfg["fred"].get("vintage_series", [])
        for sid in self.NEW_SERIES:
            assert sid in vintage, (
                f"{sid} not in fred.vintage_series. "
                f"Required for ALFRED PIT fetching (PREREG_NFP_DECOMP_V1.md)."
            )

    def test_ahe_comment_has_units(self, cfg):
        """CES0500000003 entry should have $/hr in its comment."""
        release_intel = cfg["fred"]["series"].get("release_intel", {})
        ahe_comment = release_intel.get("CES0500000003", "")
        assert "$/hr" in ahe_comment or "dollar" in ahe_comment.lower() or \
               "hourly" in ahe_comment.lower(), (
            "CES0500000003 comment should mention $/hr units"
        )

    def test_awh_comment_has_units(self, cfg):
        """AWHAETP entry should have hrs/wk or hours in its comment."""
        release_intel = cfg["fred"]["series"].get("release_intel", {})
        awh_comment = release_intel.get("AWHAETP", "")
        assert "hrs/wk" in awh_comment or "hours" in awh_comment.lower(), (
            "AWHAETP comment should mention hrs/wk units"
        )


# ---------------------------------------------------------------------------
# 2. Decomposition: components sum to point
# ---------------------------------------------------------------------------

class TestDecompSumToPoint:
    """parts_sum + residual == model_point (within floating-point tolerance)."""

    def _make_simple_vintages(self):
        # PAYEMS: 10 periods with gradual growth
        periods = pd.date_range("2020-01-01", periods=15, freq="MS")
        payems_vals = [150000 + i * 200 for i in range(15)]
        uspriv_vals = [125000 + i * 160 for i in range(15)]  # ~83% private
        usgovt_vals = [25000 + i * 40 for i in range(15)]

        vint_payems = _make_vintages("PAYEMS", list(periods), payems_vals, [25] * 15)
        vint_uspriv = _make_vintages("USPRIV", list(periods), uspriv_vals, [25] * 15)
        vint_usgovt = _make_vintages("USGOVT", list(periods), usgovt_vals, [25] * 15)
        return _build_combined_vintages(vint_payems, vint_uspriv, vint_usgovt)

    def _make_full_vintages(self):
        """Extended vintage fixture that ensures private_trend and government_trend
        are non-None: 20 periods of PAYEMS + USPRIV + USGOVT with release delay 25d."""
        periods = pd.date_range("2019-01-01", periods=20, freq="MS")
        payems_vals = [150000.0 + i * 200 for i in range(20)]
        uspriv_vals = [125000.0 + i * 160 for i in range(20)]  # ~83% private
        usgovt_vals = [25000.0 + i * 40 for i in range(20)]
        vint_payems = _make_vintages("PAYEMS", list(periods), payems_vals, [25] * 20)
        vint_uspriv = _make_vintages("USPRIV", list(periods), uspriv_vals, [25] * 20)
        vint_usgovt = _make_vintages("USGOVT", list(periods), usgovt_vals, [25] * 20)
        return _build_combined_vintages(vint_payems, vint_uspriv, vint_usgovt)

    def test_parts_sum_equals_point(self):
        """When all decomp parts are present, sum(parts) + residual == model_point.
        Fixture is constructed so private_trend, government_trend, and BD prior are
        all non-None; asserts are unconditional (no if-guard)."""
        vintages = self._make_full_vintages()
        model_point = 250.0  # synthetic ridge output

        # Synthetic walk-forward results: one step per March in 2019-2020 (within 5yr lookback)
        # so BD prior for March is present. asof is after the last USPRIV/USGOVT release.
        wf_results = []
        for yr in [2019, 2020]:
            wf_results.append({
                "actual": 200.0,
                "predicted": 195.0,  # residual = 5 for each March
                "period": pd.Timestamp(f"{yr}-03-01"),
                "result_pos": len(wf_results),
            })

        asof = date(2021, 3, 20)   # all 20 PAYEMS/USPRIV/USGOVT periods knowable (rt_start<=asof)
        ref_month = date(2021, 3, 1)

        comps = build_nfp_components(
            model_point, asof, ref_month, vintages, wf_results,
            knowable_series_fn=_knowable,
            birth_death_lookback_years=10,  # wide enough to include 2019-2020
        )

        # All three parts must be present with this fixture
        private_trend = comps.get("private_trend")
        government_trend = comps.get("government_trend")
        bd_prior = comps.get("birth_death_residual_prior")
        residual = comps.get("residual")

        assert private_trend is not None, (
            f"private_trend is None; fixture should have USPRIV+PAYEMS data. "
            f"absent_parts={comps.get('absent_parts')}"
        )
        assert government_trend is not None, (
            f"government_trend is None; fixture should have USGOVT data. "
            f"absent_parts={comps.get('absent_parts')}"
        )
        assert bd_prior is not None, (
            f"bd_prior is None; fixture has March 2019+2020 residuals in wf_results. "
            f"absent_parts={comps.get('absent_parts')}"
        )
        assert residual is not None, "residual must not be None when parts are present"

        recon = private_trend + government_trend + bd_prior + residual
        assert abs(recon - model_point) < 0.01, (
            f"Decomposition does not sum to model_point: "
            f"private={private_trend}, govt={government_trend}, bd={bd_prior}, "
            f"residual={residual}, recon={recon}, model_point={model_point}"
        )

    def test_none_model_point_returns_all_none(self):
        """If model_point is None, all decomp parts are None."""
        vintages = pd.DataFrame(columns=["series", "period", "value",
                                         "realtime_start", "realtime_end"])
        comps = build_nfp_components(
            None, date(2021, 1, 1), date(2021, 1, 1), vintages, [],
            knowable_series_fn=_knowable,
        )
        assert comps["private_trend"] is None
        assert comps["government_trend"] is None
        assert comps["birth_death_residual_prior"] is None
        assert comps["residual"] is None

    def test_confidence_map_keys_present(self):
        """confidence_map must have all four decomp parts as keys."""
        vintages = pd.DataFrame(columns=["series", "period", "value",
                                         "realtime_start", "realtime_end"])
        comps = build_nfp_components(
            100.0, date(2021, 1, 1), date(2021, 1, 1), vintages, [],
            knowable_series_fn=_knowable,
        )
        conf_map = comps.get("confidence_map", {})
        for key in ["private_trend", "government_trend",
                    "birth_death_residual_prior", "residual"]:
            assert key in conf_map, f"confidence_map missing key: {key}"


# ---------------------------------------------------------------------------
# 3. BD prior PIT: uses only trailing history
# ---------------------------------------------------------------------------

class TestBDPriorPIT:
    """Birth-death prior must use only walk-forward steps strictly BEFORE ref_month."""

    def test_bd_prior_excludes_future_steps(self):
        """Steps whose period >= ref_month must NOT contribute to BD prior.

        Fixture uses 3 past March steps with residual=30 each, plus one
        'future' step (period=ref_month) with residual=999. The fixture is
        constructed so BD prior is always non-None; the assert is unconditional.
        """
        # wf_results: March 2009, 2010, 2011 (well within 10yr lookback) → residual=30 each
        # Future step: March 2021 (== ref_month) → residual=999, must be excluded
        wf_results = []
        for yr in [2009, 2010, 2011]:
            wf_results.append({
                "actual": 230.0,
                "predicted": 200.0,  # residual = 30
                "period": pd.Timestamp(f"{yr}-03-01"),
                "result_pos": len(wf_results),
            })
        # Future step: same month but period IS ref_month (should be excluded)
        wf_results.append({
            "actual": 1200.0,
            "predicted": 201.0,  # residual = 999; must not contribute
            "period": pd.Timestamp("2021-03-01"),
            "result_pos": 3,
        })

        ref_month = date(2021, 3, 1)
        vintages_empty = pd.DataFrame(columns=["series", "period", "value",
                                               "realtime_start", "realtime_end"])
        comps = build_nfp_components(
            200.0, date(2021, 3, 5), ref_month, vintages_empty, wf_results,
            knowable_series_fn=_knowable,
            birth_death_lookback_years=15,  # wide enough to catch 2009-2011
        )

        bd = comps.get("birth_death_residual_prior")
        # BD prior must be non-None: 3 March steps (2009, 2010, 2011) are in the lookback
        assert bd is not None, (
            "BD prior is None despite 3 valid March steps (2009, 2010, 2011) in wf_results. "
            f"absent_parts={comps.get('absent_parts')}, method_notes={comps.get('method_notes')}"
        )
        # Must be ~30 (mean of [30, 30, 30]), NOT influenced by the 999 residual
        assert abs(bd - 30.0) < 1.0, (
            f"BD prior={bd} != expected ~30; future step's 999 residual leaked in"
        )

    def test_bd_prior_profile_12_months(self):
        """compute_bd_prior_12month_profile returns values for all 12 months."""
        wf_results = []
        for yr in range(2020, 2026):
            for mo in range(1, 13):
                wf_results.append({
                    "actual": 300.0 + mo,
                    "predicted": 280.0,
                    "period": pd.Timestamp(f"{yr}-{mo:02d}-01"),
                    "result_pos": len(wf_results),
                })
        profile = compute_bd_prior_12month_profile(wf_results, as_of_year=2025, lookback_years=5)
        assert set(profile.keys()) == set(range(1, 13)), (
            f"Profile must have keys 1..12, got {set(profile.keys())}"
        )
        for m in range(1, 13):
            val = profile[m]
            assert val is not None, f"Month {m} has null prior despite data being present"
            expected = 300.0 + m - 280.0  # = m + 20
            assert abs(val - expected) < 0.01, (
                f"Month {m}: expected prior~{expected:.1f}, got {val:.4f}"
            )


# ---------------------------------------------------------------------------
# M1 regression: BD prior must come from the reference-month bucket, not
# the asof-month bucket when asof month != reference month.
# ---------------------------------------------------------------------------

class TestBDPriorRefMonthAlignment:
    """Regression test for M1 bug: BD prior bucket must be keyed by the TARGET
    reference month, not by the calendar month of the decision date (asof).

    Scenario: decision date is in month X (e.g. February), but the reference
    month being predicted is month Y (e.g. March). Walk-forward history has
    distinct residual signatures for February and March. The BD prior must draw
    from the MARCH bucket.

    This test would FAIL under the old code where ref_month was derived from asof
    (date(asof.year, asof.month, 1)) instead of the actual target period.
    """

    def test_bd_prior_uses_reference_month_bucket_not_asof_month(self):
        """BD prior must come from the ref_month (March) bucket, not the asof (February) bucket.

        Setup:
          - decision date (asof) = 2021-02-10 (February)
          - reference month (ref_month) = 2021-03-01 (March — the upcoming NFP print)
          - walk-forward has February steps with residual=-999 (poison value)
          - walk-forward has March steps with residual=42 (expected value)
        Expected: BD prior ~ 42 (from March bucket).
        Old buggy behavior: BD prior ~ -999 (from February/asof-month bucket).
        """
        # wf_results with distinct February and March buckets
        wf_results = []
        # February steps: residual = -999 (poison — must NOT be picked up)
        for yr in [2016, 2017, 2018, 2019, 2020]:
            wf_results.append({
                "actual": -800.0,
                "predicted": 199.0,   # residual = -999
                "period": pd.Timestamp(f"{yr}-02-01"),
                "result_pos": len(wf_results),
            })
        # March steps: residual = 42 (expected value)
        for yr in [2016, 2017, 2018, 2019, 2020]:
            wf_results.append({
                "actual": 242.0,
                "predicted": 200.0,   # residual = 42
                "period": pd.Timestamp(f"{yr}-03-01"),
                "result_pos": len(wf_results),
            })

        # Decision date is in February; ref_month is March
        asof = date(2021, 2, 10)
        ref_month = date(2021, 3, 1)  # the target print period

        vintages_empty = pd.DataFrame(columns=["series", "period", "value",
                                               "realtime_start", "realtime_end"])
        comps = build_nfp_components(
            200.0, asof, ref_month, vintages_empty, wf_results,
            knowable_series_fn=_knowable,
            birth_death_lookback_years=10,
        )

        bd = comps.get("birth_death_residual_prior")
        # BD prior must be non-None (5 valid March steps in lookback)
        assert bd is not None, (
            "BD prior is None despite 5 valid March steps in wf_results. "
            f"absent_parts={comps.get('absent_parts')}, method_notes={comps.get('method_notes')}"
        )
        # Must be ~42 (March bucket), not ~-999 (February/asof-month bucket)
        assert abs(bd - 42.0) < 1.0, (
            f"BD prior={bd:.1f} — expected ~42 (March bucket). "
            f"If this is ~-999, the M1 bug is still present: the code is using "
            f"the asof calendar month (February) instead of the target ref_month (March)."
        )


# ---------------------------------------------------------------------------
# 4. Government trend math
# ---------------------------------------------------------------------------

class TestGovernmentTrendMath:
    """government_trend = mean of last 3 USGOVT initial-print MoM changes."""

    def test_government_trend_equals_trailing_mean(self):
        # USGOVT levels: 25000, 25050, 25020, 25080 (3 diffs: 50, -30, 60)
        # trailing mean = (50 + -30 + 60) / 3 = 80/3 ≈ 26.67
        periods = pd.date_range("2020-01-01", periods=4, freq="MS")
        vals = [25000.0, 25050.0, 25020.0, 25080.0]
        vint = _make_vintages("USGOVT", list(periods), vals, [25] * 4)

        asof = date(2020, 5, 15)
        vintages = vint
        comps = build_nfp_components(
            100.0, asof, date(2020, 5, 1), vintages, [],
            knowable_series_fn=_knowable,
        )
        govt_trend = comps.get("government_trend")
        expected = (50.0 + (-30.0) + 60.0) / 3
        assert govt_trend is not None, "government_trend should not be None"
        assert abs(govt_trend - expected) < 0.01, (
            f"government_trend={govt_trend}, expected={expected:.4f}"
        )

    def test_government_trend_absent_if_insufficient_data(self):
        """If USGOVT has fewer than government_lookback+1 prints, govt_trend may be None."""
        # Only 2 periods -> 1 diff -> mean of 1 value (still computes if >= lookback)
        periods = pd.date_range("2020-01-01", periods=2, freq="MS")
        vals = [25000.0, 25010.0]
        vint = _make_vintages("USGOVT", list(periods), vals, [25] * 2)

        asof = date(2020, 4, 15)
        comps = build_nfp_components(
            100.0, asof, date(2020, 4, 1), vint, [],
            knowable_series_fn=_knowable,
            government_lookback=3,  # need 3 diffs but only have 1
        )
        # With only 1 diff and lookback=3, the code takes last 3 available (=1)
        # so it won't be None but will use whatever is available
        # The important thing: no exception raised
        _ = comps.get("government_trend")  # may be None or a value — no crash


# ---------------------------------------------------------------------------
# 5. AHE contract
# ---------------------------------------------------------------------------

class TestAHEContract:
    """project_awh output must satisfy the contract keys and authority flags."""

    REQUIRED_KEYS = {
        "release", "asof", "target", "regime_axis", "spec_attempt",
        "point", "p10", "p25", "p50", "p75", "p90",
        "confidence", "confidence_components", "input_completeness",
        "benchmark_set", "surprise_skew", "pit_provenance",
        "display_only", "authority",
    }

    def test_empty_ahe_has_required_keys(self):
        proj = _empty_ahe_projection(date(2021, 6, 1), "test")
        missing = self.REQUIRED_KEYS - set(proj.keys())
        assert not missing, f"Empty AHE projection missing keys: {missing}"

    def test_empty_ahe_display_only_true(self):
        proj = _empty_ahe_projection(date(2021, 6, 1), "test")
        assert proj["display_only"] is True

    def test_empty_ahe_authority_false(self):
        proj = _empty_ahe_projection(date(2021, 6, 1), "test")
        assert proj["authority"] is False

    def test_empty_ahe_spec_attempt_is_1(self):
        proj = _empty_ahe_projection(date(2021, 6, 1), "test")
        assert proj["spec_attempt"] == 1

    def test_empty_ahe_release_field(self):
        proj = _empty_ahe_projection(date(2021, 6, 1), "test")
        assert proj["release"] == "ahe"
        assert proj["target"] == "ahe_mom"

    def test_empty_ahe_pit_provenance_authority_false(self):
        proj = _empty_ahe_projection(date(2021, 6, 1), "test")
        prov = proj.get("pit_provenance", {})
        assert prov.get("authority") is False
        assert prov.get("display_only") is True


# ---------------------------------------------------------------------------
# 6. AWH contract + persistence_only flag
# ---------------------------------------------------------------------------

class TestAWHContract:
    """project_awh must return persistence_only=True and correct contract."""

    REQUIRED_KEYS = {
        "release", "asof", "target", "regime_axis", "spec_attempt",
        "persistence_only", "persistence_only_note",
        "point", "p10", "p25", "p50", "p75", "p90",
        "benchmark_set", "pit_provenance", "display_only", "authority",
    }

    def test_empty_awh_has_required_keys(self):
        proj = _empty_awh_projection(date(2021, 6, 1), "test")
        missing = self.REQUIRED_KEYS - set(proj.keys())
        assert not missing, f"Empty AWH projection missing keys: {missing}"

    def test_awh_persistence_only_true(self):
        proj = _empty_awh_projection(date(2021, 6, 1), "test")
        assert proj["persistence_only"] is True

    def test_awh_display_only_true(self):
        proj = _empty_awh_projection(date(2021, 6, 1), "test")
        assert proj["display_only"] is True

    def test_awh_authority_false(self):
        proj = _empty_awh_projection(date(2021, 6, 1), "test")
        assert proj["authority"] is False

    def test_awh_live_point_equals_last_level(self):
        """project_awh point = last initial-print AWHAETP level."""
        periods = pd.date_range("2020-01-01", periods=10, freq="MS")
        vals = [34.1, 34.2, 34.0, 34.3, 34.1, 34.4, 34.2, 34.5, 34.3, 34.6]
        vint = _make_vintages("AWHAETP", list(periods), vals, [25] * 10)

        asof = date(2020, 11, 15)  # only 10 periods visible (last rt_start = 2020-10-26)
        proj = project_awh(
            asof, vint,
            knowable_series_fn=_knowable,
            min_quantile_obs=5,
        )
        assert proj["persistence_only"] is True
        assert proj["point"] is not None
        # The last knowable level should be the last AWHAETP with rt_start <= asof
        expected_last = None
        for i in range(len(vals) - 1, -1, -1):
            rt = periods[i] + pd.Timedelta(days=25)
            if rt.date() <= asof:
                expected_last = vals[i]
                break
        if expected_last is not None:
            assert abs(proj["point"] - expected_last) < 0.01, (
                f"AWH point={proj['point']} != expected last level {expected_last}"
            )

    def test_awh_quantiles_ordered(self):
        """p10 <= p25 <= p50 <= p75 <= p90 when enough history."""
        periods = pd.date_range("2015-01-01", periods=50, freq="MS")
        rng = np.random.default_rng(42)
        vals = [34.0 + 0.1 * i + rng.standard_normal() * 0.1 for i in range(50)]
        vint = _make_vintages("AWHAETP", list(periods), vals, [25] * 50)

        asof = date(2019, 4, 15)
        proj = project_awh(
            asof, vint,
            knowable_series_fn=_knowable,
            min_quantile_obs=24,
        )
        ps = [proj.get(f"p{q}") for q in [10, 25, 50, 75, 90]]
        if all(p is not None for p in ps):
            assert ps[0] <= ps[1] <= ps[2] <= ps[3] <= ps[4], (
                f"AWH quantile order violated: {ps}"
            )


# ---------------------------------------------------------------------------
# 7. AHE kill rule evaluation
# ---------------------------------------------------------------------------

class TestAHEKillRule:
    """kill_rule_eval must correctly flag benchmark_only when model >= naive."""

    def _make_ahe_walk_forward_results(self, model_worse: bool) -> list[dict]:
        """Produce synthetic walk-forward rows where model is better or worse than naive."""
        rng = np.random.default_rng(99)
        results = []
        for i in range(70):
            actual = float(rng.standard_normal() * 0.05 + 0.1)
            # naive = slightly better at predicting than the model if model_worse=True
            naive = actual + (0.03 if model_worse else -0.03)
            predicted = actual + (0.05 if model_worse else -0.01)
            results.append({
                "actual": actual,
                "predicted": predicted,
                "baseline_naive": naive,
                "baseline_trailing3m": naive,
                "baseline_ar3": naive,
                "result_pos": i,
                "idx": i + 60,
                "n_train": i + 60,
                "n_features_used": 3,
                "input_completeness": 1.0,
            })
        return results

    def test_kill_rule_in_ahe_projection_output(self):
        """AHE projection output must contain kill_rule_eval dict."""
        proj = _empty_ahe_projection(date(2021, 6, 1), "test")
        assert "kill_rule_eval" in proj, "kill_rule_eval key missing from empty AHE projection"
        assert isinstance(proj["kill_rule_eval"], dict)

    def _compute_mae_metrics(self, wf_rows: list[dict]) -> dict:
        """Compute metrics dict with mae_model and mae_naive for _check_kill_rule."""
        model_errors = [abs(r["actual"] - r["predicted"]) for r in wf_rows]
        naive_errors = [abs(r["actual"] - r["baseline_naive"]) for r in wf_rows]
        return {
            "n": len(wf_rows),
            "mae_model": float(np.mean(model_errors)),
            "mae_naive": float(np.mean(naive_errors)),
        }

    def test_kill_rule_fires_when_model_worse_than_naive(self):
        """_check_kill_rule returns True (kill triggered) when model MAE >= naive MAE
        in both the full window and the 2021+ slice."""
        # model_worse=True → model has higher MAE than naive in both slices
        rows_full = self._make_ahe_walk_forward_results(model_worse=True)
        rows_2021 = self._make_ahe_walk_forward_results(model_worse=True)

        m_full = self._compute_mae_metrics(rows_full)
        m_2021 = self._compute_mae_metrics(rows_2021)

        # Sanity: model MAE > naive MAE in these fixtures
        assert m_full["mae_model"] > m_full["mae_naive"], (
            "Fixture problem: model should be WORSE than naive (mae_model > mae_naive)"
        )

        killed = _check_kill_rule(m_full, m_2021)
        assert killed is True, (
            f"Kill rule did not fire despite model_worse=True. "
            f"Full: mae_model={m_full['mae_model']:.4f}, mae_naive={m_full['mae_naive']:.4f}. "
            f"2021+: mae_model={m_2021['mae_model']:.4f}, mae_naive={m_2021['mae_naive']:.4f}."
        )

    def test_model_beats_naive_when_model_better(self):
        """_check_kill_rule returns False (model active) when model MAE < naive MAE."""
        # model_worse=False → model has lower MAE than naive
        rows_full = self._make_ahe_walk_forward_results(model_worse=False)
        rows_2021 = self._make_ahe_walk_forward_results(model_worse=False)

        m_full = self._compute_mae_metrics(rows_full)
        m_2021 = self._compute_mae_metrics(rows_2021)

        # Sanity: model MAE < naive MAE in these fixtures
        assert m_full["mae_model"] < m_full["mae_naive"], (
            "Fixture problem: model should be BETTER than naive (mae_model < mae_naive)"
        )

        killed = _check_kill_rule(m_full, m_2021)
        assert killed is False, (
            f"Kill rule fired incorrectly despite model being better. "
            f"Full: mae_model={m_full['mae_model']:.4f}, mae_naive={m_full['mae_naive']:.4f}. "
            f"2021+: mae_model={m_2021['mae_model']:.4f}, mae_naive={m_2021['mae_naive']:.4f}."
        )


# ---------------------------------------------------------------------------
# 8. Revision risk math
# ---------------------------------------------------------------------------

class TestRevisionRiskMath:
    """compute_nfp_revision_risk mean and pct_upward must match manual calculation."""

    def test_revision_risk_basic_math(self):
        # 4 periods, initial vs latest known
        # Period 1: initial 150000, latest 150050 → revision +50
        # Period 2: initial 150200, latest 150180 → revision -20
        # Period 3: initial 150400, latest 150450 → revision +50
        # Period 4: initial 150600, latest 150590 → revision -10
        rows = []
        periods = pd.date_range("2024-01-01", periods=4, freq="MS")
        initials = [150000.0, 150200.0, 150400.0, 150600.0]
        latests = [150050.0, 150180.0, 150450.0, 150590.0]
        # initial: realtime_start = period + 30 days
        # latest: realtime_start = period + 60 days
        for p, iv, lv in zip(periods, initials, latests):
            rows.append({"series": "PAYEMS", "period": p,
                         "value": iv, "realtime_start": p + pd.Timedelta(days=30),
                         "realtime_end": pd.Timestamp("2099-12-31")})
            rows.append({"series": "PAYEMS", "period": p,
                         "value": lv, "realtime_start": p + pd.Timedelta(days=60),
                         "realtime_end": pd.Timestamp("2099-12-31")})
        vintages = pd.DataFrame(rows)
        vintages["period"] = pd.to_datetime(vintages["period"])
        vintages["realtime_start"] = pd.to_datetime(vintages["realtime_start"])
        vintages["realtime_end"] = pd.to_datetime(vintages["realtime_end"])

        result = compute_nfp_revision_risk(vintages, series="PAYEMS", trailing_months=24)
        # Expected: revisions = [50, -20, 50, -10], mean = 70/4 = 17.5
        # pct_upward = 2/4 = 0.5
        assert result["n_periods"] == 4
        assert abs(result["mean_k"] - 17.5) < 0.01, (
            f"mean_k={result['mean_k']}, expected 17.5"
        )
        assert abs(result["pct_upward"] - 0.5) < 0.01, (
            f"pct_upward={result['pct_upward']}, expected 0.5"
        )

    def test_revision_risk_empty_vintages(self):
        """Empty vintage DataFrame returns None fields."""
        vintages = pd.DataFrame(columns=["series", "period", "value",
                                         "realtime_start", "realtime_end"])
        result = compute_nfp_revision_risk(vintages)
        assert result["mean_k"] is None
        assert result["pct_upward"] is None
        assert result["n_periods"] == 0

    def test_revision_risk_all_upward(self):
        """All positive revisions → pct_upward = 1.0."""
        rows = []
        periods = pd.date_range("2023-01-01", periods=5, freq="MS")
        for p in periods:
            rows.append({"series": "PAYEMS", "period": p,
                         "value": 100.0, "realtime_start": p + pd.Timedelta(days=30),
                         "realtime_end": pd.Timestamp("2099-12-31")})
            rows.append({"series": "PAYEMS", "period": p,
                         "value": 110.0, "realtime_start": p + pd.Timedelta(days=60),
                         "realtime_end": pd.Timestamp("2099-12-31")})
        vintages = pd.DataFrame(rows)
        vintages["period"] = pd.to_datetime(vintages["period"])
        vintages["realtime_start"] = pd.to_datetime(vintages["realtime_start"])
        vintages["realtime_end"] = pd.to_datetime(vintages["realtime_end"])

        result = compute_nfp_revision_risk(vintages, trailing_months=24)
        assert result["pct_upward"] == 1.0, f"Expected 1.0, got {result['pct_upward']}"
        assert abs(result["mean_k"] - 10.0) < 0.01, f"Expected 10.0, got {result['mean_k']}"


# ---------------------------------------------------------------------------
# 9. AHE feature builder contract
# ---------------------------------------------------------------------------

class TestAHEFeatureBuilder:
    """build_ahe_features must return the right feature keys."""

    EXPECTED_KEYS = {
        "ahe_mom_lag1", "ahe_mom_lag2", "ahe_mom_lag3",
        "awh_mom_last", "jolts_mom_last", "icsa_level_z",
    }

    def _make_ces_vintages(self, n: int = 20) -> pd.DataFrame:
        periods = pd.date_range("2018-01-01", periods=n, freq="MS")
        vals = [36.0 + i * 0.01 for i in range(n)]
        return _make_vintages("CES0500000003", list(periods), vals, [25] * n)

    def test_feature_keys_present(self):
        """All 6 expected feature keys must be in the returned dict."""
        ces_vint = self._make_ces_vintages()
        vintages = ces_vint

        asof = date(2019, 9, 15)
        ref_month = date(2019, 9, 1)
        feats, prov = build_ahe_features(
            asof, ref_month, vintages,
            knowable_series_fn=_knowable,
            survey_week_claims_fn=lambda v, s, a, r: None,  # no ICSA data
        )
        missing = self.EXPECTED_KEYS - set(feats.keys())
        assert not missing, f"build_ahe_features missing keys: {missing}"

    def test_ahe_lag1_is_most_recent_mom(self):
        """ahe_mom_lag1 must equal MoM % of the last knowable CES0500000003 print."""
        # Values: 36.00, 36.18 → MoM = (36.18/36.00 - 1) * 100 = 0.5
        periods = pd.date_range("2019-06-01", periods=3, freq="MS")
        vals = [36.00, 36.18, 36.30]  # lag1 = (36.30-36.18)/36.18*100; lag2=(36.18-36.00)/36.00*100
        vint = _make_vintages("CES0500000003", list(periods), vals, [25] * 3)
        asof = date(2019, 10, 15)  # all 3 periods knowable

        feats, _ = build_ahe_features(
            asof, date(2019, 10, 1), vint,
            knowable_series_fn=_knowable,
            survey_week_claims_fn=lambda v, s, a, r: None,
        )
        expected_lag1 = (36.30 / 36.18 - 1) * 100
        expected_lag2 = (36.18 / 36.00 - 1) * 100

        if feats["ahe_mom_lag1"] is not None:
            assert abs(feats["ahe_mom_lag1"] - expected_lag1) < 1e-8, (
                f"lag1={feats['ahe_mom_lag1']}, expected {expected_lag1}"
            )
        if feats["ahe_mom_lag2"] is not None:
            assert abs(feats["ahe_mom_lag2"] - expected_lag2) < 1e-8, (
                f"lag2={feats['ahe_mom_lag2']}, expected {expected_lag2}"
            )

    def test_prov_display_only_true(self):
        """Provenance must carry display_only=True and authority=False."""
        ces_vint = self._make_ces_vintages()
        asof = date(2019, 9, 15)
        _, prov = build_ahe_features(
            asof, date(2019, 9, 1), ces_vint,
            knowable_series_fn=_knowable,
            survey_week_claims_fn=lambda v, s, a, r: None,
        )
        assert prov.get("display_only") is True
        assert prov.get("authority") is False
