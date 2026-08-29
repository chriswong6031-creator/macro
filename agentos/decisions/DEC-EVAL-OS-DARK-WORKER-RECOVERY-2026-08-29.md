---
key: EVAL-OS-DARK-WORKER-RECOVERY-2026-08-29
question: >
  How should Intelligence Evaluation OS recover after the E1 and A1 execution embodiments became
  unusable while their canonical GitHub and production effects remained independently reconcilable?
answer: >
  Terminalize only the stale child dialogues, preserve every reconciled effect, and create fresh
  bounded E1 and A1 recovery children under current placement and watcher law.
rationale: >
  The old E1 worker stopped returning despite valid Sol CONTINUE edges, while A1's historical
  started runtime lacks a recoverable canonical ABA-safe RuntimeBinding generation. Neither child
  has an EFFECT_UNKNOWN repository state. Preserving #6598/#6607, the real stock clock, and PR #6651
  while minting fresh child identities avoids blind failover, duplicate implementation carriers,
  and indefinite execution limbo.
alternatives:
  - option: Keep both old children nonterminal indefinitely and wait for their original runtimes.
    why_not: >
      E1 has no returning worker and A1 cannot satisfy the current ABA-safe RuntimeBinding gate;
      indefinite HOLD leaves recoverable program work dark without increasing correctness.
  - option: Rebind or re-wake the old A1 runtime, or reuse the old E1 worker identity.
    why_not: >
      Started runtime binding is sticky until canonical reconciliation and terminal old children do
      not authorize a successor. A1 generation is unproven and E1's old dialogue is nonresponsive;
      fresh children are the lawful operation boundary.
evidence:
  - "Slack C0BSBM78V1N thread 1787896831.113919: terminal SOL CLOSED / STOP at 1788024583.456369."
  - "Slack C0BSBM78V1N thread 1787971248.615479: terminal SOL CLOSED / STOP at 1788024599.319629."
  - "Macro data/qledger/evidence_clock_start/stock_desk.json on recovery base: first_prospective_registration_utc=2026-08-29T11:08:11.609328+00:00."
  - "Macro PR #6651: OPEN+DRAFT/HOLD at exact head b1651b800c2d97992464d4a4be8eafce05290e67; unmerged and undeployed."
  - "Mastermind control_plane/session_targets.py: RuntimeBinding persistence remains deferred; the accepted continuity program has not production-proven recovery of this historical A1 binding generation."
affects:
  - "WS:EVAL-OS-MEASUREMENT-LAW"
  - "WS:EVAL-OS-EVIDENCE-VIEW"
  - "agentos/handoffs/EVAL-OS-E1-THEMATIC-COHORT-RECOVERY-2026-08-29.md"
  - "agentos/handoffs/EVAL-OS-A1-PR6651-RECOVERY-2026-08-29.md"
confidence: high
reversibility: easy
decided_by: ceo-sol
decided_at: 2026-08-29
---

# Ruling

The parent Intelligence Evaluation OS program remains active. Two old child execution embodiments
became continuity liabilities and are terminalized without discarding their durable GitHub or
production evidence.

## E1 old child

Old operation: `eval-os-e1-clock-accrual-20260827`.

The worker last returned a nonterminal HOLD and then stopped responding despite repeated valid Sol
CONTINUE edges. All known GitHub and production effects are reconciled. The child received terminal
`SOL CLOSED / STOP` on Slack `C0BSBM78V1N/1787896831.113919` at `1788024583.456369`.

Banked truth:

- #6598 and #6607 are merged and retained.
- `stock_desk` general evidence clock is `PROVEN_LIVE`, first prospective registration
  `2026-08-29T11:08:11.609328+00:00`, 20 trading days.
- stock matched-control remains truthfully NOT STARTED until a real governed controlled claim exists.
- `thematic_desk` still has no durable general evidence clock.
- qledger grading is live after the stock clock, but the explicit production cohort/exclusion receipt
  required by E1 remains outstanding.

The old child is terminal for worker-continuity loss, not accepted completion.

## A1 old child

Old operation: `eval-os-a1-evidence-view-20260828-sol-001`.

Its known repository effect is reconciled and APPLIED at Macro PR #6651 exact head
`b1651b800c2d97992464d4a4be8eafce05290e67`; the PR remains OPEN+DRAFT/HOLD, unmerged and
undeployed. The native Codex thread lineage was evidenced, but the canonical ABA-safe
`RuntimeBinding.binding_generation` could not be recovered. Current protected
`control_plane/session_targets.py` still states RuntimeBinding persistence is deferred, while the
protected Operator Continuity program leaves continuation binding as an unproven owner for this
historical execution. The write-capable interrupted-runtime law therefore cannot lawfully continue
this historical child on a different runtime merely because the provider thread remains visible.

The child received terminal `SOL CLOSED / STOP` on Slack
`C0BSBM78V1N/1787971248.615479` at `1788024599.319629`. PR #6651 is preserved as the single A1
implementation carrier and candidate evidence. The old runtime must not be re-woken or rebound.

## Successor law

Terminalizing the children does not terminate Eval OS and does not authorize blind failover. Each
remaining mission receives a fresh child identity, fresh current-state reconciliation, lawful
placement, explicit pickup, separate START, and a fresh reciprocal watcher cycle.

### E1 recovery child

`eval-os-e1-thematic-cohort-recovery-20260829-sol-001`

- `PREFERRED_AVENUE: Opus`
- `WHY`: difficult but bounded production-path, model fail-soft, scorability, and qledger proof under
  a frozen architecture.
- `WHY NOT FABLE`: no unresolved cross-repository or principal-level architecture decision remains;
  the mission is specific and evidence-driven.
- `RECEIVER_BINDING_MODE: CAPACITY_SELECTABLE`
- `PLACEMENT_STATE: WAITING_CAPACITY / needs_placement` until a concrete eligible Claude session is
  nominated and Sol directly targets it.
- Do not use Codex for this recovery.

### A1 recovery child

`eval-os-a1-pr6651-recovery-20260829-sol-001`

- `PREFERRED_AVENUE: Opus`
- `WHY`: bounded difficult exact-PR recovery, deploy-closure debugging, current-base CI adjudication,
  independent review, and production-proof preparation.
- `WHY NOT FABLE`: the architecture and no-rebuild boundary are frozen; no sustained principal
  integration or adjudication is required.
- `RECEIVER_BINDING_MODE: CAPACITY_SELECTABLE`
- `PLACEMENT_STATE: WAITING_CAPACITY / needs_placement` until a concrete eligible Claude session is
  nominated and Sol directly targets it.
- Existing PR #6651 is the sole implementation carrier. No sibling PR or branch may be created merely
  because the old runtime died.
- Do not use Codex or re-wake a prior Codex CTO/runtime.

## Placement and watcher discipline

Grok Secretary may coordinate availability and nominate an eligible Opus-capable Claude session; that
nomination is transport/capacity coordination, not lifecycle truth. Sol performs the actual
`DIRECT_TARGETED` handoff once a concrete receiver is resolved. The worker must then, in the exact
Slack carrier:

1. `PICKUP_ACK` with its actual identity;
2. reread the full thread and current protected Skillpack and current GitHub truth;
3. **actually arm a watcher on that exact Slack thread and emit truthful `WATCH_ARMED` evidence before
   START**;
4. emit a separate START only after current collision and authority gates are clear;
5. keep the watcher and re-arm discipline through every nonterminal return until explicit Sol STOP.

No unbound `OPEN_PICKUP`, no Chairman numbered-account babysitting, no duplicate watcher/control plane,
and no new director role.

## Unrelated terminal and parked boundaries

This ruling touches only Eval OS recovery. It does not resume or wake Web-Sol canary MAS-198, TFG-1,
GS-OP1/2, or any other PARKED/HARD-STOP child, and it does not re-wake the Codex CTO sessions.
