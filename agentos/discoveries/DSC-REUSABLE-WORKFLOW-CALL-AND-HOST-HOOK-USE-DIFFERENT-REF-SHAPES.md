---
key: REUSABLE-WORKFLOW-CALL-AND-HOST-HOOK-USE-DIFFERENT-REF-SHAPES
claim: >
  A reusable-workflow caller must name a branch, tag or commit after `@`; the
  fully qualified `@refs/heads/main` form used by runner-group selected-workflow
  policy is invalid caller syntax. For a same-repository PR call using `@main`,
  `job.workflow_ref` identifies the called workflow as
  `trusted-ci-executor.yml@main`, while `github.workflow_ref`, `GITHUB_REF` and
  the persistent runner start hook retain the caller PR identity
  `ci.yml@refs/pull/N/merge` / `refs/pull/N/merge`.
falsifier: >
  Show a GitHub Actions run where `uses: owner/repo/.github/workflows/file.yml@refs/heads/main`
  is accepted as a reusable-workflow call, or a successful `@main` called job
  whose `job.workflow_ref`/start-hook caller variables use the same ref shape.
so_what: >
  Keep the server-side runner-group selection pinned to `@refs/heads/main`, but
  call the workflow with `@main`. Bind called identity in the hosted gate with
  `job.workflow_ref` plus immutable `job.workflow_sha`. At the PC start hook,
  admit only the exact PR merge ref/caller/job plus main-defined same-repository,
  base and control-SHA facts; do not pretend `GITHUB_WORKFLOW_REF` is the called
  workflow and do not weaken the group selection.
kind: landmine
verified_at: 2026-08-27
verified_by: >
  PR #6505 run 33038617258 failed at workflow admission with zero jobs and the
  GitHub annotation `failed to fetch workflow: reference to workflow should be
  either a valid branch, tag, or commit`; official GitHub context contracts;
  local executed trust/admission tests; drained root-hook deployment to
  pc-ci-1/2/3 with identical SHA-256 and allowed/hostile decision receipts.
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
