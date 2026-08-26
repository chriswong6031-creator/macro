#!/usr/bin/env python3
"""Resolve a trusted-main or same-repository PR merge ref for CI canaries."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import urllib.request
from pathlib import Path


class ResolutionError(RuntimeError):
    pass


def git(*args: str) -> str:
    result = subprocess.run(["git", *args], text=True, capture_output=True, check=False)
    if result.returncode:
        raise ResolutionError(
            f"git {' '.join(args)} failed ({result.returncode}): "
            f"{(result.stderr or result.stdout).strip()}"
        )
    return result.stdout.strip()


def pull_request(repository: str, number: int, token: str) -> dict[str, object]:
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repository}/pulls/{number}",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "mastermind-ci-canary-resolver",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        return json.load(response)


def write_outputs(path: Path, values: dict[str, str]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        for key, value in values.items():
            handle.write(f"{key}={value}\n")


def resolve(repository: str, github_sha: str, pr_number: int, token: str) -> dict[str, str]:
    if pr_number == 0:
        tested_sha = git("rev-parse", f"{github_sha}^{{commit}}")
        parent = git("rev-parse", f"{tested_sha}^")
        return {
            "source_kind": "trusted-main",
            "tested_ref": tested_sha,
            "tested_sha": tested_sha,
            "base_sha": parent,
            "head_sha": tested_sha,
            "contamination_sha": parent,
        }

    if not token:
        raise ResolutionError("GITHUB_TOKEN is required to resolve a pull request")
    data = pull_request(repository, pr_number, token)
    if data.get("state") != "open":
        raise ResolutionError(f"pull request #{pr_number} is not open")
    head = data.get("head") or {}
    base = data.get("base") or {}
    head_repo = (head.get("repo") or {}).get("full_name")
    if str(head_repo).lower() != repository.lower():
        raise ResolutionError(
            f"pull request #{pr_number} head is {head_repo!r}, not same-repository"
        )
    if base.get("ref") != "main":
        raise ResolutionError(f"pull request #{pr_number} does not target main")
    tested_ref = f"refs/pull/{pr_number}/merge"
    local_ref = f"refs/ci-canary/pull/{pr_number}/merge"
    git("fetch", "--no-tags", "origin", f"+{tested_ref}:{local_ref}")
    tested_sha = git("rev-parse", f"{local_ref}^{{commit}}")
    api_base_sha = str(base.get("sha") or "")
    head_sha = str(head.get("sha") or "")
    if len(api_base_sha) != 40 or len(head_sha) != 40:
        raise ResolutionError("GitHub returned an invalid base/head SHA")
    api_merge = data.get("merge_commit_sha")
    if api_merge and api_merge != tested_sha:
        raise ResolutionError(
            f"merge ref moved during resolution: API={api_merge}, fetched={tested_sha}"
        )
    base_sha = git("rev-parse", f"{tested_sha}^1")
    fetched_head = git("rev-parse", f"{tested_sha}^2")
    if fetched_head != head_sha:
        raise ResolutionError(
            "fetched merge head does not match the frozen API head: "
            f"fetched={fetched_head}, API={head_sha}"
        )
    return {
        "source_kind": "same-repository-pr-merge",
        "tested_ref": tested_ref,
        "tested_sha": tested_sha,
        "base_sha": base_sha,
        "head_sha": head_sha,
        "contamination_sha": base_sha,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True)
    parser.add_argument("--github-sha", required=True)
    parser.add_argument("--pr-number", type=int, default=0)
    parser.add_argument("--github-output", type=Path, required=True)
    args = parser.parse_args()
    try:
        values = resolve(
            args.repository,
            args.github_sha,
            args.pr_number,
            os.environ.get("GITHUB_TOKEN", ""),
        )
    except ResolutionError as exc:
        print(f"::error title=ci-canary-ref::{exc}", flush=True)
        return 2
    write_outputs(args.github_output, values)
    print(
        "CI_CANARY_REF="
        + json.dumps({"repository": args.repository, **values}, sort_keys=True),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
