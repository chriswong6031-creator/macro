---
workstream: WS:TERMINAL-GITHUB-CANONICALIZATION
session: sol/terminal-github-canonicalization-agentos-20260830
model: sol
ended_because: ci_handoff
mission: >
  Establish the durable Agent OS home for Terminal GitHub canonicalization, preserve the accepted
  Wave-0 production topology, record the GitHub-source-authority ruling, and hand the exact PR #484
  acceptance frontier to the next fresh Sol session without creating a runtime or deployment plane.
state_before: >
  Terminal issue #483 was the only durable program carrier. Wave 0 had been accepted in GitHub and
  Slack, PR #484 carried the Wave-1 source audit, but Macro Agent OS contained no workstream,
  decision, discovery or continuation handoff for the multi-wave program.
changed:
  - path: agentos/workstreams/WS-TERMINAL-GITHUB-CANONICALIZATION.md
    what: >
      Created the durable six-wave organizational home, capability frontier, landmines,
      do-not-redo boundaries and exact next action for Terminal issue #483.
  - path: agentos/decisions/DEC-TERMINAL-GITHUB-OWNS-IMPLEMENTATION-TRUTH.md
    what: >
      Recorded the Chairman ruling that GitHub owns normal Terminal implementation/evidence while
      the host retains only explicit runtime/config/secret boundaries and emergency divergence law.
  - path: agentos/discoveries/DSC-TERMINAL-PRODUCTION-SOURCE-CLEAN-PLAIN-COPY.md
    what: >
      Preserved the falsifiable Wave-0 finding that the serving plain copy matched a pristine
      accepted checkout with zero unexplained implementation drift at the observation time.
  - path: agentos/handoffs/TERMINAL-GITHUB-CANONICALIZATION-2026-08-30.md
    what: >
      Recorded immutable pins, exact RED/GREEN receipts, remaining acceptance gates and the ordered
      continuation into Wave 2 after #484 acceptance.
verified:
  - claim: Protected Sol procedure was loaded atomically from one compatible commit.
    command: >
      GitHub.fetch Mastermind branches/master then GitHub.fetch_file docs/sol_skills/INDEX.md and
      every required skill at 75b90cfeb4752d2a356a463b351382c1e0c25cb1
    result: >
      mastermind.sol_skillpack.v1 version 1.0.1, minimum bootstrap major 1, bootstrap major 1
      compatible; protected commit 75b90cfeb4752d2a356a463b351382c1e0c25cb1.
  - claim: Wave 0 recovered the current production source topology without mutation.
    command: >
      GitHub.fetch_issue_comments mastermindx-market-intelligence/mastermind-terminal#483 and
      Slack.slack_read_thread operation terminal-github-canonical-deploy-20260829-sol-001
    result: >
      Accepted production receipt names /opt/terminal/terminal as serving plain copy,
      /opt/terminal/.gitsrc as pristine checkout, deployed accepted SHA
      b1b21a17f843d23e6e77d2abf0cc7e3dfd28ccea, and zero unexplained implementation drift.
  - claim: The final stdout regression failed against the pre-fix head for the intended reason.
    command: GitHub.fetch_workflow_job_logs job 99209177107 from run 33293505721
    result: >
      test_cli_stdout_failure_returns_documented_blocking_code returned process code 120 instead of
      64 with BrokenPipeError during shutdown; the rest of Python reported 798 passed, 7 skipped.
  - claim: The minimal stdout repair passed the full hosted Python required job.
    command: GitHub.fetch_workflow_job_logs job 99209310890 from run 33293571359
    result: >
      Ingest + signal-layer tests SUCCESS on exact head
      6164f6c1cae733b2b1657b0ae38de4aefdafb7e3 with 799 passed, 7 skipped.
  - claim: PR #484 remained the one open Wave-1 implementation carrier at record creation.
    command: >
      GitHub.get_pr_info mastermindx-market-intelligence/mastermind-terminal#484 and
      GitHub.search_prs query deploy in mastermindx-market-intelligence/mastermind-terminal
    result: >
      PR #484 open, mergeable, non-draft, branch sol/terminal-source-audit-wave1, exact head
      6164f6c1cae733b2b1657b0ae38de4aefdafb7e3; no second active deploy-hardening PR found.
unverified:
  - claim: The protected Terminal typecheck, unit and responsive-E2E job is green on exact head 6164f6c1cae733b2b1657b0ae38de4aefdafb7e3.
    what_would_verify: >
      Re-read workflow run 33293571359 and require job Terminal typecheck + tests to be completed
      with conclusion success on the same immutable PR head.
  - claim: The final independent Opus exact-head review finds no unresolved BLOCKER or MAJOR.
    what_would_verify: >
      Read the RESULT on Slack carrier C0BSBM78V1N/1788065824.919679 for operation
      terminal-source-audit-pr484-final-review-20260830-sol-001 and re-pin PR #484 head unchanged.
  - claim: PR #484 is accepted, merged and available on Terminal master.
    what_would_verify: >
      After the two preceding gates pass, record Sol acceptance, merge through the existing lawful
      protected path, and re-read Terminal master plus the merged PR immutable merge SHA.
  - claim: Exact accepted-SHA production deployment and truthful rollback receipts are built and live.
    what_would_verify: >
      Complete Wave 2 from fresh Terminal master, then run the reviewed source preflight, real
      deployment, failure/rollback drill, deployed-SHA readback and service/browser/data proof.
unresolved:
  - PR #484 cannot merge until the final protected Terminal job and independent exact-head review both pass.
  - Wave 2 needs a narrow production source-audit policy derived from the accepted Wave-0 census.
  - The canonical deploy must distinguish attempted, deployed and rollback identities and must not overclaim app/runtime atomicity after a post-health runtime-sync failure.
  - Repository ruleset, CODEOWNERS, merge-method, security and dependency settings must reconcile with the parallel GitHub Estate Governor before Terminal-specific mutation.
  - Private repository visibility remains held until connected-tool/operator access, deploy authentication, private-safe fetches and rollback are proven.
next_actions:
  - Re-pin protected Skillpack, Terminal master, PR #484 head, run 33293571359 and the final-review Slack carrier.
  - If any head moved, return STALE_HEAD and review the new immutable head rather than inheriting old evidence.
  - If all three required checks and the independent review pass, record Sol acceptance and merge exact PR #484 through the existing protected merge path without administrator bypass.
  - Re-read the merged Terminal master and update this workstream W1 to done before starting Wave 2.
  - Start Wave 2 only after a fresh collision census; derive the production policy from W0, implement explicit accepted-SHA deploy and complete attempted/deployed/rollback receipts using the existing deploy controller.
  - Production-prove the canonical deploy, responsive browser surfaces, representative real Macro-backed data, drift refusal and rollback before advancing repository privacy.
do_not_redo:
  - Do not rerun broad production archaeology unless a fresh audit falsifies the accepted W0 topology or a later release changes it.
  - Do not create another source-audit command, deploy controller, deployment database, scheduler, merge bot or lifecycle store.
  - Do not revive the terminal prior review/repair children that Sol explicitly stopped; use the final-review carrier named in unverified.
  - Do not treat a source-audit CLEAN result, CI green, merge, healthy HTTP 200 or matching marker as complete production proof.
  - Do not move Macro data producers, mutable market data, environment configuration or secrets into Terminal Git.
danger_areas:
  - The serving tree is a plain copy, so destructive convergence before a fresh preflight can erase a newly introduced host-only implementation delta.
  - The deployed marker and .next build can diverge during failed health or rollback unless both identities move together and are receipted.
  - Runtime-code synchronization occurs after application health in the historical builder; later failure can leave a mixed app/runtime generation.
  - The builder historically self-installs for the next deploy, making the first rollout a distinct bootstrap operation.
  - Merge-on-green uses privileged trusted-default-branch code; self-modification, check provenance, label authority and native bypass require hardening in place rather than replacement.
prs: [484]
decisions: [DEC:TERMINAL-GITHUB-OWNS-IMPLEMENTATION-TRUTH]
discoveries: [DSC:TERMINAL-PRODUCTION-SOURCE-CLEAN-PLAIN-COPY]
---

## Continuation state

The durable source of program truth is Terminal issue #483 plus this Agent OS workstream. PR #484
is an independently useful source-audit vertical, not the full deployment program. Its merge makes
the command available on Terminal master and changes no production bytes.

The exact next branch of work is binary:

- **Acceptance path:** immutable head `6164f6c1cae733b2b1657b0ae38de4aefdafb7e3`, all protected checks SUCCESS,
  independent final review PASS, then Sol accepts and merges through the existing protected path.
- **Repair path:** any new review finding or head movement stays on PR #484; write RED first,
  reproduce it in hosted evidence, apply the smallest repair, and restart exact-head review.

Only the accepted merge opens Wave 2. Wave 2 must preserve one canonical deployment controller,
reuse PR #484 as the pre-mutation source fence, and make release/rollback state mechanically
observable without creating another runtime or truth store.
