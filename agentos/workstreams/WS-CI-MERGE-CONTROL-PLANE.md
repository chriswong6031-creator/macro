---
key: CI-MERGE-CONTROL-PLANE
title: CI + merge control-plane recovery (the 2026-08 traffic jam)
objective: >
  A PR loop where ordinary changes validate quickly, structural mistakes red
  in minutes, armed PRs merge without babysitting, and a fast-moving producer
  main cannot re-prove the universe — with no transport in the pipeline that
  an unbounded changed-file list can kill.
status: active
program: project-active-build-control
repos: [macro]
owner: coo-fable
class: build
blast_radius: reversible
ambiguity: open
waves:
  - id: W-TRANSPORT
    title: Bounded changed-files transport (E2BIG repair, PR 5578 incident)
    status: awaiting_ci
    note: >
      Landed directly on main's architecture after both rewrite lineages
      churned: the list rides the ci-changed-files artifact, its sha256 joins
      plan_hash_payload so --expect-plan-sha pins it, children read
      CI_CHANGED_FILES_FILE, and the CI_CHANGED_FILES_JSON env/output hops are
      deleted. Evidence: DSC:CI-CHANGED-FILES-ENV-HAS-AN-EXECVE-CEILING;
      E2BIG execve mutation regression in tests/test_ci_pack.py; wiring pins
      in tests/test_ci_plan_workflow.py.
  - id: W-REWRITE
    title: Structural rewrite of planner/merge control plane
    status: in_progress
    note: >
      Two lineages collided 2026-08-14: PR 5585 (claude — API diff, plan
      consumption, wake diet) was closed in a reconciliation naming PR 5591
      (codex — authority plan artifact, committed scope index, evidence
      chain) canonical; 5591 is under active iteration and carries the E2BIG
      defects this workstream's W-TRANSPORT fixed on main (receipts posted on
      the PR). Whichever lineage lands must preserve the bounded transport —
      the wiring pins enforce it.
next_action: >
  Drive W-TRANSPORT through merge, then close/reopen PR 5578 for real pack
  execution at its exact head; the 5591 lineage owns the comparison-base law
  and the sweeper wake diet; merge-on-green re-enablement is an operator
  decision.
owns_paths:
  - ".github/workflows/ci.yml"
  - ".github/workflows/merge-on-green.yml"
  - "scripts/run_ci_pack.py"
  - "scripts/merge_on_green.py"
---

The E2BIG incident model and receipts live in
DSC:CI-CHANGED-FILES-ENV-HAS-AN-EXECVE-CEILING and the session handoff
CI-MERGE-CONTROL-PLANE-2026-08-14-e2big.md. The competing rewrite lineages'
own documentation lives in their PRs (5585 closed, 5591 open).
