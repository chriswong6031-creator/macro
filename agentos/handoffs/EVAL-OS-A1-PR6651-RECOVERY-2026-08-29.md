---
workstream: "WS:EVAL-OS-EVIDENCE-VIEW"
session: sol/eval-os-dark-worker-recovery-20260829
model: sol
ended_because: blocked
mission: >
  Recover the existing A1 implementation on its sole PR #6651 after the prior started runtime became
  continuity-unrecoverable: re-pin current truth, adopt the preserved exact remote candidate rather
  than rebuilding it, repair only the A1-introduced deploy-closure blocker if still present, obtain
  current exact-head CI and independent review, then return for Sol-controlled production proof.
state_before: >
  Prior A1 child is terminally stopped for RuntimeBinding generation loss. Repository effect is APPLIED
  and preserved at PR #6651 head b1651b800c2d97992464d4a4be8eafce05290e67. PR remains DRAFT/HOLD,
  unmerged and undeployed. A1 remains BUILT_NOT_PROVEN. Fresh recovery child is waiting for a concrete
  eligible Opus-capable Claude placement.
changed:
  - path: agentos/handoffs/EVAL-OS-A1-PR6651-RECOVERY-2026-08-29.md
    what: "Created the fresh bounded A1 recovery packet while preserving PR #6651 as the sole implementation carrier."
verified:
  - claim: "PR #6651 remains the preserved A1 implementation carrier at exact head b1651b800c2d97992464d4a4be8eafce05290e67."
    command: "GitHub get PR #6651 metadata and exact head before recovery freeze."
    result: "PASS — OPEN + DRAFT/HOLD, unmerged, exact head b1651b800c2d97992464d4a4be8eafce05290e67."
  - claim: "The old A1 child has an explicit terminal Sol STOP and its known repository effect is APPLIED rather than EFFECT_UNKNOWN."
    command: "Read Slack C0BSBM78V1N thread 1787971248.615479 through terminal Sol edge 1788024599.319629 and reconcile PR #6651."
    result: "PASS — child terminal; PR effect preserved."
  - claim: "Current recovery routing requires a fresh child and exact-thread watcher before START."
    command: "Read current protected Mastermind Skillpack WORKER_AVENUE_ROUTING.md, COMMISSION_WAVE.md and AGENT_DIALOGUE_SESSION_CLOSE_LAW.md."
    result: "PASS."
unverified:
  - claim: "Whether A1's introduced deploy-closure failure remains on a fresh current-base execution after foreign main repair settles."
    what_would_verify: "Fresh current-main merge-context reproduction on PR #6651 by the lawfully assigned recovery worker."
  - claim: "Final exact-head hosted CI, independent final review, merge/deploy state and authenticated production proof."
    what_would_verify: "Recovery worker return plus separate Sol-controlled merge/deploy and authenticated admin proof."
unresolved:
  - "Smallest correct repair for the A1-introduced deploy/runtime closure if it remains reproducible."
next_actions:
  - "Await lawful concrete Opus-capable Claude placement, then Sol sends a DIRECT_TARGETED assignment on one fresh Slack parent."
  - "Assigned worker must PICKUP_ACK with actual identity, reread current law/thread, actually arm an exact-thread watcher and emit WATCH_ARMED before separate START."
  - "Continue only PR #6651; return an immutable reviewed candidate to Sol without merge/deploy."
do_not_redo:
  - "Do not create a sibling A1 PR or rebuild the feature from scratch."
  - "Do not re-wake or rebind the old Codex runtime or any Codex CTO."
  - "Do not repair inherited Caddy/import-hygiene reds inside A1; #6662/foreign current-main ownership remains external."
  - "Do not merge, deploy or mark Ready without a separate Sol release after exact-head review."
danger_areas:
  - "Admin import fixes must not solve CI by creating a duplicate evaluator/store or weakening production dependency checks."
  - "Current-main organizational projection may lag the preserved candidate; reconcile rather than creating a second workstream authority."
---

# Eval OS A1 PR #6651 recovery

**Fresh operation:** `eval-os-a1-pr6651-recovery-20260829-sol-001`  
**Preferred avenue:** `Opus`  
**Receiver binding:** `CAPACITY_SELECTABLE`  
**Placement state:** `WAITING_CAPACITY / needs_placement`  
**Why not Fable:** architecture, authority and no-rebuild boundaries are already frozen; this is difficult but bounded exact-PR debugging/review work.  
**Codex:** prohibited for this recovery; do not re-wake any prior Codex runtime/CTO.

This is a fresh child under the existing Eval OS parent. The prior operation
`eval-os-a1-evidence-view-20260828-sol-001` is terminal for runtime-continuity loss. Its GitHub effect
is known and preserved. This child may take over the same canonical PR carrier only after a fresh
lawful receiver assignment; it is not continuation of the old runtime.

## Observable mission

Make PR #6651 a current-main-reconciled, exact-head-reviewed A1 candidate with every A1-introduced
hosted failure closed, while leaving inherited foreign-plane reds with their existing owner. Return
an immutable candidate and proof packet to Sol. The worker does not merge, deploy or declare A1 live.

## Frozen carrier and boundaries

- Sole implementation carrier: Macro PR #6651 / branch `claude/eval-os-a1-evidence-view-20260828`.
- Preserved pickup head at recovery freeze: `b1651b800c2d97992464d4a4be8eafce05290e67`.
- Existing candidate is a deterministic derived evidence view over T1/T4 and canonical owner evidence.
- No persisted score/evidence store, second registry, health store, promotion service, qledger copy,
  second admin product, queue or router may be introduced.
- `Validated` may be empty; null `output_class` stays null; illegal/mixed bases never pool; model
  output has zero evidence or promotion authority.
- The known A1-introduced hosted red was `biocatalyst-deploy-integration` via expanded admin load-time
  import closure. Reproduce it on the fresh current merge context before changing anything.
- Inherited Caddy and Linear-planner/import-hygiene reds are foreign current-main ownership and must
  not be repaired in this child. Do not absorb #6662 or any successor foreign repair.

## Required startup protocol

THIS DURABLE FILE IS SCOPE, NOT RECEIVER ASSIGNMENT. After Sol deliberately delivers the commission
to a concrete eligible Claude session, that delivery is the assignment edge.

1. Post `PICKUP_ACK eval-os-a1-pr6651-recovery-20260829-sol-001` on the new exact Slack parent using
   the actual receiver identity.
2. Reread the complete exact Slack thread, CURRENT protected Mastermind Skillpack, current Macro main,
   this file and PR #6651.
3. **Actually arm a watcher on that exact Slack thread and emit truthful `WATCH_ARMED` before START.**
   If the tool-first watcher setup cannot succeed, return `WATCH_UNAVAILABLE`; no watcher means no START.
4. Perform current-main/open-PR/path collision census and verify #6651 remains the one carrier.
5. Emit a separate `START eval-os-a1-pr6651-recovery-20260829-sol-001` only when the gates are clear.

## Execution and proof

Reproduce the A1-introduced deploy/import-closure failure on the current merge context. If still real,
add a discriminating RED regression and make the smallest GREEN repair. Prefer reducing an accidental
A1 import closure over widening deployment dependencies when that preserves product behavior; if an
existing deploy contract truly must expand, prove that before touching it. Do not refactor CI or
repair foreign failures.

Run the focused A1/admin tests, owning CI/contract tests, JS/diff checks, and complete hosted exact-head
matrix. Obtain independent exact-head review from a different worker/model where required. Preserve
DRAFT/HOLD. Return `RESULT / HOLD-FOR-SOL` with exact head, base/current-main relation, changed files,
A1-introduced versus inherited CI attribution, test receipts, independent review, remaining production
gate and watcher state.

## Program-level completion remains outside worker scope

A1 becomes `PROVEN_LIVE` only after separate Sol-controlled merge/deploy and authenticated
`admin.mastermind-x.com` API/UI proof covering empty/null/degraded/incomplete states, lawful
mixed-basis refusal, negative proof of no persisted score store, no new promotion authority, and
durable Agent OS/Linear reconciliation. Green CI alone is not completion.

Only explicit Sol STOP closes this fresh child. Every nonterminal return must leave the exact-thread
watcher armed/re-armed.
