---
workstream: WS:AGENT-OS
session: sol/linear-slack-operating-law
model: local
ended_because: complete
mission: >
  Make the Mastermind-X Linear and Slack integration architecture durable inside
  the repository so future Sol/Fable/worker sessions can recover it without
  relying on chat memory, while preserving Agent OS and Mastermind OS as the
  canonical orchestration/control system.
state_before: >
  Linear had been populated with the live Agent OS portfolio and Slack had been
  organized into shared control-plane channels, but the hierarchy existed mainly
  in Linear/Slack/session context rather than as durable repository law. That left
  a future-session risk of treating Linear as canonical or Slack delivery as
  equivalent to agent-runtime delivery.
changed:
  - path: agentos/decisions/DEC-LINEAR-IS-PORTFOLIO-PROJECTION-NOT-CANONICAL.md
    what: >
      Freezes Linear as a selective executive/product portfolio projection over
      Agent OS + GitHub, never a replacement canonical state store.
  - path: agentos/decisions/DEC-SLACK-IS-EVENT-TRANSPORT-NOT-RUNTIME-DELIVERY.md
    what: >
      Freezes Slack as communication/event transport and distinguishes message
      receipt from runtime visibility and explicit agent acknowledgement.
  - path: research/MASTERMIND_LINEAR_PORTFOLIO_PROJECTION_CONTRACT_2026-08-20.md
    what: >
      Defines the WS -> Linear Project -> MAS issue -> GitHub execution -> proof ->
      Agent OS transition projection chain, selective issue law and completion law.
  - path: research/MASTERMIND_SLACK_AGENT_EVENT_BRIDGE_CONTRACT_2026-08-20.md
    what: >
      Defines mastermind.dispatch.v1, seat resolution, transport lifecycle,
      durable pending inbox semantics, ACK/RESULT threading and failure states.
verified:
  - claim: >
      The branch is records-only and does not touch runtime, product, workflow,
      data, site, control_plane, or scheduler code.
    command: >
      Compare branch to main and inspect the changed-file list.
    result: >
      Only the two Agent OS decisions, two research contracts and this handoff are
      intended to differ.
  - claim: >
      The new law preserves existing Agent OS boundary I1 and the Chairman-ratified
      no-task-store ruling.
    command: >
      Read WS:AGENT-OS and DEC:AGENTOS-NO-TASK-STORE before authoring the contracts.
    result: >
      Dispatch authority remains in Mastermind/control-plane or hook layers; Linear
      remains advisory projection; Slack transport does not create a rival task store.
unverified:
  - claim: Exact-head Agent OS validation and hosted CI are green.
    what_would_verify: >
      Open the linked PR, let exact-head checks conclude, and inspect Agent OS
      validation/record-schema results before merge.
  - claim: The records are canonical on main.
    what_would_verify: The PR merges after review against current main.
unresolved:
  - "Linear initiative API remains unreliable; do not fake an executive initiative."
  - "MAS-27/MAS-28 implement the one-way projector/linkage guard; not built here."
  - "MAS-29/MAS-30/MAS-31 implement the durable Slack dispatch runtime bridge; not built here."
  - "Browser-hosted ChatGPT/Claude/Fable sessions cannot be assumed to wake from Slack alone."
next_actions:
  - "Open the records-only PR with explicit WS:AGENT-OS + MAS-43 linkage."
  - "Run exact-head review/validation; repair only records defects found."
  - "After merge, close MAS-43; leave MAS-27/28 and MAS-29/30/31 as separate bounded implementation waves."
  - "Then continue direct-record Linear reconciliation and operator/CEO gate extraction."
do_not_redo:
  - "Do not make Linear canonical for workstream, decision, discovery, handoff or proof truth."
  - "Do not make Slack messages canonical state or equate Slack delivery with runtime delivery."
  - "Do not create a second task/job registry inside agentos/."
  - "Do not hard-gate CI on Linear linkage before the report-only validator has measured false positives."
danger_areas:
  - "A Linear issue may show Done while Agent OS still requires production proof; merge != completion."
  - "Slack retries/edits can duplicate transport unless the eventual bridge is idempotent."
  - "A receiving Slack account is not itself an executing AI runtime."
---

# Return point

Read the two decisions and the two contracts first. The architecture is intentionally
one-way at the portfolio layer and transport-only at the Slack layer. Runtime implementation
begins only in the separately tracked MAS-27/28 and MAS-29/30/31 waves.
