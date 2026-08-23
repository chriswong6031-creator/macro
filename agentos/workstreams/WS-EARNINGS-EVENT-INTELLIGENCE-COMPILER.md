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
  HOLD-FOR-SOL: E3-A2 draft PR. Do not merge. Do not mark E3-A2 done.
  Do not start E3-B.
owns_paths:
  - research/earnings_intelligence/e3/**
  - engine/company_intelligence/qa_reconstruction.py
  - tests/test_company_intelligence_qa_reconstruction.py
artifacts:
  - research/earnings_intelligence/e3/E3_EVENT_INTELLIGENCE_COMPILER_FREEZE_2026-08-20.md
  - research/earnings_intelligence/e3/E3A_AAPL_SHADOW_EXTRACTION_HANDOFF_2026-08-20.md
  - research/earnings_intelligence/e3/E3B_AAPL_LIVE_QA_HANDOFF_2026-08-20.md
  - research/earnings_intelligence/e3/E3C_SECOND_EVENT_GENERALIZATION_HANDOFF_2026-08-20.md
  - research/earnings_intelligence/e3/E3P_NATURAL_CYCLE_COMMISSIONING_HANDOFF_2026-08-20.md
  - agentos/handoffs/EARNINGS-EVENT-INTELLIGENCE-COMPILER-2026-08-21.md
  - agentos/handoffs/EARNINGS-EVENT-INTELLIGENCE-COMPILER-2026-08-22.md
  - agentos/handoffs/EARNINGS-EVENT-INTELLIGENCE-COMPILER-2026-08-22-e3a-r1.md
  - agentos/handoffs/EARNINGS-EVENT-INTELLIGENCE-COMPILER-2026-08-23-e3a-r2.md
  - agentos/handoffs/EARNINGS-EVENT-INTELLIGENCE-COMPILER-2026-08-23-e3a-landed.md
  - agentos/handoffs/EARNINGS-EVENT-INTELLIGENCE-COMPILER-2026-08-23-e3a2.md
  - engine/company_intelligence/qa_reconstruction.py
  - tests/test_company_intelligence_qa_reconstruction.py
  - research/earnings_intelligence/e3/e3a2_aapl_fy2026_q3_reconstruction_receipt.json
  - research/earnings_intelligence/e3/gold/aapl_fy2026_q3_qa_gold.json
  - research/earnings_intelligence/e3/gold/aapl_fy2026_q3_eval_receipt.json
  - research/earnings_intelligence/e3/gold/aapl_fy2026_q3_adjudication_receipt.json
  - research/earnings_intelligence/e3/gold/aapl_fy2026_q3_blind_pass_b.json
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
  - Do not tune Qwen's full-transcript prompt to rescue a measured [] result.
  - Do not collapse qa_exchange.v1 respondents[] to unique speakers.
  - Do not treat a validator rejection as an accepted-object hard-gate miss.
  - Do not rewrite AAPL historical gold when a later current-marker generation moves if source SHAs still match.
  - Do not rewrite the pre-inference blind Pass B packet after inference.
  - Do not treat blind-packet hash b2ae2508… as the qa_topic.v1 taxonomy hash.
  - Do not treat Haiku topic Jaccard as usefulness, promotion, or topic-model authority.
  - Do not grant Haiku production authority.
  - Do not manufacture a numeric usefulness threshold from N=7.
  - Do not start E3-B. E3-B remains locked until E3-A2 is complete and Sol unlocks it.
  - Do not treat E3-A2 structural reconstruction as qa_exchange.v1 publication authority.
  - Do not copy Pass-A topic labels into deterministic reconstruction.
  - Do not put AAPL names, tickers, or boundary indexes in qa_reconstruction.py.
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
    status: done
    depends_on: [E3-0]
    pr: 6245
    artifacts:
      - research/earnings_intelligence/e3/gold/aapl_fy2026_q3_qa_gold.json
      - research/earnings_intelligence/e3/gold/aapl_fy2026_q3_eval_receipt.json
      - research/earnings_intelligence/e3/gold/aapl_fy2026_q3_adjudication_receipt.json
      - research/earnings_intelligence/e3/gold/aapl_fy2026_q3_blind_pass_b.json
      - engine/company_intelligence/e3_shadow_compiler.py
      - tests/test_company_intelligence_event_compiler_e3a.py
    next_action: >
      Done as a completed calibration / negative-method experiment.
      Squash-merge d919637f3680d3da25a904484749409b043f60e9
      (#6245; Sol review 5001747968; accepted head
      b403fba8e141e4a12083f97d104a851178f68051).
      Full-transcript Qwen structural extraction not promoted.
      Haiku benchmark-only. Topic adjudication UNRESOLVED /
      PASS_A_REFERENCE_ONLY. Structural gold accepted: 7 exchanges /
      26 answer-turns. No numeric usefulness threshold manufactured.
  - id: E3-A2
    title: Deterministic source-native Q&A skeleton
    status: in_progress
    depends_on: [E3-A]
    artifacts:
      - engine/company_intelligence/qa_reconstruction.py
      - tests/test_company_intelligence_qa_reconstruction.py
      - research/earnings_intelligence/e3/e3a2_aapl_fy2026_q3_reconstruction_receipt.json
    next_action: >
      Draft PR held for Sol. Local proof: 7 exchanges / 26 answer-turns /
      exact AAPL structural gold parity; runtime has no gold import and
      no AAPL literals. Topics remain UNRESOLVED / PASS_A_REFERENCE_ONLY.
      Do not merge. Do not mark this wave done. Do not start E3-B.
  - id: E3-B
    title: AAPL live Q&A into event_workspace.v1
    status: todo
    depends_on: [E3-A2]
    next_action: >
      LOCKED. Do not start E3-B. Depends on E3-A2 completing and an
      explicit Sol unlock. Do not publish live qa_exchanges from the
      E3-A model experiment.
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

E3-A is done as a completed calibration / negative-method experiment. Immutable squash-merge SHA: `d919637f3680d3da25a904484749409b043f60e9` (#6245; Sol review 5001747968; accepted head `b403fba8e141e4a12083f97d104a851178f68051`; merged 2026-08-23T05:57:38Z). Gold is `aapl_fy2026_q3_qa_gold.v2` SHA `fc6df84d2a8d0d96475ce697ba92ffdd071d5c283b8daee97c1b3381382fa42c`; v1 `6b1100b148396db9a29974da5bc6e0cc55e5534185e50e061fe3635d429ed761` is superseded calibration gold. Canonical taxonomy remains `qa_topic.v1` / `a928ca72ab2e91bda74bd1e69021e08a5234e501f095610e623655db7e323b5e`. The immutable blind Pass B packet stores `b2ae2508877ccda4dea911d52952c49f78b0dbc26049326d542ee77439cf9a14` as a **noncanonical pass-local members digest**, not the qa_topic.v1 hash; enum membership matches. **Topic adjudication is UNRESOLVED / PASS_A_REFERENCE_ONLY** — Pass A and Pass B disagree on all 7 per-exchange topic sets; Haiku Jaccard 0.722 is descriptive against Pass-A reference labels only and grants zero topic-model authority. Structural gold is accepted: 7 Operator-delimited exchanges, exact source spans, identities, 26 management answer-turns. Measured eval `run_id=27e3e380f70658c1`: Qwen `[]` (NOT_EXERCISED, local $0.00) — full-transcript Qwen structural extraction is **not promoted**; Haiku remains **benchmark-only**. No numeric usefulness threshold was manufactured.

E3-A2 is implemented on a held draft PR and is **not done**. Generic runtime `engine/company_intelligence/qa_reconstruction.py` reconstructs Operator-`go ahead` exchanges, question/answer spans, questioner identity, and management answer-turns from source segments only. Local AAPL oracle parity is 7 exchanges / 26 turns with exact spans and identities; topics are not copied. **E3-B stays locked.** Sol decides whether E3-A2 lands. Do not start E3-B.
