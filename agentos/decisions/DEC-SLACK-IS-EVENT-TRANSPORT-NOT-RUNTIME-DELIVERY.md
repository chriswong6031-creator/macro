---
key: SLACK-IS-EVENT-TRANSPORT-NOT-RUNTIME-DELIVERY
question: >
  Can Slack messages themselves serve as agent dispatch/runtime delivery for Sol,
  Fable and worker sessions, or must Mastermind distinguish transport from actual
  runtime delivery and acknowledgement?
answer: >
  Slack is a human-visible event transport, not runtime delivery and not canonical
  state. A Mastermind dispatcher must durably ingest/validate/route the event, and
  the target runtime must produce an explicit delivery receipt and ACK before the
  system may say the agent received or accepted the mission.
rationale: >
  Browser-hosted ChatGPT/Claude/Fable sessions do not inherently listen to an employee
  Slack inbox while running or stopped. Treating a posted message as delivered-to-model
  creates the worst possible false-green: the sender believes work was dispatched while
  no runtime ever saw it. Agent OS invariant I1 already places execution/dispatch authority
  outside the knowledge plane, and DEC:AGENTOS-NO-TASK-STORE places future autonomous job
  assignment in the Executive OS dispatcher. The bridge therefore needs its own durable
  transport lifecycle (received, queued, runtime-visible, ACKed, result) while Agent OS
  remains the canonical work/decision/handoff source it consumes.
alternatives:
  - option: Use direct Slack DMs between employee accounts as the agent inbox
    why_not: >
      A Slack user notification proves only that Slack accepted a message. It does not prove a
      ChatGPT/Claude/Fable session was active, read the message, received current Agent OS context,
      or accepted the authority boundary.
  - option: Make Slack threads the canonical handoff/workstream state
    why_not: >
      Chat transcripts are mutable/noisy transport, lack Agent OS schema/provenance gates, and
      recreate the cross-account state-loss problem the file-backed handoff protocol solved.
  - option: Do not use Slack in the agent architecture
    why_not: >
      Loses a useful shared human-visible coordination/event surface across durable employee seats
      and makes dispatch/escalation harder to observe while the runtime control plane is completed.
evidence:
  - "agentos/workstreams/WS-AGENT-OS.md landmine — anything that gates or dispatches belongs in Mastermind control_plane/ or the Macro hook layer"
  - "agentos/decisions/DEC-AGENTOS-NO-TASK-STORE.md — future task/job store belongs in the Executive OS dispatcher"
  - "research/MASTERMIND_AGENT_HANDOFF_PROTOCOL.md — durable state is a cold-stranger artifact, not chat history"
  - "research/MASTERMIND_SLACK_AGENT_EVENT_BRIDGE_CONTRACT_2026-08-20.md — immutable event/lifecycle/runtime-delivery contract"
affects:
  - WS:AGENT-OS
  - project-active-build-control
  - research/MASTERMIND_SLACK_AGENT_EVENT_BRIDGE_CONTRACT_2026-08-20.md
confidence: high
reversibility: easy
decided_by: ceo-sol
decided_at: 2026-08-20
---

## Required transport distinction

The bridge state machine is separate from the workstream state machine:

`RECEIVED → VALIDATED → ROUTED → QUEUED → RUNTIME_VISIBLE → ACKED → RUNNING → RESULT`.

A Slack post may establish `RECEIVED`; it can never establish `RUNTIME_VISIBLE` or `ACKED`
without a runtime/bootstrap adapter receipt.

## Current runtime law

For a runtime with no approved launch/resume adapter, the dispatch remains in a durable seat
inbox and is surfaced by the next eligible session bootstrap before unrelated new work. That
is honest delayed delivery, not fake asynchronous autonomy.
