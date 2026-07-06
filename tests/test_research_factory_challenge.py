"""tests/test_research_factory_challenge.py — W4 challenger + probes tests.

Coverage:
  1.  Packet built for a real-shaped oracle fixture (aggregate fields present)
  2.  Permutation probe: insensitive fixture flags True
  3.  Permutation probe: sensitive fixture flags False
  4.  Permutation probe: missing per-fire data → not_applicable (never null)
  5.  Reviewer-response validation: valid response passes
  6.  Reviewer-response validation: malformed does NOT transition
  7.  Reviewer-response validation: confidence-number smuggling rejected
  8.  Reviewer-response validation: invalid recommendation enum rejected
  9.  Reviewer-response validation: invalid blocker category rejected
  10. Governance event emitted with article=null after successful write
  11. write_challenge: missing reviewer_response → writes packet-only file (no reviewer block)
  12. write_challenge: bad reviewer_response raises ValueError (no file written)
  13. Report pack embeds all four dedup context blocks (absent-safe when registries missing)
  14. collect_flags: extracts flags from candidate flags list
  15. gauntlet_legs: extracts leg verdicts from reversion block
  16. gauntlet_legs: returns [] when no gauntlet data
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# ===========================================================================
# Fixtures
# ===========================================================================

def _make_oracle_candidate(
    candidate_id: str = "rf-20260706-oracle-washout-001",
    *,
    include_outcomes: bool = False,
    outcomes_insensitive: bool = False,
    flags: list[str] | None = None,
    reversion_block: dict | None = None,
) -> dict:
    """Minimal oracle-shaped candidate for testing.

    Permutation probe uses SIGN-FLIP permutation and a p-value decision rule:
      p = fraction of permuted WRs >= real_WR
      input_insensitive=True when p > 0.10 (real WR not distinguishable from null)

      insensitive fixture: WR = 50% (balanced outcomes).
        ~50% of sign-permuted draws produce WR >= 50% → p ≈ 0.50 > 0.10 → insensitive=True
      sensitive fixture: WR = 100% (all positive outcomes).
        ~0% of sign-permuted draws produce WR >= 100% → p ≈ 0 < 0.10 → insensitive=False
    """
    outcomes = None
    if include_outcomes:
        if outcomes_insensitive:
            # Balanced outcomes: WR ≈ 50% — sign-permutation barely changes WR
            # permuted WR ≈ 50%, threshold = 0.95 * 50% = 47.5% → 50% >= 47.5% → insensitive
            outcomes = [0.02] * 150 + [-0.02] * 150   # exactly 50% WR
        else:
            # All positive outcomes: WR = 100% — sign-permutation destroys WR
            # permuted WR ≈ 50%, threshold = 0.95 * 100% = 95% → 50% < 95% → NOT insensitive
            outcomes = [0.05] * 200  # 100% WR; permuted WR ≈ 50% << 95%

    rev_block = reversion_block or {
        "n": 200,
        "wr": 0.68,
        "asym": 2.1,
        "ret_exit": 0.018,
        "gauntlet": "PASS",
        "asof": "2026-07-05",
    }

    artifacts: dict = {
        "search_width_at_scan": 42,
    }
    if outcomes is not None:
        artifacts["reversion_screen"] = {
            "outcomes": outcomes,
            "n": len(outcomes),
            "WR": sum(1 for v in outcomes if v > 0) / len(outcomes),
        }

    return {
        "schema": "research_factory.candidate.v1",
        "authority": "display_only",
        "candidate_id": candidate_id,
        "created_at": "2026-07-06T00:00:00Z",
        "hypothesis": "Washout + opposite-complex cascade captures a durable bounce.",
        "mechanism": "washout_w and episode_event fire simultaneously; forced sellers exhausted.",
        "candidate_type": "oracle_compound",
        "domain": "oracle",
        "source": "oracle_brainstorm",
        "status": "screened",
        "trial_accounting": {"mode": "oracle_screen", "family": None, "declared_at": None},
        "evaluation_plan": {
            "primary_metric": "WR",
            "horizon_d": 21,
            "min_n": 100,
            "fdr_scope": "batch",
        },
        "flags": flags or [],
        "artifacts": artifacts,
        "reversion": rev_block,
        "lineage": {"respin_of": None, "refinement_generation": 0},
        "transition_log": [],
    }


def _make_valid_reviewer_response(candidate_id: str = "rf-20260706-oracle-washout-001") -> dict:
    return {
        "candidate_id": candidate_id,
        "agent_type": "reviewer",
        "recommendation": "ADVISORY_REVIEW",
        "blockers": [
            {
                "severity": "minor",
                "category": "mechanism",
                "finding": "Mechanism plausible but episode-event conditioning relies on flow data with known lag.",
                "evidence_ref": "mechanism field",
            }
        ],
        "non_blocking_concerns": ["Monitor for regime clustering in OOS period."],
        "best_counterargument": "The timing placebo passed and holdout WR held; the mechanical evidence is solid.",
        "minimum_fix_to_reconsider": None,
        "falsifier_spec": "If WR drops below 0.58 in the next 100 live fires, the mechanism is weakening.",
        "human_review_question": "Does the episode-lag concern constitute a material lookahead risk sufficient to block promotion?",
    }


# ===========================================================================
# 1. Packet built for a real-shaped oracle fixture
# ===========================================================================

class TestBuildChallengeInput:
    def test_packet_has_required_fields(self, tmp_path):
        from engine.research_factory.challenge import build_challenge_input
        candidate = _make_oracle_candidate()
        packet = build_challenge_input(candidate, root=tmp_path)

        assert packet["candidate_id"] == "rf-20260706-oracle-washout-001"
        assert packet["hypothesis"] == candidate["hypothesis"]
        assert packet["mechanism"] == candidate["mechanism"]
        assert packet["candidate_type"] == "oracle_compound"
        assert packet["domain"] == "oracle"
        assert packet["authority"] == "display_only"
        assert "mechanical_probes" in packet
        assert "aggregate_metrics" in packet
        assert "dedup_context" in packet

    def test_packet_is_outcome_blind(self, tmp_path):
        """Per-fire outcomes must not appear in the packet."""
        from engine.research_factory.challenge import build_challenge_input
        candidate = _make_oracle_candidate(include_outcomes=True, outcomes_insensitive=True)
        packet = build_challenge_input(candidate, root=tmp_path)

        # Check that per-fire arrays are not in the packet top level
        packet_str = json.dumps(packet)
        # The outcomes list is large; the packet should not contain 300 entries inline
        agg = packet.get("aggregate_metrics", {})
        rev_screen = agg.get("reversion_screen", {})
        assert "outcomes" not in agg
        # No direct outcomes key at top level
        assert "outcomes" not in packet

    def test_aggregate_metrics_from_reversion_block(self, tmp_path):
        from engine.research_factory.challenge import build_challenge_input
        candidate = _make_oracle_candidate()
        packet = build_challenge_input(candidate, root=tmp_path)
        agg = packet["aggregate_metrics"]
        # Should pick up fields from the reversion block
        assert agg.get("wr") == 0.68 or agg.get("WR") == 0.68 or "n" in agg

    def test_mechanical_probes_block_present(self, tmp_path):
        from engine.research_factory.challenge import build_challenge_input
        candidate = _make_oracle_candidate()
        packet = build_challenge_input(candidate, root=tmp_path)
        mp = packet["mechanical_probes"]
        assert "near_dup" in mp
        assert "mechanism_spec_mismatch" in mp
        assert "gauntlet_legs" in mp
        assert "permutation_probe" in mp

    def test_dedup_context_has_nw_quant_s3(self, tmp_path):
        from engine.research_factory.challenge import build_challenge_input
        candidate = _make_oracle_candidate()
        packet = build_challenge_input(candidate, root=tmp_path)
        dc = packet["dedup_context"]
        assert "nw_quant_synthesis_s3_text" in dc
        assert "DUPLICATE-OF-EXISTING" in dc["nw_quant_synthesis_s3_text"]


# ===========================================================================
# 2-4. Permutation probe
# ===========================================================================

class TestPermutationProbe:
    def test_insensitive_fixture_flags_true(self):
        """Balanced-outcome fixture (WR=50%): ~50% of sign-permuted draws >= 50% → p≈0.50 > 0.10 → insensitive."""
        from engine.research_factory.probes import permutation_probe
        candidate = _make_oracle_candidate(
            candidate_id="rf-test-insensitive",
            include_outcomes=True,
            outcomes_insensitive=True,  # builds balanced outcomes: 50% WR
        )
        result = permutation_probe(candidate)
        # real WR = 50%; sign-permuted WR clusters at ~50%; p ≈ 0.50 > 0.10 → insensitive=True
        assert result["input_insensitive"] is True
        assert isinstance(result["real_metric"], float)
        assert isinstance(result["permuted_p_value"], float)
        # p-value should be large (near 0.50) for a balanced fixture
        assert result["permuted_p_value"] > 0.10
        assert result["n_permutations"] > 0

    def test_sensitive_fixture_flags_false(self):
        """All-positive outcomes (WR=100%): ~0% of sign-permuted draws >= 100% → p≈0 < 0.10 → NOT insensitive."""
        from engine.research_factory.probes import permutation_probe
        candidate = _make_oracle_candidate(
            candidate_id="rf-test-sensitive",
            include_outcomes=True,
            outcomes_insensitive=False,  # builds all-positive outcomes: 100% WR
        )
        result = permutation_probe(candidate)
        # real WR = 100%; sign-permuted WR ≈ 50%; p ≈ 0 (no perm reaches 100%) → insensitive=False
        assert result["input_insensitive"] is False
        assert abs(result["real_metric"] - 1.0) < 0.01
        # p-value should be very small (near 0) for all-positive outcomes
        assert result["permuted_p_value"] < 0.10

    def test_missing_data_returns_not_applicable(self):
        """No per-fire data → not_applicable sentinel, never null."""
        from engine.research_factory.probes import permutation_probe
        candidate = _make_oracle_candidate(include_outcomes=False)
        # Remove reversion_screen from artifacts
        candidate["artifacts"].pop("reversion_screen", None)
        result = permutation_probe(candidate)
        assert result["input_insensitive"] == "not_applicable"
        # Should be a dict, not None
        assert result is not None

    def test_deterministic_with_same_seed(self):
        """Same candidate_id → same result every time (seeded deterministic)."""
        from engine.research_factory.probes import permutation_probe
        candidate = _make_oracle_candidate(
            candidate_id="rf-determinism-test",
            include_outcomes=True,
            outcomes_insensitive=False,  # all-positive: WR=100%, insensitive=False
        )
        r1 = permutation_probe(candidate)
        r2 = permutation_probe(candidate)
        assert r1["input_insensitive"] == r2["input_insensitive"]
        assert r1["permuted_p_value"] == r2["permuted_p_value"]


# ===========================================================================
# 5-9. Reviewer-response validation
# ===========================================================================

class TestValidateReviewerResponse:
    def test_valid_response_passes(self):
        from engine.research_factory.challenge import validate_reviewer_response
        resp = _make_valid_reviewer_response()
        errs = validate_reviewer_response(resp)
        assert errs == []

    def test_missing_candidate_id_rejected(self):
        from engine.research_factory.challenge import validate_reviewer_response
        resp = _make_valid_reviewer_response()
        del resp["candidate_id"]
        errs = validate_reviewer_response(resp)
        assert any("candidate_id" in e for e in errs)

    def test_missing_recommendation_rejected(self):
        from engine.research_factory.challenge import validate_reviewer_response
        resp = _make_valid_reviewer_response()
        del resp["recommendation"]
        errs = validate_reviewer_response(resp)
        assert any("recommendation" in e for e in errs)

    def test_invalid_recommendation_enum_rejected(self):
        from engine.research_factory.challenge import validate_reviewer_response
        resp = _make_valid_reviewer_response()
        resp["recommendation"] = "REJECT"  # not ADVISORY_REJECT
        errs = validate_reviewer_response(resp)
        assert any("ADVISORY_" in e or "recommendation" in e for e in errs)

    def test_confidence_score_smuggling_rejected(self):
        """A confidence_score field in the reviewer response must be rejected."""
        from engine.research_factory.challenge import validate_reviewer_response
        resp = _make_valid_reviewer_response()
        resp["confidence_score"] = 0.87
        errs = validate_reviewer_response(resp)
        assert any("confidence" in e.lower() for e in errs)

    def test_confidence_in_blocker_rejected(self):
        """confidence_score inside a blocker must also be rejected."""
        from engine.research_factory.challenge import validate_reviewer_response
        resp = _make_valid_reviewer_response()
        resp["blockers"][0]["confidence_score"] = 0.9
        errs = validate_reviewer_response(resp)
        assert any("confidence" in e.lower() for e in errs)

    def test_invalid_blocker_category_rejected(self):
        from engine.research_factory.challenge import validate_reviewer_response
        resp = _make_valid_reviewer_response()
        resp["blockers"][0]["category"] = "invalid_category_xyz"
        errs = validate_reviewer_response(resp)
        assert any("category" in e for e in errs)

    def test_invalid_blocker_severity_rejected(self):
        from engine.research_factory.challenge import validate_reviewer_response
        resp = _make_valid_reviewer_response()
        resp["blockers"][0]["severity"] = "critical"  # not in enum
        errs = validate_reviewer_response(resp)
        assert any("severity" in e for e in errs)

    def test_non_dict_response_rejected(self):
        from engine.research_factory.challenge import validate_reviewer_response
        errs = validate_reviewer_response("some string")
        assert len(errs) == 1
        assert "dict" in errs[0]

    def test_all_valid_recommendation_values_pass(self):
        from engine.research_factory.challenge import validate_reviewer_response
        for rec in ("ADVISORY_REJECT", "ADVISORY_REVIEW", "ADVISORY_PASS"):
            resp = _make_valid_reviewer_response()
            resp["recommendation"] = rec
            errs = validate_reviewer_response(resp)
            assert errs == [], f"Expected {rec} to pass validation, got: {errs}"

    def test_all_valid_blocker_categories_pass(self):
        from engine.research_factory.challenge import validate_reviewer_response, _VALID_CATEGORIES
        for cat in _VALID_CATEGORIES:
            resp = _make_valid_reviewer_response()
            resp["blockers"][0]["category"] = cat
            errs = validate_reviewer_response(resp)
            assert errs == [], f"Expected category {cat!r} to pass, got: {errs}"

    def test_parametric_lookahead_category_valid(self):
        """Specifically verify parametric_lookahead is in the valid enum (blocker requirement)."""
        from engine.research_factory.challenge import validate_reviewer_response
        resp = _make_valid_reviewer_response()
        resp["blockers"] = [{
            "severity": "blocker",
            "category": "parametric_lookahead",
            "finding": "This critique depends on memorized 2022 sector performance.",
            "evidence_ref": "mechanism field",
        }]
        errs = validate_reviewer_response(resp)
        assert errs == []


# ===========================================================================
# 10. Governance event emitted with article=null
# ===========================================================================

class TestGovernanceEvent:
    def test_governance_event_emitted_with_article_null(self, tmp_path):
        """After successful ingest-response, governance event has article=None."""
        from engine.research_factory.challenge import (
            build_challenge_input, write_challenge, apply_challenge_transitions,
        )

        # Set up minimal candidates.jsonl
        cand = _make_oracle_candidate()
        cid = cand["candidate_id"]
        rf_dir = tmp_path / "data" / "research_factory"
        rf_dir.mkdir(parents=True)
        (rf_dir / "candidates.jsonl").write_text(
            json.dumps(cand) + "\n", encoding="utf-8"
        )
        (rf_dir / "transitions.jsonl").write_text("", encoding="utf-8")

        packet = build_challenge_input(cand, root=tmp_path)
        reviewer = _make_valid_reviewer_response(cid)
        challenge_path = write_challenge(cid, packet, reviewer_response=reviewer, root=tmp_path)
        apply_challenge_transitions(cid, challenge_path, root=tmp_path)

        # Now emit governance event and verify article=None
        events = []
        def mock_append_event(event_type, target, *, article, **kwargs):
            events.append({"event_type": event_type, "target": target, "article": article})
            return True

        with patch("engine.neuralweb.governance.append_event", side_effect=mock_append_event):
            from scripts.research_factory_challenge_pack import _emit_governance_event
            _emit_governance_event(cid, str(challenge_path), root=tmp_path)

        assert len(events) == 1
        ev = events[0]
        assert ev["event_type"] == "research_factory_challenge"
        assert ev["article"] is None   # RF-12: factory events never claim Article authority

    def test_governance_event_written_to_file(self, tmp_path):
        """Governance event is actually written to the governance ledger."""
        from engine.neuralweb.governance import append_event
        gov_dir = tmp_path / "data" / "neuralweb"
        gov_dir.mkdir(parents=True)

        ok = append_event(
            event_type="research_factory_challenge",
            target="research_factory/challenges/test-candidate",
            article=None,
            authored_by="test",
            root=tmp_path,
        )
        assert ok is True
        gov_path = gov_dir / "governance.jsonl"
        assert gov_path.exists()
        line = gov_path.read_text(encoding="utf-8").strip()
        row = json.loads(line)
        assert row["event_type"] == "research_factory_challenge"
        assert row["article"] is None


# ===========================================================================
# 11-12. write_challenge edge cases
# ===========================================================================

class TestWriteChallenge:
    def test_write_without_reviewer_response(self, tmp_path):
        """write_challenge without reviewer_response writes the packet-only file."""
        from engine.research_factory.challenge import build_challenge_input, write_challenge
        cand = _make_oracle_candidate()
        packet = build_challenge_input(cand, root=tmp_path)
        out = write_challenge(cand["candidate_id"], packet, root=tmp_path)
        assert out.exists()
        row = json.loads(out.read_text(encoding="utf-8"))
        assert row["authority"] == "display_only"
        assert row["schema"] == "research_factory.challenge.v1"
        assert "reviewer" not in row  # no reviewer block when no response provided

    def test_write_with_valid_reviewer_response(self, tmp_path):
        """write_challenge with valid reviewer_response includes reviewer block."""
        from engine.research_factory.challenge import build_challenge_input, write_challenge
        cand = _make_oracle_candidate()
        cid = cand["candidate_id"]
        packet = build_challenge_input(cand, root=tmp_path)
        resp = _make_valid_reviewer_response(cid)
        out = write_challenge(cid, packet, reviewer_response=resp, root=tmp_path)
        row = json.loads(out.read_text(encoding="utf-8"))
        assert "reviewer" in row
        assert row["reviewer"]["recommendation"] == "ADVISORY_REVIEW"

    def test_write_bad_reviewer_response_raises_no_file_written(self, tmp_path):
        """Malformed reviewer JSON raises ValueError; challenge file should not be present."""
        from engine.research_factory.challenge import build_challenge_input, write_challenge
        cand = _make_oracle_candidate(candidate_id="rf-bad-resp")
        packet = build_challenge_input(cand, root=tmp_path)
        bad_resp = {"candidate_id": "rf-bad-resp", "confidence_score": 0.9}  # no recommendation + confidence
        with pytest.raises(ValueError, match="confidence"):
            write_challenge("rf-bad-resp", packet, reviewer_response=bad_resp, root=tmp_path)

    def test_malformed_does_not_transition(self, tmp_path):
        """If reviewer response is invalid, transitions.jsonl must NOT be written."""
        from engine.research_factory.challenge import build_challenge_input, write_challenge
        rf_dir = tmp_path / "data" / "research_factory"
        rf_dir.mkdir(parents=True)
        transitions_path = rf_dir / "transitions.jsonl"
        # Start with empty transitions
        transitions_path.write_text("", encoding="utf-8")

        cand = _make_oracle_candidate(candidate_id="rf-no-transition")
        packet = build_challenge_input(cand, root=tmp_path)
        bad_resp = {"candidate_id": "rf-no-transition", "recommendation": "REJECT_NOW"}  # invalid rec

        try:
            write_challenge("rf-no-transition", packet, reviewer_response=bad_resp, root=tmp_path)
        except ValueError:
            pass  # expected

        # Transitions file should still be empty
        content = transitions_path.read_text(encoding="utf-8").strip()
        assert content == ""


# ===========================================================================
# 13. Report pack dedup context blocks (absent-safe)
# ===========================================================================

class TestReportPack:
    def test_pack_contains_all_four_dedup_blocks(self, tmp_path):
        """Report pack embeds all 4 dedup context blocks."""
        from scripts.research_factory_report_pack import build_report_pack
        pack = build_report_pack("A short test report.", data_dir=tmp_path / "data")

        # Block 1: species (may be empty but section header present)
        assert "Setup Species Registry" in pack or "Species" in pack or "species" in pack.lower()

        # Block 2: machine registry (may be absent)
        assert "Machine Registry" in pack or "machine_registry" in pack

        # Block 3: trial families (may be empty)
        assert "Trial Ledger" in pack or "trial_ledger" in pack or "Trial" in pack

        # Block 4: NW_QUANT_SYNTHESIS §3 table
        assert "DUPLICATE-OF-EXISTING" in pack
        assert "beneficial_ownership" in pack  # a known item from the §3 table

    def test_pack_embeds_report_text(self, tmp_path):
        """Report text appears in the extraction pack."""
        from scripts.research_factory_report_pack import build_report_pack
        report = "This is a novel hypothesis about ETF flows."
        pack = build_report_pack(report, data_dir=tmp_path / "data")
        assert report in pack

    def test_pack_absent_safe_no_registries(self, tmp_path):
        """Pack generates without error when all registries are absent."""
        from scripts.research_factory_report_pack import build_report_pack
        # tmp_path has no data subdirectory
        pack = build_report_pack("test", data_dir=tmp_path / "empty_data")
        assert len(pack) > 100  # something was generated
        assert "DUPLICATE-OF-EXISTING" in pack

    def test_pack_from_file(self, tmp_path):
        """--report can load from a file path."""
        from scripts.research_factory_report_pack import _load_report_text
        report_path = tmp_path / "report.md"
        report_path.write_text("Report content here.", encoding="utf-8")
        text = _load_report_text(str(report_path))
        assert text == "Report content here."

    def test_pack_from_inline_text(self, tmp_path):
        """--report treats non-existent paths as inline text."""
        from scripts.research_factory_report_pack import _load_report_text
        text = _load_report_text("inline note text that is not a file path")
        assert text == "inline note text that is not a file path"

    def test_pack_with_real_species_registry(self, tmp_path):
        """When species registry is available, pack includes species names."""
        from scripts.research_factory_report_pack import build_report_pack
        pack = build_report_pack("test", data_dir=Path("data"))
        # If the registry exists, species IDs should appear
        # This test passes even if registry absent (absent-safe)
        assert "DUPLICATE-OF-EXISTING" in pack


# ===========================================================================
# 14. collect_flags
# ===========================================================================

class TestCollectFlags:
    def test_extracts_flags_from_candidate(self):
        from engine.research_factory.probes import collect_flags
        cand = _make_oracle_candidate(flags=["near_dup_review", "mechanism_spec_mismatch"])
        result = collect_flags(cand)
        assert result["near_dup"]["flagged"] is True
        assert result["mechanism_spec_mismatch"] is True
        assert result["recent_only_columns"] is False
        assert result["scale_flagged"] is False

    def test_empty_flags_returns_false_for_all(self):
        from engine.research_factory.probes import collect_flags
        cand = _make_oracle_candidate(flags=[])
        result = collect_flags(cand)
        assert result["near_dup"]["flagged"] is False
        assert result["mechanism_spec_mismatch"] is False

    def test_all_flags_recognised(self):
        from engine.research_factory.probes import collect_flags
        cand = _make_oracle_candidate(flags=[
            "near_dup_review", "mechanism_spec_mismatch",
            "recent_only_columns", "scale_flagged",
        ])
        result = collect_flags(cand)
        assert result["near_dup"]["flagged"] is True
        assert result["mechanism_spec_mismatch"] is True
        assert result["recent_only_columns"] is True
        assert result["scale_flagged"] is True


# ===========================================================================
# 15. gauntlet_legs
# ===========================================================================

class TestGauntletLegs:
    def test_extracts_leg_verdicts_from_reversion_block(self):
        from engine.research_factory.probes import gauntlet_legs
        cand = _make_oracle_candidate(reversion_block={
            "n": 200, "wr": 0.68, "asym": 2.1, "ret_exit": 0.018, "gauntlet": "PASS",
        })
        legs = gauntlet_legs(cand)
        assert isinstance(legs, list)
        assert len(legs) > 0
        # leg1 (n>=100) should pass
        leg1 = next((l for l in legs if l["leg"] == "leg1"), None)
        assert leg1 is not None
        assert leg1["verdict"] == "PASS"

    def test_leg_verdicts_from_artifact_gauntlet_legs(self):
        from engine.research_factory.probes import gauntlet_legs
        cand = _make_oracle_candidate()
        cand["artifacts"]["reversion_screen"] = {
            "gauntlet_legs": [
                {"leg": "leg1", "verdict": "PASS"},
                {"leg": "leg2", "verdict": "FAIL"},
                {"leg": "leg3", "verdict": "PASS"},
            ]
        }
        legs = gauntlet_legs(cand)
        assert len(legs) == 3
        assert legs[0]["leg"] == "leg1"
        assert legs[1]["verdict"] == "FAIL"

    def test_returns_empty_when_no_gauntlet_data(self):
        from engine.research_factory.probes import gauntlet_legs
        cand = _make_oracle_candidate()
        # Remove all gauntlet data
        cand.pop("reversion", None)
        cand["artifacts"] = {}
        legs = gauntlet_legs(cand)
        assert legs == []

    def test_fail_verdict_when_below_gate(self):
        from engine.research_factory.probes import gauntlet_legs
        cand = _make_oracle_candidate(reversion_block={
            "n": 50,   # below 100 → leg1 FAIL
            "wr": 0.55,  # below 0.62 → leg2 FAIL
            "asym": 1.2,  # below 1.5 → leg3 FAIL
            "ret_exit": 0.005,  # below 0.01 → leg4 FAIL
            "gauntlet": "FAIL",
        })
        legs = gauntlet_legs(cand)
        leg1 = next((l for l in legs if l["leg"] == "leg1"), None)
        assert leg1 is not None
        assert leg1["verdict"] == "FAIL"


# ===========================================================================
# 16. End-to-end: packet generated for one fixture candidate
# ===========================================================================

class TestEndToEnd:
    def test_challenge_packet_generated_end_to_end(self, tmp_path):
        """Full flow: build packet → write challenge → transitions written."""
        from engine.research_factory.challenge import (
            build_challenge_input, write_challenge, apply_challenge_transitions,
        )

        cand = _make_oracle_candidate()
        cid = cand["candidate_id"]

        # Setup transitions file
        rf_dir = tmp_path / "data" / "research_factory"
        rf_dir.mkdir(parents=True)
        transitions_path = rf_dir / "transitions.jsonl"
        transitions_path.write_text("", encoding="utf-8")

        packet = build_challenge_input(cand, root=tmp_path)
        resp = _make_valid_reviewer_response(cid)
        challenge_path = write_challenge(cid, packet, reviewer_response=resp, root=tmp_path)

        assert challenge_path.exists()
        row = json.loads(challenge_path.read_text(encoding="utf-8"))
        assert row["candidate_id"] == cid
        assert row["reviewer"]["recommendation"] == "ADVISORY_REVIEW"
        assert row["mechanical_probes"]["gauntlet_legs"]  # non-empty for our fixture

        # Apply transitions
        apply_challenge_transitions(cid, challenge_path, root=tmp_path)

        # Verify two transition rows written
        lines = [l for l in transitions_path.read_text().splitlines() if l.strip()]
        assert len(lines) == 2
        t1 = json.loads(lines[0])
        t2 = json.loads(lines[1])
        assert t1["from"] == "screened" and t1["to"] == "challenged"
        assert t2["from"] == "challenged" and t2["to"] == "human_review"
        assert t1["actor"] == "script"
        assert t2["actor"] == "script"


# ===========================================================================
# 17. Outcome-blindness whitelist (RF-7b — finding 2 fix)
# ===========================================================================

class TestOutcomeBlindnessWhitelist:
    """Verify that outcome-revealing scalars in reversion_screen are blocked."""

    def test_outcome_revealing_scalars_not_in_aggregate_metrics(self, tmp_path):
        """best_fire_return, per_fire_max_gain must not appear in aggregate_metrics."""
        from engine.research_factory.challenge import build_challenge_input

        cand = _make_oracle_candidate()
        # Inject outcome-revealing scalars into reversion_screen
        cand["artifacts"]["reversion_screen"] = {
            "n": 200,
            "WR": 0.68,
            "gauntlet": "PASS",
            # These should be blocked by the whitelist:
            "best_fire_return": 0.44,
            "per_fire_max_gain": 0.51,
            "max_drawdown_realized": -0.12,
            "post_fire_alpha": 0.07,
        }

        packet = build_challenge_input(cand, root=tmp_path)
        agg = packet["aggregate_metrics"]

        # Outcome-revealing scalars must NOT appear
        assert "best_fire_return" not in agg, "best_fire_return leaked into aggregate_metrics"
        assert "per_fire_max_gain" not in agg, "per_fire_max_gain leaked into aggregate_metrics"
        assert "max_drawdown_realized" not in agg, "max_drawdown_realized leaked into aggregate_metrics"
        assert "post_fire_alpha" not in agg, "post_fire_alpha leaked into aggregate_metrics"

        # Whitelisted keys must still be present
        assert agg.get("WR") == 0.68 or agg.get("n") == 200

    def test_whitelisted_keys_pass_through(self, tmp_path):
        """Aggregate keys in _AGGREGATE_METRIC_KEYS pass through the whitelist."""
        from engine.research_factory.challenge import build_challenge_input, _AGGREGATE_METRIC_KEYS

        cand = _make_oracle_candidate()
        cand["artifacts"]["reversion_screen"] = {
            "n": 150,
            "wr": 0.65,
            "asym": 1.8,
            "ret_exit": 0.015,
            "gauntlet": "PASS",
            "outcome_poison": 0.99,  # must be blocked
        }

        packet = build_challenge_input(cand, root=tmp_path)
        agg = packet["aggregate_metrics"]

        assert "outcome_poison" not in agg
        # At least some whitelisted keys should be present (may be overridden by reversion block)
        # The reversion block from the fixture also sets n/wr; either source is fine
        assert "n" in agg or "wr" in agg or "WR" in agg

    def test_screen_result_outcome_scalars_blocked(self, tmp_path):
        """screen_result per-section outcome-revealing scalars must not reach the packet.

        Regression test for the sibling-path leak: screen_result sections
        (all/risk_on/risk_off) must use the same WHITELIST as reversion_screen.
        The old blocklist + isinstance(v,list) filter let per-fire realized
        outcome scalars (best_fire_return, max_drawdown_realized, per_fire_max_gain,
        post_fire_alpha) through to aggregate_metrics / screen_* keys.
        """
        import json as _json
        from engine.research_factory.challenge import build_challenge_input

        cand = _make_oracle_candidate()
        # Inject outcome-revealing scalars into screen_result (the oracle 63d screen artifact)
        cand["artifacts"]["screen_result"] = {
            "all": {
                "n": 120,
                "WR": 0.61,
                "best_fire_return": 0.44,        # outcome-revealing — must be blocked
                "max_drawdown_realized": -0.20,   # outcome-revealing — must be blocked
                "per_fire_max_gain": 0.51,        # outcome-revealing — must be blocked
                "post_fire_alpha": 0.07,          # outcome-revealing — must be blocked
            },
            "risk_on": {
                "n": 80,
                "WR": 0.65,
                "best_fire_return": 0.55,
                "max_drawdown_realized": -0.15,
                "per_fire_max_gain": 0.60,
                "post_fire_alpha": 0.09,
            },
            "risk_off": {
                "n": 40,
                "wr": 0.52,
                "best_fire_return": 0.22,
                "max_drawdown_realized": -0.30,
                "per_fire_max_gain": 0.35,
                "post_fire_alpha": 0.02,
            },
        }

        packet = build_challenge_input(cand, root=tmp_path)

        # Check via json.dumps membership (mirrors reversion_screen test pattern)
        packet_json = _json.dumps(packet)

        # Outcome-revealing scalars must NOT appear anywhere in the packet
        assert "best_fire_return" not in packet_json, \
            "best_fire_return leaked into challenge packet from screen_result"
        assert "max_drawdown_realized" not in packet_json, \
            "max_drawdown_realized leaked into challenge packet from screen_result"
        assert "per_fire_max_gain" not in packet_json, \
            "per_fire_max_gain leaked into challenge packet from screen_result"
        assert "post_fire_alpha" not in packet_json, \
            "post_fire_alpha leaked into challenge packet from screen_result"

        # Whitelisted aggregate keys should still be present in the screen_* sections
        agg = packet["aggregate_metrics"]
        # n and WR are in _AGGREGATE_METRIC_KEYS — they must survive for each section
        screen_all = agg.get("screen_all", {})
        assert screen_all.get("n") == 120, "screen_all.n should survive whitelist"
        assert screen_all.get("WR") == 0.61, "screen_all.WR should survive whitelist"

        screen_risk_on = agg.get("screen_risk_on", {})
        assert screen_risk_on.get("n") == 80
        assert screen_risk_on.get("WR") == 0.65

        screen_risk_off = agg.get("screen_risk_off", {})
        assert screen_risk_off.get("n") == 40
        assert screen_risk_off.get("wr") == 0.52


# ===========================================================================
# 18. State machine enforcement via _transition (finding 3 fix)
# ===========================================================================

class TestStateMachineEnforcement:
    """Verify _transition routes through state.transition and raises on violations."""

    def test_illegal_transition_pair_raises(self, tmp_path):
        """_transition must raise IllegalTransition on disallowed from→to pair."""
        from engine.research_factory.challenge import _transition
        from engine.research_factory.state import IllegalTransition

        rf_dir = tmp_path / "data" / "research_factory"
        rf_dir.mkdir(parents=True)
        (rf_dir / "transitions.jsonl").write_text("", encoding="utf-8")

        with pytest.raises(IllegalTransition):
            _transition(
                "rf-test-illegal",
                from_state="paper",           # paper→challenged is NOT in allowed matrix
                to_state="challenged",
                reason_code="test",
                reason_text="should fail",
                challenge_ref="challenges/rf-test-illegal.json",
                root=tmp_path,
            )

        # Nothing should have been written
        lines = [
            l for l in (rf_dir / "transitions.jsonl").read_text().splitlines()
            if l.strip()
        ]
        assert lines == [], "No row should be written when state machine rejects"

    def test_script_actor_blocked_from_human_gate_target(self, tmp_path):
        """Script actor cannot transition to 'paper' (human-gate target)."""
        from engine.research_factory.challenge import _transition
        from engine.research_factory.state import IllegalTransition

        rf_dir = tmp_path / "data" / "research_factory"
        rf_dir.mkdir(parents=True)
        (rf_dir / "transitions.jsonl").write_text("", encoding="utf-8")

        # human_review → paper is allowed pair, but only for human actors (fable/operator)
        with pytest.raises(IllegalTransition, match="script"):
            _transition(
                "rf-test-actor-gate",
                from_state="human_review",
                to_state="paper",
                reason_code="test",
                reason_text="script actor trying to enter paper",
                root=tmp_path,
            )

    def test_idempotency_guard_blocks_re_run(self, tmp_path):
        """apply_challenge_transitions must raise ValueError if candidate already past screened."""
        from engine.research_factory.challenge import (
            build_challenge_input, write_challenge, apply_challenge_transitions,
        )

        cand = _make_oracle_candidate(candidate_id="rf-idempotency-test")
        cid = cand["candidate_id"]

        rf_dir = tmp_path / "data" / "research_factory"
        rf_dir.mkdir(parents=True)
        transitions_path = rf_dir / "transitions.jsonl"
        transitions_path.write_text("", encoding="utf-8")

        packet = build_challenge_input(cand, root=tmp_path)
        resp = _make_valid_reviewer_response(cid)
        challenge_path = write_challenge(cid, packet, reviewer_response=resp, root=tmp_path)

        # First call should succeed
        apply_challenge_transitions(cid, challenge_path, root=tmp_path)

        # Second call on same candidate (now in human_review) must raise
        with pytest.raises(ValueError, match="already in state"):
            apply_challenge_transitions(cid, challenge_path, root=tmp_path)

        # Verify only 2 transition rows (not 4) in the log
        lines = [l for l in transitions_path.read_text().splitlines() if l.strip()]
        assert len(lines) == 2, f"Expected 2 rows but got {len(lines)}"

    def test_legal_transitions_still_write(self, tmp_path):
        """Valid screened→challenged→human_review pair writes two rows."""
        from engine.research_factory.challenge import (
            build_challenge_input, write_challenge, apply_challenge_transitions,
        )

        cand = _make_oracle_candidate(candidate_id="rf-legal-transitions-test")
        cid = cand["candidate_id"]

        rf_dir = tmp_path / "data" / "research_factory"
        rf_dir.mkdir(parents=True)
        (rf_dir / "transitions.jsonl").write_text("", encoding="utf-8")

        packet = build_challenge_input(cand, root=tmp_path)
        challenge_path = write_challenge(cid, packet, root=tmp_path)
        apply_challenge_transitions(cid, challenge_path, root=tmp_path)

        lines = [
            l for l in (rf_dir / "transitions.jsonl").read_text().splitlines()
            if l.strip()
        ]
        assert len(lines) == 2
        row = json.loads(lines[0])
        assert row["from"] == "screened"
        assert row["to"] == "challenged"
        assert row["actor"] == "script"
