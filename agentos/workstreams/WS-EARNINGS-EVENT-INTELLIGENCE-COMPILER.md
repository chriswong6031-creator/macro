---
key: EARNINGS-EVENT-INTELLIGENCE-COMPILER
title: Earnings Event Intelligence Compiler — E3 arc
objective: >
  Build one clock-safe Event Intelligence Compiler in which models propose
  candidates, deterministic validation admits evidence, and accepted
  intelligence extends the existing canonical event_workspace.v1. Done means
  E3-A gold+leakage-free eval, E3-B non-empty live AAPL Q&A in Terminal,
  E3-C non-empty second-issuer Q&A in product, and E3-P natural-cycle
  accepted exchange on an eligible print. No earnings_qual score as event
  truth and no FIF/Prophet fork.
status: awaiting_review
program: earnings-intelligence
repos: [macro, terminal]
owner: coo-fable
class: research
blast_radius: user_facing
ambiguity: specified
depends_on:
  - WS:EARNINGS-INTELLIGENCE-OS
decisions:
  - DEC:E3-EVENT-INTELLIGENCE-COMPILER-NOT-SCORER
next_action: >
  HOLD-FOR-SOL on PR #6161 after the Sol-review-4998678880 amendment.
  Do not begin E3-A, model calls, gold files, R2 writes, Terminal, or FIF
  work until Sol ratifies the amended freeze.
owns_paths:
  - research/earnings_intelligence/e3/**
artifacts:
  - research/earnings_intelligence/e3/E3_EVENT_INTELLIGENCE_COMPILER_FREEZE_2026-08-20.md
  - research/earnings_intelligence/e3/E3A_AAPL_SHADOW_EXTRACTION_HANDOFF_2026-08-20.md
  - research/earnings_intelligence/e3/E3B_AAPL_LIVE_QA_HANDOFF_2026-08-20.md
  - research/earnings_intelligence/e3/E3C_SECOND_EVENT_GENERALIZATION_HANDOFF_2026-08-20.md
  - research/earnings_intelligence/e3/E3P_NATURAL_CYCLE_COMMISSIONING_HANDOFF_2026-08-20.md
  - agentos/handoffs/EARNINGS-EVENT-INTELLIGENCE-COMPILER-2026-08-21.md
needs_ceo:
  question: >
    Ratify the amended E3-0 freeze after review 4998678880 (compiler not
    scorer; versioned nested source-clock with document-revision
    source_available_at; Q&A-first into existing qa_exchanges; ordered
    respondents; speaker_unresolvable; taxonomy version/hash;
    revision-scoped exchange_id; no candidate store; non-vacuous E3-B/C/P)?
  options:
    - "Ratify the amended freeze and unlock E3-A"
    - "Request one further bounded amendment"
    - "Reject and keep E3 parked"
  recommendation: >
    Ratify. The thesis was already accepted; this packet only closes the
    seven named findings. Do not begin E3-A until this lands.
  by_when: 2026-08-23
landmines:
  - WS:EARNINGS-INTELLIGENCE-OS is done; do not reopen E2-T1 or E2-D to make E3 look active.
  - Parent event_workspace.v1 WORKSPACE_KEYS are closed; a new top-level key is a schema bump Terminal exactKeys will fail.
  - Macro nested sources[] are list-only (silent pass); Terminal nested sources are strip; that is not additive compatibility.
  - DNR:KILL-LLM-ORIGINATION and DNR:KILL-LLM-FRAME-TAGS — no deflection/evasiveness/non-answer verdicts in E3.
  - FIF remains financial-fact authority; FIF-7 still owns earnings/non-GAAP/KPI/guidance convergence; basis_match true and beat/miss stay forbidden.
  - Local Qwen _call_openai_compat currently writes no ai_costs row; E3 must ledger it.
  - earnings_qual head/tail truncation is not canonical extraction.
  - identity_not_in_source is not a valid TypedAbsence reason; use speaker_unresolvable.
  - N=7 AAPL gold is calibration, not OOS; do not auto-unlock E3-B without a pre-frozen or Sol-granted usefulness gate.
do_not_redo:
  - Do not implement runtime E3 in the architecture wave.
  - Do not treat earnings_qual output as event truth.
  - Do not create a second Q&A store beside qa_exchanges.
  - Do not create a second model-routing control plane.
  - Do not create a durable candidate database or R2 plane in E3-A or E3-B.
  - Do not freeze GOOGL (or CAT/BAC/SNOW) as the E3-C issuer before a held source-completeness receipt.
  - Do not invent or loosen Q&A usefulness thresholds after seeing model results.
  - Do not stamp generated_at or conference time as transcript source_available_at.
  - Do not mint a second earnings-intelligence program key.
  - Do not record this architecture decision as decided_by coo-fable.
waves:
  - id: E3-0
    title: Compiler architecture freeze
    status: awaiting_ci
    pr: 6161
    next_action: Sol ratification of the amended DRAFT HOLD PR. Docs only.
  - id: E3-A
    title: AAPL shadow extraction gold + leakage-free Qwen eval
    status: todo
    depends_on: [E3-0]
    next_action: Freeze gold, taxonomy, scoring method, and any usefulness bar before the first model call.
  - id: E3-B
    title: AAPL live Q&A into event_workspace.v1
    status: todo
    depends_on: [E3-A]
    next_action: Publish non-empty accepted qa_exchanges and render them in Terminal.
  - id: E3-C
    title: Second-event generalization
    status: todo
    depends_on: [E3-B]
    next_action: Register pass rule, freeze issuer from §11 receipt, then extract. GOOGL only if held.
  - id: E3-P
    title: Natural-cycle commissioning
    status: todo
    depends_on: [E3-C]
    next_action: Eligible natural print with source-supported Q&A yields ≥1 accepted exchange to a real consumer.
---

E3-0 is research/design only. E0–E2 stay closed on `WS:EARNINGS-INTELLIGENCE-OS`.
Canonical freeze: `research/earnings_intelligence/e3/E3_EVENT_INTELLIGENCE_COMPILER_FREEZE_2026-08-20.md`.
Owner is `coo-fable` (execution). Architecture authority is `DEC:E3-EVENT-INTELLIGENCE-COMPILER-NOT-SCORER` `decided_by: sol`.
