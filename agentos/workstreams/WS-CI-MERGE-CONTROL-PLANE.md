---
key: CI-MERGE-CONTROL-PLANE
title: CI + merge control-plane recovery (the 2026-08 traffic jam)
objective: >
  A PR loop where ordinary changes validate in single-digit minutes, structural
  mistakes red in ~2 minutes, armed PRs merge without babysitting, and a
  fast-moving producer main cannot re-prove the universe. Done = the 2026-08-14
  incident doc's §0 acceptance list holds on live runs.
status: awaiting_ci
program: project-active-build-control
repos: [macro]
owner: coo-fable
class: build
blast_radius: reversible
ambiguity: scoped
waves:
  - id: W0
    title: Incident model + merge-queue verdict + structural repair PR
    status: awaiting_ci
    note: >
      PR #5585 (metadata planner, plan consumption, preflight, narrative tier,
      dynamic packs, sweeper wake diet + verified markers). Evidence:
      research/CI_MERGE_CONTROL_PLANE_RECOVERY_2026_08_14.md;
      DEC:CI-NATIVE-MERGE-QUEUE-REJECTED.
  - id: W1
    title: Heavy-tail curation (scope exclusive) + engine-render-guards split
    status: todo
    note: chipped as standalone tasks 2026-08-14; mechanism already shipped in W0.
next_action: >
  Verify PR #5585's own full-suite run (31777710942), arm merge-on-green, then
  run the two live probes (narrow md PR; unwired-test red-fixture PR) and write
  the closure report into the recovery doc §5.
owns_paths:
  - ".github/workflows/ci.yml"
  - ".github/workflows/merge-on-green.yml"
  - "scripts/run_ci_pack.py"
  - "scripts/ci_plan_changed_files.py"
  - "scripts/merge_on_green.py"
  - "docs/CI_MERGE_ARCHITECTURE.md"
---

The jam's mechanism, measurements, and repair architecture live in
research/CI_MERGE_CONTROL_PLANE_RECOVERY_2026_08_14.md; the succinct current
state lives in docs/CI_MERGE_ARCHITECTURE.md. Merge-queue adoption is settled
by DEC:CI-NATIVE-MERGE-QUEUE-REJECTED (reopen precondition recorded there).
