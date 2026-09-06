# F02-X1 Official Sanctions Geography — implementation plan

**Operation:** `marketontology-f02-sanctions-geography-v1-20260904-sol-001`
**Issue:** #6821
**Capability state at start:** `NOT_BUILT`
**Required return state:** `BUILT_NOT_PROVEN / PRODUCTION_INERT` on one Draft/HOLD PR; no merge or deploy.

## Outcome

Build one deterministic, source-supported lens over the U.S. Treasury Office of Foreign Assets
Control (OFAC) Specially Designated Nationals (SDN) list. An authenticated reader can move between a
world map, a country table, and entry detail while seeing exactly which published address fields
support every geographic count. A bounded JSON artifact exposes the same projection to machines.

This is a context and research surface, not a compliance-screening product, a current-location claim,
a sanctions prediction, or trade authority.

## Frozen source and identity contract

- The sole sanctions source owner is the official OFAC Sanctions List Service (SLS).
- The current membership source is `SDN.XML`, verified against the SLS catalog's SHA-256 and byte
  count when available. The matching OFAC XSD is acquired and receipted as schema evidence.
- Official archive-catalog delta XML files supply explicit `add` / `remove` actions. The comprehensive
  current list remains membership truth; delta omission never implies removal.
- Entry identity is the numeric OFAC UID within the SDN list. Address identity is the deterministic
  hash of normalized published address fields under its entry UID. Programs and entity type are
  preserved as published.
- Only an address element's published `country` field contributes to the geographic projection.
  Nationality, citizenship, flag, birthplace, program, issuing country, and narrative text remain
  separate and never become address or current-location evidence.
- `site/world-110m.json` is the existing boundary owner. A small, audited OFAC-name to existing
  Natural-Earth-geometry-ID bridge handles source spelling differences without creating an ISO or
  country master. Missing geometry is preserved as `GEO_UNRESOLVED`; territories and `Region:` values
  are not silently rolled up to a sovereign country.
- The Natural Earth project publishes its vector/raster map data as public domain. The UI records
  both Natural Earth and OFAC provenance and warns that boundaries are schematic and may reflect
  disputed-boundary choices.

## Deterministic states and correction law

The projection uses the closed visible state vocabulary:

- entry/change: `CURRENT`, `ADDED`, `REMOVED`, `SOURCE_CORRECTED`, `IDENTITY_UNRESOLVED`;
- geography: `GEO_UNRESOLVED`;
- source: `STALE`, `UNAVAILABLE`, `PARSER_SHAPE_CHANGED`;
- query/UI: `NO_RESULTS`.

`SOURCE_CORRECTED` means the same UID's normalized source fields changed between two accepted current
snapshots. `ADDED` / `REMOVED` require an explicit official delta action. On a failed acquisition,
the builder may keep the last accepted projection only while marking it `UNAVAILABLE`; it must never
replace it with an empty success. If the same raw inputs and parser revision recur, the published
projection keeps its original acquisition receipt so the no-op build is byte-stable.

## Journey and surface composition

1. The page opens with source status, publication clock, SHA-256 receipt, coverage, and a concise
   epistemic boundary.
2. The map shows counts of distinct current SDN entries with at least one published address in each
   resolved boundary. Selecting a boundary filters the table and updates a keyboard-accessible
   detail rail.
3. The country table shows entry counts, address counts, recent official adds/removes, programs, and
   explicit unresolved coverage. Search and filters never synthesize facts; an empty filter renders
   `NO_RESULTS`.
4. Entry detail exposes UID, name, type, programs, published address text, its resolved boundary (if
   any), change state, and source evidence. It never calls the address a current location.
5. The machine consumer carries the same schema, source receipt, aggregates, entries, changes, and
   unresolved values. Hard bounds fail closed rather than truncate silently.

## Theme art directions

**Dark treatment — command center.** A deep navy/graphite field, low-luminance map, restrained red
intensity, cool instrument panels, and a precise bright selection ring. Depth comes from luminance
and restrained glow; red is used for sanctions intensity and source failure, not decoration.

**Light treatment — research workspace.** A cool paper canvas, white material panels, graphite map
ink, hairline borders, and quiet rose/coral intensity. Depth comes from edge discipline and shallow
shadow; the map remains legible without neon or dark-mode glow.

Both treatments share information architecture, ordering, spacing/type scales, semantics, filters,
focus behavior, and density. Their material depth mechanisms intentionally differ because glow that
clarifies a dark instrument surface muddies a light research canvas.

Theme-specific degraded states retain text + icon + state code: dark uses a solid high-contrast
warning rail; light uses a bordered warning sheet. Color is never the only carrier.

## Evidence matrix

The exact same source/projection identity is exercised in:

| Theme | Language | Desktop | Mobile |
|---|---|---:|---:|
| Dark | EN | 1440 px | 390 px |
| Dark | ZH | 1440 px | 390 px |
| Light | EN | 1440 px | 390 px |
| Light | ZH | 1440 px | 390 px |

Each cell must prove usable map/table/detail transitions, visible focus, no horizontal page trap,
honest unresolved/source states, and identical machine facts. Reduced-motion behavior is verified.

## Ordered implementation and proof

1. Write failing parser, receipt, URL-boundary, correction, geography, degraded-state, and byte-stable
   tests.
2. Implement one collector adapter and one pure parser/projector.
3. Write failing build/machine-contract tests, then implement the single build script.
4. Build the page presentation and one minimal shared-nav inventory link without changing global nav
   geometry or token ownership.
5. Build once from the live official source, rerun for byte stability, and inspect source health and
   unresolved coverage.
6. Run targeted tests, design-system/runtime-style/evidence ratchets, relevant CI pack validation,
   and real headless-browser proof across the 8-cell matrix.
7. Commit/push one branch, open one Draft PR, obtain independent exact-head hostile review, repair as
   needed, prove binding checks green, and park `HOLD-FOR-SOL` with no auto-merge/merge/deploy.

## Stop conditions

Stop and return `DECISION_REQUEST / OWNER_OR_PATH_BOUNDARY_REQUIRED` if another live owner appears on
the frozen paths, official source identity cannot be verified, address country cannot be kept
distinct from other geography meanings, a new database/service/scheduler or licensed boundary asset
would be required, or a material UI change would require inventing a third navigation/token system.
