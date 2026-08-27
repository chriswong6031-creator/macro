---
key: AUTONOMY-V1-DISPATCH-DIALOGUE-RUNTIME-SEPARATION
question: >
  How should Sol CEO seats, Executive OS worker routing, Slack #agent-dispatch, active COO/worker
  dialogue, GitHub evidence and Agent OS state interact while Autonomy V1 is being closed, and
  what happens to the existing DELIVERY_ONLY Slack backlog?
answer: >
  Executive OS remains the sole Job/Attempt/Worker/Event lifecycle and worker-routing authority.
  ChatGPT1/2/3 Slack identities remain peer Sol CEO communication identities even when the same
  paid subscriptions also supply isolated codex-pro-01/02/03 worker capacity. #agent-dispatch is
  not a task queue: new absent-recipient DELIVERY_ONLY worker/Fable commissions are frozen.
  Worker/COO dialogue uses the bounded ASD Agent Relay only after a session is already active and
  commissioned. Historical DELIVERY_ONLY posts are reconciled individually against Executive,
  GitHub and Agent OS truth before any later canonical re-issue; they are never bulk-backfilled.
rationale: >
  Live Slack census on 2026-08-26 shows #agent-dispatch contains only Chairman plus ChatGPT1/2/3,
  while production Agent Relay is still not built and Personal-Pro Executive ingress/routing is
  not production-proven. Continued Fable/worker pickup posts therefore create dispatch-shaped
  dead letters rather than execution. Treating Slack, GitHub or Linear as a second task source
  would violate the one-canonical-system law and create duplicate/ambiguous work. The accepted ASD
  architecture already separates active-session dialogue from generic dispatch/wake; the accepted
  Executive routing architecture already places routing below Executive OS.
alternatives:
  - option: Keep using #agent-dispatch as a manual worker queue
    why_not: >
      There is no receiving Fable/worker/Relay principal today, delivery does not create a Job,
      and historical messages cannot safely establish lifecycle or execution state.
  - option: Make GitHub PR creation automatically originate Executive Jobs
    why_not: >
      GitHub owns implementation/evidence truth, not scheduling. This would create a second
      admission path and make implementation side effects originate work implicitly.
  - option: Address @ChatGPT1/2/3 as workers because their Codex allocations supply capacity
    why_not: >
      Slack identity and Executive Worker/realm identity are distinct. Executive OS must claim
      the concrete worker realm; otherwise CEO communication identity is conflated with execution.
  - option: Trigger Sol on every progress/completion event
    why_not: >
      Routine progress belongs to Executive/COO state. Sol attention is reserved for material
      blockers, architecture/authority/scope/rights/security decisions, named milestone review and
      final/root acceptance.
evidence:
  - "Mastermind PR #168 — operational reconciliation/source-law carrier"
  - "Mastermind research/MASTERMIND_AUTONOMY_V1_OPERATIONAL_RECONCILIATION_2026-08-26.md"
  - "Mastermind research/MASTERMIND_ACTIVE_SESSION_EXECUTIVE_DIALOGUE_F0_ARCHITECTURE_AND_FABLE01_COMMISSION_2026-08-22.md"
  - "Mastermind docs/EXECUTIVE_WORKER_ROUTING.md"
  - "Mastermind PR #150 / e9cb5cbd745b36dc51f54bd83238ec38ef0c80c7 — CF2-F accepted"
  - "Mastermind research/MASTERMIND_EXECUTIVE_CAPACITY_CF2_P0_HOST_CENSUS_2026-08-25.md — NO_SAFE_CF1_ACQUISITION_PATH"
  - "Slack #agent-dispatch C0BSBM78V1N current membership: Chairman + ChatGPT1/2/3 only"
affects:
  - WS:CHAIRMAN-CONTROL-ROOM
  - WS:EXECUTIVE-CAPACITY-FABRIC
  - Personal-Pro Executive Shell / MAS-48 family
  - Autonomy V1 integration closure
confidence: high
reversibility: costly
decided_by: ceo-sol
decided_at: 2026-08-26
---

## Operating law

1. **CEO ingress** — once C1/B2/C2 is production-proven, Sol submits bounded CEO requests through
   the dedicated Personal-Pro Executive ingress. Executive OS creates the canonical root Job.
2. **Worker routing** — Executive OS and its accepted router/capacity fabric select/claim concrete
   Worker/realm identities. Slack usernames are never worker-selection keys.
3. **Implementation evidence** — GitHub owns code/PR/CI/review proof. GitHub activity does not
   originate new work by itself.
4. **Organizational memory** — Agent OS records accepted workstream/decision/discovery/handoff truth.
5. **Dialogue** — `#agent-dispatch` carries only already-active, already-commissioned ASD dialogue
   once the Agent Relay is live; Slack delivery never proves runtime claim or completion.
6. **Attention** — routine starts/progress/child completions stay with Executive/COO. Sol attention
   is raised only for material `BLOCKED`, `DECISION_REQUEST`, milestone `RESULT`, final/root result,
   or another declared executive gate.
7. **Backlog** — historical DELIVERY_ONLY messages are reconciled one by one; no bulk conversion or
   operation-key reuse after ambiguous effects.

## Current closure topology

Autonomy V1 closes through four parallel lanes, then one integration canary:

- Lane A: C1 production SOL_STATE -> B2 -> C2.
- Lane B: current merged CF2-H0 + compatibility repairs -> exact installed-host proof -> independent
  P0 rerun -> only then CF2-I/routing and multi-realm fan-out. CF2-F is accepted and must not be
  redesigned.
- Lane C: ASD-A2 production Agent Relay -> A3 real COO/worker decision request -> Sol ruling -> same
  session continuation/result.
- Lane D: existing Worker Browser B1 carrier -> real governed browser/resource proof.
- Integration: one real Chairman outcome -> Sol ingress -> Executive root -> >=2 governed children ->
  one material ASD decision -> independent review -> terminal result -> GitHub/Agent OS closeout ->
  Control Room attention/evidence projection.

No lane may create another lifecycle, queue, worker identity, provider broker, dialogue inbox or
Slack-owned task system to accelerate closure.
