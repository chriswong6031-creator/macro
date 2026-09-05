---
key: MARKET-ONTOLOGY-AUTONOMY-V1-DISPATCH-PRECEDENCE
question: >
  After the Market Ontology F00-F13 organizational commissions exist durably, may Sol
  or F00 post new generic DELIVERY_ONLY "Fable pickup" messages to #agent-dispatch
  when no known active receiving worker/session exists?
answer: >
  No. Current Autonomy V1 operational law in protected Mastermind
  `research/MASTERMIND_AUTONOMY_V1_OPERATIONAL_RECONCILIATION_2026-08-26.md` controls
  transport. The F00-F13 packets are durable organizational commissions and operation
  identities, not authorization to use Slack as a dispatch queue. A new transitional
  manual Slack handoff is allowed only to a known already-active explicitly
  commissioned receiving session that will read the exact bound carrier. Otherwise the
  commission remains unclaimed/unstarted until a lawful active receiver exists or the
  production-proven Executive OS admission/routing path can carry it. Existing
  #agent-dispatch posts are visibility/dialogue evidence only and must not be backfilled
  automatically into Executive OS.
rationale: >
  Chairman's desired operating model is high parallelism without Chairman/Sol prompt
  carriage. Posting work to an absent Fable account recreates a dead-letter task queue
  in Slack and falsely suggests dispatch. Autonomy V1 explicitly freezes that behavior,
  assigns canonical Job/Attempt/Worker/Event lifecycle to Executive OS, and reserves
  #agent-dispatch for dialogue with already-active sessions. This transport correction
  does not narrow the multi-COO product architecture: F00-F13 remain distinct durable
  lane identities and should execute in parallel as actual governed capacity becomes
  available.
alternatives:
  - option: Post all F01-F13 packets now so someone might pick them up later.
    why_not: >
      Rejected. That turns Slack into a queue/dead-letter inbox and has already produced
      duplicate/false dispatch state.
  - option: Collapse the work back into the one currently active F00/Sol session.
    why_not: >
      Rejected. Lack of current transport capacity must not collapse the durable
      multi-COO topology or turn Sol/F00 into the serial implementer.
  - option: Auto-create Executive Jobs from the existing Slack backlog.
    why_not: >
      Rejected by Autonomy V1. Existing posts require per-operation reconciliation;
      GitHub/Slack/Linear do not implicitly originate Jobs.
evidence:
  - "Mastermind@be68ec881460aa60d7d77cdb69f7c1cae81f6310 — research/MASTERMIND_AUTONOMY_V1_OPERATIONAL_RECONCILIATION_2026-08-26.md"
  - agentos/decisions/DEC-MARKET-ONTOLOGY-FABLE-MULTI-COO-CONCURRENCY-TOPOLOGY.md
  - agentos/handoffs/MARKET-ONTOLOGY-F00-F13-FABLE-COO-FANOUT-MANIFEST-2026-08-26.md
  - "Slack reconciliation on 2026-08-26/27 found duplicate DELIVERY_ONLY messages for the same parity/K2-C/K3-D operation keys; later duplicates were deleted and earliest carriers preserved."
affects:
  - "marketontology-complete-parity-fanout-20260826-sol-001"
  - "marketontology-f00-parity-control-20260826-fable-001"
  - "marketontology-f01-* through marketontology-f13-* lane operations"
  - "#agent-dispatch transport wording in existing parity handoffs"
confidence: high
reversibility: easy
decided_by: sol
under_chairman_intent: 2026-08-26
decided_at: 2026-08-27
---

# Binding transport rider

This decision supersedes only the **transport implications** of older parity packets.
Their scope, owner, architecture, operation key, acceptance law and multi-COO topology
remain controlling.

## Current state vocabulary

For every F00-F13 lane distinguish:

- `COMMISSIONED_DURABLY` — packet/operation identity exists in Agent OS/GitHub;
- `UNCLAIMED` — no receiving operator/runtime claim evidence;
- `ACTIVE_MANUAL_CARRIER` — a known already-active commissioned receiver explicitly
  ACKed the exact operation and current pickup/collision state;
- canonical Executive lifecycle states — only when Executive OS actually owns an
  admitted Job/Attempt/Worker/Event path.

`COMMISSIONED_DURABLY` is **not** `QUEUED`, `ACKED`, `EXECUTING` or even proof that a
worker has seen the packet.

## F00 operating behavior until Autonomy V1 closes

F00 may maintain coverage accounting, dependency/collision maps, owner archaeology,
current-public delta research, historical-corpus import and child-wave packets without
creating fake dispatch state. It should not emit new dead-letter Slack assignments.

When an actual Fable/frontier session is already active and can receive a bounded
manual transitional handoff, F00 may bind that session to exactly one durable lane or
child operation, record the ACK/pickup evidence, and let it continue through routine
work under the lane envelope.

When production Executive routing becomes available, use the accepted CEO/root Job →
COO/planner → worker-router path; do not convert the Slack backlog wholesale or invent
new operation identities for already-bound work.

## Repair to existing manifest/handoff prose

Any existing line that says, in substance, "after #6504 lands, post/deliver F01-F13 to
Fable" must be read as:

> after #6504 lands, make the durable commissions eligible for allocation; transport
> only to an already-active known receiver, otherwise wait for lawful Executive routing.

No new Slack post is required merely because a records PR merged.