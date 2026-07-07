"""Tests for the adjudication packet validator.

Covers:
  1. Rubrics file loads and every decision class maps to exactly one tier
  2. Every invariant is absent from the decision_classes list
  3. Selftest passes (subprocess: python scripts/check_adjudication_packet.py --selftest, rc=0)
  4. V1 drill fixture hard-blocks (rc=1) via --packet on a tmp file
  5. A well-formed decided tier 1 packet passes (rc=0)
  6. A tier 2 packet with a panel of 2 'refute' verdicts + operator decision passes (rc=0)
  7. HB-13: omitted tier for a known class → hard fail
  8. HB-9: omitted decision_class → hard fail
  9. HB-2 stance enforcement: 2 approve-stance panelists → hard fail
 10. HB-11: authority-touching packet with empty authority dict → hard fail
 11. HB-12: privacy-touching packet missing mastermind_booleans_unchanged → hard fail
 12. m1 drift test: builder class→tier map matches rubrics exactly

All tests are hermetic: only tmp_path fixtures, no reliance on the live queue.

Run:
    python -m pytest tests/test_adjudication_packet.py -q
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
RUBRICS_PATH = ROOT / "config" / "adjudication_rubrics.yml"
CHECK_SCRIPT = ROOT / "scripts" / "check_adjudication_packet.py"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def load_rubrics() -> dict:
    with open(RUBRICS_PATH, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def run_check(*args: str) -> subprocess.CompletedProcess:
    """Run check_adjudication_packet.py with extra args, capture output."""
    return subprocess.run(
        [sys.executable, str(CHECK_SCRIPT)] + list(args),
        capture_output=True,
        text=True,
    )


# ---------------------------------------------------------------------------
# 1. Rubrics schema and decision class mapping
# ---------------------------------------------------------------------------


class TestRubricsLoad:
    def test_rubrics_file_exists(self):
        assert RUBRICS_PATH.exists(), f"rubrics file missing: {RUBRICS_PATH}"

    def test_rubrics_loads(self):
        rubrics = load_rubrics()
        assert isinstance(rubrics, dict), "rubrics must be a dict"

    def test_meta_present(self):
        rubrics = load_rubrics()
        assert "meta" in rubrics
        assert rubrics["meta"]["schema_version"] == 1

    def test_tiers_defined(self):
        rubrics = load_rubrics()
        tiers = rubrics.get("tiers", {})
        assert "t0" in tiers
        assert "t1" in tiers
        assert "t2" in tiers

    def test_every_decision_class_has_one_tier(self):
        """Each decision_class appears exactly once and maps to a valid tier."""
        rubrics = load_rubrics()
        classes = rubrics.get("decision_classes", [])
        assert len(classes) > 0, "decision_classes must not be empty"
        seen: dict[str, int] = {}
        for entry in classes:
            cls = entry["class"]
            tier = entry["tier"]
            assert cls not in seen, f"duplicate decision_class: {cls}"
            assert tier in (0, 1, 2), f"invalid tier {tier!r} for class {cls!r}"
            seen[cls] = tier

    def test_decision_classes_cover_all_tiers(self):
        """There must be at least one class for each of the three tiers."""
        rubrics = load_rubrics()
        tiers_present = {e["tier"] for e in rubrics.get("decision_classes", [])}
        assert 0 in tiers_present, "no tier 0 decision_class found"
        assert 1 in tiers_present, "no tier 1 decision_class found"
        assert 2 in tiers_present, "no tier 2 decision_class found"


# ---------------------------------------------------------------------------
# 2. Invariants not in decision_classes
# ---------------------------------------------------------------------------


class TestInvariants:
    def test_invariants_absent_from_decision_classes(self):
        rubrics = load_rubrics()
        invariant_classes = {e["class"] for e in rubrics.get("invariants", [])}
        decision_classes = {e["class"] for e in rubrics.get("decision_classes", [])}
        overlap = invariant_classes & decision_classes
        assert not overlap, (
            f"invariant class(es) also appear in decision_classes: {overlap} "
            f"— invariants must never be approvable"
        )

    def test_three_invariants_defined(self):
        rubrics = load_rubrics()
        invariants = rubrics.get("invariants", [])
        assert len(invariants) == 3, f"expected 3 invariants, got {len(invariants)}"

    def test_article1_invariant_present(self):
        rubrics = load_rubrics()
        classes = {e["class"] for e in rubrics.get("invariants", [])}
        assert "article_1_amendment_or_a7_origination" in classes

    def test_trial_budget_laundering_invariant_present(self):
        rubrics = load_rubrics()
        classes = {e["class"] for e in rubrics.get("invariants", [])}
        assert "trial_budget_laundering" in classes

    def test_delete_null_history_invariant_present(self):
        rubrics = load_rubrics()
        classes = {e["class"] for e in rubrics.get("invariants", [])}
        assert "delete_negative_or_null_history" in classes


# ---------------------------------------------------------------------------
# 3. Selftest passes
# ---------------------------------------------------------------------------


class TestSelftest:
    def test_selftest_exits_zero(self):
        result = run_check("--selftest")
        assert result.returncode == 0, (
            f"selftest returned rc={result.returncode}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )

    def test_selftest_output_contains_passed(self):
        result = run_check("--selftest")
        combined = result.stdout + result.stderr
        assert "PASSED" in combined, (
            f"selftest output does not contain 'PASSED':\n{combined}"
        )


# ---------------------------------------------------------------------------
# Packet factories — inline (no import of check script to keep test hermetic)
# ---------------------------------------------------------------------------


def _clean_t1_packet() -> dict:
    return {
        "schema": "neuralweb.adjudication_packet.v1",
        "packet_id": "adj-2026-07-06-test-t1",
        "tier": 1,
        "created_at": "2026-07-06T10:00:00Z",
        "created_by": "opus",
        "request": {
            "title": "Add display-only metric to entry dashboard",
            "requested_decision": "scoped_build",
            "decision_class": "scoped_build",
            "source_doc": "research/ENTRY_STACK_AMENDMENT3.md",
            "source_pr": None,
        },
        "scope": {
            "owner_program": "entry_stack_expansion",
            "proposed_classification": "study",
            "touched_artifacts": ["entry_dashboard"],
            "touched_paths": ["engine/entry_stack.py"],
        },
        "case_law": {
            "ruling_hits": ["RUL-7"],
            "duplicate_risk": "low",
            "deferred_or_killed_hits": [],
        },
        "authority": {
            "current_ceiling": "A2",
            "requested_ceiling": "A2",
            "article2_surfaces_touched": [],
            "nondelegable": False,
        },
        "statistics": {
            "fdr_family": "esx_decline_geometry",
            "trial_budget_change": False,
            "evidence_floor_met": True,
            "outcome_data_seen": False,
            "preregistration_ref": None,
        },
        "clocks": {
            "come_back_on": "2026-10-06",
            "due_status": "accruing",
        },
        "allowed_outcomes": ["scoped_build"],
        "blocked_outcomes": ["new_lobe_charter"],
        "escalation": {
            "opened_on": "2026-07-06",
            "stale_after_days": 14,
            "escalated": False,
        },
        "decision": {
            "outcome": "scoped_build",
            "decided_by": "opus",
            "actor_ref": "opus-session-test",
            "rationale": "Scoped display build within program; no scored-path change.",
            "decided_on": "2026-07-06",
        },
    }


def _drill_packet(tier_override: int = 1) -> dict:
    """V1 drill: scored_path_behavior_change claimed at tier_override."""
    return {
        "schema": "neuralweb.adjudication_packet.v1",
        "packet_id": "adj-2026-07-06-drill-v1",
        "tier": tier_override,
        "created_at": "2026-07-06T09:00:00Z",
        "created_by": "codex",
        "request": {
            "title": "Promote cycle-pattern turn hazard into a board rank conditioner",
            "requested_decision": "scoped_build",
            "decision_class": "scored_path_behavior_change",
            "source_doc": "research/CODEX_MEMO.md",
            "source_pr": None,
        },
        "scope": {
            "owner_program": "entry_stack",
            "proposed_classification": "study",
            "touched_artifacts": ["board_rank"],
            "touched_paths": ["engine/entry_stack.py"],
        },
        "case_law": {
            "ruling_hits": [],
            "duplicate_risk": "low",
            "deferred_or_killed_hits": [],
        },
        "authority": {
            "current_ceiling": "A2",
            "requested_ceiling": "A2",
            "article2_surfaces_touched": ["board_rank"],
            "nondelegable": False,
        },
        "statistics": {
            "fdr_family": "esx_decline_geometry",
            "trial_budget_change": False,
            "evidence_floor_met": True,
            "outcome_data_seen": False,
            "preregistration_ref": None,
        },
        "clocks": {
            "come_back_on": "2026-08-06",
            "due_status": "not_clocked",
        },
        "allowed_outcomes": ["scoped_build"],
        "blocked_outcomes": [],
        "escalation": {
            "opened_on": "2026-07-06",
            "stale_after_days": 14,
            "escalated": False,
        },
        "decision": {
            "outcome": "scoped_build",
            "decided_by": "opus",
            "actor_ref": "opus-session-drill",
            "rationale": "Approving as scoped build.",
            "decided_on": "2026-07-06",
        },
    }


def _t2_packet_good() -> dict:
    """Tier 2 packet with 2 refute-stance panelists and operator sign-off."""
    return {
        "schema": "neuralweb.adjudication_packet.v1",
        "packet_id": "adj-2026-07-06-t2-good",
        "tier": 2,
        "created_at": "2026-07-06T08:00:00Z",
        "created_by": "operator",
        "request": {
            "title": "Charter new lobe for macro timing",
            "requested_decision": "new_lobe_charter",
            "decision_class": "new_lobe_charter",
            "source_doc": "research/NW_LOBES.md",
            "source_pr": None,
        },
        "scope": {
            "owner_program": "nw_rails_lobes",
            "proposed_classification": "lobe",
            "touched_artifacts": [],
            "touched_paths": [],
        },
        "case_law": {
            "ruling_hits": ["RUL-SUCC-1"],
            "duplicate_risk": "low",
            "deferred_or_killed_hits": [],
        },
        "authority": {
            "current_ceiling": "A2",
            "requested_ceiling": "A2",
            "article2_surfaces_touched": [],
            "nondelegable": True,
        },
        "privacy": {
            "privacy_class": "public_research",
            "public_paths_touched": [],
            "private_fields": [],
        },
        "statistics": {
            "fdr_family": "macro_tx",
            "trial_budget_change": False,
            "evidence_floor_met": True,
            "outcome_data_seen": False,
            "preregistration_ref": None,
        },
        "clocks": {
            "come_back_on": "2026-10-01",
            "due_status": "accruing",
        },
        "build_collision": {
            "open_prs_touching_paths": [],
            "owner_conflicts": [],
        },
        "review": {
            "required_lenses": ["evidence", "architecture"],
            "opus_findings": [],
            "panel": [
                {
                    "reviewer_ref": "opus-reviewer-a",
                    "stance": "refute",
                    "verdict": "stands",
                    "rationale": "Evidence floor met; no redundancy with existing lobes.",
                },
                {
                    "reviewer_ref": "opus-reviewer-b",
                    "stance": "refute",
                    "verdict": "stands",
                    "rationale": "Architecture sound; no scored-path leakage.",
                },
            ],
        },
        "allowed_outcomes": ["new_lobe_charter"],
        "blocked_outcomes": [],
        "escalation": {
            "opened_on": "2026-07-06",
            "stale_after_days": 14,
            "escalated": False,
        },
        "decision": {
            "outcome": "new_lobe_charter",
            "decided_by": "operator",
            "actor_ref": "operator",
            "rationale": "Panel cleared (2 refute reviewers, both 'stands'); operator signs off.",
            "decided_on": "2026-07-06",
        },
    }


# ---------------------------------------------------------------------------
# 4. V1 drill fixture hard-blocks via --packet
# ---------------------------------------------------------------------------


class TestDrillPacket:
    def test_drill_tier1_hard_blocks(self, tmp_path: Path):
        """V1 drill packet claiming tier 1 must trigger HB-10 (tier laundering)."""
        pkt = _drill_packet(tier_override=1)
        pkt_file = tmp_path / "drill_t1.json"
        pkt_file.write_text(json.dumps(pkt), encoding="utf-8")
        result = run_check("--packet", str(pkt_file), "--as-of", "2026-07-06")
        assert result.returncode == 1, (
            f"drill tier=1 packet should hard-fail (HB-10) but got rc={result.returncode}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
        combined = result.stdout + result.stderr
        assert "HB-10" in combined, (
            f"expected HB-10 in output but got:\n{combined}"
        )

    def test_drill_tier2_no_panel_blocks(self, tmp_path: Path):
        """V1 drill packet at tier=2 (no panel, opus decider) must trigger HB-2 and HB-3."""
        pkt = _drill_packet(tier_override=2)
        # Add t2-required fields so only HB-2/HB-3 remain
        pkt["privacy"] = {
            "privacy_class": "public_research",
            "public_paths_touched": [],
            "private_fields": [],
        }
        pkt["build_collision"] = {"open_prs_touching_paths": [], "owner_conflicts": []}
        pkt["review"] = {"required_lenses": [], "opus_findings": [], "panel": []}
        pkt_file = tmp_path / "drill_t2.json"
        pkt_file.write_text(json.dumps(pkt), encoding="utf-8")
        result = run_check("--packet", str(pkt_file), "--as-of", "2026-07-06")
        assert result.returncode == 1, (
            f"drill tier=2 no-panel packet should hard-fail but got rc={result.returncode}\n"
            f"stdout:\n{result.stdout}"
        )
        combined = result.stdout + result.stderr
        assert "HB-2" in combined or "HB-3" in combined, (
            f"expected HB-2 or HB-3 in output but got:\n{combined}"
        )


# ---------------------------------------------------------------------------
# 5. Well-formed decided tier 1 packet passes
# ---------------------------------------------------------------------------


class TestCleanT1Packet:
    def test_clean_t1_passes(self, tmp_path: Path):
        pkt = _clean_t1_packet()
        pkt_file = tmp_path / "clean_t1.json"
        pkt_file.write_text(json.dumps(pkt), encoding="utf-8")
        result = run_check("--packet", str(pkt_file), "--as-of", "2026-07-06")
        assert result.returncode == 0, (
            f"clean t1 packet should pass (rc=0) but got rc={result.returncode}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )


# ---------------------------------------------------------------------------
# 6. Tier 2 packet with proper panel and operator sign-off passes
# ---------------------------------------------------------------------------


class TestT2GoodPacket:
    def test_t2_good_packet_passes(self, tmp_path: Path):
        pkt = _t2_packet_good()
        pkt_file = tmp_path / "t2_good.json"
        pkt_file.write_text(json.dumps(pkt), encoding="utf-8")
        result = run_check("--packet", str(pkt_file), "--as-of", "2026-07-06")
        assert result.returncode == 0, (
            f"t2 good packet should pass (rc=0) but got rc={result.returncode}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )

    def test_t2_stands_verdicts_panel(self, tmp_path: Path):
        """Confirm 2 'refute'-stance panelists with 'stands' verdicts pass HB-2.

        HB-2 requires stance='refute' AND a verdict; the verdict value
        (refuted|stands) is not further restricted.
        """
        pkt = _t2_packet_good()
        assert len(pkt["review"]["panel"]) == 2
        for p in pkt["review"]["panel"]:
            assert p["stance"] == "refute"   # m2: stance must be refute
            assert p["verdict"] == "stands"
        pkt_file = tmp_path / "t2_stands.json"
        pkt_file.write_text(json.dumps(pkt), encoding="utf-8")
        result = run_check("--packet", str(pkt_file), "--as-of", "2026-07-06")
        assert result.returncode == 0, (
            f"t2 packet with 2 'refute'-stance 'stands' verdicts + operator should pass:\n{result.stdout}"
        )


# ---------------------------------------------------------------------------
# 7. HB-13: omitted tier → hard fail for known class
# ---------------------------------------------------------------------------


class TestHB13OmittedTier:
    def test_omitted_tier_known_class_fails(self, tmp_path: Path):
        """Packet with known decision_class but no tier field → HB-13."""
        pkt = _clean_t1_packet()
        del pkt["tier"]
        pkt_file = tmp_path / "no_tier.json"
        pkt_file.write_text(json.dumps(pkt), encoding="utf-8")
        result = run_check("--packet", str(pkt_file), "--as-of", "2026-07-06")
        assert result.returncode == 1, (
            f"packet with missing tier should hard-fail (rc=1) but got rc={result.returncode}"
        )
        combined = result.stdout + result.stderr
        assert "HB-13" in combined, (
            f"expected HB-13 in output but got:\n{combined}"
        )


# ---------------------------------------------------------------------------
# 8. HB-9: omitted decision_class → hard fail
# ---------------------------------------------------------------------------


class TestHB9MissingDecisionClass:
    def test_missing_decision_class_fails(self, tmp_path: Path):
        """Packet with decision_class=null → HB-9 hard fail."""
        pkt = _clean_t1_packet()
        pkt["request"]["decision_class"] = None
        pkt_file = tmp_path / "no_class.json"
        pkt_file.write_text(json.dumps(pkt), encoding="utf-8")
        result = run_check("--packet", str(pkt_file), "--as-of", "2026-07-06")
        assert result.returncode == 1, (
            f"packet with missing decision_class should hard-fail but got rc={result.returncode}"
        )
        combined = result.stdout + result.stderr
        assert "HB-9" in combined, (
            f"expected HB-9 in output but got:\n{combined}"
        )


# ---------------------------------------------------------------------------
# 9. HB-2 stance enforcement: approve-stance panelists do not count
# ---------------------------------------------------------------------------


class TestHB2StanceEnforcement:
    def test_two_approve_stance_panelists_fail(self, tmp_path: Path):
        """Tier 2 decided with 2 approve-stance panelists must hard-fail HB-2."""
        pkt = _t2_packet_good()
        # Replace refute-stance panelists with approve-stance
        pkt["review"]["panel"] = [
            {
                "reviewer_ref": "reviewer-a",
                "stance": "approve",
                "verdict": "stands",
                "rationale": "Looks good to me.",
            },
            {
                "reviewer_ref": "reviewer-b",
                "stance": "approve",
                "verdict": "stands",
                "rationale": "Also looks good.",
            },
        ]
        pkt_file = tmp_path / "approve_stance.json"
        pkt_file.write_text(json.dumps(pkt), encoding="utf-8")
        result = run_check("--packet", str(pkt_file), "--as-of", "2026-07-06")
        assert result.returncode == 1, (
            f"2 approve-stance panelists should hard-fail (rc=1) but got rc={result.returncode}"
        )
        combined = result.stdout + result.stderr
        assert "HB-2" in combined, (
            f"expected HB-2 in output (approve-stance does not satisfy refute requirement) "
            f"but got:\n{combined}"
        )

    def test_one_refute_one_approve_fails(self, tmp_path: Path):
        """One refute + one approve panelist does not meet >=2 refute requirement."""
        pkt = _t2_packet_good()
        pkt["review"]["panel"] = [
            {
                "reviewer_ref": "reviewer-a",
                "stance": "refute",
                "verdict": "stands",
                "rationale": "Evidence floor met.",
            },
            {
                "reviewer_ref": "reviewer-b",
                "stance": "approve",
                "verdict": "stands",
                "rationale": "Approving.",
            },
        ]
        pkt_file = tmp_path / "mixed_stance.json"
        pkt_file.write_text(json.dumps(pkt), encoding="utf-8")
        result = run_check("--packet", str(pkt_file), "--as-of", "2026-07-06")
        assert result.returncode == 1, (
            f"1 refute + 1 approve should hard-fail (rc=1) but got rc={result.returncode}"
        )
        combined = result.stdout + result.stderr
        assert "HB-2" in combined, f"expected HB-2, got:\n{combined}"


# ---------------------------------------------------------------------------
# 10. HB-11: authority-touching packet with empty authority dict → hard fail
# ---------------------------------------------------------------------------


class TestHB11AuthorityFloor:
    def test_ceiling_change_no_floor_fields_fails(self, tmp_path: Path):
        """Ceiling change triggers HB-11 when article_citation and article3_evidence absent."""
        pkt = _clean_t1_packet()
        pkt["authority"] = {
            "current_ceiling": "A2",
            "requested_ceiling": "A3",  # ceiling change → floor triggered
            "article2_surfaces_touched": [],
            "nondelegable": False,
            # No article_citation, no article3_evidence
        }
        pkt_file = tmp_path / "auth_floor.json"
        pkt_file.write_text(json.dumps(pkt), encoding="utf-8")
        result = run_check("--packet", str(pkt_file), "--as-of", "2026-07-06")
        assert result.returncode == 1, (
            f"authority-touching packet without floor fields should hard-fail "
            f"but got rc={result.returncode}"
        )
        combined = result.stdout + result.stderr
        assert "HB-11" in combined, f"expected HB-11, got:\n{combined}"

    def test_article2_surfaces_no_floor_fails(self, tmp_path: Path):
        """Non-empty article2_surfaces_touched triggers HB-11 when floor is empty."""
        pkt = _clean_t1_packet()
        pkt["authority"] = {
            "current_ceiling": "A2",
            "requested_ceiling": "A2",  # same ceiling
            "article2_surfaces_touched": ["board_rank"],  # surfaces touched → triggers floor
            "nondelegable": False,
        }
        pkt_file = tmp_path / "auth_surfaces.json"
        pkt_file.write_text(json.dumps(pkt), encoding="utf-8")
        result = run_check("--packet", str(pkt_file), "--as-of", "2026-07-06")
        assert result.returncode == 1, (
            f"packet with article2_surfaces but no floor fields should hard-fail "
            f"but got rc={result.returncode}"
        )
        combined = result.stdout + result.stderr
        assert "HB-11" in combined, f"expected HB-11, got:\n{combined}"


# ---------------------------------------------------------------------------
# 11. HB-12: privacy-touching packet missing mastermind_booleans_unchanged → hard fail
# ---------------------------------------------------------------------------


class TestHB12PrivacyFloor:
    def test_private_privacy_class_no_mastermind_boolean_fails(self, tmp_path: Path):
        """host_private privacy_class triggers HB-12 when mastermind_booleans_unchanged absent."""
        pkt = _clean_t1_packet()
        # Use a class that triggers privacy floor (public_private_boundary is t2;
        # here we use a t1 class but set privacy_class to host_private to trigger the floor)
        pkt["privacy"] = {
            "privacy_class": "host_private",
            "public_paths_touched": [],
            "private_fields": ["api_key"],
            # mastermind_booleans_unchanged absent → floor violation
        }
        pkt_file = tmp_path / "priv_floor.json"
        pkt_file.write_text(json.dumps(pkt), encoding="utf-8")
        result = run_check("--packet", str(pkt_file), "--as-of", "2026-07-06")
        assert result.returncode == 1, (
            f"privacy-touching packet without mastermind_booleans_unchanged should hard-fail "
            f"but got rc={result.returncode}"
        )
        combined = result.stdout + result.stderr
        assert "HB-12" in combined, f"expected HB-12, got:\n{combined}"

    def test_mastermind_booleans_false_fails(self, tmp_path: Path):
        """mastermind_booleans_unchanged=false triggers HB-12 (must be true)."""
        pkt = _clean_t1_packet()
        pkt["privacy"] = {
            "privacy_class": "mastermind_private",
            "public_paths_touched": [],
            "private_fields": [],
            "mastermind_booleans_unchanged": False,  # explicitly false
        }
        pkt_file = tmp_path / "mastermind_false.json"
        pkt_file.write_text(json.dumps(pkt), encoding="utf-8")
        result = run_check("--packet", str(pkt_file), "--as-of", "2026-07-06")
        assert result.returncode == 1, (
            f"mastermind_booleans_unchanged=false should hard-fail but got rc={result.returncode}"
        )
        combined = result.stdout + result.stderr
        assert "HB-12" in combined, f"expected HB-12, got:\n{combined}"


# ---------------------------------------------------------------------------
# 12. m1 drift test: builder class→tier map matches rubrics exactly
# ---------------------------------------------------------------------------


class TestBuilderRubricsDrift:
    """The builder's class→tier map must be exact-equal to rubrics decision_classes."""

    @pytest.fixture(autouse=True)
    def _load_builder(self):
        build_script = ROOT / "scripts" / "build_adjudication_packet.py"
        spec = importlib.util.spec_from_file_location("build_adjudication_packet", build_script)
        mod = importlib.util.module_from_spec(spec)
        sys.path.insert(0, str(ROOT))
        spec.loader.exec_module(mod)
        self.builder = mod

    def _rubrics_class_tier_map(self) -> dict[str, int]:
        rubrics = load_rubrics()
        return {e["class"]: e["tier"] for e in rubrics.get("decision_classes", [])}

    def _rubrics_invariant_set(self) -> set[str]:
        rubrics = load_rubrics()
        return {e["class"] for e in rubrics.get("invariants", [])}

    def _builder_class_tier_map(self) -> dict[str, int]:
        result: dict[str, int] = {}
        for cls in self.builder._T0_CLASSES:
            result[cls] = 0
        for cls in self.builder._T1_CLASSES:
            result[cls] = 1
        for cls in self.builder._T2_CLASSES:
            result[cls] = 2
        return result

    def test_builder_and_rubrics_class_tier_map_exact_match(self):
        """Builder class→tier map is exactly equal to rubrics decision_classes."""
        rubrics_map = self._rubrics_class_tier_map()
        builder_map = self._builder_class_tier_map()
        assert builder_map == rubrics_map, (
            f"Builder class→tier map does not match rubrics.\n"
            f"In builder but not rubrics: {set(builder_map) - set(rubrics_map)}\n"
            f"In rubrics but not builder: {set(rubrics_map) - set(builder_map)}\n"
            f"Tier mismatches: "
            f"{{k: (builder={builder_map.get(k)}, rubrics={rubrics_map.get(k)}) "
            f"for k in set(builder_map) & set(rubrics_map) if builder_map[k] != rubrics_map[k]}}"
        )

    def test_builder_classes_disjoint_from_rubrics_invariants(self):
        """Builder's classes must not overlap with rubrics invariants."""
        invariants = self._rubrics_invariant_set()
        builder_map = self._builder_class_tier_map()
        overlap = set(builder_map.keys()) & invariants
        assert not overlap, (
            f"Builder classes overlap with rubrics invariants: {overlap} — "
            f"invariants must never be buildable/approvable"
        )


# ---------------------------------------------------------------------------
# 13. FIX 2 regression: non-mapping section does not crash the sweep
# ---------------------------------------------------------------------------


def _clean_t1_decided_packet(packet_id: str) -> dict:
    """A well-formed decided tier-1 packet with a unique id."""
    pkt = _clean_t1_packet()
    pkt["packet_id"] = packet_id
    return pkt


class TestNonMappingSectionRobustness:
    """A malformed packet (authority: string) must not abort the queue sweep.

    FIX 2: check_adjudication_packet.py must:
    (a) emit HB-8 "not a mapping" for the malformed section
    (b) continue evaluating the next packet in the queue (sweep resilience)
    (c) return rc=1 overall because there is at least one HB finding
    """

    def test_malformed_section_hb8_plus_clean_packet_evaluated(self, tmp_path: Path):
        """Queue with one malformed packet + one clean packet → rc=1.

        The malformed packet has authority='garbage' (string, not dict).
        Expected outcomes:
          - rc=1 (hard blocker from malformed packet)
          - HB-8 "not a mapping" appears in output
          - Clean packet's packet_id appears in output (proving it was evaluated)
        """
        malformed_pkt = _clean_t1_decided_packet("adj-malformed-authority-001")
        malformed_pkt["authority"] = "garbage"  # string instead of dict → crashes old code

        clean_pkt = _clean_t1_decided_packet("adj-clean-after-malformed-002")

        queue = {
            "schema": "neuralweb.adjudication_queue.v1",
            "updated_at": "2026-07-06",
            "packets": [malformed_pkt, clean_pkt],
        }
        queue_file = tmp_path / "malformed_queue.json"
        queue_file.write_text(json.dumps(queue), encoding="utf-8")

        result = run_check("--queue", str(queue_file), "--as-of", "2026-07-06")
        combined = result.stdout + result.stderr

        assert result.returncode == 1, (
            f"Queue with malformed packet should return rc=1 but got rc={result.returncode}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
        assert "HB-8" in combined, (
            f"Expected HB-8 (not-a-mapping) finding but got:\n{combined}"
        )
        assert "not a mapping" in combined.lower() or "not_a_mapping" in combined.lower() or \
               "is not a mapping" in combined, (
            f"Expected 'not a mapping' message in output but got:\n{combined}"
        )
        # The clean packet must also appear in the output, proving the sweep continued
        assert clean_pkt["packet_id"] in combined or "2 packet" in combined, (
            f"Expected evidence that the clean packet '{clean_pkt['packet_id']}' was "
            f"evaluated (sweep continued past the malformed packet). Output:\n{combined}"
        )
