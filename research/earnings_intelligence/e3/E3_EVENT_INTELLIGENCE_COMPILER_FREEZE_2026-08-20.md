# E3 Event Intelligence Compiler Freeze

**Wave:** E3-0 · **Date:** 2026-08-20 · **Runtime mutation:** none  
**Status:** RATIFIED · ON_MAIN via #6161 squash-merge `22686d255eb047cf5bffc91a35984515acb3d466`  
**Decision:** `DEC:E3-EVENT-INTELLIGENCE-COMPILER-NOT-SCORER`  
**Workstream:** `WS:EARNINGS-EVENT-INTELLIGENCE-COMPILER`  
**Program:** `earnings-intelligence` (existing key; no second program)  
**Does not reopen:** `WS:EARNINGS-INTELLIGENCE-OS` (E0–E2 remains `done`)

This is the only architecture document for E3. The four files beside it are
implementation handoffs, not competing freezes.

Starting tree of the original freeze: Macro `origin/main`
`7a7694cc8314644d4211cf1df071580e0c5d368a`. First push reconciled onto
`5ba8447ca827c494fc497ff94de167e81aff8c13`. This amendment pass
reconciles once onto current Macro `origin/main`
`e39f6c26493e784f17a05e3322659d40d1d7fad3` (unrelated data/render churn
ignored). E2-D landing record: `#6130` →
`a42e54bc2d1e6f6bf537ec78a56dc3345d21cab7`. Terminal consumer pin for
this amendment: `origin/master` `89391806a353a7d9344a8ead090f1504d990ca30`.
`terminal/lib/eventWorkspace.ts` on that pin still uses parent
`exactKeys(WORKSPACE_KEYS)`, `qa_exchanges: unknown[]`, and
`normalizeSource` reconstructing a closed source object that strips
unknown nested fields. No architecture change is required for the pin
advance.

FIF observed state on current main: FIF-2A remains accepted (`#5983`).
FIF-2B has **landed** via `#6157` squash-merge
`56d1a36caa43ca2a8ea4570808edca75ca2fc334` (merged 2026-08-21T16:08:36Z).
Current `WS:FINANCIAL-INTELLIGENCE-FABRIC` records FIF-2B as
`ACCEPTED / FIXTURE_PROVEN / ON_MAIN` (accepted head `55663277a32c`,
merge `56d1a36caa43`, PR `#6157`; fixture-proven revision-history read;
not production-issuer coverage). FIF-7 (earnings / non-GAAP / KPI /
guidance convergence) remains `todo`. **E3 does not fork FIF-7.**

---

## 0. Cold-builder answers

A later builder may start E3-A from this table. If a row is still a
product decision, E3-0 has failed.

| Question | Frozen answer |
|---|---|
| What exact source bytes enter extraction? | The production AAPL FY2026 Q3 package already used by E2: Exhibit 99.1 SHA `070abd6a9cdb7070e546d24ffcbc41c65450d939c6f88f189cb18ec711cf5fdb` (accession `0000320193-26-000018`) and transcript document `tx:AAPL/2026Q3` uncompressed SHA `a8ff5d03e875fef5604791edbf625186c447af049e6e02f55bb89c68c7cc9f9f`. Fixtures: `tests/fixtures/company_intelligence/aapl_fy2026_q3_ex99_1.htm` and `aapl_fy2026_q3.json.gz`. Live workspace generation `f709a0a6ec514282d5769e7d`. |
| Which clocks govern them? | Native document clocks: `source_available_at` = earliest verifiable availability of **that exact revision** (SEC acceptance for a filing/release; issuer/provider transcript publication for transcript bytes). Conference/call time is event-occurrence, never transcript availability. Session phase from the listing MIC calendar, else `unknown`. Missing clocks stay `unknown`. `generated_at` is never a substitute. Published `sources[]` does **not** yet carry those clocks (see §3). |
| What may Qwen propose? | Q&A boundaries, closed topic labels, exact claim candidates, management-priority candidates, entity mentions, guidance candidates, commitment candidates. Candidates only. |
| What may Qwen never mint? | Source receipts, source timestamps, typed absences, financial arithmetic, beat/miss, `basis_match`, event identity, corrections, causal read-through, rank/size/gate/trade, Prophet authority, deflection/evasiveness/non-answer verdicts (`DNR:KILL-LLM-ORIGINATION`, `DNR:KILL-LLM-FRAME-TAGS`). |
| How does evidence become replayable? | Every accepted item names event_id, document revision SHA, ordered `source_span.v1` locators. The validator independently resolves the event, loads that revision, locates the span, and byte-replays the supporting text. Failure → reject. |
| How do rejected candidates remain rejected? | They stay in a **bounded shadow/evaluation artifact** for that run. They never enter `qa_exchanges[]`, never become `address_only`, never become paraphrase, never become typed absence, and they are **not** canonical product truth. E3-A/B mint **no** durable candidate database or R2 plane. |
| How do corrections invalidate prior extraction? | Same `event_id` + new document revision/source SHA → invalidate affected candidates → rerun only that extraction family → deterministic revalidation → new `generation_id`. Never fork a second event. |
| Where do model provenance/cost telemetry live? | Existing plane: `engine.llm_auth.make_call` → `lib.ai_costs.record_usage` (`data/ai_costs/usage.jsonl`, schema `ai_costs.usage.v1`) plus `engine.provider_health.record_attempt`. E3 must also ledger the local Qwen rung (today `_call_openai_compat` writes no `ai_costs` row). Lane tag `earnings_event_compiler`, not `earnings_qual`. |
| Why is legacy `earnings_qual` not canonical E3 truth? | It is a descriptive scorer (`sentiment`, `performance` 0–10, `tone_word`, highlights, summary, `is_context_only: true`). Parallel plane: `engine/company_intelligence/` does not import it. Head/tail truncation is scorer law, not extraction law. |
| What does `qa_exchange` minimally mean? | §7. Existing `event_workspace.v1` slot. No parallel Q&A store. Ordered `respondents[]` / `answer_turns`, canonical `speaker_unresolvable`, taxonomy version/hash, revision-scoped `exchange_id`. |
| What does E3-A measure? | §10. AAPL is **development/calibration gold**, not an OOS promotion set. Freeze the 7-exchange gold, taxonomy version/hash, scoring method, and any usefulness threshold **before** the first Qwen or stronger-model inference. Neither model may see gold labels. Hard gates: unsupported accepted = 0, cross-event contamination = 0, span replay = 100% of accepted. If N=7 cannot justify a numeric usefulness threshold, do not invent one; E3-A returns to Sol and **must not** auto-unlock E3-B. |
| What does E3-B visibly add? | A **non-empty** accepted AAPL Q&A set that passed the E3-A/Sol usefulness gate, rendered in the real Terminal workflow (plus bounded dossier questions state). Empty remains an honest **failure**, not completion. Still no evasiveness, sentiment, beat/miss, or Prophet. |
| How does E3-C prove no AAPL hard-coding? | First second-issuer / OOS generalization test. Selection procedure §11; GOOGL preferred **if held**, not currently held. Pass rule registered **before** the first E3-C model call. Completion requires non-empty accepted Q&A on the second issuer through the same compiler, published into the canonical event and consumed in product. An honest typed failure stays blocked/in-progress. |
| What natural-cycle proof makes E3 done? | E3-P: an eligible naturally arriving print with source-supported Q&A produces **at least one** accepted exchange automatically and reaches a real product consumer. Qwen-outage / invalid JSON / rights-block / empty Q&A / exhausted cloud budget are **resilience receipts only**. Honest natural failure → wait for the next eligible event; status remains `BUILT_NOT_PROVEN`. |

---

## 1. Capability delta after E2

E2 proved the canonical event and its real consumers. It did not prove a
general intelligence compiler.

| Object | E2 live state | Remaining |
|---|---|---|
| Canonical event | `evt_cik0000320193_2026q3_results` | One live v2 issuer/event |
| Generation | `f709a0a6ec514282d5769e7d` | Collapsed clocks (below) |
| Terminal E2-T1 | `#418` / `abf87195c7ea` | Do not reopen |
| Macro E2-D public glance | `#6021` / `12f087aec3c1` | Do not reopen |
| `qa_exchanges` | `[]` (hardcoded in `event_workspace_build.py`) | First E3 vertical |
| Analyst questions | typed unstructured; overlay `14` is not a count | Structured exchanges |
| Reaction | `not_joined` | Later (not E3-B) |
| Consensus | `unlicensed`; `basis_match=false` | FIF-7 + licensed provider |
| Slides | typed absent | Later |
| Public wire | typed 404 | Acquisition, not E3 |
| Filing collector join | `unjoinable_filing_identity` | Later |
| Financial facts on the workspace | Deterministic bind (revenue $109.4B, +16%, Q4 growth 9–11%) | FIF remains filing-fact authority |

This amends the E0 capability ledger assignment that parked structured Q&A
at E6. The **slot** `qa_exchanges` was already frozen on `event_workspace.v1`.
E3-B fills that slot. E6 keeps later topic clustering, deflection methods,
and peer-topic propagation.

E0/E1/E2 freeze still wins on current **truth** semantics. E3 may not
silently mutate them. Amendments in this document are named in §14.

---

## 2. Why E3 is a compiler

The next moat is not another summary or sentiment score. It is:

```
source truth
  → structured observations (model proposes candidates)
  → exact evidence (validator locates and replays bytes)
  → accepted event intelligence (extends event_workspace.v1)
  → longitudinal / cross-company reasoning later
```

Models propose. Deterministic validation admits. Accepted objects extend
the existing workspace. Rejected objects remain rejected.

E3 is **not** `earnings_qual` v3, not a second XBRL/KPI/consensus fabric,
not a new model-routing control plane, and not Prophet authority.

---

## 3. Source-clock ruling (Sol-review)

**Ruling: versioned nested source-clock contract. Parent schema stays
`event_workspace.v1`. This is not a silent additive bag extension.**

Do not implement either shape in E3-0.

### 3.1 What is true on the live object

G0 is confirmed against this tree:

- Lifecycle projection is `{state, observed_at, source_available_at}`
  (`event_workspace.py` `_lifecycle_payload`).
- Live AAPL collapses those clocks to `generated_at=2026-07-30T20:30:28Z`.
- Builder `sources[]` items carry `kind`, `document_id`, `source_sha256`,
  `receipt_state`, optional `url` / `filing_key` / `typed_absence` —
  **no native clocks**.
- `SourceDocument` already has `fetched_at`, `published_at`, `available_at`
  (`documents.py`). They are not copied onto the published workspace sources.
- `generated_at` is the builder clock. It is never a substitute for
  `source_available_at`.

### 3.2 Consumer behavior (not inferred from an open dict)

| Boundary | Extra nested keys on `sources[]` items |
|---|---|
| Macro `validate_event_workspace` | Top-level `WORKSPACE_KEYS` are exact. Nested `sources[]` items are **list-only** — extra keys **silently pass**. |
| Macro `_strip_private` | Strips unknown **top-level** keys; source items pass through. |
| Macro public glance `/api/event-workspace/{ticker}` | Emits `source_states[]` of `{kind, status}` only (`app/company_intelligence.py` `_glance_source_states`). Extra keys **do not leak** to the public wire. |
| Macro `read_event_workspace` (Brain) | Returns the workspace dict after validation — extra keys **would be visible** to authenticated Brain. |
| Terminal `normalizeEventWorkspace` | Top-level `exactKeys(WORKSPACE_KEYS)` — extra **top-level** keys hard-fail the workspace to `null`. |
| Terminal `normalizeSource` | **No** `exactKeys`. Builds a closed object and **silently strips** unknown nested fields (`terminal/lib/eventWorkspace.ts` on `origin/master` `89391806`; behavior unchanged from the original `756332fa` pin). |
| Terminal `qa_exchanges` | Array length cap only; items stored as `unknown[]`; **no presenter reads them**. Questions UI today reads `facts.questions_count`, not `qa_exchanges`. |

Nearest closed source validator (`contracts.py` `_validate_source`,
`_SOURCE_KEYS`) belongs to **`company_intelligence_context.v1`**, not
`event_workspace.v1`. Compatibility must not be inferred from that
validator, nor from Macro's nested-source silence.

### 3.3 Why "additive v1 source extension" fails the G0 test

1. Terminal would not see the clocks. Shipping them as unknown nested
   keys is a false freeze: the real E2 consumer strips them.
2. Public glance would not see them (`{kind, status}` only).
3. Brain would see unversioned extra keys on a model-facing object.
4. `lifecycle.source_available_at` currently means the collapsed
   generation clock. Putting a different meaning of `source_available_at`
   on `sources[]` without a nested schema key is a dual-clock trap.
5. G0 forbade building model-generated intelligence on that temporal
   ambiguity. Open nested dicts are not a contract.

A parent bump to `event_workspace.v2` is also refused: Terminal
`obj.schema !== EVENT_WORKSPACE_SCHEMA` would fail the live AAPL
workspace.

### 3.4 Frozen nested contract (specify now, implement later)

Name: `event_source_clock.v1`. Attach under each `sources[]` item as
`clocks`, never as a new top-level workspace key.

Required fields:

| Field | Law |
|---|---|
| `schema` | `event_source_clock.v1` |
| `source_available_at` | Earliest verifiable availability of **the exact document revision being extracted**. SEC filing/release → SEC acceptance (or equivalent native publication time). Transcript bytes → issuer/provider transcript publication/availability time. Conference/call time is an **event-occurrence clock**, never transcript-document availability. If transcript availability is unknown: `null` + explicit `clock_state=unknown`. **Never** substitute conference time or `generated_at`. Live audio, if ever admitted later, is a **separate** source object with its own availability. |
| `system_recorded_at` | Our `fetched_at` / write time |
| `revision` | `document_id` + `source_sha256` (already on the source item; clock object must repeat them) |
| `rights_profile` | Existing rights profile; unknown stays unknown |
| `session_phase` | `pre_open \| regular \| after_hours \| unknown` from `source_available_at` + listing MIC calendar. Else `unknown`. Never derived from conference time when `source_available_at` is null. |

Until this nested contract is implemented **and** Terminal
`normalizeSource` reads it:

- The compiler keeps an **internal** clock ledger from `SourceDocument`.
- Published `sources[]` does not grow silent keys.
- E3-B may not promote a `qa_exchange` whose provenance clock is
  `generated_at`. If the native clock is unknown, the exchange carries
  `source_available_at: null` and `clock_state: unknown`.
- Missing clock knowledge remains explicit. Never fabricate a timestamp
  from processing time.

G0's later `information_frontier` top-level projection is **not** this
wave. A new top-level key would break Terminal exact-keys. Frontier
derivation can read `event_source_clock.v1` later without a parent
schema bump.

---

## 4. Candidate → validator → promotion

```
held source bytes + native clocks + rights
        │
        ▼
deterministic segmenter (stable segment_id, overlap, source receipt)
        │
        ▼
model proposer (Qwen first rung)  →  candidate objects
        │
        ▼
deterministic validator (trust boundary)
        │
        ├─ reject → bounded shadow/eval/run artifact only
        └─ accept → extend event_workspace.v1 (new generation)
                    Terminal / dossier consume accepted objects
```

**One extraction contract**, not ten tab prompts. Long transcripts use
deterministic chapter/segment windows with stable segment identities,
overlap, and source receipts. Do **not** carry
`earnings_qual._bounded_transcript_text` (head 48k / tail 16k, middle
dropped) into canonical extraction.

AAPL FY2026 Q3 is small enough that the whole Q&A section (~25k
formatted chars) and even the whole transcript (~50k formatted chars)
fit in one prompt. That does not license head/tail truncation as the
method. The method must survive a longer second event.

### 4.1 Validator must independently

For every accepted model-derived observation:

1. Resolve the correct `event_id`.
2. Resolve the exact document revision (`document_id` + `source_sha256`).
3. Locate the exact source segment/span (`source_span.v1`, UTF-8 bytes).
4. Replay the supporting bytes; the span must be unique in that revision.
5. Verify rights (`rp_public_primary_v1` on the flagship; otherwise
   `blocked_rights` remains non-mintable — do not invent a registry here).
6. Validate enum/type semantics against this freeze.
7. Validate ticker/company/event identity (no GOOG/GOOGL split; ticker
   is never a durable key).
8. Reject unsupported or cross-event material.

If evidence cannot be independently reconstructed: **reject**. Do not
downgrade to `address_only`, paraphrase, or manufacture typed absence.

Typed absence remains a **deterministic** producer state (slides, wire,
consensus, empty analyst-role count). Models do not mint it.

### 4.2 Promotion

- Workspace `qa_exchanges[]` contains **accepted** objects only.
- **No new durable candidate database or R2 plane in E3-A or E3-B.**
  The full candidate/evaluation ledger is a bounded **shadow/evaluation
  artifact**, not canonical product truth. Rejected candidates may remain
  in bounded diagnostic/run artifacts. A durable candidate store later
  needs separate architecture review.
- Accepted production `qa_exchange` objects must be independently
  auditable from source spans plus extractor / provider / model /
  prompt / validator / run provenance. Do **not** put a foreign-key-like
  `candidate_id` on canonical provenance; this freeze defines no resolver
  for one.
- `authority` stays `context_only`. `prophet_flags` stay all false.
- No rank / size / gate / trade.
- Partial family success is allowed: Q&A accepted while commitments
  remain empty. A model failure must not delete or regress the E2 event
  to v1.

### 4.3 Extraction families (first live = Q&A only)

| Family | E3 live? | Notes |
|---|---|---|
| `qa_exchange.v1` | E3-B | This freeze's first vertical |
| claim / guidance / commitment candidates | E3-A may shadow; not E3-B product | Validator-ready objects, not workspace writes in B |
| deflection / evasiveness | Forbidden in E3 | Needs a later validated method |
| beat/miss / consensus | Forbidden | FIF + license |
| reaction geometry | Forbidden | `not_joined` stays honest |

---

## 5. Model-routing boundary

Local Qwen (`config/earnings_qual.yml` `openai_compat`, default
`qwen3.5:9b` at an OpenAI-compatible `/v1`) is the intended high-volume
first rung **if** it clears whatever usefulness bar was frozen
**before** E3-A inference (or a later Sol grant). A stronger model is
an independent comparator only.

### 5.1 Qwen may propose

- Q&A boundaries (question span sequence, answer span sequence)
- Topic labels from the **closed** taxonomy (§7)
- Exact claim candidates (verbatim spans, not paraphrases)
- Management-priority candidates (verbatim)
- Entity mentions (names present in source)
- Guidance candidates (verbatim numeric/range spans)
- Commitment candidates (verbatim)

### 5.2 Qwen may never mint

Source receipts, source timestamps, typed absences, financial
arithmetic, beat/miss, `basis_match`, event identity, corrections,
causal read-through, rank/size/gate/trade, Prophet authority,
deflection / evasiveness / non-answer verdicts.

A stronger model is an **independent comparator** in E3-A evaluation
only. It runs on the same held source bytes and candidate schema as
Qwen, **without gold labels**, and is scored against the frozen gold
afterward. That does not give it production authority. Neither model
may see gold labels.

### 5.3 Reusable transport (do not build a second control plane)

Reuse:

| Seam | Path |
|---|---|
| Waterfall executor | `engine.llm_auth.make_call` |
| Provider descriptors | `engine.llm_auth.build_providers` |
| Cost ledger | `lib.ai_costs.record_usage` |
| Health ledger | `engine.provider_health.record_attempt` |
| Local OpenAI-compatible POST | `engine.earnings_qual._call_openai_compat` **as HTTP only** |

Do not reuse as truth: `score_text`, `_STORE_COLUMNS`, `sentiment`,
`performance`, `confidence`, `tone_word`, `positive_highlights`,
`negative_highlights`, `tags`, `summary`, `analysis_schema_version`
(`earnings-qual/v2`), `prompt_version` (`equal-v3+…`).

Do not reuse `_bounded_transcript_text` for canonical extraction.

Lane tag: `earnings_event_compiler`. Never write E3 usage as
`earnings_qual`.

### 5.4 Fallback

No silent paid-provider fallback. Every rung, including local Qwen and
every cloud fallback, writes `provider`, `model`, `reason`, tokens, and
cost (local cost may be `0`). Config order today is
`openai_compat → deepseek → kimi → anthropic`. Codex is not an implicit
rung (`earnings_qual.py` sets `codex_provider=False` on the llm_auth
path). E3 keeps that discipline: name the rung, ledger it, stop at the
first valid JSON candidate set, and surface `provider_fallback_reason`
on the candidate batch — never on the canonical event.

Cloud budget exhausted → model enrichment unavailable. The E2 event
remains.

---

## 6. Legacy Qwen / `earnings_qual` disposition

`engine/earnings_qual.py`, `tools/earnings_worker/`,
`config/earnings_qual.yml`, the `earnings_calls/` R2 score/history
store, sentiment, performance 0–10, tone words, positive/negative
highlights, and Stage-facing score context remain a **legacy descriptive
plane**.

They stay live for Stage/chronicle consumers. E3 does not delete them.
E3 does not read them as event truth. `engine/company_intelligence/`
does not import `earnings_qual` on this tree.

Stage may keep displaying tone from that plane. That display is not
`qa_exchange` intelligence.

---

## 7. Minimum `qa_exchange.v1` for E3-B

`event_workspace.v1` already has `qa_exchanges`. Do not create a
parallel Q&A store. E2 left the list empty on purpose (analyst `role`
is `''` on the held transcript; overlay `14` is not a structured
count). E3-B fills the list with **validator-accepted** objects.

Schema name: `qa_exchange.v1`. Parent workspace schema unchanged.

| Field | Required | Law |
|---|---|---|
| `schema` | yes | `qa_exchange.v1` |
| `exchange_id` | yes | **Document-revision scoped**, not a permanent graph identity. Format: `qx_{event_id}_{document_sha256[:12]}_{ordinal:02d}`. A corrected transcript that inserts or removes an exchange mints **new** IDs on the new revision. E3 does **not** define cross-revision logical matching or supersession. Prior-revision accepted exchanges are invalidated by §8 (new `generation_id`), not rematched. |
| `event_id` | yes | Must match workspace `event_id` |
| `ordinal` | yes | 0-based order **within this document revision** |
| `document_id` | yes | Transcript document id (`tx:AAPL/2026Q3` on the flagship) |
| `document_sha256` | yes | Exact revision; also binds `exchange_id` |
| `question_spans` | yes | Ordered `source_span.v1[]`. Non-empty. |
| `answer_spans` | yes | Ordered `source_span.v1[]`. Empty **only** when the source has a question with no following management speech before the next operator intro — still a reconstructed fact, not an evasiveness verdict. |
| `questioner` | yes | `{name, affiliation, name_state, affiliation_state}`. `name` and `affiliation` are independently available. A missing affiliation **must not** erase a source-supported analyst name. Whole-identity absence uses the canonical TypedAbsence reason `speaker_unresolvable` (`documents.py` `ABSENCE_REASONS`). Do **not** mint `identity_not_in_source` — it is not a valid reason. |
| `respondents` | yes | Ordered array, one element per management **answer-turn** in source order, each `{name, role, identity_state, span_indexes}` where `span_indexes` are indexes into `answer_spans`. Preserve multiple speakers: if Tim Cook and Kevan Parekh both participate, both appear. Do **not** arbitrarily choose one executive. Same speaker may occupy more than one turn. Empty array **only** in the empty-answer case above. Identity absence on a turn uses `speaker_unresolvable`. |
| `topics` | yes | 1–3 labels from the closed taxonomy at `taxonomy_version`. No open strings. |
| `taxonomy_version` | yes | Closed-enum version id (E3-A mints `qa_topic.v1` when freezing gold). |
| `taxonomy_hash` | yes | SHA-256 of the canonical JSON enum membership for that version. Later enum change **requires** a new `taxonomy_version`. |
| `provenance` | yes | `extractor_id`, `provider`, `model`, `prompt_version`, `validator_id`, `run_id`, `validation_state=accepted`, clock fields per §3 (`source_available_at` or `clock_state=unknown`), `rights_profile`. **No** `candidate_id`. |
| `validation` | yes | `replayed`, `unique_span`, `event_match`, `revision_match`, `rights_ok` — all true on accepted items |

Do **not** put on this object in E3-B: evasiveness scoring, answer-quality
scoring, contradictions, peer-topic propagation, commitments lifecycle,
read-through, sentiment, trading implications.

### 7.1 Topic taxonomy version law

No closed Q&A taxonomy exists in-repo today (CI tags are a different
object). E3-0 freezes the **rule**, not a fake enum. E3-A **finalizes**
the enum while adjudicating the gold, **before any model inference**,
and stamps `taxonomy_version` + `taxonomy_hash` onto every accepted
exchange.

- Closed enum. Gold (E3-A) mints membership from the AAPL exchanges
  before Qwen runs.
- Descriptive, not verdict-bearing.
- Reserved members now: `other`, `unavailable`.
- Seed candidates for gold (may be dropped if the source does not
  support them): `demand`, `product`, `pricing`, `costs_supply`,
  `capital_allocation`, `capacity`, `geography`, `regulation`,
  `capital_structure`.
- E3-A may add a label only when a gold exchange cannot be labeled
  honestly by the seed. It may not add deflection/tone/sentiment labels.
- Any later enum change requires a new `taxonomy_version` (and a new
  hash). Existing accepted objects keep the version they were minted
  under. `topics: [...]` must not silently change meaning across
  generations.

### 7.2 AAPL source structure (gold unit)

Deterministic census of the production transcript fixture (108
segments): roles `IR 10 / CEO 42 / CFO 23 / Operator 8 / empty 25`.

- Operator-intro method ("go ahead"): **7** primary exchanges, ±0.
- Finer role-transition method: **~24** sub-turns, ±2–3.
- Recommended gold unit: the 7 operator-delimited exchanges, each with
  ordered sub-turn spans **and ordered `respondents[]`**. Do not claim 14.
  Do not collapse Cook + Parekh into one respondent.
- Offsets: existing `source_span.v1` `segment_index` + UTF-8
  `start_byte`/`end_byte` already replay (`claim_revenue_lede` segment 2
  bytes 110–143 = `$109.4 billion in revenue, up 16%`).
- Whole Q&A ≈ 25k formatted chars; whole transcript ≈ 50k. Both fit a
  modern context window. Segment windows remain the method.

E3-A adjudicates the 7 exchanges **before** Qwen sees them.

---

## 8. Correction law

Unchanged identity law, extended to extraction:

```
same event_id
  + new document revision / source SHA
  → invalidate affected extraction candidates
  → rerun only affected extraction family
  → deterministic revalidation
  → new workspace generation_id
```

Never fork a corrected call into a second event.
`canonical_event_id(company_id, fiscal_period, event_type)` is unchanged
(`events.py`). `generation_id` hashes workspace content including
`qa_exchanges` (`_generation_identity`).

A source correction after extraction is a first-class failure state
(§9): prior accepted exchanges whose spans no longer replay are
invalidated, not silently kept. Because `exchange_id` is
document-revision scoped, the new revision does not reuse old IDs and
does not invent a cross-revision graph match in E3.

---

## 9. Failure states

All of these must remain representable. None may delete the E2 event or
fall the consumer back to CI v1 overlay for a covered event.

| State | Workspace consequence | Model enrichment |
|---|---|---|
| Local Qwen unreachable / not served | Event unchanged | Unavailable; optional named fallback if budget remains |
| Invalid JSON | Event unchanged | Bounded retry then reject batch |
| Context/window overflow | Event unchanged | Split to segment windows; do not head/tail truncate |
| Candidate references nonexistent segment | Reject candidate | — |
| Support text not uniquely replayable | Reject candidate | — |
| Wrong event / document revision | Reject candidate | — |
| Source clock unknown | Accept only with `clock_state=unknown` | Do not stamp `generated_at` |
| Source rights prohibit projection | Do not project; `blocked_rights` still non-mintable | — |
| Model disagreement (gold vs Qwen / comparator vs Qwen) | Do not accept | Record on the bounded shadow/eval artifact |
| Provider fallback used | Event unchanged except provenance on accepted items | Explicit telemetry |
| Cloud budget exhausted | Event unchanged | Enrichment unavailable |
| Source corrected after extraction | New generation; invalidate affected | Rerun affected family |
| Partial extraction family success | Q&A may accept; other families empty | Honest |

A v2 404 without `code=event_workspace_not_covered` remains a
partial-deploy failure, not coverage absence (E2-D law). E3 must not
weaken that cutover.

---

## 10. E3-A golden evaluation design

AAPL is the E3 **development / calibration gold**, not an out-of-sample
promotion set. Create the adjudicated extraction gold from the **exact**
production source revisions in §0 **before** any Qwen or stronger-model
inference. Neither model may see gold labels.

### 10.1 Leakage-free sequence (order is the safety gate)

1. Freeze bytes (SHAs above). If fixture and R2 workspace source SHAs
   diverge, stop; do not evaluate.
2. Dual-human (or dual-session) adjudication of the 7 operator-delimited
   exchanges: question spans, answer spans, ordered `respondents[]`,
   questioner name/affiliation independently, topic labels.
3. Finalize the closed Q&A topic taxonomy from that gold. Freeze
   `taxonomy_version` + `taxonomy_hash`.
4. Freeze the gold file, the scoring method, **and** either (a) any
   numeric usefulness / precision-recall-style clearance threshold or
   (b) an explicit written refusal to set one because N=7 is too small.
   This freeze does **not** invent a theatrical 0.90 bar.
5. **Only then** run local Qwen on the held source bytes and candidate
   schema. Gold labels withheld.
6. **Independently** run one stronger-model comparator on the **same**
   held source bytes and candidate schema. Gold labels withheld.
   Evaluation only; no production authority.
7. Score both outputs against the frozen gold afterward.
8. If (b) was chosen — no numeric usefulness threshold — E3-A measures
   everything under the already-frozen **hard safety gates** and
   **returns to Sol**. It may **not** auto-unlock E3-B on a post-hoc
   qualitative judgment.
9. No threshold may be invented or loosened after results.

### 10.2 Metrics (measure all; freeze any usefulness bar before inference)

| Metric | E3-0 bar |
|---|---|
| Exchange boundary quality | Measure; any numeric bar must be frozen in step 4, else Sol |
| Source-span replay success | **100% of accepted** |
| Unsupported candidate rate | Measure on candidates; **accepted unsupported = 0** |
| Cross-event contamination | **0 accepted** |
| Topic-label agreement | Measure; any numeric bar frozen in step 4, else Sol |
| Identity/role availability | Measure vs gold; unavailable must match source, not guesses; affiliation-missing must not drop a source-supported name |
| Invalid-schema rate | **0 accepted**; candidates may retry once |
| Local-Qwen success rate | Measure |
| Bounded retry/fallback rate | Measure; every fallback ledgered |
| Latency | Measure |
| Model/provider cost | Measure via `ai_costs` |

Hard safety gates are already frozen and do not wait on N=7: accepted
unsupported = 0, cross-event = 0, span replay 100% of accepted, invalid
schema 0 accepted. Primary safety gate is **not** model confidence.
Every accepted production item must have independently replayable
evidence.

---

## 11. E3-C second-event selection law

E3 must not finish on AAPL. The issuer is **not** frozen in E3-0 because
no second golden-universe name currently holds an E2-quality current
package.

Frozen golden universe (E0): AAPL, GOOGL/GOOG (one issuer), CAT, BAC, SNOW.

### 11.1 Procedure (pre-registered; run before any E3-C extraction)

1. Do not look at any model extraction output.
2. For GOOGL current event (`evt_cik0001652044_2026q2_results` is the
   named candidate): require held Exhibit 99.1 **and** held transcript,
   both `byte_replayed`, adequate rights, useful Q&A (operator-delimited
   exchanges ≥ 1), real CIK/accession, and dual-class identity collapsing
   GOOG → GOOGL as one issuer.
3. If that package is held, select GOOGL. Dual-class is the architectural
   complication AAPL does not test.
4. Else walk CAT, then BAC, then SNOW. First name whose current package
   meets the same byte/rights/Q&A bar wins. Prefer the complication the
   name actually carries (CAT amendment/join, BAC bank basis, SNOW
   growth KPI / non-standard FY) but **never** prefer a name because
   Qwen extracted it cleanly.
5. Write a source-completeness receipt (same axes as E2:
   `release / filing / transcript / slides / consensus / reaction` with
   `byte_replayed | address_only | typed_absence`) and freeze the choice
   in the E3-C handoff **before** extraction.
6. If none qualify, E3-C is blocked on acquisition. Do not weaken the
   bar. Do not use synthetic corpus bodies as production sources.

### 11.2 Pass rule (register before the first E3-C model call)

E3-C is the first second-issuer / out-of-sample generalization test.
Register this pass rule **before** looking at any extraction on the
selected event. Do **not** tune the compiler on the selected E3-C event
and then call the same event validation.

Pass (wave complete) requires **all** of:

1. Completeness receipt predates the first model call and shows ≥1 real
   source-supported Q&A exchange (already required by admission).
2. The **same** compiler path as AAPL (no issuer-special extraction).
3. **Non-empty** accepted `qa_exchange.v1` objects on that second issuer.
4. Those objects published into the canonical `event_workspace.v1` and
   consumed by a real product surface (Terminal, plus bounded dossier
   questions state if that issuer is public).
5. Hard safety gates hold: accepted unsupported = 0, cross-event = 0,
   span replay 100% of accepted.

An honest typed failure, empty accepted set, or rights/clock block is a
valid **receipt**. It does **not** complete E3-C. Status stays
blocked/in-progress until a qualifying second issuer produces non-empty
accepted Q&A.

### 11.3 Current completeness (2026-08-20 census; re-run at E3-C start)

| Name | Current 8-K/Exhibit fixture | Current transcript fixture | Published `event_workspace.v1` | Notes |
|---|---|---|---|---|
| AAPL Q3 FY2026 | Held | Held | Yes (`f709a0a6…`) | Flagship |
| GOOGL Q2 FY2026 | **Not held** locally; EDGAR parquet cutoff 2026-07-02; CI v1 glance 200 is **not** an event_workspace | **Not held** as E2 fixture | No | Preferred **if** acquired |
| CAT / BAC Q2 FY2026 | Not held (local 8-K store ends before those prints) | Not held | No | Eligible walk order |
| SNOW | CIK 1640147 absent from local 8-K parquet | Not held | No | Eligible walk order |

GOOGL CI HTTP 200 / GOOG 404 (2026-08-16) is identity evidence, not a
held compiler package.

---

## 12. Authority matrix

| Domain | Owner | E3 may |
|---|---|---|
| Canonical event / workspace | Earnings Intelligence (`event_workspace.v1`) | Extend accepted Q&A; later accepted families |
| Filing GAAP / XBRL / packet cells | FIF | Cite; never replace |
| Consensus / basis_match / beat-miss | FIF-7 + licensed provider (neither yet) | Typed `unlicensed` / `basis_match=false` only |
| Guidance **item** on the event | Earnings (E1 already mints one) | Shadow more items; no cross-event guidance arithmetic |
| Guidance **history** / non-GAAP recon / KPI series | FIF-7 | No |
| Prophet rank/size/gate | Prophet | `prophet_flags` stay false |
| Terminal chrome / routing | Terminal | E3-B consumes `qa_exchanges`; do not reopen E2-T1 taxonomy fights |
| Public dossier glance | Macro E2-D | May show structured Q&A count once accepted; do not reopen v1 overlay |
| Stage tone / 0–10 | Legacy `earnings_qual` | Leave in place; not event truth |
| Wire excerpt archive | Earnings Wire | Not compiler truth; `generated_at` is not print time |

FIF landmine is one-way: FIF must not edit Earnings Intelligence docs.
E3 docs may cite FIF. E3 must not edit FIF owned paths.

---

## 13. Waves

| Wave | Job | Starts after | Completes only if |
|---|---|---|---|
| **E3-0** | This freeze. Docs only. | E2 done | Sol ratifies the amended freeze |
| **E3-A** | AAPL shadow extraction + gold + leakage-free eval. No production workspace write. | Sol accept of this freeze | Gold + taxonomy + scoring method frozen **before** inference; hard safety gates reported; usefulness gate frozen beforehand **or** return-to-Sol packet if N=7 cannot support a number |
| **E3-B** | AAPL live Q&A into `qa_exchanges[]` + Terminal/dossier consume accepted objects. Nested source clocks implemented enough that provenance is not `generated_at`. | E3-A clears hard gates **and** the frozen (or Sol-granted) usefulness gate | **Non-empty** accepted AAPL Q&A rendered in the real Terminal workflow. `qa_exchanges=[]` is honest failure, not completion |
| **E3-C** | Second event per §11. First OOS generalization proof. | Completeness receipt + E3-B complete on AAPL + pass rule registered | **Non-empty** accepted Q&A on the second issuer through the same compiler, published and consumed. Honest failure stays in-progress |
| **E3-P** | Natural-cycle commissioning on a later eligible event. | E3-C complete | At least one accepted exchange from an unattended production run on a naturally arriving print with source-supported Q&A, reaching a real consumer. Resilience-only receipts leave status `BUILT_NOT_PROVEN` |

Handoffs:

- `E3A_AAPL_SHADOW_EXTRACTION_HANDOFF_2026-08-20.md`
- `E3B_AAPL_LIVE_QA_HANDOFF_2026-08-20.md`
- `E3C_SECOND_EVENT_GENERALIZATION_HANDOFF_2026-08-20.md`
- `E3P_NATURAL_CYCLE_COMMISSIONING_HANDOFF_2026-08-20.md`

Do not begin E3-A from this session.

---

## 14. Amendments vs E0/E1/E2 freeze

| Topic | E0–E2 freeze | This amendment |
|---|---|---|
| `qa_exchanges` | E1 empty list; E2 may render count + open transcript; no fake exchanges | E3-B may populate with validator-accepted objects. Empty until then is honest. Fake exchanges still forbidden. E3-B **completion** requires a non-empty accepted AAPL set (source gold has seven real exchanges). |
| Q&A owner wave | Ledger row said E2/E6 | First structured vertical is E3-B. E6 keeps clustering / deflection method / peers. |
| Nested `sources[]` keys | Unspecified bag | Not a silent additive clock dump. Versioned `event_source_clock.v1` later. |
| `earnings_qual` | Parallel descriptive plane | Explicitly not canonical E3 truth |
| Event identity, correction, authority, beat/miss, FIF | Binding | Unchanged |
| Terminal E2-T1 / Macro E2-D product | Landed | Do not reopen |

Silent mutation of the accepted E2 contract is forbidden. If E3-B needs a
parent `WORKSPACE_KEYS` change, stop and escalate — that is a workspace
revision, not this freeze.

---

## 15. What E3-0 did not do

No runtime, model call, R2 mutation, workflow, UI, Terminal, Prophet,
FIF, or corpus-backfill change. No implementation of `event_source_clock.v1`
or `qa_exchange.v1` validators. No gold file. No Qwen run.

## 16. Sol review 4998678880 amendment (2026-08-21)

Thesis accepted. Freeze not yet ratified. This pass closed only the
seven requested findings. Core architecture is unchanged.

1. Transcript `source_available_at` is document-revision availability, never conference time.
2. E3-A is leakage-free calibration gold; no post-hoc threshold; no auto-unlock of E3-B if N=7 cannot support a number.
3. `qa_exchange.v1` closed: ordered `respondents[]`, canonical `speaker_unresolvable`, taxonomy version/hash, revision-scoped `exchange_id`.
4. No durable candidate store; no canonical `candidate_id`.
5. E3-B/C/P completion is non-vacuous (non-empty accepted Q&A / natural accepted exchange).
6. FIF-2B recorded as landed via `#6157` / `BUILT_NOT_ACCEPTED`; FIF-7 still owns convergence.
7. `DEC:E3-EVENT-INTELLIGENCE-COMPILER-NOT-SCORER` durable authority is `decided_by: sol`.

STOP for Sol final freeze ratification. Do not begin E3-A.
