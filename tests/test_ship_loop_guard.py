"""Regression tests for the tracked Claude completion guard."""

from __future__ import annotations

import contextlib
import email.message
import importlib.util
import io
import json
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
HOOK_PATH = ROOT / ".claude" / "hooks" / "ship_loop_guard.py"
SPEC = importlib.util.spec_from_file_location("ship_loop_guard", HOOK_PATH)
assert SPEC and SPEC.loader
GUARD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GUARD)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ("git", *args),
        cwd=repo,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    ).stdout.strip()


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "config", "user.email", "test@example.com")
    (repo / "kept.txt").write_text("baseline\n", encoding="utf-8")
    _git(repo, "add", "kept.txt")
    _git(repo, "commit", "-m", "initial")
    return repo


def test_fingerprint_ignores_unchanged_baseline_dirt(tmp_path):
    repo = _repo(tmp_path)
    (repo / "kept.txt").write_text("pre-existing\n", encoding="utf-8")
    baseline = GUARD._fingerprint(repo)
    assert GUARD._changed_since_baseline(baseline, GUARD._fingerprint(repo)) == []


def test_fingerprint_detects_session_edit_on_dirty_baseline(tmp_path):
    repo = _repo(tmp_path)
    (repo / "kept.txt").write_text("pre-existing\n", encoding="utf-8")
    baseline = GUARD._fingerprint(repo)
    (repo / "kept.txt").write_text("session edit\n", encoding="utf-8")
    assert GUARD._changed_since_baseline(baseline, GUARD._fingerprint(repo)) == ["kept.txt"]


def test_fingerprint_detects_new_and_deleted_paths(tmp_path):
    repo = _repo(tmp_path)
    baseline = GUARD._fingerprint(repo)
    (repo / "new.txt").write_text("new\n", encoding="utf-8")
    assert GUARD._changed_since_baseline(baseline, GUARD._fingerprint(repo)) == ["new.txt"]
    (repo / "new.txt").unlink()
    (repo / "kept.txt").unlink()
    assert GUARD._changed_since_baseline(baseline, GUARD._fingerprint(repo)) == ["kept.txt"]


def _nested_repo(repo: Path, rel: str) -> Path:
    """Build the shape git reports as ONE untracked directory entry.

    An agent worktree carries a `.git` entry, and git's status scan stops at
    that boundary instead of recursing, so the whole tree arrives as a single
    `?? <dir>/` line whose mtime moves whenever its owner touches a child.
    Measured: a real nested repository produces `?? vendor/nested/`, while a
    worktree whose gitdir has been pruned is recursed into and produces one
    line per file — the fix has to survive both shapes.
    """
    nested = repo / rel
    nested.mkdir(parents=True)
    _git(nested, "init", "-b", "main")
    _git(nested, "config", "user.name", "Other Session")
    _git(nested, "config", "user.email", "other@example.com")
    (nested / "work.py").write_text("owned by another session\n", encoding="utf-8")
    return nested


def test_a_path_that_becomes_ignored_mid_session_does_not_block(tmp_path):
    """Ignoring foreign dirt must not itself register as this session's work.

    Measured 2026-07-30: adding `.codex-worktrees/` to `.git/info/exclude`
    mid-session turned 34 already-baselined directories into "outstanding
    changes", because the union comparison read every vanished path as
    `<fingerprint> != None`. The remedy for the noise CAUSED the block.
    """
    repo = _repo(tmp_path)
    scratch = repo / "scratch"
    scratch.mkdir()
    (scratch / "note.txt").write_text("pre-existing dirt\n", encoding="utf-8")
    baseline = GUARD._fingerprint(repo)
    assert "scratch/note.txt" in baseline

    exclude = repo / ".git" / "info" / "exclude"
    exclude.parent.mkdir(parents=True, exist_ok=True)
    exclude.write_text("scratch/\n", encoding="utf-8")

    assert GUARD._changed_since_baseline(baseline, GUARD._fingerprint(repo)) == []


def test_a_foreign_worktree_does_not_block_while_its_owner_works(tmp_path):
    """Another session's checkout is not this session's uncommitted work.

    The blocked session can neither commit it nor delete it without destroying
    live work, so any churn there is an unsatisfiable gate.
    """
    repo = _repo(tmp_path)
    nested = _nested_repo(repo, ".codex-worktrees/other-session")
    baseline = GUARD._fingerprint(repo)
    assert not [path for path in baseline if path.startswith(".codex-worktrees/")]

    # The owner keeps working: a new child, an edit, and a bumped directory mtime.
    (nested / "another.py").write_text("more work\n", encoding="utf-8")
    (nested / "work.py").write_text("edited by its owner\n", encoding="utf-8")
    later = time.time() + 60
    os.utime(nested, (later, later))

    assert GUARD._changed_since_baseline(baseline, GUARD._fingerprint(repo)) == []


def test_a_pruned_worktree_git_recurses_into_is_excluded_too(tmp_path):
    """The file-shaped variant of the same entry must be excluded as well.

    A worktree whose gitdir was pruned is no longer a boundary, so git recurses
    and reports each file. Both `.claire/worktrees/<x>/tests/test_y.py` and
    `?? .codex-worktrees/<x>/` were present in the same measured status output.
    """
    repo = _repo(tmp_path)
    stale = repo / ".claire" / "worktrees" / "pruned-session"
    stale.mkdir(parents=True)
    (stale / ".git").write_text("gitdir: /nonexistent/worktrees/pruned\n", encoding="utf-8")
    (stale / "work.py").write_text("owned by another session\n", encoding="utf-8")

    baseline = GUARD._fingerprint(repo)
    assert not [path for path in baseline if path.startswith(".claire/")]

    (stale / "work.py").write_text("edited by its owner\n", encoding="utf-8")
    assert GUARD._changed_since_baseline(baseline, GUARD._fingerprint(repo)) == []


def test_a_nested_repository_is_fingerprinted_by_presence_not_by_metadata(tmp_path):
    """A directory entry outside the known roots must be stable too.

    Root exclusion alone would leave the next agent fleet's root — one nobody
    has added to the list — churning on `st_mtime_ns`. Git already declined to
    look inside a nested repository; whether it is dirty is a question about
    its own repository, so presence is the whole signal.
    """
    repo = _repo(tmp_path)
    nested = _nested_repo(repo, "vendor/nested")
    baseline = GUARD._fingerprint(repo)
    assert baseline["vendor/nested/"] == "??:dir"

    (nested / "another.py").write_text("more work\n", encoding="utf-8")
    later = time.time() + 60
    os.utime(nested, (later, later))

    assert GUARD._changed_since_baseline(baseline, GUARD._fingerprint(repo)) == []


def test_a_new_file_written_by_the_session_still_blocks(tmp_path):
    """The gate's real job, asserted alongside a churning foreign worktree."""
    repo = _repo(tmp_path)
    _nested_repo(repo, ".codex-worktrees/other-session")
    baseline = GUARD._fingerprint(repo)

    (repo / "scripts").mkdir()
    (repo / "scripts" / "new_builder.py").write_text("session work\n", encoding="utf-8")

    assert GUARD._changed_since_baseline(baseline, GUARD._fingerprint(repo)) == [
        "scripts/new_builder.py"
    ]


def _dirty_after_shipped_exclusion(repo: Path, baseline: dict) -> list[str]:
    """The Stop gate's dirty verdict, including the shipped-identical filter."""
    now = GUARD._fingerprint(repo)
    dirty = GUARD._changed_since_baseline(baseline, now)
    shipped = GUARD._shipped_identical_untracked(repo, now, dirty)
    return [entry for entry in dirty if entry not in shipped]


def _repo_with_stale_head(tmp_path: Path) -> Path:
    """A checkout detached on a HEAD that predates origin/main's hook file.

    Models the 2026-08-20 primary-checkout state: origin/main tracks
    `.claude/hooks/hook.py`, the working tree sits on an older commit that
    does not, so a byte-restore of the shipped file shows up as `??`.
    """
    repo = _repo(tmp_path)
    old_head = _git(repo, "rev-parse", "HEAD")
    hooks = repo / ".claude" / "hooks"
    hooks.mkdir(parents=True)
    (hooks / "hook.py").write_text("shipped bytes\n", encoding="utf-8")
    _git(repo, "add", ".claude/hooks/hook.py")
    _git(repo, "commit", "-m", "ship hook")
    _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    _git(repo, "checkout", "--detach", old_head)
    return repo


def test_untracked_bytes_identical_to_origin_main_do_not_block(tmp_path):
    """The documented `git show origin/main:<p> > <p>` repair is not dirt.

    2026-08-20: three hook files byte-restored into the stale primary checkout
    blocked every session evaluating that tree, though a commit would have
    added nothing main did not already have.
    """
    repo = _repo_with_stale_head(tmp_path)
    baseline = GUARD._fingerprint(repo)

    hook = repo / ".claude" / "hooks" / "hook.py"
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text("shipped bytes\n", encoding="utf-8")

    assert GUARD._fingerprint(repo)[".claude/hooks/hook.py"].startswith("??:")
    assert _dirty_after_shipped_exclusion(repo, baseline) == []


def test_untracked_bytes_that_differ_from_origin_main_still_block(tmp_path):
    """One changed byte is real unshipped work, not a restore."""
    repo = _repo_with_stale_head(tmp_path)
    baseline = GUARD._fingerprint(repo)

    hook = repo / ".claude" / "hooks" / "hook.py"
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text("shipped bytes plus an edit\n", encoding="utf-8")

    assert _dirty_after_shipped_exclusion(repo, baseline) == [".claude/hooks/hook.py"]


def test_the_shipped_exclusion_fails_closed_without_an_origin_main_ref(tmp_path):
    """No origin/main to compare against -> nothing is excused."""
    repo = _repo_with_stale_head(tmp_path)
    _git(repo, "update-ref", "-d", "refs/remotes/origin/main")
    baseline = GUARD._fingerprint(repo)

    hook = repo / ".claude" / "hooks" / "hook.py"
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text("shipped bytes\n", encoding="utf-8")

    assert _dirty_after_shipped_exclusion(repo, baseline) == [".claude/hooks/hook.py"]


def test_a_tracked_file_rewritten_to_match_origin_main_still_blocks(tmp_path):
    """The exclusion is for `??` entries only.

    A tracked file whose working bytes match origin/main is still a diff
    against HEAD — excusing it would also excuse an un-pulled revert riding
    in the working tree.
    """
    repo = _repo(tmp_path)
    old_head = _git(repo, "rev-parse", "HEAD")
    (repo / "kept.txt").write_text("v2 shipped\n", encoding="utf-8")
    _git(repo, "add", "kept.txt")
    _git(repo, "commit", "-m", "v2")
    _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    _git(repo, "checkout", "--detach", old_head)
    baseline = GUARD._fingerprint(repo)

    (repo / "kept.txt").write_text("v2 shipped\n", encoding="utf-8")

    current = GUARD._fingerprint(repo)
    assert current["kept.txt"].startswith(" M:")
    assert _dirty_after_shipped_exclusion(repo, baseline) == ["kept.txt"]


def test_an_untracked_symlink_is_never_excused_as_shipped(tmp_path):
    """A symlink's blob is its target string; the followed file must not count."""
    repo = _repo_with_stale_head(tmp_path)
    baseline = GUARD._fingerprint(repo)

    target = repo / "target.txt"
    target.write_text("shipped bytes\n", encoding="utf-8")
    hook = repo / ".claude" / "hooks" / "hook.py"
    hook.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(target, hook)

    dirty = _dirty_after_shipped_exclusion(repo, baseline)
    assert ".claude/hooks/hook.py" in dirty


def test_a_tracked_file_deleted_by_the_session_still_blocks(tmp_path):
    """The inverse case: leaving the working tree is not leaving the status.

    Narrowing the comparison to paths git still reports must not be confused
    with narrowing it to paths that still EXIST. A deleted tracked file is gone
    from disk but present in status as ` D`, so it keeps blocking.
    """
    repo = _repo(tmp_path)
    baseline = GUARD._fingerprint(repo)
    (repo / "kept.txt").unlink()

    current = GUARD._fingerprint(repo)
    assert current["kept.txt"].startswith(" D:")
    assert GUARD._changed_since_baseline(baseline, current) == ["kept.txt"]


def test_tracked_content_under_a_worktree_root_still_blocks(tmp_path):
    """The exclusion is for UNTRACKED foreign checkouts, and fails closed.

    These roots are ignored by construction, so anything git tracks under one
    is real repository content and keeps gating normally.
    """
    repo = _repo(tmp_path)
    root = repo / ".codex-worktrees"
    root.mkdir()
    (root / "README.md").write_text("tracked\n", encoding="utf-8")
    _git(repo, "add", "-f", ".codex-worktrees/README.md")
    _git(repo, "commit", "-m", "track a file under the root")

    baseline = GUARD._fingerprint(repo)
    (root / "README.md").write_text("session edit\n", encoding="utf-8")

    assert GUARD._changed_since_baseline(baseline, GUARD._fingerprint(repo)) == [
        ".codex-worktrees/README.md"
    ]


def test_the_worktree_exclusion_is_anchored_at_the_repository_root(tmp_path):
    """A root's name deeper in the tree is not a foreign checkout."""
    repo = _repo(tmp_path)
    stray = repo / "docs" / ".codex-worktrees"
    stray.mkdir(parents=True)
    baseline = GUARD._fingerprint(repo)

    (stray / "note.md").write_text("session work\n", encoding="utf-8")

    assert GUARD._changed_since_baseline(baseline, GUARD._fingerprint(repo)) == [
        "docs/.codex-worktrees/note.md"
    ]


def test_github_slug_accepts_https_and_ssh(monkeypatch, tmp_path):
    repo = _repo(tmp_path)
    monkeypatch.setattr(
        GUARD, "_run", lambda *_args, **_kwargs: "https://github.com/acme/widgets.git"
    )
    assert GUARD._github_slug(repo) == ("acme", "widgets")
    monkeypatch.setattr(GUARD, "_run", lambda *_args, **_kwargs: "git@github.com:acme/widgets.git")
    assert GUARD._github_slug(repo) == ("acme", "widgets")


def test_the_health_payload_is_never_sniffed_for_a_sha():
    """The recursive sha-sniffer the live gate used to read is gone, not spare.

    It returned whichever plausible key the payload yielded first, which made the
    gate read `commit` for every merge — see
    test_a_pull_only_merge_is_proven_live_by_the_checkout_field for what that cost.
    `_health_sha` reads one NAMED field; nothing may reintroduce a walker beside it.
    """
    assert not hasattr(GUARD, "_find_commit")
    assert GUARD._health_sha({"ok": True, "deployment": {"revision": "a" * 40}}, "commit") == ""


def _commit(repo: Path, rel: str, body: str, message: str) -> str:
    target = repo / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    _git(repo, "add", rel)
    _git(repo, "commit", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def test_needs_render_only_when_the_merge_itself_touched_render_inputs(tmp_path):
    """The render precondition is scoped to the merge's OWN diff.

    render.yml's push trigger is path-filtered, so a merge that matched none of
    those paths never queues a render of its own, and demanding one is an
    unsatisfiable block rather than a real gap. (_render_status may now
    also accept a later main descendant's render — that widens what SATISFIES the
    requirement, not which merges carry one.)
    """
    repo = _repo(tmp_path)
    start_head = _git(repo, "rev-parse", "HEAD")
    # A CONCURRENT session's template merge lands first — this is what used to
    # poison the session-range basis for every later unrelated merge.
    _commit(repo, "templates/index.html", "<p>other session</p>\n", "other: hero")
    mine = _commit(repo, ".github/workflows/ci.yml", "on: push\n", "ci: wire a test")

    assert GUARD._needs_render(repo, mine, start_head, mine) is False, (
        "a ci.yml-only merge must not require a render it can never have"
    )
    # And the session range genuinely does contain templates/ — proving the
    # False above comes from correct scoping, not from an empty diff.
    session_range = _git(repo, "diff", "--name-only", start_head, mine).splitlines()
    assert "templates/index.html" in session_range


def test_needs_render_still_fires_on_a_real_template_or_builder_merge(tmp_path):
    """The fix must not weaken the gate for merges that DO render."""
    repo = _repo(tmp_path)
    start_head = _git(repo, "rev-parse", "HEAD")
    tmpl = _commit(repo, "templates/macro.html.j2", "{{ x }}\n", "feat: template")
    assert GUARD._needs_render(repo, tmpl, start_head, tmpl) is True

    builder = _commit(repo, "scripts/build_thing.py", "print(1)\n", "feat: builder")
    assert GUARD._needs_render(repo, builder, start_head, builder) is True

    # A sibling script that is not a build_* entrypoint must not trigger one.
    other = _commit(repo, "scripts/check_thing.py", "print(2)\n", "chore: checker")
    assert GUARD._needs_render(repo, other, start_head, other) is False

    # Nor a NESTED build_*: the fail-closed fallback models the old top-level
    # wildcard, which did not cross `/`, and the lane invokes nothing under
    # scripts/research/ regardless.
    nested = _commit(repo, "scripts/research/build_panel.py", "print(3)\n", "chore: research")
    assert GUARD._needs_render(repo, nested, start_head, nested) is False


def _commit_files(repo: Path, files: dict[str, str], message: str) -> str:
    """Commit several paths at once — a paired asset ships both halves together."""
    for rel, body in files.items():
        target = repo / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
        _git(repo, "add", rel)
    _git(repo, "commit", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _paired_repo(tmp_path: Path) -> Path:
    """A fixture repo carrying the REAL pair enumerator the guard loads.

    Copied rather than stubbed: the point of the exemption is that the guard and
    CI's ui.template_site_sync gate read one definition, so the test must exercise
    that same file.
    """
    repo = _repo(tmp_path)
    (repo / "scripts").mkdir(exist_ok=True)
    shutil.copy(
        ROOT / "scripts" / "check_template_site_sync.py",
        repo / "scripts" / "check_template_site_sync.py",
    )
    _git(repo, "add", "scripts/check_template_site_sync.py")
    _git(repo, "commit", "-m", "chore: the pair enumerator")
    return repo


def test_a_paired_plain_copy_asset_merge_does_not_require_a_render(tmp_path):
    """THE false gate. #3671's exact shape: templates/<name> + its site/ twin.

    render.yml produces re-baked .j2 pages and ?v= re-stamps; a plain-copy asset
    is neither. Its site/ copy is committed straight to main and the VPS pulls
    main every 3 minutes, so it was live 3 minutes after the merge — while the
    guard held Stop at `render_pending` for 40+ minutes against a render lane in
    which 28 of the last 30 runs had concluded `cancelled`.
    """
    repo = _paired_repo(tmp_path)
    start_head = _git(repo, "rev-parse", "HEAD")
    paired = _commit_files(
        repo,
        {
            "templates/mm_brain.js": "var brain = 'light';\n",
            "site/mm_brain.js": "var brain = 'light';\n",
        },
        "feat(brain): light-mode theme",
    )
    assert GUARD._needs_render(repo, paired, start_head, paired) is False, (
        "a paired plain-copy asset is live via the VPS pull; render produces nothing for it"
    )
    # Several pairs at once is the same shape, not a weaker case.
    many = _commit_files(
        repo,
        {
            "templates/theme.css": "body{color:#111}\n",
            "site/theme.css": "body{color:#111}\n",
            "templates/index.html": "<h1>hi</h1>\n",
            "site/index.html": "<h1>hi</h1>\n",
        },
        "fix(landing): restyle",
    )
    assert GUARD._needs_render(repo, many, start_head, many) is False


def test_a_j2_riding_with_a_paired_asset_still_requires_a_render(tmp_path):
    """The exemption is per-diff, not per-file: one .j2 re-bake keeps the gate."""
    repo = _paired_repo(tmp_path)
    start_head = _git(repo, "rev-parse", "HEAD")
    mixed = _commit_files(
        repo,
        {
            "templates/mm_brain.js": "var brain = 1;\n",
            "site/mm_brain.js": "var brain = 1;\n",
            "templates/macro.html.j2": "{{ x }}\n",
        },
        "feat: asset + page",
    )
    assert GUARD._needs_render(repo, mixed, start_head, mixed) is True


def test_a_one_sided_or_unpaired_templates_edit_still_requires_a_render(tmp_path):
    """Fail closed on everything the pair list cannot vouch for."""
    repo = _paired_repo(tmp_path)
    start_head = _git(repo, "rev-parse", "HEAD")

    # site/ twin missing from the commit: the sync gate rejects this anyway, and
    # it means the live bytes have not moved.
    one_sided = _commit(repo, "templates/mm_brain.js", "var brain = 2;\n", "fix: source only")
    assert GUARD._needs_render(repo, one_sided, start_head, one_sided) is True

    # Never shipped as a site/ copy -> not a pair -> render.
    unpaired = _commit_files(
        repo,
        {"templates/partial.html": "<p>x</p>\n"},
        "feat: unshipped asset",
    )
    assert GUARD._needs_render(repo, unpaired, start_head, unpaired) is True

    # find_pairs walks direct children only; templates/fonts/ is a render copytree.
    nested = _commit_files(
        repo,
        {"templates/fonts/x.woff2": "binary\n", "site/fonts/x.woff2": "binary\n"},
        "feat(fonts): subset",
    )
    assert GUARD._needs_render(repo, nested, start_head, nested) is True


def test_the_page_rewriting_sweeps_require_a_render(tmp_path):
    """render.yml renders on these too — they rewrite every page in site/.

    Omitting them under-required a render, which is the fail-OPEN direction: the
    #3558 class of change reaches main and re-bakes nothing.
    """
    repo = _paired_repo(tmp_path)
    start_head = _git(repo, "rev-parse", "HEAD")
    for rel in ("scripts/optimize_assets.py", "scripts/externalize_css.py",
                "scripts/inject_data_base.py", "lib/pages.py"):
        sha = _commit(repo, rel, f"# {rel}\n", f"fix: {rel}")
        assert GUARD._needs_render(repo, sha, start_head, sha) is True, rel


@pytest.mark.needs_full_checkout("site")
def test_the_pair_list_is_the_ci_gate_s_own_enumeration(tmp_path):
    """One definition, so the exemption and ui.template_site_sync cannot drift.

    Marked: it asserts the pair list is NON-EMPTY, and `find_pairs` builds that
    list by walking `site/` — which a sparse session worktree omits (policy R8).
    Without the marker it fails with a bare `assert set()` that reads like a real
    regression in the exemption logic.
    """
    import scripts.check_template_site_sync as sync

    expected = {name for name, _t, _s in sync.find_pairs(ROOT)}
    assert expected, "the repo must have plain-copy pairs for this exemption to matter"
    assert GUARD._plain_copy_pairs(ROOT) == expected

    # Ignorance is not permission: an unreadable pair list requires the render.
    assert GUARD._plain_copy_pairs(tmp_path) == set()


def test_needs_render_matches_the_real_merges_it_was_written_for(tmp_path):
    """Replayed against this repo's own history, not a fixture.

    0effaadbd31 = #3671 (templates/mm_brain.js + site/mm_brain.js, no .j2) — the
    merge that spent 40+ minutes blocked while already live.
    a7e8c15b30b = #3696 (templates/intl.html.j2 + rendered pages) — still gated.
    """
    for sha in ("0effaadbd31", "a7e8c15b30b"):
        if subprocess.run(
            ("git", "cat-file", "-e", f"{sha}^{{commit}}"), cwd=ROOT, check=False
        ).returncode:
            pytest.skip(f"{sha} not present (shallow clone)")
    assert GUARD._needs_render(ROOT, "0effaadbd31", "HEAD", "HEAD") is False
    assert GUARD._needs_render(ROOT, "a7e8c15b30b", "HEAD", "HEAD") is True


def _public_lane_repo(tmp_path: Path) -> Path:
    """A fixture repo carrying the real pair enumerator AND both real workflows.

    Copied rather than stubbed, for the same reason `_paired_repo` copies the
    sync gate: the point of the #3834 split is that the guard READS the two
    workflows instead of transcribing them, so the test has to exercise the very
    files CI and GitHub read.
    """
    repo = _paired_repo(tmp_path)
    workflows = repo / ".github" / "workflows"
    workflows.mkdir(parents=True, exist_ok=True)
    for name in ("render.yml", "public-render.yml"):
        shutil.copy(ROOT / ".github" / "workflows" / name, workflows / name)
    _git(repo, "add", ".github")
    _git(repo, "commit", "-m", "chore: both render lanes")
    return repo


def test_a_public_surface_merge_owes_the_fast_lane_not_the_heavy_render(tmp_path):
    """THE false gate the #3834 split created. PR #3897's exact shape.

    render.yml's push filter negates `templates/plans.html.j2`, so a
    push-triggered render.yml run for this merge CANNOT EXIST — and the guard
    demanded one forever. Observed 2026-07-28: merged as 7fe17018,
    public-render.yml run 30349907107 concluded success on that exact sha and
    pushed d4ac971df7a, https://www.mastermind-x.com/plans.html was browser-
    verified live in production, and Stop still returned `render_pending`.
    """
    repo = _public_lane_repo(tmp_path)
    start_head = _git(repo, "rev-parse", "HEAD")
    merged = _commit_files(
        repo,
        {
            "templates/plans.html.j2": "{% extends 'seo_base.html.j2' %}\n",
            "site/plans.html": "<h1>Plans</h1>\n",
        },
        "feat(plans): rebuild the pricing page",
    )
    assert GUARD._needs_render(repo, merged, start_head, merged) is False, (
        "render.yml excludes this path, so demanding its run blocks forever"
    )
    assert GUARD._needs_public_render(repo, merged, start_head, merged) is True, (
        "the fast lane owns it, and its green run is what satisfies the gate"
    )


def test_every_surface_render_yml_negates_is_owned_by_the_public_lane(tmp_path):
    """The whole negation list, path by path — no lane may be left unowned.

    A path render.yml excludes and public-render.yml never claims is a dead
    wire: nothing renders it, and a guard that exempted it would be fail-OPEN.
    """
    repo = _public_lane_repo(tmp_path)
    start_head = _git(repo, "rev-parse", "HEAD")
    for rel in (
        "templates/plans.html.j2",
        "templates/support.html.j2",
        "templates/unsubscribe.html.j2",
        "templates/seo_base.html.j2",
        "templates/_public_nav.html.j2",
        "templates/_public_footer.html.j2",
        "templates/_public_chrome_css.html.j2",
        "templates/_public_chrome_js.html.j2",
        "scripts/build_public_pages.py",
        "config/plans.yml",
    ):
        sha = _commit(repo, rel, f"# {rel}\n", f"feat: {rel}")
        assert GUARD._needs_render(repo, sha, start_head, sha) is False, rel
        assert GUARD._needs_public_render(repo, sha, start_head, sha) is True, rel


def test_the_heavy_lane_keeps_everything_the_split_left_it(tmp_path):
    """The fix must not hand the market renderer's own work to the fast lane."""
    repo = _public_lane_repo(tmp_path)
    start_head = _git(repo, "rev-parse", "HEAD")
    for rel in (
        "templates/macro.html.j2",
        "templates/intl.html.j2",
        "templates/fonts/x.woff2",
        "scripts/build_site.py",
        "scripts/optimize_assets.py",
        "lib/pages.py",
    ):
        sha = _commit(repo, rel, f"# {rel}\n", f"fix: {rel}")
        assert GUARD._needs_render(repo, sha, start_head, sha) is True, rel
        assert GUARD._needs_public_render(repo, sha, start_head, sha) is False, rel


def test_explicit_builder_ownership_drops_uninvoked_builders_from_the_heavy_lane():
    """A builder the workflow never executes must not create a render wait.

    These are real recent false admissions: their merges queued the shared
    self-hosted renderer even though render.yml never invoked the changed module.
    """
    filters = GUARD._render_lane_filters(ROOT)
    for rel in (
        "scripts/build_session_digest.py",
        "scripts/build_live_quotes.py",
        "scripts/build_flow_archive.py",
        "scripts/build_marketing.py",
        "scripts/build_press_properties.py",
    ):
        assert GUARD._render_lanes_for_paths([rel], set(), filters) == set(), rel

    for rel in (
        "scripts/build_site.py",
        "scripts/build_stock_library.py",
        "scripts/build_china_library.py",
    ):
        assert GUARD._render_lanes_for_paths([rel], set(), filters) == {"render"}, rel


def test_the_paired_plain_copy_exemption_outranks_the_public_lane(tmp_path):
    """#3671's ruling survives the split: a paired asset owes NEITHER lane.

    `templates/theme.css` is public-render territory now, but the operator
    already decided this shape needs no lane at all — the site/ twin is committed
    straight to main and the VPS pulls it within 3 minutes, and the only thing
    forfeited is the `?v=` re-stamp. Routing it to the fast lane instead would
    quietly re-impose the wait that ruling removed.
    """
    repo = _public_lane_repo(tmp_path)
    start_head = _git(repo, "rev-parse", "HEAD")
    paired = _commit_files(
        repo,
        {"templates/theme.css": "body{color:#111}\n", "site/theme.css": "body{color:#111}\n"},
        "fix(theme): restyle",
    )
    assert GUARD._required_render_lanes(repo, paired, start_head, paired) == set()

    # One-sided is still one-sided: the live bytes have not moved, so the lane
    # that owns the path is owed a run.
    one_sided = _commit(repo, "templates/theme.css", "body{color:#222}\n", "fix: source only")
    assert GUARD._required_render_lanes(repo, one_sided, start_head, one_sided) == {
        "public-render"
    }


def test_a_mixed_merge_owes_both_lanes(tmp_path):
    """One diff can straddle the split, and each half must still be proved."""
    repo = _public_lane_repo(tmp_path)
    start_head = _git(repo, "rev-parse", "HEAD")
    mixed = _commit_files(
        repo,
        {"templates/plans.html.j2": "{{ x }}\n", "templates/macro.html.j2": "{{ y }}\n"},
        "feat: pricing + macro",
    )
    assert GUARD._required_render_lanes(repo, mixed, start_head, mixed) == {
        "render",
        "public-render",
    }


def test_an_unreadable_workflow_pair_falls_back_to_demanding_the_heavy_render(tmp_path):
    """Fail CLOSED, exactly like the pair list: ignorance is not permission.

    With neither filter parseable the ownership test goes silent and the
    pre-split behaviour returns — every templates/ path demands render.yml.
    """
    assert GUARD._render_lane_filters(tmp_path) == ([], [])
    assert GUARD._public_render_owns("templates/plans.html.j2", ([], [])) is False
    assert GUARD._render_lanes_for_paths(
        ["templates/plans.html.j2"], set(), ([], [])
    ) == {"render"}
    # A path only ONE side vouches for is not a split either.
    assert GUARD._public_render_owns("templates/plans.html.j2", ([], ["templates/*.j2"])) is False


def test_a_push_filter_is_read_in_order_because_the_last_match_wins(tmp_path):
    """GitHub lets a later pattern overturn an earlier one, and so must this.

    "Any negation excludes" happens to agree with render.yml today, but only
    because no positive pattern currently follows a negation of the same path.
    """
    patterns = ["templates/**", "!templates/*.js", "templates/keep.js"]
    assert GUARD._path_filter_includes("templates/keep.js", patterns) is True
    assert GUARD._path_filter_includes("templates/other.js", patterns) is False
    assert GUARD._path_filter_includes("templates/page.html.j2", patterns) is True
    # `*` does not cross a slash; `**` does.
    assert GUARD._path_filter_includes("templates/sub/other.js", ["templates/*.js"]) is False
    assert GUARD._path_filter_includes("templates/sub/other.js", ["templates/**"]) is True
    assert GUARD._path_filter_includes("scripts/research/build_x.py", ["scripts/build_*.py"]) is False


def test_the_push_paths_scanner_reads_the_real_filter_and_fails_closed(tmp_path):
    """Parsed from the workflow, never transcribed — and silent when unsure."""
    heavy, public = GUARD._render_lane_filters(ROOT)
    assert heavy[0] == "templates/**", "order matters; the scanner must preserve it"
    assert "!templates/plans.html.j2" in heavy
    assert "scripts/build_public_pages.py" not in heavy
    assert "config/plans.yml" in public and "templates/plans.html.j2" in public
    assert not any(p.startswith("!") for p in public), "the fast lane claims, it does not negate"

    # Every negated path must be claimed by the other lane — the same no-dead-wire
    # invariant tests/test_public_render_fastlane.py pins from the workflow side.
    for pattern in (p[1:] for p in heavy if p.startswith("!")):
        assert pattern in public, f"render.yml drops {pattern} and nothing picks it up"

    # Unreadable, and a workflow with no push trigger at all, both yield nothing.
    assert GUARD._workflow_push_paths(tmp_path / "absent.yml") == []
    no_push = tmp_path / "no-push.yml"
    no_push.write_text("name: x\non:\n  workflow_dispatch: {}\njobs: {}\n", encoding="utf-8")
    assert GUARD._workflow_push_paths(no_push) == []
    flow = tmp_path / "flow.yml"
    flow.write_text(
        "name: x\non:\n  push:\n    paths: [templates/**]\njobs: {}\n", encoding="utf-8"
    )
    assert GUARD._workflow_push_paths(flow) == [], "a flow list is not guessed at"


def test_needs_public_render_matches_the_real_merge_it_was_written_for():
    """Replayed against this repo's own history, not a fixture.

    7fe17018 = #3897 (templates/plans.html.j2 + site/plans.html) — the merge that
    returned `render_pending` forever while its public-render run was green and
    the page was live.
    """
    if subprocess.run(
        ("git", "cat-file", "-e", "7fe17018^{commit}"), cwd=ROOT, check=False
    ).returncode:
        pytest.skip("7fe17018 not present (shallow clone)")
    assert GUARD._required_render_lanes(ROOT, "7fe17018", "HEAD", "HEAD") == {"public-render"}


# ── The live gate: which /api/health field proves THIS merge live ──────────────
# `commit` is the sha the running macro-api process imported; `checkout` is
# /opt/macro's tree. Reading `commit` for every merge was unsatisfiable for the
# merges that restart nothing — the two tests below pin BOTH halves, because a
# fix that only unblocks them would be an escape hatch, not a gate.


def _deploy_repo(tmp_path: Path) -> Path:
    """A repo carrying THE REAL ``app/deploy/update.sh``.

    Copied, never stubbed: the predicate under test is that script's own restart
    regex, and a hand-written stand-in would pin the test's idea of the deploy
    rather than the VPS's.
    """
    repo = _repo(tmp_path)
    (repo / "app" / "deploy").mkdir(parents=True)
    shutil.copy(ROOT / "app" / "deploy" / "update.sh", repo / "app" / "deploy" / "update.sh")
    _git(repo, "add", "app/deploy/update.sh")
    _git(repo, "commit", "-m", "deploy: install update.sh")
    return repo


def test_a_pull_only_merge_is_proven_live_by_the_checkout_field(tmp_path):
    """A merge that restarts nothing is live the moment the pull loop has it.

    Observed 2026-08-04 on PR #4499 (tests + fixtures only, merge 1995a987): the
    gate read `commit`, which sat 70 commits and ~14 hours behind because nothing
    in that window touched API code, and blocked `live_stale` on a merge that had
    been serving for hours. Nothing the session could do would ever satisfy it —
    restarting production to bless a test-only merge is the wrong action, so the
    session was pinned until an unrelated later PR happened to change app/.
    """
    repo = _deploy_repo(tmp_path)
    base = _git(repo, "rev-parse", "HEAD")
    tests_only = _commit(repo, "tests/test_hk_board_ui.py", "def test_x():\n    pass\n", "test: freeze")

    # Production as it actually was: the API never restarted, the pull loop is current.
    payload = {"status": "ok", "commit": base, "checkout": tests_only}
    assert GUARD._needs_api_restart(repo, tests_only, base, tests_only) is False
    ok, detail = GUARD._live_gate(repo, tests_only, base, tests_only, payload)
    assert ok, detail
    assert "checkout" in detail

    # And the block was real before the field choice, not an artefact of the fixture.
    assert not GUARD._is_ancestor(repo, tests_only, base)


def test_an_api_code_merge_is_not_proven_live_by_the_checkout_field(tmp_path):
    """The other half: `checkout` must never stand in for an API DEPLOY.

    A merge that changes code macro-api imported is on disk the moment the pull
    loop runs and still NOT live — the process keeps serving its old import until
    update.sh restarts it. If `checkout` could satisfy this merge the fix would be
    a general escape hatch rather than a lane selector.
    """
    repo = _deploy_repo(tmp_path)
    base = _git(repo, "rev-parse", "HEAD")
    api_code = _commit(repo, "app/main.py", "PORT = 8000\n", "feat(api): port")

    payload = {"status": "ok", "commit": base, "checkout": api_code}
    assert GUARD._needs_api_restart(repo, api_code, base, api_code) is True
    assert GUARD._live_health_fields(repo, api_code, base, api_code) == ("commit",)
    ok, detail = GUARD._live_gate(repo, api_code, base, api_code, payload)
    assert not ok, "an unrestarted API must not be blessed by its own checkout"
    assert "RESTARTED" in detail

    # The checkout genuinely carries it — the False comes from the field choice,
    # not from the merge being absent everywhere.
    assert GUARD._health_sha(payload, "checkout") == api_code

    # Once the API restarts into it, the same merge clears.
    restarted = {"status": "ok", "commit": api_code, "checkout": api_code}
    assert GUARD._live_gate(repo, api_code, base, api_code, restarted)[0]


def test_one_production_payload_answers_the_two_merges_differently(tmp_path):
    """Both halves against a SINGLE health reading, which is how `_stop` sees it."""
    repo = _deploy_repo(tmp_path)
    base = _git(repo, "rev-parse", "HEAD")
    pull_only = _commit(repo, "docs/NOTES.md", "hello\n", "docs: note")
    api_code = _commit(repo, "app/main.py", "PORT = 8000\n", "feat(api): port")

    payload = {"status": "ok", "commit": base, "checkout": api_code}
    assert GUARD._live_gate(repo, pull_only, base, api_code, payload)[0] is True
    assert GUARD._live_gate(repo, api_code, base, api_code, payload)[0] is False


def test_the_restart_predicate_is_the_deploy_scripts_own_regex(tmp_path):
    """Parsed from update.sh at runtime — never a second copy that drifts.

    That list names ~120 modules and grows most weeks as new engine code enters
    the API's sys.modules; transcribing it here would be wrong within days.
    """
    pattern = GUARD._api_restart_filter(ROOT)
    assert pattern.startswith("^(app/.*\\.py|"), pattern[:60]
    compiled = re.compile(pattern)
    for restarts in (
        "app/main.py",
        "app/requirements.txt",
        "config/site_access.yml",
        "engine/neuralweb/brain_gateway.py",
        "lib/config.py",
    ):
        assert compiled.search(restarts), f"{restarts} restarts macro-api"
    for pulls in (
        "tests/test_hk_board_ui.py",
        "docs/DESIGN_DOCTRINE.md",
        "templates/index.html",
        "site/index.html",
        "engine/hk_board.py",
        "scripts/build_thing.py",
        "app/deploy/update.sh",
    ):
        assert not compiled.search(pulls), f"{pulls} does not restart macro-api"

    # `$API_UNIT_UPDATED` is what distinguishes the macro-api guard from the dozen
    # other `grep -qE` restart blocks in that script (admin, press feeds,
    # biocatalyst, the live timers). Exactly one line may match.
    lines = (ROOT / "app" / "deploy" / "update.sh").read_text(encoding="utf-8").splitlines()
    matched = [n for n, line in enumerate(lines, 1) if GUARD._API_RESTART_GUARD.search(line)]
    assert len(matched) == 1, f"ambiguous macro-api restart guard on lines {matched}"
    assert "systemctl restart macro-api" in "\n".join(lines[matched[0] : matched[0] + 25])


def test_an_unreadable_deploy_script_demands_the_restarted_field(tmp_path):
    """Not knowing whether the API restarts means demanding the field that shows it."""
    repo = _repo(tmp_path)  # no app/deploy/update.sh at all
    base = _git(repo, "rev-parse", "HEAD")
    tests_only = _commit(repo, "tests/test_x.py", "pass\n", "test: x")
    assert GUARD._api_restart_filter(repo) == ""
    assert GUARD._needs_api_restart(repo, tests_only, base, tests_only) is True

    payload = {"status": "ok", "commit": base, "checkout": tests_only}
    assert not GUARD._live_gate(repo, tests_only, base, tests_only, payload)[0]

    # A script whose guard was renamed reads the same way — silence, not permission.
    (tmp_path / "renamed").mkdir()
    renamed = _deploy_repo(tmp_path / "renamed")
    script = renamed / "app" / "deploy" / "update.sh"
    script.write_text(
        script.read_text(encoding="utf-8").replace("API_UNIT_UPDATED", "API_SVC_CHANGED"),
        encoding="utf-8",
    )
    assert GUARD._api_restart_filter(renamed) == ""


@pytest.mark.parametrize(
    "payload",
    [
        {"status": "ok", "commit": "deadbee"},  # older build, no `checkout` key
        {"status": "ok", "commit": "deadbee", "checkout": None},
        {"status": "ok", "commit": "deadbee", "checkout": "not-a-sha"},
        {"status": "ok", "commit": "deadbee", "checkout": "0" * 40},  # unknown here
        {},
        "ok",
    ],
)
def test_an_unusable_health_field_blocks_rather_than_passes(tmp_path, payload):
    """Absent, non-string, sha-less, or unknown to this checkout — all no evidence."""
    repo = _deploy_repo(tmp_path)
    base = _git(repo, "rev-parse", "HEAD")
    tests_only = _commit(repo, "tests/test_x.py", "pass\n", "test: x")
    assert not GUARD._live_gate(repo, tests_only, base, tests_only, payload)[0]


def test_an_unreachable_health_endpoint_shares_the_stale_deploys_escape_class():
    """A network blip and a stale deploy are different faults, both external.

    The fetch failure now reports `live_unreachable` instead of borrowing
    `live_stale`, so the operator reads the real cause. Both must stay EXTERNAL:
    the internal ladder only releases at 10 consecutive blocks, and neither fault
    is anything the session can fix.
    """
    assert {"live_unreachable", "live_stale"} <= GUARD.EXTERNAL_BLOCKERS


def test_the_health_field_is_read_by_name_not_sniffed(tmp_path):
    """`commit` and `checkout` answer different questions in the same payload.

    So the reader takes the field the gate decided on and never the payload's
    first plausible sha — the two live side by side and both look like one.
    """
    payload = {"status": "ok", "commit": "a" * 11, "checkout": "b" * 11}
    assert GUARD._health_sha(payload, "checkout") == "b" * 11
    assert GUARD._health_sha(payload, "commit") == "a" * 11
    assert GUARD._health_sha(payload, "absent") == ""


def test_the_live_gate_replays_the_merge_it_was_written_for():
    """Replayed against this repo's own history and the payload measured that day.

    1995a987 = #4499 (tests/test_hk_board_{ui,rank}.py + two fixtures) — the merge
    that returned `live_stale` forever while it was serving in production. The two
    shas are the real 2026-08-04T07:13Z reading of /api/health.
    """
    if subprocess.run(
        ("git", "cat-file", "-e", "1995a987^{commit}"), cwd=ROOT, check=False
    ).returncode:
        pytest.skip("1995a987 not present (shallow clone)")
    measured = {"status": "ok", "commit": "33b81f82ef4", "checkout": "96ebe5cc903"}
    if subprocess.run(
        ("git", "cat-file", "-e", "96ebe5cc903^{commit}"), cwd=ROOT, check=False
    ).returncode:
        pytest.skip("the measured production shas are not in this checkout")

    assert GUARD._needs_api_restart(ROOT, "1995a987", "HEAD", "HEAD") is False
    ok, detail = GUARD._live_gate(ROOT, "1995a987", "HEAD", "HEAD", measured)
    assert ok, detail

    # And the field it used to read really did not carry the merge — the block was
    # honest about its evidence and wrong about its question.
    assert not GUARD._is_ancestor(ROOT, "1995a987", "33b81f82ef4")


@pytest.fixture(autouse=True)
def _clear_token_cache(monkeypatch):
    """The token is memoised per process; tests must not inherit each other's."""
    monkeypatch.setattr(GUARD, "_TOKEN_CACHE", None, raising=False)
    for key in ("GH_TOKEN", "GITHUB_TOKEN"):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture(autouse=True)
def _clear_index_lock_cache():
    """The worktree gitdir is memoised per root so the second sweep is free.

    One hook process only ever judges one tree; this module reuses a single
    imported guard across every test, so the memo is dropped between them.
    """
    GUARD._INDEX_LOCK_CACHE.clear()
    yield
    GUARD._INDEX_LOCK_CACHE.clear()


@pytest.fixture(autouse=True)
def _clear_render_lane_cache():
    """`_stop` asks the lane question once per lane, so the answer is memoised.

    One hook process only ever sees one merge, but this module reuses a single
    imported guard across every test — so the memo is dropped between them
    rather than left to make a later fixture's answer depend on an earlier one's.
    """
    GUARD._RENDER_LANE_CACHE.clear()
    yield
    GUARD._RENDER_LANE_CACHE.clear()


def _fake_gh(returncode: int, stdout: str, calls: list):
    def runner(args, **kwargs):
        calls.append(tuple(args))
        return subprocess.CompletedProcess(args, returncode, stdout, "")

    return runner


def test_token_falls_back_to_the_gh_cli_when_no_env_var_is_set(monkeypatch):
    """The whole bug: Claude sessions set no token, so the guard ran anonymous at 60/hour."""
    calls: list = []
    monkeypatch.setattr(GUARD.subprocess, "run", _fake_gh(0, "gho_fromcli\n", calls))
    assert GUARD._github_token() == "gho_fromcli"
    assert calls and calls[0][:3] == ("gh", "auth", "token")


def test_token_prefers_the_environment_over_the_cli(monkeypatch):
    calls: list = []
    monkeypatch.setenv("GH_TOKEN", "from-env")
    monkeypatch.setattr(GUARD.subprocess, "run", _fake_gh(0, "from-cli", calls))
    assert GUARD._github_token() == "from-env"
    assert calls == [], "an env token must not spawn the CLI"


def test_token_is_cached_for_the_process(monkeypatch):
    """A Stop evaluation makes four API calls; it must not shell out four times."""
    calls: list = []
    monkeypatch.setattr(GUARD.subprocess, "run", _fake_gh(0, "gho_cached", calls))
    assert GUARD._github_token() == GUARD._github_token() == GUARD._github_token()
    assert len(calls) == 1


@pytest.mark.parametrize(
    "runner",
    [
        lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError("gh not installed")),
        lambda *a, **k: (_ for _ in ()).throw(subprocess.TimeoutExpired("gh", 5)),
        lambda args, **k: subprocess.CompletedProcess(args, 1, "", "not logged in"),
    ],
)
def test_token_degrades_to_anonymous_when_the_cli_cannot_help(monkeypatch, runner):
    """A missing, hung, or logged-out gh must degrade — never break the hook."""
    monkeypatch.setattr(GUARD.subprocess, "run", runner)
    assert GUARD._github_token() == ""


def _capture_requests(monkeypatch) -> list:
    sent: list = []

    def fake_urlopen(request, *args, **kwargs):
        sent.append(request)
        raise urllib.error.URLError("captured")

    monkeypatch.setattr(GUARD.urllib.request, "urlopen", fake_urlopen)
    return sent


def test_the_github_token_is_never_sent_to_the_live_health_host(monkeypatch):
    """_get_json serves both GitHub and production health.

    Authenticating unconditionally would hand a repo-scoped credential to an
    unrelated host on every Stop evaluation — harmless only while no token
    existed, which is exactly the state the CLI fallback ends.
    """
    monkeypatch.setattr(GUARD.subprocess, "run", _fake_gh(0, "gho_secret", []))
    sent = _capture_requests(monkeypatch)

    for url in (f"https://{GUARD.GITHUB_API_HOST}/repos/a/b/pulls", GUARD.LIVE_HEALTH_URL):
        with pytest.raises(Exception):
            GUARD._get_json(url)

    by_host = {request.host: request for request in sent}
    assert by_host[GUARD.GITHUB_API_HOST].get_header("Authorization") == "Bearer gho_secret"
    live_host = urllib.parse.urlsplit(GUARD.LIVE_HEALTH_URL).hostname
    assert by_host[live_host].get_header("Authorization") is None
    assert "gho_secret" not in json.dumps(dict(by_host[live_host].header_items()))


def _http_error(code: int, reason: str, **headers) -> urllib.error.HTTPError:
    message = email.message.Message()
    for key, value in headers.items():
        message[key.replace("_", "-")] = value
    return urllib.error.HTTPError("https://api.github.com/x", code, reason, message, None)


def test_spent_quota_is_reported_as_rate_limited_not_unreachable(monkeypatch):
    """`HTTP Error 403: rate limit exceeded` read as a repo/network fault it never was."""
    # Pin the anonymous case: an unpinned token would consult the real `gh` and
    # make this assertion depend on whether the host happens to be logged in.
    monkeypatch.setattr(GUARD, "_TOKEN_CACHE", "", raising=False)
    error = GUARD._http_failure(
        _http_error(
            403,
            "rate limit exceeded",
            X_RateLimit_Remaining="0",
            X_RateLimit_Limit="60",
            X_RateLimit_Reset="1785010477",
        )
    )
    assert isinstance(error, GUARD.RateLimited)
    assert GUARD._github_block_code(error) == "github_rate_limited"
    assert "quota" in str(error).lower()
    assert "UNAUTHENTICATED" in str(error), "must name the fix when running anonymous"


def test_an_authenticated_quota_message_does_not_tell_you_to_log_in(monkeypatch):
    monkeypatch.setattr(GUARD, "_TOKEN_CACHE", "already-authenticated", raising=False)
    error = GUARD._http_failure(
        _http_error(403, "rate limit exceeded", X_RateLimit_Remaining="0", X_RateLimit_Limit="5000")
    )
    assert isinstance(error, GUARD.RateLimited)
    assert "gh auth login" not in str(error)


@pytest.mark.parametrize(
    "error",
    [
        _http_error(404, "Not Found"),
        _http_error(500, "Server Error"),
        _http_error(403, "Forbidden", X_RateLimit_Remaining="55"),
        urllib.error.HTTPError("u", 403, "rate limit exceeded", None, None),
    ],
)
def test_genuine_failures_stay_github_unreachable(error):
    """Only an actually-spent quota reclassifies; everything else keeps the old code."""
    failure = GUARD._http_failure(error)
    assert not isinstance(failure, GUARD.RateLimited)
    assert GUARD._github_block_code(failure) == "github_unreachable"


def test_rate_limited_has_the_same_escape_class_as_the_blocker_it_split_from():
    assert "github_rate_limited" in GUARD.EXTERNAL_BLOCKERS
    assert "github_unreachable" in GUARD.EXTERNAL_BLOCKERS


class _JsonResponse:
    def __init__(self, payload, headers=None):
        self.payload = payload
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode()


def _rate_headers(*, remaining="4499", etag='"guard-v1"'):
    return {
        "X-RateLimit-Remaining": remaining,
        "X-RateLimit-Limit": "5000",
        "X-RateLimit-Reset": str(int(GUARD.time.time()) + 3600),
        "ETag": etag,
    }


def test_github_gets_are_shared_across_hook_processes(monkeypatch, tmp_path):
    """One fresh response serves every worktree instead of spending one call each."""
    monkeypatch.setenv("MACRO_GITHUB_API_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr(GUARD, "_TOKEN_CACHE", "shared-token", raising=False)
    calls = []

    def fake_urlopen(request, *args, **kwargs):
        calls.append(request)
        if request.full_url.endswith("/rate_limit"):
            return _JsonResponse(
                {
                    "resources": {
                        "core": {
                            "remaining": 4500,
                            "limit": 5000,
                            "reset": int(GUARD.time.time()) + 3600,
                        }
                    }
                }
            )
        return _JsonResponse({"value": 1}, _rate_headers())

    monkeypatch.setattr(GUARD.urllib.request, "urlopen", fake_urlopen)
    url = "https://api.github.com/repos/acme/widgets/pulls?state=closed"
    assert GUARD._get_json(url) == {"value": 1}
    assert GUARD._get_json(url) == {"value": 1}
    target_calls = [call for call in calls if not call.full_url.endswith("/rate_limit")]
    assert len(target_calls) == 1


def test_expired_cache_uses_etag_and_a_304_costs_no_new_payload(monkeypatch, tmp_path):
    """After the short TTL, conditional GET preserves correctness and primary quota."""
    monkeypatch.setenv("MACRO_GITHUB_API_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr(GUARD, "_TOKEN_CACHE", "shared-token", raising=False)
    monkeypatch.setattr(GUARD, "GITHUB_API_CACHE_TTL_SECONDS", 0)
    target_calls = []

    def fake_urlopen(request, *args, **kwargs):
        if request.full_url.endswith("/rate_limit"):
            return _JsonResponse(
                {
                    "resources": {
                        "core": {
                            "remaining": 4500,
                            "limit": 5000,
                            "reset": int(GUARD.time.time()) + 3600,
                        }
                    }
                }
            )
        target_calls.append(request)
        if len(target_calls) == 1:
            return _JsonResponse({"value": 1}, _rate_headers())
        assert request.get_header("If-none-match") == '"guard-v1"'
        message = email.message.Message()
        for key, value in _rate_headers(remaining="4499").items():
            message[key] = value
        raise urllib.error.HTTPError(request.full_url, 304, "Not Modified", message, None)

    monkeypatch.setattr(GUARD.urllib.request, "urlopen", fake_urlopen)
    url = "https://api.github.com/repos/acme/widgets/check-runs"
    assert GUARD._get_json(url) == {"value": 1}
    assert GUARD._get_json(url) == {"value": 1}
    assert len(target_calls) == 2


def test_shared_circuit_breaker_preserves_the_operator_reserve(monkeypatch, tmp_path):
    """Stop hooks pause before they consume the requests needed to repair/merge."""
    monkeypatch.setenv("MACRO_GITHUB_API_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr(GUARD, "_TOKEN_CACHE", "shared-token", raising=False)
    directory = GUARD._github_cache_directory("shared-token")
    GUARD._save_private_json(
        directory / "rate-limit.json",
        {
            "remaining": GUARD.GITHUB_RATE_LIMIT_RESERVE,
            "limit": 5000,
            "reset": int(GUARD.time.time()) + 3600,
            "observed_at": GUARD.time.time(),
            "refreshed_at": GUARD.time.time(),
        },
    )
    monkeypatch.setattr(
        GUARD.urllib.request,
        "urlopen",
        lambda *_a, **_k: pytest.fail("the reserve must block before a network request"),
    )
    with pytest.raises(GUARD.RateLimited, match="safety reserve"):
        GUARD._get_json("https://api.github.com/repos/acme/widgets/pulls")


_CI_RUNS_ENDPOINT = "actions/workflows/ci.yml/runs"
_CI_HEAD_SHA = "a" * 40
_CI_MERGE_SHA = "b" * 40
_CI_HEAD_BRANCH = "claude/wizardly-leavitt"
_CI_MERGED_AT = "2026-07-26T13:10:00Z"
# The observed 2026-07-26 12:50-13:03Z window: concurrent sibling pull requests.
_SIB_A = ("c" * 40, "claude/vector-dsr")
_SIB_B = ("d" * 40, "claude/w2-support")
_SIB_C = ("e" * 40, "claude/gracious-moser")
_PRE_MERGE = "2026-07-26T13:03:00Z"
_ALSO_PRE_MERGE = "2026-07-26T12:51:00Z"
_OLDEST_PRE_MERGE = "2026-07-26T12:50:00Z"
_POST_MERGE = "2026-07-26T13:20:00Z"
# Check-suite ids pair a sibling's workflow run with the check runs it published.
# The A value is the real suite observed on the 2026-07-26 replay.
_SUITE_A = 81_847_430_333
_SUITE_B = 81_847_430_444
_SUITE_C = 81_847_430_555


def _check_run(
    name: str,
    conclusion,
    started_at: str = _PRE_MERGE,
    status: str = "completed",
    suite=None,
):
    return {
        "name": name,
        "status": status,
        "conclusion": conclusion,
        "started_at": started_at,
        "check_suite": {"id": suite},
    }


def _head_page(*runs, total_count=None) -> dict:
    """One page of the merged head's check-run listing."""
    return {
        "total_count": len(runs) if total_count is None else total_count,
        "check_runs": list(runs),
    }


def _pr_ci_run(
    run_id: int, sibling: tuple[str, str], started: str, conclusion="failure", suite=None
) -> dict:
    sha, branch = sibling
    return {
        "id": run_id,
        "head_sha": sha,
        "head_branch": branch,
        "event": "pull_request",
        "status": "completed",
        "conclusion": conclusion,
        "run_started_at": started,
        "created_at": started,
        "check_suite_id": suite,
    }


def _main_ci_run(run_id: int, head_sha: str, conclusion="success", status="completed") -> dict:
    return {
        "id": run_id,
        "head_sha": head_sha,
        "head_branch": "main",
        "event": "workflow_dispatch",
        "status": status,
        "conclusion": conclusion,
        "run_started_at": "2026-07-26T13:40:00Z",
        "created_at": "2026-07-26T13:40:00Z",
    }


def _fake_ci_api(monkeypatch, *, head_pages, main_runs=(), pr_runs=(), sibling_runs=None) -> list:
    """Serve every `_check_ci` endpoint by URL and record what was fetched.

    Both commit listings share a path shape, so the head's own listing is
    identified by the `page=` parameter only it carries. An unrouted URL asserts
    rather than returning a plausible empty payload — a silently-served endpoint
    would make the cheapness claims below unfalsifiable.
    """
    urls: list = []
    siblings = dict(sibling_runs or {})

    def fake_get_json(url: str):
        urls.append(url)
        parts = urllib.parse.urlsplit(url)
        params = urllib.parse.parse_qs(parts.query)
        if "/check-runs" in parts.path:
            if "page" in params:
                return head_pages[int(params["page"][0])]
            sha = parts.path.split("/commits/", 1)[1].split("/")[0]
            return {"check_runs": list(siblings.get(sha, ()))}
        assert _CI_RUNS_ENDPOINT in parts.path, f"unexpected endpoint: {url}"
        if params.get("branch") == ["main"]:
            return {"workflow_runs": list(main_runs)}
        assert params.get("event") == ["pull_request"], f"unrouted ci.yml listing: {url}"
        return {"workflow_runs": list(pr_runs)}

    monkeypatch.setattr(GUARD, "_get_json", fake_get_json)
    return urls


def _ci_verdict(
    repo: Path,
    *,
    head_sha: str = _CI_HEAD_SHA,
    merge_sha: str = _CI_MERGE_SHA,
    merged_at: str = _CI_MERGED_AT,
    head_branch: str = _CI_HEAD_BRANCH,
):
    return GUARD._check_ci(repo, "acme", "widgets", head_sha, merge_sha, merged_at, head_branch)


def _param(url: str, key: str):
    """One query parameter, parsed. Substring matching would read `page` out of `per_page`."""
    return urllib.parse.parse_qs(urllib.parse.urlsplit(url).query).get(key, [None])[0]


def _probe_urls(urls: list) -> list:
    """The per-sibling-head check-run probes: commit listings that are not the head's."""
    return [url for url in urls if "/check-runs" in url and _param(url, "page") is None]


def test_check_ci_still_blocks_on_a_red_check(monkeypatch, tmp_path):
    """The authentication work must not soften the gate it exists to evaluate."""
    repo = _repo(tmp_path)
    _fake_ci_api(
        monkeypatch,
        head_pages={1: _head_page(_check_run("ci", "failure"), _check_run("lint", "success"))},
    )
    ok, reason = _ci_verdict(repo)
    assert ok is False
    assert reason.startswith("Failing"), "_stop keys the ci_failed code off this prefix"
    assert "ci (failure)" in reason


def test_check_ci_passes_only_when_every_real_check_is_green(monkeypatch, tmp_path):
    repo = _repo(tmp_path)
    urls = _fake_ci_api(
        monkeypatch,
        head_pages={
            1: _head_page(
                _check_run("ci", "success"),
                _check_run("Workers Builds: macro", "failure"),
            )
        },
    )
    assert _ci_verdict(repo) == (True, "")
    assert len(urls) == 1, "a green head is judged without gathering any evidence"

    urls = _fake_ci_api(
        monkeypatch,
        head_pages={1: _head_page(_check_run("ci", None, status="in_progress"))},
    )
    ok, reason = _ci_verdict(repo)
    assert ok is False and reason.startswith("CI still running")
    assert len(urls) == 1

    urls = _fake_ci_api(monkeypatch, head_pages={1: _head_page()})
    assert _ci_verdict(repo)[0] is False
    assert len(urls) == 1


def test_check_ci_does_not_own_the_ci_authority_inactive_base_context(monkeypatch, tmp_path):
    """The merged-head gate filtered LESS than the two loops it claimed parity with.

    `.github/workflows/ci-authority.yml` publishes two complementary exact-head
    contexts and states that "each PR run FAILS the inactive context so an edited
    retarget cannot reuse a success earned against another base". Sessions here only
    track pull requests targeting main, so `ci-authority/codex/merge-queue-pilot` is
    red on EVERY one of them, by design — measured on sibling PR #5767, whose single
    failing check was this context and which merged clean.

    `_red_checks` and `_split_head_runs` had both always skipped it, and so does the
    sweeper; this loop called `_is_spurious_check` instead, under a comment claiming
    "ONE definition of 'not a red', shared with `_split_head_runs` above and with the
    sweeper's own copy". So it alone blocked sessions whose work had merged GREEN.
    Invisible until #5771 repaired the semantic proof path ahead of it, which had
    been raising first and producing a different refusal.
    """
    repo = _repo(tmp_path)
    urls = _fake_ci_api(
        monkeypatch,
        head_pages={
            1: _head_page(
                _check_run("ci", "success"),
                _check_run("ci-authority/main", "success"),
                _check_run(GUARD.CI_AUTHORITY_INACTIVE_CONTEXT, "failure"),
            )
        },
    )
    assert _ci_verdict(repo) == (True, "")
    assert len(urls) == 1, (
        "the inactive base context must not even be treated as a red worth "
        "gathering base-side evidence about"
    )


def test_check_ci_still_owns_the_ACTIVE_ci_authority_context(monkeypatch, tmp_path):
    """The fix adds exactly one name. `ci-authority/main` stays binding.

    The failure mode of a non-binding-check list is waving a genuine red through as
    noise, so the sibling context — the one that actually adjudicates this PR's base
    — must still block, on the same head shape as the test above.
    """
    repo = _repo(tmp_path)
    _fake_ci_api(
        monkeypatch,
        head_pages={
            1: _head_page(
                _check_run("ci", "success"),
                _check_run("ci-authority/main", "failure"),
                _check_run(GUARD.CI_AUTHORITY_INACTIVE_CONTEXT, "failure"),
            )
        },
    )
    ok, reason = _ci_verdict(repo)
    assert ok is False
    assert "ci-authority/main (failure)" in reason
    assert GUARD.CI_AUTHORITY_INACTIVE_CONTEXT not in reason, (
        "the inactive context must not be named as a red the session owns"
    )


def test_every_gate_shares_one_non_binding_definition():
    """Parity asserted BEHAVIOURALLY, because a comment claiming it is what failed.

    `_red_pairs`, `_split_head_runs` and the merged-head loop must agree on every
    name. Driving all three with the same runs is the only form of this assertion
    that a fourth loop filtering less could not quietly pass.
    """
    runs = [
        {"name": "ci", "status": "completed", "conclusion": "success"},
        {"name": "Workers Builds: macro", "status": "completed", "conclusion": "failure"},
        {"name": GUARD.CI_AUTHORITY_INACTIVE_CONTEXT, "status": "completed",
         "conclusion": "failure"},
    ]
    assert GUARD._red_pairs(runs) == []
    red, pending, passed = GUARD._split_head_runs(runs)
    assert red == [] and pending == [] and passed == ["ci"]
    for name in ("Workers Builds: macro", GUARD.CI_AUTHORITY_INACTIVE_CONTEXT):
        assert GUARD._is_non_binding_check(name) is True
    # …and it is still narrow: nothing else is waved through.
    for name in ("ci", "ci-authority/main", "ci-gate", "ci-pack-3", "fence-pack"):
        assert GUARD._is_non_binding_check(name) is False
        assert GUARD._is_spurious_check(name) is False


def test_check_ci_green_path_fetches_only_the_head_listing(monkeypatch, tmp_path):
    """The common case must stay a single API call — evidence is only gathered for a red."""
    repo = _repo(tmp_path)
    urls = _fake_ci_api(
        monkeypatch,
        head_pages={
            1: _head_page(
                _check_run("ci-pack-1", "success"),
                _check_run("nav-gap", "success"),
                _check_run("legacy-member", "skipped"),
            )
        },
    )
    # The lazy origin/main refresh lives inside the evidence phase, so a green head
    # must not spawn git either — the gate stays as cheap as it was.
    monkeypatch.setattr(
        GUARD, "_run", lambda *args, **_kwargs: pytest.fail(f"green path shelled out: {args[1:]}")
    )
    assert _ci_verdict(repo) == (True, "")
    assert len(urls) == 1 and "/check-runs" in urls[0] and _param(urls[0], "page") == "1"


def test_check_ci_paginates_past_the_first_hundred_check_runs(monkeypatch, tmp_path):
    """THE fail-open regression: one `per_page=100` call hid the tail of a 101-run head.

    PR #3629's merged head carries 101 check runs. A red sitting at position 101
    was never fetched, so the gate passed work it had not looked at — the one
    direction this guard may never fail.
    """
    repo = _repo(tmp_path)
    urls = _fake_ci_api(
        monkeypatch,
        head_pages={
            1: {
                "total_count": 101,
                "check_runs": [_check_run(f"pure-{index}", "success") for index in range(100)],
            },
            2: {"total_count": 101, "check_runs": [_check_run("ci-pack-1", "failure")]},
        },
    )
    ok, reason = _ci_verdict(repo)
    assert ok is False and reason.startswith("Failing")
    assert "ci-pack-1 (failure)" in reason
    pages = [_param(url, "page") for url in urls if "/check-runs" in url]
    assert pages == ["1", "2"], "both pages, each exactly once"


def test_a_base_side_red_confirmed_on_two_independent_heads_is_excluded_and_named(
    monkeypatch, tmp_path
):
    """THE defect. A red the PR inherited from the base can never clear itself.

    2026-07-26: the chronicle gate-1 staleness window (heal owned by the still-open
    PR #3634) pinned merged PR #3629's `ci-pack-1`. `gh run rerun` replays the
    frozen `refs/pull/N/merge` tree, and a follow-up PR is impossible once the fix
    is on main, so the session was pushed into `SHIP LOOP BLOCKED:` over work that
    was green. Two independent concurrent heads failing the SAME name before the
    merge is the evidence that the cause was never ours — and the pass must name
    the checks it ignored and the heads it read.
    """
    repo = _repo(tmp_path)
    sib_a_sha, sib_a_branch = _SIB_A
    sib_b_sha, sib_b_branch = _SIB_B
    sib_c_sha, sib_c_branch = _SIB_C
    # Our own red started at _PRE_MERGE, so proximity ranks A, then B, then C.
    urls = _fake_ci_api(
        monkeypatch,
        head_pages={
            1: _head_page(
                _check_run("ci-pack-1", "failure", _PRE_MERGE),
                _check_run("nav-gap", "success"),
            )
        },
        pr_runs=(
            _pr_ci_run(30_200_000_301, _SIB_A, _PRE_MERGE, suite=_SUITE_A),
            _pr_ci_run(30_200_000_302, _SIB_B, _ALSO_PRE_MERGE, suite=_SUITE_B),
            _pr_ci_run(30_200_000_303, _SIB_C, _OLDEST_PRE_MERGE, suite=_SUITE_C),
        ),
        sibling_runs={
            sib_a_sha: (_check_run("ci-pack-1", "failure", _PRE_MERGE, suite=_SUITE_A),),
            sib_b_sha: (_check_run("ci-pack-1", "failure", _ALSO_PRE_MERGE, suite=_SUITE_B),),
            sib_c_sha: (_check_run("ci-pack-1", "failure", _OLDEST_PRE_MERGE, suite=_SUITE_C),),
        },
    )
    ok, note = _ci_verdict(repo)
    assert ok is True
    assert "Ignored base-side CI" in note and "ci-pack-1" in note
    assert sib_a_sha[:7] in note and sib_b_sha[:7] in note
    assert sib_a_branch in note and sib_b_branch in note
    assert not note.startswith("Failing"), "_stop must not read a pass note as a block"
    assert not note.startswith("CI still")
    # The bar is two, so the third (furthest) candidate is never probed.
    assert len(_probe_urls(urls)) == 2 and sib_c_branch not in note


def test_probes_run_in_proximity_order_to_our_own_red(monkeypatch, tmp_path):
    """THE live-replay failure: newest-first missed a true base-side red entirely.

    2026-07-26, merged_at 13:24:17Z, our `ci-pack-1` red started 12:06:25Z. A
    13:14-13:22Z burst of other sessions' pushes filled the newest candidate slots
    and every one of them had `ci-pack-1` GREEN — their runs failed on other checks
    — so the guard returned a plain "Failing CI: ci-pack-1" while six of seven heads
    in the 11:59-12:17Z band around our own red carried the same red. The real
    confirmations sat at listing positions ~9 and ~12, out of reach of any modest
    cap. This class of defect is a temporal STRIPE in the base vintage, so the
    probative siblings are the ones that ran nearest OUR failing check, and
    proximity ordering is also immune to a newer burst crowding the listing.
    """
    repo = _repo(tmp_path)
    merged_at = "2026-07-26T13:24:17Z"
    # Nine newer candidates: more than the probe cap, exactly as in the field.
    burst = tuple(
        (
            str(index) * 40,
            f"claude/burst-{index}",
            f"2026-07-26T13:{22 - index}:00Z",
            810 + index,
        )
        for index in range(1, 10)
    )
    near = (
        ("f" * 40, "claude/outbox", "2026-07-26T12:07:08Z", 826),
        ("0" * 40, "claude/cool-allen", "2026-07-26T12:04:51Z", 827),
    )
    sibling_runs = {
        sha: (_check_run("ci-pack-1", "success", started, suite=suite),)
        for sha, _branch, started, suite in burst
    }
    sibling_runs.update(
        {
            sha: (_check_run("ci-pack-1", "failure", started, suite=suite),)
            for sha, _branch, started, suite in near
        }
    )
    urls = _fake_ci_api(
        monkeypatch,
        head_pages={1: _head_page(_check_run("ci-pack-1", "failure", "2026-07-26T12:06:25Z"))},
        pr_runs=tuple(
            _pr_ci_run(900 + index, (sha, branch), started, suite=suite)
            for index, (sha, branch, started, suite) in enumerate(burst + near)
        ),
        sibling_runs=sibling_runs,
    )
    ok, note = _ci_verdict(repo, merged_at=merged_at)
    assert ok is True and "Ignored base-side CI" in note
    probes = _probe_urls(urls)
    assert len(probes) == 2, "the two nearest heads meet the bar; the burst is never probed"
    assert all(any(sha in url for sha, *_rest in near) for url in probes)
    assert all(branch in note for _sha, branch, *_rest in near)


def test_a_branchs_older_red_head_survives_its_newer_green_head(monkeypatch, tmp_path):
    """Per-branch keep-newest discarded valid evidence on the live replay.

    w2-support-page's newer 13:22 head had dodged the stripe (`ci-pack-1` green),
    and per-branch dedupe let that newer head silently delete the branch's own
    12:51 red. An older head's red is still proof the base was sick without our
    content, so candidates are keyed by HEAD SHA and both heads stay in play.
    """
    repo = _repo(tmp_path)
    dodging = ("8" * 40, "claude/w2-support-page")
    striped = ("9" * 40, "claude/w2-support-page")
    other = ("7" * 40, "claude/w1-china")
    _fake_ci_api(
        monkeypatch,
        head_pages={1: _head_page(_check_run("ci-pack-1", "failure", "2026-07-26T12:55:00Z"))},
        pr_runs=(
            _pr_ci_run(931, dodging, "2026-07-26T13:08:00Z", suite=931),
            _pr_ci_run(932, striped, _ALSO_PRE_MERGE, suite=932),
            _pr_ci_run(933, other, "2026-07-26T12:57:00Z", suite=933),
        ),
        sibling_runs={
            dodging[0]: (_check_run("ci-pack-1", "success", "2026-07-26T13:08:00Z", suite=931),),
            striped[0]: (_check_run("ci-pack-1", "failure", _ALSO_PRE_MERGE, suite=932),),
            other[0]: (_check_run("ci-pack-1", "failure", "2026-07-26T12:57:00Z", suite=933),),
        },
    )
    ok, note = _ci_verdict(repo)
    assert ok is True and "Ignored base-side CI" in note
    assert striped[0][:7] in note and other[0][:7] in note
    assert dodging[0][:7] not in note, "the green head is not the evidence"


def test_two_heads_of_one_branch_confirm_only_once(monkeypatch, tmp_path):
    """Sha-dedupe widens the candidate set; the BAR still counts distinct BRANCHES.

    Keeping every head is what stops a newer dodging head from erasing an older
    head's red — but one branch is one independent observation however many of its
    heads carry the stripe.
    """
    repo = _repo(tmp_path)
    solo_new, solo_old = ("8" * 40, "claude/solo"), ("9" * 40, "claude/solo")
    _fake_ci_api(
        monkeypatch,
        head_pages={1: _head_page(_check_run("ci-pack-1", "failure", _PRE_MERGE))},
        pr_runs=(
            _pr_ci_run(941, solo_new, "2026-07-26T13:02:00Z", suite=941),
            _pr_ci_run(942, solo_old, _ALSO_PRE_MERGE, suite=942),
        ),
        sibling_runs={
            solo_new[0]: (_check_run("ci-pack-1", "failure", "2026-07-26T13:02:00Z", suite=941),),
            solo_old[0]: (_check_run("ci-pack-1", "failure", _ALSO_PRE_MERGE, suite=942),),
        },
    )
    ok, reason = _ci_verdict(repo)
    assert ok is False and reason.startswith("Failing")


def test_a_lone_sibling_confirmation_stays_ci_failed(monkeypatch, tmp_path):
    """One sibling sharing a pack name is coincidence, not a shared cause.

    `ci-pack-1` fronts many jobs and member granularity does not exist (pack
    members are `if: false` definitions that publish `skipped`), so a single
    same-named red proves nothing. Two distinct branches is the bar.
    """
    repo = _repo(tmp_path)
    sib_a_sha, _ = _SIB_A
    _fake_ci_api(
        monkeypatch,
        head_pages={1: _head_page(_check_run("ci-pack-1", "failure"))},
        pr_runs=(_pr_ci_run(30_200_000_301, _SIB_A, _PRE_MERGE, suite=_SUITE_A),),
        sibling_runs={sib_a_sha: (_check_run("ci-pack-1", "failure", _PRE_MERGE, suite=_SUITE_A),)},
    )
    ok, reason = _ci_verdict(repo)
    assert ok is False and reason.startswith("Failing")
    assert "ci-pack-1 (failure)" in reason


def test_sibling_reds_after_the_merge_cannot_classify(monkeypatch, tmp_path):
    """Evidence has to come from a PRE-MERGE run — but the CHECK's clock proves nothing.

    An open pull request's merge ref recomputes against the moving base, so a
    sibling run created after our merge landed may have OUR content as its cause,
    and its red is not evidence. What does NOT follow is judging the second hop by
    time: `github.sha` is frozen at event time, so a check run's `started_at`
    measures queue latency. Under runner contention a pre-merge run's `ci-pack-1`
    job started at 13:25:04, after a 13:24:17 merge, while still testing the
    pre-merge tree. The check suite is the real linkage — a rerun replaces check
    runs inside the same suite, a fresh post-merge event mints a new one.
    """
    repo = _repo(tmp_path)
    sib_a_sha, _ = _SIB_A
    sib_b_sha, _ = _SIB_B

    # Hop 1: the sibling RUNS are post-merge, so nothing about them is evidence.
    _fake_ci_api(
        monkeypatch,
        head_pages={1: _head_page(_check_run("ci-pack-1", "failure"))},
        pr_runs=(
            _pr_ci_run(30_200_000_301, _SIB_A, _POST_MERGE, suite=_SUITE_A),
            _pr_ci_run(30_200_000_302, _SIB_B, _POST_MERGE, suite=_SUITE_B),
        ),
        sibling_runs={
            sib_a_sha: (_check_run("ci-pack-1", "failure", _PRE_MERGE, suite=_SUITE_A),),
            sib_b_sha: (_check_run("ci-pack-1", "failure", _ALSO_PRE_MERGE, suite=_SUITE_B),),
        },
    )
    assert _ci_verdict(repo)[0] is False

    in_window_runs = (
        _pr_ci_run(30_200_000_301, _SIB_A, _PRE_MERGE, suite=_SUITE_A),
        _pr_ci_run(30_200_000_302, _SIB_B, _ALSO_PRE_MERGE, suite=_SUITE_B),
    )

    # Hop 2, negative: the reds belong to a DIFFERENT suite on the same heads — a
    # fresh post-merge pull_request event, which our content could have caused.
    _fake_ci_api(
        monkeypatch,
        head_pages={1: _head_page(_check_run("ci-pack-1", "failure"))},
        pr_runs=in_window_runs,
        sibling_runs={
            sib_a_sha: (_check_run("ci-pack-1", "failure", _POST_MERGE, suite=_SUITE_A + 1),),
            sib_b_sha: (_check_run("ci-pack-1", "failure", _POST_MERGE, suite=_SUITE_B + 1),),
        },
    )
    ok, reason = _ci_verdict(repo)
    assert ok is False and reason.startswith("Failing")

    # Hop 2, fail-closed: no suite id at all on the check runs.
    _fake_ci_api(
        monkeypatch,
        head_pages={1: _head_page(_check_run("ci-pack-1", "failure"))},
        pr_runs=in_window_runs,
        sibling_runs={
            sib_a_sha: (_check_run("ci-pack-1", "failure", _PRE_MERGE),),
            sib_b_sha: (_check_run("ci-pack-1", "failure", _ALSO_PRE_MERGE),),
        },
    )
    assert _ci_verdict(repo)[0] is False

    # Hop 2, positive twin: the SAME late-started reds confirm once their suite
    # matches the pre-merge run — the timestamp was never the evidence.
    _fake_ci_api(
        monkeypatch,
        head_pages={1: _head_page(_check_run("ci-pack-1", "failure"))},
        pr_runs=in_window_runs,
        sibling_runs={
            sib_a_sha: (_check_run("ci-pack-1", "failure", _POST_MERGE, suite=_SUITE_A),),
            sib_b_sha: (_check_run("ci-pack-1", "failure", _POST_MERGE, suite=_SUITE_B),),
        },
    )
    ok, note = _ci_verdict(repo)
    assert ok is True and "Ignored base-side CI" in note


def test_own_branch_runs_are_not_independent_evidence(monkeypatch, tmp_path):
    """Independence is structural: a distinct branch, on a sha that is not ours.

    Our own pull request's earlier attempts carry the same red for the same
    reason, so counting them would let a PR confirm its own innocence.
    """
    repo = _repo(tmp_path)
    ours_again = ("f" * 40, _CI_HEAD_BRANCH)
    same_sha_other_branch = (_CI_HEAD_SHA, "claude/mirror-of-ours")
    urls = _fake_ci_api(
        monkeypatch,
        head_pages={1: _head_page(_check_run("ci-pack-1", "failure"))},
        pr_runs=(
            _pr_ci_run(30_200_000_301, ours_again, _PRE_MERGE),
            _pr_ci_run(30_200_000_302, same_sha_other_branch, _ALSO_PRE_MERGE),
        ),
    )
    ok, reason = _ci_verdict(repo)
    assert ok is False and reason.startswith("Failing")
    assert _probe_urls(urls) == [], "neither run should have been worth probing"


def test_sibling_run_failures_with_a_green_pack_are_not_evidence(monkeypatch, tmp_path):
    """The observed window's actual shape: most sibling run-failures are the sibling's own bug.

    2026-07-26 12:50-13:03Z: gracious-moser, brain-symmetric and brain-consistency
    all concluded `failure` at the RUN level while their `ci-pack-1` check was
    GREEN. Only vector-dsr 13:03 and w2-support 12:51 carried a red `ci-pack-1`.
    So a run conclusion is never evidence — only a per-head probe of the same NAME.
    """
    repo = _repo(tmp_path)
    sib_a_sha, _ = _SIB_A
    sib_b_sha, _ = _SIB_B
    sib_c_sha, _ = _SIB_C
    urls = _fake_ci_api(
        monkeypatch,
        head_pages={1: _head_page(_check_run("ci-pack-1", "failure"))},
        pr_runs=(
            _pr_ci_run(30_200_000_301, _SIB_A, _PRE_MERGE, suite=_SUITE_A),
            _pr_ci_run(30_200_000_302, _SIB_B, _ALSO_PRE_MERGE, suite=_SUITE_B),
            _pr_ci_run(30_200_000_303, _SIB_C, _OLDEST_PRE_MERGE, suite=_SUITE_C),
        ),
        sibling_runs={
            sib_a_sha: (_check_run("ci-pack-1", "success", _PRE_MERGE, suite=_SUITE_A),),
            sib_b_sha: (_check_run("ci-pack-1", "success", _ALSO_PRE_MERGE, suite=_SUITE_B),),
            sib_c_sha: (_check_run("ci-pack-1", "success", _OLDEST_PRE_MERGE, suite=_SUITE_C),),
        },
    )
    ok, reason = _ci_verdict(repo)
    assert ok is False and reason.startswith("Failing")
    assert len(_probe_urls(urls)) == 3, "each candidate head is probed by name, once"


def test_a_dispatched_green_ci_run_on_a_main_descendant_clears_every_red(monkeypatch, tmp_path):
    """The operator's unblock lever, and the only evidence strong enough for any conclusion.

    ci.yml triggers on `pull_request` + `workflow_dispatch` only, so main commits
    carry no ci.yml runs at all — dispatching one on main once the base-side cause
    is healed is how a pinned session clears. A descendant's tree contains the
    merge, so a full green run there proves the merged content passes and every bad
    conclusion goes with it, `cancelled` included.
    """
    repo, _parent, merge, descendant = _merge_train(tmp_path)
    urls = _fake_ci_api(
        monkeypatch,
        head_pages={
            1: _head_page(
                _check_run("ci-pack-1", "failure"),
                _check_run("tier-gate", "cancelled"),
            )
        },
        main_runs=(_main_ci_run(30_200_000_401, descendant),),
    )
    ok, note = _ci_verdict(repo, merge_sha=merge)
    assert ok is True
    assert "30200000401" in note and descendant[:12] in note
    assert "tier-gate (cancelled)" in note, "content-green clears conclusions E2 never could"
    assert not note.startswith("Failing")
    assert not any(_param(url, "event") == "pull_request" for url in urls), "E1 short-circuits E2"


def test_a_green_main_run_on_a_non_descendant_cannot_clear(monkeypatch, tmp_path):
    """Real git decides ancestry: a green run on the merge's PARENT rendered a tree without it."""
    repo, parent, merge, _descendant = _merge_train(tmp_path)
    _fake_ci_api(
        monkeypatch,
        head_pages={1: _head_page(_check_run("ci-pack-1", "failure"))},
        main_runs=(_main_ci_run(30_200_000_401, parent),),
    )
    ok, reason = _ci_verdict(repo, merge_sha=merge)
    assert ok is False and reason.startswith("Failing")
    assert "ci-pack-1 (failure)" in reason


def test_partial_exclusion_still_blocks_and_names_both_sides(monkeypatch, tmp_path):
    """Exclusion is per check name. One inherited red does not launder our own."""
    repo = _repo(tmp_path)
    sib_a_sha, _ = _SIB_A
    sib_b_sha, _ = _SIB_B
    _fake_ci_api(
        monkeypatch,
        head_pages={
            1: _head_page(_check_run("ci-pack-1", "failure"), _check_run("own-check", "failure"))
        },
        pr_runs=(
            _pr_ci_run(30_200_000_301, _SIB_A, _PRE_MERGE, suite=_SUITE_A),
            _pr_ci_run(30_200_000_302, _SIB_B, _ALSO_PRE_MERGE, suite=_SUITE_B),
        ),
        sibling_runs={
            sib_a_sha: (
                _check_run("ci-pack-1", "failure", _PRE_MERGE, suite=_SUITE_A),
                _check_run("own-check", "success", _PRE_MERGE, suite=_SUITE_A),
            ),
            sib_b_sha: (
                _check_run("ci-pack-1", "failure", _ALSO_PRE_MERGE, suite=_SUITE_B),
                _check_run("own-check", "success", _ALSO_PRE_MERGE, suite=_SUITE_B),
            ),
        },
    )
    ok, message = _ci_verdict(repo)
    assert ok is False and message.startswith("Failing CI:")
    assert "own-check (failure)" in message
    assert "Ignored as base-side" in message and "ci-pack-1" in message
    assert "ci-pack-1 (failure). These run against" not in message, (
        "the excluded name must not be listed as a red we own"
    )


def test_non_failure_head_conclusions_are_not_base_side_excludable(monkeypatch, tmp_path):
    """A `cancelled` check on a merged head is genuinely rerunnable, so it stays ours.

    Rerunning replays the frozen merge ref, which is fatal for a base-side FAILURE
    but perfectly capable of greening a cancellation. Only content-green evidence
    clears those, never a sibling argument.
    """
    repo = _repo(tmp_path)
    sib_a_sha, _ = _SIB_A
    sib_b_sha, _ = _SIB_B
    urls = _fake_ci_api(
        monkeypatch,
        head_pages={1: _head_page(_check_run("tier-gate", "cancelled"))},
        pr_runs=(
            _pr_ci_run(30_200_000_301, _SIB_A, _PRE_MERGE, suite=_SUITE_A),
            _pr_ci_run(30_200_000_302, _SIB_B, _ALSO_PRE_MERGE, suite=_SUITE_B),
        ),
        sibling_runs={
            sib_a_sha: (_check_run("tier-gate", "failure", _PRE_MERGE, suite=_SUITE_A),),
            sib_b_sha: (_check_run("tier-gate", "failure", _ALSO_PRE_MERGE, suite=_SUITE_B),),
        },
    )
    ok, reason = _ci_verdict(repo)
    assert ok is False and reason.startswith("Failing")
    assert "tier-gate (cancelled)" in reason
    assert not any(_param(url, "event") == "pull_request" for url in urls), (
        "with nothing eligible, the sibling listing is not even worth fetching"
    )
    assert _probe_urls(urls) == []


def test_evidence_api_errors_fail_closed_to_the_original_red(monkeypatch, tmp_path):
    """A broken evidence phase must keep the red, never reclassify or swallow it."""
    repo = _repo(tmp_path)

    def fake_get_json(url: str):
        if _CI_RUNS_ENDPOINT in url:
            raise RuntimeError("workflow listing exploded")
        return _head_page(_check_run("ci-pack-1", "failure"))

    monkeypatch.setattr(GUARD, "_get_json", fake_get_json)
    ok, message = _ci_verdict(repo)
    assert ok is False and message.startswith("Failing")
    assert "ci-pack-1 (failure)" in message
    assert "evidence unavailable" in message.lower()
    assert "Ignored" not in message


_RENDER_ENDPOINT = "actions/workflows/render.yml/runs"
_MERGED_AT = "2026-07-26T06:11:36Z"


def _merge_train(tmp_path: Path) -> tuple[Path, str, str, str]:
    """A real repo shaped like a merge train: parent -> merge -> a later merge.

    Ancestry is decided by git itself, so these are genuine 40-char shas rather
    than strings that only look related.
    """
    repo = _repo(tmp_path)
    parent = _git(repo, "rev-parse", "HEAD")
    merge = _commit(repo, "templates/mine.html", "<p>mine</p>\n", "feat: my merge")
    descendant = _commit(repo, "templates/later.html", "<p>later</p>\n", "feat: a later merge")
    return repo, parent, merge, descendant


def _render_run(run_id: int, head_sha: str, event: str, created_at: str, status: str, conclusion=None):
    return {
        "id": run_id,
        "head_sha": head_sha,
        "head_branch": "main",
        "event": event,
        "created_at": created_at,
        "status": status,
        "conclusion": conclusion,
    }


def _fake_render_api(monkeypatch, *, exact: list, branch: list, workflow: str = "render.yml") -> list:
    """Serve the two render listings by query string and record every URL fetched."""
    urls: list = []
    endpoint = f"actions/workflows/{workflow}/runs"

    def fake_get_json(url: str):
        urls.append(url)
        assert endpoint in url, f"unexpected endpoint: {url}"
        if "head_sha=" in url:
            return {"workflow_runs": exact}
        assert "branch=main" in url, f"neither an exact-sha nor a main listing: {url}"
        return {"workflow_runs": branch}

    monkeypatch.setattr(GUARD, "_get_json", fake_get_json)
    return urls


def test_render_status_accepts_the_exact_sha_success_in_one_call(monkeypatch, tmp_path):
    """The common case must stay a single API call — the descendant scan is a fallback."""
    repo, _parent, merge, _descendant = _merge_train(tmp_path)
    urls = _fake_render_api(
        monkeypatch,
        exact=[_render_run(1, merge, "push", "2026-07-26T06:11:38Z", "completed", "success")],
        branch=[_render_run(2, merge, "push", "2026-07-26T06:11:38Z", "completed", "failure")],
    )
    assert GUARD._render_status(repo, "acme", "widgets", merge, _MERGED_AT) == ("success", "")
    assert len(urls) == 1 and "head_sha=" in urls[0], "the branch listing must not be fetched"


def test_a_superseded_train_member_is_covered_by_a_later_descendant_render(monkeypatch, tmp_path):
    """THE regression. render.yml coalesces, so exact-sha-only was unsatisfiable.

    2026-07-26 merge train: PR #3572 merged as b4449443590 and its push render
    30190635141 was superseded-cancelled seconds later by a newer merge queuing
    its own run (`cancel-in-progress: false` supersedes the PENDING run, not the
    running one). Descendant run 30193723520 then concluded success at
    8f5cfe12a66 — whose scope union already covered b4449443590 — yet the guard
    demanded a dedicated run at the merge sha that could never exist, forcing a
    manual ~50-minute rerun.
    """
    repo, _parent, merge, descendant = _merge_train(tmp_path)
    urls = _fake_render_api(
        monkeypatch,
        exact=[
            _render_run(30190635141, merge, "push", "2026-07-26T06:11:38Z", "completed", "cancelled")
        ],
        branch=[
            _render_run(
                30193723520, descendant, "push", "2026-07-26T07:57:25Z", "completed", "success"
            )
        ],
    )
    assert GUARD._render_status(repo, "acme", "widgets", merge, _MERGED_AT) == ("success", "")
    assert len(urls) == 2, "the descendant scan costs exactly one extra call"


def test_an_in_flight_descendant_render_defers_rather_than_blocks(monkeypatch, tmp_path):
    """An in-flight covering run is coverage-in-progress, not a wall.

    The operator ruling of 2026-07-27: the VPS pulls main every 3 minutes so the
    merge is live regardless, the shared lane owns the re-bake, and house law
    forbids a waiting session from touching it — so a queued/running covering run
    now yields ``deferred`` (satisfied by ``_stop``), never ``pending`` (which
    only means the lane never fired) or ``failed``.
    """
    repo, _parent, merge, descendant = _merge_train(tmp_path)
    _fake_render_api(
        monkeypatch,
        exact=[_render_run(1, merge, "push", "2026-07-26T06:11:38Z", "completed", "cancelled")],
        branch=[
            _render_run(2, descendant, "push", "2026-07-26T07:57:25Z", "in_progress")
        ],
    )
    status, detail = GUARD._render_status(repo, "acme", "widgets", merge, _MERGED_AT)
    assert status == "deferred"
    assert "in_progress" in detail
    assert "2" in detail, "the deferral names the covering run id"
    assert "coalescing lane" in detail and "nightly scope=all" in detail


def test_an_exact_sha_render_still_in_flight_also_defers(monkeypatch, tmp_path):
    """The deferral is not descendant-only: a queued run at the merge sha covers it too."""
    repo, _parent, merge, _descendant = _merge_train(tmp_path)
    _fake_render_api(
        monkeypatch,
        exact=[_render_run(77, merge, "push", "2026-07-26T06:11:38Z", "queued")],
        branch=[],
    )
    status, detail = GUARD._render_status(repo, "acme", "widgets", merge, _MERGED_AT)
    assert status == "deferred"
    assert "queued" in detail and "77" in detail


def test_a_failed_descendant_render_blocks_and_a_pre_merge_success_cannot_rescue_it(
    monkeypatch, tmp_path
):
    """Coverage needs a DESCENDANT: a green re-run of pre-merge history rendered a tree
    that never contained this merge, even though it ran after the merge landed."""
    repo, parent, merge, descendant = _merge_train(tmp_path)
    _fake_render_api(
        monkeypatch,
        exact=[_render_run(1, merge, "push", "2026-07-26T06:11:38Z", "completed", "cancelled")],
        branch=[
            _render_run(2, descendant, "push", "2026-07-26T07:57:25Z", "completed", "failure"),
            _render_run(3, parent, "push", "2026-07-26T08:10:00Z", "completed", "success"),
        ],
    )
    status, detail = GUARD._render_status(repo, "acme", "widgets", merge, _MERGED_AT)
    assert status == "failed", "a success on the merge's PARENT is not coverage"
    assert "failure" in detail and "descendant" in detail
    assert "gh run rerun 2" in detail, "the remediation must name the concluded run"


def test_only_a_push_lane_render_after_the_merge_can_cover_it(monkeypatch, tmp_path):
    """The event set and the created-at floor both have to hold, or coverage is fiction."""
    repo, _parent, merge, descendant = _merge_train(tmp_path)
    superseded = [
        _render_run(1, merge, "push", "2026-07-26T06:11:38Z", "completed", "cancelled")
    ]

    # A nightly `schedule` run is not the push lane this merge queued into.
    _fake_render_api(
        monkeypatch,
        exact=superseded,
        branch=[
            _render_run(2, descendant, "schedule", "2026-07-26T07:57:25Z", "completed", "success")
        ],
    )
    assert GUARD._render_status(repo, "acme", "widgets", merge, _MERGED_AT)[0] == "failed"

    # Belt-and-braces: a run created BEFORE the merge cannot have carried it.
    _fake_render_api(
        monkeypatch,
        exact=superseded,
        branch=[
            _render_run(3, descendant, "push", "2026-07-26T05:00:00Z", "completed", "success")
        ],
    )
    assert GUARD._render_status(repo, "acme", "widgets", merge, _MERGED_AT)[0] == "failed"

    # Same sha, on the lane and inside the window: a manual dispatch does cover it.
    _fake_render_api(
        monkeypatch,
        exact=superseded,
        branch=[
            _render_run(
                4, descendant, "workflow_dispatch", "2026-07-26T07:57:25Z", "completed", "success"
            )
        ],
    )
    assert GUARD._render_status(repo, "acme", "widgets", merge, _MERGED_AT) == ("success", "")


def test_no_render_run_at_all_is_still_the_just_merged_race(monkeypatch, tmp_path):
    """Nothing has started yet must stay pending — the widened scan must not turn it red."""
    repo, _parent, merge, _descendant = _merge_train(tmp_path)
    _fake_render_api(monkeypatch, exact=[], branch=[])
    assert GUARD._render_status(repo, "acme", "widgets", merge, _MERGED_AT) == (
        "pending",
        "The required render workflow has not started yet.",
    )


_PUBLIC_WORKFLOW = "public-render.yml"


def test_a_green_public_render_run_satisfies_the_gate(monkeypatch, tmp_path):
    """The other half of the #3897 fix: the fast lane's own run is proof.

    Run 30349907107 concluded success at the merge sha, pushed d4ac971df7a and
    put plans.html live — the guard just had no way to look at it. One API call,
    against public-render.yml's endpoint and no other.
    """
    repo, _parent, merge, _descendant = _merge_train(tmp_path)
    urls = _fake_render_api(
        monkeypatch,
        exact=[
            _render_run(
                30349907107, merge, "push", "2026-07-28T14:41:00Z", "completed", "success"
            )
        ],
        branch=[],
        workflow=_PUBLIC_WORKFLOW,
    )
    assert GUARD._render_status(
        repo, "acme", "widgets", merge, _MERGED_AT, _PUBLIC_WORKFLOW
    ) == ("success", "")
    assert len(urls) == 1 and _PUBLIC_WORKFLOW in urls[0], urls


def test_a_superseded_public_render_is_covered_by_the_run_that_replaced_it(
    monkeypatch, tmp_path
):
    """The fast lane runs `cancel-in-progress: TRUE`, so supersession is routine.

    A killed run can never re-conclude, so exact-sha-only would be unsatisfiable
    here for the same reason it was on the heavy lane — with an even shorter
    fuse, since ANY newer push kills the running job rather than only a pending
    one. Coverage still holds: every run checks out `ref: main` and rebuilds the
    public surfaces from scratch, so the survivor's tree contains what it killed.
    """
    repo, _parent, merge, descendant = _merge_train(tmp_path)
    _fake_render_api(
        monkeypatch,
        exact=[_render_run(1, merge, "push", "2026-07-28T14:41:00Z", "completed", "cancelled")],
        branch=[
            _render_run(2, descendant, "push", "2026-07-28T14:49:00Z", "completed", "success")
        ],
        workflow=_PUBLIC_WORKFLOW,
    )
    assert GUARD._render_status(
        repo, "acme", "widgets", merge, _MERGED_AT, _PUBLIC_WORKFLOW
    ) == ("success", "")


def test_every_public_lane_verdict_names_the_public_lane(monkeypatch, tmp_path):
    """A verdict that says "render" sends the operator to the wrong workflow."""
    repo, _parent, merge, _descendant = _merge_train(tmp_path)

    _fake_render_api(monkeypatch, exact=[], branch=[], workflow=_PUBLIC_WORKFLOW)
    assert GUARD._render_status(
        repo, "acme", "widgets", merge, _MERGED_AT, _PUBLIC_WORKFLOW
    ) == ("pending", "The required public-render workflow has not started yet.")

    _fake_render_api(
        monkeypatch,
        exact=[_render_run(5, merge, "push", "2026-07-28T14:41:00Z", "completed", "failure")],
        branch=[],
        workflow=_PUBLIC_WORKFLOW,
    )
    status, detail = GUARD._render_status(
        repo, "acme", "widgets", merge, _MERGED_AT, _PUBLIC_WORKFLOW
    )
    assert status == "failed"
    assert "gh run rerun 5" in detail and "public-render.yml on main" in detail
    assert "scope=all" not in detail, "the fast lane has no scope union to dispatch"

    _fake_render_api(
        monkeypatch,
        exact=[_render_run(6, merge, "push", "2026-07-28T14:41:00Z", "in_progress")],
        branch=[],
        workflow=_PUBLIC_WORKFLOW,
    )
    status, detail = GUARD._render_status(
        repo, "acme", "widgets", merge, _MERGED_AT, _PUBLIC_WORKFLOW
    )
    assert status == "deferred"
    assert "Public-render run 6" in detail and "public fast lane" in detail

    # And the heavy lane's own wording is untouched by the parameterisation.
    _fake_render_api(monkeypatch, exact=[], branch=[])
    assert GUARD._render_status(repo, "acme", "widgets", merge, _MERGED_AT) == (
        "pending",
        "The required render workflow has not started yet.",
    )


def _session_repo(tmp_path: Path) -> tuple[Path, Path]:
    """A repo with committed session work on a feature branch, plus its guard state."""
    repo = _repo(tmp_path)
    start_head = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "-b", "claude/feature")
    _commit(repo, "work.txt", "session work\n", "feat: session work")
    state_path = tmp_path / "state.json"
    GUARD._save(
        state_path,
        {
            "root": str(repo),
            "start_head": start_head,
            "baseline": GUARD._fingerprint(repo),
            "last_blocker": "",
            "blocker_count": 0,
        },
    )
    return repo, state_path


def _stop_verdict(
    monkeypatch, capsys, repo, state_path, *, merged_pr, ci=(True, ""), open_pull=None
):
    monkeypatch.setattr(GUARD, "_github_slug", lambda _root: ("acme", "widgets"))
    monkeypatch.setattr(GUARD, "_latest_merged_pr", lambda *_a: merged_pr)
    monkeypatch.setattr(GUARD, "_check_ci", lambda *_a: ci)
    # The armed-pull-request probe sits on the no-merged-pull-request path, so every
    # test that reaches it would otherwise hit the real API. No open pull request is
    # the default shape; the armed-PR tests below pass one explicitly.
    monkeypatch.setattr(GUARD, "_open_pull", lambda *_a: open_pull)
    GUARD._stop(repo, state_path, {"hook_event_name": "Stop"})
    out = capsys.readouterr().out.strip()
    if not out:
        return None
    emitted = json.loads(out)
    if "reason" not in emitted:
        return None  # a clean stop, not a block
    # Reason reads "SHIP LOOP <code>: <detail>" — the code sits before the colon.
    return emitted["reason"].split(":", 1)[0].split()[-1]


@pytest.mark.parametrize(
    "branch",
    (
        "codex/feature",
        "claire/feature",
        "feature",
        "claude",
        "claudeish/feature",
    ),
)
def test_non_claude_branch_is_rejected_before_stand_down_and_github(
    monkeypatch, tmp_path, capsys, branch
):
    repo, state_path = _session_repo(tmp_path)
    _git(repo, "branch", "-m", branch)
    monkeypatch.setattr(
        GUARD,
        "_fast_forwarded_onto_main",
        lambda *_a: pytest.fail("a forbidden branch reached the stand-down gate"),
    )
    monkeypatch.setattr(
        GUARD,
        "_github_slug",
        lambda *_a: pytest.fail("a forbidden branch reached GitHub"),
    )

    GUARD._stop(repo, state_path, {"hook_event_name": "Stop"})

    emitted = json.loads(capsys.readouterr().out.strip())
    assert "SHIP LOOP unsafe_branch" in emitted["reason"]
    assert "claude/* branch" in emitted["reason"]


def test_claude_branch_still_reaches_the_full_delivery_chain(
    monkeypatch, tmp_path, capsys
):
    repo, state_path = _session_repo(tmp_path)

    verdict = _stop_verdict(
        monkeypatch, capsys, repo, state_path, merged_pr=None
    )

    assert verdict == "unpushed"


# `base` is part of the real `/pulls` shape and the CI gate reads it (the merged
# head's semantic proof base — see the merged-PR base tests at the end of this
# file), so a fixture without one is a pull request GitHub never returns. It also
# keeps the proof-reuse tests below honest: an incomplete cached record is
# deliberately refetched, so only a COMPLETE one can prove the cache is reused.
_MERGED_PR = {
    "merged_at": "2026-07-25T22:18:56Z",
    "head": {"sha": "a" * 40},
    "base": {"sha": "c" * 40},
    "merge_commit_sha": "b" * 40,
}


def _stub_remote_git(monkeypatch) -> None:
    """Let the two remote-dependent git calls pass in a fixture repo with no origin.

    Only `git fetch` and `merge-base --is-ancestor` are faked; rev-parse, branch,
    rev-list and diff still run for real against the fixture, so the parts of
    `_stop` under test are not stubbed out from under it.
    """
    real_run = GUARD._run

    def router(root, *args, **kwargs):
        if args[:2] == ("git", "fetch") or args[:3] == ("git", "merge-base", "--is-ancestor"):
            return ""
        return real_run(root, *args, **kwargs)

    monkeypatch.setattr(GUARD, "_run", router)


def test_stop_emits_the_exclusion_note_as_a_system_message(monkeypatch, tmp_path, capsys):
    """A pass that rests on excluded reds must be auditable, not silent.

    The CI gate can now clear a red it judged base-side, on named evidence. That
    judgement is exactly what an operator has to be able to challenge afterwards,
    so `_stop` prints it on the way through instead of swallowing it — and still
    lets the session stop.
    """
    repo, state_path = _session_repo(tmp_path)
    note = (
        "Ignored base-side CI: ci-pack-1 (failure) — the same check failed on 2 independent "
        "concurrent PR head(s) (ccccccc@claude/vector-dsr, ddddddd@claude/w2-support) before "
        "this merge."
    )
    monkeypatch.setattr(GUARD, "_github_slug", lambda _root: ("acme", "widgets"))
    monkeypatch.setattr(GUARD, "_latest_merged_pr", lambda *_a: _MERGED_PR)
    monkeypatch.setattr(GUARD, "_check_ci", lambda *_a, **_k: (True, note))
    monkeypatch.setattr(GUARD, "_needs_render", lambda *_a: False)
    monkeypatch.setattr(
        GUARD, "_get_json", lambda _url: {"commit": _git(repo, "rev-parse", "HEAD")}
    )
    _stub_remote_git(monkeypatch)

    GUARD._stop(repo, state_path, {"hook_event_name": "Stop"})

    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert any(note in str(line.get("systemMessage") or "") for line in lines), lines
    assert not any(line.get("decision") == "block" for line in lines), lines


def test_stop_reuses_completed_pr_ci_and_main_proofs_while_render_waits(
    monkeypatch, tmp_path, capsys
):
    """A long render wait must poll only render, not replay earlier GitHub gates."""
    repo, state_path = _session_repo(tmp_path)
    calls = {"pull": 0, "ci": 0, "render": 0}

    monkeypatch.setattr(GUARD, "_github_slug", lambda _root: ("acme", "widgets"))

    def merged(*_args):
        calls["pull"] += 1
        return _MERGED_PR

    def green(*_args):
        calls["ci"] += 1
        return True, ""

    def pending(*_args):
        calls["render"] += 1
        return "pending", "Render workflow is queued."

    monkeypatch.setattr(GUARD, "_latest_merged_pr", merged)
    monkeypatch.setattr(GUARD, "_check_ci", green)
    monkeypatch.setattr(GUARD, "_needs_render", lambda *_a: True)
    monkeypatch.setattr(GUARD, "_render_status", pending)
    _stub_remote_git(monkeypatch)

    GUARD._stop(repo, state_path, {"hook_event_name": "Stop"})
    capsys.readouterr()
    GUARD._stop(repo, state_path, {"hook_event_name": "Stop"})
    capsys.readouterr()

    assert calls == {"pull": 1, "ci": 1, "render": 2}
    proofs = json.loads(state_path.read_text(encoding="utf-8"))["ship_proofs"]
    assert set(proofs) >= {"merged_pull", "ci", "origin_main"}
    assert "render" not in proofs


def test_stop_reuses_render_proof_while_production_catches_up(monkeypatch, tmp_path, capsys):
    """Once render is green, repeated live-health waits spend zero GitHub API calls."""
    repo, state_path = _session_repo(tmp_path)
    calls = {"pull": 0, "ci": 0, "render": 0, "health": 0}

    monkeypatch.setattr(GUARD, "_github_slug", lambda _root: ("acme", "widgets"))

    def merged(*_args):
        calls["pull"] += 1
        return _MERGED_PR

    def green(*_args):
        calls["ci"] += 1
        return True, ""

    def rendered(*_args):
        calls["render"] += 1
        return "success", ""

    def stale_health(_url):
        calls["health"] += 1
        return {"commit": "not-a-commit"}

    monkeypatch.setattr(GUARD, "_latest_merged_pr", merged)
    monkeypatch.setattr(GUARD, "_check_ci", green)
    monkeypatch.setattr(GUARD, "_needs_render", lambda *_a: True)
    monkeypatch.setattr(GUARD, "_render_status", rendered)
    monkeypatch.setattr(GUARD, "_get_json", stale_health)
    _stub_remote_git(monkeypatch)

    GUARD._stop(repo, state_path, {"hook_event_name": "Stop"})
    capsys.readouterr()
    GUARD._stop(repo, state_path, {"hook_event_name": "Stop"})
    capsys.readouterr()

    assert calls == {"pull": 1, "ci": 1, "render": 1, "health": 2}
    proofs = json.loads(state_path.read_text(encoding="utf-8"))["ship_proofs"]
    assert set(proofs) >= {"merged_pull", "ci", "origin_main", "render"}


def test_stop_defers_an_in_flight_render_and_proceeds_to_the_live_gate(
    monkeypatch, tmp_path, capsys
):
    """An in-flight covering render must NOT hold the session at the render gate.

    Operator ruling 2026-07-27: `_render_status` returns ``deferred``, `_stop`
    remembers the render proof carrying that note, falls through to the (green)
    live gate, and the clean stop emits a systemMessage naming the deferral — no
    block line anywhere.
    """
    repo, state_path = _session_repo(tmp_path)
    monkeypatch.setattr(GUARD, "_github_slug", lambda _root: ("acme", "widgets"))
    monkeypatch.setattr(GUARD, "_latest_merged_pr", lambda *_a: _MERGED_PR)
    monkeypatch.setattr(GUARD, "_check_ci", lambda *_a, **_k: (True, ""))
    monkeypatch.setattr(GUARD, "_needs_render", lambda *_a: True)
    deferral = (
        "Render run 30193723520 is in_progress and covers this merge; completion is "
        "deferred to the shared coalescing lane, with the nightly scope=all re-render "
        "as backstop."
    )
    monkeypatch.setattr(GUARD, "_render_status", lambda *_a: ("deferred", deferral))
    monkeypatch.setattr(
        GUARD, "_get_json", lambda _url: {"commit": _git(repo, "rev-parse", "HEAD")}
    )
    _stub_remote_git(monkeypatch)

    GUARD._stop(repo, state_path, {"hook_event_name": "Stop"})

    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert not any(line.get("decision") == "block" for line in lines), lines
    assert any(deferral in str(line.get("systemMessage") or "") for line in lines), lines
    # The proof persists the deferral so a later Stop reads it back without repolling.
    assert not state_path.exists() or json.loads(state_path.read_text(encoding="utf-8"))


def test_stop_reads_a_persisted_render_deferral_and_still_notes_it(monkeypatch, tmp_path, capsys):
    """A render deferred on an earlier Stop must not be re-polled — and must still audit.

    The proof value is a dict carrying ``deferred``; `_stop` reads it back, skips
    `_render_status` entirely, and folds the note into the systemMessage.
    """
    repo, state_path = _session_repo(tmp_path)
    monkeypatch.setattr(GUARD, "_github_slug", lambda _root: ("acme", "widgets"))
    monkeypatch.setattr(GUARD, "_latest_merged_pr", lambda *_a: _MERGED_PR)
    monkeypatch.setattr(GUARD, "_check_ci", lambda *_a, **_k: (True, ""))
    monkeypatch.setattr(GUARD, "_needs_render", lambda *_a: True)
    monkeypatch.setattr(
        GUARD, "_render_status", lambda *_a: pytest.fail("a persisted deferral must not repoll")
    )
    monkeypatch.setattr(
        GUARD, "_get_json", lambda _url: {"commit": _git(repo, "rev-parse", "HEAD")}
    )
    _stub_remote_git(monkeypatch)

    note = "Render run 42 is queued and covers this merge; deferred to the lane."
    GUARD._remember_proof(
        state_path,
        json.loads(state_path.read_text(encoding="utf-8")),
        "render",
        "b" * 40,
        {"deferred": note},
    )

    GUARD._stop(repo, state_path, {"hook_event_name": "Stop"})

    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert not any(line.get("decision") == "block" for line in lines), lines
    assert any(note in str(line.get("systemMessage") or "") for line in lines), lines


def _public_lane_session(tmp_path: Path) -> tuple[Path, Path, str, dict]:
    """A session whose merged commit is #3897's shape, in a repo with both lanes.

    Nothing about the lane decision is stubbed here — the guard reads the real
    workflows out of the fixture and diffs the real merge — so this is the
    end-to-end statement of the fix rather than a restatement of its unit tests.
    """
    repo = _public_lane_repo(tmp_path)
    start_head = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "-b", "claude/plans")
    merge_sha = _commit_files(
        repo,
        {
            "templates/plans.html.j2": "{% extends 'seo_base.html.j2' %}\n",
            "site/plans.html": "<h1>Plans</h1>\n",
        },
        "feat(plans): rebuild the pricing page",
    )
    state_path = tmp_path / "state.json"
    GUARD._save(
        state_path,
        {
            "root": str(repo),
            "start_head": start_head,
            "baseline": GUARD._fingerprint(repo),
            "last_blocker": "",
            "blocker_count": 0,
        },
    )
    pull = {
        "number": 3897,
        "head": {"sha": merge_sha, "ref": "claude/plans"},
        "merge_commit_sha": merge_sha,
        "merged_at": "2026-07-28T14:38:00Z",
    }
    return repo, state_path, merge_sha, pull


def test_stop_clears_a_public_only_merge_on_the_fast_lane_alone(monkeypatch, tmp_path, capsys):
    """THE regression, end to end. A green public-render run must release Stop.

    And the heavy lane must not even be ASKED: render.yml's push filter excludes
    every path in this merge, so polling it can only ever return the
    `render_pending` that blocked PR #3897 forever — which is why the router
    below fails the test outright if that endpoint is touched.
    """
    repo, state_path, merge_sha, pull = _public_lane_session(tmp_path)
    seen: list[str] = []

    monkeypatch.setattr(GUARD, "_github_slug", lambda _root: ("acme", "widgets"))
    monkeypatch.setattr(GUARD, "_latest_merged_pr", lambda *_a: pull)
    monkeypatch.setattr(GUARD, "_check_ci", lambda *_a, **_k: (True, ""))
    monkeypatch.setattr(GUARD, "_open_pull", lambda *_a: None)

    def router(url: str):
        if "actions/workflows/" in url:
            seen.append(url)
        if "actions/workflows/render.yml/runs" in url:
            pytest.fail("the heavy lane can never have a run for this merge")
        if "actions/workflows/public-render.yml/runs" in url:
            return {
                "workflow_runs": [
                    _render_run(
                        30349907107,
                        merge_sha,
                        "push",
                        "2026-07-28T14:41:00Z",
                        "completed",
                        "success",
                    )
                ]
            }
        return {"commit": _git(repo, "rev-parse", "HEAD")}

    monkeypatch.setattr(GUARD, "_get_json", router)
    _stub_remote_git(monkeypatch)

    GUARD._stop(repo, state_path, {"hook_event_name": "Stop"})

    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert not any(line.get("decision") == "block" for line in lines), lines
    assert seen and all("public-render.yml" in url for url in seen), seen


def test_stop_still_blocks_when_the_public_lane_never_fired(monkeypatch, tmp_path, capsys):
    """The fix widens what SATISFIES the gate; it must not delete the gate.

    A dead wire on the fast lane is still a missing render, and `pending` still
    blocks — the one verdict that means no run exists at all.
    """
    repo, state_path, _merge_sha, pull = _public_lane_session(tmp_path)

    monkeypatch.setattr(GUARD, "_github_slug", lambda _root: ("acme", "widgets"))
    monkeypatch.setattr(GUARD, "_latest_merged_pr", lambda *_a: pull)
    monkeypatch.setattr(GUARD, "_check_ci", lambda *_a, **_k: (True, ""))
    monkeypatch.setattr(GUARD, "_open_pull", lambda *_a: None)
    monkeypatch.setattr(
        GUARD,
        "_get_json",
        lambda url: {"workflow_runs": []}
        if "actions/workflows/" in url
        else {"commit": _git(repo, "rev-parse", "HEAD")},
    )
    _stub_remote_git(monkeypatch)

    GUARD._stop(repo, state_path, {"hook_event_name": "Stop"})

    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.strip()]
    blocks = [line for line in lines if line.get("decision") == "block"]
    assert blocks, lines
    assert "public-render workflow has not started" in blocks[0]["reason"]


def test_stop_folds_ci_and_render_notes_into_one_system_message(monkeypatch, tmp_path, capsys):
    """A single Stop invocation must emit ONE JSON object even with two audit notes.

    Two separate systemMessage lines would break the single-object stdout contract.
    """
    repo, state_path = _session_repo(tmp_path)
    ci_note = "Ignored base-side CI: ci-pack-1 (failure) — two independent heads."
    deferral = "Render run 9 is in_progress and covers this merge; deferred to the lane."
    monkeypatch.setattr(GUARD, "_github_slug", lambda _root: ("acme", "widgets"))
    monkeypatch.setattr(GUARD, "_latest_merged_pr", lambda *_a: _MERGED_PR)
    monkeypatch.setattr(GUARD, "_check_ci", lambda *_a, **_k: (True, ci_note))
    monkeypatch.setattr(GUARD, "_needs_render", lambda *_a: True)
    monkeypatch.setattr(GUARD, "_render_status", lambda *_a: ("deferred", deferral))
    monkeypatch.setattr(
        GUARD, "_get_json", lambda _url: {"commit": _git(repo, "rev-parse", "HEAD")}
    )
    _stub_remote_git(monkeypatch)

    GUARD._stop(repo, state_path, {"hook_event_name": "Stop"})

    raw = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert len(raw) == 1, f"stdout must stay a single JSON object, got {raw}"
    message = json.loads(raw[0])["systemMessage"]
    assert ci_note in message and deferral in message


def test_a_merged_branch_deleted_on_merge_is_not_reported_as_unpushed(
    monkeypatch, tmp_path, capsys
):
    """The completed end state must not read as the state before any push.

    GitHub auto-deletes the head branch on merge, which drops `@{upstream}`. The
    guard used to block `unpushed` right there, before ever looking up the merged
    pull request — an unsatisfiable verdict on finished work, since the branch is
    merged and recreating it would be wrong.
    """
    repo, state_path = _session_repo(tmp_path)
    assert "fatal" in subprocess.run(
        ("git", "rev-parse", "--abbrev-ref", "@{upstream}"),
        cwd=repo, text=True, capture_output=True,
    ).stderr, "precondition: this repo has no upstream"

    # CI is failed purely to stop the chain at a code that proves we got past the
    # upstream gate; ci_failed lives strictly after it.
    verdict = _stop_verdict(
        monkeypatch, capsys, repo, state_path,
        merged_pr=_MERGED_PR, ci=(False, "Failing CI: build (failure)"),
    )
    assert verdict == "ci_failed", f"expected to reach the CI gate, got {verdict}"


def test_no_upstream_and_no_merged_pr_is_still_unpushed(monkeypatch, tmp_path, capsys):
    """The deferral must not lose the real unpushed case."""
    repo, state_path = _session_repo(tmp_path)
    verdict = _stop_verdict(monkeypatch, capsys, repo, state_path, merged_pr=None)
    assert verdict == "unpushed"


def test_pushed_but_unmerged_still_blocks_as_unmerged(monkeypatch, tmp_path, capsys):
    repo, state_path = _session_repo(tmp_path)
    bare = tmp_path / "origin.git"
    subprocess.run(("git", "init", "--bare", str(bare)), check=True, capture_output=True)
    _git(repo, "remote", "add", "origin", str(bare))
    _git(repo, "push", "-u", "origin", "claude/feature")
    verdict = _stop_verdict(monkeypatch, capsys, repo, state_path, merged_pr=None)
    assert verdict == "unmerged"


def test_unpushed_commits_still_block_when_an_upstream_exists(monkeypatch, tmp_path, capsys):
    """The ahead-count check must keep firing; only its guard clause moved."""
    repo, state_path = _session_repo(tmp_path)
    bare = tmp_path / "origin.git"
    subprocess.run(("git", "init", "--bare", str(bare)), check=True, capture_output=True)
    _git(repo, "remote", "add", "origin", str(bare))
    _git(repo, "push", "-u", "origin", "claude/feature")
    _commit(repo, "more.txt", "later\n", "feat: not pushed")
    GUARD._save(
        state_path,
        {**json.loads(state_path.read_text(encoding="utf-8")), "baseline": GUARD._fingerprint(repo)},
    )
    verdict = _stop_verdict(monkeypatch, capsys, repo, state_path, merged_pr=_MERGED_PR)
    assert verdict == "unpushed"


def _stand_down_repo(tmp_path: Path) -> tuple[Path, Path]:
    """A session that found its assigned defect already fixed on origin/main:
    it fast-forwarded its worktree onto the fix and created nothing."""
    repo = _repo(tmp_path)
    start_head = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "-b", "claude/stand-down")
    state_path = tmp_path / "state.json"
    GUARD._save(state_path, {
        "root": str(repo),
        "start_head": start_head,
        "baseline": GUARD._fingerprint(repo),
        "last_blocker": "",
        "blocker_count": 0,
    })
    bare = tmp_path / "origin.git"
    subprocess.run(("git", "init", "--bare", str(bare)), check=True, capture_output=True)
    _git(repo, "remote", "add", "origin", str(bare))
    _git(repo, "checkout", "main")
    _commit(repo, "fix.txt", "already fixed on main\n", "fix: landed by another session")
    _git(repo, "push", "origin", "main")
    _git(repo, "checkout", "claude/stand-down")
    _git(repo, "reset", "--hard", "origin/main")
    return repo, state_path


def test_a_stand_down_session_fast_forwarded_onto_main_may_stop(monkeypatch, tmp_path, capsys):
    """A session that verified its defect was already fixed must be able to stop.

    The no-op exemption only covers a session whose HEAD never moved. A stand-down
    session syncs to tip first — `git reset --hard origin/main` — to check the fix
    where it actually landed, so HEAD moves with zero session-created commits and
    the old check missed it. The chain it was then held to is unsatisfiable:
    GitHub refuses a zero-diff pull request ("No commits between main and
    <branch>") and `unmerged` is not an escapable external blocker, so the only
    exit observed in the field (2026-07-26, claude/serene-colden-e5b716) was
    resetting back to start_head. Nothing shipped here, so nothing is asked of
    GitHub either — the stubs below fail the test if it is consulted at all.
    """
    repo, state_path = _stand_down_repo(tmp_path)
    monkeypatch.setattr(
        GUARD, "_github_slug", lambda *_a: pytest.fail("a fast-forwarded no-op asked GitHub")
    )
    monkeypatch.setattr(
        GUARD, "_latest_merged_pr", lambda *_a: pytest.fail("a fast-forwarded no-op asked GitHub")
    )

    GUARD._stop(repo, state_path, {"hook_event_name": "Stop"})

    assert capsys.readouterr().out.strip() == ""


def test_a_direct_push_to_main_is_not_exempted_by_the_fast_forward(monkeypatch, tmp_path, capsys):
    """Ancestry proves POSITION, not authorship — so the branch gate outranks it.

    This repo satisfies all three of the exemption's own conditions: HEAD equals
    origin/main, the ahead-count is 0, the tree is clean. But it got there by
    committing on main and pushing, not by syncing to someone else's fix, and
    `merge-base` cannot tell those apart. Work pushed straight to main really did
    ship, so exempting it would skip the render and live gates on live work —
    fail-open, which this guard may never be. `unsafe_branch` is the correct
    verdict, and it is only reachable if the branch check runs FIRST.
    """
    repo = _repo(tmp_path)
    start_head = _git(repo, "rev-parse", "HEAD")
    state_path = tmp_path / "state.json"
    GUARD._save(state_path, {
        "root": str(repo),
        "start_head": start_head,
        "baseline": GUARD._fingerprint(repo),
        "last_blocker": "",
        "blocker_count": 0,
    })
    bare = tmp_path / "origin.git"
    subprocess.run(("git", "init", "--bare", str(bare)), check=True, capture_output=True)
    _git(repo, "remote", "add", "origin", str(bare))
    _commit(repo, "hotfix.txt", "straight to main\n", "fix: pushed without a PR")
    _git(repo, "push", "origin", "main")

    assert _git(repo, "rev-parse", "HEAD") == _git(repo, "rev-parse", "origin/main")
    assert _git(repo, "rev-list", "--count", "origin/main..HEAD") == "0"
    assert GUARD._fast_forwarded_onto_main(repo), "precondition: the exemption itself would fire"

    verdict = _stop_verdict(monkeypatch, capsys, repo, state_path, merged_pr=None)
    assert verdict == "unsafe_branch"


def test_commits_ahead_of_main_still_demand_the_full_chain(monkeypatch, tmp_path, capsys):
    """Syncing to tip does not buy an exemption for work built on top of it.

    The commit is committed, so the tree is clean and the dirty gate has nothing
    to say — the verdict has to come from the CHAIN. `--is-ancestor` returns rc=1
    the moment one session commit sits above origin/main, and the guard falls
    straight through to ordinary enforcement.
    """
    repo, state_path = _stand_down_repo(tmp_path)
    _commit(repo, "work.txt", "session work\n", "feat: real session work")
    verdict = _stop_verdict(monkeypatch, capsys, repo, state_path, merged_pr=None)
    assert verdict == "unpushed"


def test_a_dirty_stand_down_session_still_blocks_as_uncommitted(monkeypatch, tmp_path, capsys):
    """Uncommitted work is judged before the exemption and keeps blocking.

    A worktree that is level with origin/main but carries edits is not a
    stand-down; it is unfinished work that would be lost. The dirty-baseline gate
    sits above the exemption precisely so a fast-forward cannot launder it.
    """
    repo, state_path = _stand_down_repo(tmp_path)
    (repo / "notes.txt").write_text("session scratch\n", encoding="utf-8")
    verdict = _stop_verdict(monkeypatch, capsys, repo, state_path, merged_pr=None)
    assert verdict == "uncommitted"


def test_an_unreachable_origin_fails_closed_to_the_full_chain(monkeypatch, tmp_path, capsys):
    """Ancestry against a STALE local ref is not evidence; the fetch must succeed.

    Everything else about this repo still says "exempt": refs/remotes/origin/main
    survives the broken remote url, it still names HEAD, the ahead-count is 0 and
    the tree is clean. Only the fetch fails — so this isolates the fail-closed
    rule. Offline, the exemption simply does not apply and the normal chain (whose
    GitHub failures ARE escapable external blockers) takes the session back.
    """
    repo, state_path = _stand_down_repo(tmp_path)
    _git(repo, "remote", "set-url", "origin", str(tmp_path / "gone.git"))
    verdict = _stop_verdict(monkeypatch, capsys, repo, state_path, merged_pr=None)
    assert verdict == "unpushed"


def test_a_session_that_never_moved_head_may_still_stop(monkeypatch, tmp_path, capsys):
    """The original no-op exemption, and its ORDER relative to the new one.

    A session that changed nothing has always been free to stop. It must stay
    free without paying for a network round trip: the start_head comparison has to
    short-circuit BEFORE `_fast_forwarded_onto_main`, or an offline no-op session
    would sit through a failing fetch on every Stop. Both stubs fail the test if
    either is reached.
    """
    repo = _repo(tmp_path)
    state_path = tmp_path / "state.json"
    GUARD._save(state_path, {
        "root": str(repo),
        "start_head": _git(repo, "rev-parse", "HEAD"),
        "baseline": GUARD._fingerprint(repo),
        "last_blocker": "",
        "blocker_count": 0,
    })
    monkeypatch.setattr(
        GUARD, "_github_slug", lambda *_a: pytest.fail("a no-op session asked GitHub")
    )
    monkeypatch.setattr(
        GUARD,
        "_fast_forwarded_onto_main",
        lambda *_a: pytest.fail("a no-op session paid for a fetch"),
    )

    GUARD._stop(repo, state_path, {"hook_event_name": "Stop"})

    assert capsys.readouterr().out.strip() == ""


def _pushed_session_repo(tmp_path: Path) -> tuple[Path, Path]:
    """A session that committed and PUSHED its branch, with a real origin.

    Everything the stand-down exemption checks is genuinely available here — a
    reachable remote, a real origin/main to fetch — so a test built on this
    fixture exercises the exemption rather than being declined by a missing ref.
    Main is advanced by a concurrent session so that landing on origin/main is
    never also a landing on start_head, which the older no-op exemption would
    claim first.
    """
    repo = _repo(tmp_path)
    bare = tmp_path / "origin.git"
    subprocess.run(("git", "init", "--bare", str(bare)), check=True, capture_output=True)
    _git(repo, "remote", "add", "origin", str(bare))
    _git(repo, "push", "-q", "-u", "origin", "main")
    start_head = _git(repo, "rev-parse", "HEAD")
    state_path = tmp_path / "state.json"
    GUARD._save(state_path, {
        "root": str(repo),
        "start_head": start_head,
        "baseline": GUARD._fingerprint(repo),
        "last_blocker": "",
        "blocker_count": 0,
    })
    _git(repo, "checkout", "-qb", "claude/feature")
    _commit(repo, "work.txt", "session work\n", "feat: real session work")
    _git(repo, "push", "-q", "-u", "origin", "claude/feature")
    _git(repo, "checkout", "-q", "main")
    _commit(repo, "other.txt", "another session\n", "other: concurrent merge")
    _git(repo, "push", "-q", "origin", "main")
    _git(repo, "checkout", "-q", "claude/feature")
    return repo, state_path


def test_an_open_pull_request_is_not_a_stand_down(monkeypatch, tmp_path, capsys):
    """Pushed work waiting on CI looks EXACTLY like a stand-down by position.

    `git reset --hard origin/main` moves the LOCAL branch ref, so peeking at main
    while a pull request is still open leaves the worktree at origin's tip with a
    zero ahead-count and a clean tree — every condition `_fast_forwarded_onto_main`
    tests — while the session's commits are alive on `origin/<branch>` under an
    unmerged pull request. Exempting that abandons the pull request silently.

    The verdict is `unpushed` rather than `unmerged` because the ahead-count gate
    reaches it first: the reset worktree now carries main's commit, which the
    branch's own upstream does not have. Either way the session is held — what
    this pins is that the exemption does not release it.
    """
    repo, state_path = _pushed_session_repo(tmp_path)
    _git(repo, "reset", "--hard", "-q", "origin/main")
    assert GUARD._fast_forwarded_onto_main(repo), (
        "precondition: by POSITION this is indistinguishable from a stand-down"
    )
    assert _git(repo, "log", "--oneline", "-1", "origin/claude/feature"), (
        "precondition: the session's commits are alive on the remote"
    )

    verdict = _stop_verdict(monkeypatch, capsys, repo, state_path, merged_pr=None)
    assert verdict == "unpushed", f"an open pull request must still block, got {verdict}"


def test_a_merge_commit_that_keeps_the_branch_shas_still_runs_the_ci_gate(
    monkeypatch, tmp_path, capsys
):
    """A squash mints a new sha; a merge commit or rebase merge does not.

    With the branch's own shas on main, the tip becomes a literal ancestor of
    origin/main with no reset and no branch switch — the session simply stops
    where it stood. Position alone would exempt a merge that really landed and
    skip CI, render, and live for it. `ci_failed` proves the chain was reached.
    """
    repo, state_path = _pushed_session_repo(tmp_path)
    # The server merged it without squashing: main now contains this very sha.
    _git(repo, "checkout", "-q", "main")
    _git(repo, "merge", "--no-ff", "-q", "-m", "Merge pull request", "claude/feature")
    _git(repo, "push", "-q", "origin", "main")
    _git(repo, "checkout", "-q", "claude/feature")
    _git(repo, "fetch", "-q", "origin", "main")
    assert GUARD._fast_forwarded_onto_main(repo), (
        "precondition: an unsquashed merge leaves the tip inside origin/main"
    )

    verdict = _stop_verdict(
        monkeypatch, capsys, repo, state_path,
        merged_pr=_MERGED_PR, ci=(False, "Failing CI: build (failure)"),
    )
    assert verdict == "ci_failed", f"expected to reach the CI gate, got {verdict}"


def test_a_branch_pushed_without_an_upstream_is_not_a_stand_down(
    monkeypatch, tmp_path, capsys
):
    """`@{upstream}` alone cannot answer "was this ever pushed?".

    `git push origin HEAD:<branch>` sets no upstream but does update the
    remote-tracking ref, and so does any later fetch — which is why the remote
    ref is the second half of the question.
    """
    repo, state_path = _pushed_session_repo(tmp_path)
    _git(repo, "branch", "--unset-upstream")
    _git(repo, "reset", "--hard", "-q", "origin/main")
    assert GUARD._fast_forwarded_onto_main(repo)
    assert GUARD._branch_was_pushed(repo, "claude/feature") is True

    verdict = _stop_verdict(monkeypatch, capsys, repo, state_path, merged_pr=None)
    assert verdict == "unpushed", f"a pushed branch is never a stand-down, got {verdict}"


def test_branch_was_pushed_fails_closed_when_git_cannot_answer(tmp_path):
    """Ignorance declines the exemption; it never grants it."""
    repo = _repo(tmp_path)
    assert GUARD._branch_was_pushed(repo, "claude/never-pushed") is False
    assert GUARD._branch_was_pushed(repo, "") is True, "an unknown branch is not a stand-down"
    assert GUARD._branch_was_pushed(tmp_path / "not-a-repo", "claude/x") is True


# --- escape ladders (operator ruling 2026-07-27: fix the traps, keep the gate) ---

_REPORTED = "SHIP LOOP BLOCKED: the same external blocker persists with evidence.\n"


def _block_state(tmp_path: Path) -> Path:
    """A fresh guard-state file carrying the four counters _block maintains."""
    path = tmp_path / "block-state.json"
    GUARD._save(
        path,
        {
            "root": str(tmp_path),
            "start_head": "0" * 40,
            "baseline": {},
            "last_blocker": "",
            "blocker_count": 0,
            "total_blocks": 0,
            "external_blocks": 0,
        },
    )
    return path


def _drive_block(path: Path, capsys, code: str, payload: dict) -> bool:
    """Run one _block against the CURRENT on-disk state; return True if it ESCAPED.

    State is reloaded each call exactly as `_stop` does, so cumulative counters are
    read back from disk rather than inherited from a live dict.
    """
    state = GUARD._load(path)
    GUARD._block(path, state, payload, code, f"reason for {code}")
    return capsys.readouterr().out.strip() == ""


def _drive_block_keyed(path: Path, capsys, code: str, payload: dict, exit_key: str) -> bool:
    """`_drive_block` with an exit key; return True if the Stop was allowed."""
    state = GUARD._load(path)
    GUARD._block(path, state, payload, code, f"reason for {code}", exit_key=exit_key)
    return capsys.readouterr().out.strip() == ""


def test_a_ratified_ladder_exit_is_remembered_for_the_exact_frozen_state(tmp_path, capsys):
    """One evidence report per frozen merged head, not one per Stop.

    A `ci_failed` block on a merged head argues about evidence frozen at merge,
    so once the full ladder ratified an exit (report + external arms) the same
    state must pass every later Stop without demanding an identical re-report —
    the 2026-08-19 authority-frozen session filed the same `SHIP LOOP BLOCKED:`
    report dozens of times."""
    path = _block_state(tmp_path)
    reported = {"stop_hook_active": True, "last_assistant_message": _REPORTED}
    key = f"ci_failed:{'a' * 40}:{'c' * 40}"
    assert _drive_block_keyed(path, capsys, "ci_failed", reported, key) is False
    assert _drive_block_keyed(path, capsys, "ci_failed", reported, key) is True
    assert GUARD._load(path)["ladder_exits"] == [key]
    # A later NATURAL stop — no report, no stop_hook_active — passes through
    # silently and bumps no counter.
    natural = {"stop_hook_active": False, "last_assistant_message": "done."}
    before = GUARD._load(path)["total_blocks"]
    assert _drive_block_keyed(path, capsys, "ci_failed", natural, key) is True
    assert GUARD._load(path)["total_blocks"] == before


def test_a_remembered_exit_never_covers_a_different_frozen_state(tmp_path, capsys):
    path = _block_state(tmp_path)
    reported = {"stop_hook_active": True, "last_assistant_message": _REPORTED}
    first = f"ci_failed:{'a' * 40}:{'c' * 40}"
    assert _drive_block_keyed(path, capsys, "ci_failed", reported, first) is False
    assert _drive_block_keyed(path, capsys, "ci_failed", reported, first) is True
    # A new merge mints a new key; without a fresh report it must still block.
    second = f"ci_failed:{'e' * 40}:{'f' * 40}"
    natural = {"stop_hook_active": False, "last_assistant_message": "done."}
    assert _drive_block_keyed(path, capsys, "ci_failed", natural, second) is False
    assert GUARD._load(path)["ladder_exits"] == [first]


def test_an_unratified_block_records_no_ladder_exit(tmp_path, capsys):
    """Only the moment an escape actually fires may write the memory — a block
    that was refused (no report yet) must leave nothing behind."""
    path = _block_state(tmp_path)
    unreported = {"stop_hook_active": True, "last_assistant_message": "still working"}
    key = f"ci_failed:{'a' * 40}:{'c' * 40}"
    assert _drive_block_keyed(path, capsys, "ci_failed", unreported, key) is False
    assert _drive_block_keyed(path, capsys, "ci_failed", unreported, key) is False
    assert "ladder_exits" not in GUARD._load(path)


def test_a_keyless_block_never_reads_or_writes_the_exit_memory(tmp_path, capsys):
    """Internal codes and evolving states carry no key; the ladder is unchanged
    for them even when a remembered exit exists for another state."""
    path = _block_state(tmp_path)
    reported = {"stop_hook_active": True, "last_assistant_message": _REPORTED}
    key = f"ci_failed:{'a' * 40}:{'c' * 40}"
    assert _drive_block_keyed(path, capsys, "ci_failed", reported, key) is False
    assert _drive_block_keyed(path, capsys, "ci_failed", reported, key) is True
    natural = {"stop_hook_active": False, "last_assistant_message": "done."}
    assert _drive_block(path, capsys, "render_pending", natural) is False
    assert GUARD._load(path)["ladder_exits"] == [key]


def test_external_ping_pong_escapes_on_the_third_cumulative_external_block(tmp_path, capsys):
    """The new cumulative arm. Alternating external codes reset the CONSECUTIVE
    counter every hop, so the old `count >= 2` rule never armed — a session
    ping-ponging render_pending -> github_rate_limited -> render_pending was
    trapped. `external_blocks >= 3` breaks that loop."""
    path = _block_state(tmp_path)
    reported = {"stop_hook_active": True, "last_assistant_message": _REPORTED}
    codes = ["render_pending", "github_rate_limited", "render_failed"]
    escapes = [_drive_block(path, capsys, code, reported) for code in codes]
    assert escapes == [False, False, True], escapes
    state = GUARD._load(path)
    assert state["external_blocks"] == 3 and state["blocker_count"] == 1


def test_two_consecutive_external_blocks_still_escape(tmp_path, capsys):
    """The pre-existing consecutive-external arm must keep working unchanged."""
    path = _block_state(tmp_path)
    reported = {"stop_hook_active": True, "last_assistant_message": _REPORTED}
    assert _drive_block(path, capsys, "render_pending", reported) is False
    assert _drive_block(path, capsys, "render_pending", reported) is True
    state = GUARD._load(path)
    assert state["blocker_count"] == 2 and state["external_blocks"] == 2


def test_internal_unmerged_is_refused_at_nine_and_escapes_at_ten(tmp_path, capsys):
    """Internal codes had NO escape — the 258x infinite loop on `unmerged`.

    The any-code loop breaker arms at 10 CONSECUTIVE blocks, never before."""
    path = _block_state(tmp_path)
    reported = {"stop_hook_active": True, "last_assistant_message": _REPORTED}
    for _ in range(9):
        assert _drive_block(path, capsys, "unmerged", reported) is False
    assert GUARD._load(path)["blocker_count"] == 9
    assert _drive_block(path, capsys, "unmerged", reported) is True
    assert GUARD._load(path)["blocker_count"] == 10


def test_total_blocks_ceiling_escapes_a_mixed_internal_loop(tmp_path, capsys):
    """15 total blocks escape even when no single code reaches its consecutive
    ceiling — the mixed-code loop that the consecutive counters alone miss."""
    path = _block_state(tmp_path)
    reported = {"stop_hook_active": True, "last_assistant_message": _REPORTED}
    # Alternate two internal codes so neither consecutive run passes ~7, and no
    # code is external, so only total_blocks can arm the escape.
    codes = ["unmerged", "unpushed"]
    escapes = [
        _drive_block(path, capsys, codes[index % 2], reported) for index in range(15)
    ]
    assert escapes[:14] == [False] * 14, escapes
    assert escapes[14] is True
    state = GUARD._load(path)
    assert state["total_blocks"] == 15 and state["external_blocks"] == 0


def test_the_escape_never_arms_without_the_reported_phrase(tmp_path, capsys):
    """No counter releases a session that has not filed `SHIP LOOP BLOCKED:`."""
    path = _block_state(tmp_path)
    # stop_hook_active set, but the final message is NOT the report.
    unreported = {"stop_hook_active": True, "last_assistant_message": "done for now"}
    for _ in range(30):
        assert _drive_block(path, capsys, "unmerged", unreported) is False
    # Well past both the consecutive (10) and total (15) ceilings, still blocking.
    assert GUARD._load(path)["total_blocks"] == 30

    # And a reported message on the FIRST block is inert however it is phrased —
    # the report cannot buy a bailout before the session has tried again.
    path = _block_state(tmp_path)
    no_active = {"stop_hook_active": False, "last_assistant_message": _REPORTED}
    assert _drive_block(path, capsys, "render_pending", no_active) is False
    assert GUARD._load(path)["total_blocks"] == 1


# --- the ladders have to be REACHABLE (measured brick, 2026-08-04) ---
#
# The escape ladders above were unreachable in the field, so the guard inflicted the
# exact brick they exist to prevent. Two independent causes, both about DETECTING the
# `SHIP LOOP BLOCKED:` report rather than about whether one is required:
#
#   1. `stop_hook_active` describes how the CURRENT turn was started, not whether the
#      guard has ever blocked. A background `<task-notification>` starting the turn
#      clears it. Session 787452b5 filed a correct token-leading report on live_stale
#      at count 5 and was refused on exactly that turn.
#   2. `last_assistant_message` is an UNDOCUMENTED payload field. This harness sends
#      it; a client that does not would make every report invisible.


def _transcript(tmp_path: Path, *messages, sidechain_tail: bool = False) -> Path:
    """A JSONL transcript ending in `messages` as assistant turns.

    Shaped like a real one: user rows, tool_result rows, and a thinking block ahead
    of the visible text, so the reader is exercised against the noise it must skip
    rather than a one-line fixture.
    """
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "transcript.jsonl"
    rows: list[dict] = [
        {"type": "user", "message": {"role": "user", "content": "ship it"}},
        {
            "type": "user",
            "message": {
                "role": "user",
                "content": [{"type": "tool_result", "content": "x" * 4096}],
            },
        },
    ]
    for text in messages:
        rows.append(
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "thinking", "thinking": "SHIP LOOP BLOCKED: not visible"},
                        {"type": "text", "text": text},
                    ],
                },
            }
        )
    if sidechain_tail:
        rows.append(
            {
                "type": "assistant",
                "isSidechain": True,
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "subagent finished"}],
                },
            }
        )
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    return path


def test_a_payload_supplied_report_is_still_the_source_of_truth(tmp_path, capsys):
    """(a) When the harness supplies `last_assistant_message`, nothing changes.

    The transcript is not consulted at all, proved by pointing at one whose final
    message says the OPPOSITE of the payload in both directions.
    """
    contradicting = _transcript(tmp_path, "done for now")
    path = _block_state(tmp_path)
    payload = {
        "stop_hook_active": True,
        "last_assistant_message": _REPORTED,
        "transcript_path": str(contradicting),
    }
    assert _drive_block(path, capsys, "render_pending", payload) is False
    assert _drive_block(path, capsys, "render_pending", payload) is True

    # Inverse: a payload message that is NOT the report keeps blocking even though
    # the transcript holds a valid one. A present message is never second-guessed.
    reporting = _transcript(tmp_path / "b", "SHIP LOOP BLOCKED: evidence")
    path = _block_state(tmp_path)
    unreported = {
        "stop_hook_active": True,
        "last_assistant_message": "still working on it",
        "transcript_path": str(reporting),
    }
    for _ in range(20):
        assert _drive_block(path, capsys, "render_pending", unreported) is False


def test_the_report_is_recovered_from_the_transcript_when_the_field_is_absent(tmp_path, capsys):
    """(b) No `last_assistant_message`, but the transcript's last assistant message
    starts with the token -> the ladder arms once the counters clear the ceiling."""
    path = _block_state(tmp_path)
    payload = {
        "stop_hook_active": True,
        "transcript_path": str(_transcript(tmp_path, "SHIP LOOP BLOCKED: live_stale, evidence")),
    }
    assert _drive_block(path, capsys, "render_pending", payload) is False
    assert _drive_block(path, capsys, "render_pending", payload) is True


def test_a_transcript_without_the_token_still_blocks(tmp_path, capsys):
    """(c) Recovering the message must not lower the bar: a transcript whose final
    assistant message is ordinary prose files no report and never escapes."""
    path = _block_state(tmp_path)
    payload = {
        "stop_hook_active": True,
        "transcript_path": str(
            _transcript(tmp_path, "SHIP LOOP BLOCKED: an earlier one", "all done, merged and live")
        ),
    }
    for _ in range(20):
        assert _drive_block(path, capsys, "render_pending", payload) is False
    assert GUARD._load(path)["total_blocks"] == 20


def test_an_unreadable_transcript_fails_closed(tmp_path, capsys):
    """(d) Missing, absent, or unparseable transcripts leave the report unfiled."""
    for transcript in (
        {},
        {"transcript_path": ""},
        {"transcript_path": str(tmp_path / "nope.jsonl")},
        {"transcript_path": str(tmp_path)},  # a directory
    ):
        path = _block_state(tmp_path)
        payload = {"stop_hook_active": True, **transcript}
        for _ in range(20):
            assert _drive_block(path, capsys, "render_pending", payload) is False

    corrupt = tmp_path / "corrupt.jsonl"
    corrupt.write_bytes(b"\x00not json\nalso not json\n")
    path = _block_state(tmp_path)
    payload = {"stop_hook_active": True, "transcript_path": str(corrupt)}
    for _ in range(20):
        assert _drive_block(path, capsys, "render_pending", payload) is False


def test_a_task_notification_turn_no_longer_vetoes_a_filed_report(tmp_path, capsys):
    """The measured brick. `stop_hook_active` is False on a turn a background
    `<task-notification>` started, even though the guard had already blocked. The
    guard's own ledger proves re-entrancy instead, so a filed report still counts."""
    path = _block_state(tmp_path)
    notification_turn = {"stop_hook_active": False, "last_assistant_message": _REPORTED}
    # First block: total_blocks == 1, so no arm can fire and no bailout is possible.
    assert _drive_block(path, capsys, "live_stale", notification_turn) is False
    # Second: external arm armed (count >= 2) and the ledger proves re-entrancy.
    assert _drive_block(path, capsys, "live_stale", notification_turn) is True


def test_the_ledger_never_widens_a_ladder_beyond_its_counters(tmp_path, capsys):
    """`total_blocks >= 2` cannot release anything the counters would not already
    allow: an INTERNAL code still has to reach its own far higher ceiling."""
    path = _block_state(tmp_path)
    notification_turn = {"stop_hook_active": False, "last_assistant_message": _REPORTED}
    for index in range(9):
        assert _drive_block(path, capsys, "unmerged", notification_turn) is False, index
    assert _drive_block(path, capsys, "unmerged", notification_turn) is True


def test_the_transcript_reader_skips_thinking_and_sidechain_rows(tmp_path):
    """A report has to be text the operator can read in the transcript. Reasoning the
    session never surfaced does not count, and a subagent's last word is not the
    session's — both would otherwise forge a report the session never filed."""
    thinking_only = _transcript(tmp_path, "ordinary closing text")
    assert not GUARD._transcript_final_message(
        {"transcript_path": str(thinking_only)}
    ).startswith("SHIP LOOP BLOCKED:")

    with_subagent = _transcript(
        tmp_path / "s", "SHIP LOOP BLOCKED: evidence", sidechain_tail=True
    )
    assert GUARD._transcript_final_message(
        {"transcript_path": str(with_subagent)}
    ).startswith("SHIP LOOP BLOCKED:")


def test_the_report_is_found_past_a_tool_result_larger_than_the_tail_window(tmp_path):
    """The tail window is an optimisation, not a cap. One pathological tool_result
    row bigger than the window must not hide the report behind it."""
    path = tmp_path / "huge.jsonl"
    rows = [
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "SHIP LOOP BLOCKED: behind a wall"}],
            },
        },
        {
            "type": "user",
            "message": {
                "role": "user",
                "content": [
                    {"type": "tool_result", "content": "y" * (GUARD._TRANSCRIPT_TAIL_BYTES + 4096)}
                ],
            },
        },
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    assert GUARD._transcript_final_message({"transcript_path": str(path)}).startswith(
        "SHIP LOOP BLOCKED:"
    )


def test_the_escape_hint_is_gated_by_proximity_to_the_ceiling(tmp_path, capsys):
    """A fresh internal block must NOT invite `SHIP LOOP BLOCKED:` — that offer is
    only made when an escape is plausibly one attempt away (external code, or an
    internal code near its ceiling). External codes always carry the hint."""
    path = _block_state(tmp_path)
    payload = {"stop_hook_active": True, "last_assistant_message": "still working"}

    GUARD._block(path, GUARD._load(path), payload, "unmerged", "no merged PR yet")
    reason = json.loads(capsys.readouterr().out.strip())["reason"]
    assert "SHIP LOOP BLOCKED:" not in reason, "a low-count internal block must not invite bailout"
    assert "Continue the task" in reason

    # An external code at count 1 DOES carry the hint (its ceiling is low).
    path = _block_state(tmp_path)
    GUARD._block(path, GUARD._load(path), payload, "render_pending", "still rendering")
    reason = json.loads(capsys.readouterr().out.strip())["reason"]
    assert "SHIP LOOP BLOCKED:" in reason


def test_the_escape_hint_appears_as_an_internal_code_nears_the_ceiling(tmp_path, capsys):
    """At consecutive count 9 (one below the 10 escape) the hint is offered."""
    path = _block_state(tmp_path)
    payload = {"stop_hook_active": True, "last_assistant_message": "still working"}
    for _ in range(8):
        GUARD._block(path, GUARD._load(path), payload, "unmerged", "no merged PR yet")
        capsys.readouterr()
    # The 9th block: count reaches 9, escape_hint arms, but the escape itself does not.
    GUARD._block(path, GUARD._load(path), payload, "unmerged", "no merged PR yet")
    reason = json.loads(capsys.readouterr().out.strip())["reason"]
    assert "SHIP LOOP BLOCKED:" in reason
    assert GUARD._load(path)["blocker_count"] == 9


def _guard_error_payload(**extra) -> dict:
    base = {"hook_event_name": "Stop"}
    base.update(extra)
    return base


def test_guard_error_routes_through_the_counters_and_escapes_at_the_ceiling(
    monkeypatch, tmp_path, capsys
):
    """A persistently crashing guard used to brick a session forever with no exit.

    `main()` now routes the Stop-event exception through `_block("guard_error", …)`,
    so the any-code ceiling can release it once the session files the report.
    guard_error is NOT external, so only the 10-consecutive / 15-total ladder frees
    it — never the low external one.
    """
    assert "guard_error" not in GUARD.EXTERNAL_BLOCKERS

    repo = _repo(tmp_path)
    state_path = GUARD._state_path(repo, {"session_id": "guard-error-test"})
    GUARD._save(
        state_path,
        {
            "root": str(repo),
            "start_head": _git(repo, "rev-parse", "HEAD"),
            "baseline": {},
            "last_blocker": "",
            "blocker_count": 0,
            "total_blocks": 0,
            "external_blocks": 0,
        },
    )

    monkeypatch.setattr(GUARD, "_repo_root", lambda _payload: repo)
    monkeypatch.setattr(GUARD, "_state_path", lambda _root, _payload: state_path)

    def explode(*_a, **_k):
        raise RuntimeError("the guard itself crashed")

    monkeypatch.setattr(GUARD, "_stop", explode)

    reported = _REPORTED
    payload = _guard_error_payload(stop_hook_active=True, last_assistant_message=reported)

    def run_once() -> str:
        monkeypatch.setattr(
            GUARD.sys, "stdin", type("S", (), {"read": staticmethod(lambda: json.dumps(payload))})()
        )
        monkeypatch.setattr(GUARD.json, "load", lambda _stream: payload)
        GUARD.main()
        return capsys.readouterr().out.strip()

    # First nine crashes are refused, and each increments the shared counters.
    for _ in range(9):
        out = run_once()
        emitted = json.loads(out)
        assert emitted["decision"] == "block"
        assert "guard_error" in emitted["reason"]
    assert GUARD._load(state_path)["blocker_count"] == 9

    # The tenth crash, with the report filed, is released by the any-code ceiling.
    assert run_once() == "", "a persistently crashing guard must be escapable at the ceiling"
    assert GUARD._load(state_path)["total_blocks"] == 10


def test_guard_error_falls_back_to_a_plain_block_when_state_cannot_load(monkeypatch, tmp_path):
    """If `_load` returns None (no state file), the plain guard_error block still fires."""
    repo = _repo(tmp_path)
    missing = tmp_path / "does-not-exist.json"
    monkeypatch.setattr(GUARD, "_repo_root", lambda _payload: repo)
    monkeypatch.setattr(GUARD, "_state_path", lambda _root, _payload: missing)
    monkeypatch.setattr(GUARD, "_stop", lambda *_a: (_ for _ in ()).throw(RuntimeError("boom")))

    payload = {"hook_event_name": "Stop"}
    monkeypatch.setattr(GUARD.json, "load", lambda _stream: payload)
    monkeypatch.setattr(GUARD.sys, "stdin", type("S", (), {"read": staticmethod(lambda: "{}")})())

    import io
    import contextlib

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        GUARD.main()
    emitted = json.loads(buffer.getvalue().strip())
    assert emitted["decision"] == "block"
    assert "guard_error" in emitted["reason"] and "boom" in emitted["reason"]


# --- an armed pull request is NOT an exit (operator ruling 2026-08-12) ---
#
# From 2026-07-28 to 2026-08-12 an open pull request carrying `merge-on-green`
# RELEASED the session at this gate: the sweeper owned the merge from there, and
# the worker printed a terminal marker and stopped. The operator removed the rule
# after it reported an unfinished job as complete — a session emitted the marker
# and declared itself done while its pull request sat `merge-blocked` on a red
# check, and the work had to be reopened by hand.
#
# The label still works and the sweeper may still perform the merge. What it can
# no longer do is end a session. `unmerged` is satisfied by an actually-merged
# pull request and by nothing else, so every test below asserts a BLOCK; the only
# question the armed pull request answers now is WHICH block, and with what detail.


def _pushed_unmerged_session(tmp_path: Path) -> tuple[Path, Path, str]:
    """A session that committed and pushed, with an upstream and no merged PR.

    This is the exact shape the armed-pull-request gate is judged in: without the
    upstream the `unpushed` gate answers first and the probe is never reached.
    """
    repo, state_path = _session_repo(tmp_path)
    bare = tmp_path / "origin.git"
    subprocess.run(("git", "init", "--bare", str(bare)), check=True, capture_output=True)
    _git(repo, "remote", "add", "origin", str(bare))
    _git(repo, "push", "-q", "-u", "origin", "claude/feature")
    return repo, state_path, _git(repo, "rev-parse", "HEAD")


def _armed_pr(head_sha: str, *, number=4242, labels=(GUARD.MERGE_ON_GREEN_LABEL,)) -> dict:
    return {
        "number": number,
        "head": {"sha": head_sha, "ref": "claude/feature"},
        "labels": [{"name": name} for name in labels],
    }


def _run_stub(name: str, status: str = "completed", conclusion=None) -> dict:
    return {"name": name, "status": status, "conclusion": conclusion}


#: Every check-run shape whose classification anyone has ever gotten wrong here,
#: plus the boundaries around them, and what `_split_head_runs` must answer for
#: each. One case would pin nothing — drift shows up at an edge.
_SPLIT_CASES = [
    ([], ([], [], [])),
    # The known-spurious Cloudflare X is dropped from every bucket, red included.
    ([_run_stub("Workers Builds: macro", conclusion="failure")], ([], [], [])),
    ([_run_stub("workers builds: MACRO (preview)", conclusion="failure")], ([], [], [])),
    (
        [_run_stub("Workers Builds: charting-app", conclusion="failure")],
        (["Workers Builds: charting-app (failure)"], [], []),
    ),
    ([_run_stub("ci-pack-1", conclusion="success")], ([], [], ["ci-pack-1"])),
    ([_run_stub("ci-pack-1", conclusion="failure")], (["ci-pack-1 (failure)"], [], [])),
    ([_run_stub("ci-pack-1", conclusion="cancelled")], (["ci-pack-1 (cancelled)"], [], [])),
    ([_run_stub("ci-pack-1", conclusion="timed_out")], (["ci-pack-1 (timed_out)"], [], [])),
    (
        [_run_stub("ci-pack-1", conclusion="action_required")],
        (["ci-pack-1 (action_required)"], [], []),
    ),
    # `completed` with no conclusion at all is not in NON_RED_CONCLUSIONS, so it is red.
    ([_run_stub("ci-pack-1", conclusion=None)], (["ci-pack-1 (None)"], [], [])),
    ([_run_stub("ci-pack-1", "queued")], ([], ["ci-pack-1"], [])),
    ([_run_stub("ci-pack-1", "in_progress")], ([], ["ci-pack-1"], [])),
    ([_run_stub("ci-pack-1", "waiting")], ([], ["ci-pack-1"], [])),
    # #4779: skipped/neutral are NOT failures, but they prove nothing either — they
    # land in no bucket, which is what makes an all-skipped head "unproven".
    ([_run_stub("Supabase Preview", conclusion="skipped")], ([], [], [])),
    ([_run_stub("Supabase Preview", conclusion="neutral")], ([], [], [])),
    ([_run_stub("a", conclusion="skipped"), _run_stub("b", conclusion="neutral")], ([], [], [])),
    ([_run_stub("a", conclusion="skipped"), _run_stub("b", "in_progress")], ([], ["b"], [])),
    ([_run_stub("a", conclusion="success"), _run_stub("b", conclusion="skipped")], ([], [], ["a"])),
    (
        [_run_stub("a", conclusion="failure"), _run_stub("b", "in_progress")],
        (["a (failure)"], ["b"], []),
    ),
    (
        [_run_stub("a", conclusion="failure"), _run_stub("b", conclusion="success")],
        (["a (failure)"], [], ["b"]),
    ),
    (
        [_run_stub("a", conclusion="failure"), _run_stub("b", conclusion="timed_out")],
        (["a (failure)", "b (timed_out)"], [], []),
    ),
    (
        [
            _run_stub("Workers Builds: macro", conclusion="failure"),
            _run_stub("ci-pack-2", "in_progress"),
        ],
        ([], ["ci-pack-2"], []),
    ),
    (
        [
            _run_stub("Supabase Preview", conclusion="skipped"),
            _run_stub("Workers Builds: macro", conclusion="failure"),
        ],
        ([], [], []),
    ),
    # Malformed payloads must classify, not crash: a Stop hook that tracebacks is
    # worse than one that blocks.
    (
        [{"name": None, "status": "completed", "conclusion": "failure"}],
        (["unnamed check (failure)"], [], []),
    ),
    ([{"status": "completed", "conclusion": "failure"}], (["unnamed check (failure)"], [], [])),
    ([{"name": "ci-pack-1"}], ([], ["ci-pack-1"], [])),
]


@pytest.mark.parametrize("runs,expected", _SPLIT_CASES, ids=range(len(_SPLIT_CASES)))
def test_split_head_runs_classifies_every_shape_that_has_ever_been_wrong(runs, expected):
    assert GUARD._split_head_runs(runs) == expected


def test_an_armed_pull_request_with_checks_pending_does_NOT_release_the_session(
    monkeypatch, tmp_path, capsys
):
    """THE NEW LAW, pinned. This test used to assert the exact opposite.

    Arming `merge-on-green` buys a merge the session does not have to perform. It
    does not end the session: until the pull request is MERGED, the work is not
    shipped, and a session that stops here reports an unfinished job as complete —
    measured, and the reason the release path was removed.
    """
    repo, state_path, head = _pushed_unmerged_session(tmp_path)
    monkeypatch.setattr(GUARD, "_github_slug", lambda _root: ("acme", "widgets"))
    monkeypatch.setattr(GUARD, "_latest_merged_pr", lambda *_a: None)
    monkeypatch.setattr(GUARD, "_open_pull", lambda *_a: _armed_pr(head))
    monkeypatch.setattr(
        GUARD, "_head_check_runs", lambda *_a: [_run_stub("ci-pack-1", "in_progress")]
    )

    GUARD._stop(repo, state_path, {"hook_event_name": "Stop"})

    raw = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert len(raw) == 1, f"stdout must stay a single JSON object, got {raw}"
    emitted = json.loads(raw[0])
    assert emitted["decision"] == "block", "an armed but unmerged PR must BLOCK"
    reason = emitted["reason"]
    assert "unmerged" in reason
    assert "#4242" in reason, "the block must name the pull request it is waiting on"
    assert "ci-pack-1" in reason, "and what it is waiting on"
    assert state_path.exists(), "a blocked session keeps its state file"
    # The old release path's machine receipt must not survive anywhere.
    assert "CI_HANDOFF" not in reason


def test_an_armed_pull_request_with_every_check_green_still_blocks(
    monkeypatch, tmp_path, capsys
):
    """Not even a clean head is an exit. The merge is the exit.

    A concluded-green armed head is precisely when the sweep is about to merge —
    which is exactly when leaving costs the least and proves the least. The session
    waits the one sweep out and verifies the merge.
    """
    repo, state_path, head = _pushed_unmerged_session(tmp_path)
    monkeypatch.setattr(
        GUARD, "_head_check_runs", lambda *_a: [_run_stub("ci-pack-1", conclusion="success")]
    )
    verdict = _stop_verdict(
        monkeypatch, capsys, repo, state_path, merged_pr=None, open_pull=_armed_pr(head)
    )
    assert verdict == "unmerged", f"green-but-unmerged must keep the session, got {verdict}"


def test_an_armed_pull_request_with_a_genuine_red_blocks_as_ci_failed(
    monkeypatch, tmp_path, capsys
):
    """The sweeper never merges a red, so nothing would pick this up.

    This is the failure the operator removed the release path over: the session
    called itself done while the pull request sat `merge-blocked`. Naming the red
    is the whole value of answering here instead of filing a bare `unmerged`.

    The code is asserted EXACTLY. `"ci_failed" in reason` was the original
    assertion and it is a substring of `ci_failed_unmerged`, so it could not tell
    the external code from the internal one — which is the only difference that
    decides whether this state has a 2-Stop exit.
    """
    repo, state_path, head = _pushed_unmerged_session(tmp_path)
    monkeypatch.setattr(
        GUARD,
        "_head_check_runs",
        lambda *_a: [
            _run_stub("ci-pack-1", conclusion="failure"),
            _run_stub("nav-gap", conclusion="success"),
        ],
    )
    monkeypatch.setattr(GUARD, "_github_slug", lambda _root: ("acme", "widgets"))
    monkeypatch.setattr(GUARD, "_latest_merged_pr", lambda *_a: None)
    monkeypatch.setattr(GUARD, "_open_pull", lambda *_a: _armed_pr(head))
    GUARD._stop(repo, state_path, {"hook_event_name": "Stop"})
    emitted = json.loads(capsys.readouterr().out.strip())
    assert emitted["decision"] == "block"
    code = emitted["reason"].split(":", 1)[0].split()[-1]
    assert code == GUARD.CI_FAILED_UNMERGED == "ci_failed_unmerged", (
        f"an UNMERGED head's own red must file the internal code, got {code!r}"
    )
    assert code != "ci_failed", "the external code belongs to the MERGED path only"
    assert "ci-pack-1 (failure)" in emitted["reason"], "naming the check is the point"
    assert "nav-gap" not in emitted["reason"], "a green check is not a red"


# --------------------------------------------------------------------------
# The unmerged red is INTERNAL, and the pre-merge path is base-side-aware.
#
# Two coupled properties, and they must land together. The first change on its own
# leaves the operator's exact reported failure with a 2-Stop exit; the second on
# its own would make a fleet-wide red main unstoppable for every session at once.
# --------------------------------------------------------------------------


def test_the_unmerged_red_code_is_not_an_external_blocker():
    """The membership IS the fix, so it is pinned as a fact, not only as behaviour.

    `ci_failed` is external because it describes a MERGED pull request whose red is
    pinned to a frozen merge ref the session may genuinely be unable to clear. A
    red on an UNMERGED armed head is the state this whole change exists to prevent
    being reported as done — alive session, armed PR, sweeper that will never merge
    it, head still pushable — so routing it through the external ladder would have
    made it the CHEAPEST state in the guard to leave.
    """
    assert GUARD.CI_FAILED_UNMERGED not in GUARD.EXTERNAL_BLOCKERS
    assert "ci_failed" in GUARD.EXTERNAL_BLOCKERS, "the merged path keeps its mercy exit"


def _block_run(state_path, code, *, attempts):
    """Drive `_block` `attempts` times with a valid report; return per-attempt blocks."""
    state = {
        "root": "/x",
        "start_head": "a" * 40,
        "baseline": {},
        "last_blocker": "",
        "blocker_count": 0,
        "total_blocks": 0,
        "external_blocks": 0,
    }
    payload = {
        "hook_event_name": "Stop",
        "stop_hook_active": True,
        "last_assistant_message": (
            "SHIP LOOP BLOCKED: ci-pack-2 is red on my armed PR #9999; evidence: run 123."
        ),
    }
    blocked = []
    for _ in range(attempts):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            GUARD._block(state_path, state, payload, code, "Failing CI on #9999: ci-pack-2.")
        blocked.append(bool(buffer.getvalue().strip()))
    return blocked


def test_an_unmerged_own_red_does_not_escape_on_the_second_stop(tmp_path):
    """THE regression this file exists to prevent, driven rather than read.

    Before the split, an unmerged armed PR's own red filed `ci_failed`, which is in
    `EXTERNAL_BLOCKERS`, whose ladder releases at 2 CONSECUTIVE blocks. So the
    operator's exact reported sequence — Stop, write `SHIP LOOP BLOCKED:`, Stop —
    ended the session with the pull request still sitting `merge-blocked` on the
    red. Measured on the pre-fix hook: `attempt 1: BLOCKED / attempt 2: RELEASED`.
    """
    state_path = tmp_path / "state.json"
    blocked = _block_run(state_path, GUARD.CI_FAILED_UNMERGED, attempts=3)
    assert blocked == [True, True, True], (
        "a red on an unmerged armed PR must not have a 2-Stop exit"
    )


def test_the_merged_path_keeps_its_two_stop_external_exit(tmp_path):
    """Control for the test above, so it cannot pass by the ladder being dead.

    `ci_failed` on a MERGED pull request is genuinely external — `gh run rerun`
    replays a frozen merge ref — and its 2-consecutive exit is deliberate. If this
    stops releasing, the split has broken the merged path instead of the pre-merge
    one.
    """
    state_path = tmp_path / "state.json"
    blocked = _block_run(state_path, "ci_failed", attempts=3)
    assert blocked[0] is True, "never a first-attempt bailout"
    assert blocked[1] is False, "the external ladder still releases at two"


def test_the_unmerged_red_still_reaches_the_any_code_loop_breaker(tmp_path):
    """Internal is not UNSTOPPABLE. The 10-consecutive ladder is kept intact.

    An unsatisfiable gate must never trap a session forever — that is what the
    any-code ceiling is for, and moving a code out of `EXTERNAL_BLOCKERS` must not
    take it out of reach.
    """
    state_path = tmp_path / "state.json"
    blocked = _block_run(state_path, GUARD.CI_FAILED_UNMERGED, attempts=12)
    assert blocked[:9] == [True] * 9, "nine refusals before the loop breaker arms"
    assert blocked[9] is False, "the any-code ladder releases at 10 consecutive"


_PRE_MERGE_RED_AT = "2026-08-13T03:00:00Z"
_MAIN_PROOF_AT = "2026-08-13T02:50:00Z"
_MAIN_PROOF_SHA = "f" * 40


def _job(name: str, conclusion, status: str = "completed") -> dict:
    return {"name": name, "status": status, "conclusion": conclusion}


def _main_proof_run(run_id: int, started: str = _MAIN_PROOF_AT) -> dict:
    return {
        "id": run_id,
        "head_sha": _MAIN_PROOF_SHA,
        "head_branch": "main",
        "status": "completed",
        "conclusion": "failure",
        "run_started_at": started,
        "created_at": started,
    }


def _fake_pre_merge_api(
    monkeypatch, *, main_runs=None, main_jobs=None, pr_runs=(), sibling_runs=None
) -> list:
    """Serve the endpoints `_base_side_pre_merge` reads, and record every URL.

    `main_runs`/`main_jobs` are keyed by workflow file name so a test can make
    ci.yml and fences.yml disagree. An unrouted URL asserts rather than returning a
    plausible empty payload — a silently-served endpoint would make the
    call-accounting assertions unfalsifiable.
    """
    urls: list = []
    main_runs = dict(main_runs or {})
    main_jobs = dict(main_jobs or {})
    siblings = dict(sibling_runs or {})

    def fake_get_json(url: str):
        urls.append(url)
        parts = urllib.parse.urlsplit(url)
        params = urllib.parse.parse_qs(parts.query)
        if parts.path.endswith("/jobs"):
            run_id = int(parts.path.rsplit("/runs/", 1)[1].split("/")[0])
            return {"jobs": list(main_jobs.get(run_id, ()))}
        if "/check-runs" in parts.path:
            sha = parts.path.split("/commits/", 1)[1].split("/")[0]
            return {"check_runs": list(siblings.get(sha, ()))}
        assert "/actions/workflows/" in parts.path, f"unexpected endpoint: {url}"
        workflow = parts.path.split("/actions/workflows/", 1)[1].split("/")[0]
        if params.get("branch") == ["main"]:
            return {"workflow_runs": list(main_runs.get(workflow, ()))}
        assert params.get("event") == ["pull_request"], f"unrouted listing: {url}"
        return {"workflow_runs": list(pr_runs)}

    monkeypatch.setattr(GUARD, "_get_json", fake_get_json)
    return urls


def _armed_verdict(monkeypatch, head_runs, *, branch="claude/feature", head="a" * 40):
    monkeypatch.setattr(GUARD, "_open_pull", lambda *_a: _armed_pr(head))
    monkeypatch.setattr(GUARD, "_head_check_runs", lambda *_a: list(head_runs))
    return GUARD._armed_pull_status("acme", "widgets", branch, head)


def test_a_red_main_is_currently_red_on_is_reported_as_inherited_not_as_yours(
    monkeypatch,
):
    """#5037's shape, on the PRE-merge path this time.

    A routine fleet-wide pack red used to tell every armed session in the fleet
    "Fix the cause and re-run the failed job" about a defect none of them wrote.
    Several then start healing one pack in parallel — and two partial heals of one
    pack can never both go green, because a pack is ONE check.
    """
    _fake_pre_merge_api(
        monkeypatch,
        main_runs={"ci.yml": (_main_proof_run(77),), "fences.yml": ()},
        main_jobs={77: (_job("ci-pack-3", "failure"), _job("nav-gap", "success"))},
    )
    code, detail = _armed_verdict(
        monkeypatch, [_check_run("ci-pack-3", "failure", _PRE_MERGE_RED_AT)]
    )
    assert code == "unmerged", f"main's red is not this session's defect, got {code}"
    assert "INHERITED FROM MAIN" in detail and "ci-pack-3" in detail
    assert "ci.yml run 77" in detail, "the block must cite the proof it read"
    assert "Fix the cause" not in detail, "there is nothing here for this session to fix"
    assert "--ref main" in detail, "and it must name main's lever"
    assert "instead of re-dispatching over it" in detail, "with the livelock preflight"


def test_the_inherited_verdict_still_blocks_and_is_not_an_external_blocker(monkeypatch):
    """An inherited red is a reclassification, never a release.

    The session still owns the pull request through the merge; only the ADVICE
    changes. `unmerged` is internal, so this cannot become a cheaper exit than the
    red it replaced.
    """
    _fake_pre_merge_api(
        monkeypatch,
        main_runs={"ci.yml": (_main_proof_run(77),), "fences.yml": ()},
        main_jobs={77: (_job("ci-pack-3", "failure"),)},
    )
    code, _ = _armed_verdict(
        monkeypatch, [_check_run("ci-pack-3", "failure", _PRE_MERGE_RED_AT)]
    )
    assert code == "unmerged" and code not in GUARD.EXTERNAL_BLOCKERS


def test_a_pre_merge_red_confirmed_on_two_sibling_heads_is_inherited(monkeypatch):
    """The second base-side source, when main itself has published no usable proof.

    Same bar as the merged path — two DISTINCT branches, because a pack name fronts
    many jobs and one sibling sharing it is a coincidence rather than a shared
    cause. The window differs: an unmerged head's content is on no shared base, so
    a sibling red AFTER ours is evidence too (on the merged path it could have had
    our merge as its cause, and is excluded).
    """
    sib_a_sha, sib_a_branch = _SIB_A
    sib_b_sha, sib_b_branch = _SIB_B
    after_ours = "2026-08-13T03:40:00Z"
    _fake_pre_merge_api(
        monkeypatch,
        main_runs={"ci.yml": (), "fences.yml": ()},
        pr_runs=(
            _pr_ci_run(1, _SIB_A, _PRE_MERGE_RED_AT, suite=_SUITE_A),
            _pr_ci_run(2, _SIB_B, after_ours, suite=_SUITE_B),
        ),
        sibling_runs={
            sib_a_sha: (_check_run("ci-pack-3", "failure", _PRE_MERGE_RED_AT, suite=_SUITE_A),),
            sib_b_sha: (_check_run("ci-pack-3", "failure", after_ours, suite=_SUITE_B),),
        },
    )
    code, detail = _armed_verdict(
        monkeypatch, [_check_run("ci-pack-3", "failure", _PRE_MERGE_RED_AT)]
    )
    assert code == "unmerged", f"two independent siblings is the bar, got {code}"
    assert sib_a_branch in detail and sib_b_branch in detail
    assert sib_a_sha[:7] in detail and sib_b_sha[:7] in detail


def test_a_lone_sibling_confirmation_keeps_the_pre_merge_red_as_yours(monkeypatch):
    """FAIL-CLOSED, and in the only direction that is safe.

    One sibling sharing a pack name is a coincidence. A guard that excused a red on
    it would hand every genuine regression a base-side alibi, which is strictly
    worse than telling one session to look at a red that turns out to be main's.
    """
    sib_a_sha, _ = _SIB_A
    _fake_pre_merge_api(
        monkeypatch,
        main_runs={"ci.yml": (), "fences.yml": ()},
        pr_runs=(_pr_ci_run(1, _SIB_A, _PRE_MERGE_RED_AT, suite=_SUITE_A),),
        sibling_runs={
            sib_a_sha: (_check_run("ci-pack-3", "failure", _PRE_MERGE_RED_AT, suite=_SUITE_A),),
        },
    )
    code, detail = _armed_verdict(
        monkeypatch, [_check_run("ci-pack-3", "failure", _PRE_MERGE_RED_AT)]
    )
    assert code == GUARD.CI_FAILED_UNMERGED, f"one witness is not two, got {code}"
    assert "ci-pack-3 (failure)" in detail


def test_a_stale_main_proof_cannot_excuse_todays_red(monkeypatch):
    """A three-day-old red main describes a base vintage that no longer exists.

    Without the staleness bound, one bad night on main would permanently excuse
    every future red carrying the same pack name — the guard would go blind in the
    shrink direction and nobody would see it happen.
    """
    long_ago = "2026-08-09T03:00:00Z"
    _fake_pre_merge_api(
        monkeypatch,
        main_runs={"ci.yml": (_main_proof_run(77, started=long_ago),), "fences.yml": ()},
        main_jobs={77: (_job("ci-pack-3", "failure"),)},
        pr_runs=(),
    )
    code, detail = _armed_verdict(
        monkeypatch, [_check_run("ci-pack-3", "failure", _PRE_MERGE_RED_AT)]
    )
    assert code == GUARD.CI_FAILED_UNMERGED, f"a stale proof proves nothing, got {code}"
    assert "ci-pack-3 (failure)" in detail


def test_only_failure_conclusions_are_base_side_excludable_pre_merge(monkeypatch):
    """A `cancelled` or `timed_out` check genuinely can green on a re-run.

    Same rule the merged path carries: those stay this session's to re-run, and
    they are not argued about with sibling heads at all.
    """
    _fake_pre_merge_api(
        monkeypatch,
        main_runs={"ci.yml": (_main_proof_run(77),), "fences.yml": ()},
        main_jobs={77: (_job("ci-pack-3", "failure"),)},
        pr_runs=(),
    )
    code, detail = _armed_verdict(
        monkeypatch,
        [
            _check_run("ci-pack-3", "failure", _PRE_MERGE_RED_AT),
            _check_run("ci-pack-1", "cancelled", _PRE_MERGE_RED_AT),
        ],
    )
    assert code == GUARD.CI_FAILED_UNMERGED, f"the cancelled check is still ours ({code})"
    assert "ci-pack-1 (cancelled)" in detail, "and it must still be named"
    assert "ci-pack-3 (failure)" not in detail.split("(Ignored as base-side")[0], (
        "the inherited red must not be re-blamed in the same breath"
    )
    assert "Ignored as base-side, inherited from main: ci-pack-3" in detail


def test_a_base_side_probe_that_raises_keeps_the_red_and_names_the_gap(monkeypatch):
    """FAIL-CLOSED on infrastructure, and never silently.

    An unanswerable probe is not evidence of innocence. The red stays this
    session's, and the reason says the evidence was unavailable — a swallowed
    exception here would read as "we checked and it is yours".
    """
    def boom(url: str):
        raise urllib.error.URLError("api down")

    monkeypatch.setattr(GUARD, "_get_json", boom)
    code, detail = _armed_verdict(
        monkeypatch, [_check_run("ci-pack-3", "failure", _PRE_MERGE_RED_AT)]
    )
    assert code == GUARD.CI_FAILED_UNMERGED
    assert "ci-pack-3 (failure)" in detail
    assert "Base-side evidence unavailable" in detail


def test_an_undated_red_spends_nothing_on_the_base_side_probe(monkeypatch):
    """No anchor means no proof could be accepted, so no call may be made.

    Every armed session in the fleet reaches this path at once under a red main.
    Calls that cannot change the verdict are pure waste on the shared 5,000/hr REST
    pool that `ship_loop_guard` itself fails CLOSED without.
    """
    urls = _fake_pre_merge_api(monkeypatch, main_runs={}, pr_runs=())
    code, detail = _armed_verdict(monkeypatch, [_run_stub("ci-pack-3", conclusion="failure")])
    assert code == GUARD.CI_FAILED_UNMERGED
    assert urls == [], f"an undated red must cost zero API calls, spent {urls}"
    assert "no start stamp" in detail, "and must say why it could not be argued about"


def test_the_pre_merge_probe_is_not_vacuous(monkeypatch):
    """Control: the probe must actually RUN, or every pin above passes by silence."""
    urls = _fake_pre_merge_api(
        monkeypatch,
        main_runs={"ci.yml": (_main_proof_run(77),), "fences.yml": ()},
        main_jobs={77: (_job("something-else", "failure"),)},
        pr_runs=(),
    )
    code, _ = _armed_verdict(
        monkeypatch, [_check_run("ci-pack-3", "failure", _PRE_MERGE_RED_AT)]
    )
    assert code == GUARD.CI_FAILED_UNMERGED, "a name main is green on stays ours"
    assert any("/actions/workflows/ci.yml/runs" in url for url in urls), "main proof read"
    assert any(url.endswith("/jobs?per_page=100") for url in urls), "its jobs read"
    assert any("event=pull_request" in url for url in urls), "siblings read"


def test_a_clean_head_never_spends_a_base_side_call(monkeypatch):
    """Evidence is only ever gathered to argue about a red — same rule as `_check_ci`.

    A green or pending armed head is the COMMON case on every Stop of every armed
    session; paying for a base-side probe there would multiply the fleet's REST
    burn by the number of live sessions for no verdict change.
    """
    urls = _fake_pre_merge_api(monkeypatch, main_runs={}, pr_runs=())
    code, _ = _armed_verdict(monkeypatch, [_check_run("ci-pack-3", "success")])
    assert code == "unmerged"
    assert urls == [], f"a clean head must cost nothing extra, spent {urls}"


def test_a_spurious_only_red_is_not_a_red_but_is_still_not_a_merge(
    monkeypatch, tmp_path, capsys
):
    """`Workers Builds: macro` is the known-spurious X on both sides of the merge.

    It must not read as `ci_failed` — and the session must still not stop, because
    the pull request is not merged.
    """
    repo, state_path, head = _pushed_unmerged_session(tmp_path)
    monkeypatch.setattr(
        GUARD,
        "_head_check_runs",
        lambda *_a: [
            _run_stub("Workers Builds: macro", conclusion="failure"),
            _run_stub("ci-pack-2", "in_progress"),
        ],
    )
    verdict = _stop_verdict(
        monkeypatch, capsys, repo, state_path, merged_pr=None, open_pull=_armed_pr(head)
    )
    assert verdict == "unmerged", f"spurious is not a red, but nor is it a merge ({verdict})"


def test_an_armed_pull_request_with_no_check_runs_blocks_and_says_why(
    monkeypatch, tmp_path, capsys
):
    """A paths-filtered docs-only PR is unproven, and the sweeper will never merge it.

    An absence of red is not a pass (#4779). The block has to say so, or the
    session waits out a sweep that is never coming.
    """
    repo, state_path, head = _pushed_unmerged_session(tmp_path)
    monkeypatch.setattr(GUARD, "_head_check_runs", lambda *_a: [])
    monkeypatch.setattr(GUARD, "_github_slug", lambda _root: ("acme", "widgets"))
    monkeypatch.setattr(GUARD, "_latest_merged_pr", lambda *_a: None)
    monkeypatch.setattr(GUARD, "_open_pull", lambda *_a: _armed_pr(head))
    GUARD._stop(repo, state_path, {"hook_event_name": "Stop"})
    emitted = json.loads(capsys.readouterr().out.strip())
    assert "unmerged" in emitted["reason"]
    assert "no sweep will ever merge it" in emitted["reason"]


def test_an_open_pull_request_without_the_label_is_not_probed(monkeypatch, tmp_path, capsys):
    """An unlabeled PR costs no check-run listing: the ordinary `unmerged` block
    already says everything true about it, and the REST pool is shared."""
    repo, state_path, head = _pushed_unmerged_session(tmp_path)
    monkeypatch.setattr(
        GUARD, "_head_check_runs", lambda *_a: pytest.fail("an unlabeled PR must not be probed")
    )
    verdict = _stop_verdict(
        monkeypatch,
        capsys,
        repo,
        state_path,
        merged_pr=None,
        open_pull=_armed_pr(head, labels=("enhancement",)),
    )
    assert verdict == "unmerged"


def test_an_armed_pull_request_on_a_stale_head_is_not_probed(monkeypatch, tmp_path, capsys):
    """The armed head must be THIS work. A force-moved branch reaches here with a
    clean ahead-count, and its older head's checks describe a different tree."""
    repo, state_path, _head = _pushed_unmerged_session(tmp_path)
    monkeypatch.setattr(
        GUARD, "_head_check_runs", lambda *_a: pytest.fail("a stale head must not be probed")
    )
    verdict = _stop_verdict(
        monkeypatch,
        capsys,
        repo,
        state_path,
        merged_pr=None,
        open_pull=_armed_pr("f" * 40),
    )
    assert verdict == "unmerged", f"a stale armed head must keep the session, got {verdict}"


def test_a_failing_pull_request_probe_falls_through_to_the_normal_block(
    monkeypatch, tmp_path, capsys
):
    """Fail-closed: an API failure in the probe never releases a session.

    The external escape ladder in `_block` already covers a persistently broken
    API, so the probe itself has no business inventing a second exit.
    """
    repo, state_path, _head = _pushed_unmerged_session(tmp_path)
    monkeypatch.setattr(GUARD, "_github_slug", lambda _root: ("acme", "widgets"))
    monkeypatch.setattr(GUARD, "_latest_merged_pr", lambda *_a: None)

    def exploding(*_args):
        raise RuntimeError("pull listing exploded")

    monkeypatch.setattr(GUARD, "_open_pull", exploding)
    GUARD._stop(repo, state_path, {"hook_event_name": "Stop"})
    emitted = json.loads(capsys.readouterr().out.strip())
    assert emitted["decision"] == "block"
    assert "unmerged" in emitted["reason"]


def test_no_stop_path_can_emit_a_terminal_release_marker():
    """The retired release path printed a machine receipt a controller parsed as
    "this worker is done", and loaded a now-deleted contract module by file path.

    One lowercase substring covers both, and covers them in every casing anyone
    would reintroduce them in. Asserted against the hook's SOURCE rather than
    against a call, because the danger is a path that only fires in production.
    """
    source = (ROOT / ".claude" / "hooks" / "ship_loop_guard.py").read_text(encoding="utf-8")
    assert "handoff" not in source.lower()


@pytest.mark.parametrize(
    "name,spurious",
    [
        ("Workers Builds: macro", True),
        ("workers builds: MACRO (preview)", True),
        ("WORKERS BUILDS: macro-dashboard", True),
        ("Workers Builds: charting-app", False),
        ("Cloudflare Workers Builds", False),
        ("macro", False),
        ("ci-pack-1", False),
        ("", False),
        ("unnamed check", False),
    ],
)
def test_the_spurious_check_rule_is_deliberately_narrow(name, spurious):
    """Widening this allowlist is a RULING, not a refactor — a broadened predicate
    waves a REAL red through as noise. `scripts/merge_on_green.py` carries the same
    literal; the two must move together or not at all.

    The hook holds its own copy on purpose: it is loaded by file path and may not
    acquire the application import graph to answer one string question.
    """
    assert GUARD._is_spurious_check(name) is spurious


def test_the_sweeper_and_the_hook_still_agree_on_the_spurious_check():
    """The one place a copy is dangerous: the sweeper decides what gets MERGED and
    the hook decides what pins a session. Read the sweeper's predicate out of its
    own source and compare — a divergence here strands work in exactly one
    direction (the hook releases, the sweeper refuses, the PR sits forever).
    """
    spec = importlib.util.spec_from_file_location(
        "_test_merge_on_green", ROOT / "scripts" / "merge_on_green.py"
    )
    assert spec and spec.loader
    sweeper_module = importlib.util.module_from_spec(spec)
    sys.modules["_test_merge_on_green"] = sweeper_module
    spec.loader.exec_module(sweeper_module)

    for name in (
        "Workers Builds: macro",
        "workers builds: MACRO (preview)",
        "WORKERS BUILDS: macro-dashboard",
        "Workers Builds: charting-app",
        "Cloudflare Workers Builds",
        "macro",
        "ci-pack-1",
        "",
    ):
        assert GUARD._is_spurious_check(name) is bool(
            sweeper_module.is_spurious_check(name)
        ), name


def test_check_ci_holds_the_non_red_conclusions_literal(monkeypatch, tmp_path):
    """`_check_ci` reads the module's own NON_RED_CONCLUSIONS. It used to read the
    deleted contract's copy, with a literal fallback; the literal is now the only
    definition, and an empty set here would read `success` itself as a red and
    block every merged session on the planet."""
    assert GUARD.NON_RED_CONCLUSIONS == frozenset({"success", "neutral", "skipped"})
    monkeypatch.setattr(
        GUARD,
        "_head_check_runs",
        lambda *_a: [
            _run_stub("ci-pack-1", conclusion="success"),
            _run_stub("legacy", conclusion="skipped"),
            _run_stub("third-party", conclusion="neutral"),
        ],
    )
    assert GUARD._check_ci(tmp_path, "acme", "widgets", "a" * 40, "b" * 40, "", "") == (True, "")


def test_settings_wire_session_start_and_stop():
    settings = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    hooks = settings["hooks"]
    assert "SessionStart" in hooks
    assert "Stop" in hooks
    commands = json.dumps(hooks)
    assert "ship_loop_guard.py" in commands


def test_ui_contract_separates_scores_from_axis_labels():
    source = (ROOT / "templates" / "dashboard.html.j2").read_text(encoding="utf-8")
    assert "container: risk-dialog / inline-size" in source
    assert 'class="rkc-mood-score"' in source
    assert 'class="rkc-mood-axis rsx-axis-labels"' in source
    assert "rkc-mood-flag" not in source
    assert "@container risk-dialog (max-width:520px)" in source


# ── merge artifacts are not competing verdicts (2026-08-15) ──────────────────
#
# Merging fires `pull_request: closed`, and ci.yml's concurrency block deliberately
# starts a ZERO-RUNNER replacement for it. So every cleanly merged head carries two
# ci-gate check-runs: the real concluded one, plus a `skipped` artifact created 12-15s
# later BY the merge. Counting the artifact as a second opinion raised
# "links multiple latest ci-gate workflow runs" on every merged head and blocked the
# authoring session from stopping on work that had merged GREEN — with no session-side
# remedy, because merged check-runs are immutable and `gh run rerun` preserves the run id.

def _gate(run_id: int, conclusion: str) -> dict:
    return {
        "name": "ci-gate",
        "conclusion": conclusion,
        "details_url": f"https://github.com/o/r/actions/runs/{run_id}/job/1",
    }


def test_skipped_merge_artifact_does_not_make_evidence_ambiguous(monkeypatch):
    """The real shape of merged PR #5754 head c02fc9eac6e8."""
    seen: dict = {}

    def _fake_get_json(url: str):
        seen["url"] = url
        raise AssertionError("stop after run resolution")

    monkeypatch.setattr(GUARD, "_get_json", _fake_get_json)
    runs = [_gate(31887298300, "success"), _gate(31889718105, "skipped")]
    with pytest.raises(AssertionError, match="stop after run resolution"):
        GUARD._semantic_evidence_for_head("o", "r", "c02fc9eac6e8", check_runs=runs)
    # It resolved the DECISIVE run, not the merge artifact, and did not raise ambiguity.
    assert "31887298300" in seen["url"]


def test_two_decisive_ci_gates_still_raise_ambiguity():
    """Fail-closed is preserved: two real conclusions remain irreconcilable."""
    runs = [_gate(111, "success"), _gate(222, "failure")]
    with pytest.raises(Exception, match="multiple latest ci-gate workflow runs"):
        GUARD._semantic_evidence_for_head("o", "r", "deadbeefcafe", check_runs=runs)


def test_only_skipped_ci_gates_do_not_resolve_to_a_run(monkeypatch):
    """A head whose ONLY gate is skipped has no usable evidence — never a fake pass."""
    called: dict = {"n": 0}

    def _fake_get_json(url: str):
        called["n"] += 1
        raise AssertionError("must not resolve a run from skipped-only evidence")

    monkeypatch.setattr(GUARD, "_get_json", _fake_get_json)
    runs = [_gate(333, "skipped"), _gate(444, "skipped")]
    # Two skipped ids remain ambiguous rather than silently choosing one.
    with pytest.raises(Exception, match="multiple latest ci-gate workflow runs"):
        GUARD._semantic_evidence_for_head("o", "r", "0123456789ab", check_runs=runs)
    assert called["n"] == 0


# ── a merged head cannot bind its own proof base (2026-08-15) ────────────────
#
# GitHub drops `pull_requests` from check-runs once the PR closes — measured on #5754's
# ci-gate: `n_prs: 0` on BOTH entries — so `_semantic_pr_base_sha` returns None for every
# merged head and the loader refused with "does not identify the exact PR proof base".
# Same trap shape as the skipped-gate artifact: no session-side repair exists. The merged
# pull request record still carries the authoritative base, so `_check_ci` threads it in.

def _capture_base(monkeypatch):
    seen: dict = {}

    def _fake_loader(owner, repo, head_sha, *, check_runs=None, expected_base_sha=None):
        seen["expected_base_sha"] = expected_base_sha
        raise RuntimeError("stop after base binding")

    monkeypatch.setattr(GUARD, "_semantic_evidence_for_head", _fake_loader)
    monkeypatch.setattr(GUARD, "_head_can_advertise_semantic_evidence", lambda runs: True)
    monkeypatch.setattr(
        GUARD,
        "_head_check_runs",
        lambda owner, repo, sha: [
            {"name": "ci-pack-1", "status": "completed", "conclusion": "failure"}
        ],
    )
    return seen


def test_merged_head_binds_its_proof_base_from_the_pull_request(monkeypatch, tmp_path):
    """No association metadata survives the merge — the PR record is the fallback."""
    seen = _capture_base(monkeypatch)
    monkeypatch.setattr(GUARD, "_semantic_pr_base_sha", lambda *a, **k: None)
    GUARD._check_ci(tmp_path, "o", "r", "head", "merge", "2026-08-15T14:22:11Z",
                    "claude/x", "b9473646cfba")
    assert seen["expected_base_sha"] == "b9473646cfba"


def test_check_run_bound_base_still_wins_over_the_pull_request_record(monkeypatch, tmp_path):
    """The immutable, event-frozen base outranks the mutable PR record wherever it exists."""
    seen = _capture_base(monkeypatch)
    monkeypatch.setattr(GUARD, "_semantic_pr_base_sha", lambda *a, **k: "aaaaaaaaaaaa")
    GUARD._check_ci(tmp_path, "o", "r", "head", "merge", "2026-08-15T14:22:11Z",
                    "claude/x", "b9473646cfba")
    assert seen["expected_base_sha"] == "aaaaaaaaaaaa"


def test_absent_base_everywhere_stays_none_rather_than_empty_string(monkeypatch, tmp_path):
    """Fail-closed: an unbindable base must read as absent, never as a falsy base."""
    seen = _capture_base(monkeypatch)
    monkeypatch.setattr(GUARD, "_semantic_pr_base_sha", lambda *a, **k: None)
    GUARD._check_ci(tmp_path, "o", "r", "head", "merge", "2026-08-15T14:22:11Z",
                    "claude/x", "")
    assert seen["expected_base_sha"] is None


# ── the merged-PR fallback must actually HAVE a base to fall back to (2026-08-16) ──
#
# The three tests above prove `_check_ci` threads its `base_sha` argument through to
# the semantic loader. What they cannot see is where `_stop` gets that argument from,
# and there the fix above shipped DEAD ON ARRIVAL: #3746 had already narrowed the
# cached `merged_pull` record to "only the fields the remaining gates consume", and
# `base` was not among them. So #5757's fallback read a key that no longer existed,
# `str((pull.get("base") or {}).get("sha") or "")` was ALWAYS `""`, and every merged
# head advertising semantic evidence refused with "does not identify the exact PR
# proof base" — `ci_failed` at Stop on work that had merged green, fleet-wide.
#
# Measured on PR #5769 (merged 2026-08-16T02:43:09Z): run 31921385097 concluded
# `success` with `prs: []`, while `/pulls/5769` still carried its authoritative base
# c2484fe7134b63b8acba50471396edf9929d20a3. The data was there the whole time; only
# the narrowing lost it.

_PROOF_BASE_SHA = "e" * 40


def _merged_pr_api_record() -> dict:
    """The `/pulls` shape GitHub returns for a merged pull request, unnarrowed."""
    return {
        "number": 5769,
        "head": {"sha": "a" * 40, "ref": "claude/feature", "label": "acme:claude/feature"},
        "base": {"sha": _PROOF_BASE_SHA, "ref": "main", "label": "acme:main"},
        "merge_commit_sha": "b" * 40,
        "merged_at": "2026-08-16T02:43:09Z",
        "_links": {"self": {"href": "https://api.github.com/repos/acme/widgets/pulls/5769"}},
    }


def _merged_pr_stop(monkeypatch, repo, state_path, *, merged_pr, ci_calls: list):
    """Drive one Stop over a merged pull request, capturing the CI gate's arguments.

    It halts at a pending render on purpose: a CLEAN stop unlinks the state file,
    and the remembered `merged_pull` proof is half of what these tests assert on.
    """
    monkeypatch.setattr(GUARD, "_github_slug", lambda _root: ("acme", "widgets"))
    monkeypatch.setattr(GUARD, "_latest_merged_pr", lambda *_a: merged_pr())
    monkeypatch.setattr(
        GUARD, "_check_ci", lambda *args: (ci_calls.append(args), (True, ""))[1]
    )
    monkeypatch.setattr(GUARD, "_needs_render", lambda *_a: True)
    monkeypatch.setattr(
        GUARD, "_render_status", lambda *_a: ("pending", "Render workflow is queued.")
    )
    _stub_remote_git(monkeypatch)
    GUARD._stop(repo, state_path, {"hook_event_name": "Stop"})


def test_narrowed_merged_pull_record_keeps_the_semantic_proof_base(
    monkeypatch, tmp_path, capsys
):
    """#3746's narrowing dropped the exact field #5757's merged-head fallback reads.

    The record `_stop` caches and hands to `_check_ci` must still carry `base.sha`,
    because a merged head has no surviving PR association to bind its proof base
    with. Assert the VALUE, not the key: a base of `None` reads as `""` at the call
    site and is the same always-empty fallback the defect shipped.
    """
    repo, state_path = _session_repo(tmp_path)
    ci_calls: list = []

    _merged_pr_stop(
        monkeypatch, repo, state_path, merged_pr=_merged_pr_api_record, ci_calls=ci_calls
    )
    capsys.readouterr()

    assert ci_calls, "the CI gate never ran"
    # `_check_ci(root, owner, repo, head_sha, merge_sha, merged_at, head_ref, base_sha)`
    assert ci_calls[0][-1] == _PROOF_BASE_SHA
    value = json.loads(state_path.read_text(encoding="utf-8"))["ship_proofs"]["merged_pull"][
        "value"
    ]
    assert value["base"] == {"sha": _PROOF_BASE_SHA}
    # Still narrowed: the state file must not grow the rest of the API payload.
    assert set(value) == {"number", "head", "base", "merge_commit_sha", "merged_at"}


def test_cached_merged_pull_proof_without_a_base_is_refetched_not_reused(
    monkeypatch, tmp_path, capsys
):
    """The cache, not the API, is what a re-blocked session reads.

    #3746 narrowed the record; #5757 then wired the merged-head proof base to a key
    that narrowing had already dropped. Keeping the field is only half the repair —
    the proof is keyed by branch+head, and neither moves again after a merge, so a
    session that already remembered the pre-fix shape would stay pinned forever on
    its own stale record.
    """
    repo, state_path = _session_repo(tmp_path)
    head = _git(repo, "rev-parse", "HEAD")
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["ship_proofs"] = {
        "merged_pull": {
            "key": f"claude/feature:{head}",
            # The exact pre-fix narrowing, verbatim: no `base` at all.
            "value": {
                "number": 5769,
                "head": {"sha": "a" * 40, "ref": "claude/feature"},
                "merge_commit_sha": "b" * 40,
                "merged_at": "2026-08-16T02:43:09Z",
            },
        }
    }
    GUARD._save(state_path, state)
    ci_calls: list = []
    fetches = {"n": 0}

    def refetched() -> dict:
        fetches["n"] += 1
        return _merged_pr_api_record()

    _merged_pr_stop(monkeypatch, repo, state_path, merged_pr=refetched, ci_calls=ci_calls)
    capsys.readouterr()

    assert fetches["n"] == 1, "the stale cache shape was reused instead of refetched"
    assert ci_calls and ci_calls[0][-1] == _PROOF_BASE_SHA
    # And the refetch re-remembers the complete shape, so the next Stop is a cache hit.
    value = json.loads(state_path.read_text(encoding="utf-8"))["ship_proofs"]["merged_pull"][
        "value"
    ]
    assert value["base"] == {"sha": _PROOF_BASE_SHA}


def test_merged_head_stop_binds_its_proof_base_with_no_pr_associations_left(
    monkeypatch, tmp_path, capsys
):
    """End to end on the real post-merge shape: `prs: []` on the run, base on the PR.

    This is the live block that exposed the defect (PR #5769). The run carries no
    `pull_requests` entries, so `_semantic_pr_base_sha` returns None and the merged
    pull request record is the ONLY source of the proof base. With the narrowing
    dropping it, `_semantic_evidence_for_run` refused with "does not identify the
    exact PR proof base"; with it kept, the base binds and evaluation continues to
    the next honest refusal (an expired artifact here, which is strictly PAST the
    base binding — that is what makes it evidence the base bound at all).
    """
    repo, state_path = _session_repo(tmp_path)
    head_sha = "a" * 40
    seen: dict = {}
    real_for_run = GUARD._semantic_evidence_for_run

    def spy(owner, repo_name, run, *, role, expected_base_sha=None):
        seen["expected_base_sha"] = expected_base_sha
        return real_for_run(owner, repo_name, run, role=role, expected_base_sha=expected_base_sha)

    def router(url: str):
        if url.endswith("/actions/runs/31921385097"):
            return {
                "id": 31921385097,
                "name": "ci",
                "path": ".github/workflows/ci.yml",
                "event": "pull_request",
                "head_sha": head_sha,
                "conclusion": "success",
                "pull_requests": [],  # GitHub drops these once the PR closes.
            }
        if url.endswith("/actions/runs/31921385097/artifacts?per_page=100"):
            return {
                "total_count": 1,
                "artifacts": [
                    {
                        "name": f"{GUARD.SEMANTIC_ARTIFACT_PREFIX}31921385097",
                        "archive_download_url": "https://api.github.com/artifact.zip",
                        "expired": True,
                    }
                ],
            }
        raise AssertionError(f"unexpected API call: {url}")

    monkeypatch.setattr(GUARD, "_github_slug", lambda _root: ("acme", "widgets"))
    monkeypatch.setattr(GUARD, "_latest_merged_pr", lambda *_a: _merged_pr_api_record())
    monkeypatch.setattr(
        GUARD,
        "_head_check_runs",
        lambda *_a: [
            {"name": "ci-pack-3", "status": "completed", "conclusion": "failure"},
            {
                "name": "ci-gate",
                "status": "completed",
                "conclusion": "success",
                "details_url": (
                    "https://github.com/acme/widgets/actions/runs/31921385097/job/1"
                ),
                "pull_requests": [],
            },
        ],
    )
    monkeypatch.setattr(GUARD, "_semantic_evidence_for_run", spy)
    monkeypatch.setattr(GUARD, "_get_json", router)
    _stub_remote_git(monkeypatch)

    GUARD._stop(repo, state_path, {"hook_event_name": "Stop"})

    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.strip()]
    blocks = [line for line in lines if line.get("decision") == "block"]
    assert blocks, lines
    reason = blocks[0]["reason"]
    assert seen.get("expected_base_sha") == _PROOF_BASE_SHA, reason
    assert "does not identify the exact PR proof base" not in reason
    assert "advertised semantic artifact is expired" in reason


# ── evergreen bootstrap: execute the evaluated worktree's guard (#hardening) ─
#
# Settings.json launches this file from $CLAUDE_PROJECT_DIR (the primary
# checkout). The tree being evaluated is a linked worktree. The executing copy
# must become a one-shot bootstrap into that worktree's own hook, or fail closed
# as hook_source_mismatch — never a misleading ci_failed from stale primary code.


_STUB_HOOK = """\
import json, os, sys
from pathlib import Path
raw = sys.stdin.buffer.read()
receipt = os.environ.get("SHIP_LOOP_STUB_RECEIPT")
if receipt:
    Path(receipt).write_bytes(raw)
sys.stdout.write(json.dumps({
    "stub": True,
    "file": __file__,
    "delegated": os.environ.get("SHIP_LOOP_GUARD_DELEGATED"),
    "cwd": os.getcwd(),
}))
"""


def _git_repo_at(path: Path) -> Path:
    path.mkdir(parents=True)
    _git(path, "init", "-b", "main")
    _git(path, "config", "user.name", "Test")
    _git(path, "config", "user.email", "test@example.com")
    (path / "kept.txt").write_text("baseline\n", encoding="utf-8")
    _git(path, "add", "kept.txt")
    _git(path, "commit", "-m", "initial")
    return path


def _linked_worktrees(tmp_path: Path) -> tuple[Path, Path]:
    primary = _git_repo_at(tmp_path / "primary")
    worktree = tmp_path / "worktree"
    _git(primary, "worktree", "add", str(worktree))
    return primary.resolve(), worktree.resolve()


def _install_stub_hook(root: Path) -> Path:
    target = root / ".claude" / "hooks" / "ship_loop_guard.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_STUB_HOOK, encoding="utf-8")
    return target


def test_repo_root_prefers_payload_cwd_over_project_dir(monkeypatch, tmp_path):
    primary = _git_repo_at(tmp_path / "primary")
    session = _git_repo_at(tmp_path / "session")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(primary))
    monkeypatch.chdir(primary)
    found = GUARD._repo_root({"cwd": str(session)})
    assert found.resolve() == session.resolve()


def test_same_source_and_evaluated_root_does_not_delegate(monkeypatch, tmp_path):
    repo = _git_repo_at(tmp_path / "repo")
    _install_stub_hook(repo)
    spawned: list[Path] = []
    monkeypatch.setattr(GUARD, "_hook_source_root", lambda: repo)
    monkeypatch.setattr(
        GUARD,
        "_spawn_delegated_guard",
        lambda target, raw, *, cwd: spawned.append(target) or 0,
    )
    payload = {"cwd": str(repo), "hook_event_name": "Stop"}
    assert GUARD._delegate_to_evaluated_hook(payload, b"{}") is False
    assert spawned == []


def test_delegated_child_receives_original_payload_and_runs_once(
    monkeypatch, tmp_path, capsys
):
    primary, worktree = _linked_worktrees(tmp_path)
    _install_stub_hook(worktree)
    monkeypatch.setattr(GUARD, "_hook_source_root", lambda: primary)
    receipt = tmp_path / "payload.bin"
    monkeypatch.setenv("SHIP_LOOP_STUB_RECEIPT", str(receipt))
    raw = b'{"cwd":"SESSION","hook_event_name":"Stop","keep":[1,2],"x":"y"}'
    payload = {"cwd": str(worktree), "hook_event_name": "Stop"}
    assert GUARD._delegate_to_evaluated_hook(payload, raw) is True
    assert receipt.read_bytes() == raw
    emitted = json.loads(capsys.readouterr().out)
    assert emitted["stub"] is True
    assert emitted["delegated"] == "1"
    assert Path(emitted["file"]).resolve() == (
        worktree / ".claude" / "hooks" / "ship_loop_guard.py"
    ).resolve()

    monkeypatch.setenv(GUARD.DELEGATION_ENV, "1")
    assert GUARD._delegate_to_evaluated_hook(payload, raw) is False


def test_missing_target_hook_fails_closed_as_source_mismatch(
    monkeypatch, tmp_path, capsys
):
    primary, worktree = _linked_worktrees(tmp_path)
    monkeypatch.setattr(GUARD, "_hook_source_root", lambda: primary)
    payload = {"cwd": str(worktree), "hook_event_name": "Stop"}
    assert GUARD._delegate_to_evaluated_hook(payload, b"{}") is True
    emitted = json.loads(capsys.readouterr().out)
    assert emitted["decision"] == "block"
    reason = emitted["reason"]
    assert "hook_source_mismatch" in reason
    assert "ci_failed" not in reason
    assert str(primary) in reason
    assert str(worktree) in reason
    assert "target hook unavailable" in reason


def test_malformed_target_hook_fails_closed_as_source_mismatch(
    monkeypatch, tmp_path, capsys
):
    primary, worktree = _linked_worktrees(tmp_path)
    target = worktree / ".claude" / "hooks" / "ship_loop_guard.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("def oops(\n", encoding="utf-8")
    monkeypatch.setattr(GUARD, "_hook_source_root", lambda: primary)
    payload = {"cwd": str(worktree), "hook_event_name": "Stop"}
    assert GUARD._delegate_to_evaluated_hook(payload, b"{}") is True
    emitted = json.loads(capsys.readouterr().out)
    assert emitted["decision"] == "block"
    assert "hook_source_mismatch" in emitted["reason"]
    assert "target hook malformed" in emitted["reason"]
    assert "ci_failed" not in emitted["reason"]


@pytest.mark.parametrize("failure", ["missing", "malformed", "spawn", "nonzero"])
def test_watcher_delegation_failure_emits_an_enforceable_pretool_denial(
    monkeypatch, tmp_path, capsys, failure
):
    """Once a Bash command is classified as a watcher, evaluated-tree
    delegation is part of admission. A diagnostic systemMessage is not an
    admission decision and therefore must never fail open."""
    primary, worktree = _linked_worktrees(tmp_path)
    target = worktree / ".claude" / "hooks" / "ship_loop_guard.py"
    if failure != "missing":
        _install_stub_hook(worktree)
    if failure == "malformed":
        target.write_text("def broken(\n", encoding="utf-8")
    monkeypatch.setattr(GUARD, "_hook_source_root", lambda: primary)
    if failure == "spawn":
        monkeypatch.setattr(
            GUARD,
            "_spawn_delegated_guard",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
        )
    elif failure == "nonzero":
        monkeypatch.setattr(GUARD, "_spawn_delegated_guard", lambda *_a, **_k: 19)
    payload = _watcher_payload("gh run watch 123 --exit-status")
    payload["cwd"] = str(worktree)
    assert GUARD._delegate_to_evaluated_hook(payload, b"{}") is True
    emitted = json.loads(capsys.readouterr().out.splitlines()[-1])
    verdict = emitted["hookSpecificOutput"]
    assert verdict["hookEventName"] == "PreToolUse"
    assert verdict["permissionDecision"] == "deny"
    assert "hook_source_mismatch" in verdict["permissionDecisionReason"]


def test_nonzero_watcher_delegate_cannot_precede_the_denial_with_child_stdout(
    monkeypatch, tmp_path, capsys
):
    """Hook stdout is one JSON value. A crashing evaluated child may have
    printed before exiting; that partial output must not mask the parent's
    enforceable fail-closed decision."""
    primary, worktree = _linked_worktrees(tmp_path)
    _install_stub_hook(worktree)
    monkeypatch.setattr(GUARD, "_hook_source_root", lambda: primary)
    monkeypatch.setattr(GUARD, "_repo_root", lambda _payload: worktree)
    monkeypatch.setattr(GUARD, "_same_git_repository", lambda *_args: True)
    monkeypatch.setattr(GUARD, "_short_head", lambda _root: "abc123")
    monkeypatch.setattr(
        GUARD.subprocess,
        "run",
        lambda *_args, **_kwargs: type(
            "Proc",
            (),
            {
                "returncode": 23,
                "stdout": b'{"systemMessage":"partial child output"}\n',
                "stderr": b"child traceback\n",
            },
        )(),
    )
    payload = _watcher_payload("gh run watch 123 --exit-status")
    payload["cwd"] = str(worktree)
    assert GUARD._delegate_to_evaluated_hook(payload, b"{}") is True
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 1
    verdict = json.loads(lines[0])["hookSpecificOutput"]
    assert verdict["permissionDecision"] == "deny"


def test_unrelated_tmp_repo_is_not_a_source_mismatch(monkeypatch, tmp_path, capsys):
    """Existing main() tests use disposable git repos that are not this clone."""
    other = _git_repo_at(tmp_path / "other")
    monkeypatch.setattr(GUARD, "_hook_source_root", lambda: GUARD._REPOSITORY_ROOT)
    payload = {"cwd": str(other), "hook_event_name": "Stop"}
    assert GUARD._delegate_to_evaluated_hook(payload, b"{}") is False
    assert capsys.readouterr().out == ""


# --------------------------------------------------------------------------
# A slow `git status` must not become a WEDGED checkout (observed 2026-08-19):
# 161s wall at 10% CPU on a full worktree, a 90s budget, a SIGKILLed git, and a
# zero-byte `index.lock` left in the worktree gitdir by the very guard that was
# only reading the tree.
# --------------------------------------------------------------------------


def _sleeper(marker: Path | None) -> str:
    """A child that sleeps; with a marker it records the signal that ended it."""
    if marker is None:
        return (
            "import signal, time\n"
            "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
            "time.sleep(30)\n"
        )
    return (
        "import signal, sys, time\n"
        "def _bye(signum, _frame):\n"
        f"    open({str(marker)!r}, 'w').write(str(signum))\n"
        "    sys.exit(0)\n"
        "signal.signal(signal.SIGTERM, _bye)\n"
        "time.sleep(30)\n"
    )


def test_a_timed_out_child_is_asked_to_leave_before_it_is_shot(tmp_path):
    """SIGKILL is the reason a timed-out status orphaned a lock at all.

    git installs a SIGTERM handler precisely so its lock files are unlinked on
    the way out; SIGKILL cannot be caught, so the lock outlives its owner and
    every later git in that tree fails on it. The marker is proof the child was
    signalled rather than shot — it can only be written from inside a handler.
    """
    marker = tmp_path / "signal.txt"
    # 3s, not 1s: the child has to finish interpreter startup and install its
    # handler before the budget expires, and a 4-core runner under fleet load is
    # exactly where a tight budget would turn this into a flake.
    with pytest.raises(subprocess.TimeoutExpired):
        GUARD._run(tmp_path, sys.executable, "-c", _sleeper(marker), timeout=3)
    assert marker.exists(), "the child was shot before it could handle a signal"
    assert marker.read_text() == str(int(signal.SIGTERM))


def test_a_child_that_ignores_sigterm_is_still_killed(monkeypatch, tmp_path):
    """The grace period is a courtesy, not a hostage clause.

    The child sleeps 30s and ignores SIGTERM, so anything that waits for it to
    leave voluntarily blows the hook's own wall. Escalation has to be certain.
    """
    monkeypatch.setattr(GUARD, "GIT_TERM_GRACE_SECONDS", 1)
    started = time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired):
        GUARD._run(tmp_path, sys.executable, "-c", _sleeper(None), timeout=1)
    assert time.monotonic() - started < 10


def _timeout_always(_root, *args, timeout):
    raise subprocess.TimeoutExpired(list(args), timeout)


def test_a_status_timeout_is_retried_once_on_the_index_the_first_pass_warmed(
    monkeypatch, tmp_path
):
    """161s cold, 13s warm: the first run PAYS FOR the second (2026-08-19).

    Failing on the first timeout threw that warm-up away and filed `guard_error`
    against a tree that was one cheap re-run from answering.
    """
    budgets: list[int] = []
    swept: list[Path] = []

    def fake_run_raw(_root, *args, timeout):
        assert args[:2] == ("git", "status")
        budgets.append(timeout)
        if len(budgets) == 1:
            raise subprocess.TimeoutExpired(list(args), timeout)
        return "?? warm.txt\n"

    monkeypatch.setattr(GUARD, "_run_raw", fake_run_raw)
    monkeypatch.setattr(GUARD, "_sweep_stale_index_lock", lambda root: swept.append(root))

    assert GUARD._status_output(tmp_path) == "?? warm.txt\n"
    assert budgets == [
        GUARD.STATUS_TIMEOUT_SECONDS,
        GUARD.STATUS_RETRY_TIMEOUT_SECONDS,
    ]
    assert budgets[1] > budgets[0], "the retry must get a LONGER budget, not the same one"
    assert swept == [tmp_path], "the retry must not trip over our own wreckage"


def test_a_status_that_cannot_answer_twice_still_fails_closed(monkeypatch, tmp_path):
    """The retry buys a second chance to ANSWER, never permission to skip.

    Both timeout paths sweep, because a lock this guard orphaned outlives the
    process that made it: the second sweep is for the NEXT invocation, which
    would otherwise inherit a tree this one wedged.
    """
    swept: list[Path] = []
    monkeypatch.setattr(GUARD, "_run_raw", _timeout_always)
    monkeypatch.setattr(GUARD, "_sweep_stale_index_lock", lambda root: swept.append(root))

    with pytest.raises(subprocess.TimeoutExpired):
        GUARD._fingerprint(tmp_path)
    assert swept == [tmp_path, tmp_path]


def test_an_unanswerable_status_reaches_stop_as_a_block(monkeypatch, tmp_path, capsys):
    """Fail-closed end to end: an unresolvable dirty check still refuses Stop."""
    repo = _repo(tmp_path)
    state_path = GUARD._state_path(repo, {"session_id": "status-timeout"})
    GUARD._save(
        state_path,
        {
            "root": str(repo),
            "start_head": _git(repo, "rev-parse", "HEAD"),
            "baseline": {},
            "last_blocker": "",
            "blocker_count": 0,
            "total_blocks": 0,
            "external_blocks": 0,
        },
    )
    monkeypatch.setattr(GUARD, "_repo_root", lambda _payload: repo)
    monkeypatch.setattr(GUARD, "_state_path", lambda _root, _payload: state_path)
    monkeypatch.setattr(GUARD, "_run_raw", _timeout_always)
    monkeypatch.setattr(GUARD, "_sweep_stale_index_lock", lambda _root: None)

    payload = {"hook_event_name": "Stop", "session_id": "status-timeout"}
    monkeypatch.setattr(
        GUARD.sys,
        "stdin",
        type("S", (), {"read": staticmethod(lambda: json.dumps(payload))})(),
    )
    monkeypatch.setattr(GUARD.json, "load", lambda _stream: payload)
    GUARD.main()

    emitted = json.loads(capsys.readouterr().out)
    assert emitted["decision"] == "block"
    assert "guard_error" in emitted["reason"]


def test_the_whole_pathological_status_path_fits_the_hooks_own_wall():
    """A budget past the harness's wall is a budget that cannot conclude.

    `.claude/settings.json` owns the wall and the HARNESS enforces it: a hook
    cancelled mid-flight emits no decision at all, so overrunning it trades a
    block for a silently skipped Stop evaluation — a fail-OPEN, strictly worse
    than the block it was trying to file.

    The sum is the WHOLE worst path, not just the two status attempts: the sweeps
    and every SIGTERM grace are on it too, and leaving them out is how a budget
    that looks like it fits does not. Pinned here because the numbers live in a
    different file from the wall and nothing else would notice them drifting.
    """
    settings = json.loads(
        (ROOT / ".claude" / "settings.json").read_text(encoding="utf-8")
    )
    walls = [
        int(hook["timeout"])
        for entry in settings["hooks"]["Stop"]
        for hook in entry["hooks"]
        if "ship_loop_guard.py" in hook.get("command", "")
    ]
    assert walls, "the Stop hook must still be the ship loop guard"

    grace = GUARD.GIT_TERM_GRACE_SECONDS
    probe = GUARD.SWEEP_PROBE_TIMEOUT_SECONDS
    first_sweep = probe + grace + probe  # resolve the gitdir, then lsof
    later_sweep = probe  # the gitdir is cached by then, so lsof only
    # The heal runs AFTER the status is read (never between the attempts — see
    # `test_the_heal_runs_only_after_the_status_it_could_contaminate`), but it is
    # on the worst path either way: read the config, test the filesystem, write it.
    heal = (
        probe
        + grace
        + GUARD.UNTRACKED_CACHE_TEST_TIMEOUT_SECONDS
        + grace
        + probe
        + grace
    )
    worst = (
        GUARD.STATUS_TIMEOUT_SECONDS
        + grace
        + first_sweep
        + GUARD.STATUS_RETRY_TIMEOUT_SECONDS
        + grace
        + later_sweep
        + heal
    )
    assert worst <= min(walls), (
        "the pathological status path must still reach its own guard_error block: "
        f"{worst}s of a {min(walls)}s wall"
    )
    # The costlier shape is the one that SUCCEEDS. A retry answering just under its
    # budget still owes the whole rest of `_stop` — PR lookup, CI attribution (up to
    # ~16 REST calls when there is a red to attribute), render coverage, live checks
    # — and a wall sized flush to `worst` would cancel the hook mid-evaluation there,
    # which fails OPEN. This is the residual that makes that path survivable, not
    # slack to be reclaimed by a later budget rise.
    answered = (
        GUARD.STATUS_TIMEOUT_SECONDS
        + grace
        + first_sweep
        + GUARD.STATUS_RETRY_TIMEOUT_SECONDS
        + heal
    )
    assert min(walls) - answered >= 60, (
        "a retry that ANSWERS must leave the rest of the Stop evaluation room to "
        f"run: {min(walls) - answered}s left of a {min(walls)}s wall"
    )
    # MATERIALLY larger, not merely larger. The retry has to finish the part of the
    # walk the warm-up pass never reached, so a retry sized like the first attempt
    # is the exact arithmetic that failed twice: 60/70 could not answer a 78s tree,
    # and 100/150 could not answer the 333s one (2026-08-21). Both attempts sitting
    # under the cold cost is a pair that can never succeed however often it runs.
    assert (
        GUARD.STATUS_RETRY_TIMEOUT_SECONDS >= 2 * GUARD.STATUS_TIMEOUT_SECONDS
    ), "the retry must be able to absorb a cold walk the first attempt could not"


# --------------------------------------------------------------------------
# A tree too slow to READ must be repaired, not merely retried (2026-08-21):
# 333s cold `status` on 75,427 index entries with `core.untrackedCache` unset,
# against 1s warm. The retry budget lets that Stop answer; the untracked cache is
# what stops the next one from having to.
# --------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_untracked_cache_heal(monkeypatch):
    """The heal is once-per-process; tests must not inherit a sibling's attempt."""
    monkeypatch.setattr(GUARD, "_UNTRACKED_CACHE_HEAL_TRIED", False)


def _heal_capture(calls: list[tuple[str, ...]], codes: dict[str, int]):
    """A `_capture` stand-in recording the heal's git calls and faking their rc."""

    def fake_capture(_root, args, timeout):
        calls.append(tuple(args))
        for key, code in codes.items():
            if key in args:
                return subprocess.CompletedProcess(list(args), code, "", "")
        return subprocess.CompletedProcess(list(args), 0, "", "")

    return fake_capture


def test_a_timed_out_status_enables_the_untracked_cache(monkeypatch, tmp_path):
    """The blown first budget is the evidence that this tree is too slow to read.

    A healthy checkout never reaches that line, so the timeout is a well-targeted
    trigger: the heal costs nothing on every tree that answers in time.
    """
    calls: list[tuple[str, ...]] = []
    # `--get` returns 1 (unset), the filesystem test passes, the write succeeds.
    monkeypatch.setattr(GUARD, "_capture", _heal_capture(calls, {"--get": 1}))

    budgets: list[int] = []

    def fake_run_raw(_root, *args, timeout):
        budgets.append(timeout)
        if len(budgets) == 1:
            raise subprocess.TimeoutExpired(list(args), timeout)
        return ""

    monkeypatch.setattr(GUARD, "_run_raw", fake_run_raw)
    monkeypatch.setattr(GUARD, "_sweep_stale_index_lock", lambda _root: None)

    assert GUARD._status_output(tmp_path) == ""
    assert calls == [
        ("git", "config", "--get", "core.untrackedCache"),
        ("git", "update-index", "--test-untracked-cache"),
        ("git", "config", "core.untrackedCache", "true"),
    ], "the heal must test the filesystem BEFORE it writes the config"


def test_a_status_that_answers_first_time_never_pays_for_the_heal(
    monkeypatch, tmp_path
):
    """The trigger is a blown budget, not "every Stop".

    Without this, moving the heal ahead of the first attempt would pass every
    other test in this block while charging ~6s and an `index.lock` take to every
    healthy tree in the fleet, on every Stop.
    """
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(GUARD, "_capture", _heal_capture(calls, {"--get": 1}))
    monkeypatch.setattr(GUARD, "_run_raw", lambda _root, *args, timeout: "?? a.txt\n")

    assert GUARD._status_output(tmp_path) == "?? a.txt\n"
    assert calls == [], "a tree that answers in time must not be probed at all"


def test_the_heal_runs_only_after_the_status_it_could_contaminate(
    monkeypatch, tmp_path
):
    """Ordering is load-bearing: the mtime test writes INTO the worktree root.

    `--test-untracked-cache` builds `mtime-test-XXXXXX/` in the working directory
    and a killed one leaves it behind (measured). Run between the two attempts, the
    retry would report `?? mtime-test-XXXXXX/newfile` and the guard would file a
    false `uncommitted` block naming a file it created itself. Reading status first
    means even a failed cleanup cannot contaminate this invocation's answer.
    """
    order: list[str] = []

    def fake_run_raw(_root, *args, timeout):
        order.append("status")
        if len(order) == 1:
            raise subprocess.TimeoutExpired(list(args), timeout)
        return ""

    monkeypatch.setattr(GUARD, "_run_raw", fake_run_raw)
    monkeypatch.setattr(GUARD, "_sweep_stale_index_lock", lambda _root: None)
    monkeypatch.setattr(
        GUARD, "_enable_untracked_cache", lambda _root: order.append("heal") or True
    )

    GUARD._status_output(tmp_path)
    assert order == ["status", "status", "heal"], (
        "the heal must not run between the two status attempts"
    )


def _mtime_scratch(root: Path, name: str = "mtime-test-abc123") -> Path:
    """The scratch tree a killed `--test-untracked-cache` leaves in the worktree."""
    scratch = root / name
    (scratch / "new-dir").mkdir(parents=True)
    (scratch / "newfile").write_text("", encoding="utf-8")
    (scratch / "new-dir" / "new").write_text("", encoding="utf-8")
    return scratch


def test_a_killed_mtime_test_does_not_leave_dirt_the_guard_would_block_on(
    monkeypatch, tmp_path
):
    """The guard must never file `uncommitted` against a file the guard created."""
    repo = _repo(tmp_path)
    scratch = repo / "mtime-test-abc123"

    def fake_capture(_root, args, _timeout):
        if "--test-untracked-cache" in args:
            # git creates its scratch tree, then is killed before removing it.
            _mtime_scratch(repo, scratch.name)
            raise subprocess.TimeoutExpired(list(args), 20)
        return subprocess.CompletedProcess(list(args), 1 if "--get" in args else 0, "", "")

    monkeypatch.setattr(GUARD, "_capture", fake_capture)
    monkeypatch.setattr(GUARD, "_sweep_stale_index_lock", lambda _root: None)

    assert GUARD._enable_untracked_cache(repo) is False
    assert not scratch.exists(), "a timed-out mtime test must clean up after itself"
    assert "mtime-test" not in GUARD._status_output(repo)


def test_the_scratch_cleanup_refuses_anything_it_did_not_recognise(tmp_path):
    """It deletes inside somebody's worktree, so every doubt keeps the directory.

    An unexpected `mtime-test-*` is far better reported as dirt than removed on a
    guess — a wrong delete here is silent data loss in a tree somebody is using.
    """
    repo = _repo(tmp_path)

    # Real shape, but already present when the call started: somebody else's.
    old = _mtime_scratch(repo, "mtime-test-old123")
    # Right shape, but carries a file git never writes.
    extra = _mtime_scratch(repo, "mtime-test-xtra12")
    (extra / "mine.txt").write_text("precious", encoding="utf-8")
    # Wrong name shape entirely.
    unrelated = repo / "mtime-test-not-git"
    unrelated.mkdir()
    (unrelated / "newfile").write_text("", encoding="utf-8")

    GUARD._remove_mtime_test_scratch(repo, GUARD._mtime_test_scratches(repo))
    assert old.exists(), "a directory that predates the call is not ours to remove"

    # Now with an empty snapshot: everything above counts as having appeared.
    GUARD._remove_mtime_test_scratch(repo, set())
    assert extra.exists(), "an unrecognised entry must keep the whole directory"
    assert (extra / "mine.txt").read_text(encoding="utf-8") == "precious"
    assert unrelated.exists(), "only git's own glob shape is ever removed"
    assert not old.exists(), "the exact shape, newly appeared, IS removed"


def test_a_real_killed_mtime_test_is_cleaned_up(tmp_path):
    """End to end against real git: a SIGTERMed mtime test leaves a real scratch.

    The mocked tests above construct the leftover by hand, so they cannot catch a
    glob or entry-name that drifts from what git actually writes.
    """
    repo = _repo(tmp_path)
    before = GUARD._mtime_test_scratches(repo)
    proc = subprocess.Popen(
        ("git", "update-index", "--test-untracked-cache"),
        cwd=repo,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(3)  # long enough for the scratch tree to exist
    proc.terminate()
    proc.wait(timeout=30)
    assert list(repo.glob("mtime-test-*")), "git should have left its scratch behind"

    GUARD._remove_mtime_test_scratch(repo, before)
    assert not list(repo.glob("mtime-test-*"))
    assert "mtime-test" not in GUARD._status_output(repo)


def test_the_untracked_cache_heal_never_overwrites_a_configured_value(
    monkeypatch, tmp_path
):
    """rc 0 means somebody already decided this, in either direction.

    An operator who set `false` did so deliberately, and this hook is a dirty
    check, not a config manager. Only git's specific "unset" (rc 1) is permission.
    """
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(GUARD, "_capture", _heal_capture(calls, {"--get": 0}))

    assert GUARD._enable_untracked_cache(tmp_path) is False
    assert calls == [("git", "config", "--get", "core.untrackedCache")]


@pytest.mark.parametrize("rc", [2, 128])
def test_an_unreadable_untracked_cache_setting_is_never_interpreted(
    monkeypatch, tmp_path, rc
):
    """Neither 0 nor 1: an erroring `git config` is not evidence the key is unset."""
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(GUARD, "_capture", _heal_capture(calls, {"--get": rc}))

    assert GUARD._enable_untracked_cache(tmp_path) is False
    assert calls == [("git", "config", "--get", "core.untrackedCache")]


def test_a_filesystem_that_fails_the_mtime_test_never_gets_the_cache(
    monkeypatch, tmp_path
):
    """Enabling it on unreliable mtimes would make `status` LIE — a fail-OPEN.

    The untracked cache trusts directory mtimes to decide a directory is
    unchanged. Where they are not reliable, git would skip the directory and the
    session's new untracked files would simply not appear in the dirty check this
    whole hook exists to make. Saving the test's ~6s would buy a fast wrong answer.
    """
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(
        GUARD,
        "_capture",
        _heal_capture(calls, {"--get": 1, "--test-untracked-cache": 1}),
    )

    assert GUARD._enable_untracked_cache(tmp_path) is False
    assert ("git", "config", "core.untrackedCache", "true") not in calls


def test_a_failed_heal_still_leaves_the_retry_its_full_budget(monkeypatch, tmp_path):
    """The heal is an optimisation; it must never become why the retry is skipped."""

    def exploding_capture(_root, _args, _timeout):
        raise OSError("git is not on PATH")

    monkeypatch.setattr(GUARD, "_capture", exploding_capture)

    budgets: list[int] = []

    def fake_run_raw(_root, *args, timeout):
        budgets.append(timeout)
        if len(budgets) == 1:
            raise subprocess.TimeoutExpired(list(args), timeout)
        return "?? warm.txt\n"

    monkeypatch.setattr(GUARD, "_run_raw", fake_run_raw)
    monkeypatch.setattr(GUARD, "_sweep_stale_index_lock", lambda _root: None)

    assert GUARD._status_output(tmp_path) == "?? warm.txt\n"
    assert budgets == [
        GUARD.STATUS_TIMEOUT_SECONDS,
        GUARD.STATUS_RETRY_TIMEOUT_SECONDS,
    ]


def test_the_untracked_cache_heal_is_attempted_only_once_per_process(
    monkeypatch, tmp_path
):
    """Its answer cannot change mid-run, and re-learning it costs ~6s each time."""
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(GUARD, "_capture", _heal_capture(calls, {"--get": 1}))

    assert GUARD._enable_untracked_cache(tmp_path) is True
    first = len(calls)
    assert GUARD._enable_untracked_cache(tmp_path) is False
    assert len(calls) == first, "the second attempt must not re-run the git calls"


def test_the_heal_really_enables_the_untracked_cache_on_a_real_repository(tmp_path):
    """End to end against real git: the mocks above cannot prove the rc contract.

    Every other test in this block fakes `_capture`, so a wrong subcommand name or
    a misread exit code would pass all of them. This one pays the real
    `--test-untracked-cache` (~6s, dominated by its own mtime-granularity sleeps)
    to pin that the three invocations are the ones git actually implements.
    """
    repo = _repo(tmp_path)
    unset = GUARD._capture(repo, ("git", "config", "--get", "core.untrackedCache"), 30)
    assert unset.returncode == 1, "git's 'this key is unset' rc is what the heal reads"

    enabled = GUARD._enable_untracked_cache(repo)
    if not enabled:
        pytest.skip("this filesystem does not support git's untracked cache")
    assert (
        GUARD._run(repo, "git", "config", "--get", "core.untrackedCache", timeout=30)
        == "true"
    )
    # The dirty check must still see everything it saw before the heal.
    (repo / "fresh.txt").write_text("x", encoding="utf-8")
    assert "fresh.txt" in GUARD._status_output(repo)


def _orphaned_lock(repo: Path) -> Path:
    """The zero-byte `index.lock` a SIGKILLed git leaves in the worktree gitdir."""
    lock = Path(GUARD._run(repo, "git", "rev-parse", "--absolute-git-dir")) / "index.lock"
    lock.write_bytes(b"")
    return lock


@pytest.mark.skipif(
    shutil.which("lsof") is None, reason="the unheld half of the check needs lsof"
)
def test_the_sweep_removes_a_zero_byte_lock_this_guard_orphaned(tmp_path):
    """The damage is measured in `git add`, not `git status`.

    A stale lock leaves `status` working — it simply declines to write the
    refreshed index — so the wedge is invisible until the session tries to
    COMMIT, which is the very next thing the ship loop asks of it.
    """
    repo = _repo(tmp_path)
    lock = _orphaned_lock(repo)
    (repo / "shipped.txt").write_text("work\n", encoding="utf-8")
    with pytest.raises(subprocess.CalledProcessError):
        _git(repo, "add", "shipped.txt")

    assert GUARD._sweep_stale_index_lock(repo) == lock
    assert not lock.exists()
    _git(repo, "add", "shipped.txt")
    assert "A  shipped.txt" in _git(repo, "status", "--porcelain")


def test_the_sweep_keeps_a_lock_that_predates_this_process(monkeypatch, tmp_path):
    """Only OUR killed git's lock is ours to remove.

    Moving the guard's start AHEAD of the lock is how a pre-existing lock looks
    from inside the sweep — the operator's, a sibling session's, or one from an
    earlier crash nobody has diagnosed yet.
    """
    repo = _repo(tmp_path)
    lock = _orphaned_lock(repo)
    monkeypatch.setattr(GUARD, "_GUARD_STARTED_AT", time.time() + 60)
    assert GUARD._sweep_stale_index_lock(repo) is None
    assert lock.exists()


def test_the_sweep_keeps_a_lock_a_live_process_still_holds(tmp_path):
    """Zero-byte AND newer than the guard, so only `lsof` separates this one.

    A git that has just created its lock and not yet written the new index looks
    exactly like our wreckage on disk. Deleting it is silent index corruption in
    a tree somebody is using.
    """
    repo = _repo(tmp_path)
    lock = _orphaned_lock(repo)
    with lock.open("w"):
        assert GUARD._sweep_stale_index_lock(repo) is None
    assert lock.exists()


def test_the_sweep_keeps_a_lock_git_has_written_an_index_into(tmp_path):
    repo = _repo(tmp_path)
    lock = _orphaned_lock(repo)
    lock.write_bytes(b"DIRC")
    assert GUARD._sweep_stale_index_lock(repo) is None
    assert lock.exists()


def test_the_sweep_never_reaches_past_a_worktree_into_the_clone(tmp_path):
    """A linked worktree has its OWN index; the primary's lock is never ours.

    `--git-common-dir` — the question `_git_common_dir` asks for delegation —
    would point every session in the clone at the primary checkout's lock file.
    """
    repo = _repo(tmp_path)
    linked = tmp_path / "linked"
    _git(repo, "worktree", "add", "-b", "claude/linked", str(linked))

    resolved = GUARD._worktree_index_lock(linked)
    assert resolved is not None
    assert resolved.resolve() == (
        repo / ".git" / "worktrees" / "linked" / "index.lock"
    ).resolve()
    assert resolved.resolve() != (repo / ".git" / "index.lock").resolve()


@pytest.mark.parametrize(
    "returncode, stdout, stderr, held",
    [
        (1, "", "", False),  # the ONLY free answer: quiet on every channel
        (0, "COMMAND  PID  USER  FD  TYPE\ngit  4242  chriswong  4w  REG\n", "", True),
        (1, "", "lsof: status error on /x/index.lock: Permission denied\n", True),
        (2, "", "", True),  # an exit code lsof does not document
    ],
)
def test_only_a_silent_lsof_proves_a_lock_is_free(
    monkeypatch, returncode, stdout, stderr, held
):
    """`lsof` exits 1 for "nobody has it" AND for its own errors.

    Reading the exit code alone would let a malformed invocation — a `--` an old
    build does not take, an unreadable path — certify a LIVE git's lock as free,
    and the sweep would then delete the index out from under it.
    """
    monkeypatch.setattr(
        GUARD.subprocess,
        "run",
        lambda *_a, **_k: subprocess.CompletedProcess((), returncode, stdout, stderr),
    )
    assert GUARD._lock_is_held(Path("/nonexistent/index.lock")) is held


def test_an_lsof_that_cannot_run_at_all_reads_as_held(monkeypatch):
    """Linux runners need not ship `lsof`; absence is not evidence of absence."""

    def absent(*_a, **_k):
        raise FileNotFoundError("lsof")

    monkeypatch.setattr(GUARD.subprocess, "run", absent)
    assert GUARD._lock_is_held(Path("/nonexistent/index.lock")) is True


def test_the_gitdir_probe_is_paid_once_not_once_per_sweep(monkeypatch, tmp_path):
    """The second sweep runs past a SECOND blown budget, with no room to spare.

    Re-resolving the gitdir there is how the pathological path would overrun the
    wall `test_the_whole_pathological_status_path_fits_the_hooks_own_wall` pins.
    """
    repo = _repo(tmp_path)
    probes: list[tuple] = []
    real_run = GUARD._run

    def counting_run(root, *args, **kwargs):
        if "rev-parse" in args:
            probes.append(args)
        return real_run(root, *args, **kwargs)

    monkeypatch.setattr(GUARD, "_run", counting_run)
    first = GUARD._worktree_index_lock(repo)
    second = GUARD._worktree_index_lock(repo)
    assert first == second is not None
    assert len(probes) == 1, "the gitdir must be resolved once per root, not per sweep"


def test_an_unresolvable_gitdir_is_remembered_as_unresolvable(monkeypatch, tmp_path):
    """Caching the FAILURE matters as much as caching the answer.

    A tree whose git cannot answer is the same tree on the second sweep, and the
    retry path has no budget to ask again.
    """
    calls: list[int] = []

    def refuse(_root, *_args, **_kwargs):
        calls.append(1)
        raise RuntimeError("git is unreadable")

    monkeypatch.setattr(GUARD, "_run", refuse)
    assert GUARD._worktree_index_lock(tmp_path) is None
    assert GUARD._worktree_index_lock(tmp_path) is None
    assert len(calls) == 1
    assert GUARD._sweep_stale_index_lock(tmp_path) is None


# ── ship-watcher quiescence after terminal states (Sol commission #6379) ─────
#
# A leftover background task's completion starts a NEW turn via
# `<task-notification>` (reproduced live 2026-08-24), and that turn's Stop
# re-enters this guard. Terminal states must therefore be REMEMBERED: a
# ratified external ladder exit passes the wake silently, exactly as the
# merged-head ci_failed exit has since 2026-08-19, while internal codes keep
# the full-priced loop breaker (Journey C, byte-unchanged semantics).


def test_every_external_code_mints_a_frozen_exit_key():
    head = "a" * 40
    for code in sorted(GUARD.EXTERNAL_BLOCKERS):
        key = GUARD._external_exit_key(code, head, f"reason for {code}")
        assert key.startswith(f"{code}:{head}:") and len(key.split(":")) == 3, key
    for code in ("unmerged", GUARD.CI_FAILED_UNMERGED, "unpushed", "uncommitted",
                 "unsafe_branch", "guard_error"):
        assert GUARD._external_exit_key(code, head, "reason") == ""


def test_a_ratified_external_exit_quiesces_the_task_notification_wake(tmp_path, capsys):
    """Incident PR #6377's shape: escape ratified, then a delayed timer wakes
    the session. The wake turn's Stop re-derives the SAME frozen external state
    and must pass silently without demanding the report again."""
    path = _block_state(tmp_path)
    reported = {"stop_hook_active": True, "last_assistant_message": _REPORTED}
    key = GUARD._external_exit_key("github_unreachable", "a" * 40, "fetch died")
    assert _drive_block_keyed(path, capsys, "github_unreachable", reported, key) is False
    assert _drive_block_keyed(path, capsys, "github_unreachable", reported, key) is True
    # The wake: started by a task notification, so stop_hook_active is False and
    # the final message is ordinary prose, not a SHIP LOOP BLOCKED report.
    wake = {"stop_hook_active": False, "last_assistant_message": "Leftover timer drained."}
    before = GUARD._load(path)["total_blocks"]
    assert _drive_block_keyed(path, capsys, "github_unreachable", wake, key) is True
    assert GUARD._load(path)["total_blocks"] == before
    assert GUARD._load(path)["ladder_exits"] == [key]


def test_an_external_exit_for_one_head_never_excuses_a_new_head(tmp_path, capsys):
    """A generic outage reason can recur verbatim for NEW work; the head in the
    key is what keeps the old report from covering it."""
    path = _block_state(tmp_path)
    reported = {"stop_hook_active": True, "last_assistant_message": _REPORTED}
    old = GUARD._external_exit_key("github_unreachable", "a" * 40, "fetch died")
    assert _drive_block_keyed(path, capsys, "github_unreachable", reported, old) is False
    assert _drive_block_keyed(path, capsys, "github_unreachable", reported, old) is True
    fresh = GUARD._external_exit_key("github_unreachable", "b" * 40, "fetch died")
    wake = {"stop_hook_active": False, "last_assistant_message": "done."}
    assert _drive_block_keyed(path, capsys, "github_unreachable", wake, fresh) is False
    assert GUARD._load(path)["ladder_exits"] == [old]


def test_a_changed_external_reason_regates_fresh(tmp_path, capsys):
    """A materially changed blocker is a NEW state (commission failure case:
    'external blocker changes reason while a watcher is sleeping')."""
    path = _block_state(tmp_path)
    reported = {"stop_hook_active": True, "last_assistant_message": _REPORTED}
    first = GUARD._external_exit_key("render_failed", "a" * 40, "render run 1 failed")
    assert _drive_block_keyed(path, capsys, "render_failed", reported, first) is False
    assert _drive_block_keyed(path, capsys, "render_failed", reported, first) is True
    changed = GUARD._external_exit_key("render_failed", "a" * 40, "render run 2 failed")
    wake = {"stop_hook_active": False, "last_assistant_message": "done."}
    assert _drive_block_keyed(path, capsys, "render_failed", wake, changed) is False


def test_internal_own_red_cannot_ride_the_external_quiescence_path(tmp_path, capsys):
    """`ci_failed_unmerged` mints no key and keeps the 10/15 loop breaker: the
    cheap external wake-quiescence path must be unreachable for an owned red."""
    path = _block_state(tmp_path)
    assert GUARD._external_exit_key(GUARD.CI_FAILED_UNMERGED, "a" * 40, "own red") == ""
    reported = {"stop_hook_active": True, "last_assistant_message": _REPORTED}
    assert _drive_block(path, capsys, GUARD.CI_FAILED_UNMERGED, reported) is False
    assert _drive_block(path, capsys, GUARD.CI_FAILED_UNMERGED, reported) is False
    assert "ladder_exits" not in GUARD._load(path)


# ── one-watcher law (PreToolUse ship-watcher gate) ───────────────────────────


def _watcher_payload(command: str, background: bool = True, tool: str = "Bash") -> dict:
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": tool,
        "tool_input": {"command": command, "run_in_background": background},
    }


@pytest.mark.parametrize(
    "command,background",
    [
        ("sleep 600", True),
        ("sleep 600 && gh run view 1", True),
        ("sleep 45s && gh pr checks 2", True),
        ("sleep $WAIT_SECONDS && gh run view 1", True),
        ("sleep $((30 * 60)) && gh run view 1", True),
        ("python -c 'import time; time.sleep(600)'", True),
        ("sleep 600", False),
        ("sleep 600 && gh run view 1 &", False),
    ],
)
def test_timer_only_wait_forms_are_classified_for_fail_closed_refusal(command, background):
    """Every form that can wake the model merely to poll unchanged state is
    classified, including the exact syntactic bypasses from the Sol review.

    Mutation caught: returning ``None`` for foreground, shell-background, or
    computed sleeps lets those timers bypass the only admission boundary.
    """
    request = GUARD._watcher_request(_watcher_payload(command, background=background))
    assert request is not None
    assert request["admission"] == "deny_timer"


@pytest.mark.parametrize(
    "command",
    [
        "/bin/sleep 600",
        "env sleep 600",
        "command /usr/bin/sleep 600",
        "alias nap=/bin/sleep; nap 600",
        "python -c 'import time as t; t.sleep(600)'",
        "python -c 'from time import sleep as nap; nap(600)'",
        "python -c \"__import__('time').sleep(600)\"",
        "bash -c 'env sleep 600'",
    ],
)
def test_executed_timer_spellings_cannot_bypass_shell_aware_classification(command):
    request = GUARD._watcher_request(_watcher_payload(command, background=False))
    assert request is not None
    assert request["admission"] == "deny_timer"


@pytest.mark.parametrize(
    "command,admission",
    [
        ("eval 'sleep 600'", "deny_timer"),
        ("eval 'gh run watch 123 --exit-status'", "reserve_condition"),
        ("CMD='sleep 600'; eval \"$CMD\"", "deny_timer"),
        ("nohup gh run watch 123 --exit-status &", "deny_detached"),
        ("exec gh run watch 123 --exit-status", "deny_uncertain"),
        ("env -S 'sleep 600'", "deny_timer"),
        ("pwsh -Command 'Start-Sleep 600'", "deny_timer"),
    ],
)
def test_executable_indirection_and_transport_cannot_bypass_wait_admission(
    command, admission
):
    request = GUARD._watcher_request(_watcher_payload(command, background=False))
    assert request is not None
    assert request["admission"] == admission


@pytest.mark.parametrize(
    "command,argv",
    [
        (
            "/usr/bin/nice gh run watch 123 --exit-status --interval 60",
            ["/usr/bin/nice"],
        ),
        (
            "/usr/bin/caffeinate -i gh run watch 123 --exit-status --interval 60",
            ["/usr/bin/caffeinate", "-i"],
        ),
        (
            "timeout 300 gh run watch 123 --exit-status --interval 60",
            ["timeout", "300"],
        ),
    ],
)
def test_argv_wrappers_cannot_hide_a_real_fake_gh_watch(
    command, argv, tmp_path
):
    """The classified argv shape is also executed against a fake gh binary.

    This prevents a parser-only repair from recognizing a spelling that the
    real wrapper does not actually execute as the child command.
    """
    request = GUARD._watcher_request(_watcher_payload(command, background=False))
    assert request is not None
    assert request["admission"] == "reserve_condition"
    assert request["condition"] == "gh-run:current-repo:123"

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    receipt = tmp_path / "gh-argv.txt"
    fake_gh = fake_bin / "gh"
    fake_gh.write_text(
        "#!/bin/sh\nprintf '%s\\n' \"$@\" > \"$FAKE_GH_RECEIPT\"\n",
        encoding="utf-8",
    )
    fake_gh.chmod(0o700)
    if argv[0] == "timeout":
        fake_timeout = fake_bin / "timeout"
        fake_timeout.write_text(
            "#!/bin/sh\nshift\nexec \"$@\"\n",
            encoding="utf-8",
        )
        fake_timeout.chmod(0o700)
    elif not Path(argv[0]).exists():
        pytest.skip(f"system wrapper absent: {argv[0]}")
    env = dict(os.environ)
    env["PATH"] = f"{fake_bin}{os.pathsep}{env.get('PATH', '')}"
    env["FAKE_GH_RECEIPT"] = str(receipt)
    subprocess.run(
        [*argv, "gh", "run", "watch", "123", "--exit-status", "--interval", "60"],
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
        timeout=10,
    )
    assert receipt.read_text(encoding="utf-8").splitlines() == [
        "run",
        "watch",
        "123",
        "--exit-status",
        "--interval",
        "60",
    ]


def test_unknown_argv_transport_with_literal_gh_watch_fails_closed():
    request = GUARD._watcher_request(
        _watcher_payload(
            "/opt/local/bin/custom-wrapper gh run watch 123 --exit-status",
            background=False,
        )
    )
    assert request is not None
    assert request["admission"] == "deny_uncertain"


@pytest.mark.parametrize(
    "command",
    [
        "/usr/bin/nice echo gh run watch 123 --exit-status",
        "/usr/bin/caffeinate -i printf '%s' 'gh run watch 123 --exit-status'",
        "timeout 300 cat notes-about-gh-run-watch.txt",
    ],
)
def test_argv_wrappers_preserve_data_and_prose_negative_controls(command):
    assert GUARD._watcher_request(
        _watcher_payload(command, background=False)
    ) is None


@pytest.mark.parametrize(
    "command",
    [
        "cat <<'EOF'\nsleep 600\nEOF",
        "cat <<'EOF'\ngh run watch 123 --exit-status\nEOF",
        "python - <<'PY'\nprint('gh run watch 123 --exit-status')\nPY",
    ],
)
def test_heredoc_wait_text_is_data_not_executable_admission(command):
    assert GUARD._watcher_request(_watcher_payload(command, background=False)) is None


@pytest.mark.parametrize(
    "command,admission,condition",
    [
        ("bash <<'EOF'\nsleep 600\nEOF", "deny_timer", "timer-poll"),
        (
            "sh -s <<'EOF'\ngh run watch 123 --exit-status --interval 60\nEOF",
            "reserve_condition",
            "gh-run:current-repo:123",
        ),
        (
            "python - <<'PY'\nimport time\ntime.sleep(600)\nPY",
            "deny_timer",
            "timer-poll",
        ),
    ],
)
def test_executable_stdin_heredocs_are_classified_as_code(
    command, admission, condition
):
    """A here-document is data only when its consumer treats it as data.

    Interpreter stdin is executable code and must remain inside watcher
    admission without reintroducing the cat/printf prose false positives.
    """
    request = GUARD._watcher_request(_watcher_payload(command, background=False))
    assert request is not None
    assert request["admission"] == admission
    assert request["condition"] == condition


@pytest.mark.parametrize(
    "command,admission,condition",
    [
        ("CMD='sleep 600'; $CMD", "deny_uncertain", "uncertain-wait"),
        (
            "CMD='gh run watch 123 --exit-status --interval 60'; $CMD",
            "deny_uncertain",
            "uncertain-wait",
        ),
        ("$(printf '%s' 'sleep 600')", "deny_uncertain", "uncertain-wait"),
        (
            "$(printf '%s' 'gh run watch 123 --exit-status --interval 60')",
            "deny_uncertain",
            "uncertain-wait",
        ),
    ],
)
def test_computed_command_position_cannot_bypass_wait_admission(
    command, admission, condition
):
    request = GUARD._watcher_request(_watcher_payload(command, background=False))
    assert request is not None
    assert request["admission"] == admission
    assert request["condition"] == condition


def test_command_substitution_used_as_an_ordinary_argument_is_not_execution():
    command = "echo \"$(printf '%s' 'gh run watch 123 --exit-status')\""
    assert GUARD._watcher_request(_watcher_payload(command, background=False)) is None


def test_non_wait_command_substitution_at_command_position_remains_ordinary_bash():
    assert GUARD._watcher_request(
        _watcher_payload("$(printf '%s' 'echo ok')", background=False)
    ) is None


@pytest.mark.parametrize(
    "command",
    [
        "echo 'time.sleep(600)'",
        "printf '%s\\n' 'time.sleep(600)'",
        "rg -n 'time[.]sleep[(]' tests",
        "python -c 'print(\"time.sleep(600)\")'",
        "echo 'gh run watch 123 --exit-status'",
        "echo 'while waiting for gh to finish'",
    ],
)
def test_wait_syntax_used_as_ordinary_data_is_not_denied(command):
    assert GUARD._watcher_request(_watcher_payload(command)) is None


@pytest.mark.parametrize(
    "command",
    [
        "gh run watch 123 --exit-status",
        "gh pr checks 456 --watch --interval 60",
        "gh pr checks --watch --interval 60",
    ],
)
def test_native_condition_watches_are_classified_as_the_one_reservable_owner(command):
    request = GUARD._watcher_request(_watcher_payload(command, background=False))
    assert request is not None
    assert request["admission"] == "reserve_condition"


@pytest.mark.parametrize(
    "command,condition",
    [
        (
            "/opt/homebrew/bin/gh run watch 123 --exit-status",
            "gh-run:current-repo:123",
        ),
        ("env gh run watch 123 --exit-status", "gh-run:current-repo:123"),
        ("alias g=gh; g run watch 123 --exit-status", "gh-run:current-repo:123"),
        (
            "gh pr checks --watch=true --interval 60",
            "gh-pr-checks:current-repo:current-head",
        ),
    ],
)
def test_native_condition_watch_legal_spellings_share_stable_identity(command, condition):
    request = GUARD._watcher_request(_watcher_payload(command, background=False))
    assert request is not None
    assert request["admission"] == "reserve_condition"
    assert request["condition"] == condition


@pytest.mark.parametrize(
    "command,condition",
    [
        (
            "gh run watch --exit-status 123 --interval 60",
            "gh-run:current-repo:123",
        ),
        (
            "gh run watch -R owner/repo 123 --interval 60",
            "gh-run:owner/repo:123",
        ),
        (
            "gh -R owner/repo run watch --interval 60 124",
            "gh-run:owner/repo:124",
        ),
        (
            "gh pr checks --watch 456 --interval 60",
            "gh-pr-checks:current-repo:456",
        ),
        (
            "gh pr checks --required 456 --watch --interval 60",
            "gh-pr-checks:current-repo:456",
        ),
        (
            "gh pr checks -R owner/repo --watch 456 --interval 60",
            "gh-pr-checks:owner/repo:456",
        ),
    ],
)
def test_gh_wait_condition_identity_parses_option_arity_and_subject(
    command, condition
):
    request = GUARD._watcher_request(_watcher_payload(command, background=False))
    assert request is not None
    assert request["admission"] == "reserve_condition"
    assert request["condition"] == condition


def test_distinct_repositories_and_subjects_have_distinct_wait_digests():
    commands = [
        "gh run watch -R owner/one 123 --interval 60",
        "gh run watch -R owner/two 123 --interval 60",
        "gh run watch -R owner/one 124 --interval 60",
        "gh pr checks -R owner/one --watch 123 --interval 60",
    ]
    requests = [GUARD._watcher_request(_watcher_payload(command)) for command in commands]
    assert all(request is not None for request in requests)
    assert len({request["condition"] for request in requests}) == len(commands)
    assert len({request["digest"] for request in requests}) == len(commands)


def test_dynamic_watcher_executable_fails_closed_as_watcher_shaped_uncertainty():
    request = GUARD._watcher_request(
        _watcher_payload("GH=gh; $GH run watch 123 --exit-status", background=False)
    )
    assert request is not None
    assert request["admission"] == "deny_uncertain"


def test_dynamic_sleep_executable_fails_closed_as_watcher_shaped_uncertainty():
    request = GUARD._watcher_request(
        _watcher_payload("S=/bin/sleep; $S 600", background=False)
    )
    assert request is not None
    assert request["admission"] == "deny_uncertain"


def test_shell_background_operator_cannot_detach_the_reserved_condition_owner():
    request = GUARD._watcher_request(
        _watcher_payload("gh run watch 123 --exit-status &", background=False)
    )
    assert request is not None
    assert request["admission"] == "deny_detached"


def test_current_pr_watch_has_a_stable_condition_key_independent_of_flag_order():
    first = GUARD._watcher_request(
        _watcher_payload("gh pr checks --watch --interval 60", background=False)
    )
    second = GUARD._watcher_request(
        _watcher_payload("gh pr checks --interval 60 --watch", background=True)
    )
    assert first is not None and second is not None
    assert (
        first["condition"]
        == second["condition"]
        == "gh-pr-checks:current-repo:current-head"
    )
    assert first["digest"] == second["digest"]


def test_explicit_false_watch_flag_is_an_ordinary_one_shot_command():
    assert GUARD._watcher_request(
        _watcher_payload("gh pr checks --watch=false", background=False)
    ) is None


def test_watcher_classifier_keeps_ordinary_bash_and_other_tools_out_of_scope():
    assert GUARD._watcher_request(_watcher_payload("pytest -q tests/test_x.py")) is None
    assert GUARD._watcher_request(_watcher_payload("echo sleeper")) is None
    assert GUARD._watcher_request(_watcher_payload("sleep 600", tool="Read")) is None


@pytest.mark.parametrize(
    "command",
    [
        "sleep 600",
        "sleep $WAIT_SECONDS && gh run view 1",
        "python -c 'import time; time.sleep(600)'",
        "gh run watch 123 --exit-status &",
    ],
)
def test_timer_and_detached_waits_are_denied_before_delegation(
    monkeypatch, capsys, command
):
    """Classification must reach a real PreToolUse denial even with no ledger;
    otherwise the syntactic bypass is merely labelled, not prevented."""

    def explode(*_args, **_kwargs):
        raise AssertionError("refused transport must not reach delegation")

    monkeypatch.setattr(GUARD, "_delegate_to_evaluated_hook", explode)
    GUARD._pre_tool_use(_watcher_payload(command, background=False), b"{}")
    verdict = json.loads(capsys.readouterr().out)["hookSpecificOutput"]
    assert verdict["permissionDecision"] == "deny"
    assert "REFUSED" in verdict["permissionDecisionReason"]


def _watcher_state(tmp_path: Path, extra: dict | None = None) -> Path:
    path = tmp_path / "watch-state.json"
    state = {
        "root": str(tmp_path),
        "start_head": "0" * 40,
        "baseline": {},
        "last_blocker": "",
        "blocker_count": 0,
        "total_blocks": 0,
        "external_blocks": 0,
    }
    state.update(extra or {})
    GUARD._save(path, state)
    return path


def _drive_watcher_gate(monkeypatch, capsys, path: Path, command: str, head: str = "a" * 40) -> str:
    monkeypatch.setattr(GUARD, "_run", lambda _root, *args, **_kw: head)
    watch = GUARD._watcher_request(_watcher_payload(command))
    assert watch is not None
    state = GUARD._load(path)
    GUARD._watcher_gate(Path("/unused"), path, state, watch)
    return capsys.readouterr().out


def test_first_native_condition_watcher_reserves_and_second_is_coalesced(
    monkeypatch, capsys, tmp_path
):
    path = _watcher_state(tmp_path)
    command = "gh run watch 1 --exit-status"
    assert _drive_watcher_gate(monkeypatch, capsys, path, command) == ""
    reservation = GUARD._load(path)["ship_watcher"]
    assert reservation["head"] == "a" * 40
    assert reservation["fragment"] == command
    assert reservation["condition"] == "gh-run:current-repo:1"
    # A second request inside the start grace is refused unconditionally —
    # the admitted task may not have spawned yet, so ps proves nothing.
    denied = _drive_watcher_gate(monkeypatch, capsys, path, "gh pr checks 2 --watch")
    verdict = json.loads(denied)["hookSpecificOutput"]
    assert verdict["permissionDecision"] == "deny"
    assert "SHIP WATCHER COALESCED" in verdict["permissionDecisionReason"]
    assert "still starting" in verdict["permissionDecisionReason"]
    # The refusal must not clobber the live reservation.
    assert GUARD._load(path)["ship_watcher"] == reservation


def test_admitted_condition_watch_gets_a_unique_process_marker_in_updated_input(
    monkeypatch, capsys, tmp_path
):
    path = _watcher_state(tmp_path)
    monkeypatch.setattr(GUARD, "_delegate_to_evaluated_hook", lambda *_args: False)
    monkeypatch.setattr(GUARD, "_repo_root", lambda _payload: tmp_path)
    monkeypatch.setattr(GUARD, "_state_path", lambda _root, _payload: path)
    monkeypatch.setattr(GUARD, "_run", lambda _root, *_args, **_kwargs: "a" * 40)

    payload = _watcher_payload(
        "gh run watch 123 --exit-status --interval 60", background=True
    )
    GUARD._pre_tool_use(payload, b"{}")
    output = json.loads(capsys.readouterr().out)["hookSpecificOutput"]
    assert output["permissionDecision"] == "allow"
    updated = output["updatedInput"]
    assert updated["run_in_background"] is True
    reservation = GUARD._load(path)["ship_watcher"]
    marker = reservation["process_marker"]
    assert marker.startswith("ship-watcher:")
    assert marker in updated["command"]
    assert "gh run watch 123 --exit-status --interval 60" in updated["command"]
    assert reservation["confirmed"] is False


def test_hot_watch_inside_executable_heredoc_is_denied_before_reservation(
    monkeypatch, capsys, tmp_path
):
    path = _watcher_state(tmp_path)
    monkeypatch.setattr(GUARD, "_delegate_to_evaluated_hook", lambda *_args: False)
    monkeypatch.setattr(GUARD, "_repo_root", lambda _payload: tmp_path)
    monkeypatch.setattr(GUARD, "_state_path", lambda _root, _payload: path)
    command = "sh -s <<'EOF'\ngh run watch 123 --exit-status\nEOF"

    GUARD._pre_tool_use(_watcher_payload(command, background=False), b"{}")

    verdict = json.loads(capsys.readouterr().out)["hookSpecificOutput"]
    assert verdict["permissionDecision"] == "deny"
    assert "SHARED GITHUB QUOTA" in verdict["permissionDecisionReason"]
    assert "ship_watcher" not in GUARD._load(path)


def test_allowed_watcher_confirms_the_existing_reservation_before_gh_executes(
    monkeypatch, capsys, tmp_path
):
    """The permission hook may only create a pending claim. The command that
    actually survives every parallel PreToolUse hook must confirm that exact
    marker before GitHub execution, binding ownership to real execution rather
    than to one hook's isolated allow decision."""
    path = _watcher_state(tmp_path)
    monkeypatch.setattr(GUARD, "_delegate_to_evaluated_hook", lambda *_args: False)
    monkeypatch.setattr(GUARD, "_repo_root", lambda _payload: tmp_path)
    monkeypatch.setattr(GUARD, "_state_path", lambda _root, _payload: path)
    monkeypatch.setattr(GUARD, "_run", lambda _root, *_args, **_kwargs: "a" * 40)

    GUARD._pre_tool_use(
        _watcher_payload("gh run watch 123 --exit-status --interval 60", background=False),
        b"{}",
    )
    output = json.loads(capsys.readouterr().out)["hookSpecificOutput"]
    updated = output["updatedInput"]["command"]

    fake_gh = tmp_path / "gh"
    fake_gh.write_text(
        "#!/bin/sh\nprintf 'executed\\n' > \"$GH_EXECUTED\"\n",
        encoding="utf-8",
    )
    fake_gh.chmod(0o755)
    receipt = tmp_path / "gh-executed.txt"
    env = dict(os.environ)
    env["PATH"] = f"{tmp_path}:{env.get('PATH', '')}"
    env["GH_EXECUTED"] = str(receipt)
    result = subprocess.run(
        ("/bin/bash", "-c", updated),
        cwd=tmp_path,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert receipt.read_text(encoding="utf-8") == "executed\n"
    reservation = GUARD._load(path)["ship_watcher"]
    assert reservation["confirmed"] is True
    assert int(reservation["process_pid"]) > 0
    assert reservation["process_start"]


def test_process_liveness_uses_unique_reservation_marker_not_shared_command_fragment(
    monkeypatch, capsys, tmp_path
):
    state_path = _watcher_state(tmp_path)
    state = GUARD._load(state_path)
    state["ship_watcher"] = {
        "digest": "08e6d841f709",
        "condition": "gh-run:current-repo:1",
        "fragment": "gh run watch 1 --exit-status",
        "process_marker": "ship-watcher:this-session",
        "head": "a" * 40,
        "created": GUARD.time.time() - 300,
    }
    GUARD._save(state_path, state)
    seen = []

    def marker_liveness(reservation):
        seen.append(reservation["process_marker"])
        # A sibling runs the identical command, but carries a distinct marker.
        return reservation["process_marker"] == "ship-watcher:sibling-session"

    monkeypatch.setattr(GUARD, "_watcher_process_alive", marker_liveness)
    assert _drive_watcher_gate(
        monkeypatch,
        capsys,
        path=state_path,
        command="gh run watch 2 --exit-status",
    ) == ""
    assert seen == ["ship-watcher:this-session"]
    assert (
        GUARD._load(state_path)["ship_watcher"]["condition"]
        == "gh-run:current-repo:2"
    )


def test_watcher_liveness_binds_pid_and_start_identity_and_rejects_pid_reuse(
    monkeypatch
):
    start = "Mon Aug 25 12:34:56 2026"
    marker = "ship-watcher:owned-session"

    def ps(*_args, **_kwargs):
        return type(
            "Proc",
            (),
            {
                "returncode": 0,
                "stdout": f"  4242 {start} /bin/bash -c : '{marker}'\n",
            },
        )()

    monkeypatch.setattr(GUARD.subprocess, "run", ps)
    reservation = {"process_marker": marker}
    assert GUARD._watcher_process_alive(reservation) is True
    assert reservation["process_pid"] == 4242
    assert reservation["process_start"] == start

    # The numeric PID can be reused after the owner exits. A different start
    # identity is a different process and must not keep the reservation live.
    reservation["process_start"] = "Sun Aug 24 12:34:56 2026"
    assert GUARD._watcher_process_alive(reservation) is False


def test_composite_shell_exec_and_identical_sibling_do_not_confuse_liveness(
    monkeypatch
):
    own_marker = "ship-watcher:owned-session"
    sibling_marker = "ship-watcher:sibling-session"
    start = "Mon Aug 25 12:34:56 2026"

    def ps(*_args, **_kwargs):
        return type(
            "Proc",
            (),
            {
                "returncode": 0,
                "stdout": (
                    f"  4001 {start} /bin/bash -c cd /repo && gh run watch 7 "
                    f"--exit-status >/tmp/log; : '{sibling_marker}'\n"
                    "  4002 Mon Aug 25 12:35:01 2026 gh run watch 7 --exit-status\n"
                ),
            },
        )()

    monkeypatch.setattr(GUARD.subprocess, "run", ps)
    # The identical gh child and sibling shell are not this session's owner.
    assert GUARD._watcher_process_alive({"process_marker": own_marker}) is False


def test_multiple_processes_with_one_reservation_marker_are_unanswerable(monkeypatch):
    marker = "ship-watcher:ambiguous"
    start = "Mon Aug 25 12:34:56 2026"

    def ps(*_args, **_kwargs):
        return type(
            "Proc",
            (),
            {
                "returncode": 0,
                "stdout": (
                    f"  41 {start} bash -c : '{marker}'\n"
                    f"  42 {start} bash -c : '{marker}'\n"
                ),
            },
        )()

    monkeypatch.setattr(GUARD.subprocess, "run", ps)
    assert GUARD._watcher_process_alive({"process_marker": marker}) is None


def _aged_reservation(
    path: Path,
    *,
    age: float = 300.0,
    fragment: str = "gh run watch 1 --exit-status",
    head: str = "a" * 40,
) -> None:
    state = GUARD._load(path)
    now = GUARD.time.time()
    state["ship_watcher"] = {
        # Literal fixture for ``gh-run:current-repo:1``. This is
        # intentionally not derived through _watcher_request, so a broken
        # classifier cannot make both sides agree with itself.
        "digest": "08e6d841f709",
        "fragment": fragment,
        "condition": "gh-run:current-repo:1",
        "head": head,
        "created": now - age,
    }
    GUARD._save(path, state)


def test_a_completed_watch_cannot_spawn_an_unchanged_successor_timer(
    monkeypatch, capsys, tmp_path
):
    """The #6406 mutation: process absence must not authorize the same
    condition watcher again. That would make completion wake the model, permit
    a successor, and repeat forever while GitHub remains unchanged."""
    path = _watcher_state(tmp_path)
    _aged_reservation(path)
    monkeypatch.setattr(GUARD, "_watcher_process_alive", lambda _f: False)
    denied = _drive_watcher_gate(monkeypatch, capsys, path, "gh run watch 1 --exit-status")
    assert "UNCHANGED WAIT REFUSED" in denied
    assert GUARD._load(path)["ship_watcher"]["created"] < GUARD.time.time() - 60


def test_five_unchanged_observations_admit_zero_successor_watchers(
    monkeypatch, capsys, tmp_path
):
    """N>=5 frozen observations produce no hook-level continuation admission.

    The PreToolUse contract can deterministically prove deny decisions and the
    absence of a rewritten command. It cannot claim ownership of the client's
    model-turn lifecycle, which remains an external acceptance boundary.
    """
    path = _watcher_state(tmp_path)
    _aged_reservation(path)
    before = GUARD._load(path)["ship_watcher"]
    monkeypatch.setattr(GUARD, "_watcher_process_alive", lambda _f: False)
    for _ in range(5):
        denied = _drive_watcher_gate(
            monkeypatch, capsys, path, "gh run watch 1 --exit-status"
        )
        verdict = json.loads(denied)["hookSpecificOutput"]
        assert verdict["permissionDecision"] == "deny"
        assert "updatedInput" not in verdict
        assert "UNCHANGED WAIT REFUSED" in verdict["permissionDecisionReason"]
    assert GUARD._load(path)["ship_watcher"] == before


def test_one_material_change_admits_exactly_one_new_owner(
    monkeypatch, capsys, tmp_path
):
    path = _watcher_state(tmp_path)
    _aged_reservation(path)
    monkeypatch.setattr(GUARD, "_watcher_process_alive", lambda _f: False)
    changed = "gh run watch 2 --exit-status"
    assert _drive_watcher_gate(monkeypatch, capsys, path, changed) == ""
    for _ in range(5):
        denied = _drive_watcher_gate(monkeypatch, capsys, path, changed)
        assert "SHIP WATCHER COALESCED" in denied
    assert GUARD._load(path)["ship_watcher"]["condition"] == "gh-run:current-repo:2"


def test_identical_conditions_in_distinct_sessions_each_have_one_owner(
    monkeypatch, capsys, tmp_path
):
    first = _watcher_state(tmp_path / "first")
    second = _watcher_state(tmp_path / "second")
    command = "gh run watch 1 --exit-status"
    assert _drive_watcher_gate(monkeypatch, capsys, first, command) == ""
    assert _drive_watcher_gate(monkeypatch, capsys, second, command) == ""
    first_marker = GUARD._load(first)["ship_watcher"]["process_marker"]
    second_marker = GUARD._load(second)["ship_watcher"]["process_marker"]
    assert first_marker != second_marker


def test_a_materially_new_condition_can_replace_a_completed_watcher(
    monkeypatch, capsys, tmp_path
):
    path = _watcher_state(tmp_path)
    _aged_reservation(path)
    monkeypatch.setattr(GUARD, "_watcher_process_alive", lambda _f: False)
    assert _drive_watcher_gate(monkeypatch, capsys, path, "gh run watch 2 --exit-status") == ""
    replaced = GUARD._load(path)["ship_watcher"]
    assert replaced["fragment"] == "gh run watch 2 --exit-status"
    assert replaced["created"] > GUARD.time.time() - 30


def test_a_live_watcher_refuses_stacking_past_head_and_condition_changes(
    monkeypatch, capsys, tmp_path
):
    """Sol re-review blocker: occupancy binds to the REAL task lifetime. While
    the reserved process is observably alive, neither a moved HEAD nor a
    changed condition frees the slot."""
    path = _watcher_state(tmp_path)
    _aged_reservation(path, age=7200.0)
    monkeypatch.setattr(GUARD, "_watcher_process_alive", lambda _f: True)
    denied = _drive_watcher_gate(
        monkeypatch, capsys, path, "gh run watch 2 --exit-status", head="b" * 40
    )
    verdict = json.loads(denied)["hookSpecificOutput"]
    assert verdict["permissionDecision"] == "deny"
    assert "still RUNNING" in verdict["permissionDecisionReason"]
    assert "successor is admitted once" not in verdict["permissionDecisionReason"]
    assert "material" in verdict["permissionDecisionReason"].lower()
    # The live reservation is untouched.
    assert GUARD._load(path)["ship_watcher"]["fragment"] == "gh run watch 1 --exit-status"


def test_unknown_watcher_liveness_refuses_stacking(monkeypatch, capsys, tmp_path):
    """An unanswerable process table is OCCUPIED, not free: unknown completion
    must not permit stacking a second live watcher."""
    path = _watcher_state(tmp_path)
    _aged_reservation(path)
    monkeypatch.setattr(GUARD, "_watcher_process_alive", lambda _f: None)
    denied = _drive_watcher_gate(monkeypatch, capsys, path, "gh run watch 2 --exit-status")
    assert "could not be determined" in denied


def test_watcher_process_liveness_reads_the_real_process_table(tmp_path):
    """_watcher_process_alive against the live host: this test's own pytest
    process is visible; a nonsense fragment is not; empty is unanswerable."""
    assert GUARD._watcher_process_alive({}) is None


def test_session_ledger_directory_is_private(monkeypatch, tmp_path):
    monkeypatch.setattr(GUARD.tempfile, "gettempdir", lambda: str(tmp_path))
    root = tmp_path / "repo"
    root.mkdir()
    path = GUARD._state_path(root, {"session_id": "private-mode"})
    assert path.parent.stat().st_mode & 0o777 == 0o700


def _mock_root_owned_sticky_temp(monkeypatch):
    """Make only the first opened directory look like standard root /tmp."""
    real_fstat = GUARD.os.fstat
    calls = {"count": 0}

    def root_temp_then_real(descriptor):
        calls["count"] += 1
        info = real_fstat(descriptor)
        if calls["count"] == 1:
            return SimpleNamespace(
                st_mode=stat.S_IFDIR | stat.S_ISVTX | 0o777,
                st_uid=0,
            )
        return info

    monkeypatch.setattr(GUARD.os, "fstat", root_temp_then_real)


def test_root_owned_sticky_os_temp_root_can_host_private_session_ledgers(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(GUARD.tempfile, "gettempdir", lambda: str(tmp_path))
    _mock_root_owned_sticky_temp(monkeypatch)
    repo = tmp_path / "repo"
    repo.mkdir()

    path = GUARD._state_path(repo, {"session_id": "root-sticky-temp"})

    assert path.parent.stat().st_mode & 0o777 == 0o700
    assert path.parent.parent.stat().st_mode & 0o777 == 0o700


def test_root_owned_sticky_temp_still_refuses_a_session_root_symlink(
    monkeypatch, tmp_path
):
    victim = tmp_path / "attacker-owned-target"
    victim.mkdir()
    (tmp_path / "macro-claude-ship-sessions").symlink_to(
        victim, target_is_directory=True
    )
    monkeypatch.setattr(GUARD.tempfile, "gettempdir", lambda: str(tmp_path))
    _mock_root_owned_sticky_temp(monkeypatch)
    called = []
    real_child_open = GUARD._private_child_directory_fd

    def recording_child_open(parent_fd, name, *, create):
        called.append(name)
        return real_child_open(parent_fd, name, create=create)

    monkeypatch.setattr(GUARD, "_private_child_directory_fd", recording_child_open)
    repo = tmp_path / "repo"
    repo.mkdir()

    with pytest.raises(OSError):
        GUARD._state_path(repo, {"session_id": "root-sticky-symlink"})
    assert called == ["macro-claude-ship-sessions"]
    assert list(victim.iterdir()) == []


def test_session_ledger_root_ancestor_symlink_is_never_followed(monkeypatch, tmp_path):
    victim = tmp_path / "attacker-owned-target"
    victim.mkdir()
    ledger_root = tmp_path / "macro-claude-ship-sessions"
    ledger_root.symlink_to(victim, target_is_directory=True)
    monkeypatch.setattr(GUARD.tempfile, "gettempdir", lambda: str(tmp_path))
    repo = tmp_path / "repo"
    repo.mkdir()

    with pytest.raises(OSError):
        GUARD._state_path(repo, {"session_id": "ancestor-symlink"})
    assert list(victim.iterdir()) == []


def test_state_and_lock_symlinks_fail_closed_without_touching_their_targets(tmp_path):
    victim = tmp_path / "victim.json"
    victim.write_text('{"secret":"unchanged"}', encoding="utf-8")
    state_link = tmp_path / "state.json"
    state_link.symlink_to(victim)
    assert GUARD._load(state_link) is None
    with pytest.raises(OSError):
        GUARD._save(state_link, {"replacement": True})
    assert victim.read_text(encoding="utf-8") == '{"secret":"unchanged"}'

    lock_link = tmp_path / "state.watcher.lock"
    lock_link.symlink_to(victim)
    with pytest.raises(OSError):
        with GUARD._file_lock(lock_link):
            pytest.fail("a planted lock symlink must never be acquired")
    assert victim.read_text(encoding="utf-8") == '{"secret":"unchanged"}'


@pytest.mark.parametrize("unsafe_kind", ["symlink", "malformed"])
def test_ordinary_stop_fails_closed_for_an_unsafe_session_ledger(
    monkeypatch, capsys, tmp_path, unsafe_kind
):
    """Only a genuinely absent pre-install ledger gets the one legacy fail-open.
    A planted symlink or malformed existing ledger is an enforcement fault and
    must never be collapsed into that absence case."""
    repo = _repo(tmp_path)
    victim = tmp_path / "victim.json"
    victim.write_text('{"secret":"unchanged"}', encoding="utf-8")
    state_path = tmp_path / "unsafe-state.json"
    if unsafe_kind == "symlink":
        state_path.symlink_to(victim)
    else:
        state_path.write_text("{not-json", encoding="utf-8")
    monkeypatch.setattr(GUARD, "_delegate_to_evaluated_hook", lambda *_a: False)
    monkeypatch.setattr(GUARD, "_repo_root", lambda _payload: repo)
    monkeypatch.setattr(GUARD, "_state_path", lambda _root, _payload: state_path)
    monkeypatch.setattr(
        GUARD.sys,
        "stdin",
        io.StringIO(json.dumps({"hook_event_name": "Stop", "session_id": "unsafe"})),
    )

    GUARD.main()

    verdict = json.loads(capsys.readouterr().out)
    assert verdict["decision"] == "block"
    assert "guard_error" in verdict["reason"]
    assert victim.read_text(encoding="utf-8") == '{"secret":"unchanged"}'


def test_genuinely_missing_legacy_stop_ledger_retains_the_narrow_fail_open(
    monkeypatch, capsys, tmp_path
):
    repo = _repo(tmp_path)
    missing = tmp_path / "never-created.json"
    monkeypatch.setattr(GUARD, "_delegate_to_evaluated_hook", lambda *_a: False)
    monkeypatch.setattr(GUARD, "_repo_root", lambda _payload: repo)
    monkeypatch.setattr(GUARD, "_state_path", lambda _root, _payload: missing)
    monkeypatch.setattr(
        GUARD.sys,
        "stdin",
        io.StringIO(json.dumps({"hook_event_name": "Stop", "session_id": "legacy"})),
    )
    GUARD.main()
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("unsafe_kind", ["state-symlink", "lock-symlink"])
def test_session_start_reports_unsafe_ledger_paths_without_claiming_enforcement_loaded(
    monkeypatch, capsys, tmp_path, unsafe_kind
):
    repo = _repo(tmp_path)
    victim = tmp_path / "victim.json"
    victim.write_text('{"secret":"unchanged"}', encoding="utf-8")
    state_path = tmp_path / "session-state.json"
    if unsafe_kind == "state-symlink":
        state_path.symlink_to(victim)
    else:
        state_path.write_text("{}", encoding="utf-8")
        state_path.with_suffix(".watcher.lock").symlink_to(victim)
    monkeypatch.setattr(GUARD, "_delegate_to_evaluated_hook", lambda *_a: False)
    monkeypatch.setattr(GUARD, "_repo_root", lambda _payload: repo)
    monkeypatch.setattr(GUARD, "_state_path", lambda _root, _payload: state_path)
    monkeypatch.setattr(
        GUARD.sys,
        "stdin",
        io.StringIO(
            json.dumps(
                {
                    "hook_event_name": "SessionStart",
                    "source": "startup",
                    "session_id": "unsafe-start",
                }
            )
        ),
    )

    GUARD.main()

    output = capsys.readouterr().out
    assert "guard_error" in output
    assert "MANDATORY SHIP LOOP" not in output
    assert victim.read_text(encoding="utf-8") == '{"secret":"unchanged"}'


def test_stop_path_resolution_fault_is_inside_the_fail_closed_router(
    monkeypatch, capsys, tmp_path
):
    repo = _repo(tmp_path)
    monkeypatch.setattr(GUARD, "_delegate_to_evaluated_hook", lambda *_a: False)
    monkeypatch.setattr(GUARD, "_repo_root", lambda _payload: repo)
    monkeypatch.setattr(
        GUARD,
        "_state_path",
        lambda *_a: (_ for _ in ()).throw(OSError("unsafe session directory")),
    )
    monkeypatch.setattr(
        GUARD.sys,
        "stdin",
        io.StringIO(json.dumps({"hook_event_name": "Stop", "session_id": "unsafe-path"})),
    )
    GUARD.main()
    verdict = json.loads(capsys.readouterr().out)
    assert verdict["decision"] == "block"
    assert "guard_error" in verdict["reason"]
    assert "unsafe session directory" in verdict["reason"]


def test_atomic_save_does_not_follow_the_old_predictable_temp_symlink(tmp_path):
    path = tmp_path / "state.json"
    victim = tmp_path / "victim.json"
    victim.write_text("unchanged", encoding="utf-8")
    planted = path.with_suffix(f".{os.getpid()}.tmp")
    planted.symlink_to(victim)
    GUARD._save(path, {"safe": True})
    assert victim.read_text(encoding="utf-8") == "unchanged"
    assert GUARD._load(path) == {"safe": True}


def test_quiescence_standing_law_matches_zero_turn_amendment():
    paths = [
        ROOT / "AGENTS.md",
        ROOT / "CLAUDE.md",
        ROOT / ".cursor" / "rules" / "ship-loop-terminal-states.mdc",
        ROOT / "agentos" / "handoffs" / "CI-MERGE-CONTROL-PLANE-2026-08-24-quiescence.md",
        ROOT / "agentos" / "workstreams" / "WS-CI-MERGE-CONTROL-PLANE.md",
    ]
    for path in paths:
        text = path.read_text(encoding="utf-8").lower()
        normalized = " ".join(text.split())
        assert "zero new model turns while external state is unchanged" in normalized, path
        assert "fired watcher's successor is admitted" not in normalized, path
        assert "background command with a literal `sleep`" not in normalized, path


def test_only_the_parked_latch_refuses_new_watchers_for_its_exact_head(
    monkeypatch, capsys, tmp_path
):
    parked = _watcher_state(tmp_path, {"parked_latch": f"parked:6371:{'a' * 40}"})
    denied = _drive_watcher_gate(monkeypatch, capsys, parked, "gh pr checks 6371 --watch")
    verdict = json.loads(denied)["hookSpecificOutput"]
    assert verdict["permissionDecision"] == "deny"
    assert "SHIP WATCHER REFUSED" in verdict["permissionDecisionReason"]

    # A ratified ladder exit does NOT refuse a watcher (red-team F4): exits
    # have no clearing path, and a transient external blocker (a spent
    # rate-limit window) lawfully resumes at the same head — its wake
    # quiescence is owned by the exit-key memory in _block, not by creation
    # refusal.
    escaped = _watcher_state(
        tmp_path,
        {"ladder_exits": [GUARD._external_exit_key("github_rate_limited", "a" * 40, "x")]},
    )
    assert _drive_watcher_gate(monkeypatch, capsys, escaped, "gh pr checks 9 --watch") == ""
    assert GUARD._load(escaped)["ship_watcher"]["head"] == "a" * 40

    # A latch for a DIFFERENT head never refuses fresh work's watcher.
    other = _watcher_state(tmp_path, {"parked_latch": f"parked:6371:{'c' * 40}"})
    assert _drive_watcher_gate(monkeypatch, capsys, other, "gh pr checks 9 --watch") == ""


def test_watcher_admission_fails_closed_without_ledger_or_git(monkeypatch, capsys, tmp_path):
    # No ledger: _pre_tool_use allows before ever reaching the gate.
    monkeypatch.setattr(GUARD, "_delegate_to_evaluated_hook", lambda *_a: False)
    monkeypatch.setattr(GUARD, "_repo_root", lambda _p: tmp_path)
    monkeypatch.setattr(GUARD, "_state_path", lambda _r, _p: tmp_path / "absent.json")
    GUARD._pre_tool_use(
        _watcher_payload("gh run watch 1 --exit-status --interval 60"), b"{}"
    )
    assert "SHIP WATCHER REFUSED" in capsys.readouterr().out
    # A watcher-shaped request cannot be tracked safely when git is
    # unanswerable, so admission fails closed instead of recording an unknown
    # condition identity.
    path = _watcher_state(tmp_path)

    def broken_run(_root, *_args, **_kw):
        raise RuntimeError("git unavailable")

    monkeypatch.setattr(GUARD, "_run", broken_run)
    watch = GUARD._watcher_request(_watcher_payload("gh run watch 1 --exit-status"))
    GUARD._watcher_gate(Path("/unused"), path, GUARD._load(path), watch)
    assert "SHIP WATCHER REFUSED" in capsys.readouterr().out
    assert "ship_watcher" not in GUARD._load(path)


def test_fourteen_concurrent_watcher_acquisitions_admit_exactly_one(tmp_path):
    """Sol re-review blocker: acquisition must be linearizable ACROSS
    PROCESSES. Three simultaneous watcher-shaped PreToolUse calls race the
    same session ledger with a widened read→write window; the flock must
    admit exactly one and refuse the other thirteen. Removing the lock
    (mutation) makes several observe the empty slot and all admit."""
    import os as _os
    import subprocess as _subprocess
    import sys as _sys

    state_path = _watcher_state(tmp_path)
    driver = tmp_path / "driver.py"
    driver.write_text(
        """
import importlib.util, pathlib, sys
spec = importlib.util.spec_from_file_location("g", sys.argv[1])
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)
g._delegate_to_evaluated_hook = lambda *_a: False
g._repo_root = lambda _p: pathlib.Path(sys.argv[2])
g._state_path = lambda _r, _p: pathlib.Path(sys.argv[3])
g._run = lambda _root, *a, **k: "a" * 40
payload = {
    "hook_event_name": "PreToolUse",
    "tool_name": "Bash",
    "tool_input": {"command": "gh run watch 1 --exit-status --interval 60", "run_in_background": True},
}
g._pre_tool_use(payload, b"{}")
""",
        encoding="utf-8",
    )
    env = dict(_os.environ)
    env["SHIP_WATCHER_TEST_ACQUIRE_DELAY"] = "0.1"
    procs = [
        _subprocess.Popen(
            [_sys.executable, str(driver), str(HOOK_PATH), str(tmp_path), str(state_path)],
            stdout=_subprocess.PIPE,
            stderr=_subprocess.PIPE,
            text=True,
            env=env,
        )
        for _ in range(14)
    ]
    outputs = [proc.communicate(timeout=60)[0] for proc in procs]
    admitted = [out for out in outputs if '"permissionDecision": "allow"' in out]
    denied = [out for out in outputs if "SHIP WATCHER COALESCED" in out]
    assert len(admitted) == 1, outputs
    assert len(denied) == 13, outputs
    assert GUARD._load(state_path)["ship_watcher"]["fragment"] == "gh run watch 1 --exit-status --interval 60"


def test_concurrent_stop_writer_cannot_erase_a_live_watcher_reservation(
    capsys, tmp_path
):
    """A Stop starts from an old snapshot while PreToolUse reserves a watcher.

    Mutation caught: serializing only watcher acquisition still lets the Stop
    save its stale whole-ledger snapshot afterward and silently reopen the
    watcher slot while the first process remains alive.
    """
    import threading

    path = _watcher_state(tmp_path)
    stale_loaded = threading.Event()
    watcher_written = threading.Event()

    def stop_writer():
        stale = GUARD._load(path)
        stale_loaded.set()
        assert watcher_written.wait(timeout=10)
        GUARD._block(
            path,
            stale,
            {"last_assistant_message": ""},
            "github_unreachable",
            "api unavailable",
        )

    writer = threading.Thread(target=stop_writer)
    writer.start()
    assert stale_loaded.wait(timeout=10)
    current = GUARD._load(path)
    current["ship_watcher"] = {
        "digest": "d" * 12,
        "fragment": "gh run watch 1 --exit-status",
        "head": "a" * 40,
        "created": GUARD.time.time(),
    }
    with GUARD._file_lock(path.with_suffix(".watcher.lock")):
        GUARD._save(path, current)
    watcher_written.set()
    writer.join(timeout=10)
    assert not writer.is_alive()
    state = GUARD._load(path)
    assert state["ship_watcher"]["fragment"] == "gh run watch 1 --exit-status"
    assert state["last_blocker"] == "github_unreachable"
    capsys.readouterr()


def test_concurrent_proof_writer_cannot_erase_a_live_watcher_reservation(tmp_path):
    """A slow GitHub proof completion must merge into the latest locked ledger,
    not overwrite the watcher admitted while that proof was in flight."""
    import threading

    path = _watcher_state(tmp_path)
    stale_loaded = threading.Event()
    watcher_written = threading.Event()

    def proof_writer():
        stale = GUARD._load(path)
        stale_loaded.set()
        assert watcher_written.wait(timeout=10)
        GUARD._remember_proof(path, stale, "ci", "head:abc", {"green": True})

    writer = threading.Thread(target=proof_writer)
    writer.start()
    assert stale_loaded.wait(timeout=10)
    current = GUARD._load(path)
    current["ship_watcher"] = {
        "digest": "d" * 12,
        "fragment": "gh run watch 1 --exit-status",
        "head": "a" * 40,
        "created": GUARD.time.time(),
    }
    with GUARD._file_lock(path.with_suffix(".watcher.lock")):
        GUARD._save(path, current)
    watcher_written.set()
    writer.join(timeout=10)
    assert not writer.is_alive()
    state = GUARD._load(path)
    assert state["ship_watcher"]["fragment"] == "gh run watch 1 --exit-status"
    assert state["ship_proofs"]["ci"] == {
        "key": "head:abc",
        "value": {"green": True},
    }


def test_non_watcher_bash_returns_before_delegation(monkeypatch, capsys):
    """The common case must stay free: no delegation subprocess, no git, no
    ledger read for ordinary Bash calls."""

    def explode(*_a, **_kw):
        raise AssertionError("non-watcher PreToolUse must not reach delegation")

    monkeypatch.setattr(GUARD, "_delegate_to_evaluated_hook", explode)
    monkeypatch.setattr(GUARD, "_repo_root", explode)
    GUARD._pre_tool_use(_watcher_payload("pytest -q tests/test_x.py", background=False), b"{}")
    assert capsys.readouterr().out == ""


def test_settings_wire_pre_tool_use_watcher_gate():
    settings = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    bash_hooks = [
        hook
        for entry in settings["hooks"]["PreToolUse"]
        if entry.get("matcher") == "Bash"
        for hook in entry["hooks"]
    ]
    commands = [hook["command"] for hook in bash_hooks]
    assert any("gh_quota_guard.py" in command for command in commands)
    assert any("ship_loop_guard.py" in command for command in commands)


def test_parallel_quota_denial_cannot_leave_a_phantom_consumed_reservation(
    monkeypatch, tmp_path
):
    """Drive the two configured hooks independently as Claude does. The ship
    hook must not reserve a command the canonical quota guard will deny. The
    quota-compliant correction is admitted immediately, without sleeping out
    a pending-claim grace window or creating a second lifecycle."""
    repo = _repo(tmp_path)
    scratch = tmp_path / "tmp"
    scratch.mkdir()
    env = dict(os.environ)
    env["TMPDIR"] = str(scratch)
    env["CLAUDE_PROJECT_DIR"] = str(ROOT)
    session_id = "parallel-hooks-phantom"

    def run_hook(path: Path, payload: dict) -> subprocess.CompletedProcess:
        return subprocess.run(
            (sys.executable, str(path)),
            cwd=repo,
            input=json.dumps(payload),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            timeout=30,
            check=False,
        )

    start = {
        "hook_event_name": "SessionStart",
        "source": "startup",
        "session_id": session_id,
        "cwd": str(repo),
    }
    started = run_hook(HOOK_PATH, start)
    assert started.returncode == 0, started.stderr

    hot = _watcher_payload("gh run watch 123 --exit-status", background=False)
    hot.update({"session_id": session_id, "cwd": str(repo)})
    quota = run_hook(ROOT / ".claude" / "hooks" / "gh_quota_guard.py", hot)
    ship = run_hook(HOOK_PATH, hot)
    quota_verdict = json.loads(quota.stdout)["hookSpecificOutput"]
    ship_verdict = json.loads(ship.stdout)["hookSpecificOutput"]
    assert quota_verdict["permissionDecision"] == "deny"
    assert ship_verdict["permissionDecision"] == "deny"

    monkeypatch.setattr(GUARD.tempfile, "gettempdir", lambda: str(scratch))
    state_path = GUARD._state_path(repo.resolve(), start)
    assert "ship_watcher" not in GUARD._load(state_path)

    lawful = _watcher_payload(
        "gh run watch 123 --exit-status --interval 60", background=False
    )
    lawful.update({"session_id": session_id, "cwd": str(repo)})
    retry = run_hook(HOOK_PATH, lawful)
    retry_verdict = json.loads(retry.stdout)["hookSpecificOutput"]
    assert retry_verdict["permissionDecision"] == "allow"
    replacement = GUARD._load(state_path)["ship_watcher"]
    assert replacement["confirmed"] is False
    assert replacement["condition"] == "gh-run:current-repo:123"


def test_main_routes_a_real_pre_tool_use_payload_end_to_end(monkeypatch, capsys, tmp_path):
    """Drive GUARD.main() with an actual PreToolUse payload: the deny JSON is
    emitted through the whole entrypoint, and a crashing watcher admission
    fails closed without changing ordinary Bash's fail-open path."""
    import io

    path = _watcher_state(tmp_path, {"parked_latch": f"parked:6371:{'a' * 40}"})
    monkeypatch.setattr(GUARD, "_delegate_to_evaluated_hook", lambda *_a: False)
    monkeypatch.setattr(GUARD, "_repo_root", lambda _p: tmp_path)
    monkeypatch.setattr(GUARD, "_state_path", lambda _r, _p: path)
    monkeypatch.setattr(GUARD, "_run", lambda _root, *args, **_kw: "a" * 40)
    payload = json.dumps(_watcher_payload("gh pr checks 6371 --watch"))
    monkeypatch.setattr(GUARD.sys, "stdin", io.StringIO(payload))
    GUARD.main()
    verdict = json.loads(capsys.readouterr().out)["hookSpecificOutput"]
    assert verdict["permissionDecision"] == "deny"

    def explode(*_a, **_kw):
        raise RuntimeError("gate crashed")

    monkeypatch.setattr(GUARD, "_watcher_gate", explode)
    monkeypatch.setattr(GUARD.sys, "stdin", io.StringIO(payload))
    GUARD.main()
    crashed = json.loads(capsys.readouterr().out)["hookSpecificOutput"]
    assert crashed["permissionDecision"] == "deny"
    assert "admission was unanswerable" in crashed["permissionDecisionReason"]


def test_a_legacy_fragmentless_reservation_releases_by_its_own_deadline(
    monkeypatch, capsys, tmp_path
):
    """Migration: a reservation minted by the superseded intermediate gate
    carries no fragment, so liveness can never be observed for it. Observed
    live 2026-08-25: demanding evidence wedged the slot forever. It stays
    occupied until its own recorded deadline, then frees."""
    path = _watcher_state(tmp_path)
    now = GUARD.time.time()
    state = GUARD._load(path)
    state["ship_watcher"] = {
        "digest": "d" * 12,
        "head": "a" * 40,
        "created": now - 300,
        "expires": now + 600,
    }
    GUARD._save(path, state)
    denied = _drive_watcher_gate(monkeypatch, capsys, path, "sleep 900 && gh pr checks 2")
    assert "earlier guard version" in denied
    state = GUARD._load(path)
    state["ship_watcher"]["expires"] = now - 10
    GUARD._save(path, state)
    assert _drive_watcher_gate(monkeypatch, capsys, path, "sleep 900 && gh pr checks 2") == ""
    assert GUARD._load(path)["ship_watcher"]["fragment"] == "sleep 900 && gh pr checks 2"


def test_a_markerless_fragment_era_reservation_releases_by_its_own_deadline(
    monkeypatch, capsys, tmp_path
):
    """Second superseded generation (observed live 2026-08-26 on this repair's
    own session): a fragment-carrying but MARKER-LESS reservation can never be
    identity-bound, so demanding liveness evidence wedged the slot forever.
    Like the fragment-less generation, it stays occupied until its own
    recorded deadline, then frees."""
    path = _watcher_state(tmp_path)
    now = GUARD.time.time()
    state = GUARD._load(path)
    state["ship_watcher"] = {
        "digest": "d" * 12,
        "fragment": 'sleep 1500 && echo "CI-WATCH-3: recheck"',
        "head": "a" * 40,
        "created": now - 97000,
        "nominal_fire": now + 600,
    }
    GUARD._save(path, state)
    denied = _drive_watcher_gate(monkeypatch, capsys, path, "gh run watch 9 --exit-status")
    assert "earlier guard version" in denied
    state = GUARD._load(path)
    state["ship_watcher"]["nominal_fire"] = now - 10
    GUARD._save(path, state)
    assert _drive_watcher_gate(monkeypatch, capsys, path, "gh run watch 9 --exit-status") == ""
    replaced = GUARD._load(path)["ship_watcher"]
    assert replaced["condition"] == "gh-run:current-repo:9"
    assert replaced["process_marker"]
