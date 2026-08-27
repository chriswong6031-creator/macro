---
workstream: "WS:GMI-THEME-GRAPH"
session: sol/gmi-d2c-pit-vintage-commission-20260827
model: sol
ended_because: complete
mission: >
  Commission D2C to make the remaining current-snapshot theme-membership planes
  forward-replayable with truthful PIT vintages, without reconstructing knowledge
  that was not observed or creating another graph/history store.
state_before: >
  W3A provides append-only bitemporal graph edges and Finviz vintage handling, but
  the accepted D2 census still classifies crosswalk/THS graph grain as current-
  snapshot-only for the required historical question. D2C was never implemented.
changed:
  - path: agentos/handoffs/GMI-THEME-GRAPH-2026-08-27-d2c-pit-vintage-commission.md
    what: "Frozen the D2C operator mission, method, proof and stop boundary."
verified:
  - claim: "D2C is a missing D2 gate rather than a completed implementation."
    command: "GitHub D2C PR census + V4 D2 handoff"
    result: "PASS."
  - claim: "Existing graph semantics are append-only/bitemporal and must be extended, not replaced."
    command: "contracts/theme_graph/README.md + engine/theme_graph/store.py"
    result: "PASS."
unverified:
  - claim: "D2C and D2D can write concurrently without collisions."
    what_would_verify: "Claim-time exact changed-path census."
unresolved:
  - "No worker/runtime has claimed this operation."
next_actions:
  - "Claim operation gmi-theme-pit-d2c-20260827-sol-001 through a lawful route/known receiver."
  - "Refresh protected Skillpack, main, D2D carrier state and current source receipts before the first write."
do_not_redo:
  - "No new graph/history database and no rewritten historical edge rows."
  - "No backfilled discovery date inferred from present membership."
  - "No ThemeState, ontology mapping, user surface or Prophet work."
danger_areas:
  - "Using seed constants or scrape file dates as if they were true membership-observation dates."
  - "Treating current crosswalk/THS membership as knowable before first lawful observed vintage."
---

# D2C — PIT Vintage Completion · principal-builder commission

**Operation key:** `gmi-theme-pit-d2c-20260827-sol-001`  
**State at mint:** `UNCLAIMED / NOT_DISPATCHED`  
**Repository:** `mastermindx-market-intelligence/macro`  
**Authority:** `WS:GMI-THEME-GRAPH`

## Observable mission

After D2C, a machine asking “what local/canonical theme membership was knowable at date D?” can use the existing GMI reader and receive a correct PIT answer or a typed unavailable boundary for every in-scope W3A membership plane. A later-discovered THS/crosswalk/member relationship must never appear in an earlier as-of query.

## Why it matters

W3B ThemeState requires change-over-time measurement. Without truthful membership vintages, acceleration/broadening and replay can silently use future taxonomy knowledge. D2C converts the currently live semantic substrate into a defensible temporal substrate without fabricating pre-observation history.

## Authority / precedence

1. Current Chairman completion instruction + `DEC:GMI-THEME-GRAPH-END-TO-END-COMPLETION-OWNERSHIP-SEQUENCING`.
2. `research/theme_graph/THEME_GRAPH_END_TO_END_COMPLETION_FREEZE_2026-08-27.md`.
3. `research/prophet_v4/V4_D2_ONTOLOGY_AND_PROBATION_HANDOFF.md` gate 3 and D1 PIT census.
4. `contracts/theme_graph/README.md` append-only / latest-belief / era / date-provenance laws.
5. Current source-owner receipts and current main at claim time.

Never treat this packet as authority to weaken a newer source/right/identity law.

## Verified current state / recent implementation

- W3A #5718 created the local-theme plane and vintage semantics.
- Natural graph has current Finviz vintages (`2026-06-27`, `2026-08-15`) and THS concepts on the nightly path.
- D2 handoff says crosswalk + THS current-snapshot planes need forward-only dated vintages from the D2 observation start; no reconstruction of earlier knowledge.
- D2C has no dedicated implementation carrier at commission freeze.

## Exact scope

Expected owned changes after fresh archaeology are limited to the existing GMI temporal/materialization surfaces, for example `engine/theme_graph/**`, `scripts/build_theme_graph.py`, `data/theme_graph/**` generated artifacts/receipts, focused graph contract tests and D2 continuation records. If a required source-vintage change belongs to the Finviz/THS collector owner rather than the graph owner, stop and route that primitive to the owner; do not bypass the owner by reading raw snapshots directly into a new history plane.

## Explicit non-goals

No D2D mapping curation; no canonical-theme expansion; no sector master; no ThemeState; no exposure weight; no rank/gate/size/origination; no user surface; no Prophet selection changes; no reconstruction of unobserved history.

## Complete user / machine journey

1. Receive `as_of`/knowledge cutoff D and a local/canonical membership query.
2. Resolve current company/security identity through existing graph/Data OS seams.
3. Read the latest graph belief that was knowable by D.
4. Apply `valid_from` / `valid_to` and membership vintage semantics.
5. Return the membership plus source family, observation/vintage clock, era and date provenance.
6. If D predates the first lawful observation for a current-snapshot plane, return an explicit unavailable/not-observed boundary rather than present membership.
7. Later disappearance/reappearance creates closed/new intervals; earlier rows remain immutable.
8. Re-running the same generation without new observations produces no fabricated temporal movement.

## Data / contract / time / null / correction law

- Belief time and valid-time remain distinct.
- `seed_constant` remains a reconstruction convention, never observation proof.
- First observed membership starts no earlier than the first source/owner receipt that supports it.
- Removal is interval-censored to the first vintage observed absent unless the source supplies a stronger dated changelog.
- Reappearance opens a new interval.
- Missing source clock/receipt is `UNKNOWN`/unusable for forward state; never silently stamped with build time as source availability.
- Corrections append a new belief; they do not rewrite prior belief rows.
- Existing era labels survive and remain visible to consumers.

## Deterministic / statistical / model-generated method

Temporal derivation and materialization are deterministic. No LLM/embedding may infer dates, membership intervals, entity identity or source chronology. Statistical calculations are outside D2C.

## Failure states

Hard-red or typed refuse on duplicated/overlapping interval for one source assertion, backward first-observed movement, missing required clock, later vintage leaking into earlier replay, unregistered source family, identity ambiguity, mutation of append-only historical rows, or an unexpected competing D2C carrier.

## Ordered implementation sequence

1. Refresh Skillpack/main/open carriers and current PIT freshness matrix.
2. Enumerate exact current-snapshot membership families still failing D2 gate 3; do not rework already-correct Finviz paths without evidence.
3. Write RED replay tests proving later knowledge currently leaks or an honest unavailable boundary is missing.
4. Freeze the smallest additive temporal contract needed inside the existing graph.
5. Implement per-owner vintage ingestion/materialization using existing append-only store semantics.
6. Add hostile tests for disappearance, reappearance, missing vintage, stale source, duplicate vintage, first-observed boundary and deterministic re-run.
7. Run strict graph contract checks plus focused D2C tests and full affected graph suites.
8. Run a real current-source build, then execute at least two historical as-of queries on opposite sides of a known membership change/first-observed boundary.
9. Merge only after independent adversarial review and exact-head CI; merge remains `BUILT_NOT_PROVEN` until a natural nightly advances/holds vintages correctly.
10. Record the natural production receipt and return to Sol/D2E; do not start D2E yourself.

## Acceptance / real production proof

Required proof includes:

- RED-before-green no-lookahead fixtures;
- byte/row preservation of prior historical beliefs except lawful additive rows;
- strict graph guard green;
- a natural nightly generation on the accepted implementation showing correct vintage accrual;
- a machine-reader demonstration that a post-change member is absent before first observation and present after observation;
- a disappearance/reappearance or equivalent interval fixture;
- explicit era/date-provenance in output;
- no new store or duplicate consumer path.

## Stop condition / continuation

Stop after D2C is merged and naturally proven, update `WS:GMI-THEME-GRAPH`/D2 records on the accepted carrier, and return a handoff with exact PR/SHA/generation/queries. D2E remains held until D2D is independently accepted too. Any need to redefine ontology, rights, identity authority or source ownership returns to Sol instead of widening this wave.
