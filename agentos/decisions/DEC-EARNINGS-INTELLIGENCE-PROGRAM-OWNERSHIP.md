---
key: EARNINGS-INTELLIGENCE-PROGRAM-OWNERSHIP
question: >
  What is the canonical program key and ownership boundary for the Earnings /
  Company Event product relative to group-reads, thematic-intelligence,
  neural-web, and prophet?
answer: >
  Keep the existing registry key earnings-intelligence. The product name is
  Mastermind Earnings Intelligence OS. It owns event, document, claim, and
  earnings product truth, including the public Wire as an evidence/acquisition
  surface and the Event Workspace payload. It consumes Group Reads and TIL,
  feeds Neural Web/research, and feeds Prophet only through governed
  context/shadow contracts. Do not mint a second program key in E0.
rationale: >
  config/mastermind_programs.yml already has earnings-intelligence as a
  context_only semantic rail. group-reads already owns group earnings
  read-through. thematic-intelligence already owns theme lifecycle and
  explicitly does not own earnings read-through. Creating earnings-intelligence-os
  as a second key would duplicate the control-plane prohibition and require
  generated-map work that E0 must not take. Expanding owns/does_not_own on the
  existing key is the honest follow-up, in a later registry PR.
alternatives:
  - option: Mint a new key earnings-intelligence-os / company-event-intelligence
    why_not: >
      A second key for the same organ splits ownership, trips duplicate_control_planes
      spirit, and forces generated-map regeneration in an E0 docs freeze.
  - option: Park the product under group-reads because that program already
      mentions earnings read-through
    why_not: >
      Group Reads owns basket participation and sympathy, not issuer event/claim
      truth or the Wire/Terminal workspace. Mislabeling would hide the real owner.
  - option: Leave ownership unspecified until a later wave
    why_not: >
      The E0 handoff required a freeze so E1 does not invent a program boundary.
evidence:
  - "config/mastermind_programs.yml:2046-2081 earnings-intelligence owns evidence packets; does_not_own selection/ranking/sizing/gates"
  - "config/mastermind_programs.yml:1289-1293 group-reads owns group earnings read-through"
  - "config/mastermind_programs.yml:1247-1251 thematic-intelligence does_not_own earnings read-through"
  - "DEC:EARNINGS-INTELLIGENCE-IS-A-CENTRAL-LOBE"
  - "research/earnings_intelligence/E0_E1_E2_CONTRACT_FREEZE.md §0"
affects:
  - "WS:EARNINGS-INTELLIGENCE-OS"
  - earnings-intelligence
  - group-reads
  - thematic-intelligence
  - neural-web
  - prophet
confidence: high
reversibility: costly
decided_by: session-e0-freeze
decided_at: 2026-08-16
---

## Follow-up (not this PR)

Expand `owns` / `does_not_own` on `earnings-intelligence` and regenerate
`docs/MASTERMIND_SYSTEM_MAP.md` in a dedicated registry PR. E0 must not take
generated-map work.
