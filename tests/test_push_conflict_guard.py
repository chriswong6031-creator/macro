"""Conflicted-autostash containment (P0 2026-08-01, d29e4dd44d / #4167).

The incident this pins: `git pull --rebase --autostash` EXITS 0 when the rebase
succeeds but the autostash re-apply conflicts. Git leaves
`Updated upstream / Stashed changes` conflict blocks plus unmerged index
entries in the working tree, stores the autostash entry, prints a stderr
warning — and the push loop's success branch keeps running. On 2026-08-01 the
nightly's chronicle push did exactly that while the whole night's render sat
dirty and uncommitted; the next step's broad `git add data/ site/ reports/`
staged the conflicted tree verbatim and engine commit d29e4dd44d shipped 1,707
marker-polluted pages to main (emergency heal: #4167).

What must stay true:
  * the incident reproduces: a conflicted autostash apply exits 0 (if a git
    upgrade changes this, we want to KNOW — the containment design assumes it)
  * push_autostash_ok detects the conflicted apply, discards the throwaway
    leftovers, drops ONLY git's own `autostash` stash entry (foreign/named
    entries survive — the stash stack is repo-global), and returns 1
  * push_staged_clean refuses a commit whose index carries conflict markers or
    unmerged entries — including a truncated LONE closing marker (the
    site/watchlist.html case) — and emits a line-start ::error annotation
  * a bare `=======` line alone never trips it (setext underlines and similar)
  * every render-family lane is actually WIRED to both guards (a guard the
    trigger never reaches is no guard)
"""

from __future__ import annotations

import os
import subprocess
import textwrap
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
LIB = REPO_ROOT / "scripts" / "ci" / "push_retry.sh"

# Column-0 marker lines, assembled so THIS file (inside the scanned tests/…
# no — tests/ is unscanned, but keep the idiom scripts/ uses) never carries one.
OPEN_MARKER = "<" * 7 + " Updated upstream"
CLOSE_MARKER = ">" * 7 + " Stashed changes"
MID_MARKER = "=" * 7


def run_sh(body: str, cwd: Path) -> subprocess.CompletedProcess:
    """Source the library into a `bash -e` shell (GitHub's shell) and run body."""
    script = f'. "{LIB}"\n' + textwrap.dedent(body)
    return subprocess.run(
        ["bash", "-eo", "pipefail", "-c", script],
        capture_output=True,
        text=True,
        env={**os.environ},
        cwd=str(cwd),
    )


def git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True, check=check
    )


def _seed_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "-q", "-b", "main")
    git(path, "config", "user.name", "guard-test")
    git(path, "config", "user.email", "guard-test@example.invalid")
    git(path, "config", "commit.gpgsign", "false")


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "work"
    _seed_repo(r)
    (r / "page.html").write_text("line1\nline2\nline3\n", encoding="utf-8")
    git(r, "add", "page.html")
    git(r, "commit", "-q", "-m", "base")
    return r


def _incident_state(tmp_path: Path, *, foreign_stash: bool = False) -> Path:
    """Reproduce the incident end-to-end with a REAL pull --rebase --autostash.

    origin gains a commit that rewrites the same lines the work clone has dirty
    (the #4151/#4155/#4158 cache-rotation analog); the work clone commits an
    unrelated file (the chronicle commit analog) and pulls. With foreign_stash,
    a named entry is parked BEFORE the pull so the conflicted autostash lands
    on top of it — the repo-global-stash layering the drop must respect.
    """
    origin = tmp_path / "origin"
    _seed_repo(origin)
    (origin / "page.html").write_text("line1\nline2\nline3\n", encoding="utf-8")
    git(origin, "add", "page.html")
    git(origin, "commit", "-q", "-m", "base")

    work = tmp_path / "incident"
    subprocess.run(
        ["git", "clone", "-q", str(origin), str(work)], capture_output=True, check=True
    )
    git(work, "config", "user.name", "guard-test")
    git(work, "config", "user.email", "guard-test@example.invalid")

    # upstream re-stamps the page (the mobile-Terminal cache-key rotation analog)
    (origin / "page.html").write_text("line1\nline2 upstream-stamp\nline3\n", encoding="utf-8")
    git(origin, "add", "page.html")
    git(origin, "commit", "-q", "-m", "upstream stamp")

    if foreign_stash:
        (work / "foreign.txt").write_text("other session's recoverable work\n", encoding="utf-8")
        git(work, "add", "foreign.txt")
        git(work, "stash", "push", "-m", "retired-worktree-guard-test", "--", "foreign.txt")

    # the lane's tree: page dirty with tonight's render, chronicle committed
    (work / "page.html").write_text("line1\nline2 fresh-render\nline3\n", encoding="utf-8")
    (work / "chronicle.json").write_text("{}\n", encoding="utf-8")
    git(work, "add", "chronicle.json")
    git(work, "commit", "-q", "-m", "chronicle analog")

    pull = git(work, "pull", "--rebase", "--autostash", "origin", "main", check=False)
    # THE incident behavior: conflicted autostash apply, exit code 0.
    assert pull.returncode == 0, (
        "pull --rebase --autostash no longer exits 0 on a conflicted autostash "
        f"apply — the containment design must be revisited: {pull.stderr}"
    )
    content = (work / "page.html").read_text(encoding="utf-8")
    assert OPEN_MARKER in content and CLOSE_MARKER in content
    assert git(work, "ls-files", "-u").stdout.strip(), "expected unmerged entries"
    return work


# ---------------------------------------------------------------------------
# 1. push_autostash_ok — detect, discard, drop own entry only
# ---------------------------------------------------------------------------

def test_autostash_ok_passes_on_a_clean_tree(repo: Path):
    r = run_sh("push_retry_init t; push_autostash_ok; echo rc=$?", repo)
    assert r.returncode == 0, r.stderr
    assert "rc=0" in r.stdout


def test_conflicted_autostash_apply_is_detected_and_recovered(tmp_path: Path):
    # a foreign named entry parked UNDER the autostash must survive recovery
    work = _incident_state(tmp_path, foreign_stash=True)
    # the conflicted pull's own entry sits at stash@{0} with subject `autostash`
    subjects = git(work, "log", "-g", "--format=%gs", "refs/stash").stdout.splitlines()
    assert subjects and subjects[0] == "autostash", subjects

    r = run_sh("push_retry_init t; if push_autostash_ok; then echo rc=0; else echo rc=1; fi", work)
    assert r.returncode == 0, r.stderr
    assert "rc=1" in r.stdout, "a conflicted apply must fail the pull condition"
    assert any(
        l.startswith("::warning title=conflicted autostash apply")
        for l in r.stdout.splitlines()
    ), r.stdout
    # tree recovered: no unmerged entries, no marker bytes, clean status
    assert not git(work, "ls-files", "-u").stdout.strip()
    assert OPEN_MARKER not in (work / "page.html").read_text(encoding="utf-8")
    assert not git(work, "status", "--porcelain").stdout.strip()
    # own autostash entry dropped; the foreign entry survives at the top
    subjects = git(work, "log", "-g", "--format=%gs", "refs/stash").stdout.splitlines()
    assert subjects, "foreign stash entry must survive"
    assert "retired-worktree-guard-test" in subjects[0]
    assert all(s != "autostash" for s in subjects)


def test_autostash_ok_never_touches_a_foreign_top_entry(repo: Path):
    (repo / "keep.txt").write_text("keep\n", encoding="utf-8")
    git(repo, "add", "keep.txt")
    git(repo, "stash", "push", "-m", "retired-worktree-2026-07-24", "--", "keep.txt")
    r = run_sh("push_retry_init t; push_autostash_ok", repo)
    assert r.returncode == 0, r.stderr
    subjects = git(repo, "log", "-g", "--format=%gs", "refs/stash").stdout.splitlines()
    assert subjects and "retired-worktree-2026-07-24" in subjects[0]


# ---------------------------------------------------------------------------
# 2. push_staged_clean — the fail-closed commit gate
# ---------------------------------------------------------------------------

def _stage(repo: Path, name: str, text: str) -> None:
    (repo / name).write_text(text, encoding="utf-8")
    git(repo, "add", name)


def test_staged_conflict_block_refuses_the_commit(repo: Path):
    _stage(repo, "bad.html", f"a\n{OPEN_MARKER}\nours\n{MID_MARKER}\ntheirs\n{CLOSE_MARKER}\nb\n")
    r = run_sh("push_retry_init t; if push_staged_clean; then echo rc=0; else echo rc=1; fi", repo)
    assert r.returncode == 0, r.stderr
    assert "rc=1" in r.stdout
    error_lines = [l for l in r.stdout.splitlines() if l.startswith("::error")]
    assert error_lines, "the ::error annotation must START its line (repo law)"
    assert "bad.html" in error_lines[0]


def test_a_truncated_lone_closing_marker_still_refuses(repo: Path):
    # the site/watchlist.html case: a partially overwritten block leaves one line
    _stage(repo, "lone.html", f"a\n{CLOSE_MARKER}\nb\n")
    r = run_sh("push_retry_init t; if push_staged_clean; then echo rc=0; else echo rc=1; fi", repo)
    assert "rc=1" in r.stdout


def test_a_bare_equals_underline_is_not_a_marker(repo: Path):
    _stage(repo, "doc.md", f"Heading\n{MID_MARKER}\nbody text\n")
    r = run_sh("push_retry_init t; if push_staged_clean; then echo rc=0; else echo rc=1; fi", repo)
    assert "rc=1" not in r.stdout and "rc=0" in r.stdout, r.stdout


def test_clean_index_passes_and_exports_empty_offenders(repo: Path):
    _stage(repo, "good.html", "all clean\n")
    r = run_sh(
        'push_retry_init t; push_staged_clean; echo "off=[$PUSH_STAGED_OFFENDERS]"', repo
    )
    assert r.returncode == 0, r.stderr
    assert "off=[]" in r.stdout


def test_the_real_polluted_tree_is_refused_end_to_end(tmp_path: Path):
    """The broad `git add` after a conflicted apply — d29e4dd44d's exact shape."""
    work = _incident_state(tmp_path)
    git(work, "add", "--", "page.html")  # what `git add data/ site/ reports/` did
    r = run_sh("push_retry_init t; if push_staged_clean; then echo rc=0; else echo rc=1; fi", work)
    assert "rc=1" in r.stdout, "the staged incident tree must refuse the commit"
    assert any(l.startswith("::error") for l in r.stdout.splitlines())


def test_pathspec_scoping_only_scans_requested_paths(repo: Path):
    _stage(repo, "outside.log", f"{OPEN_MARKER}\nx\n{CLOSE_MARKER}\n")
    (repo / "site").mkdir()
    _stage(repo, "site/in.html", "clean\n")
    r = run_sh("push_retry_init t; if push_staged_clean site/; then echo rc=0; else echo rc=1; fi", repo)
    assert "rc=0" in r.stdout, "markers outside the scanned pathspecs are out of scope"


# ---------------------------------------------------------------------------
# 3. Wiring — the trigger must reach the guard in every render-family lane
# ---------------------------------------------------------------------------

WF = REPO_ROOT / ".github" / "workflows"


def _steps(workflow: str, job: str) -> list[dict]:
    doc = yaml.safe_load((WF / workflow).read_text(encoding="utf-8"))
    return doc["jobs"][job]["steps"]


def _step_script(workflow: str, job: str, name: str) -> str:
    for step in _steps(workflow, job):
        if step.get("name") == name:
            return step.get("run", "")
    raise AssertionError(f"{workflow}:{job} step {name!r} not found")


def _loop_scripts() -> list[tuple[str, str]]:
    """(label, script) for each render-family commit step, resolved tolerantly:
    step names drift, so locate by content — the push loop that pulls with
    --autostash and carries a broad site/templates follow-up add."""
    out = []
    for wf_name in [
        "daily.yml", "render.yml", "engine-render.yml",
        "closing-bell.yml", "earlyclose.yml", "asia-close.yml",
    ]:
        doc = yaml.safe_load((WF / wf_name).read_text(encoding="utf-8"))
        for job_name, job in doc["jobs"].items():
            for step in job.get("steps", []):
                script = step.get("run") or ""
                if "pull --rebase --autostash" in script and "git add site/ templates/" in script:
                    out.append((f"{wf_name}:{job_name}:{step.get('name')}", script))
    return out


def test_every_render_family_pull_is_wrapped_with_the_autostash_guard():
    scripts = _loop_scripts()
    assert len(scripts) >= 6, [s[0] for s in scripts]
    for label, script in scripts:
        for line in script.splitlines():
            if "pull --rebase --autostash" in line and "if" in line.split("pull")[0]:
                assert "push_autostash_ok" in line, (
                    f"{label}: pull condition lost the push_autostash_ok wrap:\n{line}"
                )


def test_every_render_family_broad_commit_is_gated_by_the_staged_scan():
    scripts = _loop_scripts()
    for label, script in scripts:
        assert "push_staged_clean" in script, (
            f"{label}: broad-add commit step lost its push_staged_clean gate"
        )


def test_chronicle_push_never_touches_the_dirty_render_tree():
    script = _step_script("daily.yml", "engine", "commit chronicle artifacts")
    assert "push_metadata_replay_commit" in script, (
        "chronicle must publish via metadata replay — its old porcelain pull is "
        "what parked the whole night's render and baked d29e4dd44d"
    )
    assert "pull --rebase" not in script, (
        "chronicle push must NEVER pull: it runs while the night's render sits "
        "dirty and uncommitted (P0 2026-08-01)"
    )


def test_daily_engine_commit_heals_then_hard_fails():
    script = _step_script("daily.yml", "engine", "commit engine outputs")
    assert "push_staged_clean data/ site/ reports/ templates/" in script
    assert 'git checkout HEAD -- "$f"' in script, "the HEAD-restore heal disappeared"
    assert "conflict markers persist" in script, "the hard-fail branch disappeared"
    persist_branch = script.split("conflict markers persist", 1)[1]
    assert "exit 1" in persist_branch.split("git commit", 1)[0], (
        "the persist branch must hard-fail BEFORE the engine commit"
    )


def test_guard_functions_exist_in_the_library():
    lib = LIB.read_text(encoding="utf-8")
    assert "push_autostash_ok()" in lib
    assert "push_staged_clean()" in lib
    # scoped drop: only git's own entry, matched by exact subject
    assert '= "autostash" ]' in lib
