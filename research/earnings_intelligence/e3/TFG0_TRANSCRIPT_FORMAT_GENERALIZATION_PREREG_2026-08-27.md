# TFG-0 — Transcript Format Generalization pre-registration

**Operation:** `tfg0-transcript-format-census-20260827-v1`  
**Authority:** Chairman continuation + Sol E3-C REVIEW_RETURN ruling  
**Base:** Macro `main` `5d07658b899d2d3457dfeeccbc0a91c280f5bc1f`  
**State:** PRE-REGISTERED BEFORE NEW TRANSCRIPT-BODY INSPECTION  
**Runtime mutation:** none

## Outcome

Turn the GOOGL E3-C source-format falsifier into a principled, vendor-neutral transcript-structure method without fitting the repaired method to GOOGL and without consuming the untouched OOS candidates needed for later clearance.

TFG-0 is research/architecture only. It does **not** change `qa_reconstruction.py`, `qa_exchange.py`, `event_workspace.v1`, source acquisition, publication, Terminal, Prophet, FIF, or E3-P. It does not make E3-C complete.

GOOGL Q2 FY2026 is now a permanent known falsifier/regression input. It may be used to confirm that a later frozen method addresses the discovered failure class, but it may never again serve as the untouched OOS proof for that repaired method.

## Anti-leakage corpus law

Before inspecting any additional transcript body in this operation:

1. Read one committed `mastermind.tx-index/v1` production index snapshot.
2. Eligible development pairs must:
   - advertise a non-empty 64-hex `body_sha256`;
   - advertise a `call_date` from `2026-05-01` through `2026-08-26` inclusive;
   - have transcript id `2026Q2` or `2026Q3`;
   - not be any excluded OOS/calibration symbol below.
3. Excluded symbols are permanently unavailable to the TFG development corpus:
   - `AAPL` — E3 calibration/proven-live oracle;
   - `GOOGL`, `GOOG` — revealed E3-C falsifier / same issuer;
   - `CAT`, `BAC`, `SNOW` — still-uninspected golden-universe candidates reserved from this development census.
4. For every eligible pair compute:

   `selection_hash = sha256("TFG0|" + pair + "|" + body_sha256)`

5. Sort ascending by `(selection_hash, pair)` and take the first **16** pairs.
6. Freeze the exact 16 pairs + advertised SHAs in a census receipt **before** opening any selected body.
7. If a selected body cannot byte-replay to its advertised SHA, record `SOURCE_REVISION_MISMATCH` for that slot. Do not replace it with the next-cleanest format. The slot remains a source failure so corpus composition cannot be optimized after inspection.
8. CAT/BAC/SNOW remain untouched even if the 16-pair corpus is structurally homogeneous.

This is a **development corpus**, not an acceptance set. All 16 selected pairs become permanently ineligible as the untouched OOS clearance event for the later repaired method.

## What may be measured after corpus freeze

Source-structural features only, before proposing a repair:

- segment count;
- exact role vocabulary and counts;
- Operator segment count;
- source-level Q&A/operator-intro candidates;
- terminal sentence/cue shapes used by Operator question intros;
- whether analyst name and affiliation are explicit in the Operator text;
- whether the subsequent speaker name confirms the parsed questioner;
- whether management/prepared speakers carry roles in segment metadata;
- whether explicit name→title evidence exists elsewhere in the same transcript body (for example an IR opening roster);
- housekeeping / IR interruption shapes;
- current deterministic compiler result and typed failure **only after** corpus identity is frozen;
- exact source-span replay needed for any proposed identity mapping.

No external biography lookup may be used to manufacture respondent roles. A role/title is source-supported only if replayable in the held transcript revision or another already-held source whose admissibility/identity is independently frozen.

## Architecture questions TFG-0 must answer

1. **Boundary invariant:** what vendor-neutral evidence identifies an analyst-question boundary without a literal `go ahead` dependency and without admitting presentation handoffs?
2. **Questioner identity:** what deterministic grammar supports common Operator intro variants while requiring source-supported name/affiliation and next-speaker consistency?
3. **Respondent identity:** can a transcript-local speaker roster provide replayable name→role/title support when segment metadata is roleless? If not, what explicit unresolved state is required without fabricating a role?
4. **Affiliation termination:** what sentence/grammar rule avoids carrying phrases such as `Your line is now open` into the affiliation without a vendor-specific phrase list becoming the primary method?
5. **Failure law:** which ambiguities must still refuse rather than be guessed?
6. **Compatibility:** how does the method preserve AAPL exact 7 exchanges / 26 management turns / 68 spans and all current cross-event/revision guards?

## Approaches to compare

### A — transcript-local evidence normalization (**preferred hypothesis; not yet accepted**)

Construct deterministic transient source evidence before exchange reconstruction:

- source-native speaker roster from explicit segment roles plus replayable transcript-local name/title declarations;
- question-boundary candidate from Operator question semantics + parsed questioner + next-speaker consistency, rather than one literal ending;
- sentence-bounded affiliation parsing;
- fail closed when the roster cannot source-support a respondent role/title required by the canonical contract.

This keeps `qa_exchange.v1` semantics strict and avoids external role inference.

### B — weaken canonical respondent role to nullable/unresolved

Potentially handles roleless vendors directly but changes the canonical contract and every consumer. This is allowed only if TFG-0 proves transcript-local evidence cannot support a useful strict contract and Sol explicitly freezes a schema/consumer migration. Never silently turn `role` into an optional string.

### C — provider/source swap

Rejected as the default method. Selecting a cleaner transcript provider after a failure would optimize source choice rather than generalize the compiler. A genuinely new provider/revision may be acquired later under its own source/rights/clock receipt, but cannot erase the GOOGL falsifier or substitute for TFG method hardening.

## Hard non-goals

- no GOOGL-specific regex, boundary index, management-name list, or ticker branch;
- no CAT/BAC/SNOW body inspection;
- no external person-title lookup to fill source gaps;
- no new transcript store, Q&A store, identity plane, publication plane, model router, or lifecycle;
- no model/LLM extraction in TFG-0;
- no beat/miss, scoring, ranking, gating, sizing, trade, or Prophet authority;
- no E3-P;
- no production registry extension until a non-empty accepted second-issuer capability is actually ready.

## TFG-0 completion

TFG-0 completes only when the deterministic development corpus is frozen and measured, the source-format failure taxonomy is recorded, one architecture is selected with explicit data/null/correction semantics, and a bounded TFG-1 implementation handoff is written.

TFG-0 completion is `SPEC_ONLY`; it does not itself improve production Q&A coverage.

The later TFG-1 implementation must be followed by a **new pre-registered untouched-OOS selection/proof operation**. Only that successor proof may unlock E3-P.
