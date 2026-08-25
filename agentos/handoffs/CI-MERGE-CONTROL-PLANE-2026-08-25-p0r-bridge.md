---
workstream: WS:CI-MERGE-CONTROL-PLANE
session: claude/ci-p0r-bridge
model: fable
ended_because: complete
decisions:
  - DEC:CI-EXECUTION-PROFILE-V2
mission: >
  Deliver the P0R diagnostic bridge frozen by Sol on issue #6351: reconcile the
  hardened self-hosted CI canary to the current production CI semantic contract
  (one authoritative plan, gate code, Python 3.12.13, truthful provenance,
  strict semantic-fragment parity) and replace the false ubuntu-latest runner
  contract with a runtime-attested portable Linux execution profile v2 — as one
  bounded wave of the #6286 -> P0R -> P1 -> P2 -> P3A/P3B -> P4 promotion
  sequence owned end-to-end by the Fable COO principal.
state_before: >
  PR #6286 (W3 ci-plan containment) had just merged as
  fafe8d7ee775f8b60a0229c085fb7aee6d4349e7 under Sol's corrected acceptance law
  (review 5023367453) and the recorded Chairman release. The diagnostic canary
  was BROKEN / CONTRACT_DRIFT: floating Python 3.12, no gate code, independent
  re-planning on every runner, and a pr-candidate plan shape
  (--changed-from under workflow_dispatch) the current engine refuses.
  agentos validate was red on main (exit 1) from schema defects in the
  2026-08-25 Defense D6-B0 handoff, which postdated #6286's tested tree. Live
  repo-runner census 2026-08-25T20:52Z: zero ci-linux / ci-linux-canary
  listeners registered; render-linux online via pc-render-2/3/4 (pc-render-1
  absent); org runner-group state unreadable from the fleet token.
changed:
  - path: scripts/run_ci_pack.py
    what: >
      Diagnostic pair (pr_head, workflow_dispatch) admitted ONLY for
      workflow == infrastructure-selfhosted-ci-canary in build_plan and
      load_authoritative_plan (SUPPORTED_PLAN_ROLE_EVENTS itself unchanged);
      RUNNER_CONTRACT v2 = ci-pack/linux-x86_64/python-3.12.13/node-20/v2;
      attest_execution_profile() fails closed before semantic execution when a
      plan is consumed or a fragment is emitted (no env/CLI bypass).
  - path: .github/workflows/selfhosted-ci-canary.yml
    what: >
      Python pinned 3.12.13 everywhere; planner passes full explicit
      provenance (pr>0 diagnostic pair with --gate code; pr_number=0 role main
      with tested==head==base and no --changed-from); both consumers consume
      the one frozen plan via --plan-json/--changed-files-file/--expect-*;
      fragments uploaded per pack; hosted-control and compare are matrices
      over the same selected packs for both slot counts.
  - path: scripts/select_ci_canary_packs.py
    what: >
      Fixed stale ci.pack_plan.v1 schema literal to v2 (the selector could
      never have accepted a real emitted plan); kept stdlib-only because the
      file is copied standalone across the trust boundary.
  - path: scripts/capture_ci_canary_receipt.py
    what: >
      Receipt schema v2 with fragment_schema/fragment_plan_sha256 reference
      and an optional --prewarm-seconds flag (CLI only, not yet wired).
  - path: scripts/compare_ci_canary_receipts.py
    what: >
      Strict canonical fragment equality after identity validation; imports
      only FRAGMENT_SCHEMA/canonical_sha256, never merge-authority entry
      points.
  - path: tests/
    what: >
      Mutation, admission, hostile, attestation, and workflow-structure tests
      across test_ci_pack.py, test_ci_pack_semantic.py, test_ci_canary_tools.py,
      test_ci_canary_workflows.py, test_ci_semantic_proof.py.
  - path: agentos/handoffs/DEFENSE-PROCUREMENT-V3-2026-08-25-d6b0-sol-acceptance-d6b-authorization.md
    what: >
      Initially carried a one-PR-per-pack heal of the schema defects redding
      agentos validate on main; sibling PR #6425 repaired the same record and
      landed on main first, so this branch YIELDED and took main's ratified
      copy verbatim (commit 246af73e4c63) rather than forcing a superseded
      regeneration over it. Net content change from this PR: none.
  - path: agentos/workstreams/WS-CI-MERGE-CONTROL-PLANE.md
    what: >
      W3-PLANNER-CONTAINMENT recorded done (PR #6286 receipts); new
      W-SELFHOSTED-BRIDGE wave; next_action names the #6351 ownership of pack
      materialization.
  - path: agentos/workstreams/WS-RUNNER-FLEET-RESILIENCE.md
    what: >
      Capability ledger (per Sol durability gate), live runner census, and the
      pc-render-1 landmine recorded; DEC:CI-EXECUTION-PROFILE-V2 cited.
  - path: agentos/decisions/DEC-CI-EXECUTION-PROFILE-V2.md
    what: >
      Records the deliberate semantic-contract version change and its
      non-comparability consequence.
verified:
  - claim: >
      The full targeted engine/canary test population passes with the bridge
      applied: 268 passed, exit 0.
    command: >
      python3 -m pytest tests/test_ci_pack.py tests/test_ci_pack_semantic.py
      tests/test_ci_canary_tools.py tests/test_ci_canary_workflows.py
      tests/test_ci_semantic_proof.py tests/test_runner_policy.py -q
    result: 268 passed, 3 warnings in 504.80s; exit code 0.
  - claim: agentos validate is green again with the heal applied.
    command: python3 scripts/agentos.py validate
    result: 714 records — 0 error(s), 33 pre-existing warning(s); exit 0.
  - claim: The rewired canary workflow parses.
    command: >
      python3 -c "import yaml; yaml.safe_load(open('.github/workflows/selfhosted-ci-canary.yml'))"
    result: >
      Parses cleanly; jobs trust-gate, plan, hosted-control, selfhosted-pack,
      cache-negative-control, contamination-probe, render-reservation-probe,
      compare.
  - claim: >
      scripts/ci_semantic_proof.py is byte-unchanged by this wave and refuses
      diagnostic plans.
    command: >
      git diff fafe8d7e -- scripts/ci_semantic_proof.py (empty) plus the two
      new hostile tests in tests/test_ci_semantic_proof.py.
    result: >
      Empty diff; hostile tests prove the diagnostic pair is double-refused and
      the pr0/main canary plan is refused by the workflow gate alone.
unverified:
  - claim: >
      Hosted and self-hosted semantic fragments will compare byte-equal on a
      green pack in a real P1 run (fragments carry no timing fields, so this
      should hold; red-path failure detail may embed runner paths).
    what_would_verify: P1 one-slot canary dispatch after CI listeners return.
  - claim: >
      The PC/WSL runtime can satisfy the v2 execution profile (Python exactly
      3.12.13 via setup-python toolcache on self-hosted Linux).
    what_would_verify: >
      P1 canary run: attest_execution_profile passes on a live ci-linux-canary
      listener.
unresolved:
  - >
    --prewarm-seconds exists on capture_ci_canary_receipt.py but is not wired
    into the workflow; prewarm timing is currently derivable only from the
    prewarm log and trace2. Wire it (or accept trace2 receipts) before P1
    acceptance judges the prewarm/fetch/checkout split.
  - >
    No automated FAIL yet on a promisor/lazy full-tree walk after
    materialization begins; P1/P2 acceptance must judge this from trace2 and
    cache before/after receipts until an automated guard is designed.
  - >
    .github/workflows/data-health.yml carries a stale comment naming the old
    v1 RUNNER_CONTRACT string (comment only; out of this wave's owned files).
next_actions:
  - >
    Consume the host-readiness lane's receipts for restored ci-linux-canary /
    ci-linux listeners; do not loosen workflow admission if the pool is absent.
  - >
    Run the live runner/group census at execution time, then P1: one-slot
    canary on one collision-safe same-repo PR candidate re-read at execution,
    per the #6351 P1 acceptance list including materialization receipts.
  - P2 three CI slots plus independent render-reservation proof.
  - P3A inert trusted executor, then P3B production route with hosted
    ci-pack-N anchors; P4 three natural PR proofs.
do_not_redo:
  - >
    Do not re-litigate the diagnostic-pair design: a generic
    pr_head/workflow_dispatch escape and a second planner/loader were
    explicitly rejected by Sol's freeze; the workflow-name-scoped admission is
    the accepted shape.
  - >
    Do not restore the v1 RUNNER_CONTRACT string or compare v2-era digests
    against v1-era evidence (DEC:CI-EXECUTION-PROFILE-V2 non-comparability).
  - >
    Do not dispatch the canary before live listeners exist; runner-policy
    registry state is not liveness proof.
danger_areas:
  - >
    attest_execution_profile has NO bypass by design; a runtime that cannot
    satisfy the profile blocks every pack it would have run — that is the
    contract, not a bug. STOP FOR SOL rather than broadening the profile.
  - >
    ci.yml's production packs now attest too (they pass --plan-json and
    --emit-semantic-fragment): hosted ubuntu-latest satisfies the profile
    today (3.12.13 pin, node 20, Linux x86_64), but a future hosted toolcache
    drift will fail closed loudly rather than silently changing the runtime.
  - >
    The compare job's strategy matrix reads needs.plan.outputs.matrix under
    if always(); a failed plan job can error the matrix expression itself —
    an honest red, but do not misread it as a comparator defect.
return_point: >
  Issue #6351 is the coordination/evidence carrier; Sol CEO incident command
  comment 2026-08-25T19:52Z is the standing command; the frozen bridge design
  is the 2026-08-24T06:21:57Z architecture-freeze comment plus the
  2026-08-25T19:44Z live-incident amendment. Protected Sol Skillpack pin
  51f9942733b86e550bb9169d2a43462bd28e774f; Macro main at wave start
  fafe8d7ee775f8b60a0229c085fb7aee6d4349e7.
---
