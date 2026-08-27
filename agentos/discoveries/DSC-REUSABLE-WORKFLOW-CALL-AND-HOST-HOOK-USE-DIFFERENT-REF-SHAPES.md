---
key: REUSABLE-WORKFLOW-CALL-AND-HOST-HOOK-USE-DIFFERENT-REF-SHAPES
claim: >
  A reusable-workflow caller must name a branch, tag or commit after `@`; the
  fully qualified `@refs/heads/main` form used by runner-group selected-workflow
  policy is invalid caller syntax. For a same-repository PR call using `@main`,
  `job.workflow_ref` identifies the called workflow as
  `trusted-ci-executor.yml@refs/heads/main`; the caller declaration and the
  called-workflow context therefore use different spellings for the same main
  definition. Meanwhile `github.workflow_ref`, `GITHUB_REF` and the persistent
  runner start hook retain the caller PR identity
  `ci.yml@refs/pull/N/merge` / `refs/pull/N/merge`. The pre-job hook runs before
  workflow/job `env` is installed: it receives default GitHub variables and
  `GITHUB_EVENT_PATH`, so job-level environment cannot carry host admission
  authority.
falsifier: >
  Show a GitHub Actions run where `uses: owner/repo/.github/workflows/file.yml@refs/heads/main`
  is accepted as a reusable-workflow call, or where an `@main` reusable call's
  `job.workflow_ref` is the shorthand `@main` instead of the canonical full ref.
so_what: >
  Keep the server-side runner-group selection pinned to `@refs/heads/main`, but
  call the workflow with `@main`. Bind called identity in the hosted gate with
  the exact full `job.workflow_ref` plus immutable `job.workflow_sha`; do not
  accept shorthand, tag or candidate refs in that context. At the PC start hook,
  rely on the selected-workflow runner-group restriction for called-main
  identity, and admit only the exact PR merge ref/caller/job plus the
  GitHub-authored event payload's same-repository/main-base identity. The
  root-owned wrapper must forward `GITHUB_EVENT_PATH`; do not pretend job `env`
  reaches the hook, do not pretend `GITHUB_WORKFLOW_REF` is the called workflow,
  and do not weaken the group selection.
kind: landmine
verified_at: 2026-08-27
verified_by: >
  PR #6505 run 33038617258 failed at workflow admission with zero jobs and the
  GitHub annotation `failed to fetch workflow: reference to workflow should be
  either a valid branch, tag, or commit`; official GitHub context contracts;
  local executed trust/admission tests; PR #6505 run 33039532309 host-hook logs;
  official GitHub pre-job-hook and selected-workflow documentation; drained
  Python+JavaScript hook deployment to pc-ci-1/2/3 with post-restart SHA-256 and
  allowed/hostile decision receipts; post-merge runs 33074339679 and 33074386695,
  whose real `job.workflow_ref` was the full protected-main ref.
scope: [macro, ".github/workflows/ci.yml", ".github/workflows/trusted-ci-executor.yml", "ops/runner-host/**"]
confidence: verified
---

## Incident and repair receipt

The first P3B-B production-route attempt, run 33038617258 on head
`7a7462c79731bbb7030aa505ec2dc7f6c11fb830`, failed during workflow parsing.
No job started, no PC listener acquired work and no hosted pack minute was spent.

The same carrier changed the reusable call to `@main`, split direct-dispatch
`@refs/heads/main` from reusable-call `@main` in the hosted trust gate, and added
main-defined host-admission facts to the called pack job. After all three PC CI
runners were confirmed online and idle, their services were stopped, the old
hook hash `e4ff74a96e9949a0ce4707e3fdb58cfffc251057d5e8c69a7309fe2871e11202`
was retained at an exact backup path, and the new root-owned hook hash
`cd7f67591fe9aaaea2976db467c4ce053cf94d06e5a17f60bc0706086d566736`
was installed. Exact same-repository/main/PR/caller/job/control-SHA input passed;
the fork mutation returned exit 77. All three services and runner registrations
returned online and idle. This receipt does not prove P3B-B execution; the
corrected PR run still owes real PC pickup, semantic parity and final gate proof.

The next exact head resolved the main workflow but run 33039188648 stopped at
startup with zero jobs because the called workflow requested `pull-requests:
read` while the caller allowed `none`. The same carrier now grants only
`contents: read` and `pull-requests: read` on the reusable-call job. This is the
minimum permission needed by the main resolver; it adds no write or secret scope.

Run 33039532309 then proved the reusable call and hosted plan, created all twelve
trusted-pack jobs, and failed the first three in the root-owned pre-job hook with
zero workflow steps or tests. Its hook receipt showed the exact caller PR facts
but empty `MASTERMIND_TRUSTED_*` values. GitHub's hook contract explains why:
job `env` does not exist yet, while default variables and `GITHUB_EVENT_PATH` do.
The same run's contract-delta independently found the new route suite unwired.

The same carrier now derives head-repository/base from the GitHub event payload,
forwards that path through the root-owned JavaScript wrapper, removes the
misleading job `env`, and names the route suite in the existing legacy policy
step. Local contract-delta reports `0 introduced, 0 inherited`; the broad battery
reported 216 passed plus the inherited `defense-rail-laws:engine/*.py`
startability gap, which this carrier does not alter. After an all-idle drain,
pc-ci-1/2/3 received Python hash
`69faac248f755829a39f6821f17015382788056991f6d1ff9046b1842e86a002` and
wrapper hash `d55f046e6a6a758f55e311ed73b921e007c8570cc0aba11e0cafdc31cef06dee`.
Both hashes persisted after restart; three listeners returned online/idle; the
same-repo/main payload passed and a fork payload returned exit 77. P3B-B still
owes exact PR execution, parity, hosted relays and final gate proof.

PR #6505 subsequently proved all twelve trusted packs and the final gate on run
33070187935 and squash-merged as `4b9c9ece8593a2483997432e25f233bfe7af8779`.
The first two natural post-merge calls, runs 33074339679 and 33074386695, exposed
one remaining representation defect before PC pickup: GitHub supplied
`job.workflow_ref` as
`mastermindx-market-intelligence/macro/.github/workflows/trusted-ci-executor.yml@refs/heads/main`,
while the gate still expected the caller-syntax shorthand `@main`. P4 therefore
remains unaccepted until the exact canonical full-ref gate repair merges and
three ordinary product PRs prove the production route naturally.
