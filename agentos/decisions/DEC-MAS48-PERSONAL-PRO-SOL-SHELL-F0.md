---
key: MAS48-PERSONAL-PRO-SOL-SHELL-F0
question: >
  After the Personal-Pro native architecture research and Mastermind F0 merge, what
  now governs Sol's primary CEO shell/read path, and which earlier MAS-48 assumptions
  are superseded without changing the accepted PR-A dedicated-ingress law?
answer: >
  Mastermind PR #99, merged as b02630fc1f3587672390b383998b28cb3206202f,
  is the accepted F0 architecture amendment for the Personal-Pro Sol Executive Shell.
  Personal Pro remains the protected primary Sol cognition plan. A Shared Mastermind
  Project is the persistent shell/context boundary, detailed procedure lives in a
  protected versioned Sol Skillpack on Mastermind master, and the final Personal-Pro
  runtime/read path is designed around a private SOL_STATE projection plus the approved
  Slack carrier into the existing dedicated Executive CeoIngress. Existing Executive
  MCP remains useful optional audit/readback infrastructure but is no longer a required
  Personal-Pro dependency. The downstream sequence is now PR-A plus independent S0 and
  SHELL-1, then after Sol accepts PR-A: R0 state-read law -> B1 Executive hot-state /
  SOL_STATE publisher -> C1 production read proof -> B2 inbound Socket Mode write
  transport -> C2 production write canary. PR-A itself remains exactly the two-schema
  hermetic capability frozen by Mastermind #96 and is not widened by F0.
rationale: >
  The Chairman's actual product requirement is to preserve the highest-value Personal-Pro
  Sol cognition/research seat while still giving it reliable company context and one safe
  modifying path into canonical Executive OS. Those jobs do not require ChatGPT Business,
  a private Plugin, or mandatory custom-MCP write/read access. Separating the Shared
  Project shell, protected Git procedure, transport-neutral Executive hot state, Slack
  carrier and canonical Executive lifecycle gives the Personal-Pro seat a coherent cold
  start and writeback workflow without creating another control/memory/lifecycle plane.
  Shipping the read lane before inbound writes also creates an independently useful,
  lower-risk capability and gives the real three-seat transport semantics a dedicated S0
  kill gate instead of assuming them from documentation.
alternatives:
  - option: Keep read-only Executive MCP as a mandatory Personal-Pro preflight and readback dependency
    why_not: >
      It couples the final user journey to a ChatGPT surface/entitlement that the product
      does not need. Existing MCP remains available as an independent audit surface, but
      SOL_STATE plus canonical Slack receipts become the Pro-native primary path once the
      read-side waves are accepted.
  - option: Put detailed Sol procedure and live state inside Shared Project instructions/history
    why_not: >
      Project memory is a shared information/context surface that can be stale, edited or
      adversarial; it is not durable company authority. The Project receives only a minimal
      Bootstrap Kernel while procedure is versioned in protected Mastermind Git and live
      organizational/runtime truth is re-read from its canonical owner.
  - option: Put the Sol Skillpack on Macro main beside Agent OS
    why_not: >
      Macro is the correct organizational-memory/semantic owner but its operational main
      branch is high-churn and receives automated publication/data commits. Instruction-
      bearing CEO procedure belongs on protected Mastermind master with the Executive
      governance surface; Agent OS remains in Macro.
  - option: Let the Slack Relay read the broad Operator socket or create a new state service/database
    why_not: >
      The broad Operator surface violates least privilege, while a fourth listener/service
      or state database duplicates lifecycle/composition for no new authority. R0 instead
      reviews a diagnostic read frame on the same dedicated CeoIngress after PR-A.
  - option: Keep the old monolithic PR-B -> PR-C sequence
    why_not: >
      It combines outbound hot-state publication, real Personal-Pro carrier uncertainty,
      inbound modifying transport and production write arming into overly broad waves.
      F0 separates S0/R0/B1/C1/B2/C2 so each slice proves one independently useful capability.
evidence:
  - "Mastermind PR #91 merged e61e48904302d0aae53baeab0e2681ee3fbec97d — accepted dedicated CeoIngress parent architecture"
  - "Mastermind PR #96 merged 5f9016f2db45acf60d4344656d85dfc496b87252 — exact PR-A implementation law; R2/R1 precedence retained"
  - "Mastermind PR #99 merged b02630fc1f3587672390b383998b28cb3206202f — three-record Personal-Pro Sol Executive Shell / Relay F0 freeze"
  - "Mastermind #99 exact-head CI run 264 — checkout, compile, shell validation and repository test gate PASS"
  - "Linear MAS-106/107/108/109/110 created for S0/R0/B1/C1/SHELL-1; MAS-102 reserved as B2 and MAS-101 reserved as C2"
  - "Linear MAS-103 corrected to #build-events-only native Linear->Slack visibility; protected Executive channels receive zero automatic Linear traffic"
  - "Mastermind PR #100 exists as the PR-A implementation and remains HOLD-FOR-SOL; F0 does not absorb or widen it"
affects:
  - WS:AGENT-OS
  - MAS-9
  - MAS-48
  - MAS-75
  - MAS-101
  - MAS-102
  - MAS-106
  - MAS-107
  - MAS-108
  - MAS-109
  - MAS-110
  - agentos/decisions/DEC-MAS48-CEO-INGRESS-V1-ACCEPTED-ARCHITECTURE.md
  - agentos/decisions/DEC-SLACK-IS-EVENT-TRANSPORT-NOT-RUNTIME-DELIVERY.md
confidence: high
reversibility: costly
decided_by: ceo-sol
decided_at: 2026-08-20
---

## Supersession boundary

This decision does **not** replace the dedicated-ingress architecture from Mastermind #91
or the PR-A mechanics from Mastermind #96. It supersedes only these earlier MAS-48
product/sequencing assumptions where they conflict:

1. Personal-Pro Sol must use Executive MCP as the mandatory primary preflight/readback;
2. the first post-PR-A transport sequence is one monolithic PR-B followed by PR-C;
3. the CEO shell itself needs a Business/private-Plugin dependency.

The following remain binding:

* Executive SQLite is the sole Job/Attempt/Worker/Event lifecycle authority;
* `control_plane.ceo_intent.submit_intent` is the canonical v1 admission sink;
* PR-A remains exactly submit + Slack-namespace status and must be Sol-accepted before R0;
* Slack is transport/receipt, not runtime state or automatic wake;
* Agent OS is organizational memory, not a task/execution store;
* one modifying operation binds to one carrier until canonical reconciliation;
* no Slack lifecycle DB, dedupe DB, replay-cursor DB, seat inbox, direct SQLite or broad
  Operator access is authorized;
* Wake and generic `#agent-dispatch` remain held beyond MAS-48 production proof.

## Organizational-memory clarification

`WS:AGENT-OS` appears in `affects` because that existing workstream owns maintenance of
Agent OS organizational memory and the Linear/Slack operating-law records. This decision
does **not** assign an Executive runtime `workstream: WS:AGENT-OS` to MAS-48, MAS-75 or any
CEO intent.

The existing discovery `DSC:EXECUTIVE-OS-NO-PROGRAM-ROW` remains controlling: the global
program registry still lacks a lawful Executive OS program parent. Do not invent an
approximate Agent OS Executive workstream to make the portfolio look tidier. Full product
architecture stays in Mastermind research/docs; Agent OS records the cross-session ruling
and handoff only.

## Current execution gate

At this decision point:

* F0 / Mastermind #99 is accepted and merged;
* MAS-48/MAS-9 Linear projection has been reconciled to the new sequence;
* MAS-75 / PR-A is implemented on Mastermind #100 but remains `HOLD-FOR-SOL` with a
  requested repair so `control_plane.ceo_request` becomes the single shared normalization
  implementation required by #96;
* SHELL-1 / MAS-110 and S0 / MAS-106 are independent post-F0 waves;
* R0/B1/C1/B2/C2 remain dependency-held.

The next session must not skip directly from F0 to B2/C2 merely because a Slack app or
Socket Mode connection is technically available.
