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
  * every OTHER lane that pulls with --autostash (the narrow single-path
    lanes: sentinels, marketing, metabolism, research, seo, probes) carries
    push_autostash_ok in the pull condition itself and sources the library —
    they commit before pulling and add only their own paths, so they cannot
    ship markers to main, but an unguarded conflicted apply leaves
    marker-polluted persisted trees and stale autostash entries on the
    shared runner checkouts
"""

from __future__ import annotations

import os
import re
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
    """Source the library and run body under `bash -eo pipefail`.

    (GitHub's default step shell is `bash -e` WITHOUT pipefail — this harness
    is deliberately stricter, so a pass here never hides a production abort.)
    """
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
    # prime the variable so the assertion distinguishes "reset to empty" from
    # "never touched" — an unset var would also print off=[]
    r = run_sh(
        'push_retry_init t; PUSH_STAGED_OFFENDERS=stale-sentinel; '
        'push_staged_clean; echo "off=[$PUSH_STAGED_OFFENDERS]"',
        repo,
    )
    assert r.returncode == 0, r.stderr
    assert "off=[]" in r.stdout


def test_heal_restores_display_paths_and_passes(tmp_path: Path):
    """push_staged_heal: a polluted site/ page is restored WHOLESALE from HEAD."""
    r = tmp_path / "healrepo"
    _seed_repo(r)
    (r / "site").mkdir()
    clean = "line1\nline2\nline3\n"
    (r / "site" / "page.html").write_text(clean, encoding="utf-8")
    git(r, "add", "site/page.html")
    git(r, "commit", "-q", "-m", "base")
    _stage(r, "site/page.html", f"line1\n{OPEN_MARKER}\nours\n{MID_MARKER}\ntheirs\n{CLOSE_MARKER}\nline3\n")
    out = run_sh("push_retry_init t; if push_staged_heal site/; then echo rc=0; else echo rc=1; fi", r)
    assert out.returncode == 0, out.stderr
    assert "rc=0" in out.stdout, out.stdout
    assert any(l.startswith("::warning title=conflict markers healed") for l in out.stdout.splitlines())
    assert (r / "site" / "page.html").read_text(encoding="utf-8") == clean, (
        "the offender must be byte-identical to HEAD after the heal"
    )
    assert not git(r, "status", "--porcelain").stdout.strip()


def test_heal_dies_on_ledger_paths_and_sweeps_them(tmp_path: Path):
    """data/ offenders are never auto-healed (PIT law) — fail closed, sweep the file."""
    r = tmp_path / "ledgerrepo"
    _seed_repo(r)
    (r / "data").mkdir()
    (r / "data" / "ledger.jsonl").write_text('{"day":1}\n', encoding="utf-8")
    git(r, "add", "data/ledger.jsonl")
    git(r, "commit", "-q", "-m", "base")
    _stage(r, "data/ledger.jsonl", f'{{"day":1}}\n{OPEN_MARKER}\nours\n{MID_MARKER}\ntheirs\n{CLOSE_MARKER}\n')
    out = run_sh("push_retry_init t; if push_staged_heal data/; then echo rc=0; else echo rc=1; fi", r)
    assert out.returncode == 0, out.stderr
    assert "rc=1" in out.stdout, out.stdout
    assert any(l.startswith("::error title=ledger conflict") for l in out.stdout.splitlines())
    assert not (r / "data" / "ledger.jsonl").exists(), (
        "the polluted ledger must be swept so an always() artifact cannot ship it"
    )


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


SWEPT_WORKFLOWS = [
    "daily.yml", "render.yml", "engine-render.yml",
    "closing-bell.yml", "earlyclose.yml", "asia-close.yml", "weekly.yml",
]


def _code(script: str) -> str:
    """The script with comment lines removed — census keys must never match a
    comment (deleting an explanatory comment must not drop a lane)."""
    return "\n".join(
        l for l in script.splitlines() if not l.lstrip().startswith("#")
    )


def _loop_scripts() -> list[tuple[str, str]]:
    """(label, script) for each step that both pulls with --autostash and
    broad-adds a site/ pathspec — the exact shape that shipped d29e4dd44d.
    Located structurally (non-comment code), not by step name or comment text."""
    out = []
    for wf_name in SWEPT_WORKFLOWS:
        doc = yaml.safe_load((WF / wf_name).read_text(encoding="utf-8"))
        for job_name, job in doc["jobs"].items():
            for step in job.get("steps", []):
                code = _code(step.get("run") or "")
                # TWO rebase spellings count, and both must, or this census goes
                # blind: the original `git pull --rebase --autostash`, and the
                # explicit `push_fetch_main_for_rebase` + `git rebase --autostash
                # origin/main` form render.yml moved to so its untracked-collision
                # sweep runs against the exact fetched tree. Matching only the
                # first is not a narrower guard but a SILENT one — render.yml
                # vanishes from by_job, every assertion below stops covering it,
                # and the suite still reports green.
                rebases_onto_main = (
                    "pull --rebase --autostash" in code
                    or ("push_fetch_main_for_rebase" in code
                        and re.search(r"git rebase [^\n]*--autostash", code))
                )
                if rebases_onto_main and re.search(
                    r"^\s*git add [^\n]*\bsite/", code, re.M
                ):
                    out.append((f"{wf_name}:{job_name}:{step.get('name')}", code))
    return out


def test_every_render_family_pull_is_wrapped_with_the_autostash_guard():
    scripts = _loop_scripts()
    # engine + standout-audit + the 7 site-file offrender/factor/brief lanes in
    # daily.yml, plus render, engine-render, closing-bell, earlyclose,
    # asia-close ×2, weekly
    assert len(scripts) >= 15, [s[0] for s in scripts]
    for label, code in scripts:
        for line in code.splitlines():
            if "pull --rebase --autostash" in line and "if" in line.split("pull")[0]:
                assert "push_autostash_ok" in line, (
                    f"{label}: pull condition lost the push_autostash_ok wrap:\n{line}"
                )


# The lanes where a polluted tree CAN reach a commit or an always() artifact:
# broad adds that either follow a pull in the same step (render-sync
# follow-ups) or sit in jobs whose earlier machinery pulls/dirties the tree.
GATE_REQUIRED = [
    ("daily.yml", "engine"),
    ("daily.yml", "standout_audit_us"),
    ("render.yml", "render"),
    ("engine-render.yml", "engine-render"),
    ("closing-bell.yml", "closingbell"),
    ("earlyclose.yml", "earlyclose"),
    ("asia-close.yml", "asia"),
    ("weekly.yml", "weekly-report"),
]


def test_every_render_family_broad_commit_is_gated_by_the_staged_scan():
    scripts = _loop_scripts()
    by_job: dict[tuple[str, str], list[str]] = {}
    for label, code in scripts:
        wf, job, _ = label.split(":", 2)
        by_job.setdefault((wf, job), []).append(code)
    for key in GATE_REQUIRED:
        assert key in by_job, f"{key} vanished from the census — check the discriminator"
        assert any(
            "push_staged_heal" in code or "push_staged_clean" in code
            for code in by_job[key]
        ), f"{key}: broad-add commit step lost its conflict gate"


def test_no_swept_lane_regrows_an_unguarded_autostash_pull_before_a_broad_add():
    """The chronicle/marketing shape: an early narrow-commit step that pulls
    over a dirty tree inside a job whose LATER step broad-adds. Both converted
    steps must stay metadata-only (no pull at all)."""
    for wf_name, job, step_name in [
        ("daily.yml", "engine", "commit chronicle artifacts"),
        ("daily.yml", "standout_audit_us", "commit marketing learning artifacts (XG-W6)"),
    ]:
        code = _code(_step_script(wf_name, job, step_name))
        assert "push_metadata_replay_commit" in code, f"{wf_name}:{step_name}"
        assert "pull --rebase" not in code, (
            f"{wf_name}:{step_name} must never pull — it runs over a dirty tree "
            "whose paths a later step in the same job broad-adds (P0 d29e4dd44d)"
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
    code = _code(script)
    assert "push_staged_heal data/ site/ reports/ templates/" in code
    heal_call = code.split("push_staged_heal", 1)[1]
    assert "exit 1" in heal_call.split("git commit", 1)[0], (
        "a failed heal must hard-fail BEFORE the engine commit"
    )


# ---------------------------------------------------------------------------
# 4. Narrow single-path lanes — EVERY autostash pull repo-wide is guarded
# ---------------------------------------------------------------------------


def _autostash_pull_steps() -> list[tuple[str, str]]:
    """(label, code) for every workflow step whose non-comment code pulls with
    --autostash — the render family AND the narrow single-path lanes. Located
    structurally over the whole workflows dir so a new lane is swept the
    moment it is born, not when someone remembers to list it."""
    out = []
    for wf_path in sorted(list(WF.glob("*.yml")) + list(WF.glob("*.yaml"))):
        doc = yaml.safe_load(wf_path.read_text(encoding="utf-8"))
        for job_name, job in (doc.get("jobs") or {}).items():
            for step in job.get("steps", []):
                code = _code(step.get("run") or "")
                if "pull --rebase --autostash" in code:
                    out.append((f"{wf_path.name}:{job_name}:{step.get('name')}", code))
    return out


def test_every_autostash_pull_repo_wide_carries_the_guard_on_its_own_line():
    steps = _autostash_pull_steps()
    # 51 steps at the 2026-08-01 sweep (render family + 30 narrow-lane sites).
    # A census far below that has lost its discriminator, not its lanes.
    assert len(steps) >= 45, [s[0] for s in steps]
    for label, code in steps:
        for line in code.splitlines():
            if "pull --rebase --autostash" in line:
                assert "push_autostash_ok" in line, (
                    f"{label}: autostash pull without push_autostash_ok in the "
                    f"same condition (conflicted-apply containment, d29e4dd44d):\n{line}"
                )


def test_every_autostash_pulling_step_sources_the_library():
    """push_autostash_ok is defined in scripts/ci/push_retry.sh; a step that
    calls it without sourcing dies with `command not found` — under the retry
    loops' `if` that reads as an eternal lost race, never as a wiring bug."""
    steps = _autostash_pull_steps()
    for label, code in steps:
        assert "push_retry.sh" in code, (
            f"{label}: pulls with --autostash but never sources "
            "scripts/ci/push_retry.sh in the same step"
        )


def test_intl_etf_pull_is_guarded_even_without_autostash():
    """intl_etf pulls WITHOUT --autostash (so the census above cannot see it)
    but is wired anyway: the guard also sweeps autostash entries leaked into
    the shared runner checkout by other lanes' earlier unguarded runs."""
    doc = yaml.safe_load((WF / "intl_etf.yml").read_text(encoding="utf-8"))
    hits = []
    for job in doc["jobs"].values():
        for step in job.get("steps", []):
            code = _code(step.get("run") or "")
            for line in code.splitlines():
                if "git pull --rebase" in line:
                    hits.append((step.get("name"), line, code))
    assert hits, "intl_etf.yml lost its pull — check the census"
    for name, line, code in hits:
        assert "push_autostash_ok" in line, f"{name}: {line}"
        assert "push_retry.sh" in code, f"{name}: library not sourced"


def test_guard_functions_exist_in_the_library():
    lib = LIB.read_text(encoding="utf-8")
    assert "push_autostash_ok()" in lib
    assert "push_staged_clean()" in lib
    assert "push_staged_heal()" in lib
    # scoped drop: only git's own entry, matched by exact subject
    assert '= "autostash" ]' in lib
    # the scan must read WORKTREE bytes of changed paths, never index objects —
    # a --cached grep on the blobless render checkout hydrates ~594MB of
    # promised blobs, or silently passes when the promisor call fails
    assert "--cached --name-only" in lib, "changed-path enumeration disappeared"
    assert "git grep -l --cached" not in lib, (
        "index-object grep reintroduced — fail-open + promisor hydration (P0 review finding 1)"
    )
