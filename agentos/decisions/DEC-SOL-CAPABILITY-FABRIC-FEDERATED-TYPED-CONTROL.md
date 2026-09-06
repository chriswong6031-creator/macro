---
key: SOL-CAPABILITY-FABRIC-FEDERATED-TYPED-CONTROL
question: >
  How should Chat-native CEO Sol receive materially stronger company-wide
  visibility and control without creating unrestricted ambient root access or
  duplicating Mastermind's canonical lifecycle, authority, identity, memory,
  queue, retry and control systems?
answer: >
  Use One Experience, Federated Authority. The Mastermind Sol plugin supplies
  reviewed procedure and a coherent Chat-native experience, while small
  privilege-separated apps and safe native connectors expose closed,
  source-attributed capabilities owned by the existing canonical systems.
  Reads may be broad; consequential actions remain owner-specific, exact-target,
  prepared, current-source revalidated and effect-reconciled. Administration is
  isolated and normally disabled.
rationale: >
  Sol needs enough deterministic visibility and bounded action reach to stop
  wasting frontier reasoning on GitHub, runtime, session, CI and company-state
  reconstruction. Centralizing all effects in one super-MCP would nevertheless
  create a confused deputy and a second company control plane. Federating by
  canonical owner and privilege preserves one premium user experience while
  keeping authority, idempotency, corrections, reconciliation and blast radius
  where they already belong.
alternatives:
  - option: Give Sol one universal super-MCP with ambient administration
    why_not: >
      It collapses incompatible authority and blast radii, makes prompt
      injection a company-wide confused-deputy risk and recreates lifecycle,
      scheduling, identity and retry behavior outside their canonical owners.
  - option: Ship only a read-only executive cockpit
    why_not: >
      It improves visibility but leaves the Chairman manually carrying routine
      bounded actions, session transitions and commissions, so it does not
      satisfy the intended operating-efficiency outcome.
  - option: Expose many unrelated apps with no coherent Sol plugin experience
    why_not: >
      Sol and the Chairman would still need to remember app brands, reconstruct
      cross-owner state and manually translate workflows, losing the product
      value while retaining integration complexity.
  - option: Let the plugin own durable company memory and task state
    why_not: >
      Reviewed procedure is valuable, but plugin-owned memory or scheduling
      would fork Agent OS and Executive OS and make transcript-local state look
      authoritative.
evidence:
  - "Mastermind PR #283 and merge 98bc7a71dcd70947c7a18eb5af7493a2f62a2571"
  - "Mastermind docs/superpowers/specs/2026-08-30-sol-capability-fabric-design.md"
  - "Mastermind docs/superpowers/plans/2026-08-30-sol-capability-fabric-tool-catalog.md"
  - "Mastermind docs/superpowers/plans/2026-08-30-sol-capability-fabric-program.md"
  - "Mastermind docs/EXECUTIVE_WORKER_ROUTING_CHAIRMAN_ADDENDUM.md"
  - "Mastermind docs/AGENT_DIALOGUE_SESSION_CLOSE_LAW.md"
affects:
  - WS:SOL-CAPABILITY-FABRIC
  - WS:AGENT-OS
  - WS:EXECUTIVE-CAPACITY-FABRIC
  - WS:CHAIRMAN-CONTROL-ROOM
confidence: high
reversibility: costly
decided_by: ceo-sol
decided_at: 2026-08-30
---

# Operating law

The Chairman sees one named Mastermind operating experience. Internally,
authority remains federated:

| Concern | Canonical owner |
|---|---|
| CEO admission and Job / Attempt / Worker / Event lifecycle | Executive OS |
| organizational workstreams, decisions, discoveries and handoffs | Agent OS |
| source, branch, PR, review, CI, merge and implementation evidence | GitHub |
| logical and concrete Sol reasoning surfaces | SessionTargetRegistry / RuntimeBinding |
| attention obligation and acknowledgement | Wake |
| placement and provider/account/surface eligibility | Capacity Fabric / Model Router |
| active bounded dialogue and transport | Company Dialogue / Agent Relay / Slack |
| cross-owner read composition | Executive Steward / Chairman Control Room |
| workflow procedure | reviewed Mastermind Sol plugin |

Technical permission is not organizational authority. OAuth authenticates; it
does not elect an executive, select a worker, bind a Sol surface or authorize a
company effect.

# Privilege and effect boundary

```text
R0_OBSERVE
W1_ROUTINE
W2_CONSEQUENTIAL
A3_ADMIN
```

Consequential actions are exposed only by the app for their canonical owner.
They use exact targets, authenticated storeless prepared tokens, current-source
and authority revalidation, and the closed effect truth:

```text
NOT_APPLIED
APPLIED
EFFECT_UNKNOWN
```

`EFFECT_UNKNOWN` requires same-owner read reconciliation and forbids blind
retry or failover. Cross-system closure may remain `PARTIAL_CLOSEOUT`; no
cosmetic global DONE flag is created.

# Rejected design

A universal super-MCP, generic shell/SQL/HTTP/filesystem/browser actuator,
plugin-owned memory, MCP-owned scheduler, provider process spawner, second
RuntimeBinding registry or model-selected credential/account/host/branch writer
is rejected by design.
