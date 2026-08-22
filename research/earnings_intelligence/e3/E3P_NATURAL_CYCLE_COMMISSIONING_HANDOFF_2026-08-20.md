# E3-P — Natural-cycle commissioning handoff

**Wave:** E3-P · **Date:** 2026-08-20 · **Amended:** 2026-08-21 · **Authority:** `E3_EVENT_INTELLIGENCE_COMPILER_FREEZE_2026-08-20.md`  
**Depends on:** E3-C **complete** (non-empty second-issuer Q&A in product).  
**This is what makes E3 done.** Do not start from E3-0.

Not done unless a later eligible earnings event — not the E3-A gold event and not the E3-C second issuer — traverses the unattended production path and produces **at least one** accepted exchange that reaches a real product consumer.

---

## Mission

Commission the compiler on a natural subsequent print. No AAPL special cases, no second-issuer special cases, no manual gold re-adjudication as a substitute for the pipeline.

## Eligible event

- A real issuer with real CIK/accession.
- Held release + held transcript, `byte_replayed`, rights that allow the intended projection.
- Source-supported Q&A (≥1 operator-delimited exchange).
- Not `evt_cik0000320193_2026q3_results`.
- Not the E3-C frozen `event_id`.
- Prefer the next print from an already-admitted issuer if one exists; otherwise any issuer that meets the source bar. Do not choose by model quality.

Record the completeness receipt before extraction, same axes as E3-C.

## Production path to prove

1. Sources land (existing collectors / bind — do not invent a second publisher).
2. Workspace generation writes `event_workspace.v1` with identity/facts as E2 does.
3. Compiler runs Q&A family off the render path, unattended.
4. Validator admits or rejects.
5. At least one accepted `qa_exchange.v1` is published into the canonical event.
6. Terminal + Macro see the new generation. Covered event never falls to CI v1 overlay because the model failed.
7. `ai_costs` lane `earnings_event_compiler` has the run (including local-Qwen zero-cost rows).

## Resilience receipts (valid, not completion)

Local Qwen down, invalid JSON, unknown clocks, rights block, empty Q&A, cloud budget exhaust — **if** they are explicit and the event object survives — are valid **resilience proofs**. They do **not** make the E3 arc `done`. Silent paid fallback fails commissioning.

If a natural run fails honestly, record the receipt and **wait for the next eligible natural event**. Status remains `BUILT_NOT_PROVEN`.

## E3 done means

- E3-A gold + leakage-free eval exist (and usefulness gate frozen beforehand or Sol-granted).
- E3-B AAPL live **non-empty** Q&A consumed in Terminal.
- E3-C second issuer **non-empty** Q&A consumed in product.
- E3-P natural-cycle receipt exists for an eligible print with source-supported Q&A that produced **≥1 accepted exchange** automatically and reached a real consumer (run id, generation_id, source SHAs, accepted/rejected counts, cost ledger rows).
- No Prophet authority, no beat/miss, no FIF fork, no `earnings_qual` score as event truth.

## Out of scope

E4+ (commitments lifecycle, reaction geometry, longitudinal). FIF-7. Universe backfill. Deflection method (`DNR:KILL-LLM-FRAME-TAGS` still binds). Declaring the arc done from a Qwen-outage or empty-Q&A survival test.
