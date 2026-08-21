# E3-A — AAPL shadow extraction handoff

**Wave:** E3-A · **Date:** 2026-08-20 · **Authority:** `E3_EVENT_INTELLIGENCE_COMPILER_FREEZE_2026-08-20.md`  
**Do not start until Sol accepts E3-0.** No production workspace write. No R2 mutation. No Terminal/UI.

Not done unless a cold builder can replay the gold and the Qwen eval from this file plus the freeze.

---

## Mission

Adjudicate an AAPL FY2026 Q3 extraction gold set from the **exact** E2 production source revisions, freeze it, then evaluate local Qwen (and one stronger-model reviewer, eval-only) against that gold. Do not promote any model-derived field into `event_workspace.v1`.

## Frozen source package

| Artifact | Locator | SHA-256 |
|---|---|---|
| Event | `evt_cik0000320193_2026q3_results` | — |
| Generation (live E2) | `f709a0a6ec514282d5769e7d` | workspace object `dbd50e5c30e8a031f844e02362ffd53b25e3230e75eeef19bf3825543cb81197` |
| Exhibit 99.1 | accession `0000320193-26-000018`; fixture `tests/fixtures/company_intelligence/aapl_fy2026_q3_ex99_1.htm` | `070abd6a9cdb7070e546d24ffcbc41c65450d939c6f88f189cb18ec711cf5fdb` |
| Transcript | `tx:AAPL/2026Q3`; fixture `tests/fixtures/company_intelligence/aapl_fy2026_q3.json.gz` | uncompressed `a8ff5d03e875fef5604791edbf625186c447af049e6e02f55bb89c68c7cc9f9f` |
| Filing metadata fixture | `tests/fixtures/company_intelligence/aapl_fy2026_q3_filing.json` | confirm on open |

If fixture SHAs and the live workspace `sources[].source_sha256` diverge, **stop**. Do not evaluate a different revision.

## Gold unit

7 operator-delimited exchanges (Operator role + "go ahead"), ±0. Annotate ordered question spans and answer spans as `source_span.v1` (`segment_index` + UTF-8 `start_byte`/`end_byte`). Sub-turns (~24) nest under those 7. Do not use overlay `14`.

Questioner names live in Operator intro text and empty-role `speaker`. Affiliation is intro text only. Respondents: `Tim Cook`/`CEO`, `Kevan Parekh`/`CFO` when those segments answer.

Topic labels: closed-rule taxonomy in freeze §7.1. Mint membership from these 7 exchanges. Reserved: `other`, `unavailable`. No deflection/tone labels.

## Sequence (order is load-bearing)

1. Re-hash the two source fixtures; confirm live workspace source SHAs.
2. Deterministic segmenter: stable `segment_id` = `(document_sha256, segment_index)`. No head/tail truncation.
3. Dual adjudication of the 7 exchanges **before any model call**. Freeze `research/earnings_intelligence/e3/gold/aapl_fy2026_q3_qa_gold.json` (or equivalent path in the E3-A PR).
4. Only then run local Qwen via existing OpenAI-compatible transport (`engine.earnings_qual._call_openai_compat` HTTP only, or `engine.llm_auth.make_call` if that rung is wired). Prompt consumes **segment windows**, not `earnings_qual._bounded_transcript_text`.
5. Run one stronger-model reviewer on the **same frozen gold** (evaluation only; no production authority).
6. Measure every metric in freeze §10.2. Set precision/recall-style thresholds **after** seeing gold N and disagreement. Hard gates are already frozen: accepted unsupported = 0, cross-event = 0, span replay 100% of accepted, invalid schema 0 accepted.
7. Ledger every rung through `lib.ai_costs.record_usage` with lane `earnings_event_compiler`, including local Qwen (cost may be 0). No silent fallback.
8. Write rejected candidates to an append-only ledger that is **not** the workspace.

## Clocks in shadow

Read `SourceDocument.available_at` / `published_at` / `fetched_at`. Do not stamp `generated_at`. Do not publish `event_source_clock.v1` in this wave (freeze §3). Candidates must still carry internal clock fields or explicit `unknown`.

## Owned files (expected)

- `research/earnings_intelligence/e3/gold/*` (gold + eval receipts)
- Shadow compiler module under `engine/company_intelligence/` **only if** tests require it; default is research/eval code that does not write R2
- Tests under `tests/test_company_intelligence_event_compiler_e3a.py` (name may vary; must pin SHAs)

Do not edit `engine/earnings_qual.py` score schema. Do not edit FIF. Do not edit Terminal. Do not reopen E2-D JS.

## Not done unless

- Gold file hashes the production SHAs above and is frozen before the first Qwen log line.
- Eval packet reports all §10.2 metrics with commands.
- Zero accepted items lack unique byte replay.
- No `event_workspace.v1` generation advances.
- Stronger-model reviewer is named, cost-ledgered, and explicitly non-authoritative.

## Out of scope

E3-B live writes, E3-C issuer choice, evasiveness, beat/miss, slides, reaction, consensus.
