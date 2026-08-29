---
key: CODEX-NATIVE-SESSION-IDENTITY-IS-UNDERBOUND
claim: >
  Transition-era Slack handoffs do not uniquely bind a native Codex reasoning session to one child
  operation. A Slack principal, `/root` working directory, provider/model label, GitHub identity, or
  unique worktree/branch is insufficient to prove receiver uniqueness. The current estate permits
  two native Codex conversations to present as the same receiver for one operation, while separate
  dispatch posts can also reopen or overlap already-active logical work. Existing RuntimeBinding
  identity plus Agent Dialogue/Executive admission are the correct owners; model obedience and
  prompt text alone cannot make the binding exclusive.
falsifier: >
  This discovery is falsified when the production path proves, under concurrent native Codex
  sessions behind one communication principal, that one active child operation resolves to exactly
  one current RuntimeBinding generation before START; a second session is deterministically refused
  before any repository/PR/host effect; every local result/blocker/tool failure is mechanically
  projected to the exact canonical Agent Dialogue carrier; terminal STOP invalidates stale-session
  writes; and the 2/5/14-session collision canary completes with zero duplicate effect and zero silent
  orphan. Slack display names, `/root`, GitHub authorship, separate worktrees, or voluntary model
  messages do not satisfy the falsifier.
so_what: >
  Autonomous operation cannot rely on Codex remembering to use Slack or on the Chairman/Grok
  Secretary noticing duplicate tabs. Permanent repair must extend existing Executive admission,
  RuntimeBinding/Operator Continuity, Agent Dialogue/Wake and owner-specific write guards. It must
  not create a second session registry, supervisor database, retry plane or Slack-owned lifecycle.
kind: runtime
verified_at: 2026-08-29
verified_by: >
  Live #agent-dispatch reconciliation on C0BSBM78V1N; protected Mastermind
  19fe09ddbe065d57292effc2544edcbf447bfcc0; current Macro main
  ab3f0350bac31c6d7bdad7b336b714841c3c3aa3; canonical RuntimeBinding and Agent Dialogue V2 source.
scope:
  - WS:CHAIRMAN-CONTROL-ROOM
  - WS:EXECUTIVE-CAPACITY-FABRIC
  - slack:#agent-dispatch
confidence: verified
---

## Evidence

### Same operation, same communication identity, duplicate native-session pickup

Canonical fourth-slot child `ci-pc-fourth-slot-20260829-sol-001` uses Slack parent
`1787976107.477789`. The same communication principal emitted two `PICKUP_ACK` messages for that
same operation roughly forty-one seconds apart:

- `1787979799.163609` identifies the receiver as a Codex desktop session at `/root`;
- `1787979840.510519` again accepts the Chairman handoff for the same operation while describing the
  receiver through the same transition-era surface identity.

Both are transport statements from one Slack principal. Neither supplies a canonical opaque native
RuntimeBinding identity/generation that can prove they came from one and only one reasoning
conversation. This is the concrete discriminator: **Slack principal + `/root` is not receiver
identity**.

### Duplicate dispatch can manufacture competing entry points

On 2026-08-29 the CI throughput lane emitted later `OPEN_PICKUP`/assignment entries for work that was
already bound, STARTED, or terminal on earlier carriers. The collided entries included:

- `ship-loop-ci-quiescence-r2-20260829-sol-001` overlapping live
  `ci-quiescence-v2-20260829-sol-001`;
- `ci-scope-l2-false-ownership-20260829-sol-001` overlapping live
  `ci-l2-false-ownership-20260829-sol-001`;
- `ci-pc-fourth-slot-c4-20260829-sol-001` overlapping live
  `ci-pc-fourth-slot-20260829-sol-001`;
- a repost of `ci-main-integrity-c0-20260829-sol-001` after that exact child had already received a
  terminal Sol STOP.

The later entries had no pickup/effect yet and were explicitly terminally closed during the incident.
The associated assignment board was marked superseded. The incident proves that worker-side
obedience cannot repair a dispatch author that exposes multiple plausible carriers for the same
logical capability.

### Write effects can occur without the expected dialogue handshake

The `macro-context-index-c0-recovery-20260828-sol-002` recovery carrier exposed a separate admission
defect: PR #6600 moved under commits attributed to `Oracle post-heal audit` while the canonical Slack
reconciliation found no matching receiver binding, ACK, watcher, START, or return for that actor.
Sol PARKed the carrier rather than reset/retry it. This evidence is provider-neutral: a repository
write path cannot infer authority merely because a session can write Git.

### Return projection remains behavioral instead of mechanical

Protected Mastermind already records the incident classes `WORKER_RETURN_NOT_PROJECTED` and
`DIALOGUE_CARRIER_SPLIT`. Live Codex children continue to show why: local work can finish or wait
while the company carrier receives no typed semantic return until the reasoning session voluntarily
posts one. Claude's higher empirical conformance does not make the protocol safe; it only masks the
missing enforcement more often.

A related classifier mismatch is visible in current practice: Codex may post `PROGRESS` while saying
it is awaiting explicit Sol direction, but the accepted turn classifier treats contributor
`PROGRESS` as `NO_ACTION`. Any return that requires Sol must therefore use a typed actionable edge
such as `BLOCKED`, `DECISION_REQUEST`, or `RESULT`; do not encode `requires_response` only in prose.

## Root cause

This is not one root cause called "Codex disobedience." Three boundaries are under-enforced:

1. **receiver identity** — the manual Slack handshake does not require/verify the exact native
   RuntimeBinding generation;
2. **effect admission** — provider/worktree access can reach Git/PR/host mutation without a
   mechanically checked current operation/binding/effect grant at every first effect boundary;
3. **semantic projection** — the company dialogue still depends on a reasoning model voluntarily
   emitting the required typed return instead of the existing harness/Agent Dialogue path projecting
   accepted local outcomes mechanically.

`AGENTS.md` unique-worktree/branch law prevents filesystem collisions but cannot solve these three
identity/admission/communication boundaries.

## Permanent acceptance law

Extend existing owners only. The production repair is not complete until it proves all of:

- before START, one child operation/carrier resolves to exactly one current RuntimeBinding;
- after START, `binding_id + binding_generation` is sticky until canonical reconciliation;
- a second native session claiming the same active child is read-only/refused before effect and its
  refusal is projected to Sol;
- first repository/PR/host mutation is admitted only with current operation/carrier + binding
  generation + exact effect scope; missing/stale/terminal admission refuses before effect;
- any session/tool/provider failure emits one bounded same-carrier diagnostic with attempted action,
  exact branch/head/worktree where relevant, and effect status `NONE`, `APPLIED`, or `EFFECT_UNKNOWN`;
- local accepted result/blocker/decision-request becomes a typed Agent Dialogue return without
  depending on the Codex model to remember Slack;
- terminal Sol STOP invalidates stale-tab/watcher writes and binding generations prevent ABA-style
  resume after restart;
- distinct child operations may run concurrently through distinct bindings even when they share the
  same Slack communication principal;
- duplicate same-child native sessions cannot create a second branch/effect;
- stress tests cover 2/5/14 concurrent native Codex sessions plus kill/restart/network/tool-failure
  paths, with zero silent orphan and zero duplicate effect.

## No-rebuild boundary

Do not create a Codex session registry, Slack lifecycle table, supervisor DB, watcher DB, duplicate
retry service, or provider-derived authority plane. Reuse:

- Executive OS for Job/Attempt/Worker/Event and modification admission;
- existing RuntimeBinding/Operator Continuity for exact runtime/session identity;
- Agent Dialogue V2 for the canonical semantic carrier;
- Wake for attention/resumption;
- existing repository/ship/self-mod/host guards for effect enforcement;
- OCR-6 Executive Steward/Control Room for read-only attention/exception composition.
