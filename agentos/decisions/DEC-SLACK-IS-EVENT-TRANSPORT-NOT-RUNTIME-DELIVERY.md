---
key: SLACK-IS-EVENT-TRANSPORT-NOT-RUNTIME-DELIVERY
question: >
  Can Slack messages themselves serve as agent dispatch/runtime delivery for Sol,
  Fable and worker sessions, and should the Slack integration create its own durable
  lifecycle/seat-inbox state?
answer: >
  Slack is a human-visible transport and acknowledgement surface, not canonical state,
  not runtime delivery, and not a reason to create another lifecycle store. Reuse the
  canonical state of the system receiving the command. For the first CEO-intent vertical,
  Slack feeds the existing Mastermind Executive OS CEO-intent admission and sole
  Job/JOB_CREATED lifecycle; bounded Slack transport provenance and a thread ACK prove
  the round trip. Generic agent dispatch remains a later program and must be re-designed
  against the then-current Executive OS and Wake authority rather than pre-authorizing a
  new Slack queue, mutable dispatch store, or durable seat-inbox database.
rationale: >
  Browser-hosted ChatGPT/Claude/Fable sessions do not inherently listen to a Slack inbox,
  so a Slack post cannot prove runtime visibility or acknowledgement. More importantly,
  current Executive OS archaeology shows the durable Job/Attempt/Worker/Event plane,
  command-id idempotency, CEO-intent admission, and recomputed Executive Inbox already
  exist. A separate Slack event lifecycle database or mutable seat inbox would duplicate
  canonical state and violate Mastermind's one-system law. The correct first vertical is
  narrower: Personal-Pro Sol writes a bounded high-level request to #ceo-control-room;
  a least-privilege Slack transport validates transport facts and submits through the
  existing Executive control service; existing Executive SQLite records one canonical
  Job/JOB_CREATED; Slack returns an acknowledgement; read-only MCP proves the same state.
alternatives:
  - option: Persist every Slack dispatch in a new Slack lifecycle database and seat inbox
    why_not: >
      Rebuilds lifecycle, dedupe and pending-work state already owned by Executive OS.
      It also turns transport implementation convenience into a second control plane.
  - option: Treat direct Slack DMs or channel posts as agent runtime delivery
    why_not: >
      A Slack notification proves only transport receipt. It does not prove a browser
      ChatGPT/Claude/Fable runtime was active, read current Agent OS context, or accepted
      the authority boundary.
  - option: Make Slack threads canonical handoff/workstream state
    why_not: >
      Slack is noisy transport and lacks Agent OS's durable work-identity, decision,
      discovery, handoff and proof contracts.
  - option: Exclude Slack from the architecture entirely
    why_not: >
      Loses a useful approved write transport and shared human-visible acknowledgement
      surface, including the immediate Pro-Sol CEO-intent writeback path.
evidence:
  - "agentos/workstreams/WS-AGENT-OS.md — anything that gates or dispatches belongs in Mastermind control_plane/ or existing execution hooks"
  - "agentos/decisions/DEC-AGENTOS-NO-TASK-STORE.md — autonomous job/task authority belongs in Executive OS, not Agent OS"
  - "Mastermind PR #91 / MAS-48 — current Executive OS archaeology: Executive SQLite is sole Job/Attempt/Worker/Event authority; no Slack queue or durable seat-inbox DB"
  - "research/MASTERMIND_SLACK_AGENT_EVENT_BRIDGE_CONTRACT_2026-08-20.md — transport sequence and no-duplicate-state contract"
affects:
  - WS:AGENT-OS
  - project-active-build-control
  - research/MASTERMIND_SLACK_AGENT_EVENT_BRIDGE_CONTRACT_2026-08-20.md
  - MAS-9
  - MAS-48
confidence: high
reversibility: easy
decided_by: ceo-sol
decided_at: 2026-08-20
---

## Required truth distinction

These facts must never be collapsed:

`SLACK_POSTED -> TRANSPORT_ACCEPTED -> CANONICAL_SYSTEM_ACCEPTED -> RUNTIME_VISIBLE -> AGENT_ACKED -> RUNNING -> RESULT`

Not every integration needs to persist each label as its own state machine. The canonical
receiving system is authoritative. In the CEO-intent V1, Executive OS Job/Event state plus
bounded Slack transport provenance and the Slack ACK are sufficient; `dispatched=false`
remains explicit.

## First vertical: CEO intent

`MAS-48` is the first implementation proof:

`Pro Sol -> #ceo-control-room -> least-privilege Slack transport -> ExecutiveControlService -> existing ceo_intent.submit_intent -> one Job/JOB_CREATED -> Slack ACK -> MCP readback`.

No generic #agent-dispatch bus, Wake dependency, new SQLite table/database, mutable Slack
dispatch store, or durable seat-inbox store is authorized by this decision.

## Generic agent dispatch remains later

`MAS-29/30/31` must consume MAS-48 production proof and the then-current Wake ruling before
implementation. Prefer projections over new mutable state. If a future generic dispatch fact
cannot be represented by existing Executive Job/Event authority, a separate architecture
ruling must prove why before any new persistence is introduced.

## Browser-runtime law

A browser-hosted AI session is never claimed as awakened or runtime-visible because Slack
received a message. Pending-work presentation at session bootstrap must be derived from an
accepted canonical representation; this decision does not pre-authorize a new durable seat
inbox to solve that problem.
