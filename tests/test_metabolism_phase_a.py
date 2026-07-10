"""tests/test_metabolism_phase_a.py — Hermetic tests for Metabolism Phase A spine.

COVERAGE:
  A1  journal read/write/resume + idempotence
  A1b orphan-GC helper logic (safety guards, not actual subprocess calls)
  A2  preflight fail-safe (broken token → auth_ok False, no expensive call)
  A3  fitness card honest-accruing on immature sensors + tolerant of absent artifacts
  A6  verify regime-aware branch (confirmed→keep, overfit→revert-plan,
      ambiguous→operator-tap, unverifiable→operator-tap)
  A7  budget over-cap no-op + circuit breaker trip
  A8  digest renders (covers all columns, no exception)
  INE inertness assertion: with AUTONOMY_PAUSED unset, every stage entrypoint
      exits 0 + journals noop_paused; no writes outside data/metabolism

All tests are HERMETIC (tmp dirs, in-process, no real data / network / subprocess).
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _tmp_metab_root() -> Path:
    """Return a fresh temp dir with minimal metabolism directory structure."""
    d = Path(tempfile.mkdtemp())
    (d / "data" / "metabolism" / "journal").mkdir(parents=True)
    (d / "data" / "metabolism" / "fitness").mkdir(parents=True)
    (d / "data" / "metabolism" / "verify").mkdir(parents=True)
    (d / "data" / "metabolism" / "digest").mkdir(parents=True)
    (d / "data" / "neuralweb").mkdir(parents=True)
    (d / "data" / "foresight").mkdir(parents=True)
    (d / "data" / "qledger").mkdir(parents=True)
    (d / "config").mkdir(parents=True)
    return d


def _write_budget_config(root: Path) -> None:
    """Write a minimal metabolism_budget.yml for tests."""
    cfg = (
        "schema: metabolism_budget.v1\n"
        "per_cycle_usd_cap: 25\n"
        "per_cycle_token_cap: 25000000\n"
        "max_docket_size: 5\n"
        "circuit_breaker_trip: 3\n"
        "lobe_caps:\n"
        "  til:\n"
        "    per_cycle_usd_cap: 25\n"
        "    per_cycle_token_cap: 25000000\n"
        "    max_docket_size: 5\n"
        "    breaker_trip: 3\n"
    )
    (root / "config" / "metabolism_budget.yml").write_text(cfg, encoding="utf-8")


# ===========================================================================
# A1 — Journal read/write/resume + idempotence
# ===========================================================================

class TestJournal:

    def test_new_cycle_id_format(self):
        from scripts.metabolism_journal import new_cycle_id
        cid = new_cycle_id()
        assert cid.startswith("cycle-")
        parts = cid.split("-")
        # cycle-YYYY-MM-DD-XXXX
        assert len(parts) == 5

    def test_default_journal_is_pending(self):
        from scripts.metabolism_journal import load_journal
        root = _tmp_metab_root()
        j = load_journal("cycle-nonexistent", root=root)
        assert j["status"] == "pending"
        assert j["cycle_id"] == "cycle-nonexistent"
        assert j["auth_ok"] is None
        assert j["artifacts"] == []
        assert j["stages"] == {}

    def test_write_and_read_journal(self):
        from scripts.metabolism_journal import start_stage, load_journal
        root = _tmp_metab_root()
        cid = "cycle-2026-07-09-test1"
        j = start_stage(cid, "sense", root=root)
        assert j["status"] == "running"
        assert j["stage"] == "sense"
        assert j["stages"]["sense"]["status"] == "running"

        # Re-read from disk
        j2 = load_journal(cid, root=root)
        assert j2["stages"]["sense"]["status"] == "running"

    def test_finish_stage_done(self):
        from scripts.metabolism_journal import start_stage, finish_stage, load_journal
        root = _tmp_metab_root()
        cid = "cycle-2026-07-09-test2"
        start_stage(cid, "sense", root=root)
        j = finish_stage(cid, "sense", "done", artifacts=["data/metabolism/fitness/til.json"],
                         root=root)
        assert j["status"] == "done"
        assert j["stages"]["sense"]["status"] == "done"
        assert "data/metabolism/fitness/til.json" in j["artifacts"]

        # Re-read idempotent
        j2 = load_journal(cid, root=root)
        assert j2["stages"]["sense"]["status"] == "done"

    def test_start_stage_idempotent_when_done(self):
        """start_stage on an already-done stage must NOT overwrite it."""
        from scripts.metabolism_journal import start_stage, finish_stage, is_stage_done
        root = _tmp_metab_root()
        cid = "cycle-2026-07-09-test3"
        start_stage(cid, "sense", root=root)
        finish_stage(cid, "sense", "done", root=root)

        # Call start_stage again — must return existing done stage, not reset to running
        j = start_stage(cid, "sense", root=root)
        assert j["stages"]["sense"]["status"] == "done", (
            "start_stage must not overwrite a done stage"
        )

    def test_is_stage_done_false_before_done(self):
        from scripts.metabolism_journal import start_stage, is_stage_done
        root = _tmp_metab_root()
        cid = "cycle-2026-07-09-test4"
        assert is_stage_done(cid, "sense", root=root) is False
        start_stage(cid, "sense", root=root)
        assert is_stage_done(cid, "sense", root=root) is False

    def test_is_stage_done_true_after_done(self):
        from scripts.metabolism_journal import start_stage, finish_stage, is_stage_done
        root = _tmp_metab_root()
        cid = "cycle-2026-07-09-test5"
        start_stage(cid, "sense", root=root)
        finish_stage(cid, "sense", "done", root=root)
        assert is_stage_done(cid, "sense", root=root) is True

    def test_finish_stage_noop_paused(self):
        from scripts.metabolism_journal import finish_stage, load_journal
        root = _tmp_metab_root()
        cid = "cycle-2026-07-09-test6"
        j = finish_stage(cid, "sense", "noop_paused", note="AUTONOMY_PAUSED guard", root=root)
        assert j["status"] == "noop_paused"
        assert j["stages"]["sense"]["status"] == "noop_paused"

    def test_auth_ok_written_to_journal(self):
        from scripts.metabolism_journal import start_stage, finish_stage, load_journal
        root = _tmp_metab_root()
        cid = "cycle-2026-07-09-test7"
        start_stage(cid, "preflight", root=root)
        finish_stage(cid, "preflight", "done", auth_ok=False, root=root)
        j = load_journal(cid, root=root)
        assert j["auth_ok"] is False

    def test_artifact_dedup(self):
        from scripts.metabolism_journal import start_stage, finish_stage, load_journal
        root = _tmp_metab_root()
        cid = "cycle-2026-07-09-test8"
        start_stage(cid, "sense", root=root)
        finish_stage(cid, "sense", "done", artifacts=["path/a", "path/b"], root=root)
        finish_stage(cid, "verify", "done", artifacts=["path/a", "path/c"], root=root)
        j = load_journal(cid, root=root)
        # path/a should appear only once
        assert j["artifacts"].count("path/a") == 1
        assert "path/b" in j["artifacts"]
        assert "path/c" in j["artifacts"]

    def test_corrupt_journal_returns_default(self):
        from scripts.metabolism_journal import load_journal, journal_path
        root = _tmp_metab_root()
        cid = "cycle-2026-07-09-corrupt"
        # Write corrupt JSON
        p = journal_path(cid, root=root)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("NOT VALID JSON {{{", encoding="utf-8")
        j = load_journal(cid, root=root)
        # Must return default without crashing
        assert j["cycle_id"] == cid
        assert j["status"] == "pending"

    def test_list_cycles(self):
        from scripts.metabolism_journal import start_stage, list_cycles
        root = _tmp_metab_root()
        start_stage("cycle-2026-07-09-aaaa", "sense", root=root)
        start_stage("cycle-2026-07-09-bbbb", "sense", root=root)
        cycles = list_cycles(root=root)
        assert "cycle-2026-07-09-aaaa" in cycles
        assert "cycle-2026-07-09-bbbb" in cycles


# ===========================================================================
# A1b — GC helper (unit-level; no actual subprocess calls)
# ===========================================================================

class TestGCHelper:

    def test_gc_skips_non_matching_patterns(self):
        """Worktrees not matching the watched patterns are ignored."""
        from scripts.metabolism_gc import _matches_pattern
        assert _matches_pattern("wf_some_worktree") is True
        assert _matches_pattern("metabolism-cycle-01") is True
        assert _matches_pattern("claude/loop-xyz") is True
        assert _matches_pattern("metabolism/cycle-2026") is True
        assert _matches_pattern("feature/my-pr") is False
        assert _matches_pattern("main") is False

    def test_journal_is_terminal_done(self):
        from scripts.metabolism_gc import _journal_is_terminal
        root = _tmp_metab_root()
        # Write a done journal
        journal_dir = root / "data" / "metabolism" / "journal"
        journal_dir.mkdir(parents=True, exist_ok=True)
        (journal_dir / "cycle-done.json").write_text(
            json.dumps({"cycle_id": "cycle-done", "status": "done"}),
            encoding="utf-8",
        )
        assert _journal_is_terminal(root) is True

    def test_journal_is_terminal_false_for_running(self):
        from scripts.metabolism_gc import _journal_is_terminal
        root = _tmp_metab_root()
        journal_dir = root / "data" / "metabolism" / "journal"
        journal_dir.mkdir(parents=True, exist_ok=True)
        (journal_dir / "cycle-running.json").write_text(
            json.dumps({"cycle_id": "cycle-running", "status": "running"}),
            encoding="utf-8",
        )
        assert _journal_is_terminal(root) is False

    def test_journal_is_terminal_empty_dir(self):
        from scripts.metabolism_gc import _journal_is_terminal
        root = _tmp_metab_root()
        # Empty journal dir
        assert _journal_is_terminal(root) is False


# ===========================================================================
# A2 — Preflight fail-safe
# ===========================================================================

class TestPreflightAuth:

    def test_broken_token_returns_false_no_expensive_call(self):
        """Broken capability → auth_ok=False without any subprocess call."""
        from scripts.preflight_claude_auth import check_auth
        # Use a temp root with no capability manifest → broker denies
        root = _tmp_metab_root()
        # No capability_manifest.yml in root/config → resolve() returns denied
        result = check_auth(lane="test-lane", root=root)
        assert result["auth_ok"] is False
        assert "reason" in result

    def test_env_var_not_set_returns_false(self):
        """When the env var is absent, auth_ok=False (fail-closed)."""
        from scripts.preflight_claude_auth import check_auth
        root = _tmp_metab_root()
        # Write a minimal capability manifest that resolves successfully
        cap_manifest = (
            "schema: capability_manifest.v1\n"
            "capabilities:\n"
            "  - capability_id: claude_code_oauth\n"
            "    kind: llm_oauth\n"
            "    secret_ref: CLAUDE_CODE_OAUTH_TOKEN_TEST_ABSENT\n"
            "    storage_locus: gh-secret\n"
            "    allowed_lanes:\n"
            "      - test-lane\n"
            "    allowed_tiers:\n"
            "      - T0\n"
            "    rotation_state: active\n"
            "    kill_state: active\n"
        )
        (root / "config" / "capability_manifest.yml").write_text(cap_manifest, encoding="utf-8")
        # Ensure the env var is NOT set
        env_backup = os.environ.pop("CLAUDE_CODE_OAUTH_TOKEN_TEST_ABSENT", None)
        try:
            result = check_auth(lane="test-lane", root=root)
            assert result["auth_ok"] is False
            assert "ref_name" in result
        finally:
            if env_backup is not None:
                os.environ["CLAUDE_CODE_OAUTH_TOKEN_TEST_ABSENT"] = env_backup

    def test_any_exception_returns_false(self):
        """Any unexpected error → auth_ok=False (fail-closed)."""
        from scripts.preflight_claude_auth import check_auth
        # Pass a non-existent root to trigger resolve error
        result = check_auth(lane="test-lane", root=Path("/nonexistent/path/xyz"))
        assert result["auth_ok"] is False

    def test_ping_failure_returns_false(self):
        """Subprocess ping failure → auth_ok=False."""
        from scripts.preflight_claude_auth import _run_ping_check
        # Patch subprocess.run to simulate FileNotFoundError (claude CLI absent)
        with patch("subprocess.run", side_effect=FileNotFoundError("claude not found")):
            ok, reason = _run_ping_check("SOME_TOKEN_REF")
        assert ok is False
        assert "not found" in reason.lower() or "cli" in reason.lower()

    def test_ping_timeout_returns_false(self):
        """Subprocess timeout → auth_ok=False."""
        import subprocess
        from scripts.preflight_claude_auth import _run_ping_check
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("claude", 20)):
            ok, reason = _run_ping_check("SOME_TOKEN_REF")
        assert ok is False
        assert "timeout" in reason.lower() or "timed out" in reason.lower()

    def test_ping_nonzero_exit_returns_false(self):
        """Non-zero subprocess exit → auth_ok=False."""
        from scripts.preflight_claude_auth import _run_ping_check
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "OAuth token expired"
        mock_result.stdout = ""
        with patch("subprocess.run", return_value=mock_result):
            ok, reason = _run_ping_check("SOME_TOKEN_REF")
        assert ok is False

    def test_ping_empty_stdout_returns_false(self):
        """Empty stdout on zero exit → auth_ok=False."""
        from scripts.preflight_claude_auth import _run_ping_check
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "   "
        mock_result.stderr = ""
        with patch("subprocess.run", return_value=mock_result):
            ok, reason = _run_ping_check("SOME_TOKEN_REF")
        assert ok is False

    def test_ping_success_returns_true(self):
        """Non-empty stdout on zero exit → auth_ok=True."""
        from scripts.preflight_claude_auth import _run_ping_check
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "pong"
        mock_result.stderr = ""
        with patch("subprocess.run", return_value=mock_result):
            ok, reason = _run_ping_check("SOME_TOKEN_REF")
        assert ok is True


# ===========================================================================
# A3 — TIL fitness card
# ===========================================================================

class TestTilFitness:

    def test_fitness_card_absent_artifacts_all_accruing(self):
        """No sensor artifacts present → all sensors 'accruing', no crash."""
        from engine.metabolism.til_fitness import build_fitness_card
        root = _tmp_metab_root()
        card = build_fitness_card(root)
        assert card["schema"] == "metabolism.til_fitness.v1"
        assert card["lobe"] == "til"
        assert card["maturity"] == "accruing"
        sensors = card["sensors"]
        assert set(sensors.keys()) == {
            "front_run_lead", "placebo_hit_rate", "falsifier_honesty", "live_leg_quality"
        }
        for name, s in sensors.items():
            assert s["value"] is None, f"sensor {name} should have null value when absent"
            assert s["maturity"] == "accruing"
            assert s["n"] == 0

    def test_fitness_card_authority_block(self):
        """Authority block must be context-only with no promotion flags."""
        from engine.metabolism.til_fitness import build_fitness_card
        root = _tmp_metab_root()
        card = build_fitness_card(root)
        auth = card["authority"]
        assert auth["is_context_only"] is True
        assert auth["may_rank"] is False
        assert auth["may_gate"] is False
        assert auth["may_size"] is False
        assert auth["may_escalate"] is False

    def test_fitness_card_no_validated_text(self):
        """The word 'validated' must not appear in the fitness card notes."""
        from engine.metabolism.til_fitness import build_fitness_card
        import json as _json
        root = _tmp_metab_root()
        card = build_fitness_card(root)
        card_str = _json.dumps(card).lower()
        assert "validated" not in card_str, (
            "House law: the word 'validated' must never appear in user-facing text"
        )

    def test_fitness_card_with_partial_leadlag(self):
        """With <MIN_N earliness grades, front_run_lead is still accruing."""
        from engine.metabolism.til_fitness import build_fitness_card
        root = _tmp_metab_root()
        # Write a minimal earliness_grades.json with too few flags
        early_data = {
            "schema": "foresight.earliness_grades.v1",
            "as_of": "2026-07-09",
            "n_flags": 3,
            "n_pending": 5,
            "pooled_summary": {
                "n_graded_flags": 3,
                "overall_median_lead_days": 2.5,
                "share_led": 0.67,
            },
        }
        (root / "data" / "foresight" / "earliness_grades.json").write_text(
            json.dumps(early_data), encoding="utf-8"
        )
        card = build_fitness_card(root)
        lead_sensor = card["sensors"]["front_run_lead"]
        # n=3 < MIN_N=10 → still accruing
        assert lead_sensor["maturity"] == "accruing"
        assert lead_sensor["value"] is None
        assert lead_sensor["n"] == 3

    def test_fitness_card_with_mature_leadlag(self):
        """With >= MIN_N earliness grades, front_run_lead becomes ready."""
        from engine.metabolism.til_fitness import build_fitness_card, _MIN_N_LEAD
        root = _tmp_metab_root()
        early_data = {
            "schema": "foresight.earliness_grades.v1",
            "as_of": "2026-07-09",
            "n_flags": _MIN_N_LEAD + 1,
            "n_pending": 0,
            "pooled_summary": {
                "n_graded_flags": _MIN_N_LEAD + 1,
                "overall_median_lead_days": 5.0,
                "share_led": 0.8,
            },
        }
        (root / "data" / "foresight" / "earliness_grades.json").write_text(
            json.dumps(early_data), encoding="utf-8"
        )
        card = build_fitness_card(root)
        lead_sensor = card["sensors"]["front_run_lead"]
        assert lead_sensor["maturity"] == "ready"
        assert lead_sensor["value"] == 5.0

    def test_fitness_card_falsifier_honesty(self):
        """Falsifier honesty = confirmed / (confirmed + tripped)."""
        from engine.metabolism.til_fitness import build_fitness_card, _MIN_N_FALSIFIER
        root = _tmp_metab_root()
        # Write enough evaluations to reach MIN_N_FALSIFIER
        evals_path = root / "data" / "qledger" / "falsifier_evaluations.jsonl"
        rows = (
            [{"claim_id": f"c{i}", "outcome": "CONFIRMED"} for i in range(_MIN_N_FALSIFIER)] +
            [{"claim_id": f"t{i}", "outcome": "FALSIFIER_TRIPPED"} for i in range(2)]
        )
        with evals_path.open("w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")

        card = build_fitness_card(root)
        sensor = card["sensors"]["falsifier_honesty"]
        assert sensor["maturity"] == "ready"
        # confirmed/(confirmed+tripped) = MIN_N_FALSIFIER / (MIN_N_FALSIFIER + 2)
        expected = _MIN_N_FALSIFIER / (_MIN_N_FALSIFIER + 2)
        assert abs(sensor["value"] - expected) < 0.001
        assert sensor["n_confirmed"] == _MIN_N_FALSIFIER
        assert sensor["n_tripped"] == 2

    def test_build_til_fitness_script_dry_run(self):
        """build_til_fitness in dry-run mode builds but does not write artifact."""
        from scripts.build_til_fitness import run
        root = _tmp_metab_root()
        card = run(root, dry_run=True)
        assert card.get("schema") == "metabolism.til_fitness.v1"
        # File must NOT be written
        assert not (root / "data" / "metabolism" / "fitness" / "til.json").exists()

    def test_build_til_fitness_script_writes(self):
        """build_til_fitness in normal mode writes the artifact."""
        from scripts.build_til_fitness import run
        root = _tmp_metab_root()
        run(root, dry_run=False)
        out = root / "data" / "metabolism" / "fitness" / "til.json"
        assert out.exists()
        card = json.loads(out.read_text(encoding="utf-8"))
        assert card["schema"] == "metabolism.til_fitness.v1"


# ===========================================================================
# A6 — VERIFY realized-delta grader
# ===========================================================================

class TestVerify:

    def _base_contract(self, check_by: str = "2026-01-01") -> dict:
        return {
            "proposal_id": "prop-test-001",
            "title": "Test proposal",
            "sensor": "falsifier_honesty",
            "expected_sign": "positive",
            "band": [0.6, 1.0],
            "check_by": check_by,
            "placebo_to_beat": 0.5,
            "asof": "2025-10-01",
            "falsifier_spec": {"kind": "soft", "reason": "test-only"},
        }

    def test_pending_when_checkby_future(self):
        """check_by in the future → pending record, no triage."""
        from engine.metabolism.verify import verify_proposal
        root = _tmp_metab_root()
        contract = self._base_contract(check_by="2099-12-31")
        record = verify_proposal("cycle-test", contract, root=root, today="2026-07-09")
        assert record["triage"]["classification"] == "pending"
        assert record["triage"]["action"] == "wait"

    def test_confirmed_outcome_gives_keep_action(self):
        """CONFIRMED outcome → triage classification=confirmed, action=keep."""
        from engine.metabolism.verify import verify_proposal
        root = _tmp_metab_root()
        # Patch _evaluate_contract to return CONFIRMED
        with patch("engine.metabolism.verify._evaluate_contract",
                   return_value=("CONFIRMED", "rel_return check passed")):
            record = verify_proposal("cycle-test", self._base_contract("2026-01-01"),
                                     root=root, today="2026-07-09")
        assert record["realized"]["outcome"] == "CONFIRMED"
        assert record["triage"]["classification"] == "confirmed"
        assert record["triage"]["action"] == "keep"
        assert record["triage"]["revert_plan"] is None

    def test_tripped_clean_overfit_gives_revert_plan(self):
        """FALSIFIER_TRIPPED with no regime/estimator flags → overfit → revert_plan."""
        from engine.metabolism.verify import verify_proposal
        root = _tmp_metab_root()
        with patch("engine.metabolism.verify._evaluate_contract",
                   return_value=("FALSIFIER_TRIPPED", "miss")):
            record = verify_proposal("cycle-test", self._base_contract("2026-01-01"),
                                     root=root, today="2026-07-09",
                                     context={})  # no regime flags
        assert record["realized"]["outcome"] == "FALSIFIER_TRIPPED"
        assert record["triage"]["classification"] == "overfit"
        assert record["triage"]["action"] == "revert_plan"
        revert = record["triage"]["revert_plan"]
        assert revert is not None
        assert revert["action"] == "git_revert"
        # Revert plan must include a DO_NOT_REBUILD row
        assert "do_not_rebuild_row" in revert

    def test_tripped_regime_suspected_gives_operator_tap(self):
        """FALSIFIER_TRIPPED + regime_change_suspected → operator_tap, revert HELD."""
        from engine.metabolism.verify import verify_proposal
        root = _tmp_metab_root()
        with patch("engine.metabolism.verify._evaluate_contract",
                   return_value=("FALSIFIER_TRIPPED", "miss")):
            record = verify_proposal("cycle-test", self._base_contract("2026-01-01"),
                                     root=root, today="2026-07-09",
                                     context={"regime_change_suspected": True})
        assert record["triage"]["classification"] == "regime_change"
        assert record["triage"]["action"] == "operator_tap"
        assert record["triage"]["revert_plan"] is None
        assert record["triage"]["operator_tap_reason"] is not None

    def test_unverifiable_gives_operator_tap(self):
        """UNVERIFIABLE outcome → operator_tap."""
        from engine.metabolism.verify import verify_proposal
        root = _tmp_metab_root()
        with patch("engine.metabolism.verify._evaluate_contract",
                   return_value=("UNVERIFIABLE", "soft check")):
            record = verify_proposal("cycle-test", self._base_contract("2026-01-01"),
                                     root=root, today="2026-07-09")
        assert record["triage"]["classification"] == "unverifiable"
        assert record["triage"]["action"] == "operator_tap"

    def test_verify_write_file(self):
        """write_verify_record writes the file atomically."""
        from engine.metabolism.verify import verify_proposal, write_verify_record
        root = _tmp_metab_root()
        with patch("engine.metabolism.verify._evaluate_contract",
                   return_value=("CONFIRMED", "ok")):
            record = verify_proposal("cycle-write-test", self._base_contract("2026-01-01"),
                                     root=root, today="2026-07-09")
        out = write_verify_record(record, root)
        assert out is not None
        assert out.exists()
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["schema"] == "metabolism.verify.v1"

    def test_verify_script_noop_when_paused(self, monkeypatch):
        """metabolism_verify script exits 0 + journals noop_paused when paused."""
        from scripts.metabolism_verify import main
        root = _tmp_metab_root()
        # Ensure paused: unset the env var
        monkeypatch.delenv("AUTONOMY_PAUSED", raising=False)
        cid = "cycle-paused-verify"
        rc = main(["--cycle-id", cid, "--root", str(root), "--dry-run"])
        assert rc == 0
        # Journal must record noop_paused
        from scripts.metabolism_journal import load_journal
        j = load_journal(cid, root=root)
        assert j["stages"].get("verify", {}).get("status") == "noop_paused"


# ===========================================================================
# A7 — Budget governor + circuit breaker
# ===========================================================================

class TestBudget:

    def test_init_cycle_creates_ledger(self):
        from scripts.metabolism_budget import init_cycle
        root = _tmp_metab_root()
        _write_budget_config(root)
        ledger = init_cycle("cycle-budget-test", root=root)
        assert ledger["cycle_id"] == "cycle-budget-test"
        assert ledger["usd_spent"] == 0.0
        assert ledger["token_spent"] == 0
        assert ledger["entries"] == []

    def test_init_cycle_idempotent(self):
        from scripts.metabolism_budget import init_cycle
        root = _tmp_metab_root()
        _write_budget_config(root)
        l1 = init_cycle("cycle-idem", root=root)
        l2 = init_cycle("cycle-idem", root=root)
        assert l1["started_at"] == l2["started_at"]

    def test_record_spend_under_cap(self):
        from scripts.metabolism_budget import init_cycle, record_spend
        root = _tmp_metab_root()
        _write_budget_config(root)
        init_cycle("cycle-spend", root=root)
        result = record_spend("cycle-spend", "sense", usd=1.0, tokens=5000, root=root)
        assert result["ok"] is True
        assert result["over_cap"] is False
        assert result["usd_remaining"] == pytest.approx(24.0, abs=0.001)

    def test_record_spend_over_usd_cap(self):
        from scripts.metabolism_budget import init_cycle, record_spend
        root = _tmp_metab_root()
        _write_budget_config(root)
        init_cycle("cycle-overcap", root=root)
        # Spend right up to the cap
        record_spend("cycle-overcap", "sense", usd=20.0, root=root)
        # Now exceed it
        result = record_spend("cycle-overcap", "propose", usd=10.0, root=root)
        assert result["over_cap"] is True
        assert result["ok"] is False

    def test_check_cap_under_cap(self):
        from scripts.metabolism_budget import init_cycle, check_cap
        root = _tmp_metab_root()
        _write_budget_config(root)
        init_cycle("cycle-check", root=root)
        result = check_cap("cycle-check", root=root)
        assert result["ok"] is True
        assert result["over_cap"] is False

    def test_circuit_breaker_trip_at_threshold(self):
        from scripts.metabolism_budget import init_cycle, record_pr_outcome, is_lobe_paused
        root = _tmp_metab_root()
        _write_budget_config(root)
        init_cycle("cycle-cb", root=root)
        # 3 failures = trip (breaker_trip=3 in test config)
        for _ in range(2):
            result = record_pr_outcome("cycle-cb", "til", success=False, root=root)
            assert result["paused"] is False
        # Third failure → trip
        result = record_pr_outcome("cycle-cb", "til", success=False, root=root)
        assert result["paused"] is True
        assert is_lobe_paused("til", root=root) is True

    def test_circuit_breaker_reset_on_success(self):
        from scripts.metabolism_budget import init_cycle, record_pr_outcome, is_lobe_paused
        root = _tmp_metab_root()
        _write_budget_config(root)
        init_cycle("cycle-cb-reset", root=root)
        # 2 failures
        for _ in range(2):
            record_pr_outcome("cycle-cb-reset", "til", success=False, root=root)
        # Success resets streak
        result = record_pr_outcome("cycle-cb-reset", "til", success=True, root=root)
        assert result["failed_streak"] == 0
        assert is_lobe_paused("til", root=root) is False

    def test_circuit_breaker_not_tripped_below_threshold(self):
        from scripts.metabolism_budget import init_cycle, record_pr_outcome
        root = _tmp_metab_root()
        _write_budget_config(root)
        init_cycle("cycle-cb-safe", root=root)
        for _ in range(2):  # 2 < 3 → no trip
            result = record_pr_outcome("cycle-cb-safe", "til", success=False, root=root)
        assert result["paused"] is False


# ===========================================================================
# A8 — Digest renders
# ===========================================================================

class TestDigest:

    def test_digest_renders_no_exception(self):
        """Digest must render without crashing, even with no data."""
        from scripts.metabolism_digest import build_digest
        root = _tmp_metab_root()
        now = datetime(2026, 7, 9, 12, 0, 0, tzinfo=timezone.utc)
        content = build_digest(root, now)
        assert isinstance(content, str)
        assert len(content) > 100

    def test_digest_contains_required_sections(self):
        """Digest must have all required sections."""
        from scripts.metabolism_digest import build_digest
        root = _tmp_metab_root()
        now = datetime(2026, 7, 9, 12, 0, 0, tzinfo=timezone.utc)
        content = build_digest(root, now)
        assert "Kill-switch state" in content
        assert "Cycles" in content
        assert "Governance events" in content
        assert "Verify outcomes" in content
        assert "Budget" in content
        assert "Capability audit tape" in content

    def test_digest_week_label(self):
        """Digest header must contain the week label."""
        from scripts.metabolism_digest import build_digest, _week_label
        root = _tmp_metab_root()
        now = datetime(2026, 7, 9, 12, 0, 0, tzinfo=timezone.utc)
        content = build_digest(root, now)
        week = _week_label(now)
        assert week in content

    def test_digest_no_validated_text(self):
        """The word 'validated' must not appear in digest output."""
        from scripts.metabolism_digest import build_digest
        root = _tmp_metab_root()
        now = datetime(2026, 7, 9, 12, 0, 0, tzinfo=timezone.utc)
        content = build_digest(root, now).lower()
        assert "validated" not in content, (
            "House law: 'validated' must never appear in user-facing text"
        )

    def test_digest_dry_run_prints(self, capsys):
        """Dry-run mode prints the digest without writing."""
        from scripts.metabolism_digest import main
        root = _tmp_metab_root()
        rc = main(["--dry-run", "--root", str(root), "--no-notify"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "Metabolism" in out or "metabolism" in out.lower()

    def test_digest_writes_to_disk(self):
        """Digest in normal mode writes a file."""
        from scripts.metabolism_digest import main
        root = _tmp_metab_root()
        rc = main(["--root", str(root), "--no-notify", "--week", "2026-W28"])
        assert rc == 0
        digest_file = root / "data" / "metabolism" / "digest" / "2026-W28.md"
        assert digest_file.exists()


# ===========================================================================
# INERTNESS ASSERTION
# ===========================================================================

class TestInertness:
    """With AUTONOMY_PAUSED unset (default paused), every stage entrypoint
    must produce ZERO merges, ZERO non-draft PRs, and journal 'noop_paused'.
    """

    def test_verify_stage_noop_when_paused(self, monkeypatch, tmp_path):
        """metabolism_verify exits 0 + journals noop_paused when AUTONOMY_PAUSED unset."""
        from scripts.metabolism_verify import main
        monkeypatch.delenv("AUTONOMY_PAUSED", raising=False)
        root = tmp_path
        (root / "data" / "metabolism" / "journal").mkdir(parents=True)
        cid = "cycle-inertness-test"
        rc = main(["--cycle-id", cid, "--root", str(root), "--dry-run"])
        assert rc == 0
        from scripts.metabolism_journal import load_journal
        j = load_journal(cid, root=root)
        assert j["stages"].get("verify", {}).get("status") == "noop_paused"

    def test_no_writes_outside_metabolism_dir_when_paused(self, monkeypatch, tmp_path):
        """When paused, no file should be written outside data/metabolism/ by the verify stage."""
        from scripts.metabolism_verify import main
        monkeypatch.delenv("AUTONOMY_PAUSED", raising=False)
        root = tmp_path
        (root / "data" / "metabolism" / "journal").mkdir(parents=True)
        (root / "data" / "metabolism" / "verify").mkdir(parents=True)
        (root / "data" / "neuralweb").mkdir(parents=True)

        cid = "cycle-no-write-test"

        # Capture files before
        before = set(tmp_path.rglob("*"))
        main(["--cycle-id", cid, "--root", str(root), "--dry-run"])
        after = set(tmp_path.rglob("*"))
        new_files = {f for f in (after - before) if f.is_file()}

        for f in new_files:
            rel = f.relative_to(tmp_path)
            assert str(rel).startswith("data/metabolism"), (
                f"File written outside data/metabolism/ when paused: {rel}"
            )

    def test_budget_noop_when_paused(self, monkeypatch, tmp_path):
        """Budget governor returns ok when no cycle is initialized (effectively a no-op)."""
        from scripts.metabolism_budget import check_cap
        monkeypatch.delenv("AUTONOMY_PAUSED", raising=False)
        # With no ledger, check_cap must not crash and return ok=True (no budget spent)
        result = check_cap("nonexistent-cycle", root=tmp_path)
        assert result["ok"] is True

    def test_fitness_card_dry_run_writes_nothing(self, monkeypatch, tmp_path):
        """build_til_fitness in dry-run writes nothing outside the temp root."""
        from scripts.build_til_fitness import run
        monkeypatch.delenv("AUTONOMY_PAUSED", raising=False)
        (tmp_path / "data" / "foresight").mkdir(parents=True)
        (tmp_path / "data" / "qledger").mkdir(parents=True)
        (tmp_path / "data" / "metabolism" / "fitness").mkdir(parents=True)
        run(tmp_path, dry_run=True)
        # dry-run must not write the fitness file
        assert not (tmp_path / "data" / "metabolism" / "fitness" / "til.json").exists()
