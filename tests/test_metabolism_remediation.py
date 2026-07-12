"""tests/test_metabolism_remediation.py — Hermetic tests for R-V7-7 audit-reject remediation.

COVERAGE:
  1. reject_record_triggers_remediation — reject record present + attempts remaining
     → remediation build dispatched with findings injected into task prompt; SAME branch.
  2. attempts_exhausted_parks_proposal — attempts >= max → NO rebuild; audit_rebuild_exhausted
     insight emitted; proposal status = audit_rebuild_exhausted.
  3. already_remediated_no_rebuild — reject record SHA matches last-remediated SHA
     → no remediation (normal build path taken).
  4. approve_record_no_remediation — approve record only → no remediation (normal path).
  5. no_audit_record_no_remediation — no audit record at all → normal build path.
  6. remediation_attempts_durable — _remediation_attempts survives journal read-back.
  7. audit_proposal_id_stamped — audit.py stamps proposal_id into record + governance evidence.
  8. remediation_prompt_contains_findings — task prompt contains rationale + findings text.
  9. remediation_uses_same_branch — remediation rebuild dispatches onto the SAME branch.
  10. find_reject_for_proposal_returns_most_recent — two reject records → most-recent returned.
  11. find_reject_for_proposal_ignores_approve — approve record ignored; only reject returned.

All tests HERMETIC (tmp dirs, monkeypatch, no real subprocess, no real network).
"""
from __future__ import annotations

import importlib
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _tmp_root(extra_subdirs: list[str] | None = None) -> Path:
    d = Path(tempfile.mkdtemp(prefix="metab_remediation_test_"))
    for sub in [
        "data/metabolism/journal",
        "data/metabolism/dockets",
        "data/metabolism/audit",
        "data/metabolism/claims",
        "data/neuralweb",
        "config",
        "docs",
        "research",
    ]:
        (d / sub).mkdir(parents=True, exist_ok=True)
    (d / "research" / "DO_NOT_REBUILD.md").write_text("# empty\n")
    (d / "docs" / "ACTIVE_BUILD_MAP.md").write_text("# empty\n")
    # Budget with max_audit_rebuild_attempts = 2
    (d / "config" / "metabolism_budget.yml").write_text(
        "schema: metabolism_budget.v1\n"
        "max_build_attempts: 2\n"
        "stale_running_ttl_hours: 3\n"
        "max_audit_rebuild_attempts: 2\n"
        "audit_max_diff_lines: 2000\n"
    )
    for sub in (extra_subdirs or []):
        (d / sub).mkdir(parents=True, exist_ok=True)
    return d


def _tmp_wt() -> str:
    return tempfile.mkdtemp(prefix="metab_rem_wt_test_")


def _minimal_proposal(
    pid: str = "p_rem1",
    target_files: list[str] | None = None,
    cycle_id: str = "cycle-rem-001",
    lobe: str = "test_lobe",
) -> dict:
    return {
        "proposal_id": pid,
        "cycle_id": cycle_id,
        "title": f"Test remediation proposal {pid}",
        "tier": "T1",
        "lobe": lobe,
        "target_files": target_files or ["engine/test_sensor.py"],
        "targets_sensor": "test_sensor",
        "rationale": "test rationale for remediation",
        "fitness_contract": {"metric": "liveness", "threshold": 0.5},
    }


def _minimal_docket(
    cycle_id: str,
    lobe: str,
    proposals: list[dict],
    root: Path,
) -> Path:
    docket = {
        "schema": "metabolism.docket.v1",
        "cycle_id": cycle_id,
        "lobe": lobe,
        "proposals": proposals,
    }
    p = root / "data" / "metabolism" / "dockets" / f"{cycle_id}.json"
    p.write_text(json.dumps(docket, indent=2))
    return p


def _write_audit_record(
    root: Path,
    pr_number: int,
    proposal_id: str,
    verdict: str,
    head_sha: str = "sha_abc123",
    findings: list[str] | None = None,
    rationale: str = "test rationale",
    ts: str = "2026-07-12T10:00:00+00:00",
) -> dict:
    rec = {
        "schema": "metabolism.audit.v1",
        "pr_number": pr_number,
        "proposal_id": proposal_id,
        "head_sha": head_sha,
        "verdict": verdict,
        "deterministic_ok": verdict == "approve",
        "llm_verdict": verdict,
        "confidence": 0.9 if verdict == "approve" else 0.1,
        "findings": findings or (["scope creep detected"] if verdict == "reject" else []),
        "rationale": rationale,
        "ts": ts,
    }
    p = root / "data" / "metabolism" / "audit" / f"{pr_number}.json"
    p.write_text(json.dumps(rec, indent=2))
    return rec


def _armed_env():
    return {**os.environ, "AUTONOMY_PAUSED": "false"}


def _import_mb():
    import scripts.metabolism_build as mb
    importlib.reload(mb)
    return mb


def _import_audit():
    import engine.metabolism.audit as a
    importlib.reload(a)
    return a


# ── 1. reject record present + attempts remaining → remediation rebuild ───────

class TestRejectTriggerRemediation:
    """With a reject record and attempts remaining, run_build_lane dispatches remediation."""

    def test_remediation_dispatched_with_findings_in_prompt(self):
        mb = _import_mb()
        d = _tmp_root()
        cycle_id = "cycle-rem-001"
        pid = "p_rem1"
        lobe = "test_lobe"

        prop = _minimal_proposal(pid=pid, cycle_id=cycle_id, lobe=lobe)
        dp = _minimal_docket(cycle_id, lobe, [prop], d)

        # Write an audit reject record
        _write_audit_record(
            d, pr_number=42, proposal_id=pid, verdict="reject",
            head_sha="sha_abc123",
            findings=["scope creep: engine/extra.py added", "missing fitness contract step"],
            rationale="The diff added an undeclared file and skipped a required step.",
        )

        dispatched_prompts: list[str] = []
        dispatched_branches: list[str] = []

        def fake_dispatch(prop_arg, wt, branch, cap, *, cycle_id=None,
                          target_files=None, root=None, dry_run=False,
                          remediation=None):
            dispatched_branches.append(branch)
            if remediation:
                prompt = mb._build_session_task_prompt(
                    prop_arg, wt, branch, cycle_id or "",
                    target_files=target_files,
                    remediation=remediation,
                )
                dispatched_prompts.append(prompt)
            return {"dispatched": True, "proposal_id": prop_arg.get("proposal_id")}

        def fake_two_key(cycle, pid_arg, docket_path, *, root=None):
            return True

        def fake_worktree(branch, *, root=None, dry_run=False):
            wt = _tmp_wt()
            return {"wt_path": wt, "error": None}

        def fake_claim(cid, pid_arg, lobe_arg, tfiles, *, root=None, dry_run=False):
            return {"claimed": True, "collision_files": [], "ts": "2026-07-12T10:00:00"}

        def fake_open_pr(branch, cid, prop_arg, dry_run=False):
            return {"opened": False, "stub": True}

        def fake_pick_key(root=None, exclude=None):
            return "claude_code_oauth_1"

        def fake_journal_dispatch(cid, pid_arg, record, *, root=None):
            pass  # swallow

        env = _armed_env()
        with patch.dict(os.environ, env, clear=False):
            with patch.object(mb, "_is_two_key_granted", side_effect=fake_two_key):
                with patch.object(mb, "_create_build_worktree", side_effect=fake_worktree):
                    with patch.object(mb, "claim_proposal", side_effect=fake_claim):
                        with patch.object(mb, "_dispatch_build_session", side_effect=fake_dispatch):
                            with patch.object(mb, "_open_draft_pr", side_effect=fake_open_pr):
                                with patch.object(mb, "_pick_build_key", side_effect=fake_pick_key):
                                    with patch.object(mb, "_journal_dispatch", side_effect=fake_journal_dispatch):
                                        with patch.object(mb, "_gc_worktree"):
                                            results = mb.run_build_lane(
                                                cycle_id, str(dp), root=d, dry_run=False,
                                            )

        assert len(results) == 1
        r = results[0]
        assert r.get("status") == "audit_remediation_dispatched", (
            f"Expected audit_remediation_dispatched, got: {r.get('status')}"
        )
        assert len(dispatched_prompts) == 1, "Expected exactly one remediation prompt"
        prompt = dispatched_prompts[0]
        assert "PRIOR AUDIT REJECTION" in prompt, "Remediation block missing from prompt"
        assert "scope creep" in prompt, "Findings not injected into prompt"
        assert "missing fitness contract step" in prompt, "Second finding missing"
        assert "The diff added an undeclared file" in prompt, "Rationale not injected"

    def test_remediation_uses_same_branch(self):
        """Remediation dispatch uses the SAME branch as a normal build would."""
        mb = _import_mb()
        d = _tmp_root()
        cycle_id = "cycle-rem-002"
        pid = "p_rem2"
        lobe = "test_lobe"

        prop = _minimal_proposal(pid=pid, cycle_id=cycle_id, lobe=lobe)
        dp = _minimal_docket(cycle_id, lobe, [prop], d)
        _write_audit_record(d, pr_number=43, proposal_id=pid, verdict="reject", head_sha="sha_xyz")

        expected_branch = mb._build_branch_name(lobe, cycle_id, proposal_id=pid)
        dispatched_branches: list[str] = []

        def fake_dispatch(prop_arg, wt, branch, cap, *, cycle_id=None,
                          target_files=None, root=None, dry_run=False,
                          remediation=None):
            dispatched_branches.append(branch)
            return {"dispatched": True, "proposal_id": pid}

        env = _armed_env()
        with patch.dict(os.environ, env, clear=False):
            with patch.object(mb, "_is_two_key_granted", return_value=True):
                with patch.object(mb, "_create_build_worktree",
                                  return_value={"wt_path": _tmp_wt(), "error": None}):
                    with patch.object(mb, "claim_proposal",
                                      return_value={"claimed": True, "collision_files": [], "ts": "t"}):
                        with patch.object(mb, "_dispatch_build_session", side_effect=fake_dispatch):
                            with patch.object(mb, "_open_draft_pr",
                                              return_value={"opened": False, "stub": True}):
                                with patch.object(mb, "_pick_build_key", return_value="key1"):
                                    with patch.object(mb, "_journal_dispatch"):
                                        with patch.object(mb, "_gc_worktree"):
                                            mb.run_build_lane(cycle_id, str(dp), root=d)

        assert len(dispatched_branches) == 1
        assert dispatched_branches[0] == expected_branch, (
            f"Branch mismatch: expected {expected_branch!r}, got {dispatched_branches[0]!r}"
        )


# ── 2. attempts exhausted → park, no rebuild ─────────────────────────────────

class TestAttemptsExhausted:
    """When remediation_attempts >= max_audit_rebuild_attempts, proposal is parked."""

    def test_exhausted_parks_no_dispatch(self):
        mb = _import_mb()
        d = _tmp_root()
        cycle_id = "cycle-rem-003"
        pid = "p_rem3"
        lobe = "test_lobe"

        prop = _minimal_proposal(pid=pid, cycle_id=cycle_id, lobe=lobe)
        dp = _minimal_docket(cycle_id, lobe, [prop], d)
        _write_audit_record(d, pr_number=44, proposal_id=pid, verdict="reject",
                            head_sha="sha_zzz",
                            findings=["foreign_file:engine/bad.py"])

        # Simulate 2 prior remediation attempts (= max)
        # We do this by pre-writing a journal note with _remediation_attempts=2.
        # Directly write the journal so _read_remediation_attempts returns 2.
        journal_dir = d / "data" / "metabolism" / "journal"
        journal_path = journal_dir / f"{cycle_id}.json"
        stage = f"build_dispatch_{pid}"
        journal_data = {
            "cycle_id": cycle_id,
            "stages": {
                stage: {
                    "status": "audit_remediation",
                    "note": json.dumps({"_remediation_attempts": 2, "status": "audit_remediation"}),
                }
            }
        }
        journal_path.write_text(json.dumps(journal_data))

        dispatched: list[dict] = []
        exhausted_insights: list[dict] = []

        def fake_dispatch(*a, **kw):
            dispatched.append(kw)
            return {"dispatched": True}

        def fake_emit_exhausted(cid, pid_arg, pr_number, findings, remediation_attempts, *, root=None):
            exhausted_insights.append({
                "cycle_id": cid, "proposal_id": pid_arg,
                "remediation_attempts": remediation_attempts,
            })

        env = _armed_env()
        with patch.dict(os.environ, env, clear=False):
            with patch.object(mb, "_is_two_key_granted", return_value=True):
                with patch.object(mb, "_dispatch_build_session", side_effect=fake_dispatch):
                    with patch.object(mb, "_emit_audit_rebuild_exhausted_insight",
                                      side_effect=fake_emit_exhausted):
                        with patch.object(mb, "_journal_dispatch"):
                            with patch.object(mb, "_gc_worktree"):
                                results = mb.run_build_lane(cycle_id, str(dp), root=d)

        assert len(results) == 1
        r = results[0]
        assert r.get("status") == "audit_rebuild_exhausted", (
            f"Expected audit_rebuild_exhausted, got {r.get('status')!r}"
        )
        assert len(dispatched) == 0, "No new build session should be dispatched when exhausted"

    def test_exhausted_emits_insight_at_threshold(self):
        """_journal_dispatch emits audit_rebuild_exhausted insight at the threshold crossing."""
        mb = _import_mb()
        d = _tmp_root()
        cycle_id = "cycle-rem-insight"
        pid = "p_insight"

        # Pre-populate journal with 1 prior attempt (so new count=2 crosses threshold=2).
        journal_dir = d / "data" / "metabolism" / "journal"
        stage = f"build_dispatch_{pid}"
        journal_path = journal_dir / f"{cycle_id}.json"
        journal_data = {
            "cycle_id": cycle_id,
            "stages": {
                stage: {
                    "status": "audit_remediation",
                    "note": json.dumps({"_remediation_attempts": 1}),
                }
            }
        }
        journal_path.write_text(json.dumps(journal_data))

        emitted_insights: list[dict] = []

        def fake_emit_exhausted(cid, pid_arg, pr_number, findings, remediation_attempts, *, root=None):
            emitted_insights.append({
                "cycle_id": cid, "proposal_id": pid_arg,
                "remediation_attempts": remediation_attempts,
            })

        def fake_finish_stage(cid, stage_name, status, *, note=None, root=None):
            pass

        with patch.object(mb, "_emit_audit_rebuild_exhausted_insight",
                          side_effect=fake_emit_exhausted):
            with patch("scripts.metabolism_journal.finish_stage", side_effect=fake_finish_stage):
                mb._journal_dispatch(
                    cycle_id, pid,
                    {
                        "status": "audit_remediation",
                        "action": "dispatched",
                        "remediation_attempts": 2,
                        "pr_number": 99,
                        "findings": ["bad finding"],
                    },
                    root=d,
                )

        # Should have fired the exhausted insight exactly once at threshold crossing
        assert len(emitted_insights) == 1
        assert emitted_insights[0]["remediation_attempts"] == 2
        assert emitted_insights[0]["proposal_id"] == pid


# ── 3. already-remediated SHA → no double-fire ────────────────────────────────

class TestAlreadyRemediated:
    """If the reject record's head SHA was already remediated, normal build path taken."""

    def test_already_remediated_sha_no_remediation(self):
        mb = _import_mb()
        d = _tmp_root()
        cycle_id = "cycle-rem-004"
        pid = "p_rem4"
        lobe = "test_lobe"

        prop = _minimal_proposal(pid=pid, cycle_id=cycle_id, lobe=lobe)
        dp = _minimal_docket(cycle_id, lobe, [prop], d)

        # Write a reject record with sha_already_done
        _write_audit_record(d, pr_number=45, proposal_id=pid, verdict="reject",
                            head_sha="sha_already_done")

        # Pre-populate journal so _read_last_remediated_sha returns "sha_already_done"
        stage = f"build_dispatch_{pid}"
        journal_data = {
            "cycle_id": cycle_id,
            "stages": {
                stage: {
                    "status": "audit_remediation",
                    "note": json.dumps({
                        "_remediation_attempts": 1,
                        "_last_remediated_sha": "sha_already_done",
                    }),
                }
            }
        }
        (d / "data" / "metabolism" / "journal" / f"{cycle_id}.json").write_text(
            json.dumps(journal_data)
        )

        # The normal build path should run (not remediation).
        # We detect it by watching whether _dispatch_build_session is called
        # with remediation=None (normal) vs remediation=dict (remediation).
        dispatched_remediations: list[dict] = []
        dispatched_normals: list[dict] = []

        def fake_dispatch(prop_arg, wt, branch, cap, *, cycle_id=None,
                          target_files=None, root=None, dry_run=False,
                          remediation=None):
            if remediation:
                dispatched_remediations.append({"remediation": remediation})
            else:
                dispatched_normals.append({"proposal_id": prop_arg.get("proposal_id")})
            return {"dispatched": True, "proposal_id": prop_arg.get("proposal_id")}

        env = _armed_env()
        with patch.dict(os.environ, env, clear=False):
            with patch.object(mb, "_is_two_key_granted", return_value=True):
                with patch.object(mb, "_create_build_worktree",
                                  return_value={"wt_path": _tmp_wt(), "error": None}):
                    with patch.object(mb, "claim_proposal",
                                      return_value={"claimed": True, "collision_files": [], "ts": "t"}):
                        with patch.object(mb, "_dispatch_build_session", side_effect=fake_dispatch):
                            with patch.object(mb, "_open_draft_pr",
                                              return_value={"opened": False, "stub": True}):
                                with patch.object(mb, "_pick_build_key", return_value="key1"):
                                    with patch.object(mb, "_journal_dispatch"):
                                        with patch.object(mb, "_gc_worktree"):
                                            mb.run_build_lane(cycle_id, str(dp), root=d)

        assert len(dispatched_remediations) == 0, "Should NOT dispatch remediation when SHA already done"
        assert len(dispatched_normals) == 1, "Should dispatch normal build"


# ── 4. approve record → no remediation ───────────────────────────────────────

class TestApproveNoRemediation:
    """An approve audit record does not trigger remediation."""

    def test_approve_record_normal_path(self):
        mb = _import_mb()
        d = _tmp_root()
        cycle_id = "cycle-rem-005"
        pid = "p_rem5"
        lobe = "test_lobe"

        prop = _minimal_proposal(pid=pid, cycle_id=cycle_id, lobe=lobe)
        dp = _minimal_docket(cycle_id, lobe, [prop], d)

        # Write an APPROVE audit record
        _write_audit_record(d, pr_number=46, proposal_id=pid, verdict="approve")

        dispatched_remediations: list[dict] = []

        def fake_dispatch(prop_arg, wt, branch, cap, *, cycle_id=None,
                          target_files=None, root=None, dry_run=False,
                          remediation=None):
            if remediation:
                dispatched_remediations.append({"remediation": remediation})
            return {"dispatched": True, "proposal_id": prop_arg.get("proposal_id")}

        env = _armed_env()
        with patch.dict(os.environ, env, clear=False):
            with patch.object(mb, "_is_two_key_granted", return_value=True):
                with patch.object(mb, "_create_build_worktree",
                                  return_value={"wt_path": _tmp_wt(), "error": None}):
                    with patch.object(mb, "claim_proposal",
                                      return_value={"claimed": True, "collision_files": [], "ts": "t"}):
                        with patch.object(mb, "_dispatch_build_session", side_effect=fake_dispatch):
                            with patch.object(mb, "_open_draft_pr",
                                              return_value={"opened": False, "stub": True}):
                                with patch.object(mb, "_pick_build_key", return_value="key1"):
                                    with patch.object(mb, "_journal_dispatch"):
                                        with patch.object(mb, "_gc_worktree"):
                                            mb.run_build_lane(cycle_id, str(dp), root=d)

        assert len(dispatched_remediations) == 0, "Approve record must not trigger remediation"


# ── 5. no audit record → normal build path ───────────────────────────────────

class TestNoAuditRecord:
    """No audit record → normal build path (no remediation)."""

    def test_no_audit_record_normal_path(self):
        mb = _import_mb()
        d = _tmp_root()
        cycle_id = "cycle-rem-006"
        pid = "p_rem6"
        lobe = "test_lobe"

        prop = _minimal_proposal(pid=pid, cycle_id=cycle_id, lobe=lobe)
        dp = _minimal_docket(cycle_id, lobe, [prop], d)
        # No audit records written for this proposal.

        dispatched_remediations: list[dict] = []

        def fake_dispatch(prop_arg, wt, branch, cap, *, cycle_id=None,
                          target_files=None, root=None, dry_run=False,
                          remediation=None):
            if remediation:
                dispatched_remediations.append({"remediation": remediation})
            return {"dispatched": True, "proposal_id": prop_arg.get("proposal_id")}

        env = _armed_env()
        with patch.dict(os.environ, env, clear=False):
            with patch.object(mb, "_is_two_key_granted", return_value=True):
                with patch.object(mb, "_create_build_worktree",
                                  return_value={"wt_path": _tmp_wt(), "error": None}):
                    with patch.object(mb, "claim_proposal",
                                      return_value={"claimed": True, "collision_files": [], "ts": "t"}):
                        with patch.object(mb, "_dispatch_build_session", side_effect=fake_dispatch):
                            with patch.object(mb, "_open_draft_pr",
                                              return_value={"opened": False, "stub": True}):
                                with patch.object(mb, "_pick_build_key", return_value="key1"):
                                    with patch.object(mb, "_journal_dispatch"):
                                        with patch.object(mb, "_gc_worktree"):
                                            mb.run_build_lane(cycle_id, str(dp), root=d)

        assert len(dispatched_remediations) == 0


# ── 6. remediation_attempts durable via journal ───────────────────────────────

class TestRemediationAttemptsDurable:
    """_remediation_attempts survives journal write → read round-trip."""

    def test_counter_survives_round_trip(self):
        mb = _import_mb()
        d = _tmp_root()
        cycle_id = "cycle-rem-durable"
        pid = "p_durable"

        # Write a journal entry via _journal_dispatch with audit_remediation status.
        def fake_finish_stage(cid, stage_name, status, *, note=None, root=None):
            # Actually write the journal file to disk so the reader can find it.
            journal_dir = (root or d) / "data" / "metabolism" / "journal"
            journal_dir.mkdir(parents=True, exist_ok=True)
            jpath = journal_dir / f"{cid}.json"
            existing = {}
            if jpath.exists():
                try:
                    existing = json.loads(jpath.read_text())
                except Exception:
                    pass
            existing.setdefault("cycle_id", cid)
            existing.setdefault("stages", {})[stage_name] = {
                "status": status, "note": note or ""
            }
            jpath.write_text(json.dumps(existing))

        with patch("scripts.metabolism_journal.finish_stage", side_effect=fake_finish_stage):
            with patch("scripts.metabolism_journal._read_journal") as mock_read:
                # Make _read_journal return what's on disk.
                def _real_read(cid, root=None):
                    jpath = (root or d) / "data" / "metabolism" / "journal" / f"{cid}.json"
                    if jpath.exists():
                        try:
                            return json.loads(jpath.read_text())
                        except Exception:
                            pass
                    return {}
                mock_read.side_effect = _real_read

                # Dispatch first attempt
                mb._journal_dispatch(
                    cycle_id, pid,
                    {
                        "status": "audit_remediation",
                        "action": "dispatched",
                        "remediation_attempts": 1,
                        "pr_number": 77,
                        "findings": ["finding A"],
                    },
                    root=d,
                )
                count_after_1 = mb._read_remediation_attempts(cycle_id, pid, root=d)
                assert count_after_1 == 1, f"Expected 1, got {count_after_1}"

                # Dispatch second attempt (simulates the next cycle run)
                mb._journal_dispatch(
                    cycle_id, pid,
                    {
                        "status": "audit_remediation",
                        "action": "dispatched",
                        "remediation_attempts": 2,
                        "pr_number": 77,
                        "findings": ["finding A"],
                    },
                    root=d,
                )
                count_after_2 = mb._read_remediation_attempts(cycle_id, pid, root=d)
                assert count_after_2 == 2, f"Expected 2, got {count_after_2}"


# ── 7. audit.py stamps proposal_id ────────────────────────────────────────────

class TestAuditProposalIdStamped:
    """audit_pr stamps proposal_id into the record and governance evidence."""

    def test_proposal_id_in_record(self):
        from engine.metabolism import audit as a
        importlib.reload(a)

        d = _tmp_root()
        pid = "p_audit_stamp"
        proposal = {
            "proposal_id": pid,
            "title": "Test",
            "target_files": ["engine/foo.py"],
            "rationale": "test",
            "fitness_contract": {},
        }
        # Minimal diff that passes deterministic checks
        diff = (
            "diff --git a/engine/foo.py b/engine/foo.py\n"
            "+++ b/engine/foo.py\n"
            "@@ -1 +1 @@\n"
            "+added line 1\n"
        )

        # Patch out LLM and governance so test is hermetic
        def fake_call_llm(*args, **kwargs):
            return "approve", 0.95, [], "looks good", None

        def fake_append_governance(*args, **kwargs):
            pass

        with patch.object(a, "_call_llm_auditor", side_effect=fake_call_llm):
            with patch.object(a, "_append_governance_event", side_effect=fake_append_governance):
                rec = a.audit_pr(
                    pr_number=55,
                    proposal=proposal,
                    diff_text=diff,
                    head_sha="sha_stamp_test",
                    root=d,
                )

        assert rec.get("proposal_id") == pid, (
            f"proposal_id not stamped; got: {rec.get('proposal_id')!r}"
        )
        assert rec.get("verdict") == "approve"

    def test_proposal_id_explicit_param_overrides_proposal_dict(self):
        """When proposal_id kwarg is given explicitly, it takes priority."""
        from engine.metabolism import audit as a
        importlib.reload(a)

        d = _tmp_root()
        proposal = {
            "proposal_id": "from_dict",
            "title": "Test",
            "target_files": ["engine/bar.py"],
            "rationale": "test",
            "fitness_contract": {},
        }
        diff = "+++ b/engine/bar.py\n+added\n"

        with patch.object(a, "_call_llm_auditor", return_value=("approve", 0.9, [], "ok", None)):
            with patch.object(a, "_append_governance_event"):
                rec = a.audit_pr(
                    pr_number=56,
                    proposal=proposal,
                    diff_text=diff,
                    head_sha="sha_explicit",
                    root=d,
                    proposal_id="explicit_override",
                )

        assert rec.get("proposal_id") == "explicit_override"

    def test_proposal_id_in_governance_evidence(self):
        """audit.py's governance evidence carries proposal_id."""
        from engine.metabolism import audit as a
        importlib.reload(a)

        d = _tmp_root()
        pid = "p_gov_evidence"
        proposal = {
            "proposal_id": pid,
            "title": "Gov test",
            "target_files": ["engine/baz.py"],
            "rationale": "test",
            "fitness_contract": {},
        }
        diff = "+++ b/engine/baz.py\n+line\n"

        captured_evidence: list[dict] = []

        def capture_governance_event(record, root=None):
            # Replicate the evidence dict that _append_governance_event builds.
            captured_evidence.append({
                "head_sha": record.get("head_sha"),
                "proposal_id": record.get("proposal_id"),
                "verdict": record.get("verdict"),
            })

        with patch.object(a, "_call_llm_auditor", return_value=("approve", 0.9, [], "ok", None)):
            with patch.object(a, "_append_governance_event", side_effect=capture_governance_event):
                a.audit_pr(
                    pr_number=57,
                    proposal=proposal,
                    diff_text=diff,
                    head_sha="sha_gov_test",
                    root=d,
                )

        assert len(captured_evidence) == 1
        assert captured_evidence[0]["proposal_id"] == pid


# ── 8. Remediation prompt contains findings text ─────────────────────────────

class TestRemediationPrompt:
    """_build_session_task_prompt with remediation= prepends the audit rejection block."""

    def test_remediation_block_injected(self):
        mb = _import_mb()
        d = _tmp_root()
        prop = _minimal_proposal()
        remediation = {
            "findings": ["foreign_file:engine/bad.py", "missing test coverage"],
            "rationale": "The diff introduced an undeclared file.",
        }
        prompt = mb._build_session_task_prompt(
            prop, "/wt", "metabolism/build-test", "cycle-001",
            remediation=remediation,
        )
        assert "PRIOR AUDIT REJECTION" in prompt
        assert "foreign_file:engine/bad.py" in prompt
        assert "missing test coverage" in prompt
        assert "The diff introduced an undeclared file." in prompt
        assert "Fix EXACTLY these issues." in prompt

    def test_no_remediation_no_block(self):
        mb = _import_mb()
        prop = _minimal_proposal()
        prompt = mb._build_session_task_prompt(
            prop, "/wt", "metabolism/build-test", "cycle-001",
            remediation=None,
        )
        assert "PRIOR AUDIT REJECTION" not in prompt

    def test_empty_remediation_dict_no_crash(self):
        mb = _import_mb()
        prop = _minimal_proposal()
        # Should not crash on empty dict
        prompt = mb._build_session_task_prompt(
            prop, "/wt", "metabolism/build-test", "cycle-001",
            remediation={},
        )
        assert isinstance(prompt, str)


# ── 9. _find_reject_for_proposal — most-recent, ignores approve ───────────────

class TestFindRejectForProposal:
    """_find_reject_for_proposal scans audit/ and returns the most-recent reject."""

    def test_returns_most_recent_reject(self):
        mb = _import_mb()
        d = _tmp_root()
        pid = "p_scan"

        # Write two reject records with different timestamps
        _write_audit_record(d, pr_number=10, proposal_id=pid, verdict="reject",
                            head_sha="sha_old", ts="2026-07-10T10:00:00+00:00")
        _write_audit_record(d, pr_number=11, proposal_id=pid, verdict="reject",
                            head_sha="sha_new", ts="2026-07-11T10:00:00+00:00")

        rec = mb._find_reject_for_proposal(pid, root=d)
        assert rec is not None
        assert rec.get("head_sha") == "sha_new", (
            f"Expected sha_new (most recent), got {rec.get('head_sha')!r}"
        )

    def test_ignores_approve_records(self):
        mb = _import_mb()
        d = _tmp_root()
        pid = "p_approve_only"

        _write_audit_record(d, pr_number=20, proposal_id=pid, verdict="approve")

        rec = mb._find_reject_for_proposal(pid, root=d)
        assert rec is None, "Should return None when only approve records exist"

    def test_ignores_other_proposals(self):
        mb = _import_mb()
        d = _tmp_root()

        _write_audit_record(d, pr_number=30, proposal_id="p_other", verdict="reject")

        rec = mb._find_reject_for_proposal("p_mine", root=d)
        assert rec is None, "Should only return records for the queried proposal_id"

    def test_returns_none_on_empty_dir(self):
        mb = _import_mb()
        d = _tmp_root()
        # No audit records written
        rec = mb._find_reject_for_proposal("p_nobody", root=d)
        assert rec is None

    def test_returns_none_on_missing_dir(self):
        mb = _import_mb()
        d = Path(tempfile.mkdtemp(prefix="metab_rem_empty_"))
        # No audit dir at all
        rec = mb._find_reject_for_proposal("p_nobody", root=d)
        assert rec is None


# ── 10. insight_bus has audit_rebuild_exhausted kind ─────────────────────────

class TestInsightBusKind:
    """audit_rebuild_exhausted is a valid kind in the insight bus."""

    def test_kind_registered(self):
        from engine.metabolism.insight_bus import _KINDS
        assert "audit_rebuild_exhausted" in _KINDS, (
            f"audit_rebuild_exhausted missing from _KINDS: {_KINDS}"
        )

    def test_build_row_accepts_kind(self):
        from engine.metabolism import insight_bus as ib
        row = ib.build_row(
            emitter="test",
            kind="audit_rebuild_exhausted",
            severity="high",
            entities=["p1", "cycle1"],
            summary="exhausted test",
        )
        assert row["kind"] == "audit_rebuild_exhausted"
        assert row["severity"] == "high"
