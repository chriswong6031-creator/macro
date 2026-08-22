# E3-A — AAPL shadow extraction handoff

**Wave:** E3-A · **Date:** 2026-08-20 · **Amended:** 2026-08-21 · **Authority:** `E3_EVENT_INTELLIGENCE_COMPILER_FREEZE_2026-08-20.md`  
**E3-0 landed** (#6161 / `22686d255eb047cf5bffc91a35984515acb3d466`). E3-A may start. No production workspace write. No R2 mutation. No Terminal/UI.

Not done unless a cold builder can replay the gold and the Qwen eval from this file plus the freeze.

---

## Mission

Adjudicate an AAPL FY2026 Q3 extraction gold set from the **exact** E2 production source revisions, freeze gold + taxonomy version/hash + scoring method + any usefulness bar **before the first model inference**, then evaluate local Qwen and one stronger-model comparator independently against that gold. AAPL is **development/calibration gold**, not an OOS promotion set. Do not promote any model-derived field into `event_workspace.v1`.

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

7 operator-delimited exchanges (Operator role + "go ahead"), ±0. Annotate ordered question spans and answer spans as `source_span.v1` (`segment_index` + UTF-8 `start_byte`/`end_byte`). Sub-turns (~24) nest under those 7 as ordered `respondents[]` answer-turns. Do not use overlay `14`. Do not collapse Tim Cook and Kevan Parekh into one respondent.

Questioner names live in Operator intro text and empty-role `speaker`. Affiliation is intro text only and is **independent** of name: a missing affiliation must not erase a source-supported analyst name. Whole-identity absence uses canonical `speaker_unresolvable`. Do not mint `identity_not_in_source`.

Topic labels: closed taxonomy finalized during gold adjudication. Stamp `taxonomy_version` + `taxonomy_hash`. Reserved: `other`, `unavailable`. No deflection/tone labels. Any later enum change needs a new taxonomy version.

## Leakage-free sequence (order is load-bearing)

1. Re-hash the two source fixtures; confirm live workspace source SHAs.
2. Deterministic segmenter: stable `segment_id` = `(document_sha256, segment_index)`. No head/tail truncation.
3. Dual adjudication of the 7 exchanges **before any model call**.
4. Finalize the closed topic enum from that gold. Freeze `taxonomy_version` + `taxonomy_hash`.
5. Freeze `research/earnings_intelligence/e3/gold/aapl_fy2026_q3_qa_gold.json` (or equivalent path in the E3-A PR), the metric/scoring method, **and** either a numeric usefulness threshold **or** an explicit written refusal because N=7 is too small. **Do not invent a theatrical 0.90 bar.**
6. **Only then** run local Qwen via existing OpenAI-compatible transport (`engine.earnings_qual._call_openai_compat` HTTP only, or `engine.llm_auth.make_call` if that rung is wired). Prompt consumes **segment windows**, not `earnings_qual._bounded_transcript_text`. Gold labels withheld.
7. Independently run one stronger-model comparator on the **same held source bytes and candidate schema**. Gold labels withheld. Evaluation only; no production authority.
8. Score both outputs against the frozen gold afterward. Measure every metric in freeze §10.2. Hard gates are already frozen: accepted unsupported = 0, cross-event = 0, span replay 100% of accepted, invalid schema 0 accepted.
9. If no numeric usefulness threshold was frozen in step 5, **STOP for Sol** with the measured packet. Do **not** auto-unlock E3-B on a post-hoc qualitative judgment.
10. No threshold may be invented or loosened after results.
11. Ledger every rung through `lib.ai_costs.record_usage` with lane `earnings_event_compiler`, including local Qwen (cost may be 0). No silent fallback.

## Candidate / eval artifacts

The full candidate/evaluation ledger is a **bounded shadow/evaluation artifact**, not canonical product truth and **not** a new R2/DB plane. Rejected candidates may remain in bounded diagnostic/run artifacts. Do not mint `candidate_id` as a foreign key on any object that would later be promoted.

## Clocks in shadow

Read `SourceDocument.available_at` / `published_at` / `fetched_at`. Transcript `source_available_at` is issuer/provider **transcript publication/availability**, never conference/call time. If unknown: `null` + `clock_state=unknown`. Do not stamp `generated_at`. Do not publish `event_source_clock.v1` in this wave (freeze §3). Candidates must still carry internal clock fields or explicit `unknown`.

## Owned files (expected)

- `research/earnings_intelligence/e3/gold/*` (gold + eval receipts)
- Shadow compiler module under `engine/company_intelligence/` **only if** tests require it; default is research/eval code that does not write R2
- Tests under `tests/test_company_intelligence_event_compiler_e3a.py` (name may vary; must pin SHAs)

Do not edit `engine/earnings_qual.py` score schema. Do not edit FIF. Do not edit Terminal. Do not reopen E2-D JS.

## Not done unless

- Gold file hashes the production SHAs above and is frozen, with taxonomy version/hash and scoring method, **before** the first Qwen or comparator log line.
- Neither model saw gold labels.
- Eval packet reports all §10.2 metrics with commands.
- Zero accepted items lack unique byte replay.
- No `event_workspace.v1` generation advances.
- Stronger-model comparator is named, cost-ledgered, independent, and explicitly non-authoritative.
- If no numeric usefulness bar was frozen: a Sol-return packet exists and E3-B is **not** auto-unlocked.

## Out of scope

E3-B live writes, E3-C issuer choice, evasiveness, beat/miss, slides, reaction, consensus, durable candidate store.
