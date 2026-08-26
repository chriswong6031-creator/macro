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
  independently hosted. P3A declares workflow_call but refuses it at runtime;
  only a direct main workflow_dispatch whose caller-context workflow_ref is the
  exact trusted-ci-executor main path can run one proof pack. The PC host repeats
  that exact event/ref/workflow-ref/job decision before job start. P3B is the
  separate authority-changing wave that may admit the exact same-repository caller
  and move production execution.
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
  - "GitHub runner-group selected-workflow rule: only jobs directly defined in selected workflows may access the group"
affects: ["WS:CI-MERGE-CONTROL-PLANE", "WS:RUNNER-FLEET-RESILIENCE", ".github/runner-policy.yml", ".github/workflows/trusted-ci-executor.yml"]
confidence: high
reversibility: easy
decided_by: ceo-sol
decided_at: 2026-08-26
---

## P3A stop boundary

P3A may merge the inert reusable workflow, register its exact main path in the
existing runner group, and dispatch one real proof pack from main. It may not edit
production ci.yml, enable workflow_call admission, rename required checks, or move
any hosted control/untrusted route. Before the proof dispatch, all three drained PC
CI roots must receive and re-read the merged root-owned admission bytes. Those are
P3B decisions after P3A proof.
