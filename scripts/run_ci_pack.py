#!/usr/bin/env python3
"""Run the legacy CI manifest using a small number of shared runners.

GitHub Actions used to provision one fresh VM for every job in ``ci.yml``.
The repository is large enough that checkout and interpreter setup dominated
the useful test work, so one PR fanned out to more than eighty hosted runners.

The workflow now contains only the two real ``ci-pack`` matrix jobs. Legacy job
definitions live in ``.github/ci/legacy-jobs.yml`` so GitHub does not publish
roughly one hundred skipped check runs on every pull request. The pack jobs call
this script, which validates the manifest and executes every legacy ``run``
step. A hard reset/clean between legacy jobs preserves their former
clean-checkout isolation. Jobs with different declared pip dependencies also
get freshly recreated virtual environments; only jobs whose install commands
are byte-identical share an environment.

The validator is intentionally fail-closed.  A future job using services,
containers, per-step conditions/environments, or an unfamiliar action must
teach this runner how to preserve that behavior before the workflow can pass.

Execution is refused outside GitHub Actions because workspace cleanup is
destructive by design.  Local callers can safely use ``--validate-only``.

PATH SELECTION (``CI_SELECTIVE=1``) is deliberately built the SAFE way round.
A job may DECLARE the paths it measures; the only thing a declaration can do is
let that job be skipped when a pull request touches none of them.  Every safety
property falls out of one rule: **a job with no ``paths:`` key always runs.**

  * An unannotated job can never be skipped, so adding the mechanism changes
    nothing until someone deliberately annotates a job.
  * ``scripts/check_ci_pack_paths.py`` demands that a declaration COVER the
    resolved read-closure of everything the job runs.  That resolver
    under-reports by construction, so it can only ever ask for MORE entries —
    the failure direction is "you must declare more", never "you may skip more".
  * A diff we cannot compute (unresolvable ref, git failure, empty output) runs
    everything, and so does any change to the manifest, the selector, the shared
    matcher, ``tests/conftest.py``, ``config.yml`` or ``.github/workflows/**``:
    a change to the machinery invalidates the selection itself.
  * Selection is scoped to ``pull_request`` by ci.yml.  main / push / dispatch /
    schedule always run everything, because ``merge_on_green.main_proof`` reads
    main's ci.yml run to decide whether a pull request's red is base-side and a
    partial main proof would silently narrow that.

Selection happens AFTER the partition, never before.  Repartitioning the
surviving jobs would balance better, but it would also mean a pull request's
``ci-pack-2`` no longer holds the same jobs as main's ``ci-pack-2`` — and the
base-inherited-red refresh compares those checks BY NAME.  Skipping inside a
stable partition keeps every pull-request pack a strict SUBSET of main's pack of
the same name, so that comparison stays exactly as sound as it is today.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import yaml

try:  # imported as `scripts.run_ci_pack` (the test pack, and any other caller)
    from scripts.gh_path_filter import NEGATION_PREFIX, matched
except ImportError:  # run as `python3 scripts/run_ci_pack.py` (the workflow step)
    from gh_path_filter import NEGATION_PREFIX, matched  # type: ignore[no-redef]


PACK_JOB_ID = "ci-pack"
DISABLED_IF = "${{ false }}"
ALLOWED_JOB_KEYS = {"if", "paths", "runs-on", "steps", "timeout-minutes"}
ALLOWED_STEP_KEYS = {"name", "run", "uses", "with"}
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

# A change to any of these invalidates the SELECTION, not just a job: the
# manifest carries every declaration, the selector and the shared matcher decide
# what a declaration means, conftest is imported by every pytest job in the tree,
# and config.yml is read by most engines. `.github/workflows/**` is here because
# ci.yml carries both the pack step and its own `on.pull_request.paths` gate — a
# pull request that rewrites how CI starts must be measured by all of it.
ALWAYS_RUN_TRIGGERS = (
    "tests/conftest.py",
    "config.yml",
    ".github/ci/legacy-jobs.yml",
    "scripts/run_ci_pack.py",
    "scripts/gh_path_filter.py",
    ".github/workflows/**",
)
SELECTION_ENV = "CI_SELECTIVE"


class ManifestError(ValueError):
    """The legacy manifest cannot be executed without losing semantics."""


@dataclass(frozen=True)
class LegacyJob:
    """Validated legacy job plus its deterministic balancing weight."""

    job_id: str
    definition: dict[str, Any]
    ordinal: int
    weight: int

    @property
    def declared_paths(self) -> list[str]:
        """The job's own `paths:` entries, or ``[]`` when it declares none.

        Empty means UNANNOTATED, which means unskippable.  That is the whole
        safety property, so it is spelled here rather than at every call site.
        """
        declared = self.definition.get("paths")
        return [str(entry) for entry in declared] if declared else []


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

        if "paths" in raw_definition:
            declared = raw_definition["paths"]
            if not isinstance(declared, list) or not declared:
                findings.append(
                    f"{prefix} paths must be a non-empty list of patterns; omit "
                    "the key entirely to keep the job unskippable"
                )
            else:
                for entry in declared:
                    if not isinstance(entry, str) or not entry.strip():
                        findings.append(
                            f"{prefix} paths entry {entry!r} must be a non-empty string"
                        )
                    elif entry.startswith(NEGATION_PREFIX):
                        # gh_path_filter does not model `!` exclusions, and a
                        # mis-evaluated negation is exactly the silent-skip this
                        # design exists to prevent.  Refuse rather than guess.
                        findings.append(
                            f"{prefix} paths entry {entry!r} uses a `!` negation, "
                            "which the shared matcher does not model"
                        )

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

        legacy.append(
            LegacyJob(
                job_id=str(job_id),
                definition=raw_definition,
                ordinal=ordinal,
                weight=_job_weight(str(job_id), raw_definition),
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


# ─────────────────────────────────────────────────────────────────────────────
# path selection — fail-closed in every direction
# ─────────────────────────────────────────────────────────────────────────────

def selection_enabled(environ: dict[str, str] | None = None) -> bool:
    """Selection is OFF unless a caller explicitly turns it on.

    ci.yml sets ``CI_SELECTIVE=1`` for `pull_request` events only.  Unset, empty
    or `0` — every push, dispatch and schedule, and every local invocation —
    runs the full pack.
    """
    env = os.environ if environ is None else environ
    return env.get(SELECTION_ENV, "") == "1"


def _git_stdout(args: list[str]) -> str | None:
    """``None`` on ANY git failure, so every caller degrades to "run it all"."""
    try:
        result = subprocess.run(
            ["git", *args], capture_output=True, text=True, timeout=120
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode:
        return None
    return result.stdout


def _resolve_ref(candidates: Iterable[str]) -> str | None:
    for candidate in candidates:
        if not candidate:
            continue
        if _git_stdout(["rev-parse", "--verify", "--quiet", f"{candidate}^{{commit}}"]):
            return candidate
    return None


def changed_files(base_ref: str, head_ref: str) -> list[str] | None:
    """Files this pull request changes, or ``None`` when that is UNKNOWABLE.

    ``None`` is not "nothing changed" — it is "no honest answer", and every
    caller must then run the full pack.  Both refs are tried under their remote
    spelling first: a `pull_request` checkout is a detached HEAD at the merge
    ref, so `origin/main` resolves where a bare `main` often does not, and the
    head branch may exist under no local name at all (hence the `HEAD` fallback,
    which on that checkout IS the head under test).
    """
    base = _resolve_ref([f"origin/{base_ref}", base_ref])
    head = _resolve_ref([head_ref, f"origin/{head_ref}", "HEAD"])
    if base is None or head is None:
        return None
    out = _git_stdout(["diff", "--name-only", f"{base}...{head}"])
    if out is None:
        return None
    files = [line.strip() for line in out.splitlines() if line.strip()]
    # An empty diff against a resolvable base is indistinguishable here from a
    # base that is simply wrong (a shallow clone whose merge-base is HEAD), and
    # the wrong reading skips everything.  Refuse it.
    return files or None


def always_run_reason(changed: Iterable[str]) -> str | None:
    """The first changed file that invalidates selection itself, if any."""
    for rel in changed:
        for trigger in ALWAYS_RUN_TRIGGERS:
            if matched(rel, [trigger]):
                return f"{rel} (matches {trigger})"
    return None


def select_jobs(
    jobs: Iterable[LegacyJob], changed: Iterable[str]
) -> tuple[list[LegacyJob], list[LegacyJob]]:
    """Split ``jobs`` into (run, skipped) for this changed-file set.

    A job is skipped ONLY when it declares a non-empty `paths:` list and no
    changed file matches any entry.  Everything else runs.
    """
    changed = list(changed)
    run: list[LegacyJob] = []
    skipped: list[LegacyJob] = []
    for job in jobs:
        declared = job.declared_paths
        if declared and not any(matched(rel, declared) for rel in changed):
            skipped.append(job)
        else:
            run.append(job)
    return run, skipped


def announce_selection(
    selected: list[LegacyJob], skipped: list[LegacyJob], *, total_weight: int
) -> None:
    """Print the skip decision where GitHub can actually see it.

    Bare `print` at column 0 with `flush`, never a logger: every builder here
    logs with a prefixing format, so a logged `::notice` emits `INFO ::notice`
    and GitHub silently drops it (CLAUDE.md).  A silent skip is indistinguishable
    from a job that never existed, which is precisely the darkness this whole
    mechanism must not create.
    """
    saved = sum(job.weight for job in skipped)
    share = f"{saved * 100 / total_weight:.1f}%" if total_weight else "0.0%"
    print(
        f"::notice title=ci-pack-selection::path selection ON: running "
        f"{len(selected)} job(s), skipping {len(skipped)}; estimated weight "
        f"saved {saved} of {total_weight} ({share}) in this pack",
        flush=True,
    )
    if skipped:
        names = ", ".join(f"{job.job_id}({job.weight})" for job in skipped)
        print(f"::notice title=ci-pack-skipped::{names}", flush=True)


def apply_selection(pack: list[LegacyJob]) -> list[LegacyJob]:
    """Return the jobs this pack should actually run, announcing every skip."""
    total_weight = sum(job.weight for job in pack)
    if not selection_enabled():
        print(
            "::notice title=ci-pack-selection::path selection OFF "
            f"({SELECTION_ENV} is not 1) — running every job in this pack",
            flush=True,
        )
        return pack

    base_ref = os.environ.get("CI_BASE_REF", "main")
    head_ref = os.environ.get("CI_HEAD_REF", "")
    changed = changed_files(base_ref, head_ref)
    if changed is None:
        print(
            "::notice title=ci-pack-selection::path selection ON but the diff "
            f"{base_ref}...{head_ref or 'HEAD'} is unavailable — running every "
            "job in this pack",
            flush=True,
        )
        return pack

    reason = always_run_reason(changed)
    if reason is not None:
        print(
            "::notice title=ci-pack-selection::path selection ON but this pull "
            f"request changes {reason} — running every job in this pack",
            flush=True,
        )
        return pack

    selected, skipped = select_jobs(pack, changed)
    announce_selection(selected, skipped, total_weight=total_weight)
    return selected


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


def execute_pack(jobs: list[LegacyJob]) -> int:
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
    args = parser.parse_args(argv)
    if args.execute and args.validate_only:
        parser.error("--execute and --validate-only are mutually exclusive")
    if not 0 <= args.pack_index < args.pack_count:
        parser.error("--pack-index must be between 0 and pack-count - 1")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        legacy = load_legacy_jobs(args.workflow)
        packs = partition_jobs(legacy, args.pack_count)
        selected = packs[args.pack_index]
        weights = [sum(job.weight for job in pack) for pack in packs]
        print(
            f"Validated {len(legacy)} legacy jobs; pack weights={weights}; "
            f"selected pack {args.pack_index} ({len(selected)} jobs)."
        )
        print("Selected jobs: " + ", ".join(job.job_id for job in selected))
        if args.validate_only or not args.execute:
            return 0
        # Selection runs on the PARTITIONED pack, never before the partition —
        # see the module docstring: pull-request pack N must stay a subset of
        # main's pack N or the base-inherited-red refresh compares two different
        # job sets under one check name.
        return execute_pack(apply_selection(selected))
    except (ManifestError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"ci-pack validation/execution failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
