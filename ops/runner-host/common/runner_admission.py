#!/usr/bin/env python3
"""Host-enforced allowlist for jobs assigned to persistent home runners."""

from __future__ import annotations

import json
import os
import re


REPOSITORY = "mastermindx-market-intelligence/macro"
MAIN_REF = "refs/heads/main"

ALLOWLIST = {
    "pc-ci": {
        *{
            (
                "workflow_dispatch",
                f"{REPOSITORY}/.github/workflows/selfhosted-ci-canary.yml@{MAIN_REF}",
                job,
            )
            for job in ("selfhosted-pack", "cache-negative-control", "contamination-probe")
        },
        (
            "workflow_dispatch",
            f"{REPOSITORY}/.github/workflows/trusted-ci-executor.yml@{MAIN_REF}",
            "trusted-pack",
        ),
    },
    "m1-canary": {
        (
            "workflow_dispatch",
            f"{REPOSITORY}/.github/workflows/m1-runner-canary.yml@{MAIN_REF}",
            "m1-service-canary",
        )
    },
    "pc-render": {
        (event, f"{REPOSITORY}/.github/workflows/{workflow}@{MAIN_REF}", job)
        for event, workflow, job in (
            ("push", "engine-render.yml", "engine-render"),
            ("workflow_dispatch", "engine-render.yml", "engine-render"),
            ("push", "render.yml", "render"),
            ("workflow_dispatch", "render.yml", "render"),
            ("workflow_dispatch", "selfhosted-ci-canary.yml", "render-reservation-probe"),
        )
    },
}


def _pull_request_event_facts(environment: dict[str, str]) -> tuple[str, str]:
    """Read the GitHub-authored PR identity available to the pre-job hook.

    GitHub runs ``ACTIONS_RUNNER_HOOK_JOB_STARTED`` before workflow/job ``env``
    is installed.  The hook does receive the default variables and the event
    payload path, so fail closed on any unreadable or malformed payload and
    derive same-repository/base identity from that GitHub-authored document.
    """

    event_path = environment.get("GITHUB_EVENT_PATH", "")
    if not event_path:
        return "", ""
    try:
        with open(event_path, encoding="utf-8") as handle:
            payload = json.load(handle)
        pull_request = payload["pull_request"]
        head_repository = pull_request["head"]["repo"]["full_name"]
        base_ref = pull_request["base"]["ref"]
    except (KeyError, OSError, TypeError, ValueError):
        return "", ""
    if not isinstance(head_repository, str) or not isinstance(base_ref, str):
        return "", ""
    return head_repository, base_ref


def _trusted_pr_pack_allowed(facts: dict[str, str]) -> bool:
    match = re.fullmatch(r"refs/pull/([1-9][0-9]*)/merge", facts["ref"])
    if match is None:
        return False
    expected_workflow_ref = (
        f"{REPOSITORY}/.github/workflows/ci.yml@{facts['ref']}"
    )
    return (
        facts["profile"] == "pc-ci"
        and facts["event"] == "pull_request"
        and facts["workflow_ref"] == expected_workflow_ref
        and facts["job"] == "trusted-pack"
        and facts["head_repository"] == REPOSITORY
        and facts["base_ref"] == "main"
    )

def decision(environment: dict[str, str]) -> tuple[bool, dict[str, str]]:
    profile = environment.get("MASTERMIND_CI_PROFILE", "")
    head_repository, base_ref = _pull_request_event_facts(environment)
    facts = {
        "profile": profile,
        "repository": environment.get("GITHUB_REPOSITORY", ""),
        "event": environment.get("GITHUB_EVENT_NAME", ""),
        "ref": environment.get("GITHUB_REF", ""),
        "workflow_ref": environment.get("GITHUB_WORKFLOW_REF", ""),
        "job": environment.get("GITHUB_JOB", ""),
        "head_repository": head_repository,
        "base_ref": base_ref,
    }
    key = (facts["event"], facts["workflow_ref"], facts["job"])
    allowed = (
        facts["repository"] == REPOSITORY
        and (
            (
                facts["ref"] == MAIN_REF
                and key in ALLOWLIST.get(profile, set())
            )
            or _trusted_pr_pack_allowed(facts)
        )
    )
    return allowed, facts


def main() -> int:
    allowed, facts = decision(dict(os.environ))
    print(
        "RUNNER_ADMISSION="
        + json.dumps(
            {
                "schema": "runner.admission.v1",
                "allowed": allowed,
                **facts,
            },
            sort_keys=True,
        ),
        flush=True,
    )
    if not allowed:
        print("::error title=runner-admission::persistent runner refused this job", flush=True)
        return 77
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
