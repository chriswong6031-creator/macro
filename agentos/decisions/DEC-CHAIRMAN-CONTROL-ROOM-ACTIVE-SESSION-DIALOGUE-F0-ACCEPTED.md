---
key: CHAIRMAN-CONTROL-ROOM-ACTIVE-SESSION-DIALOGUE-F0-ACCEPTED
question: >
  Should the zero-Chairman-copy Sol↔Fable active-session communication capability
  become a separate Agent OS workstream/control plane, or remain a bounded dialogue
  wave under the existing Chairman Control Room organizational identity?
answer: >
  Keep one canonical workstream: WS:CHAIRMAN-CONTROL-ROOM. Accept merged Mastermind
  Active-Session Dialogue F0 as the source law for a bounded active-session dialogue
  wave under that workstream. Slack remains transport only; Executive OS remains
  runtime/lifecycle authority; Agent OS remains durable organizational memory; GitHub
  remains implementation/evidence truth. F0 does not authorize implementation by itself.
rationale: >
  The Chairman's underlying job is one coordination burden: stop manually carrying
  context between Sol, Fable and worker surfaces. The Control Room addresses discovery
  and navigation; Active-Session Dialogue addresses substantive back-and-forth after
  the exact Sol/Fable sessions are already active and commissioned. Splitting this into
  a second Agent OS workstream would create duplicate organizational identity for one
  user journey. The merged ASD F0 architecture already preserves the critical boundary
  between active-session dialogue and generic dispatch/wake and prohibits another
  dialogue DB, inbox, cursor, queue or lifecycle store.
alternatives:
  - option: Create a new WS:ACTIVE-AGENT-COMMS workstream
    why_not: >
      Duplicates the same Chairman coordination outcome and would force future sessions
      to reconcile which workstream owns the Sol/Fable return path.
  - option: Treat Slack messages as the durable state machine
    why_not: >
      Slack is transport/hot-state visibility only. Delivery, ACK, RESULT or message
      history cannot author Executive lifecycle or Agent OS organizational truth.
  - option: Merge F0 and immediately start Agent Relay/A0/A1
    why_not: >
      The accepted source law explicitly separates architecture acceptance from a
      later fresh implementation release and requires current collision/authority review.
evidence:
  - "Mastermind PR #115 merged as e1101eb2c1f17d801d480ded497b3fc1bb0ef18b"
  - "Mastermind research/MASTERMIND_ACTIVE_SESSION_EXECUTIVE_DIALOGUE_F0_ARCHITECTURE_AND_FABLE01_COMMISSION_2026-08-22.md"
  - "Mastermind research/MASTERMIND_ACTIVE_SESSION_EXECUTIVE_DIALOGUE_F0_CURRENT_STATE_AMENDMENT_2026-08-22.md"
  - "Macro PR #6230 merged as aecc82a67f245ce43496c1daf0bf2c722fdab161"
  - "agentos/decisions/DEC-SLACK-IS-EVENT-TRANSPORT-NOT-RUNTIME-DELIVERY.md"
affects:
  - WS:CHAIRMAN-CONTROL-ROOM
  - project-active-build-control
  - mastermind/research/MASTERMIND_ACTIVE_SESSION_EXECUTIVE_DIALOGUE_F0_*.md
  - macro/agentos/**
confidence: high
reversibility: costly
decided_by: ceo-sol
decided_at: 2026-08-22
---

## Capability boundary

This decision makes the organizational ownership and implementation gate recoverable. It does
not build Agent Relay, provision or mutate Slack credentials, send a dialogue frame, wake or
resume a session, create an Executive Job, or change the persistent Chairman Control Room.

## Accepted split

```text
Control Room navigation:
  find / bind / open already-known surfaces

Active-Session Dialogue:
  already active + already commissioned + exact Slack thread + bounded dialogue

Generic Wake / Dispatch:
  discover/assign/wake/resume execution sessions
```

The first two share one Chairman Control Room workstream because they are contiguous parts of the
same Chairman coordination journey. Generic Wake/Dispatch remains a separate later runtime
capability and cannot inherit authority from this decision.
