# Evidence Foundation contracts v1

The K1 surface has three closed contracts: `EvidenceRef` points to one owner-native
object; `EvidenceBlock` is a bounded consumer projection over one or more refs; and
`EvidenceRecipe` is an ordered composition instruction for one named consumer job.
They are contracts, not stores. There is no `data/evidence_mesh/`, index, writer,
scheduler, catalog mirror, payload warehouse, or cross-owner reader in K1.

The owner-native object remains truth. A reference carries only its immutable owner
identity, typed subject, native clocks, pointer provenance, correction/replay
semantics, relations, missingness, and an all-false authority envelope. It never
contains the native body. Consumers continue to use the owner-bound accessor named in
`vocabulary.v1.json`; `reader_kind` states honestly whether that symbol is a direct
read, a collection read requiring native-key selection, or a parser for caller-held
canonical bytes. K1 does not pretend a parser or materializer is a physical reader.

## Frozen files

- `reference.v1.schema.json` is the closed wire shape.
- `block.v1.schema.json` is the closed consumer-projection shape.
- `recipe.v1.schema.json` is the closed, ordered composition-instruction shape.
- `vocabulary.v1.json` is the versioned owner/identity/clock binding table.
- `lib/evidence_foundation.py` exports the one combined JSON-Schema plus semantic
  fail-closed surface for refs, blocks, and recipes. Its semantic passes enforce exact
  owner schema, identity type and source-backed value grammar, coverage/replay
  capability, pointer and clock bindings, lossless block clocks, denominator receipts,
  authority/object-class separation, correction recompilation, lawful identity-join
  declarations that never substitute for resolution proof,
  ordered required/optional blocks, v1 automatic-effect refusal, append/supersede
  lineage, and replay lookahead refusal. Public validation always uses the validated
  repository vocabulary and accepts no caller-supplied vocabulary authority.

The schema and vocabulary version are both `1.0.0`. Evolution is additive within v1.
Renaming a field, repurposing an enum member, weakening all-false authority, or
changing a native clock binding requires v2.

## Laws

1. **Object class is explicit.** `world_observation`, `derived_view`,
   `system_belief`, `forward_claim`, and `instrument_state` are different claims.
   An instrument state is never a market verdict.
2. **Owner identity is reused.** There is no universal entity id and no
   `ticker_store_key`. `ISS:`/`SEC:`/listing identities come only from the produced
   Data OS master; earnings CIK/event ids, theme node ids (including `#<epoch>`),
   NCT, award, 13F, TXI, QLedger, and Market Memory ids remain owner-native. A CIK to
   listing/security join is lawful only through the Earnings `company_identity.v1`
   PIT alias. Symbol-directory plus `cik_map` is not a listing-security binding.
   Every owner identity field and every subject-key type carries a source-backed
   value grammar; matching the field label or scalar type is insufficient. Every
   subject admitted by an owner is also bound to a value carried by that object's
   native identity. When the pointer key cannot prove an issuer/security/node, the
   reference exposes only the native object ID; there is no successful `unbound`
   subject mode.
3. **Every clock keeps its native name.** The seven classes are
   `world_valid`, `source_published`, `knowable`, `observed`, `system_recorded`,
   `belief_or_build`, and `review_due`. `vocabulary.v1.json` binds each class to exact
   owner fields; every registered owner clock is present exactly once, including an
   explicit `unknown` value when its native value is unavailable. A reference cannot
   omit or silently relabel a timestamp. Each owner entry
   also binds its existing Synapse `asof_field`, or materializes `null` when that
   owner-native object is not registered. `null` is an adverse result, not permission
   to guess a replacement clock.
4. **Pointers, not bodies.** `pointer_only` is true and `body_embedded` false.
   `native_digest`, coverage, freshness basis, rights, and authority class are explicit.
   Unknown freshness/digest/rights stay unknown; none is zero-filled or guessed.
   `coverage_class` is exact per owner, not a caller-selected claim.
5. **Independence has three axes and v1 does not verify them.** Source independence,
   information novelty, and economic/mechanism independence are separately declared
   on every relation with `assessment=declarative_unverified`. Until an owner supplies
   typed deterministic lineage IDs, K1 neither detects nor certifies independence.
   Shared upstreams therefore cannot be promoted as independent corroboration merely
   because two projections differ.
6. **Automatic effects are unavailable in v1.** Every relation materializes
   `automatic_effect=false` and `deterministic_key=null`. The contract has no frozen
   typed owner-native deterministic-lineage key, so even an `exact_duplicate` label
   cannot make an arbitrary caller-authored key suppress, net, rank, or promote.
7. **Missingness is typed.** Absence never becomes numeric zero. `unsupported`,
   `stale`, `rights_blocked`, `unresolved_identity`, and the other closed reasons are
   actionable states, not values.
8. **Corrections append.** Amendments, restatements, source corrections,
   withdrawals, and superseding generations name predecessor references, append a new
   object, and preserve replay. The complete set of `corrects` or `supersedes` relation
   targets must exactly equal the predecessor set, and the wire states whether native
   clock ordering was verified or remains unverified. In-place mutation is forbidden.
9. **Replay is honest and owner-capable.** Every owner declares the exact supported
   mode-to-vintage combinations; a current-only source cannot masquerade as
   owner-native historical replay. Every known cutoff is parsed even when the reference carries
   no clock in that class. `historical_replay` carries typed cutoffs, code revision,
   input digest, and an available vintage state. FIF historical replay additionally
   requires known native `accepted_at` and `recorded_at` clocks. A clock beyond its
   same-class cutoff is refused;
   same-day date-versus-datetime comparisons are ambiguous in either direction unless
   a future contract supplies an explicit boundary. `current_rule_recomputation` is a
   different mode and may not be described as replay.
10. **Authority defaults down.** Missing authority is interpreted as no authority,
    but wire producers must materialize every boolean. `can_rank`, `can_gate`,
    `can_size`, `can_originate`, and `can_open_entry` are all literal false.

## EvidenceBlock

An `EvidenceBlock` names a consumer/job, a supported claim or question, the exact
reference IDs it projects, and the fact/deterministic/model/human class of the
projection. Its clock summary is lossless: every owner-native clock field/value/grain
is retained with its ref ID and `collapsed` is always false. Its denominator receipt
names total, included, excluded, missing, stale, rights-blocked, and fallback counts;
`complete` is illegal when any adverse count is non-zero.

Dependence is separate from row count. A block may include two refs while counting one
independent evidence leg when they share an upstream source. Conflict and correction
states never net automatically. A corrected ref requires a new block ID plus a
`recompiled` lineage receipt naming the prior block and invalidating reference; the
predecessor block is not rewritten. Probability is illegal without derivation and
calibration receipts. Permitted consumer classes and the all-false authority envelope
are materialized on every block.

## EvidenceRecipe

An `EvidenceRecipe` orders required and optional block specs for one consumer output.
Each spec freezes allowed owner stores, object classes, evidence class, reference
cardinality, absence behavior, and output mappings. Identity-join declarations must
exactly match the owner-approved vocabulary. A declaration names the only lawful
future bridge; it is not itself a resolution receipt. In particular,
CIK-to-security/listing joins may use only the Earnings `company_identity.v1` PIT
alias, and Theme-node-to-security joins may use only a validated Theme Graph identity
resolution row. The dated symbol-directory plus `cik_map` route fails closed.

The recipe freezes required refusal/degradation rules, deterministic dedup rules,
non-automatic dependence relations, denominator/dominant-degradation laws,
correction recompilation, confidence receipts, and no owner-payload copying.
`compile_recipe()` operates only on caller-supplied owner-reader results and returns an
in-memory `recipe_compilation_receipt.v1`; it persists no ref, block, owner payload, or
consumer output. In v1 the compile input has no validated bridge-object slot, so only
a reference carrying the exact canonical subject instance can enter composition.
Native-only or cross-type subjects are `identity_unresolved`: optional blocks are
excluded and degrade, while required blocks refuse. Caller-authored join triples can
never make them look resolved.

## AAPL golden composition

`aapl_security_state_recipe_valid.json` composes four owner families for the bounded
Market OS B1 candidate job: Earnings `event_workspace.v1` (required), a source-valid
fixture-only FIF packet, a subject-bearing Theme Graph edge belief, and a constructed
QLedger owner claim. The QLedger leg remains model authority and cannot be presented
as fact. The golden receipt is honestly `REFUSED / identity_unresolved`: all four
owner objects and their native clocks are present, but none carries the recipe's
canonical Data OS security ID and K1 has no validated bridge object in its compile
input. The denominator therefore records 0 included / 4 excluded /
4 identity-unresolved; no owner payload is copied.

The measured local fixture-reader/validation composition baseline (Darwin arm64,
Python 3.14.7, 100 iterations) was p50 164.225 ms, p95 168.261 ms, max 224.977 ms.
This is a contract/fixture measurement, not a production owner-I/O SLA. No commission
or current consumer names a latency requirement that it fails. A pointer index would
not turn an owner-native packet/claim/edge/event ID into a validated cross-type
identity bridge, so it cannot cure the refusal. Under the commission's frozen binary
store verdict, K1 therefore remains `NO_BUILD_DIRECT_READERS_SUFFICIENT` for owner
access while explicitly refusing the composed consumer output.

## Identity and deterministic reference id

`reference_id` is `efr_` plus the SHA-256 of canonical JSON for the entire reference
with `reference_id` removed. There is no reference write/run clock in the identity.
Native object clocks remain because they identify the pointed claim; adding a join
write clock would turn this pointer contract into a different observation-log object.

## Replay chronology mapping

The merged PIT replay harness maps without loss: session/effective ceiling to
`world_valid`; source publication/acceptance to `source_published`; public/source
availability to `knowable`; retrieval to `observed`; retained/recorded to
`system_recorded`; vintage commit/build belief to `belief_or_build`; and any review
deadline to `review_due`. Native first-seen fields retain their owner meaning rather
than sharing a global shortcut: GovRev and BioCatalyst first-seen are `knowable`.
Unknown native clocks remain explicit unknown values, except where an owner replay
contract explicitly requires them to be known.

## Physical-store decision

K1 found no authorized/committed PR or workstream whose direct owner-reader baseline
fails a named requirement that a physical pointer index can cure. The A0 Brain example
is hypothetical. Current main's later #6325 packet names Market OS B1/AAPL as a
candidate job, but explicitly keeps B1A `PREPARED_NOT_AUTHORIZED`. Its golden recipe
now refuses because a validated cross-type identity bridge is absent; a pointer store
would preserve that absence. Therefore K1 freezes contracts and fixtures only. A
future store requires a committed consumer,
measured failed requirement, Data OS persistence adjudication, a producer, owner
program, native `asof_field`, freshness SLA, and `config/synapse.yml` registration
before any path is minted.
