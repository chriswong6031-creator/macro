#!/usr/bin/env python3
"""Cheap, immutable-path structural admission check for pull-request CI.

The expensive CI planner derives transitive ownership for the whole legacy
manifest.  Admission needs a smaller question first: is the submitted tree
structurally safe enough to spend runners on?  This command consumes an exact
changed-path list supplied by the caller; it never discovers a mutable diff.

It deliberately reuses the repository's existing validators and policies:

* ``run_ci_pack.load_legacy_jobs`` validates the packed legacy manifest;
* ``check_workflow_yaml.check_file`` validates workflow parse/top-level shape;
* ``audit_unrun_tests.defines_tests`` distinguishes real pytest suites from
  test-shaped command-line instruments;
* ``workflow_run_source.resolve_run_source`` keeps extracted shell bodies
  visible to the wiring census; and
* ``check_conflict_markers.scan_file`` owns conflict-marker semantics.

Only changed tests/workflows and small CI metadata need to be materialized.
Other changed files are classified from their immutable paths and scanned for
conflict markers when the sparse checkout materialized them.

Examples:
    python scripts/ci_structural_preflight.py \
      --changed-path tests/test_example.py --changed-path engine/example.py
    python scripts/ci_structural_preflight.py \
      --changed-paths-file "$RUNNER_TEMP/changed-paths.json"

The command writes exactly one compact JSON object to stdout.  Exit 0 is clean,
exit 1 is a structural/configuration refusal, and exit 2 is invalid input.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Iterator

import yaml

# Pin repository imports for direct execution from any working directory.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.audit_unrun_tests import (  # noqa: E402
    _named_by_a_run_step,
    defines_tests,
)
from scripts.check_conflict_markers import (  # noqa: E402
    _looks_binary,
    scan_file,
)
from scripts.check_workflow_yaml import check_file as check_workflow_file  # noqa: E402
from scripts.run_ci_pack import (  # noqa: E402
    GLOBAL_INVALIDATORS,
    OPAQUE_IO_ROOTS,
    PASSIVE_UNOWNED_PATTERNS,
    SCOPE_REFERENCE_RE,
    ManifestError,
    _matches_any,
    load_legacy_jobs,
    partition_jobs,
)
from scripts.workflow_run_source import (  # noqa: E402
    WorkflowRunSourceError,
    resolve_run_source,
)


SCHEMA = "ci.structural_preflight.v1"
CI_WORKFLOW = ".github/workflows/ci.yml"
CI_MANIFEST = ".github/ci/legacy-jobs.yml"
PACK_COUNT = 12

_TEST_NAME = re.compile(r"^(?:test_.+|.+_test)\.py$")
_WORKFLOW_PATH = re.compile(r"^\.github/workflows/[^/]+\.ya?ml$")
_EXECUTABLE_SUFFIXES = frozenset(
    {
        ".bash",
        ".cjs",
        ".go",
        ".js",
        ".jsx",
        ".mjs",
        ".py",
        ".rb",
        ".rs",
        ".sh",
        ".ts",
        ".tsx",
        ".zsh",
    }
)

# ``*`` is intentionally excluded: it would make every new root-level program
# look configured.  The remaining patterns are the planner's explicit,
# established repository surfaces.  A new executable root must first be added
# to planner metadata or claimed by a manifest job.
_ESTABLISHED_SURFACES = tuple(pattern for pattern in OPAQUE_IO_ROOTS if pattern != "*")


def _finding(
    code: str,
    classification: str,
    message: str,
    *,
    path: str | None = None,
) -> dict[str, str]:
    item = {
        "classification": classification,
        "code": code,
        "message": " ".join(str(message).split()),
    }
    if path is not None:
        item["path"] = path
    return item


def _normalize_paths(raw_paths: Iterable[str]) -> list[str]:
    normalized: list[str] = []
    for raw in raw_paths:
        if not isinstance(raw, str):
            raise ValueError("changed paths must be strings")
        candidate = raw.strip().replace("\\", "/")
        if not candidate:
            raise ValueError("changed paths must be non-empty strings")
        path = PurePosixPath(candidate)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError(
                f"changed path {raw!r} must be repository-relative and contain no '..'"
            )
        rendered = path.as_posix()
        if rendered == ".":
            raise ValueError("changed path '.' is not a file")
        normalized.append(rendered)
    return list(dict.fromkeys(normalized))


def _read_paths_file(path: str) -> list[str]:
    text = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    stripped = text.strip()
    if not stripped:
        return []
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        # A newline file is convenient for gh-api pagination output while JSON
        # remains the canonical ci-plan artifact representation.
        return [line for line in (line.strip() for line in text.splitlines()) if line]
    if isinstance(payload, dict):
        payload = payload.get("paths")
    if not isinstance(payload, list) or not all(isinstance(item, str) for item in payload):
        raise ValueError(
            "changed-paths file must contain a JSON string array, a {paths: [...]} "
            "object, or one path per line"
        )
    return payload


def _is_test_candidate(rel: str) -> bool:
    path = PurePosixPath(rel)
    return bool(path.parts and path.parts[0] == "tests" and _TEST_NAME.match(path.name))


def _is_workflow(rel: str) -> bool:
    return bool(_WORKFLOW_PATH.match(rel))


def _git_head_contains(root: Path, rel: str) -> bool | None:
    """Whether HEAD carries ``rel``; None means this is not a Git checkout."""
    try:
        completed = subprocess.run(
            [
                "git", "-C", str(root), "ls-tree", "-z", "--name-only",
                "--full-tree", "HEAD", "--", rel,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode == 0:
        names = completed.stdout.decode("utf-8", "replace").split("\0")
        return rel in names
    if b"not a git repository" in completed.stderr.lower():
        return None
    return None


@contextlib.contextmanager
def _submitted_file(root: Path, rel: str) -> Iterator[Path | None]:
    """Yield a changed HEAD file without requiring it in the sparse worktree."""
    materialized = root / rel
    if materialized.is_file():
        yield materialized
        return
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), "show", f"HEAD:{rel}"],
            capture_output=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        yield None
        return
    if completed.returncode != 0:
        yield None
        return
    with tempfile.TemporaryDirectory(prefix="ci-preflight-blob-") as directory:
        temporary = Path(directory) / PurePosixPath(rel).name
        temporary.write_bytes(completed.stdout)
        yield temporary


def _tracked_test_inventory(root: Path, changed: Iterable[str]) -> list[str]:
    """Test-shaped paths from Git metadata, without materializing the test tree."""
    names: list[str] = []
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z", "--", "tests"],
            capture_output=True,
            check=True,
            timeout=10,
        )
        names = [
            item
            for item in completed.stdout.decode("utf-8", "replace").split("\0")
            if item
        ]
    except (OSError, subprocess.SubprocessError):
        tests_root = root / "tests"
        if tests_root.is_dir():
            names = [
                path.relative_to(root).as_posix()
                for path in tests_root.rglob("*.py")
                if path.is_file()
            ]
    names.extend(rel for rel in changed if _is_test_candidate(rel))
    return sorted(
        {
            rel
            for rel in names
            if _is_test_candidate(rel)
        }
    )


def _legacy_run_blob(jobs: Iterable[Any], root: Path) -> tuple[str, list[str]]:
    chunks: list[str] = []
    errors: list[str] = []
    for job in jobs:
        for step in job.definition.get("steps", []):
            if not isinstance(step, dict) or not isinstance(step.get("run"), str):
                continue
            raw = step["run"]
            try:
                chunks.append(resolve_run_source(raw, root))
            except WorkflowRunSourceError as exc:
                errors.append(str(exc))
                # Preserve direct references in the original command so one
                # indirection error does not manufacture unrelated unwired rows.
                chunks.append(raw)
    return "\n".join(chunks), errors


def _manifest_reference_patterns(jobs: Iterable[Any], run_blob: str) -> tuple[str, ...]:
    patterns: set[str] = set()
    for job in jobs:
        patterns.update(job.paths)
    for raw in SCOPE_REFERENCE_RE.findall(run_blob):
        patterns.add(raw.split("::", 1)[0].rstrip(".,;:'\")"))
    return tuple(sorted(patterns))


def _is_executable(root: Path, rel: str) -> bool:
    if PurePosixPath(rel).suffix.lower() in _EXECUTABLE_SUFFIXES:
        return True
    path = root / rel
    try:
        return bool(path.stat().st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))
    except OSError:
        return False


def _is_controlled_text(root: Path, rel: str) -> bool:
    if _matches_any(PASSIVE_UNOWNED_PATTERNS, rel):
        return False
    return (
        _is_executable(root, rel)
        or _is_test_candidate(rel)
        or _is_workflow(rel)
        or _matches_any(GLOBAL_INVALIDATORS, rel)
        or _matches_any(_ESTABLISHED_SURFACES, rel)
    )


def _needs_values(value: object) -> tuple[tuple[str, ...], str | None]:
    if value is None:
        return (), None
    if isinstance(value, str) and value:
        return (value,), None
    if isinstance(value, list) and value and all(
        isinstance(item, str) and item for item in value
    ):
        return tuple(value), None
    return (), "needs must be a non-empty job id or list of job ids"


def _workflow_graph_findings(path: Path, rel: str) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return findings  # check_workflow_file owns the parse finding.
    if not isinstance(document, dict) or not isinstance(document.get("jobs"), dict):
        return findings

    jobs = document["jobs"]
    graph: dict[str, tuple[str, ...]] = {}
    for raw_job_id, definition in jobs.items():
        job_id = str(raw_job_id)
        if not isinstance(definition, dict):
            continue
        needs, error = _needs_values(definition.get("needs"))
        if error:
            findings.append(
                _finding(
                    "workflow_invalid_needs",
                    "planner_configuration_failure",
                    f"job {job_id!r} {error}",
                    path=rel,
                )
            )
            continue
        graph[job_id] = needs
        for dependency in needs:
            if dependency not in jobs:
                findings.append(
                    _finding(
                        "workflow_unknown_dependency",
                        "planner_configuration_failure",
                        f"job {job_id!r} needs unknown job {dependency!r}",
                        path=rel,
                    )
                )

    state: dict[str, int] = {}
    stack: list[str] = []
    reported_cycles: set[tuple[str, ...]] = set()

    def visit(job_id: str) -> None:
        state[job_id] = 1
        stack.append(job_id)
        for dependency in graph.get(job_id, ()):
            if dependency not in graph:
                continue
            if state.get(dependency, 0) == 0:
                visit(dependency)
            elif state.get(dependency) == 1:
                start = stack.index(dependency)
                cycle = tuple(stack[start:] + [dependency])
                if cycle not in reported_cycles:
                    reported_cycles.add(cycle)
                    findings.append(
                        _finding(
                            "workflow_dependency_cycle",
                            "planner_configuration_failure",
                            "job dependency cycle: " + " -> ".join(cycle),
                            path=rel,
                        )
                    )
        stack.pop()
        state[job_id] = 2

    for job_id in sorted(graph):
        if state.get(job_id, 0) == 0:
            visit(job_id)

    if rel == CI_WORKFLOW:
        required = {"ci-plan", "ci-pack", "ci-gate"}
        for missing in sorted(required - set(jobs)):
            findings.append(
                _finding(
                    "ci_admission_job_missing",
                    "planner_configuration_failure",
                    f"required admission job {missing!r} is missing",
                    path=rel,
                )
            )
        required_edges = {
            "ci-pack": {"ci-plan"},
            "ci-gate": {"ci-plan", "ci-pack"},
        }
        for job_id, dependencies in required_edges.items():
            if job_id not in graph:
                continue
            absent = dependencies - set(graph[job_id])
            if absent:
                findings.append(
                    _finding(
                        "ci_admission_edge_missing",
                        "planner_configuration_failure",
                        f"job {job_id!r} must need {', '.join(sorted(absent))}",
                        path=rel,
                    )
                )
        on_block = document[True] if True in document else document.get("on")
        if not isinstance(on_block, dict) or "pull_request" not in on_block:
            findings.append(
                _finding(
                    "ci_pull_request_trigger_missing",
                    "planner_configuration_failure",
                    "admission workflow must declare an on.pull_request trigger",
                    path=rel,
                )
            )
    return findings


def _status(findings: Iterable[dict[str, str]], codes: set[str]) -> str:
    return "fail" if any(item["code"] in codes for item in findings) else "pass"


def run_preflight(root: Path, changed_paths: Iterable[str]) -> dict[str, Any]:
    started = time.perf_counter()
    root = root.resolve()
    changed = _normalize_paths(changed_paths)
    findings: list[dict[str, str]] = []
    metrics: dict[str, int] = {
        "changed_tests_examined": 0,
        "changed_tests_wired": 0,
        "conflict_files_scanned": 0,
        "known_executable_paths": 0,
        "manifest_jobs": 0,
        "passive_paths": 0,
        "unowned_non_executable_paths": 0,
        "workflow_files_checked": 0,
    }

    manifest_path = root / CI_MANIFEST
    jobs: list[Any] = []
    old_cwd = Path.cwd()
    try:
        os.chdir(root)
        try:
            jobs = load_legacy_jobs(manifest_path)
            metrics["manifest_jobs"] = len(jobs)
            packs = partition_jobs(jobs, PACK_COUNT)
            flattened = [job.job_id for pack in packs for job in pack]
            expected = [job.job_id for job in jobs]
            if len(flattened) != len(set(flattened)) or sorted(flattened) != sorted(expected):
                findings.append(
                    _finding(
                        "manifest_pack_graph_invalid",
                        "planner_configuration_failure",
                        "legacy jobs do not partition into one complete disjoint pack graph",
                        path=CI_MANIFEST,
                    )
                )
        except (ManifestError, OSError, yaml.YAMLError) as exc:
            findings.append(
                _finding(
                    "manifest_invalid",
                    "planner_configuration_failure",
                    str(exc),
                    path=CI_MANIFEST,
                )
            )
    finally:
        os.chdir(old_cwd)

    run_blob = ""
    reference_patterns: tuple[str, ...] = ()
    if jobs:
        run_blob, source_errors = _legacy_run_blob(jobs, root)
        for message in source_errors:
            findings.append(
                _finding(
                    "manifest_run_source_unresolvable",
                    "planner_configuration_failure",
                    message,
                    path=CI_MANIFEST,
                )
            )
        reference_patterns = _manifest_reference_patterns(jobs, run_blob)

    workflow_paths = {CI_WORKFLOW}
    workflow_paths.update(rel for rel in changed if _is_workflow(rel))
    for rel in sorted(workflow_paths):
        with _submitted_file(root, rel) as path:
            if path is None:
                if rel == CI_WORKFLOW or _git_head_contains(root, rel) is True:
                    findings.append(
                        _finding(
                            "workflow_unreadable",
                            "planner_configuration_failure",
                            "workflow exists in the submitted tree but its HEAD blob could not be read",
                            path=rel,
                        )
                    )
                continue  # A changed workflow absent from HEAD was deleted.
            metrics["workflow_files_checked"] += 1
            workflow_problems = check_workflow_file(path)
            for problem in workflow_problems:
                findings.append(
                    _finding(
                        "workflow_invalid",
                        "planner_configuration_failure",
                        problem,
                        path=rel,
                    )
                )
            if not workflow_problems:
                findings.extend(_workflow_graph_findings(path, rel))

    inventory = _tracked_test_inventory(root, changed)
    basename_counts = Counter(rel.rsplit("/", 1)[-1] for rel in inventory)
    ambiguous = frozenset(name for name, count in basename_counts.items() if count > 1)
    for rel in sorted(path for path in changed if _is_test_candidate(path)):
        with _submitted_file(root, rel) as path:
            if path is None:
                if _git_head_contains(root, rel) is True:
                    findings.append(
                        _finding(
                            "changed_test_unreadable",
                            "planner_configuration_failure",
                            "changed test exists in the submitted tree but its HEAD blob could not be read",
                            path=rel,
                        )
                    )
                continue  # Deleted suite.
            if not defines_tests(path):
                continue
            metrics["changed_tests_examined"] += 1
            if run_blob and _named_by_a_run_step(rel, run_blob, ambiguous):
                metrics["changed_tests_wired"] += 1
            else:
                findings.append(
                    _finding(
                        "unwired_changed_test",
                        "pr_structural_failure",
                        "changed pytest suite is named by no run step in the legacy CI manifest",
                        path=rel,
                    )
                )

    for rel in changed:
        if _matches_any(PASSIVE_UNOWNED_PATTERNS, rel):
            metrics["passive_paths"] += 1
            continue
        executable = _is_executable(root, rel)
        known = (
            _matches_any(GLOBAL_INVALIDATORS, rel)
            or _matches_any(reference_patterns, rel)
            or _matches_any(_ESTABLISHED_SURFACES, rel)
        )
        if executable and known:
            metrics["known_executable_paths"] += 1
        elif executable:
            findings.append(
                _finding(
                    "unknown_executable_ownership",
                    "planner_configuration_failure",
                    "executable path is outside every configured planner surface and manifest ownership pattern",
                    path=rel,
                )
            )
        elif not known:
            metrics["unowned_non_executable_paths"] += 1

        with _submitted_file(root, rel) as path:
            if path is None:
                if (
                    _git_head_contains(root, rel) is True
                    and _is_controlled_text(root, rel)
                ):
                    findings.append(
                        _finding(
                            "changed_blob_unreadable",
                            "planner_configuration_failure",
                            "changed controlled file exists in HEAD but its blob could not be read",
                            path=rel,
                        )
                    )
                continue
            if (
                not _is_controlled_text(root, rel)
                or _looks_binary(str(path))
            ):
                continue
            metrics["conflict_files_scanned"] += 1
            for lineno, line in scan_file(str(path)):
                findings.append(
                    _finding(
                        "conflict_marker",
                        "pr_structural_failure",
                        f"git conflict marker at line {lineno}: {line}",
                        path=rel,
                    )
                )

    findings.sort(key=lambda item: (item.get("path", ""), item["code"], item["message"]))
    classifications = sorted({item["classification"] for item in findings})
    if not classifications:
        classification = "clean"
    elif len(classifications) == 1:
        classification = classifications[0]
    else:
        classification = "multiple_failures"

    manifest_codes = {
        "manifest_invalid",
        "manifest_pack_graph_invalid",
        "manifest_run_source_unresolvable",
    }
    workflow_codes = {
        "ci_admission_edge_missing",
        "ci_admission_job_missing",
        "ci_pull_request_trigger_missing",
        "workflow_dependency_cycle",
        "workflow_invalid",
        "workflow_invalid_needs",
        "workflow_unreadable",
        "workflow_unknown_dependency",
    }
    test_codes = {"changed_test_unreadable", "unwired_changed_test"}
    ownership_codes = {"unknown_executable_ownership"}
    conflict_codes = {"changed_blob_unreadable", "conflict_marker"}
    return {
        "checks": {
            "changed_tests": {"status": _status(findings, test_codes)},
            "conflict_markers": {"status": _status(findings, conflict_codes)},
            "manifest_pack_graph": {"status": _status(findings, manifest_codes)},
            "ownership": {"status": _status(findings, ownership_codes)},
            "workflow_graph": {"status": _status(findings, workflow_codes)},
        },
        "changed_path_count": len(changed),
        "classification": classification,
        "classifications": classifications,
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "findings": findings,
        "metrics": metrics,
        "schema": SCHEMA,
        "status": "fail" if findings else "pass",
    }


def _input_failure(message: str) -> dict[str, Any]:
    return {
        "checks": {},
        "changed_path_count": 0,
        "classification": "input_failure",
        "classifications": ["input_failure"],
        "elapsed_ms": 0,
        "findings": [
            _finding("invalid_changed_paths", "input_failure", message)
        ],
        "metrics": {},
        "schema": SCHEMA,
        "status": "fail",
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--changed-path",
        action="append",
        default=[],
        help="exact repository-relative changed path; repeatable",
    )
    parser.add_argument(
        "--changed-paths-file",
        help="JSON array/object or newline path file; '-' reads stdin",
    )
    parser.add_argument("--root", default=".", help="repository checkout root")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        raw_paths = list(args.changed_path)
        if args.changed_paths_file is not None:
            raw_paths.extend(_read_paths_file(args.changed_paths_file))
        if not raw_paths and args.changed_paths_file is None:
            raise ValueError("provide --changed-path or --changed-paths-file")
        result = run_preflight(Path(args.root), raw_paths)
    except (OSError, ValueError) as exc:
        result = _input_failure(str(exc))
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
