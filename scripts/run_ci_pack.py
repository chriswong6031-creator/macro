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
as a hashed ``CIPackPlan`` (``--plan-only``). Each pack consumes that exact JSON
artifact, validates its hash/tree/head/base and manifest execution contracts,
and never recomputes selection or partition, so twelve runners cannot quietly
disagree about what the suite is.

The validator is intentionally fail-closed.  A future job using services,
containers, per-step conditions/environments, or an unfamiliar action must
teach this runner how to preserve that behavior before the workflow can pass.

Execution is refused outside GitHub Actions because workspace cleanup is
destructive by design.  Local callers can safely use ``--validate-only``.
"""

from __future__ import annotations

import argparse
import contextlib
import functools
import hashlib
import json
import os
import platform
import re
import signal
import shutil
import subprocess
import sys
import sysconfig
import tempfile
import threading
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

import yaml

# The pack runner imports only repository-owned scope metadata.  Pin the checkout
# root unconditionally so direct script execution and importlib-based tests resolve
# it identically; conditional pins can silently prefer an installed namesake.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.ci_semantic_proof import (  # noqa: E402
    FRAGMENT_SCHEMA,
    PLAN_SCHEMA,
    FailureAtomCollector,
    SemanticProofError,
    effective_proof_id,
    job_exec_sha256,
    step_spec_sha256,
)
from scripts.ci_authority_paths import (  # noqa: E402
    AuthorityPathError,
    is_ci_authority_path,
)
from scripts.ci_scope_dependencies import (  # noqa: E402
    planner_path_exists,
    planner_path_is_file,
    planner_tracked_path_inventory,
)


PACK_JOB_ID = "ci-pack"
DISABLED_IF = "${{ false }}"
ALLOWED_JOB_KEYS = {
    "gate",
    "if",
    "paths",
    "runs-on",
    "scope",
    "steps",
    "timeout-minutes",
}

#: Every job must declare which tree moves its verdict. `code`: the verdict is
#: a function of the pull request's tree only (pure logic, tmp_path fixtures,
#: committed goldens, config/contracts). `data`: a nightly/wire data commit
#: alone — no code change — can change the verdict (assertions over live
#: `data/**`, rendered `site/**`, or any ledger the nightly advances). The
#: merge gate packs only `gate: code` jobs once the data-health lane exists
#: (W2 of research/CI_MERGE_GATE_RELIABILITY_ROOT_CAUSE_2026_08_19.md);
#: `gate: data` jobs still run and still red something a human reads — the
#: field never deletes a receipt.
GATE_VALUES = ("code", "data")
ALLOWED_STEP_KEYS = {"name", "proof_id", "run", "uses", "with"}

# Changing any item in this string changes the job execution contract digest.
# It deliberately describes only the infrastructure shared by all legacy jobs;
# pack index and matrix position are transport trivia and never enter it.
#
# v2 (2026-08-25, P0R diagnostic bridge, issue #6351): "ubuntu-latest" was
# aspirational, not a runtime fact — it named the hosted image, not what a
# self-hosted diagnostic runner actually is. "linux-x86_64" is a truthful
# logical claim both hosted (ubuntu-latest is Linux/x86_64) and self-hosted
# (Homebrew CPython on Linux/x86_64 PC canary hosts) execution can attest to
# byte-identically, which is the whole point of reconciling their semantic
# fragments. `attest_execution_profile` below enforces every clause of this
# string at runtime before any legacy job executes; production ci.yml already
# pins python-version "3.12.13" and node-version "20" (see ci.yml's ci-pack
# setup-python comment), so this bump does not change what production already
# runs — it only makes the contract string match reality and makes a runtime
# that DISAGREES with it fail closed instead of silently minting evidence.
RUNNER_CONTRACT = "ci-pack/linux-x86_64/python-3.12.13/node-20/v2"

# Admitted ONLY for (role, event) == ("pr_head", "workflow_dispatch"), and ONLY
# when `workflow` equals this exact name (issue #6351 P0R diagnostic bridge).
# SUPPORTED_PLAN_ROLE_EVENTS stays CLOSED — this is a second, narrower, named
# admission on top of it, not a widening of the set itself. The diagnostic
# canary dispatches under workflow_dispatch (GitHub gives no `pull_request`
# transport for a same-repository PR run triggered by hand) but still needs to
# plan and replay an exact PR candidate's changed-file inventory the same way
# `ci.yml`'s real `pr_head/pull_request` plan does, so every existing pr_head
# invariant (exact changed inventory, changed_from == base_sha) still applies
# unchanged. No other workflow name may use this pair; a merge-gating plan
# (`workflow == "ci"`) is refused independently by
# scripts/ci_semantic_proof.py's own narrower pair set and its own
# `workflow == "ci"` assertion, which this constant does not touch.
DIAGNOSTIC_CANARY_WORKFLOW = "infrastructure-selfhosted-ci-canary"
TRUSTED_EXECUTOR_WORKFLOW = "trusted-ci-executor"
DIAGNOSTIC_PR_WORKFLOWS = frozenset(
    {DIAGNOSTIC_CANARY_WORKFLOW, TRUSTED_EXECUTOR_WORKFLOW}
)

# Failure output is streamed live.  These caps cover only the small structured
# atom collector retained alongside the stream; raw logs never enter evidence.
FAILURE_CAPTURE_MAX_BYTES = 131_072
FAILURE_CAPTURE_MAX_ATOMS = 64
FAILURE_CAPTURE_MAX_LINE_BYTES = 4_096

DEFAULT_BASE_REPLAY_BUDGET_SECONDS = 15 * 60
SEMANTIC_DETAIL_MAX_BYTES = 1_024

# Repo-binding Git variables must never reach a legacy step OR a runner
# probe.  Injecting GIT_DIR/GIT_WORK_TREE into the job env (PR #5750,
# 2026-08-15) made every child `git` operate on the pack checkout.  The
# follow-up pack-9 own-red was the same family: the post-step
# ``for-each-ref`` probe still bound GIT_DIR and exited 128, and a
# timeout SIGKILL left packed-refs unreadable.  Runner-owned probes use
# cwd/`git -C` discovery, set GIT_OPTIONAL_LOCKS=0, and heal a smashed
# ref store so the next job still sees tests/*.py.
REPO_BINDING_GIT_VARS = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_COMMON_DIR",
    "GIT_NAMESPACE",
)

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
# the full manifest still audits main. Ordinary PRs do not widen to that audit
# merely because one changed path has no proven owner — that mapping was the
# speed hole (PR #5488: `.claude/hooks/gh_quota_guard.py` → all 185/187 jobs).
# Unowned paths stay on always-on fences + owners of the rest of the diff.
# Main / CI_SCOPE_MODE=off remains the long fail-fast:false heal pack.
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

# Bounded `.md` mention in a job command. A substring test also fires on
# `.mdx` / `.mdown` / `.mdc` and incidental `.md` inside a URL, which would
# promote every opaque fallback of those jobs back into the owned tier.
MD_COMMAND_RE = re.compile(r"\.md(?![A-Za-z0-9])")

# A statically opaque subprocess or tree traversal must own every established
# repository surface it could inspect.  This is deliberately broad: it keeps
# whole-tree guards such as all-exports-resolve selected for every engine/script
# edit, while still allowing an unrelated narrow owner to skip guards that have
# no opaque I/O.  A new top-level directory remains unowned; it does not widen
# the PR to a full run — it rides always-on fences only.
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
# A scope that ``narrow_to_suffixes`` produced: `<parent>/**/*.<ext>`, its
# `/**` directory-subtree companion, or the `*.<ext>` repository-root form. The
# tail carries no glob metacharacter, so every such pattern matches a strict
# subset of `<parent>/**`.
SUFFIX_NARROWED_RE = re.compile(
    r"(?:(?P<parent>[^*?]+)/\*\*/)?\*\.[A-Za-z0-9_]{1,8}(?:/\*\*)?"
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
# Hosted ubuntu-latest step times from green PR #5550 / run 31729769728
# (legacy-job groups only; checkout excluded). Pack 1's 56-minute wall-clock
# was 31 minutes of fetch-depth:0 stampede plus these underweighted heavies
# sitting together because the 2026-08-11 local Mac weights were stale.
#
# 2026-08-14: `engine-render-guards` (1036) was split into three lanes. Its 1036
# was a hosted measurement of the whole job, and no hosted per-STEP breakdown
# exists, so the three weights below are that hosted total re-apportioned by the
# per-step shares measured locally in
# research/CI_RENDER_GUARD_TIMING_RECEIPT_2026-08-12.md (427.6s wall, twelve
# steps): rot sweep + statement-tape 83.4%, the express guards 10.8%, the
# B4/attested-history cluster 5.8%. Two express steps (market-score authority,
# China Policy Watch) were wired AFTER that receipt and are unmeasured, so
# express carries an explicit allowance above its 112s share. These are
# estimates from a measured shape, not a second hosted run — replace them from
# a green post-split run's step timings when one exists.
# Which (role, event) pairs may mint or consume a semantic plan.
#
# ``role`` carries the SUBSTANCE and is enforced separately below: ``pr_head``
# requires an exact changed-file inventory and ``changed_from == base_sha``;
# ``main`` requires one identical tree/head/base SHA and no ``changed_from``.
# The event is the TRANSPORT, and it is allowlisted rather than ignored so a
# combination nobody has reasoned about fails closed instead of silently
# planning something unintended.
#
# The two ``main`` triggers below the dispatch were added 2026-08-19 because
# leaving them out did not fail closed in the useful sense — it left the lane
# that runs every ``gate: data`` job unable to run ANY of them. ``data-health.yml``
# (W2 of research/CI_MERGE_GATE_RELIABILITY_ROOT_CAUSE_2026_08_19.md) took the
# 74 data-gated jobs off the merge gate on the promise that this lane would still
# grade them AFTER the nightly writes the tree they assert against. It fires on
# ``workflow_run`` (daily completed) and on a 13:30 UTC ``schedule`` backstop,
# and both resolve role ``main`` — so both raised ManifestError before a single
# legacy job ran. Measured: run 32262001614 (schedule, 2026-08-19T14:06Z) died
# with ``main/schedule is unsupported``, exit 2, in all SIX packs; the
# ``workflow_run`` run 32246816331 only escaped the same fate because its packs
# were skipped by the daily-success condition. The single execution that lane
# achieved all day came from a manual ``workflow_dispatch``, and it graded the
# universe against ``data/symbol_directory/snapshots/2026-08-10.parquet`` — nine
# days stale, because the 2026-08-19 snapshot (6f3fd8b3ea1f) was not committed
# until 12:16Z, after it. The schedule that exists to catch exactly that ordering
# is the one that could not start.
#
# Both events describe the same shape ``main`` already means: a whole-tree run at
# one checked-out SHA with no diff. Nothing about the substance is relaxed here —
# the ``role == "main"`` invariants still reject a plan that is not that shape.
# The set stays CLOSED; ``push`` is deliberately absent (no gating workflow uses
# it, and ci.yml has no push trigger).
#
# ``ci_semantic_proof._identity`` keeps its OWN, narrower pair set on purpose —
# do not "unify" it with this one. That gate also asserts ``workflow == "ci"``:
# it judges merge-gate proofs, and a data-health plan is not one. Widening it
# would let a non-gating lane's plan pose as authority for a merge.
SUPPORTED_PLAN_ROLE_EVENTS = frozenset({
    ("pr_head", "pull_request"),
    ("main", "workflow_dispatch"),
    ("main", "workflow_run"),
    ("main", "schedule"),
})

PACK_TARGET_SECONDS = 600
OBSERVED_COMMAND_SECONDS = {
    "engine-render-guards": 860,
    "express-render-guards": 150,
    "attested-history-guards": 60,
    "workflow-yaml": 438,
    "market-memory-contract": 416,
    "unrun-government-revenue-grader": 322,
    "biocatalyst-worker": 274,
    "biocatalyst-serving": 272,
    "flow-surface": 267,
    "capital-structure-intelligence": 247,
    "marketing-engine": 250,
    "unrun-picks-boards": 245,
    "biocatalyst-history": 172,
    "unrun-subsector-themes": 134,
    "inline-js": 124,
    "unrun-market-plumbing": 114,
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
    # Patterns whose provenance is an OPAQUE fallback: a subprocess call or
    # filesystem traversal somewhere in the job's closure widened it to whole
    # scan roots. They still select the job for code/data edits, but a
    # narrative file (`**/*.md`) never matches this tier.
    fallback_paths: tuple[str, ...] = ()
    # True when the manifest declares `scope: exclusive` — the declared
    # `paths:` then REPLACE inference instead of being unioned under it, and
    # the declaration is coverage-audited fatally at load time.
    exclusive: bool = False
    # Which tree moves this job's verdict: "code" (the PR's tree only) or
    # "data" (a nightly/wire data commit alone can flip it). Mandatory in the
    # manifest; see GATE_VALUES.
    gate: str = "code"

    @property
    def is_scoped(self) -> bool:
        """Whether ANY tier can narrow this job off a diff."""
        return bool(self.paths or self.fallback_paths)


@dataclass(frozen=True)
class SemanticStepSpec:
    """Stable semantic identity and execution contract for one manifest step."""

    proof_id: str
    step_spec_sha256: str
    display_name: str = field(compare=False)
    step_index: int = field(compare=False)
    raw_step: Mapping[str, Any] = field(compare=False, repr=False)

    def plan_dict(self) -> dict[str, str]:
        # The display name and ordinal are diagnostics, never proof identity.
        return {
            "proof_id": self.proof_id,
            "step_spec_sha256": self.step_spec_sha256,
        }


@dataclass(frozen=True)
class SemanticJobSpec:
    """Expected proof surface for one selected logical job."""

    logical_job_id: str
    pack_index: int
    job_exec_sha256: str
    steps: tuple[SemanticStepSpec, ...]

    def plan_dict(self) -> dict[str, Any]:
        return {
            "logical_job_id": self.logical_job_id,
            "pack_index": self.pack_index,
            "job_exec_sha256": self.job_exec_sha256,
            "steps": [step.plan_dict() for step in self.steps],
        }


@dataclass(frozen=True)
class CommandObservation:
    """One streamed command outcome without retained raw output."""

    outcome: str
    returncode: int | None
    failure_signature: Mapping[str, Any] | None = None
    detail: str | None = None


@dataclass(frozen=True)
class JobExecution:
    """Raw facts produced by one logical job on one tree."""

    logical_job_id: str
    job_exec_sha256: str
    infrastructure: Mapping[str, Any]
    steps: tuple[Mapping[str, Any], ...]
    failure: str | None

    def fragment_dict(self) -> dict[str, Any]:
        return {
            "logical_job_id": self.logical_job_id,
            "job_exec_sha256": self.job_exec_sha256,
            "infrastructure": dict(self.infrastructure),
            "steps": [dict(step) for step in self.steps],
        }


def _describe_failure(value: object) -> str:
    """Render a failure WITH the child's own stderr, never the exit status alone.

    ``CalledProcessError`` stringifies to "returned non-zero exit status 1" and
    drops everything the command actually said. That is how a fleet-wide
    base-replay checkout failure stayed undiagnosable: every consumer saw the
    command line and an exit code, while git's one explanatory line
    ("unable to read sha1 file of ...") existed only in the raw runner log.
    A classifier that degrades to ``unknown`` must at least say why.
    """
    if not isinstance(value, subprocess.CalledProcessError):
        return str(value)
    parts = [str(value)]
    for label, stream in (("stderr", value.stderr), ("stdout", value.stdout)):
        if isinstance(stream, (bytes, bytearray)):
            text = bytes(stream).decode("utf-8", "replace")
        else:
            text = stream or ""
        text = text.strip()
        if text:
            parts.append(f"{label}: {text}")
    return " | ".join(parts)


def _bounded_detail(value: object, *, limit: int = SEMANTIC_DETAIL_MAX_BYTES) -> str:
    """Return a deterministic one-line diagnostic with a strict UTF-8 bound."""
    text = _one_line(_describe_failure(value))
    encoded = text.encode("utf-8", "replace")
    if len(encoded) <= limit:
        return text
    suffix = "…[truncated]".encode("utf-8")
    return (encoded[: max(0, limit - len(suffix))] + suffix).decode(
        "utf-8", "ignore"
    )


def _is_dependency_step(step: Mapping[str, Any]) -> bool:
    command = str(step.get("run", ""))
    return bool(command and "pip install" in command)


def _provided_action_spec(step: Mapping[str, Any]) -> dict[str, Any]:
    """Return one action contract the pack runner implements exactly.

    A broad ``actions/checkout@`` prefix is not an execution contract. In
    particular, four legacy jobs request full history while the transport
    checkout is deliberately shallow. Keep the accepted surface closed so a
    new action version/input cannot be silently skipped by the pack runner.
    """
    uses = step.get("uses")
    raw_with = step.get("with")
    if raw_with is None:
        inputs: dict[str, Any] = {}
    elif isinstance(raw_with, Mapping):
        inputs = dict(raw_with)
    else:
        raise ManifestError("action with must be a mapping")
    contract = {"uses": uses, "with": inputs}
    allowed = (
        {"uses": "actions/checkout@v4", "with": {}},
        {"uses": "actions/checkout@v4", "with": {"fetch-depth": 0}},
        {
            "uses": "actions/setup-python@v5",
            "with": {"python-version": "3.12"},
        },
        {"uses": "actions/setup-node@v4", "with": {"node-version": "20"}},
    )
    if contract not in allowed:
        raise ManifestError(
            "action is not provided by the pack runner with these exact inputs: "
            + json.dumps(contract, sort_keys=True, separators=(",", ":"))
        )
    return contract


def _job_action_contract(job: LegacyJob) -> tuple[dict[str, Any], ...]:
    return tuple(
        _provided_action_spec(step)
        for step in job.definition.get("steps", [])
        if isinstance(step, Mapping) and "uses" in step
    )


def semantic_step_specs(job: LegacyJob) -> tuple[SemanticStepSpec, ...]:
    """Return every executable semantic step in manifest order.

    Checkout/setup actions and the validated standalone dependency install are
    infrastructure.  They intentionally receive no proof identity.
    """
    specs: list[SemanticStepSpec] = []
    seen: dict[str, int] = {}
    for index, step in enumerate(job.definition.get("steps", [])):
        if not isinstance(step, Mapping) or "run" not in step:
            continue
        if _is_dependency_step(step):
            continue
        try:
            proof_id = effective_proof_id(step)
            digest = step_spec_sha256(step)
        except SemanticProofError as exc:
            raise ManifestError(
                f"job {job.job_id!r} step {index + 1} has invalid semantic "
                f"identity: {exc}"
            ) from exc
        if proof_id in seen:
            raise ManifestError(
                f"job {job.job_id!r} semantic proof_id {proof_id!r} is not "
                f"unique (steps {seen[proof_id] + 1} and {index + 1}); add "
                "explicit proof_id values only to the ambiguous steps"
            )
        seen[proof_id] = index
        specs.append(
            SemanticStepSpec(
                proof_id=proof_id,
                step_spec_sha256=digest,
                display_name=str(step.get("name") or ""),
                step_index=index,
                raw_step=step,
            )
        )
    return tuple(specs)


def semantic_job_digest(job: LegacyJob) -> str:
    """Digest execution/environment inputs shared by all semantic steps."""
    actions = _job_action_contract(job)
    action_digest = hashlib.sha256(
        json.dumps(
            actions,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return job_exec_sha256(
        dependency_install_command=dependency_command(job),
        timeout_minutes=job.definition.get("timeout-minutes"),
        runner_contract=f"{RUNNER_CONTRACT}/actions-{action_digest}",
    )


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


def _ambiguity_roots(item: str) -> tuple[str, ...] | None:
    """The repository trees one opaque construct can reach, or None if unknown."""
    if "filesystem roots=" in item:
        raw = item.split("filesystem roots=", 1)[1]
        return tuple(f"{root}/**" for root in raw.split(",") if root)
    if "subprocess roots=" in item:
        raw = item.split("subprocess roots=", 1)[1]
        return tuple(f"{root}/**" for root in raw.split(",") if root)
    if item.endswith("filesystem code traversal"):
        return CODE_SCAN_ROOTS
    if item.endswith("filesystem artifact traversal"):
        return ARTIFACT_SCAN_ROOTS
    if item.endswith("filesystem glob"):
        return OPAQUE_IO_ROOTS
    if item.endswith("subprocess invocation"):
        return SUBPROCESS_ROOTS
    if item.endswith("dynamic import"):
        # The target expression is opaque. Widen across every repository tree
        # that can carry importable code, including research/tools helpers and
        # test plugins, rather than guessing one package.
        return CODE_SCAN_ROOTS
    return None


def narrow_to_suffixes(
    patterns: Iterable[str], suffixes: Iterable[str]
) -> tuple[str, ...]:
    """Intersect a root claim with the filename kinds a traversal can yield.

    ``d.glob("*.parquet")`` enumerates parquet files wherever ``d`` points, so a
    ``.json`` or ``.py`` edit cannot change its result even when the directory is
    statically unknown. The old classifier read the pattern only to pick the root
    SET and then claimed every file under it — measured 2026-08-11, that is what
    made a single parquet scan in a hub module hand ``data/**`` to 90 of the 181
    legacy jobs, and left the narrow-diff contract at exactly zero headroom.

    The result is a strict SUBSET of ``patterns``: ``data/**/*.parquet`` matches
    only paths ``data/**`` already matched. No suffixes means no narrowing.

    A glob can also match a DIRECTORY whose name carries the suffix — pyarrow
    writes partitioned datasets as ``x.parquet/part-0.parquet`` — so the subtree
    under a matched entry is claimed alongside it. Without that, an edit inside
    such a directory would silently lose its owner.
    """
    suffixes = tuple(suffixes)
    if not suffixes:
        return tuple(patterns)
    narrowed: set[str] = set()
    for pattern in patterns:
        if pattern.endswith("/**"):
            stems = [f"{pattern[:-3]}/**/*{suffix}" for suffix in suffixes]
        elif pattern == "*":
            stems = [f"*{suffix}" for suffix in suffixes]
        else:
            narrowed.add(pattern)
            continue
        narrowed.update(stems)
        narrowed.update(f"{stem}/**" for stem in stems)
    return tuple(sorted(narrowed))


def exclude_peer_test_ownership(patterns: Iterable[str]) -> tuple[str, ...]:
    """Drop catch-alls that make every ``tests/*.py`` edit select a named pytest job.

    A job that names ``pytest tests/test_foo.py`` already owns that file plus its
    import/read closure. Opaque traversals inside the suite used to add ``*``,
    ``tests/**``, and ``tests/**/*.py``, so a one-file test PR selected 131 of 185
    scoped jobs (measured PR #5550 / run 31729769728: 133/187 jobs, all twelve
    packs, slowest pack 56 minutes). Fixture claims under ``tests/`` that are
    suffix-narrowed to a non-Python kind (``tests/**/*.json``) stay — those can
    change the named suite without being a peer test file. Unpatterned
    ``docs/**`` / ``content/**`` are dropped the same way (narrative trees a
    named pytest job should not rerun for). ``research/**`` stays: it is a
    code-scan root (``all-exports-resolve`` must own it). Script-invoking jobs
    keep the unfiltered fallbacks; this filter applies to the final path set of
    jobs that named specific pytest files.
    """
    dropped_roots = {
        "*",
        "*.py",
        "*.py/**",
        "tests",
        "tests/",
        "tests/**",
        "docs",
        "docs/",
        "docs/**",
        "content",
        "content/",
        "content/**",
    }
    kept: list[str] = []
    for pattern in patterns:
        if pattern in dropped_roots:
            continue
        if pattern.startswith("tests/") and _is_peer_python_or_unpatterned_glob(pattern):
            continue
        kept.append(pattern)
    return tuple(dict.fromkeys(kept))


def _is_peer_python_or_unpatterned_glob(pattern: str) -> bool:
    """True for globs that claim every Python test (or the whole tests tree)."""
    if not any(char in pattern for char in "*?["):
        return False
    stem = pattern[: -len("/**")] if pattern.endswith("/**") else pattern
    if SUFFIX_NARROWED_RE.fullmatch(pattern) or SUFFIX_NARROWED_RE.fullmatch(stem):
        return stem.endswith(".py")
    return True


def _has_glob(segment: str) -> bool:
    """Does this path fragment contain a glob metacharacter?"""
    return any(char in segment for char in "*?")


def scope_pattern_is_startable(pattern: str, triggers: Iterable[str]) -> bool:
    """Can an edit to something ``pattern`` covers start the gating workflow?

    Literal membership in ci.yml's `paths` filter remains the rule for every
    root-level scope. A suffix-narrowed pattern is startable BY CONSTRUCTION when
    its unnarrowed parent is a trigger: ``data/**/*.parquet`` matches a strict
    subset of ``data/**``, so any edit that reaches the job also starts the run.

    Checking the parent instead of demanding a literal entry per (root, suffix)
    pair keeps this guard exactly as strict — a scope rooted at an untriggerable
    tree still fails — while keeping the trigger list closed. Minting an entry
    per pair would red an unrelated pull request the first time any module globbed
    a new extension.
    """
    triggers = tuple(triggers)
    if pattern in triggers:
        return True
    narrowed = SUFFIX_NARROWED_RE.fullmatch(pattern)
    if narrowed:
        parent = narrowed.group("parent")
        pattern = f"{parent}/**" if parent else "*"
        if pattern in triggers:
            return True
    if not pattern.endswith("/**"):
        # `app/*` is a single-level subset of `app/**`. Any edit it covers
        # also matches that ancestor trigger, so the run starts. Exclusive
        # declarations use this form on purpose (`*` does not cross `/`).
        #
        # This covers `app/*.py` too, not just a bare `app/*`. SUFFIX_NARROWED_RE
        # requires a `**/` before the suffix, so a SINGLE-LEVEL suffix glob
        # matched neither it nor the bare-`/*` test below and fell through to
        # False — even though `engine/*.py` is as strictly contained in
        # `engine/**` as `app/*` is. Measured 2026-08-26: `defense-rail-laws`
        # derived an `engine/*.py` scope and reported an unstartable gap against
        # a trigger list that carries `engine/**`, `*` AND `**`. Because
        # ci-pack is path-scoped, only a PR touching .github/ci/ ever ran the
        # test that says so, so the gap sat green on every unrelated PR.
        #
        # Ancestors are walked for the same containment reason as the subtree
        # branch below: `a/b/*.py` ⊂ `a/b/**` ⊂ `a/**`. A glob anywhere in the
        # PARENT is not proven and still fails.
        head, sep, last = pattern.rpartition("/")
        if sep and _has_glob(last) and not _has_glob(head):
            segments = head.split("/")
            while segments:
                if "/".join(segments) + "/**" in triggers:
                    return True
                segments.pop()
        return False
    # A subtree scope is startable when an ANCESTOR subtree is a trigger, for the
    # same reason: `data/smart_money/**` matches a subset of `data/**`.
    segments = pattern[: -len("/**")].split("/")
    while len(segments) > 1:
        segments.pop()
        if "/".join(segments) + "/**" in triggers:
            return True
    return False


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
        if not planner_path_exists(Path(referenced)):
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


def _decode_changed_files(raw: str | None) -> list[str] | None:
    """The ONE decoder both transports share: file bytes and env string alike.

    Two readers that agree today drift tomorrow, and a drift here is silent by
    construction — a list decoded one way and hashed the other simply refuses
    every plan.  Semantics: the token ``null`` and every malformed shape widen
    to ``None``; a JSON array of strings narrows to exactly its non-empty
    entries, in the ORDER the planner resolved them (never sorted — the hash in
    ``changed_files_digest`` pins that order). The exact empty array remains an
    empty list, distinct from ``null``/uncertainty, so an empty-diff plan can be
    consumed under the same sha256 it published.
    """
    if raw is None:
        return None
    stripped = raw.strip()
    if not stripped or stripped == "null":
        return None
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, list) or not all(
        isinstance(path, str) for path in parsed
    ):
        return None
    if not parsed:
        return []
    return [path for path in parsed if path] or None


def changed_files_digest(changed: Iterable[str] | None) -> str:
    """sha256 of a resolved changed-file list, or "" when there is no list.

    The empty string is the affirmative encoding of "the planner had no list"
    (main's baseline, every widen) and is NOT a hash of anything, so a pack can
    tell "planned full suite" apart from "planned this exact diff" without a
    second flag.  Compact separators and the RESOLVED order — sorting here would
    make two different lists hash the same and defeat the drift gate the digest
    exists to arm.
    """
    if changed is None:
        return ""
    payload = json.dumps(list(changed), separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _read_changed_files_handle(handle: str | None) -> tuple[str, list[str]]:
    """Classify the published changed-files FILE without deciding anything.

    Five states, because a pack about to refuse a plan needs to NAME the reason
    where ``resolve_changed_files`` deliberately only widens: ``absent``
    (nothing configured), ``unreadable`` (configured, but the artifact never
    landed or is not text), ``malformed`` (present and not a changed-file
    handle), ``null`` (the planner's affirmative "no list"), and ``list``
    (paths, including the exact empty array). Normalisation is
    ``_decode_changed_files``'s, exactly. A non-empty array made only of empty
    strings remains ``null``/uncertain; literal ``[]`` remains a known empty
    list because its digest differs from the planner's no-list sentinel.
    """
    if not handle:
        return "absent", []
    try:
        raw = Path(handle).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return "unreadable", []
    stripped = raw.strip()
    if not stripped:
        return "malformed", []
    if stripped == "null":
        return "null", []
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return "malformed", []
    if not isinstance(parsed, list) or not all(
        isinstance(path, str) for path in parsed
    ):
        return "malformed", []
    if not parsed:
        return "list", []
    paths = [path for path in parsed if path]
    return ("list", paths) if paths else ("null", [])


def resolve_changed_files(
    changed_from: str | None,
    *,
    explicit_json: str | None = None,
    explicit_file: str | Path | None = None,
) -> list[str] | None:
    """Prefer the planner's file list so packs can shallow-checkout.

    Source order, most authoritative first: ``explicit_file`` →
    ``CI_CHANGED_FILES_FILE`` → ``explicit_json`` → ``CI_CHANGED_FILES_JSON`` →
    ``git diff``.  The FILE is the production transport (2026-08-14, run
    31775693780): the same list rode a job output into every pack step's
    ``env:`` at 350,264 bytes, past Linux's 131,072-byte MAX_ARG_STRLEN, and
    every pack died at launch with "Argument list too long" before a single test
    ran.  A path is a few dozen bytes whatever the diff's size; the list it names
    is an artifact.  The env string stays supported so an old runner, a local
    reproduction, or a hand-driven invocation keeps working.

    Packs must not re-run ``git diff`` against a fetch-depth-1 tree — that miss
    would fail-safe-widen every PR to the full suite and undo the
    shallow-checkout saving.  An unset/empty value still falls back to ``git
    diff`` so a local ``--changed-from`` invocation works.

    Malformed input widens (None), never narrows — for BOTH transports, and a
    configured-but-unreadable file included: an unreadable handle is exactly the
    doubt this law is written for, and falling through to git behind it would
    answer a stale question (the base SHA a pack is handed can be many hours and
    thousands of paths behind main).  A pack that was PINNED to a published plan
    does not merely widen on that doubt, it refuses: the widened list hashes to
    something else, so ``--expect-plan-sha`` fires.  See ``main``.
    """
    handle = (
        explicit_file
        if explicit_file is not None
        else os.environ.get("CI_CHANGED_FILES_FILE")
    )
    if handle:
        try:
            raw_file = Path(handle).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None
        return _decode_changed_files(raw_file)
    raw = explicit_json if explicit_json is not None else os.environ.get(
        "CI_CHANGED_FILES_JSON"
    )
    if raw is not None and raw != "":
        return _decode_changed_files(raw)
    if changed_from:
        return changed_files(changed_from)
    return None


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

        A traversal that reports ``suffixes=`` has narrowed itself: its glob
        pattern is literal, so it can only ever enumerate those filename kinds no
        matter which directory it walks. The root claim stands; the file kinds it
        can carry are intersected with it (see ``narrow_to_suffixes``).
        """
        fallbacks: set[str] = set()
        for item in ambiguities:
            head, _, suffix_field = item.partition(" suffixes=")
            suffixes = tuple(part for part in suffix_field.split(",") if part)
            roots = _ambiguity_roots(head)
            if roots is None:
                return None
            fallbacks.update(narrow_to_suffixes(roots, suffixes))
        return tuple(sorted(fallbacks))

    def infer_job_paths(
        definition: dict[str, Any],
    ) -> tuple[set[str], set[str]] | None:
        """(owned, fallback) or None when the job cannot be scoped at all.

        ``owned`` carries NAMED evidence: closure files, literal references,
        and any fallback of a job whose commands demonstrably mention
        markdown. ``fallback`` carries OPAQUE widening only — subprocess and
        traversal root claims — and is the tier a narrative file can never
        select (see ``LegacyJob.fallback_paths``).
        """
        commands = [
            str(step["run"])
            for step in definition.get("steps", [])
            if isinstance(step, dict)
            and "run" in step
            and "pip install" not in str(step["run"])
        ]
        owned: set[str] = set()
        fallback: set[str] = set()
        named_any = False
        named_pytest = False
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
                fallback.update(exclude_peer_test_ownership(fallbacks))
                named_pytest = True
                named_any = True

            for reference in SCOPE_REFERENCE_RE.findall(command):
                rel = reference.split("::", 1)[0].rstrip(".,;:'\")")
                path = Path(rel)
                if not planner_path_is_file(path):
                    continue
                owned.add(rel)
                named_any = True
                if rel.endswith(".py"):
                    closure = suite_dependency_closure(rel)
                    fallbacks = ambiguity_fallbacks(closure.ambiguities)
                    if fallbacks is None:
                        return None
                    owned.update(closure.files)
                    fallback.update(fallbacks)
        if not named_any:
            return None
        if named_pytest:
            # Script-path fallbacks in the same job re-introduced ``*`` / ``tests/**``
            # after the named-suite filter (marketing-engine still matched a prophet
            # test via ``tests/**``). Strip catch-alls from the FINAL set whenever
            # the job named specific pytest files.
            fallback = set(exclude_peer_test_ownership(fallback))
        # A job whose commands mention markdown reads narrative files on
        # purpose (doc linters, handoff censuses). ALL its opaque claims keep
        # matching `.md` edits via the owned tier.
        if MD_COMMAND_RE.search("\n".join(commands)):
            owned.update(fallback)
            fallback = set()
        fallback -= owned
        return (owned, fallback) if owned else None

    inferred: list[LegacyJob] = []
    scoped = 0
    declared = 0
    for job in jobs:
        if job.exclusive:
            # The curated tier: the manifest's own coverage-audited `paths:`
            # ARE the scope. Inference is skipped entirely, so fallback smear
            # from an opaque edge deep in a suite's closure cannot re-widen a
            # job the operator deliberately narrowed.
            inferred.append(replace(job, fallback_paths=()))
            declared += 1
            continue
        result = infer_job_paths(job.definition)
        if result:
            owned, fallback = result
            inferred.append(
                replace(
                    job,
                    paths=tuple(sorted(set(job.paths) | owned)),
                    fallback_paths=tuple(sorted(fallback)),
                )
            )
            scoped += 1
        else:
            inferred.append(replace(job, paths=(), fallback_paths=()))
    summary = f"derived scopes for {scoped}/{len(inferred)} jobs"
    if declared:
        summary += f"; {declared} declared exclusive"
    return inferred, summary


def _job_diff_match(job: LegacyJob, changed: Iterable[str]) -> tuple[str, str] | None:
    """The first (changed path, tier) that selects this job, or None.

    Tier order is deliberate: a NAMED owner (`declared` for exclusive jobs,
    `owned` for closure/literal evidence) always outranks an opaque `fallback`
    claim in the explanation, and the fallback tier never fires for a
    narrative file.
    """
    for path in changed:
        if _matches_any(job.paths, path):
            return path, ("declared" if job.exclusive else "owned")
    for path in changed:
        if _matches_any(PASSIVE_UNOWNED_PATTERNS, path):
            continue
        if _matches_any(job.fallback_paths, path):
            return path, "fallback"
    return None


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
    scoped_jobs = [job for job in jobs if job.is_scoped]
    unowned = [
        path for path in changed
        if not any(_job_diff_match(job, [path]) for job in scoped_jobs)
        and not _matches_any(PASSIVE_UNOWNED_PATTERNS, path)
    ]
    selected = [
        job
        for job in jobs
        if not job.is_scoped or _job_diff_match(job, changed)
    ]
    unscoped = sum(1 for job in jobs if not job.is_scoped)
    reason = (
        f"scoped to {len(changed)} changed file(s): {len(selected)}/{len(jobs)} jobs "
        f"({unscoped} unscoped always-on, "
        f"{len(selected) - unscoped} scoped matches)"
    )
    if unowned:
        reason += (
            f"; {len(unowned)} unowned path(s) did not widen "
            f"({unowned[0]})"
        )
    return selected, reason


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


def load_legacy_jobs(path: Path, *, gate: str | None = None) -> list[LegacyJob]:
    """Load and fail-closed validate every job in the legacy manifest.

    PACK_JOB_ID is still ignored when present so small historical test fixtures
    remain valid; the production manifest intentionally contains no pack job.

    ``gate`` (optional, one of ``GATE_VALUES``) filters the returned jobs to
    that ``LegacyJob.gate`` value. Filtering happens here — the single load
    choke point — so every caller (plan-only, plan-json execution, and the
    unpinned fallback) sees an identically filtered manifest before any
    partition/weight arithmetic runs. ``None`` (the default) returns every
    job, unchanged from before this parameter existed.
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
            if has_uses:
                try:
                    _provided_action_spec(step)
                except ManifestError as exc:
                    findings.append(f"{step_prefix} {exc}")
            elif "with" in step:
                findings.append(f"{step_prefix} run step must not declare with")
            if has_uses and "proof_id" in step:
                findings.append(
                    f"{step_prefix} is infrastructure and must not declare proof_id"
                )
            if has_run and _is_dependency_step(step) and "proof_id" in step:
                findings.append(
                    f"{step_prefix} is dependency infrastructure and must not "
                    "declare proof_id"
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

        # `scope: exclusive` is the CURATED tier: the declared `paths:` above
        # REPLACE inference for this job instead of being unioned under it.
        # The coverage audit just ran and is FATAL here like any other finding,
        # so an exclusive job that fails to cover a file its own commands name
        # cannot load — mis-declaring narrow is a loud manifest error, not a
        # silent false green. An exclusive job with no paths would be a job
        # that never runs on any pull request; refuse that outright.
        raw_scope_mode = raw_definition.get("scope")
        if raw_scope_mode not in (None, "exclusive"):
            findings.append(
                f"{prefix} scope must be the literal 'exclusive' when present"
            )
        exclusive = raw_scope_mode == "exclusive"
        if exclusive and not scope:
            findings.append(
                f"{prefix} declares scope: exclusive but no paths — an "
                "exclusive job with no declared surface would never run on "
                "any pull request"
            )

        # Absent defaults to "code": an undeclared job STAYS a merge
        # precondition — nothing can leave the merge gate silently. An invalid
        # value is fatal. The real manifest is additionally required to declare
        # the field on every job (tests/test_ci_pack.py), so the default only
        # serves synthetic fixtures.
        raw_gate = raw_definition.get("gate", "code")
        if raw_gate not in GATE_VALUES:
            findings.append(
                f"{prefix} gate must be one of {'/'.join(GATE_VALUES)} when "
                f"present, got {raw_gate!r}"
            )
            raw_gate = "code"

        job = LegacyJob(
            job_id=str(job_id),
            definition=raw_definition,
            ordinal=ordinal,
            weight=_job_weight(str(job_id), raw_definition),
            paths=scope,
            exclusive=exclusive,
            gate=str(raw_gate),
        )
        try:
            semantic_step_specs(job)
        except ManifestError as exc:
            findings.append(str(exc))
        legacy.append(job)

    if findings:
        raise ManifestError("\n".join(findings))
    if not legacy:
        raise ManifestError("workflow contains no legacy jobs")
    if gate is not None:
        legacy = [job for job in legacy if job.gate == gate]
    return legacy


def inferred_as_if_not_exclusive(manifest_path: Path) -> dict[str, LegacyJob]:
    """What inference WOULD derive for every job, exclusivity aside.

    Canonical home for a computation that used to live only as a local helper in
    ``tests/test_ci_pack.py``. Two callers now share this single copy: that test
    (``test_curated_exclusive_scopes_cover_their_own_import_closure`` and its
    siblings) and ``scripts/check_contract_delta.py``'s PR-vs-base contract-delta
    gate. Neither may keep a private re-derivation — see
    ``curated_exclusive_closure_findings`` below for why that matters.
    """
    jobs = [replace(job, exclusive=False) for job in load_legacy_jobs(manifest_path)]
    inferred, _note = infer_job_scopes(jobs)
    return {job.job_id: job for job in inferred}


def curated_exclusive_closure_findings(manifest_path: Path) -> dict[str, tuple[str, ...]]:
    """``{job_id: uncovered closure paths}`` for every ``scope: exclusive`` job.

    This IS ``tests/test_ci_pack.py::
    test_curated_exclusive_scopes_cover_their_own_import_closure``'s check, factored
    out so that test and ``scripts/check_contract_delta.py`` import one copy instead
    of drifting apart. ``scope: exclusive`` REPLACES inference, so the declared
    ``paths:`` are the whole scope; a closure file matched by no declared pattern is
    a job that silently stops running when its own dependency changes.

    Raises ``ValueError`` if a curated job derives no closure at all (curation
    cannot be checked) — the same hard-fail posture the test's own ``assert``
    took before this factoring, preserved so behavior does not change.
    """
    would_infer = inferred_as_if_not_exclusive(manifest_path)
    declared = {job.job_id: job for job in load_legacy_jobs(manifest_path) if job.exclusive}
    misses: dict[str, tuple[str, ...]] = {}
    for job_id, job in sorted(declared.items()):
        closure = [p for p in would_infer[job_id].paths if "*" not in p]
        if not closure:
            raise ValueError(f"{job_id} derives no closure — curation cannot be checked")
        uncovered = tuple(p for p in closure if not _matches_any(job.paths, p))
        if uncovered:
            misses[job_id] = uncovered
    return misses


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
# computed ONCE by `build_plan`, published by `ci-plan` as a hashed artifact,
# and CONSUMED by each pack (`--plan-json`). Packs still load and validate the
# current manifest's semantic contracts, but never re-run inference or decide a
# partition. Twelve runners silently disagreeing about the suite becomes one
# loud plan-identity error instead.
#
# What this does NOT buy at this revision, measured 2026-08-11 against the real
# 180-job manifest: it saved ZERO packs THEN.  Scope inference derived scopes for
# 179/180 jobs, yet every realistic diff still selected enough of them to fill
# all twelve packs because named pytest suites inherited ``tests/**`` and ``*``
# from opaque traversals inside those suites.  That catch-all is now stripped
# (``exclude_peer_test_ownership``); a one-test-file PR must no longer emit
# twelve packs.  The empty-pack machinery is load-bearing for that narrowing.
#
# Historical v1 packs recomputed the plan to check one output hash, so the
# planner added a thirteenth inference pass. Semantic v2 cannot do that: the
# plan now contains the complete expected `(logical_job_id, proof_id)` surface,
# execution digests, and exact tree/head/base provenance. Recomputing selection
# would create a second proof universe. Artifact consumption is therefore a
# correctness requirement; avoiding the repeated inference is incidental.
#
# What plan-once buys at this revision is therefore exactly two things, both
# correctness: runners cannot silently disagree about what the suite IS, and
# `ci-gate` receives one complete expected proof surface even when scoped CI
# legitimately launches only a subset of ci-pack-0..11.
# ---------------------------------------------------------------------------

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
    workflow_run_id: str
    workflow: str
    event: str
    role: str
    tested_tree_sha: str
    subject_head_sha: str
    base_sha: str
    authority_changed: bool
    semantic_jobs: tuple[SemanticJobSpec, ...]
    plan_sha256: str
    # Neither serialised nor hashed.  `scoped_jobs` carries the RESOLVED jobs so
    # main() executes the manifest objects named by the consumed plan instead of
    # inferring scopes a second time. `predicted_job_ids`
    # carries what select_jobs chose BEFORE a shadow/off override widened
    # `eligible_job_ids` back to the full manifest — that difference is the
    # entire output of the shadow lane.  Both are compare=False so two plans
    # built from the same inputs stay equal and the hash remains the identity.
    scoped_jobs: tuple[LegacyJob, ...] = field(default=(), compare=False, repr=False)
    predicted_job_ids: tuple[str, ...] = field(default=(), compare=False, repr=False)
    # The resolved diff. Packs receive it so they can shallow-checkout instead of
    # re-running `git diff` against a fetch-depth-0 history. As a run ARTIFACT
    # since 2026-08-14, never a job output: an output becomes an `env:` string in
    # the consuming job, and PR #5578's 350,264-byte list met execve's
    # 131,072-byte MAX_ARG_STRLEN and killed all twelve packs at launch (run
    # 31775693780).
    changed_paths: tuple[str, ...] | None = field(
        default=None, compare=False, repr=False
    )
    # sha256 of the RESOLVED list (see `changed_files_digest`) and its length.
    # `compare=False` because `changed_paths` already is; the digest is a
    # function of it and adds no distinguishing power to plan EQUALITY. It DOES
    # enter `plan_hash_payload`, and that is the whole repair: the list now
    # travels out of band, so without a bounded pin inside the decision identity
    # a swapped or truncated artifact would silently re-scope the guards that
    # read it. A pack recomputing from the wrong file recomputes a different
    # plan sha, and the consuming pack's artifact/digest check refuses.
    changed_files_sha256: str = field(default="", compare=False, repr=False)
    changed_files_count: int = field(default=0, compare=False, repr=False)

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
            "workflow_run_id": self.workflow_run_id,
            "workflow": self.workflow,
            "event": self.event,
            "role": self.role,
            "tested_tree_sha": self.tested_tree_sha,
            "subject_head_sha": self.subject_head_sha,
            "base_sha": self.base_sha,
            "authority_changed": self.authority_changed,
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
            "semantic_jobs": [job.plan_dict() for job in self.semantic_jobs],
            "plan_sha256": self.plan_sha256,
            # The DIGEST and the COUNT, never the list. This document is printed
            # as one machine line in the planner's log, so an unbounded array
            # here would simply move the 350,264 bytes from the pack step's
            # `env:` into a log line nobody can read. The list itself is the
            # `ci-changed-files` artifact.
            "changed_files_sha256": self.changed_files_sha256,
            "changed_files_count": self.changed_files_count,
        }


def plan_hash_payload(
    *,
    workflow_run_id: str,
    workflow: str,
    event: str,
    role: str,
    tested_tree_sha: str,
    subject_head_sha: str,
    base_sha: str,
    authority_changed: bool,
    changed_from: str | None,
    scope_mode: str,
    changed_files_sha256: str,
    pack_count: int,
    eligible_job_ids: Iterable[str],
    pack_jobs: Iterable[Iterable[str]],
    pack_weights: Iterable[int],
    semantic_jobs: Iterable[SemanticJobSpec | Mapping[str, Any]],
) -> dict[str, Any]:
    """Exactly what a pack must agree with ci-plan about, and nothing else.

    Prose (`reason`, `scope_summary`) is EXCLUDED on purpose: rewording a
    diagnostic must never be able to make a pack refuse a plan that selects the
    identical jobs.  Derived values (non-empty indices, skipped ids, counts) are
    excluded because they are functions of the keys below — hashing them only
    adds ways for two identical decisions to disagree.  The matrix MODE is
    excluded too: it is an emission policy, so ci-plan and ci-pack agree on the
    hash whether or not every pack was launched.

    `changed_files_sha256` is IN, next to `changed_from` and for the same reason
    (2026-08-14, run 31775693780): the base pins which commit the diff was taken
    against, this pins the diff itself.  It is what makes the out-of-band
    transport safe.  The list left the job outputs because a 350,264-byte
    `env:` string cannot cross execve, and an artifact is reachable by anything
    that can write a file — so a consuming pack hashes the downloaded list and
    refuses a swapped, truncated, or missing artifact before one semantic step
    runs. Without this key it could quietly run guards over somebody else's
    diff under a valid-looking plan.
    """
    return {
        "schema": PLAN_SCHEMA,
        "workflow_run_id": workflow_run_id,
        "workflow": workflow,
        "event": event,
        "role": role,
        "tested_tree_sha": tested_tree_sha,
        "subject_head_sha": subject_head_sha,
        "base_sha": base_sha,
        "authority_changed": authority_changed,
        "changed_from": changed_from,
        "scope_mode": scope_mode,
        "changed_files_sha256": changed_files_sha256,
        "pack_count": pack_count,
        # PLAN order, never sorted: partition_jobs is greedy over
        # (-weight, ordinal), so the sequence itself is load-bearing.
        "eligible_job_ids": list(eligible_job_ids),
        "pack_jobs": [list(jobs) for jobs in pack_jobs],
        "pack_weights": list(pack_weights),
        "semantic_jobs": [
            job.plan_dict() if isinstance(job, SemanticJobSpec) else dict(job)
            for job in semantic_jobs
        ],
    }


def _canonical_json(payload: object) -> str:
    """Canonical JSON — stable and type-sensitive (``true`` is not ``1``)."""
    # The shared reconciler hashes canonical UTF-8 bytes with non-ASCII text
    # preserved. Using json.dumps' default ensure_ascii=True here makes two
    # equivalent documents hash differently as soon as a proof name contains
    # Unicode — a real property of the production manifest.
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _canonical_digest(payload: dict[str, Any]) -> str:
    """Canonical JSON sha256 — identical on any machine, Python, or dict order."""
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def build_plan(
    jobs: Iterable[LegacyJob],
    changed: list[str] | None,
    *,
    changed_from: str | None,
    scope_mode: str,
    pack_count: int = 12,
    workflow_run_id: str | None = None,
    workflow: str | None = None,
    event: str | None = None,
    role: str | None = None,
    tested_tree_sha: str | None = None,
    subject_head_sha: str | None = None,
    base_sha: str | None = None,
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
    # Hashed from the list the plan was actually built on, so the pin and the
    # decision cannot describe different diffs. `changed is None` is the
    # full-suite case and hashes to "" — an affirmative "no list", not a hash of
    # the empty list.
    changed_files_sha256 = changed_files_digest(changed)
    tested_tree_sha = (
        tested_tree_sha
        or os.environ.get("CI_TESTED_TREE_SHA")
        or os.environ.get("GITHUB_SHA")
        or "unbound-tested-tree"
    )
    subject_head_sha = (
        subject_head_sha
        or os.environ.get("CI_SUBJECT_HEAD_SHA")
        or tested_tree_sha
    )
    base_sha = (
        base_sha
        or os.environ.get("CI_BASE_SHA")
        or changed_from
        or tested_tree_sha
    )
    event = event or os.environ.get("GITHUB_EVENT_NAME") or (
        "pull_request" if changed_from is not None else "workflow_dispatch"
    )
    role = role or os.environ.get("CI_SEMANTIC_ROLE") or (
        "pr_head" if event == "pull_request" else "main"
    )
    # `workflow` is resolved HERE, before the role/event validation below, so
    # the narrow main-owned diagnostic admission can be evaluated in the same gate instead of
    # a second, later, easy-to-miss check. Moving this resolution earlier does
    # not change what any OTHER caller gets: it was unconditional before too.
    workflow = workflow or os.environ.get("GITHUB_WORKFLOW") or "ci"
    if (role, event) not in SUPPORTED_PLAN_ROLE_EVENTS and not (
        role == "pr_head"
        and event == "workflow_dispatch"
        and workflow in DIAGNOSTIC_PR_WORKFLOWS
    ):
        raise ManifestError(
            f"semantic plan role/event combination {role}/{event} is unsupported"
        )
    if role == "pr_head" and changed is None:
        raise ManifestError(
            "a PR semantic plan requires an exact changed-file inventory; "
            "planner uncertainty may widen compatibility execution but cannot "
            "mint authority_changed=false"
        )
    if role == "pr_head" and changed_from != base_sha:
        raise ManifestError("PR semantic plan changed_from must equal exact base_sha")
    if role == "main" and (
        changed_from is not None
        or tested_tree_sha != subject_head_sha
        or tested_tree_sha != base_sha
    ):
        raise ManifestError(
            "main semantic plan requires one tree/head/base SHA and no changed_from"
        )
    workflow_run_id = (
        workflow_run_id or os.environ.get("GITHUB_RUN_ID") or "local"
    )
    try:
        authority_changed = bool(
            role == "pr_head"
            and changed is not None
            and any(is_ci_authority_path(path) for path in changed)
        )
    except AuthorityPathError as exc:
        raise ManifestError(f"changed-file authority path is invalid: {exc}") from exc
    job_to_pack = {
        job_id: pack_index
        for pack_index, job_ids in enumerate(pack_jobs)
        for job_id in job_ids
    }
    semantic_jobs = tuple(
        SemanticJobSpec(
            logical_job_id=job.job_id,
            pack_index=job_to_pack[job.job_id],
            job_exec_sha256=semantic_job_digest(job),
            steps=semantic_step_specs(job),
        )
        for job in eligible
    )
    hash_payload = plan_hash_payload(
        workflow_run_id=workflow_run_id,
        workflow=workflow,
        event=event,
        role=role,
        tested_tree_sha=tested_tree_sha,
        subject_head_sha=subject_head_sha,
        base_sha=base_sha,
        authority_changed=authority_changed,
        changed_from=changed_from,
        scope_mode=scope_mode,
        changed_files_sha256=changed_files_sha256,
        pack_count=pack_count,
        eligible_job_ids=eligible_job_ids,
        pack_jobs=pack_jobs,
        pack_weights=pack_weights,
        semantic_jobs=semantic_jobs,
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
        workflow_run_id=workflow_run_id,
        workflow=workflow,
        event=event,
        role=role,
        tested_tree_sha=tested_tree_sha,
        subject_head_sha=subject_head_sha,
        base_sha=base_sha,
        authority_changed=authority_changed,
        semantic_jobs=semantic_jobs,
        plan_sha256=_canonical_digest(hash_payload),
        scoped_jobs=tuple(jobs),
        predicted_job_ids=predicted_job_ids,
        changed_paths=tuple(changed) if changed is not None else None,
        changed_files_sha256=changed_files_sha256,
        changed_files_count=len(changed) if changed is not None else 0,
    )


def plan_from_workflow(
    workflow: Path,
    *,
    changed_from: str | None,
    scope_mode: str,
    pack_count: int = 12,
    changed_files_file: str | Path | None = None,
    tracked_paths_file: str | Path | None = None,
    workflow_run_id: str | None = None,
    workflow_name: str | None = None,
    event: str | None = None,
    role: str | None = None,
    tested_tree_sha: str | None = None,
    subject_head_sha: str | None = None,
    base_sha: str | None = None,
    gate: str | None = None,
) -> CIPackPlan:
    """Load the manifest, resolve the diff, and plan — the whole decision."""
    if tracked_paths_file is not None and tested_tree_sha is None:
        raise RuntimeError(
            "--tracked-paths-file requires --tested-tree-sha so repository "
            "existence cannot drift to a different checkout"
        )
    inventory = (
        planner_tracked_path_inventory(
            Path(tracked_paths_file), tested_tree_sha or ""
        )
        if tracked_paths_file is not None
        else contextlib.nullcontext()
    )
    with inventory:
        legacy = load_legacy_jobs(workflow, gate=gate)
        changed = resolve_changed_files(
            changed_from, explicit_file=changed_files_file
        )
        return build_plan(
            legacy,
            changed,
            changed_from=changed_from,
            scope_mode=scope_mode,
            pack_count=pack_count,
            workflow_run_id=workflow_run_id,
            workflow=workflow_name,
            event=event,
            role=role,
            tested_tree_sha=tested_tree_sha,
            subject_head_sha=subject_head_sha,
            base_sha=base_sha,
        )


def _load_json_object(path: Path, *, max_bytes: int = 5_000_000) -> dict[str, Any]:
    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        document: dict[str, Any] = {}
        for key, value in pairs:
            if key in document:
                raise ManifestError(
                    f"authoritative JSON contains duplicate key {key!r}"
                )
            document[key] = value
        return document

    try:
        size = path.stat().st_size
        if size > max_bytes:
            raise ManifestError(f"{path} is {size} bytes (limit {max_bytes})")
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=reject_duplicate_keys,
        )
    except ManifestError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ManifestError(f"cannot load authoritative plan {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ManifestError(f"authoritative plan {path} must be a JSON object")
    return payload


def load_authoritative_plan(
    path: Path,
    *,
    workflow: Path,
    changed_files_file: str | Path | None = None,
    expect_plan_sha: str | None = None,
    expect_tested_tree_sha: str | None = None,
    expect_subject_head_sha: str | None = None,
    expect_base_sha: str | None = None,
    gate: str | None = None,
) -> CIPackPlan:
    """Load the planner artifact without recomputing scope or partition.

    The manifest is still validated and its semantic contracts must byte-for-
    byte agree with the plan.  What is forbidden here is re-deciding selection:
    the planner's selected jobs and pack assignment are the sole authority.

    ``gate`` must match what produced the published plan: it narrows the
    manifest used for the consistency/semantic checks below to the same set
    the planner selected from, exactly as ``plan_from_workflow`` does for the
    unpinned path.
    """
    document = _load_json_object(path)
    if document.get("schema") != PLAN_SCHEMA:
        raise ManifestError(
            f"authoritative plan schema must be {PLAN_SCHEMA!r}, got "
            f"{document.get('schema')!r}"
        )

    def required_text(key: str) -> str:
        value = document.get(key)
        if not isinstance(value, str) or not value:
            raise ManifestError(f"authoritative plan {key} must be non-empty text")
        return value

    published_sha = required_text("plan_sha256")
    if not re.fullmatch(r"[0-9a-f]{64}", published_sha):
        raise ManifestError("authoritative plan plan_sha256 must be lowercase hex")
    identities = {
        "tested_tree_sha": required_text("tested_tree_sha"),
        "subject_head_sha": required_text("subject_head_sha"),
        "base_sha": required_text("base_sha"),
    }
    for key, value in identities.items():
        if not re.fullmatch(r"[0-9a-f]{40}", value):
            raise ManifestError(
                f"authoritative plan {key} must be an exact 40-hex commit SHA"
            )
    expectations = {
        "plan_sha256": expect_plan_sha,
        "tested_tree_sha": expect_tested_tree_sha,
        "subject_head_sha": expect_subject_head_sha,
        "base_sha": expect_base_sha,
    }
    actuals = {"plan_sha256": published_sha, **identities}
    for key, expected in expectations.items():
        if expected and actuals[key] != expected:
            raise ManifestError(
                f"authoritative plan {key} is {actuals[key]!r}, expected {expected!r}"
            )

    raw_packs = document.get("packs")
    if not isinstance(raw_packs, list) or not raw_packs:
        raise ManifestError("authoritative plan packs must be a non-empty list")
    pack_jobs: list[tuple[str, ...]] = []
    pack_weights: list[int] = []
    for index, raw_pack in enumerate(raw_packs):
        if (
            not isinstance(raw_pack, dict)
            or type(raw_pack.get("index")) is not int
            or raw_pack.get("index") != index
        ):
            raise ManifestError(f"authoritative plan pack {index} is malformed")
        raw_jobs = raw_pack.get("jobs")
        weight = raw_pack.get("weight")
        if (
            not isinstance(raw_jobs, list)
            or any(not isinstance(item, str) or not item for item in raw_jobs)
            or type(weight) is not int
            or weight < 0
        ):
            raise ManifestError(f"authoritative plan pack {index} is malformed")
        pack_jobs.append(tuple(raw_jobs))
        pack_weights.append(weight)
    flattened = [job_id for pack in pack_jobs for job_id in pack]
    if len(flattened) != len(set(flattened)):
        raise ManifestError("authoritative plan assigns a logical job more than once")
    eligible = document.get("eligible_jobs")
    skipped = document.get("skipped_jobs")
    if not isinstance(eligible, list) or eligible != flattened:
        # Planner order is manifest order, whereas packs are execution bins.
        # Compare membership below and preserve the planner's explicit order.
        if (
            not isinstance(eligible, list)
            or any(not isinstance(item, str) or not item for item in eligible)
            or set(eligible) != set(flattened)
            or len(eligible) != len(flattened)
        ):
            raise ManifestError(
                "authoritative plan eligible_jobs does not equal pack membership"
            )
    if (
        not isinstance(skipped, list)
        or any(not isinstance(item, str) or not item for item in skipped)
        or len(skipped) != len(set(skipped))
        or len(eligible) != len(set(eligible))
        or set(eligible) & set(skipped)
    ):
        raise ManifestError("authoritative plan skipped_jobs is malformed")

    all_jobs = load_legacy_jobs(workflow, gate=gate)
    by_id = {job.job_id: job for job in all_jobs}
    manifest_ids = set(by_id)
    if set(eligible) | set(skipped) != manifest_ids:
        raise ManifestError(
            "authoritative plan selected/skipped inventory does not equal manifest"
        )
    pack_by_job = {
        job_id: pack_index
        for pack_index, job_ids in enumerate(pack_jobs)
        for job_id in job_ids
    }
    semantic_jobs = tuple(
        SemanticJobSpec(
            logical_job_id=job_id,
            pack_index=pack_by_job[job_id],
            job_exec_sha256=semantic_job_digest(by_id[job_id]),
            steps=semantic_step_specs(by_id[job_id]),
        )
        for job_id in eligible
    )
    published_semantic = document.get("semantic_jobs")
    actual_semantic = [job.plan_dict() for job in semantic_jobs]
    if _canonical_json(published_semantic) != _canonical_json(actual_semantic):
        raise ManifestError(
            "authoritative plan semantic inventory does not match this manifest"
        )

    changed_from = document.get("changed_from")
    if changed_from is not None and not isinstance(changed_from, str):
        raise ManifestError("authoritative plan changed_from must be text or null")
    role = required_text("role")
    if role not in {"pr_head", "main"}:
        raise ManifestError("authoritative plan role must be pr_head or main")
    event = required_text("event")
    # `workflow` is read HERE, before the role/event validation below, so the
    # same narrow main-owned diagnostic admission build_plan() grants can be
    # evaluated in this reader too, rather than only when the published
    # `workflow` field is reached later (still needed for the hash payload).
    workflow = required_text("workflow")
    if (role, event) not in SUPPORTED_PLAN_ROLE_EVENTS and not (
        role == "pr_head"
        and event == "workflow_dispatch"
        and workflow in DIAGNOSTIC_PR_WORKFLOWS
    ):
        raise ManifestError(
            f"authoritative plan role/event combination {role}/{event} is unsupported"
        )
    if role == "pr_head" and changed_from != identities["base_sha"]:
        raise ManifestError(
            "PR authoritative plan must diff and replay the same exact base SHA"
        )
    if role == "main" and (
        changed_from is not None
        or identities["tested_tree_sha"] != identities["subject_head_sha"]
        or identities["tested_tree_sha"] != identities["base_sha"]
    ):
        raise ManifestError(
            "main authoritative plan requires one identical tree/head/base SHA "
            "and no changed_from"
        )
    scope_mode = required_text("scope_mode")
    if scope_mode not in {"active", "shadow", "off"}:
        raise ManifestError("authoritative plan scope_mode is unsupported")
    changed_files_sha256 = document.get("changed_files_sha256")
    changed_files_count = document.get("changed_files_count")
    authority_changed = document.get("authority_changed")
    if (
        not isinstance(changed_files_sha256, str)
        or (
            changed_files_sha256 != ""
            and not re.fullmatch(r"[0-9a-f]{64}", changed_files_sha256)
        )
        or type(changed_files_count) is not int
        or changed_files_count < 0
    ):
        raise ManifestError("authoritative plan changed-file binding is malformed")
    if type(authority_changed) is not bool:
        raise ManifestError("authoritative plan authority_changed must be boolean")

    payload = plan_hash_payload(
        workflow_run_id=required_text("workflow_run_id"),
        workflow=workflow,
        event=event,
        role=role,
        tested_tree_sha=identities["tested_tree_sha"],
        subject_head_sha=identities["subject_head_sha"],
        base_sha=identities["base_sha"],
        authority_changed=authority_changed,
        changed_from=changed_from,
        scope_mode=scope_mode,
        changed_files_sha256=changed_files_sha256,
        pack_count=len(pack_jobs),
        eligible_job_ids=eligible,
        pack_jobs=pack_jobs,
        pack_weights=pack_weights,
        semantic_jobs=semantic_jobs,
    )
    computed_sha = _canonical_digest(payload)
    if computed_sha != published_sha:
        raise ManifestError(
            f"authoritative plan digest is {published_sha}, computed {computed_sha}"
        )

    state, changed = _read_changed_files_handle(changed_files_file)
    if changed_files_file is not None:
        if state not in {"list", "null"}:
            raise ManifestError(
                f"changed-file artifact is {state}; cannot prove planner input"
            )
        resolved_changed = changed if state == "list" else None
        if changed_files_digest(resolved_changed) != changed_files_sha256:
            raise ManifestError("changed-file artifact digest disagrees with plan")
        if len(changed) != changed_files_count:
            raise ManifestError("changed-file artifact count disagrees with plan")
        try:
            computed_authority_changed = bool(
                role == "pr_head"
                and resolved_changed is not None
                and any(is_ci_authority_path(item) for item in resolved_changed)
            )
        except AuthorityPathError as exc:
            raise ManifestError(f"changed-file authority path is invalid: {exc}") from exc
        if computed_authority_changed != authority_changed:
            raise ManifestError(
                "changed-file artifact authority classification disagrees with plan"
            )
    else:
        resolved_changed = None

    plan = CIPackPlan(
        schema=PLAN_SCHEMA,
        changed_from=changed_from,
        scope_mode=scope_mode,
        reason=required_text("reason"),
        scope_summary=required_text("scope_summary"),
        legacy_job_count=len(all_jobs),
        eligible_job_ids=tuple(eligible),
        skipped_job_ids=tuple(skipped),
        pack_jobs=tuple(pack_jobs),
        pack_weights=tuple(pack_weights),
        nonempty_pack_indices=tuple(
            index for index, job_ids in enumerate(pack_jobs) if job_ids
        ),
        workflow_run_id=required_text("workflow_run_id"),
        workflow=workflow,
        event=event,
        role=role,
        tested_tree_sha=identities["tested_tree_sha"],
        subject_head_sha=identities["subject_head_sha"],
        base_sha=identities["base_sha"],
        authority_changed=authority_changed,
        semantic_jobs=semantic_jobs,
        plan_sha256=published_sha,
        scoped_jobs=tuple(all_jobs),
        predicted_job_ids=tuple(eligible),
        changed_paths=(
            tuple(resolved_changed) if resolved_changed is not None else None
        ),
        changed_files_sha256=changed_files_sha256,
        changed_files_count=changed_files_count,
    )
    if _canonical_json(plan.to_dict()) != _canonical_json(document):
        raise ManifestError(
            "authoritative plan contains inconsistent derived fields or unknown keys"
        )
    return plan


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
    changed_files_sha256: str = "",
    changed_files_count: int = 0,
) -> None:
    """Append the ci-plan outputs to a `$GITHUB_OUTPUT` file.

    `name=value` cannot carry a newline and `reason` is free prose (a manifest
    error message reaches it verbatim on the fallback path), so every value uses
    the heredoc form.  The delimiter is derived from the plan hash: it cannot
    appear in compact JSON, in "true"/"false", in a hexdigest, or in prose about
    job counts and paths.

    NO OUTPUT HERE MAY BE UNBOUNDED (2026-08-14, run 31775693780).  A job output
    becomes an `env:` string in the consuming job, and Linux caps a SINGLE env
    string at MAX_ARG_STRLEN = 131,072 bytes; the retired `changed_files` output
    measured 350,264 bytes on PR #5578 and killed all twelve packs at launch
    with "Argument list too long" before one test ran.  Its replacement is the
    64-character digest below — the same value `plan_hash_payload` hashes, so
    the list travels as an artifact while its identity still rides the trusted
    output channel.  Everything else is a matrix over twelve indices, a boolean,
    a hexdigest, a decimal count, or one line of prose.
    """
    delimiter = "ci_plan_" + (plan_sha[:32] or "planner_fallback")
    payload = "".join(
        f"{name}<<{delimiter}\n{value}\n{delimiter}\n"
        for name, value in (
            ("matrix", json.dumps(matrix, sort_keys=True, separators=(",", ":"))),
            ("has_work", "true" if has_work else "false"),
            ("plan_sha", plan_sha),
            ("reason", reason),
            ("changed_files_sha256", changed_files_sha256),
            ("changed_files_count", str(changed_files_count)),
        )
    )
    # ONE append, never five: a failure between writes would leave GitHub parsing
    # a half-declared output, and the fallback path would then append a second,
    # contradicting `matrix` behind it.
    with path.open("a", encoding="utf-8") as handle:
        handle.write(payload)


def _write_changed_files_artifact(
    destination: str | Path, changed: Iterable[str] | None
) -> Path:
    """Write the resolved list where the packs will download it from.

    THIS FILE IS THE TRANSPORT (2026-08-14, run 31775693780). The same list rode
    a job output into every pack step's `env:` at 350,264 bytes, past execve's
    131,072-byte MAX_ARG_STRLEN, and all twelve packs died at launch before one
    test ran. A path is a few dozen bytes however large the diff.

    The token `null` is written for a full-suite plan rather than nothing at all:
    an affirmative "no list" is what stops a pack's children falling back to
    `git diff` against a fetch-depth-1 tree that cannot see `origin/main...HEAD`
    (#5556/#5519/#5499). Parent directories are created here so the ci.yml step
    stays a single folded scalar — a `#`-free, uniform-indent `>-` block is a
    law in this workflow (see the pack step's comment), and prefixing a `mkdir`
    would force it into a multi-line literal.
    """
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        "null" if changed is None else json.dumps(list(changed), separators=(",", ":"))
    )
    path.write_text(payload + "\n", encoding="utf-8")
    return path


def _atomic_write_json(
    path: Path, payload: Mapping[str, Any], *, indent: int | None = None
) -> None:
    """Publish an authority artifact atomically; partial JSON is never visible."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    encoded = (
        json.dumps(payload, indent=indent)
        if indent is not None
        else json.dumps(payload, sort_keys=True, separators=(",", ":"))
    )
    try:
        temporary.write_text(encoded + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()


def _emit_plan_artifacts(args: argparse.Namespace, plan: CIPackPlan) -> None:
    """Publish the plan in whichever forms the caller asked for."""
    if args.emit_changed_files:
        handle = _write_changed_files_artifact(
            args.emit_changed_files, plan.changed_paths
        )
        # Bounded by construction: a count, a digest prefix, and a path. Printing
        # the payload here would put a third unbounded copy of the diff in the
        # Actions log, which is the habit that made the env string look harmless.
        print(
            f"changed-file list: {plan.changed_files_count} path(s) "
            f"sha256={plan.changed_files_sha256[:16] or '(no list)'} -> {handle}",
            flush=True,
        )
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
            _atomic_write_json(Path(args.emit_plan_json), document, indent=2)
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
        changed_files_sha256=plan.changed_files_sha256,
        changed_files_count=plan.changed_files_count,
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

    The changed-files artifact is written HERE TOO, holding the token `null`.
    ci.yml uploads it unconditionally and `if-no-files-found: error`, so a
    planner that failed before writing it would red the planner itself rather
    than the manifest defect it was trying to report — and the packs would then
    download nothing and hand their child guards an absent handle, which
    licenses a `git diff` a depth-1 pack cannot answer. `null` is the honest
    value: this path widened to the full suite, so there is no list.
    """
    if args.emit_changed_files:
        _write_changed_files_artifact(args.emit_changed_files, None)
    _write_github_output(
        args.github_output,
        matrix=_full_matrix(args.pack_count),
        has_work=True,
        plan_sha="",
        reason=f"full suite: planner error ({exc})",
        changed_files_sha256="",
        changed_files_count=0,
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


def _trusted_git_environment(_root: Path | None = None) -> dict[str, str]:
    """Clean env for runner-owned git: no repo-binding GIT_* vars.

    Do not set GIT_DIR/GIT_WORK_TREE.  Binding those made the post-step
    ``for-each-ref refs/replace`` probe exit 128 (unrun-picks-boards,
    2026-08-15) against a checkout ``git -C`` / cwd discovery could still
    see.  ``GIT_OPTIONAL_LOCKS=0`` keeps a leftover ``*.lock`` after a
    SIGKILL'd step from turning a timeout into infrastructure unknown.
    """
    clean_env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("GIT_")
    }
    for key in REPO_BINDING_GIT_VARS:
        clean_env.pop(key, None)
    clean_env["GIT_OPTIONAL_LOCKS"] = "0"
    clean_env["GIT_NO_REPLACE_OBJECTS"] = "1"
    return clean_env


def _absolute_git_dir(root: Path) -> Path:
    """Resolve the checkout's git dir without binding GIT_DIR into the env."""
    result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--absolute-git-dir"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        env=_trusted_git_environment(root),
    )
    if result.returncode == 0 and result.stdout.strip():
        return Path(result.stdout.strip())
    candidate = root / ".git"
    if candidate.is_file():
        text = candidate.read_text(encoding="utf-8", errors="replace").strip()
        prefix = "gitdir:"
        if text.lower().startswith(prefix):
            pointed = Path(text[len(prefix) :].strip())
            if not pointed.is_absolute():
                pointed = (root / pointed).resolve()
            return pointed
    return candidate.resolve()


def _git_cmd(
    root: Path,
    env: Mapping[str, str],
    *args: str,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        cwd=root,
        check=check,
        capture_output=True,
        text=True,
        env=dict(env),
    )


def _git_boundary_probes(
    root: Path, env: Mapping[str, str]
) -> tuple[bool, str | None]:
    """Return whether ``for-each-ref refs/replace`` and ``rev-parse HEAD`` work."""
    refs = _git_cmd(root, env, "for-each-ref", "--format=%(refname)", "refs/replace")
    head = _git_cmd(root, env, "rev-parse", "HEAD")
    sha = head.stdout.strip().lower()
    head_ok = head.returncode == 0 and bool(re.fullmatch(r"[0-9a-f]{40}", sha))
    return refs.returncode == 0 and head_ok, sha if head_ok else None


def _replace_refs_from_filesystem(git_dir: Path) -> list[str]:
    """List ``refs/replace/**`` without asking Git to take a ref lock."""
    found: list[str] = []
    replace_dir = git_dir / "refs" / "replace"
    if replace_dir.is_dir():
        for path in sorted(replace_dir.rglob("*")):
            if not path.is_file() or path.name.endswith(".lock"):
                continue
            found.append(path.relative_to(git_dir).as_posix())
    packed = git_dir / "packed-refs"
    if packed.is_file():
        for line in packed.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line or line.startswith("#") or line.startswith("^"):
                continue
            parts = line.split()
            if len(parts) >= 2 and parts[1].startswith("refs/replace/"):
                found.append(parts[1])
    return found


def _git_rewrite_metadata(root: Path, env: Mapping[str, str]) -> tuple[list[str], Path]:
    """Return replace-refs and the grafts path without fail-closing on probe 128.

    ``git for-each-ref refs/replace`` exits 0 when the namespace is empty. Exit
    128 is a lock, a killed sibling, or a confused GIT_DIR — not proof that
    history was rewritten. Fall back to a filesystem listing so a racy probe
    cannot turn a green (or merely timed-out) job into infrastructure unknown.
    Reftable repositories have no loose ``refs/replace`` files; if the Git
    listing fails there, refuse rather than silently miss a rewrite.
    """
    listed = _git_cmd(
        root, env, "for-each-ref", "--format=%(refname)", "refs/replace"
    )
    git_dir = _absolute_git_dir(root)
    if listed.returncode == 0:
        refs = [line for line in listed.stdout.splitlines() if line.strip()]
    else:
        if not git_dir.is_dir():
            raise RuntimeError(
                "`git for-each-ref --format=%(refname) refs/replace` returned "
                f"{listed.returncode} and git dir is not a directory "
                f"({git_dir})"
            )
        if (git_dir / "reftable").is_dir():
            raise RuntimeError(
                "`git for-each-ref --format=%(refname) refs/replace` returned "
                f"{listed.returncode} in a reftable repository; cannot confirm "
                "the absence of replace refs from the filesystem"
            )
        refs = _replace_refs_from_filesystem(git_dir)
    graft_text = _git_cmd(root, env, "rev-parse", "--git-path", "info/grafts")
    if graft_text.returncode != 0:
        graft_path = (
            git_dir / "info" / "grafts"
            if git_dir.is_dir()
            else root / ".git" / "info" / "grafts"
        )
    else:
        graft_path = Path(graft_text.stdout.strip())
        if not graft_path.is_absolute():
            graft_path = root / graft_path
    return refs, graft_path


def _heal_pack_git(root: Path, target: str | None, git_env: Mapping[str, str]) -> None:
    """Rebuild a usable ref store after a child SIGKILL or packed-refs smash.

    Measured 2026-08-15 on PR #5750 pack-9: a job-timeout SIGKILL left
    ``packed-refs`` unreadable. ``rev-parse --absolute-git-dir`` still
    worked, but ``for-each-ref refs/replace`` exited 128 and the post-step
    probe reported infrastructure unknown, masking the timeout and
    breaking every later pack job.
    """
    git_dir = _absolute_git_dir(root)
    commondir = git_dir / "commondir"
    if commondir.exists():
        pointed = commondir.read_text(encoding="utf-8", errors="replace").strip()
        common = Path(pointed)
        if not common.is_absolute():
            common = (git_dir / common).resolve()
        if not common.is_dir():
            commondir.unlink()
    refs_dir = git_dir / "refs"
    if refs_dir.is_file():
        refs_dir.unlink()
    refs_dir.mkdir(parents=True, exist_ok=True)
    (refs_dir / "heads").mkdir(exist_ok=True)
    (refs_dir / "tags").mkdir(exist_ok=True)
    with contextlib.suppress(OSError):
        os.chmod(refs_dir, 0o755)
    _git_cmd(root, git_env, "config", "core.repositoryformatversion", "0")
    _git_cmd(root, git_env, "config", "--unset-all", "extensions.refstorage")
    if target and re.fullmatch(r"[0-9a-f]{40}", target.lower()):
        (git_dir / "HEAD").write_text(f"{target}\n", encoding="utf-8")
    elif not (git_dir / "HEAD").exists() or not (git_dir / "HEAD").stat().st_size:
        (git_dir / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    packed = git_dir / "packed-refs"
    refs_probe = _git_cmd(
        root, git_env, "for-each-ref", "--format=%(refname)", "refs/replace"
    )
    if refs_probe.returncode != 0 and packed.exists():
        broken = git_dir / "packed-refs.broken"
        with contextlib.suppress(FileNotFoundError):
            broken.unlink()
        packed.replace(broken)
    _disable_sparse_checkout(root, git_env)
    if target:
        _git_cmd(root, git_env, "checkout", "--detach", "--force", target)
        _git_cmd(root, git_env, "reset", "--hard", target)


def _ensure_pack_git_usable(root: Path, target: str | None) -> bool:
    """Heal a smashed checkout git dir. Return True if a repair ran."""
    git_env = _trusted_git_environment(root)
    ok, _head = _git_boundary_probes(root, git_env)
    if ok:
        return False
    _heal_pack_git(root, target, git_env)
    git_env = _trusted_git_environment(root)
    ok, _head = _git_boundary_probes(root, git_env)
    if not ok:
        raise RuntimeError(
            "unable to restore git for-each-ref refs/replace and rev-parse HEAD "
            "after a pack job step"
        )
    return True


def _assert_no_git_rewrites(root: Path) -> None:
    env = _trusted_git_environment(root)
    refs, graft_path = _git_rewrite_metadata(root, env)
    if refs or graft_path.exists():
        raise RuntimeError(
            "checkout contains Git history rewrite metadata "
            f"(replace_refs={refs}, grafts={graft_path.exists()})"
        )


def _disable_sparse_checkout(root: Path, git_env: Mapping[str, str]) -> None:
    """Re-open a full tree before the hard reset.

    ``git checkout --force`` honours an active sparse cone, so a prior step
    that ran ``git sparse-checkout set`` (or inherited a leaked GIT_DIR and
    did the same to this checkout) would leave later jobs without
    ``tests/*.py``.  Disable first; the later checkout/reset then materializes
    every path.  ``sparse-checkout disable`` needs a usable HEAD, so the
    config/file fallback still runs when an orphan checkout left HEAD unborn.
    """
    subprocess.run(
        ["git", "sparse-checkout", "disable"],
        cwd=root,
        env=dict(git_env),
        check=False,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "config", "core.sparseCheckout", "false"],
        cwd=root,
        env=dict(git_env),
        check=False,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "config", "index.sparse", "false"],
        cwd=root,
        env=dict(git_env),
        check=False,
        capture_output=True,
        text=True,
    )
    sparse_text = subprocess.run(
        ["git", "rev-parse", "--git-path", "info/sparse-checkout"],
        cwd=root,
        env=dict(git_env),
        check=False,
        capture_output=True,
        text=True,
    )
    if sparse_text.returncode == 0:
        sparse_path = Path(sparse_text.stdout.strip())
        if not sparse_path.is_absolute():
            sparse_path = root / sparse_path
        with contextlib.suppress(FileNotFoundError):
            sparse_path.unlink()


def _restore_workspace(tested_tree_sha: str | None = None) -> None:
    """Restore the clean-checkout boundary that each old job received."""
    root = Path.cwd().resolve()
    _ensure_pack_git_usable(root, tested_tree_sha)
    git_env = _trusted_git_environment(root)
    replace_refs, graft_path = _git_rewrite_metadata(root, git_env)
    for ref in replace_refs:
        subprocess.run(
            ["git", "update-ref", "-d", ref],
            cwd=root,
            env=git_env,
            check=True,
        )
    with contextlib.suppress(FileNotFoundError):
        graft_path.unlink()
    _disable_sparse_checkout(root, git_env)
    target = tested_tree_sha or "HEAD"
    subprocess.run(
        ["git", "checkout", "--detach", "--force", target],
        cwd=root,
        env=git_env,
        check=True,
    )
    subprocess.run(["git", "reset", "--hard", target], cwd=root, env=git_env, check=True)
    subprocess.run(["git", "clean", "-ffdx"], cwd=root, env=git_env, check=True)
    if tested_tree_sha is not None:
        observed = _current_commit_sha(root)
        if observed != tested_tree_sha:
            raise RuntimeError(
                f"workspace restore resolved {observed}, expected {tested_tree_sha}"
            )


def _current_commit_sha(root: Path) -> str:
    git_env = _trusted_git_environment(root)
    result = _git_cmd(root, git_env, "rev-parse", "HEAD")
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip() or "no git output"
        raise RuntimeError(f"git rev-parse HEAD exited {result.returncode}: {detail}")
    value = result.stdout.strip().lower()
    if not re.fullmatch(r"[0-9a-f]{40}", value):
        raise RuntimeError(f"checkout HEAD is not an exact commit SHA: {value!r}")
    return value


def _prepare_provided_actions(
    job: LegacyJob,
    *,
    root: Path,
    tested_tree_sha: str | None,
) -> None:
    """Materialize the action semantics the pack workflow shares.

    setup-python 3.12 and setup-node 20 are supplied by the pack job itself.
    The ordinary checkout is represented by the exact-tree reset. A manifest
    checkout requesting fetch-depth 0 additionally receives every advertised
    branch and tag with complete history, matching checkout@v4's closed input
    contract. Exact-base replay points ``origin`` at its isolated base-only
    remote, so this same operation can never substitute moving current main.
    """
    contracts = _job_action_contract(job)
    if not any(
        contract == {
            "uses": "actions/checkout@v4",
            "with": {"fetch-depth": 0},
        }
        for contract in contracts
    ):
        return
    if tested_tree_sha is None:
        raise RuntimeError(
            f"job {job.job_id!r} requires fetch-depth 0 without an exact tested tree"
        )
    subprocess.run(
        [
            "git",
            "fetch",
            "--no-recurse-submodules",
            "--prune",
            "--tags",
            "--depth=2147483647",
            "origin",
            "+refs/heads/*:refs/remotes/origin/*",
        ],
        cwd=root,
        env=_trusted_git_environment(root),
        check=True,
    )


def _run_job(
    job: LegacyJob,
    *,
    base_ref: str,
    head_ref: str,
    command_env: dict[str, str],
    tested_tree_sha: str | None = None,
) -> JobExecution:
    """Run one legacy job and account for every expected semantic step."""
    _restore_workspace(tested_tree_sha)
    _prepare_provided_actions(
        job,
        root=Path.cwd(),
        tested_tree_sha=tested_tree_sha,
    )
    semantic_env = _child_git_environment(command_env)
    if tested_tree_sha is not None:
        # Bind replace-object *resolution* only.  Do not set GIT_DIR /
        # GIT_WORK_TREE — those force every nested `git init` onto this tree.
        semantic_env["GIT_NO_REPLACE_OBJECTS"] = "1"
    timeout_minutes = job.definition.get("timeout-minutes")
    timeout_seconds = int(timeout_minutes) * 60 if timeout_minutes else None
    job_deadline = (
        time.monotonic() + timeout_seconds if timeout_seconds is not None else None
    )
    specs = semantic_step_specs(job)
    by_index = {spec.step_index: spec for spec in specs}
    observations: list[dict[str, Any]] = []
    failure: str | None = None
    infrastructure: dict[str, Any] = {"outcome": "passed"}

    for index, step in enumerate(job.definition["steps"]):
        spec = by_index.get(index)
        if spec is None:
            continue  # checkout/setup/dependency-install infrastructure.
        if failure is not None:
            infrastructure_failed = infrastructure.get("outcome") != "passed"
            observations.append(
                {
                    **spec.plan_dict(),
                    "outcome": (
                        "infrastructure_blocked"
                        if infrastructure_failed
                        else "not_run_prior_failure"
                    ),
                    "failure_signature": None,
                    "detail": (
                        infrastructure.get("detail", "runner infrastructure failed")
                        if infrastructure_failed
                        else "an earlier semantic step did not pass"
                    ),
                }
            )
            continue
        step_name = spec.display_name or spec.proof_id
        group_open = False
        try:
            command = render_command(
                str(step["run"]), base_ref=base_ref, head_ref=head_ref
            )
            print(f"::group::{job.job_id} — {step_name}", flush=True)
            group_open = True
            remaining = (
                max(0.0, job_deadline - time.monotonic())
                if job_deadline is not None
                else None
            )
            if remaining is not None and remaining <= 0:
                result = CommandObservation(
                    outcome="timed_out",
                    returncode=None,
                    failure_signature=None,
                    detail="logical job timeout exhausted before this step started",
                )
            else:
                result = _stream_command(
                    command,
                    env=semantic_env,
                    timeout_seconds=remaining,
                )
        except Exception as exc:  # noqa: BLE001 — preserve earlier observations
            detail = _bounded_detail(exc)
            infrastructure = {"outcome": "unknown", "detail": detail}
            observations.append(
                {
                    **spec.plan_dict(),
                    "outcome": "infrastructure_blocked",
                    "failure_signature": None,
                    "detail": detail,
                }
            )
            failure = f"{job.job_id}: infrastructure unknown ({detail})"
            continue
        finally:
            if group_open:
                print("::endgroup::", flush=True)
        record: dict[str, Any] = {
            **spec.plan_dict(),
            "outcome": result.outcome,
            "failure_signature": (
                dict(result.failure_signature)
                if result.failure_signature is not None
                else None
            ),
        }
        if result.detail:
            record["detail"] = result.detail
        if tested_tree_sha is not None:
            # Always leave for-each-ref/rev-parse working for the next step.
            # A timed-out step was SIGKILL'd and may have smashed packed-refs;
            # heal first, then only a *passed* step can still hide a rewrite.
            try:
                healed = _ensure_pack_git_usable(Path.cwd(), tested_tree_sha)
            except Exception:  # noqa: BLE001 — last-ditch; proof already lost
                healed = False
                with contextlib.suppress(Exception):
                    _ensure_pack_git_usable(Path.cwd(), tested_tree_sha)
            if result.outcome == "passed":
                try:
                    _assert_no_git_rewrites(Path.cwd())
                    observed_tree_sha = _current_commit_sha(Path.cwd())
                    if observed_tree_sha != tested_tree_sha:
                        raise RuntimeError(
                            f"semantic step changed checkout HEAD to {observed_tree_sha}; "
                            f"expected {tested_tree_sha}"
                        )
                    if healed:
                        raise RuntimeError(
                            "semantic step left git for-each-ref/rev-parse unusable"
                        )
                except Exception as exc:  # noqa: BLE001 — tree doubt blocks proof
                    detail = _bounded_detail(exc)
                    with contextlib.suppress(Exception):
                        _ensure_pack_git_usable(Path.cwd(), tested_tree_sha)
                    infrastructure = {"outcome": "unknown", "detail": detail}
                    record = {
                        **spec.plan_dict(),
                        "outcome": "infrastructure_blocked",
                        "failure_signature": None,
                        "detail": detail,
                    }
                    failure = f"{job.job_id}: infrastructure unknown ({detail})"
        observations.append(record)
        if failure is not None and record["outcome"] == "infrastructure_blocked":
            continue
        if result.outcome == "timed_out":
            failure = f"{job.job_id}: timed out after {timeout_minutes} minutes"
        elif result.outcome == "failed":
            failure = (
                f"{job.job_id}: step {step_name!r} exited {result.returncode}"
            )
    return JobExecution(
        logical_job_id=job.job_id,
        job_exec_sha256=semantic_job_digest(job),
        infrastructure=infrastructure,
        steps=tuple(observations),
        failure=failure,
    )


def _stream_command(
    command: str,
    *,
    env: Mapping[str, str],
    timeout_seconds: int | float | None,
) -> CommandObservation:
    """Stream a child live while retaining only bounded structured atoms."""
    deadline = (
        time.monotonic() + max(0.0, float(timeout_seconds))
        if timeout_seconds is not None
        else None
    )
    collector = FailureAtomCollector(
        max_bytes=FAILURE_CAPTURE_MAX_BYTES,
        max_atoms=FAILURE_CAPTURE_MAX_ATOMS,
        max_line_bytes=FAILURE_CAPTURE_MAX_LINE_BYTES,
    )
    process = subprocess.Popen(
        ["bash", "-eo", "pipefail", "-c", command],
        env=dict(env),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=0,
        start_new_session=True,
    )
    assert process.stdout is not None
    pump_error: list[str] = []

    def pump() -> None:
        pending = bytearray()
        discard_remainder = False
        try:
            while True:
                chunk = process.stdout.read(4_096)
                if not chunk:
                    break
                # Normal Actions output remains live.  Decode only for display;
                # the collector receives the original bounded byte line.
                print(chunk.decode("utf-8", "replace"), end="", flush=True)
                pending.extend(chunk)
                while b"\n" in pending:
                    raw, _, rest = pending.partition(b"\n")
                    pending = bytearray(rest)
                    if not discard_remainder:
                        collector.feed(bytes(raw) + b"\n")
                    discard_remainder = False
                if len(pending) > FAILURE_CAPTURE_MAX_LINE_BYTES:
                    if not discard_remainder:
                        collector.feed(
                            bytes(pending[:FAILURE_CAPTURE_MAX_LINE_BYTES]),
                            truncated=True,
                        )
                    pending.clear()
                    discard_remainder = True
            if pending and not discard_remainder:
                collector.feed(bytes(pending))
        except Exception as exc:  # noqa: BLE001 — never hide child completion
            pump_error.append(_bounded_detail(exc))

    reader = threading.Thread(target=pump, name="ci-pack-output", daemon=True)
    reader.start()
    timed_out = False
    try:
        wait_seconds = (
            max(0.0, deadline - time.monotonic())
            if deadline is not None
            else None
        )
        process.wait(timeout=wait_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
        with contextlib.suppress(subprocess.TimeoutExpired):
            process.wait(
                timeout=(
                    max(0.0, deadline - time.monotonic())
                    if deadline is not None
                    else 0
                )
            )
    finally:
        reader.join(
            timeout=(
                max(0.0, deadline - time.monotonic())
                if deadline is not None
                else 5
            )
        )
        stream_incomplete = reader.is_alive()
        with contextlib.suppress(OSError):
            process.stdout.close()

    if timed_out:
        return CommandObservation(
            outcome="timed_out",
            returncode=process.returncode,
            failure_signature=None,
            detail="semantic step exceeded its job timeout",
        )
    if pump_error:
        return CommandObservation(
            outcome="failed",
            returncode=process.returncode,
            failure_signature=None,
            detail=f"output stream failed: {pump_error[0]}",
        )
    if stream_incomplete:
        return CommandObservation(
            outcome="failed",
            returncode=process.returncode,
            failure_signature=None,
            detail="output stream did not close with the semantic command",
        )
    if process.returncode:
        signature = collector.signature()
        return CommandObservation(
            outcome="failed",
            returncode=process.returncode,
            failure_signature=signature,
            detail=f"exited {process.returncode}",
        )
    return CommandObservation(outcome="passed", returncode=0)


def _child_environment(
    changed_files_file: str | Path | None = None,
) -> dict[str, str]:
    """The base environment every legacy step inherits — file in, list out.

    ONE SOURCE FOR THE CHILDREN, AND IT IS THE FILE (2026-08-14, run
    31775693780).  Every legacy step is a fresh `bash -eo pipefail -c` — an
    execve — and Linux caps a SINGLE env string at MAX_ARG_STRLEN = 131,072
    bytes.  The measured list was 350,264 bytes, so a child inheriting it dies
    with "Argument list too long" before its first line runs; that is what killed
    all twelve packs on PR #5578.  Forwarding both transports would also let a
    stale env string out-vote the artifact in whichever child happens to read it
    first, so when the handle is configured the inline string is REMOVED rather
    than merely ignored.
    """
    command_env = os.environ.copy()
    if changed_files_file is not None:
        command_env["CI_CHANGED_FILES_FILE"] = str(changed_files_file)
    if command_env.get("CI_CHANGED_FILES_FILE"):
        command_env.pop("CI_CHANGED_FILES_JSON", None)
    return _child_git_environment(command_env)


def _child_git_environment(command_env: Mapping[str, str]) -> dict[str, str]:
    """Drop repo-binding Git vars so a child can `git init` in tmp_path."""
    cleaned = dict(command_env)
    for key in REPO_BINDING_GIT_VARS:
        cleaned.pop(key, None)
    return cleaned


def _dependency_environment(
    install_command: str | None,
    *,
    changed_files_file: str | Path | None = None,
) -> dict[str, str]:
    """Build a clean, single-use dependency environment for a job group."""
    # `_child_environment`, never a bare `os.environ.copy()`: this is one of the
    # two places a legacy step's environment is assembled, and the E2BIG repair
    # lives there.
    command_env = _child_environment(changed_files_file)
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


def _blocked_job_execution(
    job: LegacyJob,
    *,
    infrastructure_outcome: str,
    detail: object,
) -> JobExecution:
    bounded = _bounded_detail(detail)
    return JobExecution(
        logical_job_id=job.job_id,
        job_exec_sha256=semantic_job_digest(job),
        infrastructure={"outcome": infrastructure_outcome, "detail": bounded},
        steps=tuple(
            {
                **spec.plan_dict(),
                "outcome": "infrastructure_blocked",
                "failure_signature": None,
                "detail": bounded,
            }
            for spec in semantic_step_specs(job)
        ),
        failure=f"{job.job_id}: infrastructure {infrastructure_outcome} ({bounded})",
    )


def _coerce_job_execution(
    job: LegacyJob, value: JobExecution | str | None
) -> JobExecution:
    """Refuse a runner-internal result shape as infrastructure doubt."""
    if isinstance(value, JobExecution):
        return value
    return _blocked_job_execution(
        job,
        infrastructure_outcome="unknown",
        detail=(
            "internal runner returned invalid execution result "
            f"{type(value).__name__}"
        ),
    )


def _write_semantic_fragment(path: Path, fragment: Mapping[str, Any]) -> None:
    """Atomically write the bounded raw fragment consumed by ci-gate."""
    _atomic_write_json(path, fragment)


class ExecutionProfileError(RuntimeError):
    """The runtime executing ``--execute`` disagrees with RUNNER_CONTRACT.

    RUNNER_CONTRACT's ``linux-x86_64/python-3.12.13/node-20`` clause is baked
    into every job's semantic digest (`semantic_job_digest`), and hosted and
    self-hosted execution are reconciled bytewise against that digest. A
    runner whose actual OS/arch/interpreter silently disagrees with the
    string would let two genuinely different environments compare as one
    attested contract, so this is a distinct, fail-closed error raised
    before any legacy job executes — never folded into a generic
    infrastructure outcome a reader might mistake for a transient flake.
    """


def _selected_python_loader_environment() -> dict[str, str]:
    """Derive the Linux loader path from the attested interpreter itself.

    ``actions/setup-python`` selects a versioned shared-library build.  Re-execing
    that interpreter with a deliberately small environment must retain only its
    own library directory.  The action can expose that directory through a
    runner-local alias while ``sysconfig`` reports its canonical tool-cache path,
    so preserve an ambient alias only after proving it resolves to the declared
    directory inside ``sys.base_prefix`` and contains a declared Python SONAME.
    """
    if platform.system() != "Linux":
        return {}
    raw_library_dir = sysconfig.get_config_var("LIBDIR")
    raw_library_names = [
        sysconfig.get_config_var("LDLIBRARY"),
        sysconfig.get_config_var("INSTSONAME"),
    ]
    library_names = [
        name for name in raw_library_names if isinstance(name, str) and name
    ]
    if not isinstance(raw_library_dir, str) or not raw_library_dir:
        raise ExecutionProfileError("selected Python does not declare LIBDIR")
    if not library_names:
        raise ExecutionProfileError(
            "selected Python does not declare LDLIBRARY or INSTSONAME"
        )
    try:
        prefix = Path(sys.base_prefix).resolve(strict=True)
        declared_library_dir = Path(raw_library_dir).resolve(strict=True)
        declared_library_dir.relative_to(prefix)
    except (OSError, ValueError) as exc:
        raise ExecutionProfileError(
            "selected Python library directory is outside selected interpreter prefix"
        ) from exc

    candidates: list[Path] = []
    for entry in os.environ.get("LD_LIBRARY_PATH", "").split(os.pathsep):
        if not entry:
            continue
        candidate = Path(entry)
        try:
            if candidate.resolve(strict=True) == declared_library_dir:
                candidates.append(candidate)
        except OSError:
            continue
    candidates.append(Path(raw_library_dir))
    for candidate in candidates:
        if any((candidate / name).is_file() for name in library_names):
            return {"LD_LIBRARY_PATH": str(candidate)}
    raise ExecutionProfileError(
        "selected Python shared library is absent: "
        f"{declared_library_dir} ({', '.join(library_names)})"
    )


def _node_major_version() -> int | None:
    """Return node's major version, or None if node is missing/unparseable."""
    try:
        result = subprocess.run(
            ["node", "--version"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    match = re.fullmatch(r"v(\d+)\.\d+\.\d+\s*", result.stdout)
    return int(match.group(1)) if match else None


def attest_execution_profile(plan: "CIPackPlan | None") -> None:
    """Fail closed before any legacy job runs unless this runtime matches
    the portable Linux execution profile v2 RUNNER_CONTRACT declares.

    Invoked on the ``--execute`` path whenever a run consumes an
    authoritative plan (``--plan-json``) or mints a semantic fragment
    (``--emit-semantic-fragment``) — the two cases that publish evidence a
    reconciler or comparator will trust. Checks, in order: OS family Linux;
    machine x86_64; interpreter patch exactly 3.12.13; node major exactly
    20; and, when a plan is present, that the checkout HEAD equals the
    plan's ``tested_tree_sha`` (already independently enforced earlier in
    `execute_pack` via ``--expect-tested-tree-sha``; repeated here so the
    attestation itself is a complete, self-contained claim).

    There is deliberately no env/CLI bypass. A unit test monkeypatches this
    function itself to exercise the surrounding plumbing, or monkeypatches
    its module-level primitives (``platform``, `_node_major_version`,
    `_current_commit_sha`) to exercise the real refusal logic.
    """
    system = platform.system()
    if system != "Linux":
        raise ExecutionProfileError(
            f"execution profile requires Linux, runtime reports {system!r}"
        )
    machine = platform.machine()
    if machine != "x86_64":
        raise ExecutionProfileError(
            f"execution profile requires x86_64, runtime reports {machine!r}"
        )
    python_version = platform.python_version()
    if python_version != "3.12.13":
        raise ExecutionProfileError(
            "execution profile requires Python 3.12.13, runtime reports "
            f"{python_version!r}"
        )
    node_major = _node_major_version()
    if node_major != 20:
        raise ExecutionProfileError(
            f"execution profile requires node 20.x, runtime reports major "
            f"{node_major!r}"
        )
    if plan is not None:
        observed = _current_commit_sha(_workspace_root())
        if observed != plan.tested_tree_sha:
            raise ExecutionProfileError(
                f"checkout HEAD {observed} does not match attested tested "
                f"tree {plan.tested_tree_sha}"
            )


def _remaining_seconds(deadline: float) -> float:
    return max(0.0, deadline - time.monotonic())


def _git_run_bounded(
    args: Sequence[str],
    *,
    cwd: Path,
    deadline: float,
    check: bool = True,
    capture_output: bool = True,
    env: Mapping[str, str] | None = None,
    stdin_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    remaining = _remaining_seconds(deadline)
    if remaining <= 0:
        raise TimeoutError("exact-base replay budget exhausted")
    return subprocess.run(
        list(args),
        cwd=cwd,
        check=check,
        capture_output=capture_output,
        text=True,
        timeout=remaining,
        env=None if env is None else dict(env),
        input=stdin_text,
    )


def _promisor_remote(root: Path, *, deadline: float) -> str | None:
    """Name the remote that backs this repository's omitted objects, if any."""
    probe = _git_run_bounded(
        ["git", "config", "--get-regexp", r"^remote\..*\.promisor$"],
        cwd=root,
        deadline=deadline,
        check=False,
    )
    if probe.returncode:
        return None
    for line in probe.stdout.splitlines():
        key, _, value = line.partition(" ")
        if value.strip().lower() != "true":
            continue
        name = key[len("remote.") : -len(".promisor")]
        if name:
            return name
    return None


def _missing_tree_objects(root: Path, sha: str, *, deadline: float) -> list[str]:
    """Blob OIDs at ``sha`` that are absent from the local object store.

    ``git rev-list --missing=print`` cannot answer this. A blob a partial clone
    omitted is an EXPECTED absence, so it is never printed — measured against a
    real ``blob:none`` clone, a tree with three genuinely absent blobs reported
    zero missing objects. ``GIT_NO_LAZY_FETCH`` makes ``cat-file`` report those
    same objects as ``missing`` instead of silently fetching them back one
    network round trip at a time, which is both the accurate detector and the
    cheap one.
    """
    listing = _git_run_bounded(
        ["git", "ls-tree", "-r", "-z", sha],
        cwd=root,
        deadline=deadline,
    ).stdout
    oids: list[str] = []
    seen: set[str] = set()
    for entry in listing.split("\0"):
        meta, _, _path = entry.partition("\t")
        fields = meta.split()
        if len(fields) < 3 or fields[1] != "blob":
            continue
        oid = fields[2]
        if oid not in seen:
            seen.add(oid)
            oids.append(oid)
    if not oids:
        return []
    probe = _git_run_bounded(
        ["git", "cat-file", "--batch-check"],
        cwd=root,
        deadline=deadline,
        check=False,
        env={**os.environ, "GIT_NO_LAZY_FETCH": "1"},
        stdin_text="".join(f"{oid}\n" for oid in oids),
    )
    return [
        line.split(" ", 1)[0]
        for line in probe.stdout.splitlines()
        if line.endswith(" missing")
    ]


def _hydrate_exact_base_objects(root: Path, sha: str, *, deadline: float) -> None:
    """Materialise every blob at ``sha`` before the replay borrows this odb.

    The replay checkout runs in a private repository that borrows only this
    one's object database through ``objects/info/alternates``. Alternates share
    OBJECTS, never the partial-clone extension or the promisor remote that can
    go and get the omitted ones — so on a ``blob:none`` runner checkout
    (ci.yml gives every pack ``filter: blob:none``) the borrowing repository
    cannot lazily fetch, and ``git checkout`` dies with "unable to read sha1
    file" on precisely the blobs the PR changed. Hydrating here, in the
    checkout that DOES hold the promisor remote and its credentials, is what
    keeps the replay repository's isolation free of network configuration.
    """
    remote = _promisor_remote(root, deadline=deadline)
    if remote is None:
        return
    missing = _missing_tree_objects(root, sha, deadline=deadline)
    if not missing:
        return
    # git's own lazy-fetch path issues ONE fetch PER OBJECT (measured: three
    # missing blobs, three `git fetch` invocations), so the bulk `--stdin`
    # form it uses internally is the first move and the per-object path is
    # only the fallback for a git that does not accept it.
    bulk = _git_run_bounded(
        [
            "git",
            "fetch",
            remote,
            "--no-tags",
            "--no-write-fetch-head",
            "--recurse-submodules=no",
            "--filter=blob:none",
            "--stdin",
        ],
        cwd=root,
        deadline=deadline,
        check=False,
        stdin_text="".join(f"{oid}\n" for oid in missing),
    )
    residual = _missing_tree_objects(root, sha, deadline=deadline)
    fallback: subprocess.CompletedProcess[str] | None = None
    if residual:
        fallback = _git_run_bounded(
            ["git", "cat-file", "--batch-check"],
            cwd=root,
            deadline=deadline,
            check=False,
            stdin_text="".join(f"{oid}\n" for oid in residual),
        )
        residual = _missing_tree_objects(root, sha, deadline=deadline)
    if residual:
        sample = ", ".join(residual[:5])
        if len(residual) > 5:
            sample += f", …(+{len(residual) - 5})"
        detail = (
            f"exact-base hydration left {len(residual)} object(s) of "
            f"{len(missing)} unresolved for {sha} via promisor remote "
            f"{remote!r}: {sample}; bulk rc={bulk.returncode} "
            f"stderr={_one_line(bulk.stderr or '')}"
        )
        if fallback is not None:
            detail += (
                f"; per-object rc={fallback.returncode} "
                f"stderr={_one_line(fallback.stderr or '')}"
            )
        raise RuntimeError(detail)


def _ensure_exact_commit(root: Path, sha: str, *, deadline: float) -> str:
    """Acquire only the exact replay commit; never widen to full history."""
    if not re.fullmatch(r"[0-9a-fA-F]{40}", sha):
        raise RuntimeError(f"base replay requires a full 40-hex SHA, got {sha!r}")
    probe = _git_run_bounded(
        ["git", "cat-file", "-e", f"{sha}^{{commit}}"],
        cwd=root,
        deadline=deadline,
        check=False,
    )
    if probe.returncode:
        _git_run_bounded(
            ["git", "fetch", "--no-tags", "--depth=1", "origin", sha],
            cwd=root,
            deadline=deadline,
        )
    resolved = _git_run_bounded(
        ["git", "rev-parse", f"{sha}^{{commit}}"],
        cwd=root,
        deadline=deadline,
    ).stdout.strip()
    if resolved.lower() != sha.lower():
        raise RuntimeError(
            f"exact-base acquisition resolved {resolved!r}, expected {sha!r}"
        )
    exact = resolved.lower()
    _hydrate_exact_base_objects(root, exact, deadline=deadline)
    return exact


def _bounded_rmtree(path: Path, *, deadline: float) -> None:
    """Start cleanup without letting teardown exceed the replay deadline."""
    cleanup = threading.Thread(
        target=shutil.rmtree,
        args=(path,),
        kwargs={"ignore_errors": True},
        name="ci-base-replay-cleanup",
        daemon=True,
    )
    cleanup.start()
    cleanup.join(timeout=_remaining_seconds(deadline))


@contextlib.contextmanager
def _exact_base_worktree(
    root: Path, sha: str, *, deadline: float
) -> Iterator[Path]:
    """Create an independent exact-base checkout with a pinned local origin.

    A linked worktree shares refs and remote configuration with the head
    checkout. That lets a base manifest's ordinary ``git fetch origin main``
    substitute whatever main points to later. This repository shares only the
    immutable object database; its refs/config/index are private, and its sole
    origin branch is ``main`` at the exact replay SHA.
    """
    exact_sha = _ensure_exact_commit(root, sha, deadline=deadline)
    runner_temp = Path(os.environ.get("RUNNER_TEMP") or tempfile.gettempdir())
    holder = Path(tempfile.mkdtemp(prefix="ci-base-replay-", dir=runner_temp))
    worktree = holder / "worktree"
    repository = holder / "repository.git"
    pinned_origin = holder / "origin.git"
    try:
        common_dir_text = _git_run_bounded(
            ["git", "rev-parse", "--git-common-dir"],
            cwd=root,
            deadline=deadline,
        ).stdout.strip()
        common_dir = Path(common_dir_text)
        if not common_dir.is_absolute():
            common_dir = root / common_dir
        shared_objects = (common_dir / "objects").resolve()

        _git_run_bounded(
            ["git", "init", "--bare", str(pinned_origin)],
            cwd=root,
            deadline=deadline,
        )
        (pinned_origin / "objects" / "info" / "alternates").write_text(
            str(shared_objects) + "\n",
            encoding="utf-8",
        )
        _git_run_bounded(
            [
                "git",
                "--git-dir",
                str(pinned_origin),
                "update-ref",
                "refs/heads/main",
                exact_sha,
            ],
            cwd=root,
            deadline=deadline,
        )
        _git_run_bounded(
            [
                "git",
                "--git-dir",
                str(pinned_origin),
                "symbolic-ref",
                "HEAD",
                "refs/heads/main",
            ],
            cwd=root,
            deadline=deadline,
        )

        _git_run_bounded(
            ["git", "init", "--bare", str(repository)],
            cwd=root,
            deadline=deadline,
        )
        (repository / "objects" / "info" / "alternates").write_text(
            str(shared_objects) + "\n",
            encoding="utf-8",
        )
        worktree.mkdir()
        for key, value in (
            ("core.bare", "false"),
            ("core.worktree", str(worktree)),
        ):
            _git_run_bounded(
                ["git", "--git-dir", str(repository), "config", key, value],
                cwd=root,
                deadline=deadline,
            )
        _git_run_bounded(
            [
                "git",
                "--git-dir",
                str(repository),
                "remote",
                "add",
                "origin",
                str(pinned_origin),
            ],
            cwd=root,
            deadline=deadline,
        )
        _git_run_bounded(
            [
                "git",
                "--git-dir",
                str(repository),
                "update-ref",
                "refs/remotes/origin/main",
                exact_sha,
            ],
            cwd=root,
            deadline=deadline,
        )
        _git_run_bounded(
            [
                "git",
                "--git-dir",
                str(repository),
                "--work-tree",
                str(worktree),
                "checkout",
                "--detach",
                "--force",
                exact_sha,
            ],
            cwd=root,
            deadline=deadline,
        )
        (worktree / ".git").write_text(
            f"gitdir: {repository}\n",
            encoding="utf-8",
        )
        observed_head = _git_run_bounded(
            ["git", "rev-parse", "HEAD"],
            cwd=worktree,
            deadline=deadline,
        ).stdout.strip()
        observed_main = _git_run_bounded(
            ["git", "rev-parse", "origin/main"],
            cwd=worktree,
            deadline=deadline,
        ).stdout.strip()
        if observed_head != exact_sha or observed_main != exact_sha:
            raise RuntimeError(
                "isolated base checkout did not bind HEAD and origin/main to "
                f"{exact_sha}"
            )
        yield worktree
    finally:
        _bounded_rmtree(holder, deadline=deadline)


def _stream_process_with_deadline(
    command: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str],
    deadline: float,
) -> tuple[int | None, bool]:
    """Run the base runner serially with inherited live output and one budget."""
    remaining = _remaining_seconds(deadline)
    if remaining <= 0:
        return None, True
    process = subprocess.Popen(
        list(command),
        cwd=cwd,
        env=dict(env),
        start_new_session=True,
    )
    try:
        return process.wait(timeout=_remaining_seconds(deadline)), False
    except subprocess.TimeoutExpired:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
        with contextlib.suppress(subprocess.TimeoutExpired):
            process.wait(timeout=_remaining_seconds(deadline))
        return process.returncode, True


def _base_replay_unavailable(base_sha: str, detail: object) -> dict[str, Any]:
    return {
        "tested_tree_sha": base_sha,
        "outcome": "unavailable",
        "detail": _bounded_detail(detail),
    }


def _run_exact_base_replays(
    *,
    root: Path,
    plan: CIPackPlan,
    records: list[dict[str, Any]],
    budget_seconds: int,
) -> None:
    """Replay failed logical jobs serially under the exact base checkout."""
    failed_records = [
        record
        for record in records
        if any(
            step.get("outcome") in {"failed", "timed_out"}
            for step in record.get("steps", [])
        )
    ]
    if not failed_records or plan.role != "pr_head":
        return
    deadline = time.monotonic() + max(1, budget_seconds)
    base_sha = plan.base_sha
    try:
        with _exact_base_worktree(root, base_sha, deadline=deadline) as base_root:
            base_runner = base_root / "scripts" / "run_ci_pack.py"
            base_manifest = base_root / ".github" / "ci" / "legacy-jobs.yml"
            for record in failed_records:
                target_steps = [
                    step
                    for step in record["steps"]
                    if step.get("outcome") in {"failed", "timed_out"}
                ]
                if _remaining_seconds(deadline) <= 0:
                    replay = {
                        "tested_tree_sha": base_sha,
                        "outcome": "timed_out",
                        "detail": "exact-base replay budget exhausted",
                    }
                    for step in target_steps:
                        step["base_replay"] = replay
                    continue
                # Keep all runner outputs OUTSIDE the clean base worktree.
                # `_run_job` hard-cleans that tree, and evidence generation must
                # never mutate the subject it claims to have replayed.
                child_temp = base_root.parent / "runner-temp"
                child_temp.mkdir(exist_ok=True)
                replay_path = child_temp / "base-replay.json"
                with contextlib.suppress(FileNotFoundError):
                    replay_path.unlink()
                base_changed_files = child_temp / "changed-files.json"
                base_changed_files.write_text("null\n", encoding="utf-8")
                # A replay is a base-only execution context, not a PR runner
                # wearing a different cwd. Build from a small non-capability
                # allowlist: denylisting GITHUB_TOKEN alone still leaves the
                # Actions runtime/artifact and OIDC bearer tokens live.
                safe_parent_names = {
                    "PATH",
                    "SHELL",
                    "LANG",
                    "LANGUAGE",
                    "LC_ALL",
                    "TZ",
                    "TERM",
                    "COLORTERM",
                    "NO_COLOR",
                    "FORCE_COLOR",
                    "SSL_CERT_FILE",
                    "SSL_CERT_DIR",
                    "REQUESTS_CA_BUNDLE",
                    "CURL_CA_BUNDLE",
                    "HTTP_PROXY",
                    "HTTPS_PROXY",
                    "ALL_PROXY",
                    "NO_PROXY",
                    "http_proxy",
                    "https_proxy",
                    "all_proxy",
                    "no_proxy",
                    "PYTHONUTF8",
                    "PYTHONIOENCODING",
                    "PYTHONDONTWRITEBYTECODE",
                    "RUNNER_OS",
                    "RUNNER_ARCH",
                    "RUNNER_ENVIRONMENT",
                    "RUNNER_TOOL_CACHE",
                    "ImageOS",
                    "ImageVersion",
                }
                child_env = {
                    key: value
                    for key, value in os.environ.items()
                    if key in safe_parent_names or key.startswith("LC_")
                }
                # Re-exec the selected setup-python interpreter without copying
                # candidate-controlled loader state.  The directory is derived
                # and containment-checked against sys.base_prefix above.
                child_env.update(_selected_python_loader_environment())
                child_home = child_temp / "home"
                child_home.mkdir(exist_ok=True)
                child_env.update(
                    {
                        "HOME": str(child_home),
                        "TMPDIR": str(child_temp),
                        "GITHUB_ACTIONS": "true",
                        "GITHUB_WORKSPACE": str(base_root),
                        "GITHUB_SHA": base_sha,
                        "GITHUB_REF": "refs/heads/main",
                        "GITHUB_REF_NAME": "main",
                        "GITHUB_REF_TYPE": "branch",
                        "GITHUB_HEAD_REF": "",
                        "GITHUB_BASE_REF": "",
                        "GITHUB_EVENT_NAME": "base_replay",
                        "GITHUB_RUN_ID": plan.workflow_run_id,
                        "GITHUB_WORKFLOW": plan.workflow,
                        "RUNNER_TEMP": str(child_temp),
                        "CI_DISABLE_BASE_REPLAY": "1",
                        # Replay the base as BASE, never fetch/inspect the PR
                        # branch through a dynamic manifest expression or a
                        # head changed-file handle inherited from this pack.
                        "CI_BASE_REF": "main",
                        "CI_HEAD_REF": "main",
                        "CI_CHANGED_FILES_FILE": str(base_changed_files),
                        "CI_TESTED_TREE_SHA": base_sha,
                        "CI_SUBJECT_HEAD_SHA": base_sha,
                        "CI_BASE_SHA": base_sha,
                        "CI_SEMANTIC_ROLE": "main",
                    }
                )
                child_env.pop("CI_CHANGED_FILES_JSON", None)
                command = [
                    sys.executable,
                    str(base_runner),
                    "--workflow",
                    str(base_manifest),
                    "--execute",
                    "--semantic-replay-job",
                    str(record["logical_job_id"]),
                    "--emit-semantic-fragment",
                    str(replay_path),
                    "--tested-tree-sha",
                    base_sha,
                    "--subject-head-sha",
                    base_sha,
                    "--base-sha",
                    base_sha,
                    "--role",
                    "main",
                    "--event",
                    "base_replay",
                    "--workflow-run-id",
                    plan.workflow_run_id,
                    "--workflow-name",
                    plan.workflow,
                    "--disable-base-replay",
                ]
                _returncode, timed_out = _stream_process_with_deadline(
                    command,
                    cwd=base_root,
                    env=child_env,
                    deadline=deadline,
                )
                if timed_out:
                    replay: dict[str, Any] = {
                        "tested_tree_sha": base_sha,
                        "outcome": "timed_out",
                        "detail": "exact-base replay budget exhausted",
                    }
                elif not replay_path.is_file():
                    replay = _base_replay_unavailable(
                        base_sha,
                        "base runner did not emit semantic replay evidence "
                        "(the base may predate the semantic epoch)",
                    )
                else:
                    try:
                        replay_doc = _load_json_object(replay_path)
                        if replay_doc.get("schema") != FRAGMENT_SCHEMA:
                            raise ManifestError("base replay fragment schema mismatch")
                        if replay_doc.get("tested_tree_sha") != base_sha:
                            raise ManifestError("base replay tree identity mismatch")
                        if replay_doc.get("subject_head_sha") != base_sha:
                            raise ManifestError("base replay subject identity mismatch")
                        if replay_doc.get("base_sha") != base_sha:
                            raise ManifestError("base replay base identity mismatch")
                        if replay_doc.get("role") != "main":
                            raise ManifestError("base replay role must be main")
                        if replay_doc.get("job_present") is False:
                            replay = {
                                "tested_tree_sha": base_sha,
                                "job_present": False,
                            }
                        else:
                            replay_jobs = replay_doc.get("jobs")
                            if not isinstance(replay_jobs, list) or len(replay_jobs) != 1:
                                raise ManifestError(
                                    "base replay must contain exactly one logical job"
                                )
                            base_job = replay_jobs[0]
                            if base_job.get("logical_job_id") != record["logical_job_id"]:
                                raise ManifestError("base replay logical job mismatch")
                            replay = {
                                "tested_tree_sha": base_sha,
                                "job_present": True,
                                "logical_job_id": base_job["logical_job_id"],
                                "job_exec_sha256": base_job["job_exec_sha256"],
                                "infrastructure": base_job["infrastructure"],
                                "steps": base_job["steps"],
                            }
                    except (ManifestError, OSError, json.JSONDecodeError) as exc:
                        replay = _base_replay_unavailable(base_sha, exc)
                for step in target_steps:
                    step["base_replay"] = replay
    except (RuntimeError, subprocess.SubprocessError, TimeoutError, OSError) as exc:
        replay = _base_replay_unavailable(base_sha, exc)
        for record in failed_records:
            for step in record.get("steps", []):
                if step.get("outcome") in {"failed", "timed_out"}:
                    step["base_replay"] = replay


def execute_pack(
    jobs: list[LegacyJob],
    *,
    shadow_predicted: frozenset[str] | None = None,
    plan: CIPackPlan | None = None,
    pack_index: int = 0,
    emit_semantic_fragment: Path | None = None,
    enable_base_replay: bool = True,
    base_replay_budget_seconds: int = DEFAULT_BASE_REPLAY_BUDGET_SECONDS,
    changed_files_file: str | Path | None = None,
    require_attestation: bool = False,
) -> int:
    """Execute a pack, account completely, and emit raw bounded evidence."""
    root = _workspace_root()
    base_ref = os.environ.get("CI_BASE_REF", "main")
    head_ref = os.environ.get("CI_HEAD_REF", "")
    failures: list[str] = []
    records: list[dict[str, Any]] = []
    pack_infrastructure: list[dict[str, str]] = []
    current_dependency: object = object()
    dependency_error: str | None = None
    bound_tree_sha = plan.tested_tree_sha if plan is not None else os.environ.get(
        "CI_TESTED_TREE_SHA"
    )
    if bound_tree_sha is not None and not re.fullmatch(
        r"[0-9a-f]{40}", bound_tree_sha
    ):
        bound_tree_sha = None
    command_env = _child_environment(changed_files_file)
    if plan is not None:
        try:
            observed_tree_sha = _current_commit_sha(root)
            if observed_tree_sha != plan.tested_tree_sha:
                raise RuntimeError(
                    f"checkout HEAD {observed_tree_sha} does not match planned "
                    f"tested tree {plan.tested_tree_sha}"
                )
        except Exception as exc:  # noqa: BLE001 — emit an explicit blocked pack
            detail = _bounded_detail(exc)
            records = [
                _blocked_job_execution(
                    job,
                    infrastructure_outcome="runner_startup_failed",
                    detail=detail,
                ).fragment_dict()
                for job in jobs
            ]
            failures = [
                f"{job.job_id}: infrastructure runner_startup_failed ({detail})"
                for job in jobs
            ] or [f"ci-pack: runner_startup_failed ({detail})"]
            for failure in failures:
                job_id = failure.split(":", 1)[0]
                print(f"::error title=legacy-job-{job_id}::{failure}", flush=True)
            if emit_semantic_fragment is not None:
                _write_semantic_fragment(
                    emit_semantic_fragment,
                    {
                        "schema": FRAGMENT_SCHEMA,
                        "workflow_run_id": plan.workflow_run_id,
                        "workflow": plan.workflow,
                        "event": plan.event,
                        "role": plan.role,
                        "tested_tree_sha": plan.tested_tree_sha,
                        "subject_head_sha": plan.subject_head_sha,
                        "base_sha": plan.base_sha,
                        "plan_sha256": plan.plan_sha256,
                        "pack_index": pack_index,
                        "infrastructure": [
                            {
                                "outcome": "runner_startup_failed",
                                "detail": detail,
                            }
                        ],
                        "jobs": records,
                    },
                )
            failed_ids = sorted(
                failure.split(":", 1)[0] for failure in failures
            )
            print("CI_PACK_FAILED_JOBS=" + json.dumps(failed_ids), flush=True)
            return 1
    if require_attestation:
        try:
            attest_execution_profile(plan)
        except Exception as exc:  # noqa: BLE001 — emit an explicit blocked pack
            detail = _bounded_detail(exc)
            records = [
                _blocked_job_execution(
                    job,
                    infrastructure_outcome="attestation_failed",
                    detail=detail,
                ).fragment_dict()
                for job in jobs
            ]
            failures = [
                f"{job.job_id}: infrastructure attestation_failed ({detail})"
                for job in jobs
            ] or [f"ci-pack: attestation_failed ({detail})"]
            # A distinct annotation FIRST — the whole point of a distinct
            # fail-closed error is that a reader searching the log for
            # "attestation" finds it, not just the generic per-job title.
            print(f"::error title=ci-attestation::{_one_line(detail)}", flush=True)
            for failure in failures:
                job_id = failure.split(":", 1)[0]
                print(f"::error title=legacy-job-{job_id}::{failure}", flush=True)
            if emit_semantic_fragment is not None:
                _write_semantic_fragment(
                    emit_semantic_fragment,
                    {
                        "schema": FRAGMENT_SCHEMA,
                        "workflow_run_id": (
                            plan.workflow_run_id
                            if plan is not None
                            else os.environ.get("GITHUB_RUN_ID", "local")
                        ),
                        "workflow": (
                            plan.workflow
                            if plan is not None
                            else os.environ.get("GITHUB_WORKFLOW", "ci")
                        ),
                        "event": (
                            plan.event
                            if plan is not None
                            else os.environ.get("GITHUB_EVENT_NAME", "local")
                        ),
                        "role": (
                            plan.role
                            if plan is not None
                            else os.environ.get("CI_SEMANTIC_ROLE", "main")
                        ),
                        "tested_tree_sha": (
                            plan.tested_tree_sha
                            if plan is not None
                            else (
                                os.environ.get("CI_TESTED_TREE_SHA")
                                or os.environ.get(
                                    "GITHUB_SHA", "unbound-tested-tree"
                                )
                            )
                        ),
                        "subject_head_sha": (
                            plan.subject_head_sha
                            if plan is not None
                            else os.environ.get("CI_SUBJECT_HEAD_SHA", "")
                        ),
                        "base_sha": (
                            plan.base_sha
                            if plan is not None
                            else os.environ.get("CI_BASE_SHA", "")
                        ),
                        "plan_sha256": (
                            plan.plan_sha256 if plan is not None else "replay-only"
                        ),
                        "pack_index": pack_index,
                        "infrastructure": [
                            {"outcome": "attestation_failed", "detail": detail}
                        ],
                        "jobs": records,
                    },
                )
            failed_ids = sorted(
                failure.split(":", 1)[0] for failure in failures
            )
            print("CI_PACK_FAILED_JOBS=" + json.dumps(failed_ids), flush=True)
            return 1
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
                current_dependency = dependency
                dependency_error = None
                try:
                    command_env = _dependency_environment(
                        dependency,
                        changed_files_file=changed_files_file,
                    )
                except Exception as exc:  # noqa: BLE001 — evidence must survive
                    dependency_error = _bounded_detail(exc)
            if dependency_error is not None:
                execution = _blocked_job_execution(
                    job,
                    infrastructure_outcome="dependency_failed",
                    detail=dependency_error,
                )
            else:
                try:
                    execution = _coerce_job_execution(
                        job,
                        _run_job(
                            job,
                            base_ref=base_ref,
                            head_ref=head_ref,
                            command_env=command_env,
                            tested_tree_sha=bound_tree_sha,
                        ),
                    )
                except Exception as exc:  # noqa: BLE001 — complete accounting
                    execution = _blocked_job_execution(
                        job,
                        infrastructure_outcome=(
                            "timed_out"
                            if isinstance(
                                exc,
                                (TimeoutError, subprocess.TimeoutExpired),
                            )
                            else "unknown"
                        ),
                        detail=exc,
                    )
            failure = execution.failure
            records.append(execution.fragment_dict())
            if failure:
                failures.append(failure)
                # title=legacy-job-<id> is what merge_on_green parses for
                # live-inherited reds. The message still starts with job_id so
                # older parsers and the Actions log grep keep working.
                print(
                    f"::error title=legacy-job-{job.job_id}::{failure}",
                    flush=True,
                )
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
        try:
            _restore_workspace(bound_tree_sha)
        except Exception as exc:  # noqa: BLE001 — fragment still gets written
            detail = _bounded_detail(exc)
            failures.append(f"ci-pack: final workspace restore failed ({detail})")
            pack_infrastructure.append(
                {"outcome": "unknown", "detail": f"workspace restore: {detail}"}
            )

    if plan is not None and enable_base_replay and not os.environ.get(
        "CI_DISABLE_BASE_REPLAY"
    ):
        try:
            _run_exact_base_replays(
                root=root,
                plan=plan,
                records=records,
                budget_seconds=base_replay_budget_seconds,
            )
        except Exception as exc:  # noqa: BLE001 — head fragment must survive
            detail = _bounded_detail(exc)
            print(
                "::warning title=ci-base-replay::exact-base replay unavailable "
                f"({detail})",
                flush=True,
            )
            unavailable = _base_replay_unavailable(plan.base_sha, detail)
            for record in records:
                for step in record.get("steps", []):
                    if step.get("outcome") in {"failed", "timed_out"}:
                        step["base_replay"] = unavailable

    if emit_semantic_fragment is not None:
        if plan is not None:
            identity = {
                "workflow_run_id": plan.workflow_run_id,
                "workflow": plan.workflow,
                "event": plan.event,
                "role": plan.role,
                "tested_tree_sha": plan.tested_tree_sha,
                "subject_head_sha": plan.subject_head_sha,
                "base_sha": plan.base_sha,
                "plan_sha256": plan.plan_sha256,
            }
        else:
            tested = os.environ.get("CI_TESTED_TREE_SHA") or os.environ.get(
                "GITHUB_SHA", "unbound-tested-tree"
            )
            identity = {
                "workflow_run_id": os.environ.get("GITHUB_RUN_ID", "local"),
                "workflow": os.environ.get("GITHUB_WORKFLOW", "ci"),
                "event": os.environ.get("GITHUB_EVENT_NAME", "local"),
                "role": os.environ.get("CI_SEMANTIC_ROLE", "main"),
                "tested_tree_sha": tested,
                "subject_head_sha": os.environ.get("CI_SUBJECT_HEAD_SHA", tested),
                "base_sha": os.environ.get("CI_BASE_SHA", tested),
                "plan_sha256": "replay-only",
            }
        fragment = {
            "schema": FRAGMENT_SCHEMA,
            **identity,
            "pack_index": pack_index,
            "infrastructure": pack_infrastructure,
            "jobs": records,
        }
        _write_semantic_fragment(emit_semantic_fragment, fragment)

    failed_ids = sorted(
        {failure.split(":", 1)[0] for failure in failures if ":" in failure}
    )
    print("CI_PACK_FAILED_JOBS=" + json.dumps(failed_ids), flush=True)
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
    parser.add_argument(
        "--gate",
        choices=GATE_VALUES,
        default=None,
        help=(
            "filter the manifest to jobs declaring this gate value before "
            "selection/partition; absent runs the whole manifest as before "
            "this flag existed (research/CI_MERGE_GATE_RELIABILITY_ROOT_CAUSE_"
            "2026_08_19.md W2)"
        ),
    )
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument(
        "--plan-json",
        type=Path,
        default=None,
        help=(
            "consume this authoritative ci.pack_plan.v2 artifact; selection and "
            "partition are never recomputed in this mode"
        ),
    )
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
        "--emit-changed-files",
        default=None,
        metavar="PATH",
        help=(
            "write the resolved changed-file list to this path as compact JSON, "
            "or the token 'null' when there is no list; parent directories are "
            "created. This file is the packs' transport — the list left the job "
            "outputs on 2026-08-14 because a 350,264-byte value exceeds execve's "
            "131,072-byte per-string cap"
        ),
    )
    parser.add_argument(
        "--changed-files-file",
        default=None,
        metavar="PATH",
        help=(
            "read the planner's changed-file list from this file instead of the "
            "process environment; defaults to $CI_CHANGED_FILES_FILE"
        ),
    )
    parser.add_argument(
        "--tracked-paths-file",
        default=None,
        metavar="PATH",
        help=(
            "planner-only handle containing the exact tested tree's tracked paths; "
            "preserves repository-existence semantics in a sparse ci-plan checkout"
        ),
    )
    parser.add_argument(
        "--expect-plan-sha",
        default=None,
        help="refuse to execute unless the authoritative plan has this sha256",
    )
    parser.add_argument("--tested-tree-sha", default=None)
    parser.add_argument("--subject-head-sha", default=None)
    parser.add_argument("--base-sha", default=None)
    parser.add_argument("--workflow-run-id", default=None)
    parser.add_argument("--workflow-name", default=None)
    parser.add_argument("--event", default=None)
    parser.add_argument("--role", choices=("pr_head", "main"), default=None)
    parser.add_argument("--expect-tested-tree-sha", default=None)
    parser.add_argument("--expect-subject-head-sha", default=None)
    parser.add_argument("--expect-base-sha", default=None)
    parser.add_argument(
        "--emit-semantic-fragment",
        type=Path,
        default=None,
        help="write the bounded raw ci.semantic_fragment.v1 pack artifact",
    )
    parser.add_argument(
        "--base-replay-budget-seconds",
        type=int,
        default=int(
            os.environ.get(
                "CI_BASE_REPLAY_BUDGET_SECONDS",
                str(DEFAULT_BASE_REPLAY_BUDGET_SECONDS),
            )
        ),
        help="one fail-closed serial budget shared by all exact-base replays",
    )
    parser.add_argument("--semantic-replay-job", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--disable-base-replay", action="store_true", help=argparse.SUPPRESS)
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
    if args.plan_json is not None and args.plan_only:
        parser.error("--plan-json consumes a plan and cannot pair with --plan-only")
    if args.tracked_paths_file is not None and not args.plan_only:
        parser.error("--tracked-paths-file is planner-only and requires --plan-only")
    if args.tracked_paths_file is not None and not args.tested_tree_sha:
        parser.error("--tracked-paths-file requires --tested-tree-sha")
    if args.semantic_replay_job and not args.execute:
        parser.error("--semantic-replay-job requires --execute")
    if args.semantic_replay_job and args.emit_semantic_fragment is None:
        parser.error("--semantic-replay-job requires --emit-semantic-fragment")
    if args.base_replay_budget_seconds < 1:
        parser.error("--base-replay-budget-seconds must be positive")
    if not 0 <= args.pack_index < args.pack_count:
        parser.error("--pack-index must be between 0 and pack-count - 1")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.semantic_replay_job:
            jobs = load_legacy_jobs(args.workflow)
            target = next(
                (job for job in jobs if job.job_id == args.semantic_replay_job),
                None,
            )
            tested = args.tested_tree_sha or os.environ.get("GITHUB_SHA") or ""
            if target is None:
                _write_semantic_fragment(
                    args.emit_semantic_fragment,
                    {
                        "schema": FRAGMENT_SCHEMA,
                        "workflow_run_id": args.workflow_run_id or "local",
                        "workflow": args.workflow_name or "ci",
                        "event": args.event or "base_replay",
                        "role": args.role or "main",
                        "tested_tree_sha": tested,
                        "subject_head_sha": args.subject_head_sha or tested,
                        "base_sha": args.base_sha or tested,
                        "plan_sha256": "replay-only",
                        "pack_index": 0,
                        "infrastructure": [],
                        "job_present": False,
                        "jobs": [],
                    },
                )
                return 0
            identity_env = {
                "CI_TESTED_TREE_SHA": tested,
                "CI_SUBJECT_HEAD_SHA": args.subject_head_sha or tested,
                "CI_BASE_SHA": args.base_sha or tested,
                "CI_SEMANTIC_ROLE": args.role or "main",
                "GITHUB_RUN_ID": args.workflow_run_id or "local",
                "GITHUB_WORKFLOW": args.workflow_name or "ci",
                "GITHUB_EVENT_NAME": args.event or "base_replay",
            }
            os.environ.update(identity_env)
            return execute_pack(
                [target],
                pack_index=0,
                emit_semantic_fragment=args.emit_semantic_fragment,
                enable_base_replay=False,
                # parse_args already requires --emit-semantic-fragment here,
                # so this replay always mints evidence and always attests —
                # cheaply, since it runs on the same already-attested runner
                # as the pack invocation that spawned it.
                require_attestation=True,
            )

        changed_handle = args.changed_files_file or os.environ.get(
            "CI_CHANGED_FILES_FILE"
        )
        if args.plan_json is not None:
            plan = load_authoritative_plan(
                args.plan_json,
                workflow=args.workflow,
                changed_files_file=changed_handle,
                expect_plan_sha=args.expect_plan_sha,
                expect_tested_tree_sha=args.expect_tested_tree_sha,
                expect_subject_head_sha=args.expect_subject_head_sha,
                expect_base_sha=args.expect_base_sha,
                gate=args.gate,
            )
        else:
            plan = plan_from_workflow(
                args.workflow,
                changed_from=args.changed_from,
                scope_mode=args.scope_mode,
                pack_count=args.pack_count,
                changed_files_file=args.changed_files_file,
                tracked_paths_file=args.tracked_paths_file,
                workflow_run_id=args.workflow_run_id,
                workflow_name=args.workflow_name,
                event=args.event,
                role=args.role,
                tested_tree_sha=args.tested_tree_sha,
                subject_head_sha=args.subject_head_sha,
                base_sha=args.base_sha,
                gate=args.gate,
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
        # Legacy/unpinned callers can still build locally; production packs
        # consume --plan-json above and never recompute selection or partition.
        if args.expect_plan_sha and args.expect_plan_sha != plan.plan_sha256:
            # NAME THE CHANGED-FILE HANDLE FIRST (2026-08-14). Since
            # `changed_files_sha256` entered the hashed payload, the most likely
            # cause of a parity failure is no longer a manifest that drifted
            # between two runners — it is the `ci-changed-files` artifact that
            # failed to download, landed truncated, or was swapped. The parity
            # check is the GATE; this line is the diagnosis, because "recomputed
            # X but ci-plan published Y" alone sends an operator hunting through
            # a 192-job manifest for a difference that is in a file.
            handle = args.changed_files_file or os.environ.get(
                "CI_CHANGED_FILES_FILE"
            )
            state, paths = _read_changed_files_handle(handle)
            print(
                f"::error title=ci-changed-files::pack {args.pack_index} planned "
                f"from {plan.changed_files_count} changed path(s) "
                f"({plan.changed_files_sha256[:16] or 'no list'}) read as {state} "
                f"from {handle or '$CI_CHANGED_FILES_FILE (unset)'}"
                + (f" carrying {len(paths)} path(s)" if state == "list" else ""),
                flush=True,
            )
            print(
                "::error title=ci-plan-parity::pack "
                f"{args.pack_index} loaded plan {plan.plan_sha256} but ci-plan "
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
            plan=plan,
            pack_index=args.pack_index,
            emit_semantic_fragment=args.emit_semantic_fragment,
            enable_base_replay=(
                args.plan_json is not None and not args.disable_base_replay
            ),
            base_replay_budget_seconds=args.base_replay_budget_seconds,
            changed_files_file=changed_handle,
            # Attest only when this run consumes an authoritative plan
            # (--plan-json) or mints a semantic fragment
            # (--emit-semantic-fragment) — the two cases that publish
            # evidence downstream. A bare local `--execute` (neither flag)
            # stays unattested: it mints no semantic evidence, so there is
            # nothing for a wrong runtime to falsely certify.
            require_attestation=(
                args.plan_json is not None or args.emit_semantic_fragment is not None
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
        # A pinned pack may fail before it can materialize a replacement plan
        # when the changed-file artifact is missing or malformed. Preserve the
        # established operator-facing parity receipts in that earlier refusal
        # path: the expected plan still exists, but this runner cannot prove the
        # changed-file input needed to reconstruct it. This is diagnostic only;
        # the exception below remains the fail-closed gate.
        if args.expect_plan_sha:
            handle = args.changed_files_file or os.environ.get(
                "CI_CHANGED_FILES_FILE"
            )
            state, paths = _read_changed_files_handle(handle)
            if state not in {"list", "null"}:
                print(
                    f"::error title=ci-changed-files::pack {args.pack_index} "
                    f"could not reconstruct the published plan; changed paths "
                    f"read as {state} from "
                    f"{handle or '$CI_CHANGED_FILES_FILE (unset)'}"
                    + (f" carrying {len(paths)} path(s)" if state == "list" else ""),
                    flush=True,
                )
                print(
                    "::error title=ci-plan-parity::pack "
                    f"{args.pack_index} could not verify published plan "
                    f"{args.expect_plan_sha}; refusing before legacy execution",
                    flush=True,
                )
        if isinstance(
            exc,
            (
                ManifestError,
                RuntimeError,
                SemanticProofError,
                subprocess.CalledProcessError,
            ),
        ):
            print(f"ci-pack validation/execution failed: {exc}", file=sys.stderr)
            return 2
        raise


if __name__ == "__main__":
    raise SystemExit(main())
