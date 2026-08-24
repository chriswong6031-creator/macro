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

## Epoch identity and China actor extensions

Manager complexes, filers, and vehicles are immutable epochs with distinct
effective, valid, and knowable intervals; active/inactive/unresolved status;
resolution state; explicit decision mode (`discretionary`, `passive`,
`systematic`, `mixed`, or `unknown`); and append-only original/remap/correction
lineage. Raw actor strings and original ontology versions remain in history.
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
| Institutionalization / Saturation | typed complex presence/count or unavailable | eligible/excluded complex epochs | breadth/context only; no crowding gate or master score |

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
reliability, payload, authority, and determinism cases.
