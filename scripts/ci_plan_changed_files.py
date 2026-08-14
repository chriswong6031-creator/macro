"""Resolve a pull request's changed files from the GitHub API — no history fetch.

ci-plan used to learn the diff from `git diff` against the immutable base SHA,
which required `fetch-depth: 0` — measured at 7-8 minutes of checkout on this
~64k-file repository and the single largest component of planner wall time
(incident model, research/CI_MERGE_CONTROL_PLANE_RECOVERY_2026_08_14.md). The
PR files API returns the same base...head comparison as metadata, so the
planner needs only a depth-1 checkout for the tree it analyzes.

Contract, mirroring `resolve_changed_files`:

* stdout is EXACTLY one line: a compact JSON array of changed paths, or the
  literal token `null` meaning "unknowable — run the full suite".
* Every uncertainty WIDENS: an HTTP error, a malformed payload, a truncated
  listing (GitHub caps this endpoint at 3000 files), or a missing token all
  emit `null`. Emitting a PARTIAL list would narrow the suite on exactly the
  PRs least understood, so partial output is the one forbidden shape.
* A rename contributes BOTH sides: the new path selects its new owners, the
  previous path still selects the owners of what the PR removed.

Exit code is 0 even on `null` — widening is a decision, not a failure. Only a
usage error (no PR number resolvable) exits non-zero, because that means the
workflow wired the step to the wrong event.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

PER_PAGE = 100
# GitHub stops listing files at 3,000 for this endpoint. One page past that
# ceiling proves truncation, and a truncated diff must widen.
MAX_PAGES = 30
REQUEST_TIMEOUT_SECONDS = 30
ATTEMPTS_PER_PAGE = 2


def _emit(value: str) -> int:
    print(value, flush=True)
    return 0


def _fetch_page(url: str, token: str) -> list[dict[str, object]] | None:
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "ci-plan-changed-files",
        },
    )
    last_error: Exception | None = None
    for attempt in range(ATTEMPTS_PER_PAGE):
        try:
            with urllib.request.urlopen(
                request, timeout=REQUEST_TIMEOUT_SECONDS
            ) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if isinstance(payload, list):
                return payload
            return None
        except (
            urllib.error.URLError,
            TimeoutError,
            json.JSONDecodeError,
            UnicodeDecodeError,
        ) as exc:
            last_error = exc
            if attempt + 1 < ATTEMPTS_PER_PAGE:
                time.sleep(2)
    print(
        f"::warning title=ci-plan-diff::files API page failed after "
        f"{ATTEMPTS_PER_PAGE} attempts ({last_error}); widening to full suite",
        flush=True,
    )
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY"))
    parser.add_argument("--pr", default=os.environ.get("CI_PR_NUMBER"))
    args = parser.parse_args(argv)
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""

    if not args.repo or not args.pr or not str(args.pr).strip():
        print(
            "::error title=ci-plan-diff::no repository or PR number supplied; "
            "this step only runs on pull_request events",
            flush=True,
        )
        return 2
    if not token:
        # No token, no metadata. Widen rather than guess.
        return _emit("null")

    paths: dict[str, None] = {}
    for page in range(1, MAX_PAGES + 1):
        url = (
            f"https://api.github.com/repos/{args.repo}/pulls/{args.pr}/files"
            f"?per_page={PER_PAGE}&page={page}"
        )
        payload = _fetch_page(url, token)
        if payload is None:
            return _emit("null")
        for entry in payload:
            filename = entry.get("filename")
            if not isinstance(filename, str) or not filename:
                return _emit("null")
            paths[filename] = None
            previous = entry.get("previous_filename")
            if isinstance(previous, str) and previous:
                paths[previous] = None
        if len(payload) < PER_PAGE:
            return _emit(json.dumps(sorted(paths), separators=(",", ":")))
    # MAX_PAGES full pages: the listing is at or beyond GitHub's own 3,000-file
    # ceiling, so the diff cannot be known completely. Widen.
    print(
        "::warning title=ci-plan-diff::pull request lists 3000+ files; "
        "diff unknowable, widening to full suite",
        flush=True,
    )
    return _emit("null")


if __name__ == "__main__":
    raise SystemExit(main())
