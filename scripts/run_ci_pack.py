#!/usr/bin/env python3
"""Run the legacy CI manifest using a small number of shared runners.

GitHub Actions used to provision one fresh VM for every job in ``ci.yml``.
The repository is large enough that checkout and interpreter setup dominated
the useful test work, so one PR fanned out to more than eighty hosted runners.

The workflow now contains one small ``ci-pack`` matrix instead. Legacy job
definitions live in ``.github/ci/legacy-jobs.yml`` so GitHub does not publish
roughly one hundred skipped check runs on every pull request. The pack jobs call
this script, which validates the manifest and executes every legacy ``run``
step. A hard reset/clean between legacy jobs preserves their former
clean-checkout isolation. Jobs with different declared pip dependencies also
get freshly recreated virtual environments; only jobs whose install commands
are byte-identical share an environment.

Which jobs land in which pack is decided ONCE, by ``build_plan``, and published
as a hashed ``CIPackPlan`` (``--plan-only``).  Each pack recomputes the same
pure function and refuses to run when its hash disagrees (``--expect-plan-sha``),
so twelve runners can never quietly disagree about what the suite is.

The validator is intentionally fail-closed.  A future job using services,
containers, per-step conditions/environments, or an unfamiliar action must
teach this runner how to preserve that behavior before the workflow can pass.

Execution is refused outside GitHub Actions because workspace cleanup is
destructive by design.  Local callers can safely use ``--validate-only``.
"""

from __future__ import annotations

import argparse
import functools
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Iterable

import yaml

# The pack runner imports only repository-owned scope metadata.  Pin the checkout
# root unconditionally so direct script execution and importlib-based tests resolve
# it identically; conditional pins can silently prefer an installed namesake.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


PACK_JOB_ID = "ci-pack"
DISABLED_IF = "${{ false }}"
ALLOWED_JOB_KEYS = {"if", "paths", "runs-on", "steps", "timeout-minutes"}
ALLOWED_STEP_KEYS = {"name", "run", "uses", "with"}

# ---------------------------------------------------------------------------
# Changed-path scoping (2026-08-09)
#
# Every pull request used to run every legacy job regardless of its diff, so
# a one-template PR paid for the entire engine/site/research suite: 4 packs x
# ~30 min x every PR, against an account-wide hosted-runner pool. Measured
# 2026-08-09: 122 runs queued, packs waiting 46-85 MINUTES for a runner.
# Adding runners buys a constant factor; per-PR cost is what scales with fleet
# size, so scoping the suite to the diff is the only lever that changes slope.
#
# The design is fail-SAFE in every direction, because a false green here is far
# more expensive than a wasted runner-minute:
#   * a job with NO `paths:` always runs (declaring a scope is opt-in);
#   * no --changed-from (main's baseline, workflow_dispatch) runs everything;
#   * a git failure runs everything;
#   * touching a GLOBAL_INVALIDATOR runs everything;
#   * a scope that does not cover the paths its own commands name is a hard
#     manifest error, not a silent skip (see _scope_coverage_findings).
#
# The residual risk is an IMPLICIT dependency: a scoped job whose tests import a
# module the commands never name. That cannot be caught statically here, so the
# the full manifest still audits main. That post-merge audit is not a substitute
# for conservative PR ownership: any ambiguity below widens to a full PR run.
# ---------------------------------------------------------------------------

# A change to any of these invalidates scoping entirely: they can alter what any
# job means, so no per-job scope can be trusted against them.
GLOBAL_INVALIDATORS = (
    ".github/workflows/**",
    ".github/ci/**",
    ".github/ci/legacy-jobs.yml",
    ".github/workflows/ci.yml",
    "scripts/run_ci_pack.py",
    "scripts/ci_scope_dependencies.py",
    "scripts/check_ci_trigger_closure.py",
    "scripts/audit_unrun_tests.py",
    "config/dag.yml",
    "config/synapse.yml",
    "conftest.py",
    "**/conftest.py",
    "requirements*.txt",
    "**/requirements*.txt",
    "constraints*.txt",
    "**/constraints*.txt",
    "pyproject.toml",
    "**/pyproject.toml",
    "setup.cfg",
    "**/setup.cfg",
    "setup.py",
    "**/setup.py",
    "tox.ini",
    "**/tox.ini",
    "pytest.ini",
    "**/pytest.ini",
    "package.json",
    "**/package.json",
    "package-lock.json",
    "**/package-lock.json",
    "uv.lock",
    "**/uv.lock",
    "poetry.lock",
    "**/poetry.lock",
)

# Narrative files cannot alter executable behavior unless a suite explicitly
# reads them. Such a reader's derived scope owns the file and still runs; an
# otherwise-unowned Markdown edit must not turn a narrow code PR back into all
# 180 jobs merely because it carries its handoff/provenance note.
PASSIVE_UNOWNED_PATTERNS = ("**/*.md",)

# A statically opaque subprocess or tree traversal must own every established
# repository surface it could inspect.  This is deliberately broad: it keeps
# whole-tree guards such as all-exports-resolve selected for every engine/script
# edit, while still allowing an unrelated narrow owner to skip guards that have
# no opaque I/O.  A new top-level directory remains unowned and therefore widens
# the whole PR to a full run.
OPAQUE_IO_ROOTS = (
    "*",
    "app/**", "admin/**", "collectors/**", "config/**", "content/**", "contracts/**",
    "data/**", "docs/**", "engine/**", "lib/**", "ops/**", "research/**",
    "scripts/**", "site/**", "templates/**", "tests/**", "tools/**",
    "worker/**",
)
CODE_SCAN_ROOTS = (
    "app/**", "admin/**", "collectors/**", "engine/**", "lib/**",
    "research/**", "scripts/**", "site/**", "tests/**", "tools/**",
    "worker/**",
)
ARTIFACT_SCAN_ROOTS = (
    "config/**", "content/**", "contracts/**", "data/**", "docs/**", "ops/**",
    "research/**", "site/**", "templates/**",
)
SUBPROCESS_ROOTS = tuple(sorted(set(CODE_SCAN_ROOTS) | {
    "config/**", "contracts/**", "templates/**",
}))

# Repo paths named literally inside a job's own commands. Used to verify that a
# declared scope covers at least the files that job demonstrably reads.
TRACKED_ROOTS = (
    "app",
    "admin",
    "config",
    "content",
    "docs",
    "engine",
    "research",
    "scripts",
    "site",
    "templates",
    "tests",
)
SCOPE_REFERENCE_RE = re.compile(
    r"\b(?:" + "|".join(TRACKED_ROOTS) + r")/[A-Za-z0-9_./-]+"
)
SUITE_REFERENCE_RE = re.compile(
    r"(?<![\w/.-])((?:[\w.-]+/)*(?:test_[\w-]+|[\w-]+_test)\.py)"
    r"(?![\w])"
)
PROVIDED_ACTION_PREFIXES = (
    "actions/checkout@",
    "actions/setup-python@",
    "actions/setup-node@",
)
EXPRESSION_RE = re.compile(r"\$\{\{[^}]+\}\}")
PIP_INSTALL_RE = re.compile(
    r"^\s*(?:(?:python|python3) -m )?pip install [^\n]+\s*$"
)
# Command-only timings from successful ci run 30173070380.  These few outliers
# dominate wall time; checkout/setup/install were deliberately excluded because
# packs share or group that work.  The fallback heuristic handles every other
# job and any job added later.
OBSERVED_COMMAND_SECONDS = {
    "engine-render-guards": 481,
    "inline-js": 124,
    "font-ui-defined": 96,
    "neural-web-core": 89,
    "capability-broker": 74,
    "validated-claims": 39,
    "neural-web": 37,
    "hub-a11y": 37,
}


class ManifestError(ValueError):
    """The legacy manifest cannot be executed without losing semantics."""


@dataclass(frozen=True)
class LegacyJob:
    """Validated legacy job plus its deterministic balancing weight."""

    job_id: str
    definition: dict[str, Any]
    ordinal: int
    weight: int
    # Empty means UNSCOPED — the job runs on every pull request. Declaring a
    # scope is opt-in, so adding one can only ever remove work, never add it.
    paths: tuple[str, ...] = ()


@functools.lru_cache(maxsize=None)
def _glob_to_regex(pattern: str) -> re.Pattern[str]:
    """Translate a repo-relative glob to a regex.

    `fnmatch` is unusable here: its `*` crosses `/`, so `engine/*` would match
    `engine/a/b/c.py` and a scope meant to name one directory would silently
    cover the whole subtree. Separator semantics are the whole point of a scope,
    so the translation is explicit — `**` crosses `/`, a single `*` does not.
    A pattern ending in `/` is a directory prefix and covers everything under it.
    """
    if pattern.endswith("/"):
        pattern += "**"
    out: list[str] = []
    index = 0
    while index < len(pattern):
        char = pattern[index]
        if pattern.startswith("**/", index):
            out.append("(?:.*/)?")
            index += 3
        elif pattern.startswith("**", index):
            out.append(".*")
            index += 2
        elif char == "*":
            out.append("[^/]*")
            index += 1
        elif char == "?":
            out.append("[^/]")
            index += 1
        else:
            out.append(re.escape(char))
            index += 1
    return re.compile("^" + "".join(out) + "$")


def _matches_any(patterns: Iterable[str], path: str) -> bool:
    return any(_glob_to_regex(pattern).match(path) for pattern in patterns)


def _scope_coverage_findings(job_id: str, definition: dict[str, Any],
                             scope: tuple[str, ...]) -> list[str]:
    """A declared scope must cover every repo path its own commands name.

    This is what makes scoping reviewable rather than trusted. A job that runs
    `pytest tests/test_foo.py` but scopes itself to `engine/bar/**` would never
    re-run when `test_foo.py` itself changed — a silent false green. Here that
    is a hard manifest error instead, and the fix (widen the scope) is the safe
    direction. Paths that no longer exist are ignored: stale references in a
    comment must not be able to fail the build.
    """
    if not scope:
        return []
    commands = "\n".join(
        str(step["run"])
        for step in definition.get("steps", [])
        if isinstance(step, dict) and "run" in step
    )
    findings: list[str] = []
    for reference in sorted(set(SCOPE_REFERENCE_RE.findall(commands))):
        referenced = reference.split("::", 1)[0].rstrip(".,;:'\")")
        if not Path(referenced).exists():
            continue
        if _matches_any(GLOBAL_INVALIDATORS, referenced):
            continue
        if not _matches_any(scope, referenced):
            findings.append(
                f"job {job_id!r} declares paths that do not cover {referenced!r}, "
                "which its own commands read — widen the scope or drop it"
            )
    return findings


def _validate_scope(prefix: str, raw: Any) -> tuple[tuple[str, ...], list[str]]:
    if raw is None:
        return (), []
    if not isinstance(raw, list) or not raw:
        return (), [f"{prefix} paths must be a non-empty list of globs"]
    findings: list[str] = []
    scope: list[str] = []
    for entry in raw:
        if not isinstance(entry, str) or not entry.strip():
            findings.append(f"{prefix} paths entries must be non-empty strings")
            continue
        if entry.startswith("/") or ".." in entry:
            findings.append(
                f"{prefix} path {entry!r} must be repo-relative and contain no '..'"
            )
            continue
        scope.append(entry)
    return tuple(scope), findings


def changed_files(base_ref: str) -> list[str] | None:
    """Return paths changed against ``base_ref``, or None if unknowable.

    None means "scope nothing" — every caller treats it as a full-suite run.
    """
    for revision in (f"{base_ref}...HEAD", f"origin/{base_ref}...HEAD"):
        try:
            result = subprocess.run(
                [
                    "git", "diff", "--name-status", "-z", "--find-renames",
                    "--find-copies",
                    revision,
                ],
                capture_output=True, text=True, check=True,
            )
        except (subprocess.CalledProcessError, OSError):
            continue
        # `--name-status -z` emits STATUS\0PATH\0 for ordinary changes and
        # Rnnn/Cnnn\0OLD\0NEW\0 for renames/copies.  Both sides are load-bearing:
        # deleting or renaming a subject must still select the job that owned its
        # old path, while the new path must select its new owner.
        fields = result.stdout.split("\0")
        if fields and fields[-1] == "":
            fields.pop()
        changed: list[str] = []
        index = 0
        try:
            while index < len(fields):
                status = fields[index]
                index += 1
                if not status:
                    raise ValueError("empty git diff status")
                if status[0] in {"R", "C"}:
                    changed.extend((fields[index], fields[index + 1]))
                    index += 2
                else:
                    changed.append(fields[index])
                    index += 1
        except (IndexError, ValueError):
            return None
        changed = list(dict.fromkeys(path for path in changed if path))
        # An empty PR comparison is unusual (ancestry-only rewrite, missing
        # objects, or wrong base). It is not proof that only always-on jobs are
        # sufficient, so widen just like a failed diff.
        return changed or None
    return None


def infer_job_scopes(jobs: Iterable[LegacyJob]) -> tuple[list[LegacyJob], str]:
    """Attach conservative runtime-derived scopes to statically legible jobs.

    The legacy YAML remains the reviewable command manifest.  Scope ownership is
    derived from the suites/scripts each command names and their first-party read
    closure, so it cannot drift as thousands of copied YAML path rows would.
    Opaque edges widen that job to their complete root domain; an unparseable
    invocation returns ``None`` and remains always-on.
    """
    try:
        from scripts.audit_unrun_tests import discover_suites
        from scripts.ci_scope_dependencies import (
            pytest_invocation_ambiguities,
            suite_dependency_closure,
        )
    except (ImportError, OSError, SyntaxError) as exc:
        return list(jobs), f"scope inference unavailable ({exc})"

    suite_index: dict[str, set[str]] = {}
    for suite in discover_suites():
        suite_index.setdefault(suite, set()).add(suite)
        suite_index.setdefault(suite.rsplit("/", 1)[-1], set()).add(suite)

    def ambiguity_fallbacks(
        ambiguities: Iterable[str],
    ) -> tuple[str, ...] | None:
        """Only opaque repository ownership blocks a scope.

        A subprocess call or filesystem traversal can inspect paths static import
        closure cannot see, so the caller owns the statically visible scan roots;
        an unresolved scan widens to every established root. Dynamic imports own
        every importable code root rather than guessing a particular module.
        """
        fallbacks: set[str] = set()
        for item in ambiguities:
            if "filesystem roots=" in item:
                raw = item.split("filesystem roots=", 1)[1]
                fallbacks.update(f"{root}/**" for root in raw.split(",") if root)
                continue
            if "subprocess roots=" in item:
                raw = item.split("subprocess roots=", 1)[1]
                fallbacks.update(f"{root}/**" for root in raw.split(",") if root)
                continue
            if item.endswith("filesystem code traversal"):
                fallbacks.update(CODE_SCAN_ROOTS)
                continue
            if item.endswith("filesystem artifact traversal"):
                fallbacks.update(ARTIFACT_SCAN_ROOTS)
                continue
            if item.endswith("filesystem glob"):
                fallbacks.update(OPAQUE_IO_ROOTS)
                continue
            if item.endswith("subprocess invocation"):
                fallbacks.update(SUBPROCESS_ROOTS)
                continue
            if item.endswith("dynamic import"):
                # The target expression is opaque. Widen across every repository
                # tree that can carry importable code, including research/tools
                # helpers and test plugins, rather than guessing one package.
                fallbacks.update(CODE_SCAN_ROOTS)
                continue
            return None
        return tuple(sorted(fallbacks))

    def infer_job_paths(definition: dict[str, Any]) -> tuple[str, ...] | None:
        commands = [
            str(step["run"])
            for step in definition.get("steps", [])
            if isinstance(step, dict)
            and "run" in step
            and "pip install" not in str(step["run"])
        ]
        owned: set[str] = set()
        named_any = False
        for command in commands:
            if pytest_invocation_ambiguities(command):
                return None
            named_here: set[str] = set()
            for raw in SUITE_REFERENCE_RE.findall(command):
                token = raw[2:] if raw.startswith("./") else raw
                named_here.update(suite_index.get(token, ()))
            if "pytest" in command and not named_here:
                # A pytest invocation whose collected suite cannot be enumerated is
                # runtime discovery, not evidence for a narrow owner.
                return None
            for suite in named_here:
                closure = suite_dependency_closure(suite, pytest_command=command)
                fallbacks = ambiguity_fallbacks(closure.ambiguities)
                if fallbacks is None:
                    return None
                owned.update(closure.files)
                owned.update(fallbacks)
                named_any = True

            for reference in SCOPE_REFERENCE_RE.findall(command):
                rel = reference.split("::", 1)[0].rstrip(".,;:'\")")
                path = Path(rel)
                if not path.is_file():
                    continue
                owned.add(rel)
                named_any = True
                if rel.endswith(".py"):
                    closure = suite_dependency_closure(rel)
                    fallbacks = ambiguity_fallbacks(closure.ambiguities)
                    if fallbacks is None:
                        return None
                    owned.update(closure.files)
                    owned.update(fallbacks)
        return tuple(sorted(owned)) if named_any and owned else None

    inferred: list[LegacyJob] = []
    scoped = 0
    for job in jobs:
        paths = infer_job_paths(job.definition)
        if paths:
            inferred.append(
                replace(job, paths=tuple(sorted(set(job.paths) | set(paths))))
            )
            scoped += 1
        else:
            inferred.append(replace(job, paths=()))
    return inferred, f"derived scopes for {scoped}/{len(inferred)} jobs"


def select_jobs(
    jobs: Iterable[LegacyJob], changed: list[str] | None
) -> tuple[list[LegacyJob], str]:
    """Pick the jobs a diff can actually affect, erring toward running more."""
    jobs = list(jobs)
    if changed is None:
        return jobs, "full suite: changed-file set unavailable"
    invalidators = [path for path in changed if _matches_any(GLOBAL_INVALIDATORS, path)]
    if invalidators:
        return jobs, f"full suite: global invalidator changed ({invalidators[0]})"
    scoped_jobs = [job for job in jobs if job.paths]
    unowned = [
        path for path in changed
        if not any(_matches_any(job.paths, path) for job in scoped_jobs)
        and not _matches_any(PASSIVE_UNOWNED_PATTERNS, path)
    ]
    if unowned:
        return jobs, f"full suite: changed path has no proven owner ({unowned[0]})"
    selected = [
        job
        for job in jobs
        if not job.paths or any(_matches_any(job.paths, path) for path in changed)
    ]
    unscoped = sum(1 for job in jobs if not job.paths)
    return selected, (
        f"scoped to {len(changed)} changed file(s): {len(selected)}/{len(jobs)} jobs "
        f"({unscoped} unscoped always-on, "
        f"{len(selected) - unscoped} scoped matches)"
    )


def _workflow_jobs(path: Path) -> dict[str, dict[str, Any]]:
    try:
        payload = yaml.safe_load(path.read_text())
    except (OSError, yaml.YAMLError) as exc:
        raise ManifestError(f"cannot load workflow {path}: {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), dict):
        raise ManifestError(f"{path} must contain a jobs mapping")
    return payload["jobs"]


def _job_weight(job_id: str, definition: dict[str, Any]) -> int:
    """Estimate work well enough to avoid putting both giant suites together."""
    if job_id in OBSERVED_COMMAND_SECONDS:
        return OBSERVED_COMMAND_SECONDS[job_id]
    commands = [
        str(step["run"])
        for step in definition.get("steps", [])
        if isinstance(step, dict) and "run" in step
    ]
    text = "\n".join(commands)
    # Explicit test paths correlate more closely with duration than line count.
    # Every command still costs at least one unit so static guards are balanced.
    return max(1, len(commands) + text.count("tests/test_") * 2 + len(text) // 800)


def load_legacy_jobs(path: Path) -> list[LegacyJob]:
    """Load and fail-closed validate every job in the legacy manifest.

    PACK_JOB_ID is still ignored when present so small historical test fixtures
    remain valid; the production manifest intentionally contains no pack job.
    """
    jobs = _workflow_jobs(path)

    legacy: list[LegacyJob] = []
    findings: list[str] = []
    for ordinal, (job_id, raw_definition) in enumerate(jobs.items()):
        if job_id == PACK_JOB_ID:
            continue
        prefix = f"job {job_id!r}"
        if not isinstance(raw_definition, dict):
            findings.append(f"{prefix} must be a mapping")
            continue

        unknown_job_keys = sorted(set(raw_definition) - ALLOWED_JOB_KEYS)
        if unknown_job_keys:
            findings.append(
                f"{prefix} has unsupported keys: {', '.join(unknown_job_keys)}"
            )
        if raw_definition.get("if") != DISABLED_IF:
            findings.append(
                f"{prefix} must declare `if: {DISABLED_IF}` so GitHub does not "
                "allocate a duplicate runner"
            )
        if raw_definition.get("runs-on") != "ubuntu-latest":
            findings.append(f"{prefix} must use ubuntu-latest")

        steps = raw_definition.get("steps")
        if not isinstance(steps, list) or not steps:
            findings.append(f"{prefix} must contain a non-empty steps list")
            continue
        for index, step in enumerate(steps):
            step_prefix = f"{prefix} step {index + 1}"
            if not isinstance(step, dict):
                findings.append(f"{step_prefix} must be a mapping")
                continue
            unknown_step_keys = sorted(set(step) - ALLOWED_STEP_KEYS)
            if unknown_step_keys:
                findings.append(
                    f"{step_prefix} has unsupported keys: "
                    f"{', '.join(unknown_step_keys)}"
                )
            has_run = "run" in step
            has_uses = "uses" in step
            if has_run == has_uses:
                findings.append(
                    f"{step_prefix} must contain exactly one of run or uses"
                )
            if has_uses and not str(step["uses"]).startswith(PROVIDED_ACTION_PREFIXES):
                findings.append(
                    f"{step_prefix} uses unsupported action {step['uses']!r}"
                )
        installs = [
            str(step["run"])
            for step in steps
            if isinstance(step, dict)
            and "run" in step
            and "pip install" in str(step["run"])
        ]
        if len(installs) > 1:
            findings.append(f"{prefix} has more than one dependency-install step")
        elif installs and not PIP_INSTALL_RE.fullmatch(installs[0]):
            findings.append(
                f"{prefix} dependency install is not a standalone pip command"
            )

        scope, scope_findings = _validate_scope(prefix, raw_definition.get("paths"))
        findings.extend(scope_findings)
        if scope and not scope_findings:
            findings.extend(
                _scope_coverage_findings(str(job_id), raw_definition, scope)
            )

        legacy.append(
            LegacyJob(
                job_id=str(job_id),
                definition=raw_definition,
                ordinal=ordinal,
                weight=_job_weight(str(job_id), raw_definition),
                paths=scope,
            )
        )

    if findings:
        raise ManifestError("\n".join(findings))
    if not legacy:
        raise ManifestError("workflow contains no legacy jobs")
    return legacy


def partition_jobs(jobs: Iterable[LegacyJob], pack_count: int) -> list[list[LegacyJob]]:
    """Greedily balance stable jobs across ``pack_count`` packs."""
    if pack_count < 1:
        raise ValueError("pack_count must be positive")
    packs: list[list[LegacyJob]] = [[] for _ in range(pack_count)]
    weights = [0] * pack_count
    for job in sorted(jobs, key=lambda item: (-item.weight, item.ordinal)):
        target = min(range(pack_count), key=lambda index: (weights[index], index))
        packs[target].append(job)
        weights[target] += job.weight
    for pack in packs:
        pack.sort(key=lambda item: item.ordinal)
    return packs


# ---------------------------------------------------------------------------
# Plan once, execute many (2026-08-11)
#
# Every pack used to re-derive the entire selection for itself: twelve runners
# each loading the manifest, each running infer_job_scopes over 180 jobs, each
# re-deciding the same partition from the same inputs.  That decision is a pure
# function of (manifest, changed set, scope mode, pack count), so it is now
# computed ONCE by `build_plan`, published by `ci-plan` as a hashed document,
# and merely CHECKED by each pack (`--expect-plan-sha`).  Twelve runners
# silently disagreeing about what the suite is becomes one loud red instead.
#
# What this does NOT buy at this revision, measured 2026-08-11 against the real
# 180-job manifest: it saves ZERO packs.  Scope inference derives scopes for
# 179/180 jobs, yet every realistic diff still selects enough of them to fill
# all twelve packs —
#
#     docs-only          120/180 eligible -> 12/12 packs non-empty
#     one template       130/180          -> 12/12
#     one engine module  122/180          -> 12/12
#     test-only          115/180          -> 12/12
#
# (pack weights [481, ~250-310 x11]; pack 0 is the indivisible
# engine-render-guards lane, which alone cannot be split further).  So
# `nonempty_pack_indices` is [0..11] for every diff shape today and `has_work`
# is always true.  Do not read the empty-pack machinery as a claim that packs
# are being skipped now — they are not.
#
# Nor does planning once make the packs cheaper, and the arithmetic runs the
# OTHER way, so do not write that it does.  `--expect-plan-sha` requires each
# pack to RECOMPUTE the plan (a pack that trusted a handed-down partition would
# prove nothing), and a pack has always had to derive the partition anyway to
# know which jobs are its own.  So the twelve inference passes did not go away:
# ci-plan adds a THIRTEENTH, and unlike the other twelve it is serialised ahead
# of the whole matrix.  On a pull request that pass costs ~106 s locally over the
# 180-job manifest (measured 2026-08-11; scope inference is the expensive half of
# a plan, everything else is ~0.2 s).
#
# What plan-once buys at this revision is therefore exactly two things, both
# correctness rather than speed: twelve runners can no longer silently disagree
# about what the suite IS — a divergence is one loud red at pack N instead of a
# green check name covering a partition nobody published — and there is a single
# stable aggregate (`ci-gate`) for branch protection to name now that a PR may
# legitimately publish a subset of ci-pack-0..11.  The saving arrives only when
# selection narrows enough to empty a pack.
# ---------------------------------------------------------------------------

PLAN_SCHEMA = "ci.pack_plan.v1"
PLAN_MARKER = "CI_PACK_PLAN="


@dataclass(frozen=True)
class CIPackPlan:
    """One immutable CI decision, shared verbatim by ci-plan and every pack."""

    schema: str
    changed_from: str | None
    scope_mode: str
    reason: str
    scope_summary: str
    legacy_job_count: int
    eligible_job_ids: tuple[str, ...]
    skipped_job_ids: tuple[str, ...]
    pack_jobs: tuple[tuple[str, ...], ...]
    pack_weights: tuple[int, ...]
    nonempty_pack_indices: tuple[int, ...]
    plan_sha256: str
    # Neither serialised nor hashed.  `scoped_jobs` carries the RESOLVED jobs so
    # main() executes the very objects the plan partitioned instead of inferring
    # scopes a second time and hoping the second pass agrees.  `predicted_job_ids`
    # carries what select_jobs chose BEFORE a shadow/off override widened
    # `eligible_job_ids` back to the full manifest — that difference is the
    # entire output of the shadow lane.  Both are compare=False so two plans
    # built from the same inputs stay equal and the hash remains the identity.
    scoped_jobs: tuple[LegacyJob, ...] = field(default=(), compare=False, repr=False)
    predicted_job_ids: tuple[str, ...] = field(default=(), compare=False, repr=False)

    @property
    def pack_count(self) -> int:
        return len(self.pack_jobs)

    @property
    def has_work(self) -> bool:
        return bool(self.nonempty_pack_indices)

    def matrix(self) -> dict[str, list[dict[str, int]]]:
        """The GitHub Actions matrix for exactly the packs that carry work."""
        return {"include": [{"pack": index} for index in self.nonempty_pack_indices]}

    def to_dict(self) -> dict[str, Any]:
        """The published plan document.

        `scoped_jobs` and `predicted_job_ids` are deliberately absent: this
        document is a contract between two runners, and a LegacyJob's definition
        mapping is neither stable nor meaningful across that boundary.
        """
        return {
            "schema": self.schema,
            "changed_from": self.changed_from,
            "scope_mode": self.scope_mode,
            "reason": self.reason,
            "scope_summary": self.scope_summary,
            "legacy_job_count": self.legacy_job_count,
            "eligible_job_count": len(self.eligible_job_ids),
            "eligible_jobs": list(self.eligible_job_ids),
            "skipped_job_count": len(self.skipped_job_ids),
            "skipped_jobs": list(self.skipped_job_ids),
            "packs": [
                {
                    "index": index,
                    "weight": self.pack_weights[index],
                    "jobs": list(jobs),
                }
                for index, jobs in enumerate(self.pack_jobs)
            ],
            "nonempty_pack_indices": list(self.nonempty_pack_indices),
            "matrix": self.matrix(),
            "has_work": self.has_work,
            "plan_sha256": self.plan_sha256,
        }


def plan_hash_payload(
    *,
    changed_from: str | None,
    scope_mode: str,
    pack_count: int,
    eligible_job_ids: Iterable[str],
    pack_jobs: Iterable[Iterable[str]],
    pack_weights: Iterable[int],
) -> dict[str, Any]:
    """Exactly what a pack must agree with ci-plan about, and nothing else.

    Prose (`reason`, `scope_summary`) is EXCLUDED on purpose: rewording a
    diagnostic must never be able to make a pack refuse a plan that selects the
    identical jobs.  Derived values (non-empty indices, skipped ids, counts) are
    excluded because they are functions of the keys below — hashing them only
    adds ways for two identical decisions to disagree.  The matrix MODE is
    excluded too: it is an emission policy, so ci-plan and ci-pack agree on the
    hash whether or not every pack was launched.
    """
    return {
        "schema": PLAN_SCHEMA,
        "changed_from": changed_from,
        "scope_mode": scope_mode,
        "pack_count": pack_count,
        # PLAN order, never sorted: partition_jobs is greedy over
        # (-weight, ordinal), so the sequence itself is load-bearing.
        "eligible_job_ids": list(eligible_job_ids),
        "pack_jobs": [list(jobs) for jobs in pack_jobs],
        "pack_weights": list(pack_weights),
    }


def _canonical_digest(payload: dict[str, Any]) -> str:
    """Canonical JSON sha256 — identical on any machine, Python, or dict order."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_plan(
    jobs: Iterable[LegacyJob],
    changed: list[str] | None,
    *,
    changed_from: str | None,
    scope_mode: str,
    pack_count: int = 12,
) -> CIPackPlan:
    """Decide, once, what this CI run executes.

    This is the ONLY place eligibility and partitioning are decided.  It runs
    exactly the steps main() used to run inline, in the same order and under the
    same conditions, so moving the decision here cannot change it.
    """
    jobs = list(jobs)
    # A global invalidator changes what any job MEANS, so inferring scopes under
    # one is not merely useless — it spends a minute deriving ownership that
    # select_jobs is about to discard.
    invalidated = bool(
        changed and any(_matches_any(GLOBAL_INVALIDATORS, path) for path in changed)
    )
    scope_summary = "scope inference not needed"
    if (
        changed_from
        and scope_mode != "off"
        and changed is not None
        and not invalidated
    ):
        jobs, scope_summary = infer_job_scopes(jobs)

    eligible, reason = select_jobs(jobs, changed)
    predicted_job_ids = tuple(job.job_id for job in eligible)
    if scope_mode == "off" and changed_from:
        eligible = jobs
        reason = "full suite: CI_SCOPE_MODE=off"
    elif scope_mode == "shadow" and changed_from:
        eligible = jobs
        reason = (
            f"shadow full suite: predicted {len(predicted_job_ids)}/{len(jobs)} jobs; "
            f"{reason}"
        )

    # Balance across the SELECTED set, not the full manifest — otherwise a
    # scoped run would leave whole packs empty while one pack carried it all.
    packs = partition_jobs(eligible, pack_count)
    pack_jobs = tuple(tuple(job.job_id for job in pack) for pack in packs)
    pack_weights = tuple(sum(job.weight for job in pack) for pack in packs)
    eligible_job_ids = tuple(job.job_id for job in eligible)
    selected_ids = set(eligible_job_ids)
    skipped_job_ids = tuple(
        job.job_id for job in jobs if job.job_id not in selected_ids
    )
    return CIPackPlan(
        schema=PLAN_SCHEMA,
        changed_from=changed_from,
        scope_mode=scope_mode,
        reason=reason,
        scope_summary=scope_summary,
        legacy_job_count=len(jobs),
        eligible_job_ids=eligible_job_ids,
        skipped_job_ids=skipped_job_ids,
        pack_jobs=pack_jobs,
        pack_weights=pack_weights,
        nonempty_pack_indices=tuple(
            index for index, pack in enumerate(pack_jobs) if pack
        ),
        plan_sha256=_canonical_digest(
            plan_hash_payload(
                changed_from=changed_from,
                scope_mode=scope_mode,
                pack_count=pack_count,
                eligible_job_ids=eligible_job_ids,
                pack_jobs=pack_jobs,
                pack_weights=pack_weights,
            )
        ),
        scoped_jobs=tuple(jobs),
        predicted_job_ids=predicted_job_ids,
    )


def plan_from_workflow(
    workflow: Path,
    *,
    changed_from: str | None,
    scope_mode: str,
    pack_count: int = 12,
) -> CIPackPlan:
    """Load the manifest, resolve the diff, and plan — the whole decision."""
    legacy = load_legacy_jobs(workflow)
    changed = changed_files(changed_from) if changed_from else None
    return build_plan(
        legacy,
        changed,
        changed_from=changed_from,
        scope_mode=scope_mode,
        pack_count=pack_count,
    )


def _full_matrix(pack_count: int) -> dict[str, list[dict[str, int]]]:
    """Every pack, launched. The only safe answer when the plan is not trusted."""
    return {"include": [{"pack": index} for index in range(pack_count)]}


def _one_line(text: str) -> str:
    """Flatten a message destined for a GitHub annotation.

    A ManifestError joins its findings with newlines.  Emitted raw, only the
    first line would start with `::` and GitHub would drop everything after it —
    the same silent-annotation trap as logging one (CLAUDE.md, #3587).
    """
    return " / ".join(part.strip() for part in text.splitlines() if part.strip())


def _write_github_output(
    path: Path,
    *,
    matrix: dict[str, Any],
    has_work: bool,
    plan_sha: str,
    reason: str,
) -> None:
    """Append the four ci-plan outputs to a `$GITHUB_OUTPUT` file.

    `name=value` cannot carry a newline and `reason` is free prose (a manifest
    error message reaches it verbatim on the fallback path), so every value uses
    the heredoc form.  The delimiter is derived from the plan hash: it cannot
    appear in compact JSON, in "true"/"false", in a hexdigest, or in prose about
    job counts and paths.
    """
    delimiter = "ci_plan_" + (plan_sha[:32] or "planner_fallback")
    payload = "".join(
        f"{name}<<{delimiter}\n{value}\n{delimiter}\n"
        for name, value in (
            ("matrix", json.dumps(matrix, sort_keys=True, separators=(",", ":"))),
            ("has_work", "true" if has_work else "false"),
            ("plan_sha", plan_sha),
            ("reason", reason),
        )
    )
    # ONE append, never four: a failure between writes would leave GitHub parsing
    # a half-declared output, and the fallback path would then append a second,
    # contradicting `matrix` behind it.
    with path.open("a", encoding="utf-8") as handle:
        handle.write(payload)


def _emit_plan_artifacts(args: argparse.Namespace, plan: CIPackPlan) -> None:
    """Publish the plan in whichever forms the caller asked for."""
    if args.emit_plan_json:
        document = plan.to_dict()
        if str(args.emit_plan_json) == "-":
            # One prefixed machine line, the same idiom as CI_SCOPE_SHADOW_PLAN,
            # so one stream serves both a human reading the log and a parser.
            print(
                PLAN_MARKER
                + json.dumps(document, sort_keys=True, separators=(",", ":")),
                flush=True,
            )
        else:
            Path(args.emit_plan_json).write_text(
                json.dumps(document, indent=2) + "\n", encoding="utf-8"
            )
    if args.github_output is None:
        return
    if args.matrix_mode == "active":
        matrix = plan.matrix()
        has_work = plan.has_work
        reason = plan.reason
    else:
        # shadow/off launch every pack whatever the plan says.  The plan is still
        # published and still hashed, so a wrong plan shows up in the log and in
        # --expect-plan-sha long before it is ever trusted to skip a pack.
        matrix = _full_matrix(plan.pack_count)
        has_work = True
        reason = (
            f"matrix {args.matrix_mode} (all {plan.pack_count} launch): {plan.reason}"
        )
    _write_github_output(
        args.github_output,
        matrix=matrix,
        has_work=has_work,
        plan_sha=plan.plan_sha256,
        reason=reason,
    )


def _emit_planner_fallback(args: argparse.Namespace, exc: BaseException) -> None:
    """A planner that cannot decide must WIDEN, never narrow.

    `has_work: false` is only ever an affirmative proof that no pack is needed.
    An exception is not that proof, so the fallback launches every pack with an
    empty `plan_sha` (each pack then runs unpinned rather than failing on a hash
    ci-plan never produced) and the step still exits 0.

    This is not a hole: every pack runs this same script, so a genuine
    ManifestError still fails all twelve packs red.  Refusing to plan must never
    be able to skip a test.
    """
    _write_github_output(
        args.github_output,
        matrix=_full_matrix(args.pack_count),
        has_work=True,
        plan_sha="",
        reason=f"full suite: planner error ({exc})",
    )
    # Bare print, never a logger: a prefixing formatter makes GitHub drop the
    # annotation silently (CLAUDE.md — annotations must START the line).
    print(
        "::warning title=ci-plan-fallback::CI planning failed "
        f"({_one_line(str(exc))}); launching all {args.pack_count} packs unpinned",
        flush=True,
    )


def _resolve_pack(plan: CIPackPlan, pack_index: int) -> list[LegacyJob]:
    """Map a pack's planned job ids back to the jobs it executes.

    Resolution goes through `plan.scoped_jobs` rather than re-reading the
    manifest, so a pack runs the very objects the plan partitioned — it cannot
    execute a job whose derived scope was inferred twice and differed the second
    time.
    """
    by_id = {job.job_id: job for job in plan.scoped_jobs}
    return [by_id[job_id] for job_id in plan.pack_jobs[pack_index]]


def render_command(command: str, *, base_ref: str, head_ref: str) -> str:
    """Resolve the only GitHub expressions permitted in legacy run steps."""
    replacements = {
        "${{ github.base_ref || 'main' }}": base_ref or "main",
        "${{ github.base_ref }}": base_ref,
        "${{ github.head_ref }}": head_ref,
    }
    rendered = command
    for expression, value in replacements.items():
        rendered = rendered.replace(expression, value)
    leftovers = EXPRESSION_RE.findall(rendered)
    if leftovers:
        raise ManifestError(
            "unsupported GitHub expression(s) in legacy run step: "
            + ", ".join(sorted(set(leftovers)))
        )
    return rendered


def dependency_command(job: LegacyJob) -> str | None:
    """Return the validated standalone pip command for a legacy job."""
    for step in job.definition["steps"]:
        command = str(step.get("run", ""))
        if "pip install" in command:
            return command
    return None


def _workspace_root() -> Path:
    workspace = os.environ.get("GITHUB_WORKSPACE")
    if os.environ.get("GITHUB_ACTIONS") != "true" or not workspace:
        raise RuntimeError(
            "--execute is allowed only inside GitHub Actions with GITHUB_WORKSPACE set"
        )
    root = Path(workspace).resolve()
    if Path.cwd().resolve() != root:
        raise RuntimeError(f"refusing cleanup outside GITHUB_WORKSPACE ({root})")
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        check=True,
        capture_output=True,
        text=True,
    )
    if Path(result.stdout.strip()).resolve() != root:
        raise RuntimeError("GITHUB_WORKSPACE is not the checkout's git root")
    return root


def _restore_workspace() -> None:
    """Restore the clean-checkout boundary that each old job received."""
    subprocess.run(["git", "reset", "--hard", "HEAD"], check=True)
    subprocess.run(["git", "clean", "-ffdx"], check=True)


def _run_job(
    job: LegacyJob,
    *,
    base_ref: str,
    head_ref: str,
    command_env: dict[str, str],
) -> str | None:
    """Run one legacy job; return a failure description or ``None``."""
    _restore_workspace()
    timeout_minutes = job.definition.get("timeout-minutes")
    timeout_seconds = int(timeout_minutes) * 60 if timeout_minutes else None

    for index, step in enumerate(job.definition["steps"]):
        if "uses" in step:
            continue  # checkout/Python/Node are provided once by ci-pack.
        if "pip install" in str(step.get("run", "")):
            continue  # Prepared once for this exact dependency group.
        step_name = str(step.get("name") or f"run step {index + 1}")
        command = render_command(
            str(step["run"]), base_ref=base_ref, head_ref=head_ref
        )
        print(f"::group::{job.job_id} — {step_name}", flush=True)
        try:
            result = subprocess.run(
                ["bash", "-eo", "pipefail", "-c", command],
                env=command_env,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            print("::endgroup::", flush=True)
            return f"{job.job_id}: timed out after {timeout_minutes} minutes"
        print("::endgroup::", flush=True)
        if result.returncode:
            return (
                f"{job.job_id}: step {step_name!r} exited {result.returncode}"
            )
    return None


def _dependency_environment(
    install_command: str | None,
) -> dict[str, str]:
    """Build a clean, single-use dependency environment for a job group."""
    command_env = os.environ.copy()
    if install_command is None:
        return command_env

    runner_temp = os.environ.get("RUNNER_TEMP")
    if not runner_temp:
        raise RuntimeError("RUNNER_TEMP is required to isolate legacy dependencies")
    environment = Path(runner_temp).resolve() / "ci-pack-job-env"
    if environment.exists():
        shutil.rmtree(environment)
    subprocess.run([sys.executable, "-m", "venv", str(environment)], check=True)
    command_env["PATH"] = (
        str(environment / "bin") + os.pathsep + command_env.get("PATH", "")
    )
    print(f"::group::dependency environment — {install_command}", flush=True)
    result = subprocess.run(
        ["bash", "-eo", "pipefail", "-c", install_command],
        env=command_env,
    )
    print("::endgroup::", flush=True)
    if result.returncode:
        raise RuntimeError(
            f"dependency install exited {result.returncode}: {install_command}"
        )
    return command_env


def execute_pack(
    jobs: list[LegacyJob], *, shadow_predicted: frozenset[str] | None = None
) -> int:
    """Execute a pack, continuing after failures so one run reports all reds."""
    _workspace_root()
    base_ref = os.environ.get("CI_BASE_REF", "main")
    head_ref = os.environ.get("CI_HEAD_REF", "")
    failures: list[str] = []
    current_dependency: object = object()
    command_env = os.environ.copy()
    try:
        # Adjacent jobs with an identical declared dependency set share that
        # exact environment.  A different set recreates the venv from scratch,
        # preserving the old jobs' minimal-dependency boundary without keeping
        # dozens of large environments on disk.
        ordered_jobs = sorted(
            jobs, key=lambda job: (dependency_command(job) or "", job.ordinal)
        )
        for job in ordered_jobs:
            dependency = dependency_command(job)
            if dependency != current_dependency:
                command_env = _dependency_environment(dependency)
                current_dependency = dependency
            failure = _run_job(
                job,
                base_ref=base_ref,
                head_ref=head_ref,
                command_env=command_env,
            )
            if failure:
                failures.append(failure)
                print(f"::error::{failure}", flush=True)
            if shadow_predicted is not None:
                record: dict[str, object] = {
                    "job": job.job_id,
                    "predicted_selected": job.job_id in shadow_predicted,
                    "status": "failed" if failure else "passed",
                }
                if failure:
                    record["failure"] = failure
                print(
                    "CI_SCOPE_SHADOW_RESULT=" + json.dumps(record, sort_keys=True),
                    flush=True,
                )
    finally:
        _restore_workspace()

    if failures:
        print("\nLegacy CI failures:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow", type=Path, required=True)
    parser.add_argument("--pack-index", type=int, default=0)
    parser.add_argument("--pack-count", type=int, default=2)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--validate-only", action="store_true")
    # Absent = run the full suite. main's baseline and workflow_dispatch pass
    # nothing here ON PURPOSE, so the complete manifest always audits main.
    parser.add_argument("--changed-from", default=None)
    parser.add_argument(
        "--scope-mode",
        choices=("active", "shadow", "off"),
        default=os.environ.get("CI_SCOPE_MODE", "active"),
        help=(
            "active selects proven owners; shadow reports the selection but runs "
            "everything; off is the emergency full-suite kill switch"
        ),
    )
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="compute and publish the plan; never execute a legacy job",
    )
    parser.add_argument(
        "--emit-plan-json",
        default=None,
        metavar="PATH|-",
        help=(
            f"'-' prints exactly one {PLAN_MARKER}<compact json> line; a path "
            "writes the indented plan document to that file"
        ),
    )
    parser.add_argument(
        "--expect-plan-sha",
        default=None,
        help="refuse to execute unless the recomputed plan hashes to this sha256",
    )
    parser.add_argument(
        "--github-output",
        type=Path,
        default=None,
        help=(
            "append matrix/has_work/plan_sha/reason to a $GITHUB_OUTPUT file; "
            "only meaningful with --plan-only"
        ),
    )
    parser.add_argument(
        "--matrix-mode",
        choices=("active", "shadow", "off"),
        default=os.environ.get("CI_DYNAMIC_MATRIX_MODE", "shadow"),
        help=(
            "active launches only the packs that carry work; shadow and off "
            "publish the plan but still launch every pack. Affects the emitted "
            "outputs only — never the plan and never its hash"
        ),
    )
    args = parser.parse_args(argv)
    if args.execute and args.validate_only:
        parser.error("--execute and --validate-only are mutually exclusive")
    if args.execute and args.plan_only:
        parser.error("--execute and --plan-only are mutually exclusive")
    if not 0 <= args.pack_index < args.pack_count:
        parser.error("--pack-index must be between 0 and pack-count - 1")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        plan = plan_from_workflow(
            args.workflow,
            changed_from=args.changed_from,
            scope_mode=args.scope_mode,
            pack_count=args.pack_count,
        )
        shadow = args.scope_mode == "shadow" and args.changed_from
        if shadow:
            predicted_ids = frozenset(plan.predicted_job_ids)
            print(
                "CI_SCOPE_SHADOW_PLAN="
                + json.dumps(
                    {
                        "changed_from": args.changed_from,
                        "predicted_selected": sorted(predicted_ids),
                        "predicted_skipped": sorted(
                            job.job_id
                            for job in plan.scoped_jobs
                            if job.job_id not in predicted_ids
                        ),
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
        _emit_plan_artifacts(args, plan)
        # Bare print, never a logger: a prefixing formatter makes GitHub drop the
        # annotation silently (CLAUDE.md — annotations must START the line).
        print(
            f"::notice title=ci-pack-scope::{plan.reason}; {plan.scope_summary}",
            flush=True,
        )
        skipped = plan.legacy_job_count - len(plan.eligible_job_ids)
        if skipped:
            print(
                f"::notice title=ci-pack-skipped::{skipped} legacy job(s) out of "
                f"scope for this diff; main's baseline still runs all "
                f"{plan.legacy_job_count}",
                flush=True,
            )
        if args.plan_only:
            print(
                f"Planned {len(plan.eligible_job_ids)} of "
                f"{plan.legacy_job_count} legacy jobs into {plan.pack_count} packs; "
                f"pack weights={list(plan.pack_weights)}; packs with work="
                f"{list(plan.nonempty_pack_indices)}; plan sha256={plan.plan_sha256}."
            )
            return 0
        # A pack whose recomputed plan differs from the published one would run a
        # DIFFERENT suite under a check name the sweeper reads as proof of this
        # one. Refuse here, before a single legacy step runs, and name both
        # hashes so the divergence is diagnosable rather than merely red.
        if args.expect_plan_sha and args.expect_plan_sha != plan.plan_sha256:
            print(
                "::error title=ci-plan-parity::pack "
                f"{args.pack_index} recomputed plan {plan.plan_sha256} but ci-plan "
                f"published {args.expect_plan_sha}; refusing to run a suite the "
                "published plan does not describe",
                flush=True,
            )
            return 2
        selected = _resolve_pack(plan, args.pack_index)
        print(
            f"Validated {plan.legacy_job_count} legacy jobs; "
            f"{len(plan.eligible_job_ids)} in scope "
            f"({plan.reason}); pack weights={list(plan.pack_weights)}; "
            f"selected pack {args.pack_index} ({len(selected)} jobs)."
        )
        print("Selected jobs: " + ", ".join(job.job_id for job in selected))
        if args.validate_only or not args.execute:
            return 0
        return execute_pack(
            selected,
            shadow_predicted=(
                frozenset(plan.predicted_job_ids) if shadow else None
            ),
        )
    except Exception as exc:  # noqa: BLE001 — see _emit_planner_fallback
        # LAW: uncertainty WIDENS. On the ci-plan path an unplannable manifest
        # must still launch every pack, so this one path swallows the exception,
        # emits the full-suite matrix, and exits 0. Everywhere else — including
        # --plan-only WITHOUT --github-output, which is how a developer validates
        # locally — the old return 2 stands, so a manifest defect stays loud.
        if args.plan_only and args.github_output is not None:
            _emit_planner_fallback(args, exc)
            return 0
        if isinstance(
            exc, (ManifestError, RuntimeError, subprocess.CalledProcessError)
        ):
            print(f"ci-pack validation/execution failed: {exc}", file=sys.stderr)
            return 2
        raise


if __name__ == "__main__":
    raise SystemExit(main())
