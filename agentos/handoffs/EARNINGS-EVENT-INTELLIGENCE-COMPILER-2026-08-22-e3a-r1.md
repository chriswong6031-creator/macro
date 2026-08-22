---
workstream: "WS:EARNINGS-EVENT-INTELLIGENCE-COMPILER"
session: claude/e3-a-aapl-shadow
model: local
ended_because: complete
mission: >
  E3-A R1 on the same PR #6245: preserve frozen gold, replace the false-green
  scorer with a deterministic shadow validator, mutation-test the evaluator,
  verify live E2 source SHAs, run real Qwen + stronger comparator inference,
  and return the measured packet to Sol. Do not merge. Do not start E3-B.
state_before: >
  PR #6245 held Sol's pre-inference gold/taxonomy as valuable PARTIAL work.
  E3-A was not merge-ready: false-green scorer, Qwen hitting YAML localhost:11434,
  comparator filtered to anthropic-only, live R2 proof assumed from handoff.
  Merge authority was disarmed (draft, HOLD-FOR-SOL, hold, do-not-merge).
changed:
  - path: engine/company_intelligence/e3_shadow_compiler.py
    what: Closed candidate schema + shadow validator + real 1-1 boundary scoring; Qwen uses earnings-worker EARNINGS_LLM override; comparator via llm_auth oauth/anthropic; telemetry lane=earnings_event_compiler with AI_COSTS_SHARD.
  - path: tests/test_company_intelligence_event_compiler_e3a.py
    what: Mutation tests for OOR segment, unknown topic, missing/wrong-type, foreign identity, wrong Operator boundary, duplicates, wrong role, replay failure, synthetic 100% replay, and empty-set NOT_EXERCISED.
  - path: research/earnings_intelligence/e3/gold/aapl_fy2026_q3_eval_receipt.json
    what: Measured run d32326459522ff95 with live workspace proof and real Qwen/Haiku scores.
  - path: research/earnings_intelligence/e3/gold/aapl_fy2026_q3_adjudication_receipt.json
    what: dual_session adjudication receipt; gold SHA unchanged; Ternus role pinned CEO from held segment 94.
  - path: lib/ai_costs.py
    what: Map lane earnings_event_compiler to Qual lobe.
  - path: agentos/workstreams/WS-EARNINGS-EVENT-INTELLIGENCE-COMPILER.md
    what: E3-A R1 status; E3-B remains locked.
prs:
  - 6245
decisions:
  - DEC:E3-EVENT-INTELLIGENCE-COMPILER-NOT-SCORER
verified:
  - claim: Frozen gold SHA is unchanged.
    command: python3 -c "import hashlib; print(hashlib.sha256(open('research/earnings_intelligence/e3/gold/aapl_fy2026_q3_qa_gold.json','rb').read()).hexdigest())"
    result: 6b1100b148396db9a29974da5bc6e0cc55e5534185e50e061fe3635d429ed761
  - claim: Live E2 generation f709a0a6ec514282d5769e7d source SHAs equal frozen fixtures.
    command: engine.neuralweb.company_intelligence_reader.read_event_workspace against public R2, recorded in eval receipt steps.sha_verification.live_workspace
    result: "workspace_sha256=dbd50e5c30e8a031f844e02362ffd53b25e3230e75eeef19bf3825543cb81197; release=070abd6a…; transcript=a8ff5d03…; assumed_from_handoff=false"
  - claim: John Ternus role in gold matches held transcript segment 94.
    command: python3 scan of tests/fixtures/company_intelligence/aapl_fy2026_q3.json.gz segment 94 speaker/role
    result: speaker=John Ternus role=CEO; gold already CEO; no gold correction
  - claim: E3-A evaluator tests pass including empty-set NOT_EXERCISED.
    command: python3 -m pytest tests/test_company_intelligence_event_compiler_e3a.py -q
    result: 51 passed
  - claim: Measured eval run d32326459522ff95 produced real Qwen and Haiku results.
    command: PYTHONPATH=. run_e3a_eval with Dashboard venv + existing Mastermind OAuth env
    result: "Qwen qwen3.5:9b loopback/plist [] NOT_EXERCISED; Haiku oauth 7/7 valid TP=7 P=R=F1=1.0 Jaccard=0.667 identity=1.0 replay=100%"
unverified:
  - claim: Hosted CI/fences on the post-repair head have not concluded at handoff write time.
    what_would_verify: gh pr checks 6245 after the R1 head is pushed
unresolved:
  - Usefulness bar remains the frozen N=7 refusal; no E3-B grant.
  - Qwen returned a real empty candidate list; local 9b model did not extract the seven Operator exchanges.
  - PR #6245 must stay draft/HOLD-FOR-SOL until Sol releases.
next_actions:
  - Sol reviews the measured E3-A R1 packet on #6245.
  - Do not merge #6245 and do not start E3-B unless Sol explicitly grants.
  - Keep merge-on-green off; keep hold + do-not-merge.
do_not_redo:
  - Do not change gold SHA 6b1100b148396db9a29974da5bc6e0cc55e5534185e50e061fe3635d429ed761 unless a held-source error is proven.
  - Do not treat questioner-name equality as an Operator-boundary TP.
  - Do not report 100% replay or all_pass=true on an empty accepted set.
  - Do not point Qwen at YAML localhost:11434 when the earnings worker override is 127.0.0.1:11435.
  - Do not create a second local-model route or a new secret file.
  - Do not auto-unlock E3-B because Haiku boundary F1 was 1.0.
danger_areas:
  - Default python3.14 on this host has no anthropic SDK; comparator must use the Macro Dashboard venv.
  - AI_COSTS_SHARD / PROVIDER_HEALTH_PATH keep eval rows out of global JSONL; do not git add data/ai_costs or metabolism ledgers.
  - Closed candidate schema rejects unknown keys; do not re-require boundary_segment_index to be inside question_segment_indexes.
  - Sweeper will merge an armed unlabeled PR; the Sol hold is the merge barrier.
---

E3-A R1 measured packet is complete and returns to Sol. E3-B remains locked.
