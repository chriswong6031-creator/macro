---
key: EARNINGS-EVENT-INTELLIGENCE-COMPILER
title: Earnings Event Intelligence Compiler — E3 arc
objective: >
  Build one clock-safe Event Intelligence Compiler in which models propose
  candidates, deterministic validation admits evidence, and accepted
  intelligence extends the existing canonical event_workspace.v1. Done means
  E3-A gold+eval, E3-B live AAPL Q&A, E3-C second-event generalization, and
  E3-P natural-cycle commissioning are live, with no earnings_qual score as
  event truth and no FIF/Prophet fork.
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
  HOLD-FOR-SOL on the E3-0 architecture freeze PR. Do not begin E3-A, model
  calls, R2 writes, Terminal, or FIF work until Sol accepts the freeze.
owns_paths:
  - research/earnings_intelligence/e3/**
artifacts:
  - research/earnings_intelligence/e3/E3_EVENT_INTELLIGENCE_COMPILER_FREEZE_2026-08-20.md
  - research/earnings_intelligence/e3/E3A_AAPL_SHADOW_EXTRACTION_HANDOFF_2026-08-20.md
  - research/earnings_intelligence/e3/E3B_AAPL_LIVE_QA_HANDOFF_2026-08-20.md
  - research/earnings_intelligence/e3/E3C_SECOND_EVENT_GENERALIZATION_HANDOFF_2026-08-20.md
  - research/earnings_intelligence/e3/E3P_NATURAL_CYCLE_COMMISSIONING_HANDOFF_2026-08-20.md
needs_ceo:
  question: >
    Accept the E3-0 Event Intelligence Compiler freeze (compiler not scorer;
    versioned nested source-clock contract; first live vertical = structured
    Q&A into existing qa_exchanges; GOOGL not frozen until held)?
  options:
    - "Accept as written and unlock E3-A"
    - "Accept with a flip: treat nested source clocks as silent additive event_workspace.v1 keys"
    - "Reject and re-scope E3 (not this compiler, or not Q&A-first)"
  recommendation: >
    Accept as written. Silent additive source clocks would be stripped by
    Terminal normalizeSource and would not reach the public glance; G0
    forbade building model intelligence on collapsed clocks without a real
    nested contract. Do not begin E3-A until this lands.
  by_when: 2026-08-22
landmines:
  - WS:EARNINGS-INTELLIGENCE-OS is done; do not reopen E2-T1 or E2-D to make E3 look active.
  - Parent event_workspace.v1 WORKSPACE_KEYS are closed; a new top-level key is a schema bump Terminal exactKeys will fail.
  - Macro nested sources[] are list-only (silent pass); Terminal nested sources are strip; that is not additive compatibility.
  - DNR:KILL-LLM-ORIGINATION and DNR:KILL-LLM-FRAME-TAGS — no deflection/evasiveness/non-answer verdicts in E3.
  - FIF remains financial-fact authority; basis_match true and beat/miss stay forbidden.
  - Local Qwen _call_openai_compat currently writes no ai_costs row; E3 must ledger it.
  - earnings_qual head/tail truncation is not canonical extraction.
do_not_redo:
  - Do not implement runtime E3 in the architecture wave.
  - Do not treat earnings_qual output as event truth.
  - Do not create a second Q&A store beside qa_exchanges.
  - Do not create a second model-routing control plane.
  - Do not freeze GOOGL (or CAT/BAC/SNOW) as the E3-C issuer before a held source-completeness receipt.
  - Do not invent Q&A precision/recall thresholds before the AAPL gold is adjudicated.
  - Do not stamp generated_at as source_available_at.
  - Do not mint a second earnings-intelligence program key.
waves:
  - id: E3-0
    title: Compiler architecture freeze
    status: awaiting_ci
    next_action: Sol review of the draft HOLD PR. Docs only.
  - id: E3-A
    title: AAPL shadow extraction gold + Qwen eval
    status: todo
    depends_on: [E3-0]
    next_action: Frozen gold from production SHAs, then Qwen, then thresholds.
  - id: E3-B
    title: AAPL live Q&A into event_workspace.v1
    status: todo
    depends_on: [E3-A]
    next_action: Promote accepted qa_exchanges; Terminal+dossier consume them.
  - id: E3-C
    title: Second-event generalization
    status: todo
    depends_on: [E3-B]
    next_action: Freeze issuer from §11 receipt, then extract. GOOGL only if held.
  - id: E3-P
    title: Natural-cycle commissioning
    status: todo
    depends_on: [E3-C]
    next_action: Later print through the compiler; this is E3 done.
---

E3-0 is research/design only. E0–E2 stay closed on `WS:EARNINGS-INTELLIGENCE-OS`.
Canonical freeze: `research/earnings_intelligence/e3/E3_EVENT_INTELLIGENCE_COMPILER_FREEZE_2026-08-20.md`.
