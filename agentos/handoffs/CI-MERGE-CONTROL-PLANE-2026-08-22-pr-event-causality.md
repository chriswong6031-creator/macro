---
workstream: "WS:CI-MERGE-CONTROL-PLANE"
session: claude/pr-event-causality-closure
model: codex
ended_because: ci_handoff
mission: >
  Make an unchanged PR candidate re-provable while main advances and GitHub
  delivers lifecycle events out of order, without changing semantic-proof law,
  modifying PR #6223 or #5898, or adding a separate cancellation service.
state_before: >
  PR #6223's valid corrective event carried exact subject 725f9867 and same
  trusted main ref, but ci-authority/main run 32590096081 rejected it when the
  live main SHA advanced beyond the event base. In the same cycle, GitHub created
  the reopened semantic run 32590096269 before the older closed-event run
  32590097404; the delayed close shared the PR concurrency group and cancelled
  the newer proof before ci-plan completed.
changed:
  - path: scripts/ci_authority.py
    what: >
      Separate candidate authority from integration composition: retain event
      base SHA as provenance, record pre/post file-enumeration base observations,
      bind the exact head/repositories/base ref/author, and reacquire canonical
      changed paths when same-ref base movement crosses pagination.
  - path: tests/test_ci_authority.py
    what: >
      Add hostile positive and negative cases for event A/live B, B-to-C movement,
      same-count path substitution, changed-count drift, ref retarget, head drift,
      non-admin refusal, and same-repository admin admission.
  - path: .github/workflows/ci.yml
    what: >
      Remove closed from the semantic pull-request trigger and retire its dead
      concurrency suffix and job-level fences; opened, synchronize, and reopened
      remain the only proof-producing lifecycle events.
  - path: tests/test_ci_plan_workflow.py
    what: >
      Pin the exact proof-event trigger set, PR-number concurrency group, dispatch
      non-cancellation, and simplified planner/pack/gate conditions.
  - path: tests/test_ci_pack.py
    what: >
      Replace the historical merged-close assertion with structural tripwires
      proving closed cannot schedule or enter the live PR proof group.
  - path: agentos/discoveries/DSC-PR-EVENT-DELIVERY-IS-NOT-CANDIDATE-IDENTITY.md
    what: >
      Record the live-verified causal-order and mutable-base identity landmine,
      its falsifier, and the split between candidate and integration authority.
  - path: agentos/workstreams/WS-CI-MERGE-CONTROL-PLANE.md
    what: >
      Add W-PR-EVENT-CAUSALITY as awaiting_ci, cite the discovery, add
      scripts/ci_authority.py ownership, and preserve every adjacent wave.
  - path: agentos/handoffs/CI-MERGE-CONTROL-PLANE-2026-08-22-pr-event-causality.md
    what: >
      Provide the cold-start continuation packet and exact remaining bootstrap,
      CI, merge, and containment proof obligations.
verified:
  - claim: >
      The focused authority mutation battery and semantic workflow-structure
      suite pass with the new candidate/base split and lifecycle trigger law.
    command: >
      python3 -m pytest tests/test_ci_authority.py
      tests/test_ci_plan_workflow.py -q
    result: "92 passed in 10.08s"
  - claim: >
      The owning CI-pack concurrency and hosted-pack wiring cases accept the new
      trigger/group contract without changing pack allocation or runner policy.
    command: >
      python3 -m pytest tests/test_ci_pack.py -q -k
      'workflows_cancel_superseded_pr_runs or
      ci_pack_uses_twelve_balanced_hosted_jobs'
    result: "2 passed, 94 deselected in 2.88s"
  - claim: >
      The full owning CI-pack, semantic-proof, merge-on-green, and ship-loop
      regression surface remains green after the causality repair.
    command: >
      python3 -m pytest tests/test_ci_pack.py tests/test_ci_pack_semantic.py
      tests/test_ci_semantic_proof.py tests/test_merge_on_green_semantic.py
      tests/test_ship_loop_semantic.py -q
    result: "261 passed in 508.95s"
  - claim: >
      Every workflow parses, the workflow validator controls pass, every legacy
      CI job registration validates, and AgentOS records are schema-clean.
    command: >
      python3 scripts/check_workflow_yaml.py && python3
      scripts/check_workflow_yaml.py --selftest && python3
      scripts/run_ci_pack.py --workflow .github/ci/legacy-jobs.yml
      --validate-only && python3 scripts/agentos.py validate
    result: >
      93 workflows valid; 4 workflow-validator controls pass; 200 legacy jobs
      valid; AgentOS reports zero errors (27 pre-existing warnings).
unverified:
  - claim: >
      The exact candidate head is admitted by the pre-existing ci-authority/main
      implementation despite normal same-ref main movement.
    what_would_verify: >
      A successful active ci-authority/main check on the final candidate head;
      if the old gate false-reds solely on event/live main SHA drift, one bounded
      metadata-only edited event may re-evaluate it without changing the branch.
  - claim: >
      Semantic CI, contract-delta, fences, workflow syntax, and every selected
      pack conclude green on one exact candidate head.
    what_would_verify: >
      Concluded exact-head ci and fences runs, clear ci.semantic_evidence.v1,
      successful contract-delta/ci-gate/fence-pack and published fence contexts.
  - claim: >
      Current main contains the repair.
    what_would_verify: >
      Normal exact-head-pinned squash merge followed by a fresh origin/main fetch
      and ancestry/remote containment proof for the resulting merge SHA.
unresolved:
  - >
    GitHub exposes no atomic PR/files/permission snapshot. The controller closes
    observable candidate/count races and conditionally discards a crossed
    inventory, then requires one bounded replacement enumeration bracketed by a
    stable live base SHA; a fully unobservable platform ABA interval remains
    residual API risk and is not represented as atomic proof.
  - >
    The landing PR changes authority code, so the current main implementation —
    not the candidate's new rule — must admit it. Fast producer movement may require
    the one authorized metadata-only edited re-evaluation.
next_actions:
  - >
    Finish local owning validation, AgentOS validation, workflow YAML parsing, and
    an independent security review; resolve every blocker before committing.
  - >
    Re-fetch current main, audit scoped overlap, reconcile mechanically if needed,
    then commit, push, and open one bounded control-plane PR.
  - >
    Require old-authority ci-authority/main, semantic CI and contract-delta,
    fences, syntax, and the exact selected pack universe green on the final head.
  - >
    Squash-merge normally with the expected subject head pinned, prove current
    main contains the merge, then return to Sol without touching PR #5898.
do_not_redo:
  - >
    Do not restore event base SHA == live base SHA as candidate identity. Event
    base remains provenance; semantic CI parent 1 remains exact tested-base law.
  - >
    Do not restore closed as an implicit cancellation event or build a replacement
    cancellation service in this wave. Runner reclamation is a separate capability.
  - >
    Do not weaken PR #5750 semantic identity, pack accounting, contract-delta,
    required check names, or base-specific authority contexts.
  - >
    Do not modify, synchronize, re-run, close/reopen, arm, or merge PR #6223 or
    PR #5898 from this wave.
danger_areas:
  - >
    A same-ref base move across file pagination requires bounded inventory
    reacquisition and a stable second bracket. Ignoring the list because only the
    base moved could hide an authority path behind an unchanged count; accepting
    endless movement would claim an inventory snapshot the API never proved.
  - >
    Workflow job conditions run after concurrency allocation. A closed trigger
    plus a job-level skip is still able to replace/cancel an active proof and is
    therefore not a lawful substitute for trigger exclusion.
  - >
    Authority permissions are live and non-atomic with check publication. Do not
    cache them across runs or treat write/maintain as admin.
discoveries:
  - "DSC:GITHUB-CONCURRENCY-SUPERSEDES-PENDING"
  - "DSC:PR-EVENT-DELIVERY-IS-NOT-CANDIDATE-IDENTITY"
---

## 0. State

The candidate implements one bounded capability: unchanged PR candidates can be
re-proven while the trusted base ref advances and lifecycle delivery is inverted.
Local focused proof is green. Exact-head GitHub proof, old-authority bootstrap,
normal merge, and main containment remain to be completed by the owning session.

## 1. What is left

Run the owning local validation and independent red team, reconcile only scoped
current-main overlap, then carry one PR through exact-head checks, normal squash,
and current-main containment. If the old active authority context alone false-reds
because main moved, use only the bounded metadata edit allowed by the mission.

## 2. What will bite you

GitHub Actions concurrency is evaluated before any job or identity script. A job
condition cannot make a closed event harmless. Conversely, removing live base SHA
from candidate identity without stabilizing the changed-path population creates a
same-count authority-classification race; the conditional reacquisition is the
load-bearing complement to the relaxed SHA equality.

## 3. What was decided and found

DSC:PR-EVENT-DELIVERY-IS-NOT-CANDIDATE-IDENTITY records the incident. No new
Decision is required: the implementation applies existing semantic-proof and
pending-supersession law to a newly observed event-order failure.

## 4. Not in scope

No Fundamental Forensics, Capital Structure, Prophet, render, branch protection,
pack sizing, runner allocation, merge-on-green, semantic scoring, self-mod
immutable-set, #6223, or #5898 change belongs in this packet.
