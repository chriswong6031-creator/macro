# Evidence Foundation reference contract v1

`evidence_foundation.reference.v1` is the smallest shared language for pointing at
evidence already owned by another Macro intelligence system. It is a contract, not a
store. There is no `data/evidence_mesh/`, index, writer, scheduler, catalog mirror, or
cross-owner reader in K1.

The owner-native object remains truth. A reference carries only its immutable owner
identity, typed subject, native clocks, pointer provenance, correction/replay
semantics, relations, missingness, and an all-false authority envelope. It never
contains the native body. Consumers continue to use the owner-bound accessor named in
`vocabulary.v1.json`; `reader_kind` states honestly whether that symbol is a direct
read, a collection read requiring native-key selection, or a parser for caller-held
canonical bytes. K1 does not pretend a parser or materializer is a physical reader.

## Frozen files

- `reference.v1.schema.json` is the closed wire shape.
- `vocabulary.v1.json` is the versioned owner/identity/clock binding table.
- `lib/evidence_foundation.py` exports the one combined JSON-Schema plus semantic
  fail-closed validator. Its semantic pass enforces exact owner schema, identity type,
  pointer and clock bindings, v1 automatic-effect refusal, append/supersede lineage,
  and replay lookahead refusal.

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
   `native_digest` and `coverage_class` use explicit `unknown` states; neither is
   zero-filled or guessed.
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
9. **Replay is honest.** Every known cutoff is parsed even when the reference carries
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

K1 found no named PR or workstream committed to list, in one query, native objects
across at least three owner stores for one subject without importing owner engines.
The A0 Brain example is hypothetical and does not satisfy the gate. Therefore K1
freezes contracts and fixtures only. A future store requires a new named consumer,
Data OS persistence adjudication, a producer, owner program, native `asof_field`,
freshness SLA, and `config/synapse.yml` registration before any path is minted.
