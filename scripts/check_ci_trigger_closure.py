#!/usr/bin/env python3
"""Guard: a suite's TRIGGER PATHS must cover the modules the suite measures.

The fourth darkness class, and the reverse direction of every census already here:

    UNRUN          no `run:` step names the suite            (audit_unrun_tests.py)
    UNTRIGGERABLE  NOTHING the suite reads is in ci.yml's
                   `on.pull_request.paths`                   (audit_unrun_tests.py)
    SKIP-ONLY      named, triggerable, and every test skips  (check_skip_only_suites.py)
    TRIGGER GAP    named, and SOME of what it reads is in the path filter, so the
                   suite is not "dark" by any existing measure — but ONE module in
                   its closure is not, and an edit to exactly that module ships
                   without ever running the guard that measures it.   ← THIS FILE

SCOPE IS THE WHOLE TREE.  All three of the censuses above were hard-scoped to
`tests/`; this one by a `_TEST_PATH` regex that required a literal `tests/` prefix,
so a `research/`-resident suite named in a `run:` step was invisible to the closure
gate even once it WAS wired.  Research packets are routinely fenced to files-only,
which is why their guard suites live beside the instrument rather than in `tests/`.
Suites now come from ``audit_unrun_tests.discover_suites`` and run-step tokens are
resolved against that inventory, so a `test_`-shaped CLI instrument invoked by a
`run:` step is not mistaken for a suite whose closure must be reachable (#4693).

`audit_unrun_tests.py` asks "can ANY edit start this job" (an `any()` over the
closure).  That is satisfied by a single matched file — usually the test itself.
The question it never asks is the one that matters at merge time: for the module a
PR actually touches, does the guard run?  A suite that pins `engine/foo.py` and is
reachable only through `tests/test_foo.py` is a guard with a hole exactly the shape
of its subject.

WHY THIS EXISTS AS CODE AND NOT AS A COMMENT.  The lesson is already written down
in this repo four times — "a guard whose own edit cannot start the workflow is only
half wired" (#3488), the #4559 fixture-only heal, and the "both halves listed on
purpose" comments scattered through ci.yml.  Prose in a 1,700-entry path list is
not enforcement: nobody re-derives a closure by hand while adding one line.

WHAT IT CHECKS (static — nothing is executed)

  1. Discover the PR gates: every workflow with an `on.pull_request` trigger.  A
     workflow with NO `paths:` key starts on every PR, so anything it runs is
     covered unconditionally (fences.yml).  A workflow WITH `paths:` governs both
     its own `run:` steps and any job manifest it hands to a runner
     (`--workflow .github/ci/legacy-jobs.yml`), which is how all 159 packed legacy
     jobs inherit ci.yml's single filter.
  2. For every `tests/*.py` a governed `run:` step names, resolve the first-party
     files it reads: imports, `import_module("...")`, repo-relative path literals,
     and `ROOT / "a" / "b.py"` segment joins (how a suite reaches a `research/`
     script that lives outside any package).  Every resolved path must EXIST — a
     path that is not in the tree cannot be edited, so it cannot be a gap.
  3. A module is REACHABLE when some PR-triggered workflow that runs the suite
     would start on an edit to that module alone, under GitHub's `paths` glob
     semantics (exact, fnmatch, or `prefix/**` subtree).

  FAIL when a module in a suite's closure is reachable by no gate that runs it.

DEPTH.  The gate is DIRECT reads only (depth 1).  `--depth N` widens the report to
transitive reads and is deliberately NOT gated: past depth 1 the path-literal
heuristic starts resolving placeholder strings (`config/foo.yml` is reached at
depth 3 from a docstring example), and a guard that cries wolf gets ignored, which
is the failure mode this file exists to end.

Usage:
    python3 scripts/check_ci_trigger_closure.py             # gate (exit 1 on findings)
    python3 scripts/check_ci_trigger_closure.py --report    # full census, exit 0
    python3 scripts/check_ci_trigger_closure.py --depth 3   # transitive report
    python3 scripts/check_ci_trigger_closure.py --selftest  # guard's own round-trip
"""
from __future__ import annotations

import argparse
import ast

import json
import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Reuse, do not re-implement: the census owns repo layout and the import-resolution
# rules; run_ci_pack owns the manifest's fail-closed per-job parse.
from scripts.audit_unrun_tests import (  # noqa: E402
    CI_MANIFEST,
    FIRST_PARTY,
    ROOT,
    WORKFLOWS,
    discover_suites,
)
from scripts.run_ci_pack import ManifestError, load_legacy_jobs  # noqa: E402

# Directories a repo-relative string literal may name.  Import ROOTS stay
# FIRST_PARTY (you cannot `import research`); these are the trees a suite reaches
# by path instead — research/ scripts live outside any package and are loaded with
# spec_from_file_location, which is exactly how the reclaim-veto packet is read.
#
# `data/` is deliberately EXCLUDED.  A suite reading a nightly artifact is a
# different class: those files are rewritten by the pipeline, not edited by a PR,
# so demanding a trigger entry for each would add 150+ findings that no author can
# act on.  Subject = something a human edits.
LITERAL_DIRS = tuple(FIRST_PARTY) + (
    "research", "tools", "config", "templates", "contracts", "ops",
)

# A suite named in a `run:` step, AS WRITTEN — any directory, both pytest filename
# shapes.  This used to require a literal `tests/` prefix and accept ANY `.py` under
# it, which was wrong in both directions: it could not see a wired `research/` suite
# at all, and it treated `tests/conftest.py` as a suite whose closure must be
# reachable.  Tokens are resolved against the real inventory in `suites_by_source`,
# so a stale path and a `test_`-shaped CLI instrument both drop out by construction.
_TEST_PATH = re.compile(
    r"(?<![\w/.-])((?:[\w.-]+/)*(?:test_[\w-]+|[\w-]+_test)\.py)(?![\w])"
)
_MANIFEST_REF = re.compile(r"--workflow\s+(\.github/[\w./-]+\.ya?ml)")
_IMPORT_MODULE = re.compile(r'import_module\(\s*["\']([\w.]+)["\']')
# FULL-matched against a string constant's value.  "A path is the whole string" is
# the third form of the same rule the docstring and comment exclusions apply: a
# path inside a SENTENCE is prose, not a read.  Both shapes are live here —
#
#   PRESS_MUST_RESTART = ["app/deploy/marketing-press-feeds.service", ...]   a read
#   assert ..., "... (see app/deploy/README.md § Press properties (W1.5))"   a pointer
#
# — and the second one costs a path entry for a README no suite ever opens.  An
# f-string's literal chunks carry their surrounding prose, so they fail this too.
_PATH_LITERAL = re.compile(
    r"(?:" + "|".join(LITERAL_DIRS) + r")"
    r"/[\w./-]+\.[A-Za-z0-9_]{1,8}(?:#[\w.-]+)?"
)
"""Everything below reads the AST, never the raw text.  Two reasons, both learned
the hard way in this repo:

  * COMMENTS AND DOCSTRINGS ARE NOT WIRING.  `audit_unrun_tests.py` used to scan
    raw workflow text, so a suite named in a YAML comment counted as "run by CI" —
    the census's own vacuous green (OIP E8).  The same trap is live here: a dozen
    suites describe their subject in prose ("validated against the REAL committed
    config/causal_priors.yml") without the code ever naming it.  Prose is a claim;
    only code is a read.  Comments never reach the AST at all, and docstrings are
    excluded explicitly.

  * A JOIN'S BASE DECIDES WHAT IT NAMES.  `tmp_path / "config" / "brain.yml"` and
    `ROOT / "config" / "brain.yml"` have identical segments; the first is a file
    the suite WRITES under pytest's temp dir and is not a subject at all.  Only a
    base provably derived from `__file__` can point into the checkout, so that is
    the only base accepted — under-reporting on an exotic spelling is the right
    way to be wrong for something that gates a merge.
"""


# ─────────────────────────────────────────────────────────────────────────────
# 1. the PR gates
# ─────────────────────────────────────────────────────────────────────────────

def _load(path: Path) -> dict | None:
    try:
        payload = yaml.safe_load(path.read_text(errors="ignore"))
    except yaml.YAMLError:
        return None
    return payload if isinstance(payload, dict) else None


def _on_block(payload: dict) -> dict | None:
    # PyYAML resolves the bare key `on:` to the boolean True (YAML 1.1 truthiness).
    block = payload[True] if True in payload else payload.get("on")
    return block if isinstance(block, dict) else None


def _run_steps(definition: object) -> list[str]:
    steps = definition.get("steps") if isinstance(definition, dict) else None
    return [
        str(step["run"])
        for step in steps or []
        if isinstance(step, dict) and isinstance(step.get("run"), str)
    ]


def pr_gates() -> list[dict]:
    """Every `on.pull_request` workflow, its path filter, and the files it governs.

    ``patterns is None`` means the workflow declares no `paths:` and therefore
    starts on EVERY pull request — anything it runs is unconditionally reachable.
    """
    gates: list[dict] = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        payload = _load(path)
        if payload is None:
            continue
        block = _on_block(payload)
        if block is None or "pull_request" not in block:
            continue
        trigger = block.get("pull_request")
        patterns = None
        if isinstance(trigger, dict) and isinstance(trigger.get("paths"), list):
            patterns = [str(p) for p in trigger["paths"]]

        runs: list[str] = []
        for definition in (payload.get("jobs") or {}).values():
            runs += _run_steps(definition)
        blob = "\n".join(runs)
        sources = {path.relative_to(ROOT).as_posix()}
        for ref in _MANIFEST_REF.findall(blob):
            if (ROOT / ref).is_file():
                sources.add(ref)
        gates.append(
            dict(workflow=path.name, patterns=patterns, sources=sorted(sources),
                 own_runs=blob)
        )
    return gates


def _glob_regex(pattern: str) -> re.Pattern[str]:
    """GitHub Actions filter-pattern semantics, which are NOT `fnmatch`.

    `*` matches any run of characters EXCEPT `/`; `**` crosses directories; `?` is
    one non-`/` character.  `fnmatch` lets a single `*` cross `/`, so it reports
    `scripts/*.py` as covering `scripts/ci/deep.py` — which GitHub does not.  A
    guard built on `fnmatch` therefore under-reports exactly the nested modules
    most likely to be missing an entry, so this translates the pattern instead.
    """
    out: list[str] = []
    index = 0
    while index < len(pattern):
        char = pattern[index]
        if char == "*":
            if pattern[index:index + 2] == "**":
                out.append(".*")
                index += 2
                continue
            out.append("[^/]*")
        elif char == "?":
            out.append("[^/]")
        else:
            out.append(re.escape(char))
        index += 1
    return re.compile("^" + "".join(out) + "$")


_GLOB_CACHE: dict[str, re.Pattern[str]] = {}


def matched(rel: str, patterns: list[str] | None) -> bool:
    """Would an edit to ``rel`` alone satisfy this workflow's `paths` filter?"""
    if patterns is None:
        return True                       # no filter → the workflow starts on every PR
    for pattern in patterns:
        if pattern == rel:
            return True
        if "*" in pattern or "?" in pattern:
            compiled = _GLOB_CACHE.get(pattern)
            if compiled is None:
                compiled = _GLOB_CACHE[pattern] = _glob_regex(pattern)
            if compiled.match(rel):
                return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# 2. what each governed job runs
# ─────────────────────────────────────────────────────────────────────────────

def suite_index() -> dict[str, tuple[str, ...]]:
    """``{token as a run: step may spell it: canonical repo-relative suite(s)}``.

    Both spellings resolve — the full repo-relative path (what every `run:` step in
    this repo actually writes) and the bare basename (the shape the old
    basename-only matcher accepted, kept so the widening cannot silently drop a
    job's claim to run a suite).  A token that resolves to nothing is not a suite:
    a stale path, or one of the three `test_`-shaped CLI instruments under
    `research/` that collect zero tests.
    """
    index: dict[str, list[str]] = {}
    for rel in discover_suites():
        index.setdefault(rel, []).append(rel)
        index.setdefault(rel.rsplit("/", 1)[-1], []).append(rel)
    return {token: tuple(paths) for token, paths in index.items()}


def _named_suites(run: str, index: dict[str, tuple[str, ...]]) -> set[str]:
    found: set[str] = set()
    for raw in _TEST_PATH.findall(run):
        token = raw[2:] if raw.startswith("./") else raw
        found.update(index.get(token, ()))
    return found


def suites_by_source() -> dict[str, dict[str, set[str]]]:
    """``{source file: {suite path: {job ids that run it}}}``.

    The legacy manifest is read through ``run_ci_pack.load_legacy_jobs`` so this
    guard sees jobs through the same fail-closed validator that executes them.
    """
    index = suite_index()
    out: dict[str, dict[str, set[str]]] = {}
    for path in sorted(WORKFLOWS.glob("*.yml")):
        payload = _load(path)
        if payload is None:
            continue
        rel = path.relative_to(ROOT).as_posix()
        for job_id, definition in (payload.get("jobs") or {}).items():
            for run in _run_steps(definition):
                for suite in _named_suites(run, index):
                    out.setdefault(rel, {}).setdefault(suite, set()).add(str(job_id))
    if CI_MANIFEST.is_file():
        rel = CI_MANIFEST.relative_to(ROOT).as_posix()
        for legacy in load_legacy_jobs(CI_MANIFEST):
            for step in legacy.definition["steps"]:
                if isinstance(step, dict) and isinstance(step.get("run"), str):
                    for suite in _named_suites(step["run"], index):
                        out.setdefault(rel, {}).setdefault(suite, set()).add(
                            legacy.job_id
                        )
    return out


# ─────────────────────────────────────────────────────────────────────────────
# 3. what a suite reads
# ─────────────────────────────────────────────────────────────────────────────

def _join_segments(node: ast.BinOp) -> tuple[ast.expr, list[str]] | None:
    """Flatten ``base / "a" / "b.py"`` into ``(base, ["a", "b.py"])``."""
    segments: list[str] = []
    current: ast.expr = node
    while isinstance(current, ast.BinOp) and isinstance(current.op, ast.Div):
        right = current.right
        if not (isinstance(right, ast.Constant) and isinstance(right.value, str)):
            return None
        segments.append(right.value)
        current = current.left
    if not segments:
        return None
    segments.reverse()
    return current, segments


def _mentions_file_dunder(node: ast.AST) -> bool:
    return any(
        isinstance(inner, ast.Name) and inner.id == "__file__"
        for inner in ast.walk(node)
    )


def _checkout_bases(tree: ast.Module) -> set[str]:
    """Module-level names bound to something derived from ``__file__``.

    `ROOT = Path(__file__).resolve().parents[1]` is the only way a suite can name
    the real checkout.  A name bound anywhere else — a fixture parameter, a local
    `root`, `tmp_path` — may look identical at the join site and point at a
    synthetic tree, so it is not accepted.
    """
    bases: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign) and _mentions_file_dunder(node.value):
            bases |= {t.id for t in node.targets if isinstance(t, ast.Name)}
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.value is not None
            and _mentions_file_dunder(node.value)
        ):
            bases.add(node.target.id)
    return bases


def _docstring_ids(tree: ast.Module) -> set[int]:
    """Identities of the Constant nodes that are docstrings, so prose is excluded."""
    out: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            continue
        body = getattr(node, "body", None) or []
        first = body[0] if body else None
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            out.add(id(first.value))
    return out


def _resolve(module: str) -> list[str]:
    """Repo-relative files a dotted module name can denote — existing ones only."""
    base = module.replace(".", "/")
    return [
        candidate
        for candidate in (f"{base}.py", f"{base}/__init__.py")
        if (ROOT / candidate).is_file()
    ]


def direct_reads(path: Path) -> dict[str, str]:
    """``{repo-relative file: "kind at line N"}`` for what ``path`` reads directly.

    Every returned path exists in the tree.  A path that does not exist cannot be
    edited, so it can never be the module a PR touches — including it would only
    add noise (and `config/foo.yml`-shaped placeholder strings are exactly that).

    The provenance is not decoration: a finding says "add a path entry for a file
    you did not know this suite read", and the reviewer's first question is always
    "where?".  Without the line, verifying one finding costs a grep per finding.
    """
    files: dict[str, str] = {}

    def record(rel: str, kind: str, line: int) -> None:
        files.setdefault(rel, f"{kind} at line {line}")

    try:
        tree = ast.parse(path.read_text(errors="ignore"))
    except SyntaxError:
        return files

    bases = _checkout_bases(tree)
    docstrings = _docstring_ids(tree)

    for node in ast.walk(tree):
        # a) imports
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            names = [node.module]
            # `from pkg import a, b` binds pkg.a / pkg.b when those are submodules;
            # resolving only `pkg` collapses the closure onto pkg/__init__.py and
            # understates the gap.
            if node.module.split(".")[0] in FIRST_PARTY:
                names += [f"{node.module}.{alias.name}" for alias in node.names]
        for name in names:
            if name.split(".")[0] in FIRST_PARTY:
                for rel in _resolve(name):
                    record(rel, "import", node.lineno)

        # b) importlib.import_module("engine.foo")
        if isinstance(node, ast.Call) and node.args:
            func = node.func
            label = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            first = node.args[0]
            if (
                label == "import_module"
                and isinstance(first, ast.Constant)
                and isinstance(first.value, str)
                and first.value.split(".")[0] in FIRST_PARTY
            ):
                for rel in _resolve(first.value):
                    record(rel, "import_module", node.lineno)

        # c) a whole repo-relative path in one string literal — never a docstring
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docstrings
        ):
            match = _PATH_LITERAL.fullmatch(node.value.strip())
            if match and (ROOT / match.group(0).split("#")[0]).is_file():
                record(match.group(0).split("#")[0], "path literal", node.lineno)

        # d) ROOT / "a" / "b.py" — only off a base derived from __file__
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            chain = _join_segments(node)
            if chain is not None:
                base, segments = chain
                rooted = _mentions_file_dunder(base) or (
                    isinstance(base, ast.Name) and base.id in bases
                )
                joined = "/".join(segments)
                if (
                    rooted
                    and joined.split("/")[0] in LITERAL_DIRS
                    and (ROOT / joined).is_file()
                ):
                    record(joined, "path join", node.lineno)

    # An __init__.py is a package marker, not a subject: flagging it would demand a
    # path entry for every package a suite imports through.
    return {rel: why for rel, why in files.items() if not rel.endswith("__init__.py")}


def closure(start: Path, depth: int, cache: dict[str, dict[str, str]]) -> dict[str, str]:
    """``{file: provenance}`` reachable from ``start`` in at most ``depth`` hops."""
    def reads(path: Path) -> dict[str, str]:
        key = path.as_posix()
        if key not in cache:
            cache[key] = direct_reads(path)
        return cache[key]

    seen: dict[str, str] = {}
    frontier: list[tuple[Path, int, str]] = [(start, 0, "")]
    while frontier:
        current, level, via = frontier.pop()
        for rel, why in reads(current).items():
            if rel in seen:
                continue
            seen[rel] = why if not via else f"{why} of {via}"
            if level + 1 < depth and rel.endswith(".py"):
                frontier.append((ROOT / rel, level + 1, rel))
    return seen


# ─────────────────────────────────────────────────────────────────────────────
# 4. verdict
# ─────────────────────────────────────────────────────────────────────────────

def census(depth: int = 1) -> list[dict]:
    gates = pr_gates()
    named = suites_by_source()
    cache: dict[str, dict[str, str]] = {}

    # A suite may be run by several PR gates; it is reachable if ANY of them starts.
    runners: dict[str, list[tuple[dict, str, set[str]]]] = {}
    for gate in gates:
        for source in gate["sources"]:
            for suite, jobs in (named.get(source) or {}).items():
                runners.setdefault(suite, []).append((gate, source, jobs))

    rows: list[dict] = []
    for suite in sorted(runners):
        path = ROOT / suite
        if not path.is_file():
            continue          # tests/test_ci_pack.py already fails on a stale path
        reads = closure(path, depth, cache)
        subjects = sorted(reads)
        gaps = [
            rel for rel in subjects
            if not any(matched(rel, g["patterns"]) for g, _, _ in runners[suite])
        ]
        by = sorted(
            f"{source}::{job}" for g, source, jobs in runners[suite] for job in jobs
        )
        filters = sorted({
            g["workflow"] for g, _, _ in runners[suite] if g["patterns"] is not None
        })
        rows.append(dict(
            test=suite,
            run_by=by,
            filters=filters,
            subjects=subjects,
            gaps=gaps,
            why={rel: reads[rel] for rel in gaps},
            self_reachable=any(
                matched(suite, g["patterns"]) for g, _, _ in runners[suite]
            ),
            status="GAP" if gaps else "OK",
        ))
    return rows


def _fix_hint(row: dict, rel: str) -> str:
    where = ", ".join(row["filters"]) or "the workflow path filter"
    return (
        f'{row["test"]} reads {rel} ({row["why"].get(rel, "?")}), but no '
        f'`on.pull_request.paths` entry in {where} matches it — a PR touching only '
        f'{rel} never starts {row["run_by"][0]}, the job that runs the suite. '
        f'Fix: add - "{rel}" to that paths list.'
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--report", action="store_true",
                        help="print the full census and exit 0")
    parser.add_argument("--depth", type=int, default=1,
                        help="read-hops to follow (gate is always depth 1)")
    parser.add_argument("--json", type=Path, help="write all rows as JSON")
    parser.add_argument("--selftest", action="store_true",
                        help="round-trip the detector against seeded fixtures")
    args = parser.parse_args(argv)

    if args.selftest:
        return _selftest()

    try:
        rows = census(depth=max(1, args.depth))
    except ManifestError as exc:
        print(f"::error title=ci-trigger-closure::cannot read the CI manifest: {exc}",
              flush=True)
        return 2

    if args.json:
        args.json.write_text(json.dumps(rows, indent=1))

    bad = [r for r in rows if r["status"] == "GAP"]
    unreachable_self = [r for r in rows if not r["self_reachable"]]

    print(f"suites run by a path-filtered PR gate : {len(rows)}")
    print(f"  closure fully reachable             : {len(rows) - len(bad)}")
    print(f"  TRIGGER GAP                         : {len(bad)}")
    print(f"  (test half unreachable, not gated)  : {len(unreachable_self)}")

    if args.report:
        print(f"\n=== TRIGGER GAP ({len(bad)}) ===")
        for row in bad:
            print(f"  {row['test']}  run by {', '.join(row['run_by'][:2])}")
            for rel in row["gaps"]:
                print(f"      unreachable: {rel}  ({row['why'].get(rel, '?')})")
        print(f"\n=== test half unreachable ({len(unreachable_self)}) ===")
        print("  A test-only edit (a re-pin, a fixture heal — the #4559 shape) does")
        print("  not start the job that runs it. Reported, not gated: naming all of")
        print("  these would widen ci.yml by hundreds of entries, which is a CI-cost")
        print("  call for the operator, not a guard's to make.")
        for row in unreachable_self:
            print(f"  {row['test']}")
        return 0

    if unreachable_self:
        # ONE annotation, never one per row: 90+ notices bury the errors that gate.
        print(
            f"::notice title=ci-trigger-closure::{len(unreachable_self)} suite(s) "
            "cannot be triggered by an edit to their own file (#4559 shape). Not "
            "gated — run --report for the list.",
            flush=True,
        )

    if not bad:
        print("\nOK — every module a gated suite reads can start the job that runs it.")
        return 0

    print()
    for row in bad:
        for rel in row["gaps"]:
            print(f"::error title=ci-trigger-closure::{_fix_hint(row, rel)}", flush=True)
    print(f"\n{len(bad)} suite(s) with an unreachable subject. Each one is a guard "
          f"with a hole exactly the shape of what it measures:")
    print("the suite is green, the census calls it triggerable, and the ONE edit it")
    print("exists to catch ships without ever running it (#3488, #4559).")
    return 1


# ─────────────────────────────────────────────────────────────────────────────
# selftest — a guard that stops detecting is worse than no guard
# ─────────────────────────────────────────────────────────────────────────────

_FIXTURE_SUITE = '''
"""Prose names config/reflexes.yml, which the code below never reads."""
import importlib
from pathlib import Path

from engine import market_state
from lib import config

REPO = Path(__file__).resolve().parents[1]
PACKET = REPO / "research" / "prophet_us_audit" / "reclaim_veto_packet.py"
OTHER = "scripts/audit_unrun_tests.py"
MISSING = "engine/does_not_exist_anywhere.py"
mod = importlib.import_module("collectors.fred")
NOTE = "see config/seasonality_universe.yml for the roster, not a read"

# A comment naming config/trade_flow_codes.yml is not wiring either.


def test_writes_a_lookalike(tmp_path, root):
    """Docstring naming config/clinical_modalities.yml is a claim, not a read."""
    # Same segments as real repo files, but under a synthetic tree.
    (tmp_path / "config" / "brain.yml").write_text("x")
    (root / "config" / "evidence_clock.yml").write_text("y")
'''


def _selftest() -> int:
    import tempfile

    failures: list[str] = []

    with tempfile.TemporaryDirectory() as tmp:
        suite = Path(tmp) / "test_fixture_reads.py"
        suite.write_text(_FIXTURE_SUITE)
        reads = direct_reads(suite)
    for want in (
        "engine/market_state.py",                                   # from-import
        "lib/config.py",                                            # from-import
        "research/prophet_us_audit/reclaim_veto_packet.py",         # Path segment join
        "scripts/audit_unrun_tests.py",                             # bare literal
        "collectors/fred.py",                                       # import_module()
    ):
        if want not in reads:
            failures.append(f"direct_reads missed {want}")
    if any("does_not_exist_anywhere" in r for r in reads):
        failures.append("direct_reads returned a path that is not in the tree")
    if any(r.endswith("__init__.py") for r in reads):
        failures.append("direct_reads returned a package marker")
    for wrong, why in (
        ("config/brain.yml", "a tmp_path write is not a subject"),
        ("config/evidence_clock.yml", "a synthetic `root` base is not the checkout"),
        ("config/reflexes.yml", "a module docstring is prose, not a read"),
        ("config/clinical_modalities.yml", "a function docstring is prose, not a read"),
        ("config/trade_flow_codes.yml", "a comment is prose, not a read"),
        ("config/seasonality_universe.yml", "a path inside a sentence is a pointer"),
    ):
        if wrong in reads:
            failures.append(f"direct_reads flagged {wrong}: {why}")

    # Glob semantics: the subtree form is what makes engine/** cover the incident.
    checks = (
        ("engine/signal_quality.py", ["engine/**"], True),
        ("engine/sub/deep.py", ["engine/**"], True),
        ("engineering/other.py", ["engine/**"], False),
        ("scripts/sub/x.py", ["scripts/*.py"], False),
        ("scripts/x.py", ["scripts/*.py"], True),
        ("a/b.py", ["a/b.py"], True),
        ("a/b.py", ["a/c.py"], False),
        ("anything/at/all.py", None, True),          # workflow with no paths filter
    )
    for rel, patterns, want in checks:
        if matched(rel, patterns) is not want:
            failures.append(f"matched({rel!r}, {patterns!r}) != {want}")

    # Seeded defect, both directions: the pinned module must be flagged when the
    # filter drops it and clear when the filter names it.  This is the incident in
    # miniature — the suite's own file stays matched throughout, which is exactly
    # why an any()-over-the-closure census calls it covered either way.
    gate_with = ["tests/**", "engine/signal_quality.py"]
    gate_without = ["tests/**"]
    subject = "engine/signal_quality.py"
    if matched(subject, gate_without):
        failures.append("seeded defect: subject must be UNREACHABLE without its entry")
    if not matched(subject, gate_with):
        failures.append("seeded heal: subject must be reachable once named")
    if not matched("tests/test_us_reclaim_veto_packet.py", gate_without):
        failures.append("seeded defect: the test half must stay matched (that is the trap)")

    # Scope (#4693): a `run:` step naming a suite OUTSIDE tests/ must resolve, and a
    # `test_`-shaped CLI instrument named by one must NOT — the old regex could do
    # neither, so a wired research/ suite stayed invisible to this gate.
    index = suite_index()
    real_outside = [s for s in discover_suites() if not s.startswith("tests/")]
    step = (
        "python -m pytest research/prophet_us_audit/test_label_grading_battery.py "
        "tests/test_ci_pack.py ./tests/test_merge_on_green.py "
        "research/signal_engine/test_buyfilter.py -q"
    )
    named = _named_suites(step, index)
    if "tests/test_ci_pack.py" not in named:
        failures.append("a tests/ suite in a run: step must still resolve")
    if "tests/test_merge_on_green.py" not in named:
        failures.append("a `./`-prefixed suite path must resolve")
    for rel in real_outside:
        if rel in step and rel not in named:
            failures.append(f"a run: step naming {rel} must resolve (scope is the tree)")
    if "research/signal_engine/test_buyfilter.py" in named:
        failures.append(
            "research/signal_engine/test_buyfilter.py collects zero tests — a CLI "
            "instrument must not be gated as a suite"
        )
    if not real_outside:
        failures.append(
            "discovery found no suite outside tests/; the widening is inert "
            "(expected the research/-resident guard suites)"
        )

    if failures:
        for failure in failures:
            print(f"::error title=ci-trigger-closure-selftest::{failure}", flush=True)
        return 1
    print("SELFTEST OK — reads resolved, glob semantics hold, seeded defect flagged.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
