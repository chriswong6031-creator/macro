#!/usr/bin/env python3
"""Run the legacy jobs in ``ci.yml`` using a small number of shared runners.

GitHub Actions used to provision one fresh VM for every job in ``ci.yml``.
The repository is large enough that checkout and interpreter setup dominated
the useful test work, so one PR fanned out to more than eighty hosted runners.

The workflow now keeps those legacy job definitions as an auditable manifest:
each one has ``if: ${{ false }}`` so GitHub never allocates it a runner.  The
``ci-pack`` matrix jobs call this script, which validates the manifest and
executes every legacy ``run`` step.  A hard reset/clean between legacy jobs
preserves their former clean-checkout isolation.  Jobs with different declared
pip dependencies also get freshly recreated virtual environments; only jobs
whose install commands are byte-identical share an environment.

The validator is intentionally fail-closed.  A future job using services,
containers, per-step conditions/environments, or an unfamiliar action must
teach this runner how to preserve that behavior before the workflow can pass.

Execution is refused outside GitHub Actions because workspace cleanup is
destructive by design.  Local callers can safely use ``--validate-only``.
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


PACK_JOB_ID = "ci-pack"
DISABLED_IF = "${{ false }}"
ALLOWED_JOB_KEYS = {"if", "runs-on", "steps", "timeout-minutes"}
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


class ManifestError(ValueError):
    """The legacy manifest cannot be executed without losing semantics."""


@dataclass(frozen=True)
class LegacyJob:
    """Validated legacy job plus its deterministic balancing weight."""

    job_id: str
    definition: dict[str, Any]
    ordinal: int
    weight: int


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
    """Load and fail-closed validate every non-pack job in the workflow."""
    jobs = _workflow_jobs(path)
    if PACK_JOB_ID not in jobs:
        raise ManifestError(f"{path} is missing the {PACK_JOB_ID!r} orchestration job")

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
        return execute_pack(selected)
    except (ManifestError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"ci-pack validation/execution failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
