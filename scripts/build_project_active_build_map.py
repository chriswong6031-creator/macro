"""Build the advisory active-build map for the three-repository project.

This complements, and does not replace, ``build_active_build_map.py``.  The
existing map remains Macro's detailed local air-traffic-control view; this map
shows only the project-wide coordination surface across Macro, Terminal, and
Mastermind.

The normal mode collects live pull-request state through ``gh``.  A supplied
snapshot can instead be compiled and rendered without any network access::

    python -m scripts.build_project_active_build_map
    python -m scripts.build_project_active_build_map --snapshot-in snapshot.json

ADVISORY ONLY.  Nothing in this module is a merge, CI, deploy, or authority
gate.  If any live GitHub fetch fails, generation exits successfully without
touching either existing output artifact.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Any

log = logging.getLogger("build_project_active_build_map")

SCHEMA = "project_active_builds.v1"
SOURCE_SCHEMA = "project_active_builds.source.v1"
RECENT_MERGE_LIMIT = 50
OPEN_PR_LIMIT = 100
MAX_MERGED_DAYS = 90
_PARSE_ISO_TIMESTAMP = datetime.fromisoformat
_MERGE_STATES = frozenset(
    {"BEHIND", "BLOCKED", "CLEAN", "DIRTY", "DRAFT", "HAS_HOOKS", "UNKNOWN", "UNSTABLE"}
)

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_JSON_OUT = _REPO_ROOT / "data" / "governance" / "project_active_builds.json"
_DEFAULT_MD_OUT = _REPO_ROOT / "docs" / "PROJECT_ACTIVE_BUILD_MAP.md"


@dataclass(frozen=True)
class RepositorySpec:
    key: str
    repository: str
    base_branch: str
    protected_globs: tuple[str, ...]


# This tuple is the project boundary.  Adding a fourth repository is a schema
# decision, not an incidental discovery made by a GitHub query.
REPOSITORIES: tuple[RepositorySpec, ...] = (
    RepositorySpec(
        key="macro",
        repository="mastermindx-market-intelligence/macro",
        base_branch="main",
        protected_globs=(
            ".github/workflows/**",
            ".github/ci/**",
            "config/dag.yml",
            "config/synapse.yml",
            "docs/SIGNAL_BUS.md",
            "scripts/check_*.py",
            "engine/validation.py",
            "engine/trial_ledger.py",
            "engine/promotion_gate.py",
            "engine/neuralweb/**",
            "engine/research_factory/**",
            "app/deploy/**",
            "data/trial_ledger.jsonl",
            "data/governance/**",
            "site/neuralwebdata/**",
        ),
    ),
    RepositorySpec(
        key="terminal",
        repository="mastermindx-market-intelligence/mastermind-terminal",
        base_branch="master",
        protected_globs=(
            ".github/workflows/**",
            "contracts/**",
            "ops/**",
            "terminal/middleware.ts",
            "terminal/app/api/auth/**",
            "terminal/app/api/billing/**",
            "terminal/lib/auth*",
            "terminal/lib/supabase*",
            "supabase/**",
            "package.json",
            "package-lock.json",
            "terminal/package.json",
            "terminal/package-lock.json",
        ),
    ),
    RepositorySpec(
        key="mastermind",
        repository="mastermindx-market-intelligence/Mastermind",
        base_branch="master",
        protected_globs=(
            ".github/workflows/**",
            "config/**",
            "control_plane/**",
            "ops/**",
            "scripts/deploy*.sh",
            "scripts/export_macro_snapshot.py",
            "bridge/**",
            "app/auth.py",
            "brain/provider_waterfall.py",
            "portfolio/firm_exposure.py",
            "portfolio/marks.py",
        ),
    ),
)

_SPECS_BY_REPOSITORY = {spec.repository.lower(): spec for spec in REPOSITORIES}
_REPOSITORY_ORDER = {spec.repository: index for index, spec in enumerate(REPOSITORIES)}
_REPOSITORY_ALIASES: dict[str, str] = {}
for _spec in REPOSITORIES:
    _REPOSITORY_ALIASES[_spec.key.lower()] = _spec.repository
    _REPOSITORY_ALIASES[_spec.repository.lower()] = _spec.repository
    _REPOSITORY_ALIASES[_spec.repository.rsplit("/", 1)[-1].lower()] = _spec.repository

_DEPENDENCY_LINE_RE = re.compile(
    r"\b(?:depends?\s+on|blocked\s+by|requires?|after|dependency|dependencies)\b",
    re.IGNORECASE,
)
_URL_PR_RE = re.compile(
    r"https?://github\.com/(?P<repo>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)/pull/(?P<number>\d+)",
    re.IGNORECASE,
)
_QUALIFIED_PR_RE = re.compile(
    r"(?<![A-Za-z0-9_.-])(?P<repo>(?:[A-Za-z0-9_.-]+/)?[A-Za-z0-9_.-]+)#(?P<number>\d+)",
    re.IGNORECASE,
)
_LOCAL_PR_RE = re.compile(r"(?<![A-Za-z0-9_/.-])#(?P<number>\d+)\b")

GhRunner = Callable[[list[str]], Any | None]


def is_protected_path(repository: str, file_path: str) -> bool:
    """Return whether *file_path* is advisory-protected in *repository*."""
    spec = _SPECS_BY_REPOSITORY.get(repository.lower())
    if spec is None:
        raise ValueError(f"repository is outside the project boundary: {repository}")
    normalized = file_path.lstrip("/")
    return any(fnmatch.fnmatch(normalized, pattern.lstrip("/")) for pattern in spec.protected_globs)


def _canonical_repository(alias: str) -> str | None:
    return _REPOSITORY_ALIASES.get(alias.lower())


def extract_dependencies(body: str, current_repository: str) -> list[dict[str, Any]]:
    """Extract explicit project-PR dependencies from dependency-bearing lines.

    Ordinary issue/PR mentions are intentionally ignored.  A line must say it
    depends on, is blocked by, requires, or follows another PR.  Only the three
    repositories in ``REPOSITORIES`` are admitted.
    """
    canonical_current = _canonical_repository(current_repository)
    if canonical_current is None:
        raise ValueError(f"repository is outside the project boundary: {current_repository}")

    found: set[tuple[str, int]] = set()
    for line in (body or "").splitlines():
        if not _DEPENDENCY_LINE_RE.search(line):
            continue

        scrubbed = line
        for match in _URL_PR_RE.finditer(line):
            repository = _canonical_repository(match.group("repo"))
            if repository is not None:
                found.add((repository, int(match.group("number"))))
        scrubbed = _URL_PR_RE.sub(" ", scrubbed)

        for match in _QUALIFIED_PR_RE.finditer(scrubbed):
            repository = _canonical_repository(match.group("repo"))
            if repository is not None:
                found.add((repository, int(match.group("number"))))
        scrubbed = _QUALIFIED_PR_RE.sub(" ", scrubbed)

        for match in _LOCAL_PR_RE.finditer(scrubbed):
            found.add((canonical_current, int(match.group("number"))))

    return [
        {"repo": repository, "pr": number, "source": "pr_body"}
        for repository, number in sorted(
            found,
            key=lambda item: (_REPOSITORY_ORDER[item[0]], item[1]),
        )
    ]


def compute_file_collisions(open_prs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Compute deterministic, same-repository file collisions."""
    collisions: list[dict[str, Any]] = []
    by_repository: dict[str, list[dict[str, Any]]] = {
        spec.repository: [] for spec in REPOSITORIES
    }
    for pr in open_prs:
        repository = pr["repo"]
        if repository not in by_repository:
            raise ValueError(f"repository is outside the project boundary: {repository}")
        by_repository[repository].append(pr)

    for spec in REPOSITORIES:
        repository_prs = sorted(by_repository[spec.repository], key=lambda pr: pr["number"])
        for index, pr_a in enumerate(repository_prs):
            files_a = set(pr_a.get("files", []))
            for pr_b in repository_prs[index + 1 :]:
                shared_files = sorted(files_a & set(pr_b.get("files", [])))
                if not shared_files:
                    continue
                collisions.append(
                    {
                        "repo": spec.repository,
                        "pr_a": pr_a["number"],
                        "pr_b": pr_b["number"],
                        "shared_count": len(shared_files),
                        "shared_files": shared_files,
                        "protected_collision": any(
                            is_protected_path(spec.repository, path) for path in shared_files
                        ),
                    }
                )

    collisions.sort(
        key=lambda collision: (
            _REPOSITORY_ORDER[collision["repo"]],
            -collision["shared_count"],
            collision["pr_a"],
            collision["pr_b"],
        )
    )
    return collisions


def _validate_repository_boundary(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    repositories = snapshot.get("repositories")
    if not isinstance(repositories, list):
        raise TypeError("snapshot.repositories must be a list")

    expected = {(spec.repository, spec.base_branch) for spec in REPOSITORIES}
    actual: set[tuple[str, str]] = set()
    by_repository: dict[str, dict[str, Any]] = {}
    for repository in repositories:
        if not isinstance(repository, dict):
            raise TypeError("each repository snapshot must be an object")
        pair = (str(repository.get("repo", "")), str(repository.get("base_branch", "")))
        if pair in actual:
            raise ValueError(f"duplicate repository snapshot: {pair[0]}")
        actual.add(pair)
        by_repository[pair[0]] = repository
    if actual != expected:
        raise ValueError(
            "snapshot must contain exactly macro/main, terminal/master, and mastermind/master"
        )
    return by_repository


def _validate_utc_timestamp(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{context} must be a non-empty UTC timestamp")
    try:
        parsed = _PARSE_ISO_TIMESTAMP(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{context} must be an ISO-8601 UTC timestamp") from exc
    if parsed.utcoffset() != timedelta(0):
        raise ValueError(f"{context} must use UTC")
    return value


def _validate_sha(value: Any, context: str) -> str:
    if not isinstance(value, str) or len(value) != 40 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError(f"{context} must be a full lowercase 40-hex commit SHA")
    return value


def _validate_repo_path(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError(f"{context} must be a normalized repository-relative path")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or path.as_posix() != value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ValueError(f"{context} must be a normalized repository-relative path")
    return value


def _validate_fields(
    value: dict[str, Any],
    *,
    required: set[str],
    allowed: set[str],
    context: str,
) -> None:
    missing = required - set(value)
    unknown = set(value) - allowed
    if missing:
        raise ValueError(f"{context} is missing fields: {', '.join(sorted(missing))}")
    if unknown:
        raise ValueError(f"{context} has unknown fields: {', '.join(sorted(unknown))}")


def _positive_integer(value: Any, context: str) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{context} must be a positive integer")
    return value


def _boolean(value: Any, context: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{context} must be a boolean")
    return value


def _text(value: Any, context: str, *, allow_empty: bool = True) -> str:
    if not isinstance(value, str) or (not allow_empty and not value):
        requirement = "a string" if allow_empty else "a non-empty string"
        raise TypeError(f"{context} must be {requirement}")
    return value


def compile_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Compile a supplied source/final snapshot into canonical deterministic form."""
    if not isinstance(snapshot, dict):
        raise TypeError("snapshot must be an object")
    if snapshot.get("schema") not in {SOURCE_SCHEMA, SCHEMA}:
        raise ValueError(
            f"snapshot.schema must be {SOURCE_SCHEMA!r} or {SCHEMA!r}"
        )
    _validate_fields(
        snapshot,
        required={"schema", "merged_days", "repositories"},
        allowed={
            "schema",
            "collected_at",
            "generated_at",
            "merged_days",
            "repositories",
            "advisory_only",
            "gates",
            "file_collisions",
            "summary",
        },
        context="snapshot",
    )
    by_repository = _validate_repository_boundary(snapshot)
    collected_at = _validate_utc_timestamp(
        snapshot.get("collected_at") or snapshot.get("generated_at"),
        "snapshot.collected_at",
    )
    merged_days_raw = snapshot.get("merged_days", 14)
    if type(merged_days_raw) is not int or not 1 <= merged_days_raw <= MAX_MERGED_DAYS:
        raise ValueError(
            f"snapshot.merged_days must be an integer from 1 through {MAX_MERGED_DAYS}"
        )
    merged_days = merged_days_raw

    repositories: list[dict[str, Any]] = []
    all_open_prs: list[dict[str, Any]] = []
    all_recently_merged: list[dict[str, Any]] = []

    for spec in REPOSITORIES:
        source_repo = by_repository[spec.repository]
        _validate_fields(
            source_repo,
            required={"repo", "base_branch", "base_sha", "open_prs", "recently_merged"},
            allowed={
                "key",
                "repo",
                "base_branch",
                "base_sha",
                "open_prs_truncated",
                "recently_merged_truncated",
                "open_prs",
                "recently_merged",
            },
            context=f"repositories.{spec.key}",
        )
        source_open_prs = source_repo.get("open_prs", [])
        source_recent = source_repo.get("recently_merged", [])
        if not isinstance(source_open_prs, list) or not isinstance(source_recent, list):
            raise TypeError("open_prs and recently_merged must be lists")

        base_sha = _validate_sha(
            source_repo.get("base_sha"), f"repositories.{spec.key}.base_sha"
        )
        open_prs: list[dict[str, Any]] = []
        seen_open_numbers: set[int] = set()
        for source_pr in source_open_prs:
            if not isinstance(source_pr, dict):
                raise TypeError(f"repositories.{spec.key}.open_prs entries must be objects")
            _validate_fields(
                source_pr,
                required={"number", "title", "updated_at", "merge_state", "files"},
                allowed={
                    "repo",
                    "number",
                    "url",
                    "title",
                    "branch",
                    "head_ref",
                    "updated_at",
                    "draft",
                    "is_draft",
                    "merge_state",
                    "conflict",
                    "files_count",
                    "files_truncated",
                    "files",
                    "protected_paths",
                    "body",
                    "dependencies",
                },
                context=f"repositories.{spec.key}.open_prs",
            )
            number = _positive_integer(
                source_pr["number"], f"repositories.{spec.key}.open_prs.number"
            )
            if number in seen_open_numbers:
                raise ValueError(
                    f"repositories.{spec.key}.open_prs numbers must be positive and unique"
                )
            seen_open_numbers.add(number)
            raw_files = source_pr.get("files")
            if not isinstance(raw_files, list):
                raise TypeError(f"repositories.{spec.key}.open_prs[{number}].files must be a list")
            files = [
                _validate_repo_path(
                    path, f"repositories.{spec.key}.open_prs[{number}].files"
                )
                for path in raw_files
            ]
            if len(files) != len(set(files)):
                raise ValueError(
                    f"repositories.{spec.key}.open_prs[{number}].files contains duplicates"
                )
            files.sort()
            dependencies = source_pr.get("dependencies")
            if dependencies is None:
                body = _text(
                    source_pr.get("body", ""),
                    f"repositories.{spec.key}.open_prs[{number}].body",
                )
                dependencies = extract_dependencies(
                    body, spec.repository
                )
            else:
                if not isinstance(dependencies, list):
                    raise TypeError(
                        f"repositories.{spec.key}.open_prs[{number}].dependencies must be a list"
                    )
                normalized_dependencies: list[dict[str, Any]] = []
                seen_dependencies: set[tuple[str, int]] = set()
                for dependency in dependencies:
                    if not isinstance(dependency, dict):
                        raise TypeError("dependency entries must be objects")
                    _validate_fields(
                        dependency,
                        required={"repo", "pr"},
                        allowed={"repo", "pr", "source", "status"},
                        context=f"repositories.{spec.key}.open_prs[{number}].dependency",
                    )
                    dependency_repo = _canonical_repository(
                        _text(
                            dependency.get("repo"),
                            f"repositories.{spec.key}.open_prs[{number}].dependency.repo",
                            allow_empty=False,
                        )
                    )
                    dependency_pr = _positive_integer(
                        dependency.get("pr"),
                        f"repositories.{spec.key}.open_prs[{number}].dependency.pr",
                    )
                    if dependency_repo is None:
                        raise ValueError("dependencies must name a project repository and positive PR")
                    identity = (dependency_repo, dependency_pr)
                    if identity in seen_dependencies:
                        raise ValueError("dependencies must be unique within a PR")
                    seen_dependencies.add(identity)
                    normalized_dependencies.append(
                        {"repo": dependency_repo, "pr": dependency_pr, "source": "pr_body"}
                    )
                dependencies = normalized_dependencies
                dependencies.sort(
                    key=lambda dependency: (
                        _REPOSITORY_ORDER[dependency["repo"]], dependency["pr"]
                    )
                )

            merge_state = _text(
                source_pr.get("merge_state"),
                f"repositories.{spec.key}.open_prs[{number}].merge_state",
                allow_empty=False,
            )
            if merge_state not in _MERGE_STATES:
                raise ValueError(
                    f"repositories.{spec.key}.open_prs[{number}].merge_state is invalid"
                )
            pr = {
                "repo": spec.repository,
                "number": number,
                "url": _text(
                    source_pr.get("url")
                    or f"https://github.com/{spec.repository}/pull/{number}",
                    f"repositories.{spec.key}.open_prs[{number}].url",
                    allow_empty=False,
                ),
                "title": _text(
                    source_pr.get("title"),
                    f"repositories.{spec.key}.open_prs[{number}].title",
                ),
                "branch": _text(
                    source_pr.get("branch") or source_pr.get("head_ref") or "",
                    f"repositories.{spec.key}.open_prs[{number}].branch",
                ),
                "updated_at": _validate_utc_timestamp(
                    source_pr.get("updated_at"),
                    f"repositories.{spec.key}.open_prs[{number}].updated_at",
                ),
                "draft": _boolean(
                    source_pr.get("draft", source_pr.get("is_draft", False)),
                    f"repositories.{spec.key}.open_prs[{number}].draft",
                ),
                "merge_state": merge_state,
                "conflict": merge_state == "DIRTY",
                "files_count": len(files),
                "files_truncated": _boolean(
                    source_pr.get("files_truncated", False),
                    f"repositories.{spec.key}.open_prs[{number}].files_truncated",
                ),
                "files": files,
                "protected_paths": [
                    path for path in files if is_protected_path(spec.repository, path)
                ],
                "dependencies": dependencies,
            }
            open_prs.append(pr)
            all_open_prs.append(pr)

        open_prs.sort(key=lambda pr: (pr["updated_at"], pr["number"]), reverse=True)

        recently_merged: list[dict[str, Any]] = []
        seen_merged_numbers: set[int] = set()
        for source_pr in source_recent:
            if not isinstance(source_pr, dict):
                raise TypeError(
                    f"repositories.{spec.key}.recently_merged entries must be objects"
                )
            _validate_fields(
                source_pr,
                required={"number", "title", "merged_at"},
                allowed={
                    "repo",
                    "number",
                    "url",
                    "title",
                    "branch",
                    "head_ref",
                    "merged_at",
                },
                context=f"repositories.{spec.key}.recently_merged",
            )
            number = _positive_integer(
                source_pr["number"], f"repositories.{spec.key}.recently_merged.number"
            )
            if number in seen_merged_numbers:
                raise ValueError(
                    f"repositories.{spec.key}.recently_merged numbers must be positive and unique"
                )
            seen_merged_numbers.add(number)
            recently_merged.append(
                {
                    "repo": spec.repository,
                    "number": number,
                    "url": _text(
                        source_pr.get("url")
                        or f"https://github.com/{spec.repository}/pull/{number}",
                        f"repositories.{spec.key}.recently_merged[{number}].url",
                        allow_empty=False,
                    ),
                    "title": _text(
                        source_pr.get("title"),
                        f"repositories.{spec.key}.recently_merged[{number}].title",
                    ),
                    "branch": _text(
                        source_pr.get("branch") or source_pr.get("head_ref") or "",
                        f"repositories.{spec.key}.recently_merged[{number}].branch",
                    ),
                    "merged_at": _validate_utc_timestamp(
                        source_pr.get("merged_at"),
                        f"repositories.{spec.key}.recently_merged[{number}].merged_at",
                    ),
                }
            )
        recently_merged.sort(
            key=lambda pr: (pr["merged_at"], pr["number"]), reverse=True
        )
        contradictory_numbers = seen_open_numbers & seen_merged_numbers
        if contradictory_numbers:
            joined = ", ".join(f"#{number}" for number in sorted(contradictory_numbers))
            raise ValueError(
                f"repositories.{spec.key} contains PR identities in both open and merged state: {joined}"
            )
        all_recently_merged.extend(recently_merged)

        repositories.append(
            {
                "key": spec.key,
                "repo": spec.repository,
                "base_branch": spec.base_branch,
                "base_sha": base_sha,
                "open_prs_truncated": _boolean(
                    source_repo.get("open_prs_truncated", False),
                    f"repositories.{spec.key}.open_prs_truncated",
                ),
                "recently_merged_truncated": _boolean(
                    source_repo.get("recently_merged_truncated", False),
                    f"repositories.{spec.key}.recently_merged_truncated",
                ),
                "open_prs": open_prs,
                "recently_merged": recently_merged,
            }
        )

    open_index = {(pr["repo"], pr["number"]) for pr in all_open_prs}
    merged_index = {(pr["repo"], pr["number"]) for pr in all_recently_merged}
    for pr in all_open_prs:
        resolved_dependencies: list[dict[str, Any]] = []
        for dependency in pr["dependencies"]:
            identity = (dependency["repo"], dependency["pr"])
            if identity == (pr["repo"], pr["number"]):
                continue
            if identity in open_index:
                status = "open"
            elif identity in merged_index:
                status = "recently_merged"
            else:
                status = "unresolved"
            resolved_dependencies.append({**dependency, "status": status})
        pr["dependencies"] = resolved_dependencies

    collisions = compute_file_collisions(all_open_prs)
    collision_counts: dict[str, int] = {spec.repository: 0 for spec in REPOSITORIES}
    for collision in collisions:
        collision_counts[collision["repo"]] += 1

    summary_repositories: list[dict[str, Any]] = []
    for repository in repositories:
        open_prs = repository["open_prs"]
        summary_repositories.append(
            {
                "repo": repository["repo"],
                "base_branch": repository["base_branch"],
                "open_prs": len(open_prs),
                "conflicts": sum(1 for pr in open_prs if pr["conflict"]),
                "protected_prs": sum(1 for pr in open_prs if pr["protected_paths"]),
                "dependency_edges": sum(len(pr["dependencies"]) for pr in open_prs),
                "file_collisions": collision_counts[repository["repo"]],
                "recently_merged": len(repository["recently_merged"]),
            }
        )

    return {
        "schema": SCHEMA,
        "advisory_only": True,
        "gates": [],
        "collected_at": collected_at,
        "merged_days": merged_days,
        "repositories": repositories,
        "file_collisions": collisions,
        "summary": {
            "repository_count": len(repositories),
            "open_prs": len(all_open_prs),
            "conflicts": sum(1 for pr in all_open_prs if pr["conflict"]),
            "file_collisions": len(collisions),
            "recently_merged": len(all_recently_merged),
            "repositories": summary_repositories,
        },
    }


def _md_text(value: Any) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ")


def _short_list(values: list[str], limit: int = 4) -> str:
    if not values:
        return "—"
    shown = ", ".join(f"`{_md_text(value)}`" for value in values[:limit])
    remaining = len(values) - limit
    return f"{shown} +{remaining} more" if remaining > 0 else shown


def render_markdown(payload: dict[str, Any]) -> str:
    """Render a canonical payload without consulting clocks, git, or GitHub."""
    if payload.get("schema") != SCHEMA:
        payload = compile_snapshot(payload)

    lines = [
        (
            "<!-- GENERATED — do not edit by hand; regenerate with "
            "`python -m scripts.build_project_active_build_map`. Advisory only; gates nothing. -->"
        ),
        "",
        "# Project Active Build Map",
        "",
        (
            "Project-wide coordination view for exactly Macro, Terminal, and Mastermind. "
            "Macro's deeper repository-local map remains `docs/ACTIVE_BUILD_MAP.md`."
        ),
        "",
        (
            f"Collected: {payload['collected_at']}  |  "
            f"Open PRs: {payload['summary']['open_prs']}  |  "
            f"Conflicts: {payload['summary']['conflicts']}  |  "
            f"File collisions: {payload['summary']['file_collisions']}"
        ),
        "",
        "## Repositories",
        "",
        "| Repository | Base | SHA | Open | Conflicts | Protected PRs | Dependencies | Collisions | Recently merged |",
        "|------------|------|-----|------|-----------|---------------|--------------|------------|-----------------|",
    ]
    repository_by_slug = {repo["repo"]: repo for repo in payload["repositories"]}
    for summary in payload["summary"]["repositories"]:
        repository = repository_by_slug[summary["repo"]]
        lines.append(
            f"| `{summary['repo']}` | `{summary['base_branch']}` | "
            f"`{repository['base_sha'][:12] or 'unknown'}` | {summary['open_prs']} | "
            f"{summary['conflicts']} | {summary['protected_prs']} | "
            f"{summary['dependency_edges']} | {summary['file_collisions']} | "
            f"{summary['recently_merged']} |"
        )
    truncated_pr_repositories = [
        f"`{repository['key']}`"
        for repository in payload["repositories"]
        if repository["open_prs_truncated"]
    ]
    if truncated_pr_repositories:
        lines.extend(
            [
                "",
                "**Incomplete PR census:** GitHub capped the open-PR list for "
                + ", ".join(truncated_pr_repositories)
                + ". Open counts, protected-path counts, dependencies, and collision negatives are indeterminate beyond the fetched pull requests.",
            ]
        )

    lines.extend(
        [
            "",
            "## Open Pull Requests",
            "",
            "| Repository | PR | Title | Branch | Updated | Draft | Conflict | Files | Protected paths | Dependencies |",
            "|------------|----|-------|--------|---------|-------|----------|-------|-----------------|--------------|",
        ]
    )
    open_count = 0
    truncated_file_prs: list[str] = []
    for repository in payload["repositories"]:
        for pr in repository["open_prs"]:
            open_count += 1
            files_label = str(pr["files_count"])
            if pr["files_truncated"]:
                files_label += "+ (truncated)"
                truncated_file_prs.append(
                    f"`{repository['key']}#{pr['number']}`"
                )
            dependencies = "—"
            if pr["dependencies"]:
                dependencies = ", ".join(
                    f"`{dependency['repo']}#{dependency['pr']}` ({dependency['status']})"
                    for dependency in pr["dependencies"]
                )
            lines.append(
                f"| `{repository['key']}` | [#{pr['number']}]({pr['url']}) | "
                f"{_md_text(pr['title'])} | `{_md_text(pr['branch'])}` | "
                f"{_md_text(pr['updated_at'])} | {'yes' if pr['draft'] else 'no'} | "
                f"{'yes' if pr['conflict'] else 'no'} | "
                f"{files_label} | {_short_list(pr['protected_paths'])} | {dependencies} |"
            )
    if open_count == 0:
        lines.append("| — | — | No open pull requests | — | — | — | — | — | — | — |")
    if truncated_file_prs:
        lines.extend(
            [
                "",
                "**Incomplete file census:** GitHub capped changed-file results for "
                + ", ".join(truncated_file_prs)
                + ". Their protected-path lists and all collision negatives are indeterminate beyond the fetched files.",
            ]
        )

    lines.extend(["", "## File Collisions", ""])
    if payload["file_collisions"]:
        lines.extend(
            [
                "| Repository | PR A | PR B | Shared files | Protected collision |",
                "|------------|------|------|--------------|---------------------|",
            ]
        )
        for collision in payload["file_collisions"]:
            lines.append(
                f"| `{collision['repo']}` | #{collision['pr_a']} | #{collision['pr_b']} | "
                f"{_short_list(collision['shared_files'], limit=8)} | "
                f"{'yes' if collision['protected_collision'] else 'no'} |"
            )
    else:
        qualifier = (
            " among the fetched pull requests and file lists"
            if truncated_file_prs or truncated_pr_repositories
            else ""
        )
        lines.append(f"_No same-repository file collisions detected{qualifier}._")
    if truncated_file_prs or truncated_pr_repositories:
        lines.append(
            "_Collision coverage is incomplete for the truncated repository or file censuses named above._"
        )

    lines.extend(
        [
            "",
            f"## Recently Merged (last {payload['merged_days']} days)",
            "",
            "| Repository | PR | Title | Branch | Merged |",
            "|------------|----|-------|--------|--------|",
        ]
    )
    merged_count = 0
    for repository in payload["repositories"]:
        for pr in repository["recently_merged"]:
            merged_count += 1
            lines.append(
                f"| `{repository['key']}` | [#{pr['number']}]({pr['url']}) | "
                f"{_md_text(pr['title'])} | `{_md_text(pr['branch'])}` | "
                f"{_md_text(pr['merged_at'])} |"
            )
        if repository["recently_merged_truncated"]:
            lines.append(
                f"| `{repository['key']}` | — | _Window truncated at the most recent "
                f"{RECENT_MERGE_LIMIT} PRs._ | — | — |"
            )
    if merged_count == 0:
        lines.append("| — | — | No pull requests merged in the window | — | — |")

    lines.extend(
        [
            "",
            "---",
            "",
            (
                "**Advisory only.** This artifact informs coordination; no CI, merge, deploy, "
                "runtime, or semantic-authority gate consumes it. Dependency status is limited "
                "to open PRs and the displayed recent-merge window."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def _run_gh(args: list[str]) -> Any | None:
    try:
        result = subprocess.run(
            ["gh", *args],
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        log.warning("GitHub collection failed: %s", exc)
        return None
    if result.returncode != 0:
        log.warning(
            "GitHub collection failed (rc=%d): gh %s; stderr: %s",
            result.returncode,
            " ".join(args),
            result.stderr.strip()[:400],
        )
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        log.warning("GitHub returned invalid JSON: %s", exc)
        return None


def _collect_repository(
    spec: RepositorySpec,
    *,
    merged_days: int,
    collected_at: datetime,
    gh_runner: GhRunner,
) -> dict[str, Any] | None:
    base = gh_runner(["api", f"repos/{spec.repository}/git/ref/heads/{spec.base_branch}"])
    if not isinstance(base, dict) or not base.get("object", {}).get("sha"):
        return None

    open_data = gh_runner(
        [
            "pr",
            "list",
            "--repo",
            spec.repository,
            "--state",
            "open",
            "--limit",
            str(OPEN_PR_LIMIT),
            "--json",
            "number,title,headRefName,updatedAt,isDraft,mergeStateStatus,url,body",
        ]
    )
    if not isinstance(open_data, list):
        return None

    open_prs: list[dict[str, Any]] = []
    for item in open_data:
        detail = gh_runner(
            [
                "pr",
                "view",
                str(item["number"]),
                "--repo",
                spec.repository,
                "--json",
                "files,mergeStateStatus,body",
            ]
        )
        if not isinstance(detail, dict) or not isinstance(detail.get("files"), list):
            return None
        files = [
            str(file["path"])
            for file in detail["files"]
            if isinstance(file, dict) and file.get("path")
        ]
        resolved_state = str(detail.get("mergeStateStatus") or "")
        list_state = str(item.get("mergeStateStatus") or "UNKNOWN")
        merge_state = resolved_state if resolved_state and resolved_state != "UNKNOWN" else list_state
        open_prs.append(
            {
                "number": item["number"],
                "url": item.get("url", ""),
                "title": item.get("title", ""),
                "branch": item.get("headRefName", ""),
                "updated_at": item.get("updatedAt", ""),
                "draft": bool(item.get("isDraft", False)),
                "merge_state": merge_state,
                "files": files,
                "files_truncated": len(files) >= 100,
                "body": detail.get("body") or item.get("body") or "",
            }
        )

    cutoff = (collected_at - timedelta(days=merged_days)).strftime("%Y-%m-%d")
    merged_data = gh_runner(
        [
            "pr",
            "list",
            "--repo",
            spec.repository,
            "--state",
            "merged",
            "--search",
            f"merged:>={cutoff} base:{spec.base_branch}",
            "--limit",
            str(RECENT_MERGE_LIMIT),
            "--json",
            "number,title,headRefName,mergedAt,url",
        ]
    )
    if not isinstance(merged_data, list):
        return None
    recently_merged = [
        {
            "number": item["number"],
            "url": item.get("url", ""),
            "title": item.get("title", ""),
            "branch": item.get("headRefName", ""),
            "merged_at": item.get("mergedAt", ""),
        }
        for item in merged_data
    ]

    return {
        "repo": spec.repository,
        "base_branch": spec.base_branch,
        "base_sha": base["object"]["sha"],
        "open_prs_truncated": len(open_data) >= OPEN_PR_LIMIT,
        "recently_merged_truncated": len(merged_data) >= RECENT_MERGE_LIMIT,
        "open_prs": open_prs,
        "recently_merged": recently_merged,
    }


def collect_source_snapshot(
    *,
    merged_days: int = 14,
    collected_at: datetime | None = None,
    gh_runner: GhRunner = _run_gh,
) -> dict[str, Any] | None:
    """Collect all three repositories, or return ``None`` on any failure."""
    collected_at = collected_at or datetime.now(timezone.utc)
    repositories: list[dict[str, Any]] = []
    for spec in REPOSITORIES:
        repository = _collect_repository(
            spec,
            merged_days=merged_days,
            collected_at=collected_at,
            gh_runner=gh_runner,
        )
        if repository is None:
            log.warning("Project map collection aborted at %s", spec.repository)
            return None
        repositories.append(repository)
    return {
        "schema": SOURCE_SCHEMA,
        "collected_at": collected_at.isoformat(),
        "merged_days": merged_days,
        "repositories": repositories,
    }


def build_map(
    *,
    source_snapshot: dict[str, Any] | None = None,
    merged_days: int = 14,
    gh_runner: GhRunner = _run_gh,
) -> dict[str, Any] | None:
    """Build from injected data, or collect live data when none is supplied."""
    if source_snapshot is None:
        source_snapshot = collect_source_snapshot(
            merged_days=merged_days,
            gh_runner=gh_runner,
        )
        if source_snapshot is None:
            return None
    return compile_snapshot(source_snapshot)


def _stage_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_path, 0o644)
        return temporary_path
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def _backup_existing(path: Path) -> Path | None:
    if not path.exists():
        return None
    descriptor, backup_name = tempfile.mkstemp(prefix=f".{path.name}.backup.", dir=path.parent)
    os.close(descriptor)
    backup_path = Path(backup_name)
    try:
        shutil.copy2(path, backup_path)
        with backup_path.open("rb") as handle:
            os.fsync(handle.fileno())
        return backup_path
    except Exception:
        backup_path.unlink(missing_ok=True)
        raise


def _atomic_write_pair(outputs: list[tuple[Path, str]]) -> None:
    """Publish a related artifact pair or restore both prior versions on failure."""
    if len({path.resolve() for path, _text in outputs}) != len(outputs):
        raise ValueError("paired outputs must name distinct paths")
    staged: dict[Path, Path] = {}
    backups: dict[Path, Path | None] = {}
    replaced: list[Path] = []
    preserved_backups: set[Path] = set()
    try:
        for path, content in outputs:
            staged[path] = _stage_text(path, content)
            backups[path] = _backup_existing(path)
        for path, _content in outputs:
            os.replace(staged[path], path)
            staged.pop(path)
            replaced.append(path)
    except Exception as publish_error:
        rollback_failures: list[str] = []
        for path in reversed(replaced):
            backup = backups.get(path)
            try:
                if backup is None:
                    path.unlink(missing_ok=True)
                else:
                    os.replace(backup, path)
                    backups[path] = None
            except OSError as rollback_error:
                if backup is not None:
                    preserved_backups.add(backup)
                rollback_failures.append(
                    f"{path}: {rollback_error}"
                    + (f" (backup preserved at {backup})" if backup is not None else "")
                )
        if rollback_failures:
            raise OSError(
                "paired publication failed and rollback was incomplete: "
                + "; ".join(rollback_failures)
            ) from publish_error
        raise
    finally:
        for temporary_path in [*staged.values(), *backups.values()]:
            if temporary_path is not None and temporary_path not in preserved_backups:
                temporary_path.unlink(missing_ok=True)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-in", help="Compile this JSON snapshot instead of calling GitHub")
    parser.add_argument("--json-out", default=str(_DEFAULT_JSON_OUT))
    parser.add_argument("--md-out", default=str(_DEFAULT_MD_OUT))
    parser.add_argument("--merged-days", type=int, default=14)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s  %(name)s  %(message)s",
        stream=sys.stderr,
    )
    args = _parse_args(argv)
    try:
        source_snapshot = None
        if args.snapshot_in:
            source_snapshot = json.loads(Path(args.snapshot_in).read_text(encoding="utf-8"))
        payload = build_map(
            source_snapshot=source_snapshot,
            merged_days=args.merged_days,
        )
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"ERROR: project active build map input is invalid: {exc}", file=sys.stderr)
        return 2

    if payload is None:
        print(
            "WARNING: project active build map generation skipped because live GitHub "
            "collection was incomplete. Existing output files untouched.",
            file=sys.stderr,
        )
        return 0

    json_text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    markdown_text = render_markdown(payload)
    if args.dry_run:
        print("=== JSON OUTPUT ===")
        print(json_text, end="")
        print("=== MARKDOWN OUTPUT ===")
        print(markdown_text, end="")
        return 0

    try:
        _atomic_write_pair(
            [
                (Path(args.json_out), json_text),
                (Path(args.md_out), markdown_text),
            ]
        )
    except OSError as exc:
        print(
            f"ERROR: project active build map outputs were not published: {exc}",
            file=sys.stderr,
        )
        return 2
    log.info(
        "Wrote advisory project map: %d open PR(s), %d collision(s)",
        payload["summary"]["open_prs"],
        payload["summary"]["file_collisions"],
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
