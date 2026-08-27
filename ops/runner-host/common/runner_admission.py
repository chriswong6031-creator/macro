#!/usr/bin/env python3
"""Host-enforced allowlist for jobs assigned to persistent home runners."""

from __future__ import annotations

import json
import os


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

def decision(environment: dict[str, str]) -> tuple[bool, dict[str, str]]:
    profile = environment.get("MASTERMIND_CI_PROFILE", "")
    facts = {
        "profile": profile,
        "repository": environment.get("GITHUB_REPOSITORY", ""),
        "event": environment.get("GITHUB_EVENT_NAME", ""),
        "ref": environment.get("GITHUB_REF", ""),
        "workflow_ref": environment.get("GITHUB_WORKFLOW_REF", ""),
        "job": environment.get("GITHUB_JOB", ""),
    }
    key = (facts["event"], facts["workflow_ref"], facts["job"])
    allowed = (
        facts["repository"] == REPOSITORY
        and facts["ref"] == MAIN_REF
        and key in ALLOWLIST.get(profile, set())
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
