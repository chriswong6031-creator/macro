"""tests/test_metabolism_gc_and_merge_lifecycle.py — Hermetic tests for F3 fixes.

COVERAGE:
  1. reap_propose_branches: AUTONOMY_PAUSED gate suppresses deletion (loop paused).
  2. reap_propose_branches: branch older than retention + terminal journal → deleted.
  3. reap_propose_branches: branch within retention window → skipped (too fresh).
  4. reap_propose_branches: no parseable date in cycle_id → skipped.
  5. reap_propose_branches: journal exists but status not terminal → skipped.
  6. reap_propose_branches: journal absent → skipped.
  7. reap_propose_branches: dry_run=True → logged but git push not called.
  8. reap_propose_branches: git push --delete failure is non-fatal (returns error in summary).
  9. _parse_cycle_date: YYYY-MM-DD prefix parses correctly.
 10. _parse_cycle_date: no date prefix returns None.
 11. _parse_cycle_date: date embedded after "cycle-" prefix parses correctly.
 12. _delete_remote_propose_branch: dry_run=True → no subprocess call, returns True.
 13. _delete_remote_propose_branch: successful git push → returns True.
 14. _delete_remote_propose_branch: git push failure → non-fatal, returns False.
 15. run_merge_lane: when a merge succeeds and not dry_run, _delete_remote_propose_branch is called.
 16. run_merge_lane: paused → no branch deletion.
 17. _discover_recent_cycle_ids: cycle older than max age is excluded from scan results.
 18. _discover_recent_cycle_ids: cycle within max age is included.
 19. _discover_recent_cycle_ids: cycle_id with no date passes through (max-age filter skips undated).
 20. _branch_merged_into_main: branch rebased ahead of origin/main with unpushed
     commits → NOT merged (the pre-fix inverted `git log <branch>..origin/main`
     check called exactly this shape merged → reap-eligible).
 21. _branch_merged_into_main: tip-equal-to-main → merged (a commit is its own
     ancestor under merge-base --is-ancestor).
 22. _branch_merged_into_main: absorbed branch behind an advanced main → merged
     (the pre-fix check said NOT merged here — ancestry reaping never fired).
 23. _branch_merged_into_main: squash-merged branch is invisible to ancestry
     (documented limit — journal-terminal path reaps those); unknown ref →
     fail-safe False.
 24. gc() eligibility end-to-end on real worktrees: rebased-ahead skipped,
     tip-equal reaped.

All tests HERMETIC — no network; subprocess is mocked everywhere EXCEPT the
_branch_merged_into_main direction pins (## 20–24), which run real git against
throwaway tmp-dir repos: the bug being pinned was a wrong belief about git
range direction, and a mocked subprocess would re-encode the belief instead of
testing git.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# ── Fixtures ───────────────────────────────────────────────────────────────────

def _tmp_root() -> Path:
    d = Path(tempfile.mkdtemp(prefix="test_gc_merge_lifecycle_"))
    (d / "data" / "metabolism" / "journal").mkdir(parents=True)
    (d / "data" / "metabolism" / "dockets").mkdir(parents=True)
    (d / "scripts").mkdir(parents=True)
    return d


def _date_str(days_ago: int) -> str:
    """Return a YYYY-MM-DD string for `days_ago` days ago."""
    dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return dt.strftime("%Y-%m-%d")


def _make_cycle_id(days_ago: int, suffix: str = "abc") -> str:
    return f"cycle-{_date_str(days_ago)}-{suffix}"


def _write_journal(root: Path, cycle_id: str, status: str, stage_status: str | None = None) -> None:
    """Write a minimal journal file for cycle_id."""
    data: dict = {"status": status, "cycle_id": cycle_id, "stages": {}}
    if stage_status:
        data["stages"]["adjudicate_resolve"] = {"status": stage_status}
    (root / "data" / "metabolism" / "journal" / f"{cycle_id}.json").write_text(
        json.dumps(data), encoding="utf-8"
    )


# ── _parse_cycle_date tests ────────────────────────────────────────────────────

def test_parse_cycle_date_with_prefix():
    from scripts.metabolism_gc import _parse_cycle_date
    cid = "cycle-2026-07-10-abc"
    result = _parse_cycle_date(cid)
    assert result is not None
    assert result.year == 2026
    assert result.month == 7
    assert result.day == 10


def test_parse_cycle_date_no_date():
    from scripts.metabolism_gc import _parse_cycle_date
    cid = "no-date-here"
    assert _parse_cycle_date(cid) is None


def test_parse_cycle_date_date_at_start():
    from scripts.metabolism_gc import _parse_cycle_date
    cid = "2026-07-01-something"
    result = _parse_cycle_date(cid)
    assert result is not None
    assert result.day == 1


# ── reap_propose_branches tests ───────────────────────────────────────────────

def test_reap_paused_gate():
    """When AUTONOMY_PAUSED is not 'false', branch deletion is suppressed."""
    import importlib
    import scripts.metabolism_gc as gc_mod
    importlib.reload(gc_mod)  # clear any cached state

    root = _tmp_root()
    with patch.dict(os.environ, {"AUTONOMY_PAUSED": "true"}):
        with patch("scripts.metabolism_gc._is_paused", return_value=True):
            result = gc_mod.reap_propose_branches(root, dry_run=False)
    assert result["deleted"] == []
    assert result["errors"] == []


def test_reap_old_terminal_branch_deleted():
    """Branch older than retention + terminal journal → deleted."""
    from scripts.metabolism_gc import reap_propose_branches, _PROPOSE_BRANCH_RETENTION_DAYS
    root = _tmp_root()
    cycle_id = _make_cycle_id(_PROPOSE_BRANCH_RETENTION_DAYS + 5)
    _write_journal(root, cycle_id, status="done")

    branch_ref = f"refs/heads/metabolism/propose-{cycle_id}"
    ls_remote_output = f"abc123def456\t{branch_ref}\n"

    mock_ls = MagicMock()
    mock_ls.returncode = 0
    mock_ls.stdout = ls_remote_output

    mock_del = MagicMock()
    mock_del.returncode = 0
    mock_del.stderr = ""

    def fake_run(cmd, **kwargs):
        if "ls-remote" in cmd:
            return mock_ls
        if "--delete" in cmd:
            return mock_del
        return MagicMock(returncode=0, stdout="", stderr="")

    with patch("scripts.metabolism_gc._is_paused", return_value=False):
        with patch("subprocess.run", side_effect=fake_run):
            result = reap_propose_branches(root, dry_run=False)

    assert f"metabolism/propose-{cycle_id}" in result["deleted"]
    assert result["errors"] == []


def test_reap_fresh_branch_skipped():
    """Branch within retention window → skipped."""
    from scripts.metabolism_gc import reap_propose_branches, _PROPOSE_BRANCH_RETENTION_DAYS
    root = _tmp_root()
    cycle_id = _make_cycle_id(2)  # 2 days old — within 7-day retention
    _write_journal(root, cycle_id, status="done")

    branch_ref = f"refs/heads/metabolism/propose-{cycle_id}"
    mock_ls = MagicMock(returncode=0, stdout=f"abc123\t{branch_ref}\n")

    with patch("scripts.metabolism_gc._is_paused", return_value=False):
        with patch("subprocess.run", return_value=mock_ls):
            result = reap_propose_branches(root, dry_run=False)

    assert cycle_id in result["skipped"]
    assert result["deleted"] == []


def test_reap_no_date_in_cycle_id_skipped():
    """cycle_id without a parseable date prefix → skipped."""
    from scripts.metabolism_gc import reap_propose_branches
    root = _tmp_root()
    cycle_id = "nodatehere"
    _write_journal(root, cycle_id, status="done")

    branch_ref = f"refs/heads/metabolism/propose-{cycle_id}"
    mock_ls = MagicMock(returncode=0, stdout=f"abc123\t{branch_ref}\n")

    with patch("scripts.metabolism_gc._is_paused", return_value=False):
        with patch("subprocess.run", return_value=mock_ls):
            result = reap_propose_branches(root, dry_run=False)

    assert cycle_id in result["skipped"]
    assert result["deleted"] == []


def test_reap_non_terminal_journal_skipped():
    """Journal present but status not terminal → skipped."""
    from scripts.metabolism_gc import reap_propose_branches, _PROPOSE_BRANCH_RETENTION_DAYS
    root = _tmp_root()
    cycle_id = _make_cycle_id(_PROPOSE_BRANCH_RETENTION_DAYS + 5)
    _write_journal(root, cycle_id, status="running")

    branch_ref = f"refs/heads/metabolism/propose-{cycle_id}"
    mock_ls = MagicMock(returncode=0, stdout=f"abc123\t{branch_ref}\n")

    with patch("scripts.metabolism_gc._is_paused", return_value=False):
        with patch("subprocess.run", return_value=mock_ls):
            result = reap_propose_branches(root, dry_run=False)

    assert cycle_id in result["skipped"]
    assert result["deleted"] == []


def test_reap_no_journal_skipped():
    """No journal record → skipped (cannot confirm completion)."""
    from scripts.metabolism_gc import reap_propose_branches, _PROPOSE_BRANCH_RETENTION_DAYS
    root = _tmp_root()
    cycle_id = _make_cycle_id(_PROPOSE_BRANCH_RETENTION_DAYS + 5)
    # deliberately do NOT write a journal

    branch_ref = f"refs/heads/metabolism/propose-{cycle_id}"
    mock_ls = MagicMock(returncode=0, stdout=f"abc123\t{branch_ref}\n")

    with patch("scripts.metabolism_gc._is_paused", return_value=False):
        with patch("subprocess.run", return_value=mock_ls):
            result = reap_propose_branches(root, dry_run=False)

    assert cycle_id in result["skipped"]
    assert result["deleted"] == []


def test_reap_dry_run_no_push():
    """dry_run=True logs but does not call git push --delete."""
    from scripts.metabolism_gc import reap_propose_branches, _PROPOSE_BRANCH_RETENTION_DAYS
    root = _tmp_root()
    cycle_id = _make_cycle_id(_PROPOSE_BRANCH_RETENTION_DAYS + 5)
    _write_journal(root, cycle_id, status="done")

    branch_ref = f"refs/heads/metabolism/propose-{cycle_id}"
    mock_ls = MagicMock(returncode=0, stdout=f"abc123\t{branch_ref}\n")

    push_calls = []

    def fake_run(cmd, **kwargs):
        if "--delete" in cmd:
            push_calls.append(cmd)
            return MagicMock(returncode=0, stderr="")
        return mock_ls

    with patch("scripts.metabolism_gc._is_paused", return_value=False):
        with patch("subprocess.run", side_effect=fake_run):
            result = reap_propose_branches(root, dry_run=True)

    assert f"metabolism/propose-{cycle_id}" in result["deleted"]
    # dry_run=True must NOT actually call git push --delete
    assert push_calls == []


def test_reap_push_failure_nonfatal():
    """git push --delete failure is captured in errors but is non-fatal."""
    from scripts.metabolism_gc import reap_propose_branches, _PROPOSE_BRANCH_RETENTION_DAYS
    root = _tmp_root()
    cycle_id = _make_cycle_id(_PROPOSE_BRANCH_RETENTION_DAYS + 5)
    _write_journal(root, cycle_id, status="failed")

    branch_ref = f"refs/heads/metabolism/propose-{cycle_id}"
    mock_ls = MagicMock(returncode=0, stdout=f"abc123\t{branch_ref}\n")
    mock_fail = MagicMock(returncode=1, stderr="remote ref not found")

    def fake_run(cmd, **kwargs):
        if "--delete" in cmd:
            return mock_fail
        return mock_ls

    with patch("scripts.metabolism_gc._is_paused", return_value=False):
        with patch("subprocess.run", side_effect=fake_run):
            result = reap_propose_branches(root, dry_run=False)

    assert f"metabolism/propose-{cycle_id}" not in result["deleted"]
    assert any("metabolism/propose-" in e for e in result["errors"])


# ── _delete_remote_propose_branch tests ──────────────────────────────────────

def test_delete_remote_propose_dry_run():
    """dry_run=True → returns True without calling subprocess."""
    from scripts.metabolism_merge import _delete_remote_propose_branch
    root = _tmp_root()
    with patch("subprocess.run") as mock_run:
        result = _delete_remote_propose_branch("cycle-2026-07-01-test", root=root, dry_run=True)
    assert result is True
    mock_run.assert_not_called()


def test_delete_remote_propose_success():
    """Successful git push → returns True."""
    from scripts.metabolism_merge import _delete_remote_propose_branch
    root = _tmp_root()
    mock_result = MagicMock(returncode=0, stderr="")
    with patch("subprocess.run", return_value=mock_result):
        result = _delete_remote_propose_branch("cycle-2026-07-01-test", root=root)
    assert result is True


def test_delete_remote_propose_failure_nonfatal():
    """git push failure → returns False (non-fatal)."""
    from scripts.metabolism_merge import _delete_remote_propose_branch
    root = _tmp_root()
    mock_result = MagicMock(returncode=1, stderr="remote: error: delete")
    with patch("subprocess.run", return_value=mock_result):
        result = _delete_remote_propose_branch("cycle-2026-07-01-test", root=root)
    assert result is False


# ── run_merge_lane branch deletion wiring ─────────────────────────────────────

def test_run_merge_lane_paused_no_deletion():
    """When loop is paused, run_merge_lane is a no-op and no branch deletion occurs."""
    from scripts.metabolism_merge import run_merge_lane
    root = _tmp_root()
    docket = {"lobe": "til", "proposals": [{"proposal_id": "p1"}]}
    dp = root / "data" / "metabolism" / "dockets" / "test-cycle.json"
    dp.parent.mkdir(parents=True, exist_ok=True)
    dp.write_text(json.dumps(docket))

    with patch("scripts.metabolism_merge._is_paused", return_value=True):
        with patch("scripts.metabolism_merge._delete_remote_propose_branch") as mock_del:
            results = run_merge_lane("test-cycle", dp, root=root, dry_run=False)

    mock_del.assert_not_called()
    assert any(r.get("status") == "noop_paused" for r in results)


def test_run_merge_lane_successful_merge_triggers_deletion():
    """After a successful merge, _delete_remote_propose_branch is called for the cycle."""
    from scripts.metabolism_merge import run_merge_lane
    root = _tmp_root()

    docket = {
        "lobe": "til",
        "proposals": [{"proposal_id": "p1"}],
    }
    dp = root / "data" / "metabolism" / "dockets" / "cycle-2026-07-01-x.json"
    dp.parent.mkdir(parents=True, exist_ok=True)
    dp.write_text(json.dumps(docket))

    mock_pr = {
        "number": 42,
        "headRefName": "metabolism/build-til-cycle-2026-07-01-x",
        "statusCheckRollup": [{"state": "SUCCESS"}],
        "isDraft": True,
        "files": [{"path": "data/metabolism/proposals/p1.json"}],
    }

    with patch("scripts.metabolism_merge._is_paused", return_value=False):
        with patch("scripts.metabolism_merge._list_build_draft_prs", return_value=[mock_pr]):
            with patch("scripts.metabolism_merge._is_two_key_granted", return_value=True):
                with patch("scripts.metabolism_merge._pr_ci_green", return_value=True):
                    with patch("scripts.metabolism_merge._get_pr_files", return_value=["data/metabolism/proposals/p1.json"]):
                        with patch("scripts.metabolism_merge._fence_check_pr", return_value=(True, "ok")):
                            with patch("scripts.metabolism_merge._audit_approved", return_value=(True, "approved")):
                                with patch("scripts.metabolism_merge._pr_ci_green_at_sha", return_value=True):
                                    with patch("scripts.metabolism_merge._mark_pr_ready", return_value=True):
                                        with patch("scripts.metabolism_merge._rebase_merge_pr",
                                                   return_value={"merged": True, "attempts": 1, "error": None}):
                                            with patch("scripts.metabolism_merge._delete_remote_propose_branch") as mock_del:
                                                with patch("subprocess.run") as mock_sp:
                                                    # Stub the gh pr view call for headRefOid
                                                    mock_sp.return_value = MagicMock(
                                                        returncode=0,
                                                        stdout=json.dumps({"headRefOid": "abc123"}),
                                                    )
                                                    results = run_merge_lane(
                                                        "cycle-2026-07-01-x", dp, root=root, dry_run=False
                                                    )

    mock_del.assert_called_once_with(
        "cycle-2026-07-01-x", root=root, dry_run=False
    )
    assert any(r.get("status") == "merged" for r in results)


# ── _discover_recent_cycle_ids max-age filter ──────────────────────────────────

def test_discover_recent_cycles_old_cycle_excluded():
    """Cycles older than _DISCOVER_MAX_AGE_DAYS are excluded from scan results."""
    from scripts.metabolism_audit import _discover_recent_cycle_ids, _DISCOVER_MAX_AGE_DAYS
    old_cid = _make_cycle_id(_DISCOVER_MAX_AGE_DAYS + 5)
    branch_ref = f"refs/heads/metabolism/propose-{old_cid}"
    mock_result = MagicMock(returncode=0, stdout=f"abc123\t{branch_ref}\n")

    with patch("subprocess.run", return_value=mock_result):
        cycle_ids = _discover_recent_cycle_ids()

    assert old_cid not in cycle_ids


def test_discover_recent_cycles_fresh_cycle_included():
    """Cycles within _DISCOVER_MAX_AGE_DAYS are included."""
    from scripts.metabolism_audit import _discover_recent_cycle_ids
    fresh_cid = _make_cycle_id(3)  # 3 days old — within 30-day window
    branch_ref = f"refs/heads/metabolism/propose-{fresh_cid}"
    mock_result = MagicMock(returncode=0, stdout=f"abc123\t{branch_ref}\n")

    with patch("subprocess.run", return_value=mock_result):
        cycle_ids = _discover_recent_cycle_ids()

    assert fresh_cid in cycle_ids


def test_discover_recent_cycles_no_date_passes_through():
    """Undated cycle_ids (no parseable date) pass through the filter unchanged."""
    from scripts.metabolism_audit import _discover_recent_cycle_ids
    undated_cid = "cycle-nodatehere"
    branch_ref = f"refs/heads/metabolism/propose-{undated_cid}"
    mock_result = MagicMock(returncode=0, stdout=f"abc123\t{branch_ref}\n")

    with patch("subprocess.run", return_value=mock_result):
        cycle_ids = _discover_recent_cycle_ids()

    # Undated cycles are not excluded (we can't determine age)
    assert undated_cid in cycle_ids


# ── R-V6-5 multi-docket branch: merge fan-out + branch-deletion ownership ──────

def _merge_mock_pr(number: int, branch: str) -> dict:
    return {
        "number": number,
        "headRefName": branch,
        "statusCheckRollup": [{"state": "SUCCESS"}],
        "isDraft": True,
        "files": [{"path": "data/metabolism/proposals/p1.json"}],
    }


def _run_merge_lane_all_green(cycle_id: str, dp: Path, root: Path, mock_pr: dict,
                              **lane_kwargs):
    """Drive run_merge_lane through the full all-green mock stack."""
    from scripts.metabolism_merge import run_merge_lane
    with patch("scripts.metabolism_merge._is_paused", return_value=False):
        with patch("scripts.metabolism_merge._list_build_draft_prs", return_value=[mock_pr]):
            with patch("scripts.metabolism_merge._is_two_key_granted", return_value=True):
                with patch("scripts.metabolism_merge._pr_ci_green", return_value=True):
                    with patch("scripts.metabolism_merge._get_pr_files",
                               return_value=["data/metabolism/proposals/p1.json"]):
                        with patch("scripts.metabolism_merge._fence_check_pr",
                                   return_value=(True, "ok")):
                            with patch("scripts.metabolism_merge._audit_approved",
                                       return_value=(True, "approved")):
                                with patch("scripts.metabolism_merge._pr_ci_green_at_sha",
                                           return_value=True):
                                    with patch("scripts.metabolism_merge._mark_pr_ready",
                                               return_value=True):
                                        with patch("scripts.metabolism_merge._rebase_merge_pr",
                                                   return_value={"merged": True, "attempts": 1,
                                                                 "error": None}):
                                            with patch("scripts.metabolism_merge."
                                                       "_delete_remote_propose_branch") as mock_del:
                                                with patch("subprocess.run") as mock_sp:
                                                    mock_sp.return_value = MagicMock(
                                                        returncode=0,
                                                        stdout=json.dumps({"headRefOid": "abc123"}),
                                                    )
                                                    results = run_merge_lane(
                                                        cycle_id, dp, root=root, dry_run=False,
                                                        **lane_kwargs,
                                                    )
    return results, mock_del


def test_run_merge_lane_keep_propose_branch_suppresses_deletion():
    """delete_propose_branch=False: merge fires but the shared R-V6-5 propose
    branch is NOT deleted (per-docket workflow caller owns branch lifecycle)."""
    root = _tmp_root()
    cid = "cycle-2026-07-01-x-site-us-standouts"   # per-lobe docket cycle id
    docket = {"lobe": "site-us-standouts", "proposals": [{"proposal_id": "p1"}]}
    dp = root / "data" / "metabolism" / "dockets" / f"{cid}.json"
    dp.write_text(json.dumps(docket))

    from scripts.metabolism_build import _build_branch_name
    mock_pr = _merge_mock_pr(43, _build_branch_name("site-us-standouts", cid,
                                                    proposal_id="p1"))
    results, mock_del = _run_merge_lane_all_green(
        cid, dp, root, mock_pr, delete_propose_branch=False)

    assert any(r.get("status") == "merged" for r in results), (
        f"per-lobe docket PR did not merge: {results}"
    )
    mock_del.assert_not_called()


def test_merge_cli_keep_propose_branch_flag():
    """--keep-propose-branch plumbs delete_propose_branch=False; absent → True."""
    import scripts.metabolism_merge as mm
    root = _tmp_root()
    dp = root / "data" / "metabolism" / "dockets" / "c1.json"
    dp.write_text(json.dumps({"lobe": "til", "proposals": []}))

    with patch.object(mm, "run_merge_lane", return_value=[]) as mock_lane:
        mm.main(["--cycle-id", "c1", "--docket-file", str(dp),
                 "--keep-propose-branch"])
    assert mock_lane.call_args.kwargs["delete_propose_branch"] is False

    with patch.object(mm, "run_merge_lane", return_value=[]) as mock_lane:
        mm.main(["--cycle-id", "c1", "--docket-file", str(dp)])
    assert mock_lane.call_args.kwargs["delete_propose_branch"] is True


# ── pid-suffixed build-branch resolution (the branch the build lane REALLY creates)

def test_resolve_pid_suffixed_branch_via_claims():
    """run_build_lane names branches with the proposal_id suffix; the claims-row
    resolution must exact-match that form (was: un-suffixed only → every real
    build PR skipped as no_matching_proposal)."""
    from scripts.metabolism_merge import _resolve_proposal_id_for_branch
    from scripts.metabolism_build import _build_branch_name
    root = _tmp_root()
    cid = "cycle-2026-07-01-x"
    docket = {"lobe": "til", "proposals": [{"proposal_id": "p1"}]}
    dp = root / "data" / "metabolism" / "dockets" / f"{cid}.json"
    dp.write_text(json.dumps(docket))
    claims = root / "data" / "metabolism" / "claims.jsonl"
    claims.write_text(json.dumps({
        "schema": "metabolism.build_claims.v1", "cycle_id": cid,
        "proposal_id": "p1", "lobe": "til",
        "target_files": ["engine/x.py"], "ts": "2026-07-01T00:00:00+00:00",
    }) + "\n")

    branch = _build_branch_name("til", cid, proposal_id="p1")
    assert _resolve_proposal_id_for_branch(branch, cid, docket, dp, root=root) == "p1"


def test_resolve_pid_suffixed_branch_via_docket_fallback():
    """Without claims.jsonl, the docket fallback must match the pid-suffixed
    branch per proposal — not just first-in-docket."""
    from scripts.metabolism_merge import _resolve_proposal_id_for_branch
    from scripts.metabolism_build import _build_branch_name
    root = _tmp_root()
    cid = "cycle-2026-07-01-x"
    docket = {"lobe": "til",
              "proposals": [{"proposal_id": "p1"}, {"proposal_id": "p2"}]}
    dp = root / "data" / "metabolism" / "dockets" / f"{cid}.json"
    dp.write_text(json.dumps(docket))

    branch_p2 = _build_branch_name("til", cid, proposal_id="p2")
    assert _resolve_proposal_id_for_branch(branch_p2, cid, docket, dp, root=root) == "p2"
    # Legacy un-suffixed branches (pre-suffix build lanes) still resolve.
    legacy = _build_branch_name("til", cid)
    assert _resolve_proposal_id_for_branch(legacy, cid, docket, dp, root=root) == "p1"


def test_resolve_per_lobe_cycle_isolation():
    """A per-lobe docket's build branch must NOT resolve under the BASE cycle id
    (exact-match invariant — base sweeps list per-lobe PRs by substring and must
    skip them; the per-lobe docket's own sweep merges them)."""
    from scripts.metabolism_merge import _resolve_proposal_id_for_branch
    from scripts.metabolism_build import _build_branch_name
    root = _tmp_root()
    base = "cycle-2026-07-01-x"
    docket = {"lobe": "til", "proposals": [{"proposal_id": "p1"}]}
    dp = root / "data" / "metabolism" / "dockets" / f"{base}.json"
    dp.write_text(json.dumps(docket))

    per_lobe_branch = _build_branch_name(
        "site-us-standouts", f"{base}-site-us-standouts", proposal_id="p1")
    assert _resolve_proposal_id_for_branch(
        per_lobe_branch, base, docket, dp, root=root) is None


def test_merge_workflow_yaml_enumerates_dockets_and_keeps_branch():
    """The merge workflow must fan out per docket (--list-dockets), suppress the
    script's per-docket branch deletion (--keep-propose-branch), and own the
    branch delete behind the sweep-terminal guard."""
    wf = (_ROOT / ".github" / "workflows" / "metabolism-merge.yml").read_text()
    assert "--list-dockets" in wf, (
        "metabolism-merge.yml must enumerate the branch's dockets via "
        "scripts.metabolism_adjudicate --list-dockets (R-V6-5)"
    )
    assert "--keep-propose-branch" in wf, (
        "per-docket merge invocations must suppress the script's F3(a) branch "
        "deletion — first docket's merge would strand un-merged siblings"
    )
    assert 'basename "$_DOCKET" .json' in wf, (
        "per-docket cycle id must be the docket filename stem"
    )
    assert '"$_merged_any" -eq 1' in wf and '"$_inflight" -eq 0' in wf, (
        "workflow-owned branch deletion must be gated on sweep-terminal state"
    )


# ── _branch_merged_into_main direction pins (real git — the inversion trap) ────
#
# Real throwaway repos, offline, under tmp_path — still hermetic.  The pre-fix
# check ran `git log <branch>..origin/main` and treated EMPTY as merged; that
# range is the inverse (empty ⇔ origin/main is an ancestor of the BRANCH), so a
# freshly-rebased worktree with unpushed commits read as merged while a branch
# genuinely absorbed behind an advanced main read as unmerged.  These tests pin
# both directions against real git.  Keep consistent with scripts/worktree_gc.py
# (fleet session-worktree sweeper), which documents the same trap.

def _git(cwd: Path, *args: str) -> str:
    r = subprocess.run(["git", *args], cwd=str(cwd),
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, f"git {args} failed: {r.stderr}"
    return r.stdout.strip()


def _make_repo_with_origin_main(tmp_path: Path) -> Path:
    """Local repo with one base commit on main and refs/remotes/origin/main
    pointing at it (update-ref — no clone, no network)."""
    repo = (tmp_path / "repo").resolve()
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "gc-test@example.invalid")
    _git(repo, "config", "user.name", "gc-test")
    _git(repo, "config", "commit.gpgsign", "false")
    _git(repo, "checkout", "-B", "main")
    (repo / "base.txt").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "base.txt")
    _git(repo, "commit", "-m", "base")
    _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    return repo


def _commit_file(repo: Path, fname: str, msg: str) -> None:
    (repo / fname).write_text(f"{fname}\n", encoding="utf-8")
    _git(repo, "add", fname)
    _git(repo, "commit", "-m", msg)


def test_branch_rebased_ahead_with_local_commits_not_merged(tmp_path):
    """Branch rebased onto the origin/main tip with UNPUSHED commits is NOT
    merged.  The inverted pre-fix check called this merged → live rebased
    worktrees were reap-eligible (only the lsof guard saved them)."""
    from scripts.metabolism_gc import _branch_merged_into_main
    repo = _make_repo_with_origin_main(tmp_path)
    _git(repo, "checkout", "-b", "wf_ahead", "main")
    _commit_file(repo, "local.txt", "unpushed local commit")
    assert _branch_merged_into_main("wf_ahead", repo) is False


def test_branch_tip_equal_to_main_is_merged(tmp_path):
    """Branch whose tip IS the origin/main tip (nothing local) is merged —
    merge-base --is-ancestor counts a commit as its own ancestor."""
    from scripts.metabolism_gc import _branch_merged_into_main
    repo = _make_repo_with_origin_main(tmp_path)
    _git(repo, "branch", "wf_equal", "main")
    assert _branch_merged_into_main("wf_equal", repo) is True


def test_branch_absorbed_behind_advanced_main_is_merged(tmp_path):
    """Branch fully reachable from origin/main whose tip sits BEHIND an
    advanced main IS merged.  The pre-fix check said NOT merged here, so
    ancestry-based reaping never fired for genuinely absorbed branches."""
    from scripts.metabolism_gc import _branch_merged_into_main
    repo = _make_repo_with_origin_main(tmp_path)
    _git(repo, "branch", "wf_behind", "main")  # tip = base commit
    _commit_file(repo, "advance.txt", "main advances past the absorbed branch")
    _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    assert _branch_merged_into_main("wf_behind", repo) is True


def test_branch_squash_merged_invisible_to_ancestry(tmp_path):
    """Documented limit: a squash merge rewrites content into a new commit, so
    the branch tip is never an ancestor of origin/main — ancestry says NOT
    merged.  Squash-merged worktrees are reaped via the journal-terminal path
    (guard 4), not this check."""
    from scripts.metabolism_gc import _branch_merged_into_main
    repo = _make_repo_with_origin_main(tmp_path)
    _git(repo, "checkout", "-b", "wf_squash", "main")
    _commit_file(repo, "feature.txt", "feature work")
    _git(repo, "checkout", "main")
    _git(repo, "merge", "--squash", "wf_squash")
    _git(repo, "commit", "-m", "squash: feature work")
    _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    assert _branch_merged_into_main("wf_squash", repo) is False


def test_branch_unknown_ref_fail_safe_false(tmp_path):
    """An errored ancestry check (exit 128, unknown ref) must read as NOT
    merged — never reap on an error."""
    from scripts.metabolism_gc import _branch_merged_into_main
    repo = _make_repo_with_origin_main(tmp_path)
    assert _branch_merged_into_main("no_such_branch", repo) is False


def test_gc_eligibility_rebased_ahead_skipped_tip_equal_reaped(tmp_path):
    """End-to-end through gc() on real worktrees: the rebased-ahead worktree
    with unpushed commits must NOT be reap-eligible (the inverted check made
    exactly this shape eligible); the tip-equal-to-main worktree must be.
    lsof guard is patched out (host-dependent); dry_run so nothing is removed."""
    from scripts.metabolism_gc import gc
    repo = _make_repo_with_origin_main(tmp_path)
    wts = (tmp_path / "wts").resolve()
    wts.mkdir()

    ahead_wt = wts / "wf_ahead"
    _git(repo, "worktree", "add", "-b", "wf_ahead", str(ahead_wt), "main")
    _commit_file(ahead_wt, "local.txt", "unpushed local commit")

    equal_wt = wts / "wf_equal"
    _git(repo, "worktree", "add", "-b", "wf_equal", str(equal_wt), "main")

    with patch("scripts.metabolism_gc._has_open_files", return_value=False):
        summary = gc(repo, dry_run=True)

    # Compare by leaf name — path normalization (/var vs /private/var) varies.
    reaped_names = {Path(p).name for p in summary["reaped"]}
    skipped_names = {Path(p).name for p in summary["skipped_alive"]}
    assert "wf_equal" in reaped_names, f"tip-equal worktree not reaped: {summary}"
    assert "wf_ahead" not in reaped_names, (
        f"rebased-ahead worktree with unpushed commits was reap-eligible: {summary}"
    )
    assert "wf_ahead" in skipped_names, f"rebased-ahead worktree missing from skipped: {summary}"
