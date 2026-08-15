#!/usr/bin/env python3
"""Prepare a runner checkout from the root-owned shared object cache.

This program intentionally has no origin-fetch fallback. A missing, writable,
misidentified, or incomplete cache fails before actions/checkout can recreate the
historical giant direct fetch.
"""

from __future__ import annotations

import argparse
import json
import os
import stat
import subprocess
import time
from pathlib import Path


MARKER = ".mastermind-cache-identity.json"


class PrewarmError(RuntimeError):
    pass


def git(*args: str, git_dir: Path | None = None, cwd: Path | None = None) -> str:
    command = ["git"]
    if git_dir is not None:
        command.extend(["--git-dir", str(git_dir)])
    command.extend(args)
    env = os.environ.copy()
    env["GIT_NO_LAZY_FETCH"] = "1"
    result = subprocess.run(
        command, cwd=cwd, env=env, text=True, capture_output=True, check=False
    )
    if result.returncode:
        raise PrewarmError(
            f"{' '.join(command)} failed ({result.returncode}): "
            f"{(result.stderr or result.stdout).strip()}"
        )
    return result.stdout.strip()


def canonical_repository(url: str) -> str:
    value = url.strip().removesuffix(".git").rstrip("/")
    if value.startswith("git@github.com:"):
        value = value.split(":", 1)[1]
    elif "github.com/" in value:
        value = value.split("github.com/", 1)[1]
    return value.lower()


def validate_cache(cache: Path, repository: str, expected_owner_uid: int) -> dict[str, object]:
    if not cache.is_dir():
        raise PrewarmError(f"shared cache unavailable: {cache}")
    cache_stat = cache.stat()
    if cache_stat.st_uid != expected_owner_uid:
        raise PrewarmError(
            f"shared cache owner uid {cache_stat.st_uid}, expected {expected_owner_uid}"
        )
    if cache_stat.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise PrewarmError("shared cache is group/world writable")
    marker = cache / MARKER
    if not marker.is_file():
        raise PrewarmError(f"cache identity marker missing: {marker}")
    marker_stat = marker.stat()
    if marker_stat.st_uid != expected_owner_uid or marker_stat.st_mode & (
        stat.S_IWGRP | stat.S_IWOTH
    ):
        raise PrewarmError("cache identity marker ownership/mode is unsafe")
    try:
        identity = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PrewarmError(f"cache identity marker unreadable: {exc}") from exc
    if identity.get("schema") != "mastermind.ci_git_cache.v1":
        raise PrewarmError("cache identity schema mismatch")
    if str(identity.get("repository", "")).lower() != repository.lower():
        raise PrewarmError("cache repository identity mismatch")
    if git("rev-parse", "--is-bare-repository", git_dir=cache) != "true":
        raise PrewarmError("shared cache is not bare")
    origin = git("config", "--get", "remote.origin.url", git_dir=cache)
    if canonical_repository(origin) != repository.lower():
        raise PrewarmError("cache origin URL identifies a different repository")
    return identity


def prepare(
    cache: Path,
    workspace: Path,
    repository: str,
    repository_url: str,
    base_sha: str,
    expected_owner_uid: int,
) -> dict[str, object]:
    started = time.monotonic()
    validate_cache(cache, repository, expected_owner_uid)
    git("cat-file", "-e", f"{base_sha}^{{commit}}", git_dir=cache)
    git("cat-file", "-e", f"{base_sha}^{{tree}}", git_dir=cache)

    workspace.mkdir(parents=True, exist_ok=True)
    entries = list(workspace.iterdir())
    if entries and not (workspace / ".git").is_dir():
        raise PrewarmError("workspace is non-empty but is not a Git checkout")
    if not (workspace / ".git").is_dir():
        git("init", str(workspace))
    try:
        origin = git("remote", "get-url", "origin", cwd=workspace)
    except PrewarmError:
        git("remote", "add", "origin", repository_url, cwd=workspace)
    else:
        if canonical_repository(origin) != repository.lower():
            raise PrewarmError("workspace origin identifies a different repository")
        git("remote", "set-url", "origin", repository_url, cwd=workspace)

    alternate = cache.resolve() / "objects"
    alternates_file = workspace / ".git" / "objects" / "info" / "alternates"
    alternates_file.parent.mkdir(parents=True, exist_ok=True)
    alternates_file.write_text(str(alternate) + "\n", encoding="utf-8")
    git("config", "gc.auto", "0", cwd=workspace)
    git("update-ref", "refs/cache/main", base_sha, cwd=workspace)
    # Materialize the frozen base entirely from the cache. Because this checkout is
    # not a promisor repository, a missing blob fails here instead of reaching origin.
    git("checkout", "--force", "-B", "cache-base", base_sha, cwd=workspace)
    git("reset", "--hard", base_sha, cwd=workspace)
    git("clean", "-ffdx", cwd=workspace)
    head = git("rev-parse", "HEAD", cwd=workspace)
    if head != base_sha:
        raise PrewarmError(f"base checkout resolved to {head}, expected {base_sha}")
    return {
        "schema": "mastermind.ci_prewarm.v1",
        "cache": str(cache.resolve()),
        "workspace": str(workspace.resolve()),
        "base_sha": base_sha,
        "cache_ref": git("rev-parse", "refs/cache/main", cwd=workspace),
        "alternate": str(alternate),
        "elapsed_seconds": round(time.monotonic() - started, 3),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--repository-url", required=True)
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--expected-owner-uid", type=int, default=0)
    args = parser.parse_args()
    try:
        result = prepare(
            args.cache,
            args.workspace,
            args.repository,
            args.repository_url,
            args.base_sha,
            args.expected_owner_uid,
        )
    except PrewarmError as exc:
        print(f"::error title=shared-cache-prewarm::{exc}", flush=True)
        return 66
    print("CI_CACHE_PREWARM=" + json.dumps(result, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
