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
      chain) canonical. PR 5591 was closed unmerged on 2026-08-15 and is now
      historical archaeology only; it carried the E2BIG defects this
      workstream's W-TRANSPORT fixed on main. Any successor must preserve the
      bounded transport — the wiring pins enforce it.
  - id: W-SEMANTIC-PROOF
    title: Semantic CI proof identity and ancestry-valid healing
    status: in_progress
    note: >
      Fresh-main bounded implementation commissioned by the 2026-08-14 CEO V2
      ruling is engineering-complete and awaiting its one pre-existing-gate
      bootstrap proof. Execution packs are transport only; one shared law keys
      evidence by logical job plus semantic proof ID, binds step/job execution
      digests, compares bounded non-empty failure signatures against exact-base
      BASE-code replay, accounts for every expected pack/job/step, and fails
      closed on infrastructure or malformed/absent advertised evidence.
      Authority-changing PRs cannot self-excuse. Main-red narrowing is allowed
      only for non-overlapping semantic units and never for infrastructure;
      ProofFreshness remains binding. Descendant healing requires real ancestry,
      accepts a per-unit PASS inside an overall-red main run, and is monotone.
      Both ship-loop and merge-on-green consume this same law. PR 5591 remains
      the prototype/canonical historical W-REWRITE lineage and was used only for
      surgical archaeology; this wave does not imply W-REWRITE is done.
next_action: >
  Run exactly one current required pre-existing bootstrap proof. If it is green,
  land normally, verify merged main, and only then mark W-SEMANTIC-PROOF done. If
  rotating unrelated fleet reds make the authority replacement unable to satisfy
  the old gate, stop with the CEO V2 BOOTSTRAP LANDING REQUIRED packet; do not
  self-excuse, admin-merge, or wait through repeated baselines. Do not begin the
  separate CI speed/scoping wave.
owns_paths:
  - ".github/workflows/ci.yml"
  - ".github/workflows/merge-on-green.yml"
  - "scripts/run_ci_pack.py"
  - "scripts/merge_on_green.py"
---

The E2BIG incident model and receipts live in
DSC:CI-CHANGED-FILES-ENV-HAS-AN-EXECVE-CEILING and the session handoff
CI-MERGE-CONTROL-PLANE-2026-08-14-e2big.md. The competing rewrite lineages'
own documentation lives in their PRs (5585 and 5591 both closed unmerged).
The mandatory pre-build semantic-step census is committed as
`DSC-CI-SEMANTIC-PROOF-MANIFEST-CENSUS.v1.json`.

## W-SEMANTIC-PROOF engineering receipts

- The pinned pre-build census records 193 logical jobs, 614 semantic steps,
  185 dependency-install steps, zero unnamed executable steps, and one
  two-step duplicate-name group. Only those two SBIR/STTR steps received
  explicit `proof_id` values. After fresh-main reconciliation the validated
  manifest has 194 logical jobs and 623 semantic units; no new ambiguity was
  introduced.
- `ci.pack_plan.v2` binds workflow/run/event role, tested merge tree, subject
  head, exact base, changed-file digest, semantic inventory, execution digests,
  and transport partition. `ci.semantic_fragment.v1` carries raw bounded pack
  observations. `ci.semantic_evidence.v1` is written once by `ci-gate`, including
  on planner failure, and is the only semantic-era causality verdict.
- Exact-base replay creates one independently pinned checkout, uses the base
  checkout's runner and manifest, and runs at most one serial child per failed
  logical job under one 900-second deadline. It does not create a replay matrix.
- The hostile mutation battery killed 14/14 required mutations. It exposed and
  closed a real missing-ancestry regression fixture before reaching zero
  survivors. Fresh review also closed main infrastructure bypass, job-level
  infrastructure healing, inactive pilot-authority context handling, and a
  production Unicode plan-digest mismatch.
- Local performance at the pre-release carrier: semantic inventory median
  6.316 ms (p95 9.010 ms), full plan median 9.233 ms, bounded failure capture
  over 1,001 representative lines median 0.444 ms (p95 0.702 ms), and full
  194-job/622-unit reconciliation median 12.106 ms (p95 18.490 ms). Exact-base
  checkout became ready in 129.346 s and checkout plus bounded cleanup took
  160.354 s, inside the shared 900-second red-only budget. These are overhead
  measurements, not a claim that the CI suite itself is faster.
- Green consumer paths make zero semantic artifact calls. A linked red PR lookup
  is bounded to three JSON calls plus one artifact download; descendant history
  is capped at 12 candidates. Main semantic dispatch is exact-SHA-bound and costs
  at most three calls when a red breaker lacks current evidence.
- Bootstrap remains deliberately unresolved in this file: this authority-changing
  branch must earn the old required checks without using its new inherited-red
  reasoning. Status stays `in_progress` until merged-main verification.
