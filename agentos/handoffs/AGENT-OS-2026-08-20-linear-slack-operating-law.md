---
workstream: WS:AGENT-OS
session: sol/linear-slack-operating-law
model: local
ended_because: complete
mission: >
  Make the Mastermind-X Linear and Slack integration architecture durable inside
  the repository so future Sol/Fable/worker sessions can recover it without
  relying on chat memory, while preserving Agent OS, Executive OS and existing
  execution planes as the only canonical owners of their state.
state_before: >
  Linear had been populated with the live Agent OS portfolio and Slack had been
  organized into shared channels, but the hierarchy existed mainly in
  Linear/Slack/session context rather than durable repository law. The first Slack
  draft also over-specified a new durable dispatch lifecycle and seat inbox before
  current Executive OS archaeology was reconciled.
changed:
  - path: agentos/decisions/DEC-LINEAR-IS-PORTFOLIO-PROJECTION-NOT-CANONICAL.md
    what: >
      Freezes Linear as a selective executive/product portfolio projection over
      Agent OS + GitHub, never a replacement canonical state store.
  - path: agentos/decisions/DEC-SLACK-IS-EVENT-TRANSPORT-NOT-RUNTIME-DELIVERY.md
    what: >
      Freezes Slack as transport/acknowledgement only and, after reconciliation
      with current Executive OS archaeology, explicitly forbids pre-authorizing a
      new Slack lifecycle database or durable seat-inbox store.
  - path: research/MASTERMIND_LINEAR_PORTFOLIO_PROJECTION_CONTRACT_2026-08-20.md
    what: >
      Defines the WS -> Linear Project -> MAS issue -> GitHub execution -> proof ->
      Agent OS transition projection chain, selective issue law and completion law.
  - path: research/MASTERMIND_SLACK_AGENT_EVENT_BRIDGE_CONTRACT_2026-08-20.md
    what: >
      Reconciles the long-term Slack transport vision with Mastermind PR #91 /
      MAS-48. The first vertical is Pro Sol -> #ceo-control-room -> existing
      Executive CEO-intent/Job/JOB_CREATED -> Slack ACK -> MCP readback. Generic
      #agent-dispatch is later and MAS-29/30/31 must be re-architected after MAS-48.
verified:
  - claim: >
      The branch is records-only and does not touch runtime, product, workflow,
      data, site, control_plane, scheduler, Executive database, or Slack app code.
    command: >
      Compare the PR head to main and inspect the changed-file list.
    result: >
      Only the two Agent OS decisions, two research contracts and this handoff are
      intended to differ.
  - claim: >
      The Linear law preserves Agent OS boundary I1 and the Chairman-ratified
      no-task-store ruling.
    command: >
      Read WS:AGENT-OS and DEC:AGENTOS-NO-TASK-STORE before authoring the contract.
    result: >
      Agent OS remains knowledge only; Linear remains a selective projection.
  - claim: >
      The Slack law no longer creates a duplicate Executive lifecycle or durable
      seat inbox.
    command: >
      Reconcile Macro PR #6071 against Mastermind PR #91 / Linear MAS-48 and the
      updated MAS-9/MAS-29 program rulings.
    result: >
      Executive SQLite remains sole Job/Attempt/Worker/Event lifecycle authority;
      CEO V1 reuses ceo_intent + Job/JOB_CREATED; MAS-29/30/31 are architecture-held
      for post-MAS-48 redesign; Wake remains HOLD/NOT_ACCEPTED/NOT_ARMED.
unverified:
  - claim: Exact-head Agent OS validation and hosted CI are green after the Executive OS amendment.
    what_would_verify: >
      Let PR #6071's new exact-head checks conclude and inspect the final checks
      before merge.
  - claim: The records are canonical on main.
    what_would_verify: PR #6071 merges after current-main review.
  - claim: Pro Sol can create a canonical CEO Job through Slack in production.
    what_would_verify: >
      MAS-48 PR-A/B/C and the real research_only Slack -> Job -> ACK -> MCP canary.
unresolved:
  - "Linear initiative API remains unreliable; do not fake an executive initiative."
  - "MAS-27/MAS-28 implement the one-way projector/linkage guard; not built here."
  - "MAS-48 is the first Slack writeback implementation and is separately reviewed in Mastermind."
  - "MAS-29/30/31 are not implementation-ready; consume MAS-48 proof and the then-current Wake adjudication first."
  - "Browser-hosted ChatGPT/Claude/Fable sessions cannot be assumed to wake from Slack alone."
next_actions:
  - "Run exact-head review/CI on amended PR #6071; merge only when green and current-main semantics do not conflict."
  - "After merge, close MAS-43; keep MAS-48 as the first Slack implementation vertical."
  - "Do not implement the superseded durable Slack event-store/seat-inbox design in MAS-29/30/31."
  - "Continue the one-way Linear projection/reconciliation program under MAS-6/27/28."
do_not_redo:
  - "Do not make Linear canonical for workstream, decision, discovery, handoff or proof truth."
  - "Do not make Slack messages canonical state or equate Slack delivery with runtime delivery."
  - "Do not create a Slack lifecycle DB, mutable dispatch store, or durable seat-inbox DB merely because the first draft named one."
  - "Do not create a second task/job registry inside agentos/."
  - "Do not use Wake as an accepted Slack foundation while its current ruling is HOLD/NOT_ACCEPTED/NOT_ARMED."
  - "Do not hard-gate CI on Linear linkage before the report-only validator has measured false positives."
danger_areas:
  - "A Linear issue may show Done while Agent OS still requires production proof; merge != completion."
  - "A Slack ACK can prove canonical admission without proving dispatch or execution; CEO V1 must say dispatched=false."
  - "A receiving Slack account is not itself an executing AI runtime."
  - "Generic WS provenance and runtime/session routing namespaces are distinct; never translate by string similarity."
---

# Return point

Read both decisions, both contracts, then Mastermind PR #91 / MAS-48 before changing Slack
runtime architecture. Linear is one-way projection. Slack is transport. Executive OS keeps its
canonical lifecycle. MAS-48 proves the first Pro-Sol writeback vertical. Generic agent dispatch
is a later re-architecture, not an already-frozen persistence system.
