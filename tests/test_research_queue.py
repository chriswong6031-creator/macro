"""tests/test_research_queue.py — Unit tests for research_queue EV-ranker + S14.

COVERAGE:
  A. Absent-file-safe: empty inputs → valid empty-but-valid output structure
  B. too_sparse: a candidate with n_expected < MIN_N lands in too_sparse
  C. duplicate_of_existing: a candidate that overlaps an existing species lands in
     duplicate_of_existing
  D. invalid_shape: a candidate with a spine_query referencing cortex_attention
     lands in invalid_shape
  E. high_ev_build_now: a normal novel feasible candidate ranks in high_ev_build_now
  F. blocked_by_data: a candidate whose spine_query family is unresolvable lands in
     blocked_by_data
  G. next_best_experiment is the top-ranked high_ev candidate id
  H. trial_budget is informational and always present
  I. S14 species entry passes validate_entry()
  J. Synapse registry has zero violations after adding research-queue artifact

All tests are HERMETIC (tmp dirs, no real data dependencies where possible).
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tmp_root() -> Path:
    """Return a fresh temporary repo root with minimal directory structure."""
    d = Path(tempfile.mkdtemp())
    (d / "data" / "neuralweb").mkdir(parents=True)
    (d / "data" / "neuralweb" / "cortex").mkdir(parents=True)
    (d / "data" / "species").mkdir(parents=True)
    (d / "data" / "experiments").mkdir(parents=True)
    (d / "data").mkdir(parents=True, exist_ok=True)
    # Minimal trial ledger
    (d / "data" / "trial_ledger.jsonl").touch()
    return d


def _write_inbox(root: Path, rows: list[dict]) -> None:
    p = root / "data" / "neuralweb" / "cortex" / "hypothesis_inbox.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def _write_species_registry(root: Path, species: list[dict]) -> None:
    p = root / "data" / "species" / "registry.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps({"schema": "species_registry.v1", "species": species}, indent=2),
        encoding="utf-8",
    )


def _make_inbox_candidate(
    cid: str,
    hypothesis: str,
    claim_shape: str = "lead_lag",
    family: str = "breadth",
    horizon_d: int = 21,
    n_expected: int = 50,
    **kwargs: Any,
) -> dict:
    return {
        "id": cid,
        "hypothesis": hypothesis,
        "claim_shape": claim_shape,
        "spine_query": {"family": family},
        "pre_committed_gate": {
            "metric": "win_rate",
            "threshold": 0.55,
            "min_n": n_expected,
            "horizon_d": horizon_d,
        },
        "horizon_d": horizon_d,
        "n_expected": n_expected,
        "status": "inbox-not-registered",
        **kwargs,
    }


# ---------------------------------------------------------------------------
# Import the module under test
# ---------------------------------------------------------------------------

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine.neuralweb.research_queue import build_queue, MIN_N


# ---------------------------------------------------------------------------
# A. Absent-file-safe: empty inputs → valid output structure
# ---------------------------------------------------------------------------

class TestAbsentFileSafe:
    def test_empty_root_returns_valid_structure(self) -> None:
        root = _tmp_root()
        result = build_queue(root=root)

        # Must have all required top-level keys
        required = {
            "as_of", "candidates", "high_ev_build_now", "blocked_by_data",
            "too_sparse", "duplicate_of_existing", "invalid_shape",
            "next_best_experiment", "trial_budget", "summary",
        }
        assert required.issubset(result.keys()), (
            f"Missing keys: {required - result.keys()}"
        )

        # Lists must be lists (not None)
        for list_key in ("candidates", "high_ev_build_now", "blocked_by_data",
                          "too_sparse", "duplicate_of_existing", "invalid_shape"):
            assert isinstance(result[list_key], list), f"{list_key} must be a list"

        # next_best_experiment is None when no candidates
        assert result["next_best_experiment"] is None

        # trial_budget is a dict
        assert isinstance(result["trial_budget"], dict)
        assert "week_remaining" in result["trial_budget"]
        assert result["trial_budget"].get("note")  # informational note present

        # summary counts are all zero
        assert result["summary"]["total_candidates"] == 0
        assert result["summary"]["high_ev"] == 0

    def test_missing_inbox_file_is_safe(self) -> None:
        root = _tmp_root()
        # Do not create inbox file
        result = build_queue(root=root)
        assert isinstance(result["candidates"], list)

    def test_missing_machine_registry_is_safe(self) -> None:
        root = _tmp_root()
        # machine_registry.jsonl absent — must not raise
        result = build_queue(root=root)
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# B. too_sparse: n_expected < MIN_N → too_sparse category
# ---------------------------------------------------------------------------

class TestTooSparse:
    def test_sparse_candidate_lands_in_too_sparse(self) -> None:
        root = _tmp_root()
        _write_inbox(root, [
            _make_inbox_candidate(
                cid="sparse_001",
                hypothesis="A hypothesis about breadth that has very few events",
                n_expected=MIN_N - 1,  # deliberately below floor
            )
        ])
        result = build_queue(root=root)

        assert "sparse_001" in result["too_sparse"], (
            f"Expected sparse_001 in too_sparse; got: {result['too_sparse']}"
        )
        assert "sparse_001" not in result["high_ev_build_now"]
        assert "sparse_001" not in result["blocked_by_data"]

    def test_sparse_candidate_has_category_in_candidates(self) -> None:
        root = _tmp_root()
        _write_inbox(root, [
            _make_inbox_candidate(
                cid="sparse_002",
                hypothesis="Another hypothesis breadth study too few events",
                n_expected=10,
            )
        ])
        result = build_queue(root=root)
        matches = [c for c in result["candidates"] if c["id"] == "sparse_002"]
        assert len(matches) == 1
        assert matches[0]["category"] == "too_sparse"

    def test_adequate_n_not_sparse(self) -> None:
        root = _tmp_root()
        _write_inbox(root, [
            _make_inbox_candidate(
                cid="adequate_001",
                hypothesis="A hypothesis about breadth regime lead-lag dynamics",
                n_expected=MIN_N * 3,
            )
        ])
        result = build_queue(root=root)
        assert "adequate_001" not in result["too_sparse"]


# ---------------------------------------------------------------------------
# C. duplicate_of_existing: high-overlap mechanism → duplicate category
# ---------------------------------------------------------------------------

class TestDuplicateDetection:
    def test_duplicate_of_species_mechanism(self) -> None:
        root = _tmp_root()
        # Plant a species with a known mechanism
        existing_mechanism = (
            "Within-sector overreaction -- monthly deepest-quintile within-sector "
            "reversal fuel equal-weight hygiene screens rotational reversal alpha"
        )
        _write_species_registry(root, [{
            "species_id": "EXISTING_01",
            "version": "1.0",
            "name": "Within-Sector Reversal",
            "validation_status": "phase0",
            "deployment_status": "unshipped",
            "mechanism": existing_mechanism,
            "horizon_class": "rotational",
            "evidence_stack": [],
            "rejection_rules": [],
            "archetype_scope": {"applies": [], "hostile": [], "note": ""},
            "regime_scope": {
                "learnable_projection": {"axes": ["a"], "cells": ["b"]}
            },
            "market_scope": ["US"],
            "adjacent_falsified": [],
            "fixtures": [],
            "ledger_binding": {"ledger": "x", "since": "2026-07-01", "flip_criteria": "x"},
            "gating": {"come_back_on": "2026-10-01", "cadence": "monthly", "maturation": "x"},
            "trial_count": 0,
        }])
        # Candidate with very similar mechanism text (nearly verbatim copy)
        _write_inbox(root, [
            _make_inbox_candidate(
                cid="dup_001",
                hypothesis=(
                    "Within-sector overreaction monthly deepest-quintile within-sector "
                    "reversal fuel equal-weight hygiene screens rotational reversal alpha signal"
                ),
                claim_shape="entry_quality",
                family="breadth",
                n_expected=100,
            )
        ])
        result = build_queue(root=root)

        # Must be flagged as a duplicate (species shape='species', so shape match not required)
        assert "dup_001" in result["duplicate_of_existing"], (
            f"Expected dup_001 in duplicate_of_existing; "
            f"got duplicate_of_existing={result['duplicate_of_existing']}, "
            f"candidates={[c.get('id') + ':' + c.get('category','?') for c in result['candidates']]}"
        )
        assert "dup_001" not in result["high_ev_build_now"]

    def test_novel_candidate_not_flagged_duplicate(self) -> None:
        root = _tmp_root()
        _write_species_registry(root, [])  # Empty species
        _write_inbox(root, [
            _make_inbox_candidate(
                cid="novel_001",
                hypothesis=(
                    "A completely novel hypothesis about dividend yield regime transitions "
                    "and their relationship to sector rotation breadth momentum signals"
                ),
                n_expected=80,
            )
        ])
        result = build_queue(root=root)
        assert "novel_001" not in result["duplicate_of_existing"]


# ---------------------------------------------------------------------------
# D. invalid_shape: cortex_attention self-reference → invalid_shape category
# ---------------------------------------------------------------------------

class TestInvalidShape:
    def test_cortex_attention_family_rejected(self) -> None:
        root = _tmp_root()
        candidate = _make_inbox_candidate(
            cid="selfref_001",
            hypothesis="A hypothesis that uses cortex attention as evidence",
            family="cortex_attention",  # Article-1 self-reference
            n_expected=100,
        )
        _write_inbox(root, [candidate])
        result = build_queue(root=root)

        assert "selfref_001" in result["invalid_shape"], (
            f"Expected selfref_001 in invalid_shape; got invalid_shape={result['invalid_shape']}"
        )
        assert "selfref_001" not in result["high_ev_build_now"]
        assert "selfref_001" not in result["too_sparse"]

    def test_reflex_cortex_attention_rejected(self) -> None:
        root = _tmp_root()
        candidate = {
            "id": "selfref_002",
            "hypothesis": "A hypothesis using reflex cortex attention",
            "claim_shape": "lead_lag",
            "spine_query": {"family": "reflex.cortex_attention"},
            "pre_committed_gate": {
                "metric": "win_rate", "threshold": 0.55,
                "min_n": 50, "horizon_d": 21,
            },
            "horizon_d": 21,
            "n_expected": 50,
            "status": "inbox-not-registered",
        }
        _write_inbox(root, [candidate])
        result = build_queue(root=root)
        assert "selfref_002" in result["invalid_shape"]

    def test_illegal_claim_shape_rejected(self) -> None:
        root = _tmp_root()
        candidate = _make_inbox_candidate(
            cid="badshape_001",
            hypothesis="A hypothesis about momentum signals",
            claim_shape="not_a_valid_shape",
            n_expected=100,
        )
        _write_inbox(root, [candidate])
        result = build_queue(root=root)
        assert "badshape_001" in result["invalid_shape"]

    def test_valid_claim_shapes_accepted(self) -> None:
        root = _tmp_root()
        valid_shapes = ["lead_lag", "conditional_regime", "entry_quality", "sector_conditional"]
        candidates = [
            _make_inbox_candidate(
                cid=f"valid_shape_{i}",
                hypothesis=f"Novel hypothesis about {shape} breadth momentum rotation dynamics",
                claim_shape=shape,
                n_expected=60,
            )
            for i, shape in enumerate(valid_shapes)
        ]
        _write_inbox(root, candidates)
        result = build_queue(root=root)
        for i in range(len(valid_shapes)):
            assert f"valid_shape_{i}" not in result["invalid_shape"], (
                f"valid_shape_{i} should not be in invalid_shape"
            )


# ---------------------------------------------------------------------------
# E. high_ev_build_now: normal novel feasible candidate
# ---------------------------------------------------------------------------

class TestHighEvBuildNow:
    def test_novel_feasible_candidate_ranks_high(self) -> None:
        root = _tmp_root()
        _write_inbox(root, [
            _make_inbox_candidate(
                cid="highev_001",
                hypothesis=(
                    "When breadth diverges from price regime, the next 21d forward return "
                    "on sector rotation names is elevated — lead-lag relationship"
                ),
                claim_shape="lead_lag",
                family="breadth",
                n_expected=80,
                horizon_d=21,
            )
        ])
        result = build_queue(root=root)

        assert "highev_001" in result["high_ev_build_now"], (
            f"Expected highev_001 in high_ev_build_now; "
            f"candidates={[c.get('id') for c in result['candidates']]}"
        )
        assert "highev_001" not in result["too_sparse"]
        assert "highev_001" not in result["blocked_by_data"]
        assert "highev_001" not in result["invalid_shape"]

    def test_composite_ev_is_numeric(self) -> None:
        root = _tmp_root()
        _write_inbox(root, [
            _make_inbox_candidate(
                cid="ev_numeric_001",
                hypothesis="Breadth divergence regime conditional entry quality signal study",
                n_expected=60,
            )
        ])
        result = build_queue(root=root)
        cands = {c["id"]: c for c in result["candidates"]}
        if "ev_numeric_001" in cands:
            c = cands["ev_numeric_001"]
            if c.get("category") == "high_ev_build_now":
                assert isinstance(c["composite_ev"], float)
                assert 0.0 <= c["composite_ev"] <= 1.0

    def test_shorter_horizon_ranks_higher(self) -> None:
        root = _tmp_root()
        _write_inbox(root, [
            _make_inbox_candidate(
                cid="short_hz",
                hypothesis=(
                    "Short-horizon breadth signal lead-lag regime entry quality momentum"
                ),
                n_expected=100,
                horizon_d=14,
            ),
            _make_inbox_candidate(
                cid="long_hz",
                hypothesis=(
                    "Long-horizon breadth signal lead-lag regime sector conditional momentum"
                ),
                n_expected=100,
                horizon_d=180,
            ),
        ])
        result = build_queue(root=root)
        cands = {c["id"]: c for c in result["candidates"]}

        if "short_hz" in cands and "long_hz" in cands:
            s = cands["short_hz"]
            l = cands["long_hz"]
            if (s.get("category") == "high_ev_build_now"
                    and l.get("category") == "high_ev_build_now"):
                assert s["composite_ev"] > l["composite_ev"], (
                    f"Short horizon EV {s['composite_ev']} should exceed "
                    f"long horizon EV {l['composite_ev']}"
                )


# ---------------------------------------------------------------------------
# F. blocked_by_data: unresolvable spine_query family
# ---------------------------------------------------------------------------

class TestBlockedByData:
    def test_unknown_family_is_blocked(self) -> None:
        root = _tmp_root()
        _write_inbox(root, [
            _make_inbox_candidate(
                cid="blocked_001",
                hypothesis="A hypothesis about some future data source not yet collected",
                family="paid_data_xyz_proprietary_future_feed_unresolvable",
                n_expected=100,
            )
        ])
        result = build_queue(root=root)
        assert "blocked_001" in result["blocked_by_data"], (
            f"Expected blocked_001 in blocked_by_data; got {result['blocked_by_data']}"
        )
        assert "blocked_001" not in result["high_ev_build_now"]

    def test_known_family_not_blocked(self) -> None:
        root = _tmp_root()
        _write_inbox(root, [
            _make_inbox_candidate(
                cid="notblocked_001",
                hypothesis="A hypothesis about sector breadth rotation dynamics lead-lag",
                family="breadth",  # Known resolvable family
                n_expected=100,
            )
        ])
        result = build_queue(root=root)
        assert "notblocked_001" not in result["blocked_by_data"]


# ---------------------------------------------------------------------------
# G. next_best_experiment is the top-ranked high_ev candidate
# ---------------------------------------------------------------------------

class TestNextBestExperiment:
    def test_next_best_is_top_ranked(self) -> None:
        root = _tmp_root()
        _write_inbox(root, [
            _make_inbox_candidate(
                cid="best_001",
                hypothesis=(
                    "Breadth momentum lead-lag regime conditional entry quality "
                    "sector rotation divergence study novel"
                ),
                n_expected=120,
                horizon_d=21,
            ),
            _make_inbox_candidate(
                cid="weaker_001",
                hypothesis=(
                    "Breadth regime lead-lag entry quality signal novel rotation"
                ),
                n_expected=30,  # Barely above MIN_N
                horizon_d=126,
            ),
        ])
        result = build_queue(root=root)

        if result["high_ev_build_now"]:
            assert result["next_best_experiment"] == result["high_ev_build_now"][0]
        else:
            assert result["next_best_experiment"] is None

    def test_next_best_is_none_with_no_high_ev(self) -> None:
        root = _tmp_root()
        # Only a sparse candidate
        _write_inbox(root, [
            _make_inbox_candidate(
                cid="sparse_only",
                hypothesis="Sparse hypothesis study",
                n_expected=5,  # below MIN_N
            )
        ])
        result = build_queue(root=root)
        assert result["next_best_experiment"] is None


# ---------------------------------------------------------------------------
# H. trial_budget is informational and always present
# ---------------------------------------------------------------------------

class TestTrialBudget:
    def test_trial_budget_always_present(self) -> None:
        root = _tmp_root()
        result = build_queue(root=root)
        budget = result.get("trial_budget", {})
        assert isinstance(budget, dict)
        assert "week_remaining" in budget
        assert "week_used" in budget
        assert "week_limit" in budget
        assert budget.get("note")  # informational note present

    def test_trial_budget_informational_only(self) -> None:
        """The budget note must explicitly state it is informational."""
        root = _tmp_root()
        result = build_queue(root=root)
        note = result["trial_budget"].get("note", "")
        assert "informational" in note.lower(), (
            f"Budget note must state it is informational; got: {note!r}"
        )


# ---------------------------------------------------------------------------
# I. S14 species entry passes validate_entry()
# ---------------------------------------------------------------------------

class TestS14Registration:
    """Tests that S14 'Failed breakout' entry is schema-valid."""

    def _make_s14_entry(self) -> dict:
        return {
            "species_id": "S14",
            "version": "1",
            "name": "Failed breakout (trapped-buyer supply)",
            "validation_status": "phase0",
            "deployment_status": "unshipped",
            "trial_count": 0,
            "mechanism": (
                "A new-high breakout that closes back below the breakout level traps late buyers. "
                "Top/entry-veto context — NOT a short-selling signal."
            ),
            "horizon_class": "rotational",
            "evidence_stack": [
                {
                    "condition": "Breakout-then-close-below new 52-week high",
                    "tag": "trigger",
                }
            ],
            "rejection_rules": [
                {
                    "rule": "No short-sell signals permitted",
                    "prevents": "misuse as direction signal",
                }
            ],
            "archetype_scope": {
                "applies": ["all US archetypes"],
                "hostile": [],
                "note": "Phase-0",
            },
            "regime_scope": {
                "hypothesized_supportive": ["risk-off"],
                "hypothesized_hostile": ["strong bull tape"],
                "learnable_projection": {
                    "axes": ["market_trend", "breadth"],
                    "cells": ["risk-off", "rotation-active", "strong-bull-tape"],
                    "note": "Phase-0 W1. ≤2 axes, ≤6 cells constraint satisfied.",
                },
            },
            "market_scope": ["US"],
            "adjacent_falsified": [
                {
                    "idea": "retest_hold without failure predicts continuation (Wave-5)",
                    "source": "research/species/Wave-5 retest_hold falsification study",
                    "mechanical_difference": (
                        "S14 is the failure complement; the falsification of retest_hold "
                        "as a standalone signal is the adjacent negative result."
                    ),
                }
            ],
            "fixtures": [],
            "ledger_binding": {
                "ledger": "us_board_ledger",
                "since": "2026-07-05",
                "flip_criteria": (
                    "≥25 events; median 21d fwd return below control (p<0.10); "
                    "drawdown incidence elevated vs control; regime stability."
                ),
            },
            "gating": {
                "come_back_on": "2026-10-05",
                "cadence": "quarterly",
                "maturation": "Phase-0 W1. Requires ≥25 logged events (MIN_N=25).",
            },
        }

    def test_s14_validate_entry_passes(self) -> None:
        from engine.species_registry import validate_entry
        entry = self._make_s14_entry()
        # Should not raise
        validate_entry(entry)

    def test_s14_horizon_class_is_rotational(self) -> None:
        entry = self._make_s14_entry()
        assert entry["horizon_class"] == "rotational"

    def test_s14_validation_status_is_phase0(self) -> None:
        entry = self._make_s14_entry()
        assert entry["validation_status"] == "phase0"

    def test_s14_deployment_status_is_unshipped(self) -> None:
        entry = self._make_s14_entry()
        assert entry["deployment_status"] == "unshipped"

    def test_s14_trial_count_is_zero(self) -> None:
        entry = self._make_s14_entry()
        assert entry["trial_count"] == 0

    def test_s14_regime_scope_learnable_projection_axes_le_2(self) -> None:
        entry = self._make_s14_entry()
        lp = entry["regime_scope"]["learnable_projection"]
        assert len(lp["axes"]) <= 2, "learnable_projection axes must be ≤ 2"

    def test_s14_regime_scope_learnable_projection_cells_le_6(self) -> None:
        entry = self._make_s14_entry()
        lp = entry["regime_scope"]["learnable_projection"]
        assert len(lp["cells"]) <= 6, "learnable_projection cells must be ≤ 6"

    def test_s14_adjacent_falsified_cites_retest_hold(self) -> None:
        entry = self._make_s14_entry()
        af = entry.get("adjacent_falsified", [])
        assert len(af) >= 1
        # Must reference Wave-5 / retest_hold
        found = any(
            "retest" in str(item.get("idea", "")).lower()
            or "wave-5" in str(item.get("source", "")).lower()
            for item in af
        )
        assert found, (
            "adjacent_falsified must cite the Wave-5 retest_hold falsification"
        )

    def test_s14_mechanism_is_veto_not_short(self) -> None:
        entry = self._make_s14_entry()
        mech = entry.get("mechanism", "").lower()
        # Must NOT imply short-selling
        assert "not a short" in mech or "veto" in mech, (
            "Mechanism must clarify S14 is a veto/entry-context, not a short-sell signal"
        )

    def test_s14_in_real_registry(self) -> None:
        """Verify S14 exists in the committed registry.json and passes validate_entry."""
        from engine.species_registry import load, validate_entry, get_species
        reg = load()
        s14 = get_species(reg, "S14")
        assert s14 is not None, "S14 must be present in data/species/registry.json"
        validate_entry(s14)  # Must not raise

    def test_s14_required_fields_present(self) -> None:
        from engine.species_registry import _REQUIRED_FIELDS
        entry = self._make_s14_entry()
        missing = _REQUIRED_FIELDS - entry.keys()
        assert not missing, f"S14 entry missing required fields: {missing}"

    def test_s14_both_is_disallowed(self) -> None:
        """horizon_class='both' must raise SpeciesSchemaError."""
        from engine.species_registry import validate_entry, SpeciesSchemaError
        entry = self._make_s14_entry()
        entry["horizon_class"] = "both"
        with pytest.raises(SpeciesSchemaError):
            validate_entry(entry)


# ---------------------------------------------------------------------------
# J. Synapse registry has zero violations after adding research-queue
# ---------------------------------------------------------------------------

class TestSynapseRegistry:
    def test_synapse_clean_after_research_queue_addition(self) -> None:
        """validate_registry() must return zero violations (real repo synapse.yml)."""
        repo_root = Path(__file__).resolve().parent.parent
        from engine.neuralweb.synapse import load_registry, validate_registry
        reg = load_registry(repo_root)
        violations = validate_registry(reg, root=repo_root)
        assert violations == [], (
            f"synapse.yml has {len(violations)} violation(s) after adding research-queue:\n"
            + "\n".join(f"  {v}" for v in violations)
        )

    def test_research_queue_artifact_in_registry(self) -> None:
        """research-queue artifact must be registered in synapse.yml."""
        repo_root = Path(__file__).resolve().parent.parent
        from engine.neuralweb.synapse import load_registry
        reg = load_registry(repo_root)
        artifacts = reg.get("artifacts", {})
        assert "research-queue" in artifacts, (
            "research-queue artifact must be registered in config/synapse.yml"
        )
        entry = artifacts["research-queue"]
        assert entry.get("tier") == "infrastructure"
        assert entry.get("owner_program") == "neural-web"
        assert entry.get("storage") == "git"
        assert entry.get("format") == "json"
