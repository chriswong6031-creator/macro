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
status: active
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
  E3-A R1 measured packet is on HOLD-FOR-SOL PR #6245. Gold SHA
  unchanged. Usefulness bar remains the frozen N=7 refusal. Await Sol;
  do not merge #6245; do not start E3-B.
owns_paths:
  - research/earnings_intelligence/e3/**
artifacts:
  - research/earnings_intelligence/e3/E3_EVENT_INTELLIGENCE_COMPILER_FREEZE_2026-08-20.md
  - research/earnings_intelligence/e3/E3A_AAPL_SHADOW_EXTRACTION_HANDOFF_2026-08-20.md
  - research/earnings_intelligence/e3/E3B_AAPL_LIVE_QA_HANDOFF_2026-08-20.md
  - research/earnings_intelligence/e3/E3C_SECOND_EVENT_GENERALIZATION_HANDOFF_2026-08-20.md
  - research/earnings_intelligence/e3/E3P_NATURAL_CYCLE_COMMISSIONING_HANDOFF_2026-08-20.md
  - agentos/handoffs/EARNINGS-EVENT-INTELLIGENCE-COMPILER-2026-08-21.md
  - agentos/handoffs/EARNINGS-EVENT-INTELLIGENCE-COMPILER-2026-08-22.md
  - agentos/handoffs/EARNINGS-EVENT-INTELLIGENCE-COMPILER-2026-08-22-e3a-r1.md
  - research/earnings_intelligence/e3/gold/aapl_fy2026_q3_qa_gold.json
  - research/earnings_intelligence/e3/gold/aapl_fy2026_q3_eval_receipt.json
  - research/earnings_intelligence/e3/gold/aapl_fy2026_q3_adjudication_receipt.json
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
  - Do not reopen the ratified E3-0 freeze (#6161 / 22686d255eb047cf5bffc91a35984515acb3d466).
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
    status: done
    pr: 6161
    next_action: >
      Landed. Squash-merge 22686d255eb047cf5bffc91a35984515acb3d466
      (Sol review 5000425939). Do not reopen architecture.
  - id: E3-A
    title: AAPL shadow extraction gold + leakage-free Qwen eval
    status: in_progress
    depends_on: [E3-0]
    artifacts:
      - research/earnings_intelligence/e3/gold/aapl_fy2026_q3_qa_gold.json
      - research/earnings_intelligence/e3/gold/aapl_fy2026_q3_eval_receipt.json
      - research/earnings_intelligence/e3/gold/aapl_fy2026_q3_adjudication_receipt.json
      - engine/company_intelligence/e3_shadow_compiler.py
      - tests/test_company_intelligence_event_compiler_e3a.py
    next_action: >
      Measured E3-A R1 packet is on PR #6245 (HOLD-FOR-SOL / draft /
      hold / do-not-merge). Gold SHA unchanged
      6b1100b148396db9a29974da5bc6e0cc55e5534185e50e061fe3635d429ed761.
      Usefulness bar remains the frozen N=7 refusal. Return to Sol.
      Do not start E3-B. Do not merge #6245 until Sol releases the hold.
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

E3-0 landed on main at `22686d255eb047cf5bffc91a35984515acb3d466` (#6161; Sol review 5000425939). E0–E2 stay closed on `WS:EARNINGS-INTELLIGENCE-OS`. Canonical freeze: `research/earnings_intelligence/e3/E3_EVENT_INTELLIGENCE_COMPILER_FREEZE_2026-08-20.md`. Owner is `coo-fable` (execution). Architecture authority is `DEC:E3-EVENT-INTELLIGENCE-COMPILER-NOT-SCORER` `decided_by: sol`.

E3-A R1 (2026-08-22) repaired the evaluator and ran the real model eval on PR #6245. Gold SHA remains `6b1100b148396db9a29974da5bc6e0cc55e5534185e50e061fe3635d429ed761`. Taxonomy `qa_topic.v1` / `a928ca72ab2e91bda74bd1e69021e08a5234e501f095610e623655db7e323b5e` unchanged. Live E2 workspace `f709a0a6ec514282d5769e7d` was read through `read_event_workspace`; release and transcript source SHAs match the frozen fixtures (`assumed_from_handoff=false`). Qwen `qwen3.5:9b` on the earnings-worker loopback (`127.0.0.1:11435`, plist override) returned `[]` (hard gates `NOT_EXERCISED`). Comparator `claude-haiku-4-5` via existing `llm_auth` oauth produced 7 valid candidates; boundary P/R/F1 = 1.0; mean topic Jaccard 0.667; identity/role all 1.0 on matched exchanges; span replay 100% of 7 accepted. Usefulness bar remains the frozen N=7 refusal. **Return to Sol. E3-B stays locked. Do not merge #6245.**
