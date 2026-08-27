---
key: REUSABLE-WORKFLOW-CALL-AND-HOST-HOOK-USE-DIFFERENT-REF-SHAPES
claim: >
  A reusable-workflow caller must name a branch, tag or commit after `@`; the
  fully qualified `@refs/heads/main` form used by runner-group selected-workflow
  policy is invalid caller syntax. For a same-repository PR call whose `uses:`
  value is `trusted-ci-executor.yml@main`, GitHub resolves the called runtime
  `job.workflow_ref` to `trusted-ci-executor.yml@refs/heads/main` while
  `job.workflow_sha` carries the immutable called-definition commit. The caller
  `github.workflow_ref`, `GITHUB_REF` and the persistent runner start hook retain
  the caller PR identity `ci.yml@refs/pull/N/merge` / `refs/pull/N/merge`. The
  pre-job hook runs before workflow/job `env` is installed: it receives default
  GitHub variables and `GITHUB_EVENT_PATH`, so job-level environment cannot carry
  host admission authority.
falsifier: >
  Show a GitHub Actions run where `uses: owner/repo/.github/workflows/file.yml@refs/heads/main`
  is accepted as a reusable-workflow call, or a successful same-repository PR call
  whose runtime `job.workflow_ref` is not the resolved protected-main form
  `...@refs/heads/main`, or a pre-job hook that receives candidate-controlled job
  `env` before admission.
so_what: >
  Keep reusable caller syntax at `@main` and server-side runner-group selection at
  `@refs/heads/main`, but bind the called runtime identity in the hosted trust gate
  to the observed resolved `job.workflow_ref=...@refs/heads/main` plus immutable
  `job.workflow_sha`. At the PC start hook, rely on the selected-workflow
  runner-group restriction for called-main identity, and admit only the exact PR
  merge ref/caller/job plus the GitHub-authored event payload's same-repository/
  main-base identity. The root-owned wrapper must forward `GITHUB_EVENT_PATH`; do
  not pretend job `env` reaches the hook, do not pretend `GITHUB_WORKFLOW_REF` is
  the called workflow, and do not confuse reusable `uses:` syntax with the runtime
  called-workflow ref emitted by GitHub.
kind: landmine
verified_at: 2026-08-27
verified_by: >
  PR #6505 run 33038617258 proved reusable `uses: ...@refs/heads/main` is invalid
  caller syntax; PR #6505 run 33039532309 proved the pre-job hook cannot consume
  job `env`; current post-merge downstream runs on PR #6556 (CI 33074339679,
  trust-gate job 98525641383) and PR #6539 (CI 33074386695) independently proved
  that an accepted `uses: ...@main` call emits runtime
  `job.workflow_ref=mastermindx-market-intelligence/macro/.github/workflows/trusted-ci-executor.yml@refs/heads/main`.
  In both downstream failures the caller PR ref, same-repository identity, base
  `main`, PR number and immutable called `job.workflow_sha` were otherwise valid;
  the stale `...@main` runtime literal alone rejected admission before PC work.
scope: [macro, ".github/workflows/ci.yml", ".github/workflows/trusted-ci-executor.yml", "ops/runner-host/**"]
confidence: verified
---

## Incident and repair receipt

The first P3B-B production-route attempt, run 33038617258 on head
`7a7462c79731bbb7030aa505ec2dc7f6c11fb830`, failed during workflow parsing.
No job started, no PC listener acquired work and no hosted pack minute was spent.

The same carrier changed the reusable call to `@main`, split direct-dispatch
`@refs/heads/main` from reusable caller syntax `@main`, and added main-defined
host-admission facts to the called pack job. After all three PC CI runners were
confirmed online and idle, their services were stopped, the old hook hash
`e4ff74a96e9949a0ce4707e3fdb58cfffc251057d5e8c69a7309fe2871e11202`
was retained at an exact backup path, and the new root-owned hook hash
`cd7f67591fe9aaaea2976db467c4ce053cf94d06e5a17f60bc0706086d566736`
was installed. Exact same-repository/main/PR/caller/job/control-SHA input passed;
the fork mutation returned exit 77. All three services and runner registrations
returned online and idle. This receipt did not yet prove the later runtime shape
of `job.workflow_ref` for a reusable production call.

The next exact head resolved the main workflow but run 33039188648 stopped at
startup with zero jobs because the called workflow requested `pull-requests:
read` while the caller allowed `none`. The same carrier then granted only
`contents: read` and `pull-requests: read` on the reusable-call job. This is the
minimum permission needed by the main resolver; it adds no write or secret scope.

Run 33039532309 proved the reusable call and hosted plan, created all twelve
trusted-pack jobs, and failed the first three in the root-owned pre-job hook with
zero workflow steps or tests. Its hook receipt showed the exact caller PR facts
but empty `MASTERMIND_TRUSTED_*` values. GitHub's hook contract explains why:
job `env` does not exist yet, while default variables and `GITHUB_EVENT_PATH` do.
The same run's contract-delta independently found the new route suite unwired.

The same carrier then derived head-repository/base from the GitHub event payload,
forwarded that path through the root-owned JavaScript wrapper, removed the
misleading job `env`, and named the route suite in the existing legacy policy
step. Local contract-delta reported `0 introduced, 0 inherited`; the broad battery
reported 216 passed plus the inherited `defense-rail-laws:engine/*.py`
startability gap. After an all-idle drain, pc-ci-1/2/3 received Python hash
`69faac248f755829a39f6821f17015382788056991f6d1ff9046b1842e86a002` and
wrapper hash `d55f046e6a6a758f55e311ed73b921e007c8570cc0aba11e0cafdc31cef06dee`.
Both hashes persisted after restart; three listeners returned online/idle; the
same-repo/main payload passed and a fork payload returned exit 77.

After PR #6505 merged as `4b9c9ece8593a2483997432e25f233bfe7af8779`, the first independent ordinary
same-repository PRs exposed the remaining representation defect. PR #6556 and
PR #6539 both entered the protected-main reusable workflow with valid PR caller,
base, repository and immutable called SHA, but GitHub emitted
`job.workflow_ref=...trusted-ci-executor.yml@refs/heads/main`. The trust gate still
expected the pre-production assumption `...@main`, so both runs failed in
`trusted-executor-main-admission` before persistent-runner pickup. The owning
repair therefore changes only that runtime comparison and its executable fixture;
`ci.yml` continues to call `@main`, and every SHA/caller/ref/fork/base guard remains.
