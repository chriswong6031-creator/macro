# Calcbench parity — Wave 3A bitemporal query foundation

**Canonical Wave 3A build docket**

**Date:** 2026-08-02

**Status:** receipt-acceptance baseline complete; release state is external to
this memo and this is not a full-parity claim

## Verdict

Wave 2 proved that SEC filing evidence can be acquired, normalized, diffed, stored,
and served privately at low storage cost. Wave 3 must solve the harder problem:
making every numeric answer reproducible under an explicit historical knowledge
state.

The core product is therefore not a larger browser state file. It is a separate,
bitemporal query plane whose result cells retain source, period, mapping,
derivation, revision, and publication lineage.

## Non-negotiable distinction

The existing broad EDGAR panels are useful cross-sectional accelerators. They are
not the authority for as-reported or point-in-time answers because they collapse
filing vintages and do not retain accession-coherent fact/context lineage.

| Surface | Allowed use | Prohibited claim |
|---|---|---|
| Broad modeled panel | discovery, current screens, coverage triage | original filing or true PIT |
| SEC Company Facts snapshot | raw occurrence intake and mapping candidate source | historical snapshot before it was retained |
| Filing/Submissions archive | source identity, accession, acceptance time, documents | normalized metric without a governed mapping receipt |
| Bitemporal query snapshot | original/latest/as-of answer with receipt | trade score or hidden authority |

Company Facts is a real-time, mutable SEC endpoint. A snapshot acquired today may
contain facts filed years ago, but it was not knowable to MastermindX until today.
The collector must preserve that distinction and must never backdate the retained
snapshot using a caller-supplied cutoff.

## Required clocks

Every retained or materialized observation carries the clocks that actually
exist for that artifact:

1. `accepted_at` — when EDGAR made the filing knowable;
2. `recorded_at` — when MastermindX retained the source;
3. `mapping_available_at` — when the mapping rule became available;
4. `computed_at` — when a derivation completed; and
5. `published_at` — when the result became visible to a consumer.

Source-event replay gates on SEC availability. A materialized actual-system
artifact gates on all five clocks. Wave 3A's formula cells are instead an explicit
`on_demand_cutoff_projection`: they gate retained source, filing-metadata, and
governance availability at both requested cutoffs, embed their dependency
receipts, and leave formula-level `computed_at` and `published_at` empty rather
than inventing a historical artifact. Wave 3B must add those two clocks when it
persists a query snapshot or export. Running a 2022 filing through a rule written
in 2026 is a current-rule recomputation, not a 2022 system replay.

## Wave 3A query policies

| Control | Wave 3A values | Contract |
|---|---|---|
| source selection | `as_reported`, `latest_known_as_of`, `latest_restated` | original, newest eligible, and explicitly typed reported revision are distinct |
| source cutoff | required `source_snapshot_at` | gates SEC acceptance/source-lineage visibility |
| system cutoff | required `recorded_at` | gates retained source, filing metadata, and governance visibility |
| normalized metric | governed direct mapping or formula | no issuer-extension or heuristic fallback |
| period request | typed instant or duration, with typed quarter/YTD/annual/Q4/TTM inputs | no silent approximation |

Separate raw-ledger APIs retain `source_original`, `first_system_known`, and
latest/as-of replay semantics. Representation switching, calendarization, split
adjustment, and FX adjustment remain later Wave 3 capabilities; Wave 3A does not
claim them as public query-engine controls.

An unavailable input returns `not_available`. An ambiguous, incompatible, or
unsafe derivation returns `not_evaluable`. Neither state may be coerced to zero.

## Wave 3A implemented acceptance foundation

### A. Bounded Company Facts source lane

- explicit governed ticker/CIK targets and acquisition clocks;
- SEC identity, pacing, streamed byte limits, and run caps;
- collision-free owned storage paths;
- byte-faithful response archive plus separate canonical logical hash;
- append-only capture, issuer, and run receipts;
- caller timestamps are admission-time lower bounds only; public `recorded_at`
  cannot precede the durable raw-source retention boundary;
- admitted bytes remain charged after rare post-write/readback failures whenever
  an exact durable object can still be proven;
- latest pointer promotion only after manifest/readback verification;
- every fact occurrence preserved without latest-period collapse;
- no claim that a current endpoint snapshot is a historical PIT snapshot.

Cross-process SEC throttling remains an operator-level host constraint and must be
coordinated when the lane is added to scheduled production.

### B. Raw fact and revision ledger

- immutable source, context, unit, dimension, decimals, value, and occurrence IDs;
- append-only amendment/recast/correction/reclassification/withdrawal events;
- source-original and first-system-known semantics kept separate;
- precision-aware duplicate arbitration; conflicts fail closed;
- bounded lexical, unit, dimension, typed-member, and revision-evidence inputs;
- iterative graph validation and indexed, linear selection/arbitration paths at
  admitted high cardinality;
- appending a future-hidden root or revision cannot change an earlier system
  replay's value, state, reason, identifiers, receipt, or hash;
- deterministic IDs across process hash seeds;
- numeric values reject binary floats and require units.

### C. Typed period kernel

- instant, duration, quarter, YTD, annual, direct Q4, derived Q4, TTM, stub,
  and 53-week types;
- derived Q4 only from compatible annual and nine-month YTD observations;
- TTM only from four adjacent compatible discrete quarters;
- date geometry reconciled to declared week counts;
- direct and derived inputs require an explicit shared revision basis;
- derived artifacts obey compute/publication cutoffs during system replay;
- every result retains dependency lineage.

### D. Governed 50-metric registry

- exactly 50 v1 core metrics: 40 direct mappings and 10 formulas;
- statement, working-capital, cash/debt, SBC, R&D, capex, and share coverage;
- A–D confidence, unit/period/dimension/presentation constraints;
- governed standard-concept allowlist with taxonomy-year applicability;
- immutable content digests and rule availability clocks;
- query-time registry receipts project only the contracts, mappings, aliases,
  formulas, and content digests visible at the requested `recorded_at` system
  cutoff, so a future pack extension cannot mutate an earlier receipt or query
  hash;
- restricted formula AST with dependency equality and acyclic DAG validation;
- formula availability cannot predate any dependency;
- mapping/formula confidence divergence fails closed;
- issuer extensions remain raw/review-only until separately approved.

### E. Verified source-to-query bridge

- verified Company Facts manifests are re-bound to their exact logical payload and
  occurrence inventory before conversion;
- current and declared historical Submissions files supply accession acceptance
  clocks without inventing timestamps for failed joins, while a mandatory retained
  bundle clock prevents those joins from being backdated into system replay;
- fact-level amendments, recasts, and restatements require explicit evidence and
  preserve append-only parent lineage; evidence has its own availability clock;
- every raw occurrence remains distinct, including byte-identical duplicate rows;
- Company Facts dimensional scope is explicitly **unknown**, not known-empty. Its
  occurrences remain raw/review candidates and cannot satisfy a consolidated-only
  normalized metric until an exact filing context supplies dimensional evidence;
- `as_reported`, `latest_known_as_of`, and explicitly typed `latest_restated`
  queries require both source and system cutoffs;
- filing metadata is frozen and bound to the exact source accession, document,
  body digest, availability clock, and recomputed metadata content digest;
  absent metadata and cutoff-hidden metadata are receipt-identical;
- a receipt carries one cutoff-projected `GovernanceBundle` and a flat,
  deduplicated, bounded `CellNode` DAG; recursive dependency-cell serialization
  is not an accepted format;
- direct value cells expose the selected immutable raw occurrence with exact
  source, mapping rule, period, unit, clock, and confidence evidence; formula
  cells recompute from their referenced flat dependency nodes without inventing
  formula-level compute or publication clocks;
- structural non-value cells have finite branch shapes and cannot introduce raw
  or formula evidence; accepted receipt validation reconstructs the applicable
  governance, formula, direct-fact, or non-value contract;
- JSON is the authoritative matrix receipt sidecar. CSV is a deterministic
  projection that points to that JSON evidence rather than a competing receipt
  representation;
- public provenance kinds distinguish direct-source, formula, and
  opaque-governance outcomes; structural no-results retain their bounded direct
  evidence, while matrix construction revalidates every cell against the
  projected registry receipt;
- synchronous evaluation enforces aggregate per-cell visible-history and public
  receipt bounds across all governed aliases, including hostile iterables;
- bounded cross-company matrices export deterministic JSON and CSV with a stable
  query hash;
- value, missing, and not-evaluable states are distinct and never collapse to zero.

### Wave 3A proof scope

An accepted receipt proves **selected-occurrence consistency**: the returned
direct value and its selected raw fact agree on identity, entity, concept, unit,
period, mapping, policy, source lineage, and cutoff-visible clocks. It does not
prove that no eligible fact was omitted or that the selected fact was globally
optimal. Those absence and selection-optimality claims require the external
immutable ledger; a durable `ffqs_*` query snapshot is the planned standalone
evidence layer in Wave 3B.

### Acceptance state

The active worktree is
`/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/calcbench-wave3a-acceptance-20260801`
on branch `codex/calcbench-wave3a-acceptance-20260801`. Focused registry + query
acceptance passed 93 tests and the nine-file integration suite passed 303 tests.
Two independent receipt/DAG reviews reported no open P0/P1 correctness issue
within the declared proof scope; `py_compile` and `git diff --check` also passed.
These are acceptance evidence, not standalone deployment evidence.

## Wave 3B next build

Wave 3A is substrate. The next shippable user capability is the durable/private
serving plane and peer workbench around the now-tested query kernel:

1. persist conversion receipts and compile immutable Parquet query snapshots;
2. connect the collector to scheduled bounded Company Facts/Submissions acquisition;
3. join exact filing contexts/taxonomy versions so dimension-attested facts, rather
   than context-poor Company Facts rows, can satisfy normalized metric contracts;
4. expose an authenticated query/trace API with keyset pagination;
5. add selected-peer grids and a revision timeline to the premium workbench;
6. retain the 50-company × 50-metric synchronous ceiling and tenant quotas;
7. add bounded Parquet and XLSX exports using the identical query receipt;
8. keep large history/export jobs in a durable worker lane;
9. expand the governed catalog from 50 toward the Wave 3 target of 150–300 metrics;
10. freeze and score the 200-issuer mapping gold corpus;
11. project only a bounded descriptive summary to Neural Web and Prophet.

The existing `/api/forensics/state` remains the thin Filing Change Radar payload.
It must not become a full-universe query database.

## Storage and compute shape

Measured Wave 2 production bootstrap:

- 12 issuers;
- 48 retained filings;
- 128,015,069 uncompressed SEC bytes;
- 241 private source files;
- 8,491,656 stored snapshot bytes;
- 24 of 24 annual/quarterly comparison tracks ready.

Planning ranges for ten years of periodic filings:

| Scope | Raw source | Raw facts and lineage | Query projection |
|---|---:|---:|---:|
| 200-issuer gold corpus | 10–30 GB | 20–80 GB | 1–5 GB |
| 1,500-issuer launch | 75–250 GB | 150–600 GB | 8–40 GB |
| 10,000-issuer long run | 0.5–2 TB | 1–4 TB | 60–250 GB |

Object storage is not the moat or the cost center. The difficult work is
normalization, rule reprocessing, revision semantics, query latency, and QA.

## Acceptance gates

Wave 3 cannot exit on screenshots.

1. Freeze a 200-issuer accession/package-checksum gold corpus.
2. Reach at least 99% agreement on eligible blinded A–C mapping observations.
3. Ambiguous mappings return review/no-result.
4. Prove no future source leakage in source-event replay.
5. Prove no future retention, mapping, compute, publication, identifier, reason, or
   governance-receipt leakage in system replay.
6. Pin amendments, recasts, withdrawals, duplicate conflicts, and mapping recomputes.
7. Pin stub, 52/53-week, Q4, YTD, TTM, split, FX, unit, sign, and dimension cases.
8. Match filed statement labels, order, values, and dimensions against SEC source.
9. Make peer cohort membership reproducible at its receipt timestamp.
10. Keep cursor pages stable inside a pinned snapshot.
11. Round-trip CSV/XLSX/Parquet exports to identical rows and receipt hashes.
12. Fail unauthorized, cross-tenant, expired-export, and direct-object access closed.
13. Verify desktop, mobile, keyboard, bilingual labels, and visible temporal policy.
14. Preserve the constitutional boundary: no score, rank, sizing, gate, or trade authority.

## Clean-room boundary

Implementation may use SEC filings, filing packages, XBRL taxonomies, SEC APIs,
and separately licensed sources. It may not use Calcbench code, proprietary
mappings, exported normalized datasets, protected API output, branding, or UI
geometry. Public product research defines capability checks only; MastermindX
rules, schemas, calculations, and workflows are independently designed and tested.

## Exit statement

Wave 3A acceptance exits when its source, temporal, period, and metric contracts
have a clean independent audit and final focused/full-suite evidence. Release
exit additionally requires the repository's rebase, PR, squash-merge, and
production-verification contract. It does **not** claim Calcbench parity. It is
the minimum trustworthy foundation on which the peer, bulk-query, API, Excel,
and specialist-data surfaces can be built without later rewriting the meaning of
every historical cell.
