# E3-P — Natural-cycle commissioning handoff

**Wave:** E3-P · **Date:** 2026-08-20 · **Authority:** `E3_EVENT_INTELLIGENCE_COMPILER_FREEZE_2026-08-20.md`  
**Depends on:** E3-C live.  
**This is what makes E3 done.** Do not start from E3-0.

Not done unless a later earnings event — not the E3-A gold event and not the E3-C second issuer — traverses the compiler on the production path.

---

## Mission

Commission the compiler on a natural subsequent print. No AAPL special cases, no second-issuer special cases, no manual gold re-adjudication as a substitute for the pipeline. The pipeline may still produce **zero** accepted exchanges if the source cannot support them; that is a pass when the failure state is explicit and the deterministic E2-style event remains.

## Eligible event

- A real issuer with real CIK/accession.
- Held release + held transcript, `byte_replayed`, rights that allow the intended projection.
- Not `evt_cik0000320193_2026q3_results`.
- Not the E3-C frozen `event_id`.
- Prefer the next print from an already-admitted issuer if one exists; otherwise any issuer that meets the source bar. Do not choose by model quality.

Record the completeness receipt before extraction, same axes as E3-C.

## Production path to prove

1. Sources land (existing collectors / bind — do not invent a second publisher).
2. Workspace generation writes `event_workspace.v1` with identity/facts as E2 does.
3. Compiler runs Q&A family off the render path.
4. Validator admits or rejects.
5. Marker advances only for accepted objects / honest empty list.
6. Terminal + Macro see the new generation. Covered event never falls to CI v1 overlay because the model failed.
7. `ai_costs` lane `earnings_event_compiler` has the run (including local-Qwen zero-cost rows).

## Failure states that still count as commissioning

Local Qwen down, invalid JSON, unknown clocks, rights block, empty Q&A, cloud budget exhaust — **if** they are explicit and the event object survives. Silent paid fallback fails commissioning.

## E3 done means

- E3-A gold + eval exist.
- E3-B AAPL live Q&A consumed.
- E3-C second event consumed.
- E3-P natural cycle receipt exists (run id, generation_id, source SHAs, accepted/rejected counts, cost ledger rows).
- No Prophet authority, no beat/miss, no FIF fork, no `earnings_qual` score as event truth.

## Out of scope

E4+ (commitments lifecycle, reaction geometry, longitudinal). FIF-7. Universe backfill. Deflection method (`DNR:KILL-LLM-FRAME-TAGS` still binds).
