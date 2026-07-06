"""tests/test_research_factory_adapters.py — W3 adapter tests.

All tests use mocked evaluators / fixture data only — no heavy data loads.
Absent-file-safe behavior verified throughout.

Coverage:
  1. Oracle projection mapping — exhaustive over all 6 domain statuses (RF-2)
  2. Reversion-track discriminator — reversion block present/absent
  3. Refuse-rescreen — 63d track refuses re-screen when compound already screened
  4. Count-gate refusal — 63d screen without count=True raises PermissionError
  5. Cortex absent-file — returns [] gracefully
  6. Cortex self-ref exclusion — spine_query referencing cortex_attention → excluded
  7. Alpha survivor filter — fdr_reject==True only; net_new_info stays metadata
  8. Dry-run writes nothing — research_factory_run --dry-run touches no disk
  9. Kill evidence attached on numeric_rejected (RF-10)
 10. search_width_at_scan captured in artifact
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Ensure engine package is importable
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# ===========================================================================
# 1. Oracle projection mapping (exhaustive, RF-2)
# ===========================================================================

class TestOracleProjection:
    """Exhaustive mapping of all oracle domain statuses → factory states."""

    def test_screened_maps_to_screened(self):
        from engine.research_factory.adapter_oracle import project_oracle_status
        assert project_oracle_status("screened") == "screened"

    def test_accruing_maps_to_paper(self):
        from engine.research_factory.adapter_oracle import project_oracle_status
        assert project_oracle_status("accruing") == "paper"

    def test_promoted_maps_to_promote_eligible(self):
        from engine.research_factory.adapter_oracle import project_oracle_status
        assert project_oracle_status("promoted") == "promote_eligible"

    def test_refuted_maps_to_numeric_rejected(self):
        from engine.research_factory.adapter_oracle import project_oracle_status
        assert project_oracle_status("refuted") == "numeric_rejected"

    def test_blocked_missing_column_maps_to_awaiting_data(self):
        from engine.research_factory.adapter_oracle import project_oracle_status
        assert project_oracle_status("blocked_missing_column") == "awaiting_data"

    def test_exploratory_maps_to_registered(self):
        from engine.research_factory.adapter_oracle import project_oracle_status
        assert project_oracle_status("exploratory") == "registered"

    def test_unknown_status_falls_back_to_registered(self):
        from engine.research_factory.adapter_oracle import project_oracle_status
        assert project_oracle_status("nonexistent_status") == "registered"
        assert project_oracle_status("") == "registered"

    def test_all_six_statuses_covered(self):
        """Ensure all 6 known oracle statuses have explicit mappings."""
        from engine.research_factory.adapter_oracle import ORACLE_STATUS_TO_FACTORY_STATE
        known = {"screened", "accruing", "promoted", "refuted",
                 "blocked_missing_column", "exploratory"}
        assert known == set(ORACLE_STATUS_TO_FACTORY_STATE.keys())


# ===========================================================================
# 2. Reversion-track discriminator
# ===========================================================================

class TestReversionTrackDiscriminator:

    def test_reversion_pass_is_reversion_track(self):
        from engine.research_factory.adapter_oracle import is_reversion_track
        compound = {"id": "A15", "reversion": {"gauntlet": "PASS", "n": 100}}
        assert is_reversion_track(compound) is True

    def test_reversion_fail_is_not_reversion_track(self):
        from engine.research_factory.adapter_oracle import is_reversion_track
        compound = {"id": "A1", "reversion": {"gauntlet": "FAIL"}}
        assert is_reversion_track(compound) is False

    def test_missing_reversion_block_is_63d_track(self):
        from engine.research_factory.adapter_oracle import is_reversion_track
        compound = {"id": "A1"}
        assert is_reversion_track(compound) is False

    def test_empty_reversion_block_is_63d_track(self):
        from engine.research_factory.adapter_oracle import is_reversion_track
        compound = {"id": "A1", "reversion": {}}
        assert is_reversion_track(compound) is False

    def test_null_reversion_block_is_63d_track(self):
        from engine.research_factory.adapter_oracle import is_reversion_track
        compound = {"id": "A1", "reversion": None}
        assert is_reversion_track(compound) is False


# ===========================================================================
# 3. Refuse re-screen (63d track, RF-13)
# ===========================================================================

class TestReversionRescreen:

    def _make_compound_63d(self, status: str = "screened") -> dict:
        """63d compound: no reversion block."""
        return {
            "id": "C4",
            "family": "C",
            "status": status,
            "entry_rule": {"col": "washout_w", "op": "gt", "value": 0},
            "universe": {"tier": "s"},
        }

    def test_screened_compound_63d_refused_without_count(self, tmp_path):
        from engine.research_factory.adapter_oracle import route_compound
        compound = self._make_compound_63d("screened")
        result = route_compound(compound, data_dir=tmp_path, count=False)
        assert result["re_screen_refused"] is True
        assert result["track"] == "63d"

    def test_accruing_compound_63d_refused(self, tmp_path):
        from engine.research_factory.adapter_oracle import route_compound
        compound = self._make_compound_63d("accruing")
        result = route_compound(compound, data_dir=tmp_path, count=False)
        assert result["re_screen_refused"] is True

    def test_refuted_compound_63d_refused(self, tmp_path):
        from engine.research_factory.adapter_oracle import route_compound
        compound = self._make_compound_63d("refuted")
        result = route_compound(compound, data_dir=tmp_path, count=False)
        assert result["re_screen_refused"] is True

    def test_exploratory_compound_63d_not_refused(self, tmp_path):
        """Exploratory compounds are not yet screened — no re-screen refusal."""
        from engine.research_factory.adapter_oracle import route_compound
        compound = self._make_compound_63d("exploratory")
        result = route_compound(compound, data_dir=tmp_path, count=False)
        assert result["re_screen_refused"] is False


# ===========================================================================
# 4. Count-gate refusal (RF-13, RF-6)
# ===========================================================================

class TestCountGate:

    def _make_exploratory_63d(self) -> dict:
        return {
            "id": "C_NEW",
            "family": "C",
            "status": "exploratory",
            "entry_rule": {"col": "some_col", "op": "gt", "value": 0},
            "universe": {"tier": "s"},
        }

    def test_count_false_raises_permission_error_on_invoke(self):
        """Directly test _run_63d_screen raises PermissionError when count=False."""
        from engine.research_factory.adapter_oracle import _run_63d_screen
        compound = self._make_exploratory_63d()
        with pytest.raises(PermissionError, match="COUNTED"):
            _run_63d_screen(compound, Path("data"), count=False)

    def test_route_compound_exploratory_no_count_no_screen(self, tmp_path):
        """route_compound with count=False for exploratory: read-only, no PermissionError."""
        from engine.research_factory.adapter_oracle import route_compound
        compound = self._make_exploratory_63d()
        # Should NOT raise; read-only mode
        result = route_compound(compound, data_dir=tmp_path, count=False)
        assert result["re_screen_refused"] is False
        assert result["artifact"]["source"] == "read_only_registry"
        assert result["track"] == "63d"

    def test_route_compound_exploratory_with_count_calls_screen(self, tmp_path):
        """route_compound with count=True for exploratory invokes _run_63d_screen."""
        from engine.research_factory import adapter_oracle
        compound = self._make_exploratory_63d()
        # Mock _run_63d_screen to capture the call
        with patch.object(adapter_oracle, "_run_63d_screen", return_value={"mock": True}) as mock_screen:
            result = adapter_oracle.route_compound(compound, data_dir=tmp_path, count=True)
            mock_screen.assert_called_once()
            assert result["artifact"]["screen_result"] == {"mock": True}


# ===========================================================================
# 5. Cortex absent-file → empty result
# ===========================================================================

class TestCortexAbsentFile:

    def test_load_machine_registry_absent(self, tmp_path):
        from engine.research_factory.adapter_cortex import load_machine_registry
        result = load_machine_registry(tmp_path)
        assert result == []

    def test_route_all_absent_file(self, tmp_path):
        from engine.research_factory.adapter_cortex import route_all
        result = route_all(tmp_path)
        assert result == []

    def test_route_all_empty_registry(self, tmp_path):
        """Empty file → []."""
        from engine.research_factory.adapter_cortex import route_all
        reg_path = tmp_path / "neuralweb" / "machine_registry.jsonl"
        reg_path.parent.mkdir(parents=True, exist_ok=True)
        reg_path.write_text("")
        result = route_all(tmp_path)
        assert result == []


# ===========================================================================
# 6. Cortex self-ref exclusion
# ===========================================================================

class TestCortexSelfRefExclusion:

    def _make_hyp(self, spine_query: dict | None) -> dict:
        return {
            "id": "hyp-001",
            "registered_at": "2026-07-06T00:00:00",
            "status": "registered",
            "spine_query": spine_query,
            "verdict": "passed",
            "n": 42,
            "metric_value": 0.6,
            "metric": "hit_rate",
        }

    def test_cortex_attention_ledger_excluded(self):
        from engine.research_factory.adapter_cortex import route_hypothesis
        hyp = self._make_hyp({"ledger": "cortex_attention", "family": "some"})
        result = route_hypothesis(hyp)
        assert result["self_ref_excluded"] is True
        assert result["firings_evidence"] is None

    def test_reflex_cortex_attention_engine_excluded(self):
        from engine.research_factory.adapter_cortex import route_hypothesis
        hyp = self._make_hyp({"engine": "reflex.cortex_attention"})
        result = route_hypothesis(hyp)
        assert result["self_ref_excluded"] is True
        assert result["firings_evidence"] is None

    def test_reflex_cortex_attention_family_prefix_excluded(self):
        from engine.research_factory.adapter_cortex import route_hypothesis
        hyp = self._make_hyp({"family": "reflex.cortex_attention.some_sub"})
        result = route_hypothesis(hyp)
        assert result["self_ref_excluded"] is True
        assert result["firings_evidence"] is None

    def test_clean_spine_query_not_excluded(self):
        from engine.research_factory.adapter_cortex import route_hypothesis
        hyp = self._make_hyp({"ledger": "spine", "family": "entry_quality"})
        result = route_hypothesis(hyp)
        assert result["self_ref_excluded"] is False
        assert result["firings_evidence"] is not None
        assert result["firings_evidence"]["verdict"] == "passed"

    def test_null_spine_query_not_excluded(self):
        from engine.research_factory.adapter_cortex import route_hypothesis
        hyp = self._make_hyp(None)
        result = route_hypothesis(hyp)
        assert result["self_ref_excluded"] is False

    def test_trial_accounting_mode_cortex_shared(self):
        from engine.research_factory.adapter_cortex import route_hypothesis
        hyp = self._make_hyp({"ledger": "spine"})
        result = route_hypothesis(hyp)
        assert result["trial_accounting"]["mode"] == "cortex_shared"
        assert result["trial_accounting"]["family"] is None

    def test_spec_ref_equals_metabolism_id(self):
        from engine.research_factory.adapter_cortex import route_hypothesis
        hyp = self._make_hyp({"ledger": "spine"})
        result = route_hypothesis(hyp)
        assert result["spec_ref"] == "hyp-001"
        assert result["hypothesis_id"] == "hyp-001"


# ===========================================================================
# 7. Alpha survivor filter (fdr_reject==True; net_new_info = metadata only)
# ===========================================================================

class TestAlphaGrammarSurvivorFilter:

    def _make_alpha_parquet(self, tmp_path: Path) -> None:
        """Write a minimal alpha_candidates.parquet with known survivors."""
        try:
            import pandas as pd
        except ImportError:
            pytest.skip("pandas not available")

        rows = [
            {
                "alpha_id": "surv-001",
                "family": "alpha_grammar_confluence_v1",
                "mechanism_hypothesis": "momentum",
                "fdr_reject": True,
                "dsr": 0.58,
                "mean_ic": 0.025,
                "t_hac": 3.1,
                "survivorship_caveat": "test",
                "overlap_cluster": "C0",
                "cluster_representative": "surv-001",
                "net_new_info": 0.9,
            },
            {
                "alpha_id": "non-001",
                "family": "alpha_grammar_confluence_v1",
                "mechanism_hypothesis": "noise",
                "fdr_reject": False,
                "dsr": 0.01,
                "mean_ic": 0.001,
                "t_hac": 0.5,
                "survivorship_caveat": "test",
                "overlap_cluster": "C0",
                "cluster_representative": "surv-001",
                "net_new_info": 0.1,
            },
        ]
        df = pd.DataFrame(rows)
        out = tmp_path / "research" / "alpha_candidates.parquet"
        out.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(out, index=False)

    def _make_alpha_clusters(self, tmp_path: Path) -> None:
        clusters = {
            "clusters": [
                {
                    "cluster_label": "C0",
                    "representative_alpha_id": "surv-001",
                    "members": [
                        {"alpha_id": "surv-001", "dsr": 0.58, "net_new_info": 0.9},
                        {"alpha_id": "non-001", "dsr": 0.01, "net_new_info": 0.1},
                    ],
                }
            ],
            "meta": {"n_clusters": 1, "n_candidates": 2, "cluster_threshold": 0.7},
        }
        out = tmp_path / "research" / "alpha_clusters.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(clusters))

    def test_only_fdr_survivors_returned(self, tmp_path):
        try:
            import pandas  # noqa: F401
        except ImportError:
            pytest.skip("pandas not available")
        self._make_alpha_parquet(tmp_path)
        self._make_alpha_clusters(tmp_path)
        from engine.research_factory.adapter_alpha_grammar import route_all
        results = route_all(tmp_path)
        assert len(results) == 1
        fam = results[0]
        assert fam["n_survivors"] == 1
        survivor_ids = [s["alpha_id"] for s in fam["survivors"]]
        assert "surv-001" in survivor_ids
        assert "non-001" not in survivor_ids

    def test_net_new_info_in_metadata_not_rank(self, tmp_path):
        try:
            import pandas  # noqa: F401
        except ImportError:
            pytest.skip("pandas not available")
        self._make_alpha_parquet(tmp_path)
        self._make_alpha_clusters(tmp_path)
        from engine.research_factory.adapter_alpha_grammar import route_all
        results = route_all(tmp_path)
        fam = results[0]
        # net_new_info present but trial_accounting mode is read_only (not rank)
        assert "net_new_info" in fam
        assert fam["trial_accounting"]["mode"] == "read_only"

    def test_absent_parquet_returns_empty(self, tmp_path):
        from engine.research_factory.adapter_alpha_grammar import route_all
        result = route_all(tmp_path)
        assert result == []

    def test_absent_clusters_still_returns_survivors(self, tmp_path):
        """Survivors returned even if clusters file absent (no cluster info)."""
        try:
            import pandas  # noqa: F401
        except ImportError:
            pytest.skip("pandas not available")
        self._make_alpha_parquet(tmp_path)
        # No clusters file
        from engine.research_factory.adapter_alpha_grammar import route_all
        results = route_all(tmp_path)
        assert len(results) == 1


# ===========================================================================
# 8. Dry-run writes nothing
# ===========================================================================

class TestDryRunWritesNothing:

    def _fixture_candidates(self, tmp_path: Path) -> None:
        """Write a minimal candidates.jsonl with one 'registered' oracle candidate."""
        rf_dir = tmp_path / "research_factory"
        rf_dir.mkdir(parents=True, exist_ok=True)
        candidate = {
            "schema": "research_factory.candidate.v1",
            "authority": "display_only",
            "candidate_id": "rf-test-001",
            "created_at": "2026-07-06T00:00:00Z",
            "source": "oracle_brainstorm",
            "candidate_type": "oracle_compound",
            "domain": "oracle",
            "status": "registered",
            "hypothesis": "test hypothesis",
            "mechanism": "test mechanism",
            "spec_ref": "TEST_COMPOUND",
            "trial_accounting": {"mode": "read_only", "family": None},
        }
        (rf_dir / "candidates.jsonl").write_text(json.dumps(candidate) + "\n")

    def test_dry_run_creates_no_transitions(self, tmp_path):
        self._fixture_candidates(tmp_path)
        from scripts.research_factory_run import run
        rf_dir = tmp_path / "research_factory"
        summary = run(rf_dir=rf_dir, data_dir=tmp_path, dry_run=True, count=False)
        # transitions.jsonl must not be created
        assert not (rf_dir / "transitions.jsonl").exists()
        assert summary["dry_run"] is True

    def test_dry_run_lists_routes(self, tmp_path, capsys):
        self._fixture_candidates(tmp_path)
        from scripts.research_factory_run import run
        rf_dir = tmp_path / "research_factory"
        summary = run(rf_dir=rf_dir, data_dir=tmp_path, dry_run=True, count=False)
        # Should have one route entry (compound not found in registry → awaiting_data or error)
        assert len(summary["routes"]) == 1

    def test_execute_with_no_oracle_registry_no_crash(self, tmp_path):
        """Execute mode with absent oracle registry: graceful, no crash."""
        self._fixture_candidates(tmp_path)
        from scripts.research_factory_run import run
        rf_dir = tmp_path / "research_factory"
        # Even in execute mode, missing oracle registry → awaiting_data attempt
        # (or graceful no-action); must not raise
        summary = run(rf_dir=rf_dir, data_dir=tmp_path, dry_run=False, count=False)
        assert "routes" in summary


# ===========================================================================
# 9. Kill evidence attached on numeric_rejected (RF-10)
# ===========================================================================

class TestKillEvidenceNumericRejected:

    def _refuted_reversion_compound(self) -> dict:
        """Compound with domain status 'refuted' and a reversion block."""
        return {
            "id": "A_REFUTED",
            "family": "A",
            "status": "refuted",
            "reversion": {
                "gauntlet": "PASS",
                "n": 87,
                "wr": 0.55,
                "asym": 1.1,
                "ret_exit": 0.005,
                "risk_on": {"n": 40, "wr": 0.52},
                "risk_off": {"n": 47, "wr": 0.57},
            },
        }

    def test_kill_evidence_attached_on_refuted_reversion(self, tmp_path):
        from engine.research_factory.adapter_oracle import route_compound
        compound = self._refuted_reversion_compound()
        result = route_compound(compound, data_dir=tmp_path, count=False)
        assert result["projected_state"] == "numeric_rejected"
        assert result["kill_evidence"] is not None
        ke = result["kill_evidence"]
        assert "n_at_kill" in ke
        assert ke["n_at_kill"] == 87
        assert "kill_class" in ke

    def test_kill_class_underpowered_accruing(self):
        from engine.research_factory.adapter_oracle import _kill_class_from_verdict
        assert _kill_class_from_verdict("UNDERPOWERED-ACCRUING") == "underpowered_accruing"
        assert _kill_class_from_verdict("UNDERPOWERED_ACCRUING") == "underpowered_accruing"

    def test_kill_class_refuted_maps_falsified(self):
        from engine.research_factory.adapter_oracle import _kill_class_from_verdict
        assert _kill_class_from_verdict("REFUTED") == "falsified"
        assert _kill_class_from_verdict("FAIL") == "falsified"
        assert _kill_class_from_verdict(None) == "falsified"

    def test_kill_evidence_has_regime_split(self, tmp_path):
        from engine.research_factory.adapter_oracle import route_compound
        compound = self._refuted_reversion_compound()
        result = route_compound(compound, data_dir=tmp_path, count=False)
        ke = result["kill_evidence"]
        assert "regime_split" in ke
        assert ke["regime_split"]["risk_on"] is not None


# ===========================================================================
# 10. search_width_at_scan captured in artifact
# ===========================================================================

class TestSearchWidthCapture:

    def _make_promotion_queue(self, tmp_path: Path, compound_id: str = "A15",
                              search_width: int = 45) -> None:
        oracle_dir = tmp_path / "oracle"
        oracle_dir.mkdir(parents=True, exist_ok=True)
        pq = {
            "schema": "oracle_promotion_queue.v1",
            "search_width": search_width,
            "candidates": [
                {
                    "compound_id": compound_id,
                    "search_width_at_scan": search_width,
                    "n": 100,
                    "current_status": "screened",
                }
            ],
        }
        (oracle_dir / "promotion_queue.json").write_text(json.dumps(pq))

    def test_search_width_from_pq_entry(self, tmp_path):
        from engine.research_factory.adapter_oracle import route_compound
        self._make_promotion_queue(tmp_path, "A_REVERSION", 45)
        compound = {
            "id": "A_REVERSION",
            "status": "screened",
            "reversion": {"gauntlet": "PASS", "n": 100, "wr": 0.7, "asym": 1.8},
        }
        result = route_compound(compound, data_dir=tmp_path, count=False)
        assert result["artifact"]["search_width_at_scan"] == 45

    def test_search_width_from_pq_root_when_no_entry(self, tmp_path):
        """When compound not in pq candidates, use root search_width."""
        from engine.research_factory.adapter_oracle import route_compound
        self._make_promotion_queue(tmp_path, "OTHER_ID", 55)
        compound = {
            "id": "NOT_IN_PQ",
            "status": "screened",
            "reversion": {"gauntlet": "PASS", "n": 50, "wr": 0.65, "asym": 1.5},
        }
        result = route_compound(compound, data_dir=tmp_path, count=False)
        # Falls back to root search_width
        assert result["artifact"]["search_width_at_scan"] == 55

    def test_search_width_none_when_pq_absent(self, tmp_path):
        """No pq file → search_width_at_scan is None."""
        from engine.research_factory.adapter_oracle import route_compound
        compound = {
            "id": "A_REV",
            "status": "screened",
            "reversion": {"gauntlet": "PASS", "n": 50},
        }
        result = route_compound(compound, data_dir=tmp_path, count=False)
        assert result["artifact"]["search_width_at_scan"] is None


# ===========================================================================
# 11. Cortex route_all with real registry (fixture)
# ===========================================================================

class TestCortexRouteAllWithFixture:

    def _write_registry(self, tmp_path: Path, rows: list[dict]) -> None:
        path = tmp_path / "neuralweb" / "machine_registry.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")

    def test_route_all_returns_one_per_hypothesis(self, tmp_path):
        from engine.research_factory.adapter_cortex import route_all
        self._write_registry(tmp_path, [
            {"id": "hyp-A", "status": "registered", "registered_at": "2026-07-06T00:00:00Z",
             "spine_query": {"ledger": "spine"}},
            {"id": "hyp-B", "status": "registered", "registered_at": "2026-07-06T00:00:00Z",
             "spine_query": {"ledger": "entry_quality"}},
        ])
        results = route_all(tmp_path)
        assert len(results) == 2
        ids = {r["hypothesis_id"] for r in results}
        assert ids == {"hyp-A", "hyp-B"}

    def test_spec_ref_matches_metabolism_id(self, tmp_path):
        from engine.research_factory.adapter_cortex import route_all
        self._write_registry(tmp_path, [
            {"id": "hyp-X", "status": "passed", "registered_at": "2026-07-06T00:00:00Z"},
        ])
        results = route_all(tmp_path)
        assert results[0]["spec_ref"] == "hyp-X"

    def test_self_ref_compound_excluded_in_batch(self, tmp_path):
        from engine.research_factory.adapter_cortex import route_all
        self._write_registry(tmp_path, [
            {"id": "hyp-self", "status": "registered",
             "registered_at": "2026-07-06T00:00:00Z",
             "spine_query": {"ledger": "cortex_attention"}},
        ])
        results = route_all(tmp_path)
        assert results[0]["self_ref_excluded"] is True
        assert results[0]["firings_evidence"] is None
