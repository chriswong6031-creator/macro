"""Regression tests for the tracked Claude completion guard."""

from __future__ import annotations

import email.message
import importlib.util
import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

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


def test_find_commit_handles_nested_health_payload():
    payload = {"ok": True, "deployment": {"revision": "a" * 40}}
    assert GUARD._find_commit(payload) == "a" * 40


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


def test_the_pair_list_is_the_ci_gate_s_own_enumeration(tmp_path):
    """One definition, so the exemption and ui.template_site_sync cannot drift."""
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


@pytest.fixture(autouse=True)
def _clear_token_cache(monkeypatch):
    """The token is memoised per process; tests must not inherit each other's."""
    monkeypatch.setattr(GUARD, "_TOKEN_CACHE", None, raising=False)
    for key in ("GH_TOKEN", "GITHUB_TOKEN"):
        monkeypatch.delenv(key, raising=False)


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
    # The labeled-handoff probe sits on the no-merged-pull-request path, so every
    # test that reaches it would otherwise hit the real API. No open pull request
    # is the default shape; the handoff tests below pass one explicitly.
    monkeypatch.setattr(GUARD, "_open_pull", lambda *_a: open_pull)
    GUARD._stop(repo, state_path, {"hook_event_name": "Stop"})
    out = capsys.readouterr().out.strip()
    if not out:
        return None
    emitted = json.loads(out)
    if "reason" not in emitted:
        return None  # a clean stop (e.g. the labeled handoff), not a block
    # Reason reads "SHIP LOOP <code>: <detail>" — the code sits before the colon.
    return emitted["reason"].split(":", 1)[0].split()[-1]


_MERGED_PR = {"merged_at": "2026-07-25T22:18:56Z", "head": {"sha": "a" * 40}, "merge_commit_sha": "b" * 40}


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

    # And a reported message without stop_hook_active is equally inert.
    path = _block_state(tmp_path)
    no_active = {"stop_hook_active": False, "last_assistant_message": _REPORTED}
    for _ in range(20):
        assert _drive_block(path, capsys, "render_pending", no_active) is False


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


# --- the merge-on-green labeled handoff (operator ruling 2026-07-28) ---


def _pushed_unmerged_session(tmp_path: Path) -> tuple[Path, Path, str]:
    """A session that committed and pushed, with an upstream and no merged PR.

    This is the exact shape the handoff is judged in: without the upstream the
    `unpushed` gate answers first and the probe is never reached.
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


def test_handoff_verdict_classifies_the_three_outcomes():
    """The pure classifier, pinned directly.

    Red OUTRANKS pending here — the reverse of the sweeper's own precedence —
    because this verdict only shapes a message to a session that can act on the
    red now, while the sweeper gates an irreversible merge and waits.
    """
    assert GUARD._handoff_verdict([]) == ("unproven", [])
    # A head whose ONLY run is the known-spurious X proves nothing either.
    assert GUARD._handoff_verdict(
        [_run_stub("Workers Builds: macro", conclusion="failure")]
    ) == ("unproven", [])

    verdict, names = GUARD._handoff_verdict(
        [_run_stub("ci-pack-1", conclusion="failure"), _run_stub("nav-gap", "in_progress")]
    )
    assert verdict == "red" and names == ["ci-pack-1 (failure)"]

    assert GUARD._handoff_verdict([_run_stub("ci-pack-1", "queued")]) == ("armed", [])
    assert GUARD._handoff_verdict(
        [_run_stub("ci-pack-1", conclusion="success"), _run_stub("legacy", conclusion="skipped")]
    ) == ("armed", [])


def test_a_labeled_pull_request_with_checks_pending_releases_the_session(
    monkeypatch, tmp_path, capsys
):
    """THE release valve. Merge-on-CONCLUDED made every session a CI hostage for
    20-60 minutes; an armed pull request hands that wait to the sweeper.

    The session may stop, the handoff is documented as a systemMessage naming the
    pull request and the 10-minute sweep, and the state file is dropped like any
    other clean stop.
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
    assert not any(json.loads(line).get("decision") == "block" for line in raw), raw
    assert len(raw) == 1, f"stdout must stay a single JSON object, got {raw}"
    emitted = json.loads(raw[0])
    assert "decision" not in emitted
    message = emitted["systemMessage"]
    assert "#4242" in message
    assert "merge-on-green" in message and "10 minutes" in message
    assert "CONCLUDED" in message, "the message must restate the merge discipline"
    assert not state_path.exists(), "a clean stop drops the state file"


def test_a_labeled_pull_request_with_a_genuine_red_blocks_as_ci_failed(
    monkeypatch, tmp_path, capsys
):
    """The sweeper never merges a red, so releasing the session would strand it.

    Blocking here is what tells the session the label alone will not save it.
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
    verdict = _stop_verdict(
        monkeypatch, capsys, repo, state_path, merged_pr=None, open_pull=_armed_pr(head)
    )
    assert verdict == "ci_failed", f"a red armed PR must block, got {verdict}"


def test_a_spurious_only_red_still_releases_a_labeled_session(monkeypatch, tmp_path, capsys):
    """`Workers Builds: macro` is the known-spurious X on both sides of the handoff."""
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
    assert verdict is None, f"only the spurious check is red, so the session may stop ({verdict})"


def test_a_labeled_pull_request_with_no_check_runs_still_blocks_as_unmerged(
    monkeypatch, tmp_path, capsys
):
    """A paths-filtered docs-only PR is unproven, and the sweeper will never merge it.

    Releasing the session on a head nothing has checked would ORPHAN the work —
    labeled forever, swept forever, merged never.
    """
    repo, state_path, head = _pushed_unmerged_session(tmp_path)
    monkeypatch.setattr(GUARD, "_head_check_runs", lambda *_a: [])
    verdict = _stop_verdict(
        monkeypatch, capsys, repo, state_path, merged_pr=None, open_pull=_armed_pr(head)
    )
    assert verdict == "unmerged", f"an unproven head must keep the session, got {verdict}"


def test_an_open_pull_request_without_the_label_is_not_a_handoff(monkeypatch, tmp_path, capsys):
    """Opening a PR is not arming one — the label is the whole contract."""
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


def test_a_labeled_pull_request_on_a_stale_head_is_not_a_handoff(monkeypatch, tmp_path, capsys):
    """The armed head must be THIS work. A force-moved branch reaches here with a
    clean ahead-count, and merging its older head would ship the wrong tree."""
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


def test_a_failing_handoff_probe_falls_through_to_the_normal_block(
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


def test_the_spurious_check_rule_is_one_definition(monkeypatch, tmp_path):
    """`_check_ci` and the handoff must never disagree about the spurious X."""
    assert GUARD._is_spurious_check("Workers Builds: macro") is True
    assert GUARD._is_spurious_check("workers builds: MACRO (preview)") is True
    assert GUARD._is_spurious_check("Workers Builds: charting-app") is False
    assert GUARD._is_spurious_check("ci-pack-1") is False


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
