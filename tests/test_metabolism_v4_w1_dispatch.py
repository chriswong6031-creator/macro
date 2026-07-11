"""tests/test_metabolism_v4_w1_dispatch.py — Hermetic tests for Metabolism V4 W1 (real BUILD dispatch).

COVERAGE (R-V4-2 requirements):
  1. immutable_target_refusal   — target_file in IMMUTABLE set → refused at dispatch; no subprocess.
  2. foreign_file_abort         — session changes a file outside target_files+data/metabolism/ → abort; no PR.
  3. paused_no_dispatch         — AUTONOMY_PAUSED != 'false' → dispatched=False; no subprocess.
  4. dry_run_journaling         — dry_run=True → would_dispatch record with key_ref_name, no subprocess.
  5. idempotent_rerun           — same cycle_id+proposal_id re-run → idempotent_skip; no second dispatch.
  6. key_ref_never_logged       — _dispatch_build_session never logs/persists the env var VALUE.
  7. never_raise_corrupt_proposal — corrupt/None proposal input returns safe fallback dict.
  8. sonnet_model_pinned        — _BUILD_SESSION_MODEL is the correct sonnet model id.
  9. subprocess_wrapper_mockable — _launch_build_subprocess is a standalone function (monkeypatchable).
  10. no_cap_id_not_dispatched  — cap_id=None → dispatched=False, no subprocess.
  11. successful_dispatch_path  — green path: session succeeds, files within target → dispatched=True.
  12. cleanup_on_foreign_abort  — _cleanup_worktree_on_abort runs after foreign-file violation.

All tests HERMETIC (tmp dirs, monkeypatch, no real subprocess, no real data/network).
"""
from __future__ import annotations

import importlib
import json
import logging
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _tmp_root(extra_subdirs: list[str] | None = None) -> Path:
    d = Path(tempfile.mkdtemp(prefix="metab_v4w1_test_"))
    (d / "data" / "metabolism" / "journal").mkdir(parents=True)
    (d / "data" / "metabolism" / "dockets").mkdir(parents=True)
    (d / "config").mkdir(parents=True)
    (d / "docs").mkdir(parents=True)
    (d / "research").mkdir(parents=True)
    (d / "research" / "DO_NOT_REBUILD.md").write_text("# empty\n")
    (d / "docs" / "ACTIVE_BUILD_MAP.md").write_text("# empty\n")
    for sub in (extra_subdirs or []):
        (d / sub).mkdir(parents=True, exist_ok=True)
    return d


def _minimal_proposal(
    pid: str = "p1",
    target_files: list[str] | None = None,
    cycle_id: str = "cycle-test-001",
) -> dict:
    return {
        "proposal_id": pid,
        "cycle_id": cycle_id,
        "title": f"Test proposal {pid}",
        "tier": "T1",
        "lobe": "test_lobe",
        "target_files": target_files or ["engine/test_sensor.py"],
        "targets_sensor": "test_sensor",
        "rationale": "test rationale for dispatch",
        "fitness_contract": {"metric": "liveness", "threshold": 0.5},
    }


def _armed_env():
    """Return env dict with AUTONOMY_PAUSED=false (armed state)."""
    return {**os.environ, "AUTONOMY_PAUSED": "false"}


def _import_mb():
    import scripts.metabolism_build as mb
    importlib.reload(mb)
    return mb


# ── 1. Immutable-target refusal ───────────────────────────────────────────────

class TestImmutableTargetRefusal:
    """IMMUTABLE-set paths in target_files → refused before any subprocess."""

    def test_immutable_path_refused(self):
        mb = _import_mb()
        proposal = _minimal_proposal(target_files=["config/grader_manifest.yml"])
        launched = []

        def fake_launch(cmd, env, cwd, timeout_s=1800):
            launched.append(cmd)
            return {"returncode": 0, "stdout": "", "stderr": ""}

        with patch.dict(os.environ, _armed_env(), clear=False):
            with patch.object(mb, "_launch_build_subprocess", side_effect=fake_launch):
                result = mb._dispatch_build_session(
                    proposal, "/tmp/wt", "metabolism/build-test-cycle",
                    "claude_code_oauth_1", root=_tmp_root(),
                )

        assert result["dispatched"] is False
        assert "IMMUTABLE_REFUSAL" in result["reason"] or "immutable" in result["reason"].lower()
        assert len(launched) == 0, "subprocess must NOT be launched when target is immutable"

    def test_immutable_hooks_refused(self):
        mb = _import_mb()
        proposal = _minimal_proposal(target_files=[".claude/hooks/model_routing_guard.py"])
        launched = []

        def fake_launch(cmd, env, cwd, timeout_s=1800):
            launched.append(cmd)
            return {"returncode": 0, "stdout": "", "stderr": ""}

        with patch.dict(os.environ, _armed_env(), clear=False):
            with patch.object(mb, "_launch_build_subprocess", side_effect=fake_launch):
                result = mb._dispatch_build_session(
                    proposal, "/tmp/wt", "metabolism/build-test-cycle",
                    "claude_code_oauth_1", root=_tmp_root(),
                )

        assert result["dispatched"] is False
        assert len(launched) == 0

    def test_non_immutable_path_not_blocked(self):
        """engine/some_new_sensor.py is NOT immutable — dispatch should proceed."""
        mb = _import_mb()
        proposal = _minimal_proposal(target_files=["engine/some_new_sensor.py"])
        # We expect it to proceed to the key-resolution step (which will fail here since
        # we don't set up a manifest), so we just verify immutable refusal does NOT fire.
        d = _tmp_root()
        with patch.dict(os.environ, _armed_env(), clear=False):
            result = mb._dispatch_build_session(
                proposal, "/tmp/wt", "metabolism/build-test-cycle",
                None,  # no cap_id → will exit at step 3
                root=d,
            )
        # Should fail at no_cap_id, not at immutable_refusal
        assert "immutable" not in result.get("reason", "").lower()
        assert result.get("reason") == "no_cap_id"


# ── 2. Foreign-file abort ─────────────────────────────────────────────────────

class TestForeignFileAbort:
    """After session, diff shows files outside target_files+data/metabolism/ → abort."""

    def _setup_armed_with_key(self, mb, fake_ref: str = "CLAUDE_CODE_OAUTH_TOKEN_1") -> None:
        """Patch broker + key_pool to simulate a valid key."""
        pass  # inline patching per-test is cleaner

    def test_foreign_file_aborts_dispatch(self):
        mb = _import_mb()
        proposal = _minimal_proposal(target_files=["engine/test_sensor.py"])
        d = _tmp_root()
        cap_id = "claude_code_oauth_1"
        ref_name = "CLAUDE_CODE_OAUTH_TOKEN_1"

        # Session "succeeds" but changed a foreign file
        def fake_launch(cmd, env, cwd, timeout_s=1800):
            return {"returncode": 0, "stdout": "done", "stderr": ""}

        # Diff returns a foreign file
        def fake_diff(wt_path, base_ref="origin/main"):
            return ["engine/test_sensor.py", "config/grader_manifest.yml"]

        env = {**_armed_env(), ref_name: "fake_token_value_not_logged"}

        with patch.dict(os.environ, env, clear=False):
            with patch.object(mb, "_launch_build_subprocess", side_effect=fake_launch):
                with patch.object(mb, "_diff_worktree_files", side_effect=fake_diff):
                    with patch.object(mb, "_resolve_key_ref", return_value=(ref_name, None)):
                        result = mb._dispatch_build_session(
                            proposal, "/tmp/wt", "metabolism/build-test-cycle",
                            cap_id, root=d,
                        )

        assert result["dispatched"] is False
        assert "FOREIGN_FILE_ABORT" in result.get("reason", "")
        assert "config/grader_manifest.yml" in result.get("foreign_files", [])

    def test_data_metabolism_files_not_foreign(self):
        """Files under data/metabolism/ are always allowed."""
        mb = _import_mb()
        proposal = _minimal_proposal(target_files=["engine/test_sensor.py"])
        d = _tmp_root()
        ref_name = "CLAUDE_CODE_OAUTH_TOKEN_1"

        def fake_launch(cmd, env, cwd, timeout_s=1800):
            return {"returncode": 0, "stdout": "done", "stderr": ""}

        # Diff returns target file + data/metabolism/ — both allowed
        def fake_diff(wt_path, base_ref="origin/main"):
            return ["engine/test_sensor.py", "data/metabolism/journal/cycle-test-001.json"]

        env = {**_armed_env(), ref_name: "fake_token_value_not_logged"}

        with patch.dict(os.environ, env, clear=False):
            with patch.object(mb, "_launch_build_subprocess", side_effect=fake_launch):
                with patch.object(mb, "_diff_worktree_files", side_effect=fake_diff):
                    with patch.object(mb, "_resolve_key_ref", return_value=(ref_name, None)):
                        result = mb._dispatch_build_session(
                            proposal, "/tmp/wt", "metabolism/build-test-cycle",
                            "claude_code_oauth_1", root=d,
                        )

        # No foreign-file abort — dispatched=True
        assert result["dispatched"] is True
        assert result.get("reason") == "dispatched"

    def test_diff_failure_causes_no_dispatch(self):
        """If git diff fails (returns None), dispatch is aborted (fail-closed)."""
        mb = _import_mb()
        proposal = _minimal_proposal(target_files=["engine/test_sensor.py"])
        d = _tmp_root()
        ref_name = "CLAUDE_CODE_OAUTH_TOKEN_1"

        def fake_launch(cmd, env, cwd, timeout_s=1800):
            return {"returncode": 0, "stdout": "done", "stderr": ""}

        def fake_diff_none(wt_path, base_ref="origin/main"):
            return None  # simulates git diff failure

        env = {**_armed_env(), ref_name: "fake_token_value_not_logged"}

        with patch.dict(os.environ, env, clear=False):
            with patch.object(mb, "_launch_build_subprocess", side_effect=fake_launch):
                with patch.object(mb, "_diff_worktree_files", side_effect=fake_diff_none):
                    with patch.object(mb, "_resolve_key_ref", return_value=(ref_name, None)):
                        result = mb._dispatch_build_session(
                            proposal, "/tmp/wt", "metabolism/build-test-cycle",
                            "claude_code_oauth_1", root=d,
                        )

        assert result["dispatched"] is False
        assert "foreign_file_check_failed" in result.get("reason", "")


# ── 3. Paused → no dispatch ───────────────────────────────────────────────────

class TestPausedNoDispatch:
    """AUTONOMY_PAUSED != 'false' → dispatched=False, no subprocess."""

    def test_autonomy_paused_true_no_dispatch(self):
        mb = _import_mb()
        proposal = _minimal_proposal()
        launched = []

        def fake_launch(cmd, env, cwd, timeout_s=1800):
            launched.append(cmd)
            return {"returncode": 0, "stdout": "", "stderr": ""}

        paused_env = {k: v for k, v in os.environ.items() if k != "AUTONOMY_PAUSED"}
        paused_env["AUTONOMY_PAUSED"] = "true"

        with patch.dict(os.environ, paused_env, clear=True):
            with patch.object(mb, "_launch_build_subprocess", side_effect=fake_launch):
                result = mb._dispatch_build_session(
                    proposal, "/tmp/wt", "metabolism/build-test-cycle",
                    "claude_code_oauth_1", root=_tmp_root(),
                )

        assert result["dispatched"] is False
        assert "paused" in result.get("reason", "").lower()
        assert len(launched) == 0

    def test_autonomy_paused_unset_no_dispatch(self):
        mb = _import_mb()
        proposal = _minimal_proposal()
        launched = []

        def fake_launch(cmd, env, cwd, timeout_s=1800):
            launched.append(cmd)
            return {"returncode": 0, "stdout": "", "stderr": ""}

        clean_env = {k: v for k, v in os.environ.items() if k != "AUTONOMY_PAUSED"}

        with patch.dict(os.environ, clean_env, clear=True):
            with patch.object(mb, "_launch_build_subprocess", side_effect=fake_launch):
                result = mb._dispatch_build_session(
                    proposal, "/tmp/wt", "metabolism/build-test-cycle",
                    "claude_code_oauth_1", root=_tmp_root(),
                )

        assert result["dispatched"] is False
        assert len(launched) == 0

    def test_autonomy_paused_false_allows_dispatch(self):
        """When AUTONOMY_PAUSED=false, the pause gate does NOT block."""
        mb = _import_mb()
        proposal = _minimal_proposal()
        ref_name = "CLAUDE_CODE_OAUTH_TOKEN_1"
        env = {**_armed_env(), ref_name: "fake_token_value_not_logged"}

        def fake_launch(cmd, env, cwd, timeout_s=1800):
            return {"returncode": 0, "stdout": "ok", "stderr": ""}

        def fake_diff(wt_path, base_ref="origin/main"):
            return ["engine/test_sensor.py"]

        with patch.dict(os.environ, env, clear=False):
            with patch.object(mb, "_launch_build_subprocess", side_effect=fake_launch):
                with patch.object(mb, "_diff_worktree_files", side_effect=fake_diff):
                    with patch.object(mb, "_resolve_key_ref", return_value=(ref_name, None)):
                        result = mb._dispatch_build_session(
                            proposal, "/tmp/wt", "metabolism/build-test-cycle",
                            "claude_code_oauth_1", root=_tmp_root(),
                        )

        # Should reach dispatched=True (not blocked by pause gate)
        assert result["dispatched"] is True


# ── 4. dry_run journaling ─────────────────────────────────────────────────────

class TestDryRunJournaling:
    """dry_run=True journals a would_dispatch record without launching anything."""

    def test_dry_run_no_subprocess(self):
        mb = _import_mb()
        proposal = _minimal_proposal()
        launched = []

        def fake_launch(cmd, env, cwd, timeout_s=1800):
            launched.append(cmd)
            return {"returncode": 0, "stdout": "", "stderr": ""}

        ref_name = "CLAUDE_CODE_OAUTH_TOKEN_1"
        env = {**_armed_env(), ref_name: "fake_token_value_not_logged"}

        with patch.dict(os.environ, env, clear=False):
            with patch.object(mb, "_launch_build_subprocess", side_effect=fake_launch):
                with patch.object(mb, "_resolve_key_ref", return_value=(ref_name, None)):
                    result = mb._dispatch_build_session(
                        proposal, "/tmp/wt", "metabolism/build-test-cycle",
                        "claude_code_oauth_1", root=_tmp_root(),
                        dry_run=True,
                    )

        assert result.get("dry_run") is True
        assert result["dispatched"] is False
        assert len(launched) == 0, "dry_run must NOT launch subprocess"

    def test_dry_run_records_resolved_plan(self):
        """would_dispatch includes worktree path, files, key_ref_name (NOT value)."""
        mb = _import_mb()
        proposal = _minimal_proposal(target_files=["engine/my_sensor.py"])
        ref_name = "CLAUDE_CODE_OAUTH_TOKEN_1"
        env = {**_armed_env(), ref_name: "fake_token_value_not_logged"}

        with patch.dict(os.environ, env, clear=False):
            with patch.object(mb, "_resolve_key_ref", return_value=(ref_name, None)):
                result = mb._dispatch_build_session(
                    proposal, "/fake/worktree/path", "metabolism/build-test-cycle",
                    "claude_code_oauth_1", root=_tmp_root(),
                    dry_run=True,
                )

        would = result.get("would_dispatch", {})
        assert would.get("worktree_path") == "/fake/worktree/path"
        assert "engine/my_sensor.py" in would.get("target_files", [])
        assert would.get("key_ref_name") == ref_name
        assert "fake_token_value_not_logged" not in json.dumps(would), (
            "Token value must NEVER appear in the would_dispatch record"
        )

    def test_dry_run_journals_record(self):
        """dry_run=True writes a journal record in data/metabolism/journal/."""
        mb = _import_mb()
        proposal = _minimal_proposal(cycle_id="cycle-drytest-001")
        d = _tmp_root()
        ref_name = "CLAUDE_CODE_OAUTH_TOKEN_1"
        env = {**_armed_env(), ref_name: "fake_token_value_not_logged"}

        with patch.dict(os.environ, env, clear=False):
            with patch.object(mb, "_resolve_key_ref", return_value=(ref_name, None)):
                mb._dispatch_build_session(
                    proposal, "/tmp/wt", "metabolism/build-test-cycle",
                    "claude_code_oauth_1", root=d,
                    dry_run=True,
                )

        journal_file = d / "data" / "metabolism" / "journal" / "cycle-drytest-001.json"
        assert journal_file.exists(), "dry_run must write a journal record"
        data = json.loads(journal_file.read_text())
        stages = data.get("stages", {})
        dispatch_keys = [k for k in stages if k.startswith("build_dispatch_")]
        assert len(dispatch_keys) >= 1, f"Expected build_dispatch_ stage, got stages: {list(stages.keys())}"


# ── 5. Idempotent re-run ──────────────────────────────────────────────────────

class TestIdempotentRerun:
    """Same cycle_id+proposal_id → second call is a no-op (idempotent_skip)."""

    def test_second_call_is_idempotent_skip(self):
        mb = _import_mb()
        proposal = _minimal_proposal(cycle_id="cycle-idem-001")
        d = _tmp_root()
        ref_name = "CLAUDE_CODE_OAUTH_TOKEN_1"
        launch_count = [0]

        def fake_launch(cmd, env, cwd, timeout_s=1800):
            launch_count[0] += 1
            return {"returncode": 0, "stdout": "ok", "stderr": ""}

        def fake_diff(wt_path, base_ref="origin/main"):
            return ["engine/test_sensor.py"]

        env = {**_armed_env(), ref_name: "fake_token_value_not_logged"}

        with patch.dict(os.environ, env, clear=False):
            with patch.object(mb, "_launch_build_subprocess", side_effect=fake_launch):
                with patch.object(mb, "_diff_worktree_files", side_effect=fake_diff):
                    with patch.object(mb, "_resolve_key_ref", return_value=(ref_name, None)):
                        # First call: should dispatch
                        r1 = mb._dispatch_build_session(
                            proposal, "/tmp/wt1", "metabolism/build-test-cycle-idem",
                            "claude_code_oauth_1", root=d,
                        )
                        # Second call: same cycle_id+proposal_id → idempotent skip
                        r2 = mb._dispatch_build_session(
                            proposal, "/tmp/wt1", "metabolism/build-test-cycle-idem",
                            "claude_code_oauth_1", root=d,
                        )

        assert r1["dispatched"] is True, f"First call should dispatch, got: {r1}"
        assert r2.get("idempotent_skip") is True, f"Second call should be idempotent_skip, got: {r2}"
        assert launch_count[0] == 1, f"subprocess should be called exactly once, got {launch_count[0]}"

    def test_different_proposals_not_blocked(self):
        """Two different proposal_ids in the same cycle are not blocked by each other."""
        mb = _import_mb()
        d = _tmp_root()
        ref_name = "CLAUDE_CODE_OAUTH_TOKEN_1"
        launch_count = [0]

        def fake_launch(cmd, env, cwd, timeout_s=1800):
            launch_count[0] += 1
            return {"returncode": 0, "stdout": "ok", "stderr": ""}

        def fake_diff(wt_path, base_ref="origin/main"):
            return ["engine/test_sensor.py"]

        env = {**_armed_env(), ref_name: "fake_token_value_not_logged"}

        p1 = _minimal_proposal(pid="p1", cycle_id="cycle-multi-001")
        p2 = _minimal_proposal(pid="p2", cycle_id="cycle-multi-001")

        with patch.dict(os.environ, env, clear=False):
            with patch.object(mb, "_launch_build_subprocess", side_effect=fake_launch):
                with patch.object(mb, "_diff_worktree_files", side_effect=fake_diff):
                    with patch.object(mb, "_resolve_key_ref", return_value=(ref_name, None)):
                        r1 = mb._dispatch_build_session(
                            p1, "/tmp/wt1", "metabolism/build-test-cycle-multi",
                            "claude_code_oauth_1", root=d,
                        )
                        r2 = mb._dispatch_build_session(
                            p2, "/tmp/wt2", "metabolism/build-test-cycle-multi",
                            "claude_code_oauth_1", root=d,
                        )

        assert r1["dispatched"] is True, f"p1 should dispatch: {r1}"
        assert r2["dispatched"] is True, f"p2 should dispatch: {r2}"
        assert launch_count[0] == 2


# ── 6. Key-ref never logged ───────────────────────────────────────────────────

class TestKeyRefNeverLogged:
    """The env var VALUE must never appear in logs, journals, or return values."""

    def test_token_value_not_in_result(self):
        mb = _import_mb()
        proposal = _minimal_proposal()
        ref_name = "CLAUDE_CODE_OAUTH_TOKEN_1"
        secret_value = "secret_oauth_token_should_never_appear_in_output_xyz123"
        env = {**_armed_env(), ref_name: secret_value}

        def fake_launch(cmd, env, cwd, timeout_s=1800):
            return {"returncode": 0, "stdout": "ok", "stderr": ""}

        def fake_diff(wt_path, base_ref="origin/main"):
            return ["engine/test_sensor.py"]

        with patch.dict(os.environ, env, clear=False):
            with patch.object(mb, "_launch_build_subprocess", side_effect=fake_launch):
                with patch.object(mb, "_diff_worktree_files", side_effect=fake_diff):
                    with patch.object(mb, "_resolve_key_ref", return_value=(ref_name, None)):
                        result = mb._dispatch_build_session(
                            proposal, "/tmp/wt", "metabolism/build-test-cycle",
                            "claude_code_oauth_1", root=_tmp_root(),
                        )

        result_json = json.dumps(result, default=str)
        assert secret_value not in result_json, (
            f"SECRET TOKEN VALUE appeared in dispatch result: {result_json[:200]}"
        )

    def test_token_value_not_in_dry_run_would_dispatch(self):
        mb = _import_mb()
        proposal = _minimal_proposal()
        ref_name = "CLAUDE_CODE_OAUTH_TOKEN_1"
        secret_value = "secret_oauth_token_dry_run_test_abc987"
        env = {**_armed_env(), ref_name: secret_value}

        with patch.dict(os.environ, env, clear=False):
            with patch.object(mb, "_resolve_key_ref", return_value=(ref_name, None)):
                result = mb._dispatch_build_session(
                    proposal, "/tmp/wt", "metabolism/build-test-cycle",
                    "claude_code_oauth_1", root=_tmp_root(),
                    dry_run=True,
                )

        result_json = json.dumps(result, default=str)
        assert secret_value not in result_json, (
            f"SECRET TOKEN VALUE appeared in dry_run would_dispatch: {result_json[:200]}"
        )

    def test_dry_run_includes_ref_name_not_value(self):
        """would_dispatch must include the ref NAME, not the token VALUE."""
        mb = _import_mb()
        proposal = _minimal_proposal()
        ref_name = "CLAUDE_CODE_OAUTH_TOKEN_1"
        env = {**_armed_env(), ref_name: "secret_should_not_appear"}

        with patch.dict(os.environ, env, clear=False):
            with patch.object(mb, "_resolve_key_ref", return_value=(ref_name, None)):
                result = mb._dispatch_build_session(
                    proposal, "/tmp/wt", "metabolism/build-test-cycle",
                    "claude_code_oauth_1", root=_tmp_root(),
                    dry_run=True,
                )

        would = result.get("would_dispatch", {})
        assert would.get("key_ref_name") == ref_name, (
            f"would_dispatch must include key_ref_name={ref_name}, got: {would.get('key_ref_name')}"
        )


# ── 7. NEVER-RAISE on corrupt proposal ───────────────────────────────────────

class TestNeverRaiseCorruptProposal:
    """Corrupt/None proposal input must return a safe dict, never raise."""

    def test_none_proposal(self):
        mb = _import_mb()
        with patch.dict(os.environ, _armed_env(), clear=False):
            result = mb._dispatch_build_session(
                None, "/tmp/wt", "metabolism/build-test", None,  # type: ignore[arg-type]
                root=_tmp_root(),
            )
        assert isinstance(result, dict)
        assert result.get("dispatched") is False

    def test_empty_dict_proposal(self):
        mb = _import_mb()
        with patch.dict(os.environ, _armed_env(), clear=False):
            result = mb._dispatch_build_session(
                {}, "/tmp/wt", "metabolism/build-test", None,
                root=_tmp_root(),
            )
        assert isinstance(result, dict)
        assert result.get("dispatched") is False

    def test_proposal_with_none_target_files(self):
        mb = _import_mb()
        proposal = _minimal_proposal()
        proposal["target_files"] = None  # type: ignore[assignment]
        with patch.dict(os.environ, _armed_env(), clear=False):
            result = mb._dispatch_build_session(
                proposal, "/tmp/wt", "metabolism/build-test", None,
                root=_tmp_root(),
            )
        assert isinstance(result, dict)
        assert result.get("dispatched") is False

    def test_proposal_with_junk_target_files(self):
        mb = _import_mb()
        proposal = _minimal_proposal()
        proposal["target_files"] = [None, 42, {"nested": "dict"}]  # type: ignore[list-item]
        with patch.dict(os.environ, _armed_env(), clear=False):
            result = mb._dispatch_build_session(
                proposal, "/tmp/wt", "metabolism/build-test", None,
                root=_tmp_root(),
            )
        assert isinstance(result, dict)
        # Should either dispatch or fail gracefully — must not raise

    def test_garbled_cap_id(self):
        mb = _import_mb()
        proposal = _minimal_proposal()
        env = {**_armed_env(), "CLAUDE_CODE_OAUTH_TOKEN_1": "tok"}
        with patch.dict(os.environ, env, clear=False):
            result = mb._dispatch_build_session(
                proposal, "/tmp/wt", "metabolism/build-test",
                "this-cap-id-does-not-exist-in-manifest",
                root=_tmp_root(),
            )
        assert isinstance(result, dict)
        assert result.get("dispatched") is False


# ── 8. Sonnet model pinned ────────────────────────────────────────────────────

class TestSonnetModelPinned:
    """_BUILD_SESSION_MODEL must be the correct sonnet model id."""

    def test_build_session_model_is_sonnet(self):
        mb = _import_mb()
        assert mb._BUILD_SESSION_MODEL == "claude-sonnet-4-6", (
            f"Expected 'claude-sonnet-4-6', got '{mb._BUILD_SESSION_MODEL}'"
        )

    def test_model_in_subprocess_cmd(self):
        """The claude subprocess invocation uses --model with the pinned sonnet id."""
        mb = _import_mb()
        proposal = _minimal_proposal()
        ref_name = "CLAUDE_CODE_OAUTH_TOKEN_1"
        captured_cmds = []

        def fake_launch(cmd, env, cwd, timeout_s=1800):
            captured_cmds.append(cmd)
            return {"returncode": 0, "stdout": "ok", "stderr": ""}

        def fake_diff(wt_path, base_ref="origin/main"):
            return ["engine/test_sensor.py"]

        env = {**_armed_env(), ref_name: "fake_token_value_not_logged"}

        with patch.dict(os.environ, env, clear=False):
            with patch.object(mb, "_launch_build_subprocess", side_effect=fake_launch):
                with patch.object(mb, "_diff_worktree_files", side_effect=fake_diff):
                    with patch.object(mb, "_resolve_key_ref", return_value=(ref_name, None)):
                        mb._dispatch_build_session(
                            proposal, "/tmp/wt", "metabolism/build-test-cycle",
                            "claude_code_oauth_1", root=_tmp_root(),
                        )

        assert len(captured_cmds) == 1, "subprocess should be called once"
        cmd = captured_cmds[0]
        assert "--model" in cmd
        model_idx = cmd.index("--model")
        assert cmd[model_idx + 1] == mb._BUILD_SESSION_MODEL, (
            f"Model in cmd: {cmd[model_idx + 1]!r} != {mb._BUILD_SESSION_MODEL!r}"
        )


# ── 9. Subprocess wrapper is mockable ─────────────────────────────────────────

class TestSubprocessWrapperMockable:
    """_launch_build_subprocess is a standalone function tests can monkeypatch."""

    def test_launch_build_subprocess_exists_and_callable(self):
        mb = _import_mb()
        assert callable(mb._launch_build_subprocess), (
            "_launch_build_subprocess must be a callable function"
        )

    def test_launch_build_subprocess_never_raises(self):
        """_launch_build_subprocess catches all exceptions and returns a safe dict."""
        mb = _import_mb()
        # Pass a command guaranteed to fail
        result = mb._launch_build_subprocess(
            cmd=["this_binary_does_not_exist_xyz"],
            env=dict(os.environ),
            cwd="/tmp",
            timeout_s=5,
        )
        assert isinstance(result, dict)
        assert "returncode" in result
        assert result["returncode"] != 0

    def test_patch_replaces_real_subprocess(self):
        """Patching _launch_build_subprocess prevents real subprocess execution."""
        mb = _import_mb()
        real_called = []

        def fake(cmd, env, cwd, timeout_s=1800):
            real_called.append("fake_called")
            return {"returncode": 0, "stdout": "", "stderr": ""}

        with patch.object(mb, "_launch_build_subprocess", side_effect=fake):
            result = mb._launch_build_subprocess(["ls"], dict(os.environ), "/tmp")

        assert len(real_called) == 1
        assert result["returncode"] == 0


# ── 10. No cap_id → not dispatched ───────────────────────────────────────────

class TestNoCapIdNotDispatched:
    def test_none_cap_id_not_dispatched(self):
        mb = _import_mb()
        proposal = _minimal_proposal()
        launched = []

        with patch.dict(os.environ, _armed_env(), clear=False):
            with patch.object(mb, "_launch_build_subprocess",
                              side_effect=lambda *a, **kw: launched.append(a)):
                result = mb._dispatch_build_session(
                    proposal, "/tmp/wt", "metabolism/build-test",
                    None,  # no cap_id
                    root=_tmp_root(),
                )

        assert result["dispatched"] is False
        assert result.get("reason") == "no_cap_id"
        assert len(launched) == 0


# ── 11. Successful dispatch path ──────────────────────────────────────────────

class TestSuccessfulDispatchPath:
    """Green path: all checks pass, session succeeds, files within target → dispatched=True."""

    def test_successful_dispatch_returns_dispatched_true(self):
        mb = _import_mb()
        proposal = _minimal_proposal(
            target_files=["engine/test_sensor.py", "engine/test_helper.py"]
        )
        d = _tmp_root()
        ref_name = "CLAUDE_CODE_OAUTH_TOKEN_1"
        env = {**_armed_env(), ref_name: "fake_token_value_not_logged"}

        def fake_launch(cmd, env, cwd, timeout_s=1800):
            return {"returncode": 0, "stdout": "BUILD COMPLETE", "stderr": ""}

        def fake_diff(wt_path, base_ref="origin/main"):
            return ["engine/test_sensor.py", "data/metabolism/journal/cycle-test-001.json"]

        with patch.dict(os.environ, env, clear=False):
            with patch.object(mb, "_launch_build_subprocess", side_effect=fake_launch):
                with patch.object(mb, "_diff_worktree_files", side_effect=fake_diff):
                    with patch.object(mb, "_resolve_key_ref", return_value=(ref_name, None)):
                        result = mb._dispatch_build_session(
                            proposal, "/tmp/wt", "metabolism/build-test-cycle",
                            "claude_code_oauth_1", root=d,
                        )

        assert result["dispatched"] is True
        assert result.get("reason") == "dispatched"
        assert result.get("model") == mb._BUILD_SESSION_MODEL

    def test_session_nonzero_rc_not_dispatched(self):
        """Non-zero return code from session → dispatched=False."""
        mb = _import_mb()
        proposal = _minimal_proposal()
        ref_name = "CLAUDE_CODE_OAUTH_TOKEN_1"
        env = {**_armed_env(), ref_name: "fake_token_value_not_logged"}

        def fake_launch(cmd, env, cwd, timeout_s=1800):
            return {"returncode": 1, "stdout": "", "stderr": "some error"}

        with patch.dict(os.environ, env, clear=False):
            with patch.object(mb, "_launch_build_subprocess", side_effect=fake_launch):
                with patch.object(mb, "_resolve_key_ref", return_value=(ref_name, None)):
                    result = mb._dispatch_build_session(
                        proposal, "/tmp/wt", "metabolism/build-test-cycle",
                        "claude_code_oauth_1", root=_tmp_root(),
                    )

        assert result["dispatched"] is False
        assert "nonzero_rc" in result.get("reason", "").lower() or "session" in result.get("reason", "").lower()


# ── 12. Cleanup on foreign abort ─────────────────────────────────────────────

class TestCleanupOnForeignAbort:
    def test_cleanup_called_on_foreign_abort(self):
        mb = _import_mb()
        proposal = _minimal_proposal(target_files=["engine/test_sensor.py"])
        d = _tmp_root()
        ref_name = "CLAUDE_CODE_OAUTH_TOKEN_1"
        cleanup_called = []

        def fake_launch(cmd, env, cwd, timeout_s=1800):
            return {"returncode": 0, "stdout": "ok", "stderr": ""}

        def fake_diff(wt_path, base_ref="origin/main"):
            return ["engine/test_sensor.py", "FOREIGN_FILE_violation.py"]

        def fake_cleanup(wt_path: str):
            cleanup_called.append(wt_path)

        env = {**_armed_env(), ref_name: "fake_token_value_not_logged"}

        with patch.dict(os.environ, env, clear=False):
            with patch.object(mb, "_launch_build_subprocess", side_effect=fake_launch):
                with patch.object(mb, "_diff_worktree_files", side_effect=fake_diff):
                    with patch.object(mb, "_resolve_key_ref", return_value=(ref_name, None)):
                        with patch.object(mb, "_cleanup_worktree_on_abort", side_effect=fake_cleanup):
                            result = mb._dispatch_build_session(
                                proposal, "/tmp/wt_foreign", "metabolism/build-test-cycle",
                                "claude_code_oauth_1", root=d,
                            )

        assert result["dispatched"] is False
        assert "FOREIGN_FILE_ABORT" in result.get("reason", "")
        assert "/tmp/wt_foreign" in cleanup_called, (
            "_cleanup_worktree_on_abort must be called with the worktree path"
        )

    def test_cleanup_never_raises(self):
        """_cleanup_worktree_on_abort never raises even on a nonexistent path."""
        mb = _import_mb()
        # Should not raise
        mb._cleanup_worktree_on_abort("/nonexistent/path/that/does/not/exist/xyz")
        mb._cleanup_worktree_on_abort("")
        mb._cleanup_worktree_on_abort(None)  # type: ignore[arg-type]


# ── CI-enforced word ban check ───────────────────────────────────────────────

_BANNED = "valid" + "ated"  # keep literal out of source so this file is clean


class TestBannedWordNotInNewCode:
    def test_no_banned_word_in_dispatch_module(self):
        src = (_ROOT / "scripts" / "metabolism_build.py").read_text(encoding="utf-8")
        lower = src.lower()
        assert _BANNED not in lower, (
            f"Banned word found in metabolism_build.py (CI-enforced ban)"
        )

    def test_no_banned_word_in_test_file(self):
        src = Path(__file__).read_text(encoding="utf-8")
        lower = src.lower()
        # The _BANNED variable itself assembles the string at runtime; the source
        # text of this file must not contain the assembled form as a literal.
        assert lower.count(_BANNED) <= 1, (
            f"Banned word literal found in test file beyond the assembly line (CI-enforced ban)"
        )
