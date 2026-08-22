# E3-C — Second-event generalization handoff

**Wave:** E3-C · **Date:** 2026-08-20 · **Amended:** 2026-08-21 · **Authority:** `E3_EVENT_INTELLIGENCE_COMPILER_FREEZE_2026-08-20.md` §11  
**Depends on:** E3-B **complete** on AAPL (non-empty accepted Q&A in Terminal) **and** a source-completeness receipt that freezes the second issuer **before** any extraction.  
**Do not start from E3-0. Do not freeze GOOGL in this file.**

Not done unless a non-AAPL golden-universe event produces **non-empty** accepted `qa_exchange.v1` objects through the **same** compiler path, published into the canonical event and consumed in product, with no AAPL-only binds.

---

## Mission

Prove the compiler is not AAPL-hard-coded. This is the first second-issuer / out-of-sample generalization test. Select the second event by the pre-registered procedure. Register the pass rule below **before** the first model call. Then extract, validate, and publish Q&A the same way as E3-B. Do **not** tune the compiler on the selected event and then call that same event the validation.

## Selection procedure (run first; no model calls)

Copied from the freeze so a builder cannot "prefer whoever Qwen liked":

1. Do not look at extraction output.
2. Test GOOGL current package (`evt_cik0001652044_2026q2_results`): held Exhibit 99.1 **and** held transcript, both `byte_replayed`, adequate rights, ≥1 operator-delimited Q&A exchange, real CIK `0001652044` + accession, dual-class collapse GOOG→GOOGL as **one** issuer.
3. If held → select GOOGL.
4. Else walk CAT, then BAC, then SNOW. First name whose **current** package meets the same bar wins. Complication is a bonus (CAT amendment/join, BAC bank basis, SNOW KPI/FY), not a reason to skip a missing transcript.
5. Write the completeness receipt (`release / filing / transcript / slides / consensus / reaction` × `byte_replayed | address_only | typed_absence`) into this wave's PR **before** extraction.
6. If none qualify → **stop**. Acquire a package. Do not use synthetic golden-corpus bodies as production sources.

### Census at freeze time (do not treat as a choice)

As of 2026-08-20, **no** second name holds an E2-quality current package locally. Re-run the census at E3-C start. GOOGL CI v1 HTTP 200 is not an `event_workspace.v1` package. Local EDGAR 8-K parquet ended 2026-07-02 at freeze time. Only AAPL has a published workspace generation.

## Pass rule (frozen before the first E3-C model call)

Admission already requires a source package containing real Q&A. Therefore completion cannot be an “honest typed failure.”

Pass requires **all** of:

1. Completeness receipt predates the first model call and shows ≥1 real source-supported Q&A exchange.
2. Same compiler as AAPL (no issuer-special extraction or validation forks).
3. **Non-empty** accepted `qa_exchange.v1` on that second issuer.
4. Those objects published into canonical `event_workspace.v1` and consumed by a real product surface.
5. Hard safety gates: accepted unsupported = 0, cross-event = 0, span replay 100% of accepted.

A failed second issuer remains **blocked/in-progress**. Honest empty/unavailable is a receipt, not wave completion.

## Architectural complication

Whatever name is selected must exercise one thing AAPL does not:

| If selected | Complication that must be tested |
|---|---|
| GOOGL | Dual-class identity; GOOG must not mint a second event |
| CAT | EDGAR join / amendment replay if those sources are what is held |
| BAC | Bank basis: still `basis_match=false`, still no beat/miss |
| SNOW | Non-standard FY / growth KPI mentions as claims only, not a FIF KPI store |

## Same compiler, no forks

- Same segmenter, candidate schema, validator, telemetry lane `earnings_event_compiler`.
- No `if ticker == "AAPL"` in extraction or validation. Flagship constants in `event_workspace.py` (`AAPL_CIK`, `FLAGSHIP_EVENT_ID`, …) must not be the Q&A path.
- FIF collision unchanged: no beat/miss, no licensed consensus fake, no second metric registry. FIF-7 still owns earnings/non-GAAP/KPI/guidance convergence.
- Dual-class: listing-key events are one issuer (`DEC` / E0 freeze). GOOG 404 on CI v1 must not create `evt_cik…` #2.
- No durable candidate store. No `candidate_id` on canonical provenance.
- `exchange_id` remains document-revision scoped.

## Not done unless

- Completeness receipt exists and predates the first extraction log.
- Pass rule above is written into the E3-C PR **before** the first model call.
- Selected `event_id` is canonical `evt_cik…`, not a ticker key.
- Validator rejects at least one planted cross-event AAPL span if the test suite includes that poison (required).
- Non-empty accepted Q&A is published and consumed for the second issuer.
- AAPL generation remains independently valid (no clobber).

## Out of scope

Natural-cycle third event (E3-P). Deflection method. FIF-7. Corpus backfill of the whole golden universe. Tuning the compiler on the E3-C event.
