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

All tests HERMETIC — no network, no real git, no subprocess except where mocked.
"""
from __future__ import annotations

import json
import os
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
