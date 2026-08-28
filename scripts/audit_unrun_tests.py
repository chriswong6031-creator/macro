#!/usr/bin/env python3
"""Census: which pytest suites does NO workflow ever run, and how dark are they?

SCOPE IS THE WHOLE TREE, NOT `tests/`.  This census, `check_skip_only_suites.py` and
`check_ci_trigger_closure.py` were all hard-scoped to `tests/`, and therefore
structurally blind to the suites most likely to be dark.  Research packets here are
routinely fenced to files-only, so a packet's guard suite gets written next to the
instrument under `research/` instead of in `tests/` — and measured 2026-08-06 (#4693),
`research/prophet_us_audit/test_label_grading_battery.py` (16 tests, #4547) and
`research/signal_engine/test_buy_filters.py` (6 tests) had been named by no `run:`
step in any of the 75 workflows since they landed.  Never executed, while all three
censuses reported the repo covered.  Discovery now walks the repo, so a suite is
visible wherever its author put it.

A `test_`-shaped FILENAME is not a suite, and classifying by name would replace one
blind spot with a noisy one — see `defines_tests`.

Two independent holes, deliberately measured separately:

  UNRUN        the suite's filename appears in no `run:` step in any workflow or
               the packed legacy CI manifest. There is no broad `pytest tests/`
               anywhere in the repo — every invocation carries an explicit file
               list — so an unnamed suite is genuinely never executed by CI.

  UNTRIGGERABLE  nothing that would change the suite's verdict is matched by
               ci.yml's `on.pull_request.paths`, so the workflow cannot even START.
               Checked against the test file AND the modules the suite imports,
               with glob semantics (`engine/**` is a broad catch-all; exact-membership
               checks over-report darkness badly).

A suite that is both is STRICTLY DARK: no possible edit produces a signal.  Those are
ranked first, and within them the ones reachable from the nightly/render pipelines
rank highest — a silent break there moves shipped numbers with nothing going red.

THE CENSUS IS NOW A GATE (2026-08-09).  It reported for three weeks and the backlog
did not move: 969 unrun suites of 2,146 on the day it was armed, and six separate PRs
(#4567, #4589, #4709, #4710, #4800, #4826) each un-darkened ONE suite by hand while
nothing stopped the seventh from landing dark.  A report nobody is obliged to read
re-creates the trap it measures.  So the exit code now carries the finding — but only
for suites that are NEW, against two files:

  config/unrun_test_baseline.json    the pre-gate backlog, grandfathered.  SHRINK-ONLY:
                                     a row leaves when the suite is wired or deleted,
                                     and nothing is ever added.  Rows that no longer
                                     read as unrun WARN (prune them); they never red.

  config/unrun_test_waivers.yml      suite path → reason.  For a suite that must stay
                                     unrun with an owner and an argument, not a
                                     dumping ground: every waived-and-unrun row is
                                     printed with its reason on every run.

Wiring every unrun suite at once would blow the ci-pack budget, which is why the
backlog is grandfathered rather than gated — the tiers below stay triage input.  What
the gate buys is the ratchet: the 970th dark suite cannot ship silently.

SPARSE CHECKOUTS ARE ANSWERED FROM GIT, NOT SKIPPED (2026-08-14).  Session worktrees
omit `data/`, `site/`, `mockups/` and `verify_shots/` by default, and discovery used to
end at an `is_file()` probe that cannot tell "not in this repo" from "not checked out".
A suite under an omitted tree was therefore dropped from the census AND from the
"not a suite" disclosure, and the gate exited 0 where CI's full checkout would red.
Candidates under omitted trees are now read from HEAD, so the verdict is the same in
both checkouts; the run says which trees it could not see, and REFUSES outright if
those bytes cannot be reached at all.  See `sparse_omitted_dirs` / `suite_source`.

Usage:
    python3 scripts/audit_unrun_tests.py                     # summary table, then GATE
    python3 scripts/audit_unrun_tests.py --tier P0           # list one tier
    python3 scripts/audit_unrun_tests.py --json out.json     # full machine-readable rows
    python3 scripts/audit_unrun_tests.py --selftest          # discovery + gate round-trip
    python3 scripts/audit_unrun_tests.py --write-baseline    # re-freeze the grandfather list

Exit 1 means a suite is unrun and in neither file (or the waiver file is malformed).
`--selftest` and `--write-baseline` do not gate.
"""
from __future__ import annotations

import argparse
import ast
import fnmatch
import functools
import json
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.workflow_run_source import (  # noqa: E402
    WorkflowRunSourceError,
    resolve_run_source,
    resolved_workflow_text,
)

_TRUSTED_CONTROL_REPO_ROOT_ENV = "MASTERMIND_TRUSTED_CI_REPO_ROOT"


def _repository_root() -> Path:
    """Bind copied trusted control code to its explicitly selected candidate tree."""
    default = Path(__file__).resolve().parent.parent
    raw = os.environ.get(_TRUSTED_CONTROL_REPO_ROOT_ENV)
    if raw is None:
        return default
    if not raw or not Path(raw).is_absolute():
        raise RuntimeError(
            f"{_TRUSTED_CONTROL_REPO_ROOT_ENV} must be a non-empty absolute path"
        )
    candidate = Path(raw).resolve(strict=True)
    if Path.cwd().resolve() != candidate:
        raise RuntimeError(
            f"{_TRUSTED_CONTROL_REPO_ROOT_ENV} {candidate} does not match cwd "
            f"{Path.cwd().resolve()}"
        )
    if not (candidate / ".git").exists():
        raise RuntimeError(
            f"{_TRUSTED_CONTROL_REPO_ROOT_ENV} {candidate} is not a Git checkout"
        )
    return candidate


ROOT = _repository_root()
WORKFLOWS = ROOT / ".github/workflows"
CI_MANIFEST = ROOT / ".github/ci/legacy-jobs.yml"
# The two files the gate reads. Both are OPTIONAL on disk: a checkout without them
# gates every unrun suite, which is the correct failure direction for a ratchet —
# deleting the baseline cannot quietly disarm it.
BASELINE = ROOT / "config/unrun_test_baseline.json"
WAIVERS = ROOT / "config/unrun_test_waivers.yml"
# There is deliberately no `TESTS = ROOT / "tests"` constant any more. It was the
# scope that blinded all three guards at once, nothing imports it, and leaving it
# here would invite the next reader to narrow discovery back onto it.

# pytest's own default `python_files`.  This repo ships NO pytest configuration —
# no pytest.ini, no setup.cfg, no [tool.pytest] in pyproject — so collection uses
# exactly these two shapes and a file named anything else is never collected.
_SUITE_FILENAME = re.compile(r"^(?:test_.+|.+_test)\.py$")

# Trees that are not this repo's source.  The session-worktree entries are
# load-bearing, not defensive: the primary checkout carries 357,599 test-shaped
# files under `.claude/worktrees/` alone, so an unpruned walk turns a 2,017-row
# census into a 368,938-row one.  A census that large is noise, and noise is how a
# census stops being read — the exact failure mode these guards exist to end.
EXCLUDED_DIRS = frozenset({
    ".git", ".claude", ".claire", ".codex-worktrees", ".worktrees",
    "node_modules", "site-packages", "vendor",
    ".venv", "venv", ".tox", ".nox",
    "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "ObsidianBrain",          # a symlink VIEW over memory/ + research/, not source
})

FIRST_PARTY = ("engine", "scripts", "app", "collectors", "lib", "admin", "site")

# Workflows that BUILD and PUBLISH — a module they invoke feeds shipped numbers.
PIPELINE_WORKFLOWS = (
    "daily.yml", "render.yml", "engine-render.yml", "closing-bell.yml",
    "earlyclose.yml", "intraday.yml", "intraday-fastpath.yml", "asia-close.yml",
    "weekly.yml", "sentinel.yml",
)

# A module that writes under data/ advances a forward ledger; a break there is durable.
_LEDGER_WRITE = re.compile(
    r"to_parquet|to_csv|\.write_text|\.write_bytes|json\.dump|open\([^)]*['\"][wa]", re.S)
_DATA_PATH = re.compile(r"['\"]data/|DATA_DIR|DATA_ROOT|data_dir|/data/")

TIERS = (
    ("P0", "unrun + untriggerable + on a publish pipeline"),
    ("P1", "unrun, on a publish pipeline (triggerable)"),
    ("P2", "unrun + untriggerable + writes a data/ ledger"),
    ("P3", "unrun + untriggerable (other)"),
    ("P4", "unrun, writes a data/ ledger (triggerable)"),
    ("P5", "unrun (remainder)"),
)


# ─────────────────────────────────────────────────────────────────────────────
# suite discovery — the whole tree, classified by what pytest would collect
# ─────────────────────────────────────────────────────────────────────────────

def defines_tests(path: Path, src: str | None = None) -> bool:
    """Would pytest collect anything from this file?

    A `test_`-shaped FILENAME is not a suite.  Three of them in this tree are CLI
    measurement instruments — a `def main()` behind `if __name__ == "__main__"`, no
    test functions at all — and `pytest` exits 5 (no tests collected) on each:

        research/cn_prophet_audit/sector_intel_exante_test.py
        research/signal_engine/test_breadth_consume.py
        research/signal_engine/test_buyfilter.py

    Listing those as unrun work items would trade a blind census for a noisy one,
    and a guard that cries wolf gets ignored.  So the question asked is pytest's
    own: does the file define a `test*` function, or a `Test*` class holding one?
    (Those are `python_functions`/`python_classes` defaults, which apply because
    the repo overrides neither.)  Verified against real collection: of 2,020
    filename-shaped candidates this agrees with `pytest --collect-only` on all
    2,020 — 2,017 suites, and exactly the three instruments above.

    A file that will not parse returns True.  pytest ERRORS at collection on it,
    which is louder than a miscounted row, and over-including is the safe direction
    for every consumer here: two only report, and the third fails only on a suite
    some job actually NAMES.

    ``src`` lets a caller hand over bytes it already holds — the sparse-checkout
    path reads them from HEAD, where ``path`` names a file with no working copy.
    """
    try:
        tree = ast.parse(path.read_text(errors="ignore") if src is None else src)
    except (SyntaxError, ValueError):
        return True
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("test"):
                return True
        elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            if any(
                isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef))
                and member.name.startswith("test")
                for member in node.body
            ):
                return True
    return False


def _tracked_candidates(root: Path) -> list[str] | None:
    """Every file git knows about, or ``None`` when git cannot answer.

    `git ls-files` is the authoritative inventory — it is exactly "files in this
    repo" — so an untracked sibling worktree, a vendored tree or a virtualenv
    cannot leak in whatever it happens to be named.  The pruned walk below is the
    fallback for a checkout git cannot read (an exported tarball, a sandbox).
    """
    try:
        completed = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=root, capture_output=True, text=True, check=True, timeout=120,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return [entry for entry in completed.stdout.split("\0") if entry]


def _walked_candidates(root: Path) -> list[str]:
    """Fallback inventory: a PRUNED walk, never a bare rglob (see EXCLUDED_DIRS)."""
    found: list[str] = []
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            entries = list(current.iterdir())
        except OSError:
            continue
        for entry in entries:
            if entry.is_symlink():
                continue          # ObsidianBrain is a symlink VIEW, not source
            if entry.is_dir():
                if entry.name not in EXCLUDED_DIRS:
                    stack.append(entry)
            elif _SUITE_FILENAME.match(entry.name):
                found.append(entry.relative_to(root).as_posix())
    return found


# ─────────────────────────────────────────────────────────────────────────────
# sparse checkouts — a census over a smaller tree than CI's must not read green
# ─────────────────────────────────────────────────────────────────────────────
#
# Session worktrees are SPARSE by default (policy R8, .claude/hooks/worktree_create_sparse.py):
# `data/`, `site/`, `mockups/` and `verify_shots/` are tracked but not materialized.
# Discovery used to end at `(root / rel).is_file()`, which cannot tell "git does not
# track this" from "this checkout did not check it out" — so a suite under an omitted
# tree was dropped from BOTH lists, appeared in neither the tiers nor the "not a suite"
# disclosure, and the gate exited 0 while CI's full checkout would have red.  Measured
# 2026-08-14 on a default sparse worktree: 2,408 tracked pytest-shaped paths, 2,407
# candidates classified, and the missing one — `mockups/refs/.../tools/mutation_test.py`
# — named in neither `config/unrun_test_baseline.json` nor `config/unrun_test_waivers.yml`.
# The verdict was right only by luck: that file is a CLI instrument, so a full checkout
# drops it too.  The next one need not be.
#
# The fix is not to refuse — a blanket refusal would make this census unusable in every
# session worktree and push sessions into a 3.8 GiB full checkout to answer "is my new
# test wired", which is how guards get disabled.  An omitted tree has no working copy,
# but git still holds its bytes, so the census reads them from HEAD and reaches exactly
# the verdict a full checkout would.  Refusal is kept for the case where that recovery
# FAILS, because only then is the answer genuinely unknowable.


def sparse_omitted_dirs(root: Path = ROOT) -> tuple[str, ...]:
    """Top-level trees this checkout tracks but does not materialize.

    Delegates to ``scripts.worktree_sparse.missing_dirs`` — never an ``is_dir()``
    probe, which reads a 0-byte husk left by `git reset --hard` as present.  Any
    failure answers "not sparse": the detector must never break the census, and a
    full checkout (every CI lane) is the case that has to stay untouched.
    """
    try:
        from scripts.worktree_sparse import missing_dirs
    except Exception:  # noqa: BLE001
        return ()
    try:
        return tuple(missing_dirs(root))
    except Exception:  # noqa: BLE001
        return ()


def _sparse_remedy(omitted: tuple[str, ...]) -> str:
    """The one-line remedy every sparse refusal/disclosure carries.

    Shared with the other sparse-aware guards through ``worktree_sparse`` so the
    opt-in command is written down once; a local string here would drift the day
    that command changes.
    """
    try:
        from scripts.worktree_sparse import remedy_line
    except Exception:  # noqa: BLE001
        return (f"sparse worktree — {', '.join(sorted(omitted)) or 'heavy generated trees'} "
                f"not checked out; opt into a full checkout with: "
                f"python3 scripts/worktree_sparse.py full")
    return remedy_line(list(omitted))


def _git_stdout(root: Path, *args: str) -> str | None:
    """Text of a git command run in ``root``; None when git cannot answer."""
    try:
        done = subprocess.run(
            ["git", *args], cwd=root,
            capture_output=True, check=True, timeout=120,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.decode("utf-8", errors="ignore")


def _omitted_candidates(root: Path, omitted: tuple[str, ...], known: list[str]) -> list[str]:
    """Tracked paths under sparse-omitted trees that the inventory above missed.

    Normally none: this repo's worktrees run a full index, so `git ls-files` names
    every omitted file even though none is on disk.  With `index.sparse=true` the
    index collapses an omitted tree to a single directory entry and `ls-files`
    cannot name what is inside it at all — so any tree the inventory did not reach
    into is re-read from HEAD, which is sparse-index-proof.  Skipping the trees the
    inventory already covers keeps the common case free: `ls-tree -r` over all four
    omitted trees is ~57k paths and ~2s, against ~1 path that actually matters.
    """
    seen = {rel.split("/", 1)[0] for rel in known if "/" in rel}
    found: list[str] = []
    for name in omitted:
        if name in seen:
            continue
        listed = _git_stdout(root, "ls-tree", "-r", "--name-only", "-z", "HEAD", "--", name)
        if listed is None:
            continue
        found.extend(rel for rel in listed.split("\0") if rel)
    return found


def suite_source(rel: str, root: Path | None = None) -> str | None:
    """Source of a candidate, whether or not this checkout materializes it.

    Disk first, so a full checkout behaves exactly as it always has.  A path that
    is absent only because a sparse profile omitted its tree is read from HEAD —
    the omitted trees carry no working copy, so HEAD is both the only truth
    available and the state a full checkout would materialize.  ``None`` means the
    bytes could not be reached at all, which callers must treat as fail-closed.
    """
    base = ROOT if root is None else root
    path = base / rel
    if path.is_file():
        return path.read_text(errors="ignore")
    top = rel.split("/", 1)[0]
    if top not in sparse_omitted_dirs(base):
        return None       # not sparse — a stale index entry or a deleted file
    return _git_stdout(base, "cat-file", "blob", f"HEAD:{rel}")


@functools.lru_cache(maxsize=None)
def _classify(root_str: str) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    """``(real suites, filename-shaped non-suites, unreadable)`` — cached per root.

    Keyed on the root string so a caller that repoints ``ROOT`` (the guards' own
    tests do, to seed a suite into a synthetic tree) gets a fresh classification
    instead of a stale cache.

    ``unreadable`` is the fail-closed third bucket: a candidate this checkout does
    not materialize AND whose bytes git would not hand over.  It is never silently
    dropped — ``main`` refuses on a non-empty one.
    """
    root = Path(root_str)
    names = _tracked_candidates(root)
    if names is None:
        names = _walked_candidates(root)
    omitted = sparse_omitted_dirs(root)
    names = list(names) + _omitted_candidates(root, omitted, names)
    candidates = sorted({
        rel for rel in names
        if _SUITE_FILENAME.match(rel.rsplit("/", 1)[-1])
        and not any(part in EXCLUDED_DIRS for part in rel.split("/")[:-1])
        and ((root / rel).is_file() or rel.split("/", 1)[0] in omitted)
    })
    suites: list[str] = []
    non_suites: list[str] = []
    unreadable: list[str] = []
    for rel in candidates:
        src = suite_source(rel, root)
        if src is None:
            unreadable.append(rel)
        elif defines_tests(root / rel, src=src):
            suites.append(rel)
        else:
            non_suites.append(rel)
    return tuple(suites), tuple(non_suites), tuple(unreadable)


def discover_suites() -> list[str]:
    """Repo-relative paths of every real pytest suite, wherever it lives."""
    return list(_classify(str(ROOT))[0])


def not_a_suite() -> list[str]:
    """Filename-shaped files that collect nothing — printed, never silently dropped."""
    return list(_classify(str(ROOT))[1])


def unreadable_candidates() -> list[str]:
    """Filename-shaped files this checkout can neither read nor rule out."""
    return list(_classify(str(ROOT))[2])


def _workflow_blob() -> str:
    """Text of every workflow's `run:` STEPS ONLY — never its comments.

    This used to be the raw file text, so a suite named in a YAML COMMENT counted as
    "run by CI" (OIP E8, 2026-07-29: a `# Anti-rot: tests/test_x.py` line in render.yml
    made the census report a wholly-unwired suite as covered — the census's own vacuous
    green, in the tool whose entire job is finding dark tests).  Parsing the YAML and
    concatenating `run:` scalars keeps prose out of the verdict.

    Fail-open per file: an unparseable workflow falls back to its raw text, because
    over-reporting coverage for one file is better than crashing a reporting tool.

    A step body extracted to ``scripts/ci/<name>.sh`` (512KB-cap diet) is resolved
    back to its shell source, so a suite named only inside an extracted block still
    counts as run. ``WorkflowRunSourceError`` is re-raised past the fail-open below
    on purpose: an unresolvable indirection is exactly the case where falling back
    to raw text would under-report coverage and mark a covered suite dark.
    """
    paths = sorted(WORKFLOWS.glob("*.yml"))
    if CI_MANIFEST.exists():
        paths.append(CI_MANIFEST)
    chunks: list[str] = []
    for p in paths:
        raw = p.read_text(errors="ignore")
        try:
            doc = yaml.safe_load(raw) or {}
            runs: list[str] = []
            for job in (doc.get("jobs") or {}).values():
                if not isinstance(job, dict):
                    continue
                for step in job.get("steps") or []:
                    if isinstance(step, dict) and isinstance(step.get("run"), str):
                        runs.append(resolve_run_source(step["run"], ROOT))
                    # reusable-workflow / composite indirection: keep `with:` values too
                    if isinstance(step, dict) and isinstance(step.get("with"), dict):
                        runs += [str(v) for v in step["with"].values()]
            chunks.append("\n".join(runs))
        except WorkflowRunSourceError:
            raise
        except Exception:  # noqa: BLE001 — reporting tool: never crash on one bad file
            chunks.append(raw)
    return "\n".join(chunks)


def _ci_paths() -> list[str]:
    doc = yaml.safe_load((WORKFLOWS / "ci.yml").read_text())
    on = doc[True] if True in doc else doc["on"]
    return list((on.get("pull_request") or {}).get("paths") or [])


def _matched(rel: str, patterns: list[str]) -> bool:
    """GitHub Actions paths semantics: exact, fnmatch, or `prefix/**` subtree."""
    for pat in patterns:
        if pat == rel:
            return True
        if "*" in pat:
            if fnmatch.fnmatch(rel, pat):
                return True
            if pat.endswith("**") and rel.startswith(pat[:-2]):
                return True
    return False


def _subject_modules(path: Path, src: str | None = None) -> set[str]:
    """First-party modules a suite imports, plus repo-relative files it names.

    `from pkg import a, b` binds pkg.a / pkg.b when those are submodules; resolving
    only `pkg` collapses hundreds of suites onto pkg/__init__.py and silently
    understates how dark they are.

    ``src`` carries bytes the caller already holds, so a suite recovered from HEAD
    in a sparse checkout is tiered like any other instead of raising on the read.
    """
    if src is None:
        src = path.read_text(errors="ignore")
    mods: set[str] = set()
    try:
        tree = ast.parse(src)
    except SyntaxError:
        tree = None
    if tree is not None:
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names = [node.module]
                if node.module.split(".")[0] in FIRST_PARTY:
                    for alias in node.names:
                        cand = f"{node.module}.{alias.name}"
                        rel = cand.replace(".", "/")
                        if (ROOT / f"{rel}.py").exists() or (ROOT / rel / "__init__.py").exists():
                            names.append(cand)
            for name in names:
                if name.split(".")[0] in FIRST_PARTY:
                    mods.add(name)
    for m in re.finditer(r'import_module\(\s*["\']([\w.]+)["\']', src):
        if m.group(1).split(".")[0] in FIRST_PARTY:
            mods.add(m.group(1))
    for m in re.finditer(
        r'["\']((?:engine|scripts|app|collectors|lib|admin|site|templates|config)'
        r'/[\w./-]+\.(?:py|js|mjs|ts|yml|yaml|json))["\']', src
    ):
        mods.add("@" + m.group(1))
    return mods


def _to_relpaths(mod: str) -> list[str]:
    if mod.startswith("@"):
        return [mod[1:]]
    base = mod.replace(".", "/")
    found = [c for c in (f"{base}.py", f"{base}/__init__.py") if (ROOT / c).exists()]
    return found or [f"{base}.py"]


def _pipeline_modules() -> set[str]:
    """Modules invoked by the build/publish workflows (module and script forms).

    Read through ``resolved_workflow_text`` so a builder invoked only from an
    extracted ``scripts/ci/<name>.sh`` body still counts as on-pipeline. This is
    a severity input, not a pass/fail one — ``census`` tiers a suite P0/P1 when a
    subject module is on the pipeline — so losing modules here does not red
    anything, it quietly DEMOTES suites out of the top tiers. Measured on the
    2026-08-12 diet: 13 modules (``engine.shock_deescalation``,
    ``scripts.build_options_prophet``, ``scripts.build_impulse``, ...) went
    invisible with no failing check anywhere.
    """
    out: set[str] = set()
    for name in PIPELINE_WORKFLOWS:
        p = WORKFLOWS / name
        if not p.exists():
            continue
        src = resolved_workflow_text(p, ROOT)
        cands = set(
            m.group(1) for m in
            re.finditer(r'\b(?:python3?\s+-m\s+|run_py\s+"[^"]*"\s+)([\w.]+)', src)
        )
        cands |= set(
            m.group(1).replace("/", ".")[:-3] for m in
            re.finditer(r"\b(?:python3?)\s+(scripts/[\w/]+\.py)", src)
        )
        for c in cands:
            rel = c.replace(".", "/") + ".py"
            if (ROOT / rel).exists():
                out.add(rel)
    return out


def _writes_ledger(relpaths: list[str]) -> bool:
    for rel in relpaths:
        f = ROOT / rel
        if not f.is_file():
            continue
        src = f.read_text(errors="ignore")
        if _LEDGER_WRITE.search(src) and _DATA_PATH.search(src):
            return True
    return False


def _named_by_a_run_step(rel: str, blob: str, ambiguous: frozenset[str]) -> bool:
    """Does some workflow `run:` step name this suite?

    Path first.  The BASENAME fallback is real — a step that cd's into a directory
    names the file alone — but it is only sound while the basename identifies exactly
    one suite.  Measured 2026-08-09: one basename in this tree is shared,
    `test_price_ladder.py`, living in both `tests/` and `research/prophet_us_audit/`.
    Both were unrun, so the collision was harmless until the hour the research one was
    wired — at which point the `tests/` one started reading as COVERED with nothing
    running it, and would have vanished from the backlog it belongs in.  A suite that
    reads green because of a sibling's NAME is this census's own failure mode, so an
    ambiguous basename demands the full path.
    """
    if rel in blob:
        return True
    name = rel.rsplit("/", 1)[-1]
    return name not in ambiguous and name in blob


def census() -> list[dict]:
    blob = _workflow_blob()
    patterns = _ci_paths()
    pipeline = _pipeline_modules()
    suites = discover_suites()
    shared = Counter(rel.rsplit("/", 1)[-1] for rel in suites)
    ambiguous = frozenset(n for n, seen in shared.items() if seen > 1)
    rows = []
    for rel_test in suites:
        path = ROOT / rel_test
        if _named_by_a_run_step(rel_test, blob, ambiguous):
            continue                                    # named by some run: step
        subjects = sorted({
            rel
            for mod in _subject_modules(path, src=suite_source(rel_test))
            for rel in _to_relpaths(mod)
        })
        real = [s for s in subjects
                if not s.startswith("tests") and not s.endswith("__init__.py")]
        on_pipeline = sorted(s for s in real if s in pipeline)
        triggerable = (_matched(rel_test, patterns)
                       or any(_matched(s, patterns) for s in subjects))
        ledger = _writes_ledger(real)
        if on_pipeline and not triggerable:
            tier = "P0"
        elif on_pipeline:
            tier = "P1"
        elif not triggerable and ledger:
            tier = "P2"
        elif not triggerable:
            tier = "P3"
        elif ledger:
            tier = "P4"
        else:
            tier = "P5"
        rows.append(dict(test=rel_test, tier=tier, triggerable=triggerable,
                         writes_ledger=ledger, pipeline_subjects=on_pipeline,
                         subjects=real))
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# the gate — grandfathered backlog + reasoned waivers, everything else is red
# ─────────────────────────────────────────────────────────────────────────────

_BASELINE_NOTE = (
    "Shrink-only grandfather list: the unrun-suite backlog as it stood on the day "
    "scripts/audit_unrun_tests.py started gating. NEVER add to it. A new suite gets "
    "wired into the job that owns its subject, or gets a row in "
    "config/unrun_test_waivers.yml with a reason. Rows leave this list when the suite "
    "is wired or deleted (the gate warns on rows that no longer read as unrun); "
    "regenerate with `python scripts/audit_unrun_tests.py --write-baseline`."
)


class _Unparseable(str):
    """A waivers file YAML could not read, carried into the gate as data.

    The schema is enforced in `gate()` and nowhere else, so the file path and the
    unit-test path fail identically. A parse error is just another malformed shape;
    subclassing str keeps it inert everywhere except the one isinstance below.
    """


def _load_waivers() -> object:
    """Raw parsed waivers — deliberately UNvalidated (see `_validate_waivers`).

    A missing file is not an error: it means no waivers, and the gate then judges
    every unrun suite against the baseline alone.
    """
    if not WAIVERS.exists():
        return {}
    try:
        return yaml.safe_load(WAIVERS.read_text()) or {}
    except yaml.YAMLError as exc:
        return _Unparseable(f"{WAIVERS.name} does not parse as YAML: {exc}")


def _validate_waivers(waivers: object) -> tuple[dict[str, str], list[str]]:
    """``(normalized waivers, malformed complaints)`` — one enforcement point.

    A waiver with no reason is the failure this schema exists to prevent: it reads
    exactly like the baseline, silently, and turns the exception list back into a
    dumping ground. An unreadable waiver set is fatal rather than ignored, because
    ignoring it would red every waived suite at once and bury the real complaint.
    """
    if isinstance(waivers, _Unparseable):
        return {}, [str(waivers)]
    if not isinstance(waivers, dict):
        return {}, [
            f"config/{WAIVERS.name} must be a mapping of suite path -> reason, "
            f"got {type(waivers).__name__}"
        ]
    normalized: dict[str, str] = {}
    problems: list[str] = []
    for key, reason in waivers.items():
        if not isinstance(key, str) or not key.strip():
            problems.append(f"config/{WAIVERS.name} has a non-string suite path: {key!r}")
            continue
        if not isinstance(reason, str) or not reason.strip():
            problems.append(
                f"config/{WAIVERS.name}: {key} has no reason — a waiver without an "
                f"argument is a baseline row wearing a disguise"
            )
            continue
        normalized[key] = reason.strip()
    return normalized, problems


def _load_baseline() -> set[str]:
    """Grandfathered suite paths. Keys starting with `_` are prose for the reader."""
    if not BASELINE.exists():
        return set()
    doc = json.loads(BASELINE.read_text())
    rows: set[str] = set()
    for key, value in doc.items():
        if key.startswith("_"):
            continue
        if isinstance(value, list):
            rows.update(str(entry) for entry in value)
    return rows


def _gated_findings(unrun: list[str], baseline: set[str],
                    normalized: dict[str, str]) -> list[str]:
    """Suite paths ``gate()`` exits 1 on: unrun and named in neither file.

    Factored out so ``gated_unrun_suites()`` below (the census/gate function
    ``scripts/check_contract_delta.py`` imports for its differential contract-delta
    gate) computes the identical set ``gate()`` itself reds on, with no second copy
    of the filter to drift.
    """
    return [rel for rel in unrun if rel not in baseline and rel not in normalized]


def gated_unrun_suites() -> list[str]:
    """Suite paths ``main()``'s gate would exit 1 on right now, with no printing.

    Mirrors the CLI's own pipeline exactly (``census`` -> unrun -> baseline/waiver
    filter) as a pure function, for callers that need the gated set itself rather
    than an exit code — currently ``scripts/check_contract_delta.py``'s PR-vs-base
    delta, which needs to know WHICH suites are unwired on each side, not just
    whether any are.

    Raises ``RuntimeError`` if the waivers file is malformed — the same condition
    that makes the real CLI refuse rather than compute a gate, surfaced as an
    exception here so a diffing caller does not mistake "unreadable" for "clean".
    """
    rows = census()
    unrun = sorted(r["test"] for r in rows)
    baseline = _load_baseline()
    normalized, malformed = _validate_waivers(_load_waivers())
    if malformed:
        raise RuntimeError(
            f"config/{WAIVERS.name} is malformed: " + "; ".join(malformed)
        )
    return _gated_findings(unrun, baseline, normalized)


def gate(unrun: list[str], baseline: set[str], waivers: object,
         suites: set[str]) -> int:
    """0 unless a suite is unrun and in neither file. Pure: prints, reads nothing."""
    normalized, malformed = _validate_waivers(waivers)
    if malformed:
        for detail in malformed:
            print(f"::error title=unrun-waivers-malformed::{detail}", flush=True)
        return 1

    unrun_set = set(unrun)

    # Visible accounting, never an annotation: a waiver is only honest while its
    # reason stays in front of whoever reads this output.
    waived_live = sorted(unrun_set & set(normalized))
    if waived_live:
        print(f"\n  waived ({len(waived_live)}) — unrun on purpose, "
              f"config/{WAIVERS.name}:")
        for rel in waived_live:
            print(f"    {rel}\n      {normalized[rel]}")

    for rel in sorted(baseline - unrun_set):
        why = "wired into a job" if rel in suites else "deleted or renamed"
        print(f"::warning title=stale-unrun-baseline::{rel} is no longer an unrun "
              f"suite ({why}) — prune it from config/{BASELINE.name}", flush=True)
    for rel in sorted(set(normalized) - unrun_set):
        why = "wired into a job" if rel in suites else "deleted or renamed"
        print(f"::warning title=stale-unrun-waiver::{rel} is no longer an unrun suite "
              f"({why}) — delete its row from config/{WAIVERS.name}", flush=True)
    # The waiver wins where both name a suite — it carries the reason — so the
    # baseline row is pure duplication and the one to drop.
    for rel in sorted(baseline & set(normalized)):
        print(f"::warning title=stale-unrun-baseline::{rel} is both grandfathered and "
              f"waived; the waiver is the reason of record — prune the row from "
              f"config/{BASELINE.name}", flush=True)

    findings = _gated_findings(unrun, baseline, normalized)
    for rel in findings:
        print(
            f"::error title=unrun-suite::{rel} is a collecting pytest suite named by "
            f"no run: step in any workflow — wire it into the job that owns its "
            f"subject (see the signal-contract research-resident steps in "
            f".github/ci/legacy-jobs.yml for the pattern) or add it to "
            f"config/{WAIVERS.name} with a reason",
            flush=True,
        )
    return 1 if findings else 0


def _write_baseline(unrun: list[str], waivers: object) -> int:
    """Re-freeze the grandfather list. Refuses to run on an unreadable waiver set."""
    normalized, malformed = _validate_waivers(waivers)
    if malformed:
        for detail in malformed:
            print(f"::error title=unrun-waivers-malformed::{detail}", flush=True)
        return 1
    grandfathered = sorted(rel for rel in set(unrun) if rel not in normalized)
    payload = {
        "_frozen": "2026-08-09",
        "_note": _BASELINE_NOTE,
        "grandfathered": grandfathered,
    }
    BASELINE.write_text(json.dumps(payload, indent=1) + "\n")
    print(f"\nwrote {BASELINE} ({len(grandfathered)} grandfathered, "
          f"{len(normalized)} waived)")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tier", help="list the suites in one tier (P0..P5)")
    ap.add_argument("--json", type=Path, help="write all rows as JSON")
    ap.add_argument("--selftest", action="store_true",
                    help="round-trip discovery and classification against fixtures")
    ap.add_argument("--write-baseline", action="store_true",
                    help="re-freeze config/unrun_test_baseline.json from this census")
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()

    unreadable = unreadable_candidates()
    if unreadable:
        # Fail closed, the same posture check_template_site_sync.py takes: these
        # paths are tracked, pytest-shaped, and this checkout can neither read them
        # nor rule them out, so every verdict below is a guess. Never exit 0 here.
        print(f"unrun-test census REFUSED: {_sparse_remedy(sparse_omitted_dirs(ROOT))}")
        print(f"  {len(unreadable)} tracked candidate(s) could not be read from disk "
              f"or from HEAD — classify them or the gate is a guess:")
        for rel in unreadable:
            print(f"    {rel}")
        return 1

    omitted = sparse_omitted_dirs(ROOT)
    if omitted:
        # Never a ::warning — CI runs this on a full checkout, so an annotation here
        # would only ever fire where no Actions summary exists to carry it.
        print(f"NOTE: {_sparse_remedy(omitted)}")
        print("      Their contents were read from HEAD, so the counts and the gate "
              "verdict below match a full checkout — but nothing here was executed "
              "against the files themselves.")
        print()

    rows = census()
    suites = discover_suites()
    excluded = not_a_suite()
    outside = [s for s in suites if not s.startswith("tests/")]
    counts = Counter(r["tier"] for r in rows)
    dark = sum(1 for r in rows if not r["triggerable"])

    print(f"pytest suites (whole tree) : {len(suites)}")
    print(f"  of which outside tests/  : {len(outside)}")
    print(f"  never run by any workflow : {len(rows)}")
    print(f"  ... of which STRICTLY DARK (also untriggerable) : {dark}")
    print()
    for tier, label in TIERS:
        print(f"  {tier}  {counts.get(tier, 0):5d}  {label}")

    # Printed, never silently dropped: a reader who greps for one of these names
    # has to be able to see WHY it is absent from the tiers above.
    if excluded:
        print(f"\n  not a suite ({len(excluded)}) — pytest-shaped filename, collects "
              f"nothing (CLI instruments):")
        for rel in excluded:
            print(f"    {rel}")

    if outside:
        print(f"\n  suites outside tests/ ({len(outside)}) — invisible to this census "
              f"before 2026-08-06:")
        for rel in outside:
            unrun = any(r["test"] == rel for r in rows)
            print(f"    {rel}  {'UNRUN' if unrun else 'run by a job'}")

    if args.tier:
        want = args.tier.upper()
        print(f"\n=== {want} ===")
        for r in rows:
            if r["tier"] == want:
                subj = ", ".join(r["pipeline_subjects"] or r["subjects"][:3]) or "(none)"
                print(f"  {r['test']:56s} {subj}")

    if args.json:
        args.json.write_text(json.dumps(rows, indent=1))
        print(f"\nwrote {args.json} ({len(rows)} rows)")

    unrun = sorted(r["test"] for r in rows)
    waivers = _load_waivers()
    if args.write_baseline:
        return _write_baseline(unrun, waivers)
    # --tier and --json are report SHAPES, not report-only modes: a run that gates
    # for one caller and not another is a gate that can be turned off by a flag.
    rc = gate(unrun, _load_baseline(), waivers, set(suites))
    if omitted:
        # Repeated under the verdict on purpose: the banner above scrolls off, and a
        # bare "OK" is exactly what a reader would otherwise carry away from a tree
        # smaller than CI's.
        print(f"NOTE: verdict produced in a sparse checkout — {_sparse_remedy(omitted)}")
    return rc


# ─────────────────────────────────────────────────────────────────────────────
# selftest — a census that stops seeing is worse than no census
# ─────────────────────────────────────────────────────────────────────────────

_FIXTURE_SUITE = "import pytest\n\n\ndef test_thing():\n    assert True\n"
_FIXTURE_CLASS_SUITE = (
    "class TestBattery:\n"
    "    def test_case(self):\n"
    "        assert True\n"
)
# The shape of all three real non-suites: a CLI instrument that pytest exits 5 on.
_FIXTURE_INSTRUMENT = (
    "import sys\n\n\n"
    "def main(argv=None):\n"
    "    print('measurement')\n"
    "    return 0\n\n\n"
    'if __name__ == "__main__":\n'
    "    sys.exit(main(sys.argv[1:]))\n"
)


def _selftest() -> int:
    import contextlib
    import io
    import tempfile

    failures: list[str] = []
    global ROOT
    original = ROOT

    # 1. Discovery reaches outside tests/ — the whole point of the widening.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for rel, body in (
            ("tests/test_in_tests.py", _FIXTURE_SUITE),
            ("research/packet/test_beside_the_instrument.py", _FIXTURE_SUITE),
            ("research/packet/test_class_based.py", _FIXTURE_CLASS_SUITE),
            ("research/packet/test_instrument.py", _FIXTURE_INSTRUMENT),
            ("research/packet/sector_exante_test.py", _FIXTURE_INSTRUMENT),
            ("scripts/research/test_nested.py", _FIXTURE_SUITE),
            (".claude/worktrees/other/tests/test_someone_elses.py", _FIXTURE_SUITE),
            ("node_modules/pkg/test_vendored.py", _FIXTURE_SUITE),
            ("research/packet/helper.py", _FIXTURE_SUITE),
        ):
            target = root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(body)
        try:
            ROOT = root
            found = set(discover_suites())
            skipped = set(not_a_suite())
        finally:
            ROOT = original

    for want in (
        "tests/test_in_tests.py",
        "research/packet/test_beside_the_instrument.py",
        "research/packet/test_class_based.py",
        "scripts/research/test_nested.py",
    ):
        if want not in found:
            failures.append(f"discovery missed {want}")
    for wrong, why in (
        ("research/packet/test_instrument.py", "a CLI instrument collects no tests"),
        ("research/packet/sector_exante_test.py", "a *_test.py instrument likewise"),
        ("research/packet/helper.py", "not a pytest filename shape"),
        (".claude/worktrees/other/tests/test_someone_elses.py",
         "another session's worktree is not this repo's source"),
        ("node_modules/pkg/test_vendored.py", "vendored code is not this repo's source"),
    ):
        if wrong in found:
            failures.append(f"discovery returned {wrong}: {why}")
    for want in ("research/packet/test_instrument.py",
                 "research/packet/sector_exante_test.py"):
        if want not in skipped:
            failures.append(f"{want} must be REPORTED as a non-suite, not dropped")

    # 2. Classification agrees with pytest on the real tree's known instruments.
    for rel in ("research/cn_prophet_audit/sector_intel_exante_test.py",
                "research/signal_engine/test_breadth_consume.py",
                "research/signal_engine/test_buyfilter.py"):
        target = original / rel
        if target.is_file() and defines_tests(target):
            failures.append(f"{rel} collects no tests but classified as a suite")

    # 3. The gate itself, exercised PURELY — no ROOT repoint, no files on disk, so a
    #    census that cannot see is caught above and a gate that cannot judge is caught
    #    here. stdout is captured: a PASSING selftest must not stamp its fixture's
    #    ::error lines onto the real run's Actions summary.
    def _gate(unrun, baseline, waivers, suites=()) -> tuple[int, str]:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = gate(list(unrun), set(baseline), waivers, set(suites))
        return code, buf.getvalue()

    def _has(out: str, prefix: str) -> bool:
        """Line-START, per house law — an annotation with anything in front is dropped."""
        return any(line.startswith(prefix) for line in out.splitlines())

    new = "research/packet/test_newly_dark.py"
    old = "tests/test_grandfathered.py"

    code, out = _gate([new], set(), {}, {new})
    if code != 1:
        failures.append("gate() cleared a suite that is unrun, unbaselined and unwaived")
    if not _has(out, "::error title=unrun-suite::"):
        failures.append("gate() failed without a line-start ::error unrun-suite annotation")

    code, out = _gate([new], {new}, {}, {new})
    if code != 0:
        failures.append("gate() reds a grandfathered suite; the backlog is not a to-do list")

    code, out = _gate([new], set(), {new: "owner + argument"}, {new})
    if code != 0:
        failures.append("gate() reds a waived suite")
    if "owner + argument" not in out:
        failures.append("gate() hid a live waiver's reason; a silent waiver is a baseline row")

    # Stale rows are a prune instruction, never a red: a suite that got WIRED must not
    # break the branch that wired it.
    code, out = _gate([], {old}, {}, {old})
    if code != 0 or not _has(out, "::warning title=stale-unrun-baseline::"):
        failures.append("a stale baseline row must warn and exit 0 (got "
                        f"{code}, warned={_has(out, '::warning title=stale-unrun-baseline::')})")
    code, out = _gate([], set(), {old: "why"}, {old})
    if code != 0 or not _has(out, "::warning title=stale-unrun-waiver::"):
        failures.append("a stale waiver must warn and exit 0 (got "
                        f"{code}, warned={_has(out, '::warning title=stale-unrun-waiver::')})")
    code, out = _gate([new], {new}, {new: "why"}, {new})
    if code != 0 or not _has(out, "::warning title=stale-unrun-baseline::"):
        failures.append("a suite in BOTH files must warn about the duplication and exit 0")

    for bad, why in (
        (["not", "a", "mapping"], "a list is not a suite path -> reason mapping"),
        ({new: ""}, "an empty reason is a baseline row wearing a disguise"),
        ({new: 232}, "a non-string reason carries no argument"),
        (_Unparseable("boom"), "an unreadable waiver set must not silently red every waiver"),
    ):
        code, out = _gate([new], {new}, bad, {new})
        if code != 1 or not _has(out, "::error title=unrun-waivers-malformed::"):
            failures.append(f"malformed waivers accepted ({why})")

    if failures:
        for failure in failures:
            print(f"::error title=unrun-census-selftest::{failure}", flush=True)
        return 1
    print("SELFTEST OK — discovery reaches outside tests/, instruments classified out, "
          "gate reds only the unbaselined and unwaived.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
