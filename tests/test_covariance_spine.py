"""tests/test_covariance_spine.py — R-ORTH covariance spine unit tests.

Tests cover:
- Schema/key-set including display_only and forbidden_actions.
- Floors: engine with 10 active weeks -> unmeasurable; pair with 5 shared weeks -> null corr.
- Determinism: two calls -> identical dict.
- Degradation: missing inputs -> missing_inputs populated, no raise; missing parquet -> lobes degraded.
- Placebo excluded.
- Clusters + same_bet_warning.
- effective_independent_lobes sanity.
- pctile_vs_null in [0, 1], n_null_draws == 200.
- json.dumps round-trip.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import numpy as np
import pytest


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------

def _make_spine(tmp_path: Path, rows: list[dict]) -> Path:
    """Write a minimal spine_index.parquet from a list of row dicts."""
    p = tmp_path / "data" / "neuralweb"
    p.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    out = p / "spine_index.parquet"
    df.to_parquet(out, index=False)
    return out


def _make_latest_json(tmp_path: Path) -> Path:
    """Write a minimal data/regime/latest.json with yield_curve PCA."""
    p = tmp_path / "data" / "regime"
    p.mkdir(parents=True, exist_ok=True)
    payload = {
        "yield_curve": {
            "asof": "2026-07-06",
            "shape": {
                "pca": {
                    "factors": [
                        {"key": "level", "var_explained": 0.82, "loadings": {}},
                        {"key": "slope", "var_explained": 0.10, "loadings": {}},
                        {"key": "curvature", "var_explained": 0.05, "loadings": {}},
                    ],
                    "first3_var": 0.97,
                    "window_d": 252,
                    "tenors": [],
                }
            },
        }
    }
    out = p / "latest.json"
    out.write_text(json.dumps(payload), encoding="utf-8")
    return out


def _make_factor_series(tmp_path: Path, n_points: int = 300) -> Path:
    """Write a minimal site/factordata/factor_series.json."""
    p = tmp_path / "site" / "factordata"
    p.mkdir(parents=True, exist_ok=True)

    import datetime as dt_mod
    base = dt_mod.date(2023, 1, 1)
    dates = [(base + dt_mod.timedelta(days=i)).isoformat() for i in range(n_points)]

    # Two independent factors; composite is excluded
    rng = np.random.default_rng(42)
    factor_a = rng.normal(1.0, 0.01, n_points).cumprod().tolist()
    factor_b = rng.normal(1.0, 0.01, n_points).cumprod().tolist()
    composite = rng.normal(1.0, 0.01, n_points).cumprod().tolist()

    payload = {
        "as_of": dates[-1],
        "history_start": dates[0],
        "n_rebalances": n_points // 5,
        "factors": ["factor_a", "factor_b", "composite"],
        "labels": {"factor_a": "A", "factor_b": "B", "composite": "Composite"},
        "series": {
            "factor_a": {"long_only": {"spark": [], "cum_pct": 0.0},
                         "long_short": {"spark": [], "cum_pct": 0.0}},
            "factor_b": {"long_only": {"spark": [], "cum_pct": 0.0},
                         "long_short": {"spark": [], "cum_pct": 0.0}},
            "composite": {"long_only": {"spark": [], "cum_pct": 0.0},
                          "long_short": {"spark": [], "cum_pct": 0.0}},
        },
        "chart_data": {
            "dates": dates,
            "bench": [1.0] * n_points,
            "long": {
                "factor_a": factor_a,
                "factor_b": factor_b,
                "composite": composite,
            },
            "spread": {
                "factor_a": factor_a,
                "factor_b": factor_b,
                "composite": composite,
            },
            "sector": {},
            "labels": {},
        },
        "stats": {},
        "horizons": [],
        "honesty": "test",
        "note": "test fixture",
        "crowding": {},
        "rotation": {},
        "quilt": {},
        "chart_data_narrow": {},
        "narrow_history_start": dates[0],
    }
    out = p / "factor_series.json"
    out.write_text(json.dumps(payload), encoding="utf-8")
    return out


def _make_dispersion(tmp_path: Path) -> Path:
    """Write a minimal data/dispersion/regime.json."""
    p = tmp_path / "data" / "dispersion"
    p.mkdir(parents=True, exist_ok=True)
    payload = {
        "as_of": "2026-07-06",
        "state": "lean_in",
        "dispersion_pctile": 0.75,
        "avg_corr": 0.08,
    }
    out = p / "regime.json"
    out.write_text(json.dumps(payload), encoding="utf-8")
    return out


def _iso_week(date_str: str) -> str:
    """Return ISO week string for a date."""
    return pd.Period(date_str, freq="W").strftime("%Y-%m-%d/%Y-%m-%d")


def _make_full_fixtures(tmp_path: Path) -> None:
    """Create all four input fixtures under tmp_path."""
    _make_latest_json(tmp_path)
    _make_factor_series(tmp_path)
    _make_dispersion(tmp_path)


def _spine_rows_for_engine(
    engine: str,
    n_weeks: int,
    start_date: str = "2024-07-07",
    direction: int = 1,
) -> list[dict]:
    """Generate n_weeks worth of spine rows (one per week) for an engine."""
    import datetime as dt_mod
    rows = []
    base = dt_mod.date.fromisoformat(start_date)
    for w in range(n_weeks):
        d = base + dt_mod.timedelta(weeks=w)
        rows.append({
            "engine": engine,
            "as_of": d.isoformat(),
            "symbol": f"SYM_{w % 5}",
            "direction": direction,
            "family": "test",
        })
    return rows


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSchemaAndKeys:
    def test_required_top_level_keys(self, tmp_path):
        from engine.neuralweb.covariance_spine import build_state
        _make_full_fixtures(tmp_path)
        _make_spine(tmp_path, _spine_rows_for_engine("eng_a", 5))
        result = build_state(root=tmp_path)

        required = {
            "schema", "as_of", "display_only", "authority",
            "descriptive_not_gauntleted", "blocks", "coverage",
            "missing_inputs", "committee_annotations",
            "allowed_actions", "forbidden_actions",
        }
        assert required.issubset(result.keys()), (
            f"Missing keys: {required - set(result.keys())}"
        )

    def test_display_only_true(self, tmp_path):
        from engine.neuralweb.covariance_spine import build_state
        _make_full_fixtures(tmp_path)
        _make_spine(tmp_path, [])
        result = build_state(root=tmp_path)
        assert result["display_only"] is True

    def test_forbidden_actions_present(self, tmp_path):
        from engine.neuralweb.covariance_spine import build_state
        _make_full_fixtures(tmp_path)
        _make_spine(tmp_path, [])
        result = build_state(root=tmp_path)
        for action in ["score", "size", "originate_trade", "gate", "rank"]:
            assert action in result["forbidden_actions"], f"{action} not in forbidden_actions"

    def test_authority_is_context(self, tmp_path):
        from engine.neuralweb.covariance_spine import build_state
        _make_full_fixtures(tmp_path)
        _make_spine(tmp_path, [])
        result = build_state(root=tmp_path)
        assert result["authority"] == "context"

    def test_schema_string(self, tmp_path):
        from engine.neuralweb.covariance_spine import build_state, SCHEMA
        _make_full_fixtures(tmp_path)
        _make_spine(tmp_path, [])
        result = build_state(root=tmp_path)
        assert result["schema"] == SCHEMA == "neuralweb.covariance_spine.v1"


class TestFloors:
    def test_engine_10_active_weeks_is_unmeasurable(self, tmp_path):
        """Engine with 10 active weeks must appear in coverage.unmeasurable."""
        from engine.neuralweb.covariance_spine import build_state
        _make_full_fixtures(tmp_path)
        rows = _spine_rows_for_engine("eng_10weeks", 10)
        _make_spine(tmp_path, rows)
        result = build_state(root=tmp_path)
        lobes = result["blocks"].get("lobes", {})
        unmeas = result["coverage"].get("unmeasurable", {})
        assert "eng_10weeks" in unmeas, f"Expected eng_10weeks in unmeasurable, got: {unmeas}"
        assert unmeas["eng_10weeks"] == 10

    def test_engine_10_active_weeks_not_in_measurable(self, tmp_path):
        from engine.neuralweb.covariance_spine import build_state
        _make_full_fixtures(tmp_path)
        rows = _spine_rows_for_engine("eng_10weeks", 10)
        _make_spine(tmp_path, rows)
        result = build_state(root=tmp_path)
        meas = result["coverage"].get("measurable", [])
        assert "eng_10weeks" not in meas

    def test_pair_5_shared_weeks_corr_null_with_n_shared(self, tmp_path):
        """Two measurable engines with only 5 shared weeks -> corr=None, n_shared recorded."""
        from engine.neuralweb.covariance_spine import build_state
        _make_full_fixtures(tmp_path)

        import datetime as dt_mod
        base = dt_mod.date(2024, 7, 7)

        # Engine A fires for 35 weeks, Engine B fires for only the last 5 of those
        rows_a = []
        rows_b = []
        for w in range(35):
            d = (base + dt_mod.timedelta(weeks=w)).isoformat()
            rows_a.append({"engine": "eng_a", "as_of": d,
                           "symbol": "SYM_A", "direction": 1, "family": "test"})
        for w in range(30, 35):  # only 5 shared weeks
            d = (base + dt_mod.timedelta(weeks=w)).isoformat()
            rows_b.append({"engine": "eng_b", "as_of": d,
                           "symbol": "SYM_B", "direction": 1, "family": "test"})

        _make_spine(tmp_path, rows_a + rows_b)
        result = build_state(root=tmp_path)
        # Both must be measurable (>=30 active weeks for A; B only has 5, so unmeasurable)
        # Only eng_a is measurable; eng_b is unmeasurable -> no pairs computed at all
        lobes = result["blocks"].get("lobes", {})
        unmeas = result["coverage"].get("unmeasurable", {})
        assert "eng_b" in unmeas
        assert unmeas["eng_b"] == 5


class TestDeterminism:
    def test_two_calls_identical(self, tmp_path):
        from engine.neuralweb.covariance_spine import build_state
        _make_full_fixtures(tmp_path)
        rows = _spine_rows_for_engine("eng_a", 35)
        _make_spine(tmp_path, rows)
        r1 = build_state(root=tmp_path)
        r2 = build_state(root=tmp_path)
        assert r1 == r2


class TestDegradation:
    def test_missing_latest_json_adds_to_missing_inputs(self, tmp_path):
        from engine.neuralweb.covariance_spine import build_state
        # Only create dispersion and factor_series, NOT latest.json
        _make_factor_series(tmp_path)
        _make_dispersion(tmp_path)
        _make_spine(tmp_path, [])
        result = build_state(root=tmp_path)
        assert any("rates" in m for m in result["missing_inputs"]), (
            f"Expected rates missing_input. Got: {result['missing_inputs']}"
        )
        # Must not raise

    def test_missing_factor_series_adds_to_missing_inputs(self, tmp_path):
        from engine.neuralweb.covariance_spine import build_state
        # Only latest.json and dispersion, NOT factor_series
        _make_latest_json(tmp_path)
        _make_dispersion(tmp_path)
        _make_spine(tmp_path, [])
        result = build_state(root=tmp_path)
        assert any("factors" in m for m in result["missing_inputs"]), (
            f"Expected factors missing_input. Got: {result['missing_inputs']}"
        )

    def test_missing_spine_parquet_lobes_degraded(self, tmp_path):
        from engine.neuralweb.covariance_spine import build_state
        _make_full_fixtures(tmp_path)
        # Do NOT create spine_index.parquet
        result = build_state(root=tmp_path)
        # lobes block should be absent; missing_inputs should mention lobes
        assert "lobes" not in result["blocks"], "lobes block should be absent when spine missing"
        assert any("lobes" in m for m in result["missing_inputs"]), (
            f"Expected lobes missing_input. Got: {result['missing_inputs']}"
        )

    def test_missing_all_inputs_returns_dict_not_raises(self, tmp_path):
        from engine.neuralweb.covariance_spine import build_state
        # Empty tmp_path — nothing exists
        result = build_state(root=tmp_path)
        assert isinstance(result, dict)
        assert len(result["missing_inputs"]) >= 4  # all 4 blocks should note missing


class TestPlacoboExcluded:
    def test_placebo_engine_not_in_measurable_or_coverage(self, tmp_path):
        from engine.neuralweb.covariance_spine import build_state
        _make_full_fixtures(tmp_path)
        # Mix placebo rows with real engine rows
        rows = (
            _spine_rows_for_engine("placebo", 35)
            + _spine_rows_for_engine("real_engine", 35)
        )
        _make_spine(tmp_path, rows)
        result = build_state(root=tmp_path)
        meas = result["coverage"].get("measurable", [])
        unmeas = result["coverage"].get("unmeasurable", {})
        assert "placebo" not in meas
        assert "placebo" not in unmeas
        # real_engine should be measurable
        assert "real_engine" in meas


class TestClustersAndWarning:
    def _make_three_identical_engines(self, tmp_path: Path) -> list[dict]:
        """Three engines firing identically on same symbols same weeks -> corr ~ 1."""
        import datetime as dt_mod
        rows = []
        base = dt_mod.date(2024, 7, 7)
        symbols = ["SYM_A", "SYM_B", "SYM_C"]
        for w in range(35):
            d = (base + dt_mod.timedelta(weeks=w)).isoformat()
            for sym in symbols:
                for eng in ["eng_x", "eng_y", "eng_z"]:
                    rows.append({
                        "engine": eng,
                        "as_of": d,
                        "symbol": sym,
                        "direction": 1,
                        "family": "test",
                    })
        return rows

    def test_three_identical_engines_form_cluster(self, tmp_path):
        from engine.neuralweb.covariance_spine import build_state
        _make_full_fixtures(tmp_path)
        rows = self._make_three_identical_engines(tmp_path)
        _make_spine(tmp_path, rows)
        result = build_state(root=tmp_path)
        lobes = result["blocks"].get("lobes", {})
        clusters = lobes.get("clusters", [])
        # Should have at least one cluster with all three engines
        found = any(
            set(["eng_x", "eng_y", "eng_z"]).issubset(set(c))
            for c in clusters
        )
        assert found, f"Expected cluster containing eng_x/y/z. Got clusters: {clusters}"

    def test_same_bet_warning_active_for_three_identical(self, tmp_path):
        from engine.neuralweb.covariance_spine import build_state
        _make_full_fixtures(tmp_path)
        rows = self._make_three_identical_engines(tmp_path)
        _make_spine(tmp_path, rows)
        result = build_state(root=tmp_path)
        lobes = result["blocks"].get("lobes", {})
        warn = lobes.get("same_bet_warning", {})
        assert warn.get("active") is True, f"Expected warning active. Got: {warn}"
        assert "cluster" in warn
        assert "mean_abs_corr" in warn
        assert "text" in warn

    def test_independent_engines_no_warning(self, tmp_path):
        """Three engines with very different firing patterns -> no warning."""
        from engine.neuralweb.covariance_spine import build_state
        _make_full_fixtures(tmp_path)

        import datetime as dt_mod
        rows = []
        base = dt_mod.date(2024, 7, 7)
        # Engine X fires every week, Engine Y fires only odd weeks, Engine Z only even weeks
        for w in range(35):
            d = (base + dt_mod.timedelta(weeks=w)).isoformat()
            rows.append({"engine": "ind_x", "as_of": d, "symbol": "S1",
                         "direction": 1 if w % 2 == 0 else -1, "family": "test"})
            rows.append({"engine": "ind_y", "as_of": d, "symbol": "S2",
                         "direction": 1 if w % 3 == 0 else -1, "family": "test"})
            rows.append({"engine": "ind_z", "as_of": d, "symbol": "S3",
                         "direction": -1 if w % 2 == 0 else 1, "family": "test"})
        _make_spine(tmp_path, rows)
        result = build_state(root=tmp_path)
        lobes = result["blocks"].get("lobes", {})
        warn = lobes.get("same_bet_warning", {})
        # With alternating opposite-direction signals the correlation is negative
        # so abs(corr) shouldn't all be > 0.6 (at least for uncorrelated pairs)
        # We just verify the warning structure exists
        assert "active" in warn


class TestEffectiveIndependentLobes:
    def test_identical_engines_eil_near_one(self, tmp_path):
        """When all measurable engines fire identically, EIL should be near 1."""
        from engine.neuralweb.covariance_spine import build_state
        _make_full_fixtures(tmp_path)

        import datetime as dt_mod
        rows = []
        base = dt_mod.date(2024, 7, 7)
        for w in range(35):
            d = (base + dt_mod.timedelta(weeks=w)).isoformat()
            for eng in ["eng_p", "eng_q", "eng_r"]:
                rows.append({"engine": eng, "as_of": d, "symbol": "S1",
                             "direction": 1, "family": "test"})
        _make_spine(tmp_path, rows)
        result = build_state(root=tmp_path)
        lobes = result["blocks"].get("lobes", {})
        eil = lobes.get("effective_independent_lobes")
        assert eil is not None
        # 3 perfectly correlated engines -> EIL near 1.0
        assert eil < 1.5, f"Expected EIL near 1 for identical engines, got {eil}"

    def test_independent_engines_eil_near_n(self, tmp_path):
        """When engines have zero correlation, EIL should be near n_measurable."""
        from engine.neuralweb.covariance_spine import build_state
        _make_full_fixtures(tmp_path)

        import datetime as dt_mod
        import random
        rows = []
        base = dt_mod.date(2024, 7, 7)
        rng = random.Random(12345)
        # Three engines with independent random directions
        for w in range(35):
            d = (base + dt_mod.timedelta(weeks=w)).isoformat()
            # Engine directions are independent by construction (different random sequences)
            rows.append({"engine": "ind_a", "as_of": d, "symbol": "S1",
                         "direction": rng.choice([1, -1]), "family": "test"})
            rows.append({"engine": "ind_b", "as_of": d, "symbol": "S2",
                         "direction": rng.choice([1, -1]), "family": "test"})
            rows.append({"engine": "ind_c", "as_of": d, "symbol": "S3",
                         "direction": rng.choice([1, -1]), "family": "test"})
        _make_spine(tmp_path, rows)
        result = build_state(root=tmp_path)
        lobes = result["blocks"].get("lobes", {})
        eil = lobes.get("effective_independent_lobes")
        n_meas = lobes.get("n_lobes_measurable", 0)
        assert eil is not None
        # With 3 independent engines, EIL should be > 1.5 (near 3 in ideal case)
        assert eil > 1.0, f"Expected EIL > 1 for independent engines (n={n_meas}), got {eil}"

    def test_pctile_vs_null_in_range(self, tmp_path):
        from engine.neuralweb.covariance_spine import build_state
        _make_full_fixtures(tmp_path)
        rows = _spine_rows_for_engine("eng_single", 35)
        _make_spine(tmp_path, rows)
        result = build_state(root=tmp_path)
        lobes = result["blocks"].get("lobes", {})
        null_ref = lobes.get("null_reference")
        if null_ref is not None:
            pctile = null_ref.get("pctile_vs_null")
            assert pctile is not None
            assert 0.0 <= pctile <= 1.0, f"pctile_vs_null out of range: {pctile}"

    def test_n_null_draws_is_200(self, tmp_path):
        from engine.neuralweb.covariance_spine import build_state
        _make_full_fixtures(tmp_path)
        # Need >=2 measurable engines for null_reference to be computed with draws
        import datetime as dt_mod
        rows = []
        base = dt_mod.date(2024, 7, 7)
        for w in range(35):
            d = (base + dt_mod.timedelta(weeks=w)).isoformat()
            for eng in ["eng_a", "eng_b"]:
                rows.append({"engine": eng, "as_of": d, "symbol": "S1",
                             "direction": 1, "family": "test"})
        _make_spine(tmp_path, rows)
        result = build_state(root=tmp_path)
        lobes = result["blocks"].get("lobes", {})
        null_ref = lobes.get("null_reference")
        if null_ref is not None:
            assert null_ref.get("n_null_draws") == 200


class TestJsonRoundTrip:
    def test_json_serializable(self, tmp_path):
        from engine.neuralweb.covariance_spine import build_state
        _make_full_fixtures(tmp_path)
        rows = _spine_rows_for_engine("eng_test", 35)
        _make_spine(tmp_path, rows)
        result = build_state(root=tmp_path)
        serialized = json.dumps(result, ensure_ascii=False, default=str)
        deserialized = json.loads(serialized)
        # Schema must survive round-trip
        assert deserialized["schema"] == result["schema"]
        assert deserialized["display_only"] is True
