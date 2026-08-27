# E3-C — Second-event generalization handoff

**Wave:** E3-C · **Date:** 2026-08-20 · **Amended:** 2026-08-26 · **Authority:** `E3_EVENT_INTELLIGENCE_COMPILER_FREEZE_2026-08-20.md` §11  
**Depends on:** E3-B **complete** on AAPL (non-empty accepted Q&A in Terminal) **and** a source-completeness receipt that freezes the second issuer **before** any extraction.  
**Source selection:** **GOOGL Q2 FY2026 FROZEN** by `e3c_googl_2026q2_source_completeness_receipt.json`, operation `e3c-source-census-20260826-v1`; extraction/model calls have **not** started.

Not done unless this non-AAPL golden-universe event produces **non-empty** accepted `qa_exchange.v1` objects through the **same** compiler path, published into the canonical event and consumed in product, with no AAPL-only binds.

---

## Mission

Prove the compiler is not AAPL-hard-coded. This is the first second-issuer / out-of-sample generalization test. The second event was selected by the pre-registered procedure before any extraction output or model call. The pass rule below remains frozen before the first model call. Extract, validate, and publish Q&A the same way as E3-B. Do **not** tune the compiler on GOOGL and then call that same event validation.

## Source selection — FROZEN before extraction

The fresh 2026-08-26/27 census executed the frozen order `GOOGL → CAT → BAC → SNOW` on one read-only GitHub carrier and stopped immediately because GOOGL qualified first.

Canonical receipt:

- `research/earnings_intelligence/e3/e3c_googl_2026q2_source_completeness_receipt.json`
- operation key `e3c-source-census-20260826-v1`
- GitHub run `33028067033`, job `98373967969`
- census artifact `9629162282`; artifact ZIP SHA-256 `8852da1320e36ce9644a87f39e88f2738709fd0129824ad6feea5a43dbc6b560`
- exact `census.json` SHA-256 `06c02d7eb726a08a67f4b08dce4d725669e7783494dffa11151eb021fd6df930`

Selected identity and current bytes:

- issuer `Alphabet Inc.` / company `cik:0001652044`
- canonical event `evt_cik0001652044_2026q2_results`
- canonical listing `GOOGL`; sibling security `GOOG`; both must remain one issuer / one event
- SEC accession `0001652044-26-000066`, accepted `2026-07-22T20:01:36.000Z`
- Exhibit 99.1 SHA-256 `a01f6bd87c7fa0dcb562493dda7348a1a37d017b4a4b5edb39b915b45688237e` — `byte_replayed`
- primary 8-K SHA-256 `9e881beb88f9496e316a412fdb881a22b9244fdec75131b4fb00ae11d0f9f7e4` — `byte_replayed`
- transcript `tx:GOOGL/2026Q2`, SHA-256 `a44db883463181ba73a536cb3643b81ea59a3e10c0f191859f7717538452d2a9` — `byte_replayed`
- transcript census: 90 segments and 10 source-level Operator question-intro boundaries, satisfying the pre-extraction `≥1` Q&A admission bar; this is **not** canonical extraction output
- slides `typed_absence`; consensus `typed_absence / unlicensed`; reaction `typed_absence / not_joined`
- existing rights profile `rp_public_primary_v1`; no new rights plane
- transcript `source_available_at=null`, `clock_state=unknown`; do not substitute call time or `generated_at`

The core `IssuerIdentity`/`IssuerRegistry` law already proves GOOGL class A and GOOG class C can resolve to one CIK-backed issuer while remaining distinct securities. The current `event_workspace.production_registry()` still contains only AAPL plus DHI/PHM/KBH/TOL, so Alphabet is **not yet production-registered**. That is an E3-C implementation requirement, not a reason to mint another registry: extend the existing production registry with Alphabet and ensure GOOG cannot mint a second event.

**State after this receipt:** `SOURCE_SELECTED_EXTRACTION_NOT_STARTED`. E3-C is in progress, not complete. E3-P remains locked.

## Selection procedure (completed; retained as the anti-leakage law)

Copied from the freeze so a builder cannot "prefer whoever Qwen liked":

1. Do not look at extraction output.
2. Test GOOGL current package (`evt_cik0001652044_2026q2_results`): held Exhibit 99.1 **and** held transcript, both `byte_replayed`, adequate rights, ≥1 operator-delimited Q&A exchange, real CIK `0001652044` + accession, dual-class collapse GOOG→GOOGL as **one** issuer.
3. If held → select GOOGL.
4. Else walk CAT, then BAC, then SNOW. First name whose **current** package meets the same bar wins. Complication is a bonus (CAT amendment/join, BAC bank basis, SNOW KPI/FY), not a reason to skip a missing transcript.
5. Write the completeness receipt (`release / filing / transcript / slides / consensus / reaction` × `byte_replayed | address_only | typed_absence`) into this wave's PR **before** extraction.
6. If none qualify → **stop**. Acquire a package. Do not use synthetic golden-corpus bodies as production sources.

The completed census obeyed this order and stopped after step 3. CAT, BAC and SNOW were not inspected after GOOGL qualified.

### Census at freeze time (historical context only)

As of 2026-08-20, **no** second name held an E2-quality current package locally. That freeze-time state has now been superseded by the fresh receipt above: GOOGL Q2 FY2026 is held and selected. The old GOOGL CI v1 HTTP 200 remains identity/context evidence only and was not used as the compiler package.

## Pass rule (frozen before the first E3-C model call)

No E3-C extraction/model call has occurred as of the source receipt. This rule therefore remains genuinely pre-registered.

Admission already requires a source package containing real Q&A. Therefore completion cannot be an “honest typed failure.”

Pass requires **all** of:

1. Completeness receipt predates the first model call and shows ≥1 real source-supported Q&A exchange.
2. Same compiler as AAPL (no issuer-special extraction or validation forks).
3. **Non-empty** accepted `qa_exchange.v1` on GOOGL.
4. Those objects published into canonical `event_workspace.v1` and consumed by a real product surface.
5. Hard safety gates: accepted unsupported = 0, cross-event = 0, span replay 100% of accepted.

A failed GOOGL generalization remains **blocked/in-progress**. Honest empty/unavailable is a receipt, not wave completion. Do not switch to CAT/BAC/SNOW to rescue a bad compiler result after GOOGL has been frozen.

## Architectural complication

GOOGL is selected, so E3-C must exercise the dual-class complication AAPL does not:

- `GOOGL` class A is the canonical listing for this receipt.
- `GOOG` class C is a sibling security of the same CIK-backed issuer.
- both listings must resolve to one `company_id` and one canonical `evt_cik0001652044_2026q2_results`.
- the current production workspace registry must be extended through its existing identity plane; no second issuer registry and no GOOG duplicate event are allowed.

The unselected alternatives and their complications remain historical procedure only: CAT amendment/join, BAC bank basis, SNOW non-standard FY/growth KPI.

## Same compiler, no forks

- Same segmenter, candidate schema, validator, telemetry lane `earnings_event_compiler`.
- No `if ticker == "AAPL"` or `if ticker == "GOOGL"` in extraction or validation. Flagship constants in `event_workspace.py` (`AAPL_CIK`, `FLAGSHIP_EVENT_ID`, …) must not be the Q&A path.
- FIF collision unchanged: no beat/miss, no licensed consensus fake, no second metric registry. FIF-7 still owns earnings/non-GAAP/KPI/guidance convergence.
- Dual-class: listing-key events are one issuer (`DEC` / E0 freeze). GOOG must not create canonical event #2.
- No durable candidate store. No `candidate_id` on canonical provenance.
- `exchange_id` remains document-revision scoped.
- Do not change transcript source-clock semantics: unknown native availability stays null/unknown.

## Not done unless

- The frozen completeness receipt predates the first extraction log.
- Pass rule above remains in git **before** the first model call.
- Selected `event_id` is canonical `evt_cik0001652044_2026q2_results`, not a ticker key.
- Validator rejects at least one planted cross-event AAPL span if the test suite includes that poison (required).
- Non-empty accepted Q&A is published and consumed for GOOGL.
- GOOG cannot resolve to a second canonical event.
- AAPL generation remains independently valid (no clobber).

## Out of scope

Natural-cycle third event (E3-P). Deflection method. FIF-7. Corpus backfill of the whole golden universe. Tuning the compiler on the E3-C event. Any extraction/model call in the source-selection carrier.
