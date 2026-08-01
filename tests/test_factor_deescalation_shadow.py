"""tests/test_factor_deescalation_shadow.py

Tests for:
  scripts/build_factor_deescalation_shadow.py  — RUL-NW6 dark scaffold
  scripts/check_factor_boundaries.py           — RUL-NW9/NW11 boundary guard

Test inventory
--------------
Shadow scaffold (build_factor_deescalation_shadow):
  1. refusal_path_writes_nothing
     No GATE-PASSED verdict file → script returns dark status, writes nothing.
  2. refusal_path_no_verdict_dir
     Verdict directory absent → still writes nothing (does not raise).
  3. gate_passed_verdict_exact_match
     Verdict file with exactly '**Verdict:** GATE-PASSED' → gate_ref returned.
  4. gate_passed_verdict_partial_match_ignored
     Verdict file with 'GATE-PASSED but not yet ratified' → NOT a match.
  5. gate_passed_writes_rows_with_correct_schema
     GATE-PASSED verdict + synthetic rows → rows written, schema checked.
  6. idempotence_on_rerun
     Same-day re-run does not duplicate rows.
  7. missing_required_fields_skipped
     Row missing a §11 field is skipped, others written.
  8. forbidden_field_names_rejected
     Row containing 'rank', 'score', or 'recommendation' is skipped.

Boundary guard (check_factor_boundaries):
  9.  check_a_article2_write_detected
      Factor module with 'alert_triage' reference → violation detected.
 10.  check_a_board_ordering_detected
      Factor module with 'board_ordering' reference → violation detected.
 11.  check_a_top_setups_detected
      Factor module with 'top_setups' reference → violation detected.
 12.  check_a_push_floor_detected
      Factor module with 'push_floor' reference → violation detected.
 13.  check_a_attention_queue_detected
      Factor module with 'attention_queue' reference → violation detected.
 14.  check_a_clean_tree_passes
      Clean factor module with no Article-2 references → no violations.
 15.  check_b_allowed_actions_outside_allowlist_detected
      Non-allowlisted file references 'allowed_actions' → violation detected.
 16.  check_b_allowlisted_file_clean
      State builder (allowlisted) references 'allowed_actions' → no violation.
 17.  check_b_tests_prefix_allowlisted
      File with 'tests/' prefix is allowlisted → no violation.
 18.  check_c_rank_field_detected
      State builder emits '"rank":' → violation detected.
 19.  check_c_score_field_detected
      Shadow script emits '"score":' → violation detected.
 20.  check_c_recommendation_detected
      State builder emits '"recommendation":' → violation detected.
 21.  check_c_clean_passes
      State builder with no forbidden fields → no violations.
 22.  selftest_passes
      --selftest flag exits 0 against the real repo.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Repo root
REPO_ROOT = Path(__file__).resolve().parent.parent

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.build_factor_deescalation_shadow import (  # noqa: E402
    _GATE_PASSED_PATTERN,
    _ROW_FIELDS,
    _SHADOW_FIRINGS_REL,
    _VERDICT_FILES,
    _find_gate_passed_verdict,
    _load_existing_keys,
    _validate_row,
    build_factor_deescalation_shadow,
)
from scripts.check_factor_boundaries import (  # noqa: E402
    _check_a,
    _check_b,
    _check_c,
    main as boundaries_main,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_verdict_file(tmp_path: Path, filename: str, verdict_line: str) -> None:
    """Write a verdict file containing the given line."""
    research_dir = tmp_path / "research" / "factor_intelligence"
    research_dir.mkdir(parents=True, exist_ok=True)
    (research_dir / filename).write_text(
        f"# Test verdict\n\n{verdict_line}\n\nSome other content.\n",
        encoding="utf-8",
    )


def _make_valid_row(
    as_of: str = "2026-07-06",
    ticker: str = "AAPL",
    primitive: str = "alibi_share_20d",
    gate_reference: str = "research/factor_intelligence/H2_VERDICT.md",
) -> dict:
    """Return a valid §11 schema row."""
    return {
        "ticker": ticker,
        "as_of": as_of,
        "primitive": primitive,
        "proposed_action": "display_chip_only",
        "original_surface": "data/neuralweb/factor_intelligence_state.json",
        "original_verdict": "note",
        "proposed_verdict": "display_suppressed",
        "falsifier": "direction=-1; hit = name underperforms SPY at horizon_d=21",
        "horizon_d": 21,
        "gate_reference": gate_reference,
    }


# ===========================================================================
# Shadow scaffold tests
# ===========================================================================


class TestShadowRefusal:
    """Tests for the dark/no-op path (no GATE-PASSED verdict)."""

    def test_refusal_path_writes_nothing(self, tmp_path: Path) -> None:
        """No verdict file → writes nothing, returns dark status."""
        result = build_factor_deescalation_shadow(root=tmp_path)
        assert result["status"] == "dark"
        assert result["gate_passed"] is False
        assert result["gate_reference"] is None
        assert result["rows_written"] == 0
        # Shadow ledger must not exist
        shadow_path = tmp_path / _SHADOW_FIRINGS_REL
        assert not shadow_path.exists()

    def test_refusal_path_no_verdict_dir(self, tmp_path: Path) -> None:
        """No research/ directory at all → still dark, no crash."""
        result = build_factor_deescalation_shadow(root=tmp_path)
        assert result["status"] == "dark"
        assert result["rows_written"] == 0

    def test_verdict_file_partial_match_ignored(self, tmp_path: Path) -> None:
        """Verdict text like 'GATE-PASSED but not yet ratified' is NOT a match."""
        # The pattern requires '**Verdict:** GATE-PASSED' literally
        _make_verdict_file(tmp_path, "H2_VERDICT.md", "GATE-PASSED but not yet ratified")
        result = build_factor_deescalation_shadow(root=tmp_path)
        assert result["status"] == "dark"
        assert result["rows_written"] == 0

    def test_verdict_file_wrong_key_ignored(self, tmp_path: Path) -> None:
        """Verdict file that says GATE-FAIL is not a match."""
        _make_verdict_file(tmp_path, "H2_VERDICT.md", "**Verdict:** GATE-FAIL")
        result = build_factor_deescalation_shadow(root=tmp_path)
        assert result["status"] == "dark"

    def test_verdict_file_name_mismatch_ignored(self, tmp_path: Path) -> None:
        """Verdict file named H3_VERDICT.md (not in the checked list) is ignored."""
        _make_verdict_file(tmp_path, "H3_VERDICT.md", "**Verdict:** GATE-PASSED")
        result = build_factor_deescalation_shadow(root=tmp_path)
        assert result["status"] == "dark"


class TestGatePassedPath:
    """Tests for the active path (GATE-PASSED verdict present + synthetic rows)."""

    def _setup_gate_passed(self, tmp_path: Path, filename: str = "H2_VERDICT.md") -> str:
        """Write a valid GATE-PASSED verdict file; return the gate_reference string."""
        _make_verdict_file(tmp_path, filename, _GATE_PASSED_PATTERN)
        return f"research/factor_intelligence/{filename}"

    def test_gate_passed_verdict_exact_match(self, tmp_path: Path) -> None:
        """Verdict file with exact pattern → gate_ref returned."""
        self._setup_gate_passed(tmp_path)
        gate_ref = _find_gate_passed_verdict(tmp_path)
        assert gate_ref is not None
        assert "H2_VERDICT.md" in gate_ref

    def test_gate_passed_writes_rows_with_correct_schema(self, tmp_path: Path) -> None:
        """GATE-PASSED verdict + synthetic rows → rows written with exact §11 schema."""
        gate_ref = self._setup_gate_passed(tmp_path)
        row = _make_valid_row(gate_reference=gate_ref)
        result = build_factor_deescalation_shadow(
            root=tmp_path,
            as_of_date="2026-07-06",
            _synthetic_rows=[row],
        )
        assert result["gate_passed"] is True
        assert result["rows_written"] == 1
        shadow_path = tmp_path / _SHADOW_FIRINGS_REL
        assert shadow_path.exists()
        written = json.loads(shadow_path.read_text())
        # Verify all required §11 fields are present
        for field in _ROW_FIELDS:
            assert field in written, f"Missing required §11 field: {field}"
        # No forbidden fields
        for forbidden in ("rank", "score", "recommendation"):
            assert forbidden not in written

    def test_idempotence_on_rerun(self, tmp_path: Path) -> None:
        """Same (as_of, ticker, primitive) composite key is not duplicated on rerun."""
        gate_ref = self._setup_gate_passed(tmp_path)
        row = _make_valid_row(gate_reference=gate_ref)

        # First run
        r1 = build_factor_deescalation_shadow(
            root=tmp_path, as_of_date="2026-07-06", _synthetic_rows=[row]
        )
        assert r1["rows_written"] == 1

        # Second run with same row
        r2 = build_factor_deescalation_shadow(
            root=tmp_path, as_of_date="2026-07-06", _synthetic_rows=[row]
        )
        assert r2["rows_written"] == 0
        assert r2["rows_skipped"] == 1

        # Ledger should have exactly one row
        shadow_path = tmp_path / _SHADOW_FIRINGS_REL
        rows = [l for l in shadow_path.read_text().splitlines() if l.strip()]
        assert len(rows) == 1

    def test_missing_required_fields_skipped(self, tmp_path: Path) -> None:
        """Row missing a §11 required field is skipped without crashing."""
        gate_ref = self._setup_gate_passed(tmp_path)
        valid_row = _make_valid_row(gate_reference=gate_ref)
        bad_row = {k: v for k, v in valid_row.items() if k != "falsifier"}  # missing 'falsifier'

        result = build_factor_deescalation_shadow(
            root=tmp_path, as_of_date="2026-07-06", _synthetic_rows=[bad_row]
        )
        assert result["rows_skipped"] >= 1
        assert result["rows_written"] == 0
        # Shadow file must not be created (skipped rows write nothing)
        shadow_path = tmp_path / _SHADOW_FIRINGS_REL
        assert not shadow_path.exists()

    def test_forbidden_field_names_rejected(self, tmp_path: Path) -> None:
        """Row with 'rank' or 'score' or 'recommendation' key is skipped."""
        gate_ref = self._setup_gate_passed(tmp_path)

        for bad_field in ("rank", "score", "recommendation"):
            bad_row = dict(_make_valid_row(gate_reference=gate_ref))
            bad_row[bad_field] = 1
            with pytest.raises(ValueError, match="forbidden"):
                _validate_row(bad_row)

    def test_multiple_rows_with_different_keys(self, tmp_path: Path) -> None:
        """Multiple rows with different (as_of, ticker, primitive) all written."""
        gate_ref = self._setup_gate_passed(tmp_path)
        rows = [
            _make_valid_row("2026-07-06", "AAPL", "alibi_share_20d", gate_ref),
            _make_valid_row("2026-07-06", "MSFT", "alibi_share_20d", gate_ref),
            _make_valid_row("2026-07-05", "AAPL", "alibi_share_20d", gate_ref),
        ]
        result = build_factor_deescalation_shadow(
            root=tmp_path, as_of_date="2026-07-06", _synthetic_rows=rows
        )
        assert result["rows_written"] == 3

    def test_h4_verdict_also_activates(self, tmp_path: Path) -> None:
        """H4_VERDICT.md with GATE-PASSED also activates the scaffold."""
        self._setup_gate_passed(tmp_path, "H4_VERDICT.md")
        gate_ref = _find_gate_passed_verdict(tmp_path)
        assert gate_ref is not None
        assert "H4_VERDICT.md" in gate_ref


class TestRowValidation:
    """Unit tests for _validate_row."""

    def test_valid_row_passes(self) -> None:
        row = _make_valid_row()
        _validate_row(row)  # should not raise

    def test_missing_ticker_raises(self) -> None:
        row = {k: v for k, v in _make_valid_row().items() if k != "ticker"}
        with pytest.raises(ValueError, match="ticker"):
            _validate_row(row)

    def test_missing_horizon_d_raises(self) -> None:
        row = {k: v for k, v in _make_valid_row().items() if k != "horizon_d"}
        with pytest.raises(ValueError, match="horizon_d"):
            _validate_row(row)

    def test_rank_field_raises(self) -> None:
        row = dict(_make_valid_row())
        row["rank"] = 1
        with pytest.raises(ValueError, match="forbidden"):
            _validate_row(row)

    def test_score_field_raises(self) -> None:
        row = dict(_make_valid_row())
        row["score"] = 0.9
        with pytest.raises(ValueError, match="forbidden"):
            _validate_row(row)

    def test_recommendation_field_raises(self) -> None:
        row = dict(_make_valid_row())
        row["recommendation"] = "buy"
        with pytest.raises(ValueError, match="forbidden"):
            _validate_row(row)


class TestLoadExistingKeys:
    """Unit tests for _load_existing_keys."""

    def test_nonexistent_file_returns_empty(self, tmp_path: Path) -> None:
        keys = _load_existing_keys(tmp_path / "nonexistent.jsonl")
        assert keys == set()

    def test_loads_keys_correctly(self, tmp_path: Path) -> None:
        p = tmp_path / "firings.jsonl"
        rows = [
            {"as_of": "2026-07-06", "ticker": "AAPL", "primitive": "alibi_share_20d"},
            {"as_of": "2026-07-05", "ticker": "MSFT", "primitive": "alpha_z_house"},
        ]
        p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
        keys = _load_existing_keys(p)
        assert ("2026-07-06", "AAPL", "alibi_share_20d") in keys
        assert ("2026-07-05", "MSFT", "alpha_z_house") in keys

    def test_malformed_lines_skipped(self, tmp_path: Path) -> None:
        p = tmp_path / "firings.jsonl"
        p.write_text("not json\n{}\n")
        keys = _load_existing_keys(p)
        assert len(keys) == 0


# ===========================================================================
# Boundary guard tests
# ===========================================================================


class TestCheckA:
    """Check (a): Article-2 write guard on factor-module files."""

    def test_alert_triage_detected(self) -> None:
        synthetic = {
            "scripts/build_factor_panel.py": "path = 'data/alert_triage/foo.json'\n",
        }
        viols = _check_a(REPO_ROOT, extra_files=synthetic)
        assert any(v.check == "a" and "alert_triage" in v.pattern for v in viols)

    def test_board_ordering_detected(self) -> None:
        synthetic = {
            "scripts/build_factor_intelligence_state.py": (
                "output = 'data/board_ordering/us_standouts.json'\n"
            ),
        }
        viols = _check_a(REPO_ROOT, extra_files=synthetic)
        assert any(v.check == "a" and "board_ordering" in v.pattern for v in viols)

    def test_top_setups_detected(self) -> None:
        synthetic = {
            "engine/neuralweb/factor_contradictions.py": (
                "output_dir = 'data/top_setups/'\n"
            ),
        }
        viols = _check_a(REPO_ROOT, extra_files=synthetic)
        assert any(v.check == "a" and "top_setups" in v.pattern for v in viols)

    def test_push_floor_detected(self) -> None:
        synthetic = {
            "scripts/build_factor_deescalation_shadow.py": (
                "PUSH_FLOOR_PATH = 'data/push_floor/gate.json'\n"
            ),
        }
        viols = _check_a(REPO_ROOT, extra_files=synthetic)
        assert any(v.check == "a" and "push_floor" in v.pattern for v in viols)

    def test_attention_queue_detected(self) -> None:
        synthetic = {
            "scripts/build_factor_panel.py": "queue = 'data/attention_queue/items.json'\n",
        }
        viols = _check_a(REPO_ROOT, extra_files=synthetic)
        assert any(v.check == "a" and "attention_queue" in v.pattern for v in viols)

    def test_clean_factor_module_no_violation(self) -> None:
        synthetic = {
            "scripts/build_factor_panel.py": (
                "# clean factor module\n"
                "output = 'data/factordata/panel/2026-07/panel.parquet'\n"
            ),
        }
        viols = _check_a(REPO_ROOT, extra_files=synthetic)
        assert len(viols) == 0

    def test_non_factor_module_not_checked_in_a(self) -> None:
        """Check-a only scans the listed factor modules — other files are not checked."""
        synthetic = {
            "scripts/some_other_script.py": "path = 'data/alert_triage/foo.json'\n",
        }
        viols = _check_a(REPO_ROOT, extra_files=synthetic)
        # some_other_script.py is not in _FACTOR_MODULES — should produce no check-a violation
        # (check-b would catch allowed_actions but not check-a)
        assert all(v.check != "a" for v in viols)


class TestCheckB:
    """Check (b): allowed_actions read guard."""

    def test_outside_allowlist_detected(self) -> None:
        synthetic = {
            "engine/alert_triage.py": "if state['allowed_actions']['may_rank']:\n    pass\n",
        }
        viols = _check_b(REPO_ROOT, extra_files=synthetic)
        assert any(v.check == "b" and "alert_triage" in v.module for v in viols)

    def test_engine_world_state_not_allowlisted(self) -> None:
        """engine/neuralweb/world_state.py is NOT in the allowlist."""
        synthetic = {
            "engine/neuralweb/world_state.py": "x = state['allowed_actions']\n",
        }
        viols = _check_b(REPO_ROOT, extra_files=synthetic)
        assert any(v.check == "b" for v in viols)

    def test_state_builder_allowlisted(self) -> None:
        synthetic = {
            "scripts/build_factor_intelligence_state.py": (
                "def _build_allowed_actions():\n"
                "    return {'may_rank': False}\n"
                "# allowed_actions block builder\n"
            ),
        }
        viols = _check_b(REPO_ROOT, extra_files=synthetic)
        assert not any(v.check == "b" for v in viols)

    def test_admin_neural_web_allowlisted(self) -> None:
        synthetic = {
            "admin/neural_web.py": "aa = state.get('allowed_actions', {})\n",
        }
        viols = _check_b(REPO_ROOT, extra_files=synthetic)
        assert not any(v.check == "b" for v in viols)

    def test_tests_prefix_allowlisted(self) -> None:
        synthetic = {
            "tests/test_factor_boundaries.py": "assert 'allowed_actions' in state\n",
        }
        viols = _check_b(REPO_ROOT, extra_files=synthetic)
        assert not any(v.check == "b" for v in viols)

    def test_cortex_allowlisted(self) -> None:
        synthetic = {
            "engine/neuralweb/cortex.py": "aa = payload.get('allowed_actions')\n",
        }
        viols = _check_b(REPO_ROOT, extra_files=synthetic)
        assert not any(v.check == "b" for v in viols)

    def test_sector_contract_validator_allowlisted_for_enforcement(self) -> None:
        synthetic = {
            "engine/sector_intelligence/contracts.py": (
                "actions = document.get('allowed_actions')\n"
            ),
        }
        viols = _check_b(REPO_ROOT, extra_files=synthetic)
        assert not any(v.check == "b" for v in viols)

    def test_no_token_no_violation(self) -> None:
        synthetic = {
            "engine/alert_triage.py": "# nothing here\nprint('hi')\n",
        }
        viols = _check_b(REPO_ROOT, extra_files=synthetic)
        assert len(viols) == 0


class TestCheckC:
    """Check (c): forbidden field names in state-builder/shadow script."""

    def test_rank_field_in_state_builder(self) -> None:
        synthetic = {
            "scripts/build_factor_intelligence_state.py": (
                'result = {"rank": 1, "ticker": "AAPL"}\n'
            ),
        }
        viols = _check_c(REPO_ROOT, extra_files=synthetic)
        assert any(v.check == "c" and "rank" in v.pattern for v in viols)

    def test_score_field_in_shadow_script(self) -> None:
        synthetic = {
            "scripts/build_factor_deescalation_shadow.py": (
                '    row["score"] = 0.9\n'
            ),
        }
        viols = _check_c(REPO_ROOT, extra_files=synthetic)
        assert any(v.check == "c" and "score" in v.pattern for v in viols)

    def test_recommendation_in_state_builder(self) -> None:
        synthetic = {
            "scripts/build_factor_intelligence_state.py": (
                '    payload["recommendation"] = "buy"\n'
            ),
        }
        viols = _check_c(REPO_ROOT, extra_files=synthetic)
        assert any(v.check == "c" and "recommendation" in v.pattern for v in viols)

    def test_clean_state_builder_no_violation(self) -> None:
        synthetic = {
            "scripts/build_factor_intelligence_state.py": (
                "# clean builder\n"
                'result = {"ticker": "AAPL", "as_of": "2026-07-06", "is_context_only": True}\n'
            ),
        }
        viols = _check_c(REPO_ROOT, extra_files=synthetic)
        assert len(viols) == 0

    def test_forbidden_field_in_non_target_file_not_caught(self) -> None:
        """Check-c only targets the two state-builder files."""
        synthetic = {
            "engine/neuralweb/cortex.py": '    result = {"score": 0.5}\n',
        }
        viols = _check_c(REPO_ROOT, extra_files=synthetic)
        assert not any(v.check == "c" for v in viols)


class TestCleanRepo:
    """Verify the actual repo tree passes all three checks."""

    def test_real_repo_check_a_clean(self) -> None:
        """Factor modules in the real repo contain no Article-2 write references."""
        viols = _check_a(REPO_ROOT)
        assert viols == [], "\n".join(v.message for v in viols)

    def test_real_repo_check_b_clean(self) -> None:
        """No non-allowlisted file in the real repo reads 'allowed_actions'."""
        viols = _check_b(REPO_ROOT)
        assert viols == [], "\n".join(v.message for v in viols)

    def test_real_repo_check_c_clean(self) -> None:
        """State builder and shadow script in real repo emit no forbidden field names."""
        viols = _check_c(REPO_ROOT)
        assert viols == [], "\n".join(v.message for v in viols)


class TestSelftest:
    """Verify --selftest exits 0."""

    def test_selftest_passes(self) -> None:
        rc = boundaries_main(["--selftest"])
        assert rc == 0, "check_factor_boundaries --selftest returned non-zero"
