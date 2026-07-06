"""Tests for scripts/check_cycle_pattern_authority.py.

Covers:
  1. YAML files parse and required keys are present.
  2. Authority script passes on the current repo tree (no HARD violations).
  3. --selftest fires and passes (gate proves itself on planted violations).
  4. Forbidden-target rule (ret_fwd_alone) is present in candidate_grammar.yml.
  5. Required condition dimensions are declared in candidate_grammar.yml.
  6. Required targets are declared in candidate_grammar.yml.
  7. Consumer matrix has required surfaces and artifact classes.
  8. Money-path module detection: board_rank surface yields HARD.
  9. Allowed-reader detection: engine/cycle_pattern/ yields no finding.
 10. clean module yields no finding.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Repo root fixture (avoids import-time coupling to script internals)
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent


def _load_yaml(path: Path) -> dict:
    """Load a YAML file; return parsed content."""
    import yaml  # pyyaml — always available in CI (installed with pytest)
    return yaml.safe_load(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# 1. YAML files parse
# ---------------------------------------------------------------------------

class TestYamlParses:
    """Both config YAML files must parse without error."""

    def test_candidate_grammar_parses(self):
        path = ROOT / "config" / "cycle_pattern" / "candidate_grammar.yml"
        assert path.exists(), f"Missing: {path}"
        data = _load_yaml(path)
        assert isinstance(data, dict), "candidate_grammar.yml must be a YAML mapping"

    def test_consumer_matrix_parses(self):
        path = ROOT / "config" / "cycle_pattern" / "consumer_matrix.yml"
        assert path.exists(), f"Missing: {path}"
        data = _load_yaml(path)
        assert isinstance(data, dict), "consumer_matrix.yml must be a YAML mapping"


# ---------------------------------------------------------------------------
# 2. Required keys in candidate_grammar.yml
# ---------------------------------------------------------------------------

class TestCandidateGrammarRequiredKeys:
    """candidate_grammar.yml must contain the required top-level keys."""

    @pytest.fixture(scope="class")
    def grammar(self):
        return _load_yaml(ROOT / "config" / "cycle_pattern" / "candidate_grammar.yml")

    def test_schema_version_present(self, grammar):
        assert "schema_version" in grammar

    def test_allowed_condition_dimensions_present(self, grammar):
        assert "allowed_condition_dimensions" in grammar
        assert isinstance(grammar["allowed_condition_dimensions"], list)
        assert len(grammar["allowed_condition_dimensions"]) >= 1

    def test_allowed_targets_present(self, grammar):
        assert "allowed_targets" in grammar
        assert isinstance(grammar["allowed_targets"], list)
        assert len(grammar["allowed_targets"]) >= 1

    def test_forbidden_targets_present(self, grammar):
        assert "forbidden_targets" in grammar
        assert isinstance(grammar["forbidden_targets"], list)
        assert len(grammar["forbidden_targets"]) >= 1

    def test_trial_family_budgets_present(self, grammar):
        assert "trial_family_budgets" in grammar
        assert isinstance(grammar["trial_family_budgets"], list)
        assert len(grammar["trial_family_budgets"]) >= 1

    def test_embargo_start_present_in_each_budget(self, grammar):
        for budget in grammar["trial_family_budgets"]:
            assert "embargo_start" in budget, (
                f"trial_family_budget {budget.get('family_id')!r} missing embargo_start"
            )

    def test_n_floor_present_in_each_budget(self, grammar):
        for budget in grammar["trial_family_budgets"]:
            assert "n_floor" in budget, (
                f"trial_family_budget {budget.get('family_id')!r} missing n_floor"
            )
            assert budget["n_floor"] >= 1

    def test_fdr_q_in_each_budget(self, grammar):
        for budget in grammar["trial_family_budgets"]:
            assert "fdr_q" in budget
            assert 0 < budget["fdr_q"] <= 1.0

    def test_embargo_start_value(self, grammar):
        for budget in grammar["trial_family_budgets"]:
            # embargo_start must be "2024-01-01" per masterplan
            assert budget["embargo_start"] == "2024-01-01", (
                f"Budget {budget.get('family_id')!r}: embargo_start must be "
                f"'2024-01-01' (masterplan §8 / house rule)"
            )


# ---------------------------------------------------------------------------
# 3. Condition dimensions declared in candidate_grammar.yml
# ---------------------------------------------------------------------------

class TestRequiredConditionDimensions:
    """All condition dimensions listed in the masterplan must be present."""

    REQUIRED_DIMS = {
        "phase",
        "phase_v2",
        "pos_bin",
        "osc_slope_sign",
        "age_bucket",
        "overdue",
        "hazard_src",
        "hazard_prob_bin",
        "trend_pass",
        "rs_bin",
        "vol_pctile_bin",
        "quad",
        "family",
        "region",
        "sync_tercile",
        "phase_breadth_bin",
    }

    @pytest.fixture(scope="class")
    def dim_names(self):
        grammar = _load_yaml(ROOT / "config" / "cycle_pattern" / "candidate_grammar.yml")
        return {d["name"] for d in grammar["allowed_condition_dimensions"]}

    def test_all_required_dims_present(self, dim_names):
        missing = self.REQUIRED_DIMS - dim_names
        assert not missing, (
            f"candidate_grammar.yml is missing condition dimensions: {sorted(missing)}"
        )


# ---------------------------------------------------------------------------
# 4. Targets declared in candidate_grammar.yml
# ---------------------------------------------------------------------------

class TestRequiredTargets:
    """All targets listed in the masterplan must be present in allowed_targets."""

    REQUIRED_TARGETS = {
        "max_drawdown_fwd_63d_tail",
        "max_drawdown_fwd_126d_tail",
        "turn_event_1m",
        "turn_event_3m",
        "turn_event_6m",
        "phase_changed_1m",
        "phase_changed_3m",
        "false_repair",
        "phase_persistence",
    }

    @pytest.fixture(scope="class")
    def target_names(self):
        grammar = _load_yaml(ROOT / "config" / "cycle_pattern" / "candidate_grammar.yml")
        return {t["name"] for t in grammar["allowed_targets"]}

    def test_all_required_targets_present(self, target_names):
        missing = self.REQUIRED_TARGETS - target_names
        assert not missing, (
            f"candidate_grammar.yml is missing allowed targets: {sorted(missing)}"
        )


# ---------------------------------------------------------------------------
# 5. Forbidden-target rule present (standing null CPI-001)
# ---------------------------------------------------------------------------

class TestForbiddenTargetRule:
    """The ret_fwd_alone forbidden-target rule must be present in grammar."""

    @pytest.fixture(scope="class")
    def grammar(self):
        return _load_yaml(ROOT / "config" / "cycle_pattern" / "candidate_grammar.yml")

    def test_forbidden_target_ret_fwd_alone_present(self, grammar):
        names = {ft["name"] for ft in grammar["forbidden_targets"]}
        assert "ret_fwd_alone" in names, (
            "candidate_grammar.yml must declare ret_fwd_alone as a forbidden target "
            "(standing null CPI-001 / rule CPI-FORBIDDEN-001)"
        )

    def test_forbidden_target_references_cpi001(self, grammar):
        for ft in grammar["forbidden_targets"]:
            if ft["name"] == "ret_fwd_alone":
                assert ft.get("truth_id") == "CPI-001", (
                    "ret_fwd_alone forbidden target must reference truth_id CPI-001"
                )
                break

    def test_false_repair_definition_present(self, grammar):
        """false_repair target must carry an explicit definition string."""
        for t in grammar["allowed_targets"]:
            if t["name"] == "false_repair":
                assert "definition" in t, (
                    "false_repair target must carry a 'definition' field "
                    "(phase Recovery/Repair at t AND turn_event_down within 6m)"
                )
                assert "RECOVERY" in t["definition"] or "Recovery" in t["definition"]
                return
        pytest.fail("false_repair not found in allowed_targets")


# ---------------------------------------------------------------------------
# 6. Consumer matrix required keys
# ---------------------------------------------------------------------------

class TestConsumerMatrix:
    """consumer_matrix.yml must have required keys and artifact classes."""

    REQUIRED_ARTIFACT_CLASSES = {
        "promoted_null",
        "display",
        "confirmer",
        "scored",
        "candidates",
        "lake_artifacts",
    }

    MONEY_PATH_SURFACES = {
        "board_rank",
        "oracle_escalation",
        "sector_central_direction_score",
        "position_sizing",
    }

    @pytest.fixture(scope="class")
    def matrix(self):
        return _load_yaml(ROOT / "config" / "cycle_pattern" / "consumer_matrix.yml")

    def test_schema_version_present(self, matrix):
        assert "schema_version" in matrix

    def test_artifact_classes_present(self, matrix):
        assert "artifact_classes" in matrix
        assert isinstance(matrix["artifact_classes"], list)

    def test_all_required_artifact_classes_present(self, matrix):
        declared = {ac["class"] for ac in matrix["artifact_classes"]}
        missing = self.REQUIRED_ARTIFACT_CLASSES - declared
        assert not missing, (
            f"consumer_matrix.yml is missing artifact classes: {sorted(missing)}"
        )

    def test_money_path_surfaces_in_forbidden_for_lake_and_candidates(self, matrix):
        """Board-rank etc. must be forbidden for lake_artifacts and candidates."""
        for ac in matrix["artifact_classes"]:
            if ac["class"] in ("lake_artifacts", "candidates"):
                forbidden = set(ac.get("forbidden_consumers", []))
                missing = self.MONEY_PATH_SURFACES - forbidden
                assert not missing, (
                    f"artifact_class {ac['class']!r}: money-path surfaces not in "
                    f"forbidden_consumers: {sorted(missing)}"
                )

    def test_money_path_surfaces_in_forbidden_for_promoted_null(self, matrix):
        for ac in matrix["artifact_classes"]:
            if ac["class"] == "promoted_null":
                forbidden = set(ac.get("forbidden_consumers", []))
                missing = self.MONEY_PATH_SURFACES - forbidden
                assert not missing, (
                    f"promoted_null: money-path surfaces not in forbidden_consumers: "
                    f"{sorted(missing)}"
                )

    def test_allowed_forbidden_disjoint_per_class(self, matrix):
        """allowed_consumers and forbidden_consumers must be disjoint."""
        for ac in matrix["artifact_classes"]:
            allowed = set(ac.get("allowed_consumers", []))
            forbidden = set(ac.get("forbidden_consumers", []))
            overlap = allowed & forbidden
            assert not overlap, (
                f"artifact_class {ac['class']!r}: surfaces in BOTH allowed and "
                f"forbidden lists: {sorted(overlap)}"
            )

    def test_surfaces_block_present(self, matrix):
        assert "surfaces" in matrix


# ---------------------------------------------------------------------------
# 7. Authority script passes on the current repo tree (no HARD findings)
# ---------------------------------------------------------------------------

class TestAuthorityScriptClean:
    """The authority script must exit 0 on the current repo tree."""

    def test_no_hard_findings_in_current_tree(self):
        # Import the script as a module — avoids subprocess overhead.
        sys.path.insert(0, str(ROOT / "scripts"))
        try:
            import check_cycle_pattern_authority as guard
            findings = guard.scan(ROOT)
            hard = [f for f in findings if f["severity"] == "HARD"]
            assert not hard, (
                f"check_cycle_pattern_authority found {len(hard)} HARD violation(s) "
                f"in the current repo tree:\n"
                + "\n".join(
                    f"  {f['module']}:{f['line_no']} — {f['reason']}"
                    for f in hard
                )
            )
        finally:
            sys.path.pop(0)


# ---------------------------------------------------------------------------
# 8. --selftest proves the gate fires
# ---------------------------------------------------------------------------

class TestSelftest:
    """The built-in selftest must pass (exit 0)."""

    def test_selftest_passes(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        try:
            import check_cycle_pattern_authority as guard
            result = guard._run_selftest(ROOT)
            assert result == 0, (
                "check_cycle_pattern_authority --selftest returned non-zero: "
                "one or more synthetic cases not handled correctly"
            )
        finally:
            sys.path.pop(0)


# ---------------------------------------------------------------------------
# 9 & 10. Scan mechanics: money-path → HARD; allowed reader → no finding;
#         clean module → no finding (mirrors selftest but explicit unit tests)
# ---------------------------------------------------------------------------

class TestScanMechanics:
    """Unit tests for the scan() function internals."""

    @pytest.fixture(scope="class")
    def guard(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        import check_cycle_pattern_authority as g
        yield g
        sys.path.pop(0)

    def test_money_path_module_yields_hard(self, guard):
        findings = guard.scan(ROOT, extra_files={
            "scripts/build_stock_library.py": (
                "# synthetic board_rank surface\n"
                "df = pd.read_parquet('data/cycle_pattern/outcomes.parquet')\n"
            )
        })
        hard = [f for f in findings if f["severity"] == "HARD"]
        assert hard, "Money-path module (board_rank) should yield a HARD finding"
        assert all(f["module"] == "scripts/build_stock_library.py" for f in hard)

    def test_allowed_owner_yields_no_finding(self, guard):
        findings = guard.scan(ROOT, extra_files={
            "engine/cycle_pattern/lake.py": (
                "# owner module — allowed\n"
                "df = pd.read_parquet('data/cycle_pattern/state_monthly.parquet')\n"
            )
        })
        assert not any(
            f["module"] == "engine/cycle_pattern/lake.py" for f in findings
        ), "Allowed owner (engine/cycle_pattern/) should produce no finding"

    def test_clean_module_yields_no_finding(self, guard):
        findings = guard.scan(ROOT, extra_files={
            "engine/_cp_test_clean.py": (
                "# no cycle_pattern reference\n"
                "df = pd.read_parquet('data/regime/latest.parquet')\n"
            )
        })
        assert not any(
            f["module"] == "engine/_cp_test_clean.py" for f in findings
        ), "Clean module should produce no finding"

    def test_test_module_yields_no_finding(self, guard):
        findings = guard.scan(ROOT, extra_files={
            "tests/test_cp_dummy.py": (
                "# test — always allowed\n"
                "df = pd.read_parquet('data/cycle_pattern/entities.parquet')\n"
            )
        })
        assert not any(
            f["module"] == "tests/test_cp_dummy.py" for f in findings
        ), "tests/ module should produce no finding"

    def test_adapter_cycle_pattern_yields_no_finding(self, guard):
        """Pre-allowlisted research_factory adapter should not produce a finding."""
        findings = guard.scan(ROOT, extra_files={
            "engine/research_factory/adapter_cycle_pattern.py": (
                "# factory adapter — pre-allowlisted\n"
                "df = pd.read_parquet('data/cycle_pattern/truths.jsonl')\n"
            )
        })
        assert not any(
            f["module"] == "engine/research_factory/adapter_cycle_pattern.py"
            for f in findings
        ), "Pre-allowlisted adapter_cycle_pattern.py should produce no finding"

    def test_unknown_module_yields_warn_not_hard(self, guard):
        findings = guard.scan(ROOT, extra_files={
            "engine/_cp_unknown.py": (
                "# unknown module — not in allowlist\n"
                "df = pd.read_parquet('data/cycle_pattern/outcomes.parquet')\n"
            )
        })
        matches = [f for f in findings if f["module"] == "engine/_cp_unknown.py"]
        assert matches, "Unknown module should produce a finding"
        assert all(f["severity"] == "WARN" for f in matches), (
            "Unknown non-money-path module should produce WARN, not HARD"
        )
