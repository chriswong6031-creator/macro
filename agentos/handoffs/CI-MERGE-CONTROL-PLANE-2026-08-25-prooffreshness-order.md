---
workstream: "WS:CI-MERGE-CONTROL-PLANE"
session: claude/ci-prooffreshness-before-semantic-20260825
model: codex
ended_because: ci_handoff
mission: >
  Make stale semantic evidence reach the existing ProofFreshness
  reconciliation/reproof path before its historical classifications receive a
  current merge or blocking verdict, without modifying PR #6391 or creating a
  second dispatcher, label, proof store, or refresh ledger.
state_before: >
  Pickup 221f72b413ed8250548f6393ecb665ea894ee293 classified semantic
  evidence inside sweep_pull and returned its blocked disposition before the
  later freshness.stale_for/reprove block. PR #6391 exposed the defect with
  unchanged subject 0f929e4e, historical tested base f2de463c, inherited_base=1,
  unknown=1, and unknown outcome not_run_prior_failure after current main had
  healed the inherited Price-of-Duration defect.
changed:
  - path: scripts/merge_on_green.py
    what: >
      Preserve physical pending/incomplete terminals, load and bind actual
      semantic-v1 evidence, then run the existing ProofFreshness disposition
      before semantic classification; stale receipts use only reprove(), while
      current receipts retain exact semantic authority. Legacy, malformed, and
      green zero-artifact paths keep their prior behavior. Reproof diagnostics
      now truthfully cover stale red as well as stale green.
  - path: tests/test_merge_on_green_semantic.py
    what: >
      Add the exact #6391 regression plus hostile stale-green, fresh-unknown,
      fresh-regression, pending-generation, legacy-absent, main-red non-overlap,
      no-duplicate, and truthful-reproof discriminators.
  - path: agentos/decisions/DEC-STALE-SEMANTIC-PROOF-HAS-NO-CURRENT-VERDICT-AUTHORITY.md
    what: >
      Record Sol's durable decision that freshness is symmetric prerequisite
      authority and does not change semantic classification vocabulary.
  - path: agentos/discoveries/DSC-SEMANTIC-REFUSAL-BYPASSED-PROOFFRESHNESS.md
    what: >
      Record the verified control-flow landmine, falsifier, and required future
      decision sequence.
  - path: agentos/workstreams/WS-CI-MERGE-CONTROL-PLANE.md
    what: >
      Extend the existing canonical owner with W-PROOFFRESHNESS-ORDER as
      awaiting_ci; preserve all adjacent waves and ownership.
  - path: agentos/handoffs/CI-MERGE-CONTROL-PLANE-2026-08-25-prooffreshness-order.md
    what: >
      Provide this exact continuation packet, verification receipts, inherited
      baseline blocker, live-canary boundary, and no-touch instructions.
verified:
  - claim: >
      The old #6391-shaped path was RED for the intended ordering reason before
      the implementation change, then the focused semantic-controller surface
      passed with every hostile discriminator.
    command: >
      python3 -m pytest
      tests/test_merge_on_green_semantic.py::test_stale_6391_semantic_receipt_reproves_before_unknown_can_block
      -q; then python3 -m pytest tests/test_merge_on_green_semantic.py -q
    result: >
      RED failed at mark_blocked with `stale semantic receipt gained blocking
      authority`; GREEN concluded 45 passed before the final cross-layer case,
      which then passed independently.
  - claim: >
      The complete directly owning merge controller, semantic proof,
      ProofFreshness, authority/lifecycle, workflow-control, canary, runner, and
      ship-loop regression surface is green.
    command: >
      python3 -m pytest tests/test_merge_on_green.py
      tests/test_merge_on_green_semantic.py tests/test_ci_semantic_proof.py
      tests/test_ci_authority.py tests/test_ci_plan_workflow.py
      tests/test_ci_pack.py tests/test_ci_pack_semantic.py
      tests/test_ship_loop_semantic.py tests/test_ci_canary_tools.py
      tests/test_ci_canary_workflows.py tests/test_runner_policy.py -q
    result: "770 passed in 404.30s; three unrelated macOS pytest cleanup warnings"
  - claim: >
      Workflow YAML, validator controls, and the complete legacy job registry
      remain structurally valid; the diff is whitespace-clean.
    command: >
      python3 scripts/check_workflow_yaml.py && python3
      scripts/check_workflow_yaml.py --selftest && python3
      scripts/run_ci_pack.py --workflow .github/ci/legacy-jobs.yml
      --validate-only && git diff --check
    result: >
      94 workflows valid; 4 validator controls pass; 203 legacy jobs valid;
      git diff --check emits no finding.
  - claim: >
      The independent adversarial review found no authority widening after the
      pending, legacy-boundary, and truthful-diagnostic repairs.
    command: >
      Independent subagent review followed by `python3 -m pytest -q
      tests/test_merge_on_green_semantic.py tests/test_merge_on_green.py` and
      `git diff --check`
    result: "PASS; 405 passed; no blocking security finding"
  - claim: >
      Candidate AgentOS records introduce no new validation error compared with
      the pickup/current-main store.
    command: >
      python3 scripts/agentos.py validate on origin/main fixture worktree and on
      the controller candidate worktree
    result: >
      Both stores report the same 8 inherited errors in the unrelated
      DEFENSE-PROCUREMENT-V3 d6b0 Sol-acceptance handoff; candidate record count
      increases 709 to 711 before this handoff with zero additional error kind
      or path.
unverified:
  - claim: >
      The final controller subject has complete exact-head hosted semantic CI,
      fences, and active authority proof.
    what_would_verify: >
      Concluded checks on the final pushed controller head: ci-plan,
      contract-delta, every selected pack, ci-gate clear, zero infrastructure,
      fence-pack, self-mod-fence, capability-broker, grader-manifest, and active
      ci-authority/main.
  - claim: >
      The real candidate controller observes a live stale semantic-red receipt,
      reaches exactly one lawful reproof action, and performs no merge.
    what_would_verify: >
      Disposable draft fixture PR #6423 must finish its intentional semantic-red
      proof, ordinary independent main movement must make that receipt stale,
      and the exact candidate sweep_pull must be invoked only for #6423 behind a
      non-GET write firewall; freshness must precede semantic classification and
      no GitHub mutation may occur.
  - claim: >
      Canonical AgentOS validation is globally green.
    what_would_verify: >
      A separate owner repairs the eight inherited schema errors in
      agentos/handoffs/DEFENSE-PROCUREMENT-V3-2026-08-25-d6b0-sol-acceptance-d6b-authorization.md
      on main; this PR must not absorb that unrelated repair.
unresolved:
  - >
    Current main inherited eight AgentOS schema errors from the D6-B0 Sol
    acceptance handoff at pickup. They are outside this controller capability;
    local AgentOS validation therefore cannot become globally green without an
    unlawful second repair.
  - >
    The checked-in hosted canary is intentionally read-only and contractually
    forbidden from executing merge_on_green.py; workflow_dispatch sweeps the
    whole armed backlog. The bounded live proof therefore uses the expressly
    permitted disposable draft fixture plus the existing direct sweep_pull seam
    and a write firewall, never main().
next_actions:
  - >
    Finish disposable fixture #6423's semantic-red proof and wait only for
    ordinary independent product/main movement that makes it stale; do not
    mutate main to manufacture staleness.
  - >
    Commit and push the bounded controller carrier, open the exact required
    draft HOLD-FOR-SOL PR, and run the write-fenced live single-candidate proof
    from that exact commit.
  - >
    Require every hosted semantic/fence/authority check to conclude on one exact
    controller head; keep native auto-merge null and do not add merge-on-green.
  - >
    Return the held controller PR and the inherited AgentOS baseline receipt to
    Sol. Do not operate #6391 until Sol accepts and lands this controller wave.
do_not_redo:
  - >
    Do not map unknown, inherited_base, or any semantic classification to
    freshness. A current unknown or regression is final and blocking; a stale
    green is just as non-authoritative as a stale red.
  - >
    Do not add a force-proof label, second workflow dispatcher, retry ledger,
    proof database, or alternate update-branch seam. Existing ProofFreshness,
    reprove(), refresh lease, and live authorization are the one control plane.
  - >
    Do not broaden actual semantic-v1 behavior to pre-epoch legacy_absent
    evidence, and do not let preloaded historical evidence override a pending
    physical proof generation.
  - >
    Do not modify, refresh, relabel, close/reopen, rebase, merge, or use PR #6391
    as a canary. Do not touch FF production or dispatch recovery.
danger_areas:
  - >
    Moving semantic classification ahead of freshness restores the production
    dead end; moving freshness ahead of artifact-mode/binding discovery widens
    legacy or malformed evidence; moving either ahead of pending physical
    anchors can dispatch duplicate generations.
  - >
    A stale receipt has zero current authority, not positive authority. The only
    lawful response is the existing reconciled head becoming unproven and earning
    a new independently bound proof; reproof itself never authorizes a merge.
  - >
    The real canary must call sweep_pull for one exact draft fixture. Calling
    merge-on-green main() would enumerate and potentially mutate unrelated armed
    PRs, and is forbidden for this proof.
decisions:
  - "DEC:STALE-SEMANTIC-PROOF-HAS-NO-CURRENT-VERDICT-AUTHORITY"
discoveries:
  - "DSC:SEMANTIC-REFUSAL-BYPASSED-PROOFFRESHNESS"
---

## Current boundary

The implementation is locally built and independently reviewed, but the wave is
not accepted or merge-authorized. PR #6391 remains a separate unchanged
production witness. The disposable canary is evidence infrastructure only and
must never land.

## Same-carrier recovery — 2026-09-05 (Claude8 Opus, operation ci-prooffreshness-order-recovery-20260829-sol-001)

The original session above ended pre-CI. Sol re-placed the SAME operation on the
SAME PR #6426 and SAME branch; the preserved head
`9b47c60d9fc5ca8f0e1b5fe9a5d0693fb141eb6e` was never rebased, reset, forced or
replaced.

**Current-base integration.** `origin/main` was merged into the branch with
`--no-ff` (merge commit 0ebb026948ff414499052bba7f1ba6be1e324abf, parents 9b47c60d9fc5 and
aabae60174ab). Both histories are preserved. The single conflict was
`agentos/workstreams/WS-CI-MERGE-CONTROL-PLANE.md`, where main and this branch
each appended to `discoveries:`; resolved as a union with no entry dropped and
no unrelated main byte altered. The candidate's delta against current main is
exactly the seven authorized paths.

**Supersession re-checked, not assumed.** Macro main moved four times during
this session (443fe9a6 → a1b3d9ea → 88af13cf → aabae601). At each re-pin the
newest commit touching `scripts/merge_on_green.py` was still
`8a1b938890614408d7cf3da654d998fc5fe9808a` (2026-08-21), so the temporal-authority
defect was never functionally superseded.

**Bounded repair added** (`PROOF_SURFACE_UNAVAILABLE`, see the DEC amendment and
the DSC's second failure mode): `pull_files()` now classifies HOW the inventory
was observed rather than collapsing five conditions into one `None`. Only a
positively observed transport failure defers with zero non-GET effects;
truncated/broad and complete-unclassified inventories keep their prior
conservative reproof, and an inventory not read through `pull_files` this sweep
also stays on the conservative path.

**Proof.**
- RED→GREEN (new repair): 9 focused tests failed on the merge parent, pass after.
- RED→GREEN (ordering): disabling ONLY the `proof_freshness_disposition()` call
  ahead of semantic classification fails 5 tests, including
  `test_stale_6391_semantic_receipt_reproves_before_unknown_can_block`; restoring
  returns 417 passed. The discriminator is real in both directions.
- Owning suites green: merge_on_green, merge_on_green_semantic, ci_authority,
  ci_semantic_proof, ci_canary_tools, ci_canary_workflows, ship_loop_guard,
  ship_loop_hold_wrapper, ship_loop_semantic — **1018 passed, 0 failed**.
- `python3 scripts/agentos.py validate` — 0 errors.

**do_not_redo**
- Do not treat an unreadable changed-file inventory as staleness. A failed read
  may not author a write; that is the whole point of this repair.
- Do not relax the truncated/broad or complete-unclassified branches — both are
  observed ANSWERS and were passing before this change. They are the control.
- Do not add a retry loop, negative cache, dispatcher or proof store.
  `ProofFreshness` is per-sweep; the next ordinary sweep re-observes.
- Do not emit response bodies or headers in diagnostics. A body is
  attacker-influenced and can echo a token.
- Do not mutate PR #6391 (merged, immutable) or merge #6423 (DO-NOT-MERGE fixture).

**danger_areas**
- `pull_files()` has five callers. Three fail closed on `None`
  (`_touches_semantic_authority` → True, live-inherited-red → None,
  `semantic_main_circuit_decision` → no bypass). Verify any new caller does too:
  transport exceptions now return `None` instead of propagating.
- `note_merged_commit(..., pull_files(n))` records `None` as an EMPTY complete
  file list. That is pre-existing post-merge bookkeeping, deliberately NOT changed
  here (out of commissioned scope), but it is a latent under-read worth a separate
  look.
