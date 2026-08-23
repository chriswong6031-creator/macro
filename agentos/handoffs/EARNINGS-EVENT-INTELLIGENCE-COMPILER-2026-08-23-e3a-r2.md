---
workstream: "WS:EARNINGS-EVENT-INTELLIGENCE-COMPILER"
session: claude/e3-a-aapl-shadow
model: local
ended_because: complete
mission: >
  E3-A R2 final landing repair on the same PR #6245: freeze answer-turn
  gold after a genuine blind second adjudication, bind receipts to the
  producing code, repair exact-head replay, rerun both model paths once,
  and return the measured packet to Sol. Do not merge. Do not start E3-B.
state_before: >
  Sol accepted the R1 measurement as a real research result: Qwen
  qwen3.5:9b returned []; Haiku recovered 7/7 under unique-speaker gold.
  Full-transcript Qwen is not promoted. Exact-head replay of 3cadd220
  died in _bounded_telemetry_proof (health_path use-before-assignment).
  R1 "Pass B" was a post-model rescan, not a complete pre-inference
  second adjudication. respondents[] still collapsed unique speakers.
changed:
  - path: engine/company_intelligence/e3_shadow_compiler.py
    what: Fixed telemetry use-before-assignment; bound receipts to git_head/compiler/prompt/gold/source hashes; split rejection counters from accepted-object hard gates; local Qwen cost_basis=local $0.00; comparator usage_cycle_id=run_id; source-SHA calibration survives a later current-marker generation.
  - path: tests/test_company_intelligence_event_compiler_e3a.py
    what: Hermetic run_e3a_eval end-to-end; rejection-vs-accepted terminology; exchange-0 two Tim turns; moved-marker source-SHA pin.
  - path: research/earnings_intelligence/e3/gold/aapl_fy2026_q3_qa_gold.json
    what: Minted aapl_fy2026_q3_qa_gold.v2 with answer-turn respondents[]; v1 SHA recorded as superseded; boundaries/topics unchanged.
  - path: research/earnings_intelligence/e3/gold/aapl_fy2026_q3_blind_pass_b.json
    what: Independent pre-inference Pass B packet (transcript + E3-0 + qa_topic.v1 only).
  - path: research/earnings_intelligence/e3/gold/aapl_fy2026_q3_adjudication_receipt.json
    what: e3a_adjudication_receipt.v2; gold_correction true; Pass B is independent_pre_inference_dual_adjudication.
  - path: research/earnings_intelligence/e3/gold/aapl_fy2026_q3_eval_receipt.json
    what: Measured run 27e3e380f70658c1 bound to git_head 154ec6204e585c70a576a7cf249acc2b394aa69c.
  - path: agentos/workstreams/WS-EARNINGS-EVENT-INTELLIGENCE-COMPILER.md
    what: E3-A R2 status; E3-B remains locked.
prs:
  - 6245
decisions:
  - DEC:E3-EVENT-INTELLIGENCE-COMPILER-NOT-SCORER
verified:
  - claim: Gold v2 SHA is fc6df84d2a8d0d96475ce697ba92ffdd071d5c283b8daee97c1b3381382fa42c.
    command: python3 -c "import hashlib; print(hashlib.sha256(open('research/earnings_intelligence/e3/gold/aapl_fy2026_q3_qa_gold.json','rb').read()).hexdigest())"
    result: fc6df84d2a8d0d96475ce697ba92ffdd071d5c283b8daee97c1b3381382fa42c
  - claim: Exchange 0 preserves two Tim Cook answer-turns split by analyst follow-up 38.
    command: python3 inspect of gold exchanges[0].respondents span_indexes
    result: "Kevan/CFO [0,1]; Tim/CEO [2,3]; Tim/CEO [4,5] covering answer_spans 34/35, 36/37, 39/40"
  - claim: Blind Pass B was independent of Qwen/Haiku output and of the old gold labels.
    command: research/earnings_intelligence/e3/gold/aapl_fy2026_q3_adjudication_receipt.json pass_b.pass_kind
    result: independent_pre_inference_dual_adjudication; withheld gold labels and model output; SHA a2350969470e263abb99f2614b10c2fec568422e47c8b482b92e0a6a28ff47af
  - claim: E3-A evaluator tests pass including hermetic exact-head replay.
    command: python3 -m pytest tests/test_company_intelligence_event_compiler_e3a.py -q
    result: 57 passed
  - claim: Measured eval run 27e3e380f70658c1 is bound to freeze head 154ec620 and records Qwen [] plus Haiku benchmark.
    command: PYTHONPATH=. run_e3a_eval with Dashboard venv + existing Mastermind OAuth env
    result: "Qwen qwen3.5:9b loopback/plist [] cost_basis=local $0.00 NOT_EXERCISED; Haiku oauth 7 candidates 6 accepted 1 invalid_schema_rejected(topics_arity) boundary F1=0.857 questioner/affiliation=1.0 answer-turn respondent order=0.0 replay=100% of 6 accepted hard_gates=PASS"
unverified:
  - claim: Hosted CI/fences on the post-R2 head have not concluded at handoff write time.
    what_would_verify: gh run watch of ci.yml and fences.yml after the R2 head is pushed
unresolved:
  - Usefulness bar remains the frozen N=7 refusal; no E3-B grant.
  - Qwen again returned a real empty candidate list []; full-transcript Qwen is not promoted.
  - Haiku remains unique-speaker respondents without span_indexes, so turn-level respondent order match is 0.0 against gold v2.
  - PR #6245 must stay draft/HOLD-FOR-SOL until Sol releases.
next_actions:
  - Sol reviews the measured E3-A R2 packet on #6245.
  - Do not merge #6245 and do not start E3-B unless Sol explicitly grants.
  - Keep merge-on-green off; keep hold + do-not-merge.
do_not_redo:
  - Do not present a receipt whose git_head is not the producing code as exact-head proof.
  - Do not tune Qwen's full-transcript prompt to rescue [].
  - Do not collapse respondents[] to unique speakers.
  - Do not treat unsupported_rejected as accepted_unsupported.
  - Do not rewrite AAPL gold when a later current-marker generation moves if source SHAs still match.
  - Do not auto-unlock E3-B because Haiku recovered most Operator boundaries.
danger_areas:
  - Default python3.14 on this host has no anthropic SDK; comparator must use the Macro Dashboard venv.
  - AI_COSTS_SHARD / PROVIDER_HEALTH_PATH keep eval rows out of global JSONL; do not git add data/ai_costs or metabolism ledgers.
  - Live current-marker generation d7b99467… is not the calibration generation; bindings stay on f709a0a6… / dbd50e5c….
  - Sweeper will merge an armed unlabeled PR; the Sol hold is the merge barrier.
---

E3-A R2 measured packet is complete and returns to Sol. E3-B remains locked.
