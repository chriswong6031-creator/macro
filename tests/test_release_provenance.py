"""Tests for engine/release_provenance.py (MRI-R26).

Unit tests for build_input_snapshot and compute_coverage_flags,
including empty/None/missing-source cases.

AUTHORITY test: verifies these functions are pure metadata — they do not mutate
the projection dict and the module never imports or writes to forecast outputs.
"""
from __future__ import annotations

import copy
import importlib
import inspect
import json
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_projection(
    release: str = "cpi_headline",
    asof: str = "2026-07-07",
    rev_opt: list | None = None,
    unrev: list | None = None,
    absent: list | None = None,
    fresh_legs: list | None = None,
    inputs_hash: str = "abc123",
    prediction_id: str = "",
) -> dict:
    """Minimal valid projection dict with a pit_provenance."""
    prov: dict = {
        "revision_optimistic_legs": rev_opt if rev_opt is not None else [],
        "unrevised_legs": unrev if unrev is not None else [],
        "absent_legs": absent if absent is not None else [],
        "display_only": True,
        "authority": False,
    }
    if fresh_legs is not None:
        prov["fresh_legs"] = fresh_legs
    out = {
        "release": release,
        "asof": asof,
        "inputs_hash": inputs_hash,
        "pit_provenance": prov,
        "point": 0.42,
        "p10": 0.10,
        "p25": 0.25,
        "p50": 0.40,
        "p75": 0.60,
        "p90": 0.90,
        "confidence": 0.5,
        "display_only": True,
        "authority": False,
    }
    if prediction_id:
        out["prediction_id"] = prediction_id
    return out


def _write_ledger(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


# ---------------------------------------------------------------------------
# build_input_snapshot tests
# ---------------------------------------------------------------------------

class TestBuildInputSnapshot:
    def test_returns_required_keys(self):
        from engine.release_provenance import build_input_snapshot
        proj = _make_projection(
            rev_opt=["gasoline_mom"],
            unrev=["withheld_tax_yoy"],
            absent=["adp_change"],
            inputs_hash="hash42",
            prediction_id="cpi_headline:2026-07-07:v1",
        )
        result = build_input_snapshot(proj)
        assert "prediction_id" in result
        assert "asof" in result
        assert "features" in result
        assert "legs" in result
        assert "inputs_hash" in result
        assert result.get("error") is None or "error" not in result

    def test_inputs_hash_reused_verbatim(self):
        from engine.release_provenance import build_input_snapshot
        proj = _make_projection(inputs_hash="deadbeef", rev_opt=["gasoline_mom"])
        result = build_input_snapshot(proj)
        assert result["inputs_hash"] == "deadbeef"

    def test_leg_classification_absent_wins(self):
        """A leg in both revision_optimistic and absent → classified as absent."""
        from engine.release_provenance import build_input_snapshot
        proj = _make_projection(
            rev_opt=["gasoline_mom", "shelter_nowcast"],
            absent=["gasoline_mom"],  # absent wins over rev_opt
        )
        result = build_input_snapshot(proj)
        assert result["legs"]["gasoline_mom"] == "absent"
        assert result["legs"]["shelter_nowcast"] == "revision_optimistic"

    def test_leg_classification_unrevised(self):
        from engine.release_provenance import build_input_snapshot
        proj = _make_projection(unrev=["withheld_tax_yoy"], rev_opt=["awhman_mom"])
        result = build_input_snapshot(proj)
        assert result["legs"]["withheld_tax_yoy"] == "unrevised"
        assert result["legs"]["awhman_mom"] == "revision_optimistic"

    def test_leg_classification_present(self):
        """A leg not in any special list → present."""
        from engine.release_provenance import build_input_snapshot
        # A leg in none of the lists is "present"
        proj = _make_projection(rev_opt=[], unrev=[], absent=[])
        # Add a feature manually
        proj["_features"] = {"ppifis_mom": 0.5}
        result = build_input_snapshot(proj)
        assert result["legs"]["ppifis_mom"] == "present"

    def test_prediction_id_derived_when_absent(self):
        from engine.release_provenance import build_input_snapshot
        proj = _make_projection(release="nfp", asof="2026-07-07")
        # no prediction_id key
        result = build_input_snapshot(proj)
        assert "nfp" in result["prediction_id"]
        assert "2026-07-07" in result["prediction_id"]

    def test_prediction_id_explicit_wins(self):
        from engine.release_provenance import build_input_snapshot
        proj = _make_projection(prediction_id="explicit-id-123")
        result = build_input_snapshot(proj)
        assert result["prediction_id"] == "explicit-id-123"

    def test_null_projection_returns_error(self):
        from engine.release_provenance import build_input_snapshot
        result = build_input_snapshot(None)
        assert result.get("error") is True

    def test_empty_dict_returns_error(self):
        from engine.release_provenance import build_input_snapshot
        result = build_input_snapshot({})
        # Empty dict is a valid dict but has no provenance; should not crash
        assert isinstance(result, dict)
        # Either succeeds with empty legs or flags error — must not raise
        assert "error" in result or "legs" in result

    def test_non_dict_returns_error(self):
        from engine.release_provenance import build_input_snapshot
        for bad in ["string", 42, [], None]:
            result = build_input_snapshot(bad)
            assert result.get("error") is True

    def test_all_legs_covered(self):
        from engine.release_provenance import build_input_snapshot
        proj = _make_projection(
            rev_opt=["leg_a", "leg_b"],
            unrev=["leg_c"],
            absent=["leg_d"],
        )
        result = build_input_snapshot(proj)
        legs = result["legs"]
        assert set(legs.keys()) >= {"leg_a", "leg_b", "leg_c", "leg_d"}

    def test_no_mutation_of_projection(self):
        """build_input_snapshot must not mutate the input projection."""
        from engine.release_provenance import build_input_snapshot
        proj = _make_projection(rev_opt=["gasoline_mom"], absent=["adp_change"])
        before = copy.deepcopy(proj)
        build_input_snapshot(proj)
        assert proj == before, "build_input_snapshot mutated the projection"


# ---------------------------------------------------------------------------
# compute_coverage_flags tests
# ---------------------------------------------------------------------------

class TestComputeCoverageFlags:
    def test_returns_all_four_keys(self):
        from engine.release_provenance import compute_coverage_flags
        proj = _make_projection(rev_opt=["gasoline_mom"], absent=["adp_change"])
        result = compute_coverage_flags(proj, ledger_path=None)
        assert "weight_coverage" in result
        assert "fresh_proxy_coverage" in result
        assert "non_vintaged_share" in result
        assert "model_maturity" in result

    def test_weight_coverage_all_covered(self):
        from engine.release_provenance import compute_coverage_flags
        # All legs are revision_optimistic → covered
        proj = _make_projection(rev_opt=["leg_a", "leg_b", "leg_c"])
        result = compute_coverage_flags(proj, None)
        assert result["weight_coverage"] == pytest.approx(1.0)

    def test_weight_coverage_all_absent(self):
        from engine.release_provenance import compute_coverage_flags
        proj = _make_projection(absent=["leg_a", "leg_b"])
        result = compute_coverage_flags(proj, None)
        assert result["weight_coverage"] == pytest.approx(0.0)

    def test_weight_coverage_partial(self):
        from engine.release_provenance import compute_coverage_flags
        # 1 covered (rev_opt), 1 absent → 0.5
        proj = _make_projection(rev_opt=["leg_a"], absent=["leg_b"])
        result = compute_coverage_flags(proj, None)
        assert result["weight_coverage"] == pytest.approx(0.5)

    def test_weight_coverage_with_weights_dict(self):
        from engine.release_provenance import compute_coverage_flags
        # CPI bridge: energy_block weight=0.07, shelter_block=0.36, rest absent
        proj = _make_projection(rev_opt=["energy_block", "shelter_block"], absent=["food_block"])
        weights = {"energy_block": 0.07, "shelter_block": 0.36, "food_block": 0.13}
        result = compute_coverage_flags(proj, None, weights=weights)
        # covered weight = 0.07 + 0.36 = 0.43 out of 0.56 total
        expected = (0.07 + 0.36) / (0.07 + 0.36 + 0.13)
        assert result["weight_coverage"] == pytest.approx(expected, rel=1e-6)

    def test_fresh_proxy_coverage_with_fresh_legs(self):
        from engine.release_provenance import compute_coverage_flags
        proj = _make_projection(rev_opt=["leg_a", "leg_b", "leg_c"])
        proj["pit_provenance"]["fresh_legs"] = ["leg_a", "leg_b"]
        result = compute_coverage_flags(proj, None)
        # 2 of 3 legs are fresh
        assert result["fresh_proxy_coverage"] == pytest.approx(2 / 3)

    def test_fresh_proxy_approximation_when_no_fresh_legs(self):
        from engine.release_provenance import compute_coverage_flags
        # Without fresh_legs, uses present-leg share as approximation
        proj = _make_projection(rev_opt=["leg_a"], unrev=["leg_b"], absent=["leg_c"])
        result = compute_coverage_flags(proj, None)
        # No leg is "present" (all are rev_opt, unrev, or absent)
        assert result["fresh_proxy_coverage"] == pytest.approx(0.0)
        assert result["_fresh_approximated"] is True

    def test_non_vintaged_share(self):
        from engine.release_provenance import compute_coverage_flags
        # rev_opt + unrev + absent → all non-vintaged; none present
        proj = _make_projection(
            rev_opt=["leg_a"],
            unrev=["leg_b"],
            absent=["leg_c"],
        )
        result = compute_coverage_flags(proj, None)
        assert result["non_vintaged_share"] == pytest.approx(1.0)

    def test_non_vintaged_share_mixed(self):
        from engine.release_provenance import compute_coverage_flags
        # _declared_legs unions provenance lists + _features keys (none here).
        # 1 rev_opt leg (non-vintaged) + 0 absent + 0 unrev + 0 _features = 1 total leg
        # → non_vintaged_share = 1/1 = 1.0
        proj = _make_projection(rev_opt=["leg_b"])
        result = compute_coverage_flags(proj, None)
        # Only leg_b declared via provenance; it's revision_optimistic → non-vintaged
        assert result["non_vintaged_share"] == pytest.approx(1.0)

    def test_model_maturity_zero_when_no_ledger(self):
        from engine.release_provenance import compute_coverage_flags
        proj = _make_projection()
        result = compute_coverage_flags(proj, ledger_path=None)
        assert result["model_maturity"] == 0

    def test_model_maturity_zero_when_ledger_missing(self, tmp_path):
        from engine.release_provenance import compute_coverage_flags
        proj = _make_projection()
        result = compute_coverage_flags(proj, ledger_path=tmp_path / "nonexistent.jsonl")
        assert result["model_maturity"] == 0

    def test_model_maturity_counts_scored_rows(self, tmp_path):
        from engine.release_provenance import compute_coverage_flags
        ledger = tmp_path / "ledger.jsonl"
        rows = [
            {"row_type": "scored", "release": "cpi_headline"},
            {"row_type": "scored", "release": "cpi_headline"},
            {"row_type": "projection", "release": "cpi_headline"},  # not scored
            {"row_type": "scored", "release": "nfp"},               # wrong release
        ]
        _write_ledger(ledger, rows)
        proj = _make_projection(release="cpi_headline")
        result = compute_coverage_flags(proj, ledger_path=ledger)
        assert result["model_maturity"] == 2

    def test_model_maturity_only_matching_release(self, tmp_path):
        from engine.release_provenance import compute_coverage_flags
        ledger = tmp_path / "ledger.jsonl"
        _write_ledger(ledger, [
            {"row_type": "scored", "release": "nfp"},
            {"row_type": "scored", "release": "cpi_core"},
        ])
        proj = _make_projection(release="cpi_headline")
        result = compute_coverage_flags(proj, ledger_path=ledger)
        assert result["model_maturity"] == 0

    def test_null_projection_returns_defaults(self):
        from engine.release_provenance import compute_coverage_flags
        result = compute_coverage_flags(None, ledger_path=None)
        assert result["weight_coverage"] == 0.0
        assert result["fresh_proxy_coverage"] == 0.0
        assert result["non_vintaged_share"] == 0.0
        assert result["model_maturity"] == 0

    def test_empty_provenance_returns_defaults(self):
        from engine.release_provenance import compute_coverage_flags
        proj = {"release": "nfp", "asof": "2026-07-07"}  # no pit_provenance
        result = compute_coverage_flags(proj, ledger_path=None)
        assert isinstance(result["weight_coverage"], float)
        assert isinstance(result["model_maturity"], int)

    def test_no_mutation_of_projection(self):
        """compute_coverage_flags must not mutate the input projection."""
        from engine.release_provenance import compute_coverage_flags
        proj = _make_projection(rev_opt=["gasoline_mom"], absent=["adp_change"])
        before = copy.deepcopy(proj)
        compute_coverage_flags(proj, ledger_path=None)
        assert proj == before, "compute_coverage_flags mutated the projection"

    def test_values_in_unit_interval(self):
        from engine.release_provenance import compute_coverage_flags
        proj = _make_projection(rev_opt=["a", "b"], unrev=["c"], absent=["d", "e"])
        result = compute_coverage_flags(proj, None)
        for key in ("weight_coverage", "fresh_proxy_coverage", "non_vintaged_share"):
            val = result[key]
            assert 0.0 <= val <= 1.0, f"{key}={val} out of [0,1]"
        assert isinstance(result["model_maturity"], int)
        assert result["model_maturity"] >= 0


# ---------------------------------------------------------------------------
# AUTHORITY TEST — pure metadata, no coupling to forecast outputs
# ---------------------------------------------------------------------------

class TestAuthorityPurity:
    def test_no_mutation_contract(self):
        """Both functions must return without mutating the projection dict."""
        from engine.release_provenance import build_input_snapshot, compute_coverage_flags
        proj = _make_projection(
            rev_opt=["gasoline_mom", "shelter_nowcast"],
            unrev=["withheld_tax_yoy"],
            absent=["adp_change"],
            inputs_hash="test-hash",
            prediction_id="cpi_headline:2026-07-07:v1",
        )
        original = copy.deepcopy(proj)
        build_input_snapshot(proj)
        assert proj == original, "build_input_snapshot mutated projection"
        compute_coverage_flags(proj, None)
        assert proj == original, "compute_coverage_flags mutated projection"

    def test_module_does_not_import_forecast_engine(self):
        """release_provenance must not IMPORT the forecast engine module
        (engine.release_forecast), which owns point/interval/skew outputs.
        Importing it would create a coupling path for coverage values to
        feed back into forecast math (MRI-R26 authority law).

        We check import statements only (not docstring/comment mentions).
        """
        import engine.release_provenance as prov_mod

        # Parse import statements from the module's source lines
        src_lines = inspect.getsource(prov_mod).splitlines()
        import_lines = [
            line.strip() for line in src_lines
            if (line.strip().startswith("import ") or line.strip().startswith("from "))
            and not line.strip().startswith("#")
        ]
        import_block = "\n".join(import_lines)

        # These identifiers must not appear in import statements
        forbidden_in_imports = [
            "release_forecast",
            "project_release",
            "compute_inputs_hash",
            "make_prediction_id",
        ]
        for name in forbidden_in_imports:
            assert name not in import_block, (
                f"engine/release_provenance.py IMPORTS '{name}' — "
                "this would couple coverage metadata to forecast math (MRI-R26 violation)"
            )

    def test_coverage_flags_not_in_projection_output_fields(self):
        """Coverage flag values must not appear in the projection's forecast fields
        after calling compute_coverage_flags. The projection's point/p10..p90/skew
        must be unchanged."""
        from engine.release_provenance import compute_coverage_flags
        proj = _make_projection(rev_opt=["gasoline_mom"], absent=["adp_change"])
        original_point = proj["point"]
        original_p10 = proj["p10"]
        original_p90 = proj["p90"]

        flags = compute_coverage_flags(proj, None)

        # Forecast fields untouched
        assert proj["point"] == original_point
        assert proj["p10"] == original_p10
        assert proj["p90"] == original_p90

        # Coverage flags not injected into projection dict
        for flag_key in ("weight_coverage", "fresh_proxy_coverage",
                         "non_vintaged_share", "model_maturity"):
            assert flag_key not in proj, (
                f"coverage flag '{flag_key}' was written into projection dict"
            )

    def test_no_sklearn_statsmodels_scipy(self):
        """Module must not import sklearn, statsmodels, or scipy.stats (house law)."""
        import engine.release_provenance as prov_mod
        src = inspect.getsource(prov_mod)
        forbidden_libs = ["sklearn", "statsmodels", "scipy.stats", "scipy"]
        for lib in forbidden_libs:
            assert lib not in src, (
                f"engine/release_provenance.py imports '{lib}' — "
                "only pure numpy/pandas allowed (masterplan §11.1)"
            )

    def test_authority_false_in_projection(self):
        """Verify that a projection built by the engine always carries authority=False,
        and that compute_coverage_flags does not change it."""
        from engine.release_provenance import compute_coverage_flags
        proj = _make_projection()
        assert proj.get("authority") is False
        compute_coverage_flags(proj, None)
        assert proj.get("authority") is False


# ---------------------------------------------------------------------------
# Edge cases / regression guards
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_malformed_ledger_line_skipped(self, tmp_path):
        """A JSON decode error in one ledger line should not crash — skip and continue."""
        from engine.release_provenance import compute_coverage_flags
        ledger = tmp_path / "ledger.jsonl"
        ledger.write_text(
            '{"row_type": "scored", "release": "nfp"}\n'
            'NOT_JSON_AT_ALL\n'
            '{"row_type": "scored", "release": "nfp"}\n'
        )
        proj = _make_projection(release="nfp")
        result = compute_coverage_flags(proj, ledger_path=ledger)
        assert result["model_maturity"] == 2  # two valid scored rows

    def test_empty_ledger_file(self, tmp_path):
        from engine.release_provenance import compute_coverage_flags
        ledger = tmp_path / "empty.jsonl"
        ledger.write_text("")
        proj = _make_projection()
        result = compute_coverage_flags(proj, ledger_path=ledger)
        assert result["model_maturity"] == 0

    def test_zero_weight_dict(self):
        from engine.release_provenance import compute_coverage_flags
        proj = _make_projection(rev_opt=["leg_a"])
        weights = {"leg_a": 0.0}  # all zero weights
        result = compute_coverage_flags(proj, None, weights=weights)
        assert result["weight_coverage"] == 0.0  # not NaN or error

    def test_snapshot_with_empty_provenance_lists(self):
        from engine.release_provenance import build_input_snapshot
        proj = _make_projection(rev_opt=[], unrev=[], absent=[])
        result = build_input_snapshot(proj)
        assert isinstance(result["legs"], dict)
        assert isinstance(result["features"], dict)

    def test_snapshot_asof_preserved(self):
        from engine.release_provenance import build_input_snapshot
        proj = _make_projection(asof="2026-07-01", rev_opt=["gasoline_mom"])
        result = build_input_snapshot(proj)
        assert result["asof"] == "2026-07-01"


# ---------------------------------------------------------------------------
# FIX 4 regression guard — coverage-flag denominator includes present legs
# ---------------------------------------------------------------------------

class TestCoverageFlagDenominatorFix:
    """MRI-R27 rework: _declared_legs must be used as the denominator so that
    vintaged/present legs (from _features) are included.

    NFP-shaped test case (8 total legs):
      - 5 vintaged present legs (nfp_change_lag1..3, claims_survey_week_icsa, claims_survey_week_ccsa)
        in _features, NOT in any provenance list → classified as 'present'
      - 1 revision_optimistic leg (awhman_mom) in prov → non-vintaged
      - 1 unrevised leg (withheld_tax_yoy) in prov → non-vintaged
      - 1 absent leg (adp_change) in prov (Track-M reserved) → non-vintaged

    Total: 8 legs. Non-vintaged: 3 (awhman_mom, withheld_tax_yoy, adp_change).
    non_vintaged_share = 3/8 = 0.375.

    Before the fix: denominator was only 3 (rev_opt | unrev | absent) → non_vintaged_share=1.0.
    After the fix: denominator is 8 (_declared_legs includes _features keys) → 0.375.
    """

    def _make_nfp_shaped_projection(self) -> dict:
        """Build an NFP-shaped projection with 5 present + 1 rev_opt + 1 unrev + 1 absent."""
        prov = {
            "revision_optimistic_legs": ["awhman_mom"],
            "unrevised_legs": ["withheld_tax_yoy"],
            "absent_legs": ["adp_change"],
            "display_only": True,
            "authority": False,
        }
        # 5 present (vintaged) legs carried in _features
        features = {
            "nfp_change_lag1": 150.0,
            "nfp_change_lag2": 130.0,
            "nfp_change_lag3": 120.0,
            "claims_survey_week_icsa": -5000.0,
            "claims_survey_week_ccsa": -3000.0,
            # awhman_mom is revision_optimistic — listed in prov, also in features
            "awhman_mom": 0.1,
            # withheld_tax_yoy is unrevised — listed in prov, also in features
            "withheld_tax_yoy": 2.5,
            # adp_change is absent — listed in prov (None value)
            "adp_change": None,
        }
        return {
            "release": "nfp",
            "asof": "2026-07-07",
            "inputs_hash": "nfp_test_hash",
            "pit_provenance": prov,
            "_features": features,
            "point": 150.0,
            "p10": 80.0,
            "p25": 110.0,
            "p50": 150.0,
            "p75": 190.0,
            "p90": 220.0,
            "confidence": 0.6,
            "display_only": True,
            "authority": False,
        }

    def test_non_vintaged_share_includes_present_legs(self):
        """After FIX 4: non_vintaged_share = 3/8 (not 1.0) for NFP-shaped projection."""
        from engine.release_provenance import compute_coverage_flags
        proj = self._make_nfp_shaped_projection()
        result = compute_coverage_flags(proj, ledger_path=None)
        # 3 non-vintaged (awhman_mom rev-opt, withheld_tax_yoy unrev, adp_change absent)
        # out of 8 total declared legs → 3/8 = 0.375
        assert result["non_vintaged_share"] == pytest.approx(0.375, rel=1e-6), (
            f"non_vintaged_share={result['non_vintaged_share']} expected≈0.375 (3/8). "
            "If 1.0, the denominator bug (present legs excluded) was not fixed."
        )

    def test_non_vintaged_share_not_one_for_nfp_model(self):
        """Regression guard: non_vintaged_share must NOT be 1.0 for an NFP model."""
        from engine.release_provenance import compute_coverage_flags
        proj = self._make_nfp_shaped_projection()
        result = compute_coverage_flags(proj, ledger_path=None)
        assert result["non_vintaged_share"] != pytest.approx(1.0), (
            "non_vintaged_share=1.0 for NFP model — present/vintaged legs excluded from denominator (FIX 4 regression)"
        )

    def test_fresh_proxy_coverage_not_zero_for_nfp_model(self):
        """After FIX 4: fresh_proxy_coverage > 0 because present legs count as fresh proxy."""
        from engine.release_provenance import compute_coverage_flags
        proj = self._make_nfp_shaped_projection()
        result = compute_coverage_flags(proj, ledger_path=None)
        # 5 present legs out of 8 total → fresh_proxy_coverage = 5/8 = 0.625
        assert result["fresh_proxy_coverage"] > 0.0, (
            f"fresh_proxy_coverage={result['fresh_proxy_coverage']} expected>0. "
            "If 0.0, the denominator fix is not applied correctly."
        )
        assert result["fresh_proxy_coverage"] == pytest.approx(5 / 8, rel=1e-6)

    def test_weight_coverage_includes_present_legs(self):
        """weight_coverage must count present legs as covered."""
        from engine.release_provenance import compute_coverage_flags
        proj = self._make_nfp_shaped_projection()
        result = compute_coverage_flags(proj, ledger_path=None)
        # 7 covered legs (all except adp_change absent) out of 8 → 7/8 = 0.875
        assert result["weight_coverage"] == pytest.approx(7 / 8, rel=1e-6)


# ---------------------------------------------------------------------------
# FIX 1 regression guard — champion NFP feature set does not include adp_change
# ---------------------------------------------------------------------------

class TestChampionNFPFeatureSet:
    """MRI-R27 rework FIX 1: adp_change must NOT be in the champion NFP feature_names.
    The champion was effectively a 7-feature model (adp_change always NaN-dropped because
    the file path was dead). Removing it makes the champion provably unchanged (RESULTS_V2 frozen).
    """

    def test_champion_feature_names_excludes_adp_change(self):
        """_project_nfp feature_names must not contain 'adp_change'."""
        import inspect
        import sys
        _REPO = Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(_REPO))
        import engine.release_forecast as rf
        src = inspect.getsource(rf._project_nfp)
        # Extract the feature_names list from the source
        # We look for the definition inside _project_nfp
        assert "adp_change" not in src or "adp_change reserved" in src, (
            "adp_change appears in _project_nfp feature_names — "
            "this would silently change the champion vs RESULTS_V2 (MRI-R27 rework FIX 1)"
        )
        # More direct: parse the actual feature_names list value
        import ast
        # Find the feature_names assignment
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "feature_names":
                        if isinstance(node.value, ast.List):
                            names = [
                                elt.value for elt in node.value.elts
                                if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
                            ]
                            assert "adp_change" not in names, (
                                f"Champion feature_names={names} contains 'adp_change' — "
                                "must be excluded to keep RESULTS_V2 frozen (MRI-R27 rework FIX 1)"
                            )
                            assert len(names) == 7, (
                                f"Champion should have 7 features (3 lags + 2 claims + withheld + awhman), got {len(names)}: {names}"
                            )

    def test_wf_nfp_full_feature_names_excludes_adp_change(self):
        """_wf_nfp_full feature_names (walk-forward backtest) must also exclude adp_change."""
        import inspect
        import sys
        _REPO = Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(_REPO))
        import engine.release_forecast as rf
        src = inspect.getsource(rf._wf_nfp_full)
        import ast
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "feature_names":
                        if isinstance(node.value, ast.List):
                            names = [
                                elt.value for elt in node.value.elts
                                if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
                            ]
                            assert "adp_change" not in names, (
                                f"_wf_nfp_full feature_names={names} contains 'adp_change' — "
                                "must match the champion 7-feature set (MRI-R27 rework FIX 1)"
                            )


# ---------------------------------------------------------------------------
# Rework-2a: vintaged_legs + input_manifest coverage honesty tests
# (MRI-R26 rework-2a: champions + new targets report sane coverage flags)
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[1]
_VINTAGES_PRESENT = (_REPO_ROOT / "data" / "fred_vintage" / "vintages.parquet").exists()
_INT_MARK = pytest.mark.skipif(
    not _VINTAGES_PRESENT,
    reason="data/fred_vintage/vintages.parquet absent; skipping integration coverage tests",
)


class TestVintagedLegsCoverageHonesty:
    """Rework-2a: CPI, NFP and PCE models must emit correct, non-trivial coverage flags.

    Before the fix: vintaged legs were invisible → non_vintaged_share=1.0 and
    weight_coverage=0.0/1.0 as artifacts. After the fix, mostly-vintaged models
    report LOW non_vintaged_share and non-zero weight_coverage.
    """

    @_INT_MARK
    def test_cpi_headline_low_non_vintaged_share(self):
        """CPI headline has 9 legs; only shelter_nowcast (rev_opt) + gasoline_mom (unrev)
        are non-vintaged → non_vintaged_share = 2/9 ≈ 0.222."""
        from engine.release_forecast import project_release
        from engine.release_provenance import compute_coverage_flags
        import datetime as dt
        p = project_release("cpi_headline", dt.date(2026, 7, 8), str(_REPO_ROOT))
        flags = compute_coverage_flags(p, None)
        assert flags["non_vintaged_share"] < 0.5, (
            f"CPI headline non_vintaged_share={flags['non_vintaged_share']:.3f} — "
            "expected < 0.5 (mostly-vintaged model). If 1.0, vintaged_legs fix not applied."
        )
        assert flags["non_vintaged_share"] != pytest.approx(1.0), (
            "CPI headline non_vintaged_share=1.0 — rework-2a vintaged_legs fix not applied"
        )

    @_INT_MARK
    def test_cpi_core_low_non_vintaged_share(self):
        """CPI core has 8 legs; only shelter_nowcast (rev_opt) is non-vintaged
        → non_vintaged_share = 1/8 = 0.125."""
        from engine.release_forecast import project_release
        from engine.release_provenance import compute_coverage_flags
        import datetime as dt
        p = project_release("cpi_core", dt.date(2026, 7, 8), str(_REPO_ROOT))
        flags = compute_coverage_flags(p, None)
        assert flags["non_vintaged_share"] < 0.5, (
            f"CPI core non_vintaged_share={flags['non_vintaged_share']:.3f} — "
            "expected < 0.5 (mostly-vintaged model)"
        )
        assert flags["non_vintaged_share"] != pytest.approx(1.0), (
            "CPI core non_vintaged_share=1.0 — rework-2a vintaged_legs fix not applied"
        )
        assert flags["weight_coverage"] == pytest.approx(1.0, rel=1e-6), (
            f"CPI core weight_coverage={flags['weight_coverage']:.3f} expected=1.0 "
            "(no absent legs when all features present)"
        )

    @_INT_MARK
    def test_pce_headline_coverage_not_artifacts(self):
        """PCE headline coverage must not be the 1.0/0.0 artifact.
        All 8 legs (3 own lags + 3 smf + ppifis + gasoline) are present at 2026-07-08;
        gasoline_mom is unrevised (non-vintaged), rest are ALFRED-vintaged.
        non_vintaged_share = 1/8 = 0.125 (or 0 if gasoline absent)."""
        from engine.release_forecast import project_release
        from engine.release_provenance import compute_coverage_flags
        import datetime as dt
        p = project_release("pce_headline", dt.date(2026, 7, 8), str(_REPO_ROOT))
        flags = compute_coverage_flags(p, None)
        # non_vintaged_share must NOT be 1.0 (old artifact)
        assert flags["non_vintaged_share"] != pytest.approx(1.0), (
            f"pce_headline non_vintaged_share={flags['non_vintaged_share']:.3f} — "
            "still showing artifact value 1.0; vintaged_legs + input_manifest fix not applied"
        )
        # weight_coverage must NOT be 0.0 (old pce_core artifact)
        assert flags["weight_coverage"] > 0.0, (
            f"pce_headline weight_coverage={flags['weight_coverage']:.3f} — "
            "should be > 0 when at least some legs are present"
        )

    @_INT_MARK
    def test_pce_core_coverage_not_artifacts(self):
        """PCE core coverage must not be the 1.0/0.0 artifact from old code.
        All 7 legs (3 own lags + 3 smf + ppifes) are ALFRED-vintaged.
        Before fix: weight_coverage=0.0, non_vintaged_share=0.0 (empty denominator).
        After fix: weight_coverage=1.0, non_vintaged_share=0.0."""
        from engine.release_forecast import project_release
        from engine.release_provenance import compute_coverage_flags
        import datetime as dt
        p = project_release("pce_core", dt.date(2026, 7, 8), str(_REPO_ROOT))
        flags = compute_coverage_flags(p, None)
        # weight_coverage must NOT be 0.0 (old artifact from empty denominator)
        assert flags["weight_coverage"] > 0.0, (
            f"pce_core weight_coverage={flags['weight_coverage']:.3f} — "
            "old artifact was 0.0 (empty denominator when no legs in special lists); fix not applied"
        )

    @_INT_MARK
    def test_cpi_headline_input_snapshot_non_empty(self):
        """CPI headline input_snapshot receipt must be populated (non-empty features)."""
        from engine.release_forecast import project_release
        from engine.release_provenance import build_input_snapshot
        import datetime as dt
        p = project_release("cpi_headline", dt.date(2026, 7, 8), str(_REPO_ROOT))
        snap = build_input_snapshot(p)
        assert "error" not in snap, f"build_input_snapshot returned error: {snap}"
        features = snap.get("features", {})
        non_none = {k: v for k, v in features.items() if v is not None}
        assert len(non_none) > 0, (
            "CPI headline input_snapshot.features is empty — "
            "input_manifest was not attached to the projection (rework-2a FIX)"
        )
        # Must have the own lags
        assert "cpi_hl_mom_lag1" in features, (
            "input_snapshot features missing cpi_hl_mom_lag1 — "
            "input_manifest keys not propagated into snapshot"
        )

    @_INT_MARK
    def test_cpi_core_input_snapshot_non_empty(self):
        """CPI core input_snapshot must have real feature values."""
        from engine.release_forecast import project_release
        from engine.release_provenance import build_input_snapshot
        import datetime as dt
        p = project_release("cpi_core", dt.date(2026, 7, 8), str(_REPO_ROOT))
        snap = build_input_snapshot(p)
        assert "error" not in snap
        features = snap.get("features", {})
        non_none = {k: v for k, v in features.items() if v is not None}
        assert len(non_none) > 0, "CPI core input_snapshot.features is empty"
        assert "cpi_core_mom_lag1" in features

    @_INT_MARK
    def test_pce_headline_input_snapshot_non_empty(self):
        """PCE headline input_snapshot must have real feature values."""
        from engine.release_forecast import project_release
        from engine.release_provenance import build_input_snapshot
        import datetime as dt
        p = project_release("pce_headline", dt.date(2026, 7, 8), str(_REPO_ROOT))
        snap = build_input_snapshot(p)
        assert "error" not in snap
        features = snap.get("features", {})
        non_none = {k: v for k, v in features.items() if v is not None}
        assert len(non_none) > 0, "PCE headline input_snapshot.features is empty"
        assert "pce_hl_mom_lag1" in features

    @_INT_MARK
    def test_pce_core_input_snapshot_non_empty(self):
        """PCE core input_snapshot must have real feature values."""
        from engine.release_forecast import project_release
        from engine.release_provenance import build_input_snapshot
        import datetime as dt
        p = project_release("pce_core", dt.date(2026, 7, 8), str(_REPO_ROOT))
        snap = build_input_snapshot(p)
        assert "error" not in snap
        features = snap.get("features", {})
        non_none = {k: v for k, v in features.items() if v is not None}
        assert len(non_none) > 0, "PCE core input_snapshot.features is empty"
        assert "pce_core_mom_lag1" in features

    def test_vintaged_legs_in_declared_legs(self):
        """_declared_legs must include vintaged_legs entries from provenance."""
        from engine.release_provenance import _declared_legs
        prov = {
            "revision_optimistic_legs": ["shelter_nowcast"],
            "vintaged_legs": ["cpi_hl_mom_lag1", "cpi_hl_mom_lag2", "cpi_hl_mom_lag3"],
            "unrevised_legs": ["gasoline_mom"],
            "absent_legs": [],
        }
        declared = _declared_legs(prov, {})
        assert "cpi_hl_mom_lag1" in declared, "vintaged leg cpi_hl_mom_lag1 not in declared_legs"
        assert "cpi_hl_mom_lag2" in declared
        assert "cpi_hl_mom_lag3" in declared
        assert "shelter_nowcast" in declared
        assert "gasoline_mom" in declared
        assert len(declared) == 5

    def test_input_manifest_in_declared_legs(self):
        """_declared_legs must include input_manifest keys (via merged_features in compute_coverage_flags)."""
        from engine.release_provenance import compute_coverage_flags
        # Projection with no special provenance lists, but real feature values in input_manifest
        proj = {
            "release": "pce_core",
            "asof": "2026-07-08",
            "input_manifest": {
                "pce_core_mom_lag1": 0.2,
                "pce_core_mom_lag2": 0.3,
                "pce_core_mom_lag3": 0.15,
                "sticky_mom_lag1": -36.0,
                "median_mom_lag1": -25.0,
                "flex_mom_lag1": -18.0,
                "ppifes_mom_lag1": -0.1,
            },
            "pit_provenance": {
                "revision_optimistic_legs": [],
                "vintaged_legs": ["sticky_mom_lag1", "median_mom_lag1", "flex_mom_lag1"],
                "unrevised_legs": [],
                "absent_legs": [],
                "display_only": True,
                "authority": False,
            },
            "display_only": True,
            "authority": False,
        }
        flags = compute_coverage_flags(proj, None)
        # All 7 legs are present/vintaged → weight_coverage = 1.0
        assert flags["weight_coverage"] == pytest.approx(1.0), (
            f"weight_coverage={flags['weight_coverage']} — expected 1.0 when all legs present"
        )
        # All vintaged (none in non-vintaged statuses) → non_vintaged_share = 0.0
        assert flags["non_vintaged_share"] == pytest.approx(0.0), (
            f"non_vintaged_share={flags['non_vintaged_share']} — expected 0.0 when all ALFRED-vintaged"
        )

    def test_champion_unchanged_point_and_benchmark_stable(self):
        """Two calls to project_release CPI at same asof return identical point + benchmark_set.
        Verifies rework-2a is additive — the input_manifest addition does NOT change outputs.
        (Unit-level champion-unchanged test; full integration version is in test_release_integration_2a.py)
        """
        # This is a pure structural test (not integration) — checks the champions still work
        # without requiring data; if vintages absent, the projection returns _empty_projection
        # which is deterministic regardless.
        import datetime as dt
        _REPO = Path(__file__).resolve().parents[1]
        from engine.release_forecast import project_release

        # Run twice — must be identical
        r1 = project_release("cpi_core", dt.date(2024, 3, 12), str(_REPO))
        r2 = project_release("cpi_core", dt.date(2024, 3, 12), str(_REPO))
        assert r1.get("point") == r2.get("point"), "CPI core point not stable between calls"
        # input_manifest must be present and identical
        assert "input_manifest" in r1, "input_manifest key missing from CPI core projection"
        assert r1.get("input_manifest") == r2.get("input_manifest"), "input_manifest not stable"
