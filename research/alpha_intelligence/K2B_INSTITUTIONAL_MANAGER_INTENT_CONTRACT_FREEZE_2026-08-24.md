# K2-B — Institutional Manager Complex + Research Intent Contract Freeze

**State:** contract/fixture packet only; no owner/runtime/product authority

**Carrier:** PR #6370

**Dependency:** accepted K1 Evidence Foundation v1

**Decision:** `DEC:K2B-CHAIRMAN-RELEASE-CONTRACT-ONLY`

## 1. Capability and hard boundary

K2-B freezes a deterministic vocabulary, validator, and in-memory compiler for
manager-complex evidence. It creates no 13F/ETF/ARK/borrow/ownership store, owner
reader, schedule, API, UI, alert, score, rank, gate, sizing rule, origination, or
`ENTRY_OPEN` path. The native owners remain unchanged:

- `engine/institutional_census/**` and the featured 13F desk;
- sponsor/ARK/ETF holdings owners;
- `engine/company_institutional_context/**` and the ownership wire;
- IBKR borrow;
- Data OS, Stock Identity, and Theme Graph;
- accepted K1 `contracts/evidence_foundation/**`.

Compilation returns `persistence: none`, `owner_payloads_copied: false`,
`master_score: null`, and five literal false authority axes. A professional
manager is an evidence-producing agent, not an oracle.

## 2. Second hostile-review repair ruling

The initial PR shape used one unrelated top-level QLedger anchor, seven-field
event mini-pointers, caller-authored residuals/results, a one-name theme
denominator, permissive campaign evidence, partial K1-like vocabularies, and an
unsafe count formula. That surface was blocked. The coherent repair replaces it
rather than layering more flags over it:

1. `evidence_refs` now contains complete K1 `EvidenceRef` objects; every event
   resolves one exact ID and repeats only equality-checked owner/native identity
   and clock bindings.
2. The source fixture contains an owner-model-derived raw 13F receipt reference
   with native digest, exact reader/pointer/clocks/rights/coverage/replay and
   all-false authority. K1 validates every reference.
3. Raw 13F receipt identity does not bind a security row. The real source-backed
   fixture therefore refuses a security claim; all numeric examples are openly
   marked synthetic positive/adverse.
4. True-S ETF residual and within-theme preference are compiler-derived. There
   is no caller result field.
5. Campaigns use only eligible, resolved, active, discretionary manager-intent
   observations already knowable at the transition time and return complete
   append-only history.
6. Coverage, rights, missingness, correction, replay, vintage, object/authority,
   independence, owner identity, and clocks come from validated K1 objects—not
   local free strings.
7. Counts distinguish vehicles, filers, resolved epochs, unresolved/excluded/
   mechanical rows, same-complex multivehicle deductions, and distinct eligible
   research complexes; deductions are nonnegative by construction.
8. Reliability is prospective Eval OS-only, exact complex epoch × closed domain
   × closed horizon × closed action, with coherent trial/maturity/scoring counts,
   shrinkage, compiler-derived ordered uncertainty, and compilation-cutoff law.
9. Complex/filer/vehicle effective/valid/knowable intervals and lineage are
   explicit. The canonical eight China actor roles extend B0 without erasing raw
   strings, ontology versions, unresolved states, or remap history.
10. The third repair makes every positive path point-in-time: future theme
    comparisons and future or unusable corrections cannot rewrite current
    receipts; epoch intervals are `[from,to)` and evaluated at the event,
    transition, trial, or maturity clock they govern.
11. Saturation is an aggregate derived receipt. The compiler derives the exact
    eligible complex population, exact excluded complement, usable present
    subset, counts, and ratio. No caller scalar or dangling complex ID survives.
12. Complex, filer, vehicle, and actor-remap lineages resolve within their exact
    registries, preserve entity/raw-history identity, and are append-only,
    chronological, acyclic, and linear.

## 3. Evidence-reference law

The full K1 object is the evidence anchor. `validate_reference` enforces owner
schema and identity grammars, pointer construction, clock bindings, coverage and
replay capability, rights/missingness consistency, append-only corrections,
object/authority class, and deterministic reference identity. K2 neither edits
nor shadows that vocabulary.

The raw 13F reference freezes:

- accession `0001398344-26-013841`;
- filer CIK `0001792167`;
- native schema `institutional_13f.raw_evidence_receipt/v1`;
- receipt ID `i13fraw_c16997a2b2d352a4b7ada643273e00ca482505cf84b1e33e3688d3b0dc6fa8d2`;
- native canonical digest `cc09d4f341c5d2fbb03ec994178f9ed38dddd4e4ee8e1bc333be9fb605917311`;
- owner parser `engine.institutional_census.models.RawEvidenceReceipt.from_json_bytes`;
- `report_period`, `accepted_at`, and `retained_at` clocks;
- source-release-snapshot coverage and permitted rights.

Operational availability is the later of acceptance and retention. The source
pointer row carries `unresolved_security_subject`: K1 raw receipt subjects are
manager CIK/accession, not holdings/security identities. A future real security
observation requires a bounded native catalog row selection that cites the exact
immutable catalog generation, raw receipt/accession, and requested security.
That adapter/read is deliberately not commissioned here.

## 4. Four-plane semantic freeze

### Manager Research Intent

Input is only a reported-share `Q_prev/Q_now` pair or typed unavailable state,
with a reconciled public-sleeve denominator. Both values are required to compute
an unscaled 13F reported delta. The plane is eligible context only when complex
and vehicle epochs are resolved, active, discretionary, and source state is
usable. It is never live flow, conviction truth, or an entry recommendation.

### Fund Flow Pressure

True-S ETF inputs are `Q_prev`, `Q_now`, `S_prev`, `S_now`; the compiler alone
computes:

`Q_now - Q_prev * (S_now / S_prev)`

A 13F has no S slot. Continuing-constituent sum/median and price-residual-weight
constructions are named proxy states with residual `null`; unavailable and
rights-blocked rows likewise cannot become intent.

### Theme Capital Rotation

Target and peer observations are distinct subjects in one exact theme epoch.
The comparison binds a K1 Theme Graph membership reference and its knowable
clock. The membership receipt's member set must equal target plus peers and be
exactly partitioned into eligible and typed exclusions. A late peer, passive or
mechanical peer marked eligible, overlap, one-name denominator, clock lookahead,
or unresolved member refuses. For valid rows the compiler returns target delta,
eligible-peer mean delta, and spread—never a score.

### Institutionalization / Saturation

This plane carries typed present complex-epoch IDs or unavailable state. The
compiler derives the PIT eligible set from resolved active discretionary complex
epochs, derives the exact typed excluded complement, admits present IDs only
from usable non-superseded cutoff-eligible observations, and computes present
count, eligible count, and ratio. `position_count` is not an input or output
semantic. It is descriptive breadth or concentration context only.

No plane is netted with another. The separately governed Conditional Fusion
exception grants K2-B no authority.

## 5. Identity and actor law

Complex, filer, and vehicle identities are immutable epochs with separate
effective, valid, and knowable intervals, status, resolution, decision mode, and
append-only lineage. Same-complex vehicles deduplicate by exact complex epoch.
Mixed and unknown are explicit modes. Unresolved epochs never count as eligible
research complexes.

Intervals use inclusive starts and exclusive ends; equal boundaries are empty
and invalid. Remap/correction predecessors resolve in the correct registry,
retain the same canonical entity, obey non-overlap or later correction-knowledge
chronology, and form one acyclic linear chain. Actor remaps are bound to their
complex-epoch lineage; raw actor strings and original ontology versions cannot
be mutated out of history.

China's roles are the exact masterplan extensions: institution/manager complex;
fund company; fund vehicle; manager/person; broker/research house; analyst;
named market actor/broker seat; holder/controller/executive. Raw actor string,
original ontology version, unresolved state, and remap lineage remain immutable.

## 6. Campaign and correction law

The closed campaign chain is
`IDLE → INITIATED → ACCUMULATING → PAUSED → CLOSED`. Every append record has a
stable transition ID, exact sequence and predecessor, complex epoch, subject,
transition time, eligible observation IDs, and correction lineage. Rights-
blocked, missing, unresolved, passive/systematic, mechanical, superseded, or
pre-knowledge observations cannot back a transition. A second campaign for the
same subject/complex begins only after the first closes. The receipt includes
every record and its current/superseded/not-yet-knowable state.

Observation corrections also append. A successor must retain subject/vehicle/
plane identity, arrive later, and resolve a full K1 correction/supersession
reference whose predecessor set contains the predecessor event's reference.
Supersession is evaluated as-of: a future, stale, missing, rights-blocked,
non-PIT, or epoch-inapplicable successor cannot erase the usable predecessor.
Campaign corrections become knowable at their own `transitioned_at`; historical
campaign epoch applicability is evaluated at the transition rather than a later
compile clock.

## 7. Count and reliability receipts

The count receipt separately reports raw vehicle/filer epochs, resolved active
complex epochs, same-complex multivehicle deductions, unresolved complexes,
excluded vehicles, mechanical vehicles, and distinct eligible research
complexes. It keeps K1's exact `source_independence`, `information_novelty`, and
`mechanism_independence` axis objects distinct, `not_assessed`, and
`declarative_unverified`; a distinct-complex count is not verified independence.

Reliability imports no legacy grades. The only domains, horizons, and actions are
closed in schema. Trials ≥ matured ≥ scored ≥ successes; eligible rows must be
fully matured/scored, while zero/immature/unscored rows are insufficient with no
posterior. The compiler applies the frozen beta-binomial normal-approximation
method/version, produces ordered 95% bounds, and rejects trial or maturity
cutoffs after compilation `as_of`.

Both reliability cutoffs must also fall inside the exact complex epoch. That
applicability is evaluated at the trial/maturity clocks, preserving a historically
valid posterior after a later epoch expiry. K1 reference freshness, missingness,
coverage, and native date/datetime grain are consumed directly and fail closed.

## 8. Evidence and remaining gap

The 50-test focused suite proves the nine reproduced second-round defects plus
the first round's identity, clock, class, passive/mechanical, denominator,
interval, lineage, campaign-chain, reliability, payload, authority, and
determinism cases. It also reproduces the third-round temporal, freshness,
saturation, actor-remap, and future-supersession attacks. The exact combined K2
and accepted K1 suites pass 175 tests, proving no K1 contract regression.

The remaining gap is deliberate: there is no rights-approved source adapter or
owner-reader result that binds a live security-level manager-intent observation.
K2-B is a contract freeze, not that adapter. K2-C or later work requires a
separate commission and exact source/rights/PIT evidence.
