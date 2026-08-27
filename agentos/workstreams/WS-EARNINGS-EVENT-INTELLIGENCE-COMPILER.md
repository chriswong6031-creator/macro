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
  E3-B is PROVEN_LIVE / DONE. Terminal consumer #470 is merged at
  ab7ef1d7dc5c9218ff5f94575596d74e24cbf35d; Macro producer #6376 is merged at
  94285d03ba60fe3a6bdfcad8109cfb329fc08843; production generation
  5517b178afbab673bc8c7c5f contains the exact accepted transcript revision and seven
  qa_exchange.v1 objects; bounded public regressions pass; and authenticated Terminal
  production acceptance passed at 1440 EN / 820 EN / 390 ZH on Slack carrier
  1787728244.427289. After the E3-B closeout record lands, E3-C becomes eligible to start.
  Its first lawful action is the frozen source-completeness selection receipt before any
  extraction/model call: test GOOGL current package, then CAT, BAC, SNOW, and freeze only
  the first qualifying issuer. Do not preselect GOOGL. E3-P remains locked behind E3-C.
owns_paths:
  - research/earnings_intelligence/e3/**
  - engine/company_intelligence/qa_reconstruction.py
  - tests/test_company_intelligence_qa_reconstruction.py
  - engine/company_intelligence/qa_exchange.py
  - tests/test_company_intelligence_qa_exchange.py
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
  - agentos/handoffs/EARNINGS-EVENT-INTELLIGENCE-COMPILER-2026-08-24-e3a2.md
  - agentos/handoffs/EARNINGS-EVENT-INTELLIGENCE-COMPILER-2026-08-24-e3a2-landed.md
  - agentos/handoffs/EARNINGS-EVENT-INTELLIGENCE-COMPILER-2026-08-24-e3b.md
  - agentos/handoffs/EARNINGS-EVENT-INTELLIGENCE-COMPILER-2026-08-24-e3b-r1.md
  - agentos/handoffs/EARNINGS-EVENT-INTELLIGENCE-COMPILER-2026-08-25-e3b-built-not-proven.md
  - agentos/handoffs/EARNINGS-EVENT-INTELLIGENCE-COMPILER-2026-08-26-e3b-live-proof-narrowed.md
  - engine/company_intelligence/qa_exchange.py
  - tests/test_company_intelligence_qa_exchange.py
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
  - N=7 AAPL gold is calibration, not OOS; Chairman+Sol unlocked E3-B as deterministic structural publication with topics=["unavailable"], not as a numeric usefulness threshold.
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
  - Do not begin E3-C extraction/model work or freeze its issuer before a held source-completeness receipt exists.
  - Do not describe E3-A2 as production-live Q&A.
  - Do not treat E3-A2 structural reconstruction as qa_exchange.v1 publication authority without the E3-B canonical adapter/validator.
  - Do not copy Pass-A topic labels into deterministic reconstruction.
  - Do not put AAPL names, tickers, or boundary indexes in qa_reconstruction.py.
  - Do not treat the E3-B merges or publisher success as final production proof; final acceptance is the combined immutable/public/authenticated-browser receipt recorded in the E3-B closeout.
  - Do not rerun or republish merely to replace the already-successful scheduled E3-B generation.
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
    status: done
    depends_on: [E3-A]
    pr: 6306
    artifacts:
      - engine/company_intelligence/qa_reconstruction.py
      - tests/test_company_intelligence_qa_reconstruction.py
      - research/earnings_intelligence/e3/e3a2_aapl_fy2026_q3_reconstruction_receipt.json
    next_action: >
      Done. Squash-merge 1158c9a17712084c011581cd68933f09100c2e5a
      (#6306; Sol PASS; accepted head
      2f8b7ab443bcd020f0baef618b7ce90f2d6c90fa; H_IMPL
      a6c075f18a7205d943bf6d95aaf904e782a1267c). Landed capability is a
      deterministic shadow structural method, not production-live Q&A.
      Source-format limitations preserved for later generalization.
      E3-B unlocked separately by Chairman+Sol; do not reopen E3-A2.
  - id: E3-B
    title: AAPL live Q&A into event_workspace.v1
    status: done
    depends_on: [E3-A2]
    next_action: >
      PROVEN_LIVE / DONE. Terminal consumer #470 landed at
      ab7ef1d7dc5c9218ff5f94575596d74e24cbf35d and Macro producer #6376 landed at
      94285d03ba60fe3a6bdfcad8109cfb329fc08843. Scheduled production run 32928671722
      published generation 5517b178afbab673bc8c7c5f; exact live readback proved transcript
      SHA a8ff5d03e875fef5604791edbf625186c447af049e6e02f55bb89c68c7cc9f9f,
      seven qa_exchange.v1, 26 management turns and 68 replay spans. Public AAPL/LMND/E2/
      Prophet safety regressions passed. Authenticated Terminal production acceptance on the
      existing Chrome profile passed 1440 EN / 820 EN / 390 ZH with seven rendered exchanges,
      revision-safe 2026Q3 transcript navigation, zero horizontal overflow and zero application/
      browser errors. SOURCE_CLOCK_OWNER_GAP remains explicit and lawful.
  - id: E3-C
    title: Second-event generalization
    status: todo
    depends_on: [E3-B]
    next_action: >
      Eligible after the E3-B durable closeout lands. Before any extraction/model call,
      re-run the frozen source-completeness selection procedure: test GOOGL current package
      first, then CAT, BAC, SNOW; select only the first issuer with held release/filing plus
      byte-replayed transcript, adequate rights and at least one real operator-delimited Q&A
      exchange. Write the release/filing/transcript/slides/consensus/reaction completeness
      receipt into the E3-C carrier before extraction. If none qualifies, stop and acquire
      a package. Do not use synthetic corpus bodies as production sources.
  - id: E3-P
    title: Natural-cycle commissioning
    status: todo
    depends_on: [E3-C]
    next_action: Eligible natural print with source-supported Q&A yields ≥1 accepted exchange to a real consumer.
---

E3-0 landed on main at `22686d255eb047cf5bffc91a35984515acb3d466` (#6161; Sol review 5000425939). E0–E2 stay closed on `WS:EARNINGS-INTELLIGENCE-OS`. Canonical freeze: `research/earnings_intelligence/e3/E3_EVENT_INTELLIGENCE_COMPILER_FREEZE_2026-08-20.md`. Owner is `coo-fable` (execution). Architecture authority is `DEC:E3-EVENT-INTELLIGENCE-COMPILER-NOT-SCORER` `decided_by: sol`.

E3-A is done as a completed calibration / negative-method experiment. Immutable squash-merge SHA: `d919637f3680d3da25a904484749409b043f60e9` (#6245; Sol review 5001747968; accepted head `b403fba8e141e4a12083f97d104a851178f68051`; merged 2026-08-23T05:57:38Z). Gold is `aapl_fy2026_q3_qa_gold.v2` SHA `fc6df84d2a8d0d96475ce697ba92ffdd071d5c283b8daee97c1b3381382fa42c`; v1 `6b1100b148396db9a29974da5bc6e0cc55e5534185e50e061fe3635d429ed761` is superseded calibration gold. Canonical taxonomy remains `qa_topic.v1` / `a928ca72ab2e91bda74bd1e69021e08a5234e501f095610e623655db7e323b5e`. The immutable blind Pass B packet stores `b2ae2508877ccda4dea911d52952c49f78b0dbc26049326d542ee77439cf9a14` as a **noncanonical pass-local members digest**, not the qa_topic.v1 hash; enum membership matches. **Topic adjudication is UNRESOLVED / PASS_A_REFERENCE_ONLY** — Pass A and Pass B disagree on all 7 per-exchange topic sets; Haiku Jaccard 0.722 is descriptive against Pass-A reference labels only and grants zero topic-model authority. Structural gold is accepted: 7 Operator-delimited exchanges, exact source spans, identities, 26 management answer-turns. Measured eval `run_id=27e3e380f70658c1`: Qwen `[]` (NOT_EXERCISED, local $0.00) — full-transcript Qwen structural extraction is **not promoted**; Haiku remains **benchmark-only**. No numeric usefulness threshold was manufactured.

E3-A2 is done as a landed **deterministic shadow structural method**, not production-live Q&A. Immutable squash-merge SHA: `1158c9a17712084c011581cd68933f09100c2e5a` (#6306; Sol PASS; accepted head `2f8b7ab443bcd020f0baef618b7ce90f2d6c90fa`; H_IMPL `a6c075f18a7205d943bf6d95aaf904e782a1267c`; merged 2026-08-24T09:37:22Z). Runtime `engine/company_intelligence/qa_reconstruction.py` reconstructs Operator-`go ahead` exchanges from source segments only: no model calls, no gold import, no issuer literals, no live `qa_exchanges`. AAPL oracle parity remains 7 exchanges / 32 question spans / 36 answer spans / 26 turns / 68 replay. Topics remain UNRESOLVED / PASS_A_REFERENCE_ONLY. Source-format limitations (operator-intro identity grammar; other vendor intros may refuse) are preserved for later generalization. Chairman+Sol unlocked E3-B as deterministic structural publication with `topics=["unavailable"]`. E3-B is now closed; those AAPL-specific calibration limits remain relevant to E3-C generalization.

E3-B is **PROVEN_LIVE / DONE**. Terminal consumer #470 is merged at `ab7ef1d7dc5c9218ff5f94575596d74e24cbf35d`; Macro producer #6376 is merged at `94285d03ba60fe3a6bdfcad8109cfb329fc08843`; scheduled `company-intelligence` run `32928671722` published generation `5517b178afbab673bc8c7c5f`; exact live readback proved the accepted transcript revision plus seven `qa_exchange.v1` / 26 management turns / 68 replay spans; bounded public AAPL/LMND/E2/Prophet safety regressions passed; and the final authenticated Terminal acceptance on Slack carrier `1787728244.427289` passed at 1440 EN / 820 EN / 390 ZH with exact analyst/respondent ordering, Operator exclusion, revision-safe `2026Q3` transcript navigation, zero horizontal overflow, and zero application/browser errors. `SOURCE_CLOCK_OWNER_GAP` remains explicit and truthful. E3-C is not yet started; after this closeout lands, its first lawful action is the frozen source-completeness receipt before any extraction or issuer freeze.