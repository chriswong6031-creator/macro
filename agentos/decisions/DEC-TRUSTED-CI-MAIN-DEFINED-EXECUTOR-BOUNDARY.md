---
key: TRUSTED-CI-MAIN-DEFINED-EXECUTOR-BOUNDARY
question: >
  How may ordinary same-repository PR code execute expensive CI packs on
  persistent home hardware without granting PR-authored workflow YAML direct
  runner access or weakening the hosted control, fork and merge boundaries?
answer: >
  Only a reusable workflow whose jobs are defined in
  .github/workflows/trusted-ci-executor.yml on refs/heads/main may target the
  macro-home-canary runner group. The organization runner group remains
  restricted server-side to exact selected workflow paths. The called workflow
  independently resolves the same-repository PR candidate, freezes one plan on
  hosted capacity, materializes the exact SHA through the root-owned read-only
  object cache with no credential fallback, runs with no secrets, and emits the
  existing semantic fragment and receipt formats. Candidate-authored ci.yml may
  later call that exact main path, but may never define a self-hosted job itself
  or supply trusted SHA, plan or route authority. Hosted ci-plan/anchors,
  ci-gate, fences, merge control and every fork/untrusted route remain
  independently hosted. P3B-A admits either a direct main workflow_dispatch or
  an exact same-repository pull_request call whose caller workflow_ref is
  ci.yml at that event's merge ref and whose called job.workflow_ref remains the
  main-owned trusted-ci-executor path. The call accepts no inputs: PR identity,
  exact control SHA, candidate merge SHA and semantic plan are independently
  derived by the called workflow. Direct dispatch stays one-pack bounded;
  production-mode calls may use the P2-accepted three-slot matrix. The PC host
  repeats the exact event/ref/workflow-ref/job decision before job start. P3B-B
  routes only same-repository PR execution through that exact main call. The
  existing hosted ci-pack-N jobs become tiny fragment relays: each compares the
  hosted planner SHA with the main-derived executor SHA, republishes the trusted
  fragment under the existing artifact/check contract, and feeds the unchanged
  ci-gate. Forks retain the complete hosted pack implementation.
rationale: >
  GitHub runner groups restrict access to jobs directly defined in selected
  workflows. A main-pinned reusable workflow therefore keeps runner admission
  under main even when a PR-authored caller requests the work. Re-resolving the
  PR and refusing caller-supplied identity prevents a malicious or stale caller
  from choosing another tree. Keeping the executor credential-free and its
  workspace/cache lifecycle host-sealed bounds trusted candidate execution
  without treating a persistent home checkout as a secret-bearing deployment
  environment. Splitting inert admission from production routing gives the
  server-side selected-workflow mutation and real one-pack proof their own
  rollback boundary.
alternatives:
  - option: Change ci-pack runs-on directly in PR-authored ci.yml
    why_not: >
      That would expose persistent home runners to workflow YAML controlled by
      the candidate and erase the main-defined trust boundary.
  - option: Move every CI and control job to self-hosted capacity
    why_not: >
      Forks, untrusted work, semantic authority, fences and merge control must
      remain independent of the trusted execution plane.
  - option: Add a separate scheduler, queue, proof database or retry service
    why_not: >
      GitHub Actions and the existing semantic evidence/merge controller already
      own those roles; another plane would create split authority and lifecycle.
evidence:
  - "Issue #6351 P0R/P1/P2/P2R receipts"
  - "P2 runs 32960314514 and 32964925696"
  - "P3A-R PR #6487 merged as ac3f8a888e2ece7a15f37180c19dc247227a3098"
  - "P3A-R direct main proof run 33030976647 on pc-ci-3"
  - "P3B-A PR #6496 merged as 904863dabc490ee95ac50153048c25dee048d90b"
  - "P3B-A exact-head hosted run 33035115527"
  - "GitHub runner-group selected-workflow rule: only jobs directly defined in selected workflows may access the group"
affects: ["WS:CI-MERGE-CONTROL-PLANE", "WS:RUNNER-FLEET-RESILIENCE", ".github/runner-policy.yml", ".github/workflows/ci.yml", ".github/workflows/trusted-ci-executor.yml"]
confidence: high
reversibility: easy
decided_by: ceo-sol
decided_at: 2026-08-26
---

## P3B-A stop boundary

P3B-A may make the already selected main-owned reusable workflow call-capable for
one exact same-repository PR event and use at most the P2-accepted three PC slots.
It may not edit production ci.yml, change required-check names, expose the runner
group to another workflow, accept caller-supplied identity/plan/route inputs, or
move any hosted control, fork or untrusted route. Production stays hosted and
`production_enabled` stays false. Only the separate P3B-B carrier may route
ordinary PR traffic after P3B-A is merged and exact-main callable behavior is
available for that carrier to prove.

## P3B-B production boundary

P3B-B may add exactly one zero-input `ci.yml` reusable-workflow call to
`trusted-ci-executor.yml@refs/heads/main` for ordinary same-repository PRs.
`ci-plan`, `ci-pack-N` anchors, `ci-gate`, contract delta, fences and merge
control remain hosted. The anchors may consume only the called workflow's
trusted semantic fragments and must refuse any hosted/main plan-SHA mismatch
before republishing those bytes under the existing artifact names. Fork PRs
retain the full hosted pack implementation. The runner group remains reachable
only by `trusted-ci-executor.yml:trusted-pack`; no caller input, inherited secret,
candidate checkout or direct self-hosted label is permitted in the anchor path.
