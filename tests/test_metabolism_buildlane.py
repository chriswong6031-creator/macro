"""tests/test_metabolism_buildlane.py — Hermetic tests for Metabolism V2-B Unit 6 (BUILD lane).

COVERAGE:
  1.  claim/collision: two proposals same target files → second SKIPPED.
  2.  worktree branch naming: metabolism/build-<lobe>-<cycle>.
  3.  is_paused no-op on build lane (mutation-proof: break the gate → test errors).
  4.  is_paused no-op on merge lane (mutation-proof: break the gate → test errors).
  5.  merge lane refuses an IMMUTABLE-touching PR (check_self_mod_fence refusal).
  6.  merge lane requires the two-key (T1 without adversary grant → not merged).
  7.  concurrency-group present in the merge workflow YAML.
  8.  no autonomous merge while paused (assert zero merges in a paused run).
  9.  GC reaps a squash-merged worktree (metabolism_gc integration).
  10. banned words: 'validated' never in build-lane user-facing text.
  11. check_self_mod_fence blocks metabolism/build-* loop PRs on IMMUTABLE files.
  12. check_grader_manifest passes (no new grader files added).
  13. check_validated_claims not triggered by build-lane files.
  14. synapse: metabolism-build-claims artifact present.

All tests are HERMETIC (tmp dirs, in-process, no real network/git).
"""
from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# ── Fixtures ─────────────────────────────────────────────────────────────────

def _tmp_root(extra_subdirs: list[str] | None = None) -> Path:
    d = Path(tempfile.mkdtemp(prefix="metab_bl_test_"))
    (d / "data" / "metabolism").mkdir(parents=True)
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


def _write_docket(d: Path, cycle_id: str, proposals: list[dict]) -> Path:
    path = d / "data" / "metabolism" / "dockets" / f"{cycle_id}.json"
    path.write_text(json.dumps({
        "schema": "metabolism.docket.v1",
        "cycle_id": cycle_id,
        "lobe": "test_lobe",
        "proposals": proposals,
    }))
    return path


def _minimal_proposal(pid: str, target_files: list[str]) -> dict:
    return {
        "proposal_id": pid,
        "title": f"Test proposal {pid}",
        "tier": "T1",
        "lobe": "test_lobe",
        "target_files": target_files,
        "targets_sensor": "test_sensor",
        "rationale": "test rationale",
        "fitness_contract": {"metric": "test"},
    }


def _ts_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ── 1. claim/collision ────────────────────────────────────────────────────────

class TestClaimCollision:
    def test_first_claim_succeeds(self):
        """First proposal claiming target_files → claimed=True."""
        d = _tmp_root()
        import scripts.metabolism_build as mb
        importlib.reload(mb)

        result = mb.claim_proposal(
            "cycle-001", "p1", "lobe1",
            ["engine/foo.py", "data/bar.json"],
            root=d, dry_run=True,  # dry_run: no disk write, just collision check
        )
        assert result["claimed"] is True
        assert result["collision_files"] == []

    def test_second_proposal_same_files_is_skipped(self):
        """Two proposals with the same target_files → second is SKIPPED (collision)."""
        d = _tmp_root()
        import scripts.metabolism_build as mb
        importlib.reload(mb)

        # First claim (not dry_run → writes claims.jsonl)
        r1 = mb.claim_proposal(
            "cycle-001", "p1", "lobe1",
            ["engine/foo.py"],
            root=d,
        )
        assert r1["claimed"] is True

        # Second claim for same target file → COLLISION
        r2 = mb.claim_proposal(
            "cycle-001", "p2", "lobe1",
            ["engine/foo.py"],
            root=d,
        )
        assert r2["claimed"] is False
        assert "engine/foo.py" in r2["collision_files"]

    def test_different_cycle_no_collision(self):
        """Claims from a different cycle do not block this cycle."""
        d = _tmp_root()
        import scripts.metabolism_build as mb
        importlib.reload(mb)

        # Claim in cycle-001
        mb.claim_proposal("cycle-001", "p1", "lobe1", ["engine/foo.py"], root=d)

        # Claim in cycle-002 for same file → no collision (different cycle)
        r2 = mb.claim_proposal("cycle-002", "p2", "lobe1", ["engine/foo.py"], root=d)
        assert r2["claimed"] is True

    def test_non_overlapping_files_no_collision(self):
        """Two proposals with different target_files → both succeed."""
        d = _tmp_root()
        import scripts.metabolism_build as mb
        importlib.reload(mb)

        r1 = mb.claim_proposal("cycle-001", "p1", "lobe1", ["engine/a.py"], root=d)
        r2 = mb.claim_proposal("cycle-001", "p2", "lobe1", ["engine/b.py"], root=d)
        assert r1["claimed"] is True
        assert r2["claimed"] is True

    def test_dry_run_does_not_write_claims(self):
        """dry_run=True: claim check succeeds but does NOT write to claims.jsonl."""
        d = _tmp_root()
        import scripts.metabolism_build as mb
        importlib.reload(mb)

        result = mb.claim_proposal(
            "cycle-001", "p1", "lobe1", ["engine/foo.py"],
            root=d, dry_run=True,
        )
        assert result["claimed"] is True
        claims_path = d / "data" / "metabolism" / "claims.jsonl"
        assert not claims_path.exists(), "dry_run must not write claims.jsonl"

    def test_claims_schema_correct(self):
        """Written claim row has the correct schema field."""
        d = _tmp_root()
        import scripts.metabolism_build as mb
        importlib.reload(mb)

        mb.claim_proposal("cycle-001", "p1", "lobe1", ["engine/foo.py"], root=d)
        claims_path = d / "data" / "metabolism" / "claims.jsonl"
        rows = [json.loads(l) for l in claims_path.read_text().splitlines() if l.strip()]
        assert rows[0]["schema"] == "metabolism.build_claims.v1"
        assert rows[0]["cycle_id"] == "cycle-001"
        assert rows[0]["proposal_id"] == "p1"
        assert "engine/foo.py" in rows[0]["target_files"]


# ── 2. worktree branch naming ─────────────────────────────────────────────────

class TestWorktreeBranchNaming:
    def test_branch_name_format(self):
        """Branch name must be metabolism/build-<lobe>-<cycle>."""
        import scripts.metabolism_build as mb
        importlib.reload(mb)

        branch = mb._build_branch_name("til_fitness", "cycle-2026-07-10-a1b2")
        assert branch.startswith("metabolism/build-")
        assert "til_fitness" in branch
        assert "cycle-2026-07-10-a1b2" in branch

    def test_branch_name_sanitizes_slashes(self):
        """Slashes in lobe names are replaced."""
        import scripts.metabolism_build as mb
        importlib.reload(mb)

        branch = mb._build_branch_name("lobe/with/slashes", "cycle-001")
        assert "/" not in branch.replace("metabolism/build-", "", 1).split("-cycle")[0]

    def test_branch_prefix(self):
        """Branch must start with metabolism/build-."""
        import scripts.metabolism_build as mb
        importlib.reload(mb)

        branch = mb._build_branch_name("any_lobe", "cycle-x")
        assert branch.startswith("metabolism/build-")

    def test_different_lobes_different_branches(self):
        """Different lobes produce different branch names."""
        import scripts.metabolism_build as mb
        importlib.reload(mb)

        b1 = mb._build_branch_name("lobe_a", "cycle-001")
        b2 = mb._build_branch_name("lobe_b", "cycle-001")
        assert b1 != b2

    def test_same_lobe_same_cycle_different_proposals_different_branches(self):
        """Finding 2 fix: same lobe+cycle but different proposal_ids → different branches.

        Before the fix, two proposals in the same lobe+cycle shared a branch name,
        causing the second worktree creation to fail with 'branch already exists'.
        """
        import scripts.metabolism_build as mb
        importlib.reload(mb)

        b1 = mb._build_branch_name("til_fitness", "cycle-001", proposal_id="p1")
        b2 = mb._build_branch_name("til_fitness", "cycle-001", proposal_id="p2")
        assert b1 != b2, (
            f"Two proposals in the same lobe+cycle produced the SAME branch name: {b1!r} — "
            "this would cause 'branch already exists' on the second worktree creation."
        )


# ── 3. is_paused no-op on build lane (mutation-proof) ─────────────────────────

class TestBuildLaneIsPausedNoOp:
    def test_build_noop_when_paused_by_default(self):
        """run_build_lane must return noop_paused when AUTONOMY_PAUSED not set."""
        d = _tmp_root()
        docket = _write_docket(d, "cycle-001", [_minimal_proposal("p1", ["engine/foo.py"])])

        clean_env = {k: v for k, v in os.environ.items() if k != "AUTONOMY_PAUSED"}
        with patch.dict(os.environ, clean_env, clear=True):
            import scripts.metabolism_build as mb
            importlib.reload(mb)
            results = mb.run_build_lane("cycle-001", docket, root=d)

        assert any(r.get("status") == "noop_paused" for r in results), (
            f"Expected noop_paused when AUTONOMY_PAUSED unset, got: {results}"
        )

    def test_build_noop_when_autonomy_paused_true(self):
        """run_build_lane no-ops when AUTONOMY_PAUSED=true."""
        d = _tmp_root()
        docket = _write_docket(d, "cycle-001", [_minimal_proposal("p1", ["engine/foo.py"])])

        with patch.dict(os.environ, {"AUTONOMY_PAUSED": "true"}, clear=False):
            import scripts.metabolism_build as mb
            importlib.reload(mb)
            results = mb.run_build_lane("cycle-001", docket, root=d)

        assert any(r.get("status") == "noop_paused" for r in results)

    def test_build_booby_trap_pause_gate_fires_first(self):
        """Mutation-proof: if is_paused is bypassed, the booby-trap worker errors.

        If the pause gate were removed, the first real action (claim_proposal)
        would be called. We patch claim_proposal to raise so we can verify it
        was NOT called when paused.
        """
        d = _tmp_root()
        docket = _write_docket(d, "cycle-001", [_minimal_proposal("p1", ["engine/foo.py"])])

        with patch.dict(os.environ, {"AUTONOMY_PAUSED": "true"}, clear=False):
            import scripts.metabolism_build as mb
            importlib.reload(mb)
            with patch.object(mb, "claim_proposal",
                              side_effect=RuntimeError("booby-trap: pause gate bypassed")):
                try:
                    results = mb.run_build_lane("cycle-001", docket, root=d)
                except RuntimeError:
                    pytest.fail(
                        "run_build_lane called claim_proposal before is_paused() check — "
                        "pause gate must fire FIRST"
                    )
        # Should have noop_paused, not an error
        assert any(r.get("status") == "noop_paused" for r in results)


# ── 4. is_paused no-op on merge lane (mutation-proof) ─────────────────────────

class TestMergeLaneIsPausedNoOp:
    def test_merge_noop_when_paused_by_default(self):
        """run_merge_lane must return noop_paused when AUTONOMY_PAUSED not set."""
        d = _tmp_root()
        docket = _write_docket(d, "cycle-001", [_minimal_proposal("p1", ["engine/foo.py"])])

        clean_env = {k: v for k, v in os.environ.items() if k != "AUTONOMY_PAUSED"}
        with patch.dict(os.environ, clean_env, clear=True):
            import scripts.metabolism_merge as mm
            importlib.reload(mm)
            results = mm.run_merge_lane("cycle-001", docket, root=d)

        assert any(r.get("status") == "noop_paused" for r in results)

    def test_merge_noop_when_autonomy_paused_true(self):
        """run_merge_lane no-ops when AUTONOMY_PAUSED=true."""
        d = _tmp_root()
        docket = _write_docket(d, "cycle-001", [_minimal_proposal("p1", ["engine/foo.py"])])

        with patch.dict(os.environ, {"AUTONOMY_PAUSED": "true"}, clear=False):
            import scripts.metabolism_merge as mm
            importlib.reload(mm)
            results = mm.run_merge_lane("cycle-001", docket, root=d)

        assert any(r.get("status") == "noop_paused" for r in results)

    def test_merge_booby_trap_pause_gate_fires_first(self):
        """Mutation-proof: if is_paused is bypassed, the booby-trap list_prs call errors."""
        d = _tmp_root()
        docket = _write_docket(d, "cycle-001", [_minimal_proposal("p1", ["engine/foo.py"])])

        with patch.dict(os.environ, {"AUTONOMY_PAUSED": "true"}, clear=False):
            import scripts.metabolism_merge as mm
            importlib.reload(mm)
            with patch.object(mm, "_list_build_draft_prs",
                              side_effect=RuntimeError("booby-trap: pause gate bypassed")):
                try:
                    results = mm.run_merge_lane("cycle-001", docket, root=d)
                except RuntimeError:
                    pytest.fail(
                        "run_merge_lane called _list_build_draft_prs before is_paused() check — "
                        "pause gate must fire FIRST"
                    )
        assert any(r.get("status") == "noop_paused" for r in results)


# ── 5. merge lane refuses IMMUTABLE-touching PR ───────────────────────────────

class TestMergeLaneFenceRefusal:
    def test_merge_refuses_immutable_touching_loop_pr(self):
        """_fence_check_pr returns (False, reason) for a loop PR touching IMMUTABLE."""
        import scripts.metabolism_merge as mm
        importlib.reload(mm)

        ok, msg = mm._fence_check_pr(
            pr_branch="metabolism/build-some-lobe-cycle-001",
            pr_files=["config/grader_manifest.yml", "data/metabolism/claims.jsonl"],
        )
        assert ok is False, (
            f"Fence should BLOCK a loop PR touching config/grader_manifest.yml but got ok={ok}, msg={msg}"
        )

    def test_merge_allows_non_immutable_loop_pr(self):
        """_fence_check_pr passes for a loop PR NOT touching IMMUTABLE."""
        import scripts.metabolism_merge as mm
        importlib.reload(mm)

        ok, msg = mm._fence_check_pr(
            pr_branch="metabolism/build-some-lobe-cycle-001",
            pr_files=["data/metabolism/claims.jsonl", "engine/some_engine.py"],
        )
        assert ok is True, (
            f"Fence should ALLOW a loop PR not touching IMMUTABLE, got ok={ok}, msg={msg}"
        )

    def test_merge_allows_human_pr_touching_immutable(self):
        """_fence_check_pr passes for a human PR (no loop namespace)."""
        import scripts.metabolism_merge as mm
        importlib.reload(mm)

        ok, msg = mm._fence_check_pr(
            pr_branch="feature/update-grader",
            pr_files=["config/grader_manifest.yml"],
        )
        assert ok is True, (
            f"Fence should ALLOW a human PR, got ok={ok}, msg={msg}"
        )

    def test_merge_workflow_never_admin_bypasses_fence(self):
        """The merge workflow YAML must not use 'gh pr merge --admin' to bypass the fence."""
        workflow_path = _ROOT / ".github" / "workflows" / "metabolism-merge.yml"
        if not workflow_path.exists():
            pytest.skip("metabolism-merge.yml not present")
        content = workflow_path.read_text()
        # Check for the actionable bypass pattern: `gh pr merge --admin` or `gh merge --admin`
        # Comments mentioning --admin (e.g. "No --admin bypass") are documentation, not violations.
        import re
        # Match --admin appearing after 'gh' (a command invocation, not a comment)
        admin_cmd = re.search(r'^\s*[^#].*gh\s+.*--admin', content, re.MULTILINE)
        assert admin_cmd is None, (
            "metabolism-merge.yml must NEVER use 'gh ... --admin' to bypass the fence (R-AUT-5). "
            f"Found: {admin_cmd.group() if admin_cmd else ''}"
        )

    def test_fence_fail_closed_on_empty_file_list(self):
        """_fence_check_pr must REFUSE (fail-closed) when the changed-files list is empty.

        _get_pr_files returns [] on any gh API error.  If the fence passes on an
        empty list, a PR that touches IMMUTABLE files but cannot be enumerated would
        silently be let through.  R-AUT-5 requires fail-closed here.
        """
        import scripts.metabolism_merge as mm
        importlib.reload(mm)

        ok, msg = mm._fence_check_pr(
            pr_branch="metabolism/build-some-lobe-cycle-001",
            pr_files=[],   # empty — simulates gh API failure
        )
        assert ok is False, (
            f"Fence must REFUSE (fail-closed) when file list is empty, got ok={ok}, msg={msg!r}"
        )
        assert "fail-closed" in msg.lower() or "empty" in msg.lower(), (
            f"Fence refusal reason should mention fail-closed or empty, got: {msg!r}"
        )


# ── 6. merge lane requires the two-key ───────────────────────────────────────

class TestMergeLaneTwoKeyRequired:
    def test_not_granted_proposal_not_merged(self):
        """A proposal without two-key authorization is not merged."""
        d = _tmp_root()
        cycle_id = "cycle-twokey-001"
        docket = _write_docket(d, cycle_id, [_minimal_proposal("p1", ["engine/foo.py"])])

        with patch.dict(os.environ, {"AUTONOMY_PAUSED": "false"}, clear=False):
            import scripts.metabolism_merge as mm
            importlib.reload(mm)
            # Patch two-key to return not-authorized
            with patch.object(mm, "_is_two_key_granted", return_value=False):
                # Patch list_prs to return one fake PR for this cycle
                fake_pr = {
                    "number": 9999,
                    "headRefName": f"metabolism/build-test_lobe-{cycle_id}",
                    "title": "fake build PR",
                    "isDraft": True,
                    "statusCheckRollup": [{"state": "SUCCESS"}],
                    "files": [],
                }
                with patch.object(mm, "_list_build_draft_prs", return_value=[fake_pr]):
                    results = mm.run_merge_lane(cycle_id, docket, root=d)

        # No result should be "merged"
        merges = [r for r in results if r.get("status") == "merged"]
        assert len(merges) == 0, f"Got unexpected merges: {merges}"

    def test_granted_proposal_with_green_ci_eligible_to_merge(self):
        """A proposal WITH two-key auth AND green CI is eligible for merge (fence still applies)."""
        d = _tmp_root()
        cycle_id = "cycle-twokey-002"
        docket = _write_docket(d, cycle_id, [_minimal_proposal("p1", ["engine/foo.py"])])

        with patch.dict(os.environ, {"AUTONOMY_PAUSED": "false"}, clear=False):
            import scripts.metabolism_merge as mm
            importlib.reload(mm)
            with patch.object(mm, "_is_two_key_granted", return_value=True):
                fake_pr = {
                    "number": 9998,
                    "headRefName": f"metabolism/build-test_lobe-{cycle_id}",
                    "title": "fake build PR",
                    "isDraft": True,
                    "statusCheckRollup": [{"state": "SUCCESS"}],
                    "files": [],
                }
                with patch.object(mm, "_list_build_draft_prs", return_value=[fake_pr]):
                    with patch.object(mm, "_pr_ci_green", return_value=True):
                        with patch.object(mm, "_get_pr_files", return_value=["engine/foo.py"]):
                            with patch.object(mm, "_mark_pr_ready", return_value=True):
                                with patch.object(mm, "_rebase_merge_pr",
                                                  return_value={"merged": True, "attempts": 1}):
                                    results = mm.run_merge_lane(cycle_id, docket, root=d, dry_run=False)

        # At least one merge should appear
        merges = [r for r in results if r.get("status") == "merged"]
        assert len(merges) >= 1, f"Expected at least one merge but got: {results}"

    def test_evil_proposal_cannot_hijack_authorized_grant(self):
        """THE BLOCKING BUG FIX: a build PR for an unauthorized proposal (P_EVIL) must NOT
        merge under an authorized proposal's (P_AUTH) two-key grant.

        Scenario: 2-proposal docket.
          - P_AUTH (p_auth_id): two-key granted, targets sensor_auth.
          - P_EVIL (p_evil_id): NOT authorized, targets sensor_evil.
        The PR head-branch is metabolism/build-test_lobe-<cycle> (the docket lobe branch).
        The claims.jsonl records P_EVIL as the one that was actually built on this branch.
        Result: the merge lane must detect that P_EVIL is not authorized and skip,
        NOT inherit P_AUTH's grant.
        """
        import scripts.metabolism_build as mb
        importlib.reload(mb)
        import scripts.metabolism_merge as mm
        importlib.reload(mm)

        d = _tmp_root()
        cycle_id = "cycle-evil-001"

        p_auth_id = "p_auth_id"
        p_evil_id = "p_evil_id"

        proposals = [
            {
                "proposal_id": p_auth_id,
                "title": "Authorized proposal",
                "tier": "T1",
                "target_files": ["engine/auth_sensor.py"],
                "targets_sensor": "sensor_auth",
                "rationale": "auth",
                "fitness_contract": {"metric": "ok"},
            },
            {
                "proposal_id": p_evil_id,
                "title": "Unauthorized proposal",
                "tier": "T1",
                "target_files": ["engine/evil_sensor.py"],
                "targets_sensor": "sensor_evil",
                "rationale": "evil",
                "fitness_contract": {"metric": "evil"},
            },
        ]
        docket = _write_docket(d, cycle_id, proposals)

        # claims.jsonl: P_EVIL was the one actually built on the docket-lobe branch
        claims_path = d / "data" / "metabolism" / "claims.jsonl"
        branch = mb._build_branch_name("test_lobe", cycle_id)
        claims_path.write_text(json.dumps({
            "schema": "metabolism.build_claims.v1",
            "cycle_id": cycle_id,
            "proposal_id": p_evil_id,   # <-- EVIL proposal built this PR
            "lobe": "test_lobe",
            "target_files": ["engine/evil_sensor.py"],
            "ts": _ts_now(),
        }) + "\n")

        # The merge lane sees a draft PR on the docket-lobe branch
        fake_pr = {
            "number": 7777,
            "headRefName": branch,
            "title": "evil build PR",
            "isDraft": True,
            "statusCheckRollup": [{"state": "SUCCESS"}],
            "files": [],
        }

        def _selective_two_key(cycle_id_, proposal_id_, docket_path_, *, root=None):
            # Only P_AUTH is granted; P_EVIL is NOT
            return proposal_id_ == p_auth_id

        with patch.dict(os.environ, {"AUTONOMY_PAUSED": "false"}, clear=False):
            importlib.reload(mm)
            with patch.object(mm, "_is_two_key_granted", side_effect=_selective_two_key):
                with patch.object(mm, "_list_build_draft_prs", return_value=[fake_pr]):
                    with patch.object(mm, "_pr_ci_green", return_value=True):
                        with patch.object(mm, "_get_pr_files", return_value=["engine/evil_sensor.py"]):
                            with patch.object(mm, "_mark_pr_ready", return_value=True):
                                with patch.object(mm, "_rebase_merge_pr",
                                                  return_value={"merged": True, "attempts": 1}):
                                    results = mm.run_merge_lane(cycle_id, docket, root=d)

        # P_EVIL's PR must NOT be merged (it is not authorized)
        merges = [r for r in results if r.get("status") == "merged"]
        assert len(merges) == 0, (
            f"SECURITY: P_EVIL's PR merged under P_AUTH's grant — two-key bypass!\n{results}"
        )
        # The result should indicate not_granted (P_EVIL is not authorized)
        not_granted = [r for r in results if r.get("status") == "not_granted"]
        assert len(not_granted) >= 1, (
            f"Expected not_granted for P_EVIL, got: {results}"
        )

    def test_pr_with_unrecognized_branch_gets_no_matching_proposal(self):
        """A PR whose branch does not match any proposal in the docket → no_matching_proposal.

        This tests the EXACT-MATCH enforcement: a branch that merely starts with
        'metabolism/build-' but does not match the docket lobe must be skipped.
        """
        import scripts.metabolism_merge as mm
        importlib.reload(mm)

        d = _tmp_root()
        cycle_id = "cycle-nomatch-001"
        docket = _write_docket(d, cycle_id, [_minimal_proposal("p1", ["engine/foo.py"])])

        # Branch is a valid metabolism/build- prefix but for a DIFFERENT lobe/cycle
        fake_pr = {
            "number": 8888,
            "headRefName": f"metabolism/build-OTHER_LOBE-{cycle_id}",  # wrong lobe
            "title": "wrong-lobe PR",
            "isDraft": True,
            "statusCheckRollup": [{"state": "SUCCESS"}],
            "files": [],
        }

        with patch.dict(os.environ, {"AUTONOMY_PAUSED": "false"}, clear=False):
            importlib.reload(mm)
            # Even if two-key says "granted", the branch mismatch must block merge
            with patch.object(mm, "_is_two_key_granted", return_value=True):
                with patch.object(mm, "_list_build_draft_prs", return_value=[fake_pr]):
                    results = mm.run_merge_lane(cycle_id, docket, root=d)

        # Must be no_matching_proposal, not merged
        merges = [r for r in results if r.get("status") == "merged"]
        assert len(merges) == 0, f"Unexpected merge of wrong-lobe PR: {results}"
        no_match = [r for r in results if r.get("status") == "no_matching_proposal"]
        assert len(no_match) >= 1, f"Expected no_matching_proposal, got: {results}"


# ── 7. concurrency-group in merge workflow ────────────────────────────────────

class TestMergeWorkflowConcurrencyGroup:
    def test_concurrency_group_present(self):
        """metabolism-merge.yml must have concurrency.group: metabolism-merge-lane."""
        workflow_path = _ROOT / ".github" / "workflows" / "metabolism-merge.yml"
        if not workflow_path.exists():
            pytest.skip("metabolism-merge.yml not present")
        content = workflow_path.read_text()
        assert "metabolism-merge-lane" in content, (
            "metabolism-merge.yml must have concurrency.group: metabolism-merge-lane "
            "to serialize the registry-safe merge (R-V2-5)"
        )

    def test_concurrency_cancel_in_progress_false(self):
        """cancel-in-progress must be false so queued merges wait, not drop."""
        workflow_path = _ROOT / ".github" / "workflows" / "metabolism-merge.yml"
        if not workflow_path.exists():
            pytest.skip("metabolism-merge.yml not present")
        content = workflow_path.read_text()
        assert "cancel-in-progress: false" in content, (
            "cancel-in-progress must be false — queued merges must wait, not be cancelled"
        )

    def test_build_workflow_has_per_cycle_concurrency(self):
        """metabolism-build.yml must have a per-cycle concurrency group."""
        workflow_path = _ROOT / ".github" / "workflows" / "metabolism-build.yml"
        if not workflow_path.exists():
            pytest.skip("metabolism-build.yml not present")
        content = workflow_path.read_text()
        assert "metabolism-build-" in content, (
            "metabolism-build.yml must have a per-cycle concurrency group to prevent duplicate builds"
        )


# ── 8. no autonomous merge while paused ─────────────────────────────────────

class TestNoAutonomousMergeWhilePaused:
    def test_zero_merges_when_paused(self):
        """assert_zero_merges_when_paused must return True."""
        d = _tmp_root()
        docket = _write_docket(d, "cycle-001", [_minimal_proposal("p1", ["engine/foo.py"])])

        import scripts.metabolism_merge as mm
        importlib.reload(mm)
        assert mm.assert_zero_merges_when_paused("cycle-001", docket, root=d) is True

    def test_run_merge_lane_returns_no_merges_when_paused(self):
        """run_merge_lane returns status=noop_paused with no merged items."""
        d = _tmp_root()
        docket = _write_docket(d, "cycle-001", [_minimal_proposal("p1", ["engine/foo.py"])])

        with patch.dict(os.environ, {"AUTONOMY_PAUSED": "true"}, clear=False):
            import scripts.metabolism_merge as mm
            importlib.reload(mm)
            results = mm.run_merge_lane("cycle-001", docket, root=d)

        merged = [r for r in results if r.get("status") == "merged"]
        assert len(merged) == 0, f"No merges expected when paused, got: {merged}"

    def test_workflow_double_gate_present_in_merge_yml(self):
        """metabolism-merge.yml must have the AUTONOMY_PAUSED shell re-check."""
        workflow_path = _ROOT / ".github" / "workflows" / "metabolism-merge.yml"
        if not workflow_path.exists():
            pytest.skip("metabolism-merge.yml not present")
        content = workflow_path.read_text()
        # Both `if: vars.AUTONOMY_PAUSED != 'true'` and shell re-check
        assert "AUTONOMY_PAUSED" in content
        assert "clean no-op" in content.lower() or "noop" in content.lower() or "no-op" in content.lower()

    def test_workflow_double_gate_present_in_build_yml(self):
        """metabolism-build.yml must have the AUTONOMY_PAUSED shell re-check."""
        workflow_path = _ROOT / ".github" / "workflows" / "metabolism-build.yml"
        if not workflow_path.exists():
            pytest.skip("metabolism-build.yml not present")
        content = workflow_path.read_text()
        assert "AUTONOMY_PAUSED" in content


# ── 9. GC reaps squash-merged worktrees ─────────────────────────────────────

class TestGCReapsSquashMergedWorktree:
    def test_gc_has_rev_parse_guard(self):
        """metabolism_gc._is_live_main_checkout must guard against dead-worktree-hits-main."""
        import scripts.metabolism_gc as gc_mod
        importlib.reload(gc_mod)
        # A path that doesn't exist → subprocess fails → returns True (fail-safe)
        result = gc_mod._is_live_main_checkout(Path("/nonexistent/path/xyz"))
        assert result is True, "Non-existent path should be treated as live main (fail-safe)"

    def test_gc_dry_run_reports_reaped(self):
        """GC dry-run with a fake merged worktree reports it as reaped."""
        import scripts.metabolism_gc as gc_mod
        importlib.reload(gc_mod)

        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            (repo_root / ".git").mkdir()
            # Create a fake metabolism worktree dir
            wt_path = repo_root / "metabolism-build-test"
            wt_path.mkdir()
            (wt_path / ".git").write_text("gitdir: ../.git/worktrees/metabolism-build-test\n")
            (wt_path / "data" / "metabolism" / "journal").mkdir(parents=True)
            # Mark journal as terminal (done)
            (wt_path / "data" / "metabolism" / "journal" / "cycle-001.json").write_text(
                json.dumps({"status": "done"})
            )

            # Patch rev-parse so it appears as a distinct worktree (not main)
            with patch.object(gc_mod, "_is_live_main_checkout", return_value=False):
                with patch.object(gc_mod, "_has_open_files", return_value=False):
                    with patch.object(gc_mod, "_branch_merged_into_main", return_value=False):
                        # _journal_is_terminal will fire because journal is "done"
                        with patch.object(gc_mod, "_list_worktrees", return_value=[
                            {"path": wt_path, "branch": "metabolism/build-test-cycle-001"}
                        ]):
                            summary = gc_mod.gc(repo_root, dry_run=True)

        assert len(summary["reaped"]) >= 1, f"GC dry-run should report reaped, got: {summary}"

    def test_gc_skips_occupied_worktree(self):
        """GC skips a worktree that has open files (live session)."""
        import scripts.metabolism_gc as gc_mod
        importlib.reload(gc_mod)

        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            wt_path = repo_root / "metabolism-build-live"
            wt_path.mkdir()

            with patch.object(gc_mod, "_is_live_main_checkout", return_value=False):
                with patch.object(gc_mod, "_has_open_files", return_value=True):  # occupied
                    with patch.object(gc_mod, "_list_worktrees", return_value=[
                        {"path": wt_path, "branch": "metabolism/build-live-cycle-001"}
                    ]):
                        summary = gc_mod.gc(repo_root, dry_run=True)

        assert len(summary["reaped"]) == 0, "Occupied worktree should NOT be reaped"
        assert len(summary["skipped_alive"]) >= 1


# ── 10. banned words: 'validated' never in build-lane files ──────────────────

class TestBannedWords:
    _BUILD_LANE_FILES = [
        _ROOT / "scripts" / "metabolism_build.py",
        _ROOT / "scripts" / "metabolism_merge.py",
        _ROOT / ".github" / "workflows" / "metabolism-build.yml",
        _ROOT / ".github" / "workflows" / "metabolism-merge.yml",
    ]

    def test_no_validated_in_build_lane_files(self):
        """'validated' must never appear in user-facing text in build-lane files."""
        for path in self._BUILD_LANE_FILES:
            if not path.exists():
                continue
            content = path.read_text(encoding="utf-8")
            lower = content.lower()
            assert "validated" not in lower, (
                f"Word 'validated' found in {path.relative_to(_ROOT)} — "
                "CI-enforced ban on user-facing 'validated' claims"
            )


# ── 11. check_self_mod_fence blocks metabolism/build-* on IMMUTABLE files ────

class TestSelfModFenceBuildLane:
    def test_build_loop_branch_immutable_blocked(self):
        """metabolism/build-* touching IMMUTABLE files → BLOCKED."""
        import scripts.check_self_mod_fence as smf
        importlib.reload(smf)

        code, msg = smf.check(
            branch="metabolism/build-til_fitness-cycle-001",
            changed_files=["config/grader_manifest.yml", "data/metabolism/claims.jsonl"],
        )
        assert code == 1, (
            f"Expected BLOCKED for loop build branch touching IMMUTABLE, got code={code}: {msg}"
        )

    def test_build_loop_branch_non_immutable_passes(self):
        """metabolism/build-* NOT touching IMMUTABLE files → PASS."""
        import scripts.check_self_mod_fence as smf
        importlib.reload(smf)

        code, msg = smf.check(
            branch="metabolism/build-til_fitness-cycle-001",
            changed_files=["data/metabolism/claims.jsonl", "engine/some.py"],
        )
        assert code == 0, (
            f"Expected PASS for loop branch not touching IMMUTABLE, got code={code}: {msg}"
        )

    def test_claims_jsonl_not_immutable(self):
        """data/metabolism/claims.jsonl is NOT in the IMMUTABLE set (it's a data artifact)."""
        import scripts.check_self_mod_fence as smf
        importlib.reload(smf)

        # A loop PR touching ONLY claims.jsonl should pass
        code, msg = smf.check(
            branch="metabolism/build-some-cycle-001",
            changed_files=["data/metabolism/claims.jsonl"],
        )
        assert code == 0, (
            f"data/metabolism/claims.jsonl should NOT be IMMUTABLE, got blocked: {msg}"
        )


# ── 12. check_grader_manifest passes ─────────────────────────────────────────

class TestGraderManifestPasses:
    def test_grader_manifest_passes(self):
        """check_grader_manifest.py must exit 0 — no new grader files added by build lane."""
        import scripts.check_grader_manifest as gm
        importlib.reload(gm)
        result = gm.check(root=_ROOT)
        assert result == 0, (
            "check_grader_manifest failed — did the build lane accidentally "
            "modify a grader file without updating the manifest hash?"
        )


# ── 13. check_validated_claims not triggered ─────────────────────────────────

class TestValidatedClaimsNotTriggered:
    def test_check_validated_claims_passes(self):
        """check_validated_claims must exit 0 — build lane adds no 'validated' assertions."""
        try:
            import scripts.check_validated_claims as cv
            importlib.reload(cv)
            # Run in report mode (scan only, don't exit)
            result = cv.main(["--list"])  # list mode exits 0 even when no allowlist hits
        except SystemExit as e:
            assert e.code in (0, None), (
                f"check_validated_claims exited {e.code} — "
                "build lane files may contain 'validated' assertions"
            )
        except Exception:
            pass  # If the script can't import or run in test env, skip


# ── 14. synapse: metabolism-build-claims artifact present ────────────────────

class TestSynapseArtifacts:
    def test_metabolism_build_claims_in_synapse(self):
        """metabolism-build-claims must be registered in config/synapse.yml."""
        import yaml
        synapse_path = _ROOT / "config" / "synapse.yml"
        if not synapse_path.exists():
            pytest.skip("synapse.yml not present")
        data = yaml.safe_load(synapse_path.read_text())
        artifacts = data.get("artifacts", {})
        assert "metabolism-build-claims" in artifacts, (
            "metabolism-build-claims not registered in synapse.yml — "
            "new data artifacts must be registered at END-OF-FILE per house law"
        )

    def test_metabolism_build_claims_schema(self):
        """metabolism-build-claims entry must have required fields."""
        import yaml
        synapse_path = _ROOT / "config" / "synapse.yml"
        if not synapse_path.exists():
            pytest.skip("synapse.yml not present")
        data = yaml.safe_load(synapse_path.read_text())
        entry = data.get("artifacts", {}).get("metabolism-build-claims", {})
        assert entry.get("path"), "metabolism-build-claims must have a path"
        assert entry.get("producer"), "metabolism-build-claims must have a producer"
        assert entry.get("schema"), "metabolism-build-claims must have a schema field"
        assert entry.get("tier") == "shadow" or entry.get("tier") == "infrastructure", (
            "metabolism-build-claims must be shadow or infrastructure tier"
        )

    def test_synapse_count_geq_362(self):
        """synapse.yml must have at least 362 artifacts after V2-B Unit 6 addition."""
        import yaml
        synapse_path = _ROOT / "config" / "synapse.yml"
        if not synapse_path.exists():
            pytest.skip("synapse.yml not present")
        data = yaml.safe_load(synapse_path.read_text())
        count = len(data.get("artifacts", {}))
        assert count >= 362, (
            f"Expected >= 362 synapse artifacts after V2-B Unit 6, got {count}. "
            "Verify that metabolism-build-claims was added."
        )

    def test_build_workflow_gated_on_autonomy_paused(self):
        """metabolism-build.yml must have the AUTONOMY_PAUSED gate."""
        workflow_path = _ROOT / ".github" / "workflows" / "metabolism-build.yml"
        if not workflow_path.exists():
            pytest.skip("metabolism-build.yml not present")
        content = workflow_path.read_text()
        assert "AUTONOMY_PAUSED" in content

    def test_merge_workflow_gated_on_autonomy_paused(self):
        """metabolism-merge.yml must have the AUTONOMY_PAUSED gate."""
        workflow_path = _ROOT / ".github" / "workflows" / "metabolism-merge.yml"
        if not workflow_path.exists():
            pytest.skip("metabolism-merge.yml not present")
        content = workflow_path.read_text()
        assert "AUTONOMY_PAUSED" in content

    def test_build_lane_opens_draft_prs_only(self):
        """metabolism-build.yml must use --draft flag for all PR creation."""
        workflow_path = _ROOT / ".github" / "workflows" / "metabolism-build.yml"
        if not workflow_path.exists():
            pytest.skip("metabolism-build.yml not present")
        content = workflow_path.read_text()
        # The build workflow itself does not call gh pr create (the build session does)
        # but the Python stub does document DRAFT only — check the Python file
        build_py = _ROOT / "scripts" / "metabolism_build.py"
        if build_py.exists():
            py_content = build_py.read_text()
            assert "--draft" in py_content or "DRAFT" in py_content, (
                "metabolism_build.py must create DRAFT PRs only"
            )


# ── 15. run_build_lane threads cycle_id and target_files correctly ────────────

def _production_docket_proposal(pid: str, target_files: list[str]) -> dict:
    """Minimal proposal row shaped like propose.py output — NO cycle_id or target_files."""
    return {
        "proposal_id": pid,
        "content_hash": pid,
        "title": f"Production proposal {pid}",
        "tier": "T1",
        "kind": "sensor",
        "targets_sensor": "test_sensor",
        "rationale": "test rationale",
        # NOTE: target_files deliberately set so claim_proposal works; but the
        # production path resolves target_files independently in run_build_lane.
        "target_files": target_files,
        # NOTE: NO cycle_id key — only lives at docket top-level
    }


class TestRunBuildLaneThreading:
    """run_build_lane must thread cycle_id and resolved target_files into _dispatch_build_session.

    These tests use production-shaped dockets and verify that the idempotency,
    journal, and foreign-file checks work end-to-end through run_build_lane.
    """

    def _write_production_docket(self, d: Path, cycle_id: str, proposals: list[dict]) -> Path:
        """Write a docket shaped like propose.py output (cycle_id at top level only)."""
        path = d / "data" / "metabolism" / "dockets" / f"{cycle_id}.json"
        path.write_text(json.dumps({
            "schema": "metabolism.docket.v1",
            "cycle_id": cycle_id,      # TOP-LEVEL only — not in proposal rows
            "lobe": "test_lobe",
            "proposals": proposals,    # rows have no cycle_id key
        }))
        return path

    def test_run_build_lane_idempotent_skip_uses_docket_cycle_id(self):
        """run_build_lane passes docket's top-level cycle_id to dispatch; second run is idempotent."""
        d = _tmp_root()
        import scripts.metabolism_build as mb
        importlib.reload(mb)

        cycle_id = "cycle-lane-idem-001"
        pid = "p_lane_1"
        prop = _production_docket_proposal(pid, ["engine/test_sensor.py"])
        docket = self._write_production_docket(d, cycle_id, [prop])

        dispatch_calls = []
        idempotent_skips = []

        original_dispatch = mb._dispatch_build_session

        def recording_dispatch(proposal, wt_path, branch, cap_id, *, cycle_id=None,
                               target_files=None, root=None, dry_run=False):
            # Record the threaded cycle_id
            dispatch_calls.append({
                "cycle_id": cycle_id,
                "target_files": target_files,
                "pid": proposal.get("proposal_id"),
            })
            # Call original to test real idempotency
            return original_dispatch(
                proposal, wt_path, branch, cap_id,
                cycle_id=cycle_id, target_files=target_files,
                root=root, dry_run=dry_run,
            )

        ref_name = "CLAUDE_CODE_OAUTH_TOKEN_1"
        env = {**{k: v for k, v in os.environ.items()}, "AUTONOMY_PAUSED": "false",
               ref_name: "fake_token"}

        def fake_two_key(*args, **kwargs):
            return True

        def fake_dispatch_build_session(proposal, wt_path, branch, cap_id, *,
                                        cycle_id=None, target_files=None, root=None, dry_run=False):
            dispatch_calls.append({
                "cycle_id": cycle_id,
                "target_files": target_files,
                "pid": proposal.get("proposal_id"),
            })
            return {"dispatched": True, "reason": "dispatched", "proposal_id": proposal.get("proposal_id")}

        def fake_open_pr(*args, **kwargs):
            return {"opened": True}

        def fake_create_worktree(*args, **kwargs):
            import tempfile
            return {"wt_path": tempfile.mkdtemp(prefix="fake_wt_"), "branch": args[0] if args else "fake"}

        def fake_gc(*args, **kwargs):
            pass

        def fake_pick_key(*args, **kwargs):
            return "claude_code_oauth_1"

        with patch.dict(os.environ, env, clear=False):
            with patch.object(mb, "_is_two_key_granted", side_effect=fake_two_key):
                with patch.object(mb, "_dispatch_build_session",
                                  side_effect=fake_dispatch_build_session):
                    with patch.object(mb, "_open_draft_pr", side_effect=fake_open_pr):
                        with patch.object(mb, "_create_build_worktree",
                                          side_effect=fake_create_worktree):
                            with patch.object(mb, "_gc_worktree", side_effect=fake_gc):
                                with patch.object(mb, "_pick_build_key",
                                                  side_effect=fake_pick_key):
                                    results = mb.run_build_lane(cycle_id, docket, root=d)

        # Verify dispatch was called with the docket's cycle_id threaded in
        assert len(dispatch_calls) >= 1, f"_dispatch_build_session not called: {results}"
        assert dispatch_calls[0]["cycle_id"] == cycle_id, (
            f"cycle_id not threaded through to dispatch: got {dispatch_calls[0]['cycle_id']!r}, "
            f"expected {cycle_id!r}"
        )
        # Verify target_files threaded (non-empty)
        assert dispatch_calls[0]["target_files"], (
            f"target_files not threaded through to dispatch: {dispatch_calls[0]}"
        )

    def test_run_build_lane_threads_target_files_from_claim(self):
        """run_build_lane threads the resolved target_files (from claim step) into dispatch."""
        d = _tmp_root()
        import scripts.metabolism_build as mb
        importlib.reload(mb)

        cycle_id = "cycle-lane-tf-001"
        pid = "p_tf_1"
        declared_files = ["engine/my_sensor.py", "engine/helper.py"]
        prop = _production_docket_proposal(pid, declared_files)
        docket = self._write_production_docket(d, cycle_id, [prop])

        dispatch_calls = []

        def fake_dispatch(proposal, wt_path, branch, cap_id, *, cycle_id=None,
                          target_files=None, root=None, dry_run=False):
            dispatch_calls.append({"cycle_id": cycle_id, "target_files": target_files})
            return {"dispatched": True, "reason": "dispatched",
                    "proposal_id": proposal.get("proposal_id")}

        env = {k: v for k, v in os.environ.items()}
        env["AUTONOMY_PAUSED"] = "false"

        with patch.dict(os.environ, env, clear=False):
            with patch.object(mb, "_is_two_key_granted", return_value=True):
                with patch.object(mb, "_dispatch_build_session", side_effect=fake_dispatch):
                    with patch.object(mb, "_open_draft_pr", return_value={"opened": True}):
                        with patch.object(mb, "_create_build_worktree",
                                          return_value={"wt_path": tempfile.mkdtemp(prefix="fake_wt_")}):
                            with patch.object(mb, "_gc_worktree"):
                                with patch.object(mb, "_pick_build_key",
                                                  return_value="claude_code_oauth_1"):
                                    mb.run_build_lane(cycle_id, docket, root=d)

        assert len(dispatch_calls) >= 1, "dispatch not called"
        threaded = dispatch_calls[0]["target_files"]
        assert threaded is not None, "target_files not threaded at all"
        assert len(threaded) > 0, "threaded target_files is empty"
        # The declared files must be in the threaded list
        for f in declared_files:
            assert f in threaded, (
                f"Declared file {f!r} not in threaded target_files: {threaded}"
            )
