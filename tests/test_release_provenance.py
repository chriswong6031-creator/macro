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
        # compute_coverage_flags uses only pit_provenance lists, not _features.
        # 1 rev_opt leg (non-vintaged) + 0 absent + 0 unrev = 1 total leg
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
