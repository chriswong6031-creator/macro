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
  E3-B is PROVEN_LIVE / DONE. E3-C is GENERALIZATION_REFUSED_ON_SOURCE_FORMAT — in
  progress, NOT complete, awaiting a Sol ruling. The frozen GOOGL Q2 FY2026 package
  (evt_cik0001652044_2026q2_results / tx:GOOGL/2026Q2, transcript SHA a44db883...) was
  run through the UNCHANGED E3-A2 reconstructor and E3-B qa_exchange.v1 adapter and the
  compiler REFUSED: reconstruct_qa returned status=failed / operator_intro_identity_unparsed
  at boundary segment 0 with 0 exchanges, and accepted_qa_exchanges_for_transcript returned
  []. Three independent blockers, each sufficient alone: (B1) the 'go ahead' boundary cue is
  absent from all nine real analyst intros, which close 'Your line is now open' — the only
  cue hit is segment 0's pre-presentation IR handoff, a false boundary; (B2) this vendor
  publishes NO management role at all (role vocabulary {Operator, IR, ''} = 12/3/75; Pichai,
  Schindler and Ashkenazi are all roleless), so _is_management cannot classify management
  speech; (B3) qa_exchange._assert_respondent_identity requires a non-empty source role, so
  no respondent could be minted source-supported even downstream. Per the commission's
  scientific stop the compiler was NOT tuned on GOOGL, no GOOGL-specific extraction or
  boundary constant was added, Alphabet was NOT registered in production, and the issuer was
  NOT switched to CAT/BAC/SNOW. Canonical receipt is
  research/earnings_intelligence/e3/e3c_googl_2026q2_reconstruction_refusal_receipt.json.
  Next: Sol adjudicates whether a source-format generalization (role-optional management
  classification + vendor-neutral boundary cue) is an in-scope E3-C repair or needs its own
  pre-registered wave; whether a role-annotated GOOGL revision can be acquired; and whether
  the selection law permits re-entering the walk at CAT. E3-P remains locked behind E3-C.
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
  - research/earnings_intelligence/e3/e3c_googl_2026q2_source_completeness_receipt.json
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
  - agentos/handoffs/EARNINGS-EVENT-INTELLIGENCE-COMPILER-2026-08-27-e3c-refusal.md
  - research/earnings_intelligence/e3/e3c_googl_2026q2_reconstruction_refusal_receipt.json
  - tests/test_company_intelligence_qa_generalization_e3c.py
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
  - GOOGL source selection does not mean Alphabet is already in event_workspace.production_registry; current registry is AAPL + DHI/PHM/KBH/TOL. E3-C must extend that existing identity plane for GOOGL+GOOG, never add a second registry or duplicate GOOG event.
  - The 10 GOOGL Operator-intro detections are source-admission evidence only; they are not canonical qa_exchange.v1 extraction output and cannot be used to call E3-C complete.
  - Source admission is NOT reconstructability. The source census counted 10 Operator question-intro boundaries on GOOGL, but the compiler's _qualifying_boundaries admits only Operator segments containing the literal "go ahead" and found exactly ONE — segment 0's pre-presentation IR handoff, a false boundary. A passing admission census can sit on a transcript the reconstructor refuses outright.
  - Transcript segment ROLE vocabulary is vendor-specific and load-bearing. AAPL's held body publishes IR/CEO/CFO/Operator roles; GOOGL's publishes only {Operator, IR, ''} with all management roleless. qa_reconstruction._is_management is bool(role) and qa_exchange._assert_respondent_identity requires a non-empty role, so a roleless body cannot produce a source-supported respondent at either layer. Check the role histogram before assuming any new issuer is reconstructable.
  - The GOOGL refusal is a source-format dependency, NOT ticker hard-coding. The Q&A path carries no ticker literal; the only AAPL-derived runtime literal is the accepted-revision digest at engine/company_intelligence/qa_exchange.py:35, and the transcript document id is built generically at engine/company_intelligence/event_workspace_build.py:265. Do not "fix" this by hunting for ticker branches that do not exist.
do_not_redo:
  - Do not reopen the ratified E3-0 freeze (#6161 / 22686d255eb047cf5bffc91a35984515acb3d466).
  - Do not implement runtime E3 in the architecture wave.
  - Do not treat earnings_qual output as event truth.
  - Do not create a second Q&A store beside qa_exchanges.
  - Do not create a second model-routing control plane.
  - Do not create a durable candidate database or R2 plane in E3-A or E3-B.
  - Do not rerun the GOOGL→CAT→BAC→SNOW selection or switch to CAT/BAC/SNOW after GOOGL has been frozen unless the held GOOGL source revision is later falsified before extraction.
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
  - Do not describe E3-A2 as production-live Q&A.
  - Do not treat E3-A2 structural reconstruction as qa_exchange.v1 publication authority without the E3-B canonical adapter/validator.
  - Do not copy Pass-A topic labels into deterministic reconstruction.
  - Do not put AAPL or GOOGL names, tickers, or boundary indexes in qa_reconstruction.py.
  - Do not treat the E3-B merges or publisher success as final production proof; final acceptance is the combined immutable/public/authenticated-browser receipt recorded in the E3-B closeout.
  - Do not rerun or republish merely to replace the already-successful scheduled E3-B generation.
  - Do not start E3-P.
  - Do not tune the compiler on the frozen GOOGL event to rescue the measured refusal. Generalizing the "go ahead" boundary cue, the operator-intro identity grammar, the affiliation cut rule, or the management-role requirement while GOOGL is the registered E3-C event is fitting the method to the test set; it needs a Sol ruling and its own pre-registered wave.
  - Do not switch to CAT/BAC/SNOW because GOOGL refused. The freeze binds the issuer until the held GOOGL revision is falsified or Sol releases it.
  - Do not add Alphabet to event_workspace.production_registry() until a wave can publish non-empty accepted Q&A for it; registering it now ships a live workspace with empty qa_exchanges (capability false) and breaks tests/test_issuer_profiles_a5a.py:110.
  - Do not re-run the GOOGL reconstruction expecting a different answer; it is deterministic, pinned by tests/test_company_intelligence_qa_generalization_e3c.py, and the fixture is byte-frozen at the receipt SHA.
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
    status: in_progress
    depends_on: [E3-B]
    artifacts:
      - research/earnings_intelligence/e3/e3c_googl_2026q2_source_completeness_receipt.json
      - research/earnings_intelligence/e3/e3c_googl_2026q2_reconstruction_refusal_receipt.json
      - tests/test_company_intelligence_qa_generalization_e3c.py
      - tests/fixtures/company_intelligence/googl_fy2026_q2.json.gz
    next_action: >
      GENERALIZATION_REFUSED_ON_SOURCE_FORMAT — in progress, NOT complete, awaiting Sol.
      The unchanged compiler was run against the frozen GOOGL package and refused
      (operator_intro_identity_unparsed at boundary segment 0; 0 exchanges; accepted set
      []). Honest refusal is a receipt, not wave completion, so E3-C stays in progress.
      Three independent blockers are recorded in
      research/earnings_intelligence/e3/e3c_googl_2026q2_reconstruction_refusal_receipt.json:
      vendor-specific "go ahead" boundary cue, a transcript body that publishes no
      management role at all, and qa_exchange's non-empty respondent-role requirement.
      The compiler was NOT tuned, Alphabet was NOT production-registered, and the issuer
      was NOT switched. Safety gates held: accepted-unsupported 0, cross-event 0, both
      AAPL cross-event poisons rejected, fail-closed on a mutated SHA for both issuers,
      and AAPL exact at 7 exchanges / 26 turns / 68 spans. Sol must rule on: (1) whether a
      source-format generalization is an in-scope E3-C repair or needs its own
      pre-registered wave, (2) whether a role-annotated GOOGL revision can be acquired,
      (3) whether the selection law permits re-entering the walk at CAT.
  - id: E3-P
    title: Natural-cycle commissioning
    status: todo
    depends_on: [E3-C]
    next_action: Eligible natural print with source-supported Q&A yields ≥1 accepted exchange to a real consumer.
---

E3-0 landed on main at `22686d255eb047cf5bffc91a35984515acb3d466` (#6161; Sol review 5000425939). E0–E2 stay closed on `WS:EARNINGS-INTELLIGENCE-OS`. Canonical freeze: `research/earnings_intelligence/e3/E3_EVENT_INTELLIGENCE_COMPILER_FREEZE_2026-08-20.md`. Owner is `coo-fable` (execution). Architecture authority is `DEC:E3-EVENT-INTELLIGENCE-COMPILER-NOT-SCORER` `decided_by: sol`.

E3-A is done as a completed calibration / negative-method experiment. Immutable squash-merge SHA: `d919637f3680d3da25a904484749409b043f60e9` (#6245; Sol review 5001747968; accepted head `b403fba8e141e4a12083f97d104a851178f68051`; merged 2026-08-23T05:57:38Z). Gold is `aapl_fy2026_q3_qa_gold.v2` SHA `fc6df84d2a8d0d96475ce697ba92ffdd071d5c283b8daee97c1b3381382fa42c`; v1 `6b1100b148396db9a29974da5bc6e0cc55e5534185e50e061fe3635d429ed761` is superseded calibration gold. Canonical taxonomy remains `qa_topic.v1` / `a928ca72ab2e91bda74bd1e69021e08a5234e501f095610e623655db7e323b5e`. The immutable blind Pass B packet stores `b2ae2508877ccda4dea911d52952c49f78b0dbc26049326d542ee77439cf9a14` as a **noncanonical pass-local members digest**, not the qa_topic.v1 hash; enum membership matches. **Topic adjudication is UNRESOLVED / PASS_A_REFERENCE_ONLY** — Pass A and Pass B disagree on all 7 per-exchange topic sets; Haiku Jaccard 0.722 is descriptive against Pass-A reference labels only and grants zero topic-model authority. Structural gold is accepted: 7 Operator-delimited exchanges, exact source spans, identities, 26 management answer-turns. Measured eval `run_id=27e3e380f70658c1`: Qwen `[]` (NOT_EXERCISED, local $0.00) — full-transcript Qwen structural extraction is **not promoted**; Haiku remains **benchmark-only**. No numeric usefulness threshold was manufactured.

E3-A2 is done as a landed **deterministic shadow structural method**, not production-live Q&A. Immutable squash-merge SHA: `1158c9a17712084c011581cd68933f09100c2e5a` (#6306; Sol PASS; accepted head `2f8b7ab443bcd020f0baef618b7ce90f2d6c90fa`; H_IMPL `a6c075f18a7205d943bf6d95aaf904e782a1267c`; merged 2026-08-24T09:37:22Z). Runtime `engine/company_intelligence/qa_reconstruction.py` reconstructs Operator-`go ahead` exchanges from source segments only: no model calls, no gold import, no issuer literals, no live `qa_exchanges`. AAPL oracle parity remains 7 exchanges / 32 question spans / 36 answer spans / 26 turns / 68 replay. Topics remain UNRESOLVED / PASS_A_REFERENCE_ONLY. Source-format limitations (operator-intro identity grammar; other vendor intros may refuse) are preserved for later generalization. Chairman+Sol unlocked E3-B as deterministic structural publication with `topics=["unavailable"]`. E3-B is now closed; those AAPL-specific calibration limits remain relevant to E3-C generalization.

E3-B is **PROVEN_LIVE / DONE**. Terminal consumer #470 is merged at `ab7ef1d7dc5c9218ff5f94575596d74e24cbf35d`; Macro producer #6376 is merged at `94285d03ba60fe3a6bdfcad8109cfb329fc08843`; scheduled `company-intelligence` run `32928671722` published generation `5517b178afbab673bc8c7c5f`; exact live readback proved the accepted transcript revision plus seven `qa_exchange.v1` / 26 management turns / 68 replay spans; bounded public AAPL/LMND/E2/Prophet safety regressions passed; and the final authenticated Terminal acceptance on Slack carrier `1787728244.427289` passed at 1440 EN / 820 EN / 390 ZH with exact analyst/respondent ordering, Operator exclusion, revision-safe `2026Q3` transcript navigation, zero horizontal overflow, and zero application/browser errors. `SOURCE_CLOCK_OWNER_GAP` remains explicit and truthful.

E3-C is now **`GENERALIZATION_REFUSED_ON_SOURCE_FORMAT`** — in progress, **not** complete, awaiting a Sol ruling. Operation `e3c-googl-generalization-20260827-v1` ran the **unchanged** E3-A2 reconstructor and E3-B `qa_exchange.v1` adapter against the frozen GOOGL package and the compiler **refused**: `reconstruct_qa` returned `status=failed` / `operator_intro_identity_unparsed` at boundary segment 0 with **0 exchanges**, and `accepted_qa_exchanges_for_transcript` returned `[]`. No workspace was written, no typed absence was invented, and the E2 event did not regress. Three blockers were measured, each sufficient alone: **B1** the `go ahead` boundary cue is absent from all nine real analyst intros (they close "Your line is now open"), so the only cue hit is segment 0's pre-presentation IR handoff — a false boundary; **B2** this transcript vendor publishes **no management role at all** (role vocabulary `{Operator, IR, ''}` = 12/3/75, with Pichai/Schindler/Ashkenazi all roleless), so `_is_management` (which is `bool(role)`) cannot classify management speech; **B3** `qa_exchange._assert_respondent_identity` requires a non-empty source role, so no respondent could be minted source-supported even downstream. Per the commission's scientific stop the compiler was **not** tuned, no GOOGL-specific extraction or boundary constant was added, Alphabet was **not** production-registered, and the issuer was **not** switched to CAT/BAC/SNOW. Safety gates held throughout: accepted-unsupported 0, cross-event 0, both planted AAPL cross-event poisons rejected (`event_id does not match parent workspace`; then `span document_id mismatch` after relabelling), fail-closed on a mutated SHA for both issuers, and the AAPL regression exact at **7 exchanges / 26 management turns / 68 replay spans**. The refusal is a **source-format** dependency, not ticker hard-coding: the Q&A path holds no ticker literal, the sole AAPL-derived runtime literal is the accepted-revision digest at `engine/company_intelligence/qa_exchange.py:35`, and the transcript document id is built generically at `engine/company_intelligence/event_workspace_build.py:265`. E3-A2 predicted exactly this ("other vendor intros may refuse"). Canonical receipt: `research/earnings_intelligence/e3/e3c_googl_2026q2_reconstruction_refusal_receipt.json`; regression `tests/test_company_intelligence_qa_generalization_e3c.py`; byte-frozen fixture `tests/fixtures/company_intelligence/googl_fy2026_q2.json.gz`.

The superseded selection context remains true: fresh source census operation `e3c-source-census-20260826-v1` selected GOOGL Q2 FY2026 first and stopped without inspecting CAT/BAC/SNOW. The frozen package is `evt_cik0001652044_2026q2_results`, SEC accession `0001652044-26-000066`, Exhibit 99.1 SHA `a01f6bd87c7fa0dcb562493dda7348a1a37d017b4a4b5edb39b915b45688237e`, 8-K SHA `9e881beb88f9496e316a412fdb881a22b9244fdec75131b4fb00ae11d0f9f7e4`, and transcript `tx:GOOGL/2026Q2` SHA `a44db883463181ba73a536cb3643b81ea59a3e10c0f191859f7717538452d2a9`. Source-only admission found 10 Operator question-intro boundaries; these are not canonical extraction results. The receipt preserves transcript clock `unknown/null`, existing `rp_public_primary_v1` rights, and the dual-class requirement that GOOGL and GOOG remain one CIK-backed issuer/event. Current production workspace registry still lacks Alphabet, so the next E3-C implementation must extend that existing registry rather than fork identity. E3-C remains incomplete until non-empty accepted Q&A is published and consumed. E3-P remains locked.
