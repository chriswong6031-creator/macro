---
workstream: "WS:EARNINGS-EVENT-INTELLIGENCE-COMPILER"
session: claude/e3-a-aapl-shadow
model: local
ended_because: blocked
mission: >
  Execute E3-A leakage-free calibration gold from the exact E2 production
  source revisions, freeze gold + taxonomy + scoring method + usefulness bar
  BEFORE first model inference, then evaluate local Qwen and one stronger-model
  comparator independently against that gold with gold labels hidden.
state_before: >
  E3-0 landed at 22686d255eb047cf5bffc91a35984515acb3d466 (#6161, Sol review
  5000425939). qa_exchanges=[] hardcoded in event_workspace_build.py. No gold
  file, no taxonomy, no shadow compiler existed. Both fixture SHAs matched the
  frozen spec on checkout.
changed:
  - path: research/earnings_intelligence/e3/gold/aapl_fy2026_q3_qa_gold.json
    what: >
      NEW. Adjudicated gold — 7 operator-delimited exchanges with ordered question/answer
      spans (source_span.v1 locators), questioner name/affiliation (source_supported),
      respondents[] (Tim Cook, Kevan Parekh, John Ternus — not collapsed), topics from
      closed taxonomy. Taxonomy version qa_topic.v1 / hash
      a928ca72ab2e91bda74bd1e69021e08a5234e501f095610e623655db7e323b5e frozen from
      gold adjudication before any model inference. Usefulness bar: written refusal
      (N=7 too small for numeric threshold). SHA256: 6b1100b148396db9a29974da5bc6e0cc55e5534185e50e061fe3635d429ed761.
  - path: research/earnings_intelligence/e3/gold/aapl_fy2026_q3_eval_receipt.json
    what: >
      NEW. Eval receipt for the shadow eval run. Both model rungs unavailable:
      Qwen (localhost:11434 connection refused), Anthropic claude-haiku-4-5
      (no API key). 0 candidates produced. All hard safety gates trivially pass.
      Both attempts ledgered in data/ai_costs/usage.jsonl lane=earnings_event_compiler.
  - path: engine/company_intelligence/e3_shadow_compiler.py
    what: >
      NEW. Shadow eval pipeline — verify_fixture_shas(), stable_segment_id(),
      _attempt_qwen(), _attempt_comparator(), score_attempt(), ledger_attempt(),
      run_e3a_eval(). Does not write event_workspace.v1 or R2.
  - path: tests/test_company_intelligence_event_compiler_e3a.py
    what: >
      NEW. 37 tests — fixture SHA pins, gold structural integrity, taxonomy version/hash,
      span byte ranges, respondent span indexes, compiler unit tests (sha check, segmenter,
      scorer). All pass.
  - path: agentos/workstreams/WS-EARNINGS-EVENT-INTELLIGENCE-COMPILER.md
    what: E3-A wave status updated to in_progress; artifacts and next_action recorded.
  - path: data/ai_costs/usage.jsonl
    what: 2 rows added (Qwen + Anthropic comparator), lane=earnings_event_compiler, cost=$0.
decisions: []
prs: []
verified:
  - claim: Exhibit 99.1 SHA matches frozen spec 070abd6a9cdb7070e546d24ffcbc41c65450d939c6f88f189cb18ec711cf5fdb
    command: sha256sum tests/fixtures/company_intelligence/aapl_fy2026_q3_ex99_1.htm
    result: "070abd6a9cdb7070e546d24ffcbc41c65450d939c6f88f189cb18ec711cf5fdb"
  - claim: Transcript SHA (uncompressed) matches frozen spec a8ff5d03e875fef5604791edbf625186c447af049e6e02f55bb89c68c7cc9f9f
    command: gunzip -c tests/fixtures/company_intelligence/aapl_fy2026_q3.json.gz | sha256sum
    result: "a8ff5d03e875fef5604791edbf625186c447af049e6e02f55bb89c68c7cc9f9f"
  - claim: Taxonomy hash a928ca72ab2e91bda74bd1e69021e08a5234e501f095610e623655db7e323b5e computed from sorted enum canonical JSON
    command: >
      python3 -c "import json,hashlib; m=sorted(['demand','product','pricing','costs_supply','capacity','capital_allocation','regulation','other','unavailable']); c=json.dumps({'schema':'qa_topic_taxonomy.v1','version':'qa_topic.v1','members':m},sort_keys=True,separators=(',',':')).encode(); print(hashlib.sha256(c).hexdigest())"
    result: "a928ca72ab2e91bda74bd1e69021e08a5234e501f095610e623655db7e323b5e"
  - claim: Gold SHA256 6b1100b148396db9a29974da5bc6e0cc55e5534185e50e061fe3635d429ed761
    command: sha256sum research/earnings_intelligence/e3/gold/aapl_fy2026_q3_qa_gold.json
    result: "6b1100b148396db9a29974da5bc6e0cc55e5534185e50e061fe3635d429ed761"
  - claim: 37 E3-A tests pass
    command: python3 -m pytest tests/test_company_intelligence_event_compiler_e3a.py -v
    result: 37 passed in 1.68s
  - claim: Qwen unavailable (connection refused) — ledgered with cost=0
    command: python3 -c "from engine.company_intelligence.e3_shadow_compiler import _attempt_qwen; from pathlib import Path; r=_attempt_qwen('test', Path('.')); print(r.status, r.degraded_reason)"
    result: provider_unavailable openai_compat_error
  - claim: Anthropic comparator unavailable (no API key) — ledgered with cost=0
    command: python3 -c "from engine.company_intelligence.e3_shadow_compiler import _attempt_comparator; from pathlib import Path; r=_attempt_comparator('test', Path('.')); print(r.status, r.degraded_reason)"
    result: provider_unavailable anthropic_not_configured_or_no_key
  - claim: agentos validate exits 0
    command: python3 scripts/agentos.py validate
    result: exit 0 (warnings on unrelated workstreams only)
unverified: []
unresolved:
  - Usefulness bar requires Sol authority. No numeric threshold has been set.
  - Model eval results are unavailable (both rungs unavailable). Eval metrics are all N/A except hard safety gates (trivially pass).
  - To complete a real eval: (1) run Ollama with qwen3.5:9b at localhost:11434, and/or (2) configure ANTHROPIC_API_KEY, then re-run python3 -c "from engine.company_intelligence.e3_shadow_compiler import run_e3a_eval; from pathlib import Path; run_e3a_eval(Path('.'))"
next_actions:
  - Sol reviews the frozen gold + eval receipt and either (a) grants a usefulness bar, or (b) directs environment setup for a live eval run.
  - Do NOT begin E3-B from this session. E3-B is locked.
  - If Sol grants the usefulness bar: open E3-B per E3B_AAPL_LIVE_QA_HANDOFF_2026-08-20.md.
  - The gold SHA and taxonomy hash are pinned in the test. Do not re-adjudicate unless starting fresh gold.
do_not_redo:
  - Do not re-adjudicate the 7 gold exchanges without a new taxonomy_version and gold SHA.
  - Do not set or loosen a numeric usefulness threshold without Sol authority.
  - Do not interpret "all hard gates pass" (trivially 0 candidates) as permission to unlock E3-B.
  - Do not begin E3-B, E3-C, or E3-P from this session.
  - Do not edit engine/earnings_qual.py score schema.
  - Do not write to event_workspace.v1 or R2.
danger_areas:
  - Gold SHA pinned in test (6b1100b148396db9a29974da5bc6e0cc55e5534185e50e061fe3635d429ed761). Rewriting gold requires updating GOLD_SHA256 in the test + new gold file.
  - Taxonomy hash pinned. Any enum change requires new taxonomy_version and new hash.
  - data/ai_costs/usage.jsonl has 2 new rows in the full checkout (not sparse). Sparse worktrees need "python3 scripts/worktree_sparse.py add data" before seeing the file.
  - Exchange 5 (Wamsi Mohan) has multi-speaker respondents: Tim Cook + John Ternus. Do not collapse.
---

# E3-A — AAPL Shadow Extraction Gold + Eval (RETURN TO SOL)

See frontmatter for all structured state. This section is prose context only.

## Summary

E3-A executed the leakage-free calibration sequence from `E3A_AAPL_SHADOW_EXTRACTION_HANDOFF_2026-08-20.md`. Gold was frozen before any model inference. Both model rungs (Qwen, Anthropic comparator) were unavailable in this environment. The evaluation returns to Sol with the frozen gold + written N=7 usefulness bar refusal.

## Gold: 7 exchanges

| # | Questioner | Firm | Topics |
|---|---|---|---|
| 0 | Amit Daryanani | Evercore | costs_supply |
| 1 | Michael Ng | Goldman Sachs | product, demand |
| 2 | Ben Reitzes | Melius Research | costs_supply, capacity |
| 3 | Erik Woodring | Morgan Stanley | pricing, demand |
| 4 | Aaron Rakers | Wells Fargo | demand, product |
| 5 | Wamsi Mohan | Bank of America | capital_allocation, product |
| 6 | Samik Chatterjee | JPMorgan | regulation, costs_supply |

Exchange 5 has Tim Cook (CEO) + John Ternus (CEO) as separate respondents per source.

## Eval outcome

Both model rungs unavailable. Hard safety gates trivially pass (0 candidates, 0 accepted). This is a valid §9 failure state ("Local Qwen unreachable / not served → Event unchanged"). E3-B remains locked per freeze §10.1 step 8 — no auto-unlock on qualitative judgment.
