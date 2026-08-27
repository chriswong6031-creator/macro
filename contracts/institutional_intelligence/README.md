# K2-B Institutional Intelligence contract v1

K2-B freezes a pure manager-complex and research-intent descriptor/compiler. It
is not a new institutional owner, store, reader, scheduler, API, UI, ranker,
gate, position sizer, originator, or entry system. Compilation is deterministic
and in-memory, returns `persistence: none`, copies no owner payload, emits no
master score, and materializes all five authority booleans as false.

## K1 references are the only evidence anchors

`evidence_refs` contains complete accepted K1 `EvidenceRef` objects. The public
validator runs every object through `lib.evidence_foundation.validate_reference`
and rejects unresolved IDs, duplicate IDs, owner/native-identity contradictions,
pointer or clock tampering, rights/missingness conflicts, replay/correction
violations, or authority leakage. An observation contains only a reference ID and
an exact binding back to that validated object's owner store, complete native
identity, world-valid clock, and operational-availability clock. It cannot carry
its own rights, coverage, missingness, replay, correction, source URL, owner
payload, or caller result.

Positive compilation also requires point-in-time-usable K1 coverage and a
`native_clock_bound` freshness basis whose bound native clock is knowable by the
compilation cutoff. `unknown`/`not_applicable` freshness, stale or other typed
absence, rights blockage, and non-PIT coverage fail closed into typed non-positive
states. A date-grain native clock is conservatively usable only at the following
UTC midnight; it is never silently parsed as an intraday timestamp.

The real evidence anchor is an owner-model-derived
`institutional_13f.raw_receipt` for accession `0001398344-26-013841`. Its native
identity, schema, canonical native digest, parser, pointer, report-period clock,
acceptance clock, retention clock, rights, coverage class, missingness,
correction, replay, and all-false authority envelope pass K1 unchanged. For raw
13F evidence, operational knowability is `max(accepted_at, retained_at)` and the
compiler requires the bound filer epoch to equal both the K1 subject CIK and the
native filer CIK.

That K1 raw-receipt reference does **not** bind a security or holdings row. A
source-backed pointer-only observation therefore uses
`unresolved_security_subject` and compiles to
`SOURCE_POINTER_ONLY_NO_SECURITY_BINDING`; changing it to a security ID is
refused. The numerical positive/adverse examples are explicitly labelled
`synthetic_fixture_positive` or `synthetic_fixture_adverse`. They test the
contract math without being misrepresented as owner-captured facts. A later
source-backed security observation needs a separately commissioned bounded
canonical owner-reader selection from an immutable catalog generation, with the
selected row tied to the exact raw receipt/accession and security. A pointer or a
caller assertion cannot substitute for that owner read.

## K2-C owner-row basis (v1.1.0)

The commissioned owner-reader selection above now exists
(`alpha-k2c-institutional-adapter-20260826-sol-001`). One additive basis,
`source_backed_owner_row`, represents a REAL two-period owner-read security
observation. Such an observation MUST carry `owner_row_binding` (forbidden on
every other basis): a `security` block whose canonical identity is the
owner-native CUSIP (`DEC:K2C-SECURITY-BINDING-IS-OWNER-NATIVE-CUSIP` — the Data
OS axis is carried as typed unresolved, never silently bridged), plus `previous`
and `current` period bindings, each naming a listed
`institutional_13f.catalog_generation` reference, a listed
`institutional_13f.raw_receipt` reference, and the exact selected row
(`accession`, `infotable_sk`, `row_hash`, `cusip`). The validator enforces
store/identity/clock equality against the listed K1 refs, row↔accession parity,
strictly increasing report periods, `subject_id == "cusip:<CUSIP>"`, and that
the observation's primary reference is the current-period raw receipt; the
compiler additionally gates positivity on PIT availability of all four bound
refs at the compile cutoff. `q_prev`/`q_now` under this basis must be real
numbers (typed unavailable is the lawful absence shape — a null quantity is
refused, and a missing predecessor period is `insufficient_history`, never
zero).

The producing adapter is `lib/institutional_13f_adapter.py`: a read-only,
persistence-free composition over the canonical institutional owner
(`engine/institutional_census/**`) that emits a deterministic
`institutional_intelligence.owner_read_receipt/v1` and never authors compiler
results. Its proof lane is `.github/workflows/smart-money-13f-k2c-pilot.yml`
(dispatch-only, read-only, main-gated).

## Epoch identity and China actor extensions

Manager complexes, filers, and vehicles are immutable epochs with distinct
effective, valid, and knowable intervals; active/inactive/unresolved status;
resolution state; explicit decision mode (`discretionary`, `passive`,
`systematic`, `mixed`, or `unknown`); and append-only original/remap/correction
lineage. All three intervals use inclusive starts and exclusive ends. Empty
intervals are invalid. Every remap/correction predecessor must resolve in the
correct registry, retain the canonical entity, be acyclic and linear, and obey
non-overlap or later correction-knowledge chronology. Actor remaps bind to the
manager-complex epoch lineage; dangling/self/cyclic predecessors and mutation of
the preserved raw actor string or original ontology version are refused.
Unresolved epochs cannot enter the eligible research-complex count.

The China masterplan's exact eight actor roles are additive extensions of the B0
model, not a rival ontology:

1. institution or manager complex;
2. fund company;
3. fund vehicle;
4. manager or person;
5. broker or research house;
6. analyst;
7. named market actor or broker seat;
8. holder, controller, or executive.

Identity/class is not skill. Reliability remains a separate prospective Eval OS
contract.

## Four planes stay separate

Each observation has one closed plane-specific measure and denominator. No
cross-plane netting exists.

| Plane | Closed measure | Closed denominator | Interpretation boundary |
|---|---|---|---|
| Manager Research Intent | reported `Q_prev`, `Q_now` or typed unavailable | public reported sleeve counts | only resolved active discretionary complex/vehicle context; 13F is never live flow or an oracle |
| Fund Flow Pressure | true-S ETF inputs, a named proxy, or typed unavailable | vehicle shares-outstanding state | the compiler alone derives `Q_now - Q_prev*(S_now/S_prev)`; proxies never receive a true residual or intent state |
| Theme Capital Rotation | target/peer reported share changes | PIT membership receipt | target and distinct peers must share theme epoch, be knowable by cutoff, and reconcile exactly to eligible/excluded membership |
| Institutionalization / Saturation | typed present complex IDs or unavailable | exact PIT eligible complex set plus exact excluded complement | compiler derives present/eligible counts and ratio; breadth/context only, never a crowding gate or master score |

The true-S residual is never caller supplied. A 13F manager-intent observation
has no `S` slot and only computes an unscaled reported-share delta when both
snapshots exist. Proxy/unavailable/rights-blocked/unresolved rows retain typed
non-intent states.

Within-theme preference is compiler-derived. One comparison binds a target, one
or more distinct peer subjects, an exact theme and epoch, a validated Theme
Graph K1 membership reference and clock, and a denominator receipt whose member
set is exactly partitioned into eligible and typed excluded rows. Target/peer
overlap, a one-name denominator, late peer, passive/mechanical peer marked
eligible, unresolved member, membership lookahead, or caller result fails closed.
The output is the target reported-share delta, eligible-peer mean delta, and
their spread; no score or recommendation is produced.

Saturation has no caller-authored count. The validated input can name present
complex epochs only when each one is backed by a usable, non-superseded,
cutoff-eligible saturation observation. The compiler derives the exact PIT
eligible set from resolved active discretionary complex epochs, the exact typed
excluded complement, the present subset, both counts, and the ratio. Unknown,
future, expired, passive, systematic, mixed, unresolved, missing, rights-blocked,
or superseded rows cannot inflate the numerator or denominator.

## Campaign history is append-only evidence history

Campaigns use only the linear vocabulary
`IDLE -> INITIATED -> ACCUMULATING -> PAUSED -> CLOSED`. Every transition has a
stable ID, sequence, predecessor transition, complex epoch, subject, transition
clock, eligible manager-intent observation IDs, and append-only correction
lineage. Rights-blocked, missing, unresolved, mechanical, passive/systematic,
superseded, or not-yet-knowable observations cannot back a transition. A new
campaign for the same subject and complex cannot start until the prior campaign
is closed. The compilation receipt returns the complete transition history,
including superseded and future/not-yet-knowable record states, plus current
campaign states.

Supersession is point-in-time. An observation predecessor is superseded only
after its successor reference is usable, knowable, and epoch-applicable at the
correction clock. A rights-blocked, missing, stale, or future successor cannot
erase a usable predecessor. Campaign correction availability is the correction
transition's own `transitioned_at`; a future append remains
`NOT_YET_KNOWABLE`. Historical campaign epoch applicability is evaluated at the
transition, so a later epoch expiry never rewrites valid append-only history.

## Counting and reliability

The count receipt reports raw vehicle epochs, raw filer epochs, resolved active
complex epochs, same-complex multivehicle deductions, unresolved complexes,
excluded vehicles, mechanical vehicles, and distinct eligible research
complexes. Deductions are computed as eligible vehicles minus their distinct
resolved complexes and can never be negative. Distinct complexes do not prove
independence. The exact K1 axes—`source_independence`,
`information_novelty`, and `mechanism_independence`—remain separate objects
with `state: not_assessed`, `assessment: declarative_unverified`, and an
explicit basis that the count is not independence proof.

Reliability is closed on exact complex epoch x domain x horizon x action. It is
prospective-only and Eval OS-owned, with trial/maturity/scoring cutoffs and
coherent trials/matured/scored/success counts. Zero, immature, or unscored rows
are `insufficient` with posterior and bounds `null`. Fully matured/scored rows
receive a compiler-derived beta-binomial shrunk posterior and ordered 95%
uncertainty bounds under the frozen method/version. Both cutoffs must be at or
before compilation `as_of`. Legacy `manager_quality`, `manager_trades`, and
`fund_followability` grades are neither imported nor aliased.

Trial and maturity cutoffs must each fall inside the relevant complex epoch's
effective, valid, and knowable interval. Reliability is evaluated at those trial
and maturity clocks—not at a later compilation time—so later expiry does not
erase a historically valid prospective posterior.

## Full inherited K1 vocabulary

The receipt derives and exposes the exact accepted K1 sets for coverage classes,
rights and missingness states/reasons, correction kinds/chronology, replay modes,
vintage states, independence axes/states/assessment, clock classes/grains/value
states, object classes, and authority classes/fields. K2-B's observation and
campaign correction enums are set-equal to K1's complete correction-kind set.
These are audit echoes of validated K1 objects, not caller-overridable local
vocabularies.

The hostile suite includes the nine second-review attacks—event pointer tamper,
fabricated residual, target/peer/denominator collapse, rights-blocked campaign,
pre-knowledge campaign, invented missingness, inverted uncertainty, eligible
zero-trial mismatch, and negative dedupe—as well as the first-review identity,
clock, plane, passive/mechanical, interval, correction, campaign-chain,
reliability, payload, authority, and determinism cases. The third hostile repair
adds future/expired/empty interval boundaries; future comparison and correction
lookahead; unknown freshness/stale missingness/coverage refusal; superseded theme
and saturation exclusion; exact derived saturation population/counts; and
dangling, self-referential, cyclic, cross-entity, or nonlinear epoch/actor
lineage attacks.
