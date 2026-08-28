---
key: PORTFOLIO-CONSUMES-NOT-RECOMPUTES-MARKET-RISK
question: >
  Does Mastermind Portfolio keep independently originating firm-wide market
  truth (its local fused risk state, market view, posture planes), or does it
  consume the canonical Grey Deer envelope and own only book-specific
  decisions?
answer: >
  Macro owns market truth; Portfolio consumes it. Mastermind Portfolio owns
  book state, mandates, user authority, dwell, exposure, sizing, settlement
  and execution — and combines those with the consumed envelope. The legacy
  Portfolio market fusion (brain/macro_risk.py fixed-weight fusion,
  brain/market_view.py as independent consensus authority,
  brain/posture_decider.py's fused posture) becomes a temporary compatibility
  adapter, measured against the envelope in shadow (GD-9A), and retires its
  market-truth origination only after prospective parity evidence, proven
  rollback, and Sol + Chairman approval (GD-10). Envelope absent/stale can
  never loosen risk: Portfolio enters UNKNOWN_PROTECTIVE.
rationale: >
  Two independent market-truth planes diverge silently — the incident had
  Portfolio-local fusion and Macro organs disagreeing with no lawful
  reconciliation, so neither could be graded or trusted. One canonical,
  provenance-backed envelope makes the market input auditable and shared
  across Macro/Prophet/Terminal/Portfolio, while book-specific authority
  stays where user mandates and settlement actually live. Shadow-first with
  rollback (no deletion-first) is required because Portfolio constraints are
  decision-bearing.
alternatives:
  - option: Portfolio keeps permanent independent market fusion
    why_not: >
      Permanent dual truth: divergence is invisible until it bites, every
      improvement must ship twice, and Grey Deer's receipts stop at the repo
      boundary. Explicitly banned as the end state by freeze §3/§12 and
      command packet law 9.
  - option: Delete legacy Portfolio market-risk modules in the first PR
    why_not: >
      Deletion-first removes the rollback path and the shadow-parity baseline;
      GD-10 requires legacy modules behind compatibility/rollback until
      post-cutover observation proves the new path.
  - option: Macro pushes sizing/execution directives to Portfolio directly
    why_not: >
      Gives Macro actual portfolio execution power — a program-level stop
      condition (command packet §20); book authority (mandates, user opt-in,
      settlement) is Portfolio's and never crosses the repo boundary.
evidence:
  - "research/grey_deer/GREY_DEER_RISK_INTELLIGENCE_ARCHITECTURE_FREEZE_2026-08-19.md §3 (ownership), §12 (freeze-as-legacy list)"
  - "research/grey_deer/GREY_DEER_FABLE_EXECUTION_COMMAND_PACKET_2026-08-19.md §3.3 (current Portfolio machinery), §11 GD-9A/GD-10 (shadow, cutover preconditions, UNKNOWN_PROTECTIVE)"
affects:
  - "WS:GREY-DEER-RISK-INTELLIGENCE"
  - "portfolio-desk"
  - "portfolio-control-plane"
  - "macro-intelligence-adapter"
confidence: high
reversibility: costly
decided_by: ceo-sol
decided_at: 2026-08-19
---

## Grounds

Sol architecture freeze 2026-08-19 (§3, §12), commissioned by Chairman Chris.
Cutover itself (GD-10) additionally requires Sol acceptance and Chairman
approval because it changes decision-bearing portfolio constraints.

## What would reopen this

Sol/Chairman only. If GD-9A shadow parity reveals book-critical market inputs
the envelope structurally cannot carry, that finding escalates before any
cutover — it does not license Portfolio to resume independent market-truth
origination after cutover (a named program stop condition).
