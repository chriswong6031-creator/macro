"""tests/test_build_active_build_map.py — Unit tests for build_active_build_map.py.

Tests
-----
1. collision_basic                 — two PRs sharing files produce a collision record.
2. collision_no_match              — PRs with disjoint files produce no collision.
3. collision_sort_order            — pairs sorted by shared_count descending.
4. collision_protected_flag        — any_protected set when a shared file matches a glob.
5. collision_empty_files           — PRs with no files list are skipped silently.
6. protected_path_workflow         — .github/workflows/daily.yml matches protected globs.
7. protected_path_check_star       — scripts/check_dag_conformance.py matches check_*.py glob.
8. protected_path_neuralweb        — engine/neuralweb/foo.py matches engine/neuralweb/** glob.
9. protected_path_no_match         — a plain scripts/build_foo.py does NOT match.
10. render_section_headers          — render_markdown output contains all required H2 sections.
11. render_conflicting_flag         — CONFLICTING shown for merge_state==DIRTY.
12. render_truncation               — shared_files list > 8 items is truncated with "+N more".
13. render_draft_flag               — DRAFT flag appears for is_draft=True PR.
14. render_protected_count          — protected:N shown when protected_paths_touched is non-empty.
15. render_no_gh_invocation         — none of the pure functions call subprocess (no gh access).
16. render_merged_truncated_note    — truncation annotation in merged section header when flag set.
17. render_files_error_flag         — files:error flag shown and footnote present for files_error PR.
18. render_files_truncated_distinct — files_truncated renders "files-truncated", NOT "files:error".
19. render_unknown_mergeability     — UNKNOWN annotation line rendered when PRs remain UNKNOWN.
20. render_no_unknown_annotation    — UNKNOWN line absent when all PRs resolved.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

import pytest

# Ensure repo root is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.build_active_build_map import (
    compute_collisions,
    is_protected_path,
    protected_paths_for_pr,
    render_markdown,
    PROTECTED_GLOBS,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_pr(
    number: int,
    files: list[str],
    title: str = "Test PR",
    head_ref: str = "feat/test",
    is_draft: bool = False,
    merge_state: str = "CLEAN",
    merge_state_raw: str | None = "CLEAN",
    files_truncated: bool = False,
    files_error: bool = False,
    protected_paths_touched: list[str] | None = None,
    updated_at: str = "2026-07-01T00:00:00Z",
) -> dict:
    return {
        "number": number,
        "title": title,
        "head_ref": head_ref,
        "updated_at": updated_at,
        "is_draft": is_draft,
        "merge_state": merge_state,
        "merge_state_raw": merge_state_raw,
        "files_count": len(files),
        "files_truncated": files_truncated,
        "files_error": files_error,
        "files": files,
        "protected_paths_touched": protected_paths_touched if protected_paths_touched is not None else [],
    }


# ---------------------------------------------------------------------------
# 1-5: Collision computation
# ---------------------------------------------------------------------------

def test_collision_basic():
    pr1 = _make_pr(1, ["engine/foo.py", "site/bar.html"])
    pr2 = _make_pr(2, ["engine/foo.py", "site/other.html"])
    cols = compute_collisions([pr1, pr2])
    assert len(cols) == 1
    col = cols[0]
    assert col["pr_a"] == 1
    assert col["pr_b"] == 2
    assert "engine/foo.py" in col["shared_files"]
    assert col["shared_count"] == 1


def test_collision_no_match():
    pr1 = _make_pr(1, ["engine/foo.py"])
    pr2 = _make_pr(2, ["engine/bar.py"])
    cols = compute_collisions([pr1, pr2])
    assert cols == []


def test_collision_sort_order():
    pr1 = _make_pr(1, ["a.py", "b.py", "c.py"])
    pr2 = _make_pr(2, ["a.py", "b.py", "c.py"])  # 3 shared with pr1
    pr3 = _make_pr(3, ["a.py"])                    # 1 shared with pr1
    cols = compute_collisions([pr1, pr2, pr3])
    # pair (1,2) has 3 shared, pair (1,3) has 1 shared — sorted desc
    assert cols[0]["shared_count"] >= cols[-1]["shared_count"]
    assert cols[0]["pr_a"] == 1 and cols[0]["pr_b"] == 2


def test_collision_protected_flag():
    pr1 = _make_pr(1, [".github/workflows/daily.yml", "scripts/foo.py"])
    pr2 = _make_pr(2, [".github/workflows/daily.yml", "engine/bar.py"])
    cols = compute_collisions([pr1, pr2])
    assert len(cols) == 1
    assert cols[0]["any_protected"] is True


def test_collision_empty_files():
    pr1 = _make_pr(1, [])
    pr2 = _make_pr(2, ["engine/foo.py"])
    cols = compute_collisions([pr1, pr2])
    assert cols == []


# ---------------------------------------------------------------------------
# 6-9: Protected-path glob matching
# ---------------------------------------------------------------------------

def test_protected_path_workflow():
    assert is_protected_path(".github/workflows/daily.yml") is True
    assert is_protected_path(".github/workflows/render.yml") is True


def test_protected_path_check_star():
    assert is_protected_path("scripts/check_dag_conformance.py") is True
    assert is_protected_path("scripts/check_synapse_registry.py") is True
    assert is_protected_path("scripts/check_validated_claims.py") is True


def test_protected_path_neuralweb():
    assert is_protected_path("engine/neuralweb/factor_contradictions.py") is True
    assert is_protected_path("engine/neuralweb/kernel.py") is True


def test_protected_path_no_match():
    assert is_protected_path("scripts/build_sector_central.py") is False
    assert is_protected_path("site/macro.html") is False
    assert is_protected_path("engine/alert_triage.py") is False


# ---------------------------------------------------------------------------
# 10-14: Markdown rendering
# ---------------------------------------------------------------------------

def _fixture_payload(
    open_prs: list[dict] | None = None,
    recent_merged: list[dict] | None = None,
    collisions: list[dict] | None = None,
    merged_truncated: bool = False,
) -> dict:
    if open_prs is None:
        open_prs = []
    if recent_merged is None:
        recent_merged = []
    if collisions is None:
        collisions = []
    return {
        "schema": "active_builds.v1",
        "generated_at": "2026-07-06T12:00:00+00:00",
        "base": {"sha": "abc123def"},
        "merged_days": 14,
        "merged_truncated": merged_truncated,
        "open_prs": open_prs,
        "collisions": collisions,
        "recent_merged": recent_merged,
    }


def test_render_section_headers():
    md = render_markdown(_fixture_payload())
    assert "## Open PRs" in md
    assert "## File Collisions" in md
    assert "## Recently Merged" in md
    # Advisory header present
    assert "Advisory only" in md
    # Footer present
    assert "DO_NOT_REBUILD.md" in md


def test_render_conflicting_flag():
    pr = _make_pr(99, ["engine/foo.py"], merge_state="DIRTY", title="Conflicting PR")
    payload = _fixture_payload(open_prs=[pr])
    md = render_markdown(payload)
    assert "CONFLICTING" in md
    assert "#99" in md


def test_render_truncation():
    # Build a collision record with 10 shared files
    files = [f"engine/mod_{i}.py" for i in range(10)]
    pr1 = _make_pr(1, files)
    pr2 = _make_pr(2, files)
    cols = compute_collisions([pr1, pr2])
    payload = _fixture_payload(open_prs=[pr1, pr2], collisions=cols)
    md = render_markdown(payload)
    # 10 files, max 8 shown → "+2 more" should appear
    assert "+2 more" in md


def test_render_draft_flag():
    pr = _make_pr(42, ["scripts/foo.py"], is_draft=True, title="Draft work")
    payload = _fixture_payload(open_prs=[pr])
    md = render_markdown(payload)
    assert "DRAFT" in md
    assert "#42" in md


def test_render_protected_count():
    pr = _make_pr(
        7,
        ["config/dag.yml", "engine/validation.py"],
        protected_paths_touched=["config/dag.yml", "engine/validation.py"],
        title="Protected path PR",
    )
    payload = _fixture_payload(open_prs=[pr])
    md = render_markdown(payload)
    assert "protected:2" in md


# ---------------------------------------------------------------------------
# 15: No subprocess calls in pure functions
# ---------------------------------------------------------------------------

def test_no_gh_invocation_in_pure_functions():
    """Pure functions must not call subprocess — no gh access in tests."""
    with mock.patch("subprocess.run") as mock_run:
        pr1 = _make_pr(1, ["engine/foo.py"])
        pr2 = _make_pr(2, ["engine/foo.py"])
        compute_collisions([pr1, pr2])
        is_protected_path("scripts/check_dag_conformance.py")
        protected_paths_for_pr(pr1)
        render_markdown(_fixture_payload(open_prs=[pr1, pr2]))
        # subprocess.run must never have been called
        mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# 16-20: New fix tests (FIX 1-3 coverage)
# ---------------------------------------------------------------------------

def test_render_merged_truncated_note():
    """FIX 1: section header carries truncation annotation when merged_truncated=True."""
    payload = _fixture_payload(
        recent_merged=[{"number": 1, "title": "PR one", "merged_at": "2026-07-01T00:00:00Z"}],
        merged_truncated=True,
    )
    md = render_markdown(payload)
    assert "window truncated" in md
    assert "showing most recent 500" in md


def test_render_no_merged_truncated_note_when_false():
    """FIX 1: no truncation annotation when merged_truncated=False (default)."""
    payload = _fixture_payload(
        recent_merged=[{"number": 1, "title": "PR one", "merged_at": "2026-07-01T00:00:00Z"}],
        merged_truncated=False,
    )
    md = render_markdown(payload)
    assert "window truncated" not in md
    assert "showing most recent 500" not in md


def test_render_files_error_flag():
    """FIX 3: files_error PR renders 'files:error' flag and footnote."""
    pr = _make_pr(55, [], title="Error PR", files_error=True, files_truncated=False)
    payload = _fixture_payload(open_prs=[pr])
    md = render_markdown(payload)
    assert "files:error" in md
    # Footnote about unknown collisions must also appear
    assert "collision data for those PRs is unknown" in md


def test_render_files_truncated_distinct():
    """FIX 3: files_truncated renders 'files-truncated' NOT 'files:error', no footnote."""
    pr = _make_pr(56, ["a.py"] * 100, title="Truncated PR", files_error=False, files_truncated=True)
    payload = _fixture_payload(open_prs=[pr])
    md = render_markdown(payload)
    assert "files-truncated" in md
    assert "files:error" not in md
    assert "collision data for those PRs is unknown" not in md


def test_render_unknown_mergeability():
    """FIX 2: UNKNOWN annotation line appears when PRs remain UNKNOWN after per-PR view."""
    pr = _make_pr(
        77,
        ["engine/foo.py"],
        merge_state="UNKNOWN",
        merge_state_raw="UNKNOWN",
        title="Unknown merge state",
    )
    payload = _fixture_payload(open_prs=[pr])
    md = render_markdown(payload)
    assert "mergeability not yet computed by GitHub (UNKNOWN)" in md
    assert "1 of 1 PRs" in md


def test_render_no_unknown_annotation():
    """FIX 2: UNKNOWN annotation line absent when all PRs resolved to non-UNKNOWN."""
    pr = _make_pr(
        78,
        ["engine/foo.py"],
        merge_state="CLEAN",
        merge_state_raw="CLEAN",
        title="Clean merge state",
    )
    payload = _fixture_payload(open_prs=[pr])
    md = render_markdown(payload)
    assert "mergeability not yet computed by GitHub" not in md
